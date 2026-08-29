#!/usr/bin/env python3
"""Build the tiny deterministic artifact set used by API, preview, and container smoke tests."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import h3
import pandas as pd

VARIANT_ID = "chr11-5227002-T-A"
DATA_VERSION = "demo-2026-08-24"
MODEL_VERSION = "demo-surface-v1"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("demo/artifacts"))
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    observations = pd.DataFrame(
        [
            {
                "variant_id": VARIANT_ID,
                "population_id": "demo:ghana",
                "lat": 5.56,
                "lon": -0.20,
                "radius_km": 50.0,
                "ac": 36,
                "an": 444,
                "sampling_design": "population_random",
                "source": "demo-map-hbs",
            },
            {
                "variant_id": VARIANT_ID,
                "population_id": "demo:nigeria",
                "lat": 7.38,
                "lon": 3.90,
                "radius_km": 50.0,
                "ac": 2392,
                "an": 20230,
                "sampling_design": "population_random",
                "source": "demo-map-hbs",
            },
            {
                "variant_id": VARIANT_ID,
                "population_id": "demo:india",
                "lat": 17.17,
                "lon": 82.01,
                "radius_km": 50.0,
                "ac": 412,
                "an": 5178,
                "sampling_design": "population_random",
                "source": "demo-map-hbs",
            },
        ]
    )
    surface_rows = [
        (5.56, -0.20, 0.081, 0.012, "observed"),
        (7.38, 3.90, 0.118, 0.009, "observed"),
        (11.0, 15.0, 0.092, 0.021, "interpolated"),
        (17.17, 82.01, 0.080, 0.010, "observed"),
        (23.0, 55.0, 0.041, 0.038, "prior_dominated"),
        (-8.0, 120.0, 0.010, 0.060, "unknown"),
    ]
    surfaces = pd.DataFrame(
        [
            {
                "variant_id": VARIANT_ID,
                "h3_resolution": 4,
                "h3_index": h3.latlng_to_cell(lat, lon, 4),
                "lat": lat,
                "lon": lon,
                "post_mean": mean,
                "post_sd": sd,
                "q025": max(0.0, mean - 1.96 * sd),
                "q975": min(1.0, mean + 1.96 * sd),
                "support": support,
            }
            for lat, lon, mean, sd, support in surface_rows
        ]
    )

    observations.to_parquet(args.out / "observations.parquet", index=False)
    surfaces.to_parquet(args.out / "surfaces.parquet", index=False)
    observation_path = args.out / "observations.parquet"
    surface_path = args.out / "surfaces.parquet"
    manifest = {
        "schema_version": "2",
        "artifact_version": "demo-artifacts-v1",
        "registry_version": "demo-registry-v1",
        "data_version": DATA_VERSION,
        "model_version": MODEL_VERSION,
        "created_at": "2026-08-24T00:00:00Z",
        "variants": [
            {
                "variant_id": VARIANT_ID,
                "label": "HbS (rs334)",
                "entity_type": "variant",
                "measurement": "allele_frequency",
                "surface_eligible": True,
                "assumptions": ["synthetic diagnostic data; not a scientific result"],
                "resolutions": [4],
                "observations": {
                    "path": observation_path.name,
                    "sha256": _sha256(observation_path),
                    "row_count": len(observations),
                    "schema_version": "observations-v1",
                },
                "surface": {
                    "path": surface_path.name,
                    "sha256": _sha256(surface_path),
                    "row_count": len(surfaces),
                    "schema_version": "surface-v1",
                },
                "burden": None,
            }
        ],
        "assumptions": ["fixture-backed diagnostic catalog"],
    }
    (args.out / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(f"demo artifacts: {len(observations)} observations, {len(surfaces)} surface cells")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    main()
