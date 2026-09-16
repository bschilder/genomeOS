"""Matched benchmark comparison tests (design §§4, 6–8; issue #189)."""

from __future__ import annotations

import itertools

import numpy as np
import pandas as pd
import pytest
from matplotlib.markers import MarkerStyle

from genomeos.validation.benchmark import BenchmarkFoldStatus
from genomeos.validation.paired_benchmark import compare_paired_benchmarks
from scripts.plot_hbs_current_gp_benchmark import build_figure, plt


def _predictions(log_scores: list[float], errors: list[float]) -> pd.DataFrame:
    records = []
    for index, (log_score, error) in enumerate(zip(log_scores, errors, strict=True)):
        records.append(
            {
                "split_id": f"split-{index}",
                "block_id": f"block-{index}",
                "source_record_id": f"row-{index}",
                "variant_id": "chr11-5227002-T-A",
                "region_id": f"region-{index}",
                "variant_group": "hbs",
                "cohort_id": f"cohort-{index}",
                "observed_ac": 0 if index == 0 else index,
                "observed_an": 100,
                "log_score": log_score,
                "absolute_error": error,
                "squared_error": error**2,
                "coverage_50": index < 3,
                "interval_width_50": 0.1,
                "coverage_80": index < 4,
                "interval_width_80": 0.2,
                "coverage_95": True,
                "interval_width_95": 0.3,
                "randomized_pit": 0.5,
            }
        )
    return pd.DataFrame.from_records(records)


def _statuses() -> tuple[tuple[BenchmarkFoldStatus, ...], tuple[str, ...]]:
    split_ids = tuple(f"split-{index}" for index in range(5))
    statuses = tuple(
        BenchmarkFoldStatus(split_id, "completed", (f"row-{index}",), None)
        for index, split_id in enumerate(split_ids)
    )
    return statuses, split_ids


def test_comparison_uses_exact_matched_rows_and_exhaustive_outer_blocks():
    baseline = _predictions([-5.0] * 5, [0.2] * 5)
    candidate = _predictions([-4.0, -3.0, -2.0, -1.0, 0.0], [0.1] * 5)
    statuses, split_ids = _statuses()

    report, matched = compare_paired_benchmarks(candidate, baseline, statuses, split_ids)

    assert report["matched_observation_count"] == len(matched) == 5
    assert report["scientific_promotion_decision"] == "not_made"
    differences = report["balanced_macro_metric_differences"]
    assert differences["mean_log_score"] == {
        "available": True,
        "value": pytest.approx(3.0),
        "reason": None,
    }
    assert differences["relative_mae_improvement"] == pytest.approx(0.5)
    interval = report["paired_outer_block_log_score_interval"]
    values = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    brute_force = np.array(
        [np.mean(sample) for sample in itertools.product(values, repeat=5)]
    )
    expected = np.quantile(brute_force, (0.025, 0.975), method="linear")
    assert interval["ordered_resample_count"] == 3125
    assert interval["lower"] == pytest.approx(expected[0])
    assert interval["upper"] == pytest.approx(expected[1])
    assert interval["certified_dependency_aware"] is False
    assert set(report["matched_row_count_strata"]) == {"positive", "zero"}


def test_comparison_refuses_any_key_or_held_out_count_drift():
    baseline = _predictions([-5.0] * 5, [0.2] * 5)
    candidate = _predictions([-4.0] * 5, [0.1] * 5)
    statuses, split_ids = _statuses()

    candidate.loc[0, "observed_an"] = 101
    with pytest.raises(ValueError, match="observed_an values differ"):
        compare_paired_benchmarks(candidate, baseline, statuses, split_ids)

    candidate = _predictions([-4.0] * 5, [0.1] * 5)
    candidate.loc[0, "source_record_id"] = "different-row"
    with pytest.raises(ValueError, match="prediction keys differ"):
        compare_paired_benchmarks(candidate, baseline, statuses, split_ids)


def test_comparison_refuses_partial_fold_ledgers():
    baseline = _predictions([-5.0] * 5, [0.2] * 5)
    candidate = _predictions([-4.0] * 5, [0.1] * 5)
    statuses, split_ids = _statuses()
    partial = list(statuses)
    partial[-1] = BenchmarkFoldStatus("split-4", "failed", ("row-4",), "fit failed")

    with pytest.raises(ValueError, match="every planned fold"):
        compare_paired_benchmarks(candidate, baseline, partial, split_ids)


def test_both_negative_infinite_scores_remain_visible_and_disable_interval():
    baseline = _predictions([-np.inf, -5.0, -5.0, -5.0, -5.0], [0.2] * 5)
    candidate = _predictions([-np.inf, -4.0, -4.0, -4.0, -4.0], [0.1] * 5)
    statuses, split_ids = _statuses()

    report, _ = compare_paired_benchmarks(candidate, baseline, statuses, split_ids)

    zero = report["matched_row_count_strata"]["zero"]
    assert zero["candidate_mean_log_score"] == "-Infinity"
    assert zero["baseline_mean_log_score"] == "-Infinity"
    assert zero["paired_mean_log_score_delta"] == {
        "available": False,
        "value": None,
        "reason": "both_models_assigned_negative_infinite_log_score",
        "undefined_observation_count": 1,
    }
    interval = report["paired_outer_block_log_score_interval"]
    assert interval["available"] is False
    assert interval["reason"] == "paired_log_score_contains_undefined_differences"
    assert report["balanced_macro_metric_differences"]["mean_log_score"] == {
        "available": False,
        "value": None,
        "reason": "both_models_have_negative_infinite_macro_log_score",
    }


def test_one_sided_negative_infinity_is_catastrophic_and_disables_interval():
    baseline = _predictions([-5.0] * 5, [0.2] * 5)
    candidate = _predictions([-np.inf, -4.0, -4.0, -4.0, -4.0], [0.1] * 5)
    statuses, split_ids = _statuses()

    report, _ = compare_paired_benchmarks(candidate, baseline, statuses, split_ids)

    paired = report["matched_row_count_strata"]["zero"]["paired_mean_log_score_delta"]
    assert paired == {
        "available": True,
        "value": "-Infinity",
        "reason": None,
        "undefined_observation_count": 0,
    }
    interval = report["paired_outer_block_log_score_interval"]
    assert interval["available"] is False
    assert interval["reason"] == "paired_log_score_contains_infinite_differences"
    assert interval["positive_infinity_count"] == 0
    assert interval["negative_infinity_count"] == 1


def test_figure_maps_metrics_to_actual_coordinates_with_circle_markers_only():
    baseline = _predictions([-5.0] * 5, [0.2] * 5)
    candidate = _predictions([-4.0, -3.0, -2.0, -1.0, 0.0], [0.1] * 5)
    statuses, split_ids = _statuses()
    report, matched = compare_paired_benchmarks(candidate, baseline, statuses, split_ids)
    matched["lon"] = [-75.0, -20.0, 10.0, 35.0, 80.0]
    matched["lat"] = [40.0, 5.0, 10.0, -5.0, 20.0]

    figure = build_figure({"comparison": report}, matched)
    try:
        expected_circle = MarkerStyle("o").get_path().transformed(
            MarkerStyle("o").get_transform()
        ).vertices
        for axis, value_column in zip(
            figure.axes[:2],
            ("log_score_delta", "absolute_error_improvement"),
            strict=True,
        ):
            points = [collection for collection in axis.collections if hasattr(collection, "get_offsets")]
            assert len(points) == 1
            scatter = points[0]
            observed = {
                (float(x), float(y)): float(value)
                for (x, y), value in zip(
                    scatter.get_offsets(), scatter.get_array(), strict=True
                )
            }
            expected = {
                (float(row.lon), float(row.lat)): float(getattr(row, value_column))
                for row in matched.itertuples(index=False)
            }
            assert observed == expected
            np.testing.assert_allclose(scatter.get_paths()[0].vertices, expected_circle)
    finally:
        plt.close(figure)
