# B0H predictive and parameter summaries — design

Status: personally self-reviewed and adopted for the owner-authorized implementation.
Advances #211/#189 and Atlas design §§5,7–8,12. The parent authority is
`docs/superpowers/specs/2026-09-10-population-heterogeneity-sbc-design.md`;
the accepted-fit boundary is the sibling attempts design. Only public
`DiagnosticSeedIdentity` and `DiagnosticCallError` from the selected-quantity
design are reviewed dependencies; this unit does not execute selected quantities.

## Scientific contract

1. Claim: an accepted, dataset-bound B0H fit yields explicitly aligned held-out
   count diagnostics and separate summaries of its full mean/rho posterior.
   This is adapter correctness, not actual calibration, spatial validity or
   worldwide improvement.
2. Acceptance: literal valid constructed datasets/fits, independent scalar and
   linear-quantile anchors, an actual public predictor/scorer integration,
   asymmetric two-target alignment, retained actual failures, and identity
   refusal before diagnostic work or seed-state creation. No NUTS execution.
3. Component: pure offline `summarize_heterogeneity_fit(dataset, *, attempt,
   cdf_backend)` consuming `GeneratedDataset`, accepted `FitAttemptResult`, and
   an explicit `Literal["scipy", "cupy"]`; immutable records in a second module.
4. Assumptions/refusals: studies 0,1,2,4 only. Study 3 has no fit, truth or heldout.
   The unchanged public `require_fit_identity` runs before summary work/RNG.
   No clipping, new fits, regenerated inputs, resampling, retry or fallback.
   Downstream artifact/study adapters retain arrays and execution defects;
   this unit performs no I/O, serialization, checkpointing or study reduction.

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
- No full study, actual NUTS fit, seed search, resource launch or external data operation.

## Chosen boundary and alternatives

Use two narrow modules, `heterogeneity_summary_types.py` for immutable records
and shared returned-value checks, and `heterogeneity_summaries.py` for guarded
orchestration. A single module would mix record restoration rules with call
flow; a generic diagnostic registry would introduce unnecessary indirection.
Architecture and scientific method were already chosen by root; these are
implementation-boundary tradeoffs, not a reopening of the model.

The one public entry point returns `HeterogeneityFitSummary`. Parameter evidence
has no predictive status dependency. Actual ordinary exceptions from prediction
or diagnostics return a failed predictive component and completed parameters.
Malformed returns, parameter arithmetic defects, malformed callers, identity
errors and BaseException propagate to the later execution ledger. A propagated
defect does not promise a partial returned summary or durable checkpoint.

## Public typed records and interface

All records are frozen dataclasses; all retained sequences are tuples. The plan
contains complete declarations, constructor checks and implementations.

| Public type | Fields / meaning |
| --- | --- |
| `ParameterPosteriorSummary` | `parameter: Literal["mean","rho"]`, `truth: float`, `estimate: float`, `quantiles: tuple[float,...]`, `draw_count: int`; properties `absolute_error`, `squared_error`, `coverage: tuple[bool,bool,bool]`, `interval_width: tuple[float,float,float]` |
| `HeldoutPredictiveSummary` | `target: HeldoutTarget`, `log_score: float`, `absolute_error: float`, `squared_error: float`, `coverage: tuple[bool,bool,bool]`, `interval_width: tuple[float,float,float]`, `randomized_pit: float` |
| `PredictiveSummaryEvidence` | `seed: DiagnosticSeedIdentity`, `seed_words: tuple[int,int,int,int]`, `seed_uint128: int`, `cdf_backend: Literal["scipy","cupy"]`, `draw_count: int`, `targets: tuple[HeldoutTarget,...]`, `status: Literal["complete","prediction_failed","diagnostics_failed"]`, `prediction: ReferenceHeterogeneityPrediction | None`, `rows: tuple[HeldoutPredictiveSummary,...]`, `error: DiagnosticCallError | None` |
| `HeterogeneityFitSummary` | `spec: FitAttemptSpec`, `variant_id: str`, `parameters: tuple[ParameterPosteriorSummary,ParameterPosteriorSummary]`, `predictive: PredictiveSummaryEvidence`; properties `h_ess_status` and `h_mcse_status` are exactly `"not_computed"` |

Public functions:

```python
def summarize_heterogeneity_fit(
    dataset: GeneratedDataset, *, attempt: FitAttemptResult,
    cdf_backend: Literal["scipy", "cupy"],
) -> HeterogeneityFitSummary: ...

def require_summary_prediction(
    prediction: ReferenceHeterogeneityPrediction, *,
    targets: tuple[HeldoutTarget, ...], cdf_backend: Literal["scipy", "cupy"],
    draw_count: int,
) -> None: ...

def predictive_summary_rows(
    frame: pd.DataFrame, *, targets: tuple[HeldoutTarget, ...],
) -> tuple[HeldoutPredictiveSummary, ...]: ...
```

The two returned-value functions belong to the records module; orchestration
imports only public names. They are representation/input-alignment boundaries,
not alternate scorers. No serializers, registries, private cross-module imports
or new science algorithms.

## Guard and parameter summaries

Check caller types, accepted state, typed non-None fit and backend. Call the
public dataset-bound identity guard once, before reconstructing diagnostic
records, deriving diagnostic seeds, calculating quantiles, or invoking prediction.
After the guard, validate supplied nested records through their public
constructors. The returned prediction is checked through the explicit shared
representation boundary below without copying its arrays. Do not copy the
guard's label, count, config or shape rules.

For the one fitted variant, consume every entry of `mean_draws[:,:,0]` and
`rho_draws[:,:,0]` for the accepted attempt, without mixing initial and retry
arrays. Compute `np.mean` and `np.quantile(..., method="linear")` at exactly
`(.025,.1,.25,.5,.75,.9,.975)`. The draw count is `4 * spec.config.draws`.
Retain seven finite, ordered, strictly interior quantiles and an interior mean.
Validate numerical return representation before conversion: mean is a finite
Python float or NumPy float64 scalar; quantiles are an actual float64 ndarray
of exact shape(7,) with finite values. A string, list, Boolean, object/complex/
other-precision array or malformed shape propagates as a defect, not a repaired
parameter estimate. Constructor probability/order checks then validate domains.
Absolute/squared error use this posterior mean estimate against the generated
mean/rho truth. Coverage is inclusive at quantile pairs `(2,4),(1,5),(0,6)`;
width is upper minus lower, in 50/80/95 order. Derived properties avoid
inconsistent duplicate error/coverage metadata.

All accepted draws contribute; they are not independent dataset replicates.
The fixed boundary truth mean 0/1 or rho 0 is retained unchanged. An interior
continuous posterior need not contain an endpoint atom: noncoverage in these
cases is a boundary-support stress fact, not an extra calibration failure gate.
Full-chain h ESS and MCSE remain `not_computed`.

## Prediction, PIT identity and alignment

Construct purpose7 from the actual fitted track 0/1 and attempt 0/1, supported
study 0/1/2/4, and `spawn_key=()`. Retain the seed identity, exact four uint32
words and their exact assembled Python uint128 scalar. The words and scalar
must equal the public seed properties. Neither their presence nor a planned
identity proves the PIT RNG was consumed. Diagnostics can fail before its RNG
line; no consumed/not-consumed guess is added.

Pass `tuple(target.row for target in dataset.heldouts)` in original order to
one public `predict_reference_population_heterogeneity` call with the explicit
backend. Require its exact typed returned prediction and typed `CountPredictive`,
original-order observation IDs, empty unavailable IDs, backend equality, and
float64 arrays of shape `(4 * draws, len(targets))`. Concentration is present,
finite and positive; mean is finite and interior. The representation checker
does not recompute predictive parameter arrays or claim invocation provenance.
The public prediction has no variant-label field. Variant binding therefore
comes from the unchanged dataset-bound fit guard and the declared heldout row
IDs and variant IDs; no invented prediction variant metadata is added. These
checks cannot establish array provenance or prove which predictor was invoked.

Then call `predictive_diagnostics(marginal, ac_vector, an_vector,
seed=seed_uint128)` exactly once. Vectors are original-order int64 counts and
denominators; heldouts all have AN20 by the public dataset contract. Never sort,
deduplicate, score separately, call `sample_counts`, condition on held-out latent
frequency, or introduce shared-cluster conditioning into the marginal model.

Study 2 targets are exactly `shared_cluster0`, then `fresh_cluster`, with their
full original `HeldoutTarget` values retained. Other studies use
`fresh_population`. Shared/fresh targets and paired prior-track fits remain
identified; neither is an extra independent dataset.

## Returned-value and state checks

`predictive_diagnostics` must return a DataFrame with unique columns exactly in
the existing public order: `log_score`, `absolute_error`, `squared_error`,
`coverage_50`, `interval_width_50`, `coverage_80`, `interval_width_80`,
`coverage_95`, `interval_width_95`, `randomized_pit`. Require a canonical
`RangeIndex(0,len(targets))`, no extra/missing row, and float64 numeric columns
with bool coverage columns. Reject object/complex/Boolean numeric columns,
NaN, malformed values and unexpected labels before conversion; never reset the
index or coerce a return into appearing valid.

Log score admits finite values <=0 and negative infinity, an explicit valid
zero-mass outcome. It rejects positive values, NaN and positive infinity. All
other numeric outputs must be finite in [0,1]; coverage values must be literal
or NumPy Boolean scalars normalized to bool. Coverage and width are nested
50/80/95. Do not recompute the scorer or demand exact attainability of nominal
discrete coverage. A future codec chooses how to encode negative infinity.

The predictive absolute error uses the predictive count median/AN; squared
error uses predictive mean frequency. Width/coverage concern discrete count
quantiles/AN, never latent-frequency posterior intervals.

| status | prediction | rows | error |
| --- | --- | --- | --- |
| complete | typed, aligned return | one row per original target | None |
| prediction_failed | None | empty tuple | actual predictor exception |
| diagnostics_failed | typed, aligned return | empty tuple | actual diagnostics exception |

Only an actual ordinary call exception yields `DiagnosticCallError`, with
qualified class and literal message (including an empty message). Catch only
around the invocation, never returned-value validation or record construction.
No partial DataFrame becomes partial successful rows. The retained prediction
on a diagnostics failure preserves the successfully returned immutable object;
later artifacts independently retain relevant arrays.
The cost is retaining the predictor's derived draw-aligned mean/concentration
arrays alongside the accepted fit arrays until the artifact consumer releases
them; no second copy is needed merely to check their representation.
Constructors enforce
states, tuple immutability, nested records, exact target labels/kinds, seed/spec
matching, parameter ordering and fixed-truth/variant/count alignment. They
certify structural consistency, not fit provenance or actual RNG consumption.

## Acceptance and handoff

The plan supplies literal sixteen-row fixtures with actual public constructors,
four chains of 500 or 1000 entries, no NUTS, and explicit synthetic diagnostic
numbers. A nonconstant all-draw grid independently anchors linear quantiles.
An actual integration uses constant mean .5/rho 1/3 draws. The intended analytic
beta-binomial has alpha=beta=1 and uniform counts 0..20; binary64 rho=1/3 yields
nearby shapes, not bitwise-exact integer concentration. The analytic anchor
gives log score `-log(21)`, count
quantiles `(0,2,5,10,15,18,20)` and widths `.5,.8,1.`. Study 2 uses AC2 and AC17
to catch row reversal; scalar PIT anchors use the independent uniform-count
CDF plus a declared vector stream. Tests distinguish these constructed fits
from actual sampler output. All numerical anchors set relative tolerance zero:
2e-15 absolute for parameter/error/width arithmetic, 2e-14 for concentration,
and 2e-12 for log score/PIT. These are new fixture checks, not a change to any
existing numerical/reference threshold. No timing/performance/calibration claim.

Record actual future implementation commands/outcomes and these limits in
`docs/research/population-heterogeneity-summaries-2026-09-10.md`. No renderable
product layer changes, so no map figure is required. Focused tests and smoke
follow implementation; full CI and privacy/staged-path checks precede PR and
commit/push. The runner, codec, failures ledger and full study remain separate.
