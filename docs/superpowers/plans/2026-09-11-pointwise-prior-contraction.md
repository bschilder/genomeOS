# Pointwise Prior Contraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair issue #266 so each surface cell's support ratio uses its own implemented latent prior uncertainty, while retaining existing fits and cited artifacts.

**Architecture:** A focused prior-prediction module queries the retained PyMC graph with a reproducible random stream. SurfaceFit exposes the coordinate interface, and every ratio consumer uses its aligned output. Versioned artifacts/caches distinguish corrected results from legacy scalar normalization without discarding posterior work.

**Tech Stack:** Existing NumPy/PyMC/PyTensor/Pandas/Parquet/cloudpickle and Matplotlib; existing TypeScript/Zod/Vitest browser contracts. No new dependency.

**Spec:** [Pointwise prior contraction design](../specs/2026-09-11-pointwise-prior-contraction-design.md); issue #266; Atlas design §§5–7.1b,12.

## Global Constraints

- Use the implemented approximate latent prior, including its actual hyperpriors and geometry, and the same `freq_pred` quantity as latent posterior prediction.
- The protocol is `pointwise_approximate_latent_v1`: 500 prior draws, the fit's explicit seed, and population SD (`ddof=0`).
- Preserve the support threshold 0.9, range rules, observation precedence and exclusion of `unknown`/`prior_dominated` from aggregation.
- Do not change likelihoods, model priors, posterior sampling or convergence/golden gates. Do not claim that denominator repair restores omitted covariance or establishes calibrated fitted uncertainty.
- Existing fitted posteriors, model graphs, cache files and cited artifacts must be preserved. No real data acquisition, fit, publication, overwrite or resource restart is part of this task.
- Science modules have no filesystem, network, HTTP or environment dependency. Stochastic modules declare `SEED = 42`. Every changed scientific module cites the relevant design section.
- Keep production modules at most 800 logical lines and 50 KiB; do not refactor unrelated fitting or observation-centre logic.
- No private/session/history files, personal paths, credentials or real genomic records enter commits. All test/figure inputs are authored synthetic data.
- Use a dedicated branch and PR. Before commit/push run the privacy gate and inspect staged paths. Run smoke and focused checks after changes, and the full required gates before delivery.
- The controller handles review and PR delivery. The implementer must not spawn agents, push, merge, remove worktrees or delete retained evidence.

---

### Task 1: Replace scalar normalization across the offline surface path

This is one coherent repair: an API-only change would leave existing consumers
using the defective ratio, and an artifact-only change could mislabel legacy
results. Review the complete migration as one unit.

**Files:**
- Create: `genomeos/surfaces/prior.py` — bounded prior prediction of the actual latent node.
- Modify: `genomeos/surfaces/fit.py` — coordinate method; remove obsolete scalar construction.
- Modify: `genomeos/surfaces/persistence.py` — current writes and explicit legacy-fit reconstruction.
- Modify: `genomeos/surfaces/mask.py`, `genomeos/surfaces/artifacts.py` — pointwise ratios and format 3.
- Modify: `scripts/plot_surface.py`, `scripts/publish_artifacts.py`, `scripts/screen_alleles.py` — consume/record the new protocol.
- Modify: `scripts/export_atlas_web.py`, `website/src/atlas/contracts.ts` — format-3 compatibility.
- Modify documentation: `genomeos/burden/national.py` scalar-prior comment only; add `docs/research/pointwise-prior-contraction-2026-09-11.md` explaining the scientific and migration limits.
- Create: `scripts/plot_prior_normalization.py`, `docs/figures/prior_normalization.png` — reproducible synthetic figure.
- Tests: `tests/test_surface_fit.py`, `tests/test_surface_mask.py`, `tests/test_artifacts.py`, `tests/test_publish_artifacts.py`, `tests/test_export_atlas_web.py`, `tests/test_build_atlas_catalog.py`, `website/tests/atlas-contracts.test.ts`; create focused `tests/test_surface_prior.py`, `tests/test_surface_plot_cache.py`, `tests/test_plot_prior_normalization.py` as needed by the responsibilities above.
- If small helpers make plot-cache logic directly testable, keep them in `scripts/plot_surface.py`; no generic cache framework or new runtime settings.

**Interfaces:**
- Produces `SurfaceFit.prior_frequency_sd_at(self, lat: object, lon: object) -> np.ndarray`, one SD per input coordinate in input order.
- Produces `latent_prior_frequency_sd(model: Any, coordinates: np.ndarray, *, seed: int) -> np.ndarray` in `surfaces/prior.py`; coordinates are unit-sphere Cartesian rows `(n,3)`.
- Produces constants `PRIOR_NORMALIZATION = "pointwise_approximate_latent_v1"`, `PRIOR_DRAWS = 500`, `PRIOR_BATCH_SIZE = 2048` in that module. Batch size is an engineering bound.
- Existing `predict`, `predict_draws` and `predict_observation` interfaces retain their meanings and schemas.
- Existing `save_fit`/`load_fit` names remain; new `FIT_FORMAT = 2`, known legacy format 1 is explicitly reconstructed without refitting.
- `ARTIFACT_FORMAT = 3`, readable formats `{1,2,3}`. Add the per-cell `prior_frequency_sd` column. Replace manifest scalar SD with required `prior_normalization: str`, `prior_draws: int`, `prior_seed: int`.
- Plot caches store `cache_format=2`, `prior_sd` as shape `(n,)`, exact ordered `h3_index`, `lat`, `lon`, normalization/draws/seed, and the existing central/SD/range arrays.

- [ ] **Step 1: Capture the failing normalization and compatibility tests.**

Build a deterministic fake fit whose `predict` returns a vector of local SDs and
whose new prior method returns the same vector. Do not give it the obsolete
scalar property. Use valid distinct H3 cells, one explicit observation cell and
an in-range non-observed cell; keep a far-control cell outside twice the range.
Run both `evaluate_cells` and `cell_table`, respecting their existing centre rules.

```python
np.testing.assert_array_equal(frame["prior_frequency_sd"], local_sd)
np.testing.assert_allclose(frame["posterior_contraction"], 1.0, rtol=0, atol=0)
assert frame.loc[in_range_unobserved, "support"] == "prior_dominated"
assert frame.loc[far_control, "support"] == "unknown"
assert frame.loc[observed, "support"] == "observed"
```

Add a second vector where one posterior SD is exactly 0.8 times its local prior
SD; that in-range unobserved cell must become interpolated. Assert the result of
`aggregate_cells` excludes the other masked values and returns the excluded
fraction. Add malformed per-cell prior SD (zero/NaN) rejection tests.
Run the focused new cases before production edits and retain the expected
missing-method/column failures. Do not weaken existing assertions to obtain RED.

- [ ] **Step 2: Implement actual prior prediction and remove the scalar.**

The core batch operation is:

```python
with model:
    pm.set_data({"x_pred": coordinates[start:stop]})
    prior = pm.sample_prior_predictive(
        draws=PRIOR_DRAWS, var_names=["freq_pred"], random_seed=seed,
    )
samples = prior.prior["freq_pred"].to_numpy().reshape(PRIOR_DRAWS, stop - start)
sd[start:stop] = samples.std(axis=0, ddof=0)
```

Validate a nonempty finite `(n,3)` unit-sphere array and a nonnegative integer
seed (reject Boolean). Save the previous model data before the loop and restore
it in `finally`, even if prediction fails. Each batch gets the same seed, not
seed+batch-index. Refuse nonfinite draws, wrong draw shapes or nonpositive SD;
never clip/fill/substitute a value. Keep only batch-sized draws in memory.

The SurfaceFit method converts scalar or one-dimensional lat/lon inputs,
requires matching nonempty one-dimensional shapes, finite latitudes within
[-90,90] and longitudes within [-180,180], and delegates after `to_unit_sphere`.
Reject Boolean coordinates. Remove the old field, fit-time `sample_prior_predictive`
call, scalar calculation and constructor argument. Keep the existing posterior
sampler call and every model distribution unchanged. Put the new scientific
responsibility outside fit.py so the module budget remains satisfied.

- [ ] **Step 3: Test actual model behavior and saved-work migration.**

Extend the existing actual fitted-model tests instead of creating many redundant
MCMC runs. Cover the current HSGP fixture and inducing H3/k-means configurations.
Compare the public method against direct prior sampling of the same graph using
the protocol; preserve the graph data around the independent test call.

```python
query = np.array([[9., 0.], [20., 78.], [-4., 22.]])
sd = fit.prior_frequency_sd_at(query[:, 0], query[:, 1])
again = fit.prior_frequency_sd_at(query[:, 0], query[:, 1])
order = np.array([2, 0, 1])
permuted = fit.prior_frequency_sd_at(query[order, 0], query[order, 1])
batched = np.concatenate([
    fit.prior_frequency_sd_at(query[:1, 0], query[:1, 1]),
    fit.prior_frequency_sd_at(query[1:, 0], query[1:, 1]),
])
np.testing.assert_allclose(again, sd, rtol=0, atol=1e-10)
np.testing.assert_allclose(permuted, sd[order], rtol=0, atol=1e-10)
np.testing.assert_allclose(batched, sd, rtol=0, atol=1e-10)
```

Exercise an internal batch boundary by temporarily reducing only the engineering
batch size in a test. Verify another valid seed changes samples, repeated queries
match, and the original `x_pred` is restored after success and a deliberate
prediction exception. Test invalid empty/mismatched/2-D/nonfinite/out-of-range
queries and invalid prior outputs. Actual prior tests must sample actual PyMC
models; mocks alone do not establish the contract.

New caches write format 2. For format 1, read the known required SurfaceFit fields
and rebuild the current dataclass; retain `idata`, `_model`, config and geometry.
Check the retained model exposes the expected predictive nodes. Discard only
the legacy scalar field; missing required fields or unknown formats fail with an
actionable message. Do not rewrite the input file or call a fitter in the loader.
Document the migration. Keep the existing trusted-owner pickle warning.

Test current save/load and an owned legacy-shaped payload generated in the test
from its own model/fit. Include an absurd old scalar to prove it is unused. Check
posterior summaries and local prior SD before/after at the same coordinates;
hash the input cache before/after to prove it stayed untouched. No external pickle
fixture is loaded. Keep unknown-version and missing-field refusal tests.

- [ ] **Step 4: Migrate cell artifacts, publishers and diagnostic metadata.**

Use the same operation in both cell consumers:

```python
prior_sd = fit.prior_frequency_sd_at(lat=lat, lon=lon)
contraction = predicted["post_sd"].to_numpy() / prior_sd
```

Require an aligned finite positive vector so a malformed provider cannot silently
broadcast one scalar. Add it to returned cell rows as `prior_frequency_sd`.
The artifact constructor writes only format 3; validate the three protocol fields
and existing grid/measurement requirements. New artifact reads/writes validate
the denominator and ratio (`rtol=1e-12`, `atol=0`) without rounding or recalculating
stored values. Invalid data must fail before making a publication directory.
Retain exact range metadata and existing immutability behavior.

Legacy format 1/2 tests must construct genuinely old-shaped metadata and frames,
not merely relabel format-3 rows. Assert no new field is invented and disk hashes
are unchanged after read. Keep grid provenance mandatory in format 2. Test format
3 missing metadata, scalar/zero/NaN SDs, inconsistent ratios, and exact Parquet
roundtrip of nontrivial binary64 values. A new model version coexists with old.

Update `publish_artifacts.py` to record the protocol/draws/fit seed and remove its
scalar claim. Update `screen_alleles.py` to report protocol metadata instead of a
global SD; any additional prior SD summary must explicitly name its queried
locations, so do not add one in this repair. Update the stale burden docstring
without changing national aggregation or Method B semantics.

- [ ] **Step 5: Migrate plot caches and downstream format acceptance.**

Extract focused cache read/write helpers in `plot_surface.py` if needed for direct
tests. Store arrays with `allow_pickle=False` on read, exact ordered identities,
and protocol metadata. Validate all per-cell arrays have the expected shape and
finite values. Reject legacy files, wrong protocol/draw count, coordinate/H3
reordering, a changed grid with equal length, and malformed prior SD. Cache writes
must refuse an existing path. Error text instructs keeping the old file and
choosing a new path; reuse its saved fit when available. Print an explicitly
labelled min/max of local SDs instead of formatting an array as one scalar.

```python
np.testing.assert_array_equal(restored_prior_sd, written_prior_sd)
with pytest.raises(ValueError, match="new cache path"):
    read_cache(legacy_path, h3_index=cells, lat=lat, lon=lon)
with pytest.raises(ValueError, match="identit|coordinate|grid"):
    read_cache(path, h3_index=cells[::-1], lat=lat[::-1], lon=lon[::-1])
```

Choose helper argument/return names coherently with this testable contract and
record them in the report. They are script-local adapters, not a new shared API.

The exporter must reject unknown artifact versions and validate format-3 prior
metadata/columns before projection into its existing browser surface fields.
Reuse the surface-artifact validation rather than silently accept malformed
format-3 tables. Preserve format 3 and target-grid provenance in export identity.
Zod accepts literals 1,2,3 and requires grid source/version for both 2 and 3.
Add Python export and Vitest format-3 success/refusal cases while retaining legacy
tests. Verify the serving-catalog builder preserves the extra prior-SD Parquet
column without changing its separate read API schema or doing inference.

- [ ] **Step 6: Generate the synthetic review figure and focused note.**

Use the issue's fully authored conditional counterexample: anchor grid
latitude range(-30,41,10), longitude range(-20,69,8); H3 placement budget16,
reach1500 km; Matérn-5/2 length1500 km, amplitude1, production jitter; intercept
Normal(-3.5,1.5). Evaluate the 77 midpoint queries on latitude
range(-25,36,10), longitude range(-16,65,8). Include four clearly labelled far
controls at (-75,-150), (-70,150), (75,-150), (80,160), and their actual
distance-based unknown status. This is fixed-parameter
synthetic geometry, not population observations or fitted posterior evidence.

Calculate conditional SD with an independent covariance solve and 256-point
Gauss-Hermite logistic-normal moments, using the exact equation in issue #266.
For the no-update comparison set hypothetical posterior SD equal to each local
prior SD. Show the scalar-reference and matched-local support maps side by side,
with the unchanged-distribution assumption visible. Give unevaluated background
and unknown controls explicit labels, keep all 77 queries, and never mark an
anchor as measured genetic data. If showing numeric uncertainty, use a sequential
low-to-high ramp. The known query (-25,64) must have scalar ratio about
0.8953380210217113 and local ratio1. Plotting tests verify those numeric controls
and successful creation of the standalone PNG, not pixel-perfect duplication.

Run `python scripts/plot_prior_normalization.py --out docs/figures/prior_normalization.png`.
The note explains the conditional counterexample, actual-model API validation,
finite Monte Carlo denominator, format migration, and untested omitted covariance/
real-map impact. Embed the figure using the repository raw URL. Report observed
test evidence only; do not copy private execution paths or raw history into docs.

- [ ] **Step 7: Verify, self-review and commit the complete repair.**

Confirm imports resolve to this worktree before running tests. Use the existing
locked environment; no dependency changes are required. Retain all focused RED/
GREEN and final verification logs in this plan's ignored workspace.

```bash
python -c 'import genomeos; print(genomeos.__file__)'
ruff check .
python scripts/freeze_contract.py --check
python scripts/check_module_size.py
python scripts/check_private_files.py
python scripts/smoke.py
pytest
```

Also run the affected browser contract tests and `npm run check` in website.
Frozen P0/P1 schemas are unchanged; if an actual frozen schema changes, explain
why, regenerate and commit its contract diff. Do not alter schemas to evade a
compatibility test. Inspect the generated figure and `git diff --check`.
Before committing, stage only the named task paths, inspect
`git diff --cached --name-only`, and rerun the privacy gate against staged content.
Commit with `fix: normalize surface contraction by local prior (closes #266)`.
The controller will independently review the task and full branch and handle PR
delivery. Report exact commands/counts/warnings, source identity, migration test
evidence, and any unresolved concern in the task report.
