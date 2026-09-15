# B0H selected SBC quantities design

The owner authorized implementation and delegation without routine approval.
This unit freezes selected-quantity orchestration, not actual study execution.
Advances #211/#189, closes neither. Implements Atlas design §§5,7–8,12 and the
parent population-heterogeneity SBC contract after the one-call attempt unit.

## Scientific contract

1. Claim: accepted prior-SBC fits supply the same four paired posterior points
   to six declared quantities, with fixed controls and retained numerical evidence.
2. Acceptance: literal seed/selection fixtures, independent rational log-mass
   products, control prefix accounting, guarded reference/rank handoff tests and
   one valid-case actual-reference integration. This proves adapter behavior,
   not actual-fitter calibration, negative-control power or study completion.
3. Interface: pure `selected_sbc_quantities(dataset, *, attempt)` consumes the
   public accepted attempt and generated dataset, returning immutable evidence.
   The later artifact/study consumer retains the accepted fit arrays separately.
4. Assumptions/refusals: study0 only, unchanged dataset-bound identity guard and
   reference guard; failures never cause redraw, reselection or scientific retry.
   Stress, structural/failed attempts, predictive/parameter summaries, codecs,
   checkpoints, hashing, full-study reduction and real fits are outside this unit.

## Global constraints

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

No generation purpose0..4 expansion, production scorer reuse, reference guard
copy, default seed or alternate scientific method. The null seed1653499886,
fit uint32 conversion,512 datasets per prior and existing test budgets remain
unchanged. uint128 artifact encoding belongs to the eventual checkpoint contract;
this unit retains exact Python integers and four words without choosing a codec.

## Four-module ownership

| Module under genomeos/validation | Responsibility and public contracts |
| --- | --- |
|heterogeneity_diagnostic_seeds.py|DiagnosticSeedIdentity; no attempt/fitter import|
|heterogeneity_sbc_controls.py|DiagnosticCallError, PriorControlFailure, PriorControlResult, draw_prior_control; independent of rank types|
|heterogeneity_sbc_quantity_types.py|ScalarQuantityEvidence, QuantityRankEvidence, SelectedSbcQuantities, require_quantity_reference, require_quantity_comparisons|
|heterogeneity_sbc_quantities.py|selected_sbc_quantities; selection, scalar/reference calls and ranks|

Task1 owns seeds and controls, including control record validation. Task2 owns
quantity records and orchestration and imports the public Task1 names. Controls
never import quantity types. `require_quantity_reference` is a structural return
boundary in the new quantity-types module; it is not a numerical reference
algorithm or a change/export added to the completed dependence module. There
are no private cross-module imports and no fifth production module.

## Exact public interfaces

All records below are frozen dataclasses. Literal domains are runtime checked;
all retained collections are tuples. Public scalar validation normalizes only
supported lossless scalar domains. No caller may fabricate scientific success
through a default field. Properties below are derived labels, not observations.

```python
# heterogeneity_diagnostic_seeds.py
@dataclass(frozen=True)
class DiagnosticSeedIdentity:
    case: SbcCaseId
    attempt_id: int
    purpose_id: Literal[5, 6, 7, 8]
    spawn_key: tuple[int, ...]
    @property
    def entropy(self) -> tuple[int, int, int, int, int, int, int, int, int]: ...
    @property
    def scalar_words(self) -> tuple[int, int, int, int] | None: ...
    @property
    def scalar_uint128(self) -> int | None: ...

# heterogeneity_sbc_controls.py
@dataclass(frozen=True)
class DiagnosticCallError:
    exception_class: str
    message: str

@dataclass(frozen=True)
class PriorControlFailure:
    chain: int
    parameter: Literal["mean", "rho"]
    reason: Literal["rng_exception", "invalid_scalar", "rounded_boundary"]
    sampled_mean: float | int | None
    sampled_rho: float | int | None
    returned_type: str | None
    error: DiagnosticCallError | None

@dataclass(frozen=True)
class PriorControlResult:
    seed: DiagnosticSeedIdentity
    pairs: tuple[tuple[float, float], ...]
    failure: PriorControlFailure | None
    @property
    def status(self) -> Literal["complete", "failed"]: ...

def draw_prior_control(*, seed: DiagnosticSeedIdentity) -> PriorControlResult: ...

# heterogeneity_sbc_quantity_types.py
@dataclass(frozen=True)
class ScalarQuantityEvidence:
    quantity_id: Literal[0, 1, 2, 3, 4]
    values: tuple[float, ...] | None
    error: DiagnosticCallError | None
    failed_training_row: int | None

@dataclass(frozen=True)
class QuantityRankEvidence:
    mode_id: Literal[0, 1, 2]
    quantity_id: Literal[0, 1, 2, 3, 4, 5]
    seed: DiagnosticSeedIdentity
    status: Literal[
        "ranked", "control_failed", "quantity_failed", "reference_failed",
        "dependence_reference_unresolved", "dependence_rank_order_unresolved",
        "comparison_failed", "rank_failed",
    ]
    rank: int | None
    comparisons: DependenceComparisons | None
    error: DiagnosticCallError | None

@dataclass(frozen=True)
class SelectedSbcQuantities:
    spec: FitAttemptSpec
    selected_indices: tuple[tuple[int, int], ...]
    selection_seeds: tuple[DiagnosticSeedIdentity, ...]
    control: PriorControlResult
    point_slots: tuple[int, ...]
    points: tuple[tuple[float, float], ...]
    scalar_quantities: tuple[ScalarQuantityEvidence, ...]
    reference: HeterogeneityDependenceReference | None
    reference_error: DiagnosticCallError | None
    ranks: tuple[QuantityRankEvidence, ...]
    @property
    def selection_method(self) -> str: ...
    @property
    def complete(self) -> bool: ...

def require_quantity_reference(
    reference: HeterogeneityDependenceReference,
    *, points: tuple[tuple[float, float], ...],
) -> None: ...

def require_quantity_comparisons(
    comparisons: DependenceComparisons,
    *, reference: HeterogeneityDependenceReference,
    truth_index: int, draw_indices: tuple[int, int, int, int],
) -> None: ...

# heterogeneity_sbc_quantities.py
def selected_sbc_quantities(
    dataset: GeneratedDataset, *, attempt: FitAttemptResult
) -> SelectedSbcQuantities: ...
```

The helper taking only a seed generates prior-control points; it makes no claim
that a fit was accepted and provides no posterior-selection route. Selection
exists only behind the main function's public dataset guard.

## Diagnostic identities

Use public `SbcCaseId` and `simulation_integer` from generation types. Validate
and reconstruct the case by its public constructor. Reject Boolean integers,
out-of-domain attempts, malformed spawn tuples and purpose/case mismatches.
Attempt is0/1. Track is the actual fitted case track0/1, never generation99.
Entropy is `(42,211,1,track,study,case,replicate,purpose,attempt)`.

| Purpose | Study | Spawn key | Consumer |
| --- | --- | --- | --- |
|5|0|`(chain,)`, chain0..3|draw selection|
|6|0|`(mode,quantity)`, mode0..2, quantity0..5|rank ties|
|7|0,1,2,4|`()`|later vector PIT; no prediction here|
|8|0|`(1,)`|four prior-only pairs|

For5/8 create PCG64 from the full SeedSequence entropy/spawn key, never a scalar
seed. For6/7 only, generate four uint32 words and assemble the exact Python int
`sum(int(word) << (32*i) for i,word in enumerate(words))`. Both scalar properties
are None for5/8. Direct key(c,) equals the declared spawn(4)[c] child; key(m,q)
equals spawn(3)[m].spawn(6)[q]. Deriving a seed object proves its namespace, not
that its RNG was consumed. No collision avoidance/reseeding or independence claim.

## Boundary and selection

Require valid GeneratedDataset, FitAttemptResult.status accepted, typed non-None
fit, and prior study0. Call `require_fit_identity(dataset, spec=attempt.spec,
fit=attempt.fit)` before any RNG construction, seed-state generation, selection
or quantity evaluation. Do not duplicate its shape/config/count/label rules.
Malformed callers and FitIdentityError propagate. Do not convert them into
realized quantity failures. On restored use the caller must repeat this guard;
constructor consistency alone cannot establish source or rowwise fit history.

In chain0..3 order, make one scalar `integers(0,spec.config.draws)` call in each
purpose5 stream, validate a non-Boolean integer in range, retain(c,d), and use
exact `mean_draws[c,d,0],rho_draws[c,d,0]`. Four chains may share d. No flattening,
thinning, posterior RNG, reselection or mixing initial/retry arrays. The label is
`one_uniform_postwarmup_draw_per_chain`. Selection invocation or malformed-return
failure propagates to the later execution ledger; it is not a retry condition.

## Prior control and retained prefix

`draw_prior_control` validates purpose8 identity before RNG construction. Use
one scalar meanBeta(1,1) then scalar rhoBeta(1,b), b9/4 by track, for c0..3.
Validate each scalar immediately; stop before subsequent calls on any failure.
Append a pair only after both values are finite and strictly interior. Cyclic
pairing requires no control RNG: `(correct[c].mean, correct[(c-1)%4].rho)`.

Use public `simulation_failure_scalar` to retain supported int/float evidence
losslessly, including nonfinite floats; use public `simulation_probability` and
strict-interior checking for acceptance. Unsupported values retain only their
actual qualified type and no invented numeric value. Constructor validation
uses NaN-aware comparisons where necessary without converting exact integers
to rounded floats. This is not a GenerationFailure or a purpose0 invocation.

| Control field/state | Exact requirement |
| --- | --- |
|complete|four valid interior pairs, failure None|
|failed|0..3 completed valid pairs, failure.chain=len(pairs)|
|mean failure|sampled_rho None; no later call happened|
|rho failure|sampled_mean is the accepted interior mean|
|rng_exception|actual DiagnosticCallError; failed parameter None; returned_type None|
|invalid_scalar, supported|failed parameter retains nonfinite or out-of-domain numeric scalar; error/returned_type None|
|invalid_scalar, unsupported|failed parameter None; actual nonempty qualified returned_type; error None|
|rounded_boundary|failed parameter is actual endpoint0/1; error/returned_type None|

`chain` is non-Boolean0..3. An invalid scalar must actually fail the supported
probability domain, not be an interior scalar or endpoint. Endpoint is its own
state. Rho failure never loses its earlier accepted mean. An actual exception
class is `type(error).__module__ + '.' + type(error).__qualname__`; message is
literal `str(error)`, allowed empty. Error/returned_type strings must be literal
strings with nonempty qualified class/type name (nonempty dot-separated parts),
not guessed from exception text. Constructors certify structure, not provenance.

## Canonical points and scalar calls

Slots0 truth,1..4 correct,5..8 complete prior control,9..12 cyclic. Store actual
Python float parameter pairs, strictly interior, preserving repeated points.
Complete control produces thirteen points and point_slots=tuple(range(13)).
Failed control produces exactly nine points and map `(0,1,2,3,4,9,10,11,12)`.
The failed control's prefix is retained only in its control record. No reference
placeholder or partial prior-control rank is allowed.

Compute all actual point vectors in this fixed order:

1. Quantity0 mean,1 rho,2 mean*rho.
2. Quantity3: one public `heterogeneity_log_mass(ac,an,mean=means,rho=rhos)`
   vector call for each of the sixteen training rows, in original order;
   accumulate in that order. Include AN0. Stop quantity3 after its first raised
   call exception, retaining its actual row index. No partial sum is quantity3.
3. Quantity4: one independent public call for AC0/AN20, even if quantity3 failed.
4. One public `heterogeneity_dependence_reference(counts,mean_prior=(1.,1.),
   rho_prior=(1.,b),points=points)` call with all sixteen ordered counts and
   all actual points. Reference independence does not depend on3/4 success.
5. Visit modes0,1,2 then quantities0..5; resolve eligibility, comparisons and
   ranks. Use actual scalar vectors for0..4. For5 only resolved public
   comparisons allow `randomized_rank(0,comparisons.comparisons,seed=...)`.

No production scorer, heldout count use, separate evidence computation, thirteen
reference calls or updated quadrature order. A reference executes its existing
64/128/256 orders once internally. Successful complete execution has16 training
calls, one future call, one reference call, three comparisons and18 ranks.

## Returned-value validation outside invocation catches

Catch ordinary Exception only around actual beta/oracle/comparison/rank calls.
Preserve actual class/message. Never catch BaseException, selection failures,
constructor defects or return validation as scientific call failures. A malformed
return raises ValueError outside the catch without making DiagnosticCallError.
Independent subsequent stages continue only for an actual retained call failure;
a malformed-return/programming defect aborts to the outer execution ledger.

Log-mass returns must be np.ndarray, dtype exactly float64, shape exactly(P,),
P=len(points), with every element finite. Reject scalar, list, Boolean/object,
complex/other-precision dtype, wrong dimension/length, NaN and infinity. Validate
before arithmetic/conversion; do not reshape, broadcast or cast malformed data.
The accumulated training vector must remain finite; overflow outside the call
is an arithmetic defect that propagates, not an invented oracle exception.

`require_quantity_reference` structurally validates a returned typed reference
outside any call catch and is reused by SelectedSbcQuantities construction:

- actual HeterogeneityDependenceReference; immutable tuple orders exactly
  non-Boolean integers(64,128,256); literal bool analytic_separability;
- reference.points is a tuple of exactly P actual DependencePointReference;
  each mean/rho is a supported binary64-or-narrower floating scalar, interior,
  exactly matching the corresponding expected point without approximate equality;
- components is a tuple of three tuples of four finite supported float scalars;
  raw_values is a tuple of three finite supported float scalars;
- value/error_bound finite supported float scalars, error_bound>=0; resolved is
  literal bool. Retain actual objects unchanged; no synthetic component values.

This duplicates no convergence/order guard: it checks representation, finiteness
and input binding only. It does not assert or repair component arithmetic,
separability, gaps, error-bound adequacy or invocation history. The unchanged
public dependence_comparisons remains the sole numerical ordering decision.

Comparison returns must be actual DependenceComparisons with literal status
`resolved`, `dependence_reference_unresolved` or `dependence_rank_order_unresolved`.
comparisons_by_order is immutable3x4 tuple with non-Boolean integer signs-1/0/1.
Resolved requires immutable four-sign comparisons; unresolved requires None.
Keep raw order-major signs and resolved signs unchanged. The public
require_quantity_comparisons helper owns structural comparison validation and
exact raw-sign binding to the supplied reference. Execution calls it before
the h rank; the enclosing result calls the same helper for restored/constructor
use. It validates the typed reference's representation through
require_quantity_reference, requires four distinct non-Boolean in-range draw
indices differing from the in-range truth index, and compares all three raw
sign rows exactly. A private comparison-structure helper inside the types module
is shared with individual rank constructors. Neither the representation check
nor the raw-sign calculation is duplicated in the orchestration module.
This does not reimplement the numerical guard or assert a mocked reference is
scientifically authentic. Wrong-type/shape/status/sign returns propagate
ValueError before their h rank invocation.

Rank returns must be non-Boolean Python/NumPy integer0..4, normalized losslessly
to int. Reject floats, bools and out-of-range integers outside its call catch.
No rank result is recomputed in result constructors.

## Immutable result states

Scalar entries are exactly0..4. Successful values are tuples of finite Python
floats, length P, error and failed row None. Failed entries only permit3/4,
values None, actual DiagnosticCallError; row0..15 mandatory only for3, None
for4. Zero likelihood contributions do not mean unavailable rows were measured.

Reference/reference_error is an exact exclusive pair: actual validated returned
reference with no error, or None with actual error. A returned unresolved
reference is retained as a reference. Preserve each point's components, raw h,
actual value, error_bound and resolved flag; adjacent gaps follow from raw h.

Ranks contain exactly18 entries in mode-major, then quantity order. Purpose6
identity matches spec and entry mode/quantity. Missing ranks still retain their
planned identity; this is not a claim the tie RNG was consumed. Resolve status
precedence: control failure for mode1, then unavailable scalar/reference, then
comparison result or comparison failure, then actual rank result or failure.

| status | rank | comparisons | error | permitted dependency |
| --- | --- | --- | --- | --- |
|ranked|int0..4|None for0..4; resolved for5|None|actual rank call returned|
|control_failed|None|None|None|only mode1 and failed control|
|quantity_failed|None|None|None|quantity0..4 parent scalar failed; control available|
|reference_failed|None|None|None|quantity5 parent reference failed; control available|
|dependence_reference_unresolved|None|matching returned status|None|quantity5, returned reference|
|dependence_rank_order_unresolved|None|matching returned status|None|quantity5, returned reference|
|comparison_failed|None|None|actual error|quantity5, returned reference|
|rank_failed|None|None for0..4; resolved for5|actual error|available scalar or resolved comparison|

Individual rank constructors enforce type/domain/field states. The enclosing
SelectedSbcQuantities constructor additionally enforces all parent dependencies,
study0 FitAttemptSpec, exact spec-matching seeds, chain0..3 selection index order
and bounds, exact point map, all interior pairs, fixed cyclic pairing, complete
control point equality, q0/q1/q2 exact equality to points/products, scalar lengths,
reference input binding, reference/comparison raw-sign binding and exact18-entry
ordering. It does not have dataset/fit arrays and cannot assert sampled indices
really produced correct/truth points. That evidence comes from guarded execution.
Use public constructor validation for nested records, never mutate or trust a
malformed instance merely because its outer class matches.

selection_method is exactly `one_uniform_postwarmup_draw_per_chain`.
complete is true only if all18 entries are ranked and control is complete; it
means local computability, not statistical success. Failures preserve completed
cheap quantities and available correct/cyclic results. Control failure cannot
count as detected control. No unresolved h rank, approximate tie, favorable
subset denominator, resampling, retry or success gate appears in this unit.

## Acceptance and handoff

Tests construct valid sixteen-row study0 metadata with AN
`(0,1,2,5,10,20,40,64)*2`; no bypassed constructors or AN1 toy masquerading as
generated prior data. Independent Fraction beta-binomial products at literal
rational points establish scalar values. Clearly labeled mock references test
states/call order, not real mixed-count separability. One actual-reference
integration accepts the existing guard's actual resolved/unresolved result;
it is not a second accuracy oracle or an empirical witness search.

Record the scope and synthetic/mock/actual-reference distinction in
`docs/research/population-heterogeneity-sbc-quantities-2026-09-10.md`. The evidence
note reports commands and outcomes actually run, without planned results presented
as facts. No renderable observation/surface/burden layer is added by this unit.
Focused tests and smoke are mandatory after implementation; full CI commands
and privacy/staged-path checks apply before PR/commit/push per AGENTS.md.
