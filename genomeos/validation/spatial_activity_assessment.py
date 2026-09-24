"""Assess synthetic spatial-activity predictions (design §§7–8; issue #384).

Count-distribution diagnostics are the primary estimand. Known synthetic component truth is a
separate diagnostic: it can expose an identification failure, but cannot rescue a candidate that
predicts held-out counts poorly. Null false support is computed from posterior activity draws,
never from a post-hoc classification of observed zeros.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from genomeos.validation.benchmark import validate_predictive_diagnostics
from genomeos.validation.predictive import predictive_diagnostics
from genomeos.validation.spatial_activity_preflight import ActivityCountPredictive

SEED = 42
NULL_ACTIVITY_THRESHOLD = 0.9


@dataclass(frozen=True)
class ActivityStratumMetrics:
    """Required count-predictive metrics for one explicit row stratum."""

    n_observations: int
    mean_log_score: float | None
    mae: float | None
    coverage_50: float | None
    coverage_80: float | None
    coverage_95: float | None


@dataclass(frozen=True)
class ActivityTruthRecovery:
    """Posterior-mean recovery and component dependence under known synthetic truth."""

    marginal_mean_mae: float
    conditional_mean_mae: float
    activity_probability_mae: float
    mean_absolute_component_correlation: float | None
    correlated_observation_count: int


@dataclass(frozen=True)
class ActivityNullFalseSupport:
    """Posterior inactive mass when the data-generating truth is exactly q=1."""

    mean_inactive_probability: float
    fraction_draws_below_threshold: float
    activity_threshold: float


@dataclass(frozen=True)
class ActivityPredictionAssessment:
    """One fold/model assessment with marginal scoring kept separate from components."""

    diagnostics: pd.DataFrame = field(repr=False)
    all_rows: ActivityStratumMetrics
    zero_rows: ActivityStratumMetrics
    positive_rows: ActivityStratumMetrics
    recovery: ActivityTruthRecovery
    null_false_support: ActivityNullFalseSupport | None


def _truth_vector(
    value: object,
    name: str,
    *,
    expected: int,
    strict: bool,
) -> np.ndarray:
    try:
        raw = np.asarray(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be a numeric probability vector") from error
    if (
        raw.shape != (expected,)
        or not np.issubdtype(raw.dtype, np.number)
        or np.issubdtype(raw.dtype, np.bool_)
        or np.issubdtype(raw.dtype, np.complexfloating)
    ):
        raise ValueError(f"{name} must match the predictive observation dimension")
    result = raw.astype(np.float64)
    if not np.all(np.isfinite(result)):
        raise ValueError(f"{name} must contain finite probabilities")
    lower = result > 0.0 if strict else result >= 0.0
    upper = result < 1.0 if strict else result <= 1.0
    if not np.all(lower & upper):
        qualifier = "strictly " if strict else ""
        raise ValueError(f"{name} must be {qualifier}between zero and one")
    return result


def _stratum(diagnostics: pd.DataFrame, selected: np.ndarray) -> ActivityStratumMetrics:
    count = int(np.count_nonzero(selected))
    if count == 0:
        return ActivityStratumMetrics(
            n_observations=0,
            mean_log_score=None,
            mae=None,
            coverage_50=None,
            coverage_80=None,
            coverage_95=None,
        )
    rows = diagnostics.loc[selected]
    return ActivityStratumMetrics(
        n_observations=count,
        mean_log_score=float(rows["log_score"].mean()),
        mae=float(rows["absolute_error"].mean()),
        coverage_50=float(rows["coverage_50"].mean()),
        coverage_80=float(rows["coverage_80"].mean()),
        coverage_95=float(rows["coverage_95"].mean()),
    )


def assess_spatial_activity_prediction(
    predictive: ActivityCountPredictive,
    *,
    ac: object,
    an: object,
    marginal_mean_truth: object,
    conditional_mean_truth: object,
    activity_probability_truth: object,
    seed: int = SEED,
) -> ActivityPredictionAssessment:
    """Score one synthetic holdout and report component diagnostics without interpretation."""
    if not isinstance(predictive, ActivityCountPredictive):
        raise ValueError("predictive must be ActivityCountPredictive")
    alternate, total = predictive.validated_counts(ac, an)
    marginal_truth = _truth_vector(
        marginal_mean_truth,
        "marginal_mean_truth",
        expected=predictive.n_observations,
        strict=False,
    )
    conditional_truth = _truth_vector(
        conditional_mean_truth,
        "conditional_mean_truth",
        expected=predictive.n_observations,
        strict=True,
    )
    activity_truth = _truth_vector(
        activity_probability_truth,
        "activity_probability_truth",
        expected=predictive.n_observations,
        strict=False,
    )
    if not np.allclose(
        marginal_truth,
        conditional_truth * activity_truth,
        rtol=1e-12,
        atol=1e-15,
    ):
        raise ValueError(
            "marginal_mean_truth must equal conditional_mean_truth times "
            "activity_probability_truth"
        )

    diagnostics = validate_predictive_diagnostics(
        predictive_diagnostics(
            predictive,
            alternate,
            total,
            seed=seed,
        )
    ).reset_index(drop=True)
    posterior_conditional = np.mean(predictive.conditional_mean_draws, axis=0)
    posterior_activity = np.mean(predictive.activity_probability_draws, axis=0)
    posterior_marginal = np.mean(predictive.mean_draws, axis=0)
    component = predictive.component_diagnostics()
    correlations = np.asarray(
        [
            abs(value)
            for value in component.component_correlation
            if value is not None
        ],
        dtype=np.float64,
    )
    recovery = ActivityTruthRecovery(
        marginal_mean_mae=float(np.mean(np.abs(posterior_marginal - marginal_truth))),
        conditional_mean_mae=float(
            np.mean(np.abs(posterior_conditional - conditional_truth))
        ),
        activity_probability_mae=float(
            np.mean(np.abs(posterior_activity - activity_truth))
        ),
        mean_absolute_component_correlation=(
            float(np.mean(correlations)) if len(correlations) else None
        ),
        correlated_observation_count=len(correlations),
    )
    null_support = None
    if np.array_equal(activity_truth, np.ones_like(activity_truth)):
        null_support = ActivityNullFalseSupport(
            mean_inactive_probability=float(
                np.mean(1.0 - predictive.activity_probability_draws)
            ),
            fraction_draws_below_threshold=float(
                np.mean(
                    predictive.activity_probability_draws < NULL_ACTIVITY_THRESHOLD
                )
            ),
            activity_threshold=NULL_ACTIVITY_THRESHOLD,
        )
    zero = alternate == 0
    return ActivityPredictionAssessment(
        diagnostics=diagnostics.copy(deep=True),
        all_rows=_stratum(diagnostics, np.ones(len(alternate), dtype=bool)),
        zero_rows=_stratum(diagnostics, zero),
        positive_rows=_stratum(diagnostics, ~zero),
        recovery=recovery,
        null_false_support=null_support,
    )
