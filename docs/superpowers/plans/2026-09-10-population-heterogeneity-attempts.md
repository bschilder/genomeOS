# B0H Single-Fit Attempt Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bind one unchanged public B0H fit invocation to its declared synthetic
case and preserve its exact returned fit, failure or identity-rejection evidence.

**Architecture:** One pure attempt module owns the initial/retry configuration,
public identity guard and typed one-call outcome. A separate structural check
exercises the actual all-unavailable refusal. Durable checkpoint transitions,
quantities and study execution are separate subsequent components, not hidden
callbacks or retries in this module.

**Tech Stack:** Locked Python3.12, NumPy, existing public PyMC fitter, pytest;
no new dependencies and no actual sampling in these fixtures.

**Spec:** `docs/superpowers/specs/2026-09-10-population-heterogeneity-attempts-design.md`,
extending the committed SBC and generation specifications under #211/#189.

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

The controller owns final stable-tree full CI and the broad branch review. The
implementer owns focused tests, mandatory smoke, Ruff, module-size, privacy and
scoped staging/commit. No sampler, corpus, GPU, source ingestion, HTTP or schema
change. Do not modify the fitter/generator to make an attempt fixture pass.

---

### Task 1: Declared one-attempt invocation and lossless outcome accounting

**Files:** Create `genomeos/validation/heterogeneity_attempts.py`,
`tests/test_heterogeneity_attempts.py`, and
`docs/research/population-heterogeneity-attempts-2026-09-10.md`.

**Interfaces consumed:**

- Generation facade: `SbcCaseId(track_id,study_id,case_id,replicate_id)`,
  `SeedIdentity(entropy)`, `GeneratedDataset(case_id,provenance,truth,training,
  latent_frequencies,shared_history,heldouts,beta_zero_draws,beta_one_draws)`,
  `AllUnavailableDataset(case_id,provenance,training)`,
  `sbc_seed_identity(case,*,purpose_id,attempt_id)->SeedIdentity` and public
  `generate_sbc_case(case)->GenerationResult` for tiny metadata fixtures only.
- Public `simulation_integer(value:object,name:str)->int` may be reused from
  generation types for exact non-Boolean integer validation; no private imports.
- `ReferenceCount(record_id,variant_id,group_id,region_id,variant_group,ac,an)`
  and public `ReferenceInfeasibleError` from validation.reference_counts.
- `PopulationHeterogeneityConfig(mean_prior_alpha,mean_prior_beta,rho_prior_alpha,
  rho_prior_beta,draws,tune,chains,target_accept,seed)`;
  `PopulationHeterogeneityFit(config,variant_ids,mean_draws,rho_draws,
  training_record_ids,training_group_ids,unavailable_training_ids,training_counts,
  diagnostics,divergence_count)`;
  `VariantTrainingCounts(variant_id,training_observation_count,training_ac,training_an)`;
  `VariantHeterogeneityDiagnostics(variant_id,max_rhat,min_bulk_ess,min_tail_ess)`;
  `HeterogeneityConvergenceError(reason,*,diagnostics=(),divergence_count=None)`
  from surfaces.heterogeneity_types.
- `fit_reference_population_heterogeneity(training,*,config)->PopulationHeterogeneityFit`
  from surfaces.reference_heterogeneity. Patch this imported public call in tests,
  never the model's numerical implementation.

**Interfaces produced:** Exactly the spec's frozen FitAttemptSpec, AttemptError,
FitAttemptResult and StructuralCheckResult fields; public FitIdentityError with
immutable `.mismatches`; and these functions:

```python
def plan_fit_attempt(dataset: GeneratedDataset, *, attempt_id: int) -> FitAttemptSpec: ...
def require_fit_identity(dataset: GeneratedDataset, *, spec: FitAttemptSpec,
                         fit: PopulationHeterogeneityFit) -> None: ...
def run_fit_attempt(dataset: GeneratedDataset, *, spec: FitAttemptSpec) -> FitAttemptResult: ...
def exercise_unavailable(dataset: AllUnavailableDataset) -> StructuralCheckResult: ...
```

- [ ] **Step 1: Write the seed/config and public-call fixtures before the module exists.**

The fixture generator calls produce only a handful of stable cases for metadata;
they do not constitute a new complete generation corpus or calibration study.
Use fixed case13 (mean.05,rho.1,sixteenAN20) for mocked successful calls. Use
prior case0 only for literal seed metadata anchors and mixed-AN identity checks.

```python
def test_initial_attempt_uses_literal_declared_seed() -> None:
    data = generate_sbc_case(SbcCaseId(0, 0, 0, 0))
    assert isinstance(data, GeneratedDataset)
    spec = plan_fit_attempt(data, attempt_id=0)
    assert spec.seed.entropy == (42, 211, 1, 0, 0, 0, 0, 4, 0)
    assert spec.config == PopulationHeterogeneityConfig(
        mean_prior_alpha=1.0, mean_prior_beta=1.0,
        rho_prior_alpha=1.0, rho_prior_beta=9.0,
        draws=500, tune=1000, chains=4, target_accept=0.9, seed=279725986,
    )

def test_retry_changes_only_budget_and_declared_seed() -> None:
    data = generate_sbc_case(SbcCaseId(0, 0, 0, 0))
    assert isinstance(data, GeneratedDataset)
    first = plan_fit_attempt(data, attempt_id=0)
    retry = plan_fit_attempt(data, attempt_id=1)
    assert retry.seed.entropy == (42, 211, 1, 0, 0, 0, 0, 4, 1)
    assert retry.config == replace(first.config, draws=1000, tune=2000, seed=2209982770)
```

Repeat the anchors for track1: initial848552836,retry1074711532,rho_beta4.
No seed re-enumeration benchmark is needed. Test Boolean/2/negative attempts,
GenerationFailure and structural inputs, wrong spec case/entropy/config before
any mocked fitter invocation. Invoke focused pytest before source exists and
record the actual missing-module RED, not an assumed failure message.

- [ ] **Step 2: Implement exact planned contracts, identity fields and one invocation.**

Create the module with design §§5,7–8,12 and #211 in its docstring, future
annotations and SEED=42. Implement the spec's exact constructor domains and
discriminated states; no generic registry/factory/configurable policy. Use a
private metadata-only planned-spec helper shared by constructor and public
planner rather than constructor recursion. Both fit seeds are computed from
their already-frozen purpose4 namespaces; collision is refusal, not reseeding.

The public-call boundary is structurally this sequence; all named helpers below
are private within this one module and exist only to implement these contracts:

```python
def run_fit_attempt(dataset, *, spec):
    # Raises for caller errors before the try; never records a fake realization.
    _require_planned_case(dataset, spec)
    try:
        fitted = fit_reference_population_heterogeneity(dataset.training, config=spec.config)
    except HeterogeneityConvergenceError as error:
        return _failed_attempt(spec, error, category="convergence")
    except ReferenceInfeasibleError as error:
        return _failed_attempt(spec, error, category="reference_infeasible")
    except ValueError as error:
        return _failed_attempt(spec, error, category="value")
    except ArithmeticError as error:
        return _failed_attempt(spec, error, category="arithmetic")
    except RuntimeError as error:
        return _failed_attempt(spec, error, category="runtime")
    # No unknown-Exception/BaseException catch here; later adapter owns these.
    try:
        require_fit_identity(dataset, spec=spec, fit=fitted)
    except FitIdentityError as error:
        return _identity_rejected(spec, fitted, error.mismatches)
    return FitAttemptResult(spec, "accepted", fitted, None, (), None)
```

Annotate actual source interfaces fully. `_failed_attempt` builds actual
qualified exception metadata and spec-exact state, `_identity_rejected` retains
typed fits or only wrong-return type, and `_require_planned_case` compares the
complete public planned spec without hiding errors in fit outcomes. The public
identity guard reports all closed mismatch fields in spec order. Expected rows
are lexical IDs, sorted unique groups, AN0 IDs and positive-AN count totals;
all return axes are exactly(4,draws,1). No posterior recomputation or clipping.

- [ ] **Step 3: Add exact return, failure, identity and structural fixtures.**

Construct valid mocked returned fits with explicit float64 `(4,draws,1)` arrays,
e.g. mean.25/rho.2, artificial passing diagnostics(1.0,200.0,200.0), zero
divergences and exact generated metadata. Label these as mock metadata fixtures,
not measured convergence. The fake public fitter records exactly one positional
training tuple and the keyword config and returns that object unchanged.

```python
def test_mocked_public_return_is_preserved(monkeypatch, data, mocked_fit):
    spec = plan_fit_attempt(data, attempt_id=0)
    calls = []
    def fake_fit(training, *, config):
        calls.append((training, config))
        return mocked_fit
    monkeypatch.setattr(attempts, "fit_reference_population_heterogeneity", fake_fit)
    result = run_fit_attempt(data, spec=spec)
    assert result.status == "accepted"
    assert result.fit is mocked_fit
    assert calls == [(data.training, spec.config)]
    assert result.error is None and result.identity_mismatches == ()
```

Required fixture matrix:

| Fixture | Assertions |
| --- | --- |
| Initial/retry, both tracks | One call per explicit run, exact config/rows; no automatic second call. |
| Shared paired stress | Identical training tuples across tracks; distinct priors/seeds, no batching. |
| Mixed AN | All sixteen rows including AN0 passed unchanged; lexical row10/row2 ID ordering and exact unavailable/count metadata. |
| Convergence sparse/full | Exact class/message/reason, empty or available diagnostics, optional countNone/0/positive; no fabricated fit arrays. |
| Known other errors | ReferenceInfeasibleError, ValueError, OverflowError/FloatingPointError/ArithmeticError, RuntimeError; exact category, one call, no retry. |
| Unknown execution | A custom ordinary Exception propagates unchanged; KeyboardInterrupt/SystemExit propagate, never converted to accepted/failed result. |
| Returned identity | Independently alter config/prior/seed/budget/variant, axes, record/group/unavailable IDs and counts while keeping fit constructor legal; all actual mismatch names retained, returned typed fit kept. |
| Wrong return | None/object yields exactly(return_type,) and actual qualified type; no arbitrary object serialization. |
| Invalid callers | Malformed spec/dataset/type/attempt rejected before fake call. |
| Immutable states | Frozen fields/tuples, invalid accepted/error/mismatch/type combinations, bad category/reason/count/types rejected. |

Where the public fit constructor forbids an isolated mismatch (e.g. changing
available row count without its provenance), construct the smallest legal joint
change and assert every resulting mismatch; do not bypass constructor validation.
Direct tests of array/diagnostic malformation belong to the existing fitter
contract suite; do not mutate frozen objects to manufacture impossible returns.

For both study3 tracks, leave the actual public fitter real and use mocks that
raise if its pm.Model or pm.sample is entered. Assert typed expected_refusal,
actual ReferenceInfeasibleError class/message, no returned fit/type/attempt/seed,
expected_sampler_calls0, and both mock call_count0. This is the only real public
fitter execution in this unit. Mock alternate exception/typed return/wrong return
for structural failure states; no retry, BaseException still propagates.

- [ ] **Step 4: Record bounded evidence, run gates and commit only owned files.**

The evidence note states actual commands/pass counts, real missing-module RED,
mock versus actual-refusal evidence, unchanged source contracts, exact size,
and limitations: no fitting calibration, durable checkpoint/resume, full corpus
or predictive gain. Record the one-attempt/identity-error/unused-structural-seed
rulings and their costs. No guessed dates, runtime hashes or unavailable outputs.

Use the controller-provided locked runtime and cache paths; no dependency changes.

```bash
python -m pytest tests/test_heterogeneity_attempts.py -q -rA
python scripts/smoke.py
ruff check .
python scripts/check_module_size.py
python scripts/check_private_files.py
git diff --check
git add genomeos/validation/heterogeneity_attempts.py tests/test_heterogeneity_attempts.py docs/research/population-heterogeneity-attempts-2026-09-10.md
git diff --cached --name-only
git commit -m 'feat: bind B0H fit attempts to declared cases'
```

Do not add closes#211: this advances it, but the actual complete SBC/stress
study and benchmark admission remain unfinished. Report the scoped commit and
all exact gate outcomes to the controller for fresh independent task review.
