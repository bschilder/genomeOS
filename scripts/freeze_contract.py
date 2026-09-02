"""Freeze the pandera schemas to JSON in contract/ so schema drift appears in diffs.

Plan 3's TypeScript client validates against these files, so a change to a schema must show up
as a reviewable diff rather than as a silent break for downstream consumers.

    python scripts/freeze_contract.py            # write
    python scripts/freeze_contract.py --check    # CI: fail if stale
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from genomeos.artifacts import ArtifactManifest
from genomeos.observations.schema import (
    CARRIER_OBSERVATIONS_SCHEMA,
    OBSERVATIONS_SCHEMA,
)
from genomeos.registry.schema import ALIASES_SCHEMA, POPULATIONS_SCHEMA

CONTRACT_DIR = Path(__file__).resolve().parents[1] / "contract"
PANDERA_SCHEMAS = {
    "populations.schema.json": POPULATIONS_SCHEMA,
    "population_aliases.schema.json": ALIASES_SCHEMA,
    "observations.schema.json": OBSERVATIONS_SCHEMA,
    "carrier_observations.schema.json": CARRIER_OBSERVATIONS_SCHEMA,
}
JSON_SCHEMAS = {
    "atlas_catalog.schema.json": ArtifactManifest.model_json_schema(),
}


def _serialise(schema) -> str:
    return json.dumps(json.loads(schema.to_json()), indent=2, sort_keys=True) + "\n"


def _serialise_json_schema(schema: dict) -> str:
    return json.dumps(schema, indent=2, sort_keys=True) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    CONTRACT_DIR.mkdir(exist_ok=True)
    stale = []
    rendered = {
        **{name: _serialise(schema) for name, schema in PANDERA_SCHEMAS.items()},
        **{name: _serialise_json_schema(schema) for name, schema in JSON_SCHEMAS.items()},
    }
    for name, text in rendered.items():
        path = CONTRACT_DIR / name
        if args.check:
            if not path.exists() or path.read_text() != text:
                stale.append(name)
        else:
            path.write_text(text)

    if stale:
        print(
            f"contract is stale: {stale}\nrun: python scripts/freeze_contract.py",
            file=sys.stderr,
        )
        return 1
    print("contract up to date" if args.check else f"wrote {len(rendered)} schemas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
