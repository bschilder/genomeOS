"""Freeze outer and inner splits for the spatial activity preflight (design §§4, 8; #384).

The outer splits must exactly reproduce an already validated single-variant GP benchmark plan.
Within each outer training partition, original geographic blocks are grouped into three
outcome-blind inner folds, then dependency and geographic-buffer exclusions are rebuilt. An
infeasible three-fold nesting is retained as an explicit refusal rather than silently relaxed.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from genomeos.surfaces.spatial_activity_fit import SpatialActivitySamplerConfig
from genomeos.surfaces.spatial_activity_model import (
    ACTIVITY_MODEL_MODES,
    ActivityModelMode,
    SpatialActivityModelConfig,
)
from genomeos.validation.nested_folds import (
    ThreeInnerFoldPlan,
    apply_three_inner_folds,
    plan_three_inner_folds,
)
from genomeos.validation.spatial_activity_simulation import (
    SpatialActivityScenario,
    default_spatial_activity_scenarios,
)
from genomeos.validation.spatial_gp_benchmark import SpatialGPBenchmarkPlan
from genomeos.validation.splits import BenchmarkSplit, build_buffered_splits

DependencyPair = tuple[str, str]


@dataclass(frozen=True)
class SpatialActivityInnerPlan:
    """Three inner splits for one outer training set, or its explicit refusal."""

    outer_split_id: str
    grouping: ThreeInnerFoldPlan | None
    splits: tuple[BenchmarkSplit, ...]
    refusal_reason: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.outer_split_id, str) or not self.outer_split_id.strip():
            raise ValueError("outer_split_id must be a nonempty string")
        if self.refusal_reason is None:
            if not isinstance(self.grouping, ThreeInnerFoldPlan) or len(self.splits) != 3:
                raise ValueError("feasible inner plans require one grouping and three splits")
        elif (
            not isinstance(self.refusal_reason, str)
            or not self.refusal_reason.strip()
            or self.grouping is not None
            or self.splits
        ):
            raise ValueError("refused inner plans require only a nonempty refusal reason")


@dataclass(frozen=True)
class SpatialActivityPreflightPlan:
    """Frozen simulation grid, matched model arms, and nested split protocol."""

    baseline_plan: SpatialGPBenchmarkPlan
    outer_splits: tuple[BenchmarkSplit, ...]
    inner_plans: tuple[SpatialActivityInnerPlan, ...]
    scenarios: tuple[SpatialActivityScenario, ...]
    modes: tuple[ActivityModelMode, ...]
    model_config: SpatialActivityModelConfig
    sampler_config: SpatialActivitySamplerConfig
    dependencies: tuple[DependencyPair, ...]


def _dependencies(
    dependencies: Sequence[DependencyPair],
    observation_ids: set[str],
) -> tuple[DependencyPair, ...]:
    if isinstance(dependencies, (str, bytes)) or not isinstance(dependencies, Sequence):
        raise TypeError("dependencies must be a sequence of identity pairs")
    normalized: set[DependencyPair] = set()
    for pair in dependencies:
        if not isinstance(pair, tuple) or len(pair) != 2:
            raise ValueError("each dependency must be a two-tuple")
        left, right = pair
        if (
            not isinstance(left, str)
            or not left.strip()
            or not isinstance(right, str)
            or not right.strip()
        ):
            raise ValueError("dependency identities must be nonempty strings")
        unknown = sorted({left, right} - observation_ids)
        if unknown:
            raise ValueError(f"dependency references unknown observation identities: {unknown}")
        normalized.add((left, right) if left <= right else (right, left))
    return tuple(sorted(normalized))


def _validate_scenarios(
    scenarios: Sequence[SpatialActivityScenario],
) -> tuple[SpatialActivityScenario, ...]:
    if isinstance(scenarios, (str, bytes)) or not isinstance(scenarios, Sequence):
        raise TypeError("scenarios must be a sequence of SpatialActivityScenario records")
    result = tuple(scenarios)
    expected = default_spatial_activity_scenarios()
    if result != expected:
        raise ValueError("scenario grid must exactly match the frozen default grid")
    return result


def _inner_plan(
    baseline_plan: SpatialGPBenchmarkPlan,
    outer: BenchmarkSplit,
    dependencies: tuple[DependencyPair, ...],
) -> SpatialActivityInnerPlan:
    outer_ids = set(outer.train_ids)
    source_assignments = baseline_plan.assignments.loc[
        baseline_plan.assignments["source_record_id"].isin(outer_ids),
        ["source_record_id", "block_id"],
    ].copy()
    if source_assignments["block_id"].nunique() < 3:
        return SpatialActivityInnerPlan(
            outer_split_id=outer.split_id,
            grouping=None,
            splits=(),
            refusal_reason=(
                "three inner folds are infeasible because the outer training set contains "
                "fewer than three original geographic blocks"
            ),
        )
    grouping = plan_three_inner_folds(source_assignments)
    grouped_assignments = apply_three_inner_folds(source_assignments, grouping)
    outer_observations = baseline_plan.observations.loc[
        baseline_plan.observations["source_record_id"].isin(outer_ids)
    ].copy()
    outer_dependencies = tuple(
        pair for pair in dependencies if pair[0] in outer_ids and pair[1] in outer_ids
    )
    inner_splits = build_buffered_splits(
        outer_observations,
        grouped_assignments,
        outer_dependencies,
        buffer_km=outer.buffer_km,
        data_version=f"{outer.data_version}:inner:{outer.split_id}",
    )
    return SpatialActivityInnerPlan(
        outer_split_id=outer.split_id,
        grouping=grouping,
        splits=inner_splits,
        refusal_reason=None,
    )


def plan_spatial_activity_preflight(
    baseline_plan: SpatialGPBenchmarkPlan,
    *,
    dependencies: Sequence[DependencyPair],
    model_config: SpatialActivityModelConfig,
    sampler_config: SpatialActivitySamplerConfig,
    scenarios: Sequence[SpatialActivityScenario],
) -> SpatialActivityPreflightPlan:
    """Freeze the simulation experiment against the exact baseline outer splits."""
    if not isinstance(baseline_plan, SpatialGPBenchmarkPlan):
        raise TypeError("baseline_plan must be SpatialGPBenchmarkPlan")
    if not isinstance(model_config, SpatialActivityModelConfig):
        raise ValueError("model_config must be SpatialActivityModelConfig")
    if not isinstance(sampler_config, SpatialActivitySamplerConfig):
        raise ValueError("sampler_config must be SpatialActivitySamplerConfig")
    scenario_grid = _validate_scenarios(scenarios)
    observation_ids = set(baseline_plan.observations["source_record_id"])
    normalized_dependencies = _dependencies(dependencies, observation_ids)

    first = baseline_plan.splits[0]
    reconstructed = build_buffered_splits(
        baseline_plan.observations,
        baseline_plan.assignments.loc[:, ["source_record_id", "block_id"]],
        normalized_dependencies,
        buffer_km=first.buffer_km,
        data_version=first.data_version,
    )
    if reconstructed != baseline_plan.splits:
        raise ValueError(
            "dependencies and assignments do not reproduce the baseline outer splits"
        )
    inner = tuple(
        _inner_plan(baseline_plan, outer, normalized_dependencies)
        for outer in baseline_plan.splits
    )
    return SpatialActivityPreflightPlan(
        baseline_plan=baseline_plan,
        outer_splits=baseline_plan.splits,
        inner_plans=inner,
        scenarios=scenario_grid,
        modes=ACTIVITY_MODEL_MODES,
        model_config=model_config,
        sampler_config=sampler_config,
        dependencies=normalized_dependencies,
    )
