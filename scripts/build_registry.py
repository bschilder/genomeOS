"""Build the population registry to parquet (design §6, P0). Usage:

    python scripts/build_registry.py --hgdp data/raw/hgdp_populations.tsv --out data/registry
"""

from __future__ import annotations

import argparse
from pathlib import Path

from genomeos.registry.build import build_registry
from genomeos.registry.sources import hgdp

VERSION = "0.1.0"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hgdp", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    populations, aliases = build_registry([hgdp.load(args.hgdp, VERSION)])
    args.out.mkdir(parents=True, exist_ok=True)
    populations.to_parquet(args.out / "populations.parquet", index=False)
    aliases.to_parquet(args.out / "population_aliases.parquet", index=False)
    print(f"registry v{VERSION}: {len(populations)} populations, {len(aliases)} aliases")


if __name__ == "__main__":
    main()
