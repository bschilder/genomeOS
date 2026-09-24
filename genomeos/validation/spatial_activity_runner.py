"""Execute one spatial-activity simulation fold (design §§4, 7–8, 12; issue #384).

This pure offline boundary joins the frozen synthetic truth, matched ordinary/activity PyMC
graphs, one logged doubled-budget convergence retry, new-cohort prediction, and marginal count
assessment. It performs no file, network, environment, serving, or publication operation.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import Literal

import numpy as np

from genomeos.surfaces.convergence import SamplerDiagnostics
from genomeos.surfaces.fit import derive_lengthscale_prior, to_unit_sphere
from genomeos.surfaces.spatial_activity_fit import (
    SpatialActivityConvergenceError,
    SpatialActivityFit,
    SpatialActivitySamplerConfig,
    fit_spatial_activity_graph,
    predict_spatial_activity_counts,
)
from genomeos.surfaces.spatial_activity_model import (
    ACTIVITY_MODEL_MODES,
    ActivityModelMode,
    SpatialActivityModelConfig,
    build_spatial_activity_model,
)
from genomeos.validation.benchmark import BenchmarkFoldStatus
from genomeos.validation.spatial_activity_assessment import (
    ActivityPredictionAssessment,
    assess_spatial_activity_prediction,
)
from genomeos.validation.spatial_activity_plan import SpatialActivityPreflightPlan
from genomeos.validation.spatial_activity_simulation import (
    SpatialActivityScenario,
    SpatialActivitySyntheticData,
    simulate_spatial_activity_scenario,
)
from genomeos.validation.splits import BenchmarkSplit

SplitRole = Literal["outer", "inner"]
AttemptState = Literal["completed", "nonconverged", "failed"]
FitFunction = Callable[..., SpatialActivityFit]


def _require_cdf_backend(cdf_backend: str) -> None:
    if cdf_backend == "cupy":
        from genomeos.validation.predictive_cupy import require_cupy_cdf

        require_cupy_cdf()


@dataclass(frozen=True)
class SpatialActivityFitAttempt:
    """One retained sampler budget and terminal outcome."""

    attempt: int
    draws: int
    tune: int
    seed: int
    status: AttemptState
    failure_reason: str | None
    diagnostics: SamplerDiagnostics | None

    def __post_init__(self) -> None:
        if self.attempt not in (1, 2):
            raise ValueError("attempt must be one or two")
        if self.status == "completed":
            if self.failure_reason is not None or self.diagnostics is None:
                raise ValueError("completed attempts require diagnostics and no failure reason")
        elif (
            self.status not in ("nonconverged", "failed")
            or not isinstance(self.failure_reason, str)
            or not self.failure_reason.strip()
        ):
            raise ValueError("failed attempts require a nonempty failure reason")


@dataclass(frozen=True)
class SpatialActivityFoldResult:
    """One terminal scenario/model/split result."""

    scenario_id: str
    mode: ActivityModelMode
    split_role: SplitRole
    status: BenchmarkFoldStatus
    fit_seed: int
    predictive_seed: int
    model_config: SpatialActivityModelConfig
    attempts: tuple[SpatialActivityFitAttempt, ...]
    assessment: ActivityPredictionAssessment | None
    fitted: SpatialActivityFit | None = field(default=None, repr=False)


def _seed(
    base_seed: int,
    scenario_id: str,
    mode: ActivityModelMode,
    split_role: SplitRole,
    split_id: str,
    purpose: str,
) -> int:
    payload = (
        f"{base_seed}\0{scenario_id}\0{mode}\0{split_role}\0{split_id}\0{purpose}"
    ).encode()
    return int.from_bytes(hashlib.sha256(payload).digest()[:4], "big")


def _cohort_index(values: object) -> np.ndarray:
    labels = np.asarray(values, dtype=object)
    unique = tuple(sorted(set(labels.tolist())))
    by_label = {label: index for index, label in enumerate(unique)}
    return np.asarray([by_label[label] for label in labels], dtype=np.int64)


def simulate_spatial_activity_plan_scenario(
    plan: SpatialActivityPreflightPlan,
    scenario: SpatialActivityScenario,
) -> SpatialActivitySyntheticData:
    """Generate one frozen scenario over the plan's unchanged observation template."""
    if not isinstance(plan, SpatialActivityPreflightPlan):
        raise ValueError("plan must be SpatialActivityPreflightPlan")
    if scenario not in plan.scenarios:
        raise ValueError("scenario is not present in the frozen plan")
    observations = plan.baseline_plan.observations
    return simulate_spatial_activity_scenario(
        tuple(observations["source_record_id"]),
        to_unit_sphere(observations["lat"], observations["lon"]),
        observations["an"].to_numpy(),
        cohort_ids=tuple(observations["cohort_id"]),
        scenario=scenario,
    )


def _truth_by_id(synthetic: SpatialActivitySyntheticData) -> dict[str, int]:
    return {record_id: index for index, record_id in enumerate(synthetic.record_ids)}


def _attempt(
    number: int,
    config: SpatialActivitySamplerConfig,
    *,
    status: AttemptState,
    failure_reason: str | None,
    diagnostics: SamplerDiagnostics | None,
) -> SpatialActivityFitAttempt:
    return SpatialActivityFitAttempt(
        attempt=number,
        draws=config.draws,
        tune=config.tune,
        seed=config.seed,
        status=status,
        failure_reason=failure_reason,
        diagnostics=diagnostics,
    )


def _terminal_without_fit(
    scenario: SpatialActivityScenario,
    mode: ActivityModelMode,
    split_role: SplitRole,
    split: BenchmarkSplit,
    *,
    fit_seed: int,
    predictive_seed: int,
    model_config: SpatialActivityModelConfig,
    state: Literal["failed", "infeasible"],
    reason: str,
    attempts: tuple[SpatialActivityFitAttempt, ...] = (),
) -> SpatialActivityFoldResult:
    return SpatialActivityFoldResult(
        scenario_id=scenario.scenario_id,
        mode=mode,
        split_role=split_role,
        status=BenchmarkFoldStatus(
            split_id=split.split_id,
            status=state,
            expected_test_ids=split.test_ids,
            failure_reason=reason,
        ),
        fit_seed=fit_seed,
        predictive_seed=predictive_seed,
        model_config=model_config,
        attempts=attempts,
        assessment=None,
        fitted=None,
    )


def evaluate_spatial_activity_fold(
    plan: SpatialActivityPreflightPlan,
    synthetic: SpatialActivitySyntheticData,
    split: BenchmarkSplit,
    *,
    mode: ActivityModelMode,
    split_role: SplitRole,
    scenario: SpatialActivityScenario | None = None,
    fit_function: FitFunction = fit_spatial_activity_graph,
    cdf_backend: str = "scipy",
) -> SpatialActivityFoldResult:
    """Run one arm with at most one recorded doubled-budget convergence retry."""
    if not isinstance(plan, SpatialActivityPreflightPlan):
        raise ValueError("plan must be SpatialActivityPreflightPlan")
    if not isinstance(synthetic, SpatialActivitySyntheticData):
        raise ValueError("synthetic must be SpatialActivitySyntheticData")
    if not isinstance(split, BenchmarkSplit):
        raise ValueError("split must be BenchmarkSplit")
    if mode not in ACTIVITY_MODEL_MODES:
        raise ValueError(f"mode must be one of {ACTIVITY_MODEL_MODES}")
    if split_role not in ("outer", "inner"):
        raise ValueError("split_role must be outer or inner")
    if not callable(fit_function):
        raise TypeError("fit_function must be callable")
    if cdf_backend not in {"scipy", "cupy"}:
        raise ValueError("cdf_backend must be either 'scipy' or 'cupy'")
    selected_scenario = synthetic.scenario if scenario is None else scenario
    if selected_scenario not in plan.scenarios or synthetic.scenario != selected_scenario:
        raise ValueError("synthetic data and requested scenario must match the frozen plan")
    observation_ids = tuple(plan.baseline_plan.observations["source_record_id"])
    if set(synthetic.record_ids) != set(observation_ids):
        raise ValueError("synthetic record identities must match the frozen plan")

    fit_seed = _seed(
        plan.sampler_config.seed,
        selected_scenario.scenario_id,
        mode,
        split_role,
        split.split_id,
        "fit",
    )
    predictive_seed = _seed(
        plan.sampler_config.seed,
        selected_scenario.scenario_id,
        mode,
        split_role,
        split.split_id,
        "predictive",
    )
    if not split.train_ids:
        return _terminal_without_fit(
            selected_scenario,
            mode,
            split_role,
            split,
            fit_seed=fit_seed,
            predictive_seed=predictive_seed,
            model_config=plan.model_config,
            state="infeasible",
            reason="split has no training observations after dependency and buffer exclusions",
        )

    by_id = plan.baseline_plan.observations.set_index("source_record_id", drop=False)
    training = by_id.loc[list(split.train_ids)].reset_index(drop=True)
    testing = by_id.loc[list(split.test_ids)].reset_index(drop=True)
    if len(training) < 2:
        return _terminal_without_fit(
            selected_scenario,
            mode,
            split_role,
            split,
            fit_seed=fit_seed,
            predictive_seed=predictive_seed,
            model_config=plan.model_config,
            state="infeasible",
            reason="spatial lengthscale prior requires at least two training observations",
        )
    _require_cdf_backend(cdf_backend)
    truth_index = _truth_by_id(synthetic)
    train_truth = np.asarray([truth_index[value] for value in training["source_record_id"]])
    test_truth = np.asarray([truth_index[value] for value in testing["source_record_id"]])
    ac = np.asarray(synthetic.ac, dtype=np.int64)
    an = np.asarray(synthetic.an, dtype=np.int64)
    lengthscale_mu, lengthscale_sigma, _, _ = derive_lengthscale_prior(
        training["lat"].to_numpy(),
        training["lon"].to_numpy(),
    )
    model_config = replace(
        plan.model_config,
        lengthscale_mu=lengthscale_mu,
        lengthscale_sigma=lengthscale_sigma,
    )
    graph = build_spatial_activity_model(
        to_unit_sphere(training["lat"], training["lon"]),
        ac[train_truth],
        an[train_truth],
        to_unit_sphere(testing["lat"], testing["lon"]),
        cohort_index=_cohort_index(training["cohort_id"]),
        mode=mode,
        config=model_config,
    )

    attempts: list[SpatialActivityFitAttempt] = []
    fitted: SpatialActivityFit | None = None
    base_config = replace(plan.sampler_config, seed=fit_seed)
    for number, sampler_config in (
        (1, base_config),
        (2, replace(base_config, draws=base_config.draws * 2, tune=base_config.tune * 2)),
    ):
        try:
            fitted = fit_function(graph, config=sampler_config)
        except SpatialActivityConvergenceError as error:
            attempts.append(
                _attempt(
                    number,
                    sampler_config,
                    status="nonconverged",
                    failure_reason=str(error),
                    diagnostics=error.diagnostics,
                )
            )
            continue
        except Exception as error:
            attempts.append(
                _attempt(
                    number,
                    sampler_config,
                    status="failed",
                    failure_reason=f"{type(error).__name__}: {error}",
                    diagnostics=None,
                )
            )
            return _terminal_without_fit(
                selected_scenario,
                mode,
                split_role,
                split,
                fit_seed=fit_seed,
                predictive_seed=predictive_seed,
                model_config=model_config,
                state="failed",
                reason=f"fit failed without retry: {type(error).__name__}: {error}",
                attempts=tuple(attempts),
            )
        attempts.append(
            _attempt(
                number,
                sampler_config,
                status="completed",
                failure_reason=None,
                diagnostics=fitted.diagnostics,
            )
        )
        break

    if fitted is None:
        return _terminal_without_fit(
            selected_scenario,
            mode,
            split_role,
            split,
            fit_seed=fit_seed,
            predictive_seed=predictive_seed,
            model_config=model_config,
            state="failed",
            reason="sampler did not converge after the single doubled-budget retry",
            attempts=tuple(attempts),
        )

    try:
        predictive = predict_spatial_activity_counts(
            fitted,
            prediction_cohort_index=_cohort_index(testing["cohort_id"]),
            seed=predictive_seed,
            cdf_backend=cdf_backend,
        )
        observation_truth = np.asarray(
            synthetic.observation_conditional_mean_truth,
            dtype=np.float64,
        )
        activity_truth = np.asarray(
            synthetic.activity_probability_truth,
            dtype=np.float64,
        )
        marginal_truth = np.asarray(synthetic.marginal_mean_truth, dtype=np.float64)
        assessment = assess_spatial_activity_prediction(
            predictive,
            ac=ac[test_truth],
            an=an[test_truth],
            marginal_mean_truth=marginal_truth[test_truth],
            conditional_mean_truth=observation_truth[test_truth],
            activity_probability_truth=activity_truth[test_truth],
            seed=predictive_seed,
        )
    except Exception as error:
        return _terminal_without_fit(
            selected_scenario,
            mode,
            split_role,
            split,
            fit_seed=fit_seed,
            predictive_seed=predictive_seed,
            model_config=model_config,
            state="failed",
            reason=f"prediction or assessment failed: {type(error).__name__}: {error}",
            attempts=tuple(attempts),
        )

    return SpatialActivityFoldResult(
        scenario_id=selected_scenario.scenario_id,
        mode=mode,
        split_role=split_role,
        status=BenchmarkFoldStatus(
            split_id=split.split_id,
            status="completed",
            expected_test_ids=split.test_ids,
            failure_reason=None,
        ),
        fit_seed=fit_seed,
        predictive_seed=predictive_seed,
        model_config=model_config,
        attempts=tuple(attempts),
        assessment=assessment,
        fitted=fitted,
    )
