"""Exact count-predictive scoring tests (design §7, §8; #189)."""

from __future__ import annotations

import numpy as np
import pytest

from genomeos.validation.predictive import MAX_COUNT, CountPredictive, predictive_diagnostics


def test_explicit_cpu_cdf_backend_matches_default():
    means = np.array([[0.1], [0.4]])
    default = CountPredictive(means)
    explicit = CountPredictive(means, cdf_backend="scipy")
    np.testing.assert_array_equal(default.cdf([2], [10]), explicit.cdf([2], [10]))


def test_unknown_cdf_backend_is_not_a_fallback():
    with pytest.raises(ValueError, match="cdf_backend"):
        CountPredictive(np.array([[0.2]]), cdf_backend="automatic")


@pytest.mark.parametrize("backend", [None, 1, ["scipy"]])
def test_non_string_cdf_backend_is_refused(backend):
    """Malformed selectors must receive the same explicit contract error."""
    with pytest.raises(ValueError, match="cdf_backend"):
        CountPredictive(np.array([[0.2]]), cdf_backend=backend)


def test_binomial_log_prob_is_the_log_of_the_integrated_normalized_mass():
    """Dropping choose(AN, AC), or averaging logs, makes this hand result fail."""
    predictive = CountPredictive(np.array([[0.1], [0.9]]))

    result = predictive.log_prob(ac=np.array([0]), an=np.array([1]))

    assert result == pytest.approx(np.array([np.log(0.5)]))
    assert result[0] != pytest.approx((np.log(0.9) + np.log(0.1)) / 2)

    normalized = CountPredictive(np.array([[0.5], [0.5]])).log_prob(
        ac=np.array([1]), an=np.array([2])
    )
    assert normalized == pytest.approx(np.array([np.log(0.5)]))


def test_beta_binomial_log_prob_matches_a_hand_calculated_mixture():
    """Replacing the beta-binomial with a plug-in binomial changes 11/30 to 1/2."""
    predictive = CountPredictive(
        mean_draws=np.array([[0.5], [0.5]]),
        concentration=np.array([[2.0], [4.0]]),
    )

    # For n=2, k=1: BetaBinomial(1, 1) has mass 1/3 and
    # BetaBinomial(2, 2) has mass 2/5, whose mixture is 11/30.
    result = predictive.log_prob(ac=np.array([1]), an=np.array([2]))

    assert result == pytest.approx(np.array([np.log(11 / 30)]))


@pytest.mark.parametrize("concentration", [None, np.array([[3.0, 3.0], [3.0, 3.0]])])
def test_probability_endpoints_remain_exact_degenerate_distributions(concentration):
    """Clipping p=0/1 would assign mass to impossible outcomes."""
    predictive = CountPredictive(
        np.array([[0.0, 1.0], [0.0, 1.0]]), concentration=concentration
    )

    possible = predictive.log_prob(ac=np.array([0, 5]), an=np.array([5, 5]))
    impossible = predictive.log_prob(ac=np.array([1, 4]), an=np.array([5, 5]))

    assert np.array_equal(possible, np.array([0.0, 0.0]))
    assert np.array_equal(impossible, np.array([-np.inf, -np.inf]))
    assert np.array_equal(
        predictive.cdf(ac=np.array([-1, 4]), an=np.array([5, 5])),
        np.array([0.0, 0.0]),
    )
    assert np.array_equal(
        predictive.cdf(ac=np.array([0, 5]), an=np.array([5, 5])),
        np.array([1.0, 1.0]),
    )


def test_analytic_mixture_cdfs_match_hand_calculated_values():
    """Evaluating only a mean probability misses mixture uncertainty."""
    binomial = CountPredictive(np.array([[0.25], [0.75]]))
    beta_binomial = CountPredictive(
        np.array([[0.5], [0.5]]), concentration=np.array([[2.0], [2.0]])
    )

    assert binomial.cdf(ac=np.array([0]), an=np.array([2])) == pytest.approx(
        np.array([0.3125])
    )
    assert beta_binomial.cdf(ac=np.array([0]), an=np.array([2])) == pytest.approx(
        np.array([1 / 3])
    )


def test_public_count_quantiles_are_exact_left_continuous_endpoints():
    """Returning frequency widths alone would hide the actual discrete interval endpoints."""
    predictive = CountPredictive(np.array([[0.0], [1.0]]))

    result = predictive.quantiles(an=np.array([1]), probabilities=np.array([0.5, 1.0]))

    np.testing.assert_array_equal(result, np.array([[0], [1]]))


def test_beta_binomial_cdf_handles_huge_denominators_with_a_short_exact_tail():
    """An AN-sized support array would make exact scoring unusable for large surveys."""
    an = 1_000_000_000
    predictive = CountPredictive(
        np.array([[0.5]]), concentration=np.array([[2.0]])
    )

    # BetaBinomial(n, alpha=1, beta=1) is uniform on 0, ..., n.
    assert predictive.cdf(ac=np.array([0]), an=np.array([an])) == pytest.approx(
        np.array([1 / (an + 1)]), rel=1e-6
    )
    assert predictive.cdf(ac=np.array([an - 1]), an=np.array([an])) == pytest.approx(
        np.array([an / (an + 1)]), rel=1e-12
    )


def test_beta_binomial_cdf_preserves_tiny_lower_tail_near_mean_one():
    """Subtracting a rounded-to-one survival tail erases valid lower-tail mass."""
    predictive = CountPredictive(
        np.array([[np.nextafter(1.0, 0.0)]]),
        concentration=np.array([[1.0 / np.sqrt(np.finfo(float).eps)]]),
    )

    # For n=2, P(Y<=1) = b(b + 1 + 2a) / (c(c + 1)), with
    # a=p*c and b=(1-p)*c. The hand-evaluated double-precision result is nonzero.
    result = predictive.cdf(ac=np.array([1]), an=np.array([2]))

    assert result == pytest.approx(
        np.array([2.220446032706701e-16]), rel=1e-12, abs=0.0
    )


def test_count_support_boundary_is_finite_and_larger_denominators_are_refused():
    """Allowing int64.max overflows AN+1; the declared supported boundary must be real."""
    predictive = CountPredictive(np.array([[0.5]]))

    log_mass = predictive.log_prob(ac=np.array([0]), an=np.array([MAX_COUNT]))

    assert log_mass == pytest.approx(np.array([MAX_COUNT * np.log(0.5)]))
    assert np.all(np.isfinite(log_mass))
    with pytest.raises(ValueError, match="supported maximum"):
        predictive.log_prob(
            ac=np.array([0]), an=np.array([np.iinfo(np.int64).max])
        )


def test_count_samples_are_seeded_draw_aligned_and_preserve_endpoints():
    """Changing the seed contract or sampling a pooled draw breaks reproducibility/shape."""
    predictive = CountPredictive(
        mean_draws=np.array([[0.0, 0.25, 1.0], [0.0, 0.75, 1.0]]),
        concentration=np.full((2, 3), 4.0),
    )
    an = np.array([7, 11, 13])

    first = predictive.sample_counts(an, seed=17)
    second = predictive.sample_counts(an, seed=17)

    assert first.shape == (2, 3)
    assert np.array_equal(first, second)
    assert np.array_equal(first[:, 0], np.array([0, 0]))
    assert np.array_equal(first[:, 2], np.array([13, 13]))
    assert np.all((first >= 0) & (first <= an))


def test_diagnostics_use_count_median_for_mae_and_frequency_mean_for_mse():
    """Substituting one point summary for both error metrics changes this example."""
    predictive = CountPredictive(np.array([[0.1], [0.1], [0.9]]))

    diagnostics = predictive_diagnostics(
        predictive, ac=np.array([0]), an=np.array([1]), seed=7
    )

    assert list(diagnostics.columns) == [
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
    ]
    row = diagnostics.iloc[0]
    assert row["log_score"] == pytest.approx(np.log(19 / 30))
    assert row["absolute_error"] == pytest.approx(0.0)
    assert row["squared_error"] == pytest.approx((11 / 30) ** 2)
    assert bool(row["coverage_50"])
    assert row["interval_width_50"] == pytest.approx(1.0)
    assert bool(row["coverage_80"])
    assert row["interval_width_80"] == pytest.approx(1.0)
    assert bool(row["coverage_95"])
    assert row["interval_width_95"] == pytest.approx(1.0)


def test_randomized_pit_is_deterministic_and_uses_the_lower_cdf_boundary():
    """Using F(y) directly would put a zero-count PIT above its probability jump."""
    predictive = CountPredictive(np.array([[0.25], [0.75]]))

    first = predictive_diagnostics(predictive, ac=np.array([0]), an=np.array([1]))
    second = predictive_diagnostics(predictive, ac=np.array([0]), an=np.array([1]))

    assert first.loc[0, "randomized_pit"] == second.loc[0, "randomized_pit"]
    # F(-1)=0 and the hand-integrated mass at zero is (0.75 + 0.25) / 2 = 0.5.
    expected = np.random.default_rng(42).random() * 0.5
    assert first.loc[0, "randomized_pit"] == pytest.approx(expected)


@pytest.mark.parametrize(
    ("mean_draws", "concentration", "message"),
    [
        (np.array([0.2, 0.3]), None, "two-dimensional"),
        (np.empty((0, 1)), None, "at least one"),
        (np.array([[0.2, np.nan]]), None, "finite"),
        (np.array([["0.2"]]), None, "numeric"),
        (np.array([[-0.1, 0.2]]), None, "between 0 and 1"),
        (np.array([[0.2, 1.1]]), None, "between 0 and 1"),
        (np.array([[0.2, 0.3]]), np.array([[2.0]]), "same shape"),
        (np.array([[0.2]]), np.array([[0.0]]), "positive"),
        (np.array([[0.2]]), np.array([[np.nan]]), "finite"),
    ],
)
def test_predictive_parameters_fail_closed(mean_draws, concentration, message):
    """Malformed predictive draws must not be reshaped, clipped, or defaulted."""
    with pytest.raises(ValueError, match=message):
        CountPredictive(mean_draws, concentration=concentration)


@pytest.mark.parametrize(
    ("mean", "concentration"),
    [
        (np.nextafter(0.0, 1.0), 0.1),
        (np.nextafter(1.0, 0.0), np.nextafter(0.0, 1.0)),
        (0.5, np.finfo(float).max),
    ],
)
def test_unusable_derived_beta_shapes_are_refused_before_scoring(mean, concentration):
    """Raw finite inputs can still underflow or exceed stable beta-binomial arithmetic."""
    with pytest.raises(ValueError, match="beta-binomial shape"):
        CountPredictive(
            np.array([[mean]]), concentration=np.array([[concentration]])
        )


def test_predictive_arrays_are_immutable_copies():
    """A frozen wrapper is not immutable if callers can mutate its NumPy buffers."""
    supplied = np.array([[0.2]])
    predictive = CountPredictive(supplied, concentration=np.array([[3.0]]))
    supplied[0, 0] = 0.8

    assert predictive.mean_draws[0, 0] == pytest.approx(0.2)
    with pytest.raises(ValueError, match="read-only"):
        predictive.mean_draws[0, 0] = 0.4
    with pytest.raises(ValueError):
        predictive.mean_draws.setflags(write=True)
    with pytest.raises(ValueError):
        predictive.concentration.setflags(write=True)


@pytest.mark.parametrize(
    ("method", "ac", "an", "message"),
    [
        ("log_prob", np.array([0.5]), np.array([2]), "integer"),
        ("log_prob", np.array([-1]), np.array([2]), "between 0 and AN"),
        ("log_prob", np.array([3]), np.array([2]), "between 0 and AN"),
        ("log_prob", np.array([np.nan]), np.array([2]), "finite"),
        ("log_prob", np.array(["0"]), np.array([2]), "numeric"),
        ("log_prob", np.array([0]), np.array([0]), "positive"),
        ("log_prob", np.array([0, 1]), np.array([2, 2]), "shape"),
        ("cdf", np.array([-2]), np.array([2]), "between -1 and AN"),
        ("cdf", np.array([3]), np.array([2]), "between -1 and AN"),
    ],
)
def test_count_inputs_fail_closed(method, ac, an, message):
    """Counts are observations/thresholds, so invalid values cannot be coerced."""
    predictive = CountPredictive(np.array([[0.3]]))

    with pytest.raises(ValueError, match=message):
        getattr(predictive, method)(ac=ac, an=an)


def test_sample_denominators_and_diagnostic_observations_are_validated():
    """Sampling and diagnostic helpers must not bypass the public count contract."""
    predictive = CountPredictive(np.array([[0.3]]))

    with pytest.raises(ValueError, match="integer"):
        predictive.sample_counts(np.array([2.5]))
    with pytest.raises(ValueError, match="positive"):
        predictive.sample_counts(np.array([0]))
    with pytest.raises(ValueError, match="between 0 and AN"):
        predictive_diagnostics(predictive, ac=np.array([-1]), an=np.array([2]))
