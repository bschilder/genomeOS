#!/usr/bin/env python3
"""Aggregate a versioned WorldPop raster into publication H3 cells (design §7, §9).

The output is an offline scientific input, not a visual land mask. Every row repeats the source
and source version so moving the parquet away from its command log cannot erase the provenance
needed to decide whether a surface may be published over that cell.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from genomeos.geo.population import (
    PopulationGrid,
    aggregate_raster_to_h3,
    publication_target_cells,
)

POPULATION_GRID_FORMAT = 1


def population_grid_manifest_path(parquet_path: Path) -> Path:
    """Return the sidecar path without replacing the parquet suffix."""
    parquet_path = Path(parquet_path)
    return parquet_path.with_suffix(f"{parquet_path.suffix}.manifest.json")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_population_grid(path: Path) -> PopulationGrid:
    """Read a built grid only after validating its sidecar and parquet checksum."""
    path = Path(path)
    manifest_path = population_grid_manifest_path(path)
    try:
        manifest = json.loads(manifest_path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"{manifest_path}: unreadable population-grid manifest: {error}") from error
    required = {
        "coverage_stride",
        "n_cells",
        "parquet_sha256",
        "pixels_counted",
        "pixels_nodata",
        "population_grid_format",
        "resolution",
        "source",
        "source_version",
    }
    missing = required - set(manifest)
    if missing:
        raise ValueError(f"{manifest_path}: missing required fields {sorted(missing)}")
    if manifest["population_grid_format"] != POPULATION_GRID_FORMAT:
        raise ValueError(
            f"{manifest_path}: unsupported population_grid_format "
            f"{manifest['population_grid_format']!r}"
        )
    actual_hash = _sha256_file(path)
    if actual_hash != manifest["parquet_sha256"]:
        raise ValueError(f"{path}: checksum does not match {manifest_path}")

    cells = pd.read_parquet(path)
    if len(cells) != int(manifest["n_cells"]):
        raise ValueError(
            f"{path}: manifest n_cells={manifest['n_cells']} but parquet has {len(cells)} rows"
        )
    required_columns = {"h3_index", "population", "source", "source_version"}
    missing_columns = required_columns - set(cells.columns)
    if missing_columns:
        raise ValueError(f"{path}: missing required columns {sorted(missing_columns)}")
    source_values = set(cells["source"].astype(str))
    version_values = set(cells["source_version"].astype(str))
    if source_values != {str(manifest["source"])}:
        raise ValueError(f"{path}: row source values do not match the manifest")
    if version_values != {str(manifest["source_version"])}:
        raise ValueError(f"{path}: row source_version values do not match the manifest")

    grid = PopulationGrid(
        cells=cells[["h3_index", "population"]].copy(),
        resolution=int(manifest["resolution"]),
        source=str(manifest["source"]),
        source_version=str(manifest["source_version"]),
        pixels_counted=int(manifest["pixels_counted"]),
        pixels_nodata=int(manifest["pixels_nodata"]),
        coverage_stride=int(manifest["coverage_stride"]),
    )
    publication_target_cells(grid, [])
    return grid


def build_population_grid(
    raster: Path,
    out: Path,
    *,
    resolution: int,
    source_version: str,
    overwrite: bool = False,
) -> PopulationGrid:
    """Aggregate `raster` and write a provenance-complete parquet without silent overwrite."""
    raster = Path(raster)
    out = Path(out)
    manifest_path = population_grid_manifest_path(out)
    existing = [path for path in (out, manifest_path) if path.exists()]
    if existing and not overwrite:
        raise FileExistsError(
            f"{existing[0]} already exists; pass overwrite=True deliberately"
        )
    grid = aggregate_raster_to_h3(
        raster,
        resolution,
        source_version=source_version,
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    grid.cells.assign(
        source=grid.source,
        source_version=grid.source_version,
    ).to_parquet(out, index=False)
    manifest = {
        "coverage_stride": grid.coverage_stride,
        "n_cells": len(grid.cells),
        "parquet_sha256": _sha256_file(out),
        "pixels_counted": grid.pixels_counted,
        "pixels_nodata": grid.pixels_nodata,
        "population_grid_format": POPULATION_GRID_FORMAT,
        "resolution": grid.resolution,
        "source": grid.source,
        "source_version": grid.source_version,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return grid


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raster", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--resolution", type=int, required=True)
    parser.add_argument("--source-version", required=True)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    grid = build_population_grid(
        args.raster,
        args.out,
        resolution=args.resolution,
        source_version=args.source_version,
        overwrite=args.overwrite,
    )
    digest = _sha256_file(args.out)
    print(grid)
    print(f"sha256 {digest}  {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
