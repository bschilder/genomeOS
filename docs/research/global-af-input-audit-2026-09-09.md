# Local allele-frequency input qualification audit

September 9, 2026; research program [#189](https://github.com/bschilder/genomeOS/issues/189).
This is a read-only inventory of available metadata, not independent source review or a
certification of permissions, residency, study independence, or prediction accuracy.

## Scientific contract

The objective is to identify what local evidence can support a future present-day resident
allele-frequency benchmark. The output is a traceable inventory with explicit exclusions and
missing qualification evidence. The planned offline inventory/split/report interfaces consume
reviewed P1 tables; compact browser exports are not substituted for those tables. Missing
population semantics, dates, dependency edges or reuse checks remain unknown.

## Available inventory

The canonical browser catalog is `website/public/data/atlas/catalog.json`, SHA-256
`8d6ddf4cc19534757f9dcabe76068d7e42651f4b7cfac670d583816ddcaefab0`.
Counts below follow its measurement declarations; the catalog's own reviewed-source statements
are not an independent verification performed by this audit.

| Declared measurement | Entities | Rows | Interpretation |
| --- | ---: | ---: | --- |
| Allele frequency | 25 | 7,426 | HbS 1,071; HLA 6,010; cytokines 345 |
| KIR carrier frequency | 4 | 937 | Individuals carrying a gene, not allele counts |
| G6PD deficiency phenotype | 1 | 910 | Composite phenotype, not one allele |

Rows and distinct cohort labels do not count independent individuals, studies, populations or
locus blocks. Repeated variants and exported copies cannot be counted as new evidence.
`website/dist` and `website/dist-fallback` are not additional source cohorts.

The local source inventory at `data/store/INVENTORY.json` records hashes for snapshots including
`data/raw/afnd_frequencies.tsv`, `data/raw/afnd_populations.tsv`,
`data/raw/map_hbs_surveys.csv` and `data/raw/map_g6pd_surveys.csv`.
No materialized P1 observation or population-registry store, or harmonized gnomAD frequency input,
was found during this audit. The normal complete fixture build cannot be relabeled a real-data
build when those inputs are absent. `data/store/artifacts/*/cells.parquet` contains inference;
`demo/artifacts/observations.parquet` is synthetic.

## Qualification gaps

- Browser observations omit `population_id`, date bounds and `location_type`. Reconstructing them
  from labels or defaults would manufacture evidence.
- P0 distinguishes sampling, ancestral and inferred coordinates, not present-day resident
  populations. AFND's grandparents criterion encodes ancestry; a sampling coordinate alone does
  not establish residency or resident composition. MAP uses direct survey coordinates.
- Existing adapters use legacy modern dates of zero. Zero means date-unspecified modern data,
  not a survey conducted in the current year.
- Published exports have already been used for fitting. No local sealing/model-access ledger
  establishes an untouched external confirmation set.
- Cohort IDs do not certify participant, kinship, study-table or panel-release independence.
  The benchmark requires reviewed dependency edges, including resources derived from genotypes.
- HLA `frequency_reconstructed` counts derive from rounded frequencies and denominators. The
  cytokine adapter derives allele counts from complete reported genotype-frequency triples,
  without Hardy–Weinberg reconstruction. Neither derivation can be silently upgraded to exact
  directly reported counts for a count-calibration claim; source precision needs review.
- Geography needs more than valid numeric coordinates. MAP currently substitutes a fixed area
  when extent is missing, unbounded or unrecognized. That assumed radius is not a guaranteed
  recruitment footprint for a buffered split. This was filed separately as
  [#190](https://github.com/bschilder/genomeOS/issues/190); no adapter or artifact was changed.
- Reuse-review state and biocultural notices are not carried in browser observation exports.
  Read the contributing source records before qualification; public visibility is not export
  permission. The owner's resolved
  [#66 decision](https://github.com/bschilder/genomeOS/issues/66#issuecomment-5565166083) allows
  fitted-surface redistribution with attribution and biocultural notices, clear identification of
  inference versus observation, and explicit source restrictions honored. That conditional policy
  permission does not replace source qualification; this milestone publishes no scientific surface.

## Consequence for implementation

Analytical tests, synthetic leakage tests and a reproducible baseline runner can establish
engineering correctness now. They cannot establish resident representativeness, independent
generalization or finer scientifically supported spatial resolution. WP0 input qualification and
WP1 current-model/external confirmation gates remain open. No new model should be promoted merely
because it beats the baseline on these fixtures or on previously consulted exports.
