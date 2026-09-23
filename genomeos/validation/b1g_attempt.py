"""Prespecified B1G convergence attempts (design §§4–8, 12; plan WP2; #376).

Scientific objective
    Give each B1G fit one outcome-blind chance to recover from a typed convergence failure without
    weakening the frozen sampler gates or changing the model after results are observed.
Measurable output
    Exactly two immutable attempt records retain the initial and doubled-budget retry configs,
    statuses, reasons, and sampler diagnostics; one accepted fit or one terminal refusal is emitted.
Engineering interface
    :func:`run_b1g_fit_attempts` wraps the existing fit boundary and accepts an injectable fitter
    for direct contract tests.
Assumptions and refusals
    Only :class:`B1GConvergenceError` admits the planned retry. Other exceptions fail immediately,
    interruptions propagate, and a failed retry is terminal.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any, Literal

import pandas as pd

from genomeos.surfaces.config import FitConfig
from genomeos.surfaces.convergence import SamplerDiagnostics
from genomeos.validation.b1g_basis import B1GBasisConfig
from genomeos.validation.b1g_fit import B1GConvergenceError, B1GFit, fit_b1g

AttemptState = Literal["not_attempted", "accepted", "convergence_failed", "failed"]
FitFunction = Callable[..., B1GFit]


@dataclass(frozen=True)
class B1GFitAttempt:
    """One frozen initial or retry invocation and its terminal evidence."""

    attempt: Literal["initial", "retry"]
    config: FitConfig
    status: AttemptState
    reason: str | None
    diagnostics: SamplerDiagnostics | None


@dataclass(frozen=True)
class B1GFitRun:
    """An accepted fit together with both prespecified attempt slots."""

    fit: Any
    attempts: tuple[B1GFitAttempt, B1GFitAttempt]


class B1GFitAttemptsError(RuntimeError):
    """Both-attempt evidence for a terminal fit refusal."""

    def __init__(
        self,
        reason: str,
        attempts: tuple[B1GFitAttempt, B1GFitAttempt],
        diagnostics: SamplerDiagnostics | None,
    ) -> None:
        self.reason = reason
        self.attempts = attempts
        self.diagnostics = diagnostics
        super().__init__(reason)


def _require_seed(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")
    return value


def validate_b1g_fit_attempts(
    attempts: tuple[B1GFitAttempt, ...],
    *,
    fit_config: FitConfig,
    initial_seed: int,
    retry_seed: int,
) -> int:
    """Validate a complete two-slot ledger and return its accepted or terminal fit seed."""
    if not isinstance(fit_config, FitConfig):
        raise TypeError("fit_config must be a FitConfig")
    initial_seed = _require_seed(initial_seed, "initial_seed")
    retry_seed = _require_seed(retry_seed, "retry_seed")
    if initial_seed == retry_seed:
        raise ValueError("initial_seed and retry_seed must differ")
    expected_configs = (
        replace(fit_config, seed=initial_seed),
        replace(
            fit_config,
            draws=2 * fit_config.draws,
            tune=2 * fit_config.tune,
            seed=retry_seed,
        ),
    )
    if (
        not isinstance(attempts, tuple)
        or len(attempts) != 2
        or any(not isinstance(attempt, B1GFitAttempt) for attempt in attempts)
    ):
        raise ValueError("B1G fit evidence must retain exactly two attempt slots")
    if tuple(attempt.attempt for attempt in attempts) != ("initial", "retry"):
        raise ValueError("B1G fit attempt labels are invalid")
    if tuple(attempt.config for attempt in attempts) != expected_configs:
        raise ValueError("B1G fit attempt configs contradict the frozen retry policy")
    statuses = tuple(attempt.status for attempt in attempts)
    if statuses not in {
        ("accepted", "not_attempted"),
        ("convergence_failed", "accepted"),
        ("convergence_failed", "convergence_failed"),
        ("convergence_failed", "failed"),
        ("failed", "not_attempted"),
    }:
        raise ValueError("B1G fit attempt status sequence is invalid")
    for attempt in attempts:
        diagnostics_required = attempt.status in {"accepted", "convergence_failed"}
        if diagnostics_required != isinstance(attempt.diagnostics, SamplerDiagnostics):
            raise ValueError("B1G fit attempt diagnostics contradict status")
        if (attempt.status == "accepted") != (attempt.reason is None):
            raise ValueError("B1G fit attempt reason contradicts status")
        if attempt.status != "accepted" and (
            not isinstance(attempt.reason, str) or not attempt.reason.strip()
        ):
            raise ValueError("B1G fit attempt reason must be retained")
    accepted = [attempt for attempt in attempts if attempt.status == "accepted"]
    if accepted:
        return accepted[0].config.seed
    terminal = [attempt for attempt in attempts if attempt.status != "not_attempted"][-1]
    return terminal.config.seed


def run_b1g_fit_attempts(
    training: pd.DataFrame,
    *,
    basis_config: B1GBasisConfig,
    fit_config: FitConfig,
    initial_seed: int,
    retry_seed: int,
    fit_function: FitFunction = fit_b1g,
) -> B1GFitRun:
    """Run an initial fit and at most one convergence-only doubled-budget retry."""
    if not isinstance(basis_config, B1GBasisConfig):
        raise TypeError("basis_config must be a B1GBasisConfig")
    if not isinstance(fit_config, FitConfig):
        raise TypeError("fit_config must be a FitConfig")
    initial_seed = _require_seed(initial_seed, "initial_seed")
    retry_seed = _require_seed(retry_seed, "retry_seed")
    if initial_seed == retry_seed:
        raise ValueError("initial_seed and retry_seed must differ")
    if not callable(fit_function):
        raise TypeError("fit_function must be callable")

    initial = replace(fit_config, seed=initial_seed)
    retry = replace(
        fit_config,
        draws=2 * fit_config.draws,
        tune=2 * fit_config.tune,
        seed=retry_seed,
    )
    attempts = [
        B1GFitAttempt("initial", initial, "not_attempted", "fit_not_started", None),
        B1GFitAttempt("retry", retry, "not_attempted", "initial_not_attempted", None),
    ]
    for index, attempt in enumerate(attempts):
        try:
            fitted = fit_function(
                training,
                basis_config=basis_config,
                fit_config=attempt.config,
            )
            diagnostics = getattr(fitted, "sampler_diagnostics", None)
            if not isinstance(diagnostics, SamplerDiagnostics):
                raise TypeError("fit result must retain SamplerDiagnostics")
        except B1GConvergenceError as error:
            if not isinstance(error.diagnostics, SamplerDiagnostics):
                reason = "ValueError: convergence failure lacks valid sampler diagnostics"
                attempts[index] = replace(attempt, status="failed", reason=reason)
                if index == 0:
                    attempts[1] = replace(attempts[1], reason="initial_not_retryable")
                raise B1GFitAttemptsError(reason, tuple(attempts), None) from error
            reason = f"B1GConvergenceError: {error}"
            attempts[index] = replace(
                attempt,
                status="convergence_failed",
                reason=reason,
                diagnostics=error.diagnostics,
            )
            if index == 0:
                continue
            raise B1GFitAttemptsError(reason, tuple(attempts), error.diagnostics) from error
        except Exception as error:
            reason = f"{type(error).__name__}: {error}"
            attempts[index] = replace(attempt, status="failed", reason=reason)
            if index == 0:
                attempts[1] = replace(attempts[1], reason="initial_not_retryable")
            raise B1GFitAttemptsError(reason, tuple(attempts), None) from error
        attempts[index] = replace(
            attempt,
            status="accepted",
            reason=None,
            diagnostics=diagnostics,
        )
        if index == 0:
            attempts[1] = replace(attempts[1], reason="initial_accepted")
        return B1GFitRun(fitted, tuple(attempts))
    raise AssertionError("B1G fit attempt loop ended without a result")
