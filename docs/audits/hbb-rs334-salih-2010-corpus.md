# HBB rs334 corpus slice (Salih 2010) — coverage report

Date: 2026-09-09 (v0, pre-review).
Staged under tests/fixtures/literature/hbb-rs334-salih-2010/.
Corpus: hbb-rs334-salih-2010. Source paper: Salih NA et al. Loss of
balancing selection in the betaS globin locus. BMC Med Genet 2010;11:21
(PMID 20128890, PMC2829010), Table 1 N row genotype counts (AA/AS/SS for
rs334 = chr11-5227002-T-A, counted ALT A = HbS) in two Sudanese villages.

## Coverage (per issue #151 recommended reporting)

- Candidates screened: 44 search rows across 3 PubMed queries
  (manifest v0, executed 2026-09-09); 1 source paper included at table
  level (Salih 2010). 12 candidates excluded with documented reasons
  (affected/clinical cohorts, case-control malaria groups, association
  studies, percentage-only tables, ancient DNA, duplicate 1000 Genomes
  path). Remaining candidates pending.
- Records staged: 2 (one per population measurement)
- Field-evidence decisions: 38 (19 per record)
- Records promoted to P1: 0
- Refusals at the promotion gate (expected, documented reasons):
  - verification pending: 2 (automated extraction cannot verify itself;
    independent reviewer required)
  - methods fields (assay, sampling design, dates, cohort identity,
    ascertainment): not_reviewed on all 2 (Methods are present in the PMC
    HTML but per-row survey attribution is not itemized; the independent
    full-text review pass is required before any field is claimed)
  - reported_frequency: not_reported on all 2 (no whole-population allele
    frequency printed for the Table 1 totals; Table 2 reports
    malaria-strata allele counts only)
- Distinct populations: 2 villages in eastern Sudan:
  - Hausa, Koka village (~40 km east of Um-Salala)
  - Massalit, Um-Salala village (eastern bank of the River Rahad,
    ~400 km south-east of Khartoum; tribe migrated from El-Geneina,
    Darfur in the 1980s)
- Sample identity: family-based village surveys, 8 surveys 1994-2006;
  546 individuals genotyped from 65 (Hausa) and 82 (Massalit) families;
  Table 1 totals are the 470 INDEPENDENT genotypes (224 Hausa,
  246 Massalit) after relatedness exclusion.

## Unresolved population registry proposals (NOT in fixture, cf. #21)

| population_label | Village (paper) | Coordinates / radius | Status |
|---|---|---|---|
| Hausa | Koka village, River Rahad, eastern Sudan | not published in source | unresolved — audit material |
| Massalit | Um-Salala village, River Rahad, eastern Sudan | not published in source | unresolved — audit material |

No coordinate, radius, or population alias is inferred or defaulted. The
evidence rows carry only the paper's verbatim population labels (Hausa,
Massalit). Promotion refuses until a reviewed `literature` P0 alias exists
for each label with exact lat/lon/uncertainty_radius_km.

## Orientation record (issue #151 refusal guard)

- rs334 = HBB c.20A>T, p.Glu7Val (missense, MANE ENST00000335295).
- Atlas/gnomAD v4 normalized id: chr11-5227002-T-A; REF=T, ALT=A.
- ALT A is the HbS allele (verified against the genomeOS cached gnomAD
  payload website/public/data/atlas/external/gnomad/chr11-5227002-t-a.json;
  ClinVar Pathogenic; Hb SS disease MedGen C0002895).
- Paper AA/AS/SS are allele-specific PCR calls (HbA/HbS). Class mapping
  to the atlas: SS = AA (alt/alt), AS = TA (het), AA = TT (ref/ref).
- Counted allele: A. Derived S counts: Hausa AS+2SS = 91+30 = 121 of 448;
  Massalit 68+30 = 98 of 492.
- Note: the paper's own malaria-strata counts (Table 2: "All malaria",
  "Clinical malaria", "Asymptomatic malaria", "Population control") are NOT
  population allele-frequency measurements for the atlas; the Population
  control row (Hausa 72/56 of 128; Massalit 97/55 of 152) is a subset of
  the survey and was not used. Any future use of Table 2 requires its own
  screening decision.

## Reuse

- License: CC BY 2.0 (Open Access). Terms check recorded per surface:
  BMC article page and PMC page. Finding: no_restriction_found
  (boilerplate/permissive license does not restrict factual-data reuse).
- reuse_evidence checks array is committed with each record.

## Reconciliation vs MAP/Piel (issue #151 deliverable, NOT YET DONE)

- The Piel 2010 (ncomms1104) survey database source list has not yet been
  checked for this study. Expected next step: compare study identity with
  the MAP adapter corpus rows in the P1 build and report exact matches /
  explained transformations / duplicates / unresolved mismatches. This
  audit doc will be extended when the reconciliation report exists.

## Corrections applied (none yet; v0 pre-review)

- Awaiting maintainer review. Any review findings will be logged here with
  the fix commit, mirroring the LCT corpus process (PR #156).
