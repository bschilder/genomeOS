#!/usr/bin/env python3
"""Run sharded B1G nested count benchmarking (design §§4–8, 12; #331).

The adapter has three explicit modes: freeze a campaign identity, compute one independent outer
fold, or finalize a complete shard set. It never makes a promotion decision or serves inference.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import resource
import shutil
import subprocess
import sys
import tempfile
import time
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
import genomeos.surfaces.convergence as convergence_module  # noqa: E402
import genomeos.surfaces.observation as observation_module  # noqa: E402
import genomeos.validation.b1g_attempt as attempt_module  # noqa: E402
import genomeos.validation.b1g_basis as basis_module  # noqa: E402
import genomeos.validation.b1g_benchmark as benchmark_module  # noqa: E402
import genomeos.validation.b1g_checkpoint as checkpoint_module  # noqa: E402
import genomeos.validation.b1g_fit as fit_module  # noqa: E402
import genomeos.validation.benchmark as reporting_module  # noqa: E402
import genomeos.validation.nested_folds as nested_folds_module  # noqa: E402
import genomeos.validation.predictive as predictive_module  # noqa: E402
import genomeos.validation.splits as splits_module  # noqa: E402
from genomeos.surfaces.config import FitConfig  # noqa: E402
from genomeos.validation.b1g_benchmark import (  # noqa: E402
    B1GBenchmarkConfig,
    derive_b1g_seed,
    evaluate_b1g_fold,
    plan_b1g_benchmark,
)
from genomeos.validation.b1g_checkpoint import (  # noqa: E402
    B1GFoldRuntime,
    finalize_b1g_checkpoint,
    load_b1g_fold_shards,
    write_b1g_fold_shard,
)
from genomeos.validation.benchmark import inventory_observations, validate_allele_observations  # noqa: E402
from genomeos.validation.nested_folds import (  # noqa: E402
    THREE_INNER_FOLD_ALGORITHM,
    THREE_INNER_FOLD_COUNT,
)
from genomeos.validation.spatial_gp_checkpoint import (  # noqa: E402
    build_checkpoint_header,
    initialize_checkpoint,
)

MODEL_ID = "B1G"
MODEL_NAME = "compact_positive_basis_count_model"
ASSIGNMENT_COLUMNS = ("source_record_id", "block_id", "region_id", "variant_group")
DEPENDENCY_COLUMNS = ("source_record_id_a", "source_record_id_b")
FIT_CONFIG_FIELDS = tuple(field.name for field in fields(FitConfig))
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
    "candidate_scores.tsv",
    "fold_status.tsv",
    "inner_folds.tsv",
    "inventory.json",
    "predictions.tsv",
    "summary.json",
)
SCIENCE_SOURCE_FILES = {
    "genomeos/observations/schema.py": Path(observations_schema_module.__file__).resolve(),
    "genomeos/surfaces/config.py": Path(surface_config_module.__file__).resolve(),
    "genomeos/surfaces/convergence.py": Path(convergence_module.__file__).resolve(),
    "genomeos/surfaces/observation.py": Path(observation_module.__file__).resolve(),
    "genomeos/validation/b1g_attempt.py": Path(attempt_module.__file__).resolve(),
    "genomeos/validation/b1g_basis.py": Path(basis_module.__file__).resolve(),
    "genomeos/validation/b1g_benchmark.py": Path(benchmark_module.__file__).resolve(),
    "genomeos/validation/b1g_checkpoint.py": Path(checkpoint_module.__file__).resolve(),
    "genomeos/validation/b1g_fit.py": Path(fit_module.__file__).resolve(),
    "genomeos/validation/benchmark.py": Path(reporting_module.__file__).resolve(),
    "genomeos/validation/nested_folds.py": Path(nested_folds_module.__file__).resolve(),
    "genomeos/validation/predictive.py": Path(predictive_module.__file__).resolve(),
    "genomeos/validation/splits.py": Path(splits_module.__file__).resolve(),
    "scripts/benchmark_b1g.py": Path(__file__).resolve(),
}


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
    parser = argparse.ArgumentParser(description="Run the nonpublication sharded B1G benchmark.")
    parser.add_argument("--observations", required=True, type=Path)
    parser.add_argument("--assignments", required=True, type=Path)
    parser.add_argument("--dependencies", required=True, type=Path)
    parser.add_argument("--fit-config", required=True, type=Path)
    parser.add_argument("--data-version", required=True)
    parser.add_argument("--buffer-km", required=True, type=_positive_float)
    parser.add_argument("--query-chunk-size", type=_nonnegative_integer, default=1024)
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
    parser.add_argument("--checkpoint-dir", required=True, type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--initialize", action="store_true")
    mode.add_argument("--fold-index", type=_nonnegative_integer)
    mode.add_argument("--finalize", action="store_true")
    parser.add_argument("--out", type=Path)
    return parser


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_hash(value: object) -> str:
    return _sha256_bytes(
        json.dumps(value, allow_nan=False, separators=(",", ":"), sort_keys=True).encode()
    )


def _file_record(path: Path) -> dict[str, object]:
    data = path.read_bytes()
    return {"sha256": _sha256_bytes(data), "size_bytes": len(data)}


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
        if not frame[column].map(lambda value: isinstance(value, str) and bool(value.strip())).all():
            raise ValueError(f"{name} {column} values must be nonempty literal strings")
    return frame


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"fit config contains duplicate key {key!r}")
        result[key] = value
    return result


def _read_fit_config(path: Path) -> FitConfig:
    raw = json.loads(path.read_text(), object_pairs_hook=_unique_object)
    if not isinstance(raw, dict) or set(raw) != set(FIT_CONFIG_FIELDS):
        raise ValueError(f"fit config must contain exactly the FitConfig fields: {FIT_CONFIG_FIELDS}")
    if isinstance(raw["hsgp_m"], list):
        raw["hsgp_m"] = tuple(raw["hsgp_m"])
    return FitConfig(**raw)


def _code_revision() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
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
    for name in names:
        result[name] = importlib.metadata.version(name)
    if cdf_backend == "cupy":
        import cupy

        result["cupy"] = cupy.__version__
    return result


def _device_name() -> str:
    try:
        import jax

        devices = tuple(sorted(str(device) for device in jax.devices()))
    except (ImportError, RuntimeError) as error:
        return f"unavailable:{type(error).__name__}"
    return ",".join(devices) if devices else "unavailable:no_devices"


def _peak_rss_bytes() -> int:
    value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return value if sys.platform == "darwin" else value * 1024


def _science_hashes() -> dict[str, str]:
    result = {}
    for relative, actual in SCIENCE_SOURCE_FILES.items():
        expected = (ROOT / relative).resolve()
        if actual != expected:
            raise ValueError(f"imported science source {relative!r} resolved outside this checkout")
        result[relative] = str(_file_record(actual)["sha256"])
    return result


def _json_write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, allow_nan=False, indent=2, sort_keys=True) + "\n")


def _write_tsv(frame: pd.DataFrame, path: Path) -> None:
    serialized = frame.copy()
    for column in ("log_score", "mean_log_score"):
        if column in serialized:
            serialized[column] = serialized[column].map(
                lambda value: "-Infinity" if value == -np.inf else value
            )
    serialized.to_csv(path, sep="\t", index=False, lineterminator="\n")


def _build_campaign(args: argparse.Namespace):
    if not isinstance(args.data_version, str) or not args.data_version.strip():
        raise ValueError("data_version must be a nonempty string")
    if args.query_chunk_size <= 0:
        raise ValueError("query_chunk_size must be positive")
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
    fit_config = _read_fit_config(args.fit_config)
    config = B1GBenchmarkConfig(fit_config, args.query_chunk_size, args.cdf_backend)
    pairs = tuple(dependencies.loc[:, DEPENDENCY_COLUMNS].itertuples(index=False, name=None))
    plan = plan_b1g_benchmark(
        observations,
        assignments,
        pairs,
        buffer_km=args.buffer_km,
        data_version=args.data_version,
        config=config,
        seed=args.seed,
    )
    qualification = {
        "assignment_review_status": args.assignment_review_status,
        "dependency_review_status": args.dependency_review_status,
        "scientific_promotion_decision": "not_made",
    }
    resolved = {
        "buffer_km": args.buffer_km,
        "candidate_grid": {
            "radii_km": [500.0, 1000.0, 2000.0],
            "basis_counts": [8, 16, 32],
        },
        "cdf_backend": args.cdf_backend,
        "data_version": args.data_version,
        "fit_config": asdict(fit_config),
        "fit_retry_protocol": {
            "admission_error": "B1GConvergenceError",
            "draws_multiplier": 2,
            "maximum_retries": 1,
            "tune_multiplier": 2,
        },
        "inner_fold_protocol": {
            "algorithm": THREE_INNER_FOLD_ALGORITHM,
            "fold_count": THREE_INNER_FOLD_COUNT,
        },
        "query_chunk_size": args.query_chunk_size,
        "sampler_convergence_gate": {
            "maximum_divergences": 0,
            "maximum_rhat": fit_config.max_rhat,
            "minimum_bulk_ess": fit_config.min_ess,
            "minimum_tail_ess": fit_config.min_ess,
        },
        "seed": args.seed,
    }
    seed_schedule = [
        {
            "split_id": split.split_id,
            "selection_seed": derive_b1g_seed(args.seed, split.split_id, "selection"),
        }
        for split in plan.splits
    ]
    header = build_checkpoint_header(
        model_id=MODEL_ID,
        evidence_kind=args.evidence_kind,
        qualification=qualification,
        configuration=resolved,
        input_files=input_files,
        planned_splits=[asdict(split) for split in plan.splits],
        seed_schedule=seed_schedule,
        code_revision=_code_revision(),
        science_source_sha256=_science_hashes(),
        package_versions=_package_versions(fit_config, args.cdf_backend),
    )
    return plan, header, inventory_observations(observations), input_files, qualification, resolved


def _diagnostics_columns(prefix: str, diagnostics) -> dict[str, object]:
    if diagnostics is None:
        return {
            f"{prefix}{name}": ""
            for name in (
                "max_rhat",
                "max_rhat_parameter",
                "min_bulk_ess",
                "min_bulk_ess_parameter",
                "min_tail_ess",
                "min_tail_ess_parameter",
                "divergence_count",
            )
        }
    return {f"{prefix}{key}": value for key, value in asdict(diagnostics).items()}


def _attempts_json(attempts) -> str:
    return json.dumps(
        [asdict(attempt) for attempt in attempts],
        separators=(",", ":"),
        sort_keys=True,
    )


def _evidence_tables(shards):
    fold_rows = []
    candidate_rows = []
    inner_rows = []
    for shard in shards:
        status = shard.result.status
        status_record = asdict(status)
        status_record["expected_test_ids"] = json.dumps(
            list(status.expected_test_ids), separators=(",", ":")
        )
        fold_rows.append(
            {
                "ordinal": shard.ordinal,
                **status_record,
                "fit_attempts": _attempts_json(shard.result.fit_attempts),
                **_diagnostics_columns("", shard.result.sampler_diagnostics),
                **asdict(shard.runtime),
            }
        )
        for score in shard.result.candidate_scores:
            score_record = {
                key: value for key, value in asdict(score).items() if key != "inner_folds"
            }
            score_record["failure_reasons"] = json.dumps(
                list(score.failure_reasons), separators=(",", ":")
            )
            candidate_rows.append(
                {
                    "outer_split_id": status.split_id,
                    **score_record,
                }
            )
            for inner in score.inner_folds:
                inner_record = {
                    key: value
                    for key, value in asdict(inner).items()
                    if key not in {"fit_attempts", "sampler_diagnostics"}
                }
                inner_record["expected_test_ids"] = json.dumps(
                    list(inner.expected_test_ids), separators=(",", ":")
                )
                inner_record["source_block_ids"] = json.dumps(
                    list(inner.source_block_ids), separators=(",", ":")
                )
                inner_record["fit_attempts"] = _attempts_json(inner.fit_attempts)
                inner_rows.append(
                    {
                        "outer_split_id": status.split_id,
                        "radius_km": score.radius_km,
                        "basis_count": score.basis_count,
                        **inner_record,
                        **_diagnostics_columns("", inner.sampler_diagnostics),
                    }
                )
    return (
        pd.DataFrame.from_records(fold_rows),
        pd.DataFrame.from_records(candidate_rows),
        pd.DataFrame.from_records(inner_rows),
    )


def _publish(
    output: Path,
    *,
    result,
    shards,
    header,
    inventory,
    input_files,
    qualification,
    configuration,
) -> None:
    if output.exists():
        raise ValueError(f"output directory already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}.partial-", dir=output.parent))
    try:
        folds, candidates, inner = _evidence_tables(shards)
        _write_tsv(result.predictions, staging / "predictions.tsv")
        _write_tsv(folds, staging / "fold_status.tsv")
        _write_tsv(candidates, staging / "candidate_scores.tsv")
        _write_tsv(inner, staging / "inner_folds.tsv")
        _json_write(staging / "inventory.json", inventory)
        _json_write(
            staging / "summary.json",
            {
                "schema_version": 1,
                "model_id": MODEL_ID,
                "publication_eligible": False,
                "benchmark": result.summary,
            },
        )
        manifest = {
            "schema_version": 1,
            "model": {"model_id": MODEL_ID, "name": MODEL_NAME},
            "evidence_kind": header["evidence_kind"],
            "publication_eligible": False,
            "qualification": qualification,
            "configuration": configuration,
            "configuration_sha256": _canonical_hash(configuration),
            "input_files": input_files,
            "inputs_sha256": _canonical_hash(input_files),
            "folds": [
                {
                    "ordinal": shard.ordinal,
                    "status": asdict(shard.result.status),
                    "runtime": asdict(shard.runtime),
                }
                for shard in shards
            ],
            "checkpoint_header_sha256": header["header_sha256"],
            "code_revision": header["code_revision"],
            "science_source_sha256": header["science_source_sha256"],
            "package_versions": header["package_versions"],
            "output_files": {
                name: _file_record(staging / name) for name in OUTPUT_FILENAMES
            },
        }
        _json_write(staging / "manifest.json", manifest)
        staging.rename(output)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def run(args: argparse.Namespace) -> int:
    plan, header, inventory, input_files, qualification, configuration = _build_campaign(args)
    if args.initialize:
        if args.out is not None:
            raise ValueError("--out is only valid with --finalize")
        initialize_checkpoint(args.checkpoint_dir, header)
        return 0
    load_b1g_fold_shards(args.checkpoint_dir, header, plan)
    if args.fold_index is not None:
        if args.out is not None:
            raise ValueError("--out is only valid with --finalize")
        if args.fold_index >= len(plan.splits):
            raise ValueError("fold index is outside the frozen split ledger")
        started = time.perf_counter()
        result = evaluate_b1g_fold(plan, plan.splits[args.fold_index])
        runtime = B1GFoldRuntime(
            elapsed_seconds=time.perf_counter() - started,
            peak_rss_bytes=_peak_rss_bytes(),
            device=_device_name(),
            query_chunk_size=plan.config.query_chunk_size,
        )
        write_b1g_fold_shard(
            args.checkpoint_dir,
            header,
            plan,
            args.fold_index,
            result,
            runtime,
        )
        return 0 if result.status.status == "completed" else 1
    if args.out is None:
        raise ValueError("--finalize requires --out")
    result = finalize_b1g_checkpoint(args.checkpoint_dir, header, plan)
    shards = load_b1g_fold_shards(args.checkpoint_dir, header, plan)
    _publish(
        args.out,
        result=result,
        shards=shards,
        header=header,
        inventory=inventory,
        input_files=input_files,
        qualification=qualification,
        configuration=configuration,
    )
    return 0 if result.summary["comparison_complete"] else 1


def main() -> int:
    parser = _parser()
    try:
        return run(parser.parse_args())
    except (OSError, TypeError, ValueError, subprocess.SubprocessError) as error:
        parser.exit(2, f"error: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
