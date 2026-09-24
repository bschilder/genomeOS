"""Content-addressed task manifest for the spatial activity campaign (design §8; #384).

Each task is one independent scenario/model/split fit. The manifest contains no execution or
storage policy, so local workers and RunPod fan-out can consume the same immutable identities.
Results are evaluated through the pure fold runner and can be aggregated without re-fitting.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from itertools import product

from genomeos.surfaces.spatial_activity_fit import fit_spatial_activity_graph
from genomeos.surfaces.spatial_activity_model import (
    ACTIVITY_MODEL_MODES,
    ActivityModelMode,
)
from genomeos.validation.spatial_activity_plan import SpatialActivityPreflightPlan
from genomeos.validation.spatial_activity_runner import (
    FitFunction,
    SpatialActivityFoldResult,
    evaluate_spatial_activity_fold,
    simulate_spatial_activity_plan_scenario,
)
from genomeos.validation.spatial_activity_simulation import SpatialActivityScenario
from genomeos.validation.splits import BenchmarkSplit


def _label(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonempty string")
    return value


def _task_id(
    scenario_id: str,
    mode: ActivityModelMode,
    split_role: str,
    outer_split_id: str,
    split_id: str,
) -> str:
    payload = json.dumps(
        {
            "mode": mode,
            "outer_split_id": outer_split_id,
            "scenario_id": scenario_id,
            "split_id": split_id,
            "split_role": split_role,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class SpatialActivityTask:
    """One content-addressed scenario/model/split evaluation."""

    task_id: str
    scenario_id: str
    mode: ActivityModelMode
    split_role: str
    outer_split_id: str
    split_id: str

    def __post_init__(self) -> None:
        scenario_id = _label(self.scenario_id, "scenario_id")
        if self.mode not in ACTIVITY_MODEL_MODES:
            raise ValueError(f"mode must be one of {ACTIVITY_MODEL_MODES}")
        if self.split_role not in ("outer", "inner"):
            raise ValueError("split_role must be outer or inner")
        outer_split_id = _label(self.outer_split_id, "outer_split_id")
        split_id = _label(self.split_id, "split_id")
        if self.split_role == "outer" and split_id != outer_split_id:
            raise ValueError("outer tasks must use their outer split as split_id")
        expected = _task_id(
            scenario_id,
            self.mode,
            self.split_role,
            outer_split_id,
            split_id,
        )
        if self.task_id != expected:
            raise ValueError("task_id does not match the scientific task identity")

    @classmethod
    def create(
        cls,
        *,
        scenario_id: object,
        mode: object,
        split_role: object,
        outer_split_id: object,
        split_id: object,
    ) -> SpatialActivityTask:
        normalized_scenario = _label(scenario_id, "scenario_id")
        if mode not in ACTIVITY_MODEL_MODES:
            raise ValueError(f"mode must be one of {ACTIVITY_MODEL_MODES}")
        if split_role not in ("outer", "inner"):
            raise ValueError("split_role must be outer or inner")
        normalized_outer = _label(outer_split_id, "outer_split_id")
        normalized_split = _label(split_id, "split_id")
        return cls(
            task_id=_task_id(
                normalized_scenario,
                mode,
                split_role,
                normalized_outer,
                normalized_split,
            ),
            scenario_id=normalized_scenario,
            mode=mode,
            split_role=split_role,
            outer_split_id=normalized_outer,
            split_id=normalized_split,
        )


@dataclass(frozen=True)
class SpatialActivityTaskResult:
    """One manifest identity paired with its terminal fold result."""

    task: SpatialActivityTask
    result: SpatialActivityFoldResult

    def __post_init__(self) -> None:
        if not isinstance(self.task, SpatialActivityTask):
            raise ValueError("task must be SpatialActivityTask")
        if not isinstance(self.result, SpatialActivityFoldResult):
            raise ValueError("result must be SpatialActivityFoldResult")
        if (
            self.result.scenario_id != self.task.scenario_id
            or self.result.mode != self.task.mode
            or self.result.split_role != self.task.split_role
            or self.result.status.split_id != self.task.split_id
        ):
            raise ValueError("result identity does not match its task")


def plan_spatial_activity_tasks(
    plan: SpatialActivityPreflightPlan,
) -> tuple[SpatialActivityTask, ...]:
    """Enumerate every feasible frozen task exactly once in canonical order."""
    if not isinstance(plan, SpatialActivityPreflightPlan):
        raise ValueError("plan must be SpatialActivityPreflightPlan")
    tasks = [
        SpatialActivityTask.create(
            scenario_id=scenario.scenario_id,
            mode=mode,
            split_role="outer",
            outer_split_id=split.split_id,
            split_id=split.split_id,
        )
        for scenario, mode, split in product(
            plan.scenarios,
            plan.modes,
            plan.outer_splits,
        )
    ]
    for inner in plan.inner_plans:
        tasks.extend(
            SpatialActivityTask.create(
                scenario_id=scenario.scenario_id,
                mode=mode,
                split_role="inner",
                outer_split_id=inner.outer_split_id,
                split_id=split.split_id,
            )
            for scenario, mode, split in product(
                plan.scenarios,
                plan.modes,
                inner.splits,
            )
        )
    ordered = tuple(sorted(tasks, key=lambda task: task.task_id))
    if len({task.task_id for task in ordered}) != len(ordered):
        raise RuntimeError("task manifest produced duplicate task identities")
    return ordered


def resolve_spatial_activity_task(
    plan: SpatialActivityPreflightPlan,
    task: SpatialActivityTask,
) -> tuple[SpatialActivityScenario, BenchmarkSplit]:
    """Resolve one manifest identity to its exact immutable scenario and split."""
    if not isinstance(plan, SpatialActivityPreflightPlan):
        raise ValueError("plan must be SpatialActivityPreflightPlan")
    if not isinstance(task, SpatialActivityTask):
        raise ValueError("task must be SpatialActivityTask")
    if task not in plan_spatial_activity_tasks(plan):
        raise ValueError("task is not present in this plan's frozen manifest")
    scenario = next(
        scenario for scenario in plan.scenarios if scenario.scenario_id == task.scenario_id
    )
    if task.split_role == "outer":
        split = next(split for split in plan.outer_splits if split.split_id == task.split_id)
    else:
        parent = next(
            inner
            for inner in plan.inner_plans
            if inner.outer_split_id == task.outer_split_id
        )
        split = next(split for split in parent.splits if split.split_id == task.split_id)
    return scenario, split


def evaluate_spatial_activity_task(
    plan: SpatialActivityPreflightPlan,
    task: SpatialActivityTask,
    *,
    fit_function: FitFunction = fit_spatial_activity_graph,
    cdf_backend: str = "scipy",
) -> SpatialActivityTaskResult:
    """Evaluate one manifest task without coupling it to other workers."""
    scenario, split = resolve_spatial_activity_task(plan, task)
    synthetic = simulate_spatial_activity_plan_scenario(plan, scenario)
    result = evaluate_spatial_activity_fold(
        plan,
        synthetic,
        split,
        mode=task.mode,
        split_role=task.split_role,
        scenario=scenario,
        fit_function=fit_function,
        cdf_backend=cdf_backend,
    )
    return SpatialActivityTaskResult(task=task, result=result)
