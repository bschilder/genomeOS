#!/usr/bin/env python3
"""Run the source-neutral B1 local count benchmark (design §§4–8, 12; #307).

This file is an offline I/O adapter. The model, training-only selector, support decisions, split
planning, and predictive scoring live in pure validation modules. Outputs are nonpublication
research evidence and never enter the serving path.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import subprocess
import sys
from dataclasses import asdict
from math import isfinite
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) in sys.path:
    sys.path.remove(str(ROOT))
sys.path.insert(0, str(ROOT))

import genomeos.observations.schema as observations_schema_module  # noqa: E402
import genomeos.validation.benchmark as benchmark_module  # noqa: E402
import genomeos.validation.local_count as local_count_module  # noqa: E402
import genomeos.validation.local_count_benchmark as local_benchmark_module  # noqa: E402
import genomeos.validation.local_count_selection as local_selection_module  # noqa: E402
import genomeos.validation.predictive as predictive_module  # noqa: E402
import genomeos.validation.splits as splits_module  # noqa: E402
from genomeos.validation.benchmark import inventory_observations  # noqa: E402
from genomeos.validation.local_count_benchmark import (  # noqa: E402
    evaluate_local_count_benchmark,
    plan_local_count_benchmark,
)
from genomeos.validation.local_count_selection import (  # noqa: E402
    ASSIGNMENT_COLUMNS,
    LocalCountBenchmarkConfig,
)

MODEL_ID = "B1-local-count"
MODEL_NAME = "compact_triweight_spherical_weighted_count_power_posterior"
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
OUTPUT_FILENAMES = (
    "bandwidth_selection.tsv",
    "fold_status.tsv",
    "inventory.json",
    "predictions.tsv",
    "summary.json",
    "support.tsv",
)
SCIENCE_SOURCE_FILES = {
    "genomeos/observations/schema.py": Path(observations_schema_module.__file__).resolve(),
    "genomeos/validation/benchmark.py": Path(benchmark_module.__file__).resolve(),
    "genomeos/validation/local_count.py": Path(local_count_module.__file__).resolve(),
    "genomeos/validation/local_count_benchmark.py": Path(
        local_benchmark_module.__file__
    ).resolve(),
    "genomeos/validation/local_count_selection.py": Path(
        local_selection_module.__file__
    ).resolve(),
    "genomeos/validation/predictive.py": Path(predictive_module.__file__).resolve(),
    "genomeos/validation/splits.py": Path(splits_module.__file__).resolve(),
    "scripts/benchmark_local_count.py": Path(__file__).resolve(),
}


def _positive_float(value: str) -> float:
    try:
        normalized = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a positive finite number") from error
    if not isfinite(normalized) or normalized <= 0.0:
        raise argparse.ArgumentTypeError("must be a positive finite number")
    return normalized


def _unit_interval(value: str) -> float:
    try:
        normalized = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be between zero and one") from error
    if not isfinite(normalized) or not 0.0 <= normalized <= 1.0:
        raise argparse.ArgumentTypeError("must be between zero and one")
    return normalized


def _positive_integer(value: str) -> int:
    try:
        normalized = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a positive integer") from error
    if normalized <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return normalized


def _nonnegative_integer(value: str) -> int:
    try:
        normalized = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a nonnegative integer") from error
    if normalized < 0:
        raise argparse.ArgumentTypeError("must be a nonnegative integer")
    return normalized


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the nonpublication B1 compact-support local count benchmark."
    )
    parser.add_argument("--observations", required=True, type=Path)
    parser.add_argument("--assignments", required=True, type=Path)
    parser.add_argument("--dependencies", required=True, type=Path)
    parser.add_argument("--data-version", required=True)
    parser.add_argument(
        "--bandwidth-km",
        required=True,
        action="append",
        type=_positive_float,
        help="Prespecified candidate; repeat in strictly increasing order.",
    )
    parser.add_argument("--prior-alpha", required=True, type=_positive_float)
    parser.add_argument("--prior-beta", required=True, type=_positive_float)
    parser.add_argument("--buffer-km", required=True, type=_positive_float)
    parser.add_argument(
        "--minimum-inner-emission-fraction", required=True, type=_unit_interval
    )
    parser.add_argument("--minimum-training-observations", type=_positive_integer, default=1)
    parser.add_argument("--minimum-effective-alleles", required=True, type=_positive_float)
    parser.add_argument("--posterior-draws", type=_positive_integer, default=2048)
    parser.add_argument("--query-chunk-size", type=_positive_integer, default=1024)
    parser.add_argument("--seed", type=_nonnegative_integer, default=42)
    parser.add_argument(
        "--evidence-kind",
        required=True,
        choices=("synthetic_fixture", "observational_research"),
    )
    parser.add_argument(
        "--analysis-role",
        required=True,
        choices=("synthetic_validation", "prespecified_primary", "posthoc_sensitivity"),
    )
    parser.add_argument(
        "--assignment-review-status",
        required=True,
        choices=("reviewed", "algorithmic_development_unreviewed"),
    )
    parser.add_argument(
        "--dependency-review-status",
        required=True,
        choices=("reviewed", "not_checked"),
    )
    parser.add_argument("--out", required=True, type=Path)
    return parser


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_hash(value: object) -> str:
    return _sha256_bytes(
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    )


def _file_record(path: Path) -> dict[str, object]:
    data = path.read_bytes()
    return {"sha256": _sha256_bytes(data), "size_bytes": len(data)}


def _resolved_science_sources() -> dict[str, Path]:
    for relative, actual in SCIENCE_SOURCE_FILES.items():
        if actual != (ROOT / relative).resolve():
            raise ValueError(f"imported science source {relative!r} resolved outside this checkout")
    return dict(SCIENCE_SOURCE_FILES)


def _read_observations(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(
        path,
        sep="\t",
        dtype={column: str for column in OBSERVATION_LITERAL_COLUMNS},
        keep_default_na=False,
        na_filter=False,
    )
    return benchmark_module.validate_allele_observations(frame)


def _read_auxiliary(path: Path, columns: tuple[str, ...], name: str) -> pd.DataFrame:
    frame = pd.read_csv(path, sep="\t", dtype=str, keep_default_na=False, na_filter=False)
    if frame.columns.duplicated().any() or tuple(frame.columns) != columns:
        raise ValueError(f"{name} TSV columns must be exactly {list(columns)}")
    for column in columns:
        if not frame[column].map(lambda value: isinstance(value, str) and bool(value.strip())).all():
            raise ValueError(f"{name} {column} values must be nonempty literal strings")
    return frame


def _code_revision() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    revision = completed.stdout.strip()
    if len(revision) != 40:
        raise ValueError("git revision is unavailable or malformed")
    return revision


def _package_versions() -> dict[str, str]:
    versions = {"python": ".".join(str(value) for value in sys.version_info[:3])}
    for distribution in ("genomeos", "numpy", "pandas", "scipy", "pandera"):
        versions[distribution] = importlib.metadata.version(distribution)
    return versions


def _json_write(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, allow_nan=False, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )


def _write_tsv(frame: pd.DataFrame, path: Path) -> None:
    serialized = frame.copy()
    if "inner_failure_reasons" in serialized:
        serialized["inner_failure_reasons"] = serialized["inner_failure_reasons"].map(
            lambda value: json.dumps(list(value), separators=(",", ":"))
        )
    for column in ("log_score", "mean_log_score"):
        if column in serialized:
            serialized[column] = serialized[column].map(
                lambda value: "-Infinity" if value == -np.inf else value
            )
    serialized.to_csv(path, sep="\t", index=False, lineterminator="\n")


def run(args: argparse.Namespace) -> int:
    """Run the frozen B1 benchmark and write deterministic nonpublication evidence."""
    if args.out.exists():
        raise ValueError(f"output directory already exists: {args.out}")
    if not isinstance(args.data_version, str) or not args.data_version.strip():
        raise ValueError("data_version must be a nonempty string")
    science_sources = _resolved_science_sources()
    input_paths = {
        "assignments": args.assignments,
        "dependencies": args.dependencies,
        "observations": args.observations,
    }
    input_files = {name: _file_record(path) for name, path in sorted(input_paths.items())}
    observations = _read_observations(args.observations)
    assignments = _read_auxiliary(args.assignments, ASSIGNMENT_COLUMNS, "assignments")
    dependencies = _read_auxiliary(args.dependencies, DEPENDENCY_COLUMNS, "dependencies")
    dependency_pairs = tuple(
        dependencies.loc[:, DEPENDENCY_COLUMNS].itertuples(index=False, name=None)
    )
    config = LocalCountBenchmarkConfig(
        candidate_bandwidths_km=tuple(args.bandwidth_km),
        prior_alpha=args.prior_alpha,
        prior_beta=args.prior_beta,
        posterior_draws=args.posterior_draws,
        minimum_training_observations=args.minimum_training_observations,
        minimum_effective_alleles=args.minimum_effective_alleles,
        minimum_inner_emission_fraction=args.minimum_inner_emission_fraction,
        query_chunk_size=args.query_chunk_size,
    )
    plan = plan_local_count_benchmark(
        observations,
        assignments,
        dependency_pairs,
        buffer_km=args.buffer_km,
        data_version=args.data_version,
        config=config,
        seed=args.seed,
    )
    result = evaluate_local_count_benchmark(plan)
    inventory = inventory_observations(observations)
    configuration = asdict(config) | {
        "buffer_km": args.buffer_km,
        "data_version": args.data_version,
        "seed": args.seed,
    }
    status_records = []
    for status in result.fold_status:
        record = asdict(status)
        for field in ("expected_test_ids", "emitted_test_ids", "refused_test_ids"):
            record[field] = json.dumps(record[field], separators=(",", ":"))
        status_records.append(record)
    split_records = []
    status_by_id = {status.split_id: status for status in result.fold_status}
    for split in result.splits:
        split_records.append(asdict(split) | {"result": asdict(status_by_id[split.split_id])})
    manifest = {
        "schema_version": 1,
        "model": {
            "model_id": MODEL_ID,
            "name": MODEL_NAME,
            "kernel": "compact_triweight",
            "distance": "great_circle_footprint_edge_km",
            "posterior_semantics": "weighted_count_generalized_bayes_power_posterior",
            "environmental_covariates": False,
            "source_specific_features": False,
        },
        "evidence_kind": args.evidence_kind,
        "analysis_role": args.analysis_role,
        "publication_eligible": False,
        "qualification": {
            "assignment_review_status": args.assignment_review_status,
            "dependency_review_status": args.dependency_review_status,
            "scientific_promotion_decision": "not_made",
        },
        "configuration": configuration,
        "configuration_sha256": _canonical_hash(configuration),
        "input_files": input_files,
        "inputs_sha256": _canonical_hash(input_files),
        "source_provenance": {
            "counts_by_source": inventory["counts_by_source"],
            "input_roles": sorted(input_files),
        },
        "splits": split_records,
        "split_manifest_sha256": _canonical_hash(split_records),
        "code_revision": _code_revision(),
        "science_source_sha256": {
            relative: _file_record(path)["sha256"]
            for relative, path in science_sources.items()
        },
        "package_versions": _package_versions(),
    }
    summary = {
        "schema_version": 1,
        "model_id": MODEL_ID,
        "evidence_kind": args.evidence_kind,
        "analysis_role": args.analysis_role,
        "publication_eligible": False,
        "benchmark": result.summary,
    }
    args.out.mkdir(parents=True, exist_ok=False)
    _write_tsv(result.predictions, args.out / "predictions.tsv")
    _write_tsv(result.support, args.out / "support.tsv")
    _write_tsv(result.candidate_scores, args.out / "bandwidth_selection.tsv")
    _write_tsv(pd.DataFrame.from_records(status_records), args.out / "fold_status.tsv")
    _json_write(args.out / "inventory.json", inventory)
    _json_write(args.out / "summary.json", summary)
    manifest["output_files"] = {
        name: _file_record(args.out / name) for name in OUTPUT_FILENAMES
    }
    _json_write(args.out / "manifest.json", manifest)
    return 0 if result.summary["comparison_complete"] else 1


def main() -> int:
    parser = _parser()
    args = parser.parse_args()
    try:
        return run(args)
    except (OSError, TypeError, ValueError, subprocess.SubprocessError) as error:
        parser.exit(2, f"error: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
