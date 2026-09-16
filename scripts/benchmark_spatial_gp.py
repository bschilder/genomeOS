#!/usr/bin/env python3
"""Run the offline current spatial-GP benchmark (design §§4–5, 7–8, 12; #189, #319).

This is a deterministic file adapter around
``genomeos.validation.spatial_gp_benchmark``. It requires caller-supplied geography and
dependency evidence, records their review state, and never makes a scientific promotion decision.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, fields
from math import isfinite
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) in sys.path:
    sys.path.remove(str(ROOT))
sys.path.insert(0, str(ROOT))

import genomeos.observations.schema as observations_schema_module  # noqa: E402
import genomeos.surfaces.config as surface_config_module  # noqa: E402
import genomeos.surfaces.fit as surface_fit_module  # noqa: E402
import genomeos.surfaces.observation as observation_module  # noqa: E402
import genomeos.surfaces.observation_prediction as prediction_module  # noqa: E402
import genomeos.validation.benchmark as benchmark_module  # noqa: E402
import genomeos.validation.predictive as predictive_module  # noqa: E402
import genomeos.validation.spatial_gp_benchmark as spatial_benchmark_module  # noqa: E402
import genomeos.validation.spatial_gp_checkpoint as checkpoint_module  # noqa: E402
import genomeos.validation.splits as splits_module  # noqa: E402
from genomeos.surfaces.config import FitConfig  # noqa: E402
from genomeos.validation.benchmark import (  # noqa: E402
    inventory_observations,
    validate_allele_observations,
)
from genomeos.validation.spatial_gp_benchmark import (  # noqa: E402
    evaluate_single_variant_gp_fold,
    finalize_single_variant_gp_benchmark,
    plan_single_variant_gp_benchmark,
    spatial_gp_seed_schedule,
)
from genomeos.validation.spatial_gp_checkpoint import (  # noqa: E402
    build_checkpoint_header,
    initialize_checkpoint,
    load_fold_checkpoints,
    write_fold_checkpoint,
)

MODEL_ID = "B2-current"
MODEL_NAME = "current_single_variant_spatial_gp"
ASSIGNMENT_COLUMNS = ("source_record_id", "block_id", "region_id", "variant_group")
DEPENDENCY_COLUMNS = ("source_record_id_a", "source_record_id_b")
FOLD_STATUS_COLUMNS = (
    "split_id",
    "block_id",
    "status",
    "expected_test_ids",
    "failure_reason",
)
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
FIT_CONFIG_FIELDS = tuple(field.name for field in fields(FitConfig))
SCIENCE_SOURCE_FILES = {
    "genomeos/observations/schema.py": Path(observations_schema_module.__file__).resolve(),
    "genomeos/surfaces/config.py": Path(surface_config_module.__file__).resolve(),
    "genomeos/surfaces/fit.py": Path(surface_fit_module.__file__).resolve(),
    "genomeos/surfaces/observation.py": Path(observation_module.__file__).resolve(),
    "genomeos/surfaces/observation_prediction.py": Path(prediction_module.__file__).resolve(),
    "genomeos/validation/benchmark.py": Path(benchmark_module.__file__).resolve(),
    "genomeos/validation/predictive.py": Path(predictive_module.__file__).resolve(),
    "genomeos/validation/spatial_gp_benchmark.py": Path(
        spatial_benchmark_module.__file__
    ).resolve(),
    "genomeos/validation/spatial_gp_checkpoint.py": Path(checkpoint_module.__file__).resolve(),
    "genomeos/validation/splits.py": Path(splits_module.__file__).resolve(),
    "scripts/benchmark_spatial_gp.py": Path(__file__).resolve(),
}
OUTPUT_FILENAMES = ("fold_status.tsv", "inventory.json", "predictions.tsv", "summary.json")


def _positive_float(value: str) -> float:
    try:
        result = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a positive finite number") from error
    if not isfinite(result) or result <= 0.0:
        raise argparse.ArgumentTypeError("must be a positive finite number")
    return result


def _nonnegative_integer(value: str) -> int:
    try:
        result = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a nonnegative integer") from error
    if result < 0:
        raise argparse.ArgumentTypeError("must be a nonnegative integer")
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the nonpublication current spatial-GP count benchmark."
    )
    parser.add_argument("--observations", required=True, type=Path)
    parser.add_argument("--assignments", required=True, type=Path)
    parser.add_argument("--dependencies", required=True, type=Path)
    parser.add_argument("--fit-config", required=True, type=Path)
    parser.add_argument("--data-version", required=True)
    parser.add_argument("--buffer-km", required=True, type=_positive_float)
    parser.add_argument("--seed", type=_nonnegative_integer, default=42)
    parser.add_argument("--cdf-backend", choices=("scipy", "cupy"), default="scipy")
    parser.add_argument(
        "--evidence-kind",
        required=True,
        choices=("synthetic_fixture", "observational_research"),
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
    checkpoint = parser.add_mutually_exclusive_group(required=True)
    checkpoint.add_argument("--checkpoint-dir", type=Path)
    checkpoint.add_argument("--resume-from", type=Path)
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
        expected = (ROOT / relative).resolve()
        if actual != expected:
            raise ValueError(
                f"imported science source {relative!r} resolved outside this checkout: {actual}"
            )
    return dict(SCIENCE_SOURCE_FILES)


def _read_observations(path: Path) -> pd.DataFrame:
    if path.suffix == ".parquet":
        return validate_allele_observations(pd.read_parquet(path))
    if path.suffix not in {".tsv", ".txt"}:
        raise ValueError("observations must be a .tsv, .txt, or .parquet file")
    frame = pd.read_csv(
        path,
        sep="\t",
        dtype={column: str for column in OBSERVATION_LITERAL_COLUMNS},
        keep_default_na=False,
        na_filter=False,
    )
    return validate_allele_observations(frame)


def _read_auxiliary(path: Path, columns: tuple[str, ...], name: str) -> pd.DataFrame:
    frame = pd.read_csv(path, sep="\t", dtype=str, keep_default_na=False, na_filter=False)
    if frame.columns.duplicated().any() or tuple(frame.columns) != columns:
        raise ValueError(f"{name} TSV columns must be exactly {list(columns)}")
    for column in columns:
        valid = frame[column].map(lambda value: isinstance(value, str) and bool(value.strip()))
        if not valid.all():
            raise ValueError(f"{name} {column} values must be nonempty literal strings")
    return frame


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"fit config contains duplicate key {key!r}")
        result[key] = value
    return result


def _read_fit_config(path: Path) -> FitConfig:
    raw = json.loads(path.read_text(), object_pairs_hook=_unique_object)
    if not isinstance(raw, dict) or set(raw) != set(FIT_CONFIG_FIELDS):
        raise ValueError(f"fit config must contain exactly the FitConfig fields: {FIT_CONFIG_FIELDS}")
    values = dict(raw)
    if isinstance(values["hsgp_m"], list):
        values["hsgp_m"] = tuple(values["hsgp_m"])
    return FitConfig(**values)


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


def _package_versions(config: FitConfig, cdf_backend: str) -> dict[str, str]:
    names = ["genomeos", "numpy", "pandas", "scipy", "pandera", "pymc", "pytensor"]
    if config.nuts_sampler == "numpyro":
        names.extend(("jax", "jaxlib", "numpyro"))
    result = {"python": ".".join(str(value) for value in sys.version_info[:3])}
    for distribution in names:
        result[distribution] = importlib.metadata.version(distribution)
    if cdf_backend == "cupy":
        import cupy

        result["cupy"] = cupy.__version__
    return result


def _json_write(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, allow_nan=False, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )


def _write_tsv(frame: pd.DataFrame, path: Path) -> None:
    serialized = frame.copy()
    if "log_score" in serialized:
        serialized["log_score"] = serialized["log_score"].map(
            lambda value: "-Infinity" if value == -np.inf else value
        )
    serialized.to_csv(path, sep="\t", index=False, lineterminator="\n")


def _publish_result(
    output: Path,
    *,
    inventory: dict[str, object],
    predictions: pd.DataFrame,
    status_rows: list[dict[str, object]],
    summary_document: dict[str, object],
    manifest: dict[str, object],
) -> None:
    """Write a complete publication in a sibling staging directory, then rename atomically."""
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{output.name}.partial-", dir=output.parent)
    )
    try:
        _json_write(staging / "inventory.json", inventory)
        _write_tsv(predictions, staging / "predictions.tsv")
        _write_tsv(
            pd.DataFrame.from_records(status_rows, columns=FOLD_STATUS_COLUMNS),
            staging / "fold_status.tsv",
        )
        _json_write(staging / "summary.json", summary_document)
        manifest["output_files"] = {
            name: _file_record(staging / name) for name in OUTPUT_FILENAMES
        }
        _json_write(staging / "manifest.json", manifest)
        staging.rename(output)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def run(args: argparse.Namespace) -> int:
    """Validate inputs, execute the complete planned ledger, and write the manifest last."""
    if args.out.exists():
        raise ValueError(f"output directory already exists: {args.out}")
    checkpoint_path = args.checkpoint_dir or args.resume_from
    output_resolved = args.out.resolve()
    checkpoint_resolved = checkpoint_path.resolve()
    if (
        output_resolved == checkpoint_resolved
        or output_resolved in checkpoint_resolved.parents
        or checkpoint_resolved in output_resolved.parents
    ):
        raise ValueError("output and checkpoint directories must be disjoint")
    if args.checkpoint_dir is not None and checkpoint_path.exists():
        raise ValueError(f"checkpoint directory already exists: {checkpoint_path}")
    if args.resume_from is not None and not checkpoint_path.is_dir():
        raise ValueError(f"resume checkpoint directory does not exist: {checkpoint_path}")
    if not isinstance(args.data_version, str) or not args.data_version.strip():
        raise ValueError("data_version must be a nonempty string")
    science_sources = _resolved_science_sources()
    input_paths = {
        "assignments": args.assignments,
        "dependencies": args.dependencies,
        "fit_config": args.fit_config,
        "observations": args.observations,
    }
    input_files = {name: _file_record(path) for name, path in sorted(input_paths.items())}
    observations = _read_observations(args.observations)
    assignments = _read_auxiliary(args.assignments, ASSIGNMENT_COLUMNS, "assignments")
    dependencies = _read_auxiliary(args.dependencies, DEPENDENCY_COLUMNS, "dependencies")
    config = _read_fit_config(args.fit_config)
    dependency_pairs = tuple(
        dependencies.loc[:, DEPENDENCY_COLUMNS].itertuples(index=False, name=None)
    )
    plan = plan_single_variant_gp_benchmark(
        observations,
        assignments,
        dependency_pairs,
        buffer_km=args.buffer_km,
        data_version=args.data_version,
        config=config,
        seed=args.seed,
        cdf_backend=args.cdf_backend,
    )
    inventory = inventory_observations(observations)
    resolved_config = {
        "buffer_km": args.buffer_km,
        "cdf_backend": args.cdf_backend,
        "data_version": args.data_version,
        "fit_config": asdict(config),
        "seed": args.seed,
    }
    science_hashes = {
        relative: _file_record(path)["sha256"] for relative, path in science_sources.items()
    }
    package_versions = _package_versions(config, args.cdf_backend)
    qualification = {
        "assignment_review_status": args.assignment_review_status,
        "dependency_review_status": args.dependency_review_status,
        "scientific_promotion_decision": "not_made",
    }
    planned_splits = [asdict(split) for split in plan.splits]
    seed_schedule = [asdict(seeds) for seeds in spatial_gp_seed_schedule(plan)]
    checkpoint_header = build_checkpoint_header(
        model_id=MODEL_ID,
        evidence_kind=args.evidence_kind,
        qualification=qualification,
        configuration=resolved_config,
        input_files=input_files,
        planned_splits=planned_splits,
        seed_schedule=seed_schedule,
        code_revision=_code_revision(),
        science_source_sha256=science_hashes,
        package_versions=package_versions,
    )
    if args.checkpoint_dir is not None:
        initialize_checkpoint(checkpoint_path, checkpoint_header)
        fold_results = []
    else:
        fold_results = list(
            load_fold_checkpoints(checkpoint_path, checkpoint_header, plan.splits)
        )
    for ordinal in range(len(fold_results), len(plan.splits)):
        split = plan.splits[ordinal]
        fold_result = evaluate_single_variant_gp_fold(plan, split)
        write_fold_checkpoint(checkpoint_path, ordinal, split, fold_result)
        fold_results.append(fold_result)
    result = finalize_single_variant_gp_benchmark(plan, fold_results)

    status_by_id = {status.split_id: status for status in result.fold_status}
    split_records: list[dict[str, object]] = []
    status_rows: list[dict[str, object]] = []
    for split in result.splits:
        status = status_by_id[split.split_id]
        record = asdict(split)
        record.update({"status": status.status, "failure_reason": status.failure_reason})
        split_records.append(record)
        status_rows.append(
            {
                "split_id": split.split_id,
                "block_id": split.block_id,
                "status": status.status,
                "expected_test_ids": json.dumps(
                    list(status.expected_test_ids), separators=(",", ":")
                ),
                "failure_reason": status.failure_reason or "",
            }
        )

    manifest = {
        "schema_version": 1,
        "model": {
            "model_id": MODEL_ID,
            "name": MODEL_NAME,
            "resident_calibrated": False,
            "survey_heterogeneity_model": True,
        },
        "evidence_kind": args.evidence_kind,
        "publication_eligible": False,
        "qualification": qualification,
        "configuration": resolved_config,
        "configuration_sha256": _canonical_hash(resolved_config),
        "input_files": input_files,
        "inputs_sha256": _canonical_hash(input_files),
        "source_provenance": {
            "counts_by_source": inventory["counts_by_source"],
            "input_roles": sorted(input_files),
        },
        "splits": split_records,
        "split_manifest_sha256": _canonical_hash(split_records),
        "code_revision": checkpoint_header["code_revision"],
        "science_source_sha256": science_hashes,
        "package_versions": package_versions,
    }
    summary_document = {
        "schema_version": 1,
        "model_id": MODEL_ID,
        "evidence_kind": args.evidence_kind,
        "publication_eligible": False,
        "qualification": qualification,
        "benchmark": result.summary,
    }

    _publish_result(
        args.out,
        inventory=inventory,
        predictions=result.predictions,
        status_rows=status_rows,
        summary_document=summary_document,
        manifest=manifest,
    )
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
