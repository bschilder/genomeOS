# Global Allele-Frequency Modeling Implementation Plan

> **For agentic workers:** Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` task by task. Checkboxes record implementation, not scientific validation.

**Goal:** Improve present-day resident allele-frequency predictions worldwide, at independently validated resolution, with calibrated uncertainty and explicit refusal.

**Architecture:** Reviewed observations and optional covariates feed pure offline fitters. Frozen dependency-aware benchmarks compare statistical, graph, and neural candidates. Only independently confirmed candidates produce new immutable surface artifacts; serving remains read-only.

**Tech stack:** Existing Python/Pandas/NumPy/SciPy/PyMC stack, versioned JSON/Parquet research artifacts; optional neural/GPU dependencies only when their experimental gate opens.

**Spec:** Owner-approved September 9 conversational plan; Atlas design §§4–8, 12–13; [research synthesis](../../research/genomeos-model-research-2026-09-09.md) and [full-text notes](../../research/genomeos-anandkumar-fulltext-notes-2026-09-09.md). Umbrella issue [#189](https://github.com/bschilder/genomeOS/issues/189).

## Global constraints

- Primary target: present-day residents. Origins and historical populations are distinct later outputs.
- Balanced region/variant-group performance, not cohort-size-weighted headline accuracy.
- The owner authorized needed RunPod resources and GPU-supported alternatives (September 9). Profile measured bottlenecks, validate GPU results against a CPU reference, include transfer/setup costs, prefer US/Canada datacenters, and stop task-owned resources after use. Compute authorization does not grant new data access/export rights.
- Public reproducible benchmarks and controlled-access tracks remain separately governed.
- Observations and surfaces are never conflated. No inference on the serving path.
- Artifacts are immutable, keyed by `(variant_id, model_version, data_version)`.
- Masked cells remain excluded from aggregates, with the excluded fraction returned.
- Missing coordinates, denominators, ascertainment, population identity, dates, or permissions are never invented.
- Existing clinical golden tests and server-side variant-class policy remain unchanged.
- Pure science functions have no filesystem, network, HTTP, environment, or UI dependencies.
- Deterministic given explicit configuration and data version; stochastic modules declare `SEED = 42`.
- Development seeds: 42, 43, 44. Five outer / three inner folds when feasible; infeasible tracks are reported, not silently relaxed.
- Primary geographic buffer: 300 km over sampling footprints; 100/1,000 km sensitivity tracks.
- Source-derived genotype structure, LD, imputation, feature selection, calibration, and early stopping stay inside training partitions.
- Each implementation change requires failing-test evidence, focused verification, smoke, privacy inspection, and a dedicated-branch commit. No unrelated checkout changes are staged.

## Program milestones and evidence gates

### WP0 — Target and inventory

Freeze source snapshot, releases, configurations, and existing outputs. Audit counts, denominators, measurement type, geographic support, date support, recruitment, population target, and source overlap. Record independent study/population/locus counts and unresolved metadata. Do not certify resident representativeness from reference-panel membership or recruitment labels. Keep allele, carrier, and phenotype data distinct.

**Exit:** traceable qualified input inventory, explicit exclusions, and an identifiable target for each proposed real-data benchmark. A schema-valid table alone does not satisfy this gate.

### WP1 — Benchmark foundation

Build a dependency graph for studies, participants/kin where known, reused panels/tables, and derived resources. Freeze local-interpolation, buffered-region, all-variant new-region, whole-locus, and conditional-imputation tracks separately. Reserve independent external confirmation before tuning. Nested model selection may only use training/development evidence.

Score integrated count predictive probabilities, predictive coverage/width, discrete calibration, point error, and joint-site quantities. Keep the current median-based binomial score explicitly legacy. Retain every fold, failure, retry, and refusal. Studies are averaged within represented region/variant-group cells, then cells equally; report absent cells and rare-allele/denominator/distance strata.

**Exit:** analytical score tests, deliberate-leakage tests, deterministic manifests, reproduced current-model baseline, and genuinely sealed external data. A fixture runner is engineering evidence only.

### WP2 — Observation-aware inference

Keep beta-binomial likelihoods and distinguish latent uncertainty, recruited-cohort variation, chromosome sampling, and supported assay/location uncertainty. Average probabilities over documented footprints. When only a radius is available, explicitly compare uniform-area and population-weighted assumptions; neither is reported recruitment truth.

Prediction accepts survey design and cohort identity, preserving shared new-cohort effects. Audit missing reference designs and micro-scale variation. Compare HSGP/inducing uncertainty to tractable full-GP and simulated references. Keep convergence thresholds; allow one logged retry with doubled draws/tuning, then mark failure.

**Exit:** observation-model correctness and paired benchmark improvement without hidden changes to the target.

### WP3 — Covariate admission

Acquire terrain/elevation/water, then demographics, climate normals, locus-relevant pathogens, modern migration/displacement, and finally qualified historical/paleoclimate layers. Biodiversity and historical events need narrow hypotheses and qualified support; exotic environmental signals are not mandatory inputs.

**Owner clarification, September 10:** climate includes three distinct tracks:
present-day, historical and ancient, with ancient spanning human divergence from
non-human primates through the present. Modern normals are only a first bounded
candidate, not completion of this scope; a last-glacial-cycle reconstruction does
not cover the entire evolutionary interval. Audit the actual spatial/temporal
support, uncertainty and gaps of each source family before selecting experiments.
Never infer continuous high-resolution coverage by stitching incompatible products.
See the [climate qualification note](../../research/climate-covariate-qualification-2026-09-10.md).

Version source, checksum, units, support, valid/available time, uncertainty, missingness, upstream dependencies, and terms. Cesium display assets are not a scientific covariate store. Offline extraction needs scientific semantics and asset-specific permission.

Compare baseline, added family, missingness-only, structured negative control, and incremental value after genomic structure, on unchanged evaluation populations. Record rejected layers.

**Exit:** reproducible extraction and out-of-region incremental predictive value.

### WP4 — Statistical/shared/connectivity ladder

B0 pooled uncertain count model; B1 local smoother and regularized covariate regression; B2 frozen/current then observation-aware GP; B3 shared spatial factors with variant-specific residuals; B4 sparse local/nonlocal graph model. Inner-fold B3 rank candidates: 4, 8, 16, 32. Learn genetic connectivity only from permitted training data; effective migration is not a measured movement count.

**Exit:** improvement on region and locus holdouts without erasing rare/localized alleles; learning curves versus independent population and locus-block counts.

### WP5 — Neural challengers

N0 sparse-context graph/conditional-process comparator; N1 irregular encoder, spherical global operator, local branch, stochastic decoder; N2 blockwise CoDA-NO-style variable-field attention. Use explicit count likelihoods and coherent stochastic fields, without claiming ensembles are exact posteriors. No dense interpolated whole-dataset training truth and no whole-genome all-pairs attention.

Ablate local/global branches, shared/variant components, covariates, pretraining, and joint/marginal uncertainty. Match pretraining access and tuning; report information-budget experiments separately. Single-GPU pilots precede multi-GPU scaling when measurements justify it, with end-to-end costs and US/Canada deployment preferences.

**Exit:** beat equally informed B3/B4 on count prediction, calibration, local contrasts and joint-field checks; otherwise retain the statistical winner.

### WP6 — Multiallelic, LD, GPU

Separate cross-variant sharing, complete multinomial allele observations, and haplotype dependence. Incomplete allele lists do not become zeros. Begin with short blocks and compatible individual-level data; marginal frequencies alone do not identify LD. Preserve valid joint probabilities/covariance.

Use the user's **local CuGen implementation at `/Users/bschilder/code/cugen`**, not pg_gpu. The checkout inspected on September 9 is `03df1688abf52d295bd85d47f1aca6130440b553` (package version `0.1.7`); pin and record the exact revision actually used by each experiment. Its `cugen.ld.ld_matrix` interface already provides unphased `r`/`r2`, so inspect and reuse it rather than substitute another library. Related-work audits do not change this implementation choice.

Validate CuGen counts and declared LD definitions against an independent CPU reference, including missingness, orientation, rare/monomorphic sites, subsets, ploidy and supported dosage formats. Start with explicitly requested unphased `r`/`r2`; CuGen's two-bit representation does not retain observed haplotype phase. Treat estimated `D`/`D'` as a separate, later admission decision. Cache offline by data/sample/block/statistic/version. Separate conditional imputation gains from geographic extrapolation without local genotypes.

**Exit:** numeric equivalence, complete-workflow speedup, and task-specific predictive gain.

### WP7 — Temporal/origin pilot

Qualified regional LCT/MCM6 plus neutral controls. Stochastic migration/drift first; selection separately ablated. Demographic variables are uncertain priors, not reproductive migration or effective population size. Ancient likelihoods preserve pseudohaploidy, damage/contamination, date distributions, kin/site effects, and cross-panel deduplication.

Introduce explicit calendar time; legacy modern=0 remains date-unspecified, not today's survey date. Infer history by probabilistic smoothing, never deterministic reverse migration or relocation of diaspora counts. An FNO forward-simulator surrogate is optional only after exact reference and surrogate-error checks.

Historical and ancient climate features must integrate uncertainty in climate,
dating and population location; present coordinates are not ancestral trajectories.
Use time-appropriate paleogeography and keep source time slices distinct from
interpolated model output. Do not assume a present-day variant existed throughout
the evolutionary interval. Separate retrospective reconstruction with later data
from forward prediction using only information available at its declared cutoff;
test independent sites/time windows and climate-family ablations accordingly.

**Exit:** independent site/time validation and modern-prediction ablation; regional feasibility is not a global historical claim.

The [CLUES2 full-main-text methods note](../../research/temporal-genetics-methods-2026-09-10.md)
records the direct-likelihood/genealogy tradeoff and proposed temporal controls;
its supplement remains unread and no temporal implementation is admitted by it.

## Public interfaces and publication

The eventual adapter contract is `fit(training_data, features, connectivity, config)`, `predict_latent(model, population_queries)`, `predict_observations(model, survey_designs)`, and `evaluate(predictions, observations, benchmark_manifest)`. Preserve current `fit_surface` through an adapter; do not expose private PyMC implementation as a shared interface.

Introduce research-side contracts before production schema changes. Add shared-fit hashes over every co-fitted variant/data/feature/split/weight and coherent draw IDs. Preserve old artifacts and legacy metadata honestly. Neural support requires a reviewed contract extension: ensemble disagreement must never be relabeled posterior contraction.

Shadow releases show observations, inference, uncertainty, support and validation separately. Promotion is per supported variant family/region. No restricted data/model export unless specifically permitted; All of Us data are never served by genomeOS.

## Promotion defaults

Freeze before challenger comparisons: ≥5% lower balanced macro MAE against the strongest eligible baseline; positive integrated-log-score improvement with paired dependency-aware 95% uncertainty excluding zero; predictive coverage at 50/80/95% with a three-percentage-point tolerance; ≤5% relative MAE degradation in adequately powered prespecified regional/rare strata; all primary folds complete; comparisons at matched coverage.

These are research defaults, not universal scientific constants. A single development-only feasibility revision must precede frozen comparisons and be justified in the record. Inadequate precision is inconclusive. Finer resolution additionally requires independent local contrasts. Use external confirmation once per candidate; a consulted failed set becomes development evidence. Golden burden gates stay unchanged.

## Execution status and first reviewable slice

The following tasks implement reusable WP0/WP1 engineering prerequisites. They do **not** complete WP0 qualification, establish independent real-world skill, or authorize WP2–WP7 promotion. Data qualification and empirical gates above remain mandatory. This decomposition prevents unvalidated model expansion from outrunning the benchmark.

### Task 1: Exact count predictive scoring

**Scientific contract:** evaluate a new survey's count distribution, not a plug-in frequency. Analytical mixtures are acceptance evidence; later benchmark runners consume the result. Callers must supply observation-level probabilities with all intended latent/cohort/design effects already represented.

**Files:** create `genomeos/validation/predictive.py` and `tests/test_predictive.py`; clarify the legacy score documentation in `genomeos/validation/crossval.py` without changing its results or publication gate.

**Interface:** immutable `CountPredictive(mean_draws, concentration=None)` with arrays shaped `(draws, observations)`; `None` explicitly selects binomial, otherwise concentration must match the shape and be finite/positive. Methods `log_prob(ac, an)`, `cdf(ac, an)`, `sample_counts(an, seed=42)` return per-observation log mass/CDF and `(draws, observations)` replicated counts. `predictive_diagnostics(predictive, ac, an, seed=42)` returns a per-observation DataFrame of integrated log score, frequency-scale MAE/RMSE ingredients, 50/80/95% predictive coverage/width, and randomized PIT. Use analytic mixture CDF/quantiles for coverage; point prediction is the predictive frequency distribution (mean for squared error, count-distribution median/an for absolute error). Include a clearly documented finite-discrete interval caveat.

- [x] RED: hand-calculated binomial and beta-binomial mixture probabilities; normalization term; log-mean-probability versus mean-log-probability; count boundary mass and impossible outcomes; deterministic PIT/count draws; mismatched shapes/noninteger counts/zero denominator/NaN/invalid concentration.
- [x] GREEN: implement NumPy/SciPy functions, stable log-sum-exp and exact discrete-CDF quantiles without allocating an array of length AN. No clipping invalid input into valid values; p=0/1 has exact degenerate semantics.
- [x] Verify tests and smoke, inspect diff/privacy, commit referencing #189. Keep modules below the repository size budget. Reviewed through `2bdae4c`; 34 focused scoring tests pass. Numerical limits are explicit in the module; an IEEE value being finite does not establish that its derived distribution is numerically usable.

### Task 2: Dependency-aware buffered split manifests

**Scientific contract:** withhold geographic evidence without leaking related surveys; caller-supplied block labels determine the target. No inferred ancestry, participant identity, or block geography.

**Files:** create `genomeos/validation/splits.py` and `tests/test_benchmark_splits.py`.

**Interface:** `build_buffered_splits(observations, block_assignments, dependencies, *, buffer_km, data_version)` returns a tuple of frozen `BenchmarkSplit` records. Observations require unique `source_record_id`, `cohort_id`, `lat`, `lon`, `radius_km`; block_assignments maps every record ID exactly once to a nonempty block ID. Dependencies are explicit undirected `(record_id, record_id)` pairs. Automatically connect shared cohort IDs; union transitive explicit dependencies. Test IDs are the block's seed records; exclude all connected training candidates and candidates within buffer distance of any test footprint. Store sorted train/test/excluded IDs, exclusion reasons, minimum realized edge-to-edge separation (None when unavailable), input fingerprint, buffer, data_version, and content-derived split ID. Never discard a planned block: an empty train set is an explicit infeasible split. Keep empty test blocks impossible by construction; require ≥2 blocks.

- [x] RED: transitive dependencies, multi-site cohorts, repeated variants at one location, overlapping footprints, antimeridian/poles, exact buffer boundary, infeasible folds, orphan edges/assignments, invalid coordinates/radii/identities, determinism under input row and edge reordering.
- [x] GREEN: pure deterministic split builder and strict `validate_split` verifying complete disjoint membership, no dependency/buffer leakage, and fingerprint/ID consistency. Use geodesic great-circle distance and chunking to avoid an unbounded all-pairs matrix.
- [x] Verify focused tests/smoke/privacy; commit referencing #189. Reviewed `2017c49` with no findings; 30 focused tests and 40 smoke tests passed. Declared dependencies and footprints still require empirical qualification.

### Task 3: Inventory and fail-closed benchmark reporting

**Scientific contract:** report what evidence and evaluation exist without certifying missing representativeness, independence, or permission. Synthetic fixtures are not scientific performance evidence.

**Files:** create `genomeos/validation/benchmark.py`, `tests/test_benchmark.py`; add a focused inventory module only if needed to keep responsibilities/module sizes clear.

**Interface:** `inventory_observations(observations)` validates the existing allele OBSERVATIONS_SCHEMA and returns JSON-compatible counts by source/assay/design/variant, number of distinct declared cohorts/populations, date-unspecified-modern count, zero-count count, and explicit unresolved limitations (participant overlap, resident target, permissions, registry semantics not certified by P1). Do not claim distinct labels are independent units. Counts/denominators remain separate; do not sum chromosomes across loci as people.

Before schema coercion, reject fractional or Boolean AC/AN/date bounds: the existing P1 schema can truncate fractional values before checking them. Validation may inspect lossless numeric representations, but must not change the submitted value. Keep the shared frozen schema unchanged in this task; its wider repair is separately tracked. This safeguard also protects the modern-only runner from a fractional nonzero date becoming zero. Report legitimate negative-infinite log scores as the explicit JSON string `"-Infinity"` with a zero-probability count, never NaN, silently dropped rows or an unmarked missing value.

`summarize_benchmark(predictions, fold_status, expected_split_ids)` requires unique observation/split prediction keys, explicit status for each planned split (`completed`, `failed`, `infeasible`), no unknown/missing/duplicate split statuses, and no predictions for failed/infeasible splits. For completed splits require the recorded expected test IDs exactly. Predictions require explicit `region_id`, `variant_group`, `cohort_id`, and Task 1 diagnostics. Produce study-within-region/group then cell-macro metrics, counts of represented cells and scored observations, retained failure reasons, and `comparison_complete` false if any planned split did not complete. Do not implement an automatic scientific promotion decision or treat this alone as evidence of sealed validation. Reject nonfinite diagnostic values except legitimate -inf log mass, which must remain visibly catastrophic rather than removed.

For this first reporter, the declared `cohort_id` is the weighting unit, not a certified independent study. Average observation diagnostics within each cohort/region/variant-group, then cohorts equally within each represented region/variant-group cell, then cells equally. Compute RMSE only after averaging squared errors. Validate diagnostic ranges as well as finiteness: error ingredients, frequency-scale widths and PIT are in `[0, 1]`, coverages are Boolean, and log probabilities are nonpositive. If no fold completes, return explicit unavailable metrics and the retained statuses, not an empty successful comparison. Preserve a genuine negative-infinite log score through every aggregation level; ordinary reductions must not turn it into NaN or drop its observation.

- [x] RED: missing status/prediction, failed/infeasible folds, duplicated/unknown rows, label missingness, macro weighting versus cohort size, empty successful set, legitimate zero probability, schema refusal, and real-data limitations.
- [x] GREEN: pure inventory/reporting functions, no file/network I/O.
- [x] Verify focused tests/smoke/privacy; commit referencing #189. Reviewed through `3355b0b`; 120 combined scoring/split/report tests and 40 smoke tests passed. Review added raw zero-probability counts at every aggregation level.

### Task 4: Offline reproducible baseline runner and release record

**Scientific contract:** demonstrate the entire preparation/split/fit/predict/score/report path using a clearly labeled B0 pooled Bayesian binomial baseline, without claiming it is a resident-calibrated or beta-binomial survey-heterogeneity model. Actual current-GP integration and real-data qualification remain explicit subsequent work.

**Files:** create `scripts/benchmark_allele_frequency.py`, `tests/test_benchmark_cli.py`, and small synthetic fixtures under `tests/fixtures/benchmark/`; document usage and outstanding gates in `docs/global-af-benchmark.md`.

**CLI:** require observations TSV, reviewed assignment TSV (record ID, block ID, region ID, variant group), dependencies TSV, data-version, explicit positive Beta prior alpha/beta, explicit buffer-km, and new output directory. Optional seed defaults 42 and posterior draws defaults 2048; report all values. Only the observations schema may coerce according to its existing frozen contract. Validate every auxiliary ID/assignment and group consistency. Per fold and variant, fit Beta(alpha+sum AC, beta+sum AN-AC) from training rows only; sampled latent p is shared across test observations of that variant. A test variant absent from training is marked infeasible, not silently pooled across variants or given fabricated training. Use Task 1 scores, Task 2 splits and Task 3 summaries. A failed/infeasible fold stays in the manifest and yields nonzero exit code after writing its report.

Output inventory, frozen split/config/input hashes, per-observation predictions, fold statuses, and summary as plain JSON/TSV (no pickle). Include seed, code revision, package versions, evidence kind supplied explicitly as `synthetic_fixture` or `observational_research`, and `publication_eligible=false`. The first runner is modern-only allele-count research: reject phenotype-prefixed IDs and nonzero date bounds rather than pooling phenotype/ancient observations into an AF result. Legacy zero dates remain date-unspecified; do not claim current-year resident validation. Refuse pre-existing output directories rather than overwriting. Deterministic scientific outputs exclude timestamps; runtime logs may record timing separately. No genotype/raster downloads, cost-incurring jobs, fitted surfaces, or serving changes.

Use Task 3's public `validate_allele_observations` boundary before accessing coerced counts/dates; do not duplicate its safeguards or import private validators. Subprocess tests and documented source-tree invocation must explicitly resolve this checkout's package (for example, `PYTHONPATH=. python scripts/benchmark_allele_frequency.py ...` from the repository root). A shared editable environment may otherwise import a different checkout. Record hashes of the relevant science/runner source files as well as the Git revision, so uncommitted source changes cannot masquerade as the committed revision's code.

Preserve raw AC/AN/date tokens when reading TSV until the pre-coercion guard has inspected them. Ordinary floating-point CSV inference can erase a small fractional part before validation; add a subprocess regression using an explicitly fractional decimal token that rounds to an integer in binary float. Keep auxiliary identifiers as literal strings rather than letting numeric or default-NA inference change their identity.

- [x] RED: CLI subprocess against hand-readable fixtures, reproducible hashes/bytes, explicit B0 identity and nonpublication label, missing arguments/metadata, changing held-out AC cannot alter training posterior, zero/missing distinction, invalid source IDs, pre-existing outputs, and failed-fold nonzero exit.
- [x] GREEN: implement thin I/O adapter with pure fitting helper in validation/benchmark module or a focused baseline module; no science in argument parsing/storage. Reviewed through `c83d4bb`; public `B0InfeasibleError` centralizes the scientific refusal, actual imported source paths are checked, and exact generated-output bytes are fingerprinted before writing the manifest last.
- [x] Run checkpoint CI, smoke, privacy/staged-path review and existing golden/regression suites; record environmental or baseline failures honestly. Initial runner checkpoint `9d27454`: full pytest 620 passed with five existing inducing-point warnings. Production review fixes `3fa9336`: 201 integrated/golden tests passed. Portable test fix `c83d4bb`: 18 runner tests and 40 smoke tests passed; lint, contract, module, privacy and whitespace gates passed. These are checkpoint results, not final Task 5 validation.
- [ ] Finalize the initial Task 1–5 slice with stable-tree CI and a PR advancing, not closing, #189. The controller bundles this handoff with Task 5 review; the PR must enumerate unimplemented WP0/WP1 empirical gates and WP2–WP7. No scientific release is implied by implementation completion.

### Task 5: Optional GPU CDF backend and complete-workflow measurement

**Scientific contract:** accelerate the same finite-count predictive distribution, not substitute an approximation or change the model. Acceptance requires CPU/GPU agreement on counts, intervals, error ingredients and randomized PIT, plus a measured end-to-end timing comparison. This is computational evidence, not model-accuracy evidence. The CPU implementation remains the reference and the default; GPU unavailability is an explicit error when GPU execution was requested.

**Files:** extend `genomeos/validation/predictive.py`; add a focused `genomeos/validation/predictive_cupy.py` numerical backend, `tests/test_predictive_gpu.py` and `scripts/profile_count_scoring.py`; extend `docs/global-af-benchmark.md`. If optional dependencies are added to `pyproject.toml`, regenerate the relevant universal lock with `--upgrade`, record the exact command, and commit the lock diff. Keep CUDA dependencies outside default/serving requirements. Do not modify fitters, production surfaces or burden gates.

Keep the canonical CPU `requirements.lock` free of CUDA-only packages. If declaring a GPU extra, use a separately named GPU lock for its opt-in installation and document both regeneration commands; do not make the ordinary Linux reproducibility recipe install CUDA dependencies implicitly. The hardware probe may use a smaller explicitly pinned scoring-only environment, whose complete installed versions must be recorded.

**Interfaces:** `CountPredictive(mean_draws, concentration=None, cdf_backend="scipy")` accepts only `"scipy"` or `"cupy"`; existing calls keep identical CPU behavior. Log mass and seeded replicated-count sampling may remain on CPU; the name deliberately identifies CDF acceleration rather than implying every operation is GPU-based. `cdf` and the quantiles consumed by `predictive_diagnostics` must actually use the selected backend. The CuPy module exchanges explicit typed arrays or a public validated draw contract, not imports of private scoring helpers. Validation and numerical-domain policy remain single-source; make an existing count-validation method public if that is the narrowest shared contract. Conditional CuPy loading must not initialize CUDA on CPU-only imports. There is no automatic fallback to CPU, precision downgrade or distribution approximation.

- [x] **RED — baseline/default and invalid backend:** add to the CPU tests before backend code exists:

  ```python
  def test_explicit_cpu_cdf_backend_matches_default():
      means = np.array([[0.1], [0.4]])
      default = CountPredictive(means)
      explicit = CountPredictive(means, cdf_backend="scipy")
      np.testing.assert_array_equal(default.cdf([2], [10]), explicit.cdf([2], [10]))

  def test_unknown_cdf_backend_is_not_a_fallback():
      with pytest.raises(ValueError, match="cdf_backend"):
          CountPredictive(np.array([[0.2]]), cdf_backend="automatic")
  ```

  Run the two tests and record the expected missing-keyword failure. Test explicit missing-library/device failure without making GPU-only tests appear successful when skipped.
- [x] **RED — GPU parity:** use identical host-generated draws and observations for both backends. Cover binomial and beta-binomial mixtures; heterogeneous AN; p=0/1; zero/all counts; AC=-1 CDF boundary; tiny complementary tails; supported numerical limits; every invalid parameter/count case; seeded PIT; and row/draw chunk boundaries. Compare complete diagnostic frames, not just a special function. Use exact count-quantile/coverage equality on fixtures away from quantile ties; log masses/CDF values/PIT use explicit tolerances (initially `rtol=1e-9, atol=1e-11`, with zero absolute tolerance for the analytical tiny-tail regression). If CDF rounding near a quantile tie can change an endpoint, quantify and document that distinction; do not hide it by dropping the case.
- [x] **GREEN — bounded batching:** evaluate beta-binomial log masses with float64 CuPy `gammaln`, `betaln` and log-sum-exp primitives in bounded draw/support chunks. Never allocate a support vector or matrix with extent AN. Use the same boundary and cancellation semantics as the CPU reference. Binomial CDF can use a verified CuPy special-function equivalent. Keep all probabilities finite/in-range or refuse a numerical failure explicitly. Route quantile evaluation through the selected CDF path, avoiding private cross-module coupling. Bound temporary work arrays by an explicit implementation constant/configuration; record its value in the profiler.
- [x] **GREEN — thin profiling adapter:** `python scripts/profile_count_scoring.py --draws 2048 --observations 10 --an 1000 --concentration 20 --repeats 5 --seed 42 --out NEW_DIRECTORY` generates synthetic inputs and measures full `predictive_diagnostics` for both backends. Require positive counts/sizes/concentration/repeats; refuse existing output directories. CUDA is required for this comparison; missing CUDA exits nonzero with an actionable message, not an empty success report. Report input hash, code revision, dependency versions, device/dtype, exact configuration, separate cold/warm measurements, synchronization and transfers, memory measurement semantics, numerical discrepancies and explicit parity pass/fail. Preserve individual repeat timings. Scientific outputs have `evidence_kind="synthetic_performance_probe"` and `publication_eligible=false`; they are not allele-frequency performance benchmarks. Non-parity exits nonzero after preserving the report.

  Also hash the actual scoring/profiler source files. A minimal remote source snapshot need not carry the repository's data or Git history: support explicit `--source-revision COMMIT` for that case, label its provenance as supplied rather than Git-observed, and verify uploaded source hashes against the committed local snapshot before hardware runs. Otherwise obtain the revision from Git; refuse missing provenance rather than inventing a revision. Pin the remote environment without modifying the original local virtual environment.
- [x] **Run and verify:** test CPU-only imports/refusals locally; run GPU tests on a task-owned US/Canada RunPod pod with an actual device preflight and zero unexpected skips. Run at least a small/overhead-dominated and the specified larger full-diagnostics workload, including same-host CPU comparison. Pin and record the remote environment; no real genomic inputs are needed. Collect reports, stop/delete task-owned resources, and record quoted versus estimated cost distinctly. No speedup claim may omit cold/transfer/setup costs or failures. Evidence: [synthetic complete-workflow GPU report](../../research/count-scoring-gpu-workflow-2026-09-09.md).
- [x] **Review and commit:** focused tests, smoke, lint, module/privacy/staged-path checks; independently review CPU/GPU code and numerical/performance evidence. Commit code and a reproducible synthetic report referencing #189 and advancing #104 where appropriate; do not close either whole program merely for a CDF improvement. Independently reviewed through `ebfe80b`: spec compliant, quality approved, no Critical/Important findings. Two documentation-hygiene minors (an early scratch dependency range and enumeration of existing test warnings) are retained for whole-branch review. The initial-slice final CI/PR handoff below Task 4 remains open.

## Authorized scaling follow-up: measured count-scoring acceleration

The September 9 CPU probe at Task 1 commit `a166b41` used seeded synthetic probabilities on the local Python 3.12/SciPy 1.18.1 environment. Full diagnostics for 2,048 draws, one observation, AN=1,000 took 0.018 seconds (binomial) versus 4.74 seconds (beta-binomial concentration 20). Ten observations, 256 draws and AN=10,000 took 21.54 seconds for beta-binomial diagnostics. These single-run timings identify a bottleneck; they are not controlled GPU comparisons or model-performance evidence.

After the initial four tasks, test batched CuPy special-function/reduction kernels on a task-owned RunPod GPU against the CPU oracle. Use synthetic inputs only, float64, identical inputs, explicit cold/warm timing, synchronization, host/device transfers, memory usage and all requested failure/parity cases. CuPy does not list a drop-in beta-binomial CDF; do not assume API equivalence. Retain exact finite-count semantics and bounded memory. Record algorithmic improvements separately from device speedups. Any production acceleration is optional, explicitly selected, independently reviewed, and must fail clearly if unavailable; CPU-only installations and benchmark results remain supported. Stop task-owned resources after retrieving the report. A failed parity or speed test is a valid result, not a reason to weaken the scorer.

A preliminary synthetic-only primitive probe was run while Task 1 fixes were reviewed: [reproducer and measurements](../../research/count-scoring-gpu-probe-2026-09-09.md). Warm vectorized primitive throughput justifies a complete GPU trial; cold-start cost and full diagnostic parity remain separate gates. The probe pod was stopped and deleted.

## Stop and redirect

Do not implement or publish a speculative winner to make every box green. Missing independent populations redirects effort to qualified evidence; random-split-only gains do not establish geography; local-genotype LD gains remain imputation; nonidentifiable histories remain broad/refused; fine grids without contrasts stay unvalidated. Access/export decisions remain external gates. The full program is complete only after reproducible external improvement and a supported immutable production release.
