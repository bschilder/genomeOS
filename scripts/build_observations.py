"""Build the observations store from all P1 sources (design §6, P1).

    python scripts/build_observations.py \
        --registry data/registry --gnomad data/raw/gnomad_hgdp_1kg_freqs.tsv \
        --map-surveys data/raw/map_hbs_surveys.tsv --out data/observations
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from genomeos.observations.ingest import write_observations
from genomeos.observations.sources import gnomad_hgdp_1kg as gnomad
from genomeos.observations.sources import map_surveys

VERSION = "0.1.0"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--registry", type=Path, required=True)
    ap.add_argument("--gnomad", type=Path, required=True)
    ap.add_argument("--map-surveys", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    populations = pd.read_parquet(args.registry / "populations.parquet")
    aliases = pd.read_parquet(args.registry / "population_aliases.parquet")

    surveys, survey_report = map_surveys.load(args.map_surveys, VERSION)
    frames = [
        gnomad.load(args.gnomad, populations, aliases, VERSION),
        surveys,
    ]
    obs = pd.concat(frames, ignore_index=True)
    write_observations(obs, args.out)

    # Printed, never swallowed: a refused survey is a decision the operator should see (§12).
    print(f"MAP HbS surveys: {survey_report}")

    by_design = obs["sampling_design"].value_counts().to_dict()
    print(f"observations v{VERSION}: {len(obs)} rows, {obs['variant_id'].nunique()} variants")
    print(f"  by sampling_design: {by_design}")


if __name__ == "__main__":
    main()
