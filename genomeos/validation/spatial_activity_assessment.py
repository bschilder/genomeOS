"""Assess synthetic spatial-activity predictions (design §§7–8; issue #384).

Count-distribution diagnostics are the primary estimand. Known synthetic component truth is a
separate diagnostic: it can expose an identification failure, but cannot rescue a candidate that
predicts held-out counts poorly. Null false support is computed from posterior activity draws,
never from a post-hoc classification of observed zeros.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
from numbers import Integral

import numpy as np
import pandas as pd

from genomeos.validation.benchmark import validate_predictive_diagnostics
from genomeos.validation.predictive import predictive_diagnostics
from genomeos.validation.spatial_activity_preflight import ActivityCountPredictive

SEED = 42
NULL_ACTIVITY_THRESHOLD = 0.9
OBSERVED_COUNT_COLUMNS = ("observed_ac", "observed_an")


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


def _same_number(left: float | None, right: float | None) -> bool:
    if left is None or right is None:
        return left is right
    if left == right:
        return True
    return isfinite(left) and isfinite(right) and bool(
        np.isclose(left, right, rtol=1e-12, atol=1e-15)
    )


def _same_stratum(
    submitted: ActivityStratumMetrics,
    expected: ActivityStratumMetrics,
) -> bool:
    return submitted.n_observations == expected.n_observations and all(
        _same_number(getattr(submitted, name), getattr(expected, name))
        for name in (
            "mean_log_score",
            "mae",
            "coverage_50",
            "coverage_80",
            "coverage_95",
        )
    )


def _retained_counts(frame: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    missing = sorted(set(OBSERVED_COUNT_COLUMNS) - set(frame.columns))
    if missing:
        raise ValueError(f"assessment diagnostics are missing observed counts: {missing}")
    values = []
    for column in OBSERVED_COUNT_COLUMNS:
        raw = tuple(frame[column].array)
        if any(
            isinstance(item, (bool, np.bool_))
            or not isinstance(item, Integral)
            or int(item) < 0
            for item in raw
        ):
            raise ValueError(f"assessment diagnostic {column} must contain nonnegative integers")
        values.append(np.asarray(raw, dtype=np.int64))
    alternate, total = values
    if np.any(total <= 0) or np.any(alternate > total):
        raise ValueError("assessment observed counts must satisfy 0 <= AC <= AN with AN > 0")
    return alternate, total


def validate_activity_prediction_assessment(
    assessment: ActivityPredictionAssessment,
) -> pd.DataFrame:
    """Return a validated diagnostic copy whose retained counts reproduce every stratum."""
    if not isinstance(assessment, ActivityPredictionAssessment):
        raise TypeError("assessment must be ActivityPredictionAssessment")
    frame = assessment.diagnostics
    if not isinstance(frame, pd.DataFrame) or frame.columns.duplicated().any():
        raise ValueError("assessment diagnostics must be a pandas DataFrame without duplicates")
    alternate, total = _retained_counts(frame)
    core = validate_predictive_diagnostics(frame)
    if len(core) != len(alternate):
        raise ValueError("assessment observed counts must align with predictive diagnostics")
    expected = (
        _stratum(core, np.ones(len(core), dtype=bool)),
        _stratum(core, alternate == 0),
        _stratum(core, alternate > 0),
    )
    submitted = (assessment.all_rows, assessment.zero_rows, assessment.positive_rows)
    if any(not _same_stratum(left, right) for left, right in zip(submitted, expected, strict=True)):
        raise ValueError("assessment strata do not reproduce retained observed-count diagnostics")
    recovery = assessment.recovery
    if not isinstance(recovery, ActivityTruthRecovery):
        raise ValueError("assessment recovery has the wrong type")
    recovery_values = (
        recovery.marginal_mean_mae,
        recovery.conditional_mean_mae,
        recovery.activity_probability_mae,
    )
    if any(not isfinite(value) or value < 0.0 for value in recovery_values):
        raise ValueError("assessment recovery errors must be finite and nonnegative")
    correlation = recovery.mean_absolute_component_correlation
    if correlation is not None and (not isfinite(correlation) or not 0.0 <= correlation <= 1.0):
        raise ValueError("assessment component correlation must be between zero and one")
    if not 0 <= recovery.correlated_observation_count <= len(core):
        raise ValueError("assessment correlated observation count is outside the retained rows")
    false_support = assessment.null_false_support
    if false_support is not None:
        values = (
            false_support.mean_inactive_probability,
            false_support.fraction_draws_below_threshold,
        )
        if any(not isfinite(value) or not 0.0 <= value <= 1.0 for value in values):
            raise ValueError("assessment null false-support values must be probabilities")
        if false_support.activity_threshold != NULL_ACTIVITY_THRESHOLD:
            raise ValueError("assessment null activity threshold differs from the frozen gate")
    result = pd.concat(
        [
            pd.DataFrame({"observed_ac": alternate, "observed_an": total}),
            core.reset_index(drop=True),
        ],
        axis=1,
    )
    return result


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
    diagnostics.insert(0, "observed_an", total)
    diagnostics.insert(0, "observed_ac", alternate)
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
    assessment = ActivityPredictionAssessment(
        diagnostics=diagnostics.copy(deep=True),
        all_rows=_stratum(diagnostics, np.ones(len(alternate), dtype=bool)),
        zero_rows=_stratum(diagnostics, zero),
        positive_rows=_stratum(diagnostics, ~zero),
        recovery=recovery,
        null_false_support=null_support,
    )
    validate_activity_prediction_assessment(assessment)
    return assessment
