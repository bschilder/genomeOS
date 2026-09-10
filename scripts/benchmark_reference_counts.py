#!/usr/bin/env python3
"""Run the reference-panel count benchmark (design §§ 5, 7, 8; #189).

This local-file adapter preserves every planned fold and unavailable row. Its
Beta-binomial predictions are marginal and must never be interpreted as joint draws.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import io
import json
import re
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
import genomeos.validation.count_baseline as count_baseline_module  # noqa: E402
import genomeos.validation.predictive as predictive_module  # noqa: E402
import genomeos.validation.reference_counts as reference_counts_module  # noqa: E402
from genomeos.validation.benchmark import (  # noqa: E402
    BenchmarkFoldStatus,
    summarize_benchmark,
    validate_predictive_diagnostics,
)
from genomeos.validation.count_baseline import B0InfeasibleError  # noqa: E402
from genomeos.validation.predictive import predictive_diagnostics  # noqa: E402
from genomeos.validation.reference_counts import (  # noqa: E402
    ReferenceCount,
    ReferenceInfeasibleError,
    fit_reference_b0,
    reference_group_folds,
    validate_reference_counts,
)

COUNT_COLUMNS = ("record_id", "variant_id", "group_id", "region_id", "variant_group", "ac", "an")
DIAGNOSTIC_COLUMNS = (
    "log_score", "absolute_error", "squared_error", "coverage_50", "interval_width_50",
    "coverage_80", "interval_width_80", "coverage_95", "interval_width_95", "randomized_pit",
)
PREDICTION_COLUMNS = (
    "split_id", "source_record_id", "variant_id", "region_id", "variant_group", "cohort_id",
    "observed_ac", "observed_an",
) + DIAGNOSTIC_COLUMNS
POSTERIOR_COLUMNS = (
    "split_id", "variant_id", "training_observation_count", "training_ac", "training_an",
    "posterior_alpha", "posterior_beta",
)
ROW_STATUS_COLUMNS = ("split_id", "record_id", "status", "reason")
OUTPUT_FILENAMES = ("splits.json", "row_status.tsv", "predictions.tsv", "posteriors.tsv", "summary.json")
INTEGER_TOKEN = re.compile(r"[+-]?[0-9]+\Z")


def _positive_float(value: str) -> float:
    try:
        result = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a positive finite number") from error
    if not isfinite(result) or result <= 0:
        raise argparse.ArgumentTypeError("must be a positive finite number")
    return result


def _nonnegative_integer(value: str) -> int:
    if not INTEGER_TOKEN.fullmatch(value):
        raise argparse.ArgumentTypeError("must be a nonnegative integer")
    result = int(value)
    if result < 0:
        raise argparse.ArgumentTypeError("must be a nonnegative integer")
    return result


def _positive_integer(value: str) -> int:
    result = _nonnegative_integer(value)
    if result < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a qualified reference-count B0 benchmark.")
    parser.add_argument("--counts", required=True, type=Path)
    parser.add_argument("--dependencies", required=True, type=Path)
    parser.add_argument("--source-release", required=True)
    parser.add_argument("--cohort-stage", required=True)
    parser.add_argument("--count-kind", required=True, choices=("called", "quality"))
    parser.add_argument("--evidence-role", required=True, choices=("development", "synthetic"))
    parser.add_argument("--prior-alpha", required=True, type=_positive_float)
    parser.add_argument("--prior-beta", required=True, type=_positive_float)
    parser.add_argument("--folds", type=_positive_integer, default=5)
    parser.add_argument("--seed", type=_nonnegative_integer, default=42)
    parser.add_argument("--out", required=True, type=Path)
    return parser


def _sha(path: Path) -> dict[str, object]:
    return _bytes_record(path.read_bytes())


def _bytes_record(data: bytes) -> dict[str, object]:
    return {"sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)}


def _read_counts(data: bytes) -> tuple[ReferenceCount, ...]:
    text = data.decode("utf-8")
    records = csv.reader(io.StringIO(text, newline=""), delimiter="\t", strict=True)
    try:
        header = next(records)
    except StopIteration as error:
        raise ValueError("count TSV must contain a header") from error
    if tuple(header) != COUNT_COLUMNS:
        raise ValueError(f"count TSV columns must be exactly {list(COUNT_COLUMNS)}")
    rows = []
    for line_number, record in enumerate(records, start=2):
        if len(record) != len(COUNT_COLUMNS):
            raise ValueError(f"count TSV logical record {line_number} must contain exactly 7 fields")
        source = dict(zip(COUNT_COLUMNS, record, strict=True))
        for column in ("ac", "an"):
            token = source[column]
            if not INTEGER_TOKEN.fullmatch(token):
                raise ValueError(f"{column} must contain only base-10 integer tokens")
            source[column] = int(token)
        rows.append(ReferenceCount(**source))
    return validate_reference_counts(rows)


def _read_dependencies(data: bytes) -> tuple[tuple[tuple[str, str], ...], str]:
    document = json.loads(data)
    if not isinstance(document, dict) or set(document) != {"edges", "qualification"}:
        raise ValueError("dependency JSON must contain exactly edges and qualification")
    qualification = document["qualification"]
    if not isinstance(qualification, str) or not qualification.strip():
        raise ValueError("dependency qualification must be nonempty text")
    edges = document["edges"]
    if not isinstance(edges, list):
        raise ValueError("dependency edges must be a list")
    return tuple(edges), qualification


def _json_write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, allow_nan=False, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def _write_tsv(frame: pd.DataFrame, path: Path) -> None:
    serialized = frame.copy()
    if "log_score" in serialized:
        serialized["log_score"] = serialized["log_score"].map(
            lambda value: "-Infinity" if value == -np.inf else value
        )
    serialized.to_csv(path, sep="\t", index=False, lineterminator="\n")


def _git_record() -> dict[str, object]:
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()
    dirty = bool(subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout)
    return {"head": revision, "dirty": dirty}


def _package_versions() -> dict[str, str]:
    return {
        name: importlib.metadata.version(name)
        for name in ("numpy", "scipy", "pandas")
    }


def _science_hashes() -> dict[str, str]:
    modules = {
        "genomeos/observations/schema.py": observations_schema_module,
        "genomeos/validation/benchmark.py": benchmark_module,
        "genomeos/validation/count_baseline.py": count_baseline_module,
        "genomeos/validation/predictive.py": predictive_module,
        "genomeos/validation/reference_counts.py": reference_counts_module,
    }
    result = {}
    for relative, module in modules.items():
        actual = Path(module.__file__).resolve()
        if actual != (ROOT / relative).resolve():
            raise ValueError(f"imported source {relative} resolved outside this checkout")
        result[relative] = str(_sha(actual)["sha256"])
    result["scripts/benchmark_reference_counts.py"] = str(_sha(Path(__file__).resolve())["sha256"])
    return result


def _seeds(seed: int, count: int) -> tuple[int, tuple[int, ...]]:
    split_sequence, pit_parent = np.random.SeedSequence(seed).spawn(2)
    split_seed = int(split_sequence.generate_state(1, dtype=np.uint32)[0])
    pit = tuple(int(child.generate_state(1, dtype=np.uint32)[0]) for child in pit_parent.spawn(count))
    return split_seed, pit


def run(args: argparse.Namespace) -> int:
    """Validate structure first, then publish a complete deterministic outcome ledger."""
    if args.out.exists():
        raise ValueError(f"output directory already exists: {args.out}")
    for field in ("source_release", "cohort_stage"):
        value = getattr(args, field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field} must be nonempty text")
    sources = _science_hashes()
    git_record = _git_record()
    package_versions = _package_versions()
    counts_bytes = args.counts.read_bytes()
    dependency_bytes = args.dependencies.read_bytes()
    input_files = {
        "counts": _bytes_record(counts_bytes),
        "dependencies": _bytes_record(dependency_bytes),
    }
    rows = _read_counts(counts_bytes)
    edges, qualification = _read_dependencies(dependency_bytes)
    split_seed, pit_seeds = _seeds(args.seed, args.folds)
    folds = reference_group_folds(rows, dependency_edges=edges, n_folds=args.folds, seed=split_seed)

    by_id = {row.record_id: row for row in rows}
    predictions: list[dict[str, object]] = []
    posteriors: list[dict[str, object]] = []
    row_status: list[dict[str, object]] = []
    statuses: list[BenchmarkFoldStatus] = []
    split_records = []
    for index, fold in enumerate(folds):
        training = tuple(by_id[key] for key in fold.train_ids)
        testing = tuple(by_id[key] for key in fold.test_ids)
        unavailable = tuple(row.record_id for row in testing if row.an == 0)
        scoreable = tuple(row for row in testing if row.an > 0)
        try:
            fitted = fit_reference_b0(
                training, testing, prior_alpha=args.prior_alpha, prior_beta=args.prior_beta
            )
            scored = tuple(by_id[key] for key in fitted.observation_ids)
            diagnostics = predictive_diagnostics(
                fitted.marginal_predictive,
                [row.ac for row in scored],
                [row.an for row in scored],
                seed=pit_seeds[index],
            )
            diagnostics = validate_predictive_diagnostics(diagnostics)
            for position, row in enumerate(scored):
                record = {
                    "split_id": fold.split_id, "source_record_id": row.record_id,
                    "variant_id": row.variant_id, "region_id": row.region_id,
                    "variant_group": row.variant_group, "cohort_id": row.group_id,
                    "observed_ac": row.ac, "observed_an": row.an,
                }
                record.update(diagnostics.iloc[position].to_dict())
                predictions.append(record)
            for posterior in fitted.posteriors:
                record = asdict(posterior)
                record.update({
                    "split_id": fold.split_id,
                    "posterior_alpha": record.pop("alpha"),
                    "posterior_beta": record.pop("beta"),
                })
                posteriors.append(record)
            state, reason = "completed", None
        except (B0InfeasibleError, ReferenceInfeasibleError) as error:
            state, reason = "infeasible", str(error)
        except (ArithmeticError, FloatingPointError, ValueError) as error:
            state, reason = "failed", f"{type(error).__name__}: {error}"

        expected = tuple(row.record_id for row in scoreable) if state == "completed" else fold.test_ids
        statuses.append(BenchmarkFoldStatus(fold.split_id, state, expected, reason))
        for row in testing:
            if row.record_id in unavailable:
                status, row_reason = "unavailable_denominator", "AN is zero"
            elif state == "completed":
                status, row_reason = "scored", ""
            else:
                status, row_reason = state, reason
            row_status.append(
                {
                    "split_id": fold.split_id,
                    "record_id": row.record_id,
                    "status": status,
                    "reason": row_reason,
                }
            )
        split_records.append({
            **asdict(fold), "status": state, "failure_reason": reason, "pit_seed": pit_seeds[index]
        })

    prediction_frame = pd.DataFrame.from_records(predictions, columns=PREDICTION_COLUMNS).sort_values(
        ["split_id", "source_record_id"]
    ).reset_index(drop=True)
    posterior_frame = pd.DataFrame.from_records(posteriors, columns=POSTERIOR_COLUMNS).sort_values(
        ["split_id", "variant_id"]
    ).reset_index(drop=True)
    status_frame = pd.DataFrame.from_records(row_status, columns=ROW_STATUS_COLUMNS).sort_values(
        ["split_id", "record_id"]
    ).reset_index(drop=True)
    summary = summarize_benchmark(prediction_frame, statuses, tuple(fold.split_id for fold in folds))
    summary.update({
        "target": "reference_panel_within_resource", "evidence_role": args.evidence_role,
        "joint_prediction_supported": False,
        "weighting_unit": "source_population_group_not_independent_study",
        "total_row_count": len(rows),
        "unavailable_row_count": int(
            (status_frame.status == "unavailable_denominator").sum()
        ),
        "failed_row_count": int(status_frame.status.isin(["failed", "infeasible"]).sum()),
    })
    configuration = {
        "source_release": args.source_release, "cohort_stage": args.cohort_stage,
        "count_kind": args.count_kind, "evidence_role": args.evidence_role,
        "prior_alpha": args.prior_alpha, "prior_beta": args.prior_beta,
        "folds": args.folds, "seed": args.seed,
    }
    split_document = {"configuration": configuration, "split_seed": split_seed, "folds": split_records}
    args.out.mkdir(parents=True, exist_ok=False)
    _json_write(args.out / "splits.json", split_document)
    _write_tsv(status_frame, args.out / "row_status.tsv")
    _write_tsv(prediction_frame, args.out / "predictions.tsv")
    _write_tsv(posterior_frame, args.out / "posteriors.tsv")
    _json_write(args.out / "summary.json", summary)
    manifest = {
        "schema_version": 1, "target": "reference_panel_within_resource",
        "joint_prediction_supported": False,
        "limitations": [
            "Reference-resource operational groups are not certified independent studies.",
            "Marginal predictions are not coherent joint draws.",
            "This development evidence does not establish external generalization or release fitness.",
        ],
        "configuration": configuration,
        "dependency_qualification": qualification,
        "input_files": input_files,
        "seeds": {
            "root": args.seed,
            "split": split_seed,
            "pit_by_fold": dict(
                zip((fold.split_id for fold in folds), pit_seeds, strict=True)
            ),
        },
        "git": git_record,
        "science_source_sha256": sources,
        "package_versions": package_versions,
        "output_files": {name: _sha(args.out / name) for name in OUTPUT_FILENAMES},
    }
    _json_write(args.out / "manifest.json", manifest)
    return 0 if summary["comparison_complete"] else 2


def main() -> int:
    parser = _parser()
    try:
        return run(parser.parse_args())
    except (OSError, TypeError, ValueError, json.JSONDecodeError, subprocess.SubprocessError) as error:
        parser.exit(2, f"error: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
