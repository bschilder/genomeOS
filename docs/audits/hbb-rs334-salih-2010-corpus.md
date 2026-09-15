# HBB rs334 corpus slice (Salih 2010) — coverage report

Date: 2026-09-09 (v0); revised 2026-09-10 after review round 1.
Staged under tests/fixtures/literature/hbb-rs334-salih-2010/.
Corpus: hbb-rs334-salih-2010. Source paper: Salih NA et al. Loss of
balancing selection in the betaS globin locus. BMC Med Genet 2010;11:21
(PMID 20128890, PMC2829010), Table 1 N row genotype counts (AA/AS/SS for
rs334 = chr11-5227002-T-A, counted ALT A = HbS) in two Sudanese villages.

## Coverage (per issue #151 recommended reporting)

Discovery and screening are separate versioned steps (design §5.1), so the
counts are reported against the step they belong to.

- Discovery — `searches.pending.tsv`, manifest version
  `hbb-rs334-salih-2010@2026-09-09.1`. 44 candidate rows across 3 PubMed
  queries, every one `pending`. Produced by `scripts/fetch_pubmed_manifest.py`
  from the payloads in `payloads/`; the query and `executed_at` behind each are
  recorded in `PROVENANCE.json`.
- Screening — `searches.tsv`, manifest version
  `hbb-rs334-salih-2010@2026-09-09.2`. A revision over exactly those 44 rows:
  2 `included`, 13 `excluded`, 29 `pending`. The totals reconcile,
  2 + 13 + 29 = 44. The 2 included rows are one source paper (Salih 2010)
  matched by two different queries; the 13 excluded rows cover 12 distinct
  PMIDs, because one PMID (35934714) matched two queries. Exclusion reasons are
  recorded per row (affected/clinical cohorts, case-control malaria groups,
  association studies, percentage-only tables, ancient DNA, duplicate 1000
  Genomes path).
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

## Manifest provenance (reproducible discovery and screening)

- `PROVENANCE.json` records, for each of the three queries, the exact query
  string, `executed_at`, the payload file, and the manifest version it produced.
  It also names `scripts/fetch_pubmed_manifest.py` as the tool that owns PubMed
  ESearch I/O for this corpus (design §4).
- The three raw ESearch responses are committed unmodified under `payloads/`
  (`Q1.json`, `Q2.json`, `Q3.json`).
- `searches.pending.tsv` is that tool's `build_manifest()` applied to those
  payloads, offline. The corpus test re-derives each query's rows from the
  committed payload and asserts they equal the committed snapshot, so the
  snapshot cannot drift from its source.
- `searches.tsv` is a screening revision over exactly those rows: same
  `search_id` and `candidate_id` set, same query and `executed_at`, with the
  decisions and the version advanced. The corpus test asserts that relationship,
  so a screening edit cannot silently change what discovery returned.
- These payloads were captured on 2026-09-09 with a direct NCBI ESearch call
  (`retmode=json`, `retmax=200`) before this workflow was applied to the slice.
  No live re-fetch has been run since, so the screened candidate set is the one
  that was reviewed. A later query is a new manifest version, never an edit to
  a past screening decision.

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

## Corrections applied

Review round 1, 2026-09-10:

- Coverage arithmetic: the earlier text reported "1 included, 12 excluded"
  against a single fused manifest. The two steps are reported separately now
  (see Coverage above), so the totals reconcile at every step.
- Table 2 orientation: the earlier text listed the malaria-status categories
  as though they were Table 2's columns. Table 2's columns are the
  statistics; the categories are rows. Corrected above. Both orientations
  were re-read from the PMC full text (PMC2829010). The substantive point is
  unchanged: Table 2 is a malaria-status subsample and cannot supply
  population counts, since its Hausa "All malaria" row totals 133 alleles
  against Table 1's N of 224.

Review round 2, 2026-09-10:

- Discovery was being reimplemented. The slice captured its own PubMed payloads
  and fused discovery with screening in one pass.
  `docs/literature-evidence-curation.md` step 1 names
  `scripts/fetch_pubmed_manifest.py` for discovery, and design §5.1 makes
  screening a later immutable manifest version over an all-pending snapshot. The
  bespoke fetcher is deleted. Discovery runs through that tool, and the two
  versions are published side by side: `searches.pending.tsv` (44 rows, all
  pending) and `searches.tsv` (the screening revision over exactly those rows).
- The screening verdicts move out of the builder and into the committed
  revision, where they are data rather than code. The 13 exclusion reasons are
  unchanged.
- Builder scope: `scripts/build_hbb_salih_fixture.py` now does only the part with
  no existing implementation, the deterministic transcription and derivation of
  the 2 records and 38 field rows. `--out` and `--extracted-at` are required
  arguments, the wall clock is never read, and the field rows are driven off
  `TRACKED_FIELDS`. The argparse convention and the design-section citation are
  in place.
- No live re-fetch was run. PubMed is live, so re-querying could return a
  different candidate set and would invalidate the screening that was reviewed
  against these 44. The pending snapshot is rebuilt offline from the committed
  payloads, and `PROVENANCE.json` says exactly that rather than implying the
  tool produced the original capture.
