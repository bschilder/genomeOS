# B0H single-fit attempt design

The owner authorized implementation and delegation without routine approval.
This unit freezes one-call orchestration, not actual study execution.
Advances #211/#189, Atlas design §§5,7–8,12; extends the committed population-
heterogeneity SBC and independent-generation specifications.

## Scientific contract

1. Claim: each eligible synthetic case reaches the actual public fitter with
   exactly its declared rows, prior, budget and initial/retry seed, and returned
   fits cannot be consumed under a different case identity.
2. Acceptance: deterministic mocked-invocation and immutable-return fixtures,
   literal seed/config anchors, lossless exception accounting, and actual public
   all-unavailable refusal before graph/sampler entry. These are orchestration
   correctness checks, not a new actual-fitter calibration or accuracy result.
3. Component: pure `genomeos.validation.heterogeneity_attempts`, one invocation
   per `run_fit_attempt`; downstream immutable checkpoint and quantity adapters
   consume its validated contracts and public identity guard.
4. Assumptions/refusals: generated inputs are validated; only the separately
   checkpointed convergence failure authorizes the adapter to request attempt1.
   No attempt2, hidden retry, data-dependent priors, identity substitution,
   missing-evidence fabrication, serving inference or new package dependency.

## Binding constraints

- Pure validation modules have no filesystem, network, HTTP, environment or UI dependency.
- Stochastic modules declare `SEED = 42`; inputs and configuration determine draws on a pinned runtime.
- No new package dependency, P1/production schema, serving change, inferred coordinate or radius.
- Keep existing clinical gates and global promotion defaults unchanged.
- AN=0 is retained as unavailable, never converted to frequency zero.
- No cross-variant pooling or independence claim for linked loci.
- All sampler/prior/scorer/convergence contracts in the parent B0H spec stand.
- Existing analytical, quadrature and numerical regression thresholds stay unchanged.
- Production modules target at most500 logical lines; retain the hard800/50KiB gate.

The production fitter, predictor, likelihood and generator are unchanged. No
actual NUTS fit, complete generation corpus, checkpoint serializer, CLI, rank
computation, GPU scheduling or model benchmark runs in this unit. Public fitter
calls in tests are mocked except the all-AN0 refusal with graph/sample sentinels.

## Public contracts and exact states

Import only public generation facade/types, public `ReferenceInfeasibleError`,
and the public fitter/types. No private cross-module helpers or cycle. All
collections below are immutable tuples; no broad coercion of malformed scalars.

```python
@dataclass(frozen=True)
class FitAttemptSpec:
    case: SbcCaseId
    attempt_id: int
    seed: SeedIdentity
    config: PopulationHeterogeneityConfig

@dataclass(frozen=True)
class AttemptError:
    category: str
    exception_class: str
    message: str
    reason: str | None
    diagnostics: tuple[VariantHeterogeneityDiagnostics, ...] | None
    divergence_count: int | None

@dataclass(frozen=True)
class FitAttemptResult:
    spec: FitAttemptSpec
    status: str
    fit: PopulationHeterogeneityFit | None
    error: AttemptError | None
    identity_mismatches: tuple[str, ...]
    returned_type: str | None

class FitIdentityError(ValueError):
    # Public .mismatches: tuple[str, ...], exact closed field names below.
    def __init__(self, mismatches: tuple[str, ...]) -> None: ...

@dataclass(frozen=True)
class StructuralCheckResult:
    case: SbcCaseId
    status: str
    error: AttemptError | None
    fit: PopulationHeterogeneityFit | None
    returned_type: str | None
    # fixed expected_sampler_calls property: 0, expectation not observation

def plan_fit_attempt(dataset: GeneratedDataset, *, attempt_id: int) -> FitAttemptSpec: ...
def require_fit_identity(dataset: GeneratedDataset, *, spec: FitAttemptSpec,
                         fit: PopulationHeterogeneityFit) -> None: ...
def run_fit_attempt(dataset: GeneratedDataset, *, spec: FitAttemptSpec) -> FitAttemptResult: ...
def exercise_unavailable(dataset: AllUnavailableDataset) -> StructuralCheckResult: ...
```

`FitAttemptSpec` validates a nonstructural SbcCaseId, exact non-Boolean integer
attempt0/1, its exact purpose4 entropy, and all planned config fields. Recompute
both initial/retry uint32 values and refuse a collision without choosing a seed.
`plan_fit_attempt` accepts only a successful GeneratedDataset; malformed callers,
GenerationFailure and AllUnavailableDataset raise ValueError before fitting.

Initial config: mean_prior_alpha/beta1/1, rho_prior_alpha1, rho_prior_beta9 for
track0 or4 for track1, draws500,tune1000,chains4,target_accept0.9, explicit
purpose4 fit_uint32 seed. Retry: draws1000,tune2000 and its declared attempt1
seed only; no default substitution for a field. Dataset stress truth never
changes the prior. A valid spec for another case is still rejected before fit.

AttemptError categories are exactly convergence, reference_infeasible, value,
arithmetic, runtime, unexpected_exception. All store an actual nonempty qualified
exception class (`type(error).__module__ + '.' + type(error).__qualname__`) and
actual string message, which may be empty. Only convergence has a nonempty
reason, diagnostics tuple (possibly empty), and optional nonnegative non-Boolean
integer divergence count. Other categories require those three fields None.
Do not infer classes from messages. Constructor validation asserts field
consistency, not whether a human-supplied class string truly came from a run.

Result states:

| status | fit | error | mismatches | returned_type |
| --- | --- | --- | --- | --- |
| accepted | typed actual fit | None | empty | None |
| convergence_failed | None | convergence | empty | None |
| failed | None | nonconvergence | empty | None |
| identity_rejected, typed | typed actual fit | None | nonempty, not return_type | None |
| identity_rejected, wrong type | None | None | exactly(return_type,) | actual qualified type |

For accepted state also require fit config equality with spec; its constructor
does not have the original dataset and therefore cannot establish row identity.
The runner and every restored consumer must call the dataset-bound identity
guard. No empty/zero/NaN draw arrays substitute for a failed fit. Preserve a typed
but identity-rejected returned fit for audit; do not relabel it as consumed.

## Identity validation and invocation

Guard caller dataset/spec types and exact planned case agreement before entering
the public fitter. Invoke it once, passing all sixteen `dataset.training` rows
unchanged, including any AN0 rows, with keyword config=spec.config. Do not add heldouts,
sort the actual rows, batch cases or catch planning errors as realized failures.

For a typed return, compare these field names in this exact order and retain all
mismatches: config, variant_ids, mean_draws.shape, rho_draws.shape,
training_record_ids, training_group_ids, unavailable_training_ids, training_counts.
Expected variant is `(dataset.training[0].variant_id,)`; array shapes are exactly
(4,spec.config.draws,1). IDs are lexicographically sorted (including row10 before
row2), groups sorted unique, unavailable IDs from AN0 rows. Expected count tuple
contains one VariantTrainingCounts with positive-AN row count, summed AC, summed
AN and that variant ID. The fit constructor already enforces float64/interior
arrays, diagnostic variant matching, Rhat<=1.05, ESS>=200 and zero divergences;
do not change those gates. Guard wrong-type fit as mismatch exactly return_type.

FitIdentityError holds a nonempty immutable unique tuple from that closed field
set, ordered as above; return_type is allowed only alone. A public guard success
returns None, failure raises this structured error. Use normal ValueError for
invalid dataset/spec callers; they are not returned-fit identity mismatches.

The exact source invocation and future dataset content hash provide separate
provenance: matching labels/aggregate totals alone cannot prove rowwise counts.
The later adapter must bind source/runtime/protocol/dataset bytes before using
the fit. This unit neither invents hashes nor claims a serialized checkpoint.

Catch only around the one public fitter invocation, in order:
HeterogeneityConvergenceError; ReferenceInfeasibleError; ValueError;
ArithmeticError; RuntimeError. Preserve actual class/message and available
convergence reason/diagnostics/count. Return the corresponding typed failure.
Any other Exception propagates to the later artifact adapter, which must record
unexpected execution failure; BaseException/process loss likewise is not turned
into a completed scientific result here. No prediction/rank step runs or retries.

## Structural public refusal

AllUnavailableDataset has no scientific fit seed, attempt, truth or heldout.
`exercise_unavailable` passes its sixteen rows to the actual fitter with a valid
inert constructor config: same track priors and initial budget, seed42. That
seed is never used by the sampler and must not be labeled a scientific seed or
included as a fit spec in StructuralCheckResult. Expected_sampler_calls=0 is an
expectation; the focused test measures zero entry via Model/sample sentinels.

ReferenceInfeasibleError by type yields expected_refusal, its actual error and
no fit/type. Any other ordinary Exception yields unexpected_exception and its
proper typed AttemptError; no fit/type. Any return yields unexpected_return,
no error and either actual typed fit or actual qualified wrong return type.
Never catch BaseException. Result constructors require study3 and those exact
mutually exclusive fields. Neither failure nor unexpected return authorizes retry.

## Separate checkpoint requirement and limits

This unit executes one explicitly requested attempt; it cannot prove a durable
checkpoint exists without violating the no-I/O boundary. The next adapter must
publish/validate immutable attempt0 before an allowed convergence-only attempt1,
reload complete results without fitting, refuse orphaned/mismatched retries, and
retain known publication failures without resampling a result still available.
Those resume semantics require separate adapter tests and are not claimed here.

Root choices and costs: one-attempt boundary adds an explicit durability
transition; structured identity error adds a small public error interface for
run/restored consumers; inert structural config demands an explicit unused-seed
distinction. None changes the scientific model, study denominator or tolerance.
