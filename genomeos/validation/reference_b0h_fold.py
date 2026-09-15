"""Pure B0H comparison fold boundary (design §§5, 7–8, 12; integration §§2–3)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Literal

import numpy as np
import pandas as pd

from genomeos.surfaces.heterogeneity_types import (
    HeterogeneityConvergenceError,
    PopulationHeterogeneityConfig,
    PopulationHeterogeneityFit,
    ReferenceHeterogeneityPrediction,
    VariantHeterogeneityDiagnostics,
)
from genomeos.surfaces.reference_heterogeneity import (
    fit_reference_population_heterogeneity,
    predict_reference_population_heterogeneity,
)
from genomeos.validation.benchmark import validate_predictive_diagnostics
from genomeos.validation.count_baseline import B0InfeasibleError
from genomeos.validation.predictive import predictive_diagnostics
from genomeos.validation.reference_counts import (
    ReferenceCount,
    ReferenceInfeasibleError,
    validate_reference_counts,
)

SEED = 42
FoldState = Literal["completed", "infeasible", "failed"]
Phase = Literal["preflight", "fit", "prediction", "scoring"]
AttemptState = Literal["not_attempted", "accepted", "convergence_failed", "infeasible", "failed"]
SCIENTIFIC_ERRORS = (B0InfeasibleError, ReferenceInfeasibleError, ArithmeticError,
                     ValueError, HeterogeneityConvergenceError)


@dataclass(frozen=True)
class B0HAttempt:
    attempt: Literal["initial", "retry"]
    config: PopulationHeterogeneityConfig
    status: AttemptState
    reason: str | None
    divergence_count: int | None = None
    diagnostics: tuple[VariantHeterogeneityDiagnostics, ...] = ()


@dataclass(frozen=True)
class B0HFoldResult:
    status: FoldState
    failure_phase: Phase | None
    reason: str | None
    attempts: tuple[B0HAttempt, B0HAttempt]
    fit: PopulationHeterogeneityFit | None
    prediction: ReferenceHeterogeneityPrediction | None
    diagnostics: pd.DataFrame | None
    unavailable_ids: tuple[str, ...]


def b0h_seeds(seed: int) -> tuple[int, tuple[int, ...], tuple[tuple[int, int], ...]]:
    """Preserve legacy split/PIT streams and derive five independent fit pairs."""
    split, pit, fit = np.random.SeedSequence(seed).spawn(3)

    def integer(child):
        return int(child.generate_state(1, dtype=np.uint32)[0])

    return (integer(split), tuple(integer(child) for child in pit.spawn(5)),
            tuple(tuple(integer(child) for child in fold.spawn(2)) for fold in fit.spawn(5)))


def _failure(error: Exception) -> tuple[FoldState, str]:
    if isinstance(error, (B0InfeasibleError, ReferenceInfeasibleError)):
        return "infeasible", f"{type(error).__name__}: {error}"
    return "failed", f"{type(error).__name__}: {error}"


def run_b0h_fold(
    training: Sequence[ReferenceCount], testing: Sequence[ReferenceCount], *,
    config: PopulationHeterogeneityConfig, initial_seed: int, retry_seed: int,
    pit_seed: int, cdf_backend: Literal["scipy", "cupy"],
) -> B0HFoldResult:
    """Fit training only; score a whole test fold or preserve its explicit refusal."""
    if cdf_backend not in {"scipy", "cupy"}:
        raise ValueError("cdf_backend must be scipy or cupy")
    initial = replace(config, seed=initial_seed)
    retry = replace(config, draws=2 * config.draws, tune=2 * config.tune, seed=retry_seed)
    attempts = [
        B0HAttempt("initial", initial, "not_attempted", "fold_preflight_infeasible"),
        B0HAttempt("retry", retry, "not_attempted", "initial_not_attempted"),
    ]
    unavailable = tuple(row.record_id for row in testing if row.an == 0)
    fitted = None

    def result(state, phase, reason, prediction=None, diagnostics=None):
        return B0HFoldResult(state, phase, reason, tuple(attempts), fitted,
                             prediction, diagnostics, unavailable)

    try:
        training = validate_reference_counts(training)
        testing = validate_reference_counts(testing)
        if not any(row.an > 0 for row in testing):
            raise ReferenceInfeasibleError("test fold has no scoreable rows")
    except SCIENTIFIC_ERRORS as error:
        state, reason = _failure(error)
        return result(state, "preflight", reason)

    variants = {row.variant_id for row in training if row.an > 0}
    for index, attempt in enumerate(attempts):
        try:
            fitted = fit_reference_population_heterogeneity(training, config=attempt.config)
        except HeterogeneityConvergenceError as error:
            diagnostics = tuple(sorted(error.diagnostics, key=lambda item: item.variant_id))
            ids = tuple(item.variant_id for item in diagnostics)
            if len(set(ids)) != len(ids) or not set(ids) <= variants:
                reason = "ValueError: convergence diagnostics have invalid training variant identities"
                attempts[index] = replace(attempt, status="failed", reason=reason)
                if index == 0:
                    attempts[1] = replace(attempts[1], reason="initial_not_retryable")
                return result("failed", "fit", reason)
            attempts[index] = replace(
                attempt, status="convergence_failed", reason=error.reason,
                diagnostics=diagnostics, divergence_count=error.divergence_count,
            )
            if index == 0:
                continue
            return result("failed", "fit", error.reason)
        except SCIENTIFIC_ERRORS as error:
            state, reason = _failure(error)
            attempts[index] = replace(attempt, status=state, reason=reason)
            if index == 0:
                attempts[1] = replace(attempts[1], reason="initial_not_retryable")
            return result(state, "fit", reason)
        attempts[index] = replace(attempt, status="accepted", reason=None,
                                  divergence_count=fitted.divergence_count,
                                  diagnostics=fitted.diagnostics)
        if index == 0:
            attempts[1] = replace(attempts[1], reason="initial_accepted")
        break

    try:
        prediction = predict_reference_population_heterogeneity(
            fitted, testing, cdf_backend=cdf_backend,
        )
        scoreable = tuple(row for row in testing if row.an > 0)
        if prediction.observation_ids != tuple(row.record_id for row in scoreable):
            raise ValueError("prediction identities must match scoreable test-row order")
        if prediction.unavailable_ids != unavailable:
            raise ValueError("prediction unavailable identities must match testing rows")
    except SCIENTIFIC_ERRORS as error:
        state, reason = _failure(error)
        return result(state, "prediction", reason)
    try:
        diagnostics = validate_predictive_diagnostics(predictive_diagnostics(
            prediction.marginal_predictive, [row.ac for row in scoreable],
            [row.an for row in scoreable], seed=pit_seed,
        ))
        if len(diagnostics) != len(scoreable):
            raise ValueError("diagnostic row count must match scoreable testing rows")
    except SCIENTIFIC_ERRORS as error:
        state, reason = _failure(error)
        return result(state, "scoring", reason)
    return result("completed", None, None, prediction, diagnostics)
