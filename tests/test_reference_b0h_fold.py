"""Synthetic B0H fold dispatch/refusal tests (design §§5, 7–8, 12)."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest
from reference_b0h_synthetic import synthetic_fit, synthetic_rows

import genomeos.validation.reference_b0h_fold as subject
from genomeos.surfaces.heterogeneity_types import (
    HeterogeneityConvergenceError,
    PopulationHeterogeneityConfig,
    VariantHeterogeneityDiagnostics,
)


def execute(monkeypatch, **overrides):
    monkeypatch.setattr(subject, "fit_reference_population_heterogeneity", synthetic_fit)
    rows = synthetic_rows()
    arguments = dict(
        config=PopulationHeterogeneityConfig(1, 1, 1, 9, draws=2, tune=3),
        initial_seed=17, retry_seed=19, pit_seed=23, cdf_backend="scipy",
    )
    arguments.update(overrides)
    return subject.run_b0h_fold(rows[3:], rows[:3], **arguments)


def test_seed_stream_is_literal_third_child():
    split, pit, pairs = subject.b0h_seeds(42)
    legacy_split, legacy_pit = np.random.SeedSequence(42).spawn(2)
    def integer(child):
        return int(child.generate_state(1, dtype=np.uint32)[0])

    assert split == integer(legacy_split)
    assert pit == tuple(integer(child) for child in legacy_pit.spawn(5))
    third = np.random.SeedSequence(42).spawn(3)[2]
    assert pairs == tuple(tuple(integer(child) for child in fold.spawn(2)) for fold in third.spawn(5))


def test_accepted_initial_records_unused_retry(monkeypatch):
    result = execute(monkeypatch)
    assert result.status == "completed"
    assert result.failure_phase is result.reason is None
    assert result.fit.config.seed == 17
    assert result.attempts[0].status == "accepted"
    assert result.attempts[1].reason == "initial_accepted"
    assert result.attempts[1].config.draws == 4
    assert result.attempts[1].config.tune == 6
    assert len(result.diagnostics) == 3


def test_only_typed_fit_convergence_failure_retries(monkeypatch):
    execute(monkeypatch)
    calls = []
    partial = (VariantHeterogeneityDiagnostics("NA", 1.2, 120.0, 100.0),)

    def fit(training, *, config):
        calls.append((tuple(training), config))
        if len(calls) == 1:
            raise HeterogeneityConvergenceError("synthetic partial failure", diagnostics=partial)
        return synthetic_fit(training, config=config)

    monkeypatch.setattr(subject, "fit_reference_population_heterogeneity", fit)
    rows = synthetic_rows()
    config = PopulationHeterogeneityConfig(1, 1, 1, 9, draws=2, tune=3)
    result = subject.run_b0h_fold(
        rows[3:], rows[:3], config=config, initial_seed=17, retry_seed=19,
        pit_seed=23, cdf_backend="scipy",
    )
    assert result.status == "completed"
    assert calls[0][0] == calls[1][0] == rows[3:]
    assert calls[0][1] == replace(config, seed=17)
    assert calls[1][1] == replace(config, draws=4, tune=6, seed=19)
    assert result.attempts[0].diagnostics == partial
    assert result.attempts[0].divergence_count is None
    assert result.attempts[1].status == "accepted"
    assert result.fit.mean_draws.shape == (4, 4, 3)


@pytest.mark.parametrize("error", [ValueError("structure"), ArithmeticError("domain")])
def test_structural_and_numeric_fit_failures_do_not_retry(monkeypatch, error):
    execute(monkeypatch)
    calls = []

    def fail(training, *, config):
        calls.append(config)
        raise error

    monkeypatch.setattr(subject, "fit_reference_population_heterogeneity", fail)
    result = subject.run_b0h_fold(
        synthetic_rows()[3:], synthetic_rows()[:3],
        config=PopulationHeterogeneityConfig(1, 1, 1, 9, draws=2, tune=3),
        initial_seed=17, retry_seed=19, pit_seed=23, cdf_backend="scipy",
    )
    assert len(calls) == 1
    assert result.status == "failed" and result.failure_phase == "fit"
    assert result.fit is result.prediction is result.diagnostics is None
    assert result.attempts[1].reason == "initial_not_retryable"


@pytest.mark.parametrize("phase", ["prediction", "scoring"])
def test_later_failure_retains_accepted_fit_without_retry(monkeypatch, phase):
    execute(monkeypatch)
    name = ("predict_reference_population_heterogeneity" if phase == "prediction"
            else "predictive_diagnostics")

    def fail(*args, **kwargs):
        raise HeterogeneityConvergenceError("synthetic later error")

    monkeypatch.setattr(subject, name, fail)
    result = subject.run_b0h_fold(
        synthetic_rows()[3:], synthetic_rows()[:3],
        config=PopulationHeterogeneityConfig(1, 1, 1, 9, draws=2, tune=3),
        initial_seed=17, retry_seed=19, pit_seed=23, cdf_backend="scipy",
    )
    assert result.status == "failed" and result.failure_phase == phase
    assert result.fit is not None
    assert result.prediction is result.diagnostics is None
    assert tuple(attempt.status for attempt in result.attempts) == ("accepted", "not_attempted")


def test_unavailable_preflight_and_interruption(monkeypatch):
    execute(monkeypatch)
    rows = synthetic_rows()
    kwargs = dict(config=PopulationHeterogeneityConfig(1, 1, 1, 9, draws=2),
                  initial_seed=17, retry_seed=19, pit_seed=23, cdf_backend="scipy")
    missing = tuple(replace(row, ac=0, an=0) for row in rows[:3])
    result = subject.run_b0h_fold(rows[3:], missing, **kwargs)
    assert result.status == "infeasible" and result.failure_phase == "preflight"
    assert result.unavailable_ids == tuple(row.record_id for row in missing)
    assert [item.reason for item in result.attempts] == [
        "fold_preflight_infeasible", "initial_not_attempted",
    ]

    def interrupted(*args, **kwargs):
        raise RuntimeError("synthetic interruption")

    monkeypatch.setattr(subject, "fit_reference_population_heterogeneity", interrupted)
    with pytest.raises(RuntimeError, match="synthetic interruption"):
        subject.run_b0h_fold(rows[3:], rows[:3], **kwargs)


def test_scoring_validation_and_identity_failures_are_atomic(monkeypatch):
    execute(monkeypatch)
    real = subject.predictive_diagnostics

    def invalid(*args, **kwargs):
        frame = real(*args, **kwargs)
        frame.loc[0, "randomized_pit"] = 1.1
        return frame

    monkeypatch.setattr(subject, "predictive_diagnostics", invalid)
    result = execute(monkeypatch)
    assert result.failure_phase == "scoring"
    assert result.fit is not None and result.diagnostics is None
    monkeypatch.setattr(subject, "predictive_diagnostics", real)
    predict = subject.predict_reference_population_heterogeneity

    def wrong(*args, **kwargs):
        value = predict(*args, **kwargs)
        return replace(value, observation_ids=tuple(reversed(value.observation_ids)))

    monkeypatch.setattr(subject, "predict_reference_population_heterogeneity", wrong)
    result = execute(monkeypatch)
    assert result.failure_phase == "prediction"
    assert result.fit is not None and result.prediction is None


def test_test_counts_do_not_enter_fit_and_training_only_variants_are_retained(monkeypatch):
    calls = []

    def fit(training, *, config):
        calls.append((tuple(training), config))
        return synthetic_fit(training, config=config)

    monkeypatch.setattr(subject, "fit_reference_population_heterogeneity", fit)
    rows = synthetic_rows()
    arguments = dict(config=PopulationHeterogeneityConfig(1, 1, 1, 9, draws=2),
                     initial_seed=17, retry_seed=19, pit_seed=23, cdf_backend="scipy")
    first = subject.run_b0h_fold(rows[3:], (replace(rows[0], ac=0),), **arguments)
    second = subject.run_b0h_fold(rows[3:], (replace(rows[0], ac=4),), **arguments)
    assert calls[0] == calls[1]
    assert first.fit.variant_ids == second.fit.variant_ids == ("001", "NA", "é:/v")
    assert np.array_equal(first.fit.mean_draws, second.fit.mean_draws)
    assert first.prediction.observation_ids == second.prediction.observation_ids == (rows[0].record_id,)


def test_backend_forwarding_has_no_fallback(monkeypatch):
    execute(monkeypatch)
    backends = []

    def missing_backend(fitted, testing, *, cdf_backend):
        backends.append(cdf_backend)
        raise RuntimeError("synthetic unavailable CUDA")

    monkeypatch.setattr(subject, "predict_reference_population_heterogeneity", missing_backend)
    with pytest.raises(RuntimeError, match="synthetic unavailable CUDA"):
        execute(monkeypatch, cdf_backend="cupy")
    assert backends == ["cupy"]


def test_absent_training_variant_is_infeasible_with_accepted_fit_retained(monkeypatch):
    execute(monkeypatch)
    rows = synthetic_rows()
    training = tuple(row for row in rows[3:] if row.variant_id == "001")
    result = subject.run_b0h_fold(
        training, (rows[1],), config=PopulationHeterogeneityConfig(1, 1, 1, 9, draws=2),
        initial_seed=17, retry_seed=19, pit_seed=23, cdf_backend="scipy",
    )
    assert result.status == "infeasible" and result.failure_phase == "prediction"
    assert result.fit.variant_ids == ("001",)
    assert result.prediction is result.diagnostics is None
    assert [attempt.status for attempt in result.attempts] == ["accepted", "not_attempted"]
