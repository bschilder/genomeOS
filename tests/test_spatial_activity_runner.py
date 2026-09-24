"""Executable fold-runner tests for the simulation-only activity preflight (#384)."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from genomeos.surfaces.config import FitConfig
from genomeos.surfaces.convergence import SamplerDiagnostics
from genomeos.surfaces.spatial_activity_fit import (
    SpatialActivityConvergenceError,
    SpatialActivityFit,
    SpatialActivitySamplerConfig,
)
from genomeos.surfaces.spatial_activity_model import SpatialActivityModelConfig
from genomeos.validation.spatial_activity_plan import plan_spatial_activity_preflight
from genomeos.validation.spatial_activity_simulation import (
    default_spatial_activity_scenarios,
)
from genomeos.validation.spatial_gp_benchmark import plan_single_variant_gp_benchmark


def _inputs():
    rows = []
    for block in range(3):
        for replicate in range(2):
            index = block * 2 + replicate
            rows.append(
                {
                    "variant_id": "chr11-5227002-T-A",
                    "rsid": "rs334",
                    "population_id": f"population-{index}",
                    "lat": float(-40 + block * 40 + replicate),
                    "lon": float(-140 + block * 100 + replicate),
                    "radius_km": 1.0,
                    "ac": index % 2,
                    "an": 80 + 10 * index,
                    "source_record_id": f"record-{index:02d}",
                    "source": "synthetic",
                    "assay": "genotype",
                    "date_lower": 0,
                    "date_upper": 0,
                    "sampling_design": "population_random",
                    "disease_ascertainment_excluded": True,
                    "cohort_id": f"cohort-{block}",
                    "ingest_version": "test",
                }
            )
    observations = pd.DataFrame.from_records(rows)
    assignments = pd.DataFrame(
        {
            "source_record_id": observations["source_record_id"],
            "block_id": [f"block-{index // 2}" for index in range(len(observations))],
            "region_id": [f"region-{index // 2}" for index in range(len(observations))],
            "variant_group": "hbs",
        }
    )
    return observations, assignments


def _plan():
    observations, assignments = _inputs()
    sampler = SpatialActivitySamplerConfig(
        draws=3,
        tune=4,
        chains=4,
        target_accept=0.9,
        nuts_sampler="pymc",
        max_rhat=1.05,
        min_ess=200.0,
        seed=42,
    )
    baseline = plan_single_variant_gp_benchmark(
        observations,
        assignments,
        (),
        buffer_km=300.0,
        data_version="simulation-template-v1",
        config=FitConfig(draws=3, tune=4, chains=4, nuts_sampler="pymc"),
    )
    return plan_spatial_activity_preflight(
        baseline,
        dependencies=(),
        model_config=SpatialActivityModelConfig(
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
        ),
        sampler_config=sampler,
        scenarios=default_spatial_activity_scenarios(),
    )


def _diagnostics(*, converged: bool = True) -> SamplerDiagnostics:
    return SamplerDiagnostics(
        max_rhat=1.01 if converged else 1.2,
        max_rhat_parameter="activity_intercept",
        min_bulk_ess=300.0 if converged else 20.0,
        min_bulk_ess_parameter="activity_intercept",
        min_tail_ess=300.0 if converged else 20.0,
        min_tail_ess_parameter="concentration",
        divergence_count=0 if converged else 2,
    )


def _successful_fit(graph, *, config: SpatialActivitySamplerConfig) -> SpatialActivityFit:
    shape = (config.chains * config.draws, graph.n_predictions)
    activity = 1.0 if graph.mode == "ordinary" else 0.8
    return SpatialActivityFit(
        mode=graph.mode,
        config=config,
        idata=object(),
        conditional_mean_draws=np.full(shape, 0.08),
        activity_probability_draws=np.full(shape, activity),
        concentration_draws=np.full(shape[0], 40.0),
        cohort_sd_draws=(
            np.zeros(shape[0]) if graph.cohort_effect_applied else None
        ),
        diagnostics=_diagnostics(),
    )


def test_fold_runner_connects_simulation_fit_prediction_and_assessment() -> None:
    from genomeos.validation.spatial_activity_runner import (
        evaluate_spatial_activity_fold,
        simulate_spatial_activity_plan_scenario,
    )

    plan = _plan()
    scenario = plan.scenarios[0]
    synthetic = simulate_spatial_activity_plan_scenario(plan, scenario)
    source_before = plan.baseline_plan.observations.copy(deep=True)
    result = evaluate_spatial_activity_fold(
        plan,
        synthetic,
        plan.outer_splits[0],
        mode="spatial_activity",
        split_role="outer",
        fit_function=_successful_fit,
    )

    assert result.status.status == "completed"
    assert result.status.expected_test_ids == plan.outer_splits[0].test_ids
    assert result.scenario_id == scenario.scenario_id
    assert result.mode == "spatial_activity"
    assert result.split_role == "outer"
    assert len(result.attempts) == 1
    assert result.attempts[0].status == "completed"
    assert result.assessment is not None
    assert result.assessment.all_rows.n_observations == len(plan.outer_splits[0].test_ids)
    assert result.fit_seed != result.predictive_seed
    pd.testing.assert_frame_equal(plan.baseline_plan.observations, source_before)


def test_fold_runner_retries_once_with_doubled_budget() -> None:
    from genomeos.validation.spatial_activity_runner import (
        evaluate_spatial_activity_fold,
        simulate_spatial_activity_plan_scenario,
    )

    calls = []

    def flaky_fit(graph, *, config):
        calls.append(config)
        if len(calls) == 1:
            raise SpatialActivityConvergenceError(
                "first budget did not converge",
                diagnostics=_diagnostics(converged=False),
            )
        return _successful_fit(graph, config=config)

    plan = _plan()
    synthetic = simulate_spatial_activity_plan_scenario(plan, plan.scenarios[0])
    result = evaluate_spatial_activity_fold(
        plan,
        synthetic,
        plan.outer_splits[0],
        mode="ordinary",
        split_role="outer",
        fit_function=flaky_fit,
    )

    assert result.status.status == "completed"
    assert [attempt.status for attempt in result.attempts] == [
        "nonconverged",
        "completed",
    ]
    assert [(config.draws, config.tune) for config in calls] == [(3, 4), (6, 8)]
    assert calls[0].seed == calls[1].seed == result.fit_seed


def test_cupy_admission_failure_stops_before_graph_fit(monkeypatch) -> None:
    from genomeos.validation import spatial_activity_runner as module

    called = False

    def refuse(_backend):
        raise RuntimeError("CUDA admission failed")

    def fit(_graph, *, config):
        nonlocal called
        called = True

    monkeypatch.setattr(module, "_require_cdf_backend", refuse)
    plan = _plan()
    synthetic = module.simulate_spatial_activity_plan_scenario(plan, plan.scenarios[0])

    with pytest.raises(RuntimeError, match="CUDA admission failed"):
        module.evaluate_spatial_activity_fold(
            plan,
            synthetic,
            plan.outer_splits[0],
            mode="spatial_activity",
            split_role="outer",
            fit_function=fit,
            cdf_backend="cupy",
        )

    assert called is False


def test_fold_runner_stops_after_second_convergence_failure() -> None:
    from genomeos.validation.spatial_activity_runner import (
        evaluate_spatial_activity_fold,
        simulate_spatial_activity_plan_scenario,
    )

    calls = 0

    def failed_fit(_graph, *, config):
        nonlocal calls
        calls += 1
        raise SpatialActivityConvergenceError(
            f"budget {config.draws} did not converge",
            diagnostics=_diagnostics(converged=False),
        )

    plan = _plan()
    synthetic = simulate_spatial_activity_plan_scenario(plan, plan.scenarios[0])
    result = evaluate_spatial_activity_fold(
        plan,
        synthetic,
        plan.outer_splits[0],
        mode="spatial_activity",
        split_role="outer",
        fit_function=failed_fit,
    )

    assert calls == 2
    assert result.status.status == "failed"
    assert result.assessment is None
    assert [attempt.status for attempt in result.attempts] == [
        "nonconverged",
        "nonconverged",
    ]
    assert "retry" in result.status.failure_reason


def test_nonconvergence_is_the_only_retryable_failure() -> None:
    from genomeos.validation.spatial_activity_runner import (
        evaluate_spatial_activity_fold,
        simulate_spatial_activity_plan_scenario,
    )

    calls = 0

    def broken_fit(_graph, *, config):
        nonlocal calls
        calls += 1
        raise RuntimeError(f"graph failed at seed {config.seed}")

    plan = _plan()
    synthetic = simulate_spatial_activity_plan_scenario(plan, plan.scenarios[0])
    result = evaluate_spatial_activity_fold(
        plan,
        synthetic,
        plan.outer_splits[0],
        mode="ordinary",
        split_role="outer",
        fit_function=broken_fit,
    )

    assert calls == 1
    assert result.status.status == "failed"
    assert len(result.attempts) == 1
    assert result.attempts[0].status == "failed"


def test_empty_training_split_is_infeasible_without_fitting() -> None:
    from genomeos.validation.spatial_activity_runner import (
        evaluate_spatial_activity_fold,
        simulate_spatial_activity_plan_scenario,
    )

    plan = _plan()
    synthetic = simulate_spatial_activity_plan_scenario(plan, plan.scenarios[0])
    split = replace(plan.outer_splits[0], train_ids=())
    called = False

    def fit(_graph, *, config):
        nonlocal called
        called = True

    result = evaluate_spatial_activity_fold(
        plan,
        synthetic,
        split,
        mode="ordinary",
        split_role="outer",
        fit_function=fit,
    )

    assert called is False
    assert result.status.status == "infeasible"
    assert result.attempts == ()
    assert result.assessment is None


def test_seed_schedule_is_stable_across_repeated_evaluation() -> None:
    from genomeos.validation.spatial_activity_runner import (
        evaluate_spatial_activity_fold,
        simulate_spatial_activity_plan_scenario,
    )

    plan = _plan()
    synthetic = simulate_spatial_activity_plan_scenario(plan, plan.scenarios[0])
    results = [
        evaluate_spatial_activity_fold(
            plan,
            synthetic,
            plan.outer_splits[0],
            mode="ordinary",
            split_role="outer",
            fit_function=_successful_fit,
        )
        for _ in range(2)
    ]
    assert results[0].fit_seed == results[1].fit_seed
    assert results[0].predictive_seed == results[1].predictive_seed
    assert results[0].assessment.all_rows == results[1].assessment.all_rows


def test_runner_refuses_synthetic_data_from_another_scenario() -> None:
    from genomeos.validation.spatial_activity_runner import (
        evaluate_spatial_activity_fold,
        simulate_spatial_activity_plan_scenario,
    )

    plan = _plan()
    synthetic = simulate_spatial_activity_plan_scenario(plan, plan.scenarios[1])
    with pytest.raises(ValueError, match="scenario"):
        evaluate_spatial_activity_fold(
            plan,
            synthetic,
            plan.outer_splits[0],
            mode="ordinary",
            split_role="outer",
            scenario=plan.scenarios[0],
            fit_function=_successful_fit,
        )
