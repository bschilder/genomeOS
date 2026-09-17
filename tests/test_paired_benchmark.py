"""Matched benchmark comparison tests (design §§4, 6–8; issue #189)."""

from __future__ import annotations

import itertools

import numpy as np
import pandas as pd
import pytest
from matplotlib.markers import MarkerStyle

from genomeos.validation.benchmark import BenchmarkFoldStatus
from genomeos.validation.paired_benchmark import compare_paired_benchmarks
from scripts.plot_hbs_current_gp_benchmark import (
    OBSERVATIONS_PARQUET_SHA256,
    OBSERVATIONS_TSV_SHA256,
    _compact_benchmark,
    _equivalent_summary,
    _run_diagnostics,
    _verify_shared_identity,
    build_figure,
    plt,
)


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


def _manifest(observations_sha256: str) -> dict[str, object]:
    split = {
        "split_id": "split-0",
        "block_id": "block-0",
        "buffer_km": 300.0,
        "data_version": "frozen",
        "input_fingerprint": "fingerprint",
        "train_ids": ["train"],
        "test_ids": ["test"],
        "excluded_ids": [],
        "exclusion_reasons": [],
        "min_edge_separation_km": 301.0,
    }
    return {
        "input_files": {
            "observations": {"sha256": observations_sha256, "size_bytes": 1},
            "assignments": {"sha256": "assignments", "size_bytes": 2},
            "dependencies": {"sha256": "dependencies", "size_bytes": 3},
        },
        "configuration": {"buffer_km": 300.0, "data_version": "frozen", "seed": 42},
        "splits": [split],
    }


def test_artifact_identity_accepts_only_the_two_frozen_observation_serializations():
    baseline = _manifest(OBSERVATIONS_TSV_SHA256)
    candidate = _manifest(OBSERVATIONS_PARQUET_SHA256)
    _verify_shared_identity(baseline, candidate)

    candidate["input_files"]["observations"]["sha256"] = OBSERVATIONS_TSV_SHA256
    with pytest.raises(ValueError, match="frozen Parquet"):
        _verify_shared_identity(baseline, candidate)


def test_summary_replay_allows_only_machine_level_float_rounding():
    original = {"rows": [{"label": "kept", "count": 2, "score": -11268.527876612001}]}
    replay = {"rows": [{"label": "kept", "count": 2, "score": -11268.527876612}]}
    assert _equivalent_summary(original, replay)

    replay["rows"][0]["score"] = -11268.52
    assert not _equivalent_summary(original, replay)
    replay = {"rows": [{"label": "changed", "count": 2, "score": -11268.527876612}]}
    assert not _equivalent_summary(original, replay)


def test_public_benchmark_summary_excludes_cohort_level_records():
    summary = {
        "comparison_complete": True,
        "split_counts": {"planned": 5, "completed": 5, "failed": 0, "infeasible": 0},
        "scored_observation_count": 994,
        "represented_cell_count": 5,
        "represented_declared_cohort_cell_count": 994,
        "zero_probability_count": 0,
        "metrics": {"mae": 0.1},
        "fold_status": [{"expected_test_ids": ["private-row"]}],
        "failure_reasons": [],
        "cell_metrics": [{"region_id": "region"}],
        "declared_cohort_cell_metrics": [{"cohort_id": "private-cohort"}],
    }
    compact = _compact_benchmark(summary)
    assert compact["scored_observation_count"] == 994
    assert compact["metrics"] == {"mae": 0.1}
    assert "fold_status" not in compact
    assert "cell_metrics" not in compact
    assert "declared_cohort_cell_metrics" not in compact


def test_terminal_run_log_retains_sampler_warning_counts(tmp_path):
    run_log = tmp_path / "run.log"
    fit = "NUTS[numpyro]: [lengthscale]\n"
    rhat = "The rhat statistic is larger than 1.01 for some parameters.\n"
    run_log.write_text(
        "environment probe mentions NUTS[numpyro]: twice NUTS[numpyro]:\n"
        + "===== B2 CURRENT GP CHECKPOINTED 2026-09-16T21:02:30Z =====\n"
        + (fit + rhat) * 4
        + fit
        + "There was 1 divergence after tuning. Increase target_accept.\n"
        + rhat
        + "===== DONE 2026-09-17T00:07:56Z =====\n"
    )
    diagnostics = _run_diagnostics(run_log)
    assert diagnostics["nuts_fit_invocation_count"] == 5
    assert diagnostics["rhat_above_1_01_warning_count"] == 5
    assert diagnostics["reported_post_tuning_divergence_count"] == 1
    assert diagnostics["convergence_acceptance"] == "not_met"

    run_log.write_text(run_log.read_text().replace(rhat, "", 1))
    with pytest.raises(ValueError, match="unexpected sampler warning counts"):
        _run_diagnostics(run_log)


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

    report, matched = compare_paired_benchmarks(candidate, baseline, statuses, split_ids)

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

    report, matched = compare_paired_benchmarks(candidate, baseline, statuses, split_ids)

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

    matched["lon"] = [-75.0, -20.0, 10.0, 35.0, 80.0]
    matched["lat"] = [40.0, 5.0, 10.0, -5.0, 20.0]
    figure = build_figure({"comparison": report}, matched)
    try:
        points = [
            collection
            for collection in figure.axes[0].collections
            if hasattr(collection, "get_offsets")
        ]
        assert len(points) == 1
        assert len(points[0].get_offsets()) == 5
        assert np.isfinite(points[0].get_array()).all()
    finally:
        plt.close(figure)


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
