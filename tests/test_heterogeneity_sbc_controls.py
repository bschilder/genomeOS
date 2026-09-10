"""Prior-only scalar controls; no posterior or actual-study claim."""
from __future__ import annotations

from dataclasses import FrozenInstanceError, replace

import numpy as np
import pytest

from genomeos.validation import heterogeneity_sbc_controls as controls
from genomeos.validation.heterogeneity_diagnostic_seeds import DiagnosticSeedIdentity
from genomeos.validation.heterogeneity_sbc_controls import (
    DiagnosticCallError,
    PriorControlFailure,
    PriorControlResult,
    draw_prior_control,
)
from genomeos.validation.heterogeneity_simulation_types import SbcCaseId


def identity(track=0):
    return DiagnosticSeedIdentity(SbcCaseId(track, 0, 0, 0), 0, 8, (1,))


def stream(monkeypatch, values):
    values = iter(values)
    calls = []

    class ScalarStream:
        def beta(self, alpha, beta):
            calls.append((alpha, beta))
            result = next(values)
            if isinstance(result, BaseException):
                raise result
            return result

    monkeypatch.setattr(controls.np.random, "Generator", lambda bitgen: ScalarStream())
    return calls


@pytest.mark.parametrize("track,beta", ((0, 9.0), (1, 4.0)))
def test_four_scalar_pairs_in_fixed_order(monkeypatch, track, beta):
    values = (0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.875, 0.125)
    calls = stream(monkeypatch, values)
    result = draw_prior_control(seed=identity(track))
    assert calls == [(1.0, 1.0), (1.0, beta)] * 4
    assert result.pairs == tuple(zip(values[::2], values[1::2], strict=True))
    assert result.failure is None and result.status == "complete"
    assert result.seed == identity(track)


@pytest.mark.parametrize("track,beta", ((0, 9.0), (1, 4.0)))
def test_control_matches_literal_numpy_namespace(track, beta):
    entropy = (42, 211, 1, track, 0, 0, 0, 8, 0)
    rng = np.random.Generator(np.random.PCG64(np.random.SeedSequence(entropy, spawn_key=(1,))))
    expected = tuple((float(rng.beta(1.0, 1.0)), float(rng.beta(1.0, beta))) for chain in range(4))
    result = draw_prior_control(seed=identity(track))
    assert result.pairs == expected and result.failure is None


@pytest.mark.parametrize("bad,reason,retained,type_name", (
    (0.0, "rounded_boundary", 0.0, None),
    (1.0, "rounded_boundary", 1.0, None),
    (float("inf"), "invalid_scalar", float("inf"), None),
    (2**80 + 1, "invalid_scalar", 2**80 + 1, None),
    (True, "invalid_scalar", None, "builtins.bool"),
    ("0.2", "invalid_scalar", None, "builtins.str"),
))
def test_failure_retains_three_pairs_and_fourth_mean(monkeypatch, bad, reason, retained, type_name):
    prefix = (0.25, 0.125) * 3
    calls = stream(monkeypatch, (*prefix, 0.375, bad, 0.5))
    result = draw_prior_control(seed=identity())
    assert len(calls) == 8
    assert result.pairs == ((0.25, 0.125),) * 3
    failure = result.failure
    assert failure.chain == 3 and failure.parameter == "rho"
    assert failure.reason == reason and failure.sampled_mean == 0.375
    assert failure.sampled_rho == retained
    assert failure.returned_type == type_name and failure.error is None


def test_nan_is_numeric_evidence_and_endpoint_mean_stops_before_rho(monkeypatch):
    calls = stream(monkeypatch, (np.float64("nan"), 0.2))
    result = draw_prior_control(seed=identity())
    assert len(calls) == 1 and np.isnan(result.failure.sampled_mean)
    assert result.failure.sampled_rho is None and result.failure.error is None
    calls = stream(monkeypatch, (0, 0.2))
    result = draw_prior_control(seed=identity())
    assert len(calls) == 1 and result.failure.reason == "rounded_boundary"
    assert type(result.failure.sampled_mean) is int


@pytest.mark.parametrize("where", ("mean", "rho"))
def test_actual_unexpected_exception_is_retained(monkeypatch, where):
    values = (KeyError("actual"),) if where == "mean" else (0.25, KeyError("actual"))
    calls = stream(monkeypatch, values)
    result = draw_prior_control(seed=identity())
    assert len(calls) == (1 if where == "mean" else 2)
    assert result.failure.reason == "rng_exception"
    assert result.failure.parameter == where
    assert result.failure.error == DiagnosticCallError("builtins.KeyError", "'actual'")
    assert result.failure.sampled_mean == (None if where == "mean" else 0.25)
    assert result.failure.sampled_rho is None


def test_base_exception_and_bad_seed_propagate(monkeypatch):
    stream(monkeypatch, (KeyboardInterrupt(),))
    with pytest.raises(KeyboardInterrupt):
        draw_prior_control(seed=identity())
    with pytest.raises(ValueError):
        draw_prior_control(seed=DiagnosticSeedIdentity(SbcCaseId(0, 0, 0, 0), 0, 5, (0,)))


def test_control_constructor_refuses_fabricated_completion():
    error = DiagnosticCallError("builtins.RuntimeError", "")
    failure = PriorControlFailure(3, "rho", "rng_exception", 0.25, None, None, error)
    result = PriorControlResult(identity(), ((0.25, 0.125),) * 3, failure)
    assert result.status == "failed"
    with pytest.raises(ValueError):
        replace(result, pairs=((0.25, 0.125),) * 4)
    with pytest.raises(ValueError):
        replace(result, failure=None)
    for changes in ({"chain": True}, {"sampled_rho": 0.2}, {"returned_type": "builtins.float"}):
        with pytest.raises(ValueError):
            replace(failure, **changes)
    with pytest.raises(ValueError):
        PriorControlFailure(0, "rho", "rounded_boundary", None, 0.0, None, None)
    with pytest.raises(ValueError):
        PriorControlFailure(0, "mean", "invalid_scalar", 0.25, None, None, None)
    with pytest.raises(FrozenInstanceError):
        result.pairs = ()
