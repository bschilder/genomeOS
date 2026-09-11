# Paired B0/B0H descriptive reports

This implements the reporting portion of #211 and #189 WP1/WP4, Atlas design
§§5, 7–8, 12. It follows the existing population-heterogeneity and reference-count
integration specifications. It does not admit a fit or replace either runner.

## Scientific contract

1. Objective: describe how explicit population heterogeneity changes withheld
   count prediction relative to pooled B0 on exactly matched evidence.
2. Evidence: independent small arithmetic examples, identity/membership refusals,
   complete failure accounting, deterministic reports, and a synthetic figure.
   Real comparative evidence remains unavailable until admitted runs finish.
3. Component: pure publication-byte comparison plus thin local CLI and plotting
   adapters. Existing public artifact validation and benchmark aggregation are
   reused; no private science imports and no fitting inside reporting.
4. Assumptions/refusals/consumers: source populations and adjacent variants are
   dependent development evidence. No independence-based interval, winner,
   promotion, geographic, resident, or joint-LD claim. Inputs must identify the
   same source, rows, counts, dependencies, split membership and PIT stream.

## Global constraints

- Keep all existing fitting, prediction, scoring, validation, artifact schema,
  source hashes and frozen comparison commands unchanged. Add focused modules.
- Real counts, posteriors, row predictions and private research paths stay out
  of Git. All committed examples and generated figures are explicitly synthetic.
- Science functions consume in-memory values, never paths, environment, network,
  HTTP, or global mutable state. No new dependency or stochastic calculation.
- Only complete immutable publications enter a pair. File corruption or identity
  disagreement is a hard error. A scientifically failed fold is valid retained
  evidence, distinct from an absent or corrupt publication.
- Preserve all five folds. Full-pair metrics are unavailable if either run is
  incomplete. A separately labeled completed-fold conditional report uses exactly
  the same completed folds and identical scoreable row membership in both models.
- AN0 rows remain unavailable; missing and zero are never conflated. All cohort,
  variant, region, split, and record IDs remain literal strings.
- Use the existing weighting: rows within population/region/locus cells, then
  populations within region/locus cells, then equal represented cells. Report
  cell support, unavailable/failed counts, exclusions and original fold failures.
- Difference direction is B0H minus B0. Log-score units are natural-log units;
  MAE, RMSE and widths are frequency units; coverage differences are percentage
  points. Narrower intervals alone are not an improvement claim.
- Compute each model's RMSE after its own weighted squared-error aggregation,
  then subtract. Do not average roots or substitute row differences for RMSE.
- Retain log scores of negative infinity and zero-probability counts at every
  reported aggregation level. Finite minus negative infinity is `Infinity`;
  negative infinity minus finite is `-Infinity`; two negative infinities give
  null with reason `both_negative_infinity`. Never emit JSON NaN or infinity.
- No outcome-dependent selection of prior, cohort stage, count kind, seed or
  fold. No confidence intervals using seeds or linked SNPs as independent units.
- Modules target 500 logical lines. Use typed interfaces and design docstrings.
  Every change is reviewed and delivered through a PR; no merge or deletion.

## Pair interface and validation

`compare_reference_publications(b0: Mapping[str, bytes], b0h: Mapping[str, bytes])
 -> dict[str, object]` lives in `genomeos.validation.reference_comparison`.
If needed, decoding belongs in a separate focused
`genomeos.validation.reference_comparison_inputs` module with a typed return.

The B0 input is exactly its five legacy output files plus manifest.json, schema1;
B0H is exactly its seven output files plus manifest.json, schema2. Reuse public
`validate_b0h_publication` for B0H, including its posterior companion checks.
Verify B0 file fingerprints with the same public fingerprint definition.
Parse JSON with duplicate-key/nonfinite-constant refusal; parse TSV IDs literally,
counts as exact nonnegative integers, diagnostics without lossy conversions.

Require equal target `reference_panel_within_resource`, evidence role,
source_release, cohort_stage, count_kind, prior_alpha/beta, folds and root seed;
both manifests deny joint prediction. Require equal count/dependency fingerprints,
dependency qualification, split seed and PIT-by-fold seeds. B0H's additional model,
rho and sampler settings stay explicit in the result; do not require its source,
backend or additional fit seeds to equal B0's.

Validate split IDs, train/test record and group membership, and split-local PIT
seeds across models, independently of the fold outcome. Require complete row
status coverage of test IDs, consistent unavailable membership and status/reason
relationships. Validate predictions against completed-fold scoreable IDs, unique
keys, finite/count-domain rules, and corresponding row statuses. At matched rows,
require equal variant, group, region, variant-group and observed AC/AN identities.
Reject duplicate rows, unknown extra predictions, missing scoreable rows,
predictions for failed folds, and malformed empty publications.

Recompute each model's complete and conditional summaries through public
`summarize_benchmark`; do not trust stored metric values. Keep stored summary
completion/count/target metadata consistent with the validated rows and ledgers.
Expose source manifest fingerprints and both model configurations, all fold
outcomes, matched/excluded/unavailable counts, summaries, and metric differences.
Return `publication_eligible=false`, `evidence_kind=descriptive_paired_comparison`,
and explicit dependence/target limitations. Reordering TSV rows must not change
the scientific result, excluding the deliberately changed byte fingerprints.

## Matrix CLI

`scripts/compare_reference_counts.py --pairs PAIRS_JSON --out NEW_DIRECTORY`
reads only local supplied publications. Its input has schema_version1 and a
`pairs` list; each record has `cohort_stage`, `count_kind`, `seed`,
`rho_prior_beta`, `b0_directory`, `b0h_directory`. Require exactly the full matrix:
technical_qc_4117/paper_ancestry_exclusion_4094 × called/quality ×42/43/44 ×9/4.
No duplicate/missing identities. Resolve directories relative to PAIRS_JSON's
parent, and bind every declared identity to the publication configuration.

If an entire requested publication directory is absent, retain that matrix row
as `not_available` with full expected identity, no metrics, and a reason; this is
not a failed scientific fold. A present but partial/corrupt directory is a hard
error. Do not silently skip it. Reused B0 directories are expected across priors.
No fitting, acquisition, remote transfer, watch/restart loop or acceptance override.

Write deterministic report.json for all24 identities and a manifest last, with
input specification, every consumed publication fingerprint, report fingerprint,
executed source hashes and actual relevant package versions. Use exclusive new
output directories. Exit0 only when all24 complete pairs are available; exit2
for a valid incomplete matrix. No publication output for corrupt input; preserve
any partial output after an I/O failure. No stochastic statistics or threshold.

## Figure

`scripts/plot_reference_comparison.py --report REPORT_JSON --out NEW_DIRECTORY`
renders all24 pair identities, grouping both prior tracks explicitly, with panels
for paired MAE, integrated log score, coverage differences, and interval widths.
Label direction and units, conditional/absent/failed rows, and undefined/infinite
contrasts visibly rather than omitting or coercing them onto a finite axis.
No fabricated uncertainty bars. Plot values must be independently replayed from
the report, and retained PNG plus source/receipt hashes must be reviewable.
Commit a tiny deterministic synthetic report and its PNG under docs/figures,
visually inspect it, and label it as a reporting demonstration rather than a
model-performance result. Real publication artifacts remain private and unchanged.
