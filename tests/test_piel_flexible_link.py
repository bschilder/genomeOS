"""Piel flexible-link method preflight (design §7, §8; issue #103)."""

from __future__ import annotations

import numpy as np
import pytest

from genomeos.surfaces.piel_flexible_link import (
    SMOOTHING_RULES,
    fit_piel_flexible_link,
    smooth_piel_frequencies,
)


def _counts() -> tuple[np.ndarray, np.ndarray]:
    ac = np.array([0, 0, 1, 2, 4, 8, 12, 18, 25, 35, 50, 70])
    an = np.array([50, 100, 80, 120, 100, 150, 120, 150, 180, 200, 250, 300])
    return ac, an


def test_both_appendix_equations_are_preserved_exactly() -> None:
    ac = np.array([0, 10, 20])
    an = np.array([100, 100, 20])

    printed = smooth_piel_frequencies(ac, an, rule="piel_printed_2013")
    conjugate = smooth_piel_frequencies(ac, an, rule="uniform_binomial_conjugate")

    np.testing.assert_array_equal(printed, (ac + 1) / (an + ac + 2))
    np.testing.assert_array_equal(conjugate, (ac + 1) / (an + 2))
    assert printed[-1] == 0.5
    assert conjugate[-1] == pytest.approx(21 / 22)
    assert SMOOTHING_RULES == ("piel_printed_2013", "uniform_binomial_conjugate")


@pytest.mark.parametrize(
    ("ac", "an", "match"),
    [
        ([0, 1], [10], "same shape"),
        ([False, 1], [10, 10], "Boolean"),
        ([0, 1], [True, 10], "Boolean"),
        ([0.5, 1], [10, 10], "integer"),
        ([0, 1], [10.5, 10], "integer"),
        ([0, np.nan], [10, 10], "finite"),
        ([0, 1], [10, np.inf], "finite"),
        ([-1, 1], [10, 10], "between zero and AN"),
        ([0, 11], [10, 10], "between zero and AN"),
        ([0, 0], [10, 0], "positive"),
    ],
)
def test_smoothing_refuses_invalid_counts(ac, an, match) -> None:
    with pytest.raises(ValueError, match=match):
        smooth_piel_frequencies(ac, an, rule="piel_printed_2013")


def test_smoothing_rule_is_explicit_and_closed() -> None:
    with pytest.raises(ValueError, match="smoothing rule"):
        smooth_piel_frequencies([0], [100], rule="auto")


def test_fit_applies_the_appendix_an_floor_without_dropping_silently() -> None:
    ac, an = _counts()
    ac = np.append(ac, [0, 1])
    an = np.append(an, [49, 20])

    result = fit_piel_flexible_link(ac, an, rule="piel_printed_2013", min_an=50)

    assert result.n_total == 14
    assert result.n_eligible == 12
    assert result.n_below_min_an == 2
    assert result.min_an == 50
    assert result.normal_fit == "plug_in_mle"
    assert result.plotting_position == "hazen_rank_average"


@pytest.mark.parametrize("rule", SMOOTHING_RULES)
def test_fitted_cubic_is_strictly_increasing_over_the_real_line(rule) -> None:
    result = fit_piel_flexible_link(*_counts(), rule=rule)
    grid = np.array([-1e6, -100, -10, -1, 0, 1, 10, 100, 1e6])

    derivative = result.link.derivative(grid)
    frequency = result.link.frequency(np.linspace(-20, 20, 1001))

    assert result.link.derivative_floor > 0
    assert np.all(derivative > 0)
    assert np.all(np.diff(frequency) > 0)
    assert np.all((frequency > 0) & (frequency < 1))


@pytest.mark.parametrize("rule", SMOOTHING_RULES)
def test_fit_is_deterministic_under_input_reordering(rule) -> None:
    ac, an = _counts()
    first = fit_piel_flexible_link(ac, an, rule=rule)
    order = np.array([8, 2, 10, 0, 5, 11, 3, 6, 1, 9, 4, 7])
    second = fit_piel_flexible_link(ac[order], an[order], rule=rule)

    assert first == second


def test_two_equation_arms_remain_distinguishable() -> None:
    ac, an = _counts()
    printed = fit_piel_flexible_link(ac, an, rule="piel_printed_2013")
    conjugate = fit_piel_flexible_link(ac, an, rule="uniform_binomial_conjugate")

    assert printed.smoothed_frequency_max < conjugate.smoothed_frequency_max
    assert printed.link.coefficients != conjugate.link.coefficients


@pytest.mark.parametrize("min_an", [0, -1, True, 2.5])
def test_fit_requires_an_explicit_positive_integer_floor(min_an) -> None:
    with pytest.raises(ValueError, match="min_an"):
        fit_piel_flexible_link(*_counts(), rule="piel_printed_2013", min_an=min_an)


def test_fit_refuses_too_little_or_degenerate_information() -> None:
    with pytest.raises(ValueError, match="at least 8 eligible"):
        fit_piel_flexible_link([0] * 7, [100] * 7, rule="piel_printed_2013")
    with pytest.raises(ValueError, match="distinct smoothed frequencies"):
        fit_piel_flexible_link([0] * 8, [100] * 8, rule="piel_printed_2013")


def test_link_refuses_nonfinite_latent_values() -> None:
    result = fit_piel_flexible_link(*_counts(), rule="piel_printed_2013")
    with pytest.raises(ValueError, match="finite"):
        result.link.frequency([0.0, np.nan])
    with pytest.raises(ValueError, match="finite"):
        result.link.derivative([np.inf])
