"""Pure benchmark inventory and reporting boundaries (design §§ 6, 7.1, 8; #189).

This module reports what P1 evidence and offline predictive evaluation exist. It does not fit a
model, certify that declared cohorts are independent studies, establish a present-day resident
target, verify registry semantics or permissions, or make a scientific promotion decision.

``validate_allele_observations`` is the public boundary shared with the benchmark runner. It
rejects Boolean and fractional ``ac``, ``an``, ``date_lower`` and ``date_upper`` values before
the coercing frozen P1 schema sees them, then validates a deep copy. The submitted dataframe is
never mutated. ``inventory_observations`` returns only row and distinct-label counts; allele
denominators are deliberately not summed across loci or described as people.

``BenchmarkFoldStatus`` is the immutable handoff from the runner. Every planned split has exactly
one record. Completed records have no failure reason; ``failed`` and ``infeasible`` records carry
a nonempty reason. ``expected_test_ids`` records the complete test identity set that a completed
prediction table must match.

``summarize_benchmark`` accepts one prediction row per ``(split_id, source_record_id)``. It first
averages diagnostics within each declared cohort/region/variant-group, then gives cohorts equal
weight within each region/group cell, and finally gives represented cells equal weight. The
declared cohort label is an operational weighting unit, not a certified independent study. A
genuine zero predictive probability is represented as the JSON string ``"-Infinity"`` at every
affected aggregation level. Its raw observation count is reported in every cohort and cell record
and at the global level; this audit count is summed, never averaged.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from math import isfinite, sqrt
from numbers import Real
from typing import Literal

import numpy as np
import pandas as pd

from genomeos.observations.schema import OBSERVATIONS_SCHEMA

FoldState = Literal["completed", "failed", "infeasible"]

_INTEGER_OBSERVATION_COLUMNS = ("ac", "an", "date_lower", "date_upper")
_PREDICTION_ID_COLUMNS = (
    "split_id",
    "source_record_id",
    "region_id",
    "variant_group",
    "cohort_id",
)
_DIAGNOSTIC_COLUMNS = (
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
_BOUNDED_DIAGNOSTICS = (
    "absolute_error",
    "squared_error",
    "interval_width_50",
    "interval_width_80",
    "interval_width_95",
    "randomized_pit",
)
_COVERAGE_COLUMNS = ("coverage_50", "coverage_80", "coverage_95")
_OUTPUT_INGREDIENTS = {
    "log_score": "mean_log_score",
    "absolute_error": "mae",
    "squared_error": "mean_squared_error",
    "coverage_50": "coverage_50",
    "interval_width_50": "interval_width_50",
    "coverage_80": "coverage_80",
    "interval_width_80": "interval_width_80",
    "coverage_95": "coverage_95",
    "interval_width_95": "interval_width_95",
    "randomized_pit": "mean_randomized_pit",
}
_UNAVAILABLE_METRICS = {
    "mean_log_score": None,
    "mae": None,
    "rmse": None,
    "coverage_50": None,
    "interval_width_50": None,
    "coverage_80": None,
    "interval_width_80": None,
    "coverage_95": None,
    "interval_width_95": None,
    "mean_randomized_pit": None,
}


def _require_label(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} values must be nonempty strings")
    return value


def _require_unique_labels(values: Sequence[str], field: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise TypeError(f"{field} must be a sequence of labels")
    labels = tuple(_require_label(value, field) for value in values)
    if len(set(labels)) != len(labels):
        raise ValueError(f"{field} values must be unique")
    return labels


@dataclass(frozen=True)
class BenchmarkFoldStatus:
    """Status and expected held-out observation identities for one planned split."""

    split_id: str
    status: FoldState
    expected_test_ids: tuple[str, ...]
    failure_reason: str | None

    def __post_init__(self) -> None:
        _require_label(self.split_id, "split_id")
        if self.status not in ("completed", "failed", "infeasible"):
            raise ValueError("status must be completed, failed, or infeasible")
        if not isinstance(self.expected_test_ids, tuple):
            raise TypeError("expected_test_ids must be a tuple")
        expected = _require_unique_labels(self.expected_test_ids, "expected_test_ids")
        if not expected:
            raise ValueError("expected_test_ids must not be empty")
        if self.status == "completed":
            if self.failure_reason is not None:
                raise ValueError("completed status must not have a failure_reason")
        elif not isinstance(self.failure_reason, str) or not self.failure_reason.strip():
            raise ValueError(f"{self.status} status requires a failure_reason")


def _reject_lossy_integer_coercion(frame: pd.DataFrame) -> None:
    for column in _INTEGER_OBSERVATION_COLUMNS:
        if column not in frame.columns:
            continue
        values = frame[column]
        for value in values.array:
            if isinstance(value, (bool, np.bool_)):
                raise ValueError(f"{column} must contain integer values, not Boolean values")
            if value is None or value is pd.NA:
                continue
            try:
                numeric = Decimal(str(value))
            except (InvalidOperation, ValueError):
                continue
            if numeric.is_finite() and numeric != numeric.to_integral_value():
                raise ValueError(f"{column} must not contain fractional values")


def validate_allele_observations(observations: pd.DataFrame) -> pd.DataFrame:
    """Return a schema-validated copy after refusing lossy integer coercions.

    This is a public validation boundary for inventory and offline-runner callers. It deliberately
    leaves the frozen shared P1 schema unchanged while issue #192 tracks the schema-wide repair.
    """
    if not isinstance(observations, pd.DataFrame):
        raise TypeError("observations must be a pandas DataFrame")
    if observations.columns.duplicated().any():
        raise ValueError("observations must not contain duplicate column labels")
    _reject_lossy_integer_coercion(observations)
    return OBSERVATIONS_SCHEMA.validate(observations.copy(deep=True))


def _count_labels(frame: pd.DataFrame, column: str) -> dict[str, int]:
    counts = frame[column].value_counts(sort=False)
    return {str(label): int(counts[label]) for label in sorted(counts.index)}


def inventory_observations(observations: pd.DataFrame) -> dict[str, object]:
    """Return a JSON-compatible inventory without inferring people or certification."""
    validated = validate_allele_observations(observations)
    modern_unspecified = (validated["date_lower"] == 0) & (validated["date_upper"] == 0)
    return {
        "observation_count": int(len(validated)),
        "counts_by_source": _count_labels(validated, "source"),
        "counts_by_assay": _count_labels(validated, "assay"),
        "counts_by_sampling_design": _count_labels(validated, "sampling_design"),
        "counts_by_variant": _count_labels(validated, "variant_id"),
        "distinct_declared_cohort_count": int(validated["cohort_id"].nunique()),
        "distinct_population_count": int(validated["population_id"].nunique()),
        "date_unspecified_modern_count": int(modern_unspecified.sum()),
        "zero_count_count": int((validated["ac"] == 0).sum()),
        "unresolved_limitations": {
            "participant_overlap": "not_certified",
            "resident_target": "not_certified",
            "permissions": "not_certified",
            "registry_semantics": "not_certified_by_p1",
        },
    }


def _require_predictions(predictions: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(predictions, pd.DataFrame):
        raise TypeError("predictions must be a pandas DataFrame")
    if predictions.columns.duplicated().any():
        raise ValueError("predictions must not contain duplicate column labels")
    required = _PREDICTION_ID_COLUMNS + _DIAGNOSTIC_COLUMNS
    missing = sorted(set(required) - set(predictions.columns))
    if missing:
        raise ValueError(f"predictions is missing required columns: {missing}")
    result = predictions.loc[:, required].copy(deep=True)
    for column in _PREDICTION_ID_COLUMNS:
        for value in result[column].array:
            _require_label(value, column)
    duplicated = result.duplicated(subset=["split_id", "source_record_id"], keep=False)
    if duplicated.any():
        raise ValueError("prediction (split_id, source_record_id) keys must be unique")
    _validate_diagnostics(result)
    return result


def _require_real(value: object, field: str) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise ValueError(f"{field} values must be numeric")
    return float(value)


def _validate_diagnostics(predictions: pd.DataFrame) -> None:
    for column in _BOUNDED_DIAGNOSTICS:
        for value in predictions[column].array:
            numeric = _require_real(value, column)
            if not isfinite(numeric) or not 0.0 <= numeric <= 1.0:
                raise ValueError(f"{column} values must be finite and between 0 and 1")
    for value in predictions["log_score"].array:
        numeric = _require_real(value, "log_score")
        if np.isnan(numeric) or numeric == np.inf or numeric > 0.0:
            raise ValueError("log_score values must be nonpositive and finite or -Infinity")
    for column in _COVERAGE_COLUMNS:
        if not all(isinstance(value, (bool, np.bool_)) for value in predictions[column].array):
            raise ValueError(f"{column} values must be Boolean")


def _prepare_statuses(
    fold_status: Sequence[BenchmarkFoldStatus], expected_split_ids: Sequence[str]
) -> tuple[tuple[BenchmarkFoldStatus, ...], tuple[str, ...]]:
    expected = _require_unique_labels(expected_split_ids, "expected_split_ids")
    if not expected:
        raise ValueError("expected_split_ids must not be empty")
    if isinstance(fold_status, (str, bytes)):
        raise TypeError("fold_status must be a sequence of BenchmarkFoldStatus records")
    statuses = tuple(fold_status)
    if not all(isinstance(status, BenchmarkFoldStatus) for status in statuses):
        raise TypeError("fold_status must contain BenchmarkFoldStatus records")
    status_ids = tuple(status.split_id for status in statuses)
    duplicates = sorted({split_id for split_id in status_ids if status_ids.count(split_id) > 1})
    if duplicates:
        raise ValueError(f"fold_status contains duplicate split statuses: {duplicates}")
    unknown = sorted(set(status_ids) - set(expected))
    if unknown:
        raise ValueError(f"fold_status contains unknown split statuses: {unknown}")
    missing = sorted(set(expected) - set(status_ids))
    if missing:
        raise ValueError(f"fold_status is missing planned split statuses: {missing}")
    by_id = {status.split_id: status for status in statuses}
    return tuple(by_id[split_id] for split_id in expected), expected


def _validate_prediction_membership(
    predictions: pd.DataFrame, statuses: tuple[BenchmarkFoldStatus, ...]
) -> None:
    by_split = {
        split_id: set(group["source_record_id"])
        for split_id, group in predictions.groupby("split_id", sort=False)
    }
    known = {status.split_id for status in statuses}
    unknown = sorted(set(by_split) - known)
    if unknown:
        raise ValueError(f"predictions contain unknown split IDs: {unknown}")
    for status in statuses:
        actual = by_split.get(status.split_id, set())
        if status.status != "completed":
            if actual:
                raise ValueError("predictions must not exist for failed or infeasible splits")
            continue
        if actual != set(status.expected_test_ids):
            raise ValueError(
                f"predictions for completed split {status.split_id!r} do not match its expected test IDs"
            )


def _mean(values: pd.Series) -> float:
    numeric = values.astype(float).to_numpy()
    if np.isneginf(numeric).any():
        return -np.inf
    return float(np.mean(numeric))


def _aggregate_rows(frame: pd.DataFrame, group_columns: tuple[str, ...], count_name: str) -> pd.DataFrame:
    records: list[dict[str, object]] = []
    for keys, group in frame.groupby(list(group_columns), sort=True, dropna=False):
        key_tuple = keys if isinstance(keys, tuple) else (keys,)
        record = dict(zip(group_columns, key_tuple, strict=True))
        record[count_name] = int(len(group))
        if "zero_probability_count" in group:
            record["zero_probability_count"] = int(group["zero_probability_count"].sum())
        else:
            log_scores = group["log_score"].astype(float).to_numpy()
            record["zero_probability_count"] = int(np.isneginf(log_scores).sum())
        for source, target in _OUTPUT_INGREDIENTS.items():
            record[target] = _mean(group[source])
        records.append(record)
    return pd.DataFrame.from_records(records)


def _json_number(value: float) -> float | str:
    return "-Infinity" if value == -np.inf else float(value)


def _serialized_records(frame: pd.DataFrame) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for source in frame.to_dict(orient="records"):
        record: dict[str, object] = {}
        for key, value in source.items():
            if isinstance(value, (float, np.floating)):
                record[key] = _json_number(float(value))
            elif isinstance(value, np.integer):
                record[key] = int(value)
            else:
                record[key] = value
        records.append(record)
    return records


def _headline_metrics(cells: pd.DataFrame) -> dict[str, float | str | None]:
    if cells.empty:
        return dict(_UNAVAILABLE_METRICS)
    metrics = {
        target: _mean(cells[target])
        for target in _OUTPUT_INGREDIENTS.values()
        if target != "mean_squared_error"
    }
    metrics["rmse"] = sqrt(_mean(cells["mean_squared_error"]))
    order = tuple(_UNAVAILABLE_METRICS)
    return {name: _json_number(metrics[name]) for name in order}


def summarize_benchmark(
    predictions: pd.DataFrame,
    fold_status: Sequence[BenchmarkFoldStatus],
    expected_split_ids: Sequence[str],
) -> dict[str, object]:
    """Validate a complete planned split ledger and return auditable macro diagnostics."""
    validated_predictions = _require_predictions(predictions)
    statuses, _ = _prepare_statuses(fold_status, expected_split_ids)
    _validate_prediction_membership(validated_predictions, statuses)

    completed = sum(status.status == "completed" for status in statuses)
    failed = sum(status.status == "failed" for status in statuses)
    infeasible = sum(status.status == "infeasible" for status in statuses)
    status_records = [
        {
            "split_id": status.split_id,
            "status": status.status,
            "expected_test_ids": list(status.expected_test_ids),
            "failure_reason": status.failure_reason,
        }
        for status in statuses
    ]
    failure_reasons = [
        {
            "split_id": status.split_id,
            "status": status.status,
            "reason": status.failure_reason,
        }
        for status in statuses
        if status.status != "completed"
    ]

    if validated_predictions.empty:
        cohort_cells = pd.DataFrame()
        cells = pd.DataFrame()
    else:
        cohort_cells = _aggregate_rows(
            validated_predictions,
            ("region_id", "variant_group", "cohort_id"),
            "observation_count",
        )
        cells = _aggregate_rows(
            cohort_cells.rename(columns={target: source for source, target in _OUTPUT_INGREDIENTS.items()}),
            ("region_id", "variant_group"),
            "declared_cohort_count",
        )
        observation_counts = validated_predictions.groupby(["region_id", "variant_group"], sort=True).size()
        cells["observation_count"] = [
            int(observation_counts.loc[(row.region_id, row.variant_group)])
            for row in cells.itertuples(index=False)
        ]

    return {
        "comparison_complete": completed == len(statuses),
        "split_counts": {
            "planned": len(statuses),
            "completed": completed,
            "failed": failed,
            "infeasible": infeasible,
        },
        "fold_status": status_records,
        "failure_reasons": failure_reasons,
        "scored_observation_count": int(len(validated_predictions)),
        "represented_cell_count": int(len(cells)),
        "represented_declared_cohort_cell_count": int(len(cohort_cells)),
        "zero_probability_count": int(
            np.isneginf(validated_predictions["log_score"].astype(float).to_numpy()).sum()
        ),
        "declared_cohort_cell_metrics": _serialized_records(cohort_cells),
        "cell_metrics": _serialized_records(cells),
        "metrics": _headline_metrics(cells),
    }
