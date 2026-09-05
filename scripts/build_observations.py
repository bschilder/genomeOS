"""Build the observations store from all P1 sources (design §6, P1).

    python scripts/build_observations.py \
        --registry data/registry --gnomad data/raw/gnomad_hgdp_1kg_freqs.tsv \
        --map-surveys data/raw/map_hbs_surveys.tsv \
        --literature-evidence data/raw/literature_evidence.tsv \
        --literature-field-evidence data/raw/literature_field_evidence.tsv \
        --out data/observations
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from genomeos.observations.ingest import write_observations
from genomeos.observations.sources import gnomad_hgdp_1kg as gnomad
from genomeos.observations.sources import map_surveys, publications

VERSION = "0.1.0"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--registry", type=Path, required=True)
    ap.add_argument("--gnomad", type=Path, required=True)
    ap.add_argument("--map-surveys", type=Path, required=True)
    ap.add_argument("--literature-evidence", type=Path)
    ap.add_argument("--literature-field-evidence", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    if (args.literature_evidence is None) != (args.literature_field_evidence is None):
        ap.error("--literature-evidence and --literature-field-evidence must be supplied together")

    populations = pd.read_parquet(args.registry / "populations.parquet")
    aliases = pd.read_parquet(args.registry / "population_aliases.parquet")

    surveys, survey_report = map_surveys.load(args.map_surveys, VERSION)
    frames = [
        gnomad.load(args.gnomad, populations, aliases, VERSION),
        surveys,
    ]
    literature_report = None
    retained_evidence = None
    if args.literature_evidence is not None:
        literature, retained_evidence, literature_report = publications.load(
            args.literature_evidence,
            args.literature_field_evidence,
            populations,
            aliases,
            VERSION,
        )
        frames.append(literature)
    obs = pd.concat(frames, ignore_index=True)
    write_observations(obs, args.out)
    if retained_evidence is not None:
        retained_evidence.to_parquet(args.out / "literature_evidence.parquet", index=False)

    # Printed, never swallowed: a refused survey is a decision the operator should see (§12).
    print(f"MAP HbS surveys: {survey_report}")
    if literature_report is not None:
        print(f"Literature evidence: {literature_report}")

    by_design = obs["sampling_design"].value_counts().to_dict()
    print(f"observations v{VERSION}: {len(obs)} rows, {obs['variant_id'].nunique()} variants")
    print(f"  by sampling_design: {by_design}")


if __name__ == "__main__":
    main()
