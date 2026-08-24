"""gnomAD HGDP+1KG harmonized callset adapter (design §6, P1).

The harmonized HGDP+1kGP callset (4,094 genomes, 80 populations, CC0) is the only open resource
that is simultaneously whole-genome and georeferenceable per-population — design §15's
recommended starting point.

Ascertainment (§7.1a): gnomAD excludes individuals with severe pediatric disease *and their
first-degree relatives* by policy, so every row is `healthy_reference` with
`disease_ascertainment_excluded = True`. That flag is what lets `β_design` be estimated later;
it is not a caveat in a docstring, it is data.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from genomeos.observations.schema import OBSERVATIONS_SCHEMA

SOURCE = "gnomad_hgdp_1kg"
ALIAS_SOURCES = ("hgdp", "onekg")
COHORT_ID = "gnomad-v4-hgdp-1kg"


class UnmappedPopulationError(ValueError):
    """A source population label has no entry in the registry, so it has no coordinate."""


def load(
    path: Path,
    populations: pd.DataFrame,
    aliases: pd.DataFrame,
    ingest_version: str,
) -> pd.DataFrame:
    raw = pd.read_csv(path, sep="\t")

    lookup = aliases[aliases["source"].isin(ALIAS_SOURCES)].set_index("label")["population_id"]
    unmapped = sorted(set(raw["pop_label"]) - set(lookup.index))
    if unmapped:
        raise UnmappedPopulationError(
            f"{path}: population labels absent from the registry "
            f"(add them to P0 first): {unmapped}"
        )

    coords = populations.set_index("population_id")[["lat", "lon", "uncertainty_radius_km"]]
    pop_ids = raw["pop_label"].map(lookup)

    obs = pd.DataFrame(
        {
            "variant_id": raw["variant_id"].astype(str),
            "rsid": raw["rsid"].astype(str),
            "population_id": pop_ids.to_numpy(),
            "lat": coords.loc[pop_ids, "lat"].to_numpy(),
            "lon": coords.loc[pop_ids, "lon"].to_numpy(),
            "radius_km": coords.loc[pop_ids, "uncertainty_radius_km"].to_numpy(),
            "ac": raw["AC"].astype(int),
            "an": raw["AN"].astype(int),
            "source": SOURCE,
            "assay": "genome",
            "date_lower": 0,
            "date_upper": 0,
            "sampling_design": "healthy_reference",
            "disease_ascertainment_excluded": True,
            "cohort_id": COHORT_ID,
            "ingest_version": ingest_version,
        }
    )
    return OBSERVATIONS_SCHEMA.validate(obs)
