"""Malaria Atlas Project HbS survey adapter (design §6, §8, §7.1a, P1).

The open georeferenced HbS survey database behind Piel et al. 2010/2013, published by MAP as the
``Explorer:HbS_Data`` layer. Two reasons it matters disproportionately for its size:

1. It is the input to **golden test 1** (HbS parity, §8) — the only end-to-end validation of the
   pipeline against independently published national estimates.
2. These are population screening surveys, so they are the corpus's reference
   ``population_random`` design. ``β_design`` (§7.1a) is identified by contrast *between*
   designs, so without a well-ascertained anchor the correction is unidentifiable.

Survey sites carry their own coordinates, so this adapter needs no registry join.

``cohort_id`` is the **contributing study**, not the survey site. The two differ: 332 retained
surveys come from 151 studies, and 41 studies contribute more than one site. Keying cohorts by
site would give one cohort level per observation, which is not a cohort effect at all — it is an
observation-level overdispersion term, unidentifiable as the study-level effect §7.1d wants and
free to absorb the spatial signal the GP exists to explain. Grouping by study leaves cohort
effects estimable, because replicated studies supply the within-cohort contrast that identifies
them.

Allele counts come from the reported genotypes: ``ac = hbas + 2·hbss`` over ``an = 2·sample_size``.

**Refusals, and why each exists.** The source is a literature compilation spanning decades, and
several failure modes would silently produce wrong frequencies rather than obvious errors. Rows
are refused with a stated reason and counted in the returned report — never dropped silently
(§12). The reasons are not hypothetical; each was found in the real data:

- ``partially_genotyped`` — the reported genotypes account for far less of the sample than
  ``sample_size``. The motivating case is a US newborn-screening row where 47,276 of 3,212,374
  sampled infants have genotypes, because only screen-positives were typed. Taking the genotyped
  subset as the denominator gives an HbS allele frequency of 0.31 for the United States; taking
  ``sample_size`` is right there but wrong where the shortfall is instead other haemoglobin
  variants. The denominator is genuinely ambiguous, so the row is refused.
- ``genotypes_exceed_sample`` — internally inconsistent; the genotypes total more than the
  stated sample.
- ``incomplete_genotypes`` — one of HbAA/HbAS/HbSS is absent, so no allele count is derivable.
  Treating a missing ``hbss`` as zero would bias frequencies downward exactly where the variant
  is common.
- ``no_area_type`` and ``unbounded_area`` — §6 gives ``uncertainty_radius_km`` no default, and
  §7 places each observation as a disc of that radius rather than as a point. A survey with no
  stated extent, or one recorded only as ">100 km²" with no upper bound, cannot be placed
  honestly: understating the extent would let a diffuse survey act as a pinpoint measurement.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from genomeos.observations.schema import OBSERVATIONS_SCHEMA

SOURCE = "map_surveys"
HBS_VARIANT_ID = "chr11-5227002-T-A"  # rs334, HBB Glu6Val, GRCh38
RSID = "rs334"

#: MAP's area classes, mapped to the radius of a circle of the class's upper-bound area. The
#: upper bound is used because a survey labelled "≤10 km²" may occupy any of it.
_AREA_KM2_UPPER: dict[str, float] = {
    "point": 10.0,
    "wide-area": 25.0,
    "small polygon": 100.0,
}
_UNBOUNDED_AREA = "large polygon"

#: ">100 km²" has no upper bound, and 301 otherwise-usable surveys carry no area class at all.
#: Refusing both discarded 388 real measurements over a metadata gap. Instead they are assigned
#: a deliberately coarse extent: §7 places each observation as a disc of this radius, so a
#: too-large radius makes a survey *less* influential and spreads its evidence, while a too-small
#: one lets a diffuse survey act as a pinpoint measurement. Erring coarse is the safe direction,
#: and the assumption is visible here rather than buried in a default.
_UNBOUNDED_AREA_KM2 = 500.0
_UNKNOWN_AREA_KM2 = 500.0

#: Minimum share of `sample_size` that the reported genotypes must account for.
DEFAULT_MIN_GENOTYPED_FRACTION = 0.9

REFUSAL_REASONS: tuple[str, ...] = (
    "incomplete_genotypes",
    "missing_coordinates",
    "missing_sample_size",
    "genotypes_exceed_sample",
    "partially_genotyped",
    "excluded_from_piel_2013",
)


@dataclass(frozen=True)
class IngestReport:
    """What was kept, what was refused, and why. Printed by the build script."""

    total: int
    retained: int
    refusals: dict[str, int]
    #: Surveys whose hbss was fixed at zero by subtraction rather than by assumption.
    derived_hbss: int = 0

    @property
    def retained_fraction(self) -> float:
        return self.retained / self.total if self.total else 0.0

    def __str__(self) -> str:
        lines = [f"{self.retained}/{self.total} surveys retained ({self.retained_fraction:.0%})"]
        if self.derived_hbss:
            lines.append(f"  {self.derived_hbss} hbss values derived by subtraction (hbaa+hbas==n)")
        for reason, count in sorted(self.refusals.items(), key=lambda kv: -kv[1]):
            lines.append(f"  refused {count:>5}  {reason}")
        return "\n".join(lines)


def _radius_km(area_type: object) -> float:
    """Radius of a circle with the area class's upper-bound area.

    Unclassed and unbounded surveys get a deliberately coarse extent rather than a refusal; see
    the note on `_UNKNOWN_AREA_KM2`.
    """
    if not isinstance(area_type, str) or not area_type.strip():
        return math.sqrt(_UNKNOWN_AREA_KM2 / math.pi)
    key = re.split(r"[(]", area_type.strip().lower())[0].strip()
    if key.startswith(_UNBOUNDED_AREA):
        return math.sqrt(_UNBOUNDED_AREA_KM2 / math.pi)
    area = _AREA_KM2_UPPER.get(key, _UNKNOWN_AREA_KM2)
    return math.sqrt(area / math.pi)


def _population_id(survey_id: object) -> str:
    """One id per survey *site* — this is a location, not a cohort."""
    return f"map-hbs-{int(survey_id)}"


def _cohort_id(study: object, survey_id: object) -> str:
    """One id per contributing *study*; see the module docstring on why not per site.

    Falls back to the survey id where a study accession is missing, so such a row becomes its own
    singleton cohort rather than being silently pooled with unrelated surveys.
    """
    if isinstance(study, str) and study.strip():
        return f"map-study-{study.strip()}"
    return f"map-study-unaccessioned-{int(survey_id)}"


def load(
    path: Path,
    ingest_version: str,
    *,
    piel_2013_subset_only: bool = True,
    min_genotyped_fraction: float = DEFAULT_MIN_GENOTYPED_FRACTION,
) -> tuple[pd.DataFrame, IngestReport]:
    """Load the MAP HbS survey export into observations, plus a report of what was refused.

    `piel_2013_subset_only` keeps the rows MAP flags as used in the 2013 population-estimates
    paper, which is the comparison set golden test 1 is scored against (§8).
    """
    if not 0.0 < min_genotyped_fraction <= 1.0:
        raise ValueError("min_genotyped_fraction must be in (0, 1]")

    raw = pd.read_csv(path)
    required = {
        "id", "latitude", "longitude", "sample_size", "hbaa", "hbas", "hbss", "area_type",
        "source",
    }
    missing = required - set(raw.columns)
    if missing:
        raise ValueError(f"{path}: missing required columns {sorted(missing)}")

    total = len(raw)
    refusals: dict[str, int] = {}
    keep = pd.Series(True, index=raw.index)

    # Where the reported genotypes already account for the whole sample, hbss is determined by
    # subtraction: it must be zero. That is arithmetic, not the "assume blank means zero"
    # judgement #89 asks an expert to rule on, and it recovers 317 surveys that were being
    # refused for a value the data already fixes.
    raw = raw.copy()
    derivable = (
        raw["hbss"].isna()
        & raw["hbaa"].notna()
        & raw["hbas"].notna()
        & raw["sample_size"].notna()
        & ((raw["hbaa"] + raw["hbas"]) == raw["sample_size"])
    )
    raw.loc[derivable, "hbss"] = 0.0
    derived_hbss = int(derivable.sum())

    def refuse(mask: pd.Series, reason: str) -> None:
        hit = mask & keep
        if hit.any():
            refusals[reason] = refusals.get(reason, 0) + int(hit.sum())
            keep.loc[hit] = False

    if piel_2013_subset_only and "population_estimates" in raw.columns:
        refuse(raw["population_estimates"].ne("YES"), "excluded_from_piel_2013")

    # Order matters: the reason reported should be the most fundamental defect. A row whose
    # genotypes exceed its sample is broken data whether or not it also lacks an area class.
    refuse(raw[["hbaa", "hbas", "hbss"]].isna().any(axis=1), "incomplete_genotypes")
    refuse(raw[["latitude", "longitude"]].isna().any(axis=1), "missing_coordinates")
    refuse(raw["sample_size"].isna(), "missing_sample_size")

    genotyped = raw[["hbaa", "hbas", "hbss"]].sum(axis=1)
    refuse(genotyped > raw["sample_size"], "genotypes_exceed_sample")
    refuse(genotyped < min_genotyped_fraction * raw["sample_size"], "partially_genotyped")

    radius = raw["area_type"].map(_radius_km)

    rows = raw[keep]
    obs = pd.DataFrame(
        {
            "variant_id": HBS_VARIANT_ID,
            "rsid": RSID,
            "population_id": rows["id"].map(_population_id),
            "lat": rows["latitude"].astype(float),
            "lon": rows["longitude"].astype(float),
            "radius_km": radius[keep].astype(float),
            "ac": (rows["hbas"] + 2 * rows["hbss"]).astype(int),
            "an": (2 * rows["sample_size"]).astype(int),
            "source": SOURCE,
            "assay": "genotype",
            "date_lower": 0,
            "date_upper": 0,
            "sampling_design": "population_random",
            "disease_ascertainment_excluded": False,
            "cohort_id": [
                _cohort_id(study, sid)
                for study, sid in zip(rows["source"], rows["id"], strict=True)
            ],
            "ingest_version": ingest_version,
        }
    )
    validated = OBSERVATIONS_SCHEMA.validate(obs.reset_index(drop=True))
    return validated, IngestReport(
        total=total, retained=len(validated), refusals=refusals, derived_hbss=derived_hbss
    )
