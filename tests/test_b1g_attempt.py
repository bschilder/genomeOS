"""Prespecified B1G fit-attempt policy tests (global modeling plan WP2; #376)."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from genomeos.surfaces.config import FitConfig
from genomeos.surfaces.convergence import SamplerDiagnostics
from genomeos.validation.b1g_attempt import (
    B1GFitAttemptsError,
    run_b1g_fit_attempts,
    validate_b1g_fit_attempts,
)
from genomeos.validation.b1g_basis import B1GBasisConfig
from genomeos.validation.b1g_fit import B1GConvergenceError

GOOD = SamplerDiagnostics(1.0, "intercept", 300.0, "intercept", 300.0, "intercept", 0)
BAD_INITIAL = SamplerDiagnostics(1.08, "amplitude", 110.0, "amplitude", 90.0, "amplitude", 2)
BAD_RETRY = SamplerDiagnostics(1.06, "amplitude", 190.0, "amplitude", 180.0, "amplitude", 1)
BASIS = B1GBasisConfig(1000.0, 16)
CONFIG = FitConfig(draws=10, tune=20, chains=2, seed=42)


def _fit(diagnostics: SamplerDiagnostics = GOOD):
    return SimpleNamespace(sampler_diagnostics=diagnostics)


def test_accepted_initial_records_an_unused_retry_slot():
    calls = []

    def fit_function(training, *, basis_config, fit_config):
        calls.append((training, basis_config, fit_config))
        return _fit()

    result = run_b1g_fit_attempts(
        "training",
        basis_config=BASIS,
        fit_config=CONFIG,
        initial_seed=17,
        retry_seed=19,
        fit_function=fit_function,
    )

    assert result.fit.sampler_diagnostics == GOOD
    assert calls == [("training", BASIS, replace(CONFIG, seed=17))]
    assert tuple(attempt.status for attempt in result.attempts) == ("accepted", "not_attempted")
    assert result.attempts[0].diagnostics == GOOD
    assert result.attempts[1].reason == "initial_accepted"
    assert result.attempts[1].config == replace(CONFIG, draws=20, tune=40, seed=19)


def test_only_typed_convergence_failure_admits_the_doubled_budget_retry():
    calls = []

    def fit_function(training, *, basis_config, fit_config):
        calls.append((training, basis_config, fit_config))
        if len(calls) == 1:
            raise B1GConvergenceError("initial did not converge", BAD_INITIAL)
        return _fit()

    result = run_b1g_fit_attempts(
        "training",
        basis_config=BASIS,
        fit_config=CONFIG,
        initial_seed=17,
        retry_seed=19,
        fit_function=fit_function,
    )

    assert calls == [
        ("training", BASIS, replace(CONFIG, seed=17)),
        ("training", BASIS, replace(CONFIG, draws=20, tune=40, seed=19)),
    ]
    assert tuple(attempt.status for attempt in result.attempts) == (
        "convergence_failed",
        "accepted",
    )
    assert result.attempts[0].diagnostics == BAD_INITIAL
    assert result.attempts[1].diagnostics == GOOD


def test_failed_retry_retains_both_diagnostics_and_has_no_third_attempt():
    calls = []

    def fit_function(training, *, basis_config, fit_config):
        calls.append(fit_config)
        diagnostics = BAD_INITIAL if len(calls) == 1 else BAD_RETRY
        raise B1GConvergenceError("still did not converge", diagnostics)

    with pytest.raises(B1GFitAttemptsError, match="still did not converge") as captured:
        run_b1g_fit_attempts(
            "training",
            basis_config=BASIS,
            fit_config=CONFIG,
            initial_seed=17,
            retry_seed=19,
            fit_function=fit_function,
        )

    assert len(calls) == 2
    assert tuple(attempt.status for attempt in captured.value.attempts) == (
        "convergence_failed",
        "convergence_failed",
    )
    assert tuple(attempt.diagnostics for attempt in captured.value.attempts) == (
        BAD_INITIAL,
        BAD_RETRY,
    )
    assert captured.value.diagnostics == BAD_RETRY


@pytest.mark.parametrize("error", [ValueError("structure"), RuntimeError("runtime")])
def test_nonconvergence_errors_never_retry(error: Exception):
    calls = []

    def fit_function(training, *, basis_config, fit_config):
        calls.append(fit_config)
        raise error

    with pytest.raises(B1GFitAttemptsError, match=type(error).__name__) as captured:
        run_b1g_fit_attempts(
            "training",
            basis_config=BASIS,
            fit_config=CONFIG,
            initial_seed=17,
            retry_seed=19,
            fit_function=fit_function,
        )

    assert calls == [replace(CONFIG, seed=17)]
    assert tuple(attempt.status for attempt in captured.value.attempts) == (
        "failed",
        "not_attempted",
    )
    assert captured.value.attempts[1].reason == "initial_not_retryable"


def test_interruption_propagates_without_becoming_scientific_evidence():
    def interrupted(*_args, **_kwargs):
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        run_b1g_fit_attempts(
            "training",
            basis_config=BASIS,
            fit_config=CONFIG,
            initial_seed=17,
            retry_seed=19,
            fit_function=interrupted,
        )


def test_attempt_validator_binds_both_slots_to_the_frozen_config_and_seeds():
    result = run_b1g_fit_attempts(
        "training",
        basis_config=BASIS,
        fit_config=CONFIG,
        initial_seed=17,
        retry_seed=19,
        fit_function=lambda *_args, **_kwargs: _fit(),
    )

    assert validate_b1g_fit_attempts(
        result.attempts,
        fit_config=CONFIG,
        initial_seed=17,
        retry_seed=19,
    ) == 17
    malformed_retry = replace(
        result.attempts[1],
        config=replace(result.attempts[1].config, draws=21),
    )
    with pytest.raises(ValueError, match="configs contradict"):
        validate_b1g_fit_attempts(
            (result.attempts[0], malformed_retry),
            fit_config=CONFIG,
            initial_seed=17,
            retry_seed=19,
        )
