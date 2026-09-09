# GBD cardiovascular paper: full-text assessment for genomeOS

## Source and reading scope

Vaduganathan M, Mensah GA, Turco JV, Fuster V, Roth GA. *The Global Burden of
Cardiovascular Diseases and Risk: A Compass for Future Health*. J Am Coll Cardiol.
2022;80(25):2361–2371. [DOI:10.1016/j.jacc.2022.11.005](https://doi.org/10.1016/j.jacc.2022.11.005).
Supplied by the owner September 9, 2026 for the [#189 modeling program](https://github.com/bschilder/genomeOS/issues/189).

Read the complete supplied 11-page PDF, including methods, risk-factor sections, conclusions,
funding/disclosures and all 84 bibliography entries. Visually inspected the methods page 2362,
Central Illustration on 2363, and both tables on 2364. Reading a bibliography entry is not
reading its cited paper; the detailed GBD methods and linked regional almanac are not included
in this reading claim. The first whole-document extraction was truncated; separate page 1–4,
5–8 and 9–11 extractions were read completely afterward. Publisher web access returned 403;
the local PDF made browser credentials or remote uploading unnecessary.

Source fingerprint: 880,336 bytes; SHA256
`a78402329c2a43f464c6b6bf005d527c469e3eb690a657332d25b02938ae99c7`.
The PDF credits copyright to the American College of Cardiology Foundation and publication
to Elsevier. It does not provide a reusable data licence in the inspected text. This is a
record of the inspected article notice, not a completed reuse check for GBD input datasets.
No PDF, extracted full text, figure copy, genotype, or publication-evidence observation row
is redistributed here. These agent-authored research notes are not independently verified
field-evidence decisions and cannot promote anything into P1.

## Scientific contract

**Objective:** identify transferable measurement, uncertainty and validation practices, and
candidate ancillary sources that might improve independently tested resident-AF predictions.
**Output/acceptance:** traceable source-specific hypotheses and tests below; later covariate
admission still requires qualified access/support and incremental held-out AF performance.
**Component/interface:** this research note and WP0/WP1/WP3/WP7 plan clarifications only;
no production schema, fitter, data-ingestion or serving change.
**Assumptions/refusals/consumers:** the article concerns disease burden and modifiable risks,
not genotype counts or an AF reconstruction experiment. Its modeled estimates cannot become
observed alleles, geographic ground truth, ancestry labels or demonstrated migration. The
next consumers are source qualification, benchmark design, and separately governed burden work.

## What the article establishes

- **Measurement structure (pp 2361–2362):** GBD describes estimates over 204 countries and
  territories, organized across geographic levels and stratified by age and sex. Mortality
  inputs include vital registration and household surveys; disease incidence/prevalence use
  clinical definitions; risk exposures use population-representative surveys and surveillance.
  The article reports uncertainty intervals and cites GATHER. Estimates everywhere are not
  evidence of equally dense independent measurements everywhere.
- **Different quantities (p 2362; Central Illustration; Tables 1–2):** DALYs combine years of
  life lost and years lived with disability. Attributable fractions combine exposure, relative
  risk and a theoretical minimum-risk comparison. The illustration uses age-standardized
  DALY rates; the text says DALY rates are otherwise all-ages unless specified. Tables report
  deaths and DALY counts. These quantities and their denominators are not interchangeable.
- **Candidate context (pp 2362, 2365–2368):** ambient particulate pollution, household solid-fuel
  exposure, lead and temperature accompany metabolic and behavioral risks. The article discusses
  exposure duration, cumulative LDL exposure, and moderate nonoptimal temperatures as well as
  extremes. It does not demonstrate that any of these improves allele-frequency prediction.
- **Measurement can move without the same movement in disease (pp 2367–2369):** incomplete
  detection, unequal treatment access, and disrupted care during COVID-19 complicate the
  interpretation of recorded diagnoses and hospitalizations. These sections motivate explicit
  observation-process hypotheses, not automatic corrections to genomeOS counts.
- **Uncertainty must stay visible (Table 2, p 2364; lead section, p 2368):** the printed lead-related
  attributable-death/DALY uncertainty intervals include negative lower limits. Preserve that
  source fact and investigate its upstream statistical meaning before use; do not silently
  clip it or reinterpret it as a possible negative observed count. The prose uses CI and the
  tables UI; retain the author's labels instead of inventing a statistical equivalence.

This is a high-level methods overview plus prevention review, not a reproducible operator
architecture, genetic model, or independently validated fine-resolution AF dataset. It refers
the detailed estimation methods elsewhere. Neither its graphics nor its bibliography certify
the benchmark we need.

## Consequences for our plan — proposed by genomeOS, not paper findings

1. **Keep the target fixed.** Evaluate AF against qualified held-out allele counts and
   denominators. CVD burden depends on exposures, age structure, care, ascertainment and other
   factors; resemblance to a CVD map cannot validate genetic geography. An eventual disease
   model needs independently supported effect/penetrance, exposure and denominator components.
   Preserve the existing clinical golden tests and server-side trait restrictions.
2. **Separate three ancillary layer roles.** Environmental exposures are candidate covariates;
   care/screening variables are candidate observation-process descriptors; disease/metabolic
   estimates initially remain downstream/contextual outcomes. Any proposed use of the latter
   as AF predictors requires an explicit dependency/circularity analysis and separate ablation.
   This is not a blanket claim that predictive use is impossible, or a claim of causality.
3. **Record support, time and lineage before pixels.** Preserve native spatial/temporal units,
   observed versus modeled status, vintage, input lineage, uncertainty and missingness. Sampling
   or interpolating a country estimate onto fine H3 cells does not add local information. A
   model using upstream pooled data may already contain the evaluation evidence; audit that
   dependence before classifying an external resource as independent.
4. **Respect population composition.** Qualify age/sex coverage where supplied, and distinguish
   the actual resident target from an age-standardized comparison. Any reweighting requires
   documented sampling and population denominators, with prespecified sensitivity analyses.
   Missing age/sex metadata remains unknown, never a fabricated population composition.
5. **Add controlled admission tests, not mandatory layers.** For each qualified family compare
   the existing baseline, baseline plus the family, missingness/coverage-only, and spatially
   structured negative-control arms using the same outer folds, scored people and information
   cutoff. Fit preprocessing and tuning inside training partitions. Report performance by
   source support and sparsity alongside existing regional/rare-variant strata; do not choose
   strata or the winning layer from the sealed external set.
6. **Separate timescales.** Recent care/policy/pollution changes may affect observation and
   disease outcomes without identifying multigenerational allele dynamics. Treat historical
   exposures as uncertain, time-supported hypotheses; test selection separately from migration
   and drift. Contemporary risk maps do not justify backward extrapolation into deep time.
7. **Adapt the communication, not inferred precision.** The Central Illustration visibly marks
   unestimated places. genomeOS additionally needs distinct observation, inferred mean,
   uncertainty, support and validation layers. Keep native-support/denominator/standardization
   labels visible; do not reuse the paper's CVD color scale or imply disease risk from an AF map.

## Next source checks — not yet performed

The bibliography provides concrete leads, without requiring them to outrank the existing
terrain/count/benchmark priorities:

| Article reference | Lead to inspect in full | Question before admission |
|---|---|---|
|7|Wang et al., Lancet2020,396:1160–1203; age/sex demographic estimates1950–2019|Native support, uncertainty, census/model lineage, access terms; census size is not effective population size.|
|8–9|Vos et al. and Murray et al., Lancet2020; GBD disease and risk-factor methods|Actual estimation/validation procedures, dependence between published layers, available uncertainty draws.|
|10|Stevens et al., PLoS Med2016,13:e1002056; GATHER|Translate reporting requirements into an evidence checklist after reading the statement. Reporting compliance alone is not predictive validation.|
|42|Hammer et al., Environ Sci Technol2020,54:7879–7890; PM2.5 estimates1998–2018|Satellite/model/monitor composition, spatial and temporal support, independent validation and redistribution terms.|
|70–71|Gasparrini et al., Lancet2015,386:369–375; Zhao et al., Lancet Planet Health2021,5:e415–e425|Temperature-response versus exposure surfaces; geographic transfer, nonlinear effects, lags, and actual source availability.|

No new source is admitted by this note. The primary objective remains accurate, calibrated,
independently resolved allele frequency; disease burden is a separate downstream question.
