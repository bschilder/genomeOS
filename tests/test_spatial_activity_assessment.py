"""Marginal and component assessment tests for issue #384."""

from __future__ import annotations

import numpy as np
import pytest

from genomeos.validation.spatial_activity_preflight import ActivityCountPredictive


def _predictive() -> ActivityCountPredictive:
    return ActivityCountPredictive(
        conditional_mean_draws=np.array(
            [
                [0.10, 0.20, 0.30],
                [0.20, 0.25, 0.35],
                [0.15, 0.30, 0.25],
                [0.25, 0.35, 0.40],
            ]
        ),
        activity_probability_draws=np.array(
            [
                [0.90, 0.80, 0.70],
                [0.80, 0.75, 0.65],
                [0.85, 0.70, 0.75],
                [0.75, 0.65, 0.60],
            ]
        ),
        concentration_draws=np.full((4, 3), 40.0),
    )


def test_assessment_reports_required_count_strata_and_truth_recovery() -> None:
    from genomeos.validation.spatial_activity_assessment import (
        assess_spatial_activity_prediction,
    )

    predictive = _predictive()
    marginal_truth = np.array([0.18, 0.27, 0.34]) * np.array([0.82, 0.72, 0.68])
    assessment = assess_spatial_activity_prediction(
        predictive,
        ac=np.array([0, 2, 4]),
        an=np.array([20, 20, 20]),
        marginal_mean_truth=marginal_truth,
        conditional_mean_truth=np.array([0.18, 0.27, 0.34]),
        activity_probability_truth=np.array([0.82, 0.72, 0.68]),
        seed=17,
    )

    assert len(assessment.diagnostics) == 3
    assert tuple(assessment.diagnostics["observed_ac"]) == (0, 2, 4)
    assert tuple(assessment.diagnostics["observed_an"]) == (20, 20, 20)
    assert assessment.all_rows.n_observations == 3
    assert assessment.zero_rows.n_observations == 1
    assert assessment.positive_rows.n_observations == 2
    assert assessment.all_rows.mean_log_score == pytest.approx(
        assessment.diagnostics["log_score"].mean()
    )
    assert assessment.positive_rows.mae == pytest.approx(
        assessment.diagnostics.loc[[1, 2], "absolute_error"].mean()
    )
    expected_marginal = np.mean(
        predictive.conditional_mean_draws * predictive.activity_probability_draws,
        axis=0,
    )
    assert assessment.recovery.marginal_mean_mae == pytest.approx(
        np.mean(np.abs(expected_marginal - marginal_truth))
    )
    assert assessment.recovery.conditional_mean_mae is not None
    assert assessment.recovery.activity_probability_mae is not None
    assert assessment.recovery.mean_absolute_component_correlation is not None
    assert assessment.null_false_support is None


def test_null_assessment_measures_false_inactive_support_from_draws() -> None:
    from genomeos.validation.spatial_activity_assessment import (
        NULL_ACTIVITY_THRESHOLD,
        assess_spatial_activity_prediction,
    )

    predictive = _predictive()
    assessment = assess_spatial_activity_prediction(
        predictive,
        ac=np.array([0, 2, 4]),
        an=np.array([20, 20, 20]),
        marginal_mean_truth=np.array([0.18, 0.27, 0.34]),
        conditional_mean_truth=np.array([0.18, 0.27, 0.34]),
        activity_probability_truth=np.ones(3),
        seed=42,
    )

    assert NULL_ACTIVITY_THRESHOLD == 0.9
    assert assessment.null_false_support is not None
    assert assessment.null_false_support.mean_inactive_probability == pytest.approx(
        np.mean(1.0 - predictive.activity_probability_draws)
    )
    assert assessment.null_false_support.fraction_draws_below_threshold == pytest.approx(
        np.mean(predictive.activity_probability_draws < NULL_ACTIVITY_THRESHOLD)
    )


def test_absent_zero_or_positive_stratum_is_reported_not_fabricated() -> None:
    from genomeos.validation.spatial_activity_assessment import (
        assess_spatial_activity_prediction,
    )

    predictive = _predictive()
    assessment = assess_spatial_activity_prediction(
        predictive,
        ac=np.array([1, 2, 4]),
        an=np.array([20, 20, 20]),
        marginal_mean_truth=np.array([0.18, 0.27, 0.34]) * np.array([0.82, 0.72, 0.68]),
        conditional_mean_truth=np.array([0.18, 0.27, 0.34]),
        activity_probability_truth=np.array([0.82, 0.72, 0.68]),
        seed=42,
    )

    assert assessment.zero_rows.n_observations == 0
    assert assessment.zero_rows.mean_log_score is None
    assert assessment.zero_rows.mae is None
    assert assessment.zero_rows.coverage_50 is None
    assert assessment.positive_rows.n_observations == 3


def test_constant_components_report_unavailable_correlation() -> None:
    from genomeos.validation.spatial_activity_assessment import (
        assess_spatial_activity_prediction,
    )

    predictive = ActivityCountPredictive(
        conditional_mean_draws=np.full((4, 2), 0.2),
        activity_probability_draws=np.ones((4, 2)),
        concentration_draws=np.full((4, 2), 40.0),
    )
    assessment = assess_spatial_activity_prediction(
        predictive,
        ac=np.array([0, 2]),
        an=np.array([20, 20]),
        marginal_mean_truth=np.array([0.2, 0.2]),
        conditional_mean_truth=np.array([0.2, 0.2]),
        activity_probability_truth=np.ones(2),
        seed=42,
    )

    assert assessment.recovery.mean_absolute_component_correlation is None
    assert assessment.recovery.correlated_observation_count == 0


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        ("marginal_mean_truth", np.array([0.1, 0.2]), "marginal_mean_truth"),
        ("conditional_mean_truth", np.array([0.1, np.nan, 0.3]), "conditional_mean_truth"),
        (
            "activity_probability_truth",
            np.array([0.1, 1.2, 0.3]),
            "activity_probability_truth",
        ),
        ("conditional_mean_truth", np.array([0.1, 0.0, 0.3]), "strictly"),
    ],
)
def test_assessment_refuses_invalid_truth(field: str, value: object, match: str) -> None:
    from genomeos.validation.spatial_activity_assessment import (
        assess_spatial_activity_prediction,
    )

    kwargs = {
        "marginal_mean_truth": np.array([0.18, 0.27, 0.34])
        * np.array([0.82, 0.72, 0.68]),
        "conditional_mean_truth": np.array([0.18, 0.27, 0.34]),
        "activity_probability_truth": np.array([0.82, 0.72, 0.68]),
    }
    kwargs[field] = value
    with pytest.raises(ValueError, match=match):
        assess_spatial_activity_prediction(
            _predictive(),
            ac=np.array([0, 2, 4]),
            an=np.array([20, 20, 20]),
            seed=42,
            **kwargs,
        )


def test_assessment_refuses_wrong_predictive_type() -> None:
    from genomeos.validation.spatial_activity_assessment import (
        assess_spatial_activity_prediction,
    )

    with pytest.raises(ValueError, match="predictive"):
        assess_spatial_activity_prediction(
            object(),
            ac=np.array([0]),
            an=np.array([20]),
            marginal_mean_truth=np.array([0.1]),
            conditional_mean_truth=np.array([0.2]),
            activity_probability_truth=np.array([0.5]),
            seed=42,
        )
