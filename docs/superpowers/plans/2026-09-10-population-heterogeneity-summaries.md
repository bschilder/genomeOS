# B0H predictive and parameter summaries Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce aligned descriptive predictive evidence and separate full-posterior parameter summaries for one accepted B0H fit.

**Architecture:** One records module owns immutable states and returned-value checks. One orchestration module guards dataset/fit identity, summarizes every accepted draw and makes one predictor call followed by one vector diagnostic call. Actual prediction/scoring exceptions retain successful parameter evidence.

**Tech Stack:** Existing Python, NumPy, pandas and public B0H interfaces; SciPy integration tests, no new dependency.

**Spec:** [Adopted design](../specs/2026-09-10-population-heterogeneity-summaries-design.md). Root personally self-reviewed both documents before adoption.

## Global Constraints

- Pure validation modules have no filesystem, network, HTTP, environment or UI dependency.
- Stochastic modules declare `SEED = 42`; inputs and configuration determine draws on a pinned runtime.
- No new package dependency, P1/production schema, serving change, inferred coordinate or radius.
- Keep existing clinical gates and global promotion defaults unchanged.
- AN=0 is retained as unavailable, never converted to frequency zero.
- No cross-variant pooling or independence claim for linked loci.
- All sampler/prior/scorer/convergence contracts in the parent B0H spec stand.
- Existing analytical, quadrature and numerical regression thresholds stay unchanged.
- Production modules target at most500 logical lines; retain the hard800/50KiB gate.
- No full study, actual NUTS fit, seed search, resource launch or external data operation.

All commands below specify the authorized implementation, not results already observed. Read AGENTS.md and required context first. Root owns issue-history verification (#211/#189), final verification and the branch/PR workflow. Both issues are advanced, not closed by this unit. Consume the reviewed public seed/error APIs from the prerequisite branch; never inspect or depend on selected-quantity execution internals.

## File map

Create `genomeos/validation/heterogeneity_summary_types.py` (records and shared returned-value checks), `genomeos/validation/heterogeneity_summaries.py` (guarded orchestration), `tests/test_heterogeneity_summaries.py` (constructed data, records, integration and failures), and `docs/research/population-heterogeneity-summaries-2026-09-10.md` (bounded evidence). Do not modify fit, generation, predictive or diagnostic-seed implementations.

Use the locked Python `/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python`
and sibling Ruff, with `PYTHONPATH=.`, `PYTHONDONTWRITEBYTECODE=1`,
`PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor`
and `MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib` on each
command. Do not install or alter the runtime. All pytest calls override quiet
defaults with `-o addopts='' -q`; retain actual RED exception tracebacks and
GREEN counts. Root owns one final stable-head full suite, task/final reviews
and PR publication. Implementers run focused tests and mandatory smoke/static/
privacy gates only, own their listed paths, and do not spawn agents or push.

### Task 1: Immutable summary records and returned-value boundaries

**Interfaces consumed:** Public generation contracts and label helpers; `FitAttemptSpec`; `DiagnosticSeedIdentity(case, attempt_id, purpose_id, spawn_key)` with `scalar_words` and `scalar_uint128`; `DiagnosticCallError(exception_class, message)`; `ReferenceHeterogeneityPrediction`; `CountPredictive`.

**Interfaces produced:** `ParameterPosteriorSummary`, `HeldoutPredictiveSummary`, `PredictiveSummaryEvidence`, `HeterogeneityFitSummary`, `require_summary_prediction(prediction, *, targets, cdf_backend, draw_count) -> None`, and `predictive_summary_rows(frame, *, targets) -> tuple[HeldoutPredictiveSummary,...]`. Exact code follows.

- [ ] Write the first test file with this full initial content.

```python
"""Constructed B0H summary evidence; no sampler execution (design §§7–8,12)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace

import numpy as np
import pandas as pd
import pytest

from genomeos.validation.heterogeneity_simulation_types import (
    HeldoutTarget,
    SbcCaseId,
    generation_id,
    simulation_reference_count,
)
from genomeos.validation.heterogeneity_summary_types import (
    ParameterPosteriorSummary,
    predictive_summary_rows,
)


def ordinary_target():
    case = SbcCaseId(0, 0, 0, 0)
    row = simulation_reference_count(
        generation_id(case), "heldout", "fresh_population", 2, 20
    )
    return HeldoutTarget("fresh_population", row, .5, None, None, None, None)


def literal_frame():
    return pd.DataFrame({
        "log_score": [-np.inf],
        "absolute_error": [.4],
        "squared_error": [.16],
        "coverage_50": [False],
        "interval_width_50": [.5],
        "coverage_80": [True],
        "interval_width_80": [.8],
        "coverage_95": [True],
        "interval_width_95": [1.],
        "randomized_pit": [.1],
    })


def test_literal_parameter_interval_and_error_evidence():
    item = ParameterPosteriorSummary(
        "mean", .25, .5, (.1, .2, .25, .5, .75, .8, .9), 2000
    )
    assert item.absolute_error == .25
    assert item.squared_error == .0625
    assert item.coverage == (True, True, True)
    assert item.interval_width == pytest.approx((.5, .6, .8), rel=0, abs=2e-15)
    with pytest.raises(FrozenInstanceError):
        item.estimate = .25
    for changes in (
        {"parameter": "latent_frequency"}, {"draw_count": True},
        {"truth": np.nan}, {"estimate": 0.}, {"quantiles": (.2,)},
        {"quantiles": [.1, .2, .25, .5, .75, .8, .9]},
        {"quantiles": (.1, .2, .75, .5, .25, .8, .9)},
    ):
        with pytest.raises(ValueError):
            replace(item, **changes)


def test_negative_infinite_log_score_is_retained():
    target = ordinary_target()
    rows = predictive_summary_rows(literal_frame(), targets=(target,))
    assert rows[0].target == target
    assert rows[0].log_score == -np.inf
    assert rows[0].coverage == (False, True, True)
    assert rows[0].interval_width == (.5, .8, 1.)
    assert rows[0].randomized_pit == .1


@pytest.mark.parametrize("field,value", [
    ("log_score", np.nan), ("log_score", np.inf), ("log_score", .01),
    ("absolute_error", np.inf), ("squared_error", -.1),
    ("interval_width_80", 1.1), ("randomized_pit", np.nan),
    ("randomized_pit", 1.1),
])
def test_nonfinite_or_out_of_domain_frame_is_a_defect(field, value):
    frame = literal_frame()
    frame[field] = [value]
    with pytest.raises(ValueError):
        predictive_summary_rows(frame, targets=(ordinary_target(),))


def test_malformed_frames_are_not_coerced():
    frame = literal_frame()
    malformed = (
        frame.to_dict(), frame.iloc[:0], frame.assign(extra=0),
        frame.rename(index={0: "row0"}),
        frame.drop(columns="log_score"), frame.loc[:, frame.columns[::-1]],
        frame.astype({"absolute_error": "object"}),
        frame.astype({"squared_error": "float32"}),
        frame.astype({"randomized_pit": "complex128"}),
        frame.assign(coverage_50=1), frame.assign(absolute_error=True),
        frame.assign(coverage_50=True, coverage_80=False),
        frame.assign(interval_width_50=.9),
        pd.concat([frame, frame]),
    )
    for bad in malformed:
        with pytest.raises(ValueError):
            predictive_summary_rows(bad, targets=(ordinary_target(),))


def test_output_rows_retain_no_mutable_dataframe_reference():
    frame = literal_frame()
    rows = predictive_summary_rows(frame, targets=(ordinary_target(),))
    frame.loc[0, "randomized_pit"] = .9
    assert rows[0].randomized_pit == .1
    with pytest.raises(FrozenInstanceError):
        rows[0].randomized_pit = .9
```

- [ ] Run `/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python -m pytest tests/test_heterogeneity_summaries.py -o addopts='' -q`; expect collection failure for the absent new module.
- [ ] Create `genomeos/validation/heterogeneity_summary_types.py` with this full content.

```python
"""Immutable B0H descriptive summaries and boundaries (design §§5,7–8,12; #211)."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Literal

import numpy as np
import pandas as pd

from genomeos.surfaces.heterogeneity_types import ReferenceHeterogeneityPrediction
from genomeos.validation.heterogeneity_attempts import FitAttemptSpec
from genomeos.validation.heterogeneity_diagnostic_seeds import DiagnosticSeedIdentity
from genomeos.validation.heterogeneity_sbc_controls import DiagnosticCallError
from genomeos.validation.heterogeneity_simulation_types import (
    HeldoutTarget,
    fixed_simulation_truth,
    generation_id,
    simulation_integer,
    simulation_probability,
    simulation_reference_count,
)
from genomeos.validation.predictive import CountPredictive

_PAIRS = ((2, 4), (1, 5), (0, 6))
_COLUMNS = (
    "log_score", "absolute_error", "squared_error", "coverage_50",
    "interval_width_50", "coverage_80", "interval_width_80",
    "coverage_95", "interval_width_95", "randomized_pit",
)


def _tuple(value: object, length: int | None, name: str) -> tuple:
    if not isinstance(value, tuple) or length is not None and len(value) != length:
        raise ValueError(f"{name} must be an immutable tuple of the required length")
    return value


def _record(value, cls):
    if not isinstance(value, cls):
        raise ValueError(f"expected {cls.__name__}")
    return replace(value)


def _backend(value: object) -> None:
    if type(value) is not str or value not in ("scipy", "cupy"):
        raise ValueError("cdf_backend must be scipy or cupy")


def _positive_count(value: object) -> int:
    count = simulation_integer(value, "draw_count")
    if count <= 0:
        raise ValueError("draw_count must be positive")
    return count


def _targets(value: object) -> tuple[HeldoutTarget, ...]:
    targets = tuple(_record(target, HeldoutTarget) for target in _tuple(value, None, "targets"))
    if not targets or len({target.row.record_id for target in targets}) != len(targets):
        raise ValueError("targets must be nonempty with unique row IDs")
    if len({target.row.variant_id for target in targets}) != 1 or any(t.row.an != 20 for t in targets):
        raise ValueError("heldout summaries require one variant and AN20 targets")
    return targets


@dataclass(frozen=True)
class ParameterPosteriorSummary:
    parameter: Literal["mean", "rho"]
    truth: float
    estimate: float
    quantiles: tuple[float, ...]
    draw_count: int

    def __post_init__(self) -> None:
        if type(self.parameter) is not str or self.parameter not in ("mean", "rho"):
            raise ValueError("parameter must be mean or rho")
        truth = simulation_probability(self.truth, "truth")
        estimate = simulation_probability(self.estimate, "estimate")
        quantiles = tuple(
            simulation_probability(value, "quantile")
            for value in _tuple(self.quantiles, 7, "quantiles")
        )
        if not 0.0 < estimate < 1.0 or any(not 0.0 < q < 1.0 for q in quantiles):
            raise ValueError("accepted posterior summaries must be interior")
        if tuple(sorted(quantiles)) != quantiles:
            raise ValueError("quantiles must be nondecreasing")
        if self.parameter == "rho" and truth == 1.0:
            raise ValueError("rho truth must be below one")
        object.__setattr__(self, "truth", truth)
        object.__setattr__(self, "estimate", estimate)
        object.__setattr__(self, "quantiles", quantiles)
        object.__setattr__(self, "draw_count", _positive_count(self.draw_count))

    @property
    def absolute_error(self) -> float:
        return abs(self.estimate - self.truth)

    @property
    def squared_error(self) -> float:
        return (self.estimate - self.truth) ** 2

    @property
    def coverage(self) -> tuple[bool, bool, bool]:
        return tuple(self.quantiles[lo] <= self.truth <= self.quantiles[hi] for lo, hi in _PAIRS)

    @property
    def interval_width(self) -> tuple[float, float, float]:
        return tuple(self.quantiles[hi] - self.quantiles[lo] for lo, hi in _PAIRS)


@dataclass(frozen=True)
class HeldoutPredictiveSummary:
    target: HeldoutTarget
    log_score: float
    absolute_error: float
    squared_error: float
    coverage: tuple[bool, bool, bool]
    interval_width: tuple[float, float, float]
    randomized_pit: float

    def __post_init__(self) -> None:
        target = _record(self.target, HeldoutTarget)
        if target.row.an != 20:
            raise ValueError("summary target must have AN20")
        if type(self.log_score) not in (float, np.float16, np.float32, np.float64):
            raise ValueError("log_score must be a supported floating scalar")
        score = float(self.log_score)
        if math.isnan(score) or score > 0.0:
            raise ValueError("log_score must be nonpositive, including negative infinity")
        coverage = _tuple(self.coverage, 3, "coverage")
        if any(type(value) not in (bool, np.bool_) for value in coverage):
            raise ValueError("coverage must contain Boolean scalars")
        coverage = tuple(bool(value) for value in coverage)
        widths = tuple(
            simulation_probability(value, "interval_width")
            for value in _tuple(self.interval_width, 3, "interval_width")
        )
        if coverage != tuple(sorted(coverage)) or widths != tuple(sorted(widths)):
            raise ValueError("coverage and widths must be nested in 50/80/95 order")
        object.__setattr__(self, "target", target)
        object.__setattr__(self, "log_score", score)
        object.__setattr__(self, "coverage", coverage)
        object.__setattr__(self, "interval_width", widths)
        for name in ("absolute_error", "squared_error", "randomized_pit"):
            object.__setattr__(self, name, simulation_probability(getattr(self, name), name))


def require_summary_prediction(
    prediction: ReferenceHeterogeneityPrediction, *,
    targets: tuple[HeldoutTarget, ...], cdf_backend: Literal["scipy", "cupy"],
    draw_count: int,
) -> None:
    """Check exact row order, backend and array representation before scoring."""
    targets = _targets(targets)
    _backend(cdf_backend)
    count = _positive_count(draw_count)
    if not isinstance(prediction, ReferenceHeterogeneityPrediction):
        raise ValueError("predictor must return ReferenceHeterogeneityPrediction")
    if not isinstance(prediction.marginal_predictive, CountPredictive):
        raise ValueError("prediction must contain CountPredictive")
    if (
        type(prediction.observation_ids) is not tuple
        or prediction.observation_ids != tuple(target.row.record_id for target in targets)
        or type(prediction.unavailable_ids) is not tuple
        or prediction.unavailable_ids != ()
    ):
        raise ValueError("prediction IDs must match original target order exactly")
    marginal = prediction.marginal_predictive
    if type(marginal.cdf_backend) is not str or marginal.cdf_backend != cdf_backend:
        raise ValueError("returned backend does not match explicit backend")
    for array in (marginal.mean_draws, marginal.concentration):
        if (
            not isinstance(array, np.ndarray) or array.dtype != np.dtype("float64")
            or array.shape != (count, len(targets)) or not np.all(np.isfinite(array))
            or array.flags.writeable
        ):
            raise ValueError("prediction arrays must be immutable finite float64 with exact shape")
    if np.any((marginal.mean_draws <= 0.) | (marginal.mean_draws >= 1.)):
        raise ValueError("B0H predictive mean draws must be interior")
    if np.any(marginal.concentration <= 0.):
        raise ValueError("B0H predictive concentration must be positive")


def predictive_summary_rows(
    frame: pd.DataFrame, *, targets: tuple[HeldoutTarget, ...],
) -> tuple[HeldoutPredictiveSummary, ...]:
    """Validate public diagnostic output without casting or reordering defects."""
    targets = _targets(targets)
    if not isinstance(frame, pd.DataFrame) or tuple(frame.columns) != _COLUMNS:
        raise ValueError("diagnostics must return the exact public DataFrame columns")
    if type(frame.index) is not pd.RangeIndex or not frame.index.equals(pd.RangeIndex(len(targets))):
        raise ValueError("diagnostics must retain canonical positional row order")
    for name in _COLUMNS:
        dtype = np.dtype("bool") if name.startswith("coverage_") else np.dtype("float64")
        if frame[name].dtype != dtype:
            raise ValueError(f"diagnostic {name} has an unexpected dtype")
    return tuple(
        HeldoutPredictiveSummary(
            target, frame.at[index, "log_score"], frame.at[index, "absolute_error"],
            frame.at[index, "squared_error"],
            tuple(frame.at[index, f"coverage_{level}"] for level in (50, 80, 95)),
            tuple(frame.at[index, f"interval_width_{level}"] for level in (50, 80, 95)),
            frame.at[index, "randomized_pit"],
        )
        for index, target in enumerate(targets)
    )


@dataclass(frozen=True)
class PredictiveSummaryEvidence:
    seed: DiagnosticSeedIdentity
    seed_words: tuple[int, int, int, int]
    seed_uint128: int
    cdf_backend: Literal["scipy", "cupy"]
    draw_count: int
    targets: tuple[HeldoutTarget, ...]
    status: Literal["complete", "prediction_failed", "diagnostics_failed"]
    prediction: ReferenceHeterogeneityPrediction | None
    rows: tuple[HeldoutPredictiveSummary, ...]
    error: DiagnosticCallError | None

    def __post_init__(self) -> None:
        seed = _record(self.seed, DiagnosticSeedIdentity)
        if seed.purpose_id != 7 or seed.spawn_key != ():
            raise ValueError("predictive evidence requires purpose7 with an empty spawn key")
        words = tuple(
            simulation_integer(value, "seed word")
            for value in _tuple(self.seed_words, 4, "seed_words")
        )
        scalar = simulation_integer(self.seed_uint128, "seed_uint128")
        if words != seed.scalar_words or scalar != seed.scalar_uint128:
            raise ValueError("exact seed words and scalar must match their identity")
        _backend(self.cdf_backend)
        count = _positive_count(self.draw_count)
        targets = _targets(self.targets)
        kinds = ("shared_cluster0", "fresh_cluster") if seed.case.study_id == 2 else ("fresh_population",)
        if tuple(target.kind for target in targets) != kinds:
            raise ValueError("target kinds/order do not match the study")
        for target in targets:
            expected = simulation_reference_count(
                generation_id(seed.case), "heldout", target.kind, target.row.ac, 20
            )
            if target.row != expected:
                raise ValueError("target row/variant identity does not match the case")
        rows = tuple(_record(row, HeldoutPredictiveSummary) for row in _tuple(self.rows, None, "rows"))
        if type(self.status) is not str or self.status not in (
            "complete", "prediction_failed", "diagnostics_failed"
        ):
            raise ValueError("unknown predictive evidence status")
        if self.status == "prediction_failed":
            if self.prediction is not None:
                raise ValueError("failed prediction cannot retain a returned object")
        else:
            require_summary_prediction(
                self.prediction, targets=targets, cdf_backend=self.cdf_backend, draw_count=count
            )
        if self.status == "complete":
            if self.error is not None or tuple(row.target for row in rows) != targets:
                raise ValueError("complete diagnostics must contain all aligned rows and no error")
        else:
            _record(self.error, DiagnosticCallError)
            if rows:
                raise ValueError("failed predictive calls cannot carry partial successful rows")
        object.__setattr__(self, "seed", seed)
        object.__setattr__(self, "seed_words", words)
        object.__setattr__(self, "seed_uint128", scalar)
        object.__setattr__(self, "draw_count", count)
        object.__setattr__(self, "targets", targets)
        object.__setattr__(self, "rows", rows)


@dataclass(frozen=True)
class HeterogeneityFitSummary:
    spec: FitAttemptSpec
    variant_id: str
    parameters: tuple[ParameterPosteriorSummary, ParameterPosteriorSummary]
    predictive: PredictiveSummaryEvidence

    def __post_init__(self) -> None:
        spec = _record(self.spec, FitAttemptSpec)
        parameters = tuple(
            _record(item, ParameterPosteriorSummary)
            for item in _tuple(self.parameters, 2, "parameters")
        )
        if tuple(item.parameter for item in parameters) != ("mean", "rho"):
            raise ValueError("parameter summaries must be ordered mean then rho")
        predictive = _record(self.predictive, PredictiveSummaryEvidence)
        if predictive.seed.case != spec.case or predictive.seed.attempt_id != spec.attempt_id:
            raise ValueError("predictive seed must bind the accepted attempt")
        count = spec.config.chains * spec.config.draws
        if predictive.draw_count != count or any(item.draw_count != count for item in parameters):
            raise ValueError("every summary must use all accepted chain/draw entries")
        expected_variant = predictive.targets[0].row.variant_id
        if type(self.variant_id) is not str or self.variant_id != expected_variant:
            raise ValueError("summary variant must match case-bound heldouts")
        truth = fixed_simulation_truth(spec.case)
        actual = tuple(item.truth for item in parameters)
        if truth is not None and actual != (truth.mean, truth.rho):
            raise ValueError("parameter truths must match the fixed study")
        if spec.case.study_id == 0 and not all(0. < value < 1. for value in actual):
            raise ValueError("prior-study truths must be interior")
        object.__setattr__(self, "spec", spec)
        object.__setattr__(self, "parameters", parameters)
        object.__setattr__(self, "predictive", predictive)

    @property
    def h_ess_status(self) -> Literal["not_computed"]:
        return "not_computed"

    @property
    def h_mcse_status(self) -> Literal["not_computed"]:
        return "not_computed"
```

- [ ] Run `/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python -m pytest tests/test_heterogeneity_summaries.py -o addopts='' -q`, `python scripts/smoke.py`, and `python scripts/check_module_size.py`; expect success. These checks prove record behavior only.
- [ ] Run locked sibling Ruff on the Task1 production/test files and rerun focused tests and mandatory smoke after any final source edit. Before a task commit, run the locked Python on `scripts/check_private_files.py`, stage only `genomeos/validation/heterogeneity_summary_types.py` and `tests/test_heterogeneity_summaries.py`, inspect `git diff --cached --name-only`, run `git diff --cached --check` and repeat privacy, then commit `feat: add B0H descriptive summary contracts`. This advances #211/#189 without closing either. Root owns the separate adopted-docs commit.

### Task 2: Guarded all-draw summaries and one vector predictive call

**Interfaces consumed:** All Task 1 public interfaces, public `require_fit_identity(dataset, *, spec, fit)`, `predict_reference_population_heterogeneity(fitted, testing, *, cdf_backend)`, `predictive_diagnostics(predictive, ac, an, seed)` and the declared purpose7 seed/error interfaces.

**Interface produced:** `summarize_heterogeneity_fit(dataset: GeneratedDataset, *, attempt: FitAttemptResult, cdf_backend: Literal["scipy","cupy"]) -> HeterogeneityFitSummary`. No backend default or selected-quantity input.

- [ ] Append this full content to the test module. Imports are shown here with their tests for a complete runnable block; move them into the module's import section when applying.

```python
import genomeos.validation.heterogeneity_summaries as summaries
from genomeos.surfaces.heterogeneity_types import (
    PopulationHeterogeneityFit,
    VariantHeterogeneityDiagnostics,
    VariantTrainingCounts,
)
from genomeos.surfaces.reference_heterogeneity import predict_reference_population_heterogeneity
from genomeos.validation.heterogeneity_attempts import (
    AttemptError,
    FitAttemptResult,
    FitIdentityError,
    plan_fit_attempt,
)
from genomeos.validation.heterogeneity_diagnostic_seeds import DiagnosticSeedIdentity
from genomeos.validation.heterogeneity_sbc_controls import DiagnosticCallError
from genomeos.validation.heterogeneity_simulation_types import (
    AllUnavailableDataset,
    GeneratedDataset,
    GenerationProvenance,
    ParameterTruth,
    SharedHistory,
    fixed_simulation_truth,
    sbc_seed_identity,
    simulation_training_an,
)
from genomeos.validation.predictive import CountPredictive


def literal_dataset(study=0, case_number=0, track=0):
    case = SbcCaseId(track, study, case_number, 0)
    generation = generation_id(case)
    provenance = GenerationProvenance(generation, tuple(
        sbc_seed_identity(case, purpose_id=purpose, attempt_id=0) for purpose in range(4)
    ))
    truth = fixed_simulation_truth(case) or ParameterTruth(.5, .2)
    ans = simulation_training_an(case)
    counts = tuple(
        int(an * truth.mean) if study == 4 else an // 2 for an in ans
    )
    training = tuple(
        simulation_reference_count(generation, "train", str(i), ac, an)
        for i, (ac, an) in enumerate(zip(counts, ans, strict=True))
    )
    history = None
    if study == 2:
        history = SharedHistory((.2, .8), (.4,) * 16, (True,) * 8 + (False,) * 8)
        latents = (.2,) * 8 + (.4,) * 8
        heldouts = (
            HeldoutTarget("shared_cluster0", simulation_reference_count(
                generation, "heldout", "shared_cluster0", 2, 20
            ), .2, 0, .2, .3, True),
            HeldoutTarget("fresh_cluster", simulation_reference_count(
                generation, "heldout", "fresh_cluster", 17, 20
            ), .7, 2, .9, .7, False),
        )
    else:
        latent = truth.mean if truth.rho == 0. else .5
        latents = (latent,) * 16
        ac = int(20 * truth.mean) if study == 4 else 2
        heldouts = (HeldoutTarget("fresh_population", simulation_reference_count(
            generation, "heldout", "fresh_population", ac, 20
        ), latent, None, None, None, None),)
    return GeneratedDataset(case, provenance, truth, training, latents, history, heldouts, 0, 0)


def literal_attempt(dataset, attempt_id=0, grid=False):
    spec = plan_fit_attempt(dataset, attempt_id=attempt_id)
    shape = (4, spec.config.draws, 1)
    if grid:
        size = 4 * spec.config.draws
        mean = ((np.arange(size, dtype=np.float64) + 1) / (size + 1)).reshape(shape)
        rho = mean / 2
    else:
        mean = np.full(shape, .5, dtype=np.float64)
        rho = np.full(shape, 1 / 3, dtype=np.float64)
    variant = dataset.training[0].variant_id
    available = tuple(row for row in dataset.training if row.an > 0)
    fit = PopulationHeterogeneityFit(
        spec.config, (variant,), mean, rho,
        tuple(sorted(row.record_id for row in dataset.training)),
        tuple(sorted({row.group_id for row in dataset.training})),
        tuple(sorted(row.record_id for row in dataset.training if row.an == 0)),
        (VariantTrainingCounts(variant, len(available),
                               sum(row.ac for row in available),
                               sum(row.an for row in available)),),
        (VariantHeterogeneityDiagnostics(variant, 1., 250., 250.),), 0,
    )
    return FitAttemptResult(spec, "accepted", fit, None, (), None)


def raising(error):
    def fail(*args, **kwargs):
        raise error
    return fail


def test_all_draw_linear_quantiles_survive_predictor_failure(monkeypatch):
    data = literal_dataset()
    attempt = literal_attempt(data, grid=True)
    monkeypatch.setattr(summaries, "predict_reference_population_heterogeneity",
                        raising(ArithmeticError("literal predictor failure")))
    result = summaries.summarize_heterogeneity_fit(data, attempt=attempt, cdf_backend="scipy")
    expected = tuple((1 + 1999 * p) / 2001 for p in (.025, .1, .25, .5, .75, .9, .975))
    mean, rho = result.parameters
    assert mean.quantiles == pytest.approx(expected, rel=0, abs=2e-15)
    assert rho.quantiles == pytest.approx(tuple(q / 2 for q in expected), rel=0, abs=2e-15)
    assert mean.estimate == pytest.approx(.5, rel=0, abs=2e-15)
    assert rho.estimate == pytest.approx(.25, rel=0, abs=2e-15)
    assert mean.draw_count == rho.draw_count == 2000
    assert rho.absolute_error == pytest.approx(.05, rel=0, abs=2e-15)
    assert rho.squared_error == pytest.approx(.0025, rel=0, abs=2e-15)
    assert result.predictive.status == "prediction_failed"
    assert result.predictive.prediction is None and result.predictive.rows == ()
    assert result.predictive.error == DiagnosticCallError(
        "builtins.ArithmeticError", "literal predictor failure"
    )
    assert result.h_ess_status == result.h_mcse_status == "not_computed"


@pytest.mark.parametrize("bad", [
    [.5] * 7, np.full(7, "0.5"), np.full(7, .5, dtype=np.float32),
    np.full((1, 7), .5), np.full(6, .5), np.full(7, np.nan),
    np.full(7, np.inf), np.full(7, True), np.full(7, .5 + 0j),
])
def test_malformed_quantiles_propagate_before_seed_or_prediction(monkeypatch, bad):
    data = literal_dataset()
    attempt = literal_attempt(data)
    monkeypatch.setattr(summaries.np, "quantile", lambda *a, **k: bad)
    sentinel = raising(AssertionError("diagnostic work must not begin"))
    monkeypatch.setattr(summaries, "DiagnosticSeedIdentity", sentinel)
    monkeypatch.setattr(summaries, "predict_reference_population_heterogeneity", sentinel)
    with pytest.raises(ValueError, match="posterior quantiles"):
        summaries.summarize_heterogeneity_fit(data, attempt=attempt, cdf_backend="scipy")


@pytest.mark.parametrize("bad", [True, "0.5", np.float32(.5), np.nan, np.inf, np.array(.5)])
def test_malformed_mean_propagates_without_conversion(monkeypatch, bad):
    data = literal_dataset()
    attempt = literal_attempt(data)
    monkeypatch.setattr(summaries.np, "mean", lambda *a, **k: bad)
    sentinel = raising(AssertionError("diagnostic work must not begin"))
    monkeypatch.setattr(summaries, "DiagnosticSeedIdentity", sentinel)
    monkeypatch.setattr(summaries, "predict_reference_population_heterogeneity", sentinel)
    with pytest.raises(ValueError, match="posterior mean"):
        summaries.summarize_heterogeneity_fit(data, attempt=attempt, cdf_backend="scipy")


def test_actual_predictor_and_scorer_uniform_count_anchor_and_vector_pit():
    data = literal_dataset(study=2)
    attempt = literal_attempt(data)
    result = summaries.summarize_heterogeneity_fit(data, attempt=attempt, cdf_backend="scipy")
    evidence = result.predictive
    assert evidence.status == "complete"
    assert tuple(row.target.kind for row in evidence.rows) == ("shared_cluster0", "fresh_cluster")
    assert tuple(row.target.row.ac for row in evidence.rows) == (2, 17)
    assert evidence.prediction.observation_ids == tuple(t.row.record_id for t in data.heldouts)
    assert evidence.prediction.marginal_predictive.mean_draws.shape == (2000, 2)
    assert np.all(evidence.prediction.marginal_predictive.mean_draws == .5)
    np.testing.assert_allclose(evidence.prediction.marginal_predictive.concentration,
                               2., rtol=0, atol=2e-14)
    # Independent uniform-count distribution anchor: Beta(1,1) gives P(Y=k)=1/21.
    assert [row.log_score for row in evidence.rows] == pytest.approx([-np.log(21)] * 2, rel=0, abs=2e-12)
    assert [row.absolute_error for row in evidence.rows] == pytest.approx([.4, .35], rel=0, abs=2e-15)
    assert [row.squared_error for row in evidence.rows] == pytest.approx([.16, .1225], rel=0, abs=2e-15)
    assert all(row.coverage == (False, True, True) for row in evidence.rows)
    assert all(row.interval_width == pytest.approx((.5, .8, 1.), rel=0, abs=2e-15) for row in evidence.rows)
    entropy = (42, 211, 1, 0, 2, 0, 0, 7, 0)
    words = tuple(int(word) for word in np.random.SeedSequence(entropy).generate_state(4, dtype=np.uint32))
    scalar = sum(word << (32 * i) for i, word in enumerate(words))
    assert evidence.seed.entropy == entropy and evidence.seed.spawn_key == ()
    assert evidence.seed_words == words and evidence.seed_uint128 == scalar
    uniforms = np.random.Generator(np.random.PCG64(scalar)).random(2)
    assert [row.randomized_pit for row in evidence.rows] == pytest.approx(
        ((2 + uniforms[0]) / 21, (17 + uniforms[1]) / 21), rel=0, abs=2e-12
    )
    # The same single variant is broadcast to both targets, without inferring cluster conditioning.
    assert result.parameters[0].truth == .01
    assert result.parameters[1].truth == .1


def test_one_original_order_vector_call_and_actual_scalar_seed(monkeypatch):
    data = literal_dataset(study=2, track=1)
    attempt = literal_attempt(data, attempt_id=1)
    predictor = summaries.predict_reference_population_heterogeneity
    events = []

    def predicted(fitted, testing, *, cdf_backend):
        events.append(("predictor", fitted is attempt.fit, tuple(testing), cdf_backend))
        return predictor(fitted, testing, cdf_backend=cdf_backend)

    def diagnosed(predictive, ac, an, seed):
        events.append(("diagnostics", tuple(ac), tuple(an), seed))
        first = literal_frame()
        second = literal_frame().assign(absolute_error=.35, squared_error=.1225, randomized_pit=.85)
        return pd.concat((first, second), ignore_index=True)

    monkeypatch.setattr(summaries, "predict_reference_population_heterogeneity", predicted)
    monkeypatch.setattr(summaries, "predictive_diagnostics", diagnosed)
    result = summaries.summarize_heterogeneity_fit(data, attempt=attempt, cdf_backend="scipy")
    assert len(events) == 2
    assert events[0] == ("predictor", True, tuple(t.row for t in data.heldouts), "scipy")
    assert events[1] == ("diagnostics", (2, 17), (20, 20), result.predictive.seed_uint128)
    assert result.predictive.seed == DiagnosticSeedIdentity(data.case_id, 1, 7, ())
    assert result.parameters[0].draw_count == result.predictive.draw_count == 4000
    assert [(r.target.kind, r.absolute_error, r.randomized_pit) for r in result.predictive.rows] == [
        ("shared_cluster0", .4, .1), ("fresh_cluster", .35, .85)
    ]


def test_scorer_exception_retains_actual_prediction_and_parameters(monkeypatch):
    data = literal_dataset()
    attempt = literal_attempt(data)
    returned = predict_reference_population_heterogeneity(
        attempt.fit, tuple(t.row for t in data.heldouts), cdf_backend="cupy"
    )
    monkeypatch.setattr(summaries, "predict_reference_population_heterogeneity", lambda *a, **k: returned)
    monkeypatch.setattr(summaries, "predictive_diagnostics", raising(RuntimeError("")))
    result = summaries.summarize_heterogeneity_fit(data, attempt=attempt, cdf_backend="cupy")
    assert result.predictive.status == "diagnostics_failed"
    assert result.predictive.prediction is returned
    assert result.predictive.cdf_backend == "cupy"
    assert result.predictive.error == DiagnosticCallError("builtins.RuntimeError", "")
    assert result.predictive.rows == ()
    assert result.parameters[0].estimate == .5


@pytest.mark.parametrize("study,case_number,expected_mean", [(1, 0, .001), (4, 0, 0.), (4, 1, 1.)])
def test_stress_truth_retained_without_a_posterior_boundary_atom(
    monkeypatch, study, case_number, expected_mean
):
    data = literal_dataset(study=study, case_number=case_number)
    attempt = literal_attempt(data)
    monkeypatch.setattr(summaries, "predict_reference_population_heterogeneity", raising(ValueError("fixture")))
    result = summaries.summarize_heterogeneity_fit(data, attempt=attempt, cdf_backend="scipy")
    assert result.parameters[0].truth == expected_mean
    assert result.parameters[1].truth == 0.
    assert result.parameters[1].coverage == (False, False, False)
    assert result.parameters[0].quantiles == (.5,) * 7


def test_identity_refusal_precedes_summary_work_and_seed_state(monkeypatch):
    data = literal_dataset()
    attempt = literal_attempt(data)
    fit = replace(attempt.fit, training_counts=(replace(attempt.fit.training_counts[0], training_ac=1),))
    wrong = replace(attempt, fit=fit)
    sentinel = raising(AssertionError("diagnostic work must not begin"))
    monkeypatch.setattr(summaries.np, "quantile", sentinel)
    monkeypatch.setattr(summaries.np.random, "default_rng", sentinel)
    monkeypatch.setattr(summaries, "DiagnosticSeedIdentity", sentinel)
    monkeypatch.setattr(summaries, "predict_reference_population_heterogeneity", sentinel)
    with pytest.raises(FitIdentityError) as caught:
        summaries.summarize_heterogeneity_fit(data, attempt=wrong, cdf_backend="scipy")
    assert caught.value.mismatches == ("training_counts",)


def test_refuse_ineligible_callers_before_prediction(monkeypatch):
    data = literal_dataset()
    accepted = literal_attempt(data)
    failure = FitAttemptResult(accepted.spec, "failed", None,
                              AttemptError("value", "builtins.ValueError", "bad", None, None, None), (), None)
    case = SbcCaseId(0, 3, 0, 0)
    generation = generation_id(case)
    unavailable = AllUnavailableDataset(case, GenerationProvenance(generation, tuple(
        sbc_seed_identity(case, purpose_id=p, attempt_id=0) for p in range(4)
    )), tuple(simulation_reference_count(generation, "train", str(i), 0, 0) for i in range(16)))
    monkeypatch.setattr(summaries, "predict_reference_population_heterogeneity",
                        raising(AssertionError("predictor must not run")))
    for dataset, attempt, backend in ((unavailable, accepted, "scipy"),
                                       (data, failure, "scipy"), (data, accepted, "auto")):
        with pytest.raises(ValueError):
            summaries.summarize_heterogeneity_fit(dataset, attempt=attempt, cdf_backend=backend)


def test_wrong_prediction_identity_shape_or_backend_propagates(monkeypatch):
    data = literal_dataset(study=2)
    attempt = literal_attempt(data)
    actual = predict_reference_population_heterogeneity(attempt.fit, tuple(t.row for t in data.heldouts))
    reversed_ids = replace(actual, observation_ids=actual.observation_ids[::-1])
    wrong_backend = replace(actual, marginal_predictive=CountPredictive(
        actual.marginal_predictive.mean_draws, actual.marginal_predictive.concentration, "cupy"
    ))
    wrong_draws = replace(actual, marginal_predictive=CountPredictive(
        np.full((4, 2), .5), np.full((4, 2), 2.)
    ))
    binomial = replace(actual, marginal_predictive=CountPredictive(np.full((2000, 2), .5)))
    monkeypatch.setattr(summaries, "predictive_diagnostics",
                        raising(AssertionError("scorer must not see malformed predictions")))
    for returned in (object(), reversed_ids, wrong_backend, wrong_draws, binomial):
        monkeypatch.setattr(summaries, "predict_reference_population_heterogeneity",
                            lambda *a, value=returned, **k: value)
        with pytest.raises(ValueError):
            summaries.summarize_heterogeneity_fit(data, attempt=attempt, cdf_backend="scipy")


def test_malformed_scorer_return_and_baseexception_propagate(monkeypatch):
    data = literal_dataset()
    attempt = literal_attempt(data)
    monkeypatch.setattr(summaries, "predictive_diagnostics", lambda *a, **k: literal_frame().assign(log_score=np.nan))
    with pytest.raises(ValueError):
        summaries.summarize_heterogeneity_fit(data, attempt=attempt, cdf_backend="scipy")
    monkeypatch.setattr(summaries, "predictive_diagnostics", raising(KeyboardInterrupt()))
    with pytest.raises(KeyboardInterrupt):
        summaries.summarize_heterogeneity_fit(data, attempt=attempt, cdf_backend="scipy")


def test_enclosing_summary_binds_valid_predictive_evidence_to_its_attempt(monkeypatch):
    data = literal_dataset(study=2)
    attempt = literal_attempt(data)
    monkeypatch.setattr(summaries, "predict_reference_population_heterogeneity",
                        raising(ValueError("fixture")))
    result = summaries.summarize_heterogeneity_fit(data, attempt=attempt, cdf_backend="scipy")
    # Stress tracks share generation99 targets: each changed evidence object is
    # independently valid, but neither belongs to the original fitted attempt.
    for seed in (
        DiagnosticSeedIdentity(SbcCaseId(1, 2, 0, 0), 0, 7, ()),
        DiagnosticSeedIdentity(data.case_id, 1, 7, ()),
    ):
        changed = replace(result.predictive, seed=seed, seed_words=seed.scalar_words,
                          seed_uint128=seed.scalar_uint128)
        with pytest.raises(ValueError, match="predictive seed"):
            replace(result, predictive=changed)


def test_enclosing_records_reject_inconsistent_evidence(monkeypatch):
    data = literal_dataset()
    attempt = literal_attempt(data)
    monkeypatch.setattr(summaries, "predict_reference_population_heterogeneity", raising(ValueError("fixture")))
    result = summaries.summarize_heterogeneity_fit(data, attempt=attempt, cdf_backend="scipy")
    for changes in ({"parameters": result.parameters[::-1]}, {"variant_id": "other"},
                    {"parameters": (replace(result.parameters[0], draw_count=4), result.parameters[1])}):
        with pytest.raises(ValueError):
            replace(result, **changes)
    evidence = result.predictive
    for changes in ({"seed_uint128": True}, {"seed_words": (0, 0, 0, 0)},
                    {"error": None}, {"status": "complete"}, {"rows": []},
                    {"seed": DiagnosticSeedIdentity(SbcCaseId(1, 0, 0, 0), 0, 7, ())}):
        with pytest.raises(ValueError):
            replace(evidence, **changes)
```

- [ ] Run `/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python -m pytest tests/test_heterogeneity_summaries.py -o addopts='' -q`; expect absent orchestration import failure.
- [ ] Create `genomeos/validation/heterogeneity_summaries.py` with this full content.

```python
"""Guarded B0H post-fit descriptive summaries (design §§5,7–8,12; #211)."""

from __future__ import annotations

from dataclasses import replace
from typing import Literal

import numpy as np

from genomeos.surfaces.heterogeneity_types import PopulationHeterogeneityFit
from genomeos.surfaces.reference_heterogeneity import predict_reference_population_heterogeneity
from genomeos.validation.heterogeneity_attempts import FitAttemptResult, require_fit_identity
from genomeos.validation.heterogeneity_diagnostic_seeds import DiagnosticSeedIdentity
from genomeos.validation.heterogeneity_sbc_controls import DiagnosticCallError
from genomeos.validation.heterogeneity_simulation_types import GeneratedDataset
from genomeos.validation.heterogeneity_summary_types import (
    HeterogeneityFitSummary,
    ParameterPosteriorSummary,
    PredictiveSummaryEvidence,
    predictive_summary_rows,
    require_summary_prediction,
)
from genomeos.validation.predictive import predictive_diagnostics

SEED = 42
_LEVELS = (.025, .1, .25, .5, .75, .9, .975)


def _error(error: Exception) -> DiagnosticCallError:
    return DiagnosticCallError(
        type(error).__module__ + "." + type(error).__qualname__, str(error)
    )


def _parameter_summary(
    name: Literal["mean", "rho"], truth: float, array: np.ndarray, count: int,
) -> ParameterPosteriorSummary:
    estimate = np.mean(array[:, :, 0])
    if type(estimate) not in (float, np.float64) or not np.isfinite(estimate):
        raise ValueError("posterior mean must return a finite binary64 scalar")
    quantiles = np.quantile(array[:, :, 0], _LEVELS, method="linear")
    if (
        not isinstance(quantiles, np.ndarray)
        or quantiles.dtype != np.dtype("float64")
        or quantiles.shape != (7,)
        or not np.all(np.isfinite(quantiles))
    ):
        raise ValueError("posterior quantiles must return a finite float64 vector of length seven")
    return ParameterPosteriorSummary(
        name, truth, float(estimate), tuple(float(value) for value in quantiles), count
    )


def summarize_heterogeneity_fit(
    dataset: GeneratedDataset, *, attempt: FitAttemptResult,
    cdf_backend: Literal["scipy", "cupy"],
) -> HeterogeneityFitSummary:
    """Summarize every accepted draw and the original-order marginal count targets."""
    if not isinstance(dataset, GeneratedDataset) or not isinstance(attempt, FitAttemptResult):
        raise ValueError("summary requires GeneratedDataset and FitAttemptResult")
    if attempt.status != "accepted" or not isinstance(attempt.fit, PopulationHeterogeneityFit):
        raise ValueError("summary requires an accepted typed fit")
    if type(cdf_backend) is not str or cdf_backend not in ("scipy", "cupy"):
        raise ValueError("cdf_backend must be explicitly scipy or cupy")
    require_fit_identity(dataset, spec=attempt.spec, fit=attempt.fit)
    # Constructor consistency is separate from the source/dataset identity guard.
    dataset = replace(dataset)
    attempt = replace(attempt)
    fitted = attempt.fit
    count = attempt.spec.config.chains * attempt.spec.config.draws
    parameters = tuple(
        _parameter_summary(name, truth, array, count)
        for name, truth, array in (
            ("mean", dataset.truth.mean, fitted.mean_draws),
            ("rho", dataset.truth.rho, fitted.rho_draws),
        )
    )
    seed = DiagnosticSeedIdentity(attempt.spec.case, attempt.spec.attempt_id, 7, ())
    words, scalar = seed.scalar_words, seed.scalar_uint128
    if words is None or scalar is None:
        raise ValueError("purpose7 must expose its exact scalar seed")
    targets = dataset.heldouts
    testing = tuple(target.row for target in targets)
    prediction = None
    error = None
    rows = ()
    try:
        prediction = predict_reference_population_heterogeneity(
            fitted, testing, cdf_backend=cdf_backend
        )
    except Exception as caught:
        status = "prediction_failed"
        error = _error(caught)
    else:
        require_summary_prediction(
            prediction, targets=targets, cdf_backend=cdf_backend, draw_count=count
        )
        ac = np.asarray([target.row.ac for target in targets], dtype=np.int64)
        an = np.asarray([target.row.an for target in targets], dtype=np.int64)
        try:
            frame = predictive_diagnostics(prediction.marginal_predictive, ac, an, seed=scalar)
        except Exception as caught:
            status = "diagnostics_failed"
            error = _error(caught)
        else:
            rows = predictive_summary_rows(frame, targets=targets)
            status = "complete"
    evidence = PredictiveSummaryEvidence(
        seed, words, scalar, cdf_backend, count, targets, status, prediction, rows, error
    )
    return HeterogeneityFitSummary(attempt.spec, fitted.variant_ids[0], parameters, evidence)
```

- [ ] Run `/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python -m pytest tests/test_heterogeneity_summaries.py -o addopts='' -q`; expect the literal record tests, all-draw summaries, one real SciPy predictive/scorer integration, constructed failure tests, and pre-work refusal tests to pass. Investigate failures against the source contracts; do not loosen numerical/reference gates or replace fixtures with actual fitting.
- [ ] Move Task2 test imports into the top import section. Use the locked sibling Ruff to `check --fix` and `format` the two production modules and `tests/test_heterogeneity_summaries.py`, then rerun the focused tests, mandatory smoke, module-size gate and clean Ruff check after the final edit. Expect success, but record actual outputs rather than forecast results.
- [ ] Create the evidence note with this exact initial content, then add actual command outputs only after running the specified checks.

```markdown
# B0H descriptive summary adapter evidence — 2026-09-10

This unit advances #211/#189 and implements Atlas design §§5,7–8,12 and the
bounded predictive/parameter summary contract. It makes no actual-fitter
calibration, spatial validity, worldwide accuracy or benchmark-admission claim.

All fit fixtures are directly constructed immutable arrays with synthetic
passing diagnostics. No NUTS sampler ran. A valid sixteen-row generator contract
provides row identity; no constructor is bypassed. All-draw linear quantiles are
anchored by an arithmetic progression, separately from selected SBC quantities.

The actual public predictor and diagnostic function are exercised once together
with constant mean=.5 and rho=1/3 arrays. The intended analytical Beta(1,1)
law implies uniform counts 0..20; binary64 rho=1/3 yields nearby shapes, not
bitwise-exact integer concentration. Independent uniform-count values, with
explicit absolute tolerances and no default relative tolerance, anchor the proper score,
errors, discrete interval coverage/width and vector PIT alignment. The two study2
targets use AC2 and AC17 in shared_cluster0/fresh_cluster order. They are paired
targets within a dataset, not independent datasets.

Purpose7 records retain the fitted track/attempt identity, exact four uint32
words and exact Python uint128 seed. Planned seed metadata does not certify RNG
consumption. Backend failure fixtures exercise explicit cupy retention without
launching GPU work, installing CuPy or claiming backend parity.

Actual predictor/diagnostic call failures preserve parameter summaries. A
diagnostic-call failure also retains the returned immutable predictive object;
its derived arrays cost additional memory alongside fitted arrays. Constructors
validate consistency, not invocation history. The absence of a public prediction
variant-label field means row/variant binding
uses declared targets and the dataset guard; it cannot certify array provenance.
Malformed returned evidence and
identity mismatches propagate as defects. Negative-infinite log scores are
retained as explicit zero-mass outcomes; no codec is chosen here.

Predictive intervals are discrete count intervals divided by AN. Full-posterior
parameter intervals are distinct. Boundary-support noncoverage and shared-history
stress are descriptive outputs, not additional success gates. Full-chain h ESS
and MCSE remain not_computed. Checkpoints, durable failure ledgers, array codecs,
study reductions and complete calibration execution remain outside this unit.

## Verification record

At note creation, implementation verification has not yet been recorded. Replace
this sentence with the actual commands, exit outcomes and any failures after
running the planned focused, smoke and CI checks; never describe a planned
outcome as measured evidence.
```

- [ ] Root runs the full CI gates once on the final stable source head: locked sibling Ruff `check .`; locked Python on `scripts/freeze_contract.py --check`, `scripts/check_module_size.py`, `scripts/check_private_files.py` and `scripts/smoke.py`; then `/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python -m pytest -o addopts='' -q`. Root records exact outputs; the implementer must not claim future results. No schema changes are planned.
- [ ] Before task commit, run the locked Python on `scripts/check_private_files.py`, stage only `genomeos/validation/heterogeneity_summaries.py`, `tests/test_heterogeneity_summaries.py` and `docs/research/population-heterogeneity-summaries-2026-09-10.md`, inspect `git diff --cached --name-only`, run `git diff --cached --check` and repeat privacy, then commit `feat: summarize accepted B0H posterior and heldout evidence`. Root owns adopted spec/plan commits, reviews, final verification, push and one coherent PR advancing #211/#189 without closing them. No map is required because no renderable layer changes.

## Pre-implementation self-review and execution limits

Each spec requirement maps to Task 1 structural checks or Task 2 guarded execution
and its literal tests. Target kinds and predictor/scorer signatures were checked
against source. Negative-infinite scores, exact purpose7 words/scalar, accepted
retry draw count, boundary stress, row alignment and failure retention each have
explicit checks. No source code, tests, sampler, corpus or remote resource ran
while preparing the design. Root completed personal self-review and corrected
the design and plan before adoption; these are not implementation-test results.
