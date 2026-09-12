# Global allele-frequency benchmark runner

This repository includes an offline, deterministic runner for the B0 engineering baseline in
issue #189. B0 updates an explicit Beta prior with pooled training allele counts separately for
each variant, samples the resulting latent frequency, and scores held-out binomial allele counts.
The sampled frequency is shared across held-out observations of the same variant within a draw.

B0 is not a spatial/current-resident model and has no cohort, survey-design, or recruited-sample
heterogeneity term. Its outputs always state `publication_eligible=false`. A successful synthetic
fixture run demonstrates that preparation, dependency-aware splitting, fitting, count prediction,
scoring, and reporting compose reproducibly; it is not scientific performance evidence.

## Observation-aware GP parameters

A newly fitted `SurfaceFit` can expose the existing GP observation distribution for explicit
genuinely unseen cohorts. The caller constructs `SurveyQueries` with one observation ID, cohort
ID, fitted sampling-design label, latitude and longitude per row. AC and AN are separately
validated observation counts in exactly that same row order; they are not inferred from queries.

```python
from genomeos.surfaces.fit import fit_surface
from genomeos.surfaces.observation import SurveyQueries
from genomeos.validation.predictive import CountPredictive, predictive_diagnostics

fitted = fit_surface(qualified_training_observations, fit_config)
queries = SurveyQueries(
    observation_ids=("held-out-1", "held-out-2"),
    cohort_ids=("unseen-study", "unseen-study"),
    sampling_designs=("population_random", "healthy_reference"),
    lat=(0.0, 5.0),
    lon=(-8.0, 8.0),
)
ac = (1, 3)  # separately validated and aligned to queries
an = (20, 40)

parameters = fitted.predict_new_cohort_parameters(queries, seed=42)
predictive = CountPredictive(parameters.mean_draws, concentration=parameters.concentration)
diagnostics = predictive_diagnostics(predictive, ac, an, seed=42)
```

`parameters.draw_ids` retains the named posterior chain/draw coordinates. The first fitted design
is the actual zero-offset reference used by the model, which can differ from the configured
reference when that configured label was absent from training. Queries using an unfitted design
or a training cohort are refused; seen-cohort conditioning is a different target. Legacy format-1
caches remain readable by the old prediction methods, but caches without recorded metadata and
the named latent-logit graph node refuse this interface and require refitting.

This interface exposes the resident model's existing approximation; it does not repair its
geographic footprint, qualify recruitment as representative of present-day residents, change
the fitted approximation or serving behavior, or demonstrate an accuracy improvement. The HbS, G6PD,
carrier-screening, external-validation, redistribution and publication gates remain unchanged,
and no serving-path inference is authorized.

## Source-tree invocation

Run from the repository root and explicitly select this checkout on `PYTHONPATH` so a shared
editable environment cannot import another checkout:

```bash
PYTHONPATH=. python scripts/benchmark_allele_frequency.py \
  --observations tests/fixtures/benchmark/observations.tsv \
  --assignments tests/fixtures/benchmark/assignments.tsv \
  --dependencies tests/fixtures/benchmark/dependencies.tsv \
  --data-version fixture-v1 \
  --prior-alpha 1.0 \
  --prior-beta 1.0 \
  --buffer-km 300 \
  --evidence-kind synthetic_fixture \
  --seed 42 \
  --posterior-draws 2048 \
  --out /tmp/genomeos-b0-fixture
```

`--seed` defaults to 42 and `--posterior-draws` defaults to 2048; both values are always recorded.
The priors, buffer, data version, evidence kind, input files, and a new output directory are
required. The output path must not already exist and is never overwritten. An infeasible or failed
planned fold is retained in the output and makes the process exit nonzero after all reports are
written.

## Input contracts

The observations file is a tab-separated P1 `OBSERVATIONS_SCHEMA` table. AC, AN, and both date
bounds are read as their original text tokens until the public lossless validator has rejected
fractional values; only the existing frozen observations schema may coerce them. This runner
accepts allele counts only: it refuses `phenotype:` identifiers and any nonzero date bound. Legacy
zero dates mean date unspecified, not a verified current-year resident sample.

The reviewed assignment TSV has exactly these columns:

```text
source_record_id  block_id  region_id  variant_group
```

It must assign every observation exactly once. IDs and labels are read literally, so values such
as `NA` or `001` are not converted to missing values or numbers. Every variant must have one
consistent `variant_group`; block and region labels otherwise remain caller-reviewed assignments.

The reviewed dependency TSV has exactly these columns:

```text
source_record_id_a  source_record_id_b
```

Each row is an undirected dependency edge between known observation IDs. A header-only file means
there are no reviewed explicit edges. Shared cohort IDs remain automatically connected by the
public split builder; an empty dependency file does not certify participant independence.

`evidence_kind` is supplied explicitly as either `synthetic_fixture` or
`observational_research`. This label does not verify permissions, study independence, registry
semantics, or resident representativeness.

## Outputs

All outputs are plain UTF-8 JSON or TSV, with no timestamp or output-directory path in scientific
content:

| File | Contents |
|---|---|
| `inventory.json` | Public P1 inventory counts and unresolved qualification limitations. |
| `manifest.json` | B0 identity, nonpublication label, exact configuration and hash, raw input and generated-output hashes/sizes, source counts, Git revision, package versions, hashes of the actual imported science files, immutable splits, fold statuses, and distinct posterior/PIT seeds. It is written last. |
| `predictions.tsv` | One completed-fold row per held-out observation: identities and grouping labels, observed AC/AN, posterior parameters/mean, seeds, and all ten public predictive diagnostics. A true zero probability is written as `-Infinity`. |
| `fold_status.tsv` | Every planned split with expected test IDs, `completed`/`failed`/`infeasible`, reason, and its two deterministic seeds. |
| `summary.json` | Explicit B0/evidence/nonpublication metadata plus the public hierarchical benchmark summary. |

The configuration hash covers the model inputs, the combined input hash covers all raw bytes
(including columns unused for split membership), each split retains the public validated-input
fingerprint, and the split-manifest hash covers membership, exclusions, status, reasons, and fold
seeds. Relevant source-file hashes prevent an uncommitted fitter or runner change from masquerading
as the recorded Git revision. The runner puts its own checkout first on the import path, verifies
that every imported science module resolves to the expected file under that root, and hashes those
resolved files; a conflicting editable installation cannot silently change executed science.

For each completed fold and variant, the posterior is
`Beta(prior_alpha + sum(AC), prior_beta + sum(AN - AC))` using training rows only. A held-out
variant absent from training makes the fold infeasible; it is never assigned a prior-only result or
pooled with another variant. The posterior-draw seed and randomized-PIT seed are separately derived
and recorded per fold.

## Gates that remain open

This fixture runner is only a reusable WP0/WP1 engineering prerequisite. It does not complete the
qualified input inventory, certify dependencies or a present-day resident target, reproduce the
current production model, establish genuinely sealed external evidence, implement all required
holdout tracks/strata/joint-site scores, or provide an empirical B0/B1/B2 comparison. Those WP0 and
WP1 gates remain required on reviewed, permitted data.

WP2 observation-aware likelihood, footprint, ascertainment, and cohort validation; WP3 covariate
admission; WP4 statistical/shared/connectivity models; WP5 neural challengers; WP6 multiallelic,
LD, and GPU work; and WP7 temporal/origin modeling are all unimplemented by this runner. The HbS,
G6PD, and carrier-screening publication gates remain unchanged. The owner's resolved
[#66 decision](https://github.com/bschilder/genomeOS/issues/66#issuecomment-5565166083) permits
redistribution of fitted surfaces with source attribution and biocultural notices, a clear
observed/inferred distinction, and explicit source restrictions honored. That conditional policy
permission does not qualify any source or publish any scientific result in this milestone.

## Count-scoring numerical domain

**Candidate status: numerical acceptance failed.** The admission range below describes the
implementation, not a validated accuracy range. The fixed CPU and GPU matrices each recorded
548 laws: 513 passed, 24 were expected domain refusals, and 11 had candidate mismatches on
subnormal masses or tails. Some failures occur in the previously admitted concentration range.
All ordinary log checks passed, but neither that result nor CPU/GPU parity waives the failed
probability-accuracy requirement. This candidate is not release- or calibration-ready and
establishes no global or real-population AF improvement.

Those hardware numerical runs tested source `f8e7afdc199ff227ec03ca9d55bdd84d8a91c0f5`.
The later `abddfb5c3ec60d81fe68b712c4fec04e407b8fc2` adapter/accounting correction was not a
comprehensive numerical rerun; hardware evidence applies to its recorded source hashes.

`CountPredictive` evaluates the finite beta-binomial law using complete-support normalized
neighboring-count recurrence for every admitted interior draw with AN at most 65,536. The same
below/equal/above partitions supply log mass and both tails. A legal mode anchors the relative
weights; logarithmic shape factors preserve tiny means without first rounding their products.
Tree prefix sums and compensated carries bound accumulated rounding across support chunks.
The target mass is isolated before normalization, preserving nearly certain negative log masses.
AN=1 is Bernoulli exactly; symmetric central and uniform CDF identities preserve quantile ties.

Interior concentration may exceed 67,108,864 through 1e300 when AN is at most 65,536. Above
1e300, or where positive finite usable shapes cannot be represented, construction refuses the
input. Legacy beta-normalizer validity checks remain for concentrations at most 67,108,864;
high concentrations never pass through that normalizer. High-concentration interior draws with
AN above 65,536 are refused by mass, CDF, quantiles and sampling, including trivial endpoints,
before optional backend access. Interior log mass retains the 65,536 count limit at every
concentration. For lower concentrations, CDF/quantile-only and sampling queries retain AN through
2,147,483,647 and their existing larger-count arithmetic and limitations. Exactly degenerate
p=0/1 draws and explicitly selected binomial laws retain their previous count domains.

A complete CDF costs O(draws × AN); binary-search quantiles multiply that cost by query levels
and approximately log2(AN). This also changes the cost of low-concentration short-tail queries.
Each recurrence working grid has at most four query rows, 128 draws and 1,024 support entries;
row/draw axes are flattened inside each bounded working batch (at most 512 scalar laws). Current and copied tree-prefix
buffers, factor/ratio temporaries, masks, indices and reduction exponentials obey this bound.
Carries and three partition accumulators have one value per scalar law. No working dimension
spans the complete support. Allocator pool reservation, live arrays, process RSS and device-wide
high-water measurements are distinct quantities; profiling must identify the measured scope.

The accepted quantile levels remain `0 < q <= 1`; the 100% endpoint is the exact mixture support
maximum (zero only when all draws have p=0, otherwise AN), independent of CDF rounding. Sampling
retains the seeded beta-then-binomial construction. Where latent beta variation is below floating
resolution, empirical samples cannot distinguish finite concentration from its limiting law;
this is not a new sampler branch. Numerical checks do not establish biological calibration or
AF accuracy, and the failed numerical acceptance above remains unresolved.

Completed ordinary complete-workflow timing compared the tested candidate with baseline
`d081e9415973a7bc8865243ffcd5f5fa8e1ac489` on matched synthetic inputs on the same host,
at concentration 20. Warm median runtime ratios over five repeats were:

| Workload (draws / observations / AN) | CPU candidate / baseline | GPU candidate / baseline |
|---|---:|---:|
| Small: 32 / 2 / 20 | 0.14472× | 2.37544× |
| Full: 2048 / 10 / 1000 | 1.35144× | 3.41106× |

Ratios above one are regressions. GPU timings include transfers and synchronization;
lightweight monitoring overlapped the runs, so these are not isolated-machine measurements.

The completed synthetic high-concentration workload (2048 draws, 10 observations, AN 1000,
concentration 134,217,728, seed 42) passed CPU/GPU parity. Across five warm repeats, median
times were 371.289 s on CPU and 26.582 s on GPU. The baseline does not admit this workload,
so there is no baseline high-concentration comparison. This performance/parity result does
not resolve the failed numerical acceptance above.

Recorded GPU device/pool memory metrics do not establish CPU peak RSS, which is unavailable
in these reports.

## Optional GPU count-CDF profiling

`CountPredictive` keeps `cdf_backend="scipy"` as its default and reference implementation. An
explicit `cdf_backend="cupy"` accelerates only the exact CDF evaluations used by `cdf` and the
quantiles in `predictive_diagnostics`; log mass, error ingredients, and seeded replicated-count
sampling remain on CPU. The optional backend uses float64 bounded row/draw/support chunks and
does not approximate the distribution, allocate an AN-sized support, downgrade precision, or
fall back to SciPy. A missing CuPy installation or accessible CUDA device is an explicit error.

The synthetic complete-workflow profiler is opt-in and requires a pinned CUDA-capable environment:

```bash
PYTHONPATH=. python scripts/profile_count_scoring.py \
  --draws 2048 \
  --observations 10 \
  --an 1000 \
  --concentration 20 \
  --repeats 5 \
  --seed 42 \
  --out /tmp/genomeos-count-profile
```

The output directory must be new. `report.json` records the generated-input hash, actual executed
source hashes, Git-observed revision, all installed distribution versions, device and dtype,
chunk bounds, individual warm repeats, a first-scoring measurement, CUDA preflight/context cost,
host/device transfer and synchronization scope, exact integer count-quantile endpoints, and
complete diagnostic parity. Endpoint mismatches fail parity even when interval widths and observed
coverage happen to match. GPU memory is
reported as a separately sampled device-wide high-water delta; CuPy pool reservation is named
separately and is never represented as peak live memory. A parity failure is preserved in the
report and exits nonzero.

A source-only remote snapshot without `.git` must supply a full revision explicitly with
`--source-revision COMMIT`. The report labels that value `supplied`; it does not pretend Git
observed it. The uploader must compare the report's scoring/profiler hashes with the committed
local files before treating a hardware run as reproducible evidence.

Every profiler output carries `evidence_kind="synthetic_performance_probe"` and
`publication_eligible=false`. Cold and warm timing include construction, full diagnostics,
transfers, and synchronization, but exclude imports and synthetic input generation. They are
computational measurements, not model-accuracy results or allele-frequency benchmark evidence.

The controlled synthetic A100 results, raw reports, timing qualifications, and resource lifecycle
are preserved in [the complete-workflow evidence note](research/count-scoring-gpu-workflow-2026-09-09.md).
