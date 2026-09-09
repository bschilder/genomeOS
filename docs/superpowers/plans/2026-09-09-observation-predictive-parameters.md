# Observation Predictive Parameters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose correctly aligned, observation-aware predictive parameters for genuinely unseen cohorts without changing legacy surface outputs.

**Architecture:** Pure surfaces-owned query/metadata/parameter contracts compose latent, design, cohort and nugget draws. A narrow PyMC adapter extracts explicitly aligned posterior arrays and the existing latent logit expression; the existing public count scorer consumes the resulting parameters. Configuration extraction preserves the legacy import/cache seam and makes room within the fitting module's size budget.

**Tech Stack:** Existing Python, NumPy, SciPy, pandas, PyMC/xarray and cloudpickle; no new dependency, production schema, model likelihood or serving change.

**Spec:** [Observation-aware predictive parameters](../specs/2026-09-09-observation-predictive-parameters-design.md), committed initially in `6ae09cf`; [#191](https://github.com/bschilder/genomeOS/issues/191), advancing [#189](https://github.com/bschilder/genomeOS/issues/189).

## Global Constraints

- Atlas design §§4–5, 7.1, 8 and 12 apply. Science modules have no filesystem, network, HTTP or environment dependency.
- Convention is exactly `new_cohort_count_v1`; all scientific query and fit metadata are required. Missing legacy metadata is unavailable, not a default scientific value.
- Keep `SurfaceFit` in `genomeos.surfaces.fit`. Preserve old import paths, defaults, validation, likelihoods, priors, convergence thresholds, legacy prediction methods and production artifacts.
- Use `SEED = 42`; require an explicit nonnegative integer when a seed is supplied, refusing booleans. Coordinate/ID/draw validation never fabricates an observation.
- Arrays have immutable float64 storage and explicit `(draws, observations)` shape; do not merely clear a reversible writeable flag.
- New-cohort predictions refuse any training cohort ID, unknown sampling design, unavailable graph capability or inconsistent effect metadata. No seen-cohort fallback.
- Geographic footprints, resident qualification, shared-schema coercion #192, inducing uncertainty and empirical calibration are separate unresolved work. This interface does not close them.
- Task 1–5 of the initial [program plan](2026-09-09-global-af-modeling.md) must complete hardware, independent-review and stable-tree PR handoff before implementing this follow-up. Preparing this document does not mark those gates complete.
- Every task has its own RED/GREEN, smoke, lint, contract, module-size, privacy/staged-path check and independent review. Full CI precedes this coherent slice's PR. No commits to main, no merge implied.

## File responsibilities

| File | Responsibility |
|---|---|
| `genomeos/surfaces/config.py` | Existing FitConfig and named configuration/geometry constants, with unchanged scientific documentation and validation |
| `genomeos/surfaces/observation.py` | Pure immutable contracts and new-effect composition; no PyMC dependency |
| `genomeos/surfaces/observation_prediction.py` | PyMC query canonicalization, named-dimension extraction and public-parameter adaptation |
| `genomeos/surfaces/fit.py` | Existing fitting/legacy methods; configuration re-exports, actual metadata, named latent node and small new wrapper |
| `genomeos/surfaces/persistence.py` | Existing trusted-cache I/O; document capability distinction without guessing missing metadata |
| `tests/test_surface_config.py` | Configuration extraction and legacy import compatibility |
| `tests/test_observation_parameters.py` | Analytical contracts, effect composition, determinism and numerical refusals |
| `tests/test_observation_prediction.py` | Adapter alignment/refusal/canonicalization with controlled posterior arrays |
| `tests/test_surface_fit.py` | Existing real-fitter fixture reused for integration and trusted cache tests |
| `docs/global-af-benchmark.md` | Public consumption example, version/target distinction and remaining empirical gates |

## Verification environment

Commands below run from the isolated modeling worktree, with these task-specific variables. Do not reinstall the shared editable environment or modify the original checkout.

```bash
export PYTHONPATH=/Users/bschilder/code/genomeOS/.claude/worktrees/global-af-modeling
export PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor
export MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib
AF_PYTHON=/Users/bschilder/code/genomeOS/.venv/bin/python
```

If execution uses a different isolated worktree, explicitly replace PYTHONPATH with that verified path and record it. Each task's gate commands are:

```bash
"$AF_PYTHON" scripts/smoke.py
"$AF_PYTHON" -m ruff check .
"$AF_PYTHON" scripts/freeze_contract.py --check
"$AF_PYTHON" scripts/check_module_size.py
"$AF_PYTHON" scripts/check_private_files.py
git diff --check
git diff --cached --name-only
git diff --cached --check
```

Stage only the task's named files, re-run privacy after staging, then commit. A failed check is a stop for that commit, not something to mask with a later successful command.

## Before Task 1: capture trusted synthetic legacy evidence

This is part of Task 1's compatibility acceptance, not a separate implementation task. Before changing fitting/configuration code, capture the current source revision and a fresh trusted synthetic fit, using the existing test fixture and unchanged convergence criteria. Create a new temporary directory with `mktemp -d`, record its exact path in the execution ledger, and use that explicit path in the following Python command; the filename arguments are the only substitutions.

```python
import runpy
from pathlib import Path
import numpy as np

fixture = runpy.run_path("tests/test_surface_fit.py")
fitted = fixture["fit_surface"](fixture["_observations"](), fixture["FAST_CONFIG"])
lat, lon, an = [0.0, 5.0], [-8.0, 8.0], [200, 200]
# Use the ledger's new temporary directory, supplied as argv[1].
import sys
directory = Path(sys.argv[1])
numeric = directory / "legacy-before.npz"
cached = directory / "legacy-before.pkl"
cache_numeric = directory / "cache-baseline.npz"
if numeric.exists() or cached.exists() or cache_numeric.exists():
    raise RuntimeError("legacy evidence must not be overwritten")
np.savez(
    numeric,
    latent=fitted.predict_draws(lat, lon),
    surface=fitted.predict(lat, lon).to_numpy(),
    survey=fitted.predict_observation(lat, lon, an).to_numpy(),
    prior_frequency_sd=fitted.prior_frequency_sd,
)
fixture["save_fit"](fitted, cached)
restored = fixture["load_fit"](cached)
np.savez(
    cache_numeric,
    latent=restored.predict_draws(lat, lon),
    surface=restored.predict(lat, lon).to_numpy(),
    survey=restored.predict_observation(lat, lon, an).to_numpy(),
    prior_frequency_sd=restored.prior_frequency_sd,
)
print(f"Captured trusted synthetic evidence in {directory}")
```

Run this code via the selected interpreter with the directory argument, not a production fixture or downloaded pickle. Record the command, git revision and source hashes. Keep generated cache/numeric files outside Git. The same fresh-fit calculation after Task 3 must reproduce `legacy-before.npz` on the same recorded environment; preserve discrepancies and investigate rather than relaxing tolerances silently. Separately load this old trusted cache after changes and compare with `cache-baseline.npz`, including genuine missing-new-metadata behavior. The shared environment is not an exact lock-file installation; independent locked verification remains required before merge and must not replace these same-environment controls.

**Evidence-driven comparison clarification, September 9:** a pre-change fit at `6692d1e`
already differs slightly from its reloaded cache (maximum latent difference
`5.5358870931776494e-08`, surface difference `3.432226325372767e-08`; survey array exact).
Executing the original `fit.py` Git object as `genomeos.surfaces.fit` reproduced that difference.
Comparing the same old pickle under original and extracted code is bitwise exact for all four
arrays. Therefore fresh-parent/fresh-new and cached-parent/cached-new are separate exact gates;
fresh-versus-cache is a separately retained numerical observation, not a tolerance to relax.
The original fresh reference must never be replaced by the cache control. If recovering a cache
control after extraction, execute and fingerprint the actual parent module in an isolated process;
never label changed-code output as the parent control. The execution ledger/report records both
controls and this ruling; the baseline discrepancy is tracked in [#198](https://github.com/bschilder/genomeOS/issues/198). Task 3's new-interface round-trip requirement remains independently tested.

### Task 1: Preserve configuration and cache import compatibility

**Scientific contract:** this mechanical extraction changes no scientific model. The measurable output is identical configuration behavior and successful old-path/cache use; the fitter and later adapter consume it. Refuse any need to change a prior/default as part of this task.

**Files:** create `genomeos/surfaces/config.py` and `tests/test_surface_config.py`; modify only configuration ownership/imports in `genomeos/surfaces/fit.py`.

**Interfaces:** `genomeos.surfaces.config.FitConfig` becomes the defining class; `genomeos.surfaces.fit.FitConfig` remains the same exported class. Export these unchanged names from both modules: `SEED`, `LIKELIHOODS`, `LENGTHSCALE_PRIORS`, `NUTS_SAMPLERS`, `APPROXIMATIONS`, `INDUCING_PLACEMENTS`, `JITTER`, `MIN_SPACING_FRACTION`, `MAX_INDUCING_FRACTION`, `REFERENCE_DESIGN`, `EARTH_RADIUS_KM`, `LENGTHSCALE_REGIONS`, `MIN_LENGTHSCALE_ANCHOR_KM`, `MAX_LENGTHSCALE_ANCHOR_KM`. Keep private legacy `_EPS` and `ConvergenceError` in fit.py. Geometry algorithms are not moved.

- [x] **RED:** capture the legacy evidence above, then add the failing new-module/import test and full default/invalid-configuration parity assertions. The initial new-module import must fail for the expected missing file.

  ```python
  from dataclasses import asdict
  import genomeos.surfaces.config as config
  import genomeos.surfaces.fit as fit_module

  def test_existing_import_path_is_the_same_configuration_class():
      assert fit_module.FitConfig is config.FitConfig
      assert asdict(config.FitConfig()) == asdict(fit_module.FitConfig())
      assert config.FitConfig().draws == 500
      assert config.FitConfig().tune == 1000
      assert config.FitConfig().chains == 4
      assert config.FitConfig().max_rhat == 1.05
      assert config.FitConfig().min_ess == 200.0
  ```

  Run `"$AF_PYTHON" -m pytest tests/test_surface_config.py -q`. Compare every dataclass default and `__post_init__` branch to the captured parent source, not only the five values shown. Parameterize invalid likelihood, approximation, placement, sampler, HSGP expansion, lengthscale sigma/prior, R-hat bound and target acceptance.
- [x] **GREEN:** move the existing class and named constants verbatim, including scientific comments, into the focused configuration module with a design §§5, 7 docstring and `from __future__ import annotations`. Explicitly import/re-export names in fit.py. The essential compatibility seam is:

  ```python
  from genomeos.surfaces.config import FitConfig as FitConfig
  from genomeos.surfaces.config import SEED as SEED
  ```

  Use the same explicit re-export idiom for the complete list above. Do not alter validators or strip comments to pass the size check.
- [x] **Verify:** run `tests/test_surface_config.py`, `tests/test_surface_fit.py` and `tests/test_crossval.py`. Load the pre-change trusted fit and compare its three legacy numeric outputs and prior-frequency SD to `cache-baseline.npz` with exact array equality. This tests a real old module reference against its parent-loaded control; a new pickle round trip alone does not.
- [x] **Gate/review/commit:** run every global gate, inspect staged paths, and commit `refactor: isolate surface configuration refs #191`. Record focused outputs, legacy equality and remaining Task 2/3 work. Independent review must check there is no scientific/default change.

**Completed evidence:** `c74b617` passes 14 configuration tests, 68 fitter/cross-validation
tests, 40 smoke tests and the listed lint/contract/module/privacy/whitespace gates. All four
legacy numeric arrays match the parent-loaded cache control exactly. Independent review
approved spec compliance and task quality with no Critical/Important findings; five existing
uncaptured inducing warnings remain a deferred test-noise concern. The separate direct-import
cycle is tracked in [#199](https://github.com/bschilder/genomeOS/issues/199); the established
`fit.load_fit` seam works. Fresh-fit and new-interface round-trip checks remain Task 3 gates.
Neither this milestone nor parent [PR #197](https://github.com/bschilder/genomeOS/pull/197)
completes the full modeling program.

### Task 2: Pure unseen-cohort parameter composition

**Scientific contract:** reproduce the fitted observation equation while sharing one cohort effect across all sites of that new cohort. Analytical logits and seeded identity tests are acceptance evidence, not model calibration. The public GP adapter and count scorer are consumers. Missing effects or metadata are refused rather than guessed.

**Files:** create `genomeos/surfaces/observation.py` and `tests/test_observation_parameters.py`.

**Interfaces:** implement `SurveyQueries`, `ObservationModelMetadata`, `ObservationParameters` and `compose_unseen_observations` with the exact fields, shapes and signature in the spec. This task has no PyMC import. `ObservationParameters.mean_draws` and `.concentration` are the public scorer inputs; query order and draw IDs travel with them.

- [ ] **RED — explicit analytical contract:** write the following complete no-noise case first, then run it to observe the expected missing-module/function failure.

  ```python
  import numpy as np
  from scipy.special import expit
  from genomeos.surfaces.observation import (
      ObservationModelMetadata, SurveyQueries, compose_unseen_observations,
  )

  def test_design_contrasts_use_the_actual_fitted_reference():
      queries = SurveyQueries(
          observation_ids=("a", "b"), cohort_ids=("new", "new"),
          sampling_designs=("healthy_reference", "population_random"),
          lat=(0.0, 1.0), lon=(0.0, 1.0),
      )
      metadata = ObservationModelMetadata(
          convention="new_cohort_count_v1",
          fitted_designs=("healthy_reference", "population_random"),
          training_cohort_ids=("training",), cohort_effect_applied=False,
          nugget_applied=False, likelihood="beta_binomial",
      )
      result = compose_unseen_observations(
          np.array([[-2.0, -2.0], [-1.0, -1.0]]),
          draw_ids=((0, 0), (0, 1)), queries=queries, metadata=metadata,
          design_effect_draws=np.array([[0.5], [1.0]]),
          cohort_sd_draws=None, nugget_sd_draws=None,
          concentration_draws=np.array([20.0, 40.0]), seed=42,
      )
      np.testing.assert_allclose(result.mean_draws, expit([[-2.0, -1.5], [-1.0, 0.0]]))
      np.testing.assert_array_equal(result.concentration, [[20.0, 20.0], [40.0, 40.0]])
      assert result.draw_ids == ((0, 0), (0, 1))
      assert result.queries == queries
  ```

  Run `"$AF_PYTHON" -m pytest tests/test_observation_parameters.py -q` and record RED before implementation.
- [ ] **RED — noise mechanics and refusal tests:** add exact seeded-reference tests using two streams, including all four cohort/nugget fitted/omitted combinations:

  ```python
  cohort_seed, nugget_seed = np.random.SeedSequence(42).spawn(2)
  expected_cohort_z = np.random.default_rng(cohort_seed).normal(size=(2, 2))
  expected_nugget_z = np.random.default_rng(nugget_seed).normal(size=(2, 3))
  ```

  Assign three explicit query IDs in unsorted order to two cohort IDs; calculate expected sorted-ID index maps and compare the actual logits/means. Verify identical cohort increments at two sites, independent nugget increments, same output after row permutation/inversion, and unchanged nugget draws when cohort effects are omitted. Repeat with zero scales and binomial `None` concentration. Compare returned arrays to `CountPredictive` analytical log masses for two identical draws at p=0.2, AC=1, AN=4: expected probability `4 * 0.2 * 0.8**3`.

  Parameterize exact refusals: empty/mismatched queries, repeated observation ID, blank/nonstring IDs, boolean/nonfinite/out-of-range coordinates, duplicate/boolean/fractional draw coordinates, unsupported convention/likelihood, duplicate or absent fitted designs, seen cohort, missing or extra effect arrays, wrong `(D,N)/(D,K)/(D,)` shapes, NaN/inf, negative scales, nonpositive concentration and invalid seeds. Test input-copy isolation and `setflags(write=True)` refusal on returned arrays. Test extreme finite logits without epsilon clipping.
- [ ] **GREEN — implementation:** implement the frozen contracts and shape/domain checks before randomization. Store immutable arrays using a bytes-backed copy. Build canonical maps with exact labels and separate streams:

  ```python
  cohorts = tuple(sorted(set(queries.cohort_ids)))
  observations = tuple(sorted(queries.observation_ids))
  cohort_index = np.array([cohorts.index(value) for value in queries.cohort_ids])
  observation_index = np.array([observations.index(value) for value in queries.observation_ids])
  cohort_seed, nugget_seed = np.random.SeedSequence(seed).spawn(2)
  ```

  Use dictionaries for the actual O(N) index mapping, not repeated `.index` at scale. Form one zero reference-design column plus recorded contrasts; add only declared effects using the fixed stream identities; `scipy.special.expit` produces means. Broadcast positive scalar concentration draws to `(D,N)` only when the fitted likelihood is beta-binomial. Return validated immutable `ObservationParameters`; no replicated count sampling or I/O here.
- [ ] **Verify:** run `tests/test_observation_parameters.py` and `tests/test_predictive.py`. Confirm importing the pure module does not import PyMC or a serving/storage module. Verify all analytical and deliberately malformed fixtures; record exact failures fixed rather than counting skips as evidence.
- [ ] **Gate/review/commit:** run every global gate, inspect staged paths, and commit `feat: compose unseen-cohort predictive parameters refs #191`. Independent review checks scientific effect semantics and immutable/aligned contracts before the integration task starts.

### Task 3: Fit metadata, named latent draws and public GP adapter

**Scientific contract:** expose the existing fitted approximation's observation distribution without guessing its reference design or losing posterior identity. Controlled xarray fixtures, a real fit and actual old-cache comparison are acceptance evidence. This enables later buffered GP benchmarking but does not claim empirical improvement.

**Files:** create `genomeos/surfaces/observation_prediction.py` and `tests/test_observation_prediction.py`; modify `genomeos/surfaces/fit.py`, `genomeos/surfaces/persistence.py`, `tests/test_surface_fit.py` and `docs/global-af-benchmark.md`.

**Interfaces:** consume Task 2's four public contracts. Add `SurfaceFit.prediction_metadata: ObservationModelMetadata | None = None` and `SurfaceFit.predict_new_cohort_parameters(queries: SurveyQueries, *, seed: int = SEED) -> ObservationParameters`. The focused adapter exports `predict_new_cohort_parameters(fit: SurfaceFit, queries: SurveyQueries, *, seed: int = SEED) -> ObservationParameters`; use `TYPE_CHECKING` for the class import to avoid a circular runtime dependency. No benchmark consumer imports its private helpers.

- [ ] **RED — actual fit capability:** extend the existing module-scoped `fit` fixture tests, without lowering its convergence thresholds:

  ```python
  def test_fit_records_actual_prediction_metadata(fit):
      metadata = fit.prediction_metadata
      assert metadata.convention == "new_cohort_count_v1"
      assert metadata.fitted_designs == ("population_random", "healthy_reference")
      assert metadata.training_cohort_ids == ("cohort-0", "cohort-1", "cohort-2", "cohort-3")
      assert metadata.cohort_effect_applied is True
      assert metadata.nugget_applied is False
      assert metadata.likelihood == "beta_binomial"
  ```

  Run this test first and record missing-attribute RED. In the existing single-design test also assert its actual reference, including a case where the configured reference is absent; do not assume the configured reference was fitted.
- [ ] **RED — adapter alignment:** controlled xarray posteriors have chain coordinates `[1,0]`, draw coordinates `[3,2]`, deliberately transposed variable dimensions, explicit design positional coordinates, and distinguishable scalar values per draw. Require output draw IDs `((0,2),(0,3),(1,2),(1,3))` and hand-computed aligned means/concentrations. Patch only the PyMC draw boundary to return known latent logit arrays; assert sampled query coordinates are canonically ordered and deduplicated. Add missing-variable/node, wrong event-axis, repeated/different coordinate labels, unsupported design and seen-cohort refusals; assert refusal happens before calling the expensive draw boundary.
- [ ] **GREEN — fitted provenance and graph:** populate actual metadata at the existing sole `SurfaceFit` construction, using the fit's `design_levels` before dropping its reference, sorted training cohorts and actual fitted flags. Add the named latent expression alongside the existing frequency expression:

  ```python
  pm.Deterministic("latent_logit_pred", f_pred_expr)
  pm.Deterministic("freq_pred", pm.math.invlogit(f_pred_expr))
  ```

  Leave the old frequency expression, prior sampling, likelihood, `_frequency_samples` and legacy methods otherwise unchanged. Add only the small delegating public wrapper in fit.py; the adapter owns extraction/canonicalization.
- [ ] **GREEN — canonical draw extraction:** validate capabilities/queries before sampling, canonicalize exact coordinate pairs (including the spec's antimeridian/pole equivalences), evaluate unique points once and expand to submitted query order. Extract posterior variables using named dimensions and canonical coordinate selection, with explicit checks before the following operation:

  ```python
  ordered = variable.sel(chain=sorted_chains, draw=sorted_draws)
  ordered = ordered.transpose("chain", "draw", *event_dimensions)
  values = ordered.to_numpy().reshape(n_chains * n_draws, *event_shape)
  ```

  `sorted_chains`, `sorted_draws`, event dimensions and event shapes come from validated actual coordinates, not presumed lengths. Compare latent/effect coordinate sets and labels, require exactly one positional axis for design contrasts and none for scalar effects. Missing cohort/nugget draws are errors when metadata says fitted; when omitted pass `None`. Call `compose_unseen_observations` with matched draw IDs and the original queries.
- [ ] **Verify — real integration and scorer:** on the existing real fitter, request two unseen-cohort sites and compare recorded draw IDs to canonical posterior chain/draw coordinates. Compare repeated/permuted query outputs after ID alignment. Include duplicate coordinates, antimeridian equivalence and exact poles with controlled adapter fixtures. Feed real-fit synthetic query parameters into `CountPredictive`; use small denominators and a few points for finite diagnostics rather than a huge CPU CDF workload. Analytical tests, not marginal coverage, establish shared-cohort mechanics.
- [ ] **Verify — genuine legacy and cache compatibility:** first load the pre-Task-1 trusted cache and prove its legacy outputs and prior-frequency SD remain exactly equal to `cache-baseline.npz`; the new method must refuse its absent metadata/node. Separately repeat the same-seed fresh-fit calculation and compare against every captured `legacy-before.npz` array. A mismatch blocks the claim of unchanged behavior and is investigated. On the real new fit, save/load and compare metadata and new-interface predictions exactly; assess unchanged legacy predictions in the separate fresh and cached comparison arms above. Preserve any fresh-versus-cache discrepancy explicitly rather than calling it equality. Retain cache format 1 only if these old/new readability checks pass; document capability refusal rather than inventing metadata.
- [ ] **Document:** add the exact public consumer example and limitations to `docs/global-af-benchmark.md`:

  ```python
  parameters = fitted.predict_new_cohort_parameters(queries, seed=42)
  predictive = CountPredictive(parameters.mean_draws, concentration=parameters.concentration)
  diagnostics = predictive_diagnostics(predictive, ac, an, seed=42)
  ```

  Define `fitted` as a newly fitted `SurfaceFit`, `queries` as required `SurveyQueries`, and AC/AN as separately validated matching-order observation counts. Explain actual reference vs configured reference, seen-cohort refusal, named posterior identity, legacy cache capability and unchanged resident/footprint/approximation/publication gates. Do not advertise this as observed accuracy improvement.
- [ ] **Gate/review/commit:** run focused config/composition/adapter/fitter/scorer tests and every global gate. After independent review and any verified fixes, run full `"$AF_PYTHON" -m pytest` and all CI commands on the final code. Commit `feat: expose observation-aware GP parameters closes #191` only when every #191 acceptance item is met; otherwise use `refs #191` and describe the remaining item. Open a coherent PR advancing #189, with expert-review questions about the target, effect identifiability and joint semantics. No production surface has changed, so do not manufacture a map solely for this interface PR.

## Completion and next work

The slice is complete only when its public contract, all refusals, preserved legacy behavior, real-fitter alignment, old/new cache checks and independent review are evidenced. Document any ruling with its cost if wrong. This does not complete the full research program.

Next, design the GP benchmark adapter against this reviewed contract: lossless input validation, frozen buffered splits, explicit per-chain versus total draw configuration, all attempt/convergence records, one logged doubled-draw/tuning retry, and balanced fail-closed count reporting. Data qualification and genuinely sealed external confirmation remain prerequisites to a real-world improvement claim.
