# DHS Nigeria HbS benchmark qualification

September 10, 2026; bounded WP0 note for the global allele-frequency program
[#189](https://github.com/bschilder/genomeOS/issues/189). Status:
`automated_proposal` / `pending`.

## Scientific contract and decision

**Objective.** Assess whether public DHS metadata identifies a Nigeria HbS
measurement that could be considered for a future, independent benchmark.
**Output and acceptance evidence.** This source-located qualification/refusal
note records only the inspected public methods, form definitions, catalog and
access documentation. **Component and consumer.** It informs a later
data-access and benchmark-design review; it is neither an observation adapter
nor a model input. **Assumptions and refusal.** Missing assay semantics,
weights, residency rule, footprint, linkage, permissions, or reuse review are
not inferred. Accordingly, neither survey is qualified or promoted.

This boundary implements WP0's requirement to identify the target and record
unresolved metadata before benchmarking, and the Atlas requirement that
measurements, inferred surfaces, uncertainty, and provenance remain distinct
([WP0 plan](../superpowers/plans/2026-09-09-global-af-modeling.md#wp0--target-and-inventory),
[scientific contract](../scientific-engineering-objectives.md#ascertainment-and-representation),
[design §§4--5, 12](../superpowers/specs/2026-08-22-genome-os-atlas-v1-design.md)).
It reports no frequency, count, predictive skill, observation-model choice, or
new model result.

## Public-methods finding

- **Nigeria DHS 2018 (`NG2018DHS`): conditional metadata candidate, not
  qualified.** The final report describes capillary-blood SickleSCAN testing
  for children age 6--59 months, with HPLC confirmation in a subset (FR359
  §1.3--1.4, printed pp. 3--5). This is protein-based diagnostic testing, not
  DNA sequencing, an HBB variant-calling pipeline, or allele-count output.
  That distinction does not categorically disqualify it: a future reviewed
  category-to-copy-count observation model might be appropriate. This note
  approves no mapping, handling of ambiguity/other haemoglobin variants, or
  assay-error treatment.
- **Nigeria DHS 2024 (`NG2024DHS`): not an HbS candidate on the inspected
  methods.** The inspected report describes capillary-blood haemoglobin/anaemia
  measurement with HemoCue 201+ (FR395 §1.3--1.4, printed pp. 2--4), not an
  HbS assay. Haemoglobin concentration or anaemia classification is not HbS
  genotype. This is not a categorical assertion that no possible 2024 survey
  product contains an HbS measure; it is a refusal based on the inspected
  official methods. A further HbS qualification step requires new official
  documentation of an HbS assay.

## Eligibility, design, and result semantics

The 2018 form documents household-list, age, and consent elements, but not the
analytic genotype denominator as de-facto or usual-resident. It directs age
0--5 months at Q109 past the testing flow to Q130, and a `YES` to transfusion
within three months at Q112 to Q112C, bypassing genotype consent Q112A/Q112B
(FR359 Appendix E, printed pp. 690--691, Q109 and Q112--Q112C). These are
documented skip paths: a future analysis must not silently treat all non-tests
as random missingness. They establish neither a measured bias direction or
magnitude nor a clinical causal explanation.

Q113A's completion codes (tested, not present, refused, other) are different
from Q113B's displayed diagnostic labels `AA`, `AS`, `AC`, `SC`, and `SS`
(FR359 Appendix E, printed p. 692, Q113A--Q113B). The labels establish neither
HBB copy counts nor a conversion to them. A barcode location for a
confirmatory specimen (Q112F, printed p. 692) documents tracking, not that a
confirmatory result is released or linkable to the RDT record.

The 2018 report gives a stratified two-stage design and survey weights (FR359
§1.2, printed pp. 1--2), while its inspected material does not supply
sickle-test-specific nonresponse or an assay-specific analysis weight (FR359
§1.9, printed pp. 8--9). The generic DHS-VII recode manual's child section
does not prove that no Nigeria-specific genotype field, weight, or residency
rule exists (printed pp. 26, 29--30). Country-specific, permitted materials
must resolve those questions.

## Geography, access, and independence boundary

The public catalog lists a GPS Geographic Data product for both surveys, but a
catalog listing is not access or proof of a released join. General DHS guidance
displaces released **cluster points** by 0--2 km in urban areas and 0--5 km in
rural areas, with 1% of rural points displaced 0--10 km (GPS displacement
guide, chapter 1, printed p. 1). Those bounds concern points, not enumeration
areas, households, recruitment or biological footprints. This note assigns no
`uncertainty_radius_km`, claims no high-resolution geographic validation, and
does not interpret either survey as all-age or worldwide resident evidence.

DHS states that microdata/GPS and other biomarker access is project-specific
and subject to registration, request, and electronic acknowledgement; its
terms restrict approved-study use, sharing, redistribution, re-identification,
and publication ([access instructions](https://dhsprogram.com/data/Access-Instructions.cfm),
[terms](https://dhsprogram.com/data/Terms-of-Use.cfm)). No application or
agreement was initiated or accepted, and no restricted microdata or GPS was
downloaded. Public methodology review remains possible; it does not establish
reuse permission for this project.

## Inspection boundary and next checks

An earlier audit incidentally saw an aggregate genotype search snippet without
retaining or using values; it does not create a sealed benchmark. The later
six-page questionnaire/recode pass inspected blank forms and generic
definitions only, not outcomes. No data or results are committed by this note.

Before any 2018 promotion or model-improvement claim, an authorized,
project-specific review must establish all of the following:

1. Exact SickleSCAN and subset-HPLC result categories, validation, error
   properties, and a reviewed target-specific category observation model.
2. Permitted release and linkage of result, confirmation, design variables,
   weights, and displaced clusters.
3. Genotype eligibility, completion/nonresponse, analytic resident rule, and
   country-specific weighting treatment.
4. A defensible sampling-footprint representation, or an explicit spatial
   refusal rather than an invented radius.
5. Project-specific access/reuse permission and a reviewed independence/sealing
   determination before it is used as external confirmation.

Until then, this is **no promotion and no model-improvement evidence**. It
cannot relax WP0/WP1 qualification, the P1 required ascertainment/provenance
fields, or the separate observed-versus-inferred and refusal safeguards.

## Primary public locators

- [Nigeria DHS 2018 final report, FR359](https://dhsprogram.com/pubs/pdf/FR359/FR359.pdf):
  §1.2--1.4, printed pp. 1--5; Appendix E, printed pp. 690--692.
- [Nigeria DHS 2024 final report, FR395](https://dhsprogram.com/pubs/pdf/FR395/FR395.pdf):
  §1.2--1.4, printed pp. 1--4.
- [DHS-VII Recode Manual](https://dhsprogram.com/pubs/pdf/DHSG4/Recode7_DHS_10Sep2018_DHSG4.pdf):
  printed pp. 26, 29--30.
- [DHS GPS displacement guide](https://dhsprogram.com/pubs/pdf/SAR8/SAR8.pdf):
  chapter 1, printed p. 1.
- [DHS survey metadata API](https://api.dhsprogram.com/rest/dhs/surveys?countryIds=NG&f=json)
  and [dataset catalog API](https://api.dhsprogram.com/rest/dhs/datasets?surveyIds=NG2018DHS%2CNG2024DHS&f=json).
