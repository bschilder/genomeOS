# Demographic covariates: population grids are modeled inputs

Status: `automated_proposal` / `pending`, 2026-09-10. Advances
[#189](https://github.com/bschilder/genomeOS/issues/189) WP3; no source admission,
raster extraction, model fit or predictive gain is claimed. Atlas design §§4–9,
12 and the [global modeling plan](../superpowers/plans/2026-09-09-global-af-modeling.md).

## Scientific contract

Objective: test whether population counts and age composition improve withheld
allele-count prediction beyond the strongest eligible genetic/spatial baseline.
Output now: inspected candidate identities, source dependence and an extraction/
ablation checklist. Future output is an offline, immutable footprint-feature
artifact; raster/network I/O never enters pure fitters or serving.

Resident weighting, predictor inclusion and assumed recruitment weighting are
three separate uses. A population map establishes none of them automatically.
Missing dates, support, uncertainty or applicable terms stay explicit; population
grid resolution does not establish genetic resolution or sample representativeness.

## Candidates, not interchangeable versions

| Role | Exact proposed product | Retained distinction |
| --- | --- | --- |
| Legacy comparator | Global1 2020 global 1 km count mosaic, DOI `10.5258/SOTON/WP00647` | Unconstrained; unadjusted status is inferred from the archive's named parent family, not an inspected per-asset field. Confirm that inference before use. |
| Like-year count comparison | Global2 R2025A v1, 2020 global 1 km count mosaic, DOI `10.5258/SOTON/WP00845`, Hub `80026` | Constrained, modeled people per pixel; not a new census observation. |
| Composition comparison | Global2 R2025A v1, 2020 global 1 km age/sex mosaics, DOI `10.5258/SOTON/WP00846`, Hub `99402` | Separate f/m/t count layers and age bands; never add the total-sex layer to female and male layers. |

The archive identifies the legacy mosaic's parent family separately from its
UN-adjusted country products. Current count metadata specifies 30 arcseconds,
WGS84 and population counts, not density. This is not permission to relabel the
existing denominator artifact. [Global1 archive](https://hub.worldpop.org/Global1_2000-2020),
[legacy count metadata](https://hub.worldpop.org/geodata/summary?id=24777),
[Global2 count metadata](https://hub.worldpop.org/geodata/summary?id=80026).

Global2's age labels are `00` (provider wording: 0 to 12 months), `01` (1–4),
then five-year bands through `85`, followed by `90+`. Preserve the unresolved
endpoint wording; do not invent overlapping or nonoverlapping individual-age
assignments. Listed filenames contain `CN`, `1km`, `R2025A`, `UA`, `v1`.
The proposed 2025 time sensitivity includes both the count mosaic (Hub `80031`,
DOI `10.5258/SOTON/WP00845`) and age/sex mosaics (Hub `99407`, DOI
`10.5258/SOTON/WP00846`), at the same
R2025A v1 release and 1 km grid. Neither is a default for undated observations.
[2020 age/sex metadata](https://hub.worldpop.org/geodata/summary?id=99402),
[2025 count metadata](https://hub.worldpop.org/geodata/summary?id=80031),
[2025 age/sex metadata](https://hub.worldpop.org/geodata/summary?id=99407).

## Lineage changes the experiment

Global2 disaggregates administrative counts using modeled density weights and
settlement constraints. Its national totals match January-1 WPP 2024 estimates.
Census inputs and interpolation/projection methods vary by country; some use a
single input timepoint. Its alpha release and master grid differ from Global1.

Elevation, slope, climate, land cover, lights and settlement already contribute
to the population model. Settlement inputs include GHSL, Google and Microsoft
building footprints and World Settlement Footprint. Thus agreement with terrain
features or another settlement-driven population product is not independent
confirmation. Missing cell-level uncertainty is not zero uncertainty; rapid
displacement and intra-annual mobility are not reliably represented by this series.
[WorldPop R2025A release statement, Inputs, Mastergrid, Covariates, Methods and Assumptions](https://data.worldpop.org/repo/prj/Global_2015_2030/R2025A/doc/Global2_Release_Statement_R2025A_v1.pdf).

## Access and remaining qualification

Inspected Hub pages list direct downloads, but both old and new count pages carry
CC BY 4.0 alongside ODbL language for OSM/Microsoft-derived products. The Global2
statement names Microsoft footprints as an input. Do not infer a single licence
for the exact assets or derived artifacts from the generic notices alone; resolve
applicability through asset documentation or provider clarification before
redistribution. Ordinary in-scope research is already authorized; this note adds
no blanket user-approval requirement. [Global1 notices](https://hub.worldpop.org/geodata/summary?id=24777),
[Global2 notices](https://hub.worldpop.org/geodata/summary?id=80026).

The existing population pipeline sums pixel counts into H3, records raster hashes,
and fills absent cells from ordered supplements. Those mechanics do not certify
units, acquisition dates or survey recruitment. Its negative-count validation
defect is separately tracked in [#241](https://github.com/bschilder/genomeOS/issues/241);
no published-data impact or fix is claimed here. Gridded births remain the
separate [#96](https://github.com/bschilder/genomeOS/issues/96) burden question.

Before extraction, freeze exact assets/checksums, grid/datum/units/nodata, source
and modeled years, available date, country input metadata and applicable terms.
Country source workbooks and actual raster contents have not been inspected here;
100 m-to-1 km aggregation and cell-level uncertainty remain unverified.

## Falsifiable comparison

Predeclared composition representation: aggregate the 40 female/male age-band
counts over identical valid footprint support, then divide each by their sum
`S`. The composition-only arm receives these 40 shares, not `S`, raw counts or
the duplicate `t` layers; `t` is used for reconciliation only. Require complete
finite nonnegative inputs and `S > 0`. A valid zero band stays zero; missing
support or `S = 0` makes composition unavailable, with no pseudocount or imputed
age structure. Retain that status and apply the same frozen evaluation-coverage
policy across arms, rather than dropping different outcome rows from each arm.

1. Specify mass-conserving footprint aggregation and report valid/excluded support;
   preserve zero versus missing. Test borders, grid misalignment and unsupported
   units before real extraction. Reconcile age/sex and country totals against
   documented constraints with a predeclared tolerance; never silently rescale.
2. Freeze comparable populations, folds, allele outcomes and scoring weights.
   Compare baseline, count-only, composition-only, both, missingness-only and
   spatially structured controls; test incremental value after terrain and genomic
   structure. All preprocessing/selection stays inside training partitions.
3. Select features on inner/development evidence; retain every outer-fold outcome
   and failure. Report paired uncertainty, calibration and regional/rare-allele
   strata. Changing the available-case set is not a predictive improvement.
4. Separate retrospective estimates from information-available-at-the-time
   prediction. A 2025-produced grid for 2020 is not a feature available in 2020.
   Undated modern allele observations do not become present-year surveys.

No source files, rasters, credentials, agreements, genetic observations, schemas,
denominators or serving behavior were changed by this qualification note.
