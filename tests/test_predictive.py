"""Exact count-predictive scoring tests (design §7, §8; #189)."""

from __future__ import annotations

from decimal import Decimal, localcontext
from math import comb

import numpy as np
import pytest
from scipy.special import logsumexp
from scipy.stats import binom

from genomeos.validation import predictive as predictive_module
from genomeos.validation.predictive import MAX_COUNT, CountPredictive, predictive_diagnostics

_DECIMAL_PI = Decimal(
    "3.141592653589793238462643383279502884197169399375105820974944592307816406286"
)
_BERNOULLI = (
    (1, 6),
    (-1, 30),
    (1, 42),
    (-1, 30),
    (5, 66),
    (-691, 2730),
    (7, 6),
    (-3617, 510),
    (43867, 798),
    (-174611, 330),
    (854513, 138),
)


def _decimal_log_gamma(value: Decimal) -> Decimal:
    """Independent oracle shifted well beyond the production expansion point."""
    shifted_logs = Decimal(0)
    while value < 128:
        shifted_logs += value.ln()
        value += 1
    result = (value - Decimal(".5")) * value.ln() - value
    result += (2 * _DECIMAL_PI).ln() / 2
    for order, (numerator, denominator) in enumerate(_BERNOULLI, 1):
        result += Decimal(numerator) / (
            Decimal(denominator)
            * 2
            * order
            * (2 * order - 1)
            * value ** (2 * order - 1)
        )
    return result - shifted_logs


def _decimal_beta_binomial_log_mass(
    mean: float, concentration: float, count: int, denominator: int
) -> float:
    with localcontext() as context:
        context.prec = 160
        p = Decimal.from_float(mean)
        c = Decimal.from_float(concentration)
        k = Decimal(count)
        n = Decimal(denominator)
        alpha = p * c
        beta = (1 - p) * c
        result = (
            _decimal_log_gamma(n + 1)
            - _decimal_log_gamma(k + 1)
            - _decimal_log_gamma(n - k + 1)
            + _decimal_log_gamma(k + alpha)
            - _decimal_log_gamma(alpha)
            + _decimal_log_gamma(n - k + beta)
            - _decimal_log_gamma(beta)
            - _decimal_log_gamma(n + c)
            + _decimal_log_gamma(c)
        )
    return float(result)


def _decimal_log_rising_ratio(numerator: float, denominator: float, length: int) -> float:
    with localcontext() as context:
        context.prec = 160
        top = Decimal.from_float(numerator)
        bottom = Decimal.from_float(denominator)
        offset = Decimal(length)
        result = (
            _decimal_log_gamma(top + offset)
            - _decimal_log_gamma(top)
            - _decimal_log_gamma(bottom + offset)
            + _decimal_log_gamma(bottom)
        )
    return float(result)


@pytest.mark.parametrize("mean", [1e-16, 1e-12, 0.1, np.nextafter(1.0, 0.0)])
@pytest.mark.parametrize("concentration", [1e-10, 2.0, 1e6, 2.0**26])
def test_beta_binomial_one_trial_is_bernoulli_even_near_degeneracy(mean, concentration):
    """Beta-normalizer cancellation must not corrupt either Bernoulli outcome."""
    predictive = CountPredictive(np.full((3, 1), mean), np.full((3, 1), concentration))
    for count, expected in [(0, np.log1p(-mean)), (1, np.log(mean))]:
        np.testing.assert_allclose(
            predictive.log_prob([count], [1]), [expected], rtol=2e-14, atol=0.0
        )


@pytest.mark.parametrize(
    ("mean", "concentration", "count", "denominator"),
    [
        (1e-16, 1e6, 0, 2),
        (1e-12, 1e6, 0, 100),
        (np.nextafter(1.0, 0.0), 1e6, 100, 100),
        (1e-16, 1e6, 1, 100),
        (0.3, 2.0**26, 35, 100),
        (0.3, 1e-10, 35, 100),
        (1e-16, 1e6, 0, 65_536),
    ],
)
def test_beta_binomial_mass_matches_independent_decimal_products(
    mean, concentration, count, denominator
):
    """An in-range but cancellation-corrupted negative log mass is also a failure."""
    with localcontext() as context:
        context.prec = 80
        p, c = Decimal.from_float(mean), Decimal.from_float(concentration)
        alpha, beta = p * c, (1 - p) * c
        mass = Decimal(comb(denominator, count))
        for index in range(denominator):
            numerator = alpha + index if index < count else beta + index - count
            mass *= numerator / (c + index)
        expected = float(mass.ln())
    predictive = CountPredictive(np.array([[mean]]), np.array([[concentration]]))
    np.testing.assert_allclose(
        predictive.log_prob([count], [denominator]), [expected], rtol=5e-12, atol=0.0
    )


@pytest.mark.parametrize(
    ("mean", "concentration", "count", "denominator", "absolute_tolerance"),
    [
        (0.01, 30.0, 44_431, 2_571_112, 5e-9),
        (1e-12, 1e6, 0, 2_571_112, 5e-9),
        (np.nextafter(1.0, 0.0), 1e6, 2_571_112, 2_571_112, 5e-9),
        (0.25, 20.0, 0, MAX_COUNT, 2e-8),
        (0.25, 20.0, 536_870_912, MAX_COUNT, 3e-8),
        (0.01, 30.0, 21_474_836, MAX_COUNT, 3e-8),
        (0.5, 2.0, 1_073_741_823, MAX_COUNT, 3e-8),
        (1e-6, 1e6, 10_000, MAX_COUNT, 3e-8),
    ],
)
def test_beta_binomial_large_count_scoring_matches_independent_decimal_oracle(
    mean, concentration, count, denominator, absolute_tolerance
):
    """Large survey counts must not trigger support-sized work or beta subtraction."""
    expected = _decimal_beta_binomial_log_mass(mean, concentration, count, denominator)
    predictive = CountPredictive(np.array([[mean]]), np.array([[concentration]]))

    actual = predictive.log_prob([count], [denominator])

    np.testing.assert_allclose(actual, [expected], rtol=0.0, atol=absolute_tolerance)


@pytest.mark.parametrize("count", [644_245_094, 1_073_741_823])
def test_beta_binomial_max_count_high_concentration_matches_decimal_oracle(count):
    """The full declared domain has a ten-micro-log-unit absolute error envelope."""
    mean = 0.3
    concentration = 2.0**26
    expected = _decimal_beta_binomial_log_mass(mean, concentration, count, MAX_COUNT)
    predictive = CountPredictive(np.array([[mean]]), np.array([[concentration]]))

    actual = predictive.log_prob([count], [MAX_COUNT])

    np.testing.assert_allclose(actual, [expected], rtol=0.0, atol=1e-5)


def test_high_shape_rising_ratio_matches_independent_decimal_oracle():
    """The large positive paired factor must retain the small tail-log complement."""
    mean = 0.3
    concentration = 2.0**26
    numerator = mean * concentration
    length = 644_245_094
    expected = _decimal_log_rising_ratio(numerator, 1.0, length)

    actual = predictive_module._bounded_log_rising_ratio(
        np.array([numerator]),
        np.array([1.0]),
        length,
        difference=np.array([numerator - 1.0]),
    )

    np.testing.assert_allclose(actual, [expected], rtol=0.0, atol=1e-5)


def test_beta_binomial_million_count_high_concentration_matches_decimal_oracle():
    mean = 0.01
    concentration = 2.0**26
    count = 1_285_556
    denominator = 2_571_112
    expected = _decimal_beta_binomial_log_mass(mean, concentration, count, denominator)
    predictive = CountPredictive(np.array([[mean]]), np.array([[concentration]]))

    actual = predictive.log_prob([count], [denominator])

    np.testing.assert_allclose(actual, [expected], rtol=0.0, atol=1e-5)


@pytest.mark.parametrize("mean", [0.01, 0.3, 0.5, 0.9, 0.99])
@pytest.mark.parametrize("concentration", [2.0**20, 2.0**24, 2.0**26])
@pytest.mark.parametrize("count_fraction", [0.0, 0.25, 0.5, 0.75, 1.0])
def test_beta_binomial_high_shape_grid_matches_decimal_oracle(
    mean, concentration, count_fraction
):
    """The declared maximum domain retains ten-micro-log-unit absolute accuracy."""
    count = round(count_fraction * MAX_COUNT)
    expected = _decimal_beta_binomial_log_mass(mean, concentration, count, MAX_COUNT)
    predictive = CountPredictive(np.array([[mean]]), np.array([[concentration]]))

    actual = predictive.log_prob([count], [MAX_COUNT])

    np.testing.assert_allclose(actual, [expected], rtol=0.0, atol=1e-5)


def test_beta_binomial_high_shape_mixture_matches_decimal_oracle_and_reflection():
    count = 644_245_094
    means = np.array([[0.3], [0.7]])
    concentrations = np.full_like(means, 2.0**26)
    expected_draws = np.array(
        [
            _decimal_beta_binomial_log_mass(mean, 2.0**26, count, MAX_COUNT)
            for mean in means[:, 0]
        ]
    )
    forward = CountPredictive(means, concentrations)
    reflected = CountPredictive(1.0 - means, concentrations)

    actual = forward.log_prob([count], [MAX_COUNT])
    reverse = reflected.log_prob([MAX_COUNT - count], [MAX_COUNT])

    expected = logsumexp(expected_draws) - np.log(len(expected_draws))
    np.testing.assert_allclose(actual, [expected], rtol=0.0, atol=1e-5)
    np.testing.assert_allclose(actual, reverse, rtol=0.0, atol=1e-5)


def test_beta_binomial_large_count_mixture_integrates_draw_masses():
    means = np.array([[1e-12], [0.01], [0.2], [np.nextafter(1.0, 0.0)]])
    concentrations = np.array([[1e6], [30.0], [2.0], [1e6]])
    count, denominator = 44_431, 2_571_112
    expected_draws = np.array(
        [
            _decimal_beta_binomial_log_mass(float(mean), float(shape), count, denominator)
            for mean, shape in zip(means[:, 0], concentrations[:, 0], strict=True)
        ]
    )
    predictive = CountPredictive(means, concentrations)

    actual = predictive.log_prob([count], [denominator])

    expected = logsumexp(expected_draws) - np.log(len(expected_draws))
    np.testing.assert_allclose(actual, [expected], rtol=0.0, atol=5e-9)


def test_beta_binomial_large_count_scoring_preserves_allele_complement():
    means = np.array([[1e-12], [0.01], [0.2], [0.8]])
    concentrations = np.array([[1e6], [30.0], [2.0], [7.0]])
    count, denominator = 44_431, 2_571_112
    forward = CountPredictive(means, concentrations)
    reverse = CountPredictive(1.0 - means, concentrations)

    np.testing.assert_allclose(
        forward.log_prob([count], [denominator]),
        reverse.log_prob([denominator - count], [denominator]),
        rtol=0.0,
        atol=5e-9,
    )


def test_beta_binomial_large_count_log_mass_does_not_materialize_support(
    monkeypatch: pytest.MonkeyPatch,
):
    def refuse_support(*args, **kwargs):
        raise AssertionError("log_prob must not materialize a count-support array")

    monkeypatch.setattr(predictive_module.np, "arange", refuse_support)
    predictive = CountPredictive(np.array([[0.01]]), np.array([[30.0]]))

    result = predictive.log_prob([44_431], [2_571_112])

    assert np.isfinite(result[0])


def test_beta_scoring_cap_does_not_restrict_exact_degenerate_or_binomial_draws():
    """Only interior beta draws require bounded finite products."""
    degenerate = CountPredictive(np.array([[0.0, 1.0]]), np.ones((1, 2)))
    np.testing.assert_array_equal(degenerate.log_prob([0, MAX_COUNT], [MAX_COUNT] * 2), [0, 0])
    binomial = CountPredictive(np.array([[0.1]]))
    np.testing.assert_allclose(binomial.log_prob([0], [65_537]), [65_537 * np.log1p(-0.1)])


def test_stable_beta_mixture_normalizes_and_respects_allele_complement():
    """Finite-product scoring must retain normalization and both allele orientations."""
    means = np.array([[0.125], [0.875]])
    concentration = np.array([[1e-10], [2.0**26]])
    forward = CountPredictive(means, concentration)
    reverse = CountPredictive(1 - means, concentration)
    masses = np.array([forward.log_prob([k], [8])[0] for k in range(9)])
    reflected = np.array([reverse.log_prob([8 - k], [8])[0] for k in range(9)])
    assert np.exp(masses).sum() == pytest.approx(1.0, rel=2e-14, abs=0.0)
    np.testing.assert_allclose(masses, reflected, rtol=2e-14, atol=0.0)


@pytest.mark.parametrize("concentration", [None, 20.0])
@pytest.mark.parametrize(
    "means",
    [[[0.1, 0.5]], [[0.0, 0.0]], [[1.0, 1.0]],
     [[0.0, 0.0], [0.1, 0.5]], [[0.0, 0.0], [1.0, 1.0]]],
)
def test_one_hundred_percent_quantiles_use_exact_mixture_support(concentration, means):
    """A rounded-one CDF below AN must never shorten the actual upper support."""
    means = np.array(means)
    shape = None if concentration is None else np.full_like(means, concentration)
    predictive = CountPredictive(means, shape)
    expected = [0, 0] if np.all(means == 0) else [100, 1000]
    np.testing.assert_array_equal(predictive.quantiles([100, 1000], [1.0]), [expected])


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


def test_rare_quantiles_bracket_predictive_mass_before_exact_search(
    monkeypatch: pytest.MonkeyPatch,
):
    """The first CDF probe must not traverse half of a million-count rare-allele support."""
    predictive = CountPredictive(np.full((4, 1), 1e-6))
    original_factory = CountPredictive._cdf_evaluator
    probes: list[np.ndarray] = []

    def instrumented_factory(self: CountPredictive):
        evaluate = original_factory(self)

        def record_and_evaluate(count: np.ndarray, denominator: np.ndarray) -> np.ndarray:
            probes.append(count.copy())
            return evaluate(count, denominator)

        return record_and_evaluate

    monkeypatch.setattr(CountPredictive, "_cdf_evaluator", instrumented_factory)

    result = predictive.quantiles(
        an=np.array([1_000_000]),
        probabilities=np.array([0.025, 0.1, 0.25, 0.5, 0.75, 0.9, 0.975]),
    )

    np.testing.assert_array_equal(result[:, 0], np.array([0, 0, 0, 1, 2, 2, 3]))
    assert probes
    assert int(np.max(probes[0])) < 10_000


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


def _decimal_beta_binomial_cdf(mean: float, concentration: float, count: int, an: int) -> Decimal:
    with localcontext() as context:
        context.prec = 100
        p = Decimal.from_float(mean)
        c = Decimal.from_float(concentration)
        alpha, beta = p * c, (1 - p) * c
        total = Decimal(0)
        for k in range(count + 1):
            mass = Decimal(comb(an, k))
            for index in range(an):
                numerator = alpha + index if index < k else beta + index - k
                mass *= numerator / (c + index)
            total += mass
        return +total


@pytest.mark.parametrize("concentration", [2.0**27, 1e12, 1e300])
def test_high_concentration_complete_support_matches_decimal_diagnostics(concentration):
    """The old B0H failure region must retain the finite law through every diagnostic."""
    mean, count, an = 0.37, 7, 20
    lower = _decimal_beta_binomial_cdf(mean, concentration, count - 1, an)
    inclusive = _decimal_beta_binomial_cdf(mean, concentration, count, an)
    mass = inclusive - lower
    predictive = CountPredictive(
        np.asarray([[mean]]), np.asarray([[concentration]])
    )

    assert predictive.log_prob([count], [an])[0] == pytest.approx(
        float(mass.ln()), rel=2e-14, abs=2e-14
    )
    assert predictive.cdf([count], [an])[0] == pytest.approx(
        float(inclusive), rel=2e-14, abs=0.0
    )
    levels = np.asarray([0.025, 0.5, 0.975])
    oracle_cdf = [
        _decimal_beta_binomial_cdf(mean, concentration, candidate, an)
        for candidate in range(an + 1)
    ]
    expected_quantiles = [
        next(index for index, value in enumerate(oracle_cdf) if value >= Decimal.from_float(level))
        for level in levels
    ]
    np.testing.assert_array_equal(
        predictive.quantiles([an], levels)[:, 0], expected_quantiles
    )

    diagnostics = predictive_diagnostics(predictive, [count], [an], seed=42)
    expected_pit = lower + Decimal.from_float(np.random.default_rng(42).random()) * mass
    assert diagnostics.loc[0, "randomized_pit"] == pytest.approx(
        float(expected_pit), rel=0.0, abs=np.finfo(float).eps
    )
    assert 0.0 <= diagnostics.loc[0, "randomized_pit"] <= 1.0


def test_one_high_concentration_draw_retains_original_mixture_weight():
    """Routing one exceptional draw must not drop it or renormalize either subgroup."""
    mean, count, an = 0.37, 7, 20
    concentrations = (20.0, 2.0**27)
    component_cdf = [
        _decimal_beta_binomial_cdf(mean, concentration, count, an)
        for concentration in concentrations
    ]
    component_mass = [
        cdf - _decimal_beta_binomial_cdf(mean, concentration, count - 1, an)
        for cdf, concentration in zip(component_cdf, concentrations, strict=True)
    ]
    expected_cdf = sum(component_cdf) / 2
    expected_mass = sum(component_mass) / 2
    predictive = CountPredictive(
        np.asarray([[mean], [mean]]),
        np.asarray([[concentrations[0]], [concentrations[1]]]),
    )

    assert predictive.log_prob([count], [an])[0] == pytest.approx(
        float(expected_mass.ln()), rel=2e-14, abs=2e-14
    )
    assert predictive.cdf([count], [an])[0] == pytest.approx(
        float(expected_cdf), rel=2e-14, abs=0.0
    )


def test_high_concentration_large_support_refuses_at_operation_boundary():
    """A valid predictive artifact may exist even when one requested operation is unsupported."""
    predictive = CountPredictive(np.asarray([[0.4]]), np.asarray([[2.0**27]]))

    for operation in (
        lambda: predictive.log_prob([0], [65_537]),
        lambda: predictive.cdf([0], [65_537]),
        lambda: predictive.quantiles([65_537], [0.5]),
        lambda: predictive.sample_counts([65_537]),
    ):
        with pytest.raises(ValueError, match="high-concentration|65536"):
            operation()


def test_concentration_route_boundary_preserves_each_supported_count_domain():
    """The exact legacy boundary stays full-domain; the next float takes the support-bounded route."""
    mean = np.asarray([[0.4]])
    threshold = 2.0**26
    legacy = CountPredictive(mean, np.asarray([[threshold]]))
    direct = CountPredictive(mean, np.asarray([[np.nextafter(threshold, np.inf)]]))

    assert np.isfinite(legacy.log_prob([0], [65_537])[0])
    assert direct.sample_counts([65_536], seed=42).shape == (1, 1)
    with pytest.raises(ValueError, match="high-concentration|65536"):
        direct.log_prob([0], [65_537])


def test_high_concentration_converges_to_binomial_without_substitution():
    mean, count, an = 0.37, 7, 20
    predictive = CountPredictive(np.asarray([[mean]]), np.asarray([[1e300]]))
    beta_mass = np.exp(predictive.log_prob([count], [an]))[0]
    binomial_mass = float(binom.pmf(count, an, mean))

    assert beta_mass == pytest.approx(binomial_mass, rel=2e-14, abs=0.0)


@pytest.mark.parametrize(
    ("mean", "concentration", "count", "an"),
    [
        (1e-11, 5000.0, 0, 2),
        (1e-11, 8000.0, 1, 352),
        (0.0014, 6400.0, 6, 52),
        (0.18, 6000.0, 103, 290),
    ],
)
def test_beta_binomial_cdf_matches_independent_decimal_oracle_near_one(
    mean, concentration, count, an
):
    """A shorter lower support tail can still be near one and lose complement precision."""
    expected = float(_decimal_beta_binomial_cdf(mean, concentration, count, an))
    predictive = CountPredictive(np.array([[mean]]), np.array([[concentration]]))

    result = predictive.cdf([count], [an])[0]

    assert result == pytest.approx(expected, rel=2e-15, abs=0.0)
    assert 0.0 <= result <= 1.0


def test_beta_binomial_cdf_and_pit_preserve_complements_and_mixture_bounds():
    """Wrong tail selection can corrupt either allele orientation and push a mixture PIT over one."""
    means = np.array([[1e-11], [1.0 - 1e-11]])
    concentrations = np.full((2, 1), 5000.0)
    predictive = CountPredictive(means, concentrations)
    reverse = CountPredictive(1.0 - means, concentrations)

    forward_cdf = predictive.cdf([0], [2])[0]
    reflected_survival = 1.0 - reverse.cdf([1], [2])[0]
    diagnostics = predictive_diagnostics(predictive, [1], [2], seed=42)

    expected = float(
        (_decimal_beta_binomial_cdf(1e-11, 5000.0, 0, 2)
         + _decimal_beta_binomial_cdf(1.0 - 1e-11, 5000.0, 0, 2))
        / 2
    )
    assert forward_cdf == pytest.approx(expected, rel=2e-15, abs=0.0)
    assert reflected_survival == pytest.approx(expected, rel=2e-15, abs=0.0)
    assert 0.0 <= diagnostics.loc[0, "randomized_pit"] <= 1.0


def test_near_one_randomized_pit_matches_decimal_cdf_plus_independent_mass():
    """A negative but inaccurate near-one log CDF must not make a valid PIT exceed one."""
    mean, concentration = 1e-11, 5000.0
    predictive = CountPredictive(np.array([[mean]]), np.array([[concentration]]))
    diagnostics = predictive_diagnostics(predictive, [1], [2], seed=42)
    with localcontext() as context:
        context.prec = 100
        p, c = Decimal.from_float(mean), Decimal.from_float(concentration)
        mass_one = Decimal(2) * c * p * (1 - p) / (c + 1)
        expected = _decimal_beta_binomial_cdf(mean, concentration, 0, 2) + (
            Decimal.from_float(np.random.default_rng(42).random()) * mass_one
        )

    actual = diagnostics.loc[0, "randomized_pit"]
    assert actual == pytest.approx(float(expected), rel=0.0, abs=np.finfo(float).eps)
    assert 0.0 <= actual <= 1.0


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
