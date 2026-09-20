"""Matched predictive-benchmark comparison (design §§4, 6–8; issue #189).

The public :func:`compare_paired_benchmarks` boundary compares two complete benchmark prediction
tables on exactly the same held-out observations. It reuses :func:`summarize_benchmark` for the
balanced macro estimand, retains zero-count and positive-count results separately, and computes an
exhaustive paired outer-block bootstrap interval for integrated log-score differences.

This module is descriptive. It does not certify dependencies, select a winner, make a scientific
promotion decision, read artifacts, fit a model, or render a surface.
"""

from __future__ import annotations

from collections.abc import Sequence
from math import isfinite

import numpy as np
import pandas as pd

from genomeos.validation.benchmark import BenchmarkFoldStatus, summarize_benchmark

_KEY_COLUMNS = ("split_id", "source_record_id")
_IDENTITY_COLUMNS = (
    "block_id",
    "variant_id",
    "region_id",
    "variant_group",
    "cohort_id",
    "observed_ac",
    "observed_an",
)
_COVERAGE_LEVELS = (50, 80, 95)


def _require_complete_statuses(
    statuses: Sequence[BenchmarkFoldStatus], expected_split_ids: Sequence[str]
) -> tuple[BenchmarkFoldStatus, ...]:
    records = tuple(statuses)
    expected = tuple(expected_split_ids)
    if not expected or len(set(expected)) != len(expected):
        raise ValueError("expected_split_ids must be nonempty and unique")
    if tuple(status.split_id for status in records) != expected:
        raise ValueError("fold statuses must follow the complete expected split order")
    if any(status.status != "completed" for status in records):
        raise ValueError("paired comparison requires every planned fold to be completed")
    return records


def _matched_predictions(
    candidate: pd.DataFrame, baseline: pd.DataFrame
) -> pd.DataFrame:
    required = set(_KEY_COLUMNS + _IDENTITY_COLUMNS)
    for label, frame in (("candidate", candidate), ("baseline", baseline)):
        missing = sorted(required - set(frame.columns))
        if missing:
            raise ValueError(f"{label} predictions are missing comparison columns: {missing}")
        if frame.duplicated(list(_KEY_COLUMNS)).any():
            raise ValueError(f"{label} prediction keys must be unique")

    keys = list(_KEY_COLUMNS)
    if set(map(tuple, candidate.loc[:, keys].itertuples(index=False, name=None))) != set(
        map(tuple, baseline.loc[:, keys].itertuples(index=False, name=None))
    ):
        raise ValueError("candidate and baseline prediction keys differ")
    matched = candidate.merge(
        baseline,
        on=keys,
        how="inner",
        suffixes=("_candidate", "_baseline"),
        validate="one_to_one",
    )
    for column in _IDENTITY_COLUMNS:
        left = matched[f"{column}_candidate"]
        right = matched[f"{column}_baseline"]
        if not left.equals(right):
            raise ValueError(f"candidate and baseline {column} values differ")
        matched[column] = left
    matched["log_score_delta"] = (
        matched["log_score_candidate"].astype(float)
        - matched["log_score_baseline"].astype(float)
    )
    matched["absolute_error_improvement"] = (
        matched["absolute_error_baseline"].astype(float)
        - matched["absolute_error_candidate"].astype(float)
    )
    return matched


def _json_number(value: float) -> float | str:
    if value == -np.inf:
        return "-Infinity"
    if value == np.inf:
        return "Infinity"
    if not isfinite(value):
        raise ValueError("unexpected nonfinite comparison value")
    return float(value)


def _paired_mean(values: pd.Series) -> dict[str, object]:
    numeric = values.astype(float).to_numpy()
    undefined = int(np.isnan(numeric).sum())
    if undefined:
        return {
            "available": False,
            "value": None,
            "reason": "both_models_assigned_negative_infinite_log_score",
            "undefined_observation_count": undefined,
        }
    positive_infinity = int(np.isposinf(numeric).sum())
    negative_infinity = int(np.isneginf(numeric).sum())
    if positive_infinity and negative_infinity:
        return {
            "available": False,
            "value": None,
            "reason": "paired_log_score_contains_opposite_infinities",
            "undefined_observation_count": 0,
        }
    if positive_infinity or negative_infinity:
        return {
            "available": True,
            "value": "Infinity" if positive_infinity else "-Infinity",
            "reason": None,
            "undefined_observation_count": 0,
        }
    return {
        "available": True,
        "value": _json_number(float(np.mean(numeric))),
        "reason": None,
        "undefined_observation_count": 0,
    }


def _paired_difference(candidate: object, baseline: object) -> dict[str, object]:
    left = float(candidate)
    right = float(baseline)
    if left == -np.inf and right == -np.inf:
        return {
            "available": False,
            "value": None,
            "reason": "both_models_have_negative_infinite_macro_log_score",
        }
    return {
        "available": True,
        "value": _json_number(left - right),
        "reason": None,
    }


def _row_summary(frame: pd.DataFrame) -> dict[str, object]:
    result: dict[str, object] = {
        "observation_count": int(len(frame)),
        "zero_count_observation_count": int((frame["observed_ac"] == 0).sum()),
        "candidate_mean_log_score": _json_number(
            float(np.mean(frame["log_score_candidate"].astype(float).to_numpy()))
        ),
        "baseline_mean_log_score": _json_number(
            float(np.mean(frame["log_score_baseline"].astype(float).to_numpy()))
        ),
        "paired_mean_log_score_delta": _paired_mean(frame["log_score_delta"]),
        "candidate_mae": float(frame["absolute_error_candidate"].mean()),
        "baseline_mae": float(frame["absolute_error_baseline"].mean()),
        "mean_absolute_error_improvement": float(frame["absolute_error_improvement"].mean()),
    }
    for level in _COVERAGE_LEVELS:
        result[f"candidate_coverage_{level}"] = float(
            frame[f"coverage_{level}_candidate"].mean()
        )
        result[f"baseline_coverage_{level}"] = float(
            frame[f"coverage_{level}_baseline"].mean()
        )
    return result


def _exhaustive_outer_block_interval(matched: pd.DataFrame) -> dict[str, object]:
    deltas = matched["log_score_delta"].astype(float).to_numpy()
    if np.isnan(deltas).any():
        return {
            "available": False,
            "reason": "paired_log_score_contains_undefined_differences",
            "method": "exhaustive_outer_block_percentile_bootstrap",
        }
    if np.isinf(deltas).any():
        return {
            "available": False,
            "reason": "paired_log_score_contains_infinite_differences",
            "method": "exhaustive_outer_block_percentile_bootstrap",
            "positive_infinity_count": int(np.isposinf(deltas).sum()),
            "negative_infinity_count": int(np.isneginf(deltas).sum()),
        }
    cohort_cells = (
        matched.groupby(
            ["block_id", "region_id", "variant_group", "cohort_id"], sort=True
        )["log_score_delta"]
        .mean()
        .rename("mean_log_score_delta")
        .reset_index()
    )
    cells = (
        cohort_cells.groupby(["block_id", "region_id", "variant_group"], sort=True)[
            "mean_log_score_delta"
        ]
        .mean()
        .reset_index()
    )
    blocks = cells.groupby("block_id", sort=True)["mean_log_score_delta"].mean()
    block_values = blocks.to_numpy(dtype=float)
    block_count = len(block_values)
    if block_count != 5:
        raise ValueError("the frozen HbS comparison requires exactly five outer blocks")
    indices = np.indices((block_count,) * block_count, dtype=np.int16).reshape(
        block_count, -1
    )
    replicates = block_values[indices].mean(axis=0)
    lower, upper = np.quantile(replicates, (0.025, 0.975), method="linear")
    return {
        "available": True,
        "reason": None,
        "method": "exhaustive_outer_block_percentile_bootstrap",
        "block_count": block_count,
        "ordered_resample_count": int(replicates.size),
        "quantile_method": "linear",
        "interval_level": 0.95,
        "lower": _json_number(float(lower)),
        "upper": _json_number(float(upper)),
        "block_mean_log_score_deltas": {
            str(block_id): _json_number(float(value))
            for block_id, value in blocks.items()
        },
        "certified_dependency_aware": False,
    }


def _metric_differences(
    candidate: dict[str, object], baseline: dict[str, object]
) -> dict[str, object]:
    candidate_mae = float(candidate["mae"])
    baseline_mae = float(baseline["mae"])
    if baseline_mae <= 0.0:
        relative_mae_improvement = None
    else:
        relative_mae_improvement = (baseline_mae - candidate_mae) / baseline_mae
    differences: dict[str, object] = {
        "direction": "candidate_minus_baseline_except_mae_improvement",
        "mean_log_score": _paired_difference(
            candidate["mean_log_score"], baseline["mean_log_score"]
        ),
        "mae_improvement": baseline_mae - candidate_mae,
        "relative_mae_improvement": relative_mae_improvement,
        "rmse_improvement": float(baseline["rmse"]) - float(candidate["rmse"]),
    }
    for level in _COVERAGE_LEVELS:
        differences[f"coverage_{level}_percentage_points"] = 100.0 * (
            float(candidate[f"coverage_{level}"]) - float(baseline[f"coverage_{level}"])
        )
        differences[f"candidate_coverage_{level}_absolute_deviation_percentage_points"] = (
            100.0 * abs(float(candidate[f"coverage_{level}"]) - level / 100.0)
        )
        differences[f"baseline_coverage_{level}_absolute_deviation_percentage_points"] = (
            100.0 * abs(float(baseline[f"coverage_{level}"]) - level / 100.0)
        )
        differences[f"interval_width_{level}"] = float(
            candidate[f"interval_width_{level}"]
        ) - float(baseline[f"interval_width_{level}"])
    return differences


def compare_paired_benchmarks(
    candidate_predictions: pd.DataFrame,
    baseline_predictions: pd.DataFrame,
    fold_status: Sequence[BenchmarkFoldStatus],
    expected_split_ids: Sequence[str],
) -> tuple[dict[str, object], pd.DataFrame]:
    """Return a strict matched comparison and the joined rows used to compute it.

    Every fold must be complete. The exhaustive bootstrap treats the five outer geographic blocks
    as resampling units but deliberately does not certify their statistical independence.
    """
    statuses = _require_complete_statuses(fold_status, expected_split_ids)
    matched = _matched_predictions(candidate_predictions, baseline_predictions)
    candidate_summary = summarize_benchmark(
        candidate_predictions, statuses, expected_split_ids
    )
    baseline_summary = summarize_benchmark(
        baseline_predictions, statuses, expected_split_ids
    )
    if len(matched) != candidate_summary["scored_observation_count"]:
        raise ValueError("matched row count differs from the complete candidate benchmark")

    count_stratum = np.where(matched["observed_ac"] == 0, "zero", "positive")
    matched["count_stratum"] = count_stratum
    strata = {
        str(label): _row_summary(group)
        for label, group in matched.groupby("count_stratum", sort=True)
    }
    if set(strata) != {"positive", "zero"}:
        raise ValueError("frozen comparison requires both zero-count and positive-count strata")
    regions = {
        str(label): _row_summary(group)
        for label, group in matched.groupby("region_id", sort=True)
    }
    candidate_metrics = candidate_summary["metrics"]
    baseline_metrics = baseline_summary["metrics"]
    report = {
        "comparison_complete": True,
        "scientific_promotion_decision": "not_made",
        "matched_observation_count": int(len(matched)),
        "candidate_benchmark": candidate_summary,
        "baseline_benchmark": baseline_summary,
        "balanced_macro_metric_differences": _metric_differences(
            candidate_metrics, baseline_metrics
        ),
        "paired_outer_block_log_score_interval": _exhaustive_outer_block_interval(matched),
        "matched_row_count_strata": strata,
        "matched_row_regions": regions,
        "reference_thresholds": {
            "relative_mae_improvement": 0.05,
            "coverage_absolute_tolerance_percentage_points": 3.0,
            "automatic_decision": False,
        },
    }
    return report, matched
