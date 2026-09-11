# Paired B0/B0H reporting

The local reporter describes B0H minus B0 on matching withheld evidence. It
advances #211 and #189 WP1/WP4; the real comparison campaign remains incomplete.
It does not fit models or establish a model winner, external generalization,
resident-population performance, geographic prediction, joint LD, or publication
eligibility. Source populations and adjacent variants are dependent evidence.

Create a `pairs.json` with `schema_version: 1` and a `pairs` list containing all24
combinations of `cohort_stage` (`technical_qc_4117`,
`paper_ancestry_exclusion_4094`), `count_kind` (`called`, `quality`), `seed`
(42, 43, 44), and `rho_prior_beta` (9, 4). Each record also supplies
`b0_directory` and `b0h_directory`, resolved relative to that JSON file. Reuse the
same B0 directory across the two prior tracks. For example, one record is:

```json
{
  "cohort_stage": "technical_qc_4117",
  "count_kind": "called",
  "seed": 42,
  "rho_prior_beta": 9,
  "b0_directory": "publications/b0/technical_qc_4117/called/42",
  "b0h_directory": "publications/b0h/technical_qc_4117/called/42/9"
}
```

Run with the repository's locked environment and fresh output directories:

```bash
python scripts/compare_reference_counts.py --pairs pairs.json --out paired-report
python scripts/plot_reference_comparison.py --report paired-report/report.json --out paired-figure
```

The comparison CLI writes `report.json` and a manifest containing input, source,
package, and output fingerprints. Exit 0 means all24 publication pairs are
available; exit 2 can mean a valid matrix with absent directories, or an input
error (consult stderr and whether a report was produced). A present partial or
corrupt publication is a hard error. Scientific fold failures remain valid
reported evidence and are distinct from absent publications. Availability of all
publications does not mean all folds succeeded: inspect each comparison's
`comparison_complete`, `full_pair`, and `completed_fold_conditional` fields.

The figure has separate tracks for both priors and retains every identity.
Complete pairs use all five folds. Explicitly labelled conditional pairs use only
folds completed in both models; no-common-fold pairs and missing publications
retain visible rows without numbers. AN0 rows remain unavailable in the report;
they are never zero-frequency observations. The report also retains original
fold failures, support counts, exclusions, both model summaries, and cell-level
contrasts.

All differences are **B0H minus B0**. MAE, RMSE, and interval widths have frequency
units; integrated log score uses natural-log units; coverage differences are
percentage points. The figure shows MAE, log score, and all three coverage/width
levels (50%, 80%, 95%). RMSE remains in the report. Narrower intervals alone do not
establish improvement. Infinity and -Infinity are printed as text without a
finite-axis marker; two negative-infinite log scores produce
`undefined: both_negative_infinity`. No confidence intervals treat seeds or
linked variants as independent observations.

The plotting CLI produces `comparison.png` and `receipt.json`. The receipt
records the exact report and plotting source hashes, package versions, PNG hash,
all identities/statuses, and each plotted value, unit, and artist identifier.
Neither CLI overwrites an existing output directory. Retain private reports and
receipts locally; never commit real counts, posteriors, predictions, or private
research paths.

## Synthetic demonstration and regeneration

The committed [report](figures/reference_comparison_synthetic_report.json) is
exact output from the matrix CLI over tiny hand-set synthetic publications.
Its full provenance and fold/cell ledgers are intentionally retained. It contains
17 complete pairs, four conditional pairs, two wholly failed pairs, and one
absent pair. No real data or model fitting produced these examples.

![Synthetic reporting demonstration, not a model-performance result](https://raw.githubusercontent.com/bschilder/genomeOS/main/docs/figures/reference_comparison_synthetic.png)

Regenerate the image **directly from the committed report**, using a new output
directory each time:

```bash
python scripts/plot_reference_comparison.py \
  --report docs/figures/reference_comparison_synthetic_report.json \
  --out /tmp/genomeos-paired-synthetic-figure
```

The committed [receipt](figures/reference_comparison_synthetic_receipt.json)
links that report to the PNG and source bytes. To regenerate the underlying
synthetic publications and report as well:

```bash
PYTHONPATH=.:tests python tests/reference_comparison_figure_synthetic.py \
  --out /tmp/genomeos-paired-synthetic-inputs
python scripts/compare_reference_counts.py \
  --pairs /tmp/genomeos-paired-synthetic-inputs/pairs.json \
  --out /tmp/genomeos-paired-synthetic-report
```

The latter command deliberately returns 2 because one requested directory is
absent. The test below rebuilds these synthetic inputs, checks exact committed
report bytes, independently replays all 192 plotted values/states and all24
identity labels against actual Matplotlib artists, and checks output hashes and
input/overwrite refusals:

```bash
python -m pytest tests/test_plot_reference_comparison.py
```
