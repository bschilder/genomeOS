#!/usr/bin/env python3
"""CLI for building the P4 serving catalog from published P2 surfaces (design §5, §6, §10)."""

from __future__ import annotations

import argparse
from pathlib import Path

from genomeos.artifacts.build import build_catalog


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path("data/store/artifacts"))
    parser.add_argument(
        "--metadata", type=Path, default=Path("data/store/catalog-metadata.json")
    )
    parser.add_argument("--out", type=Path, required=True)
    arguments = parser.parse_args()
    path = build_catalog(arguments.source, arguments.metadata, arguments.out)
    print(f"wrote immutable Atlas serving catalog: {path}")


if __name__ == "__main__":
    main()
