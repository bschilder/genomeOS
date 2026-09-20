# HbS external newborn-screening qualification

**Date inspected:** 2026-09-16
**Program:** global allele-frequency modeling WP0/WP1; issue
[#189](https://github.com/bschilder/genomeOS/issues/189)
**Status:** development evidence only; no source admitted to P1 and no final external set sealed

## Scientific contract

**Objective.** Determine whether four title-screened post-Piel HbS newborn-screening studies
can test a present-day resident allele-frequency model, and distinguish scientific eligibility from
paper/data reuse permission.

**Measurable output and acceptance evidence.** For each study, record the recruited population,
dates, assay, selection mechanism, geographic support, reuse/dependency risk, access terms, and a
fail-closed verdict. A study is not final external confirmation unless its outcome remained unseen
through model and candidate selection.

**Engineering component and public interface.** This is a methods/source qualification note only.
It changes no observation, schema, fitter, benchmark, surface, burden result, or serving path.

**Assumptions, refusals, and consumers.** The documented 2015–2025 recruitment windows all
postdate the Piel 2013 survey compilation, so these participants could not have contributed to it.
That timing does not establish population representativeness or independence from every later
paper. Hospital location is not silently used as participant residence or ancestry. No coordinate,
catchment footprint, uncertainty radius, allele count, or assay interpretation is invented. The
consumers are the WP1 benchmark, #45, and #103.

## Determination

All four records are **consulted development evidence**, not a sealed final test set. Their outcome
summaries became visible while retrieving their methods on 2026-09-16. Later withholding the
numbers would not restore sealing. Exact outcome values are deliberately not copied into this note.

The 2026 Luanda program is the strongest high-powered development candidate. The Dar es Salaam
program is informative but resource-timed and excludes ill newborns. Caluquembe adds a valuable
rural contrast but is small and referral-biased. The Italian program is useful for two mixed-origin
hospital birth cohorts; it is not an estimate of a homogeneous Italian population. None is eligible
for a point-resident surface observation from the published methods alone.

## Reproducible discovery snapshot

The four leads came from the complete 210-candidate PubMed discovery snapshot captured before
source qualification. The immutable pending manifest is retained at
[`hbs-newborn-external-searches-2026-09-11.tsv`](hbs-newborn-external-searches-2026-09-11.tsv).
It has 210 candidate rows, manifest version `hbs-newborn-external@2026-09-11.1`, and SHA-256
`0c3d4044d353a869b5f795a7526002b94374b4956b2b72fa2e59af0f95d799f2`. Every decision remains
`pending`; the methods review in this note does not mutate the discovery record into an inclusion
decision.

| Candidate | Recruited population and measurement | Geography/selection limit | Terms and data | Verdict |
|---|---|---|---|---|
| [Padova and Monza, Italy, 2016–2017](https://doi.org/10.1002/pbc.27657) (PMID 30724025) | Newborns in two tertiary university hospitals; Guthrie-card HPLC with molecular confirmation of positive/low-HbA results | Padova excluded NICU infants and Thursday/Friday births; Monza included maternity and NICU births seven days/week. Family origin was mixed. Center coordinates cannot stand for residence, ancestry, or either region. | The article carries Wiley copyright and no permissive article or data licence was found. Treat as citation-only pending a source-specific permission check. | Potential center-stratified development check after structured extraction; not sealed, national, or P1-ready. |
| [Dar es Salaam, Tanzania, 2015–2016](https://pmc.ncbi.nlm.nih.gov/articles/PMC7967808/) (PMID 31145786) | Newborns up to two days old at Muhimbili National and Temeke Regional hospitals; dried blood spots and isoelectric focusing, with abnormal screens repeated | Ill newborns and non-consenting families were excluded. Collection ran only a few hours on resource-available days. Published regions include a residual “other” group and do not provide reviewed recruitment footprints. An FS screen is not silently converted to a homozygous genotype count. | The 2019 article is free to view, but the journal states pre-2020 content is all-rights-reserved. No reusable row-level dataset was identified. | Promising cohort/region development check once phenotype semantics and footprints are reviewed; not direct AF input or sealed evidence. |
| [Caluquembe, Angola, 2024–2025](https://doi.org/10.1371/journal.pone.0335720) (PMID 41166322) | Infants under one month delivered at or otherwise linked to Hospital Evangélico de Caluquembe; heel-prick HemoTypeSC, repeat/review of indeterminate tests | A rural referral hospital serving complicated deliveries in a province where many births occur at home. Published data omit addresses; the hospital catchment is not a measured recruitment footprint. | Article and supporting information are CC BY 4.0. The public dataset intentionally removes identifying dates and addresses. | Useful rural development contrast with explicit selection limits; too small and geographically under-specified for resident-surface validation. |
| [Luanda, Angola, 2023–2024](https://doi.org/10.1016/j.bcmd.2026.102988) (PMID 41719825) | Infants born at or attending vaccination at Hospital Materno-Infantil Dr. Manuel Pedro Azancot de Menezes within the first month; IEF, PCR-RFLP confirmation of HbSS screens, and sequencing of atypical patterns | One hospital plus its vaccination room broadens coverage to some home births, but residence and catchment membership are not reported. Independence from other post-2013 Luanda publications is not yet certified row-by-row. | Article is CC BY 4.0. Deidentified participant data require a justified request and institutional approval, so the article licence does not make the underlying data freely redistributable. | Strongest aggregate external development candidate; not national, P1-ready, or sealed final confirmation. |

## Source-specific evidence

### Italy

The primary article reports distinct collection windows: Padova from 2 May 2016 through 30 November
2017, and Monza from 1 September 2016 through 31 August 2017. Padova sampled five days per week
and omitted NICU infants, while Monza sampled maternity and NICU infants seven days per week.
These differences require two cohort identities and sampling-design fields; pooling them behind one
“Italy” label would erase known ascertainment differences. The methods and limitations are in the
[full article](https://www.teamforchildren.it/wp-content/uploads/2016/05/RESULTS-OF-A-MULTICENTER-UNIVERSAL-NEWBORN-SCREENING-PROGRAM-FOR-SICKLE-CELL-DISEASE-IN-ITALY.pdf).

### Dar es Salaam

The study ran from January 2015 to November 2016, with blood-spot collection from October 2015
through September 2016. It recruited from two hospitals whose services extend beyond Dar es
Salaam. Screening was a resource-bounded pilot rather than continuous enumeration of all births.
The paper records participant locations privately and reports aggregates for Ilala, Kinondoni,
Temeke, and other regions, but the public report does not justify a point location or a single radius
for each aggregate. The [primary full text](https://pmc.ncbi.nlm.nih.gov/articles/PMC7967808/)
describes the recruitment and IEF workflow. The journal states that
[content before its 2020 open-access transition is all-rights-reserved](https://academic.oup.com/inthealth/pages/About).

### Caluquembe

Eligibility included infants born at the hospital and several categories of infants or family members
admitted there between October 2024 and February 2025. The hospital is a regional surgical referral
center, and the paper explicitly notes that hospital-born infants may differ systematically from home
births. This makes the cohort useful as a rural hospital contrast, not as a municipality-wide random
sample. The [primary article](https://journals.plos.org/plosone/article/file?id=10.1371/journal.pone.0335720&type=printable)
documents the eligibility, assay quality control, selection limits, CC BY licence, and public
supporting data.

### Luanda

The program recruited from June 2023 through December 2024 at one large maternity hospital and
its vaccination room. All screened infants were in their first month, no parent refused, and the
laboratory workflow used IEF with molecular confirmation for HbSS screens. That is substantially
stronger measurement evidence than a point-of-care screen alone. It still identifies a recruited
hospital/vaccination cohort rather than all Luanda residents. The
[primary article](https://repositorio.ipl.pt/bitstreams/a0116d72-de13-4d0f-afbd-ce91501bc754/download)
documents the design, assay, CC BY licence, and request-and-approval data access.

The related 2023 Luanda point-of-care study recruited a convenience sample of infants up to six
months at ten maternity/vaccination facilities and used a different protocol. The publications do not
provide a participant-level join, so absence of overlap is not certified. Record a dependency edge as
`possible_overlap_not_resolved` until dates, facilities, and participant identifiers can be reconciled.

## Consequence for WP1

These four studies can support prespecified **development** checks after their observation semantics
and P0 geography are reviewed. They cannot satisfy the plan's genuinely sealed external-confirmation
exit gate. The remaining candidate pool needs an outcome-separation procedure before another paper
is opened:

1. freeze candidate IDs, bibliographic metadata, eligibility rules, and source hashes;
2. select studies using dates, methods, target population, and access terms without exposing results;
3. have a distinct outcome custodian retain count fields and release them once, only after model,
   hyperparameters, split rules, and acceptance thresholds are frozen;
4. permanently relabel any accidentally consulted candidate as development evidence;
5. refuse the final claim if no independent custodian or technically enforced separation exists.

The immediate development priority is to structure the Luanda 2023–2024 and Dar es Salaam cohorts
as cohort-level benchmark candidates without inventing resident geography. That work must preserve
screen phenotype versus confirmed genotype semantics and cannot be used to tune against the Piel
national burden totals.

## Environmental-covariate policy

No Malaria Atlas Project product, Google Earth Engine layer, satellite embedding, vegetation index,
friction surface, or other environmental covariate was used to select or qualify these studies.
MAP data have no privileged scientific status in this program. A permissive licence permits an
experiment; it does not establish relevance to present-day resident HbS allele frequency.

An environmental source should enter a prespecified candidate comparison only when its spatial and
temporal support match the target and there is a concrete mechanism or representation hypothesis to
test. It advances only if a geography-blocked comparison improves integrated count predictive score
with a positive paired 95% confidence interval, contributes to the program's balanced-MAE target,
keeps coverage within three percentage points of nominal, and does not degrade any powered stratum
by more than five percent. Otherwise it is a dead end for this model, regardless of its malaria
branding or licence.
