#!/usr/bin/env python3
"""Run the frozen B1G basis-geometry preflight (design §§4–8, 12; #331).

This offline I/O adapter verifies the preregistered HbS inputs byte-for-byte, calls the pure B1G
geometry functions, and writes a complete split × grid ledger. It does not fit a count likelihood
or claim predictive improvement. Its artifacts are nonpublication research evidence and never enter
the serving path.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from collections.abc import Mapping
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) in sys.path:
    sys.path.remove(str(ROOT))
sys.path.insert(0, str(ROOT))

from genomeos.validation.b1g_basis import preflight_b1g_basis  # noqa: E402

SOURCE_REVISION = "d98794b18b64e230cbdbae8b23d37488a42de804"
FROZEN_SHA256 = {
    "observations": "820d725fae9859a6cebca98296676e8c525b103f7033aa5237b9aaa00f79b331",
    "assignments": "c922b240624c761f0752821d9e6986bb1479bbc97a0d9931da7db3a17ee20b20",
    "dependencies": "fa7b4c093dc2f83a2ea3c7f0810b9130e65feac7c94dc80fb8475d03c2d3cf22",
}
ASSIGNMENT_COLUMNS = ("source_record_id", "block_id", "region_id", "variant_group")
DEPENDENCY_COLUMNS = ("source_record_id_a", "source_record_id_b")
OBSERVATION_LITERAL_COLUMNS = (
    "variant_id",
    "rsid",
    "population_id",
    "ac",
    "an",
    "source_record_id",
    "source",
    "assay",
    "date_lower",
    "date_upper",
    "sampling_design",
    "cohort_id",
    "ingest_version",
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the frozen nonpublication B1G basis-geometry preflight."
    )
    parser.add_argument("--observations", required=True, type=Path)
    parser.add_argument("--assignments", required=True, type=Path)
    parser.add_argument("--dependencies", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument(
        "--data-version",
        default="hbs-current-gp-benchmark-20260916-v1",
    )
    parser.add_argument("--query-chunk-size", type=int, default=1024)
    return parser


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_hashes(paths: Mapping[str, Path], expected: Mapping[str, str]) -> dict[str, str]:
    if set(paths) != set(FROZEN_SHA256) or set(expected) != set(FROZEN_SHA256):
        raise ValueError(f"input hash maps must contain exactly {sorted(FROZEN_SHA256)}")
    actual = {name: _sha256(path) for name, path in paths.items()}
    mismatches = {
        name: {"expected": expected[name], "actual": actual[name]}
        for name in sorted(actual)
        if actual[name] != expected[name]
    }
    if mismatches:
        raise ValueError(f"frozen B1G input hash mismatch: {mismatches}")
    return actual


def _read_observations(path: Path) -> pd.DataFrame:
    return pd.read_csv(
        path,
        sep="\t",
        dtype={column: str for column in OBSERVATION_LITERAL_COLUMNS},
        keep_default_na=False,
        na_filter=False,
    )


def _read_exact_tsv(path: Path, columns: tuple[str, ...], name: str) -> pd.DataFrame:
    frame = pd.read_csv(path, sep="\t", dtype=str, keep_default_na=False, na_filter=False)
    if frame.columns.duplicated().any() or tuple(frame.columns) != columns:
        raise ValueError(f"{name} TSV columns must be exactly {list(columns)}")
    return frame


def _git_revision() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, allow_nan=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def run_preflight(
    *,
    observations_path: Path,
    assignments_path: Path,
    dependencies_path: Path,
    out: Path,
    data_version: str,
    buffer_km: float,
    query_chunk_size: int,
    expected_sha256: Mapping[str, str] = FROZEN_SHA256,
) -> None:
    """Verify inputs and write one complete immutable B1G geometry preflight."""
    paths = {
        "observations": observations_path,
        "assignments": assignments_path,
        "dependencies": dependencies_path,
    }
    input_sha256 = _verify_hashes(paths, expected_sha256)
    observations = _read_observations(observations_path)
    assignments = _read_exact_tsv(assignments_path, ASSIGNMENT_COLUMNS, "assignments")
    dependency_frame = _read_exact_tsv(
        dependencies_path,
        DEPENDENCY_COLUMNS,
        "dependencies",
    )
    dependencies = tuple(
        dependency_frame.loc[:, DEPENDENCY_COLUMNS].itertuples(index=False, name=None)
    )

    started_ns = time.perf_counter_ns()
    result = preflight_b1g_basis(
        observations,
        assignments.loc[:, ["source_record_id", "block_id"]],
        dependencies,
        buffer_km=buffer_km,
        data_version=data_version,
        query_chunk_size=query_chunk_size,
    )
    elapsed_ns = time.perf_counter_ns() - started_ns
    if out.exists() and any(out.iterdir()):
        raise ValueError(f"output directory must be absent or empty: {out}")
    out.mkdir(parents=True, exist_ok=True)

    cells = [asdict(cell) for cell in result.cells]
    cell_frame = pd.DataFrame.from_records(cells)
    cell_frame["centre_source_record_ids"] = cell_frame["centre_source_record_ids"].map(
        lambda values: json.dumps(values, separators=(",", ":"))
    )
    cell_frame.to_csv(out / "basis_preflight.tsv", sep="\t", index=False)
    status_counts = cell_frame["status"].value_counts().sort_index()
    _write_json(
        out / "report.json",
        {
            "schema_version": "b1g_basis_preflight_v1",
            "interpretation": (
                "Training-only basis geometry screen; no likelihood was fitted and no predictive "
                "improvement, coverage, or promotion claim is made."
            ),
            "data_version": result.data_version,
            "buffer_km": result.buffer_km,
            "split_count": len(result.splits),
            "cell_count": len(result.cells),
            "status_counts": {str(key): int(value) for key, value in status_counts.items()},
            "splits": [asdict(split) for split in result.splits],
            "cells": cells,
            "grid_summary": [asdict(row) for row in result.grid_summary],
        },
    )
    _write_json(
        out / "provenance.json",
        {
            "schema_version": "b1g_basis_preflight_provenance_v1",
            "source_revision": SOURCE_REVISION,
            "code_revision": _git_revision(),
            "input_sha256": input_sha256,
            "input_size_bytes": {name: path.stat().st_size for name, path in paths.items()},
            "buffer_km": buffer_km,
            "query_chunk_size": query_chunk_size,
            "elapsed_ns": elapsed_ns,
            "numpy_version": np.__version__,
            "pandas_version": pd.__version__,
        },
    )


def main() -> None:
    args = _parser().parse_args()
    if args.query_chunk_size <= 0:
        raise ValueError("query_chunk_size must be a positive integer")
    run_preflight(
        observations_path=args.observations,
        assignments_path=args.assignments,
        dependencies_path=args.dependencies,
        out=args.out,
        data_version=args.data_version,
        buffer_km=300.0,
        query_chunk_size=args.query_chunk_size,
    )
    print(f"Wrote frozen B1G basis preflight to {args.out}")


if __name__ == "__main__":
    main()
