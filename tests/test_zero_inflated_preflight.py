"""Count-mixture method preflight tests (design §§7–8; issue #103)."""

from __future__ import annotations

import numpy as np
import pytest
from scipy.stats import betabinom

from genomeos.validation.zero_inflated_preflight import (
    compare_count_models,
    count_log_mass,
    fit_count_model,
    profile_structural_zero,
)


def test_log_mass_preserves_sampling_zeros_inside_the_extra_zero_component() -> None:
    ac = np.array([0, 1])
    an = np.array([2, 2])

    beta_binomial = np.exp(
        count_log_mass(ac, an, mean=0.5, concentration=2.0, structural_zero=0.0)
    )
    inflated = np.exp(
        count_log_mass(ac, an, mean=0.5, concentration=2.0, structural_zero=0.25)
    )

    assert beta_binomial == pytest.approx([1 / 3, 1 / 3])
    assert inflated == pytest.approx([0.25 + 0.75 / 3, 0.75 / 3])
    assert inflated[0] > 0.25


@pytest.mark.parametrize(
    ("ac", "an", "mean", "concentration", "structural_zero", "message"),
    [
        ([0], [0], 0.1, 20.0, 0.1, "positive"),
        ([2], [1], 0.1, 20.0, 0.1, "between zero and AN"),
        ([0.5], [2], 0.1, 20.0, 0.1, "integer"),
        ([0], [2], 0.0, 20.0, 0.1, "strictly between zero and one"),
        ([0], [2], 0.1, 0.0, 0.1, "positive"),
        ([0], [2], 0.1, 20.0, -0.1, "between zero and one"),
    ],
)
def test_log_mass_refuses_invalid_counts_and_parameters(
    ac, an, mean, concentration, structural_zero, message
) -> None:
    with pytest.raises(ValueError, match=message):
        count_log_mass(
            ac,
            an,
            mean=mean,
            concentration=concentration,
            structural_zero=structural_zero,
        )


def _inflated_fixture(seed: int = 42) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    n_groups = 80
    rows_per_group = 4
    groups = np.repeat([f"cohort-{index:03d}" for index in range(n_groups)], rows_per_group)
    folds = np.repeat(np.arange(n_groups) % 5, rows_per_group)
    an = np.tile(np.array([100, 300, 1_000, 2_000]), n_groups)
    alpha, beta = 0.04 * 80.0, 0.96 * 80.0
    ac = betabinom.rvs(an, alpha, beta, random_state=rng)
    absent = rng.random(len(ac)) < 0.35
    ac = np.where(absent, 0, ac).astype(int)
    return ac, an, groups, folds


def test_fit_finds_a_reproducible_mixture_without_row_order_dependence() -> None:
    ac, an, _, _ = _inflated_fixture()

    fit = fit_count_model(ac, an, model="zero_inflated_beta_binomial")
    reordered = fit_count_model(
        ac[::-1], an[::-1], model="zero_inflated_beta_binomial"
    )
    baseline = fit_count_model(ac, an, model="beta_binomial")

    assert fit == reordered
    assert 0.15 < fit.structural_zero_probability < 0.60
    assert fit.log_likelihood > baseline.log_likelihood
    assert fit.n_successful_starts >= 3
    assert fit.n_equivalent_starts >= 3


def test_cohort_blocked_comparison_reports_separate_zero_and_positive_scores() -> None:
    ac, an, groups, folds = _inflated_fixture()

    result = compare_count_models(ac, an, groups=groups, folds=folds)

    assert result.n_folds == 5
    assert result.n_groups == 80
    assert result.groups_split == 0
    assert result.folds_improved >= 4
    assert result.mean_group_log_score_delta > 0.0
    assert np.isfinite(result.mean_zero_log_score_delta)
    assert np.isfinite(result.mean_positive_log_score_delta)
    assert sum(fold.n_test for fold in result.folds) == len(ac)


def test_comparison_refuses_a_cohort_split_between_folds() -> None:
    ac, an, groups, folds = _inflated_fixture()
    folds = folds.copy()
    folds[1] = (folds[0] + 1) % 5

    with pytest.raises(ValueError, match="cohort groups must not be split"):
        compare_count_models(ac, an, groups=groups, folds=folds)


def test_fit_refuses_unidentifiable_all_zero_or_all_positive_inputs() -> None:
    with pytest.raises(ValueError, match="zero and positive"):
        fit_count_model([0] * 10, [100] * 10, model="zero_inflated_beta_binomial")
    with pytest.raises(ValueError, match="zero and positive"):
        fit_count_model(
            list(range(1, 11)), [100] * 10, model="zero_inflated_beta_binomial"
        )


def test_model_name_is_explicit_and_fail_closed() -> None:
    with pytest.raises(ValueError, match="model must be one of"):
        fit_count_model([0, 1] * 5, [100] * 10, model="hurdle")


def test_structural_zero_profile_is_sorted_reproducible_and_anchored_at_baseline() -> None:
    ac, an, _, _ = _inflated_fixture()

    profile = profile_structural_zero(
        ac, an, probabilities=np.array([0.20, 0.0, 0.10, 0.05])
    )
    repeated = profile_structural_zero(
        ac[::-1], an[::-1], probabilities=np.array([0.0, 0.05, 0.10, 0.20])
    )
    baseline = fit_count_model(ac, an, model="beta_binomial")

    assert profile == repeated
    assert [point.structural_zero_probability for point in profile] == [
        0.0,
        0.05,
        0.10,
        0.20,
    ]
    assert profile[0].log_likelihood == pytest.approx(baseline.log_likelihood, abs=1e-8)
    assert max(profile, key=lambda point: point.log_likelihood).structural_zero_probability > 0
