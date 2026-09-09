# Global allele-frequency benchmark runner

This repository includes an offline, deterministic runner for the B0 engineering baseline in
issue #189. B0 updates an explicit Beta prior with pooled training allele counts separately for
each variant, samples the resulting latent frequency, and scores held-out binomial allele counts.
The sampled frequency is shared across held-out observations of the same variant within a draw.

B0 is not a spatial/current-resident model and has no cohort, survey-design, or recruited-sample
heterogeneity term. Its outputs always state `publication_eligible=false`. A successful synthetic
fixture run demonstrates that preparation, dependency-aware splitting, fitting, count prediction,
scoring, and reporting compose reproducibly; it is not scientific performance evidence.

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
G6PD, and carrier-screening publication gates remain unchanged, as does the unresolved restriction
on redistributing derived surfaces from indigenous-population panels.

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
