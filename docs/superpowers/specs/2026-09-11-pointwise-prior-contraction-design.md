# Pointwise prior normalization for surface support

Implements [#266](https://github.com/bschilder/genomeOS/issues/266), advancing
#189 WP2 and Atlas design §§5–7.1b, 12. This is a normalization repair, not a
claim of calibrated fitted uncertainty or better geographic predictions.

## Scientific contract

1. **Claim:** posterior contraction compares the uncertainty of the same latent
   frequency at the same coordinates before and after observing data. A spatial
   difference in the approximate prior alone must not count as learning.
2. **Output/evidence:** per-query prior frequency SD, aligned with posterior SD;
   reproducible prior draws across order, batch boundaries and saved-fit reload;
   unchanged-distribution controls; auditable cell tables and versioned metadata;
   legacy artifact preservation and a synthetic review figure.
3. **Component/interface:** `SurfaceFit.prior_frequency_sd_at(lat, lon)` returns
   a one-dimensional float64 array. Masking, artifact publication and plotting
   use it offline. Serving reads precomputed results and performs no inference.
4. **Assumptions/refusals/consumers:** the retained PyMC model must expose the
   existing `x_pred` data and `freq_pred` latent deterministic. Unsupported model
   caches, malformed queries and nonfinite/nonpositive prior SDs fail explicitly.
   Consumers are P2 support classification, research plots and immutable P4/P5
   artifacts. Observation noise, ascertainment contrasts and new-cohort effects
   are not added to the latent denominator.

## Normalization target

Use the **implemented approximate latent prior**, including its actual amplitude,
lengthscale and intercept priors, basis/inducing geometry and jitter. Query the
same `freq_pred` node used by latent posterior prediction. Do not reconstruct a
stationary parent-kernel marginal, use posterior hyperparameters, fix default
hyperparameters, or inject cohort/measurement uncertainty.

The protocol is `pointwise_approximate_latent_v1`: 500 prior draws, the fit's
explicit seed, and population SD (`ddof=0`) on the frequency scale, matching the
existing posterior summary convention. Replay the same random stream for each
query batch; batch size is an engineering limit, not a scientific parameter.
The finite Monte Carlo estimate has sampling error. Independent prior/posterior
samples are not expected to produce an exactly-one no-update ratio; that control
uses identical marginal distributions/SDs deliberately.

The separate omitted covariance `K-Q` remains an approximation question. This
repair neither restores it nor establishes that the approximate posterior is
calibrated against a full GP. Such claims still require the WP2 reference checks.

## Implementation boundaries

- Put PyMC prior prediction and bounded query batching in `surfaces/prior.py`.
  It accepts the actual model and unit-sphere coordinates. `SurfaceFit` validates
  latitude/longitude and delegates; its already-large module stays below the
  repository's 800 logical-line and 50 KiB limits.
- Remove the first-observation scalar field and its fit-time prior sampling.
  Leave model construction, likelihoods, priors, posterior sampling and convergence
  gates unchanged. Restore the model's previous `x_pred` value after prior queries,
  including exceptional exits.
- Preserve the support threshold 0.9, range rules, observation precedence and
  exclusion of `unknown`/`prior_dominated` from aggregation. Existing differences
  in observation-centre identification among callers are outside this repair.
- Both `evaluate_cells` and `cell_table` return a full-precision per-cell
  `prior_frequency_sd` column and compute `post_sd / prior_frequency_sd`.

## Existing work and serialization

Saved fits contain expensive posterior work and the original model graph. New
fit-cache writes use format 2. The loader supports known legacy format 1 by
reconstructing the current `SurfaceFit` from its required retained fields,
discarding only the obsolete scalar uncertainty. Require the expected predictive
nodes and an actual model/configuration; report missing fields instead of guessing.
Do not resample the posterior, rewrite the input cache, or require a refit solely
because its denominator was scalar. Unknown formats remain errors. Pickle is
still a local, environment-coupled, trusted-owner cache, not an archival format.

New surface artifacts use format 3. The manifest replaces the scalar SD with
required `prior_normalization`, `prior_draws` and `prior_seed`. Its normalization
identifier and draw count must match this protocol; seed is a nonnegative integer,
not a Boolean. Preserve unrounded correlation range and cell values. New reads
and writes validate positive finite per-cell prior SD and consistency of the
stored contraction with its two SD columns. Formats 1 and 2 remain readable as
legacy bytes/metadata, with no invented local SD or normalization identity.
Format 2 still requires its target-grid provenance; format 3 requires it too.
Only format 3 is newly published through the current manifest constructor.

Plot caches use explicit format 2 and store the full prior-SD array, protocol
metadata and exact ordered H3/coordinate identities alongside the predictions.
Refuse legacy scalar caches or identity/shape mismatches with instructions to
retain the old file and choose a new cache path. Do not delete or overwrite an
existing cache. A saved fit can be reused to generate the new cache.

The static exporter validates format-3 scientific inputs and preserves format 3
and target-grid provenance in its existing browser contract. The browser accepts
formats 1, 2 and 3, requiring target-grid provenance for 2 and 3. It continues to
display the same precomputed fields. No live fitting or browser-side scientific
calculation is introduced. The separate serving-catalog schema need not change
for an additional retained Parquet column; test that it survives the build.

## Acceptance

- Actual production-fit prior calls agree with direct PyMC prior prediction;
  cover HSGP and inducing H3/k-means, repeated/permuted/split queries, seed use,
  query validation and model-data restoration. Frequency-draw comparisons use
  absolute tolerance 1e-10 and zero relative tolerance.
- Current and known-legacy owned-cache roundtrips preserve posterior predictions
  and local prior SD. A nonsensical legacy scalar does not affect new results.
- An unchanged local distribution yields contraction 1 and stays prior-dominated
  when in range and without an observation centre, across both cell consumers.
  Retain distant unknown cells and observation precedence.
- Artifact formats 1/2 remain unchanged on disk; format 3 roundtrips the exact
  denominator and refuses malformed values/metadata or inconsistent ratios.
  Existing overwrite refusal and a new-version coexistence test remain.
- Plot-cache alignment and legacy refusals are executed tests. Export/browser
  validation accepts format 3, preserves grid provenance, and refuses unknown
  versions. Existing formats remain tested.
- A deterministic script produces a committed synthetic geographic figure of
  the conditional no-update counterexample. Label it synthetic, mark unevaluated
  and unknown locations, and do not portray geometry anchors as measured people.
- Run smoke and focused tests, full Python CI gates, affected browser tests/type
  check, privacy/staged-path review and independent task/whole-branch reviews.

Expert review should assess the normalization target, finite-prior sampling,
cache migration and the distinction between denominator correctness and full-GP
calibration. No real surface is republished by this task.
