# Observation-aware predictive parameters

## Status and scope

This is the next focused architectural slice of the owner-approved [global AF program](../plans/2026-09-09-global-af-modeling.md), implementing the observation-prediction prerequisite in [#191](https://github.com/bschilder/genomeOS/issues/191). It follows the initial benchmark/scoring slice; it does not replace its outstanding hardware, review or PR gates. The owner explicitly authorized continued implementation without routine approval pauses on September 9.

Atlas design §§4–5, 7.1, 8 and 12 apply. The primary program target remains present-day residents, but a prediction of a recorded survey is not itself evidence that its recruitment represents residents. This slice adds no data, new fitted likelihood, covariate, production surface, serving inference or publication authorization.

## Scientific contract

1. **Objective:** predict held-out survey counts under the already fitted observation model, preserving posterior alignment, actual sampling-design contrasts and shared effects for genuinely unseen cohorts.
2. **Measurable output and acceptance evidence:** immutable draw-aligned means and concentrations consumed by the exact count scorer; analytical effect-composition tests; deliberate metadata/alignment failures; deterministic query-permutation tests; real-fitter and save/load integration; unchanged legacy interfaces and convergence rules. These establish mechanics, not empirical calibration or superiority.
3. **Engineering component and interface:** a pure surfaces-owned parameter contract and composition function, plus a narrow `SurfaceFit.predict_new_cohort_parameters(queries, *, seed=42)` adapter. Benchmark code wraps the public returned arrays in `CountPredictive`; surfaces code does not import benchmark orchestration or scoring internals.
4. **Assumptions, refusal conditions and consumers:** coordinates, observation/cohort identities and sampling designs are supplied, not inferred. Seen-cohort conditioning is a separate prediction target and is refused by this interface. Missing fit metadata, unsupported designs, ambiguous draw axes and inconsistent fitted-effect declarations are hard failures. Research benchmarks are the first consumer; no production caller changes automatically.

## Chosen approach and alternatives

Add a separately versioned unseen-cohort interface while preserving `predict`, `predict_draws` and legacy `predict_observation`. Modifying the old summary method in place would silently change existing calibration results and still lack an exact count-probability interface. Implementing both seen-cohort conditioning and unseen-cohort prediction together would mix conditional-imputation and geographic-generalization targets; defer the former.

The new interface exposes parameters of the existing fitted approximation. It does not repair inducing-approximation uncertainty, fit geographic footprints, infer recruitment representativeness, or establish joint-field calibration. Those remain separate experiments in WP0–WP2.

## Public contracts

All new contracts live in `genomeos/surfaces/observation.py`, without PyMC, storage, HTTP, environment or network dependencies. Use frozen dataclasses, explicit type annotations and defensive immutable array copies. Numeric arrays have dtype float64. A frozen dataclass containing a writeable NumPy array is not sufficient: callers must be unable to restore writeability through `setflags`.

### SurveyQueries

Required fields, all length N greater than zero:

- `observation_ids: tuple[str, ...]`: unique, nonempty, actual string identifiers.
- `cohort_ids: tuple[str, ...]`: nonempty actual strings; repetition is meaningful.
- `sampling_designs: tuple[str, ...]`: nonempty actual strings, checked against fitted designs.
- `lat: tuple[float, ...]`, `lon: tuple[float, ...]`: finite WGS84 values in [-90, 90] and [-180, 180]. Refuse booleans and nonnumeric values; do not infer coordinates from identities.

No denominator is needed to predict these parameters. AC/AN enter the independently validated count scorer afterward. No defaults stand in for observation metadata.

### ObservationModelMetadata

Required fields:

- `convention: str`: exactly `new_cohort_count_v1` for this implementation.
- `fitted_designs: tuple[str, ...]`: unique nonempty actual labels, with the actual fitted zero-offset reference first and fitted contrasts afterward in coefficient order.
- `training_cohort_ids: tuple[str, ...]`: sorted unique nonempty actual labels, retained even when no cohort effect was estimated.
- `cohort_effect_applied: bool` and `nugget_applied: bool`: actual fitted choices, not choices at prediction time.
- `likelihood: str`: exactly `binomial` or `beta_binomial`.

Record the actual fitted reference even when `config.reference_design` was absent. A query using an absent design is refused; a query using a documented, actually fitted alternate anchor is supported without relabeling that anchor as population-random recruitment. Existing `SurfaceFit.design_levels` retains its legacy meaning: non-reference levels only.

### ObservationParameters

Required fields:

- `queries: SurveyQueries` and `metadata: ObservationModelMetadata` preserve the prediction target.
- `draw_ids: tuple[tuple[int, int], ...]`: unique `(chain, draw)` coordinate pairs, not a newly numbered array that hides posterior identity. The first axis is in this recorded order.
- `mean_draws: np.ndarray`: immutable finite array of shape `(D, N)`, D greater than zero, values in [0, 1].
- `concentration: np.ndarray | None`: immutable finite positive `(D, N)` array for beta-binomial; explicit `None` only for binomial.

The arrays describe conditional mean/dispersion given each combined posterior/new-effect draw. They are not replicated counts. Numerical endpoints produced by `expit` are retained without arbitrary epsilon clipping. The downstream scorer still applies its documented special-function numerical limits; mathematically positive parameters do not guarantee numerically evaluable beta-binomial probabilities.

**Arithmetic-domain clarification ([#200](https://github.com/bschilder/genomeOS/issues/200)):**
finite input arrays do not guarantee finite additions or scale products. Refuse nonfinite
composition intermediates with an explicit numerical-domain error before `expit` can hide them
as plausible endpoints. Do not add clipping or an implicit higher-precision fallback. This may
refuse mathematically finite cancellation cases outside float64's evaluable domain; ordinary
finite large logits still retain their numerical probability endpoints.

### Pure composition function

```python
def compose_unseen_observations(
    latent_logit_draws: np.ndarray,
    *,
    draw_ids: tuple[tuple[int, int], ...],
    queries: SurveyQueries,
    metadata: ObservationModelMetadata,
    design_effect_draws: np.ndarray,
    cohort_sd_draws: np.ndarray | None,
    nugget_sd_draws: np.ndarray | None,
    concentration_draws: np.ndarray | None,
    seed: int = SEED,
) -> ObservationParameters:
    ...
```

The latent array is finite `(D, N)` on the logit scale. Design contrasts are finite `(D, K)`, with K equal to `len(fitted_designs) - 1`; for one design require the explicit empty-column `(D, 0)` array. Scalar scale/concentration draws have shape `(D,)`. Scales are finite and nonnegative. A fitted cohort/nugget term requires its scale draws; an omitted term requires `None`, not a silently ignored array. Concentration follows the declared likelihood. Reject inconsistent dimensions, boolean seeds, negative seeds, duplicate draw IDs and seen training cohort IDs before generating random numbers.

Compose:

```text
logit[d, i] = latent[d, i]
            + design_contrast[d, sampling_design[i]]
            + cohort_sd[d] * z_cohort[d, cohort_id[i]]
            + nugget_sd[d] * z_observation[d, observation_id[i]]
mean[d, i]  = expit(logit[d, i])
```

The reference contrast is zero by the fitted parameterization, not an imputed effect. Draw one normal variate per `(posterior draw, distinct new cohort)` and share it across all that cohort's sites. Draw nugget variates independently per `(posterior draw, observation ID)`. Use separate `SeedSequence(seed).spawn(2)` streams, canonical sorted cohort/observation identities, and invert the query permutation. Omitted terms do not shift the other term's stream. Tests verify permutation behavior and stream isolation, not merely matching marginal variances. Query-subset invariance is not promised: changing the set can change the seeded realization.

## PyMC integration and fit provenance

`SurfaceFit` gains `prediction_metadata: ObservationModelMetadata | None = None`. `None` denotes unavailable legacy metadata, never an assumed scientific value. New fits supply metadata from the actual `design_levels`, sorted training cohorts and fitted configuration. Old cached objects lacking this field remain usable through legacy methods; the new method explicitly refuses them and requests a refit. Do not reconstruct the anchor from `config.reference_design` or from posterior column counts.

Expose the existing latent prediction expression as a named deterministic `latent_logit_pred`. Do not recover logits from clipped `freq_pred`: near a rounded probability endpoint, that would impose an arbitrary cap before adding design/cohort effects. The existing `freq_pred` expression, likelihood, priors, convergence checks and old prediction methods remain unchanged. Verify that adding a deterministic node does not alter seeded legacy results; do not assume this from its name.

The public wrapper delegates PyMC extraction to `genomeos/surfaces/observation_prediction.py`. This adapter may use the fitted graph, but exposes no private graph objects to its consumers. It must:

1. Validate queries and complete fit metadata, refuse seen cohorts and absent designs before posterior sampling.
2. Canonicalize query coordinates and sample the latent field at each unique coordinate once, then expand to query identities. Use deterministic lexicographic numeric coordinate ordering. Exact equal submitted coordinate pairs share the latent realization; normalize longitude -180 to 180 and all longitudes at exact poles only for this spatial computation, retaining submitted coordinates in the returned queries. No approximate rounding, snapping, or default coordinates.
3. Request the named latent logit expression with an explicit seed. Transpose by named `chain` and `draw` dimensions, never blindly flatten arbitrary array layouts. Require unique integer posterior coordinate labels; preserve and check exact coordinate equality across latent and effect arrays after explicit alignment. Record the canonical sorted chain-then-draw pairs in the output.
4. Extract the sole design coefficient axis in recorded fitted-contrast order, checking its size and positional coordinates. Missing, extra or ambiguous event dimensions are errors. Scalar effects must have only chain/draw dimensions. Missing required posterior variables are errors, not zero effects.
5. Call the pure composition function and return the public immutable parameters in original query order. Distinct coordinates retain whatever joint structure the existing approximation provides; this is not a new full-GP residual correction.

The adapter must not pretend a legacy graph has the new node. Cache format 1 may remain readable for legacy methods because added metadata is optional; new-interface capability is explicitly checked. Save/load tests cover new metadata, identical new predictions, unchanged legacy predictions, and an object with absent metadata. Trusted synthetic tests only: never load an untrusted pickle.

**Compatibility comparison ruling, September 9:** the unchanged parent at `6692d1e` exhibits a
small fresh-versus-reloaded prediction difference in the local environment; the original Git
object reproduces it, while the same old pickle under parent/extracted code is bitwise equal.
Preserve separately fingerprinted fresh-parent and parent-loaded-cache controls. Exact
fresh-parent/fresh-new and cached-parent/cached-new comparisons test version compatibility;
do not replace the former with the latter or weaken either with a numerical tolerance. Record the
pre-existing execution-mode discrepancy and investigate its cause separately in
[#198](https://github.com/bschilder/genomeOS/issues/198), without claiming that this refactor
fixes it. New-interface save/load equality remains its own Task 3 requirement.

## Module budget and compatibility seam

`fit.py` is near the repository's 800-line/50-KiB hard limit. Before adding integration, extract `FitConfig` and its configuration/geometry constants into `genomeos/surfaces/config.py`, preserving values, validation behavior and scientific documentation. Re-export existing public names from `fit.py` so callers and older pickle references resolve. Keep `SurfaceFit` in its current module; do not move its identity or change repository layout. Keep geometry/fitting algorithms in place. This is a narrow compatibility-preserving prerequisite, not a general refactor.

No dependency change or production schema change is required. Tests must cover old import paths, dataclass defaults/validation and persistence. The local editable environment is shared with another checkout: verification uses this worktree's explicit `PYTHONPATH` and isolated PyTensor/Matplotlib caches.

## Acceptance matrix

| Claim | Required evidence |
|---|---|
| Effects follow the recorded observation model | Hand-computed logits with zero noise, design offsets, binomial/BB outputs and all fitted/omitted combinations |
| Shared cohort mechanics are preserved | Same cohort/site latent inputs yield identical cohort increments; distinct cohorts have separate seeded draws; nugget effects remain per observation |
| Draws really align | Synthetic permuted xarray dimensions/coordinate order, explicit expected chain/draw IDs, malformed-coordinate refusals, plus an actual fitted model integration |
| Reordering does not change meaning | Pure composition and real-adapter permutation equality after matching observation IDs; duplicated coordinates share latent values before observation effects |
| Legacy behavior remains reproducible | Existing tests, exact same-seed parent/new comparisons separately for fresh and loaded graphs, and trusted synthetic persistence/capability checks |
| Exact scoring is composable | Pass returned arrays to public `CountPredictive`; compare an analytical zero-effect case and run finite count diagnostics on real-fitter synthetic queries |
| Failure remains visible | Missing old metadata/node, absent reference/query design, seen cohort, missing scale, malformed arrays/coordinates/seeds and unsupported convention are explicit errors |

Use analytical tests for rare combinations instead of repeatedly fitting tiny non-converged models. Reuse the existing module-scoped real-fitter fixture for integration. Never lower R-hat/ESS criteria to make a predictive-interface test pass. Every code/configuration change runs focused tests, smoke, lint, contract, module-size and privacy gates; full CI and independent review precede the PR. This slice advances #189 and can close #191 only after every stated adapter acceptance item is verified.

## Explicit limitations and next consumer

These outputs remain offline research parameters. They do not establish out-of-region accuracy, resolve survey-footprint issue #190, repair shared-schema coercion issue #192, qualify resident sampling, justify new geographic resolution or authorize redistribution. Beta-binomial concentration and a nugget may compete statistically; restoring a fitted nugget is not evidence that fitting both is identifiable.

The subsequent GP benchmark adapter must use the existing lossless input validator, frozen splits and fail-closed reports; record full `FitConfig`, actual chain/draw counts, prediction convention and every attempt; retain the one logged doubled-draw/tuning retry followed by failure. B0's `posterior_draws` is a total, whereas GP `FitConfig.draws` is per chain: these must not become one unlabeled tuning knob. That adapter is a separate implementation plan after this contract is reviewed.
