#!/usr/bin/env python3
"""Run the offline B0 allele-frequency benchmark (design §§ 5, 7, 8; #189).

This is a thin file/CLI adapter around the reviewed validation modules. The scientific model is
implemented in ``genomeos.validation.baseline``; split construction, predictive scoring and
hierarchical reporting are delegated to their public interfaces.
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
import genomeos.validation.baseline as baseline_module  # noqa: E402
import genomeos.validation.benchmark as benchmark_module  # noqa: E402
import genomeos.validation.predictive as predictive_module  # noqa: E402
import genomeos.validation.splits as splits_module  # noqa: E402
from genomeos.validation.baseline import B0InfeasibleError, fit_pooled_b0  # noqa: E402
from genomeos.validation.benchmark import (  # noqa: E402
    BenchmarkFoldStatus,
    inventory_observations,
    summarize_benchmark,
    validate_allele_observations,
)
from genomeos.validation.predictive import predictive_diagnostics  # noqa: E402
from genomeos.validation.splits import build_buffered_splits  # noqa: E402

MODEL_ID = "B0"
MODEL_NAME = "per_variant_pooled_beta_posterior_binomial_count_model"
ASSIGNMENT_COLUMNS = ("source_record_id", "block_id", "region_id", "variant_group")
DEPENDENCY_COLUMNS = ("source_record_id_a", "source_record_id_b")
DIAGNOSTIC_COLUMNS = (
    "log_score",
    "absolute_error",
    "squared_error",
    "coverage_50",
    "interval_width_50",
    "coverage_80",
    "interval_width_80",
    "coverage_95",
    "interval_width_95",
    "randomized_pit",
)
PREDICTION_COLUMNS = (
    "split_id",
    "block_id",
    "source_record_id",
    "variant_id",
    "region_id",
    "variant_group",
    "cohort_id",
    "observed_ac",
    "observed_an",
    "posterior_alpha",
    "posterior_beta",
    "posterior_mean",
    "posterior_draw_seed",
    "predictive_seed",
) + DIAGNOSTIC_COLUMNS
FOLD_STATUS_COLUMNS = (
    "split_id",
    "block_id",
    "status",
    "expected_test_ids",
    "failure_reason",
    "posterior_seed",
    "predictive_seed",
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
SCIENCE_SOURCE_FILES = {
    "genomeos/observations/schema.py": Path(observations_schema_module.__file__).resolve(),
    "genomeos/validation/baseline.py": Path(baseline_module.__file__).resolve(),
    "genomeos/validation/benchmark.py": Path(benchmark_module.__file__).resolve(),
    "genomeos/validation/predictive.py": Path(predictive_module.__file__).resolve(),
    "genomeos/validation/splits.py": Path(splits_module.__file__).resolve(),
    "scripts/benchmark_allele_frequency.py": Path(__file__).resolve(),
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


def _positive_integer(value: str) -> int:
    try:
        result = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a positive integer") from error
    if result <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
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
        description="Run the nonpublication B0 pooled allele-count benchmark."
    )
    parser.add_argument("--observations", required=True, type=Path)
    parser.add_argument("--assignments", required=True, type=Path)
    parser.add_argument("--dependencies", required=True, type=Path)
    parser.add_argument("--data-version", required=True)
    parser.add_argument("--prior-alpha", required=True, type=_positive_float)
    parser.add_argument("--prior-beta", required=True, type=_positive_float)
    parser.add_argument("--buffer-km", required=True, type=_positive_float)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument(
        "--evidence-kind",
        required=True,
        choices=("synthetic_fixture", "observational_research"),
    )
    parser.add_argument("--seed", type=_nonnegative_integer, default=42)
    parser.add_argument("--posterior-draws", type=_positive_integer, default=2048)
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


def _validate_assignments(observations: pd.DataFrame, assignments: pd.DataFrame) -> None:
    if assignments["source_record_id"].duplicated().any():
        raise ValueError("assignments must map each source_record_id exactly once")
    observation_ids = set(observations["source_record_id"])
    assignment_ids = set(assignments["source_record_id"])
    if assignment_ids != observation_ids:
        raise ValueError("assignments must map exactly the observation source_record_id set")

    joined = assignments.merge(
        observations.loc[:, ["source_record_id", "variant_id"]],
        on="source_record_id",
        validate="one_to_one",
    )
    groups_per_variant = joined.groupby("variant_id")["variant_group"].nunique()
    if (groups_per_variant != 1).any():
        inconsistent = sorted(groups_per_variant[groups_per_variant != 1].index)
        raise ValueError(f"each variant_id must map to exactly one variant_group: {inconsistent}")


def _validate_modern_alleles(observations: pd.DataFrame) -> None:
    phenotype = observations["variant_id"].str.startswith("phenotype:")
    if phenotype.any():
        raise ValueError("B0 allele-frequency benchmark rejects phenotype-prefixed IDs")
    dated = (observations["date_lower"] != 0) | (observations["date_upper"] != 0)
    if dated.any():
        raise ValueError("B0 allele-frequency benchmark requires zero date bounds")


def _fold_seed(seed: int, split_id: str, purpose: str) -> int:
    digest = hashlib.sha256(f"{seed}\0{split_id}\0{purpose}".encode()).digest()
    return int.from_bytes(digest[:4], "big")


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
    result = {"python": ".".join(str(value) for value in sys.version_info[:3])}
    for distribution in ("genomeos", "numpy", "pandas", "scipy", "pandera"):
        result[distribution] = importlib.metadata.version(distribution)
    return result


def _split_record(
    split,
    posterior_seed: int,
    predictive_seed: int,
    status: str,
    failure_reason: str | None,
) -> dict[str, object]:
    record = asdict(split)
    record["posterior_seed"] = posterior_seed
    record["predictive_seed"] = predictive_seed
    record["status"] = status
    record["failure_reason"] = failure_reason
    return record


def _fold_predictions(
    observations: pd.DataFrame,
    assignments: pd.DataFrame,
    split,
    *,
    prior_alpha: float,
    prior_beta: float,
    posterior_draws: int,
    posterior_seed: int,
    predictive_seed: int,
) -> pd.DataFrame:
    by_id = observations.set_index("source_record_id", drop=False)
    training = by_id.loc[list(split.train_ids)].reset_index(drop=True)
    testing = by_id.loc[list(split.test_ids)].reset_index(drop=True)
    fit = fit_pooled_b0(
        training,
        testing,
        prior_alpha=prior_alpha,
        prior_beta=prior_beta,
        posterior_draws=posterior_draws,
        seed=posterior_seed,
    )
    diagnostics = predictive_diagnostics(
        fit.predictive,
        testing["ac"].to_numpy(),
        testing["an"].to_numpy(),
        seed=predictive_seed,
    )
    posterior_by_variant = {posterior.variant_id: posterior for posterior in fit.posteriors}
    assignment_by_id = assignments.set_index("source_record_id")
    rows: list[dict[str, object]] = []
    for index, observation in enumerate(testing.itertuples(index=False)):
        posterior = posterior_by_variant[observation.variant_id]
        assignment = assignment_by_id.loc[observation.source_record_id]
        row = {
            "split_id": split.split_id,
            "block_id": split.block_id,
            "source_record_id": observation.source_record_id,
            "variant_id": observation.variant_id,
            "region_id": assignment["region_id"],
            "variant_group": assignment["variant_group"],
            "cohort_id": observation.cohort_id,
            "observed_ac": int(observation.ac),
            "observed_an": int(observation.an),
            "posterior_alpha": posterior.alpha,
            "posterior_beta": posterior.beta,
            "posterior_mean": posterior.alpha / (posterior.alpha + posterior.beta),
            "posterior_draw_seed": posterior_seed,
            "predictive_seed": predictive_seed,
        }
        row.update(diagnostics.iloc[index].to_dict())
        rows.append(row)
    return pd.DataFrame.from_records(rows, columns=PREDICTION_COLUMNS)


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


def run(args: argparse.Namespace) -> int:
    """Validate inputs, run every frozen fold, and write deterministic artifacts."""
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
    _validate_modern_alleles(observations)
    assignments = _read_auxiliary(args.assignments, ASSIGNMENT_COLUMNS, "assignments")
    dependencies = _read_auxiliary(args.dependencies, DEPENDENCY_COLUMNS, "dependencies")
    _validate_assignments(observations, assignments)
    dependency_pairs = tuple(
        dependencies.loc[:, DEPENDENCY_COLUMNS].itertuples(index=False, name=None)
    )
    splits = build_buffered_splits(
        observations,
        assignments.loc[:, ["source_record_id", "block_id"]],
        dependency_pairs,
        buffer_km=args.buffer_km,
        data_version=args.data_version,
    )

    fold_statuses: list[BenchmarkFoldStatus] = []
    status_rows: list[dict[str, object]] = []
    prediction_frames: list[pd.DataFrame] = []
    split_records: list[dict[str, object]] = []
    for split in splits:
        posterior_seed = _fold_seed(args.seed, split.split_id, "posterior")
        predictive_seed = _fold_seed(args.seed, split.split_id, "predictive")
        try:
            prediction_frames.append(
                _fold_predictions(
                    observations,
                    assignments,
                    split,
                    prior_alpha=args.prior_alpha,
                    prior_beta=args.prior_beta,
                    posterior_draws=args.posterior_draws,
                    posterior_seed=posterior_seed,
                    predictive_seed=predictive_seed,
                )
            )
            status = "completed"
            failure_reason = None
        except B0InfeasibleError as error:
            status = "infeasible"
            failure_reason = str(error)
        except Exception as error:  # Preserve a failed planned fold instead of dropping it.
            status = "failed"
            failure_reason = f"{type(error).__name__}: {error}"
        fold_status = BenchmarkFoldStatus(
            split.split_id,
            status,
            split.test_ids,
            failure_reason,
        )
        fold_statuses.append(fold_status)
        split_records.append(
            _split_record(
                split,
                posterior_seed,
                predictive_seed,
                status,
                failure_reason,
            )
        )
        status_rows.append(
            {
                "split_id": split.split_id,
                "block_id": split.block_id,
                "status": status,
                "expected_test_ids": json.dumps(list(split.test_ids), separators=(",", ":")),
                "failure_reason": failure_reason or "",
                "posterior_seed": posterior_seed,
                "predictive_seed": predictive_seed,
            }
        )

    predictions = (
        pd.concat(prediction_frames, ignore_index=True)
        if prediction_frames
        else pd.DataFrame(columns=PREDICTION_COLUMNS)
    )
    predictions = predictions.sort_values(["split_id", "source_record_id"]).reset_index(drop=True)
    summary = summarize_benchmark(
        predictions,
        fold_statuses,
        tuple(split.split_id for split in splits),
    )
    inventory = inventory_observations(observations)
    configuration = {
        "buffer_km": args.buffer_km,
        "data_version": args.data_version,
        "posterior_draws": args.posterior_draws,
        "prior_alpha": args.prior_alpha,
        "prior_beta": args.prior_beta,
        "seed": args.seed,
    }
    science_hashes = {
        relative: _file_record(path)["sha256"] for relative, path in science_sources.items()
    }
    manifest = {
        "schema_version": 1,
        "model": {
            "model_id": MODEL_ID,
            "name": MODEL_NAME,
            "resident_calibrated": False,
            "survey_heterogeneity_model": False,
        },
        "evidence_kind": args.evidence_kind,
        "publication_eligible": False,
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
        "science_source_sha256": science_hashes,
        "package_versions": _package_versions(),
    }
    summary_document = {
        "schema_version": 1,
        "model_id": MODEL_ID,
        "evidence_kind": args.evidence_kind,
        "publication_eligible": False,
        "benchmark": summary,
    }

    args.out.mkdir(parents=True, exist_ok=False)
    _json_write(args.out / "inventory.json", inventory)
    _write_tsv(predictions, args.out / "predictions.tsv")
    _write_tsv(
        pd.DataFrame.from_records(status_rows, columns=FOLD_STATUS_COLUMNS),
        args.out / "fold_status.tsv",
    )
    _json_write(args.out / "summary.json", summary_document)
    manifest["output_files"] = {
        name: _file_record(args.out / name) for name in OUTPUT_FILENAMES
    }
    _json_write(args.out / "manifest.json", manifest)
    return 0 if summary["comparison_complete"] else 1


def main() -> int:
    parser = _parser()
    args = parser.parse_args()
    try:
        return run(args)
    except (OSError, TypeError, ValueError, subprocess.SubprocessError) as error:
        parser.exit(2, f"error: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
