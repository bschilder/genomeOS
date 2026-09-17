# Global allele-frequency benchmark runner

This repository includes offline, deterministic runners for the B0 engineering baseline, the B1
local count comparator, and the unchanged current single-variant spatial GP in issue #189. B0
updates an explicit Beta prior with pooled training allele counts separately for each variant,
samples the resulting latent frequency, and scores held-out binomial allele counts. The sampled
frequency is shared across held-out observations of the same variant within a draw.

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

## Current spatial-GP runner

`scripts/benchmark_spatial_gp.py` composes the same unseen-cohort interface with the reviewed
split builder and exact count diagnostics. It accepts exactly one modern allele per run, keeps
every declared cohort in one held-out block, and makes one batched query and scoring call per
fitted fold. The loop over folds remains because every fold is a distinct posterior fit; the
adapter adds no observation-by-draw loop.

The fit configuration is a JSON object containing every `FitConfig` field. Requiring the complete
resolved object prevents library or source defaults from silently changing a rerun. Generate a
starting file from the installed checkout, inspect it, and commit or hash the reviewed copy with
the research inputs:

```bash
PYTHONPATH=. python -c \
  'import json; from dataclasses import asdict; from genomeos.surfaces.config import FitConfig; print(json.dumps(asdict(FitConfig()), indent=2, sort_keys=True))' \
  > /tmp/current-gp-fit-config.json

PYTHONPATH=. python scripts/benchmark_spatial_gp.py \
  --observations /path/to/one-variant-observations.parquet \
  --assignments /path/to/reviewed-assignments.tsv \
  --dependencies /path/to/dependencies.tsv \
  --fit-config /tmp/current-gp-fit-config.json \
  --data-version DATA_VERSION \
  --buffer-km 300 \
  --seed 42 \
  --cdf-backend scipy \
  --evidence-kind observational_research \
  --assignment-review-status reviewed \
  --dependency-review-status not_checked \
  --checkpoint-dir /new/checkpoint/directory \
  --out /new/output/directory
```

The observations input may be TSV or Parquet. Assignments and dependencies remain literal TSV
contracts. `assignment-review-status=algorithmic_development_unreviewed` and
`dependency-review-status=not_checked` preserve useful development runs without misrepresenting
their qualification. Declaring either input `reviewed` is caller-supplied provenance, not an
automated scientific decision. Every output remains `publication_eligible=false`, and the manifest
sets `scientific_promotion_decision=not_made` even when all computational folds complete.

The checkpoint directory must also be new. After each fold reaches `completed`, `failed`, or
`infeasible`, the runner atomically publishes one integrity-hashed fold artifact before starting
the next fit. The final output directory appears only after every planned fold is terminal and its
manifest has been written successfully. Checkpoints are recovery artifacts and are never accepted
as a complete benchmark publication.

Resume is explicit: repeat every scientific and provenance argument unchanged, replace
`--checkpoint-dir NEW_DIRECTORY` with `--resume-from EXISTING_DIRECTORY`, and provide a new
`--out` path. Resume refuses changes to input-file hashes, resolved configuration or CDF backend,
the planned split ledger, the complete fit/predictive seed schedule, Git revision, science-source
hashes, package versions, evidence kind, or qualification fields. It also refuses corrupt,
unknown, overwritten, or noncontiguous fold artifacts. Every terminal fold is reused, including a
failed or infeasible fold; resume is not an implicit retry mechanism.

Each fitted fold retains its maximum rank-normalized R-hat, minimum bulk ESS, minimum tail ESS,
the parameter responsible for each extreme, and the number of post-tuning divergent transitions.
A spatial-benchmark fold is `completed` only when maximum R-hat is at most the configured
`max_rhat`, both ESS extrema are at least the configured `min_ess`, and the divergence count is
zero. A diagnostic failure is an immutable `failed` checkpoint with no admissible predictions;
resume reuses that failure and cannot selectively retry it under the same benchmark identity.

Before fitting, the runner verifies that the selected likelihood's exact scorer can cover every
denominator. A single unsupported row produces a failed status for every planned fold, zero fits,
and a nonzero exit after writing the complete evidence record. It never drops that row, switches
likelihoods, or reports a partial benchmark. Fit/prediction failures inside otherwise supported
folds are likewise retained while later folds continue.

## Local count comparator

`scripts/benchmark_local_count.py` implements the source-neutral B1 comparator from issue #307.
It uses a compact triweight kernel over great-circle distance between reviewed recruitment
footprint edges. At each query, the same weight multiplies AC and `AN - AC`; those weighted counts
update an explicit Beta generalized-Bayes power posterior. Fractional weighted evidence is never
described as literal sampled alleles. No environmental layer, pathogen label, publisher identity,
or held-out count enters the model.

Candidate bandwidths are a finite, strictly increasing list declared on the command line. Each
outer fold selects among them using only new buffered folds inside its training partition. A
candidate is eligible only if every inner fold completes, it emits the declared minimum fraction
of inner queries, and it has a valid normalized held-out count score. Ties prefer the narrower
bandwidth. The outer test counts are used only after selection for scoring.

The compact kernel, minimum local-row count, and minimum kernel-weighted allele denominator form
the support rule. A query failing either evidence threshold is `unknown`; the runner does not
substitute B0, a prior-only value, or the nearest observation. Every requested row remains in
`support.tsv`, while `predictions.tsv` contains only emitted rows. `summary.json` reports requested,
emitted, excluded, and excluded-fraction totals alongside an explicitly supported-only use of the
shared hierarchical count summary.

```bash
PYTHONPATH=. python scripts/benchmark_local_count.py \
  --observations /path/to/one-variant-observations.tsv \
  --assignments /path/to/reviewed-assignments.tsv \
  --dependencies /path/to/dependencies.tsv \
  --data-version DATA_VERSION \
  --bandwidth-km 500 \
  --bandwidth-km 1000 \
  --bandwidth-km 2000 \
  --prior-alpha 1 \
  --prior-beta 1 \
  --buffer-km 300 \
  --minimum-inner-emission-fraction 0.5 \
  --minimum-training-observations 2 \
  --minimum-effective-alleles 100 \
  --posterior-draws 2048 \
  --seed 42 \
  --evidence-kind observational_research \
  --analysis-role prespecified_primary \
  --assignment-review-status reviewed \
  --dependency-review-status reviewed \
  --out /new/output/directory
```

The output manifest names the generalized posterior semantics and records
`environmental_covariates=false`, `source_specific_features=false`, the complete configuration,
input and source hashes, immutable outer splits, terminal fold outcomes, package versions, and
`publication_eligible=false`. This comparator evaluates a local-count hypothesis; it does not
privilege MAP or any other source family. `analysis_role` distinguishes the prespecified primary
comparison from a post-hoc sensitivity, while the two review-status fields prevent algorithmic
development blocks or an unchecked dependency file from being represented as reviewed evidence.

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

Each row is an undirected dependency edge between known observation IDs. For the B0 runner, a
header-only file means there are no reviewed explicit edges. The current-GP runner additionally
requires an explicit dependency review status, so an empty diagnostic file can remain
`not_checked`. Shared cohort IDs remain automatically connected by the public split builder; an
empty dependency file never certifies participant independence.

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
| `fold_status.tsv` | Every planned split with expected test IDs, `completed`/`failed`/`infeasible`, reason, and retained R-hat, bulk/tail ESS, responsible parameter names, and divergence count when fitting reached diagnostics. |
| `summary.json` | Explicit B0/evidence/nonpublication metadata plus the public hierarchical benchmark summary. |

The configuration hash covers the model inputs, the combined input hash covers all raw bytes
(including columns unused for split membership), each split retains the public validated-input
fingerprint, and the split-manifest hash covers membership, exclusions, status, reasons, and fold
seeds. Relevant source-file hashes prevent an uncommitted fitter or runner change from masquerading
as the recorded Git revision. The runner puts its own checkout first on the import path, verifies
that every imported science module resolves to the expected file under that root, and hashes those
resolved files; a conflicting editable installation cannot silently change executed science.

The current-GP runner writes the same five files. Its prediction rows contain the block, variant,
observed counts, and deterministic fit/prediction seeds instead of B0 posterior-alpha/beta fields.
Its manifest identifies `B2-current`, records the complete resolved `FitConfig`, both review-state
declarations, the selected CDF backend, and hashes of the fitted observation/prediction modules.
Every split record also carries the same sampler diagnostics as `fold_status.tsv`; these values are
inside both the split-manifest hash and the per-fold checkpoint integrity hash.

The local-count runner adds `support.tsv` and `bandwidth_selection.tsv`. The first retains every
requested query and its support or refusal evidence. The second records every candidate's
inner-fold requested and emitted counts, emission fraction, normalized log score, completion
counts, and eligibility for every outer fold. Its prediction rows include the selected bandwidth,
distance to the nearest training footprint, weighted evidence, posterior parameters, and
deterministic seeds.

For each completed fold and variant, the posterior is
`Beta(prior_alpha + sum(AC), prior_beta + sum(AN - AC))` using training rows only. A held-out
variant absent from training makes the fold infeasible; it is never assigned a prior-only result or
pooled with another variant. The posterior-draw seed and randomized-PIT seed are separately derived
and recorded per fold.

## Gates that remain open

These runners are reusable WP0/WP1 engineering prerequisites. They do not complete the qualified
input inventory, certify dependencies or a present-day resident target, establish genuinely
sealed external evidence, implement all required holdout tracks/strata/joint-site scores, or
provide a completed B0/B1/B2 comparison. The first HbS B1 run is recorded in the
[local-count evidence note](research/hbs-local-count-benchmark-2026-09-16.md): the prespecified
local grid is infeasible for global geographic holdouts, while a post-hoc 2,000 km sensitivity
finds positive-count gains on only 21.9% of rows and regresses zero counts. The bounded scorer now
admits the complete count domain without dropping rows, but the current-GP B2 run hit its time
cutoff before all folds completed. Those WP0 and WP1 gates remain required on reviewed, permitted
data.

WP2 observation-aware likelihood, footprint, ascertainment, and cohort validation; WP3 covariate
admission; WP4 statistical/shared/connectivity models; WP5 neural challengers; WP6 multiallelic,
LD, and GPU work; and WP7 temporal/origin modeling are all unimplemented by this runner. The HbS,
G6PD, and carrier-screening publication gates remain unchanged. The owner's resolved
[#66 decision](https://github.com/bschilder/genomeOS/issues/66#issuecomment-5565166083) permits
redistribution of fitted surfaces with source attribution and biocultural notices, a clear
observed/inferred distinction, and explicit source restrictions honored. That conditional policy
permission does not qualify any source or publish any scientific result in this milestone.

## Count-scoring numerical domain

`CountPredictive.log_prob` evaluates interior beta-binomial draws from the nearer endpoint mass
and a shorter-side adjustment. It evaluates two equivalent rising-factorial factorizations and
selects the one with the smaller sum of intermediate log magnitudes for each posterior draw. Each
ratio uses a 16-factor exact prefix and a fixed Euler--Maclaurin tail. Work and temporary arrays are
bounded independently of AN; the scorer never materializes `0, ..., AN` or substitutes a binomial
distribution.
An independent 160-digit Decimal oracle covers the actual 2,571,112-allele HbS maximum and the
declared 2,147,483,647 count ceiling. Measured absolute log-mass error is at most `5e-9` across the
million-scale benchmark cases and `3e-8` across endpoint and interior cases at the declared
ceiling. Mixture integration, allele
complement symmetry, small-support normalization, exact Bernoulli identities, and boundary-heavy
means remain regression-tested. The existing beta shape/concentration checks remain in force.

CDF/quantile queries retain their exact bounded-memory tail-sum arithmetic. Their memory does not
grow with AN, but runtime can grow with the shorter queried support tail; log-mass acceleration does
not imply constant-time quantiles.

The accepted quantile levels remain `0 < q <= 1`; the 100% endpoint is the exact mixture support
maximum (zero only when all draws have p=0, otherwise AN), independent of CDF rounding. Earlier
GPU timing reports identify their original source snapshots and require fresh hardware evidence
for these revised scoring and endpoint paths. That refresh is now recorded in the
[boundary-fix hardware evidence](research/count-scoring-boundary-refresh-2026-09-09.md), with
116 actual-device tests and both synthetic workloads passing; it does not establish AF accuracy.

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
