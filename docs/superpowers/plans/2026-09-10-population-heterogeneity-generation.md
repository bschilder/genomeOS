# B0H Independent Synthetic Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Independently generate every declared B0H synthetic case with exact
identity, latent/count provenance, structural absence and failure accounting.

**Architecture:** A pure sampling module and validated case/result contracts;
the original facade connects the declared manifest to the future fitter adapter.
The generator never calls the fitted likelihood, predictor or scorer. This unit
implements generation only, not the sampler runner or1936-fit study execution.

**Tech Stack:** Locked Python3.12, NumPy, pytest; no new dependency.

**Spec:** `docs/superpowers/specs/2026-09-10-population-heterogeneity-generation-design.md`,
extending `2026-09-10-population-heterogeneity-sbc-design.md`.

## Global Constraints

- Pure validation modules have no filesystem, network, HTTP, environment or UI dependency.
- Stochastic modules declare `SEED = 42`; inputs and configuration determine draws on a pinned runtime.
- No new package dependency, P1/production schema, serving change, inferred coordinate or radius.
- Keep existing clinical gates and global promotion defaults unchanged.
- AN=0 is retained as unavailable, never converted to frequency zero.
- No cross-variant pooling or independence claim for linked loci.
- All sampler/prior/scorer/convergence contracts in the parent B0H spec stand.
- Existing analytical, quadrature and numerical regression thresholds stay unchanged.
- Public science functions reject Boolean integers, malformed shapes, nonfinite
  values and unsupported domains; failures are not coerced into output.
- Production modules target at most500 logical lines; split by responsibility
  before crossing the repository limit.

The controller owns one final stable-tree full CI and one broad review. The
implementer runs focused tests, mandatory smoke, Ruff, module-size and privacy,
inspects staged paths, and commits only owned files. No actual model fit, full
generation corpus, new study, source ingestion, GPU launch or serving change.
Tiny generation calls in deterministic unit fixtures are explicitly in scope.

---

### Task 1: Independent known-truth case generation and exact fixtures

**Files:** Create `genomeos/validation/heterogeneity_simulation.py`,
`genomeos/validation/heterogeneity_simulation_types.py`,
`tests/test_heterogeneity_simulation.py`, and
`docs/research/population-heterogeneity-generation-2026-09-10.md`.

**Interfaces:** The types module consumes only public `ReferenceCount` from
`genomeos.validation.reference_counts` (record_id,variant_id,group_id,region_id,
variant_group,ac,an). Sampling consumes those public contracts. Produce the
following frozen facade value objects and functions; all constructor domains
and relationships are validated as in the spec. The types module owns case,
seed and result validation plus enumeration; the original sampling module
explicitly re-exports that original API without a circular dependency.

```python
Entropy = tuple[int, int, int, int, int, int, int, int, int]

@dataclass(frozen=True)
class SbcCaseId:
    track_id: int
    study_id: int
    case_id: int
    replicate_id: int
    # calculated canonical_id: str

@dataclass(frozen=True)
class GenerationId:
    track_id: int
    study_id: int
    case_id: int
    replicate_id: int
    # calculated canonical_id: str

@dataclass(frozen=True)
class SeedIdentity:
    entropy: Entropy
    # calculated fit_uint32: int | None, only purpose4 has a fit seed

@dataclass(frozen=True)
class ParameterTruth:
    mean: float
    rho: float

@dataclass(frozen=True)
class GenerationProvenance:
    generation_id: GenerationId
    seeds: tuple[SeedIdentity, SeedIdentity, SeedIdentity, SeedIdentity]
    # fixed protocol_id/algorithm_id/bit_generator/floating_dtype properties

@dataclass(frozen=True)
class SharedHistory:
    cluster_frequencies: tuple[float, float]
    candidate_frequencies: tuple[float, ...]
    uses_cluster: tuple[bool, ...]

@dataclass(frozen=True)
class HeldoutTarget:
    kind: str
    row: ReferenceCount
    latent_frequency: float
    cluster_id: int | None
    cluster_frequency: float | None
    candidate_frequency: float | None
    uses_cluster: bool | None

@dataclass(frozen=True)
class GeneratedDataset:
    case_id: SbcCaseId
    provenance: GenerationProvenance
    truth: ParameterTruth
    training: tuple[ReferenceCount, ...]
    latent_frequencies: tuple[float, ...]
    shared_history: SharedHistory | None
    heldouts: tuple[HeldoutTarget, ...]
    beta_zero_draws: int
    beta_one_draws: int
    # fixed status='available'

@dataclass(frozen=True)
class AllUnavailableDataset:
    case_id: SbcCaseId
    provenance: GenerationProvenance
    training: tuple[ReferenceCount, ...]
    # fixed status='all_unavailable', truth/latent_frequencies/shared_history=None,
    # heldouts=(), expected_sampler_calls=0,
    # refusal_reason='no_available_training_counts'

@dataclass(frozen=True)
class GenerationFailure:
    case_id: SbcCaseId
    provenance: GenerationProvenance
    stage: str
    index: int | None
    reason: str
    truth: ParameterTruth | None
    sampled_mean: float | None
    sampled_rho: float | None
    offending_value: float | int | None
    exception_type: str | None
    exception_message: str | None
    # fixed status='generation_failed'; no partial arrays

GenerationResult = GeneratedDataset | AllUnavailableDataset | GenerationFailure

def enumerate_sbc_cases() -> tuple[SbcCaseId, ...]: ...
def generation_id(case: SbcCaseId) -> GenerationId: ...
def sbc_seed_identity(
    case: SbcCaseId, *, purpose_id: int, attempt_id: int,
) -> SeedIdentity: ...
def generate_sbc_case(case: SbcCaseId) -> GenerationResult: ...
```

The readable single-module draft exceeded the500-line target, so the controller
authorized the focused contract/sampling split. The only new supporting public
interfaces live in the types module, not the original facade:

```python
def simulation_integer(value: object, name: str) -> int: ...
def simulation_probability(value: object, name: str) -> float: ...
def simulation_failure_scalar(value: object, name: str) -> float | int: ...
def fixed_simulation_truth(case: SbcCaseId) -> ParameterTruth | None: ...
def simulation_training_an(case: SbcCaseId) -> tuple[int, ...]: ...
def simulation_reference_count(
    generation: GenerationId, where: str, key: str, ac: int, an: int,
) -> ReferenceCount: ...
```

These are the actual shared scalar and metadata contracts, not private imports
or a registry/factory layer. Numeric helper domains are exactly the spec's
successful-probability and failure-evidence rules; integer normalization leaves
contextual bounds to callers. Case helpers validate before decoding. Row helper
requires valid GenerationId, literaltrain/heldout, canonical string index0..15
or permitted target kind, matching AN and valid integerAC. Structural cases have
no heldout. Keep generation-only provenance/evidence wrappers local/private.
Both production modules target500logical lines and retain the hard800/50KiB gate.
Test original facade exports/import order plus supporting helper refusals; no
random call, seed, scientific field or original interface is changed by the split.

Fixed labels: protocolb0h_sbc_v1, algorithmb0h_generation_v1,
bit_generatorPCG64,floating_dtypefloat64. Cases/stages/reasons/labels/RNG call
order are the exact closed spec domains, not configurable strings. Stronger
Literal annotations may clarify those domains without changing public values.
No successful-result default for a missing field. Exceptions in RNG calls become
typed generation failures only under the narrow spec rules; malformed callers
raise ValueError. No catch-all wrapper around generator validation.

- [ ] **Step 1: Write identity, literal numerical and structural failing tests.**

```python
def test_manifest_and_literal_seed_anchors():
    cases = sim.enumerate_sbc_cases()
    assert len(cases) == 1938
    assert Counter(c.study_id for c in cases) == {0:1024,1:768,2:128,3:2,4:16}
    assert cases[0].canonical_id == 'b0h_sbc_v1:s0:c0:r0:t0'
    assert cases[1].canonical_id == 'b0h_sbc_v1:s0:c0:r0:t1'
    assert cases[-1].canonical_id == 'b0h_sbc_v1:s4:c1:r3:t1'
    assert [(c.study_id,c.case_id,c.replicate_id,c.track_id) for c in cases] == sorted(
        (c.study_id,c.case_id,c.replicate_id,c.track_id) for c in cases
    )
    first = sim.sbc_seed_identity(cases[0], purpose_id=4, attempt_id=0)
    assert first.entropy == (42,211,1,0,0,0,0,4,0)
    assert first.fit_uint32 == 279725986

def test_fixed_interior_matches_independent_scalar_numpy_construction():
    case = sim.SbcCaseId(track_id=0,study_id=1,case_id=13,replicate_id=0)
    result = sim.generate_sbc_case(case)
    kappa = (1.0-.1)/.1
    rng_q = np.random.Generator(np.random.PCG64(
        np.random.SeedSequence((42,211,1,99,1,13,0,1,0))))
    q = tuple(float(rng_q.beta(.05*kappa,.95*kappa)) for _ in range(16))
    rng_ac = np.random.Generator(np.random.PCG64(
        np.random.SeedSequence((42,211,1,99,1,13,0,2,0))))
    ac = tuple(int(rng_ac.binomial(20,p)) for p in q)
    rng_test = np.random.Generator(np.random.PCG64(
        np.random.SeedSequence((42,211,1,99,1,13,0,3,0))))
    q_test = float(rng_test.beta(.05*kappa,.95*kappa))
    ac_test = int(rng_test.binomial(20,q_test))
    assert result.truth == sim.ParameterTruth(.05,.1)
    assert result.latent_frequencies == q
    assert tuple(row.ac for row in result.training) == ac
    assert tuple(row.an for row in result.training) == (20,)*16
    assert result.heldouts[0].latent_frequency == q_test
    assert result.heldouts[0].row.ac == ac_test

def test_unavailable_has_no_invented_truth_or_rng(monkeypatch):
    def forbidden_rng(*args, **kwargs):
        raise AssertionError('structural fixture must make no RNG')
    monkeypatch.setattr(np.random, 'Generator', forbidden_rng)
    result = sim.generate_sbc_case(sim.SbcCaseId(0,3,0,0))
    assert result.status == 'all_unavailable'
    assert len(result.training) == 16
    assert {(r.ac,r.an) for r in result.training} == {(0,0)}
    assert result.truth is None and result.latent_frequencies is None
    assert result.heldouts == () and result.expected_sampler_calls == 0
```

Also assert the other seven fixed fit seed anchors:
firsttrack0retry2209982770;firsttrack1initial848552836/retry1074711532;
lasttrack0initial1211901720/retry3856046949;
lasttrack1initial1619381632/retry522047641.
Check fixed case0=(.001,0,mixed),case1=(.001,0,sixteen20),
case23=(.5,.5,sixteen20);sharedcase3=(.5,.5,mixed), through public generated
results, not private decoder imports as test oracles. Tiny cases only.

Prior track1 fixture constructs literal truth entropy(42,211,1,1,0,0,0,0,0),
drawsBeta1,1then1,4, and independently repeats literal purpose1/2/3 construction
with mixedAN. Assert both AN0 rows retained with sampled q and AC0, no frequency
zero interpretation. Expected constructions import no generator seed/shape/draw
helper. Run focused file before module exists and record actual import RED.

- [ ] **Step 2: Implement typed identities, exact independent generation and refusals.**

```python
# Used stream construction: no shared RNG and no uint32 generation collapse.
rng = np.random.Generator(np.random.PCG64(np.random.SeedSequence(identity.entropy)))

# Fixed truth decoding; AN choice follows its own inner index.
mean_index, rest = divmod(case.case_id, 8)
rho_index, an_index = divmod(rest, 2)

# Exact prescribed interior arithmetic; validate each result, no floor.
kappa = (1.0 - truth.rho) / truth.rho
a = truth.mean * kappa
b = (1.0 - truth.mean) * kappa

# Shared source selection; retain both raw candidates even when unused.
candidate = rng.beta(a, b)
uniform = rng.random()
uses_cluster = uniform < math.sqrt(0.5)
q = cluster if uses_cluster else candidate
```

Implement scalar-call order from the spec verbatim: study3beforeRNG; prior mean
thenrho; all population draws before training counts; clusterBthenits8V/U rows;
sharedheldoutV/U/countthenfreshB/V/U/count. Rho0 omits Beta/shape work but still
makes16trainingBinomial+1heldoutBinomial calls. No vectorized size argument.

At each RNG call catch only ValueError,FloatingPointError,OverflowError and
record stage/index/class/message with reasonrng_exception. Explicit invalid
return, prior endpoint and shape checks select their fixed coded reason without
message parsing. Propagate unexpected RuntimeError/MemoryError. Retain actual
prior candidates and known truth according to the spec, never partial arrays.
Construct matching exact row labels. Validate joint frozen result contracts
including selected-source equality and raw endpoint counts (17ordinary-interior
or21shared latent Beta draws;0rho0). SharedB0 appears once in those counters,
not again when referenced by the shared heldout. Reject arbitrary scalar-domain
narrowing; accepted Python/NumPy binary64-or-narrower probabilities normalize
losslessly. No fit/scorer helper imports.

- [ ] **Step 3: Add controlled shared, boundary, failure and immutability fixtures.**

Use test-local scalar recording RNGs, patched at the constructor boundary. They
record stream identity, method, arguments and call order, never return production
expected values. A minimal queue fake can implement this pattern:

```python
class RecordingRng:
    def __init__(self, events):
        self.events = iter(events)
        self.calls = []
    def beta(self, a, b):
        method, value = next(self.events)
        assert method == 'beta'
        self.calls.append(('beta',a,b))
        return value
    def random(self):
        method, value = next(self.events)
        assert method == 'random'
        self.calls.append(('random',))
        return value
    def binomial(self, n, p):
        method, value = next(self.events)
        assert method == 'binomial'
        self.calls.append(('binomial',n,p))
        return value
```

Sharedfixture: B0=.2,B1=.8, allVi=.6, uniforms alternate0,.9. Exact trainingq
is(.2,.6)*4followedby(.8,.6)*4. FirstheldoutV.7,U0→q.2;
freshB.3,V.9,U.9→q.9. Secondtinyfixture uses firstU.9,freshU0→q.7,.3.
Uniform exactlysqrt(.5) selectsV. Assert complete scalar event order, correct
training/heldoutAN/q forwarded to Binomial, separate streams, retained candidates,
cluster IDs0/2, disjoint train/test records and groups. Count fake can returnAC0
for these mechanism-only tests; it is not evidence for the Binomial law.

Boundarycase0/1 assert16AC0/20andheldout0/20,16+1Binomial calls,zeroBeta/uniform.
Fixedrho0interiormean confirms no Beta call without relying on deterministic
counts. LatentBeta0/1 values are forwarded unmodified and counted; an unselected
endpointV is counted too. Prior mean0,rho.1 returns failure with both candidates,
no population draws; tinypositive mean,nextafter(0,1),rho.9 underflows a shape
and retains valid truth in failure. Cover invalidNaN/inf/outside[0,1]/Boolean/
nonscalar Beta, uniform1, noninteger or out-of-rangeAC, expected RNG exceptions
at stages and propagated RuntimeError/MemoryError. Exceptions at a trainingrow1
retain identity/truth/stage/index and no partial data attributes.

Public invalid cases: fittrack99or2,study5,priorcase1,fixedcase24,sharedcase4,
study3rep1,boundaryrep4,negative/Boolean/fractional indices; badentropy prefix,
length,track/purpose/attempt combinations; generationattempt1,fitattempt2,
purpose9,fitseedforstudy3. Validate malformed constructors/provenance, row
labels/AN/truth mismatch, wrongheldoutkind/shape, wrongselectedq/clusterB0,
endpointcounters, nonfinite successful output and Boolean numeric values.

Generate onefixed and oneshared case pertrack and verify identical scientific
generation fields,provenance,labels except planned caseidentity; distinctfitseeds.
Reverseorder and unrelatedcasecalls leave results unchanged; dataclasses/tuples
immutable. Do not generate all1938datasets or allfitseeds as a unit-test shortcut.

```python
def test_literal_shared_marginal_and_covariance_anchor():
    m, rho = Fraction(1,2), Fraction(1,2)
    latent_var = m*(1-m)*rho
    latent_cov = latent_var/2
    assert (latent_var,latent_cov) == (Fraction(1,8),Fraction(1,16))
    pmf = (Fraction(3,8),Fraction(1,4),Fraction(3,8))
    expected = sum(i*p for i,p in enumerate(pmf))
    variance = sum((i-expected)**2*p for i,p in enumerate(pmf))
    count_cov = 2*2*latent_cov
    assert variance == Fraction(3,4)
    assert count_cov == Fraction(1,4)
    assert count_cov/variance == Fraction(1,3)
```

Explain the mixture/covariance derivation in the note; this arithmetic fixture
checks the literal derivation, while controlled source selection tests actual
code behavior. It is not a Monte Carlo or fitted-law parity test.

- [ ] **Step 4: Record actual evidence, run covering gates and commit.**

Research note: exact seeds/algorithm/scalar order, synthetic labels, preserved
AN0, structural exception, endpoint semantics, mixture derivation and count-vs-
latent correlation. Record actual RED/GREEN command/output, actual fixture
outcomes, refusals and limits. Do not claim unexecuted mutations, actual study
calibration, exact NumPy continuous draws, timing or external-data validation.

```bash
python -m pytest tests/test_heterogeneity_simulation.py -q
python scripts/smoke.py
ruff check .
python scripts/check_module_size.py
python scripts/check_private_files.py
git diff --check
git add genomeos/validation/heterogeneity_simulation.py genomeos/validation/heterogeneity_simulation_types.py tests/test_heterogeneity_simulation.py docs/research/population-heterogeneity-generation-2026-09-10.md
git diff --cached --name-only
python scripts/check_private_files.py
git diff --cached --check
git commit -m "feat: add independent heterogeneity simulation cases" -m "Advances #211 and #189; no completed calibration study claim."
```
