"""Malaria Atlas Project HbS survey adapter (design §6, §8, P1).

The open georeferenced HbS survey database behind Piel et al. 2010/2013. Two reasons it matters
disproportionately for its size:

1. It is the input to **golden test 1** (HbS parity, §8) — the only end-to-end validation of the
   pipeline against independently published national estimates.
2. These are population screening surveys, so they are the corpus's reference
   `population_random` design. `β_design` (§7.1a) is identified by contrast *between* designs, so
   without a well-ascertained anchor the correction is unidentifiable.

Survey sites carry their own point coordinates, so this adapter needs no registry join. Each
site is its own `cohort_id`: survey-level effects are exactly what `β_cohort` absorbs (§7.1d).
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from genomeos.observations.schema import OBSERVATIONS_SCHEMA

SOURCE = "map_surveys"
HBS_VARIANT_ID = "chr11-5227002-T-A"  # rs334, HBB Glu6Val, GRCh38
SURVEY_RADIUS_KM = 25.0  # survey catchment; MAP models these as point-referenced with a locality


def _cohort_id(site_name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(site_name).strip().lower()).strip("-")
    return f"map-hbs-{slug}"


def load(path: Path, ingest_version: str) -> pd.DataFrame:
    raw = pd.read_csv(path, sep="\t")
    missing = {"site_name", "latitude", "longitude", "AC", "AN"} - set(raw.columns)
    if missing:
        raise ValueError(f"{path}: missing required columns {sorted(missing)}")

    obs = pd.DataFrame(
        {
            "variant_id": HBS_VARIANT_ID,
            "rsid": "rs334",
            "population_id": raw["site_name"].map(_cohort_id),
            "lat": raw["latitude"].astype(float),
            "lon": raw["longitude"].astype(float),
            "radius_km": SURVEY_RADIUS_KM,
            "ac": raw["AC"].astype(int),
            "an": raw["AN"].astype(int),
            "source": SOURCE,
            "assay": "genotype",
            "date_lower": 0,
            "date_upper": 0,
            "sampling_design": "population_random",
            "disease_ascertainment_excluded": False,
            "cohort_id": raw["site_name"].map(_cohort_id),
            "ingest_version": ingest_version,
        }
    )
    return OBSERVATIONS_SCHEMA.validate(obs)
