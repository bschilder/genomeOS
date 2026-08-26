"""Build the population registry to parquet (design §6, P0). Usage:

    python scripts/build_registry.py --hgdp data/raw/hgdp_populations.tsv --out data/registry

`--afnd` takes an AFND population export in the format documented in
`genomeos.registry.sources.afnd`. AFND publishes no licence and no bulk download, so this
repository ships no fetcher for it and the file has to be obtained by agreement with AFND; the
adapter prints what it refused and why.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from genomeos.registry.build import build_registry
from genomeos.registry.sources import afnd, hgdp

VERSION = "0.1.0"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hgdp", type=Path, required=True)
    ap.add_argument("--afnd", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    loaded: list[tuple[pd.DataFrame, pd.DataFrame]] = [hgdp.load(args.hgdp, VERSION)]
    if args.afnd is not None:
        afnd_populations, afnd_aliases, report = afnd.load(args.afnd, VERSION)
        print(report)
        loaded.append((afnd_populations, afnd_aliases))

    populations, aliases = build_registry(loaded)
    args.out.mkdir(parents=True, exist_ok=True)
    populations.to_parquet(args.out / "populations.parquet", index=False)
    aliases.to_parquet(args.out / "population_aliases.parquet", index=False)
    print(f"registry v{VERSION}: {len(populations)} populations, {len(aliases)} aliases")


if __name__ == "__main__":
    main()
