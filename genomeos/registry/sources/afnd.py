"""AFND registry adapter (design §6, §7.1, P0) — the Allele Frequency Net Database.

AFND compiles HLA/KIR/MIC/cytokine frequencies for 1,324 populations and ~4.5M individuals, and
prints a coordinate on every population page. It is immunogenetics only, but it roughly doubles
the registry's population count on its own and is the deepest georeferenced frequency corpus per
locus that exists (issue #3, section A).

**Access and licence, checked 2026-08-25 — this is why the adapter is fixture-driven.**

- AFND publishes **no licence**. The footer's "Licensing" link resolves to ``contact.asp``, which
  carries only a disclaimer and a privacy policy, and the pages are marked "©2003-2026 The Allele
  Frequency Net Database". re3data records the repository as public domain
  (https://www.re3data.org/repository/r3d100011904), but that is third-party catalogue metadata,
  not a grant from AFND.
- There is **no bulk download**. The documented programmatic route is "Automated Access"
  (``extaccess.asp``), a URL-parameter convention for *linking a search* from an external site,
  conditioned on "If you are using this facility please cite our database in your website". It
  returns rendered pages, not data files.
- The frequency tables on a population page are **session-gated**: fetched without a login they
  render "Access Denied. Your session has expired or you have not logged in yet."
- Population *metadata* — the fields this adapter needs — does render publicly at
  ``pop6001c.asp?pop_id=N``, one page per population, with no export.

AGENTS.md requires the licence to be checked before ingesting, and names AFND among the panels
whose derived artifacts may not be redistributed until #66 is settled. With no licence, no bulk
route, and 1,324 separate pages, harvesting the corpus is not something this adapter does: there
is deliberately no ``scripts/fetch_afnd.py``. The adapter is written against AFND's documented
field schema and driven by ``tests/fixtures/afnd_populations.tsv``; **it has never been run
against the full AFND corpus.** Obtaining that corpus is a permission conversation with AFND, not
a code change.

**Input.** One row per AFND population, TSV, with columns named for AFND's own field labels on
``pop6001c.asp`` — ``Population:``, ``Latitude:``, ``Longitude:``, ``Family:``, ``Urban/Rural:``
and, under Sample Data, ``Source:`` — plus ``pop_id``, the accession in that page's URL::

    pop_id  population  latitude  longitude  urban_rural  family  sample_source

Coordinates stay in AFND's printed sexagesimal form (``6º 25' S``) rather than being converted
upstream, because the printed precision is what bounds the coordinate and converting first throws
it away.

**``uncertainty_radius_km`` has no default (§6), so it is derived and stated per row**::

    radius = max(sampling-area extent, coordinate-precision floor)

*Sampling-area extent* comes from AFND's own ``Urban/Rural`` controlled vocabulary
(``datasets.asp`` §1c: "Urban (Cities, towns)", "Rural (Villages, hamlets)", "Urban and Rural",
"Unknown"). §7 places each observation as a disc of this radius, so a too-large radius spreads an
observation's evidence and makes it *less* influential while a too-small one lets a diffuse
sample act as a pinpoint measurement — erring coarse is the safe direction, the same reasoning as
``observations.sources.map_surveys``. A village is the same kind of object HGDP places at 50 km
and takes the same figure; a city draws on a metropolitan catchment; a sample AFND records as
spanning both settlement types is bounded only regionally. **"Unknown" is refused, not
defaulted.**

*Coordinate-precision floor.* AFND prints coordinates sexagesimally at whatever precision the
submitter supplied, and much of the corpus is degrees-only. The floor is the radius of the disc
containing the printed quantisation cell — half the diagonal of a cell ``q`` tall and
``q·cos(lat)`` wide, one arcminute of latitude being one nautical mile (1.852 km) by definition.
Trailing zeros are not significant figures, so ``8º 0' N`` is read as degree precision (a ~78 km
floor at that latitude) rather than as an exact arcminute. At degree precision the floor exceeds
every locality extent below "urban and rural", which is the point: a coordinate cannot be more
certain than the way it was written down.

**``location_type``.** AFND's ``Family:`` field is the only per-population statement it makes
about whether the coordinate is where the population is *from* rather than merely where it was
collected. "Grandparents live at same location" is that statement and yields ``ancestral``;
"Parents live in the same location" (two generations) and "Not known" are not, and §4's warning
about diaspora sampling sites means the default direction has to be ``sampling``.

**Ascertainment (§7.1) — recorded here, not invented downstream.** AFND's ``Source:`` field is a
controlled vocabulary (``datasets.asp`` §1f) and is exactly the ascertainment §7.1 needs: much of
the corpus is bone-marrow, blood, stem-cell, cord-blood and solid-organ donor registries, which
exclude significant disease by donor-eligibility policy, plus disease-study patients and their
controls. ``POPULATIONS_SCHEMA`` has no ascertainment columns — they belong to
``OBSERVATIONS_SCHEMA`` (P1) — so this module cannot emit them. Instead it

- publishes the mapping as ``SAMPLING_DESIGN_BY_SOURCE`` / ``sampling_design_for``, so a P1 AFND
  observations adapter consumes a reviewed table rather than inventing a design; and
- **refuses** any population whose ``Source:`` is blank, "Other", or outside the vocabulary. Such
  a population can never yield a schema-valid observation, so admitting its coordinate would only
  invite a later adapter to substitute a default. Folding "Other" into ``convenience`` would be
  worse than refusing: §7.1a identifies ``β_design`` by contrast *between* designs, so pouring
  populations of unrecorded design into a named level biases that level's estimate.

"Anthropology Study" maps to ``convenience``, not ``population_random``. These are community
panels recruited through local contact — the same kind of object as HGDP, not surveys drawn from
a sampling frame. ``population_random`` is the anchor that identifies ``β_design`` (see
``observations.sources.map_surveys``), and over-claiming it would corrupt the anchor. Disease
cohorts, conversely, are **recorded rather than refused**: a clinical cohort is a valid
observation whose bias ``β_design`` exists to correct.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

SOURCE = "afnd"

PROVENANCE_DOI = "10.1093/nar/gkz1029"  # Gonzalez-Galarza et al. 2020, NAR 48:D783-8
POPULATION_URL = "https://www.allelefrequencies.net/pop6001c.asp?pop_id={pop_id}"

# AFND spans indigenous and minority populations across all twelve of its geographic regions, and
# AGENTS.md names it in the open redistribution question (#66), so the notice is panel-wide
# rather than conditional on an ethnicity label.
BIOCULTURAL_NOTICE = (
    "AFND aggregates immunogenetic surveys including indigenous and minority populations. "
    "Reuse governed by the CARE Principles; see https://www.gida-global.org/careprinciples"
)

REQUIRED_COLUMNS: tuple[str, ...] = (
    "pop_id",
    "population",
    "latitude",
    "longitude",
    "urban_rural",
    "family",
    "sample_source",
)

_POPULATION_COLUMNS: tuple[str, ...] = (
    "population_id",
    "lat",
    "lon",
    "uncertainty_radius_km",
    "location_type",
    "provenance",
    "biocultural_notice",
    "registry_version",
)

#: One arcminute of latitude is one nautical mile, by the definition of the nautical mile.
ARCMIN_KM = 1.852

#: AFND's `Urban/Rural` vocabulary mapped to the radius of the disc it bounds. See the module
#: docstring for why erring coarse is the safe direction, and why "Unknown" is absent.
SAMPLING_AREA_RADIUS_KM: dict[str, float] = {
    "rural": 50.0,  # villages and hamlets: the object HGDP places at 50 km
    "urban": 100.0,  # a city or town draws on a metropolitan catchment
    "urban and rural": 250.0,  # explicitly not one settlement, so bounded only regionally
}

#: AFND's `Source:` vocabulary mapped onto design §7.1's `sampling_design` enum and the
#: `disease_ascertainment_excluded` flag. Donor registries are flagged because donor-eligibility
#: criteria remove significant disease by policy, which is exactly what §6 means by "any panel
#: that removed disease cohorts"; disease-study controls are flagged because a control is by
#: construction free of the study disease. Both display forms AFND uses are keyed — the CV page
#: says "Blood Donor Registry" where the population pages print "Blood Donor" — and the
#: vocabulary's own "Coord Blood Donors" spelling of cord blood is kept alongside the correction.
SAMPLING_DESIGN_BY_SOURCE: dict[str, tuple[str, bool]] = {
    "anthropology study": ("convenience", False),
    "blood donor": ("healthy_reference", True),
    "blood donor registry": ("healthy_reference", True),
    "bone marrow registry": ("healthy_reference", True),
    "coord blood donors": ("healthy_reference", True),
    "cord blood donors": ("healthy_reference", True),
    "solid organ unrelated donors": ("healthy_reference", True),
    "stem cell donors": ("healthy_reference", True),
    "controls for disease study": ("clinical_control", True),
    "disease study patients": ("clinical_case", False),
}

#: Tested in the order listed, so the reason reported is the most fundamental defect present.
REFUSAL_REASONS: tuple[str, ...] = (
    "unusable_pop_id",
    "missing_population_name",
    "unreadable_latitude",
    "unreadable_longitude",
    "no_sampling_area",
    "unmappable_ascertainment",
)

_AXES: dict[str, tuple[str, float]] = {"lat": ("NS", 90.0), "lon": ("EW", 180.0)}

# AFND writes the degree sign as U+00BA on its pages; U+00B0 is accepted too. Minutes and seconds
# are optional because the corpus carries all three precisions.
_DMS = re.compile(
    r"^(?P<deg>\d{1,3})\s*[º°]\s*"
    r"(?:(?P<min>\d{1,2})\s*'\s*)?"
    r"(?:(?P<sec>\d{1,2}(?:\.\d+)?)\s*(?:''|″|\")\s*)?"
    r"(?P<hemi>[NSEW])$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Coordinate:
    """One axis of an AFND coordinate, with the precision it was printed at."""

    degrees: float
    #: Size of the printed quantisation step, in degrees: 1, 1/60 or 1/3600.
    quantum_deg: float


@dataclass(frozen=True)
class RegistryReport:
    """What was kept, what was refused, and why. Printed by scripts/build_registry.py."""

    total: int
    retained: int
    refusals: dict[str, int]

    @property
    def retained_fraction(self) -> float:
        return self.retained / self.total if self.total else 0.0

    def __str__(self) -> str:
        lines = [f"{self.retained}/{self.total} populations retained ({self.retained_fraction:.0%})"]
        for reason, count in sorted(self.refusals.items(), key=lambda kv: -kv[1]):
            lines.append(f"  refused {count:>5}  {reason}")
        return "\n".join(lines)


def normalise(value: object) -> str:
    """Lower-case an AFND controlled-vocabulary value and drop its parenthetical gloss.

    `"Rural (Villages, hamlets)"` -> `"rural"`; the CV page glosses the terms that the population
    pages print bare, and both spellings occur.
    """
    if not isinstance(value, str):
        return ""
    return re.sub(r"\s+", " ", re.split(r"\(", value, maxsplit=1)[0].strip().lower())


def parse_dms(text: object, *, axis: str) -> Coordinate | None:
    """AFND's printed sexagesimal coordinate, or None if it is blank or malformed.

    Trailing zeros are not significant figures: `8º 0' N` is degree precision, not an exact
    arcminute. Reading it the other way would understate the extent of a coordinate that was
    rounded to the degree, and understating extent is the unsafe direction (§7).
    """
    hemispheres, limit = _AXES[axis]
    if not isinstance(text, str):
        return None
    match = _DMS.match(re.sub(r"\s+", " ", text.strip()))
    if match is None or match["hemi"].upper() not in hemispheres:
        return None

    minutes = None if match["min"] is None else int(match["min"])
    seconds = None if match["sec"] is None else float(match["sec"])
    if seconds:
        quantum = 1.0 / 3600.0
    elif minutes:
        quantum = 1.0 / 60.0
    else:
        quantum = 1.0

    degrees = int(match["deg"]) + (minutes or 0) / 60.0 + (seconds or 0.0) / 3600.0
    if degrees > limit:
        return None
    return Coordinate(
        degrees=-degrees if match["hemi"].upper() in "SW" else degrees, quantum_deg=quantum
    )


def precision_radius_km(lat: Coordinate, lon: Coordinate) -> float:
    """Radius of the disc containing the printed coordinate's quantisation cell.

    Half the diagonal of a cell `lat.quantum_deg` tall and `lon.quantum_deg · cos(lat)` wide.
    """
    lat_km = lat.quantum_deg * 60.0 * ARCMIN_KM
    lon_km = lon.quantum_deg * 60.0 * ARCMIN_KM * math.cos(math.radians(lat.degrees))
    return 0.5 * math.hypot(lat_km, lon_km)


def sampling_design_for(sample_source: object) -> tuple[str, bool] | None:
    """AFND's `Source:` as `(sampling_design, disease_ascertainment_excluded)`, or None.

    None means AFND records no usable ascertainment for the population — blank, "Other", or a
    value outside the controlled vocabulary. A P1 AFND observations adapter must consume this
    rather than inventing a design; §7.1 gives those two fields no default.
    """
    return SAMPLING_DESIGN_BY_SOURCE.get(normalise(sample_source))


def location_type_for(family: object) -> str:
    """`ancestral` only where AFND records three generations resident at the locality."""
    return "ancestral" if normalise(family).startswith("grandparents") else "sampling"


def population_id(pop_id: str) -> str:
    """`"1986"` -> `"afnd-1986"` — AFND's accession, as `map_surveys` keys on the survey id.

    The population *name* is not the key: AFND names are long, occasionally repeat, and are
    already carried losslessly in the aliases table, which is what the aliases table is for.
    """
    return f"{SOURCE}-{pop_id}"


def load(path: Path, registry_version: str) -> tuple[pd.DataFrame, pd.DataFrame, RegistryReport]:
    """Load an AFND population export into registry rows, plus a report of what was refused."""
    # Everything as text, blanks left as empty strings: pandas would otherwise read `pop_id` as a
    # float (`1986.0`, a different accession) and turn AFND's blank fields into NaN, which reads
    # as a value rather than as an absence.
    raw = pd.read_csv(path, sep="\t", dtype=str, keep_default_na=False)
    missing = set(REQUIRED_COLUMNS) - set(raw.columns)
    if missing:
        raise ValueError(f"{path}: missing required columns {sorted(missing)}")

    refusals: dict[str, int] = {}
    records: list[dict[str, object]] = []
    labels: list[str] = []

    def refuse(reason: str) -> None:
        refusals[reason] = refusals.get(reason, 0) + 1

    for row in raw.to_dict("records"):
        accession = str(row["pop_id"]).strip()
        if not accession.isdigit():
            refuse("unusable_pop_id")
            continue
        name = str(row["population"]).strip()
        if not name:
            refuse("missing_population_name")
            continue
        lat = parse_dms(row["latitude"], axis="lat")
        if lat is None:
            refuse("unreadable_latitude")
            continue
        lon = parse_dms(row["longitude"], axis="lon")
        if lon is None:
            refuse("unreadable_longitude")
            continue
        # §6 gives uncertainty_radius_km no default, so a population AFND has not placed in a
        # settlement class has no defensible extent and is refused rather than assigned one.
        extent_km = SAMPLING_AREA_RADIUS_KM.get(normalise(row["urban_rural"]))
        if extent_km is None:
            refuse("no_sampling_area")
            continue
        if sampling_design_for(row["sample_source"]) is None:
            refuse("unmappable_ascertainment")
            continue

        records.append(
            {
                "population_id": population_id(accession),
                "lat": lat.degrees,
                "lon": lon.degrees,
                "uncertainty_radius_km": max(extent_km, precision_radius_km(lat, lon)),
                "location_type": location_type_for(row["family"]),
                "provenance": f"{PROVENANCE_DOI} {POPULATION_URL.format(pop_id=accession)}",
                "biocultural_notice": BIOCULTURAL_NOTICE,
                "registry_version": registry_version,
            }
        )
        labels.append(name)

    # Columns stated explicitly so a fully-refused input still returns a schema-shaped frame
    # rather than an empty one that fails validation for the wrong reason.
    populations = pd.DataFrame(records, columns=list(_POPULATION_COLUMNS))
    aliases = pd.DataFrame(
        {"population_id": populations["population_id"], "source": SOURCE, "label": labels}
    )
    report = RegistryReport(total=len(raw), retained=len(populations), refusals=refusals)
    return populations, aliases, report

