"""Aggregate and gate the spatial activity simulation campaign (design §8; #384).

The decision uses only paired outer holdouts. Inner tasks remain mandatory completion evidence for
the frozen nested protocol. Thresholds in this module are fixed before campaign execution; a
failed or incomplete task, uncalibrated interval, null false gate, or missing paired improvement
keeps the real HbS fit ineligible.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from math import isfinite, sqrt

import numpy as np
from scipy.stats import t

from genomeos.validation.spatial_activity_assessment import (
    validate_activity_prediction_assessment,
)
from genomeos.validation.spatial_activity_plan import SpatialActivityPreflightPlan
from genomeos.validation.spatial_activity_simulation import SpatialActivityScenario
from genomeos.validation.spatial_activity_tasks import (
    SpatialActivityTaskResult,
    plan_spatial_activity_tasks,
)

NULL_LOG_SCORE_NONINFERIORITY_MARGIN = -0.01
MAX_NULL_RELATIVE_MAE_DEGRADATION = 0.05
MAX_NULL_MEAN_INACTIVE_PROBABILITY = 0.10
MAX_NULL_FRACTION_BELOW_ACTIVITY_THRESHOLD = 0.25
LOCALIZED_MIN_RELATIVE_MAE_IMPROVEMENT = 0.05
SENSITIVITY_MAX_RELATIVE_MAE_DEGRADATION = 0.05
COVERAGE_TOLERANCE = 0.03


@dataclass(frozen=True)
class SpatialActivityConditionComparison:
    """Paired outer-fold comparison for one seed-collapsed synthetic condition."""

    condition_id: str
    truth: str
    denominator_multiplier: float
    cohort_sd: float
    paired_outer_fold_count: int
    paired_zero_stratum_count: int
    paired_positive_stratum_count: int
    complete: bool
    mean_log_score_delta: float | None
    log_score_delta_ci95_low: float | None
    log_score_delta_ci95_high: float | None
    relative_mae_improvement: float | None
    relative_marginal_recovery_improvement: float | None
    mean_zero_log_score_delta: float | None
    mean_positive_log_score_delta: float | None
    candidate_coverage_50: float | None
    candidate_coverage_80: float | None
    candidate_coverage_95: float | None
    candidate_mean_absolute_component_correlation: float | None
    candidate_component_correlation_fold_count: int
    candidate_component_correlation_observation_count: int
    candidate_mean_inactive_probability: float | None
    candidate_fraction_draws_below_activity_threshold: float | None


@dataclass(frozen=True)
class SpatialActivityCampaignDecision:
    """Whether the registered simulation evidence permits a real HbS fit."""

    eligible_for_real_fit: bool
    refusal_reasons: tuple[str, ...]


@dataclass(frozen=True)
class SpatialActivityCampaignResult:
    """Complete terminal task ledger, paired summaries, and fail-closed decision."""

    task_count: int
    completed_task_count: int
    retried_task_count: int
    comparisons: tuple[SpatialActivityConditionComparison, ...]
    decision: SpatialActivityCampaignDecision
    results: tuple[SpatialActivityTaskResult, ...] = field(repr=False)


def _condition(scenario: SpatialActivityScenario) -> tuple[str, float, float]:
    return (
        scenario.truth,
        scenario.denominator_multiplier,
        scenario.cohort_sd,
    )


def _condition_id(key: tuple[str, float, float]) -> str:
    truth, denominator, cohort_sd = key
    return f"{truth}|denominator={denominator:g}|cohort_sd={cohort_sd:g}"


def _mean(values: Sequence[float]) -> float | None:
    if not values:
        return None
    array = np.asarray(values, dtype=np.float64)
    if not np.all(np.isfinite(array)):
        return None
    return float(np.mean(array))


def _ci95(values: Sequence[float]) -> tuple[float | None, float | None]:
    if len(values) < 2:
        return None, None
    array = np.asarray(values, dtype=np.float64)
    if not np.all(np.isfinite(array)):
        return None, None
    mean = float(np.mean(array))
    standard_error = float(np.std(array, ddof=1) / sqrt(len(array)))
    half_width = float(t.ppf(0.975, len(array) - 1) * standard_error)
    return mean - half_width, mean + half_width


def _relative_improvement(baseline: float, candidate: float) -> float | None:
    if not isfinite(baseline) or not isfinite(candidate) or baseline <= 0.0:
        return None
    return (baseline - candidate) / baseline


def _incomplete_comparison(
    key: tuple[str, float, float],
    pair_count: int,
) -> SpatialActivityConditionComparison:
    return SpatialActivityConditionComparison(
        condition_id=_condition_id(key),
        truth=key[0],
        denominator_multiplier=key[1],
        cohort_sd=key[2],
        paired_outer_fold_count=pair_count,
        paired_zero_stratum_count=0,
        paired_positive_stratum_count=0,
        complete=False,
        mean_log_score_delta=None,
        log_score_delta_ci95_low=None,
        log_score_delta_ci95_high=None,
        relative_mae_improvement=None,
        relative_marginal_recovery_improvement=None,
        mean_zero_log_score_delta=None,
        mean_positive_log_score_delta=None,
        candidate_coverage_50=None,
        candidate_coverage_80=None,
        candidate_coverage_95=None,
        candidate_mean_absolute_component_correlation=None,
        candidate_component_correlation_fold_count=0,
        candidate_component_correlation_observation_count=0,
        candidate_mean_inactive_probability=None,
        candidate_fraction_draws_below_activity_threshold=None,
    )


def _comparison(
    key: tuple[str, float, float],
    scenarios: tuple[SpatialActivityScenario, ...],
    plan: SpatialActivityPreflightPlan,
    by_identity: dict[tuple[str, str, str], SpatialActivityTaskResult],
) -> SpatialActivityConditionComparison:
    pairs = []
    for scenario in scenarios:
        for split in plan.outer_splits:
            ordinary = by_identity[(scenario.scenario_id, "ordinary", split.split_id)]
            candidate = by_identity[
                (scenario.scenario_id, "spatial_activity", split.split_id)
            ]
            pairs.append((ordinary, candidate))
    if any(
        ordinary.result.status.status != "completed"
        or candidate.result.status.status != "completed"
        or ordinary.result.assessment is None
        or candidate.result.assessment is None
        for ordinary, candidate in pairs
    ):
        return _incomplete_comparison(key, len(pairs))

    log_delta = []
    mae_improvement = []
    marginal_improvement = []
    zero_delta = []
    positive_delta = []
    coverage_50 = []
    coverage_80 = []
    coverage_95 = []
    component_correlation = []
    component_correlation_observations = 0
    inactive_probability = []
    below_threshold = []
    for ordinary_record, candidate_record in pairs:
        ordinary = ordinary_record.result.assessment
        candidate = candidate_record.result.assessment
        log_delta.append(
            candidate.all_rows.mean_log_score - ordinary.all_rows.mean_log_score
        )
        relative = _relative_improvement(ordinary.all_rows.mae, candidate.all_rows.mae)
        marginal_relative = _relative_improvement(
            ordinary.recovery.marginal_mean_mae,
            candidate.recovery.marginal_mean_mae,
        )
        if relative is not None:
            mae_improvement.append(relative)
        if marginal_relative is not None:
            marginal_improvement.append(marginal_relative)
        if (
            ordinary.zero_rows.mean_log_score is not None
            and candidate.zero_rows.mean_log_score is not None
        ):
            zero_delta.append(
                candidate.zero_rows.mean_log_score
                - ordinary.zero_rows.mean_log_score
            )
        if (
            ordinary.positive_rows.mean_log_score is not None
            and candidate.positive_rows.mean_log_score is not None
        ):
            positive_delta.append(
                candidate.positive_rows.mean_log_score
                - ordinary.positive_rows.mean_log_score
            )
        coverage_50.append(candidate.all_rows.coverage_50)
        coverage_80.append(candidate.all_rows.coverage_80)
        coverage_95.append(candidate.all_rows.coverage_95)
        correlation = candidate.recovery.mean_absolute_component_correlation
        if correlation is not None:
            component_correlation.append(correlation)
            component_correlation_observations += (
                candidate.recovery.correlated_observation_count
            )
        null_support = candidate.null_false_support
        if null_support is not None:
            inactive_probability.append(null_support.mean_inactive_probability)
            below_threshold.append(null_support.fraction_draws_below_threshold)

    ci_low, ci_high = _ci95(log_delta)
    return SpatialActivityConditionComparison(
        condition_id=_condition_id(key),
        truth=key[0],
        denominator_multiplier=key[1],
        cohort_sd=key[2],
        paired_outer_fold_count=len(pairs),
        paired_zero_stratum_count=len(zero_delta),
        paired_positive_stratum_count=len(positive_delta),
        complete=True,
        mean_log_score_delta=_mean(log_delta),
        log_score_delta_ci95_low=ci_low,
        log_score_delta_ci95_high=ci_high,
        relative_mae_improvement=_mean(mae_improvement),
        relative_marginal_recovery_improvement=_mean(marginal_improvement),
        mean_zero_log_score_delta=_mean(zero_delta),
        mean_positive_log_score_delta=_mean(positive_delta),
        candidate_coverage_50=_mean(coverage_50),
        candidate_coverage_80=_mean(coverage_80),
        candidate_coverage_95=_mean(coverage_95),
        candidate_mean_absolute_component_correlation=_mean(component_correlation),
        candidate_component_correlation_fold_count=len(component_correlation),
        candidate_component_correlation_observation_count=(
            component_correlation_observations
        ),
        candidate_mean_inactive_probability=_mean(inactive_probability),
        candidate_fraction_draws_below_activity_threshold=_mean(below_threshold),
    )


def _decision(
    comparisons: tuple[SpatialActivityConditionComparison, ...],
    results: tuple[SpatialActivityTaskResult, ...],
) -> SpatialActivityCampaignDecision:
    reasons: list[str] = []
    terminal_failures = sum(record.result.status.status != "completed" for record in results)
    if terminal_failures:
        reasons.append(f"{terminal_failures} terminal task results are not completed")
    for comparison in comparisons:
        if not comparison.complete:
            reasons.append(f"{comparison.condition_id}: paired outer comparison is incomplete")
            continue
        if comparison.paired_zero_stratum_count == 0:
            reasons.append(
                f"{comparison.condition_id}: zero-count stratum has no paired evidence"
            )
        if comparison.paired_positive_stratum_count == 0:
            reasons.append(
                f"{comparison.condition_id}: positive-count stratum has no paired evidence"
            )
        for metric_name, nominal in (
            ("candidate_coverage_50", 0.50),
            ("candidate_coverage_80", 0.80),
            ("candidate_coverage_95", 0.95),
        ):
            observed = getattr(comparison, metric_name)
            if observed is None or abs(observed - nominal) > COVERAGE_TOLERANCE:
                reasons.append(
                    f"{comparison.condition_id}: {metric_name} is outside the "
                    f"{COVERAGE_TOLERANCE:.0%} tolerance"
                )
        if comparison.truth == "null":
            if (
                comparison.log_score_delta_ci95_low is None
                or comparison.log_score_delta_ci95_low
                < NULL_LOG_SCORE_NONINFERIORITY_MARGIN
            ):
                reasons.append(
                    f"{comparison.condition_id}: null log-score noninferiority failed"
                )
            if (
                comparison.relative_mae_improvement is None
                or comparison.relative_mae_improvement
                < -MAX_NULL_RELATIVE_MAE_DEGRADATION
            ):
                reasons.append(f"{comparison.condition_id}: null MAE noninferiority failed")
            if (
                comparison.relative_marginal_recovery_improvement is None
                or comparison.relative_marginal_recovery_improvement
                < -MAX_NULL_RELATIVE_MAE_DEGRADATION
            ):
                reasons.append(
                    f"{comparison.condition_id}: null marginal recovery degraded"
                )
            if (
                comparison.candidate_mean_inactive_probability is None
                or comparison.candidate_mean_inactive_probability
                > MAX_NULL_MEAN_INACTIVE_PROBABILITY
                or comparison.candidate_fraction_draws_below_activity_threshold is None
                or comparison.candidate_fraction_draws_below_activity_threshold
                > MAX_NULL_FRACTION_BELOW_ACTIVITY_THRESHOLD
            ):
                reasons.append(
                    f"{comparison.condition_id}: false inactive support exceeds its null gate"
                )
            continue

        primary = (
            comparison.denominator_multiplier == 1.0
            and comparison.cohort_sd == 0.0
        )
        if primary:
            if (
                comparison.log_score_delta_ci95_low is None
                or comparison.log_score_delta_ci95_low <= 0.0
            ):
                reasons.append(
                    f"{comparison.condition_id}: localized log-score interval does not exclude zero"
                )
            if (
                comparison.relative_mae_improvement is None
                or comparison.relative_mae_improvement
                < LOCALIZED_MIN_RELATIVE_MAE_IMPROVEMENT
            ):
                reasons.append(
                    f"{comparison.condition_id}: localized MAE improvement is below 5%"
                )
            if (
                comparison.relative_marginal_recovery_improvement is None
                or comparison.relative_marginal_recovery_improvement < 0.0
            ):
                reasons.append(
                    f"{comparison.condition_id}: marginal truth recovery did not improve"
                )
        else:
            if (
                comparison.mean_log_score_delta is None
                or comparison.mean_log_score_delta <= 0.0
            ):
                reasons.append(
                    f"{comparison.condition_id}: sensitivity mean log-score did not improve"
                )
            if (
                comparison.relative_mae_improvement is None
                or comparison.relative_mae_improvement
                < -SENSITIVITY_MAX_RELATIVE_MAE_DEGRADATION
            ):
                reasons.append(
                    f"{comparison.condition_id}: sensitivity MAE degraded by more than 5%"
                )
    return SpatialActivityCampaignDecision(
        eligible_for_real_fit=not reasons,
        refusal_reasons=tuple(reasons),
    )


def finalize_spatial_activity_campaign(
    plan: SpatialActivityPreflightPlan,
    results: Sequence[SpatialActivityTaskResult],
) -> SpatialActivityCampaignResult:
    """Validate the complete task ledger, aggregate paired outer evidence, and gate it."""
    if not isinstance(plan, SpatialActivityPreflightPlan):
        raise ValueError("plan must be SpatialActivityPreflightPlan")
    if isinstance(results, (str, bytes)) or not isinstance(results, Sequence):
        raise TypeError("results must be a sequence of SpatialActivityTaskResult records")
    records = tuple(results)
    if any(not isinstance(record, SpatialActivityTaskResult) for record in records):
        raise ValueError("results must contain SpatialActivityTaskResult records")
    ids = [record.task.task_id for record in records]
    if len(set(ids)) != len(ids):
        raise ValueError("results contain duplicate task identities")
    manifest = plan_spatial_activity_tasks(plan)
    expected = {task.task_id for task in manifest}
    submitted = set(ids)
    missing = sorted(expected - submitted)
    unknown = sorted(submitted - expected)
    if missing:
        raise ValueError(f"results are missing {len(missing)} planned tasks")
    if unknown:
        raise ValueError(f"results contain {len(unknown)} unknown tasks")
    by_task = {record.task.task_id: record for record in records}
    ordered = tuple(by_task[task.task_id] for task in manifest)
    outer_splits = {split.split_id: split for split in plan.outer_splits}
    inner_splits = {
        (inner.outer_split_id, split.split_id): split
        for inner in plan.inner_plans
        for split in inner.splits
    }
    for record in ordered:
        task = record.task
        split = (
            outer_splits[task.split_id]
            if task.split_role == "outer"
            else inner_splits[(task.outer_split_id, task.split_id)]
        )
        if record.result.status.expected_test_ids != split.test_ids:
            raise ValueError(
                f"task {task.task_id} result has held-out identities that contradict its split"
            )
        if record.result.status.status == "completed":
            try:
                diagnostics = validate_activity_prediction_assessment(
                    record.result.assessment
                )
            except (TypeError, ValueError) as error:
                raise ValueError(
                    f"task {task.task_id} completed assessment has invalid retained evidence"
                ) from error
            if len(diagnostics) != len(split.test_ids):
                raise ValueError(
                    f"task {task.task_id} diagnostic rows contradict its held-out identities"
                )
    by_identity = {
        (record.task.scenario_id, record.task.mode, record.task.split_id): record
        for record in ordered
        if record.task.split_role == "outer"
    }
    grouped: dict[tuple[str, float, float], list[SpatialActivityScenario]] = {}
    for scenario in plan.scenarios:
        grouped.setdefault(_condition(scenario), []).append(scenario)
    comparisons = tuple(
        _comparison(key, tuple(grouped[key]), plan, by_identity)
        for key in sorted(grouped)
    )
    return SpatialActivityCampaignResult(
        task_count=len(ordered),
        completed_task_count=sum(
            record.result.status.status == "completed" for record in ordered
        ),
        retried_task_count=sum(len(record.result.attempts) == 2 for record in ordered),
        comparisons=comparisons,
        decision=_decision(comparisons, ordered),
        results=ordered,
    )
