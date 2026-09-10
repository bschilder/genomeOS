# HBB rs334 corpus slice (Salih 2010) — coverage report

Date: 2026-09-09 (v0); revised 2026-09-10 after review round 1.
Staged under tests/fixtures/literature/hbb-rs334-salih-2010/.
Corpus: hbb-rs334-salih-2010. Source paper: Salih NA et al. Loss of
balancing selection in the betaS globin locus. BMC Med Genet 2010;11:21
(PMID 20128890, PMC2829010), Table 1 N row genotype counts (AA/AS/SS for
rs334 = chr11-5227002-T-A, counted ALT A = HbS) in two Sudanese villages.

## Coverage (per issue #151 recommended reporting)

- Candidates screened: 44 search rows across 3 PubMed queries
  (manifest v0, executed 2026-09-09). Row breakdown: 2 included, 13
  excluded, 29 pending. The 2 included rows are one source paper (Salih
  2010) matched by two different queries; the 13 excluded rows cover 12
  distinct PMIDs, because one PMID (35934714) matched two queries. The
  totals reconcile: 2 + 13 + 29 = 44. Exclusion reasons are documented per
  row (affected/clinical cohorts, case-control malaria groups, association
  studies, percentage-only tables, ancient DNA, duplicate 1000 Genomes
  path).
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

## Manifest provenance (reproducible discovery)

- The three ESearch responses this manifest was screened from are committed
  verbatim under `payloads/` (`Q1.json`, `Q2.json`, `Q3.json`), each carrying
  its query term, the endpoint, the request mode and the capture timestamp.
- `scripts/build_hbb_salih_fixture.py` replays those payloads by default and
  reads every timestamp from their capture metadata instead of the wall clock,
  so the three corpus files regenerate byte for byte. `--refresh` is the only
  path that queries PubMed, and the only path that rewrites the payloads.
- The corpus test runs the builder in replay mode and diffs the result against
  the committed files, so the manifest cannot drift from its stated source
  without failing CI.
- PubMed is a live corpus: a later refresh can return candidates that the
  screening table leaves `pending`. That is the expected outcome and it does
  not change this manifest until a refresh is explicitly run and reviewed.

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
- Note: Table 2's columns are HbA, HbS, HbS allele frequency, odds ratio
  (95% CI), relative risk (95% CI) and P value; its rows are malaria-status
  categories ("All malaria", "Clinical malaria", "Asymptomatic malaria",
  "Population control"), repeated under a Hausa block and a Massalit block.
  None of those rows is a population allele-frequency measurement for the
  atlas: they are malaria-status strata of the survey, not whole-population
  samples. The Population control row (Hausa HbA 72 / HbS 56, 128 alleles;
  Massalit HbA 97 / HbS 55, 152 alleles) is a subset of the survey and was
  not used. Its "All malaria" Hausa row totals 133 alleles against Table 1's
  N of 224, which is why it cannot stand in for the population. Any future
  use of Table 2 requires its own screening decision.

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

## Corrections applied (review round 1, 2026-09-10)

- Coverage arithmetic: the earlier text reported "1 included, 12 excluded".
  The manifest holds 2 included rows and 13 excluded rows of 44 (one paper
  included under two queries; one PMID excluded under two queries), leaving
  29 pending. Corrected above; the totals now reconcile.
- Table 2 orientation: the earlier text listed the malaria-status categories
  as though they were Table 2's columns. Table 2's columns are the
  statistics; the categories are rows. Corrected above. Both orientations
  were re-read from the PMC full text (PMC2829010). The substantive point is
  unchanged: Table 2 is a malaria-status subsample and cannot supply
  population counts, since its Hausa "All malaria" row totals 133 alleles
  against Table 1's N of 224.
- Manifest provenance: the ESearch responses are now committed as fixtures
  and replayed by default (see above), so the manifest is reproducible from
  the same bytes the screening was performed on.
- Builder: paths now go through argparse, timestamps come from the payload
  capture metadata rather than the wall clock, the field rows are driven off
  `TRACKED_FIELDS` instead of a hardcoded copy, and a CI test diffs a replay
  against this fixture.
