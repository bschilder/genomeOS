"""Held-out validation (design §7, §8).

The scoring code is tested on synthetic data with a known answer, so a bug in the metrics cannot
be mistaken for a bug in the model.
"""

import numpy as np
import pytest
from test_surface_fit import _observations

from genomeos.surfaces.fit import FitConfig
from genomeos.validation.crossval import (
    CrossValidation,
    FoldFailure,
    FoldResult,
    cross_validate,
    make_folds,
)

# n_inducing must respect the M<<N guard against the *fold* size, not the full dataset: each
# fold trains on (k-1)/k of the data, so a budget that is fine overall can be too large per fold.
FAST = FitConfig(draws=300, tune=600, chains=4, approximation="inducing", n_inducing=25)


def _fold(**kwargs) -> FoldResult:
    defaults = dict(
        fold=0, n_train=80, n_test=20, studies_split=0,
        coverage_95_predictive=0.95, coverage_50_predictive=0.5,
        coverage_95_latent=0.30, coverage_50_latent=0.10,
        mae=0.01, rmse=0.02, log_score=-2.0, baseline_mae=0.05, baseline_log_score=-3.0,
    )
    defaults.update(kwargs)
    return FoldResult(**defaults)


# --- folds ---


def test_spatial_folds_are_geographically_contiguous():
    """A random split leaks neighbours across train/test and flatters a spatial model."""
    observations = _observations(n=150)
    spatial = make_folds(observations, 5, "spatial")
    random = make_folds(observations, 5, "random")

    def mean_spread(folds):
        return np.mean([
            observations.loc[folds == f, "lon"].std() for f in sorted(set(folds))
        ])

    assert mean_spread(spatial) < mean_spread(random), "spatial folds must be tighter in space"


def test_every_observation_is_assigned_exactly_one_fold():
    observations = _observations(n=100)
    folds = make_folds(observations, 5, "spatial")
    assert len(folds) == len(observations)
    assert set(folds) <= set(range(5))


def test_folds_are_deterministic_given_the_seed():
    observations = _observations(n=100)
    assert np.array_equal(
        make_folds(observations, 4, "spatial", seed=3),
        make_folds(observations, 4, "spatial", seed=3),
    )


@pytest.mark.parametrize("bad", [1, 0, -2])
def test_too_few_folds_is_refused(bad):
    with pytest.raises(ValueError, match="n_folds"):
        make_folds(_observations(n=50), bad)


def test_unknown_strategy_is_refused():
    with pytest.raises(ValueError, match="strategy"):
        make_folds(_observations(n=50), 3, "leave-one-country-out")


# --- scoring ---


def test_skill_is_positive_only_when_the_model_beats_the_constant_baseline():
    """A spatial model that cannot beat "assume the global average" has no spatial skill."""
    better = CrossValidation("spatial", [_fold(log_score=-2.0, baseline_log_score=-3.0)])
    worse = CrossValidation("spatial", [_fold(log_score=-4.0, baseline_log_score=-3.0)])
    assert better.skill > 0
    assert worse.skill < 0


def test_the_summary_names_the_calibration_targets():
    """Calibration is the headline: §4's defence rests on the uncertainty being real."""
    text = str(CrossValidation("spatial", [_fold()]))
    assert "predictive coverage  95%" in text
    assert "target 0.95" in text


def test_summary_frame_has_one_row_per_fold():
    result = CrossValidation("spatial", [_fold(fold=0), _fold(fold=1)])
    assert len(result.summary()) == 2


# --- end to end, small ---


def test_cross_validation_runs_and_reports_coverage_between_zero_and_one():
    observations = _observations(n=90)
    result = cross_validate(observations, FAST, n_folds=3, strategy="spatial")
    assert len(result.folds) == 3
    for fold in result.folds:
        assert 0.0 <= fold.coverage_95_predictive <= 1.0
        assert 0.0 <= fold.coverage_50_predictive <= 1.0
        assert 0.0 <= fold.coverage_95_latent <= 1.0
        assert fold.mae >= 0.0
        assert fold.n_train + fold.n_test == len(observations)


# --- fold tolerance ---


def test_a_non_converged_fold_is_recorded_not_fatal():
    """One bad fold must not destroy the run; eight hours were once lost to exactly that."""
    result = CrossValidation(
        "spatial",
        folds=[_fold(fold=0), _fold(fold=1)],
        failures=[FoldFailure(2, 80, 20, "sampler did not converge (ESS 80 < 200)")],
    )
    assert result.n_attempted == 3
    assert len(result.folds) == 2
    assert "1 did not converge" in str(result)


def test_failed_folds_are_excluded_from_the_means_not_averaged_in():
    result = CrossValidation(
        "spatial",
        folds=[_fold(coverage_95_predictive=0.9)],
        failures=[FoldFailure(1, 80, 20, "boom")],
    )
    assert result._mean("coverage_95_predictive") == pytest.approx(0.9)


def test_a_run_where_nothing_converged_says_so_rather_than_reporting_nan():
    result = CrossValidation("spatial", folds=[], failures=[FoldFailure(0, 80, 20, "boom")])
    assert "no fold converged" in str(result)
    assert np.isnan(result._mean("mae"))


def test_predictive_coverage_exceeds_latent_coverage_on_the_same_data():
    """The predictive interval must be wider than the latent one, always.

    The latent interval describes the underlying frequency; the observed frequency is a noisy
    realisation of it, carrying binomial sampling noise and its own cohort offset. An interval
    missing those components cannot cover the data as often as one that includes them. This is
    the defect in #110 stated as an invariant: if this assertion ever fails, the predictive path
    has stopped adding the variance it exists to add.
    """
    observations = _observations(n=90)
    result = cross_validate(observations, FAST, n_folds=3, strategy="spatial")
    predictive = result._mean("coverage_95_predictive")
    latent = result._mean("coverage_95_latent")
    assert predictive >= latent, f"predictive {predictive:.2f} < latent {latent:.2f}"


def test_grouped_folds_keep_every_study_intact():
    """A study cut across the split appears as singletons in training, where `cohort_sd` and the
    beta-binomial `concentration` describe the same residual and are not jointly identifiable
    (#127) — the same degeneracy #121 found in AFND, here caused by us rather than by the source.
    """
    observations = _observations(n=60)
    observations["cohort_id"] = [f"study{i // 4}" for i in range(len(observations))]
    folds = make_folds(observations, 3, "grouped", 42)
    for _, group in observations.groupby("cohort_id"):
        assert len(set(folds[group.index])) == 1, "a study must not straddle folds"


def test_grouped_folds_stay_balanced():
    """Studies are assigned largest-first to the emptiest fold. Without that, one large study —
    the real corpus has one with 33 sites against 143 multi-site studies — leaves a fold nearly
    empty and its scores meaningless."""
    observations = _observations(n=60)
    sizes = [12, 10, 8, 6, 6, 5, 4, 3, 3, 2, 1]
    labels = [f"s{i}" for i, n in enumerate(sizes) for _ in range(n)][: len(observations)]
    observations["cohort_id"] = labels + ["sX"] * (len(observations) - len(labels))
    counts = np.bincount(make_folds(observations, 3, "grouped", 42), minlength=3)
    assert counts.max() <= 2 * counts.min(), f"folds too uneven: {counts}"


def test_random_folds_split_studies_and_grouped_folds_do_not():
    """The contrast is the point: `random` measures leakage *and* identifiability damage at once,
    which is two effects under one number. `grouped` separates them."""
    observations = _observations(n=60)
    observations["cohort_id"] = [f"study{i // 4}" for i in range(len(observations))]

    def split_count(strategy):
        folds = make_folds(observations, 3, strategy, 42)
        return sum(
            1 for _, g in observations.groupby("cohort_id") if len(set(folds[g.index])) > 1
        )

    assert split_count("grouped") == 0
    assert split_count("random") > 0


def test_the_summary_reports_how_many_studies_a_split_broke():
    """Reported next to the scores because it changes what a convergence failure means."""
    result = CrossValidation("random", [_fold(studies_split=17)])
    assert "studies split per fold" in str(result)
    assert result._mean("studies_split") == 17
