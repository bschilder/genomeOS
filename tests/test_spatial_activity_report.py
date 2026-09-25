"""Aggregate spatial-activity review artifact tests (design §8; issue #384)."""

from __future__ import annotations

import hashlib
import json

import matplotlib.pyplot as plt
import pytest

from scripts.plot_spatial_activity_preflight import (
    CAMPAIGN_MANIFEST_SHA256,
    build_figure,
    build_public_summary,
)


def _comparison(
    truth: str,
    denominator: float,
    cohort_sd: float,
) -> dict[str, object]:
    return {
        "condition_id": (
            f"{truth}|denominator={denominator:g}|cohort_sd={cohort_sd:g}"
        ),
        "truth": truth,
        "denominator_multiplier": denominator,
        "cohort_sd": cohort_sd,
        "paired_outer_fold_count": 15,
        "paired_zero_stratum_count": 15,
        "paired_positive_stratum_count": 15,
        "complete": True,
        "mean_log_score_delta": 0.04,
        "log_score_delta_ci95_low": 0.01,
        "log_score_delta_ci95_high": 0.07,
        "relative_mae_improvement": 0.08,
        "relative_marginal_recovery_improvement": 0.12,
        "mean_zero_log_score_delta": 0.03,
        "mean_positive_log_score_delta": 0.05,
        "candidate_coverage_50": 0.51,
        "candidate_coverage_80": 0.80,
        "candidate_coverage_95": 0.94,
        "candidate_mean_absolute_component_correlation": 0.35,
        "candidate_component_correlation_fold_count": 15,
        "candidate_component_correlation_observation_count": 90,
        "candidate_mean_inactive_probability": 0.04 if truth == "null" else None,
        "candidate_fraction_draws_below_activity_threshold": (
            0.12 if truth == "null" else None
        ),
    }


def _result() -> dict[str, object]:
    conditions = (
        ("null", 1.0, 0.0),
        ("localized_weak", 1.0, 0.0),
        ("localized_strong", 1.0, 0.0),
        ("localized_strong", 0.25, 0.0),
        ("localized_strong", 4.0, 0.0),
        ("localized_strong", 1.0, 0.5),
    )
    artifacts = {
        f"{hashlib.sha256(str(index).encode()).hexdigest()}.json": {
            "sha256": hashlib.sha256(f"result-{index}".encode()).hexdigest(),
            "size_bytes": index + 1,
        }
        for index in range(720)
    }
    return {
        "campaign_manifest_sha256": CAMPAIGN_MANIFEST_SHA256,
        "comparisons": [_comparison(*condition) for condition in conditions],
        "completed_task_count": 720,
        "decision": {"eligible_for_real_fit": True, "refusal_reasons": []},
        "evidence_kind": "synthetic_preflight",
        "format": "spatial_activity_campaign_result",
        "publication_eligible": False,
        "retried_task_count": 3,
        "task_artifacts": artifacts,
        "task_count": 720,
        "version": 1,
    }


def _encoded(result: dict[str, object]) -> bytes:
    return json.dumps(result, sort_keys=True).encode()


def test_public_summary_authenticates_but_excludes_task_artifact_inventory() -> None:
    result = _result()
    raw = _encoded(result)

    summary = build_public_summary(result, source_bytes=raw)

    assert summary["format"] == "spatial_activity_preflight_public_summary"
    assert summary["task_count"] == 720
    assert summary["completed_task_count"] == 720
    assert len(summary["comparisons"]) == 6
    assert "task_artifacts" not in summary
    assert summary["source_result_sha256"] == hashlib.sha256(raw).hexdigest()
    expected_inventory = json.dumps(
        result["task_artifacts"],
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    assert summary["task_artifact_inventory_sha256"] == hashlib.sha256(
        expected_inventory
    ).hexdigest()


def test_summary_refuses_incomplete_task_cover() -> None:
    result = _result()
    result["task_artifacts"].pop(next(iter(result["task_artifacts"])))

    with pytest.raises(ValueError, match="exactly 720 task artifacts"):
        build_public_summary(result, source_bytes=_encoded(result))


def test_summary_refuses_a_different_campaign_manifest() -> None:
    result = _result()
    result["campaign_manifest_sha256"] = "b" * 64

    with pytest.raises(ValueError, match="registered campaign manifest"):
        build_public_summary(result, source_bytes=_encoded(result))


def test_summary_refuses_an_unknown_result_version() -> None:
    result = _result()
    result["version"] = 2

    with pytest.raises(ValueError, match="result version"):
        build_public_summary(result, source_bytes=_encoded(result))


def test_summary_refuses_duplicate_or_missing_registered_condition() -> None:
    result = _result()
    result["comparisons"][-1] = result["comparisons"][0]

    with pytest.raises(ValueError, match="six registered conditions"):
        build_public_summary(result, source_bytes=_encoded(result))


def test_summary_refuses_a_missing_registered_metric() -> None:
    result = _result()
    del result["comparisons"][0]["candidate_coverage_80"]

    with pytest.raises(ValueError, match="missing registered metric"):
        build_public_summary(result, source_bytes=_encoded(result))


def test_summary_refuses_source_bytes_from_a_different_result() -> None:
    result = _result()
    changed = _result()
    changed["retried_task_count"] = 4

    with pytest.raises(ValueError, match="source bytes do not encode"):
        build_public_summary(result, source_bytes=_encoded(changed))


def test_figure_exposes_preregistered_thresholds_and_plain_condition_labels() -> None:
    result = _result()
    summary = build_public_summary(
        result,
        source_bytes=json.dumps(result, sort_keys=True).encode(),
    )

    figure = build_figure(summary)
    try:
        assert len(figure.axes) == 6
        titles = [axis.get_title(loc="left") for axis in figure.axes]
        assert titles == [
            "A  Held-out count log score",
            "B  Count-error improvement",
            "C  Marginal-truth recovery",
            "D  Predictive interval calibration",
            "E  Component dependence",
            "F  False inactive support under null truth",
        ]
        labels = [tick.get_text() for tick in figure.axes[0].get_xticklabels()]
        assert labels == [
            "Null",
            "Weak",
            "Strong\nprimary",
            "Strong\nlow n",
            "Strong\nhigh n",
            "Strong +\ncohort SD",
        ]
        assert "eligible" in figure._suptitle.get_text().lower()
    finally:
        plt.close(figure)


def test_figure_labels_incomplete_registered_conditions_explicitly() -> None:
    result = _result()
    result["comparisons"][1]["complete"] = False
    result["comparisons"][1]["mean_log_score_delta"] = None
    result["comparisons"][1]["log_score_delta_ci95_low"] = None
    result["comparisons"][1]["log_score_delta_ci95_high"] = None
    result["decision"] = {
        "eligible_for_real_fit": False,
        "refusal_reasons": ["localized_weak comparison is incomplete"],
    }
    summary = build_public_summary(
        result,
        source_bytes=json.dumps(result, sort_keys=True).encode(),
    )

    figure = build_figure(summary)
    try:
        labels = [tick.get_text() for tick in figure.axes[0].get_xticklabels()]
        assert labels[1] == "Weak\n(incomplete)"
        assert all(
            "incomplete" not in label.lower()
            for index, label in enumerate(labels)
            if index != 1
        )
    finally:
        plt.close(figure)




def test_figure_distinguishes_successful_fits_from_terminal_artifacts() -> None:
    result = _result()
    result["completed_task_count"] = 719
    result["comparisons"][0]["complete"] = False
    result["decision"] = {
        "eligible_for_real_fit": False,
        "refusal_reasons": ["one registered task ended in a scientific failure"],
    }
    summary = build_public_summary(
        result,
        source_bytes=json.dumps(result, sort_keys=True).encode(),
    )

    figure = build_figure(summary)
    try:
        footer = figure.texts[-1].get_text()
        assert "719/720 tasks completed successfully" in footer
        assert "all 720 terminal artifacts retained" in footer
        assert footer.count("\n") == 2
    finally:
        plt.close(figure)
