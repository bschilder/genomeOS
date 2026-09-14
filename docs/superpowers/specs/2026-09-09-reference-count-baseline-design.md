# Reference-panel count baseline design

This is an implementation slice of #189, global-AF plan WP0–WP1, and Atlas
design §§5, 7, 8. It does not replace the primary resident-frequency estimand.

## Scientific contract

1. **Objective:** measure the predictive performance of a fixed pooled Beta
   allele-count baseline on withheld population groups within a qualified
   reference resource, without representing reference counts as resident surveys.
2. **Evidence:** deterministic dependency-grouped cross-validation, exact marginal
   count predictive scores, complete unavailable/failed-row accounting, and a
   reproducible real-data run. This establishes a development baseline, not model
   superiority, external generalization, geographic resolution, or release fitness.
3. **Component/interface:** pure count posterior and reference benchmark functions,
   wrapped by an offline local-file CLI. Production P1 validation and serving
   contracts remain unchanged.
4. **Assumptions/refusals/consumers:** complete diploid allele counts have already
   been qualified upstream; recorded dependencies are lower bounds, not proof of
   independence. Missing denominators are unavailable. Absent training variants,
   malformed counts/dependencies, and unstable predictive parameters are refused.
   Consumers are research comparisons and their reviewers, never the serving API.

## Global constraints

- Research target is `reference_panel_within_resource`; evidence role is `development` or `synthetic`.
- No P1 schema changes, invented ascertainment, coordinates, radii, dates, or cohort metadata.
- No network or file I/O in pure science modules; no fitting on the serving path.
- `SEED = 42`; scientific artifacts are deterministic given input bytes, configuration, and source bytes.
- Real genotypes, sample identifiers, count tables, and derived research predictions stay local and untracked in this slice.
- Zero AN is retained as `unavailable_denominator`, never converted to frequency zero or silently dropped.
- Known population dependency components must never cross train/test boundaries.
- All planned folds and all held-out rows have explicit outcomes; failed folds are not omitted from summaries.
- The baseline uses explicit positive finite Beta priors and never trains on held-out counts.
- Marginal predictions are labeled `joint_prediction_supported=false` and are not a coherent joint-site sampler.
- No dependency additions, no GPU prerequisite, and no CuGen dependency in this slice.

## Count posterior boundary

`genomeos.validation.count_baseline` owns immutable `PooledAlleleCount`,
`B0VariantPosterior`, and `B0InfeasibleError`, and a pure
`pooled_beta_posteriors` function. A datum contains literal nonempty record and
variant IDs, integer AC and positive integer AN with 0 <= AC <= AN. Bool and
fractional values are errors; accepted integer types normalize to Python ints.
Record IDs are unique within training. Requested variant IDs are nonempty,
unique strings. Output is sorted by variant ID and sums use Python integers.

Posterior shapes are prior_alpha + sum(AC) and prior_beta + sum(AN - AC).
Reject nonfinite/nonpositive shapes or total concentration. No absent-variant
prior-only fallback. `fit_pooled_b0` remains the P1 adapter, re-exporting its
existing public posterior/error names, preserving strict validation, draw order,
test-row order, and shared per-variant latent draws. Its executed-source
fingerprint must include the extracted module.

## Reference table and folds

`ReferenceCount` fields are `record_id, variant_id, group_id, region_id,
variant_group, ac, an`. String IDs are literal, nonempty, non-whitespace-only;
integer validation is lossless and permits AN=0 only with AC=0. A validated
table is nonempty, has unique record IDs and unique (group_id, variant_id), and
has one region_id per group and one variant_group per variant. These are
source operational groupings, not certified study independence or geography.

`reference_group_folds` takes a validated table and explicit dependency edges
between known, distinct group IDs. Reject unknown endpoints, self-edges, and
duplicate undirected edges. Compute connected components using identifiers
alone, sort members and components, permute components using NumPy's seeded
generator, and round-robin assign them to `n_folds` folds (integer >=2, default
5). Fewer components than requested folds is a hard error, never a smaller
implicit benchmark. Canonical sorted record IDs determine memberships; each
row is held out once, regardless of count availability. Zero-AN rows remain
in the fold membership. Fold IDs are `reference-0`, `reference-1`, etc.

Each `ReferenceFold` holds split_id, train_ids, test_ids, and held-out groups.
The source qualification graph is a declared input, hashed in the run manifest.
It does not establish independence from shared discovery/calling/QC.

## Exact marginal B0

`fit_reference_b0` validates nonempty training and testing reference tables,
requires disjoint record IDs and group IDs, excludes AN=0 only from fitting and
scoring, and returns `ReferenceB0Fit` with `marginal_predictive`,
`observation_ids`, `unavailable_ids`, and `posteriors`. Test rows preserve their
provided order in each corresponding ID sequence. The generic kernel supplies
posterior shapes. Absent training evidence for any scoreable test variant makes
the fold infeasible, rather than emitting its prior. A test fold with no
scoreable rows is also infeasible.

For each scoreable row with posterior (a,b), construct the existing
`CountPredictive` with one mean draw a/(a+b) and concentration a+b. This is the
Beta-binomial posterior predictive marginal. Reject rounded boundary means,
nonfinite parameters, and reconstructed shapes not close to the originals
(rtol=1e-10, atol=0); existing predictive-domain limits remain hard errors.
Do not clip parameters or add pseudocounts beyond the declared prior.

Reuse `predictive_diagnostics` for all existing count diagnostics. This is exact
marginal integration, not a Monte Carlo posterior ensemble. Randomized PIT has
a separately recorded seed. Training and test count perturbation tests must
demonstrate the absence of test-count leakage into fitted parameters.

## CLI and artifact contract

`scripts/benchmark_reference_counts.py` reads a local TSV with exactly the seven
ReferenceCount columns, preserving literal string tokens (`NA` is not null).
Integer fields accept only base-10 integer tokens (no decimal/exponent tokens).
It also requires local dependency JSON with exactly `edges` (pairs of group
IDs) and `qualification` (nonempty text describing the graph's limits).

Required CLI values: `--counts`, `--dependencies`, `--source-release`,
`--cohort-stage`, `--count-kind` (`called` or `quality`), `--evidence-role`,
`--prior-alpha`, `--prior-beta`, and a new `--out` directory. Optional
`--folds` defaults to5 and `--seed` to42. Supplied source identifiers are
explicit input assertions, not verification claims. No downloading, metadata
discovery, count extraction, or provenance invention in this runner.

The runner creates a new output directory exclusively and refuses reuse.
Invalid input/configuration fails before scientific outputs are published.
After structural validation, per-fold scientific infeasibility or numeric
failure is recorded and remaining folds run; output status and exit code
distinguish complete (0) from incomplete (2) comparisons.

Artifacts:

- `splits.json`: every train/test membership and held-out group; configuration.
- `row_status.tsv`: split_id, record_id, status, reason for every held-out row;
  status is `scored`, `unavailable_denominator`, `infeasible`, or `failed`.
- `predictions.tsv`: scoreable successful rows with split/source_record IDs,
  region_id, variant_group, operational group in cohort_id, counts, and the
  existing ten predictive diagnostics. No fabricated location fields.
- `posteriors.tsv`: successful fold/variant training counts and posterior shapes.
- `summary.json`: existing `summarize_benchmark` output, plus target/evidence,
  total/scored/unavailable/failed row counts, `joint_prediction_supported=false`,
  and `weighting_unit=source_population_group_not_independent_study`.
- `manifest.json`: input SHA256s; explicit source/qualification/config metadata;
  executed science-file SHA256s (including the runner); Git HEAD and dirty state;
  installed NumPy/SciPy/pandas versions; output SHA256s for the other five files;
  deterministic split/PIT seeds; and limitations above. No wall-clock timestamp,
  sample IDs, credentials, private absolute paths, or publication claims.

Summary expected-test IDs refer to scoreable rows for completed folds; the
separate full membership and row status account for unavailable rows. A failed
or infeasible fold retains its planned test IDs and failure reason. Unavailable
rows stay unavailable even when their fold fails. Every other test row receives
the fold outcome. Use the existing summary's operational weighting, explicitly
renamed in the enclosing research metadata; never call these independent cohorts.

## Acceptance and real-data protocol

Unit tests cover exact posterior arithmetic, preserved P1 sampled behavior,
literal IDs, invalid counts, zero denominators, graph transitivity, seed and row
order determinism, absent variants, exact Beta-binomial marginal agreement,
training/test separation, and complete failure accounting. CLI subprocess tests
use a tiny synthetic table and compare scientific artifacts byte-for-byte on
repeat runs. Executed imports must resolve to the runner's checkout even with a
conflicting PYTHONPATH.

After review, run the qualified 510-SNP chr22 pilot (80 population groups,
77 reported dependency components) on both predeclared cohort stages and both
count kinds with priors (1,1), five folds, and seeds42,43,44. Do not tune from
these runs. These 12 runs are correlated sensitivity checks, not independent
replicates. Report per-run errors, coverage, PIT, missingness, and failures;
do not pool across seeds as additional observations. Publish only aggregate
review evidence and artifact hashes after privacy checks. The single short
locus block and common reference source preclude global or external claims.
