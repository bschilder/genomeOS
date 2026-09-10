# B0H simulation-calibration validation design

Advances #211 and #189, Atlas design §§5,7–8,12. This extends the approved
`2026-09-10-population-heterogeneity-design.md` pre-real-data contract. The
owner authorized continued implementation and delegation without routine
approval. CuGen and real-data access are not prerequisites.

## Scientific contract

1. Claim: the actual B0H computation respects its declared posterior and
   marginal predictive law across independently simulated datasets, with
   demonstrated sensitivity to ignored counts and destroyed parameter pairing.
2. Evidence: independently anchored numerical quantities, discrete rank tests,
   explicit negative controls, every planned outcome, and separately labeled
   boundary/shared-history stress. Non-rejection is not equivalence, geographic
   validity, or worldwide allele-frequency accuracy.
3. Components: pure simulation, dependence-reference and rank/null functions;
   a later immutable offline study adapter calls the public fitter/predictor.
   No serving inference, real inputs, new dependencies or production-schema change.
4. Assumptions/refusals: independent simulated datasets are the units. Four
   independently seeded finite-run chains only approximate posterior draws.
   Retain generator, sampler, prediction, reference and rank-order failures.
   Never redraw a truth, clip a draw, shrink the study, loosen a gate, or select
   favorable seeds after inspecting results.

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

## Study definition, before actual execution

Protocol identifier `b0h_sbc_v1`. Prior track0 is meanBeta(1,1),rhoBeta(1,9);
track1 is meanBeta(1,1),rhoBeta(1,4). Report separately, never select a winner.
Mixed training AN is `(0,1,2,5,10,20,40,64)` twice. Fit each dataset as one
variant independently, with four chains,500draws,1000tune,target_accept0.9.
Exactly one convergence-error-only retry doubles draws and tune and uses a
different predeclared seed; retain both attempts. Numerical/structural failures
do not retry. Mean/rho Rhat<=1.05, bulk/tailESS>=200 and zero divergences stand.

Enumerate these stable identities in `(study_id,case_id,replicate_id,track_id)`
order, including all-unavailable fixtures:

| Study | ID | Cases in declared nested-loop order | Repeats | Tracks | Fits |
| --- | --- | --- | --- | --- | --- |
| Prior SBC |0|one case; draw truth from its track prior|512|0,1|1024|
| Fixed stress |1|mean(.001,.05,.5), then rho(0,.0001,.1,.5), then AN(mixed,sixteen20s)|16|0,1|768|
| Shared-history stress |2|mean(.01,.5), then rho(.1,.5); mixed AN|16|0,1|128|
| All-unavailable |3|sixteen AN0/AC0|1|0,1|0|
| Exact boundary |4|mean0 then mean1, rho0, sixteen20s|4|0,1|16|

There are1938 planned track-specific records and1936 initial fits; at most1936
convergence retries. Paired prior fits share stress data but are not independent
replicates. Boundary repeats are degenerate count cases, not extra information
about data variation. Stress cellN16 is descriptive, not an equivalence test.

Seeds use NumPy `SeedSequence([42,211,1,track_id,study_id,case_id,replicate_id,
purpose_id,attempt_id])`. Purpose IDs:0truth,1population frequencies,2training
counts,3held-out generation,4fit,5draw selection,6rank ties,7predictive PIT,
8negative controls. Generation always uses attempt0. Common stress generation
uses track99, independent of fitted prior; fitting uses track0/1. Initial fit
attempt0 and retry1 are distinct. Fit seeds are one generated uint32, retained
with the full entropy identity. Null entropy is `[42,211,1,100,0,0,0,0,0]`.
Quantity/control substreams, adapter/resume records and actual performance
measurement must be frozen in the runner plan before any study executes.

Interior generation independently samples Beta population frequencies then
NumPy Binomial counts; it never calls the fitted graph, count scorer or
predictive sampler. Rho0 uses exact Binomial generation at fixed mean.
Boundary mean0/1 is allowed only with rho0. Preserve AN0 rows. Every independent
case has one fresh-population held-out AN20 count. Shared-history cases have
two separately identified held-outs, one sharing cluster0, one fresh cluster.

Shared-history construction: two independent clusters, one per eight-row block.
Draw cluster B and each population V from the same Beta(mean*kappa,(1-mean)*kappa).
Each population uses B with probabilitysqrt(.5), otherwise V. Counts are
Binomial conditional on these frequencies. This preserves the Beta marginal
and gives within-cluster latent correlation.5. Shared and fresh held-outs use
their own independent switch/V/count draws; they are not independent datasets.

## Rank selection, quantities and decisions

Select one postwarmup draw uniformly and independently from each chain using
its own selection stream. Reuse the four paired mean/rho indices for every
quantity. No within-chain flattening, value-dependent selection or concatenation
of initial/retry draws. Label `one_uniform_postwarmup_draw_per_chain` explicitly.
Retain full arrays and mandatory diagnostics. Full-chain h ESS/MCSE is
`not_computed` unless actually evaluated; one selected point is not an ESS estimate.

Six quantities: mean, rho, mean*rho, independent training log likelihood,
independent futureAN20 logP(AC0), and posterior dependence log density ratio h.
Truth and all draws use the same observed training dataset for data-dependent
quantities. Literal ties randomize uniformly among tied rank positions:
number strictly less plus UniformInteger(0,number exactly tied). Four draws
give ranks0..4. Approximate equality must not be turned into a tie.

For counts c of the five ranks, use integer
`T=max(abs(5*cumsum(c)[k]-N*(k+1)) for k in range(4))`.
Generate100000 multinomial null histograms with N512 and five probabilities.2
using the frozen null stream. Inclusive plus-one p-value is
`(1 + count(null_T >= observed_T))/100001`. Twelve correct-run tests use
alpha.05/12; retain raw and Bonferroni-adjusted p-values. No continuous-KS null.
Exact exhaustive anchors: N1 gives{2:1,3:2,4:2}; N2 gives{2:2,3:6,4:9,6:6,8:2}.

Prior-only control uses four independent pairs from its declared prior and
must reject in training log likelihood for both tracks at.05/12. Cyclic pairing
loss pairs mean[c] with rho[(c-1)%4] and must reject in h for both tracks at
the same threshold. Keep all other quantities. Four control assertions have
their own stated budget; a missed control limits sensitivity, not evidence
that the correct fitter failed. No post-result witness search is allowed.

Passing requires all planned SBC datasets accounted for without unresolved
outcomes, no rejection in the twelve-test family, and both controls detected
for both priors. Say only “no discrepancy detected at this design's resolution.”
Failures preclude an unconditional claim. Conditional plots retain actual N,
failure counts and correct-N nulls; they cannot rescue the full study.
Predictive PIT,50/80/95% coverage/width, parameter coverage/width, proper scores
and errors are secondary descriptive outputs, not additional success gates.

## Independent continuous dependence reference

For independent priors and likelihood L, evidence Z:

```text
h(m,r) = log L(m,r) + log Z
         - log integral[L(m,r') pi_r(r') dr']
         - log integral[L(m',r) pi_m(m') dm'].
```

This is our algebraic diagnostic construction, not a new fitted model. Use
the independent finite-product `heterogeneity_log_mass` and validated
Beta-weighted quadrature. Never use production likelihood/scoring helpers,
nearest-grid substitution, or an estimated correlation as h.

Counts AN<=64, quadrature orders64/128/256. Evaluate all actual parameter pairs
at every order. Retain four component log terms, raw h and both adjacent gaps.
Require finite values and both pointwise gaps<=1e-6. Points are finite scalars
with mean/rho strictly inside(0,1); preserve input order and repeated points.
Bounds here apply only to this new quantity, not existing quadrature thresholds.

At each point, numerical guard:

```text
b=max(abs(h128-h64), abs(h256-h128),
      64*eps64*max_order(1+sum(abs(four component log terms))))
```

For each draw-vs-truth comparison, its less/equal/greater sign must match at
all three orders, and a strict highest-order contrast must exceed b_draw+b_truth.
Retain the individual comparison vector; aggregate ranks alone cannot detect
cancelling ordering mistakes. An unexplained equality, near contrast, changing
sign or failed point is unresolved, not a tie or permission to increase order.
These are empirical guards, not rigorous quadrature-error bounds.

Closed exact-separability predicate: every count is AN0/AC0, AN1/AC0 or1, or
AN2/AC1. If s/f are AN1 successes/failures and t is AN2/AC1 count, then
`L=2**t*m**(s+t)*(1-m)**(f+t)*(1-r)**t`. Independent priors give h=0 exactly.
Use literal0 with `analytic_separability`, but retain and check raw quadrature
h at every point/order against zero<=1e-6. Empty data are an oracle-only anchor,
never a prior-only fitting fallback. Identical parameter inputs are also exact
ties; no other equality is declared analytic by this protocol.

Independent nonseparable anchor: one count AC0/AN2 gives
`L=(1-m)*((1-m)+m*r)`. With uniform priors Z=5/12,
fixed-m integral=(1-m)*(1-m/2), fixed-r integral=(2+r)/6.
At points(1/4,1/4),(3/4,3/4),(1/4,3/4), exp(h) is respectively
65/63,13/11,75/77. With meanBeta(2,3),rhoBeta(3,2), Z=13/25,
fixed-m integral=(1-m)*(1-2*m/5), fixed-r integral=(2+r)/5;
exp(h) is169/162,169/154,65/66 at the same points. Test each component,
not only the ratio; verify complements separately.

## Evidence provenance and implementation scope

Primary-text readings and caveats are in the committed calibration-methods
note. The bounded scratch design compared two fixed approximate-posterior
corpora, not independent actual fitter studies. Five initial quantities missed
most cyclic-pairing controls; the single logged h refinement detected125/128
and128/128 conditional realizations. Those are conditional design results,
not confirmed unconditional power or actual sampler calibration. Preserve weak
and improved probes and the choice chronology in the study evidence note.

The first implementation plan covers pure reference/rank primitives only;
the next units add generation and the runner. It does not launch1936fits or
claim benchmark admission. The later runner
must snapshot protocol/source/environment identities, enumerate all cases,
retain every attempt, resume matching immutable records without overwriting,
and distinguish infrastructure restart from scientific retry. Measure an
explicit small scheduling/JIT workload before choosing task-owned US/CA pods.
Only synthetic data and reviewed public code may be sent there; collect
artifacts and delete task-owned pods when finished.
