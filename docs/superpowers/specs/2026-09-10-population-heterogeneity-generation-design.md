# B0H independent synthetic-generation design

Advances #211 and #189; implements Atlas design §§5,7–8,12 and the Study
definition of `2026-09-10-population-heterogeneity-sbc-design.md`.
This freezes the generator, not the sampler runner or an executed calibration study.

## Scientific contract

1. Objective: produce known-truth synthetic allele counts independently of the
   fitted likelihood, including deliberately dependent and boundary cases.
2. Evidence: exact case/seed identities, independent literal NumPy constructions,
   controlled RNG-call fixtures, analytic marginal/covariance identities, and
   explicit generation failures. Unit tests are not sampler-calibration evidence.
3. Component: pure `genomeos.validation.heterogeneity_simulation` sampling and
   its `heterogeneity_simulation_types` case/result contracts. The original
   facade exposes immutable objects and `generate_sbc_case(case)` to the later
   offline runner. No fitting, scoring, storage or scheduling responsibility.
4. Assumptions/refusals: pinned float64 NumPy/PCG64 execution of the declared
   laws. No redraw, clipping, easier seed, success-only output, hidden partial
   dataset, geographic claim or changed study denominator.

## Binding constraints

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

Generation imports NumPy and its public case/result contracts; the contracts
consume public `ReferenceCount`, not production likelihood, fitter, predictor,
rank or quadrature helpers. There is no arbitrary truth/prior/AN/seed/RNG
override on the public generator. No circular imports or private cross-module
imports: validated contracts point inward, sampling depends on them.

### Module-size refinement before implementation completion

The first readable single-module draft reached about610 logical lines/37KiB.
Split validated identities/results from sampling rather than compress validation
to reach the500-line target. `heterogeneity_simulation` explicitly re-exports
the original public API; supporting scalar/metadata helpers remain in the types
module and are shared by constructor validation and sampling. This changes no
scientific rule, random call order, seed, result field or facade signature.

After the split, readable constructor and joint-result validation still requires
about623 logical lines in the types module, while sampling is about403. Retain
this cohesive contract file as a documented exception to the preferred500-line
target, below the800-line/50KiB hard gate. A third module would separate result
types from their defining cross-field validation and add another import boundary;
neither dropping checks nor compressing formatting is acceptable. Record the
actual final size in the evidence note and the rationale in the module docstring.

Supporting typed interfaces in `heterogeneity_simulation_types`:

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

The integer helper normalizes exact non-Boolean integers; callers enforce their
individual bounds. Probability and failure-scalar helpers enforce the exact
numeric domains below; the latter retains actual nonfinite scalar evidence and
does not turn unsupported objects into values. Local sampling code can leave
unsupported offending objects absent. Truth/AN helpers validate the supplied
case before applying its closed decoding; prior/structural fixed truth is None.
The row helper requires a valid generation identity, `where` exactlytrain or
heldout, canonical string row0..15 or the case's permitted heldout kind, the
corresponding declared AN, and valid integerAC. Study3 has no heldout kind.
Generation-only provenance assembly and nullable offending-evidence wrappers
remain private to sampling; no generic factory or registry is introduced.

## Cases, identities and seeds

Protocol `b0h_sbc_v1`, generation algorithm `b0h_generation_v1`.
Case enumeration is `(study_id, case_id, replicate_id, track_id)` order, fit
tracks0,1 innermost. Domains and counts are fixed:

| study | case | replicate | training AN | track-specific records |
| --- | --- | --- | --- | --- |
|0 prior|0|0..511|mixed|1024|
|1 fixed|0..23|0..15|decoded below|768|
|2 shared history|0..3|0..15|mixed|128|
|3 unavailable|0|0|sixteen0|2|
|4 boundary|0..1|0..3|sixteen20|16|

Mixed AN is `(0,1,2,5,10,20,40,64)*2` in that order. Fixed case is
`((mean_index*4)+rho_index)*2+an_index`, means `(.001,.05,.5)`, rhos
`(0.,.0001,.1,.5)`, AN choices `(mixed,sixteen20)`. Shared case is
`mean_index*2+rho_index`, means `(.01,.5)`, rhos `(.1,.5)`. Boundary
case0/1 has mean0/1 and rho0. Prior track0 has meanBeta(1,1),rhoBeta(1,9);
track1 has meanBeta(1,1),rhoBeta(1,4). No prior selection is performed.

There are1938 records and1936 eligible initial fits. Both fit tracks share
stress generation (generation track99); prior generation uses its fit track.
Canonical fit ID is `b0h_sbc_v1:s{study}:c{case}:r{replicate}:t{track}`;
generation ID replaces the suffix with `g{generation_track}`.

For generation ID G, labels are literal synthetic metadata:

```text
variant_id = synthetic:{G}:variant:0
train record_id = synthetic:{G}:train:row:{i}
train group_id = synthetic:{G}:train:group:{i}
heldout record_id = synthetic:{G}:heldout:row:{kind}
heldout group_id = synthetic:{G}:heldout:group:{kind}
region_id = synthetic_nonspatial
variant_group = synthetic_single_variant
```

Training i is0..15; kind is `fresh_population`, `shared_cluster0`, or
`fresh_cluster`. Shared heldout has its own record/group, with cluster dependence
separate and explicit. Paired fits share generation row IDs, not independent
replicates. No P0 coordinate or radius is invented.

Entropy is `(42,211,1,track,study,case,replicate,purpose,attempt)`. Purposes0..3
are truth, population frequency, training count, heldout; use generation track
and attempt0. Purpose4 is fitting; use fit track and attempt0/1. No fit seed
exists for study3. Generation helper rejects other purposes/attempts;5..8 and
null track100 remain reserved for the runner as in the parent spec.

Each used stream is a fresh
`Generator(PCG64(SeedSequence(entropy)))`. Do not collapse generation entropy
to uint32 or spawn from shared mutable state. Only fitting uses
`int(SeedSequence(entropy).generate_state(1,dtype=np.uint32)[0])`, retained
alongside entropy. Provenance includes four planned namespaces0..3 even if
some make zero draws; it does not describe these as four consumed streams.

## Public result contract

All dataclasses are frozen. Collections are normalized immutable tuples;
constructors validate their domains and joint relationships. The actual typed
fields and public signatures are frozen in the implementation plan. Required states:

- `SbcCaseId`: valid fit-track/study/case/replicate and canonical ID.
- `GenerationId`: same domain but track0/1 only for study0,99 otherwise.
- `SeedIdentity`: validated nine-integer entropy, optional calculated fit_uint32.
- `ParameterTruth`: finite mean in[0,1], rho in[0,1); endpoint mean only at rho0.
- `GenerationProvenance`: matching generation identity and four ordered planned
  seed identities; fixed protocol/algorithm/PCG64/float64 labels.
- `SharedHistory`: two cluster frequencies, sixteen candidate frequencies and
  sixteen Boolean switches. Training cluster assignment is exactly i//8.
- `HeldoutTarget`: kind, ReferenceCount, latent q and explicit optional cluster,
  candidate and switch metadata. Ordinary targets have no cluster metadata;
  shared/fresh-cluster IDs are0/2 and q agrees with its selected source.
- `GeneratedDataset`: planned case, provenance, truth, sixteen training rows,
  sixteen actual q including AN0, optional shared history, one ordinary or two
  shared heldouts, raw-latent Beta endpoint counters. Status `available`.
- `AllUnavailableDataset`: study3 case, provenance and sixteen AN0/AC0 rows;
  status `all_unavailable`, reason `no_available_training_counts`, truth/latents/
  shared history None, heldouts(), expected_sampler_calls0.
- `GenerationFailure`: case/provenance, stage/index, coded reason, validated
  truth if known, actually sampled scalar mean/rho candidates if present,
  offending numeric scalar if one exists, optional exception class/message.
  Status `generation_failed`; no returned partial training or heldout arrays.

Integer domains reject Python/NumPy Booleans, floats and out-of-domain integers;
normalize accepted NumPy integers to Python int. Successful scalar probabilities
are finite Python or NumPy binary64-or-narrower floats or exact0/1 integers;
other domains are refused rather than silently rounded into valid endpoints.
No generic `float()` acceptance of arbitrary Real or non-scalar arrays.
Failures may retain actual NaN/infinity scalar evidence, not invented values;
the later artifact adapter must encode these with explicit tags, not invalid JSON.
Malformed caller inputs raise ValueError, not a synthetic realization failure.

Cross-object validation checks identity agreement, fixed case truth/AN, prior
interior truth, exact row labels/lengths, valid AC/AN and q, expected heldout kinds,
shared selected q and B0 reuse, and endpoint counters. Counter values equal the
number of0/1 values among all retained raw latent draws: ordinary training/heldout
q for rho>0, or shared B/V including unselected candidates and heldout draws.
Prior truth and rho0 fixed values are excluded. All unavailable carries no counters
because there are no latent draws. No source/environment hash is fabricated here.

## Exact arithmetic and random-call order

Every call is scalar, `size` omitted; validate each result before further use.

1. Study3 returns before RNG construction, parameter or shape work. It is an
   explicit exception to the parent sentence about every independent case having
   a heldout: this is a structural-refusal fixture, not a parameter-drawn dataset.
   It has no coverage/PIT/h/control eligibility and never enters a fitting
   denominator. A later adapter tests public refusal with zero sampler calls.
2. Prior stream0 draws meanBeta(1,1), then rhoBeta(1,9) orBeta(1,4). After a finite
   valid real mean candidate, draw rho even if mean is0/1, then check both strictly
   interior. A first invalid nonfinite/nonscalar/exception ends the case immediately.
   Fixed studies obtain literal truth and make no truth-stream draws.
3. Interior truth: float64 `kappa=(1.0-rho)/rho`, `a=mean*kappa`,
   `b=(1.0-mean)*kappa`, in order. Require finite positive kappa,a,b. Underflow
   to a zero shape and overflow fail; no floor/alternate formula/approximation.
4. Ordinary stream1 draws16 Beta(a,b) q values, including AN0 rows. At rho0 use
   mean16times with no Beta shape work or stream1 draws.
5. Shared stream1 visits clusters j0then1. Draw BjBeta, then for each of its eight
   rows ViBeta then Ui.random(); select Bj iff Ui<sqrt(.5), otherwise Vi. Always
   draw unused Vi. Complete both clusters before any training count.
6. Stream2 draws16 Binomial(ANi,qi), including Binomial(0,qi), in training order.
7. Ordinary heldout stream3: Beta q if rho>0, otherwise literal mean; then
   Binomial(20,q). Kind `fresh_population`, no cluster metadata.
8. Shared heldout stream3: first VBeta,Urandom, select against retained B0, then
   Binomial20 (kindshared_cluster0,id0). Then B2Beta,V2Beta,U2random, select B2/V2,
   then Binomial20 (kindfresh_cluster,id2). All these draws are independent
   within their stream's prescribed sequence; neither heldout is a new dataset.

Beta population/candidate output accepts machine endpoints0/1 and counts them;
out-of-domain/nonfinite/Boolean/nonscalar output fails. Prior truth endpoints
fail despite latent endpoints being valid. Uniform output is finite[0,1), so
threshold equality selects V. Binomial output must be a non-Boolean integral
scalar0..AN. Boundary means still call Binomial, giving deterministic0orAN.
NumPy's finite-precision Beta sampler is not claimed mathematically exact.

## Failure accounting

Stages: `truth_mean`, `truth_rho`, `truth_validation`, `beta_shapes`,
`training_cluster`, `training_population`, `training_switch`, `training_count`,
`heldout_cluster`, `heldout_population`, `heldout_switch`, `heldout_count`.
Index is None for truth/shapes, cluster0/1 for training_cluster, row0..15 for
training population/switch/count, heldout0/1 for heldout stages. Fixed ordinary
heldout has index0. Record reason `rng_exception`, `invalid_rng_scalar`,
`rounded_prior_boundary`, or `invalid_beta_shapes` at its explicit origin.

Catch ValueError/FloatingPointError/OverflowError only around individual RNG calls
or shape arithmetic, retaining class/message. No blanket function exception
handler or error-message substring classification. Unexpected RuntimeError,
MemoryError or process loss remains a runner unresolved exception, not a redraw.

After validated truth retain it even if the first population draw fails. Before
truth validation retain only the scalar candidates actually returned. Never
invent a missing candidate, recover values from an exception string, promote a
partial count array or fill a failed result with zeros/NaNs. The generator has
no retry or successful-subset mechanism.

## Acceptance evidence and interpretation

Literal identities/seeds and case decoding; independent literal PCG64 construction
for one interior fixed case and one prior case; recording fake RNGs for shared
history and boundary/structural paths; all failure stages/types; paired-track
identity and order independence; immutable result and malformed-constructor
checks. The plan freezes exact fixtures before code. No model fits or full study
generation are required by this unit.

For shared history, s=sqrt(1/2), latent variance sigma²=m(1-m)rho:
Qi has mixture CDFsF+(1-s)F=F, and Cov(Qi,Qj)=s²sigma²=sigma²/2 within
a cluster. Conditional independent Binomial counts give covariance
ni*nj*sigma²/2, marginal variance ni*m*(1-m)*(1+(ni-1)*rho). Count correlation
is not generally1/2 and is undefined for AN0. Fresh-cluster heldout has no shared
training source; cluster0 heldout shares only B0.

Literal m=1/2,rho=1/2,n=2 anchor: latent variance1/8,covariance1/16;
marginal AC probabilities(3/8,1/4,3/8); AC variance3/4,covariance1/4,
correlation1/3. Fraction arithmetic and controlled source-selection tests establish
this construction without using the fitted/scoring law or Monte Carlo estimates.

These tests support the generator contract, not a sampler passing claim, human
demographic realism, biological independence, geographic validity or real-data
performance. The frozen runner, actual calibration and negative controls remain
separate required work before real B0H comparison.
