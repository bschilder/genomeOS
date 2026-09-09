"""Fail-closed observation inventory and benchmark reporting (design §§ 6, 8)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import numpy as np
import pandas as pd
import pytest
from pandera.errors import SchemaError

from genomeos.validation.benchmark import (
    BenchmarkFoldStatus,
    inventory_observations,
    summarize_benchmark,
    validate_allele_observations,
)

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


def _observations() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "variant_id": ["chr1-10-A-G", "chr1-10-A-G", "chr2-20-C-T"],
            "rsid": ["rs1", "rs1", "rs2"],
            "population_id": ["pop-b", "pop-a", "pop-a"],
            "lat": [1.0, 2.0, 2.0],
            "lon": [3.0, 4.0, 4.0],
            "radius_km": [5.0, 6.0, 6.0],
            "ac": [0, 2, 1],
            "an": [20, 20, 10],
            "source_record_id": ["obs-1", "obs-2", "obs-3"],
            "source": ["source-b", "source-a", "source-a"],
            "assay": ["genome", "array", "array"],
            "date_lower": [0, 0, 100],
            "date_upper": [0, 0, 200],
            "sampling_design": [
                "healthy_reference",
                "population_random",
                "population_random",
            ],
            "disease_ascertainment_excluded": [True, False, False],
            "cohort_id": ["cohort-1", "cohort-1", "cohort-2"],
            "ingest_version": ["p1-v1", "p1-v1", "p1-v1"],
        }
    )


def _prediction(
    source_record_id: str,
    *,
    split_id: str = "split-a",
    region_id: str = "region-a",
    variant_group: str = "group-a",
    cohort_id: str = "cohort-a",
    log_score: float = -0.5,
    absolute_error: float = 0.2,
    squared_error: float = 0.09,
    coverage_50: bool = True,
    interval_width_50: float = 0.3,
    coverage_80: bool = True,
    interval_width_80: float = 0.5,
    coverage_95: bool = True,
    interval_width_95: float = 0.7,
    randomized_pit: float = 0.4,
) -> dict[str, object]:
    return locals()


def _completed(
    split_id: str = "split-a", expected_test_ids: tuple[str, ...] = ("obs-1",)
) -> BenchmarkFoldStatus:
    return BenchmarkFoldStatus(split_id, "completed", expected_test_ids, None)


def test_inventory_reports_only_observation_counts_and_explicit_limitations():
    """Summing AN as people or omitting unresolved qualification must break this contract."""
    observations = _observations()

    result = inventory_observations(observations)

    assert result == {
        "observation_count": 3,
        "counts_by_source": {"source-a": 2, "source-b": 1},
        "counts_by_assay": {"array": 2, "genome": 1},
        "counts_by_sampling_design": {
            "healthy_reference": 1,
            "population_random": 2,
        },
        "counts_by_variant": {"chr1-10-A-G": 2, "chr2-20-C-T": 1},
        "distinct_declared_cohort_count": 2,
        "distinct_population_count": 2,
        "date_unspecified_modern_count": 2,
        "zero_count_count": 1,
        "unresolved_limitations": {
            "participant_overlap": "not_certified",
            "resident_target": "not_certified",
            "permissions": "not_certified",
            "registry_semantics": "not_certified_by_p1",
        },
    }
    assert "total_an" not in result
    assert "participant_count" not in result


@pytest.mark.parametrize("column", ["ac", "an", "date_lower", "date_upper"])
@pytest.mark.parametrize("bad", [0.5, True, np.bool_(False)])
def test_inventory_rejects_fractional_and_boolean_integer_fields_without_mutation(column, bad):
    """Pandera coercion must not truncate or reinterpret submitted count/date values."""
    observations = _observations()
    observations[column] = observations[column].astype(object)
    observations.loc[0, column] = bad
    before = observations.copy(deep=True)

    with pytest.raises(ValueError, match=column):
        inventory_observations(observations)

    pd.testing.assert_frame_equal(observations, before)


def test_inventory_uses_the_complete_existing_observations_schema():
    """Inventory cannot certify a partial or schema-invalid P1 table."""
    observations = _observations().drop(columns="sampling_design")

    with pytest.raises(SchemaError):
        inventory_observations(observations)


def test_public_validator_detects_fractional_raw_token_that_binary_float_rounds_away():
    """Parsing as float first would turn this fractional AC token into integer 12."""
    observations = _observations()
    observations["ac"] = observations["ac"].astype(object)
    observations.loc[0, "ac"] = "12.000000000000000001"

    assert float(observations.loc[0, "ac"]) == 12.0
    with pytest.raises(ValueError, match="ac.*fractional"):
        validate_allele_observations(observations)


def test_public_observation_validator_returns_a_validated_copy():
    """A CLI caller needs the safeguard without mutating its submitted raw table."""
    observations = _observations()
    observations["ac"] = observations["ac"].astype(object)

    validated = validate_allele_observations(observations)

    assert validated is not observations
    assert validated["ac"].dtype.kind in "iu"
    assert observations["ac"].dtype == object


def test_fold_status_is_frozen_and_refuses_incoherent_reason_semantics():
    """Completed failures or unexplained failed folds would make the audit ambiguous."""
    status = _completed()
    with pytest.raises(FrozenInstanceError):
        status.status = "failed"  # type: ignore[misc]
    with pytest.raises(ValueError, match="must not have a failure_reason"):
        BenchmarkFoldStatus("split-a", "completed", ("obs-1",), "warning")
    with pytest.raises(ValueError, match="requires a failure_reason"):
        BenchmarkFoldStatus("split-a", "failed", ("obs-1",), None)


def test_reporter_uses_cohort_then_cell_macro_weighting_and_rmse_after_mse():
    """Observation weighting or averaging row RMSEs changes the hand-derived headline."""
    predictions = pd.DataFrame(
        [
            _prediction("a1", cohort_id="large", absolute_error=0.0, squared_error=0.0),
            _prediction("a2", cohort_id="large", absolute_error=0.0, squared_error=0.0),
            _prediction("a3", cohort_id="large", absolute_error=0.0, squared_error=0.0),
            _prediction("a4", cohort_id="small", absolute_error=1.0, squared_error=1.0),
            _prediction(
                "b1",
                region_id="region-b",
                cohort_id="other",
                absolute_error=1.0,
                squared_error=1.0,
            ),
        ]
    )
    status = _completed(expected_test_ids=("a1", "a2", "a3", "a4", "b1"))

    result = summarize_benchmark(predictions, (status,), ("split-a",))

    assert result["comparison_complete"] is True
    assert result["scored_observation_count"] == 5
    assert result["represented_cell_count"] == 2
    assert result["represented_declared_cohort_cell_count"] == 3
    assert result["metrics"]["mae"] == pytest.approx(0.75)
    assert result["metrics"]["rmse"] == pytest.approx(np.sqrt(0.75))
    assert [row["mae"] for row in result["cell_metrics"]] == pytest.approx([0.5, 1.0])
    assert result["metrics"]["mae"] != pytest.approx(2 / 5)


def test_failed_and_infeasible_statuses_are_retained_and_mark_comparison_incomplete():
    """Dropping unsuccessful planned folds would turn an incomplete benchmark into success."""
    statuses = (
        _completed(),
        BenchmarkFoldStatus("split-b", "failed", ("obs-2",), "sampler diverged"),
        BenchmarkFoldStatus("split-c", "infeasible", ("obs-3",), "no training rows"),
    )

    result = summarize_benchmark(
        pd.DataFrame([_prediction("obs-1")]),
        statuses,
        ("split-a", "split-b", "split-c"),
    )

    assert result["comparison_complete"] is False
    assert result["split_counts"] == {
        "planned": 3,
        "completed": 1,
        "failed": 1,
        "infeasible": 1,
    }
    assert result["failure_reasons"] == [
        {"split_id": "split-b", "status": "failed", "reason": "sampler diverged"},
        {"split_id": "split-c", "status": "infeasible", "reason": "no training rows"},
    ]


def test_no_completed_fold_returns_explicit_unavailable_metrics():
    """An empty reduction must remain unavailable rather than becoming a successful zero."""
    columns = ("split_id", "source_record_id", "region_id", "variant_group", "cohort_id") + DIAGNOSTIC_COLUMNS
    status = BenchmarkFoldStatus("split-a", "infeasible", ("obs-1",), "no training rows")

    result = summarize_benchmark(pd.DataFrame(columns=columns), (status,), ("split-a",))

    assert result["comparison_complete"] is False
    assert result["scored_observation_count"] == 0
    assert result["represented_cell_count"] == 0
    assert result["metrics"] == {
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


def test_negative_infinite_log_score_remains_visible_through_every_level():
    """Ordinary reductions can silently skip or NaN a genuine zero-probability outcome."""
    predictions = pd.DataFrame(
        [
            _prediction("obs-1", log_score=-np.inf),
            _prediction("obs-2", log_score=-1.0),
        ]
    )
    result = summarize_benchmark(
        predictions,
        (_completed(expected_test_ids=("obs-1", "obs-2")),),
        ("split-a",),
    )

    assert result["zero_probability_count"] == 1
    assert result["declared_cohort_cell_metrics"][0]["mean_log_score"] == "-Infinity"
    assert result["cell_metrics"][0]["mean_log_score"] == "-Infinity"
    assert result["metrics"]["mean_log_score"] == "-Infinity"


def test_zero_probability_observation_counts_are_summed_at_each_audit_level():
    """Averaging impossible-outcome counts would hide how many raw scores were catastrophic."""
    predictions = pd.DataFrame(
        [
            _prediction("a1", cohort_id="cohort-a", log_score=-np.inf),
            _prediction("a2", cohort_id="cohort-a", log_score=-np.inf),
            _prediction("a3", cohort_id="cohort-a", log_score=-1.0),
            _prediction("a4", cohort_id="cohort-b", log_score=-np.inf),
            _prediction("a5", cohort_id="cohort-b", log_score=-1.0),
            _prediction(
                "b1", region_id="region-b", cohort_id="cohort-c", log_score=-1.0
            ),
            _prediction(
                "b2", region_id="region-b", cohort_id="cohort-d", log_score=-np.inf
            ),
        ]
    )
    expected_ids = tuple(predictions["source_record_id"])

    result = summarize_benchmark(
        predictions,
        (_completed(expected_test_ids=expected_ids),),
        ("split-a",),
    )

    assert [
        row["zero_probability_count"]
        for row in result["declared_cohort_cell_metrics"]
    ] == [2, 1, 0, 1]
    assert [row["zero_probability_count"] for row in result["cell_metrics"]] == [
        3,
        1,
    ]
    assert result["zero_probability_count"] == 4


@pytest.mark.parametrize(
    ("statuses", "expected", "message"),
    [
        ((), ("split-a",), "missing"),
        ((_completed(), _completed()), ("split-a",), "duplicate"),
        ((_completed("split-b"),), ("split-a",), "unknown"),
        ((_completed(),), ("split-a", "split-a"), "unique"),
    ],
)
def test_planned_split_statuses_must_be_exactly_once(statuses, expected, message):
    """Missing, duplicate, or unknown status rows invalidate completeness accounting."""
    with pytest.raises(ValueError, match=message):
        summarize_benchmark(pd.DataFrame([_prediction("obs-1")]), statuses, expected)


@pytest.mark.parametrize(
    ("predictions", "statuses", "message"),
    [
        (
            pd.DataFrame([_prediction("obs-1"), _prediction("obs-1")]),
            (_completed(),),
            "unique",
        ),
        (
            pd.DataFrame([_prediction("obs-2")]),
            (_completed(),),
            "expected test IDs",
        ),
        (
            pd.DataFrame([_prediction("obs-1", split_id="split-b")]),
            (BenchmarkFoldStatus("split-b", "failed", ("obs-1",), "boom"),),
            "failed or infeasible",
        ),
    ],
)
def test_prediction_rows_must_match_completed_split_manifests(predictions, statuses, message):
    """Duplicate, missing, extra, or unsuccessful-fold scores cannot enter the report."""
    with pytest.raises(ValueError, match=message):
        summarize_benchmark(predictions, statuses, tuple(status.split_id for status in statuses))


@pytest.mark.parametrize("column", ["region_id", "variant_group", "cohort_id"])
@pytest.mark.parametrize("bad", [None, "", " ", 3])
def test_prediction_weighting_labels_must_be_explicit_nonempty_strings(column, bad):
    """Missing grouping labels cannot be defaulted without changing the benchmark target."""
    predictions = pd.DataFrame([_prediction("obs-1")])
    predictions[column] = predictions[column].astype(object)
    predictions.loc[0, column] = bad

    with pytest.raises(ValueError, match=column):
        summarize_benchmark(predictions, (_completed(),), ("split-a",))


@pytest.mark.parametrize(
    ("column", "bad"),
    [
        ("log_score", 0.1),
        ("log_score", np.inf),
        ("log_score", np.nan),
        ("absolute_error", -0.1),
        ("absolute_error", 1.1),
        ("absolute_error", "0.2"),
        ("squared_error", np.inf),
        ("interval_width_50", -0.1),
        ("interval_width_80", 1.1),
        ("interval_width_95", np.nan),
        ("randomized_pit", 1.1),
        ("coverage_50", 1),
        ("coverage_80", None),
        ("coverage_95", "yes"),
    ],
)
def test_diagnostics_reject_nonfinite_and_out_of_range_values(column, bad):
    """Malformed diagnostics must fail rather than be clipped, skipped, or coerced."""
    predictions = pd.DataFrame([_prediction("obs-1")])
    predictions[column] = predictions[column].astype(object)
    predictions.loc[0, column] = bad

    with pytest.raises(ValueError, match=column):
        summarize_benchmark(predictions, (_completed(),), ("split-a",))


def test_prediction_table_requires_all_identity_and_diagnostic_columns():
    """A partial Task 1 result cannot be promoted into a benchmark summary."""
    predictions = pd.DataFrame([_prediction("obs-1")]).drop(columns="randomized_pit")

    with pytest.raises(ValueError, match="missing required columns"):
        summarize_benchmark(predictions, (_completed(),), ("split-a",))
