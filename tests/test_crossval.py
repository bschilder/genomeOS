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
    studies_split_across_folds,
)

# n_inducing must respect the M<<N guard against the *fold* size, not the full dataset: each
# fold trains on (k-1)/k of the data, so a budget that is fine overall can be too large per fold.
FAST = FitConfig(draws=300, tune=600, chains=4, approximation="inducing", n_inducing=25)


def _fold(**kwargs) -> FoldResult:
    defaults = dict(
        fold=0, n_train=80, n_test=20,
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


# --- grouped folds and the identifiability confound (#127) ---


def test_grouped_folds_never_split_a_study():
    """The whole point of the strategy, stated as an invariant.

    A study effect is identified by within-study replication. Split the study across the
    train/test boundary and it becomes a singleton in training, where `cohort_sd * cohort_z` and
    the beta-binomial `concentration` describe the same single residual and stop being jointly
    identifiable. If this assertion ever fails, `grouped` has silently become `random`.
    """
    observations = _observations(n=90)
    folds = make_folds(observations, 3, "grouped")
    split, multi_site = studies_split_across_folds(observations["cohort_id"], folds)
    assert multi_site > 0, "fixture must contain multi-site studies for this to mean anything"
    assert split == 0


def test_random_folds_shatter_studies_that_grouped_folds_keep_intact():
    """The #127 contrast, on the same data: 135/143 vs 7/143 in the real corpus."""
    observations = _observations(n=90)
    random_split, multi_site = studies_split_across_folds(
        observations["cohort_id"], make_folds(observations, 3, "random")
    )
    grouped_split, _ = studies_split_across_folds(
        observations["cohort_id"], make_folds(observations, 3, "grouped")
    )
    assert random_split > grouped_split == 0
    assert random_split == multi_site, "every multi-site study should be split by a random draw"


def test_grouped_folds_need_no_seed_to_be_reproducible():
    """Ordering is by cohort size, so there is nothing to randomise and no seed to disagree on."""
    observations = _observations(n=80)
    assert np.array_equal(
        make_folds(observations, 4, "grouped", seed=1),
        make_folds(observations, 4, "grouped", seed=999),
    )


def test_grouped_folds_balance_by_observation_not_by_study_count():
    """Studies are very uneven, so round-robin over cohorts would give incomparable folds."""
    observations = _observations(n=90)
    folds = make_folds(observations, 3, "grouped")
    sizes = np.array([int((folds == f).sum()) for f in sorted(set(folds))])
    assert sizes.max() <= 2 * sizes.min(), f"folds are badly unbalanced: {sizes}"


def test_grouped_folds_refuse_when_there_are_fewer_studies_than_folds():
    """Whole studies cannot be spread across more folds than there are studies."""
    observations = _observations(n=60)  # the fixture has 4 cohorts
    with pytest.raises(ValueError, match="cohorts cannot fill"):
        make_folds(observations, 5, "grouped")


def test_a_single_site_study_is_not_counted_as_split():
    """It cannot be split and carries no within-study contrast either way, so it is not evidence."""
    cohort_id = ["solo", "pair", "pair"]
    split, multi_site = studies_split_across_folds(cohort_id, np.array([0, 0, 1]))
    assert (split, multi_site) == (1, 1)


def test_split_counts_are_reported_in_the_summary():
    result = CrossValidation("random", [_fold()], studies_split=135, multi_site_studies=143)
    text = str(result)
    assert "135/143" in text
    assert "94%" in text


def test_a_mostly_shattered_split_says_the_cohort_term_is_unidentifiable():
    """Past roughly half, the metrics describe a differently-identified model (#127)."""
    shattered = CrossValidation("random", [_fold()], studies_split=135, multi_site_studies=143)
    intact = CrossValidation("grouped", [_fold()], studies_split=0, multi_site_studies=143)
    assert "#127" in str(shattered)
    assert "#127" not in str(intact)


def test_uncomputed_split_counts_are_absent_rather_than_zero():
    """A zero here is a measurement and has to be earned; `None` must not print as 'none split'."""
    result = CrossValidation("spatial", [_fold()])
    assert result.studies_split is None
    assert "studies split" not in str(result)


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
