"""Build the observations store from all P1 sources (design §6, P1).

    python scripts/build_observations.py \
        --registry data/registry --gnomad data/raw/gnomad_hgdp_1kg_freqs.tsv \
        --map-surveys data/raw/map_hbs_surveys.tsv \
        --literature-evidence data/raw/literature_evidence.tsv \
        --literature-field-evidence data/raw/literature_field_evidence.tsv \
        --wbbc-vcf data/raw/WBBC.chr22.GRCh38.vcf.gz \
        --wbbc-variants data/raw/wbbc-variants.txt \
        --out data/observations
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from genomeos.observations.ingest import write_observations
from genomeos.observations.sources import gnomad_hgdp_1kg as gnomad
from genomeos.observations.sources import map_surveys, publications, wbbc
from genomeos.registry.publication import read_registry

VERSION = "0.1.0"


def _read_variant_ids(path: Path) -> frozenset[str]:
    values = [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if not values:
        raise ValueError(f"{path}: variant list is empty")
    if len(values) != len(set(values)):
        raise ValueError(f"{path}: variant list contains duplicates")
    return frozenset(values)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--registry", type=Path, required=True)
    ap.add_argument("--gnomad", type=Path, required=True)
    ap.add_argument("--map-surveys", type=Path, required=True)
    ap.add_argument("--literature-evidence", type=Path)
    ap.add_argument("--literature-field-evidence", type=Path)
    ap.add_argument(
        "--wbbc-vcf",
        type=Path,
        action="append",
        help="WBBC chromosome VCF; repeat for each chromosome needed by --wbbc-variants",
    )
    ap.add_argument("--wbbc-variants", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    if (args.literature_evidence is None) != (args.literature_field_evidence is None):
        ap.error("--literature-evidence and --literature-field-evidence must be supplied together")
    if (args.wbbc_vcf is None) != (args.wbbc_variants is None):
        ap.error("--wbbc-vcf and --wbbc-variants must be supplied together")

    populations, aliases = read_registry(args.registry)

    surveys, survey_report = map_surveys.load(args.map_surveys, VERSION)
    frames = [
        gnomad.load(args.gnomad, populations, aliases, VERSION),
        surveys,
    ]
    literature_report = None
    retained_evidence = None
    wbbc_report = None
    if args.literature_evidence is not None:
        literature, retained_evidence, literature_report = publications.load(
            args.literature_evidence,
            args.literature_field_evidence,
            populations,
            aliases,
            VERSION,
        )
        frames.append(literature)
    if args.wbbc_vcf is not None:
        try:
            selected_variants = _read_variant_ids(args.wbbc_variants)
        except ValueError as exc:
            ap.error(str(exc))
        wbbc_observations, wbbc_report = wbbc.load_many(
            args.wbbc_vcf,
            populations,
            aliases,
            VERSION,
            variant_ids=selected_variants,
        )
        frames.append(wbbc_observations)
    obs = pd.concat(frames, ignore_index=True)
    write_observations(obs, args.out)
    if retained_evidence is not None:
        retained_evidence.to_parquet(args.out / "literature_evidence.parquet", index=False)

    # Printed, never swallowed: a refused survey is a decision the operator should see (§12).
    print(f"MAP HbS surveys: {survey_report}")
    if literature_report is not None:
        print(f"Literature evidence: {literature_report}")
    if wbbc_report is not None:
        print(
            "WBBC WGS frequencies: "
            f"{wbbc_report.retained_observations} observations from "
            f"{wbbc_report.matched_variants} variants; "
            f"max regional rounding residual={wbbc_report.maximum_regional_count_residual:.6g}"
        )

    by_design = obs["sampling_design"].value_counts().to_dict()
    print(f"observations v{VERSION}: {len(obs)} rows, {obs['variant_id'].nunique()} variants")
    print(f"  by sampling_design: {by_design}")


if __name__ == "__main__":
    main()
