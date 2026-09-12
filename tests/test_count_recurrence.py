"""Independent finite count-law regressions (design §7, §8)."""

from __future__ import annotations

import numpy as np
import pytest

from genomeos.validation.predictive import CountPredictive
from tests.count_recurrence_oracle import verified_law


def test_high_concentration_one_trial_preserves_bernoulli():
    p = np.nextafter(1.0, 0.0)
    law = CountPredictive(np.array([[p]]), np.array([[1e300]]))
    np.testing.assert_allclose(law.log_prob([1], [1]), [np.log(p)], rtol=2e-12, atol=0)
    assert law.cdf([0], [1])[0] == 1 - p
    np.testing.assert_array_equal(law.quantiles([1], [1 - p, np.nextafter(1 - p, 1), 1]), [[0], [1], [1]])


FOCUSED_LAWS = [
    (20, 0.05, 134217728.0),
    (64, 0.5, 1e300),
    (1025, 0.001, 1e12),
    (4097, 0.5, 2.0),
    (65536, 1e-16, 1e300),
    (65536, 0.5, np.nextafter(2.0, np.inf)),
    (1025, 0.5, 1e-10),
    (1025, np.nextafter(1.0, 0.0), 1e300),
    (1025, 0.999, 1e12),
]


def support_queries(n, p):
    center = int(np.floor(n * p))
    return tuple(sorted({k for k in (0, 1, center - 1, center, center + 1, n - 1, n) if 0 <= k <= n}))


def assert_probability(actual, expected):
    reference = float(expected)
    if reference == 0:
        assert actual == 0  # True float underflow; Decimal remains nonzero.
    elif reference < np.finfo(float).tiny:
        assert abs(actual - reference) <= 4 * np.nextafter(0.0, 1.0)
    else:
        assert abs(actual - reference) <= 1e-11
        assert abs(actual - reference) <= 1e-9 * reference


@pytest.mark.parametrize("n,p,c", FOCUSED_LAWS)
def test_public_mass_and_lower_tail_against_absolute_oracle(n, p, c):
    counts = support_queries(n, p)
    reference = verified_law(n, p, c, counts)
    law = CountPredictive(np.full((1, len(counts)), p), np.full((1, len(counts)), c))
    logs = law.log_prob(counts, [n] * len(counts))
    lower = law.cdf(counts, [n] * len(counts))
    for index, exact in enumerate(reference.log_mass):
        rounded = float(exact)
        tolerance = max(5e-10, 4 * abs(np.spacing(rounded)))
        assert abs(logs[index] - rounded) <= tolerance
        if abs(rounded) < 1e-8:
            np.testing.assert_allclose(logs[index], rounded, rtol=2e-12, atol=0)
        assert_probability(lower[index], reference.lower[index])


@pytest.mark.parametrize("n,p,c", FOCUSED_LAWS)
def test_both_partition_tails_and_mass_against_absolute_oracle(n, p, c):
    from genomeos.validation.count_recurrence import beta_binomial_log_partitions

    counts = support_queries(n, p)
    reference = verified_law(n, p, c, counts)
    parts = beta_binomial_log_partitions(
        np.asarray(p), np.asarray(c), np.asarray(n), np.array(counts), array_module=np, max_count=n
    )
    lower, upper = parts.tails(array_module=np)
    for index in range(len(counts)):
        assert_probability(lower[index], reference.lower[index])
        assert_probability(upper[index], reference.upper[index])


@pytest.mark.parametrize("n,p,c", FOCUSED_LAWS[:2])
def test_all_small_support_masses_moments_and_complement(n, p, c):
    counts = tuple(range(n + 1))
    reference = verified_law(n, p, c, counts)
    law = CountPredictive(np.full((1, n + 1), p), np.full((1, n + 1), c))
    logs = law.log_prob(counts, [n] * (n + 1))
    exact_logs = np.array([float(x) for x in reference.log_mass])
    probabilities = np.exp(logs)
    exact_probabilities = np.array([float(x.exp()) for x in reference.log_mass])
    np.testing.assert_allclose(logs, exact_logs, atol=5e-10, rtol=0)
    np.testing.assert_allclose(probabilities, exact_probabilities, atol=5e-13, rtol=0)
    np.testing.assert_allclose(probabilities, exact_probabilities, atol=0, rtol=1e-10)
    assert abs(probabilities.sum() - 1) <= 5e-12
    mean = float(reference.mean)
    assert abs(np.dot(counts, probabilities) - mean) <= 5e-10
    assert abs(np.dot((np.array(counts) - mean) ** 2, probabilities) - float(reference.variance)) <= 5e-10
    reverse = CountPredictive(np.full((1, n + 1), 1 - p), np.full((1, n + 1), c))
    np.testing.assert_allclose(logs, reverse.log_prob(np.arange(n, -1, -1), [n] * (n + 1)), rtol=0, atol=5e-8)


@pytest.mark.parametrize("backend", ["scipy", "cupy"])
@pytest.mark.parametrize("operation", ["log_prob", "cdf_low", "cdf_high", "quantiles", "sample_counts"])
def test_high_count_refused_before_backend_access(backend, operation):
    law = CountPredictive(np.array([[0.0], [0.5]]), np.array([[2.0], [1e300]]), backend)
    with pytest.raises(ValueError, match="AN <= 65536"):
        if operation == "cdf_low":
            law.cdf([-1], [65537])
        elif operation == "cdf_high":
            law.cdf([65537], [65537])
        elif operation == "quantiles":
            law.quantiles([65537], [1.0])
        elif operation == "sample_counts":
            law.sample_counts([65537])
        else:
            law.log_prob([0], [65537])


@pytest.mark.parametrize("c", [67108864.0, np.nextafter(67108864.0, np.inf), 1e300])
def test_concentration_seams_admitted(c):
    law = CountPredictive(np.array([[0.5]]), np.array([[c]]))
    np.testing.assert_allclose(law.log_prob([0], [1]), [np.log(0.5)], atol=0, rtol=2e-12)


@pytest.mark.parametrize(
    "p,c",
    [(0.5, np.nextafter(1e300, np.inf)), (np.nextafter(0.0, 1.0), 1e-10), (0.25, 3 * np.nextafter(0.0, 1.0))],
)
def test_unusable_and_outside_domain_shapes_still_refused(p, c):
    with pytest.raises(ValueError, match="shape parameters"):
        CountPredictive(np.array([[p]]), np.array([[c]]))


def test_low_concentration_large_count_and_degenerate_scope_retained():
    n = 2**31 - 1
    low = CountPredictive(np.array([[0.5]]), np.array([[2.0]]))
    assert low.cdf([0], [n])[0] == pytest.approx(1 / (n + 1), rel=1e-5)
    assert low.sample_counts([n]).shape == (1, 1)
    degenerate = CountPredictive(np.array([[0.0, 1.0]]), np.full((1, 2), np.finfo(float).max))
    np.testing.assert_array_equal(degenerate.log_prob([0, n], [n, n]), [0, 0])
    np.testing.assert_array_equal(degenerate.quantiles([n, n], [1]), [[0, n]])
    np.testing.assert_array_equal(degenerate.sample_counts([n, n]), [[0, n]])


@pytest.mark.parametrize("n,c", [(1025, 1e-10), (1025, 1e300), (4097, 2.0)])
def test_exact_analytical_quantile_ties(n, c):
    law = CountPredictive(np.array([[0.5]]), np.array([[c]]))
    assert law.cdf([n // 2], [n])[0] == 0.5
    assert law.quantiles([n], [0.5])[0, 0] == n // 2
    if c == 2:
        levels = np.array([1, 1024, 2049, n + 1]) / (n + 1)
        np.testing.assert_array_equal(law.quantiles([n], levels)[:, 0], [0, 1023, 2048, n])


def test_unequal_denominators_and_129_draw_five_query_boundary(monkeypatch):
    from genomeos.validation import count_recurrence as recurrence

    means = np.tile(np.array([0.05, 0.5, 0.95]), 43)[:, None]
    means = np.broadcast_to(means, (129, 5)).copy()
    means[0, 0], means[1, 1] = 0.0, 1.0
    concentrations = np.broadcast_to(np.tile([2.0, 1e12, 134217728.0], 43)[:, None], means.shape)
    denominators = np.array([2, 3, 20, 64, 1025])
    counts = denominators // 2
    law = CountPredictive(means, concentrations)
    expected = []
    for observation, (n, k) in enumerate(zip(denominators, counts, strict=True)):
        values = []
        for p, c in zip(means[:, observation], concentrations[:, observation], strict=True):
            values.append(
                1.0
                if p == 0
                else 0.0
                if p == 1
                else float(verified_law(int(n), float(p), float(c), (int(k),)).lower[0])
            )
        expected.append(np.mean(values))
    np.testing.assert_allclose(law.cdf(counts, denominators), expected, rtol=1e-9, atol=1e-11)
    interior = (means.T > 0) & (means.T < 1)
    working_means = np.where(interior, means.T, 0.5)
    parts = recurrence.beta_binomial_log_partitions(
        working_means,
        concentrations.T,
        denominators[:, None],
        counts[:, None],
        array_module=np,
        max_count=1025,
    )
    monkeypatch.setattr(recurrence, "SUPPORT_CHUNK_SIZE", 257)
    alternate = recurrence.beta_binomial_log_partitions(
        working_means,
        concentrations.T,
        denominators[:, None],
        counts[:, None],
        array_module=np,
        max_count=1025,
    )
    # The numerical interface accepts only interior values; compare just those lanes.
    interior = (means.T > 0) & (means.T < 1)
    np.testing.assert_allclose(
        parts.log_mass(array_module=np)[interior],
        alternate.log_mass(array_module=np)[interior],
        atol=5e-10,
        rtol=0,
    )


@pytest.mark.parametrize("p,c", [(0.05, 134217728.0), (0.5, 1e300), (0.95, 134217728.0)])
def test_sampler_seed_and_fixed_independent_moment_bounds(p, c):
    import warnings

    n, size = 64, 20000
    reference = verified_law(n, p, c, (0, n))
    law = CountPredictive(np.full((size, 1), p), np.full((size, 1), c))
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        sample = law.sample_counts([n], seed=42)
    np.testing.assert_array_equal(sample, law.sample_counts([n], seed=42))
    assert sample.shape == (size, 1)
    assert np.issubdtype(sample.dtype, np.integer)
    assert np.all((sample >= 0) & (sample <= n))
    variance, mu4 = float(reference.variance), float(reference.fourth_central)
    assert abs(sample.mean() - float(reference.mean)) <= 6 * np.sqrt(variance / size)
    variance_se = np.sqrt((mu4 - ((size - 3) / (size - 1)) * variance**2) / size)
    assert abs(sample.var(ddof=1) - variance) <= 6 * variance_se


def test_sampler_admitted_shape_extremes_are_finite_without_warnings():
    import warnings

    tiny, near_one = np.nextafter(0.0, 1.0), np.nextafter(1.0, 0.0)
    parameters = [
        (tiny, 1e300),
        (tiny, 134217728.0),
        (1e-16, 1e-10),
        (0.5, 1e-10),
        (near_one, 1e-10),
        (near_one, 1e300),
    ]
    means, concentrations = np.array(parameters).T
    law = CountPredictive(means[None, :], concentrations[None, :])
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        sample = law.sample_counts([1, 2, 20, 64, 20, 64])
    assert sample.shape == (1, 6)
    assert np.all((sample >= 0) & (sample <= [1, 2, 20, 64, 20, 64]))


def test_full_diagnostics_and_strict_oracle_quantile_brackets():
    from genomeos.validation.predictive import predictive_diagnostics

    n, p, c, k = 20, 0.05, 134217728.0, 1
    reference = verified_law(n, p, c, tuple(range(n + 1)))
    lower = np.array([float(x) for x in reference.lower])
    levels = np.array([0.025, 0.1, 0.25, 0.5, 0.75, 0.9, 0.975])
    quantiles = np.searchsorted(lower, levels)
    assert np.all(lower[quantiles] > levels)
    assert all(q == 0 or lower[q - 1] < level for q, level in zip(quantiles, levels, strict=True))
    law = CountPredictive(np.array([[p]]), np.array([[c]]))
    np.testing.assert_array_equal(law.quantiles([n], levels)[:, 0], quantiles)
    frame = predictive_diagnostics(law, [k], [n], seed=42)
    assert list(frame) == [
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
    assert frame.log_score[0] == pytest.approx(float(reference.log_mass[k]), abs=5e-10)
    assert frame.absolute_error[0] == abs(quantiles[3] / n - k / n)
    assert frame.squared_error[0] == (p - k / n) ** 2
    for level, lo, hi in [(50, 2, 4), (80, 1, 5), (95, 0, 6)]:
        assert frame[f"coverage_{level}"][0] == (quantiles[lo] <= k <= quantiles[hi])
        assert frame[f"interval_width_{level}"][0] == (quantiles[hi] - quantiles[lo]) / n
    pit = lower[k - 1] + np.random.default_rng(42).uniform() * float(reference.log_mass[k].exp())
    assert frame.randomized_pit[0] == pytest.approx(pit, abs=1e-11, rel=1e-9)
    import pandas as pd

    pd.testing.assert_frame_equal(frame, predictive_diagnostics(law, [k], [n], seed=42))


@pytest.mark.parametrize("n,p,c", FOCUSED_LAWS)
def test_mode_anchor_has_legal_adjacent_probability_ratios(n, p, c):
    from decimal import Decimal, localcontext

    from genomeos.validation.count_recurrence import _mode

    anchor = int(_mode(np.array(p), np.array(c), np.array(n), np))
    assert 0 <= anchor <= n
    with localcontext() as context:
        context.prec = 400
        p, c = Decimal.from_float(float(p)), Decimal.from_float(float(c))
        alpha, beta = p * c, (1 - p) * c
        if anchor > 0:
            ratio = Decimal(n - anchor + 1) / anchor * (alpha + anchor - 1) / (beta + n - anchor)
            assert ratio >= 1
        if anchor < n:
            ratio = Decimal(n - anchor) / (anchor + 1) * (alpha + anchor) / (beta + n - anchor - 1)
            assert ratio <= 1


@pytest.mark.parametrize("p", [np.nextafter(0.0, 1.0), 1e-16, np.nextafter(1.0, 0.0)])
def test_one_trial_near_certain_logs_include_subnormal_accuracy(p):
    law = CountPredictive(np.array([[p]]), np.array([[1e300]]))
    for k, expected in [(0, np.log1p(-p)), (1, np.log(p))]:
        actual = law.log_prob([k], [1])[0]
        if abs(expected) < np.finfo(float).tiny:
            assert abs(actual - expected) <= 4 * np.nextafter(0.0, 1.0)
        else:
            np.testing.assert_allclose(actual, expected, atol=0, rtol=2e-12)


def test_high_concentration_does_not_evaluate_legacy_beta_normalizer(monkeypatch):
    import genomeos.validation.predictive as module

    original = module.betaln

    def check_shapes(alpha, beta):
        assert np.all(alpha + beta <= 67108864.0)
        return original(alpha, beta)

    monkeypatch.setattr(module, "betaln", check_shapes)
    law = CountPredictive(np.array([[0.5], [0.5]]), np.array([[20.0], [1e300]]))
    assert np.isfinite(law.log_prob([1], [2])[0])
    assert 0 < law.cdf([1], [2])[0] < 1
