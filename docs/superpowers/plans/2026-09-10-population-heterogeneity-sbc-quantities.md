# B0H Selected SBC Quantities Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce immutable six-quantity SBC evidence from accepted prior-study fits using fixed selection, prior-only and cyclic controls, and the existing independent numerical guard.

**Architecture:** Four narrow modules separate diagnostic identities, prior-control contracts/execution, quantity-result validation and guarded quantity orchestration. Task1 owns both seed and control records so it is independently testable; Task2 consumes those public contracts without private imports. A later study adapter owns persistence, execution failure accounting and statistical reduction.

**Tech Stack:** Python3.12, NumPy SeedSequence/PCG64, frozen dataclasses, existing independent heterogeneity reference and randomized-rank functions, pytest.

**Spec:** `docs/superpowers/specs/2026-09-10-population-heterogeneity-sbc-quantities-design.md`

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

---

The owner authorized scoped implementation and delegation without routine
approval. Root self-reviewed both documents before freeze, choosing bounded
ordinary-Exception catches and four production modules. Execute the two tasks
in order with their independent review gates; no further execution-choice
question is needed.

Read both the spec and applicable AGENTS.md/project reading requirements before
implementation. Existing parent/attempt specs are the scientific and accepted-fit
authority. Do not modify generation, attempt, fitter, dependence, oracle or rank
source. This plan advances#211/#189 without closing either issue.

## File map and runtime

| File | Owner and responsibility |
| --- | --- |
|genomeos/validation/heterogeneity_diagnostic_seeds.py|Task1; identity/domain/uint128 conversion, ~150 logical lines|
|genomeos/validation/heterogeneity_sbc_controls.py|Task1; error/control records and draw_prior_control, ~300–400 lines|
|genomeos/validation/heterogeneity_sbc_quantity_types.py|Task2; immutable quantity/rank/result records and structural reference boundary, ~400–500 lines|
|genomeos/validation/heterogeneity_sbc_quantities.py|Task2; guarded selection and call orchestration, ~350–450 lines|
|tests/test_heterogeneity_diagnostic_seeds.py|Task1 seed contracts|
|tests/test_heterogeneity_sbc_controls.py|Task1 scalar order/failure evidence|
|tests/test_heterogeneity_sbc_quantities.py|Task2 valid fixtures, scalar/reference/rank/call-state tests|
|docs/research/population-heterogeneity-sbc-quantities-2026-09-10.md|Task2 exact verification evidence and limitations|

Use the locked interpreter and existing caches, without changing dependencies:

```bash
export PYTHONPATH=.
export PYTHONDONTWRITEBYTECODE=1
export PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor
export MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib
```

Commands below name the interpreter explicitly. These environment settings apply
to its sibling ruff as well. Implementers own focused tests and mandatory smoke;
root owns final stable-head full CI.

### Task 1: Diagnostic identities and prior-control outcomes

**Files:**

- Create: `genomeos/validation/heterogeneity_diagnostic_seeds.py`
- Create: `genomeos/validation/heterogeneity_sbc_controls.py`
- Create: `tests/test_heterogeneity_diagnostic_seeds.py`
- Create: `tests/test_heterogeneity_sbc_controls.py`

**Interfaces:**

- Consumes public `SbcCaseId(track_id:int,study_id:int,case_id:int,replicate_id:int)`, `simulation_integer(value:object,name:str)->int`, `simulation_probability(value:object,name:str)->float`, `simulation_failure_scalar(value:object,name:str)->float|int` from generation types.
- Produces `DiagnosticSeedIdentity(case:SbcCaseId,attempt_id:int,purpose_id:Literal[5,6,7,8],spawn_key:tuple[int,...])` with `entropy`, `scalar_words` and `scalar_uint128` properties exactly as declared in the spec.
- Produces `DiagnosticCallError(exception_class:str,message:str)`; `PriorControlFailure(chain:int,parameter:Literal['mean','rho'],reason:Literal['rng_exception','invalid_scalar','rounded_boundary'],sampled_mean:float|int|None,sampled_rho:float|int|None,returned_type:str|None,error:DiagnosticCallError|None)`; `PriorControlResult(seed:DiagnosticSeedIdentity,pairs:tuple[tuple[float,float],...],failure:PriorControlFailure|None)` with `status:Literal['complete','failed']`.
- Produces `draw_prior_control(*,seed:DiagnosticSeedIdentity)->PriorControlResult`.
- No quantity-type or attempt/fitter import. Task1 is complete and useful without Task2.

- [ ] **Step 1: Write seed-contract tests.** Put this complete test code in the named seed test file.

```python
"""Literal B0H diagnostic namespaces (design §§5,7–8,12)."""
from __future__ import annotations

from dataclasses import FrozenInstanceError

import numpy as np
import pytest

from genomeos.validation import heterogeneity_diagnostic_seeds as seeds
from genomeos.validation.heterogeneity_diagnostic_seeds import DiagnosticSeedIdentity
from genomeos.validation.heterogeneity_simulation_types import SbcCaseId


@pytest.mark.parametrize("track", (0, 1))
@pytest.mark.parametrize("attempt", (0, 1))
def test_entropy_and_direct_children(track, attempt):
    case = SbcCaseId(track, 0, 0, 7)
    for chain in range(4):
        identity = DiagnosticSeedIdentity(case, attempt, 5, (chain,))
        entropy = (42, 211, 1, track, 0, 0, 7, 5, attempt)
        assert identity.entropy == entropy
        assert identity.scalar_words is None
        assert identity.scalar_uint128 is None
        direct = np.random.SeedSequence(entropy, spawn_key=(chain,))
        nested = np.random.SeedSequence(entropy).spawn(4)[chain]
        np.testing.assert_array_equal(direct.generate_state(4), nested.generate_state(4))
    for mode in range(3):
        for quantity in range(6):
            identity = DiagnosticSeedIdentity(case, attempt, 6, (mode, quantity))
            entropy = (42, 211, 1, track, 0, 0, 7, 6, attempt)
            nested = np.random.SeedSequence(entropy).spawn(3)[mode].spawn(6)[quantity]
            words = tuple(int(x) for x in nested.generate_state(4, dtype=np.uint32))
            assert identity.entropy == entropy
            assert identity.scalar_words == words
            assert identity.scalar_uint128 == sum(w << (32*i) for i, w in enumerate(words))


def test_literal_word_order(monkeypatch):
    calls = []

    class LiteralSequence:
        def __init__(self, entropy, *, spawn_key):
            calls.append((entropy, spawn_key))

        def generate_state(self, size, dtype):
            assert size == 4 and dtype is np.uint32
            return np.array([1, 2, 3, 4], dtype=np.uint32)

    monkeypatch.setattr(seeds.np.random, "SeedSequence", LiteralSequence)
    identity = DiagnosticSeedIdentity(SbcCaseId(1, 0, 0, 8), 1, 6, (2, 5))
    assert identity.scalar_words == (1, 2, 3, 4)
    assert identity.scalar_uint128 == 1 + (2 << 32) + (3 << 64) + (4 << 96)
    assert all(call == ((42, 211, 1, 1, 0, 0, 8, 6, 1), (2, 5)) for call in calls)


@pytest.mark.parametrize("study", (0, 1, 2, 4))
def test_pit_namespace_is_available_without_predictive_execution(study):
    identity = DiagnosticSeedIdentity(SbcCaseId(1, study, 0, 0), 1, 7, ())
    assert identity.entropy == (42, 211, 1, 1, study, 0, 0, 7, 1)
    assert len(identity.scalar_words) == 4
    assert isinstance(identity.scalar_uint128, int)


@pytest.mark.parametrize("attempt,purpose,key", (
    (True, 5, (0,)), (-1, 5, (0,)), (2, 5, (0,)),
    (0, True, (0,)), (0, 4, ()), (0, 9, ()),
    (0, 5, ()), (0, 5, (True,)), (0, 5, (4,)), (0, 5, [0]),
    (0, 6, (0,)), (0, 6, (3, 0)), (0, 6, (0, 6)),
    (0, 6, (0, False)), (0, 7, (0,)), (0, 8, (2,)),
))
def test_closed_domains(attempt, purpose, key):
    with pytest.raises(ValueError):
        DiagnosticSeedIdentity(SbcCaseId(0, 0, 0, 0), attempt, purpose, key)


@pytest.mark.parametrize("purpose,key", ((5, (0,)), (6, (0, 0)), (8, (1,))))
def test_prior_only_namespaces_refuse_stress(purpose, key):
    with pytest.raises(ValueError):
        DiagnosticSeedIdentity(SbcCaseId(0, 1, 0, 0), 0, purpose, key)


def test_structural_and_mutation_refusal():
    with pytest.raises(ValueError):
        DiagnosticSeedIdentity(SbcCaseId(0, 3, 0, 0), 0, 7, ())
    identity = DiagnosticSeedIdentity(SbcCaseId(0, 0, 0, 0), 0, 8, (1,))
    assert identity.scalar_words is identity.scalar_uint128 is None
    with pytest.raises(FrozenInstanceError):
        identity.attempt_id = 1
```

- [ ] **Step 2: Run seed tests and record the actual RED result.**

```bash
/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python -m pytest tests/test_heterogeneity_diagnostic_seeds.py -o addopts='' -q
```

Expected RED: import failure for the new module, not a syntax error. Correct
test syntax if necessary before accepting RED as evidence.

- [ ] **Step 3: Implement the seed record and its exact properties.** Use the spec's closed table in __post_init__; reject non-tuple spawn keys instead of silently accepting lists. This is the complete conversion body, with no uint32 shortening:

```python
@property
def entropy(self):
    case = self.case
    return (42, 211, 1, case.track_id, case.study_id, case.case_id,
            case.replicate_id, self.purpose_id, self.attempt_id)

@property
def scalar_words(self):
    if self.purpose_id not in (6, 7):
        return None
    sequence = np.random.SeedSequence(self.entropy, spawn_key=self.spawn_key)
    return tuple(int(word) for word in sequence.generate_state(4, dtype=np.uint32))

@property
def scalar_uint128(self):
    words = self.scalar_words
    if words is None:
        return None
    return sum(word << (32 * index) for index, word in enumerate(words))
```

Use exact annotations from the interface block. Constructor checks are: typed
reconstructed SbcCaseId; non-Boolean normalized attempt in(0,1); normalized
purpose in(5,6,7,8); immutable integer spawn tuple matching exactly the spec's
four rows; nonstructural study; studies restricted to0 for5/6/8. Set normalized
fields with object.__setattr__; do not access scalar properties in construction.

- [ ] **Step 4: Write control execution and constructor tests.** Put this code in the named control test file.

```python
"""Prior-only scalar controls; no posterior or actual-study claim."""
from __future__ import annotations

from dataclasses import FrozenInstanceError, replace

import numpy as np
import pytest

from genomeos.validation import heterogeneity_sbc_controls as controls
from genomeos.validation.heterogeneity_diagnostic_seeds import DiagnosticSeedIdentity
from genomeos.validation.heterogeneity_sbc_controls import (
    DiagnosticCallError, PriorControlFailure, PriorControlResult, draw_prior_control,
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
    assert result.pairs == tuple(zip(values[::2], values[1::2]))
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
```

- [ ] **Step 5: Record control RED, implement controls, then run Task1 GREEN.**

```bash
/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python -m pytest tests/test_heterogeneity_sbc_controls.py -o addopts='' -q
```

Expected RED: missing control module/public names. Implement the three control
records and actual error pair in the controls module, enforcing every row of
the spec's control-state table. Complete execution follows this exact loop;
the private validation helpers in this module instantiate the declared records,
using the spec's supported-value and exception field rules:

```python
def draw_prior_control(*, seed: DiagnosticSeedIdentity) -> PriorControlResult:
    if not isinstance(seed, DiagnosticSeedIdentity):
        raise ValueError("seed must be a DiagnosticSeedIdentity")
    seed = DiagnosticSeedIdentity(seed.case, seed.attempt_id, seed.purpose_id, seed.spawn_key)
    if seed.purpose_id != 8:
        raise ValueError("control seed must have purpose8")
    rng = np.random.Generator(np.random.PCG64(
        np.random.SeedSequence(seed.entropy, spawn_key=seed.spawn_key)
    ))
    pairs = []
    rho_beta = 9.0 if seed.case.track_id == 0 else 4.0
    for chain in range(4):
        mean = None
        for parameter, beta in (("mean", 1.0), ("rho", rho_beta)):
            try:
                raw = rng.beta(1.0, beta)
            except Exception as error:
                qualified = type(error).__module__ + "." + type(error).__qualname__
                failure = PriorControlFailure(
                    chain, parameter, "rng_exception", mean, None, None,
                    DiagnosticCallError(qualified, str(error)),
                )
                return PriorControlResult(seed, tuple(pairs), failure)
            try:
                evidence = simulation_failure_scalar(raw, parameter)
            except ValueError:
                returned_type = type(raw).__module__ + "." + type(raw).__qualname__
                failure = PriorControlFailure(
                    chain, parameter, "invalid_scalar", mean, None, returned_type, None,
                )
                return PriorControlResult(seed, tuple(pairs), failure)
            candidate_mean = evidence if parameter == "mean" else mean
            candidate_rho = evidence if parameter == "rho" else None
            try:
                probability = simulation_probability(evidence, parameter)
            except ValueError:
                failure = PriorControlFailure(
                    chain, parameter, "invalid_scalar", candidate_mean, candidate_rho, None, None,
                )
                return PriorControlResult(seed, tuple(pairs), failure)
            if probability in (0.0, 1.0):
                failure = PriorControlFailure(
                    chain, parameter, "rounded_boundary", candidate_mean, candidate_rho, None, None,
                )
                return PriorControlResult(seed, tuple(pairs), failure)
            if parameter == "mean":
                mean = probability
            else:
                pairs.append((mean, probability))
    return PriorControlResult(seed, tuple(pairs), None)
```

The `simulation_*` validator catches above distinguish observed return domains;
they never become fabricated RNG exceptions. Constructor errors occur outside
the actual RNG try. Do not introduce a generic catch/callback registry. Annotate
the local pair list and public return exactly; constructor rules are specified
in full in the accompanying spec, not optional error handling.

```bash
/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python -m pytest tests/test_heterogeneity_diagnostic_seeds.py tests/test_heterogeneity_sbc_controls.py -o addopts='' -q
/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python scripts/smoke.py
/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/ruff check genomeos/validation/heterogeneity_diagnostic_seeds.py genomeos/validation/heterogeneity_sbc_controls.py tests/test_heterogeneity_diagnostic_seeds.py tests/test_heterogeneity_sbc_controls.py
/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python scripts/check_module_size.py
```

Expected GREEN: every focused test, smoke and static command succeeds. Record
actual counts/output; do not substitute these expected results for evidence.

- [ ] **Step 6: Privacy-check, inspect staging and commit Task1's independently testable unit.**

```bash
/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python scripts/check_private_files.py
git add genomeos/validation/heterogeneity_diagnostic_seeds.py genomeos/validation/heterogeneity_sbc_controls.py tests/test_heterogeneity_diagnostic_seeds.py tests/test_heterogeneity_sbc_controls.py
git diff --cached --name-only
git diff --cached --check
/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python scripts/check_private_files.py
git commit -m "feat: add deterministic SBC diagnostic seeds and controls"
```

Expected staging contains only those four task files. No `closes` keyword:
neither#211 nor#189 is completed by this component. Root's task review gate
precedes Task2 implementation under the chosen execution workflow.

### Task 2: Guarded scalar, dependence and rank evidence

**Files:**

- Create: `genomeos/validation/heterogeneity_sbc_quantity_types.py`
- Create: `genomeos/validation/heterogeneity_sbc_quantities.py`
- Create: `tests/test_heterogeneity_sbc_quantities.py`
- Create: `docs/research/population-heterogeneity-sbc-quantities-2026-09-10.md`

**Interfaces:**

- Consumes Task1 `DiagnosticSeedIdentity(case:SbcCaseId,attempt_id:int,purpose_id:Literal[5,6,7,8],spawn_key:tuple[int,...])`; `DiagnosticCallError(exception_class:str,message:str)`; `PriorControlFailure(chain:int,parameter:Literal['mean','rho'],reason:Literal['rng_exception','invalid_scalar','rounded_boundary'],sampled_mean:float|int|None,sampled_rho:float|int|None,returned_type:str|None,error:DiagnosticCallError|None)`; `PriorControlResult(seed:DiagnosticSeedIdentity,pairs:tuple[tuple[float,float],...],failure:PriorControlFailure|None)`; `draw_prior_control(*,seed:DiagnosticSeedIdentity)->PriorControlResult`.
- Consumes existing `require_fit_identity(dataset:GeneratedDataset,*,spec:FitAttemptSpec,fit:PopulationHeterogeneityFit)->None`, `heterogeneity_log_mass(ac:int,an:int,*,mean:np.ndarray,rho:np.ndarray)->np.ndarray`, `heterogeneity_dependence_reference(counts:Sequence[tuple[int,int]],*,mean_prior:tuple[float,float],rho_prior:tuple[float,float],points:Sequence[tuple[float,float]])->HeterogeneityDependenceReference`, `dependence_comparisons(reference:HeterogeneityDependenceReference,*,truth_index:int,draw_indices:Sequence[int])->DependenceComparisons`, `randomized_rank(truth:float,draws:Sequence[float],*,seed:int)->int`.
- Produces `ScalarQuantityEvidence`, `QuantityRankEvidence`, `SelectedSbcQuantities` with every field and closed status exactly as declared in the spec; `require_quantity_reference(reference:HeterogeneityDependenceReference,*,points:tuple[tuple[float,float],...])->None`; `require_quantity_comparisons(comparisons:DependenceComparisons,*,reference:HeterogeneityDependenceReference,truth_index:int,draw_indices:tuple[int,int,int,int])->None`; `selected_sbc_quantities(dataset:GeneratedDataset,*,attempt:FitAttemptResult)->SelectedSbcQuantities`.

- [ ] **Step 1: Write valid sixteen-row fixtures and independent quantity expectations.** Start the named test file with this complete code. The fixtures use public constructors and do not generate a case or invoke a sampler.

```python
"""B0H selected quantities: mocked orchestration plus one actual reference."""
from __future__ import annotations

import math
from dataclasses import FrozenInstanceError, replace
from fractions import Fraction
from unittest.mock import Mock

import numpy as np
import pytest

from genomeos.surfaces.heterogeneity_types import (
    PopulationHeterogeneityFit, VariantHeterogeneityDiagnostics, VariantTrainingCounts,
)
from genomeos.validation import heterogeneity_sbc_quantities as quantities
from genomeos.validation.heterogeneity_attempts import (
    FitAttemptResult, FitIdentityError, plan_fit_attempt, require_fit_identity,
)
from genomeos.validation.heterogeneity_dependence import (
    DependenceComparisons, DependencePointReference, HeterogeneityDependenceReference,
    dependence_comparisons, heterogeneity_dependence_reference,
)
from genomeos.validation.heterogeneity_diagnostic_seeds import DiagnosticSeedIdentity
from genomeos.validation.heterogeneity_sbc_controls import (
    DiagnosticCallError, PriorControlFailure, PriorControlResult,
)
from genomeos.validation.heterogeneity_sbc_quantities import selected_sbc_quantities
from genomeos.validation.heterogeneity_sbc_quantity_types import (
    require_quantity_comparisons, require_quantity_reference,
)
from genomeos.validation.heterogeneity_simulation_types import (
    GeneratedDataset, GenerationProvenance, HeldoutTarget, ParameterTruth, SbcCaseId,
    generation_id, sbc_seed_identity, simulation_reference_count,
)
from genomeos.validation.sbc_ranks import randomized_rank


def fixture(track=0, attempt_id=0, *, varying=False, study=0):
    assert study in (0, 1)
    case = SbcCaseId(track, study, 0, 0)
    generation = generation_id(case)
    ans = (0, 1, 2, 5, 10, 20, 40, 64) * 2
    acs = (0, 0, 1, 2, 4, 7, 11, 19) * 2
    rows = tuple(simulation_reference_count(generation, "train", str(i), ac, an)
                 for i, (ac, an) in enumerate(zip(acs, ans, strict=True)))
    heldout = HeldoutTarget(
        "fresh_population", simulation_reference_count(generation, "heldout", "fresh_population", 3, 20),
        0.25 if study == 0 else 0.001, None, None, None, None,
    )
    data = GeneratedDataset(
        case, GenerationProvenance(generation, tuple(sbc_seed_identity(case, purpose_id=p, attempt_id=0)
                                                     for p in range(4))),
        ParameterTruth(0.25, 0.25) if study == 0 else ParameterTruth(0.001, 0.0),
        rows, ((0.25 if study == 0 else 0.001),) * 16, None, (heldout,), 0, 0,
    )
    spec = plan_fit_attempt(data, attempt_id=attempt_id)
    shape = (4, spec.config.draws, 1)
    means = np.empty(shape, dtype=np.float64)
    rhos = np.empty(shape, dtype=np.float64)
    for chain, (mean, rho) in enumerate(((0.125, 0.125), (0.25, 0.1875),
                                        (0.375, 0.3125), (0.5, 0.4375))):
        means[chain, :, 0] = mean
        rhos[chain, :, 0] = rho
        if varying:
            means[chain, :, 0] = 0.125 + (chain * spec.config.draws + np.arange(spec.config.draws)) / 8192
            rhos[chain, :, 0] = 0.125 + (chain * spec.config.draws + np.arange(spec.config.draws)) / 16384
    variant = rows[0].variant_id
    fit = PopulationHeterogeneityFit(
        spec.config, (variant,), means, rhos,
        tuple(sorted(row.record_id for row in rows)),
        tuple(sorted({row.group_id for row in rows})),
        tuple(sorted(row.record_id for row in rows if row.an == 0)),
        (VariantTrainingCounts(variant, 14, sum(acs), sum(ans)),),
        (VariantHeterogeneityDiagnostics(variant, 1.0, 200.0, 200.0),), 0,
    )
    return data, FitAttemptResult(spec, "accepted", fit, None, (), None)


def literal_control(*, seed):
    return PriorControlResult(seed, ((0.125, 0.25), (0.375, 0.5),
                                     (0.625, 0.75), (0.875, 0.125)), None)


def mocked_reference(counts, *, mean_prior, rho_prior, points):
    """Synthetic arithmetic for call/guard tests, not a mixed-count h oracle."""
    unique = tuple(dict.fromkeys(points))
    records = []
    for mean, rho in points:
        value = float(unique.index((mean, rho)))
        records.append(DependencePointReference(
            mean, rho, ((value, 0.0, 0.0, 0.0),) * 3,
            (value,) * 3, value, 1e-12, True,
        ))
    return HeterogeneityDependenceReference((64, 128, 256), False, tuple(records))


def install_mocks(monkeypatch):
    monkeypatch.setattr(quantities, "draw_prior_control", literal_control)
    reference = Mock(side_effect=mocked_reference)
    monkeypatch.setattr(quantities, "heterogeneity_dependence_reference", reference)
    return reference


def exact_mass(ac, an, mean, rho):
    """Independent rational rising-factorial Beta-binomial product."""
    mean, rho = Fraction(mean), Fraction(rho)
    kappa = (1 - rho) / rho
    alpha, beta = mean * kappa, (1 - mean) * kappa
    result = Fraction(math.comb(an, ac))
    for j in range(ac):
        result *= alpha + j
    for j in range(an - ac):
        result *= beta + j
    for j in range(an):
        result /= alpha + beta + j
    return result


@pytest.mark.parametrize("track,attempt_id", ((0, 0), (1, 0), (0, 1), (1, 1)))
def test_literal_selection_pairing_and_rational_quantities(monkeypatch, track, attempt_id):
    reference = install_mocks(monkeypatch)
    data, attempt = fixture(track, attempt_id)
    result = selected_sbc_quantities(data, attempt=attempt)
    expected_indices = []
    for chain in range(4):
        entropy = (42, 211, 1, track, 0, 0, 0, 5, attempt_id)
        rng = np.random.Generator(np.random.PCG64(np.random.SeedSequence(entropy, spawn_key=(chain,))))
        expected_indices.append((chain, int(rng.integers(0, attempt.spec.config.draws))))
    assert result.selected_indices == tuple(expected_indices)
    assert result.selection_seeds == tuple(DiagnosticSeedIdentity(data.case_id, attempt_id, 5, (chain,)) for chain in range(4))
    correct = tuple((float(attempt.fit.mean_draws[c, d, 0]), float(attempt.fit.rho_draws[c, d, 0]))
                    for c, d in expected_indices)
    assert result.points[1:5] == correct
    assert result.points[9:13] == tuple((correct[c][0], correct[(c-1) % 4][1]) for c in range(4))
    assert result.point_slots == tuple(range(13)) and result.complete
    assert result.selection_method == "one_uniform_postwarmup_draw_per_chain"
    assert reference.call_count == 1
    assert reference.call_args.args == (tuple((row.ac, row.an) for row in data.training),)
    assert reference.call_args.kwargs == {
        "mean_prior": (1.0, 1.0), "rho_prior": (1.0, 9.0 if track == 0 else 4.0),
        "points": result.points,
    }
    for index, (mean, rho) in enumerate(result.points):
        expected = (mean, rho, mean*rho,
                    math.log(float(math.prod(exact_mass(row.ac, row.an, mean, rho) for row in data.training))),
                    math.log(float(exact_mass(0, 20, mean, rho))))
        actual = tuple(entry.values[index] for entry in result.scalar_quantities)
        np.testing.assert_allclose(actual, expected, rtol=0, atol=1e-12)
    for entry in result.ranks:
        if entry.quantity_id == 5:
            assert entry.comparisons.status == "resolved"
            assert entry.rank == randomized_rank(0, entry.comparisons.comparisons,
                                                 seed=entry.seed.scalar_uint128)


def test_varying_chains_preserve_selected_pair_and_heldout_is_irrelevant(monkeypatch):
    install_mocks(monkeypatch)
    data, attempt = fixture(varying=True)
    first = selected_sbc_quantities(data, attempt=attempt)
    for i, (chain, draw) in enumerate(first.selected_indices, start=1):
        assert first.points[i] == (attempt.fit.mean_draws[chain, draw, 0], attempt.fit.rho_draws[chain, draw, 0])
    target = data.heldouts[0]
    changed = replace(data, heldouts=(replace(target, row=replace(target.row, ac=4)),))
    second = selected_sbc_quantities(changed, attempt=attempt)
    assert first == second
```

- [ ] **Step 2: Add actual-call ordering and failure tests.** Append this code before implementation. It proves the identity guard and independent stage behavior with explicit call evidence.

```python
def test_guard_runs_first_and_rejects_before_rng(monkeypatch):
    install_mocks(monkeypatch)
    data, attempt = fixture()
    called = []
    original_guard = require_fit_identity

    def guard(dataset, *, spec, fit):
        called.append("guard")
        original_guard(dataset, spec=spec, fit=fit)

    monkeypatch.setattr(quantities, "require_fit_identity", guard)
    real_generator = np.random.Generator

    def generator(bitgen):
        assert called == ["guard"]
        return real_generator(bitgen)

    monkeypatch.setattr(quantities.np.random, "Generator", generator)
    selected_sbc_quantities(data, attempt=attempt)
    _, wrong_attempt = fixture(track=1)
    sentinel = Mock(side_effect=AssertionError("RNG must not run"))
    monkeypatch.setattr(quantities.np.random, "Generator", sentinel)
    with pytest.raises(ValueError):
        selected_sbc_quantities(data, attempt=wrong_attempt)
    sentinel.assert_not_called()


def test_stress_failed_attempt_and_fit_identity_are_rejected_before_rng(monkeypatch):
    from genomeos.validation.heterogeneity_attempts import AttemptError

    data, attempt = fixture()
    stress, stress_attempt = fixture(study=1)
    wrong_fit = replace(attempt.fit, training_group_ids=tuple("wrong:" + group for group in attempt.fit.training_group_ids))
    wrong_attempt = replace(attempt, fit=wrong_fit)
    failed = FitAttemptResult(attempt.spec, "failed", None,
                              AttemptError("runtime", "builtins.RuntimeError", "fit", None, None, None), (), None)
    sentinel = Mock(side_effect=AssertionError("RNG must not run"))
    monkeypatch.setattr(quantities.np.random, "Generator", sentinel)
    for dataset, result in ((stress, stress_attempt), (data, failed), (None, attempt)):
        with pytest.raises(ValueError):
            selected_sbc_quantities(dataset, attempt=result)
    with pytest.raises(FitIdentityError) as rejected:
        selected_sbc_quantities(data, attempt=wrong_attempt)
    assert "training_group_ids" in rejected.value.mismatches
    sentinel.assert_not_called()


def test_identical_parameter_point_is_literal_h_tie(monkeypatch):
    install_mocks(monkeypatch)
    data, attempt = fixture()
    means = attempt.fit.mean_draws.copy()
    rhos = attempt.fit.rho_draws.copy()
    means[0, :, 0], rhos[0, :, 0] = data.truth.mean, data.truth.rho
    attempt = replace(attempt, fit=replace(attempt.fit, mean_draws=means, rho_draws=rhos))
    result = selected_sbc_quantities(data, attempt=attempt)
    assert result.points[1] == result.points[0]
    assert result.ranks[5].comparisons.comparisons[0] == 0


def test_repeated_draw_index_across_chains_is_valid(monkeypatch):
    install_mocks(monkeypatch)
    data, attempt = fixture(varying=True)

    class IndexStream:
        def integers(self, low, high):
            assert low == 0 and high == 500
            return np.int64(11)

    monkeypatch.setattr(quantities.np.random, "Generator", lambda bitgen: IndexStream())
    result = selected_sbc_quantities(data, attempt=attempt)
    assert result.selected_indices == ((0, 11), (1, 11), (2, 11), (3, 11))


def test_nine_actual_points_on_control_failure(monkeypatch):
    reference = install_mocks(monkeypatch)
    data, attempt = fixture()

    def failed_control(*, seed):
        return PriorControlResult(seed, ((0.25, 0.125),) * 3,
            PriorControlFailure(3, "rho", "rounded_boundary", 0.375, 0.0, None, None))

    monkeypatch.setattr(quantities, "draw_prior_control", failed_control)
    rank_spy = Mock(wraps=randomized_rank)
    comparison_spy = Mock(wraps=dependence_comparisons)
    monkeypatch.setattr(quantities, "randomized_rank", rank_spy)
    monkeypatch.setattr(quantities, "dependence_comparisons", comparison_spy)
    result = selected_sbc_quantities(data, attempt=attempt)
    assert result.point_slots == (0, 1, 2, 3, 4, 9, 10, 11, 12)
    assert len(result.points) == len(result.reference.points) == 9
    assert reference.call_count == 1 and rank_spy.call_count == 12
    assert [call.kwargs["draw_indices"] for call in comparison_spy.call_args_list] == [(1, 2, 3, 4), (5, 6, 7, 8)]
    assert all(entry.status == "control_failed" for entry in result.ranks[6:12])
    assert all(entry.status == "ranked" for entry in (*result.ranks[:6], *result.ranks[12:]))
    assert result.control.failure.sampled_mean == 0.375 and not result.complete


def test_scalar_calls_include_an0_and_precede_single_reference(monkeypatch):
    install_mocks(monkeypatch)
    data, attempt = fixture()
    calls = []
    real_mass = quantities.heterogeneity_log_mass

    def log_mass(ac, an, *, mean, rho):
        calls.append((ac, an))
        assert mean.shape == rho.shape == (13,)
        return real_mass(ac, an, mean=mean, rho=rho)

    def reference(counts, **kwargs):
        assert calls == [(row.ac, row.an) for row in data.training] + [(0, 20)]
        calls.append("reference")
        return mocked_reference(counts, **kwargs)

    monkeypatch.setattr(quantities, "heterogeneity_log_mass", log_mass)
    monkeypatch.setattr(quantities, "heterogeneity_dependence_reference", reference)
    selected_sbc_quantities(data, attempt=attempt)
    assert calls.count((0, 0)) == 2 and calls[-1] == "reference"


def test_actual_training_exception_retains_other_quantities(monkeypatch):
    reference = install_mocks(monkeypatch)
    data, attempt = fixture()
    calls = []
    real_mass = quantities.heterogeneity_log_mass

    def log_mass(ac, an, *, mean, rho):
        calls.append((ac, an))
        if len(calls) == 3:
            raise KeyError("training-call")
        return real_mass(ac, an, mean=mean, rho=rho)

    monkeypatch.setattr(quantities, "heterogeneity_log_mass", log_mass)
    result = selected_sbc_quantities(data, attempt=attempt)
    assert calls == [(0, 0), (0, 1), (1, 2), (0, 20)]
    assert result.scalar_quantities[3].error == DiagnosticCallError("builtins.KeyError", "'training-call'")
    assert result.scalar_quantities[3].failed_training_row == 2
    assert result.scalar_quantities[3].values is None
    assert all(result.scalar_quantities[q].values is not None for q in (0, 1, 2, 4))
    assert reference.call_count == 1
    assert all(result.ranks[m*6+3].status == "quantity_failed" for m in range(3))


def test_actual_reference_exception_retains_fifteen_scalar_ranks(monkeypatch):
    install_mocks(monkeypatch)
    data, attempt = fixture()
    monkeypatch.setattr(quantities, "heterogeneity_dependence_reference", Mock(side_effect=KeyError("reference")))
    result = selected_sbc_quantities(data, attempt=attempt)
    assert result.reference is None
    assert result.reference_error == DiagnosticCallError("builtins.KeyError", "'reference'")
    assert sum(entry.status == "ranked" for entry in result.ranks) == 15
    assert all(result.ranks[m*6+5].status == "reference_failed" for m in range(3))


@pytest.mark.parametrize("state", ("dependence_reference_unresolved", "dependence_rank_order_unresolved"))
def test_actual_public_guard_unresolved_states_keep_raw_evidence(monkeypatch, state):
    install_mocks(monkeypatch)
    data, attempt = fixture()

    def reference(counts, **kwargs):
        result = mocked_reference(counts, **kwargs)
        truth = result.points[0]
        if state == "dependence_reference_unresolved":
            truth = replace(truth, resolved=False)
        else:
            truth = replace(truth, error_bound=1e6)
        return replace(result, points=(truth, *result.points[1:]))

    monkeypatch.setattr(quantities, "heterogeneity_dependence_reference", reference)
    result = selected_sbc_quantities(data, attempt=attempt)
    assert result.reference is not None and result.reference_error is None
    for mode in range(3):
        entry = result.ranks[mode*6+5]
        assert entry.status == entry.comparisons.status == state
        assert len(entry.comparisons.comparisons_by_order) == 3
        assert entry.rank is entry.error is entry.comparisons.comparisons is None
    assert sum(entry.status == "ranked" for entry in result.ranks) == 15


@pytest.mark.parametrize("stage,status", (("dependence_comparisons", "comparison_failed"), ("randomized_rank", "rank_failed")))
def test_actual_comparison_and_rank_exceptions_are_separate(monkeypatch, stage, status):
    install_mocks(monkeypatch)
    data, attempt = fixture()
    monkeypatch.setattr(quantities, stage, Mock(side_effect=RuntimeError("call")))
    result = selected_sbc_quantities(data, attempt=attempt)
    affected = result.ranks if stage == "randomized_rank" else result.ranks[5::6]
    assert all(entry.status == status for entry in affected)
    assert all(entry.error == DiagnosticCallError("builtins.RuntimeError", "call") for entry in affected)
    assert result.reference is not None and all(entry.values is not None for entry in result.scalar_quantities)
```

- [ ] **Step 3: Add malformed-return, immutable-state and actual-reference integration tests.** These failures must propagate outside numerical catches; tests never count them as numerical outcomes.

```python
@pytest.mark.parametrize("bad", (
    0.0, [0.0] * 13, np.zeros((13, 1)), np.zeros(12),
    np.zeros(13, dtype=np.float32), np.zeros(13, dtype=bool),
    np.zeros(13, dtype=complex), np.full(13, np.nan), np.full(13, np.inf),
))
def test_malformed_logmass_return_propagates(monkeypatch, bad):
    reference = install_mocks(monkeypatch)
    data, attempt = fixture()
    monkeypatch.setattr(quantities, "heterogeneity_log_mass", Mock(return_value=bad))
    with pytest.raises(ValueError):
        selected_sbc_quantities(data, attempt=attempt)
    reference.assert_not_called()


@pytest.mark.parametrize("mutation", (
    lambda r: object(), lambda r: replace(r, orders=(64, 128, 255)),
    lambda r: replace(r, analytic_separability=1), lambda r: replace(r, points=r.points[:-1]),
    lambda r: replace(r, points=(replace(r.points[0], mean=0.3), *r.points[1:])),
    lambda r: replace(r, points=(replace(r.points[0], components=((0.0,) * 3,) * 3), *r.points[1:])),
    lambda r: replace(r, points=(replace(r.points[0], raw_values=(float("nan"),) * 3), *r.points[1:])),
    lambda r: replace(r, points=(replace(r.points[0], error_bound=-1.0), *r.points[1:])),
    lambda r: replace(r, points=(replace(r.points[0], resolved=1), *r.points[1:])),
))
def test_malformed_typed_reference_propagates_before_comparison(monkeypatch, mutation):
    install_mocks(monkeypatch)
    data, attempt = fixture()

    def reference(counts, **kwargs):
        return mutation(mocked_reference(counts, **kwargs))

    monkeypatch.setattr(quantities, "heterogeneity_dependence_reference", reference)
    comparisons = Mock(side_effect=AssertionError("malformed reference reached guard"))
    monkeypatch.setattr(quantities, "dependence_comparisons", comparisons)
    with pytest.raises(ValueError):
        selected_sbc_quantities(data, attempt=attempt)
    comparisons.assert_not_called()


@pytest.mark.parametrize("bad", (
    object(), DependenceComparisons("wrong", ((1,)*4,)*3, None),
    DependenceComparisons("resolved", ((True,)*4,)*3, (1,)*4),
    DependenceComparisons("resolved", ((1,)*4,)*3, None),
    DependenceComparisons("resolved", ((-1,)*4,)*3, (-1,)*4),
    DependenceComparisons("dependence_rank_order_unresolved", ((1,)*4,)*3, (1,)*4),
))
def test_malformed_comparison_propagates(monkeypatch, bad):
    install_mocks(monkeypatch)
    data, attempt = fixture()
    monkeypatch.setattr(quantities, "dependence_comparisons", Mock(return_value=bad))
    rank_spy = Mock(wraps=randomized_rank)
    monkeypatch.setattr(quantities, "randomized_rank", rank_spy)
    with pytest.raises(ValueError):
        selected_sbc_quantities(data, attempt=attempt)
    assert rank_spy.call_count == 5


@pytest.mark.parametrize("bad", (True, np.bool_(False), 2.0, -1, 5, None))
def test_malformed_rank_propagates(monkeypatch, bad):
    install_mocks(monkeypatch)
    data, attempt = fixture()
    monkeypatch.setattr(quantities, "randomized_rank", Mock(return_value=bad))
    with pytest.raises(ValueError):
        selected_sbc_quantities(data, attempt=attempt)


@pytest.mark.parametrize("truth,draws", (
    (True, (1, 2, 3, 4)), (13, (1, 2, 3, 4)),
    (0, (0, 1, 2, 3)), (0, (1, 1, 2, 3)), (0, (-1, 2, 3, 4)),
    (0, (1, 2, 3, 13)), (0, (True, 2, 3, 4)),
    (0, (1, 2, 3)), (0, [1, 2, 3, 4]),
))
def test_public_comparison_binding_refuses_bad_indices(monkeypatch, truth, draws):
    install_mocks(monkeypatch)
    data, attempt = fixture()
    result = selected_sbc_quantities(data, attempt=attempt)
    comparisons = result.ranks[5].comparisons
    require_quantity_comparisons(
        comparisons, reference=result.reference, truth_index=0, draw_indices=(1, 2, 3, 4)
    )
    with pytest.raises(ValueError):
        require_quantity_comparisons(
            comparisons, reference=result.reference, truth_index=truth, draw_indices=draws
        )


def test_future_call_failure_preserves_training_and_reference(monkeypatch):
    reference = install_mocks(monkeypatch)
    data, attempt = fixture()
    real_mass = quantities.heterogeneity_log_mass
    calls = []

    def log_mass(ac, an, *, mean, rho):
        calls.append((ac, an))
        if len(calls) == 17:
            raise KeyError("future-call")
        return real_mass(ac, an, mean=mean, rho=rho)

    monkeypatch.setattr(quantities, "heterogeneity_log_mass", log_mass)
    result = selected_sbc_quantities(data, attempt=attempt)
    assert calls == [(row.ac, row.an) for row in data.training] + [(0, 20)]
    assert result.scalar_quantities[3].values is not None
    future = result.scalar_quantities[4]
    assert future.values is None and future.failed_training_row is None
    assert future.error == DiagnosticCallError("builtins.KeyError", "'future-call'")
    assert reference.call_count == 1
    assert all(result.ranks[mode*6+4].status == "quantity_failed" for mode in range(3))
    assert sum(entry.status == "ranked" for entry in result.ranks) == 15


def test_accumulation_overflow_is_not_invented_oracle_failure(monkeypatch):
    reference = install_mocks(monkeypatch)
    data, attempt = fixture()
    log_mass = Mock(return_value=np.full(13, -1.7e308, dtype=np.float64))
    monkeypatch.setattr(quantities, "heterogeneity_log_mass", log_mass)
    with pytest.raises(ArithmeticError, match="accumulation"):
        selected_sbc_quantities(data, attempt=attempt)
    assert log_mass.call_count == 2
    reference.assert_not_called()


def test_selection_and_base_exception_propagate(monkeypatch):
    install_mocks(monkeypatch)
    data, attempt = fixture()

    class BrokenSelection:
        def integers(self, low, high):
            raise RuntimeError("selection")

    with monkeypatch.context() as patch:
        patch.setattr(quantities.np.random, "Generator", lambda bitgen: BrokenSelection())
        with pytest.raises(RuntimeError, match="selection"):
            selected_sbc_quantities(data, attempt=attempt)
    monkeypatch.setattr(quantities, "heterogeneity_dependence_reference", Mock(side_effect=KeyboardInterrupt()))
    with pytest.raises(KeyboardInterrupt):
        selected_sbc_quantities(data, attempt=attempt)


def test_immutable_and_inconsistent_result_states(monkeypatch):
    install_mocks(monkeypatch)
    data, attempt = fixture()
    result = selected_sbc_quantities(data, attempt=attempt)
    with pytest.raises(FrozenInstanceError):
        result.ranks = ()
    for changes in ({"point_slots": (0,)}, {"ranks": result.ranks[::-1]},
                    {"selected_indices": ((0, 500), (1, 0), (2, 0), (3, 0))},
                    {"reference_error": DiagnosticCallError("builtins.ValueError", "fabricated")}):
        with pytest.raises(ValueError):
            replace(result, **changes)
    ranked = result.ranks[0]
    for changes in ({"rank": True}, {"status": "control_failed"},
                    {"error": DiagnosticCallError("builtins.ValueError", "fabricated")}):
        with pytest.raises(ValueError):
            replace(ranked, **changes)
    scalar = result.scalar_quantities[0]
    with pytest.raises(ValueError):
        replace(scalar, values=None)
    with pytest.raises(ValueError):
        replace(scalar, values=(float("nan"),) * 13)


def test_actual_reference_on_one_valid_mixed_an_case(monkeypatch):
    """Integration only: real reference/guard, synthetic accepted fit and control."""
    monkeypatch.setattr(quantities, "draw_prior_control", literal_control)
    actual_reference = Mock(wraps=heterogeneity_dependence_reference)
    monkeypatch.setattr(quantities, "heterogeneity_dependence_reference", actual_reference)
    data, attempt = fixture()
    result = selected_sbc_quantities(data, attempt=attempt)
    assert actual_reference.call_count == 1
    assert result.reference_error is None
    require_quantity_reference(result.reference, points=result.points)
    assert result.reference.orders == (64, 128, 256)
    assert result.reference.analytic_separability is False
    assert all(entry.values is not None for entry in result.scalar_quantities)
    for mode, draw_indices in enumerate(((1, 2, 3, 4), (5, 6, 7, 8), (9, 10, 11, 12))):
        expected = dependence_comparisons(result.reference, truth_index=0, draw_indices=draw_indices)
        entry = result.ranks[mode*6+5]
        assert entry.comparisons == expected
        if expected.status == "resolved":
            assert entry.status == "ranked"
            assert entry.rank == randomized_rank(0, expected.comparisons, seed=entry.seed.scalar_uint128)
        else:
            assert entry.status == expected.status and entry.rank is None
```

- [ ] **Step 4: Record Task2 RED for new-module imports.**

```bash
/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python -m pytest tests/test_heterogeneity_sbc_quantities.py -o addopts='' -q
```

Expected RED: missing quantity source/types. Fix test-only syntax/import defects
before attributing the failure to missing behavior. Do not invoke actual fits.

- [ ] **Step 5: Implement result constructors and structural reference validation.** Use exactly the spec declarations, status table and enclosing-result checks. Keep representation checks separate from numerical authority. The structural helper's implementation has this complete validation pattern:

```python
def require_quantity_reference(reference, *, points):
    if not isinstance(reference, HeterogeneityDependenceReference):
        raise ValueError("reference must be a HeterogeneityDependenceReference")
    if (type(reference.orders) is not tuple
            or len(reference.orders) != 3
            or any(isinstance(x, (bool, np.bool_)) or not isinstance(x, (int, np.integer))
                   for x in reference.orders)
            or reference.orders != (64, 128, 256)
            or type(reference.analytic_separability) is not bool):
        raise ValueError("reference order or separability metadata is malformed")
    if type(points) is not tuple or not points:
        raise ValueError("expected points must be a nonempty tuple")
    if type(reference.points) is not tuple or len(reference.points) != len(points):
        raise ValueError("reference point count does not match")
    for record, expected in zip(reference.points, points, strict=True):
        if not isinstance(record, DependencePointReference):
            raise ValueError("reference point is malformed")
        if type(expected) is not tuple or len(expected) != 2:
            raise ValueError("expected point is malformed")
        for value in (*expected, record.mean, record.rho):
            if (type(value) not in (float, np.float16, np.float32, np.float64)
                    or not math.isfinite(float(value)) or not 0 < float(value) < 1):
                raise ValueError("point parameters must be finite interior floats")
        if (float(record.mean), float(record.rho)) != expected:
            raise ValueError("reference point does not match input")
        if (type(record.components) is not tuple or len(record.components) != 3
                or any(type(row) is not tuple or len(row) != 4 for row in record.components)
                or type(record.raw_values) is not tuple or len(record.raw_values) != 3
                or type(record.resolved) is not bool):
            raise ValueError("reference point evidence shape is malformed")
        for value in (*record.raw_values, record.value, record.error_bound,
                      *(value for row in record.components for value in row)):
            if (type(value) not in (float, np.float16, np.float32, np.float64)
                    or not math.isfinite(float(value))):
                raise ValueError("reference evidence must contain finite supported floats")
        if record.error_bound < 0:
            raise ValueError("reference error bound must be nonnegative")
```

Do not recompute the evidence, component arithmetic or guard in this helper.
The new constructors can normalize their own scalar fields; existing immutable
reference/comparison objects remain intact. Put the one private structural
comparison validator in this same types module; individual rank constructors
and the public binding helper below share it. Do not copy either function into
the orchestrator. All public signatures receive the declared type annotations.

```python
def _require_comparison_structure(comparisons):
    if not isinstance(comparisons, DependenceComparisons):
        raise ValueError("comparison call must return DependenceComparisons")
    if type(comparisons.status) is not str or comparisons.status not in (
        "resolved", "dependence_reference_unresolved", "dependence_rank_order_unresolved"
    ):
        raise ValueError("comparison status is invalid")
    rows = comparisons.comparisons_by_order
    if type(rows) is not tuple or len(rows) != 3:
        raise ValueError("raw comparisons must have three order rows")
    checked = list(rows)
    if comparisons.status == "resolved":
        checked.append(comparisons.comparisons)
    elif comparisons.comparisons is not None:
        raise ValueError("unresolved comparisons cannot carry resolved signs")
    for row in checked:
        if type(row) is not tuple or len(row) != 4:
            raise ValueError("comparison rows must contain four signs")
        for value in row:
            sign = simulation_integer(value, "comparison sign")
            if sign not in (-1, 0, 1):
                raise ValueError("comparison signs must be -1, 0 or1")


def require_quantity_comparisons(comparisons, *, reference, truth_index, draw_indices):
    if (not isinstance(reference, HeterogeneityDependenceReference)
            or type(reference.points) is not tuple
            or any(not isinstance(point, DependencePointReference) for point in reference.points)):
        raise ValueError("comparison reference is malformed")
    require_quantity_reference(
        reference, points=tuple((point.mean, point.rho) for point in reference.points)
    )
    truth = simulation_integer(truth_index, "truth index")
    if type(draw_indices) is not tuple or len(draw_indices) != 4:
        raise ValueError("draw indices must be a four-tuple")
    draws = tuple(simulation_integer(index, "draw index") for index in draw_indices)
    if (not 0 <= truth < len(reference.points)
            or any(not 0 <= index < len(reference.points) for index in draws)
            or truth in draws or len(set(draws)) != 4):
        raise ValueError("comparison indices must be in range and distinct")
    _require_comparison_structure(comparisons)
    expected_raw = tuple(
        tuple(
            int(reference.points[index].raw_values[order] > reference.points[truth].raw_values[order])
            - int(reference.points[index].raw_values[order] < reference.points[truth].raw_values[order])
            for index in draws
        )
        for order in range(3)
    )
    if comparisons.comparisons_by_order != expected_raw:
        raise ValueError("raw comparison signs do not match their reference points")
```

For rank records check status-specific fields from the spec. For the outer
result check all parent dependencies, exact seed identities, point map/cyclic
pairs and q0..2 values; call the public binding helper for every retained
comparison with its mapped indices. No RNG or quadrature runs in constructors.

- [ ] **Step 6: Implement guarded selection and vector quantity calls.** The code below supplies the concrete invocation/validation boundary; keep each invocation try restricted to the call itself.

```python
def _returned_vector(value, size):
    if (not isinstance(value, np.ndarray) or value.dtype != np.dtype(np.float64)
            or value.shape != (size,) or not np.all(np.isfinite(value))):
        raise ValueError("log mass must return a finite float64 point vector")
    return value


def _actual_error(error):
    return DiagnosticCallError(type(error).__module__ + "." + type(error).__qualname__, str(error))


def _scalar_quantities(data, points):
    means = np.array([point[0] for point in points], dtype=np.float64)
    rhos = np.array([point[1] for point in points], dtype=np.float64)
    entries = [ScalarQuantityEvidence(q, tuple(float(x) for x in values), None, None)
               for q, values in enumerate((means, rhos, means*rhos))]
    total = np.zeros(len(points), dtype=np.float64)
    for index, row in enumerate(data.training):
        try:
            returned = heterogeneity_log_mass(row.ac, row.an, mean=means, rho=rhos)
        except Exception as error:
            entries.append(ScalarQuantityEvidence(3, None, _actual_error(error), index))
            break
        vector = _returned_vector(returned, len(points))
        with np.errstate(over="ignore", invalid="ignore"):
            total += vector
        if not np.all(np.isfinite(total)):
            raise ArithmeticError("training log likelihood accumulation must remain finite")
    else:
        entries.append(ScalarQuantityEvidence(3, tuple(float(x) for x in total), None, None))
    try:
        returned = heterogeneity_log_mass(0, 20, mean=means, rho=rhos)
    except Exception as error:
        entries.append(ScalarQuantityEvidence(4, None, _actual_error(error), None))
    else:
        values = _returned_vector(returned, len(points))
        entries.append(ScalarQuantityEvidence(4, tuple(float(x) for x in values), None, None))
    return tuple(entries)
```

The main public entry validates accepted prior inputs then calls the actual
public require_fit_identity before creating diagnostic identities/streams. Its
selection implementation is exactly:

```python
selection_seeds = tuple(DiagnosticSeedIdentity(spec.case, spec.attempt_id, 5, (c,)) for c in range(4))
indices = []
correct = []
for chain, identity in enumerate(selection_seeds):
    stream = np.random.Generator(np.random.PCG64(np.random.SeedSequence(identity.entropy, spawn_key=identity.spawn_key)))
    draw = simulation_integer(stream.integers(0, spec.config.draws), "selected draw")
    if not 0 <= draw < spec.config.draws:
        raise ValueError("selected draw is outside the accepted attempt")
    indices.append((chain, draw))
    correct.append((float(fit.mean_draws[chain, draw, 0]), float(fit.rho_draws[chain, draw, 0])))
cyclic = tuple((correct[c][0], correct[(c-1) % 4][1]) for c in range(4))
control_seed = DiagnosticSeedIdentity(spec.case, spec.attempt_id, 8, (1,))
control = draw_prior_control(seed=control_seed)
if not isinstance(control, PriorControlResult):
    raise ValueError("control helper must return a PriorControlResult")
control = PriorControlResult(control.seed, control.pairs, control.failure)
if control.seed != control_seed:
    raise ValueError("control identity does not match accepted attempt")
truth = (dataset.truth.mean, dataset.truth.rho)
if control.status == "complete":
    slots = tuple(range(13))
    points = (truth, *correct, *control.pairs, *cyclic)
else:
    slots = (0, 1, 2, 3, 4, 9, 10, 11, 12)
    points = (truth, *correct, *cyclic)
scalar_quantities = _scalar_quantities(dataset, points)
reference = None
reference_error = None
try:
    reference = heterogeneity_dependence_reference(
        tuple((row.ac, row.an) for row in dataset.training),
        mean_prior=(1.0, 1.0), rho_prior=(1.0, 9.0 if spec.case.track_id == 0 else 4.0),
        points=points,
    )
except Exception as error:
    reference_error = _actual_error(error)
else:
    require_quantity_reference(reference, points=points)
```

Use the validated actual control record; do not catch malformed control-helper
returns as RNG failures. That helper already retains its actual RNG errors.

- [ ] **Step 7: Implement mode-major guarded rank outcomes and final return.** Follow this explicit call/state body after the point/reference code. Import the public `require_quantity_comparisons` from the types module; it validates representation and raw-sign binding, not numerical resolution.

```python
position = {slot: index for index, slot in enumerate(slots)}
rank_entries = []
for mode in range(3):
    for quantity in range(6):
        identity = DiagnosticSeedIdentity(spec.case, spec.attempt_id, 6, (mode, quantity))
        comparisons = None
        rank = None
        error_evidence = None
        if mode == 1 and control.status == "failed":
            status = "control_failed"
        elif quantity < 5 and scalar_quantities[quantity].values is None:
            status = "quantity_failed"
        elif quantity == 5 and reference is None:
            status = "reference_failed"
        else:
            draw_indices = tuple(position[1 + mode*4 + c] for c in range(4))
            if quantity < 5:
                values = scalar_quantities[quantity].values
                truth_value = values[position[0]]
                draw_values = tuple(values[index] for index in draw_indices)
                status = "ready"
            else:
                try:
                    comparisons = dependence_comparisons(reference, truth_index=position[0], draw_indices=draw_indices)
                except Exception as error:
                    status = "comparison_failed"
                    error_evidence = _actual_error(error)
                else:
                    require_quantity_comparisons(
                        comparisons, reference=reference,
                        truth_index=position[0], draw_indices=draw_indices,
                    )
                    status = "ready" if comparisons.status == "resolved" else comparisons.status
                    if status == "ready":
                        truth_value, draw_values = 0, comparisons.comparisons
            if status == "ready":
                scalar_seed = identity.scalar_uint128
                try:
                    returned_rank = randomized_rank(truth_value, draw_values, seed=scalar_seed)
                except Exception as error:
                    status = "rank_failed"
                    error_evidence = _actual_error(error)
                else:
                    rank = simulation_integer(returned_rank, "rank")
                    if not 0 <= rank <= 4:
                        raise ValueError("rank must be between0 and4")
                    status = "ranked"
        rank_entries.append(QuantityRankEvidence(mode, quantity, identity, status, rank, comparisons, error_evidence))
return SelectedSbcQuantities(
    spec, tuple(indices), selection_seeds, control, slots, points, scalar_quantities,
    reference, reference_error, tuple(rank_entries),
)
```

`ready` is a private transient local state and never a permitted public result
status. Execution and the outer result call the same public binding helper;
neither duplicates its checks or the numerical resolution guard. Do not evaluate
purpose6 scalar words before the dataset guard, randomize unresolved comparisons,
or reconstruct actual h from signs. Keep the existing objects as evidence.

- [ ] **Step 8: Run focused GREEN and the mandatory smoke/static checks.**

```bash
/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python -m pytest tests/test_heterogeneity_diagnostic_seeds.py tests/test_heterogeneity_sbc_controls.py tests/test_heterogeneity_sbc_quantities.py -o addopts='' -q
/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python scripts/smoke.py
/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/ruff check genomeos/validation/heterogeneity_diagnostic_seeds.py genomeos/validation/heterogeneity_sbc_controls.py genomeos/validation/heterogeneity_sbc_quantity_types.py genomeos/validation/heterogeneity_sbc_quantities.py tests/test_heterogeneity_diagnostic_seeds.py tests/test_heterogeneity_sbc_controls.py tests/test_heterogeneity_sbc_quantities.py
/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python scripts/freeze_contract.py --check
/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python scripts/check_module_size.py
```

Expected: focused tests including the single actual-reference integration pass,
mandatory smoke and static checks pass; frozen production schemas do not change.
Treat a test/integration failure as evidence to diagnose, not permission to
change scientific thresholds or seed identities. No extra reference-case search.

- [ ] **Step 9: Write the evidence note using observed outputs and complete the final review gates.** The fixed prose below is the note's scope section; append the actual command outputs/counts and any failures from Steps8/9 as literal observed evidence, not forecast values.

```markdown
# B0H selected SBC quantity adapter evidence

This unit advances #211/#189 and implements Atlas design §§5,7–8,12.
It evaluates six declared quantities at one uniformly selected postwarmup
draw per chain, preserving pairing across quantities. Prior-only controls
use a separate frozen scalar stream; cyclic controls apply the fixed c-1
rho pairing. Only accepted prior-SBC study0 fits are eligible.

Tests use valid sixteen-row synthetic metadata and constructed accepted-fit
objects with synthetic diagnostics. Rational beta-binomial products provide
independent scalar expectations. Mock dependence references test state and
call behavior only; they are not evidence of scientific separability or
reference accuracy for the mixed-count fixture. One test calls the actual
reference and existing comparison guard, accepting its actual outcome.

No NUTS study, negative-control detection result, full-study p-value,
conditional-success rescue, parameter/predictive summary or real-data result
is reported. Future study accounting must retain incomplete quantities and
execution defects; constructor consistency is not source or fitting provenance.
```

Before PR, the root runs the full unchanged CI commands on the final source head:

```bash
/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/ruff check .
/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python scripts/freeze_contract.py --check
/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python scripts/check_module_size.py
/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python scripts/check_private_files.py
/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python scripts/smoke.py
/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python -m pytest -o addopts='' -q
```

The implementing task does not independently rerun the full suite if root owns
that final stable-head check. Report focused commands exactly and leave full-CI
claims to root's observed output. Figure generation is not required: this unit
adds no renderable observation, surface, mask or burden artifact.

- [ ] **Step 10: Inspect staging, run the privacy gate and commit Task2.**

```bash
/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python scripts/check_private_files.py
git add genomeos/validation/heterogeneity_sbc_quantity_types.py genomeos/validation/heterogeneity_sbc_quantities.py tests/test_heterogeneity_sbc_quantities.py docs/research/population-heterogeneity-sbc-quantities-2026-09-10.md
git diff --cached --name-only
git diff --cached --check
/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python scripts/check_private_files.py
git commit -m "feat: retain guarded SBC quantities and paired-control ranks"
```

Root handles task/whole-branch review and PR publication after its checks. Do
not commit directly to main or include scratch SDD files. The coherent PR
states it advances#211/#189 and includes actual validation and limits; it
does not close either issue or imply the future full study passed.

## Preflight coverage

Task1 covers all diagnostic purposes5..8, namespace restrictions, exact word
assembly, scalar call order, immutable control states and supported failure
evidence. Task2 covers the public guard, exact accepted selection, mixed-AN
scalar products, canonical13/9 mapping, one reference, guarded ranks, every
closed state, malformed return propagation and one actual-reference integration.
The four files have coherent public dependencies; control records do not depend
on Task2. No codec choice, new reference guard, denominator or method is added.

Root personally read and self-reviewed this plan and spec before freeze.
Code blocks are implementation/test instructions, not previously passing
results. Record actual commands, failures and outputs during implementation.
