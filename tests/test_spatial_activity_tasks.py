"""Content-addressed task manifest tests for issue #384."""

from __future__ import annotations

from dataclasses import replace

import pandas as pd
import pytest

from genomeos.surfaces.config import FitConfig
from genomeos.surfaces.spatial_activity_fit import SpatialActivitySamplerConfig
from genomeos.surfaces.spatial_activity_model import SpatialActivityModelConfig
from genomeos.validation.spatial_activity_plan import plan_spatial_activity_preflight
from genomeos.validation.spatial_activity_simulation import (
    default_spatial_activity_scenarios,
)
from genomeos.validation.spatial_gp_benchmark import plan_single_variant_gp_benchmark


def _plan(blocks: int = 5):
    rows = []
    for block in range(blocks):
        for replicate in range(2):
            index = block * 2 + replicate
            rows.append(
                {
                    "variant_id": "chr11-5227002-T-A",
                    "rsid": "rs334",
                    "population_id": f"population-{index}",
                    "lat": float(-50 + block * 25 + replicate),
                    "lon": float(-150 + block * 65 + replicate),
                    "radius_km": 1.0,
                    "ac": index % 3,
                    "an": 100 + index,
                    "source_record_id": f"record-{index:02d}",
                    "source": "synthetic",
                    "assay": "genotype",
                    "date_lower": 0,
                    "date_upper": 0,
                    "sampling_design": "population_random",
                    "disease_ascertainment_excluded": True,
                    "cohort_id": f"cohort-{block:02d}",
                    "ingest_version": "test",
                }
            )
    observations = pd.DataFrame.from_records(rows)
    assignments = pd.DataFrame(
        {
            "source_record_id": observations["source_record_id"],
            "block_id": observations["cohort_id"].str.replace("cohort", "block"),
            "region_id": observations["cohort_id"].str.replace("cohort", "region"),
            "variant_group": "hbs",
        }
    )
    baseline = plan_single_variant_gp_benchmark(
        observations,
        assignments,
        (),
        buffer_km=300.0,
        data_version="task-template-v1",
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
        sampler_config=SpatialActivitySamplerConfig(
            draws=3,
            tune=4,
            chains=4,
            nuts_sampler="pymc",
        ),
        scenarios=default_spatial_activity_scenarios(),
    )


def test_manifest_contains_every_outer_and_feasible_inner_task_once() -> None:
    from genomeos.validation.spatial_activity_tasks import plan_spatial_activity_tasks

    plan = _plan()
    tasks = plan_spatial_activity_tasks(plan)

    assert len(tasks) == 720
    assert len({task.task_id for task in tasks}) == len(tasks)
    assert tasks == tuple(sorted(tasks, key=lambda task: task.task_id))
    assert sum(task.split_role == "outer" for task in tasks) == 180
    assert sum(task.split_role == "inner" for task in tasks) == 540
    assert {task.mode for task in tasks} == {"ordinary", "spatial_activity"}
    assert {task.scenario_id for task in tasks} == {
        scenario.scenario_id for scenario in plan.scenarios
    }


def test_manifest_omits_infeasible_inner_tasks_but_keeps_all_outer_tasks() -> None:
    from genomeos.validation.spatial_activity_tasks import plan_spatial_activity_tasks

    plan = _plan(blocks=3)
    tasks = plan_spatial_activity_tasks(plan)

    assert len(tasks) == 108
    assert all(task.split_role == "outer" for task in tasks)


def test_task_ids_are_stable_and_change_with_scientific_identity() -> None:
    from genomeos.validation.spatial_activity_tasks import (
        SpatialActivityTask,
        plan_spatial_activity_tasks,
    )

    task = plan_spatial_activity_tasks(_plan())[0]
    assert task == plan_spatial_activity_tasks(_plan())[0]
    changed = SpatialActivityTask.create(
        scenario_id=task.scenario_id,
        mode="spatial_activity" if task.mode == "ordinary" else "ordinary",
        split_role=task.split_role,
        outer_split_id=task.outer_split_id,
        split_id=task.split_id,
    )
    assert changed.task_id != task.task_id
    with pytest.raises(ValueError, match="task_id"):
        replace(task, task_id="0" * 64)


def test_task_resolution_returns_exact_scenario_and_parented_split() -> None:
    from genomeos.validation.spatial_activity_tasks import (
        plan_spatial_activity_tasks,
        resolve_spatial_activity_task,
    )

    plan = _plan()
    task = next(
        item for item in plan_spatial_activity_tasks(plan) if item.split_role == "inner"
    )
    scenario, split = resolve_spatial_activity_task(plan, task)

    assert scenario.scenario_id == task.scenario_id
    assert split.split_id == task.split_id
    parent = next(
        inner for inner in plan.inner_plans if inner.outer_split_id == task.outer_split_id
    )
    assert split in parent.splits


def test_task_resolution_refuses_manifest_identity_from_another_plan() -> None:
    from genomeos.validation.spatial_activity_tasks import (
        plan_spatial_activity_tasks,
        resolve_spatial_activity_task,
    )

    task = plan_spatial_activity_tasks(_plan())[0]
    smaller = _plan(blocks=3)
    with pytest.raises(ValueError, match="task"):
        resolve_spatial_activity_task(smaller, task)


def test_task_evaluation_resolves_before_delegating(monkeypatch) -> None:
    from genomeos.validation import spatial_activity_tasks as module

    plan = _plan()
    task = next(
        item for item in module.plan_spatial_activity_tasks(plan) if item.split_role == "inner"
    )
    scenario, split = module.resolve_spatial_activity_task(plan, task)
    synthetic = object()
    sentinel = object()
    calls = {}
    def simulate(actual_plan, actual_scenario):
        calls["simulation"] = (actual_plan, actual_scenario)
        return synthetic

    def evaluate(*args, **kwargs):
        calls["evaluation"] = (args, kwargs)
        return sentinel

    def wrap(*, task, result):
        calls["wrapped"] = (task, result)
        return sentinel

    monkeypatch.setattr(module, "simulate_spatial_activity_plan_scenario", simulate)
    monkeypatch.setattr(module, "evaluate_spatial_activity_fold", evaluate)
    monkeypatch.setattr(module, "SpatialActivityTaskResult", wrap)

    result = module.evaluate_spatial_activity_task(plan, task, fit_function=lambda: None)

    assert result is sentinel
    assert calls["wrapped"] == (task, sentinel)
    assert calls["simulation"] == (plan, scenario)
    args, kwargs = calls["evaluation"]
    assert args == (plan, synthetic, split)
    assert kwargs["mode"] == task.mode
    assert kwargs["split_role"] == task.split_role
    assert kwargs["scenario"] == scenario


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("scenario_id", ""),
        ("mode", "unknown"),
        ("split_role", "test"),
        ("outer_split_id", ""),
        ("split_id", ""),
    ],
)
def test_task_creation_refuses_invalid_identity(field: str, value: object) -> None:
    from genomeos.validation.spatial_activity_tasks import SpatialActivityTask

    kwargs = {
        "scenario_id": "scenario",
        "mode": "ordinary",
        "split_role": "outer",
        "outer_split_id": "outer",
        "split_id": "outer",
    }
    kwargs[field] = value
    with pytest.raises(ValueError):
        SpatialActivityTask.create(**kwargs)
