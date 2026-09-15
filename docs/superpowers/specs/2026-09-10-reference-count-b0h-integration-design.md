# Reference-count B0H integration and artifact contract

Root-adopted integration clarification of #211, extending the adopted B0H design's
“Benchmark integration and immutable evidence” section; Atlas §§5, 7–8, 12.
Adopted for offline integration implementation. No experiment admission.
Source inspected: `c75e0b68c9a7ee4b79ed7280b8434e70cc13e921` and the corrected
comparison audit. The separate SBC runner is outside this document.

## 1. Scientific contract and scope

1. Objective: test whether source-population heterogeneity improves withheld
   count predictions over pooled B0 after the separately recorded calibration gate.
2. Output now: an exact CLI/artifact contract and acceptance cases. Drafting
   supplies no calibration, runtime, convergence, or improvement evidence.
3. Component: extend `scripts/benchmark_reference_counts.py`; consume the public
   B0H config, fit, prediction, and convergence-error contracts unchanged.
4. Assumptions/refusals: preserve training-only fitting, declared dependence,
   unknown metadata, numerical/convergence gates, all unavailable rows and failures.
   Root and later research reviewers consume these artifacts; serving does not.

The real comparison remains both fixed prior tracks, each on the unchanged
two stages × two count kinds × seeds 42/43/44 × five folds. Mean prior is
Beta(1,1); rho priors are separately reported Beta(1,9) and Beta(1,4).
No outcome-selected prior, sampler budget, backend, seed, exclusion, or threshold.
No independent-locus, resident/geographic, global, LD, external, clinical,
release, or promotion claim. Real counts/draws/predictions stay local/untracked.
Fixture-only integration can precede calibration; real fitting cannot precede
the recorded separate protocol/evidence and experiment admission.

## 2. Composition and root-adopted integration choices

Recommended: keep the existing CLI/input/fold/scoring/summary path and add a
narrow B0H fold adapter plus B0H artifact serializer only where needed to keep
modules within the 500-logical-line target. The fold adapter consumes
`Sequence[ReferenceCount]`, `PopulationHeterogeneityConfig`, backend and the
two fit seeds; it returns typed attempt outcomes and an optional accepted
`PopulationHeterogeneityFit`/`ReferenceHeterogeneityPrediction`. It owns no I/O.
The serializer consumes those records, validated score frames and split IDs;
it owns the wire contract below, not fitting or scoring. Name/location are
implementation choices; do not couple to private or SBC-specific attempt code.

Alternative separate CLI duplicates strict parsing, splitting and row ledgers.
Alternative generic model registry adds an abstraction without a second real
extension consumer. Neither changes the selected model/scorer/likelihood.
No new scientific API is needed to expose the fitter's existing outputs.
Import `reference_heterogeneity` and its PyMC stack only after selecting B0H;
B0 startup, help, validation and execution must work without the surfaces extra.

Root personally reviewed this draft and the parent integration section and adopted:

- **Folds:** require `--folds 5` for B0H before fitting; keep B0's existing CLI
  and public fold validation (at least two folds and sufficient components).
  This matches the parent's five fit-stream children. Cost: B0H fixtures need
  five folds, and no reduced-fold B0H debugging run is admitted in this version.
- **Backend:** keep B0's existing SciPy execution. Accept omitted backend or
  explicit `--cdf-backend scipy` on B0 as an assertion of that execution;
  reject explicit `cupy` on B0 before fitting. B0H forwards `scipy|cupy`, default
  `scipy`, unchanged to its public predictor. Root adopted this integration choice;
  the parent had left backend handling on B0 open. It avoids changing the B0
  scientific API or silently ignoring a requested GPU backend. GPU absence or
  backend failure never triggers CPU fallback. Future GPU comparison admission
  freezes the backend before results, with actual hardware evidence.
- **Adopted parent wording clarification:** replace “successful folds only” with
  “accepted fits, including folds that subsequently fail prediction/scoring”.
  Preserve their available arrays/totals/means, paired with the failed fold status
  and no prediction rows. This changes artifact inclusion, not convergence gates
  or comparison completion. Cost: consumers must join fold status before using
  posterior files as comparison evidence. This explicitly changes the parent's
  inclusion wording; an accepted fit still does not imply a successful fold.

`--model pooled_beta_counts|B0H_population_heterogeneity` defaults to B0.
Existing required prior flags supply B0H mean shapes; B0H additionally requires
both rho flags. Reject explicitly supplied rho/draws/tune/chains/target-accept
flags on B0, including values equal to B0H defaults. Parse their absence distinctly.
B0H defaults are draws=500, tune=1000, chains=4, target_accept=0.9; validate through
the public config. Root `--seed` stays the existing split/PIT seed input.

## 3. Fold execution and failure accounting

For B0, preserve the two-child seed construction. For B0H, create a fresh
`SeedSequence(root).spawn(3)`; children 0/1 retain the original split/PIT
consumers, and child 2 spawns five fold children in returned fold order.
Each fold child spawns initial/retry children; each seed uses
`generate_state(1, dtype=np.uint32)[0]` converted to Python int. Record every
planned seed, even unused retry seeds. Counts never enter seed derivation.

Validate inputs/configuration/dependency structure before creating outputs.
Within each planned fold, retain unavailable testing IDs before any fit.
A no-scoreable-test fold is `infeasible` without fitting. Other fit/predict
infeasibilities retain the existing `infeasible` status; structural/numerical
failures are `failed`. Missing training variants never receive prior-only output.
Only a `HeterogeneityConvergenceError` raised by the fit call admits one retry:
double initial draws/tune, retain chains/target_accept/priors/rows/gates and use
the recorded retry seed. Nonfinite diagnostics trigger retry only through this
public typed error; do not infer retryability from exception messages.

Separate fit acceptance from fold completion. Once fitting returns its validated
fit, later prediction or score-validation failure does not relabel the fit as
nonconvergent and does not resample. Preserve the accepted fit diagnostics.
Append predictions only after the entire fold's prediction identity alignment
and diagnostic frame validate; never publish partial variants. Under the adopted
wording clarification, retain each accepted fit's arrays and posterior TSV rows
even if later prediction/scoring fails; retain its failed fold status explicitly.
A convergence exception exposes diagnostics, not posterior arrays;
never fabricate arrays, totals presented as fitted results, or absent diagnostics.

Catch the existing scientific errors plus typed convergence errors inside the
fold boundary and continue later folds. A generic RuntimeError, dependency/import
failure, KeyboardInterrupt, or process termination is an execution interruption,
not a scientific refusal to manufacture as a complete five-fold ledger.
At the terminal ledger, every test row is scored, unavailable, infeasible, or
failed. Unavailable rows retain `unavailable_denominator` even in failed folds.
Summary expected IDs and operational weighting remain unchanged.

## 4. Versioned manifest and file set

B0 retains manifest schema_version=1, its existing configuration/seeds/package
fields, TSV headers and six-file set. Explicit B0 model/scipy assertions do not
add fields. Same inputs/runtime yield identical scientific bytes to the legacy
path; source hashes and Git metadata are expected to change with source changes.

B0H uses `manifest.json` schema_version=2. It has all v1 top-level fields plus
`model` and `runtime`; model is exactly `B0H_population_heterogeneity`.
Configuration retains existing keys, adding `model`, `rho_prior_alpha`,
`rho_prior_beta`, `draws`, `tune`, `chains`, `target_accept`, `cdf_backend`.
`prior_alpha/beta` explicitly mean the B0H mean prior; `seed` is the root seed.
`seeds` retains root/split/pit_by_fold and adds `fit_by_fold`, mapping each
literal split ID to exactly `{initial: int, retry: int}`.

Completed publication has exactly eight files: the six B0 filenames plus
`fit_diagnostics.json` and `posterior_draws.npz`. Both B0H additions exist even
with zero successful folds. `output_files` fingerprints exactly the seven
non-manifest files with `{sha256, size_bytes}` from their final bytes.
The manifest never fingerprints itself. JSON is UTF-8, sorted object keys,
indent=2, ensure_ascii=False, allow_nan=False, with one terminal newline.

`science_source_sha256` retains the B0 source entries and adds actual consumed
B0H types, fitter, likelihood, adapter/serializer and conditional CuPy scorer.
Every module path must resolve to its expected checkout source before hashing;
do not hash a lookalike checkout instead of imported code. Include additional
local dependencies actually introduced by the adapter. Source/Git failures
remain prepublication errors. No private absolute paths enter artifacts.
`package_versions` retains numpy/scipy/pandas and adds pymc/pytensor/arviz/xarray/
numpyro/jax/jaxlib, plus cupy when selected. Required distribution provenance
must be established, not guessed from the lock file.
`runtime` has exactly `python_version`, `jax_backend`, `cdf_backend`, where each
value is `{status: available|unavailable, value: string|null, reason: string|null}`.
Available requires an observed nonempty value and null reason; unavailable
requires null value and nonempty reason. Record effective backend observations
when obtained through public runtime interfaces; a requested value alone is not
proof of device execution. Do not expose device UUIDs, environment or credentials.
The current fit and scoring results do not expose execution-placement evidence:
record `jax_backend` and `cdf_backend` as unavailable with explicit reasons.
Neither a selected flag nor a later default-device probe establishes where a
fit ran. Do not change scientific APIs just to populate these fields; future
real GPU experiment admission records separate hardware/execution evidence.

## 5. Diagnostics JSON v1

Top-level fields: `schema_version: 1`, `model`, `folds`. The array has every
planned split exactly once in returned fold order; field sets below are exact.

| Record | Fields and types |
| --- | --- |
| Fold | `split_id: str`, `status: completed|infeasible|failed`, `failure_phase: null|preflight|fit|prediction|scoring`, `reason: str|null`, `posterior_status: retained|not_available`, `posterior_prefix: str|null`, `attempts: list` |
| Attempt | `attempt: initial|retry`, `seed: int`, `draws: int`, `tune: int`, `chains: int`, `target_accept: float`, `status: not_attempted|accepted|convergence_failed|infeasible|failed`, `reason: str|null`, `divergence_count: int|null`, `diagnostics: list` |
| Variant diagnostic | `variant_id: str`, `max_rhat: finite float`, `min_bulk_ess: finite float`, `min_tail_ess: finite float` |

Every fold contains exactly two attempt slots in initial/retry order, with initial
budgets and doubled retry draws/tune. A planned slot is not execution. Unused initial reason is
`fold_preflight_infeasible`; unused retry reason is `initial_accepted`,
`initial_not_retryable`, or `initial_not_attempted` as applicable. Unused slots
have null divergence_count and empty diagnostics, never zero-success defaults.
Accepted slots have null reason, divergence_count=0, and complete sorted
diagnostics from the fit. Failed attempted slots have nonempty explicit reason;
typed convergence failure uses its reason and only the finite diagnostic subset
and global divergence count actually retained by that exception. Other errors
use `ExceptionType: message`, null divergence_count and empty diagnostics.
Diagnostic IDs are unique and sorted, and must be a subset of the available
training variant IDs; absence means unavailable evidence, not an omitted pass.

Completed fold: null failure_phase/reason and `posterior_status=retained`.
Noncompleted fold: nonempty reason and exact failing phase. No accepted fit
means `not_available`; any accepted fit means `retained`, including later failed
folds. Only retained fits have a nonnull posterior_prefix.
Completed comparison means all folds completed, not merely all fits accepted.

## 6. Posterior NPZ and TSV

For fold index i=0..4, prefix is `fold_0000` through `fold_0004`, independent of
literal IDs. Diagnostics map each prefix to its literal split. Each retained
fit has exactly three keys: `<prefix>__mean_draws`, `<prefix>__rho_draws`,
`<prefix>__variant_ids`; no other keys. ZIP member names add `.npy` only.
Arrays use C-contiguous little-endian float64 (`<f8`) with shape
`(accepted_chains, accepted_draws, variant_count)`, no warmup or flattened axes.
Mean/rho share the fit's canonical sorted literal variant ordering and each
value is finite and strictly inside (0,1). Variant IDs are shape `(variant_count,)`,
little-endian fixed-width Unicode `<U{L}`, L=max literal character count, with
exact lossless round-trip required (including `NA`, `001`, non-ASCII and punctuation).
Do not sanitize labels into filenames, truncate, coerce to object, or normalize IDs.

Write keys lexicographically, NPY format 1.0 with allow_pickle=False in ZIP_STORED
members with fixed timestamp 1980-01-01 00:00:00, empty comment/extra, and fixed
create_system=3, external_attr=(0o600 << 16), internal_attr=0, flag_bits=0 and
create_version=extract_version=20 (ZIP64-required fields excepted). An empty
accepted-fit set produces a valid empty archive; no pickle payload is written.
Readers use `np.load(..., allow_pickle=False)` without extraction and validate
exact keys, dtypes, dimensions, IDs and the manifest/diagnostics mapping. Refuse
extra members, duplicate names, missing companions, object arrays, or mismatches.
Serialization must be byte-repeatable for identical records on the pinned runtime.

B0H `posteriors.tsv` columns, in exact order:
`split_id, variant_id, training_observation_count, training_ac, training_an,
posterior_mean_mean, posterior_rho_mean` (tab-delimited).
Rows sort by literal `(split_id, variant_id)` and contain every fitted variant
of each retained fit, including training variants absent from its test rows.
Training totals are Python integer sums of positive-AN training rows only,
copied from `fit.training_counts`. Means are unweighted arithmetic means across
all chain/draw positions of the respective retained parameter arrays. Mean is
the model's population-frequency hyperparameter; rho is modeled heterogeneity.
Neither is a pooled AC/AN estimate, a test-population realization, nor a conjugate
Beta shape. Keep existing TSV quoting/newline/float rendering. Empty is header-only.

## 7. Publication boundary and literal acceptance cases

Keep exclusive new-directory creation; no overwrite/resume/recovery framework.
Write the manifest last, after every referenced file is complete and hashed.
A missing/invalid manifest or hash/file-set mismatch is interrupted publication,
never a completed comparison. No per-fold ledger is promised after process death.
Exit 0 means published comparison_complete=true; exit 2 with a valid manifest
means published incomplete scientific comparison. Nonzero without a valid
manifest is validation/execution/publication failure; consumers inspect artifacts.

- Legacy B0 default and explicit model/scipy produce equal scientific bytes;
  B0 runs without PyMC and rejects every explicit rho/sampler flag and cupy.
- B0H rejects absent rho priors, invalid settings and non-five folds before
  sampling; five-fold synthetic fixture preserves every unavailable row.
- Same root yields literal legacy split membership/PIT streams; initial/retry
  seeds follow only child 2, with no test-count effect on fit config or draws.
- Initial convergence failure retains both attempt outcomes; retry doubles only
  draws/tune. Final convergence failure emits no predictions/posteriors and
  later folds run. Structural/numerical failure never retries.
- Accepted fit plus predictor/score failure remains accepted in its attempt,
  marks all scoreable rows appropriately, retains its complete accepted posterior
  evidence with failed fold status and no predictions; unavailable rows remain unavailable.
- Partial finite convergence diagnostics preserve their exact subset and null
  missing evidence. No failure is reconstructed as posterior arrays.
- Literal IDs, variant ordering, training totals, means, retry dimensions and
  NPZ companion mapping reconcile; malformed/object/extra arrays are refused.
- Repeated mocked fixture output has identical bytes and fingerprints; source
  resolution, publication failure and missing backend never masquerade as success.

These are future integration tests, not executed evidence. Existing real synthetic
NUTS/oracle tests and separate calibration admission remain mandatory and unrelaxed.
