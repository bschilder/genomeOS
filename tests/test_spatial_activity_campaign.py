"""Campaign aggregation and preregistered decision-gate tests (#384)."""

from __future__ import annotations

from dataclasses import replace

import pandas as pd
import pytest

from genomeos.surfaces.convergence import SamplerDiagnostics
from genomeos.surfaces.spatial_activity_fit import SpatialActivitySamplerConfig
from genomeos.surfaces.spatial_activity_model import SpatialActivityModelConfig
from genomeos.validation.benchmark import BenchmarkFoldStatus
from genomeos.validation.spatial_activity_assessment import (
    ActivityNullFalseSupport,
    ActivityPredictionAssessment,
    ActivityStratumMetrics,
    ActivityTruthRecovery,
)
from genomeos.validation.spatial_activity_plan import SpatialActivityPreflightPlan
from genomeos.validation.spatial_activity_runner import (
    SpatialActivityFitAttempt,
    SpatialActivityFoldResult,
)
from genomeos.validation.spatial_activity_simulation import (
    default_spatial_activity_scenarios,
)
from genomeos.validation.spatial_activity_tasks import (
    SpatialActivityTaskResult,
    plan_spatial_activity_tasks,
)
from genomeos.validation.splits import BenchmarkSplit


def _plan() -> SpatialActivityPreflightPlan:
    splits = tuple(
        BenchmarkSplit(
            split_id=f"outer-{index}",
            block_id=f"block-{index}",
            train_ids=(f"train-{index}",),
            test_ids=tuple(f"test-{index}-{row:02d}" for row in range(20)),
            excluded_ids=(),
            exclusion_reasons=(),
            min_edge_separation_km=400.0,
            input_fingerprint="a" * 64,
            buffer_km=300.0,
            data_version="campaign-test-v1",
        )
        for index in range(2)
    )
    model = SpatialActivityModelConfig(
        hsgp_m=(2, 2, 2),
        hsgp_c=1.5,
        lengthscale_mu=-2.0,
        lengthscale_sigma=0.4,
        conditional_intercept_mu=-3.5,
        conditional_intercept_sigma=1.5,
        conditional_amplitude_sigma=1.0,
        activity_intercept_mu=2.5,
        activity_intercept_sigma=1.0,
        activity_amplitude_sigma=1.0,
        concentration_sigma=100.0,
        cohort_sd_sigma=0.5,
    )
    return SpatialActivityPreflightPlan(
        baseline_plan=object(),
        outer_splits=splits,
        inner_plans=(),
        scenarios=default_spatial_activity_scenarios(),
        modes=("ordinary", "spatial_activity"),
        model_config=model,
        sampler_config=SpatialActivitySamplerConfig(
            draws=3,
            tune=4,
            chains=4,
            nuts_sampler="pymc",
        ),
        dependencies=(),
    )


def _stratum(frame: pd.DataFrame) -> ActivityStratumMetrics:
    if frame.empty:
        return ActivityStratumMetrics(0, None, None, None, None, None)
    return ActivityStratumMetrics(
        n_observations=len(frame),
        mean_log_score=float(frame["log_score"].mean()),
        mae=float(frame["absolute_error"].mean()),
        coverage_50=float(frame["coverage_50"].mean()),
        coverage_80=float(frame["coverage_80"].mean()),
        coverage_95=float(frame["coverage_95"].mean()),
    )


def _assessment(
    scenario,
    mode: str,
    *,
    zero_count: int = 12,
) -> ActivityPredictionAssessment:
    ordinary = mode == "ordinary"
    base_log_score = -1.0
    base_mae = 0.10
    if ordinary:
        log_score = base_log_score
        mae = base_mae
        marginal_recovery = 0.10
    elif scenario.truth == "null":
        log_score = -1.005
        mae = 0.104
        marginal_recovery = 0.104
    elif scenario.truth in {"localized_weak", "localized_strong"} and (
        scenario.denominator_multiplier == 1.0 and scenario.cohort_sd == 0.0
    ):
        log_score = -0.90
        mae = 0.09
        marginal_recovery = 0.09
    else:
        log_score = -0.95
        mae = 0.10
        marginal_recovery = 0.10
    null_support = None
    if scenario.truth == "null":
        null_support = ActivityNullFalseSupport(
            mean_inactive_probability=0.0 if ordinary else 0.05,
            fraction_draws_below_threshold=0.0 if ordinary else 0.10,
            activity_threshold=0.9,
        )
    positive_count = 20 - zero_count
    zero_log_score = log_score - 0.01 if zero_count else log_score
    positive_log_score = (
        log_score + 0.01 * zero_count / positive_count
        if zero_count and positive_count
        else log_score
    )
    diagnostics = pd.DataFrame(
        {
            "observed_ac": [0] * zero_count + [1] * positive_count,
            "observed_an": [20] * 20,
            "log_score": [zero_log_score] * zero_count
            + [positive_log_score] * positive_count,
            "absolute_error": [mae] * 20,
            "squared_error": [mae**2] * 20,
            "coverage_50": [True] * 10 + [False] * 10,
            "interval_width_50": [0.2] * 20,
            "coverage_80": [True] * 16 + [False] * 4,
            "interval_width_80": [0.4] * 20,
            "coverage_95": [True] * 19 + [False],
            "interval_width_95": [0.6] * 20,
            "randomized_pit": [0.5] * 20,
        }
    )
    zeros = diagnostics["observed_ac"] == 0
    return ActivityPredictionAssessment(
        diagnostics=diagnostics,
        all_rows=_stratum(diagnostics),
        zero_rows=_stratum(diagnostics.loc[zeros]),
        positive_rows=_stratum(diagnostics.loc[~zeros]),
        recovery=ActivityTruthRecovery(
            marginal_mean_mae=marginal_recovery,
            conditional_mean_mae=0.10,
            activity_probability_mae=0.10,
            mean_absolute_component_correlation=None if ordinary else 0.85,
            correlated_observation_count=0 if ordinary else 20,
        ),
        null_false_support=null_support,
    )


def _results(plan: SpatialActivityPreflightPlan) -> tuple[SpatialActivityTaskResult, ...]:
    scenario_by_id = {scenario.scenario_id: scenario for scenario in plan.scenarios}
    split_by_id = {split.split_id: split for split in plan.outer_splits}
    diagnostics = SamplerDiagnostics(1.01, "x", 300.0, "x", 300.0, "x", 0)
    records = []
    for task in plan_spatial_activity_tasks(plan):
        scenario = scenario_by_id[task.scenario_id]
        split = split_by_id[task.split_id]
        fold = SpatialActivityFoldResult(
            scenario_id=task.scenario_id,
            mode=task.mode,
            split_role=task.split_role,
            status=BenchmarkFoldStatus(
                split_id=task.split_id,
                status="completed",
                expected_test_ids=split.test_ids,
                failure_reason=None,
            ),
            fit_seed=1,
            predictive_seed=2,
            model_config=plan.model_config,
            attempts=(
                SpatialActivityFitAttempt(
                    attempt=1,
                    draws=3,
                    tune=4,
                    seed=1,
                    status="completed",
                    failure_reason=None,
                    diagnostics=diagnostics,
                ),
            ),
            assessment=_assessment(scenario, task.mode),
            fitted=None,
        )
        records.append(SpatialActivityTaskResult(task=task, result=fold))
    return tuple(records)


def _replace_assessment(record, assessment):
    return SpatialActivityTaskResult(
        task=record.task,
        result=replace(record.result, assessment=assessment),
    )


def test_favorable_complete_campaign_passes_registered_gate() -> None:
    from genomeos.validation.spatial_activity_campaign import (
        finalize_spatial_activity_campaign,
    )

    plan = _plan()
    campaign = finalize_spatial_activity_campaign(plan, _results(plan))

    assert campaign.task_count == 72
    assert campaign.completed_task_count == 72
    assert len(campaign.comparisons) == 6
    assert campaign.decision.eligible_for_real_fit is True
    assert campaign.decision.refusal_reasons == ()
    null = next(item for item in campaign.comparisons if item.truth == "null")
    assert null.paired_outer_fold_count == 6
    assert null.paired_zero_stratum_count == 6
    assert null.paired_positive_stratum_count == 6
    assert null.candidate_component_correlation_fold_count == 6
    assert null.candidate_component_correlation_observation_count == 120
    assert null.mean_log_score_delta == pytest.approx(-0.005)
    assert null.log_score_delta_ci95_low == pytest.approx(-0.005)
    weak = next(item for item in campaign.comparisons if item.truth == "localized_weak")
    assert weak.relative_mae_improvement == pytest.approx(0.10)
    assert weak.log_score_delta_ci95_low > 0.0


def test_finalizer_refuses_missing_or_duplicate_task_results() -> None:
    from genomeos.validation.spatial_activity_campaign import (
        finalize_spatial_activity_campaign,
    )

    plan = _plan()
    results = _results(plan)
    with pytest.raises(ValueError, match="missing"):
        finalize_spatial_activity_campaign(plan, results[:-1])
    with pytest.raises(ValueError, match="duplicate"):
        finalize_spatial_activity_campaign(plan, results + (results[0],))


def test_null_false_gate_support_blocks_real_fit() -> None:
    from genomeos.validation.spatial_activity_campaign import (
        finalize_spatial_activity_campaign,
    )

    plan = _plan()
    modified = []
    for record in _results(plan):
        scenario = next(item for item in plan.scenarios if item.scenario_id == record.task.scenario_id)
        if record.task.mode == "spatial_activity" and scenario.truth == "null":
            assessment = replace(
                record.result.assessment,
                null_false_support=ActivityNullFalseSupport(0.20, 0.50, 0.9),
            )
            record = _replace_assessment(record, assessment)
        modified.append(record)
    campaign = finalize_spatial_activity_campaign(plan, tuple(modified))

    assert campaign.decision.eligible_for_real_fit is False
    assert any("false inactive support" in reason for reason in campaign.decision.refusal_reasons)


def test_localized_log_score_or_coverage_failure_blocks_real_fit() -> None:
    from genomeos.validation.spatial_activity_campaign import (
        finalize_spatial_activity_campaign,
    )

    plan = _plan()
    modified = []
    for record in _results(plan):
        scenario = next(item for item in plan.scenarios if item.scenario_id == record.task.scenario_id)
        if record.task.mode == "spatial_activity" and scenario.truth == "localized_weak":
            diagnostics = record.result.assessment.diagnostics.copy(deep=True)
            diagnostics["log_score"] = -1.10
            diagnostics["coverage_80"] = [True] * 14 + [False] * 6
            zero = diagnostics["observed_ac"] == 0
            assessment = replace(
                record.result.assessment,
                diagnostics=diagnostics,
                all_rows=_stratum(diagnostics),
                zero_rows=_stratum(diagnostics.loc[zero]),
                positive_rows=_stratum(diagnostics.loc[~zero]),
            )
            record = _replace_assessment(record, assessment)
        modified.append(record)
    campaign = finalize_spatial_activity_campaign(plan, tuple(modified))

    assert campaign.decision.eligible_for_real_fit is False
    reasons = "\n".join(campaign.decision.refusal_reasons)
    assert "localized_weak" in reasons
    assert "log-score" in reasons
    assert "coverage" in reasons


def test_terminal_task_failure_is_retained_and_blocks_real_fit() -> None:
    from genomeos.validation.spatial_activity_campaign import (
        finalize_spatial_activity_campaign,
    )

    plan = _plan()
    results = list(_results(plan))
    failed = results[0]
    failed_fold = replace(
        failed.result,
        status=BenchmarkFoldStatus(
            split_id=failed.task.split_id,
            status="failed",
            expected_test_ids=failed.result.status.expected_test_ids,
            failure_reason="sampler did not converge after retry",
        ),
        assessment=None,
    )
    results[0] = SpatialActivityTaskResult(task=failed.task, result=failed_fold)
    campaign = finalize_spatial_activity_campaign(plan, tuple(results))

    assert campaign.completed_task_count == 71
    assert campaign.decision.eligible_for_real_fit is False
    assert any("terminal task" in reason for reason in campaign.decision.refusal_reasons)


def test_finalizer_refuses_result_for_wrong_heldout_observations() -> None:
    from genomeos.validation.spatial_activity_campaign import (
        finalize_spatial_activity_campaign,
    )

    plan = _plan()
    results = list(_results(plan))
    first = results[0]
    results[0] = SpatialActivityTaskResult(
        task=first.task,
        result=replace(
            first.result,
            status=replace(
                first.result.status,
                expected_test_ids=("different-heldout-record",),
            ),
        ),
    )

    with pytest.raises(ValueError, match="held-out identities"):
        finalize_spatial_activity_campaign(plan, tuple(results))


def test_missing_count_stratum_blocks_real_fit_and_reports_denominator() -> None:
    from genomeos.validation.spatial_activity_campaign import (
        finalize_spatial_activity_campaign,
    )

    plan = _plan()
    modified = []
    for record in _results(plan):
        scenario = next(item for item in plan.scenarios if item.scenario_id == record.task.scenario_id)
        if scenario.truth == "localized_weak":
            assessment = _assessment(scenario, record.task.mode, zero_count=0)
            record = _replace_assessment(record, assessment)
        modified.append(record)

    campaign = finalize_spatial_activity_campaign(plan, tuple(modified))
    weak = next(item for item in campaign.comparisons if item.truth == "localized_weak")

    assert weak.paired_zero_stratum_count == 0
    assert campaign.decision.eligible_for_real_fit is False
    assert any("zero-count stratum" in reason for reason in campaign.decision.refusal_reasons)


def test_finalizer_refuses_summary_that_contradicts_retained_rows() -> None:
    from genomeos.validation.spatial_activity_campaign import (
        finalize_spatial_activity_campaign,
    )

    plan = _plan()
    results = list(_results(plan))
    first = results[0]
    invalid_all = replace(
        first.result.assessment.all_rows,
        mae=first.result.assessment.all_rows.mae + 0.01,
    )
    results[0] = _replace_assessment(
        first,
        replace(first.result.assessment, all_rows=invalid_all),
    )

    with pytest.raises(ValueError, match="retained evidence"):
        finalize_spatial_activity_campaign(plan, tuple(results))
