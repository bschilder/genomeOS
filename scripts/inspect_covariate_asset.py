#!/usr/bin/env python3
"""Inspect validated offline covariate metadata (design §7; global plan WP3; issue #290)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from genomeos.covariates.registry import load_default_registry, load_registry, lookup_asset


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, help="explicit canonical registry JSON")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--list", action="store_true", help="list registered candidate identities")
    mode.add_argument("--asset-key", help="show one complete validated candidate record")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        registry = load_default_registry() if args.registry is None else load_registry(args.registry)
        if args.list:
            payload = [
                {
                    "admission_status": asset.admission_status,
                    "asset_id": asset.asset_id,
                    "asset_key": asset.asset_key,
                    "commercial_compatibility": asset.commercial_compatibility,
                    "dataset_version": asset.dataset_version,
                    "extraction_status": asset.extraction_status,
                }
                for asset in registry.assets
            ]
        else:
            payload = lookup_asset(registry, args.asset_key).model_dump(mode="json")
    except (OSError, ValueError, KeyError) as error:
        parser.exit(2, f"error: {error}\n")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
