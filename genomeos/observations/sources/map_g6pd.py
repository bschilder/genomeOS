"""Malaria Atlas Project G6PD deficiency survey adapter (design §6, §8, §7.1a, P1).

The open georeferenced G6PD survey database behind Howes et al. 2012, published by MAP as the
``Explorer:G6PD_Data`` layer. It is the input to **golden test 2** (§8), which exists because
G6PD exercises X-linked inheritance and HbS does not.

**This is a phenotype, not a variant, and that distinction is load-bearing.** HbS is one allele
(rs334). G6PD deficiency is caused by roughly 200 different alleles — G6PD A-, Mediterranean,
Mahidol, Viangchan and many others — and these surveys measure *enzyme activity*, not genotype.
The ``variant_id`` written here is therefore a deliberately non-conforming composite identifier
rather than a coordinate-and-allele string, so that no reader mistakes it for a single variant.
Howes et al. modelled the aggregate deficiency allele frequency the same way, which is what makes
the parity comparison meaningful; but §6 keys artifacts by variant, and a composite does not fit
that model cleanly. See the issue linked from `COMPOSITE_NOTE`.

**Allele counts come from males only, and this is the central design choice.** Males are
hemizygous for X-linked loci, so a deficient male carries exactly one deficient allele out of
exactly one: ``ac = number_males_deficient`` over ``an = number_males`` is a direct allele
frequency requiring no assumption at all.

Females are excluded, not overlooked. A female recorded as "deficient" by an enzyme assay may be
homozygous *or* heterozygous with skewed X-inactivation, and those imply very different allele
frequencies. Resolving them needs an X-inactivation model the source cannot support, and guessing
would bias the frequency in an unknown direction. Howes et al. likewise built their estimates on
the hemizygous male data.

**Refusals, and why each exists.** Rows are refused with a stated reason and counted in the
returned report — never dropped silently (§12):

- ``no_male_denominator`` — no male counts, so no hemizygous allele frequency is derivable. This
  is the largest refusal by far and includes every female-only survey.
- ``deficient_exceeds_sampled`` — internally inconsistent; more deficient males than males.
- ``missing_coordinates`` — §6 places observations spatially; a row without a coordinate cannot
  be placed.
- ``admin0_centroid`` and ``admin1_centroid`` — **the subtle one.** MAP supplies ``area_size`` in
  km² for every row, and for most rows that area *is* the location uncertainty. But for an
  administrative centroid the coordinate is a placeholder for a whole administrative unit, and
  ``area_size`` is capped at about 3,800 km² across this entire export. A country or a province
  is one to two orders of magnitude larger than that cap, so ``area_size`` cannot express how
  little we know about where those people actually were. §6 gives ``uncertainty_radius_km`` no
  default, and there is no defensible one here, so these rows are refused. Admin2 and Admin3
  centroids are kept: districts and sub-districts are plausibly the size ``area_size`` reports,
  so the figure is not being asked to carry weight it cannot bear.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from genomeos.observations.schema import OBSERVATIONS_SCHEMA

SOURCE = "map_g6pd"

#: Not a coordinate-and-allele identifier, deliberately: G6PD deficiency is an enzyme phenotype
#: aggregating ~200 alleles, so a conforming `chr-pos-ref-alt` string would be a lie. The
#: `phenotype:` prefix is defined in `observations.schema` and is meant to be impossible to
#: mistake for a locus in a filename, a join key, or a glance at a table.
G6PD_VARIANT_ID = "phenotype:g6pd-deficiency"

COMPOSITE_NOTE = (
    "G6PD deficiency is an enzyme phenotype caused by ~200 alleles and assayed by activity, not "
    "genotype. §6 keys artifacts by variant; this is a composite. See the tracking issue."
)

#: Administrative centroids whose coordinate is a placeholder for an area far larger than the
#: capped `area_size` can describe. See the module docstring.
_INDEFENSIBLE_CENTROIDS = {
    "admin0 centroid": "admin0_centroid",
    "admin1 centroid": "admin1_centroid",
}


@dataclass(frozen=True)
class IngestReport:
    """What was kept, what was refused, and why. Printed by the build script."""

    total: int
    retained: int
    refusals: dict[str, int]
    #: Surveys that reported females but no males, and so contributed nothing. Tracked separately
    #: because it is a property of the source's design rather than a data defect.
    female_only: int = 0

    @property
    def retained_fraction(self) -> float:
        return self.retained / self.total if self.total else 0.0

    def __str__(self) -> str:
        lines = [f"{self.retained}/{self.total} surveys retained ({self.retained_fraction:.0%})"]
        if self.female_only:
            lines.append(f"  {self.female_only} female-only surveys carry no hemizygous count")
        for reason, count in sorted(self.refusals.items(), key=lambda kv: -kv[1]):
            lines.append(f"  refused {count:>5}  {reason}")
        return "\n".join(lines)


def _radius_km(area_size: object) -> float:
    """Radius of a circle with the survey's reported area.

    MAP reports `area_size` in km² for every row of this layer, so unlike the HbS layer there is
    no area *class* to translate and no unclassed rows to give a coarse default to.
    """
    return math.sqrt(float(area_size) / math.pi)


def _population_id(survey_id: object) -> str:
    """One id per survey *site* — this is a location, not a cohort."""
    return f"map-g6pd-{int(survey_id)}"


def _cohort_id(citation: object, survey_id: object) -> str:
    """One id per contributing *study*.

    The G6PD layer has no study accession column, so the citation string is the only study
    identity available; 910 usable surveys come from far fewer publications, which is what keeps
    the §7.1d cohort effect estimable rather than collapsing to one level per observation.
    Unattributed rows become singleton cohorts rather than being pooled with unrelated surveys.
    """
    if isinstance(citation, str) and citation.strip():
        return f"map-g6pd-study-{citation.strip()[:120]}"
    return f"map-g6pd-study-unattributed-{int(survey_id)}"


def load(path: Path, ingest_version: str) -> tuple[pd.DataFrame, IngestReport]:
    """Read the MAP G6PD WFS export into observations, with a refusal report.

    Returns `(observations, report)`. The observations validate against `OBSERVATIONS_SCHEMA`;
    the report names every refusal so a shrinking corpus is visible rather than silent.
    """
    raw = pd.read_csv(path)
    total = len(raw)
    keep = pd.Series(True, index=raw.index)
    refusals: dict[str, int] = {}

    def refuse(mask: pd.Series, reason: str) -> None:
        newly = mask & keep
        count = int(newly.sum())
        if count:
            refusals[reason] = refusals.get(reason, 0) + count
            keep.loc[newly] = False

    refuse(raw[["latitude", "longitude"]].isna().any(axis=1), "missing_coordinates")

    males = pd.to_numeric(raw["number_males"], errors="coerce")
    deficient = pd.to_numeric(raw["number_males_deficient"], errors="coerce")
    females = pd.to_numeric(raw["number_females"], errors="coerce")
    no_males = males.isna() | (males <= 0)
    female_only = int((no_males & females.gt(0)).sum())

    refuse(no_males | deficient.isna(), "no_male_denominator")
    refuse(deficient > males, "deficient_exceeds_sampled")

    area_class = raw["area_type"].astype("string").str.strip().str.lower()
    for label, reason in _INDEFENSIBLE_CENTROIDS.items():
        refuse(area_class.eq(label), reason)
    refuse(raw["area_size"].isna() | (pd.to_numeric(raw["area_size"], errors="coerce") <= 0),
           "missing_area_size")

    rows = raw[keep]
    obs = pd.DataFrame(
        {
            "variant_id": G6PD_VARIANT_ID,
            # No rsid: a composite phenotype has no single dbSNP identifier, and inventing one
            # would let it join against genotype data it is not comparable with.
            # index= matters: the other columns carry the filtered frame's original index,
            # and a Series built with a fresh RangeIndex would be aligned by union rather
            # than positionally, silently lengthening the frame.
            "rsid": pd.Series([pd.NA] * len(rows), index=rows.index, dtype="string[pyarrow]"),
            "population_id": rows["id"].map(_population_id),
            "lat": rows["latitude"].astype(float),
            "lon": rows["longitude"].astype(float),
            "radius_km": rows["area_size"].map(_radius_km).astype(float),
            # Hemizygous: one allele per male, so the count and the denominator are both in males.
            "ac": deficient[keep].astype(int),
            "an": males[keep].astype(int),
            "source": SOURCE,
            # Not "genotype". These surveys measure enzyme activity, and the distinction matters:
            # an activity assay detects the phenotype whatever allele caused it, and its
            # sensitivity varies with the assay used.
            "assay": "enzyme_activity",
            "date_lower": 0,
            "date_upper": 0,
            "sampling_design": "population_random",
            "disease_ascertainment_excluded": False,
            "cohort_id": [
                _cohort_id(citation, sid)
                for citation, sid in zip(rows["citation"], rows["id"], strict=True)
            ],
            "ingest_version": ingest_version,
        }
    )
    validated = OBSERVATIONS_SCHEMA.validate(obs.reset_index(drop=True))
    return validated, IngestReport(
        total=total, retained=len(validated), refusals=refusals, female_only=female_only
    )
