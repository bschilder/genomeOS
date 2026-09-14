# B0H: population-heterogeneity count comparison

Issue #211 advances #189 WP2 and the B0 end of WP4, Atlas design §§5, 7–8, 12.
The owner authorized continued implementation without routine approval pauses.
This is not spatial B1/B2, a neural model, or a release candidate.

## Scientific contract

1. Objective: test whether explicit variation among source populations improves
   withheld count predictions beyond one pooled uncertain frequency per variant.
2. Evidence: real training-only posterior fits, independent analytical/quadrature
   and known-truth checks, paired count scores/calibration/width/error against B0
   on the unchanged reference protocol, and complete failure accounting.
3. Component/interface: pure offline fit(training, config) followed by
   predict(fit, withheld rows, cdf_backend), using ReferenceCount and CountPredictive;
   the reference benchmark runner is the I/O composition boundary.
4. Assumptions/refusals/consumers: working exchangeability of reference populations,
   explicit fixed priors, no learned cross-locus prior or query-genotype context.
   Unknown geography, ascertainment, dates and dependence remain unknown.
   Invalid inputs, unavailable training variants, unsupported numerical domains
   and failed convergence are refused. Consumers are research comparisons only.

## Global constraints

- Model identifier: `B0H_population_heterogeneity`; target: `reference_panel_within_resource`.
- No new package dependency, P1/production schema, serving change, inferred coordinate or radius.
- Pure science modules have no filesystem, network, HTTP, environment or UI dependency.
- Stochastic modules declare `SEED = 42`; inputs and configuration determine draws on a pinned runtime.
- All real counts, posterior draws and per-row predictions remain local and untracked.
- AN=0 is retained as unavailable, never converted to frequency zero.
- Fitting consumes training rows only; prediction rejects training group/record overlap.
- No cross-variant parameter pooling, LD likelihood, independent-locus or joint-site prediction claim.
- No clipping, silent fallback, relaxed scoring domain, or discarded failed variant/fold.
- Convergence requires four or more chains, zero divergences, finite rank-normalized R-hat <=1.05,
  and finite bulk and tail ESS >=200 for both mean and rho in every fitted variant.
- Keep existing clinical gates and global promotion defaults unchanged.
- CuGen and source-export permission for remote CUDA are not prerequisites for local model work.

## Model and prior interpretation

For each variant v independently:

```text
mean[v] ~ Beta(mean_prior_alpha, mean_prior_beta)
rho[v]  ~ Beta(rho_prior_alpha, rho_prior_beta)
kappa[v] = (1 - rho[v]) / rho[v]
AC[g,v] ~ BetaBinomial(AN[g,v], mean[v]*kappa[v], (1-mean[v])*kappa[v])
```

The primary fixed prior is mean Beta(1,1), rho Beta(1,9); the separately reported
sensitivity is mean Beta(1,1), rho Beta(1,4). Mean prior equality preserves
allele-complement symmetry. Rho is a beta-binomial heterogeneity parameter,
not measured ancestry, migration or historical FST. Beta(1,9) has mean0.1 and
95th percentile about0.283; this is an explicit modeling choice, not an estimate
from the pilot or a universal biological prior. Both rho priors admit values
arbitrarily near zero. Draws beyond the existing count scorer's concentration
domain cause an explicit numerical refusal; do not truncate the prior silently.

The beta-binomial integrates the new population's frequency. Averaging aligned
posterior draws integrates uncertainty in mean and rho. A plug-in dispersion
is not equivalent and is not this experiment.

The formulation is motivated by the population-count model in Fumagalli et al.
(2013), not by a claim that the panel satisfies its simplifying assumptions.
Full-text reading and limits are recorded in
`docs/research/reference-count-next-models-2026-09-10.md`.
The existing spatial beta-binomial decision #83 is retained.

Vectorized PyMC/NumPyro is the implementation choice: its draws directly enter
CountPredictive and use the repository's existing sampler stack. This evaluates
a sum of separate working per-variant likelihoods; it does not establish that
the adjacent SNPs are independent observations or yield a validated joint LD
posterior. Deterministic 2D integration is the small-case numerical oracle,
not a second production scoring implementation requiring weighted-mixture APIs.

## Public fit and prediction contracts

`genomeos.surfaces.heterogeneity_types` holds validated immutable contracts.
`genomeos.surfaces.reference_heterogeneity` holds fitting and prediction.
Each production module targets <=500 logical lines.

`PopulationHeterogeneityConfig` requires four positive finite non-Boolean real
prior shapes: mean_prior_alpha, mean_prior_beta, rho_prior_alpha, rho_prior_beta.
Settings: draws=500, tune=1000, chains=4, target_accept=0.9, seed=42.
Draws/tune are positive integers; chains integer>=4; seed nonnegative integer;
target_accept is finite and strictly between0 and1. Boolean integers are rejected.
The convergence gates are fixed invariants, not permissive configuration switches.

`VariantTrainingCounts` contains variant_id, training_observation_count,
training_ac, training_an. IDs are literal nonempty strings; totals use Python
integers and contain available training rows only.

`VariantHeterogeneityDiagnostics` contains variant_id, max_rhat, min_bulk_ess,
min_tail_ess. Values are finite, with max_rhat the maximum and ESS the minimum
over mean/rho for that variant. Global divergences must not be attributed to
individual variants.

`PopulationHeterogeneityFit` contains config, variant_ids, mean_draws, rho_draws,
training_record_ids, training_group_ids, unavailable_training_ids,
training_counts, diagnostics, divergence_count. Draws are float64 arrays shaped
(chain, draw, variant), defensively copied onto immutable byte-backed storage.
All identities are explicit canonical sorted tuples; parameters and diagnostics
have exactly the same variant ordering. The stored chains/draws match config.
Successful fits have divergence_count=0 and satisfy all declared gates.

`ReferenceHeterogeneityPrediction` contains marginal_predictive:CountPredictive,
observation_ids:tuple[str,...], unavailable_ids:tuple[str,...]. IDs in each
sequence preserve submitted test-row order. Outputs remain marginal; do not
claim a validated joint-site sampler.

```python
def fit_reference_population_heterogeneity(
    training: Sequence[ReferenceCount], *,
    config: PopulationHeterogeneityConfig,
) -> PopulationHeterogeneityFit: ...

def predict_reference_population_heterogeneity(
    fitted: PopulationHeterogeneityFit,
    testing: Sequence[ReferenceCount], *,
    cdf_backend: Literal["scipy", "cupy"] = "scipy",
) -> ReferenceHeterogeneityPrediction: ...
```

Fit validates ReferenceCount rows before any sampler call. All-zero-AN training
is infeasible. It fits every variant with available training evidence, sorted by
literal variant ID, and retains unavailable training record IDs. Individual
training AN above the existing public MAX_BETA_SCORING_COUNT is refused as an
unsupported domain; counts are never thinned or capped. No metadata from test
rows participates in graph construction, RNG choice or stopping.

PyMC graph nodes are named `mean` and `rho`, with explicit `variant` coordinates;
only positive-AN rows enter the observed node. Call pm.sample with config seed,
four vectorized NumPyro chains by default, progressbar=False and the existing
`nuts={"chain_method": "vectorized"}` routing. Do not change global JAX/PyTensor
configuration or read environment variables in these science functions.
A non-float64 posterior is refused instead of silently upcast as precision proof.

Extract arrays using named dimensions and coordinate labels, not implicit
column position. Require exactly chain/draw/variant axes, canonical integer
chain and draw positions, exact variant identity sets, and matching labels
between mean/rho and sample_stats. Reindex variant axes before converting.
Missing/duplicate/misaligned labels, nonfinite values, mean/rho outside(0,1),
or a derived kappa rejected by CountPredictive are hard errors.

Use ArviZ rank R-hat and both bulk/tail ESS on mean/rho. A malformed/nonfinite
diagnostic is a failure, not a nanmin/nanmax omission. Missing/malformed
sample_stats.diverging is refused. Divergences are counted globally.
`HeterogeneityConvergenceError(RuntimeError)` carries the finite available
per-variant diagnostics, the global divergence_count when established (otherwise
None), and an explicit reason. It never returns prediction rows. Structural or
numerical failures remain ValueError/ArithmeticError with explicit reasons.

Prediction validates testing rows, disjoint training IDs/groups, known available
variants for every scoreable row, and the requested backend. A fold with no
positive test denominators raises ReferenceInfeasibleError; an absent training
variant raises B0InfeasibleError. Reconstruct flat draw-aligned mean/kappa arrays
for scoreable rows without using test AC. Do not infer a missing query factor,
prior-only frequency or sampling design.

## Benchmark integration and immutable evidence

Extend the existing reference runner without replacing its B0 path:
`--model pooled_beta_counts|B0H_population_heterogeneity` defaults to the former.
Existing required --prior-alpha/--prior-beta are B0H mean-prior shapes;
B0H additionally requires --rho-prior-alpha/--rho-prior-beta.
Reject rho/sampler settings supplied to B0 rather than silently ignoring them.
B0H sampler settings are explicit CLI defaults from the config above.
`--cdf-backend scipy|cupy` is explicit and has no automatic fallback.

Keep the existing split and PIT streams unchanged. Derive independent fit/retry
streams from the third child of a new SeedSequence(root).spawn(3); its first two
children must match the prior split/PIT streams. The third child's five children
each spawn initial/retry seeds. No seed is derived from observed counts.

One retry is allowed for a HeterogeneityConvergenceError only, with doubled
draws and tune and its separate recorded seed. Do not retry a structural or
numerical-domain failure or change priors, rows, model, gates or folds.
Record both attempts; failures remain visible even if the retry succeeds.
A final failure marks every scoreable row in that fold failed, with no predictions;
later folds still run. No failed variant is omitted inside an otherwise completed fold.

B0 artifacts remain compatible. New model configuration, backend and fit-seed
metadata use a versioned manifest; source hashes cover every consumed new module
and the runner. For B0H add `fit_diagnostics.json` with all planned split IDs and
attempt budget/seed/status/reason/diagnostics, plus `posterior_draws.npz` containing
numeric mean/rho arrays and Unicode variant IDs for successful folds only.
The NPZ contains no object/pickle arrays; consumers load with allow_pickle=False.
Fingerprint exact output bytes. Retain the existing prediction/missing/fold
contracts. B0H `posteriors.tsv` reports training totals and posterior mean/rho
means per split/variant, clearly distinguished from B0's conjugate shapes.
No model-selection or automatic promotion code is introduced.

## Pre-real-data scientific verification

Unit/fixture tests precede implementation. A real synthetic NUTS fit must pass
the same unrelaxed gates as later real data; mocked sampler outputs are limited
to structural/refusal/dispatch tests, not scientific calibration evidence.

The first sampler oracle uses two analytically tractable cases, avoiding an
approximate integrator where an exact answer exists. Five AN=1 groups with AC
0,1,1,0,1 give independent mean~Beta(4,3), rho~Beta(1,9) posteriors. Four AN=2,
AC=1 groups have likelihood proportional to [mean*(1-mean)*(1-rho)]^4, giving
independent mean~Beta(5,5), rho~Beta(1,13) posteriors. Their new AN=2 predictive
P(AC=1) values are respectively27/70 and65/154; P(AC=0) is33/140 and89/308.
Check first/second parameter moments and these predictive probabilities against
the literal rational answers within measured Monte Carlo uncertainty.

For subsequent nonconjugate cases, integrate the normalized 2D posterior over
mean/rho using an independent test-side quadrature/PMF implementation and establish
convergence at increasing orders. Complemented data must map mean to1-mean and
preserve rho and complementary count probabilities. None of these checks alone
is a population-wide calibration study.

The controller freezes the full simulation configuration and numerical acceptance
thresholds in a separate executable experiment protocol before running its
calibration study. That study covers prior simulation/rank calibration, rare/common
means, weak/strong heterogeneity, homogeneous rho=0 counts, unavailable/heterogeneous
denominators and unmodeled shared population history. Boundary/misspecification
stress tests report failures and predictive consequences; they are not mistaken for
draws from the fitted prior or a guarantee of parameter coverage at excluded atoms.
No real challenger is fitted before this protocol and evidence are recorded.

Then evaluate both fixed prior tracks on the same two stages × two count kinds ×
three seeds used by B0, with the same five folds, rows and dependencies. Report every
run, failed attempt, paired score/error/interval comparison and coverage limitations.
Do not select a winning prior/seed or compute independent-replicate uncertainty
from overlapping seeds, stages or the 510 adjacent SNPs. This development ablation
cannot satisfy external/geographic promotion, and does not alter those gates.
