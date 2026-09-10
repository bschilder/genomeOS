# Reference-count B0H Integration Implementation Plan

**Status:** Root-adopted on 2026-09-10 for fixture-backed integration, using
subagent-driven development. No real-fit or calibration admission is implied.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Root owns execution and chooses the mode; this neutral draft authorizes neither execution nor delegation.

**Goal:** Add the approved B0H comparison dispatch and immutable evidence contract to the existing offline reference-count runner while preserving pooled B0 scientific outputs.

**Architecture:** A pure fold adapter owns the convergence-only retry and complete-fold scoring boundary. A byte-oriented serializer owns diagnostics/posteriors; a small provenance adapter verifies source origins and runtime metadata. The existing CLI keeps its B0 branch, parsing, dependency-aware folds, row ledger and summaries.

**Tech Stack:** Existing Python, NumPy, pandas, SciPy and surfaces-extra PyMC/NumPyro; standard-library JSON/ZIP/NPY serialization. No new dependency.

**Spec:** `docs/superpowers/specs/2026-09-10-reference-count-b0h-integration-design.md`, root-adopted §§1–7; parent `docs/superpowers/specs/2026-09-10-population-heterogeneity-design.md`; Atlas §§5, 7–8, 12.

## Global Constraints

- Model identifier: `B0H_population_heterogeneity`; target: `reference_panel_within_resource`.
- No new package dependency, P1/production schema, serving change, inferred coordinate or radius.
- Pure science modules have no filesystem, network, HTTP, environment or UI dependency.
- Stochastic modules declare `SEED = 42`; inputs and configuration determine draws on a pinned runtime.
- All real counts, posterior draws and per-row predictions remain local and untracked.
- AN=0 is retained as unavailable, never converted to frequency zero.
- Fitting consumes training rows only; prediction rejects training group/record overlap.
- No cross-variant parameter pooling, LD likelihood, independent-locus or joint-site prediction claim.
- No clipping, silent fallback, relaxed scoring domain, or discarded failed variant/fold.
- Convergence requires four or more chains, zero divergences, finite rank-normalized R-hat <=1.05, and finite bulk and tail ESS >=200 for both mean and rho in every fitted variant.
- Keep existing clinical gates and global promotion defaults unchanged.
- B0H requires five folds; B0 retains its current fold validation.
- B0 accepts omitted/explicit SciPy only; reject explicit CuPy and all explicitly supplied rho/sampler flags even when equal to B0H defaults.
- B0H default draws=500, tune=1000, chains=4, target_accept=0.9; existing prior flags specify mean prior, both rho flags are required.
- Preserve the two B0 seed streams. B0H uses child 2 of a fresh `SeedSequence(root).spawn(3)`, five fold children, then initial/retry children.
- Only the fit call's typed `HeterogeneityConvergenceError` permits one retry, doubling only draws/tune.
- Retain every accepted fit, including a fold that later fails prediction/scoring. Such folds publish no prediction rows.
- B0 uses the unchanged six-file manifest-v1 contract; B0H uses the exact eight-file manifest-v2, diagnostics-v1, deterministic NPZ and TSV contracts in the spec.
- Immutable exclusive output directory, manifest last, no overwrite/resume/recovery. Runtime interruptions do not become scientific fold failures.
- No SBC executor, record, codec, store or runner dependency. No access to its implementation checkout or private directories.
- This plan advances #211/#189 without closing either; calibration and both fixed-prior real comparison tracks remain separate admission steps.

## Source basis and execution boundary

Read-only baseline: commit `b2f770078acd245abd96a14a5568e2b0a8bc92ff` in the root-provided stable checkout. `scripts/benchmark_reference_counts.py` has 368 physical lines; public types 262 and fitter 301. #211 and #189 were read through GitHub and are open. Read `AGENTS.md`, overview, scientific objectives, Atlas design, parent B0H design, root-adopted integration design and corrected audit before implementation. Do not inspect private directories or unrelated SBC implementation.

Scientific contract before choosing methods: the eventual claim is improved withheld-count prediction from source-population heterogeneity. This implementation's measurable evidence is deterministic synthetic dispatch/refusal/artifact tests, not calibration or improvement. Its public engineering boundary remains the existing offline CLI and B0H fit/predict functions. It assumes predeclared dependence and training-only data; unavailable evidence, numerical/convergence failures and runtime interruptions remain distinct. Consumers are offline research reviewers only.

Root adopts this plan beside the already adopted spec on its separate PR branch. Execute only in the branch/checkout root selects, preserve unrelated changes, and compare the source anchors before applying edits. Every task is independently reviewable and ends with focused tests, mandatory smoke/static/privacy checks and its own coherent commit. No task below launches a real fit: synthetic mocks verify composition only. Existing real synthetic NUTS/oracle and separate calibration gates remain mandatory in their own admitted verification workflow.

The four file responsibilities are fixed:

| Task | Production files | Responsibility |
| --- | --- | --- |
| 1 | `genomeos/validation/reference_b0h_fold.py` | Pure typed attempts, fit/predict/scoring failure boundary and seeds |
| 2 | `genomeos/validation/reference_b0h_artifacts.py` | Pure deterministic bytes and strict reader; no path I/O |
| 3 | `scripts/reference_b0h_provenance.py` | Imported source origins, required distributions and honest runtime records |
| 4 | `scripts/benchmark_reference_counts.py` | Conditional CLI composition and manifest-last publication |

Use this environment for each future verification shell (do not run during planning):

```bash
export PYTHONPATH=.
export PYTHONDONTWRITEBYTECODE=1
export PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor
export MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib
export B0H_PYTHON=/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python
export B0H_RUFF=/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/ruff
```

## Task 1: Pure complete-fold execution and attempt evidence

**Files:** Create `genomeos/validation/reference_b0h_fold.py`; create `tests/reference_b0h_synthetic.py`; create `tests/test_reference_b0h_fold.py`.

**Scientific contract:** Preserve every attempted fit and the training-only comparison boundary. Acceptance is synthetic tests of exact seeds, budget changes, retry classification, unavailable rows and accepted-fit retention; no mock is convergence evidence. The component is a pure fold function for the CLI and serializer. Structural/numerical errors refuse one fold; dependency failures and generic runtime interruptions escape.

**Interfaces:** Consumes the existing public `PopulationHeterogeneityConfig`, `PopulationHeterogeneityFit`, `ReferenceHeterogeneityPrediction`, `VariantHeterogeneityDiagnostics`, `ReferenceCount`, `predictive_diagnostics` and `validate_predictive_diagnostics`. Produces `B0HAttempt`, `B0HFoldResult`, `b0h_seeds(seed: int) -> tuple[int, tuple[int, ...], tuple[tuple[int, int], ...]]`, and `run_b0h_fold(training: Sequence[ReferenceCount], testing: Sequence[ReferenceCount], *, config: PopulationHeterogeneityConfig, initial_seed: int, retry_seed: int, pit_seed: int, cdf_backend: Literal['scipy', 'cupy']) -> B0HFoldResult`. `result.diagnostics` is a validated, complete test-row frame only on completion; `result.fit` survives subsequent failures. `result.prediction` is retained only on completion. Serialization consumes all fields except the score frame/predictor.

- [ ] Write the complete synthetic fixture module first. This fixture intentionally fabricates accepted arrays and diagnostic values to test structure; it never represents a sampler run.

```python
"""Synthetic structural fixtures for B0H integration; never calibration evidence."""

from __future__ import annotations

import numpy as np

from genomeos.surfaces.heterogeneity_types import (
    PopulationHeterogeneityFit,
    VariantHeterogeneityDiagnostics,
    VariantTrainingCounts,
)
from genomeos.validation.reference_counts import ReferenceCount


def synthetic_rows(groups=6, variants=("001", "NA", "é:/v")):
    return tuple(
        ReferenceCount(f"g{g}:{v}", v, f"g{g}", "synthetic-region", "synthetic-block", 1, 4)
        for g in range(groups) for v in variants
    )


def synthetic_fit(training, *, config):
    available = tuple(row for row in training if row.an > 0)
    variants = tuple(sorted({row.variant_id for row in available}))
    shape = (config.chains, config.draws, len(variants))
    return PopulationHeterogeneityFit(
        config, variants, np.full(shape, 0.25), np.full(shape, 0.1),
        tuple(sorted(row.record_id for row in training)),
        tuple(sorted({row.group_id for row in training})),
        tuple(sorted(row.record_id for row in training if row.an == 0)),
        tuple(VariantTrainingCounts(
            variant, sum(row.variant_id == variant for row in available),
            sum(row.ac for row in available if row.variant_id == variant),
            sum(row.an for row in available if row.variant_id == variant),
        ) for variant in variants),
        tuple(VariantHeterogeneityDiagnostics(v, 1.01, 300.0, 250.0) for v in variants),
        0,
    )
```

- [ ] Write the complete failing tests in `tests/test_reference_b0h_fold.py`.

```python
"""Synthetic B0H fold dispatch/refusal tests (design §§5, 7–8, 12)."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

import genomeos.validation.reference_b0h_fold as subject
from genomeos.surfaces.heterogeneity_types import (
    HeterogeneityConvergenceError,
    PopulationHeterogeneityConfig,
    VariantHeterogeneityDiagnostics,
)
from reference_b0h_synthetic import synthetic_fit, synthetic_rows


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
```

- [ ] Run red: `"$B0H_PYTHON" -m pytest -o addopts='' -q tests/test_reference_b0h_fold.py`. Expected collection failure: the new fold module is missing.

- [ ] Add the complete production module.

```python
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
```

- [ ] Green and commit, from the selected implementation checkout:

```bash
"$B0H_RUFF" check --select I --fix genomeos/validation/reference_b0h_fold.py tests/reference_b0h_synthetic.py tests/test_reference_b0h_fold.py
"$B0H_PYTHON" -m pytest -o addopts='' -q tests/test_reference_b0h_fold.py tests/test_reference_heterogeneity.py
"$B0H_PYTHON" scripts/smoke.py
"$B0H_RUFF" check .
"$B0H_PYTHON" scripts/check_module_size.py
"$B0H_PYTHON" scripts/check_private_files.py
git diff --check
git add genomeos/validation/reference_b0h_fold.py tests/reference_b0h_synthetic.py tests/test_reference_b0h_fold.py
git diff --cached --name-only
git diff --cached --check
"$B0H_PYTHON" scripts/check_private_files.py
git commit -m "feat: retain B0H fold attempts and accepted fits" -m "Advance #211 and #189 with synthetic integration evidence only."
```

Expected: focused tests and all gates pass; staged paths contain only these three files. Stop on any failure or private path. Do not close #211: calibration and real comparisons remain outstanding.

## Task 2: Deterministic B0H evidence bytes and strict publication reader

**Files:** Create `genomeos/validation/reference_b0h_artifacts.py`; create `tests/test_reference_b0h_artifacts.py`.

**Scientific contract:** Make accepted posterior evidence and failed-fold status jointly inspectable without inventing missing diagnostics. Acceptance is exact byte repetition, literal Unicode/shape/totals reconciliation and corruption refusal. The serializer is a pure bytes adapter for the CLI and offline artifact consumers; it fits/scores nothing and never reads a filesystem path. The publication reader distinguishes a valid incomplete comparison from interrupted publication.

**Interfaces:** Consumes Task 1's `B0HFoldResult` in the returned five-fold order. Produces `MODEL: str`, `B0H_POSTERIOR_COLUMNS: tuple[str, ...]`, `B0H_OUTPUT_FILENAMES: tuple[str, ...]`, `json_bytes(value: object) -> bytes`, `fingerprint(data: bytes) -> dict[str, object]`, `encode_b0h(folds: Sequence[tuple[str, B0HFoldResult]]) -> tuple[bytes, bytes, pd.DataFrame]` (diagnostics JSON, NPZ, posterior frame), and `validate_b0h_publication(files: Mapping[str, bytes]) -> dict[str, np.ndarray]`. The final reader consumes exactly eight filenames and returns verified posterior arrays keyed by unsanitized positional prefixes. No production caller imports test fixtures.

- [ ] Add complete failing tests.

```python
"""Synthetic immutable B0H wire tests (design §§5, 7–8, 12)."""

from __future__ import annotations

import io
import json
import zipfile
from dataclasses import replace

import numpy as np
import pytest

import genomeos.validation.reference_b0h_artifacts as subject
from genomeos.surfaces.heterogeneity_types import PopulationHeterogeneityConfig
from genomeos.validation.reference_b0h_fold import B0HAttempt, B0HFoldResult
from reference_b0h_synthetic import synthetic_fit, synthetic_rows


def synthetic_results():
    config = PopulationHeterogeneityConfig(1, 1, 1, 9, draws=2, tune=3, seed=17)
    fit = synthetic_fit(synthetic_rows(), config=config)
    accepted = B0HAttempt("initial", config, "accepted", None, 0, fit.diagnostics)
    retry = B0HAttempt("retry", replace(config, draws=4, tune=6, seed=19),
                      "not_attempted", "initial_accepted")
    return tuple((f"split:{i}/é", B0HFoldResult(
        "failed", "scoring", "ValueError: synthetic scoring refusal", (accepted, retry),
        fit, None, None, (),
    )) for i in range(5))


def synthetic_publication(results=None):
    results = synthetic_results() if results is None else results
    diagnostics, draws, posteriors = subject.encode_b0h(results)
    configuration = {
        "source_release": "synthetic", "cohort_stage": "synthetic", "count_kind": "quality",
        "evidence_role": "synthetic", "prior_alpha": 1.0, "prior_beta": 1.0, "folds": 5,
        "seed": 42, "model": subject.MODEL, "rho_prior_alpha": 1.0, "rho_prior_beta": 9.0,
        "draws": 2, "tune": 3, "chains": 4, "target_accept": 0.9, "cdf_backend": "scipy",
    }
    files = {name: b"synthetic supporting file\n" for name in subject.B0H_OUTPUT_FILENAMES}
    files.update({
        "fit_diagnostics.json": diagnostics, "posterior_draws.npz": draws,
        "posteriors.tsv": posteriors.to_csv(sep="\t", index=False, lineterminator="\n").encode(),
        "splits.json": subject.json_bytes({"folds": [
            {"split_id": split_id, "status": result.status} for split_id, result in results
        ]}),
        "summary.json": subject.json_bytes({"comparison_complete": False}),
    })
    unavailable = {"status": "unavailable", "value": None, "reason": "synthetic unobserved"}
    manifest = {
        "schema_version": 2, "model": subject.MODEL, "target": "reference_panel_within_resource",
        "joint_prediction_supported": False, "limitations": ["synthetic only"],
        "configuration": configuration, "dependency_qualification": "synthetic",
        "input_files": {name: subject.fingerprint(b"synthetic input")
                        for name in ("counts", "dependencies")},
        "git": {"head": "0" * 40, "dirty": False},
        "science_source_sha256": {"synthetic/source.py": "0" * 64},
        "package_versions": {name: "synthetic-version" for name in (
            "numpy", "scipy", "pandas", "pymc", "pytensor", "arviz", "xarray", "numpyro", "jax", "jaxlib",
        )},
        "runtime": {key: unavailable for key in ("python_version", "jax_backend", "cdf_backend")},
        "seeds": {"root": 42, "split": 1,
                  "pit_by_fold": {key: 23 for key, result in results},
                  "fit_by_fold": {key: {"initial": 17, "retry": 19} for key, result in results}},
        "output_files": {key: subject.fingerprint(value) for key, value in files.items()},
    }
    files["manifest.json"] = subject.json_bytes(manifest)
    return files


def refresh(files, name, data):
    files[name] = data
    manifest = json.loads(files["manifest.json"])
    manifest["output_files"][name] = subject.fingerprint(data)
    files["manifest.json"] = subject.json_bytes(manifest)


def test_exact_repeatable_bytes_unicode_and_retained_failed_folds():
    first = synthetic_publication()
    assert first == synthetic_publication()
    arrays = subject.validate_b0h_publication(first)
    assert len(arrays) == 15
    ids = arrays["fold_0000__variant_ids"]
    assert ids.dtype.str == "<U4" and ids.tolist() == ["001", "NA", "é:/v"]
    assert arrays["fold_0000__mean_draws"].shape == (4, 2, 3)
    assert arrays["fold_0000__mean_draws"].dtype.str == "<f8"
    diagnostics = json.loads(first["fit_diagnostics.json"])
    assert [fold["split_id"] for fold in diagnostics["folds"]] == [key for key, result in synthetic_results()]
    assert all(fold["status"] == "failed" and fold["posterior_status"] == "retained"
               for fold in diagnostics["folds"])
    with zipfile.ZipFile(io.BytesIO(first["posterior_draws.npz"])) as archive:
        assert archive.namelist() == sorted(archive.namelist())
        for item in archive.infolist():
            assert item.date_time == (1980, 1, 1, 0, 0, 0)
            assert item.compress_type == zipfile.ZIP_STORED
            assert item.create_system == 3 and item.external_attr == 0o600 << 16
            assert item.internal_attr == item.flag_bits == 0
            assert item.create_version == item.extract_version == 20
            assert item.extra == item.comment == b""
            assert archive.read(item)[:8] == b"\x93NUMPY\x01\x00"
    _, _, frame = subject.encode_b0h(synthetic_results())
    assert tuple(frame.columns) == subject.B0H_POSTERIOR_COLUMNS
    assert set(frame.training_ac) == {6} and set(frame.training_an) == {24}
    assert set(frame.training_observation_count) == {6}
    assert np.allclose(frame.posterior_mean_mean, 0.25)
    assert np.allclose(frame.posterior_rho_mean, 0.1)


def test_empty_accepted_set_is_valid_empty_archive():
    records = []
    for split, result in synthetic_results():
        initial = replace(result.attempts[0], status="failed", reason="ValueError: synthetic",
                          diagnostics=(), divergence_count=None)
        retry = replace(result.attempts[1], reason="initial_not_retryable")
        records.append((split, replace(result, failure_phase="fit", fit=None,
                                       attempts=(initial, retry))))
    files = synthetic_publication(tuple(records))
    assert subject.validate_b0h_publication(files) == {}
    assert files["posteriors.tsv"].decode().splitlines() == ["\t".join(subject.B0H_POSTERIOR_COLUMNS)]


def test_accepted_retry_uses_its_own_dimensions_and_keeps_failed_initial():
    records = []
    for split, result in synthetic_results():
        initial = replace(result.attempts[0], status="convergence_failed",
                          reason="synthetic initial divergence", divergence_count=1)
        fit = synthetic_fit(synthetic_rows(), config=result.attempts[1].config)
        retry = replace(result.attempts[1], status="accepted", reason=None,
                        divergence_count=0, diagnostics=fit.diagnostics)
        records.append((split, replace(result, fit=fit, attempts=(initial, retry))))
    files = synthetic_publication(tuple(records))
    arrays = subject.validate_b0h_publication(files)
    assert arrays["fold_0000__mean_draws"].shape == (4, 4, 3)
    initial = json.loads(files["fit_diagnostics.json"])["folds"][0]["attempts"][0]
    assert initial["status"] == "convergence_failed" and initial["divergence_count"] == 1


@pytest.mark.parametrize("mode", ["missing", "extra", "hash", "schema", "mapping", "diagnostic"])
def test_publication_corruption_is_refused(mode):
    files = synthetic_publication()
    if mode == "missing":
        del files["manifest.json"]
    elif mode == "extra":
        files["extra"] = b"synthetic"
    elif mode == "hash":
        files["posterior_draws.npz"] += b"synthetic corruption"
    elif mode == "schema":
        manifest = json.loads(files["manifest.json"])
        manifest["schema_version"] = 1
        files["manifest.json"] = subject.json_bytes(manifest)
    else:
        document = json.loads(files["fit_diagnostics.json"])
        if mode == "mapping":
            document["folds"][0]["posterior_prefix"] = "fold_0001"
        else:
            document["folds"][0]["attempts"][0]["diagnostics"][0]["max_rhat"] = 1.2
        refresh(files, "fit_diagnostics.json", subject.json_bytes(document))
    with pytest.raises((ValueError, KeyError)):
        subject.validate_b0h_publication(files)


@pytest.mark.parametrize("mode", ["object", "extra", "missing", "duplicate", "float32", "shape", "ids"])
def test_npz_corruption_even_with_updated_fingerprint_is_refused(mode):
    files = synthetic_publication()
    with np.load(io.BytesIO(files["posterior_draws.npz"]), allow_pickle=False) as loaded:
        arrays = {key: loaded[key] for key in loaded.files}
    key = "fold_0000__mean_draws"
    if mode == "object":
        arrays[key] = np.array(["synthetic"], dtype=object)
    elif mode == "extra":
        arrays["extra"] = np.zeros(1)
    elif mode == "missing":
        del arrays[key]
    elif mode == "float32":
        arrays[key] = arrays[key].astype(np.float32)
    elif mode == "shape":
        arrays[key] = arrays[key].reshape(8, 3)
    elif mode == "ids":
        arrays["fold_0000__variant_ids"] = np.array(["NA", "001", "é:/v"])
    buffer = io.BytesIO()
    np.savez(buffer, **arrays)
    if mode == "duplicate":
        with zipfile.ZipFile(buffer, "a") as archive:
            with pytest.warns(UserWarning, match="Duplicate name"):
                archive.writestr(key + ".npy", archive.read(key + ".npy"))
    refresh(files, "posterior_draws.npz", buffer.getvalue())
    with pytest.raises(ValueError):
        subject.validate_b0h_publication(files)
```

- [ ] Run red: `"$B0H_PYTHON" -m pytest -o addopts='' -q tests/test_reference_b0h_artifacts.py`. Expected missing-module collection error.

- [ ] Add this complete production module. The reader checks declared manifest and fold mappings plus exact archive members; original input rows are not available to a standalone byte reader, so source-truth verification of the recorded totals remains the fold/public-fit contract and tests.

```python
"""Pure B0H evidence serialization and reading (design §§5, 7–8, 12; integration §§4–7)."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from math import isfinite
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

if TYPE_CHECKING:
    from genomeos.validation.reference_b0h_fold import B0HFoldResult

MODEL = "B0H_population_heterogeneity"
B0H_POSTERIOR_COLUMNS = (
    "split_id", "variant_id", "training_observation_count", "training_ac", "training_an",
    "posterior_mean_mean", "posterior_rho_mean",
)
B0H_OUTPUT_FILENAMES = (
    "splits.json", "row_status.tsv", "predictions.tsv", "posteriors.tsv", "summary.json",
    "fit_diagnostics.json", "posterior_draws.npz",
)
FOLD_KEYS = set("split_id status failure_phase reason posterior_status posterior_prefix attempts".split())
ATTEMPT_KEYS = set(
    "attempt seed draws tune chains target_accept status reason divergence_count diagnostics".split()
)
DIAGNOSTIC_KEYS = set("variant_id max_rhat min_bulk_ess min_tail_ess".split())
MANIFEST_KEYS = set(
    "schema_version target joint_prediction_supported limitations configuration dependency_qualification "
    "input_files seeds git science_source_sha256 package_versions output_files model runtime".split()
)
CONFIGURATION_KEYS = set(
    "source_release cohort_stage count_kind evidence_role prior_alpha prior_beta folds seed model "
    "rho_prior_alpha rho_prior_beta draws tune chains target_accept cdf_backend".split()
)


def json_bytes(value: object) -> bytes:
    text = json.dumps(value, allow_nan=False, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    return text.encode("utf-8")


def fingerprint(data: bytes) -> dict[str, object]:
    return {"sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _text(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _integer(value, minimum=0) -> bool:
    return type(value) is int and value >= minimum


def _finite(value) -> bool:
    return type(value) in (int, float) and isfinite(value)


def _hex(value, length) -> bool:
    return (isinstance(value, str) and len(value) == length
            and all(char in "0123456789abcdef" for char in value))


def _object(value, keys, name):
    _require(isinstance(value, dict) and set(value) == keys, f"invalid {name} fields")


def _json(data):
    def pairs(items):
        result = {}
        for key, value in items:
            _require(key not in result, "duplicate JSON object key")
            result[key] = value
        return result

    def constant(value):
        raise ValueError(f"nonfinite JSON constant: {value}")

    return json.loads(data.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)


def _validate_diagnostics(document, manifest):
    _object(document, {"schema_version", "model", "folds"}, "diagnostics")
    _require(type(document["schema_version"]) is int and document["schema_version"] == 1
             and document["model"] == MODEL, "invalid diagnostics schema/model")
    folds = document["folds"]
    _require(isinstance(folds, list) and len(folds) == 5, "expected five diagnostic folds")
    split_ids = [fold["split_id"] for fold in folds]
    _require(all(_text(item) for item in split_ids) and len(set(split_ids)) == 5,
             "invalid diagnostic split identities")
    _require(set(manifest["seeds"]["fit_by_fold"]) == set(split_ids), "fit seed split mismatch")
    _require(set(manifest["seeds"]["pit_by_fold"]) == set(split_ids), "PIT seed split mismatch")
    config = manifest["configuration"]
    for index, fold in enumerate(folds):
        _object(fold, FOLD_KEYS, "fold")
        _require(fold["status"] in {"completed", "infeasible", "failed"}, "invalid fold state")
        completed = fold["status"] == "completed"
        _require((fold["reason"] is None and fold["failure_phase"] is None) if completed else
                 (_text(fold["reason"])
                  and fold["failure_phase"] in {"preflight", "fit", "prediction", "scoring"}),
                 "invalid fold failure")
        attempts = fold["attempts"]
        _require(isinstance(attempts, list) and len(attempts) == 2, "expected two attempt slots")
        seeds = manifest["seeds"]["fit_by_fold"][fold["split_id"]]
        _object(seeds, {"initial", "retry"}, "fit seeds")
        for number, attempt in enumerate(attempts):
            _object(attempt, ATTEMPT_KEYS, "attempt")
            label = ("initial", "retry")[number]
            _require(attempt["attempt"] == label and _integer(attempt["seed"])
                     and attempt["seed"] == seeds[label], "attempt seed/name mismatch")
            for name in ("draws", "tune"):
                _require(_integer(attempt[name], 1) and attempt[name] == config[name] * (number + 1),
                         "attempt budget mismatch")
            _require(_integer(attempt["chains"], 4) and attempt["chains"] == config["chains"],
                     "attempt chains mismatch")
            _require(_finite(attempt["target_accept"]) and 0 < attempt["target_accept"] < 1
                     and attempt["target_accept"] == config["target_accept"], "attempt target mismatch")
            status = attempt["status"]
            _require(status in {"not_attempted", "accepted", "convergence_failed", "infeasible", "failed"},
                     "invalid attempt state")
            diagnostics = attempt["diagnostics"]
            _require(isinstance(diagnostics, list), "diagnostics must be a list")
            ids = []
            for diagnostic in diagnostics:
                _object(diagnostic, DIAGNOSTIC_KEYS, "variant diagnostic")
                _require(_text(diagnostic["variant_id"]), "invalid variant identity")
                ids.append(diagnostic["variant_id"])
                _require(all(_finite(diagnostic[key]) for key in DIAGNOSTIC_KEYS - {"variant_id"}),
                         "nonfinite variant diagnostic")
                if status == "accepted":
                    _require(diagnostic["max_rhat"] <= 1.05 and diagnostic["min_bulk_ess"] >= 200
                             and diagnostic["min_tail_ess"] >= 200, "accepted diagnostics fail gates")
            _require(ids == sorted(set(ids)), "diagnostic identities must be unique and sorted")
            divergence = attempt["divergence_count"]
            _require(divergence is None or _integer(divergence), "invalid divergence count")
            if status == "accepted":
                _require(attempt["reason"] is None and divergence == 0 and bool(ids),
                         "invalid accepted evidence")
            else:
                _require(_text(attempt["reason"]), "nonaccepted attempt needs reason")
                if status != "convergence_failed":
                    _require(divergence is None and not ids, "fabricated unavailable diagnostics")
        initial, retry = attempts
        if initial["status"] != "convergence_failed":
            expected = {"accepted": "initial_accepted", "not_attempted": "initial_not_attempted"}.get(
                initial["status"], "initial_not_retryable")
            _require(retry["status"] == "not_attempted" and retry["reason"] == expected,
                     "retry must follow typed initial convergence failure only")
        else:
            _require(retry["status"] != "not_attempted", "missing admitted retry")
        if initial["status"] == "not_attempted":
            _require(initial["reason"] == "fold_preflight_infeasible"
                     and fold["failure_phase"] == "preflight",
                     "invalid unused initial attempt")
        accepted = [item for item in attempts if item["status"] == "accepted"]
        _require(len(accepted) <= 1, "multiple accepted attempts")
        retained = bool(accepted)
        _require(fold["posterior_status"] == ("retained" if retained else "not_available"),
                 "posterior status mismatch")
        _require(fold["posterior_prefix"] == (f"fold_{index:04d}" if retained else None),
                 "posterior prefix mismatch")
        _require(not completed or retained, "completed fold requires accepted fit")
        _require(not retained or completed or fold["failure_phase"] in {"prediction", "scoring"},
                 "accepted fit has inconsistent failure phase")
    return folds


def _npz(arrays):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        for key in sorted(arrays):
            payload = io.BytesIO()
            np.lib.format.write_array(payload, arrays[key], version=(1, 0), allow_pickle=False)
            item = zipfile.ZipInfo(key + ".npy", date_time=(1980, 1, 1, 0, 0, 0))
            item.create_system = 3
            item.external_attr = 0o600 << 16
            item.internal_attr = item.flag_bits = 0
            item.create_version = item.extract_version = 20
            item.comment = item.extra = b""
            archive.writestr(item, payload.getvalue(), compress_type=zipfile.ZIP_STORED)
    return buffer.getvalue()


def encode_b0h(folds: Sequence[tuple[str, B0HFoldResult]]) -> tuple[bytes, bytes, pd.DataFrame]:
    """Serialize five planned results; accepted fits survive later fold failure."""
    _require(len(folds) == 5, "expected five folds")
    split_ids = [split for split, result in folds]
    _require(all(_text(split) for split in split_ids) and len(set(split_ids)) == 5,
             "invalid split identities")
    records, rows, arrays = [], [], {}
    for index, (split_id, result) in enumerate(folds):
        fit = result.fit
        prefix = f"fold_{index:04d}" if fit is not None else None
        attempts = []
        for attempt in result.attempts:
            attempts.append({
                "attempt": attempt.attempt, "seed": attempt.config.seed,
                "draws": attempt.config.draws, "tune": attempt.config.tune,
                "chains": attempt.config.chains, "target_accept": attempt.config.target_accept,
                "status": attempt.status, "reason": attempt.reason,
                "divergence_count": attempt.divergence_count,
                "diagnostics": [asdict(item) for item in attempt.diagnostics],
            })
        records.append({
            "split_id": split_id, "status": result.status, "failure_phase": result.failure_phase,
            "reason": result.reason, "posterior_status": "retained" if fit is not None else "not_available",
            "posterior_prefix": prefix, "attempts": attempts,
        })
        if fit is None:
            continue
        length = max(map(len, fit.variant_ids))
        ids = np.asarray(fit.variant_ids, dtype=f"<U{length}")
        _require(tuple(ids.tolist()) == fit.variant_ids, "variant IDs must round-trip losslessly")
        arrays[prefix + "__variant_ids"] = ids
        for name in ("mean_draws", "rho_draws"):
            arrays[prefix + "__" + name] = np.ascontiguousarray(getattr(fit, name), dtype="<f8")
        for position, counts in enumerate(fit.training_counts):
            rows.append({
                "split_id": split_id, **asdict(counts),
                "posterior_mean_mean": float(fit.mean_draws[:, :, position].mean()),
                "posterior_rho_mean": float(fit.rho_draws[:, :, position].mean()),
            })
    frame = pd.DataFrame.from_records(rows, columns=B0H_POSTERIOR_COLUMNS).sort_values(
        ["split_id", "variant_id"]).reset_index(drop=True)
    document = {"schema_version": 1, "model": MODEL, "folds": records}
    config = folds[0][1].attempts[0].config
    _validate_diagnostics(document, {
        "configuration": asdict(config),
        "seeds": {
            "fit_by_fold": {split: {attempt.attempt: attempt.config.seed for attempt in result.attempts}
                            for split, result in folds},
            "pit_by_fold": dict.fromkeys(split_ids),
        },
    })
    return json_bytes(document), _npz(arrays), frame


def validate_b0h_publication(files: Mapping[str, bytes]) -> dict[str, np.ndarray]:
    """Refuse missing/altered publication bytes and malformed posterior companions."""
    _require(set(files) == set(B0H_OUTPUT_FILENAMES) | {"manifest.json"}, "publication file set mismatch")
    manifest = _json(files["manifest.json"])
    _object(manifest, MANIFEST_KEYS, "manifest")
    _require(type(manifest["schema_version"]) is int and manifest["schema_version"] == 2
             and manifest["model"] == MODEL, "invalid manifest schema/model")
    _require(manifest["target"] == "reference_panel_within_resource"
             and manifest["joint_prediction_supported"] is False, "invalid comparison target")
    configuration = manifest["configuration"]
    _object(configuration, CONFIGURATION_KEYS, "configuration")
    _require(all(_text(configuration[name]) for name in ("source_release", "cohort_stage")),
             "invalid source qualification")
    _require(configuration["count_kind"] in {"called", "quality"}
             and configuration["evidence_role"] in {"synthetic", "development"}
             and configuration["cdf_backend"] in {"scipy", "cupy"}, "invalid configuration labels")
    for name in ("prior_alpha", "prior_beta", "rho_prior_alpha", "rho_prior_beta"):
        _require(_finite(configuration[name]) and configuration[name] > 0, "invalid prior shape")
    _require(_integer(configuration["seed"]), "invalid root seed")
    _require(_integer(configuration["draws"], 1) and _integer(configuration["tune"], 1)
             and _integer(configuration["chains"], 4), "invalid sampler configuration")
    _require(_finite(configuration["target_accept"]) and 0 < configuration["target_accept"] < 1,
             "invalid target acceptance")
    _require(configuration["model"] == MODEL and _integer(configuration["folds"])
             and configuration["folds"] == 5,
             "invalid model configuration")
    _require(_text(manifest["dependency_qualification"]), "invalid dependency qualification")
    _require(isinstance(manifest["limitations"], list) and bool(manifest["limitations"])
             and all(_text(item) for item in manifest["limitations"]), "invalid limitations")
    _object(manifest["input_files"], {"counts", "dependencies"}, "input fingerprints")
    for value in manifest["input_files"].values():
        _object(value, {"sha256", "size_bytes"}, "input fingerprint")
        _require(_hex(value["sha256"], 64) and _integer(value["size_bytes"]), "invalid input fingerprint")
    _object(manifest["git"], {"head", "dirty"}, "git provenance")
    _require(_hex(manifest["git"]["head"], 40) and type(manifest["git"]["dirty"]) is bool,
             "invalid Git provenance")
    sources = manifest["science_source_sha256"]
    _require(isinstance(sources, dict) and bool(sources), "missing source fingerprints")
    for name, digest in sources.items():
        _require(_text(name) and not name.startswith("/") and ".." not in name.split("/")
                 and _hex(digest, 64), "invalid source fingerprint")
    versions = manifest["package_versions"]
    required = {"numpy", "scipy", "pandas", "pymc", "pytensor", "arviz", "xarray", "numpyro", "jax", "jaxlib"}
    if configuration["cdf_backend"] == "cupy":
        required.add("cupy")
    _require(isinstance(versions, dict) and required <= set(versions)
             and all(_text(value) for value in versions.values()), "missing required distribution provenance")
    _object(manifest["seeds"], {"root", "split", "pit_by_fold", "fit_by_fold"}, "seeds")
    _require(manifest["seeds"]["root"] == configuration["seed"]
             and _integer(manifest["seeds"]["split"]), "invalid manifest seeds")
    _require(all(_integer(seed) for seed in manifest["seeds"]["pit_by_fold"].values()),
             "invalid PIT seed")
    _object(manifest["runtime"], {"python_version", "jax_backend", "cdf_backend"}, "runtime")
    for value in manifest["runtime"].values():
        _object(value, {"status", "value", "reason"}, "runtime observation")
        _require((value["status"] == "available" and _text(value["value"]) and value["reason"] is None)
                 or (value["status"] == "unavailable" and value["value"] is None and _text(value["reason"])),
                 "invalid runtime observation")
    _require(manifest["output_files"] == {name: fingerprint(files[name]) for name in B0H_OUTPUT_FILENAMES},
             "publication fingerprints mismatch")
    folds = _validate_diagnostics(_json(files["fit_diagnostics.json"]), manifest)
    splits = _json(files["splits.json"])["folds"]
    _require([(fold["split_id"], fold["status"]) for fold in splits] ==
             [(fold["split_id"], fold["status"]) for fold in folds], "split ledger mismatch")
    complete = _json(files["summary.json"])["comparison_complete"]
    _require(type(complete) is bool and complete == all(fold["status"] == "completed" for fold in folds),
             "comparison completion mismatch")
    retained = [fold for fold in folds if fold["posterior_status"] == "retained"]
    expected = {fold["posterior_prefix"] + "__" + suffix for fold in retained
                for suffix in ("mean_draws", "rho_draws", "variant_ids")}
    data = files["posterior_draws.npz"]
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = archive.namelist()
            _require(len(names) == len(set(names)), "duplicate archive member")
            _require(set(names) == {key + ".npy" for key in expected}, "archive member set mismatch")
        with np.load(io.BytesIO(data), allow_pickle=False) as archive:
            _require(set(archive.files) == expected, "NPZ companion mismatch")
            arrays = {key: archive[key] for key in sorted(expected)}
    except (OSError, zipfile.BadZipFile) as error:
        raise ValueError("invalid posterior archive") from error
    for fold in retained:
        prefix = fold["posterior_prefix"]
        accepted = next(item for item in fold["attempts"] if item["status"] == "accepted")
        labels = tuple(item["variant_id"] for item in accepted["diagnostics"])
        ids = arrays[prefix + "__variant_ids"]
        _require(ids.shape == (len(labels),) and ids.dtype.str == f"<U{max(map(len, labels))}"
                 and tuple(ids.tolist()) == labels, "posterior variant identity/dtype mismatch")
        for suffix in ("mean_draws", "rho_draws"):
            array = arrays[prefix + "__" + suffix]
            _require(array.dtype.str == "<f8" and array.flags.c_contiguous
                     and array.shape == (accepted["chains"], accepted["draws"], len(labels)),
                     "posterior dtype/shape mismatch")
            _require(bool(np.all(np.isfinite(array))) and bool(np.all((array > 0) & (array < 1))),
                     "posterior outside finite open unit interval")
    return arrays
```

- [ ] Green and commit:

```bash
"$B0H_RUFF" check --select I --fix genomeos/validation/reference_b0h_artifacts.py tests/test_reference_b0h_artifacts.py
"$B0H_PYTHON" -m pytest -o addopts='' -q tests/test_reference_b0h_artifacts.py tests/test_reference_b0h_fold.py
"$B0H_PYTHON" scripts/smoke.py
"$B0H_RUFF" check .
"$B0H_PYTHON" scripts/check_module_size.py
"$B0H_PYTHON" scripts/check_private_files.py
git diff --check
git add genomeos/validation/reference_b0h_artifacts.py tests/test_reference_b0h_artifacts.py
git diff --cached --name-only
git diff --cached --check
"$B0H_PYTHON" scripts/check_private_files.py
git commit -m "feat: serialize immutable B0H comparison evidence" -m "Advance #211 and #189; preserve accepted fits with failed fold status."
```

Expected: corruption cases refuse, valid incomplete synthetic publication remains readable, deterministic-byte tests pass; staged paths are exactly the two task files.

## Task 3: Actual-source provenance and explicit unavailable runtime placement

**Files:** Create `scripts/reference_b0h_provenance.py`; create `tests/test_reference_b0h_provenance.py`.

**Scientific contract:** Bind comparison evidence to the code and distributions actually consumed without misrepresenting selected backend flags as observed execution. Acceptance is refusal of wrong checkout origins/missing distributions and exact runtime states. This I/O adapter is consumed only after B0H selection. Public fit/scoring arrays provide no execution-placement proof; record fixed unavailable reasons and require separate future GPU experiment evidence. No fitter/scorer API changes, runtime device probes, environment capture or SBC dependency.

**Interfaces:** Consumes the root checkout `Path` and selected backend. Produces `b0h_source_hashes(root: Path, *, cdf_backend: str) -> dict[str, str]`, `b0h_package_versions(*, cdf_backend: str) -> dict[str, str]`, and `b0h_runtime() -> dict[str, dict[str, str | None]]`. Task 4 merges the first two into the unchanged B0 metadata maps, and places runtime under manifest-v2 `runtime`. Hash this helper itself because the runner consumes it; verify origins before hashing. `cupy` records the version of the one installed distribution that actually owns its package file (including CUDA-wheel distribution names), under the manifest key `cupy`.

- [ ] Add complete failing tests.

```python
"""B0H source/distribution provenance tests (design §§5, 7–8, 12)."""

from __future__ import annotations

import hashlib
import importlib.metadata
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import reference_b0h_provenance as subject

ROOT = Path(__file__).resolve().parents[1]


def test_source_hashes_cover_consumed_modules_and_self():
    hashes = subject.b0h_source_hashes(ROOT, cdf_backend="scipy")
    assert set(hashes) == {
        "genomeos/surfaces/heterogeneity_types.py",
        "genomeos/surfaces/reference_heterogeneity.py",
        "genomeos/surfaces/heterogeneity_likelihood.py",
        "genomeos/validation/reference_b0h_fold.py",
        "genomeos/validation/reference_b0h_artifacts.py",
        "scripts/reference_b0h_provenance.py",
    }
    for relative, digest in hashes.items():
        assert digest == hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()


def test_wrong_source_origin_is_refused(monkeypatch, tmp_path):
    real = subject.importlib.import_module

    def wrong(name):
        if name == "genomeos.surfaces.heterogeneity_types":
            return SimpleNamespace(__file__=str(tmp_path / "lookalike.py"))
        return real(name)

    monkeypatch.setattr(subject.importlib, "import_module", wrong)
    with pytest.raises(ValueError, match="outside this checkout"):
        subject.b0h_source_hashes(ROOT, cdf_backend="scipy")


def test_required_versions_and_missing_distribution(monkeypatch):
    monkeypatch.setattr(subject.importlib.metadata, "version", lambda name: "synthetic-version")
    versions = subject.b0h_package_versions(cdf_backend="scipy")
    assert set(versions) == {"pymc", "pytensor", "arviz", "xarray", "numpyro", "jax", "jaxlib"}
    assert set(versions.values()) == {"synthetic-version"}

    def missing(name):
        raise importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(subject.importlib.metadata, "version", missing)
    with pytest.raises(importlib.metadata.PackageNotFoundError):
        subject.b0h_package_versions(cdf_backend="scipy")


def test_runtime_has_no_inferred_backend_evidence(monkeypatch):
    monkeypatch.setattr(subject.platform, "python_version", lambda: "3.12.synthetic")
    assert subject.b0h_runtime() == {
        "python_version": {"status": "available", "value": "3.12.synthetic", "reason": None},
        "jax_backend": {"status": "unavailable", "value": None,
                        "reason": "Public fit results do not expose JAX execution placement."},
        "cdf_backend": {"status": "unavailable", "value": None,
                        "reason": "Public scoring results do not expose CDF execution placement."},
    }


def test_cupy_distribution_owner_is_established(monkeypatch, tmp_path):
    origin = tmp_path / "cupy" / "__init__.py"
    file = Path("cupy/__init__.py")
    distribution = SimpleNamespace(
        files=[file], version="synthetic-cuda-version",
        locate_file=lambda value: tmp_path / value,
    )
    monkeypatch.setattr(subject.importlib.util, "find_spec", lambda name: SimpleNamespace(origin=str(origin)))
    monkeypatch.setattr(subject.importlib.metadata, "packages_distributions",
                        lambda: {"cupy": ["cupy-cuda12x"]})
    monkeypatch.setattr(subject.importlib.metadata, "distribution", lambda name: distribution)
    monkeypatch.setattr(subject.importlib.metadata, "version", lambda name: "synthetic-version")
    assert subject.b0h_package_versions(cdf_backend="cupy")["cupy"] == "synthetic-cuda-version"
    monkeypatch.setattr(subject.importlib.metadata, "packages_distributions", lambda: {})
    with pytest.raises(ValueError, match="one distribution"):
        subject.b0h_package_versions(cdf_backend="cupy")
```

- [ ] Run red: `"$B0H_PYTHON" -m pytest -o addopts='' -q tests/test_reference_b0h_provenance.py`. Expected missing-module collection failure.

- [ ] Add the complete production module.

```python
"""B0H local source/runtime provenance (design §§5, 7–8, 12; integration §4)."""

from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import importlib.util
import platform
from pathlib import Path


def b0h_source_hashes(root: Path, *, cdf_backend: str) -> dict[str, str]:
    """Hash imported B0H modules only after verifying their checkout origins."""
    names = [
        "genomeos.surfaces.heterogeneity_types",
        "genomeos.surfaces.reference_heterogeneity",
        "genomeos.surfaces.heterogeneity_likelihood",
        "genomeos.validation.reference_b0h_fold",
        "genomeos.validation.reference_b0h_artifacts",
    ]
    if cdf_backend == "cupy":
        names.append("genomeos.validation.predictive_cupy")
    result = {}
    for name in names:
        relative = name.replace(".", "/") + ".py"
        actual = Path(importlib.import_module(name).__file__).resolve()
        if actual != (root / relative).resolve():
            raise ValueError(f"imported source {relative} resolved outside this checkout")
        result[relative] = hashlib.sha256(actual.read_bytes()).hexdigest()
    relative = "scripts/reference_b0h_provenance.py"
    actual = Path(__file__).resolve()
    if actual != (root / relative).resolve():
        raise ValueError(f"imported source {relative} resolved outside this checkout")
    result[relative] = hashlib.sha256(actual.read_bytes()).hexdigest()
    return result


def _cupy_version() -> str:
    specification = importlib.util.find_spec("cupy")
    if specification is None or specification.origin is None:
        raise ModuleNotFoundError("selected CuPy package is unavailable")
    origin = Path(specification.origin).resolve()
    owners = []
    for name in importlib.metadata.packages_distributions().get("cupy", []):
        distribution = importlib.metadata.distribution(name)
        if any(Path(distribution.locate_file(file)).resolve() == origin
               for file in distribution.files or ()):
            owners.append(distribution)
    if len(owners) != 1:
        raise ValueError("CuPy package origin must be owned by exactly one distribution")
    return owners[0].version


def b0h_package_versions(*, cdf_backend: str) -> dict[str, str]:
    """Require installed distribution provenance, including selected CuPy ownership."""
    result = {name: importlib.metadata.version(name)
              for name in ("pymc", "pytensor", "arviz", "xarray", "numpyro", "jax", "jaxlib")}
    if cdf_backend == "cupy":
        result["cupy"] = _cupy_version()
    if any(not isinstance(value, str) or not value.strip() for value in result.values()):
        raise ValueError("required distribution versions must be nonempty")
    return result


def b0h_runtime() -> dict[str, dict[str, str | None]]:
    """Report observed Python and unavailable public execution-placement evidence."""
    version = platform.python_version()
    if not version:
        raise ValueError("Python version observation is unavailable")
    return {
        "python_version": {"status": "available", "value": version, "reason": None},
        "jax_backend": {"status": "unavailable", "value": None,
                        "reason": "Public fit results do not expose JAX execution placement."},
        "cdf_backend": {"status": "unavailable", "value": None,
                        "reason": "Public scoring results do not expose CDF execution placement."},
    }
```

- [ ] Green and commit:

```bash
"$B0H_RUFF" check --select I --fix scripts/reference_b0h_provenance.py tests/test_reference_b0h_provenance.py
"$B0H_PYTHON" -m pytest -o addopts='' -q tests/test_reference_b0h_provenance.py
"$B0H_PYTHON" scripts/smoke.py
"$B0H_RUFF" check .
"$B0H_PYTHON" scripts/check_module_size.py
"$B0H_PYTHON" scripts/check_private_files.py
git diff --check
git add scripts/reference_b0h_provenance.py tests/test_reference_b0h_provenance.py
git diff --cached --name-only
git diff --cached --check
"$B0H_PYTHON" scripts/check_private_files.py
git commit -m "feat: bind B0H evidence to consumed source origins" -m "Advance #211 and #189; keep unobserved execution placement explicit."
```

Expected: origin/distribution refusal and exact runtime-state tests pass; no GPU probe or fit occurs.

## Task 4: Existing CLI composition and complete synthetic acceptance matrix

**Files:** Modify `scripts/benchmark_reference_counts.py` at `_parser`, add `_model_config` before `run`, replace `run`, and make `_json_write` explicitly UTF-8. Create `tests/test_reference_b0h_cli.py`. Existing `tests/test_reference_counts_cli.py` remains unchanged and must pass.

**Scientific contract:** Produce an auditable offline B0H comparison ledger on the unchanged fold/scoring/summary interfaces. Acceptance is five-fold synthetic CLI publication, exact legacy default/explicit B0 equality, convergence-only retry, later-fold continuation, incomplete-fit retention and interrupted-publication refusal. Consumers remain local research reviewers. Root has admitted integration only; real fitting still requires separate recorded calibration and experiment admission.

**Interfaces:** Consumes all Task 1, 2 and 3 signatures exactly as declared. `_model_config(args: argparse.Namespace)` returns `PopulationHeterogeneityConfig | None` (imported lazily inside the function; omit its return annotation to avoid eager dependency imports). `run(args: argparse.Namespace) -> int` retains its signature. Existing CLI flags/metadata remain identical for B0; additional flags are parsed as `None` until model selection distinguishes explicit from absent. This task produces the existing `manifest.json`/six-file B0 boundary and exact eight-file B0H boundary. No fitting/scoring function is replaced or reimplemented.

- [ ] Write this complete test module first.

```python
"""Synthetic B0H CLI integration; no calibration or real-fit evidence (design §§5, 7–8, 12)."""

from __future__ import annotations

import csv
import importlib.util
import json
import subprocess
import sys
from dataclasses import asdict, replace

import pandas as pd
import pytest

import genomeos.validation.reference_b0h_fold as fold_module
from genomeos.surfaces.heterogeneity_types import HeterogeneityConvergenceError
from genomeos.validation.reference_b0h_artifacts import validate_b0h_publication
from reference_b0h_synthetic import synthetic_fit, synthetic_rows
from test_reference_counts_cli import SCRIPT, _command, _run


def load_runner():
    specification = importlib.util.spec_from_file_location("synthetic_reference_b0h_runner", SCRIPT)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def synthetic_args(tmp_path, runner, *, out_name="out", extra=()):
    counts = tmp_path / "synthetic-counts.tsv"
    rows = list(synthetic_rows())
    rows[0] = replace(rows[0], ac=0, an=0)
    with counts.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=runner.COUNT_COLUMNS, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(asdict(row) for row in rows)
    dependencies = tmp_path / "synthetic-dependencies.json"
    dependencies.write_text('{"edges": [], "qualification": "synthetic only"}\n', encoding="utf-8")
    command = _command(tmp_path / out_name, counts=counts, dependencies=dependencies, folds=5)
    return runner._parser().parse_args(command[2:] + [
        "--model", "B0H_population_heterogeneity", "--rho-prior-alpha", "1", "--rho-prior-beta", "9",
        "--draws", "2", "--tune", "3", *extra,
    ])


def read_files(out):
    return {path.name: path.read_bytes() for path in out.iterdir()}


def test_legacy_default_and_explicit_model_scipy_are_byte_equal(tmp_path):
    first, second = tmp_path / "legacy", tmp_path / "explicit"
    assert _run(_command(first)).returncode == 0
    explicit = _command(second) + ["--model", "pooled_beta_counts", "--cdf-backend", "scipy"]
    assert _run(explicit).returncode == 0
    assert read_files(first) == read_files(second)
    manifest = json.loads((first / "manifest.json").read_bytes())
    assert manifest["schema_version"] == 1
    assert "model" not in manifest and "runtime" not in manifest
    assert len(read_files(first)) == 6


@pytest.mark.parametrize(("option", "value"), [
    ("--rho-prior-alpha", "1"), ("--rho-prior-beta", "9"), ("--draws", "500"),
    ("--tune", "1000"), ("--chains", "4"), ("--target-accept", "0.9"), ("--cdf-backend", "cupy"),
])
def test_b0_rejects_every_explicit_b0h_setting(tmp_path, option, value):
    out = tmp_path / "out"
    assert _run(_command(out) + [option, value]).returncode != 0
    assert not out.exists()


def test_b0_startup_help_validation_and_execution_need_no_surfaces_extra(tmp_path):
    bootstrap = (
        "import importlib.abc, runpy, sys\n"
        "class Block(importlib.abc.MetaPathFinder):\n"
        " def find_spec(self, fullname, path=None, target=None):\n"
        "  if fullname.split('.')[0] in {'pymc','pytensor','arviz','numpyro','jax','jaxlib','xarray'}"
        " or fullname.startswith('genomeos.surfaces'):\n"
        "   raise ModuleNotFoundError('synthetic blocked surfaces extra: ' + fullname)\n"
        "sys.meta_path.insert(0, Block())\n"
        "script = sys.argv.pop(1)\n"
        "runpy.run_path(script, run_name='__main__')\n"
    )
    base = [sys.executable, "-c", bootstrap, str(SCRIPT)]
    assert subprocess.run(base + ["--help"], capture_output=True).returncode == 0
    result = subprocess.run(base + _command(tmp_path / "out")[2:], capture_output=True)
    assert result.returncode == 0, result.stderr
    invalid = subprocess.run(base + _command(tmp_path / "invalid")[2:] + ["--draws", "500"],
                             capture_output=True)
    assert invalid.returncode != 0
    assert b"synthetic blocked" not in invalid.stderr


@pytest.mark.parametrize(("field", "value"), [
    ("rho_prior_alpha", None), ("rho_prior_beta", None), ("folds", 4),
    ("chains", 3), ("draws", 0), ("tune", 0), ("target_accept", 1.0),
])
def test_b0h_invalid_configuration_refuses_before_fit(tmp_path, monkeypatch, field, value):
    runner = load_runner()
    args = synthetic_args(tmp_path, runner)
    setattr(args, field, value)

    def forbidden(*args, **kwargs):
        pytest.fail("invalid configuration reached fitter")

    monkeypatch.setattr(fold_module, "fit_reference_population_heterogeneity", forbidden)
    with pytest.raises(ValueError):
        runner.run(args)
    assert not args.out.exists()


def test_b0h_absent_sampler_options_use_public_config_defaults(tmp_path):
    runner = load_runner()
    args = synthetic_args(tmp_path, runner)
    for field in ("draws", "tune", "chains", "target_accept"):
        setattr(args, field, None)
    config = runner._model_config(args)
    assert (config.draws, config.tune, config.chains, config.target_accept) == (500, 1000, 4, 0.9)
    assert (config.mean_prior_alpha, config.mean_prior_beta) == (1.0, 1.0)
    assert not args.out.exists()


def test_mocked_fivefold_publication_is_repeatable_and_training_only(tmp_path, monkeypatch):
    runner = load_runner()
    calls = []

    def capture(training, *, config):
        calls.append((tuple(training), config))
        return synthetic_fit(training, config=config)

    monkeypatch.setattr(fold_module, "fit_reference_population_heterogeneity", capture)
    first = synthetic_args(tmp_path, runner, out_name="first")
    second = synthetic_args(tmp_path, runner, out_name="second")
    assert runner.run(first) == runner.run(second) == 0
    assert read_files(first.out) == read_files(second.out)
    files = read_files(first.out)
    arrays = validate_b0h_publication(files)
    assert len(arrays) == 15 and len(calls) == 10
    manifest = json.loads(files["manifest.json"])
    splits = json.loads(files["splits.json"])["folds"]
    for index, split in enumerate(splits):
        training, config = calls[index]
        assert {row.record_id for row in training} == set(split["train_ids"])
        assert not {row.record_id for row in training} & set(split["test_ids"])
        assert config.seed == manifest["seeds"]["fit_by_fold"][split["split_id"]]["initial"]
    legacy_split, legacy_pit = runner._seeds(42, 5)
    assert manifest["seeds"]["split"] == legacy_split
    assert list(manifest["seeds"]["pit_by_fold"].values()) == list(legacy_pit)
    rows = pd.read_csv(first.out / "row_status.tsv", sep="\t", keep_default_na=False)
    assert len(rows) == 18 and (rows.status == "unavailable_denominator").sum() == 1
    assert manifest["runtime"]["jax_backend"]["status"] == "unavailable"
    assert manifest["runtime"]["cdf_backend"]["status"] == "unavailable"


@pytest.mark.parametrize("failure", ["convergence", "numeric", "prediction", "scoring"])
def test_failed_fold_ledger_and_accepted_fit_retention(tmp_path, monkeypatch, failure):
    runner = load_runner()
    args = synthetic_args(tmp_path, runner)
    calls = []
    fail_training = None

    def fit(training, *, config):
        nonlocal fail_training
        identity = tuple(row.record_id for row in training)
        if fail_training is None:
            fail_training = identity
        calls.append(config)
        if identity == fail_training and failure == "convergence":
            raise HeterogeneityConvergenceError("synthetic terminal convergence failure")
        if identity == fail_training and failure == "numeric":
            raise ArithmeticError("synthetic numeric failure")
        return synthetic_fit(training, config=config)

    monkeypatch.setattr(fold_module, "fit_reference_population_heterogeneity", fit)
    if failure in {"prediction", "scoring"}:
        name = ("predict_reference_population_heterogeneity" if failure == "prediction"
                else "predictive_diagnostics")
        original = getattr(fold_module, name)
        invoked = False

        def fail_once(*args, **kwargs):
            nonlocal invoked
            if not invoked:
                invoked = True
                raise ValueError("synthetic later failure")
            return original(*args, **kwargs)

        monkeypatch.setattr(fold_module, name, fail_once)
    assert runner.run(args) == 2
    files = read_files(args.out)
    arrays = validate_b0h_publication(files)
    document = json.loads(files["fit_diagnostics.json"])
    first = document["folds"][0]
    assert first["status"] == "failed"
    assert all(fold["status"] == "completed" for fold in document["folds"][1:])
    assert len(calls) == (6 if failure == "convergence" else 5)
    if failure in {"prediction", "scoring"}:
        assert first["posterior_status"] == "retained"
        assert len(arrays) == 15 and first["attempts"][0]["status"] == "accepted"
    else:
        assert first["posterior_status"] == "not_available" and len(arrays) == 12
    if failure == "convergence":
        assert [item["status"] for item in first["attempts"]] == ["convergence_failed"] * 2
        assert calls[1].draws == 4 and calls[1].tune == 6
    predictions = pd.read_csv(args.out / "predictions.tsv", sep="\t", keep_default_na=False)
    assert first["split_id"] not in set(predictions.split_id)
    rows = pd.read_csv(args.out / "row_status.tsv", sep="\t", keep_default_na=False)
    assert len(rows) == 18 and (rows.status == "unavailable_denominator").sum() == 1


def test_missing_only_test_fold_never_fits_and_is_accounted(tmp_path, monkeypatch):
    runner = load_runner()
    args = synthetic_args(tmp_path, runner)
    rows = runner._read_counts(args.counts.read_bytes())
    split_seed, _pit = runner._seeds(args.seed, 5)
    folds = runner.reference_group_folds(rows, dependency_edges=(), n_folds=5, seed=split_seed)
    missing_ids = set(folds[0].test_ids)
    with args.counts.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=runner.COUNT_COLUMNS, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(
            asdict(replace(row, ac=0, an=0) if row.record_id in missing_ids else row) for row in rows
        )
    calls = []

    def fit(training, *, config):
        calls.append(config)
        return synthetic_fit(training, config=config)

    monkeypatch.setattr(fold_module, "fit_reference_population_heterogeneity", fit)
    assert runner.run(args) == 2 and len(calls) == 4
    validate_b0h_publication(read_files(args.out))
    status = pd.read_csv(args.out / "row_status.tsv", sep="\t", keep_default_na=False)
    assert set(status.loc[status.record_id.isin(missing_ids), "status"]) == {"unavailable_denominator"}


@pytest.mark.parametrize("phase", ["fit", "backend", "publication"])
def test_interruptions_never_publish_valid_completion(tmp_path, monkeypatch, phase):
    runner = load_runner()
    args = synthetic_args(tmp_path, runner)
    monkeypatch.setattr(fold_module, "fit_reference_population_heterogeneity", synthetic_fit)
    if phase == "publication":
        original = runner._json_write

        def interrupted(path, value):
            if path.name == "manifest.json":
                raise OSError("synthetic interrupted publication")
            return original(path, value)

        monkeypatch.setattr(runner, "_json_write", interrupted)
        error_type = OSError
    else:
        def interrupted(*args, **kwargs):
            raise RuntimeError("synthetic unavailable backend/interruption")

        name = ("fit_reference_population_heterogeneity" if phase == "fit" else "predictive_diagnostics")
        monkeypatch.setattr(fold_module, name, interrupted)
        error_type = RuntimeError
    with pytest.raises(error_type):
        runner.run(args)
    assert not (args.out / "manifest.json").exists()
    if args.out.exists():
        with pytest.raises(ValueError):
            validate_b0h_publication(read_files(args.out))


def test_b0h_output_reuse_and_provenance_failure_refuse_before_fit(tmp_path, monkeypatch):
    from scripts import reference_b0h_provenance as provenance

    runner = load_runner()
    args = synthetic_args(tmp_path, runner)
    monkeypatch.setattr(fold_module, "fit_reference_population_heterogeneity", synthetic_fit)
    assert runner.run(args) == 0
    before = read_files(args.out)
    with pytest.raises(ValueError, match="already exists"):
        runner.run(args)
    assert before == read_files(args.out)
    other = synthetic_args(tmp_path, runner, out_name="refused")

    def fail(*args, **kwargs):
        raise ValueError("synthetic provenance failure")

    monkeypatch.setattr(provenance, "b0h_source_hashes", fail)
    with pytest.raises(ValueError, match="synthetic provenance failure"):
        runner.run(other)
    assert not other.out.exists()
```

- [ ] Run red: `"$B0H_PYTHON" -m pytest -o addopts='' -q tests/test_reference_b0h_cli.py`. Expected argparse rejects the new model/options, before any fit.

- [ ] Replace `_parser` with this literal implementation and add `_model_config` immediately after it. Preserve the existing imports and remaining parsing helpers.

```python
def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a qualified reference-count benchmark.")
    parser.add_argument("--counts", required=True, type=Path)
    parser.add_argument("--dependencies", required=True, type=Path)
    parser.add_argument("--source-release", required=True)
    parser.add_argument("--cohort-stage", required=True)
    parser.add_argument("--count-kind", required=True, choices=("called", "quality"))
    parser.add_argument("--evidence-role", required=True, choices=("development", "synthetic"))
    parser.add_argument("--prior-alpha", required=True, type=_positive_float)
    parser.add_argument("--prior-beta", required=True, type=_positive_float)
    parser.add_argument("--model", choices=("pooled_beta_counts", "B0H_population_heterogeneity"),
                        default="pooled_beta_counts")
    parser.add_argument("--rho-prior-alpha", type=_positive_float)
    parser.add_argument("--rho-prior-beta", type=_positive_float)
    parser.add_argument("--draws", type=_positive_integer)
    parser.add_argument("--tune", type=_positive_integer)
    parser.add_argument("--chains", type=_positive_integer)
    parser.add_argument("--target-accept", type=_positive_float)
    parser.add_argument("--cdf-backend", choices=("scipy", "cupy"))
    parser.add_argument("--folds", type=_positive_integer, default=5)
    parser.add_argument("--seed", type=_nonnegative_integer, default=42)
    parser.add_argument("--out", required=True, type=Path)
    return parser


def _model_config(args: argparse.Namespace):
    """Distinguish absent options from explicit assertions before importing B0H."""
    fields = ("rho_prior_alpha", "rho_prior_beta", "draws", "tune", "chains", "target_accept")
    if args.model == "pooled_beta_counts":
        supplied = [field for field in fields if getattr(args, field) is not None]
        if supplied:
            raise ValueError(f"pooled_beta_counts rejects explicit B0H settings: {supplied}")
        if args.cdf_backend not in (None, "scipy"):
            raise ValueError("pooled_beta_counts uses scipy and rejects cdf_backend=cupy")
        return None
    if args.model != "B0H_population_heterogeneity":
        raise ValueError("unknown reference-count model")
    if args.folds != 5:
        raise ValueError("B0H_population_heterogeneity requires exactly five folds")
    if args.rho_prior_alpha is None or args.rho_prior_beta is None:
        raise ValueError("B0H_population_heterogeneity requires both rho prior shapes")
    if args.cdf_backend not in (None, "scipy", "cupy"):
        raise ValueError("cdf_backend must be scipy or cupy")
    from genomeos.surfaces.heterogeneity_types import PopulationHeterogeneityConfig

    return PopulationHeterogeneityConfig(
        args.prior_alpha, args.prior_beta, args.rho_prior_alpha, args.rho_prior_beta,
        draws=500 if args.draws is None else args.draws,
        tune=1000 if args.tune is None else args.tune,
        chains=4 if args.chains is None else args.chains,
        target_accept=0.9 if args.target_accept is None else args.target_accept,
        seed=args.seed,
    )
```

- [ ] Replace `_json_write` with its otherwise unchanged UTF-8 form:

```python
def _json_write(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, allow_nan=False, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
```

- [ ] Replace only `run` with the complete implementation below. The B0 try/except body, prediction construction and posterior transformation are preserved verbatim; B0H supplies a complete validated frame before the shared row ledger.

```python
def run(args: argparse.Namespace) -> int:
    """Publish deterministic B0/B0H evidence (design §§5, 7–8, 12; integration §§2–7)."""
    if args.out.exists():
        raise ValueError(f"output directory already exists: {args.out}")
    config = _model_config(args)
    for field in ("source_release", "cohort_stage"):
        value = getattr(args, field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field} must be nonempty text")
    sources = _science_hashes()
    git_record = _git_record()
    package_versions = _package_versions()
    counts_bytes = args.counts.read_bytes()
    dependency_bytes = args.dependencies.read_bytes()
    input_files = {
        "counts": _bytes_record(counts_bytes),
        "dependencies": _bytes_record(dependency_bytes),
    }
    rows = _read_counts(counts_bytes)
    edges, qualification = _read_dependencies(dependency_bytes)
    if config is None:
        split_seed, pit_seeds = _seeds(args.seed, args.folds)
    else:
        from genomeos.validation.reference_b0h_artifacts import (
            B0H_OUTPUT_FILENAMES,
            encode_b0h,
            json_bytes,
            validate_b0h_publication,
        )
        from genomeos.validation.reference_b0h_fold import b0h_seeds, run_b0h_fold
        from scripts.reference_b0h_provenance import (
            b0h_package_versions,
            b0h_runtime,
            b0h_source_hashes,
        )

        split_seed, pit_seeds, fit_seeds = b0h_seeds(args.seed)
    folds = reference_group_folds(rows, dependency_edges=edges, n_folds=args.folds, seed=split_seed)
    if config is not None:
        backend = args.cdf_backend or "scipy"
        sources.update(b0h_source_hashes(ROOT, cdf_backend=backend))
        package_versions.update(b0h_package_versions(cdf_backend=backend))
        runtime = b0h_runtime()

    by_id = {row.record_id: row for row in rows}
    predictions: list[dict[str, object]] = []
    posteriors: list[dict[str, object]] = []
    row_status: list[dict[str, object]] = []
    statuses: list[BenchmarkFoldStatus] = []
    split_records = []
    b0h_results = []
    for index, fold in enumerate(folds):
        training = tuple(by_id[key] for key in fold.train_ids)
        testing = tuple(by_id[key] for key in fold.test_ids)
        unavailable = tuple(row.record_id for row in testing if row.an == 0)
        scoreable = tuple(row for row in testing if row.an > 0)
        if config is not None:
            outcome = run_b0h_fold(
                training, testing, config=config, initial_seed=fit_seeds[index][0],
                retry_seed=fit_seeds[index][1], pit_seed=pit_seeds[index], cdf_backend=backend,
            )
            b0h_results.append((fold.split_id, outcome))
            state, reason = outcome.status, outcome.reason
            if state == "completed":
                for position, row in enumerate(scoreable):
                    record = {
                        "split_id": fold.split_id, "source_record_id": row.record_id,
                        "variant_id": row.variant_id, "region_id": row.region_id,
                        "variant_group": row.variant_group, "cohort_id": row.group_id,
                        "observed_ac": row.ac, "observed_an": row.an,
                    }
                    record.update(outcome.diagnostics.iloc[position].to_dict())
                    predictions.append(record)
        else:
            try:
                fitted = fit_reference_b0(
                    training, testing, prior_alpha=args.prior_alpha, prior_beta=args.prior_beta
                )
                scored = tuple(by_id[key] for key in fitted.observation_ids)
                diagnostics = predictive_diagnostics(
                    fitted.marginal_predictive,
                    [row.ac for row in scored],
                    [row.an for row in scored],
                    seed=pit_seeds[index],
                )
                diagnostics = validate_predictive_diagnostics(diagnostics)
                for position, row in enumerate(scored):
                    record = {
                        "split_id": fold.split_id, "source_record_id": row.record_id,
                        "variant_id": row.variant_id, "region_id": row.region_id,
                        "variant_group": row.variant_group, "cohort_id": row.group_id,
                        "observed_ac": row.ac, "observed_an": row.an,
                    }
                    record.update(diagnostics.iloc[position].to_dict())
                    predictions.append(record)
                for posterior in fitted.posteriors:
                    record = asdict(posterior)
                    record.update({
                        "split_id": fold.split_id,
                        "posterior_alpha": record.pop("alpha"),
                        "posterior_beta": record.pop("beta"),
                    })
                    posteriors.append(record)
                state, reason = "completed", None
            except (B0InfeasibleError, ReferenceInfeasibleError) as error:
                state, reason = "infeasible", str(error)
            except (ArithmeticError, FloatingPointError, ValueError) as error:
                state, reason = "failed", f"{type(error).__name__}: {error}"

        expected = tuple(row.record_id for row in scoreable) if state == "completed" else fold.test_ids
        statuses.append(BenchmarkFoldStatus(fold.split_id, state, expected, reason))
        for row in testing:
            if row.record_id in unavailable:
                status, row_reason = "unavailable_denominator", "AN is zero"
            elif state == "completed":
                status, row_reason = "scored", ""
            else:
                status, row_reason = state, reason
            row_status.append({
                "split_id": fold.split_id, "record_id": row.record_id,
                "status": status, "reason": row_reason,
            })
        split_records.append({
            **asdict(fold), "status": state, "failure_reason": reason, "pit_seed": pit_seeds[index]
        })

    prediction_frame = pd.DataFrame.from_records(predictions, columns=PREDICTION_COLUMNS).sort_values(
        ["split_id", "source_record_id"]
    ).reset_index(drop=True)
    if config is None:
        posterior_frame = pd.DataFrame.from_records(posteriors, columns=POSTERIOR_COLUMNS).sort_values(
            ["split_id", "variant_id"]
        ).reset_index(drop=True)
    else:
        diagnostic_bytes, posterior_bytes, posterior_frame = encode_b0h(b0h_results)
    status_frame = pd.DataFrame.from_records(row_status, columns=ROW_STATUS_COLUMNS).sort_values(
        ["split_id", "record_id"]
    ).reset_index(drop=True)
    summary = summarize_benchmark(prediction_frame, statuses, tuple(fold.split_id for fold in folds))
    summary.update({
        "target": "reference_panel_within_resource", "evidence_role": args.evidence_role,
        "joint_prediction_supported": False,
        "weighting_unit": "source_population_group_not_independent_study",
        "total_row_count": len(rows),
        "unavailable_row_count": int((status_frame.status == "unavailable_denominator").sum()),
        "failed_row_count": int(status_frame.status.isin(["failed", "infeasible"]).sum()),
    })
    configuration = {
        "source_release": args.source_release, "cohort_stage": args.cohort_stage,
        "count_kind": args.count_kind, "evidence_role": args.evidence_role,
        "prior_alpha": args.prior_alpha, "prior_beta": args.prior_beta,
        "folds": args.folds, "seed": args.seed,
    }
    if config is not None:
        configuration.update({
            "model": args.model, "rho_prior_alpha": config.rho_prior_alpha,
            "rho_prior_beta": config.rho_prior_beta, "draws": config.draws, "tune": config.tune,
            "chains": config.chains, "target_accept": config.target_accept, "cdf_backend": backend,
        })
    split_document = {"configuration": configuration, "split_seed": split_seed, "folds": split_records}
    args.out.mkdir(parents=True, exist_ok=False)
    _json_write(args.out / "splits.json", split_document)
    _write_tsv(status_frame, args.out / "row_status.tsv")
    _write_tsv(prediction_frame, args.out / "predictions.tsv")
    _write_tsv(posterior_frame, args.out / "posteriors.tsv")
    _json_write(args.out / "summary.json", summary)
    if config is not None:
        (args.out / "fit_diagnostics.json").write_bytes(diagnostic_bytes)
        (args.out / "posterior_draws.npz").write_bytes(posterior_bytes)
    filenames = OUTPUT_FILENAMES if config is None else B0H_OUTPUT_FILENAMES
    manifest = {
        "schema_version": 1, "target": "reference_panel_within_resource",
        "joint_prediction_supported": False,
        "limitations": [
            "Reference-resource operational groups are not certified independent studies.",
            "Marginal predictions are not coherent joint draws.",
            "This development evidence does not establish external generalization or release fitness.",
        ],
        "configuration": configuration,
        "dependency_qualification": qualification,
        "input_files": input_files,
        "seeds": {
            "root": args.seed,
            "split": split_seed,
            "pit_by_fold": dict(zip((fold.split_id for fold in folds), pit_seeds, strict=True)),
        },
        "git": git_record,
        "science_source_sha256": sources,
        "package_versions": package_versions,
        "output_files": {name: _sha(args.out / name) for name in filenames},
    }
    if config is not None:
        manifest.update({"schema_version": 2, "model": args.model, "runtime": runtime})
        manifest["seeds"]["fit_by_fold"] = {
            fold.split_id: {"initial": pair[0], "retry": pair[1]}
            for fold, pair in zip(folds, fit_seeds, strict=True)
        }
        files = {name: (args.out / name).read_bytes() for name in filenames}
        files["manifest.json"] = json_bytes(manifest)
        validate_b0h_publication(files)
    _json_write(args.out / "manifest.json", manifest)
    return 0 if summary["comparison_complete"] else 2
```

- [ ] Run focused green, mandatory gates and commit. Format only the listed new/modified task files if lint reports import ordering or formatting; no broad mechanical changes to unrelated files.

```bash
"$B0H_RUFF" check --select I --fix scripts/benchmark_reference_counts.py tests/test_reference_b0h_cli.py
"$B0H_PYTHON" -m pytest -o addopts='' -q tests/test_reference_b0h_cli.py tests/test_reference_counts_cli.py tests/test_reference_counts.py tests/test_reference_b0h_fold.py tests/test_reference_b0h_artifacts.py tests/test_reference_b0h_provenance.py
"$B0H_PYTHON" scripts/smoke.py
"$B0H_RUFF" check .
"$B0H_PYTHON" scripts/freeze_contract.py --check
"$B0H_PYTHON" scripts/check_module_size.py
"$B0H_PYTHON" scripts/check_private_files.py
git diff --check
git add scripts/benchmark_reference_counts.py tests/test_reference_b0h_cli.py
git diff --cached --name-only
git diff --cached --check
"$B0H_PYTHON" scripts/check_private_files.py
git commit -m "feat: compose B0H reference-count comparison artifacts" -m "Advance #211 and #189; real calibration and comparison admission remain separate."
```

Expected: all synthetic/new and existing reference tests pass; B0 default and explicit assertions produce identical six-file bytes; B0H publishes exact eight-file complete/incomplete ledgers; interruptions lack a valid manifest. Before any PR/push root runs the repository's full CI commands, including `"$B0H_PYTHON" -m pytest -o addopts='' -q`, privacy gate and staged-path inspection. Full-suite synthetic sampler tests are existing scientific verification and require the already authorized scientific execution context; this neutral plan does not execute them or claim they passed.

- [ ] After Task 4, root must pass the retained pre/post B0 acceptance check below before accepting the integration or opening/pushing its PR. The new-default/new-explicit CI test remains required, but does not establish compatibility with the untouched runner by itself.

Root already captured the untouched B0 runner in the clean comparison checkout at HEAD `bdd524a2e16a20c9b9f97ba3775e3ac198fa7596`: `/private/tmp/genomeos-b0-legacy-anchor.B5kNmZ/folds-2` exited 0; `/private/tmp/genomeos-b0-legacy-anchor.B5kNmZ/folds-5` exited 2. Both used the existing `tests/fixtures/reference_counts/counts.tsv` and `dependencies.json`, and the exact flags in `tests/test_reference_counts_cli.py::_command` with folds 2/5. The plan author read their manifests; root, not the plan author, executed these captures. The original runner digest is `261dc9ed57b4f920e128d60060880c099ad3733984108bf0a8b29e41cf0046cc`; both manifests report NumPy 2.4.6, pandas 3.0.5 and SciPy 1.18.1.

Run this bounded check from root's integration checkout, using the same pinned interpreter and environment declared above. It validates both retained anchors before creating fresh post-change directories, reruns the exact original default-B0 commands, and requires all five non-manifest files byte-identical. It then compares every manifest field except Git metadata and the expected changed runner-source digest; the remaining source hashes, packages, input identities, configuration, seeds and output fingerprints must remain identical. A missing, altered or incompatible anchor is a hard acceptance failure. Never skip this gate, regenerate/replace an old anchor, invent a default, or use a new execution as its own reference. This root-local acceptance step adds no CI dependency on historical Git objects and vendors no duplicate legacy production code.

```bash
"$B0H_PYTHON" - <<'PY'
from __future__ import annotations

import copy
import hashlib
import importlib.metadata
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

interpreter = Path("/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python")
assert Path(sys.executable).absolute() == interpreter, "use the original pinned interpreter"
assert os.environ["PYTHONPATH"] == ".", "use the declared test environment"
assert os.environ["PYTHONDONTWRITEBYTECODE"] == "1"
assert os.environ["PYTENSOR_FLAGS"] == (
    "base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor"
)
assert os.environ["MPLCONFIGDIR"] == "/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib"
checkout = Path.cwd()
script = checkout / "scripts/benchmark_reference_counts.py"
fixtures = checkout / "tests/fixtures/reference_counts"
anchors = Path("/private/tmp/genomeos-b0-legacy-anchor.B5kNmZ")
runner_key = "scripts/benchmark_reference_counts.py"
old_runner_digest = "261dc9ed57b4f920e128d60060880c099ad3733984108bf0a8b29e41cf0046cc"
anchor_manifest_digests = {
    2: "de6c0877d5459db66a5abb04f946cec09df57bc07201d3556ea1c6261e8ea1e1",
    5: "929e575d165e593f77c5c30933cfe3d3c93bba33b7499e718ac9635af3062db4",
}
expected_versions = {"numpy": "2.4.6", "pandas": "3.0.5", "scipy": "1.18.1"}
assert {name: importlib.metadata.version(name) for name in expected_versions} == expected_versions
scientific_files = (
    "splits.json", "row_status.tsv", "predictions.tsv", "posteriors.tsv", "summary.json",
)
all_files = set(scientific_files) | {"manifest.json"}


def fingerprint(data: bytes) -> dict[str, object]:
    return {"sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)}


retained = {}
for folds, expected_exit in ((2, 0), (5, 2)):
    anchor = anchors / f"folds-{folds}"
    assert anchor.is_dir(), f"required retained anchor is missing: {anchor}"
    assert {path.name for path in anchor.iterdir()} == all_files, "anchor file set changed"
    contents = {name: (anchor / name).read_bytes() for name in all_files}
    assert fingerprint(contents["manifest.json"])["sha256"] == anchor_manifest_digests[folds], (
        f"retained manifest differs from root's independently pinned digest: folds={folds}"
    )
    manifest = json.loads(contents["manifest.json"])
    assert manifest["schema_version"] == 1
    assert manifest["git"] == {
        "head": "bdd524a2e16a20c9b9f97ba3775e3ac198fa7596", "dirty": False,
    }
    assert manifest["science_source_sha256"][runner_key] == old_runner_digest
    assert manifest["package_versions"] == expected_versions
    assert manifest["configuration"] == {
        "cohort_stage": "synthetic", "count_kind": "quality", "evidence_role": "synthetic",
        "folds": folds, "prior_alpha": 1.0, "prior_beta": 1.0, "seed": 42,
        "source_release": "synthetic-v1",
    }
    assert manifest["output_files"] == {
        name: fingerprint(contents[name]) for name in scientific_files
    }, "retained output bytes disagree with their original manifest"
    assert manifest["input_files"] == {
        "counts": fingerprint((fixtures / "counts.tsv").read_bytes()),
        "dependencies": fingerprint((fixtures / "dependencies.json").read_bytes()),
    }, "input identities changed since root's original capture"
    for relative, digest in manifest["science_source_sha256"].items():
        if relative != runner_key:
            assert fingerprint((checkout / relative).read_bytes())["sha256"] == digest, relative
    assert json.loads(contents["summary.json"])["comparison_complete"] is (expected_exit == 0)
    retained[folds] = (expected_exit, contents, manifest)

post_root = Path(tempfile.mkdtemp(prefix="genomeos-b0-post-integration-", dir="/private/tmp"))
for folds, (expected_exit, before_files, before_manifest) in retained.items():
    out = post_root / f"folds-{folds}"
    command = [
        str(interpreter), str(script),
        "--counts", str(fixtures / "counts.tsv"),
        "--dependencies", str(fixtures / "dependencies.json"),
        "--source-release", "synthetic-v1", "--cohort-stage", "synthetic",
        "--count-kind", "quality", "--evidence-role", "synthetic",
        "--prior-alpha", "1", "--prior-beta", "1",
        "--folds", str(folds), "--seed", "42", "--out", str(out),
    ]
    completed = subprocess.run(command, cwd=checkout, capture_output=True, text=True, check=False)
    assert completed.returncode == expected_exit, (folds, completed.returncode, completed.stderr)
    assert {path.name for path in out.iterdir()} == all_files, "post-change B0 file set changed"
    after_files = {name: (out / name).read_bytes() for name in all_files}
    for name in scientific_files:
        assert after_files[name] == before_files[name], f"legacy scientific bytes changed: {folds}/{name}"
    after_manifest = json.loads(after_files["manifest.json"])
    assert after_manifest["science_source_sha256"][runner_key] == fingerprint(script.read_bytes())["sha256"]
    assert after_manifest["science_source_sha256"][runner_key] != old_runner_digest
    comparable_before = copy.deepcopy(before_manifest)
    comparable_after = copy.deepcopy(after_manifest)
    for document in (comparable_before, comparable_after):
        del document["git"]
        del document["science_source_sha256"][runner_key]
    assert comparable_after == comparable_before, f"legacy manifest fields changed: folds={folds}"
    print(f"PASS: folds={folds}, exit={expected_exit}, five legacy files byte-identical; post={out}")
PY
```

Expected: exactly two PASS lines, with exits 0 and 2 respectively and retained post-change output paths. Root records the command, output paths and result in implementation evidence. Any mismatch remains a regression or verification blocker; do not broaden the ignored manifest fields or replace the captured evidence to make it pass.

## Execution review and final handoff

Draft-author self-review against every integration-spec section:

| Spec section | Literal implementation and acceptance coverage |
| --- | --- |
| §1 scientific scope | Global scientific contract and each task's measurable synthetic evidence; real fixed-prior matrix/calibration admission stays separate |
| §2 composition | Task 1 pure public-API adapter; Task 4 model/config parsing, lazy imports, B0 SciPy assertion, five-fold B0H refusal and defaults tests |
| §3 execution | Task 1 exact third-child seeds and typed-convergence retry; complete score frames; unavailable/missing-training/later-failure/interrupt tests; Task 4 complete row ledger and later-fold continuation |
| §4 manifest/provenance | Task 2 schema/field/file/hash checks; Task 3 actual module origins and installed-distribution ownership, exact unavailable runtime reasons; Task 4 conditional v1/v2 publication |
| §5 diagnostics | Task 1 planned slots and retained error evidence; Task 2 exact record fields, retry budget/reason validation and prefix mapping |
| §6 posterior artifacts | Task 2 deterministic fixed ZIP/NPY writer, strict no-pickle reader, Unicode/dtype/shape/companion corruption tests, sorted totals/means TSV; initial/retry retained dimensions tested |
| §7 publication/acceptance | Task 4 exclusive output, final-byte hashes, manifest last, exit classification, ordinary CI default/explicit equality plus required root pre/post comparison against retained untouched B0 anchors, and interruption/refusal tests; Task 2 invalid publication refusal |

Task-pair interface review: Task 1's result field names and `config`-carrying attempt slots match Task 2 serialization; Task 4 passes `initial_seed`, `retry_seed`, `pit_seed`, `cdf_backend` exactly. Task 2 returns diagnostic bytes, posterior bytes and a DataFrame in the order used by Task 4; its seven output filenames feed the manifest map. Task 3 source/version/runtime signatures match Task 4 calls and include the provenance helper itself. No task imports a private scientific implementation or SBC abstraction.

The code blocks are complete minimal implementations, not executed code. Static read-through found and corrected the malformed-convergence-identity escape, unused test imports, lambda assignment lint issue, long literal lines and configuration/manifest validation omissions. Placeholder scan finds only legitimate tuple type ellipses. Imports are normalized using the explicitly listed narrow import-order fixes during implementation; all test, lint and science outcomes remain unverified until execution.

Raw literal production sizes from neutral Markdown inspection: fold adapter 143 nonblank lines/~7.2 KiB; artifact module 311/~19 KiB; provenance helper 67/~3.5 KiB. Replacing the baseline runner's parser, JSON writer and run function and adding `_model_config` yields approximately 417 nonblank lines (baseline 324, remove 160, add 253). These counts are static planning estimates, not a run of the repository size gate; recheck after implementation/import ordering.

- [ ] Inspect the final diff for unrequested source/science/configuration changes and all task-pair interfaces.
- [ ] Confirm new production modules remain below 500 logical lines and 50 KiB; the runner remains below 500 logical lines. `check_module_size.py` defaults to an 800-line hard limit and omits `scripts/`, so separately count the runner and provenance helper with `wc -l` and inspect their sizes before accepting.
- [ ] Confirm the public parent wording now retains accepted fits after later failure, and the public integration spec contains explicit unavailable runtime placement. Root adopted the spec at `bdd524a2e16a20c9b9f97ba3775e3ac198fa7596` on `feat/global-af-b0h-comparison`; underlying source remains the stated `b2f7700` basis.
- [ ] In the PR say “Advances #211 and #189”, list design §§5, 7–8, 12 and integration §§2–7, and report exactly which commands ran. Do not use closing keywords until the scientific issue is actually completed.
- [ ] Require expert review of retained-fit versus completed-fold interpretation, rho versus mean interpretation, fixed priors, unchanged gates and dependence limitations. This offline comparison adapter changes no map layer; no real-data figure or publication is part of this task.
- [ ] Root chooses inline executing-plans or an already authorized delegated workflow after adopting this neutral plan. Do not dispatch agents or execute tasks from the draft-authoring turn.
