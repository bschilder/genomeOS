"""Spatial-activity mixture preflight tests (design §§7–8; issues #103, #384)."""

from __future__ import annotations

import numpy as np
import pytest

from genomeos.validation.predictive import predictive_diagnostics
from genomeos.validation.spatial_activity_preflight import (
    ActivityCountPredictive,
    simulate_activity_counts,
)


def test_predictive_marginalizes_activity_without_classifying_zero_counts() -> None:
    predictive = ActivityCountPredictive(
        conditional_mean_draws=np.array([[0.5], [0.5]]),
        activity_probability_draws=np.array([[0.75], [0.75]]),
        concentration_draws=np.array([[2.0], [2.0]]),
    )

    probability = np.exp(predictive.log_prob(ac=[0], an=[2]))

    # BetaBinomial(2, alpha=1, beta=1) assigns 1/3 to every count. The
    # marginalized zero probability is 1/4 + 3/4 * 1/3 = 1/2.
    assert probability == pytest.approx([0.5])


def test_activity_one_is_exactly_the_ordinary_beta_binomial_boundary() -> None:
    predictive = ActivityCountPredictive(
        conditional_mean_draws=np.array([[0.5], [0.5]]),
        activity_probability_draws=np.ones((2, 1)),
        concentration_draws=np.full((2, 1), 2.0),
    )

    probability = np.exp(predictive.log_prob(ac=[0], an=[2]))

    assert probability == pytest.approx([1 / 3])


def test_cdf_retains_both_zero_paths_and_reaches_one_at_the_denominator() -> None:
    predictive = ActivityCountPredictive(
        conditional_mean_draws=np.array([[0.5]]),
        activity_probability_draws=np.array([[0.75]]),
        concentration_draws=np.array([[2.0]]),
    )

    assert predictive.cdf(ac=[-1], an=[2]) == pytest.approx([0.0])
    assert predictive.cdf(ac=[0], an=[2]) == pytest.approx([0.5])
    assert predictive.cdf(ac=[1], an=[2]) == pytest.approx([0.75])
    assert predictive.cdf(ac=[2], an=[2]) == pytest.approx([1.0])


def test_existing_count_diagnostics_score_the_full_activity_mixture() -> None:
    predictive = ActivityCountPredictive(
        conditional_mean_draws=np.array([[0.5], [0.5]]),
        activity_probability_draws=np.ones((2, 1)),
        concentration_draws=np.full((2, 1), 2.0),
    )

    diagnostics = predictive_diagnostics(predictive, ac=[1], an=[2], seed=42)

    assert diagnostics.loc[0, "log_score"] == pytest.approx(np.log(1 / 3))
    assert diagnostics.loc[0, "absolute_error"] == pytest.approx(0.0)
    assert diagnostics.loc[0, "squared_error"] == pytest.approx(0.0)
    assert bool(diagnostics.loc[0, "coverage_50"])
    assert bool(diagnostics.loc[0, "coverage_80"])
    assert bool(diagnostics.loc[0, "coverage_95"])


def test_component_diagnostics_report_dependence_without_interpreting_it() -> None:
    predictive = ActivityCountPredictive(
        conditional_mean_draws=np.array([[0.1], [0.2], [0.3]]),
        activity_probability_draws=np.array([[0.9], [0.8], [0.7]]),
        concentration_draws=np.full((3, 1), 20.0),
    )

    diagnostics = predictive.component_diagnostics()

    assert diagnostics.component_correlation == pytest.approx((-1.0,))
    assert diagnostics.conditional_mean_sd[0] > 0.0
    assert diagnostics.activity_probability_sd[0] > 0.0
    assert diagnostics.marginal_mean_sd[0] > 0.0


def test_predictive_sampling_is_seeded_draw_aligned_and_respects_inactivity() -> None:
    predictive = ActivityCountPredictive(
        conditional_mean_draws=np.full((4, 2), 0.25),
        activity_probability_draws=np.column_stack((np.zeros(4), np.ones(4))),
        concentration_draws=np.full((4, 2), 30.0),
    )

    first = predictive.sample_counts(an=[20, 20], seed=42)
    second = predictive.sample_counts(an=[20, 20], seed=42)

    np.testing.assert_array_equal(first, second)
    assert first.shape == (4, 2)
    np.testing.assert_array_equal(first[:, 0], np.zeros(4, dtype=int))
    assert np.all((first[:, 1] >= 0) & (first[:, 1] <= 20))


def test_single_chromosome_counts_expose_exact_component_nonidentifiability() -> None:
    first = ActivityCountPredictive(
        conditional_mean_draws=np.array([[0.2]]),
        activity_probability_draws=np.array([[0.5]]),
        concentration_draws=np.array([[10.0]]),
    )
    second = ActivityCountPredictive(
        conditional_mean_draws=np.array([[0.5]]),
        activity_probability_draws=np.array([[0.2]]),
        concentration_draws=np.array([[10.0]]),
    )

    for ac in (0, 1):
        assert first.log_prob(ac=[ac], an=[1]) == pytest.approx(
            second.log_prob(ac=[ac], an=[1])
        )
    assert first.marginal_mean_frequency() == pytest.approx([0.1])
    assert second.marginal_mean_frequency() == pytest.approx([0.1])


def test_simulation_is_seeded_and_preserves_latent_truth_separately() -> None:
    total = np.array([20, 20, 20, 20])
    conditional_mean = np.full(4, 0.2)
    concentration = np.full(4, 30.0)
    activity_probability = np.array([0.0, 0.25, 0.75, 1.0])

    first = simulate_activity_counts(
        total,
        conditional_mean=conditional_mean,
        concentration=concentration,
        activity_probability=activity_probability,
        seed=42,
    )
    second = simulate_activity_counts(
        total,
        conditional_mean=conditional_mean,
        concentration=concentration,
        activity_probability=activity_probability,
        seed=42,
    )

    assert first == second
    assert first.active[0] is False
    assert first.ac[0] == 0
    assert first.active[-1] is True
    assert all(0 <= ac <= an for ac, an in zip(first.ac, total, strict=True))


@pytest.mark.parametrize(
    ("conditional_mean", "activity_probability", "concentration", "message"),
    [
        ([[0.2, 0.3]], [[0.5]], [[20.0]], "same shape"),
        ([[0.0]], [[0.5]], [[20.0]], "strictly between zero and one"),
        ([[0.2]], [[-0.1]], [[20.0]], "between zero and one"),
        ([[0.2]], [[0.5]], [[0.0]], "positive"),
    ],
)
def test_predictive_refuses_malformed_component_draws(
    conditional_mean, activity_probability, concentration, message
) -> None:
    with pytest.raises(ValueError, match=message):
        ActivityCountPredictive(
            conditional_mean_draws=np.asarray(conditional_mean),
            activity_probability_draws=np.asarray(activity_probability),
            concentration_draws=np.asarray(concentration),
        )
