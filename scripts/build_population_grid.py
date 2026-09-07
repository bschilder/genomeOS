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
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from genomeos.geo.population import (
    PopulationGrid,
    aggregate_raster_to_h3,
    merge_population_grids,
    publication_target_cells,
)

POPULATION_GRID_FORMAT = 2
SUPPORTED_POPULATION_GRID_FORMATS = {1, POPULATION_GRID_FORMAT}


@dataclass(frozen=True)
class PopulationRasterSource:
    """One exact raster input and its public provenance."""

    path: Path
    source_version: str
    source_url: str


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
    grid_format = manifest["population_grid_format"]
    if grid_format not in SUPPORTED_POPULATION_GRID_FORMATS:
        raise ValueError(
            f"{manifest_path}: unsupported population_grid_format "
            f"{grid_format!r}"
        )
    if grid_format == 2:
        inputs = manifest.get("input_rasters")
        if not isinstance(inputs, list) or not inputs:
            raise ValueError(f"{manifest_path}: format 2 requires non-empty input_rasters")
        required_input = {
            "cells_added",
            "overlap_cells_ignored",
            "role",
            "sha256",
            "source_url",
            "source_version",
        }
        for index, item in enumerate(inputs):
            if not isinstance(item, dict) or required_input - set(item):
                raise ValueError(
                    f"{manifest_path}: input_rasters[{index}] is missing required provenance"
                )
            if item["role"] not in {"primary", "supplement"}:
                raise ValueError(f"{manifest_path}: input_rasters[{index}] has invalid role")
            if not str(item["source_url"]).strip() or not str(item["source_version"]).strip():
                raise ValueError(
                    f"{manifest_path}: input_rasters[{index}] requires source_url and source_version"
                )
            digest = str(item["sha256"])
            if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
                raise ValueError(f"{manifest_path}: input_rasters[{index}] has invalid sha256")
        expected_version = "+".join(str(item["source_version"]) for item in inputs)
        if manifest["source_version"] != expected_version:
            raise ValueError(
                f"{manifest_path}: source_version does not match ordered input_rasters"
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
    publication_target_cells(grid)
    return grid


def build_population_grid(
    raster: Path,
    out: Path,
    *,
    resolution: int,
    source_version: str,
    source_url: str,
    supplements: Sequence[PopulationRasterSource] = (),
    overwrite: bool = False,
) -> PopulationGrid:
    """Aggregate ordered rasters and write a provenance-complete, fill-only H3 grid."""
    raster = Path(raster)
    out = Path(out)
    if not source_url.strip():
        raise ValueError("source_url must be non-empty")
    for supplement in supplements:
        if not supplement.source_url.strip() or not supplement.source_version.strip():
            raise ValueError("supplement source_url and source_version must be non-empty")
    manifest_path = population_grid_manifest_path(out)
    existing = [path for path in (out, manifest_path) if path.exists()]
    if existing and not overwrite:
        raise FileExistsError(
            f"{existing[0]} already exists; pass overwrite=True deliberately"
        )
    primary_grid = aggregate_raster_to_h3(
        raster,
        resolution,
        source_version=source_version,
    )
    supplement_grids = [
        aggregate_raster_to_h3(
            Path(supplement.path),
            resolution,
            source_version=supplement.source_version,
        )
        for supplement in supplements
    ]
    grid, reports = merge_population_grids(primary_grid, supplement_grids)
    out.parent.mkdir(parents=True, exist_ok=True)
    grid.cells.assign(
        source=grid.source,
        source_version=grid.source_version,
    ).to_parquet(out, index=False)
    manifest = {
        "coverage_stride": grid.coverage_stride,
        "input_rasters": [
            {
                "cells_added": len(primary_grid.cells),
                "overlap_cells_ignored": 0,
                "role": "primary",
                "sha256": _sha256_file(raster),
                "source_url": source_url,
                "source_version": primary_grid.source_version,
            },
            *[
                {
                    "cells_added": report.cells_added,
                    "overlap_cells_ignored": report.overlap_cells_ignored,
                    "role": "supplement",
                    "sha256": _sha256_file(Path(supplement.path)),
                    "source_url": supplement.source_url,
                    "source_version": supplement.source_version,
                }
                for supplement, report in zip(supplements, reports, strict=True)
            ],
        ],
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
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--supplement-raster", type=Path, action="append", default=[])
    parser.add_argument("--supplement-version", action="append", default=[])
    parser.add_argument("--supplement-url", action="append", default=[])
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    supplement_lengths = {
        len(args.supplement_raster),
        len(args.supplement_version),
        len(args.supplement_url),
    }
    if len(supplement_lengths) != 1:
        raise SystemExit(
            "--supplement-raster, --supplement-version, and --supplement-url must repeat equally"
        )
    supplements = tuple(
        PopulationRasterSource(path=path, source_version=version, source_url=url)
        for path, version, url in zip(
            args.supplement_raster,
            args.supplement_version,
            args.supplement_url,
            strict=True,
        )
    )
    grid = build_population_grid(
        args.raster,
        args.out,
        resolution=args.resolution,
        source_version=args.source_version,
        source_url=args.source_url,
        supplements=supplements,
        overwrite=args.overwrite,
    )
    digest = _sha256_file(args.out)
    print(grid)
    print(f"sha256 {digest}  {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
