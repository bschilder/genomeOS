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
    FoldResult,
    cross_validate,
    make_folds,
)

FAST = FitConfig(draws=300, tune=600, chains=4, approximation="inducing", n_inducing=40)


def _fold(**kwargs) -> FoldResult:
    defaults = dict(
        fold=0, n_train=80, n_test=20, coverage_95=0.95, coverage_50=0.5,
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
    assert "coverage of 95% interval" in text
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
        assert 0.0 <= fold.coverage_95 <= 1.0
        assert 0.0 <= fold.coverage_50 <= 1.0
        assert fold.mae >= 0.0
        assert fold.n_train + fold.n_test == len(observations)
