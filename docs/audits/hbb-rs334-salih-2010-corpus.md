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

## Reconciliation vs MAP/Piel (issue #151 deliverable, in progress)

### Step 1 — the Piel 2010 source list does not contain this study

Checked 2026-10-01 against the source list of the assembly behind the MAP HbS corpus: Piel et al.
2010, *Nature Communications* 1:104 (doi:10.1038/ncomms1104), Supplementary Figures S1-S2,
Supplementary Methods and **Supplementary References**, 25 pages, 342 numbered entries.

- Retrieved file: `41467_2010_BFncomms1104_MOESM456_ESM.pdf`, 438,548 bytes,
  SHA-256 `8f4f11a8ea0b9bd57d5b5cc8b9d1d326cb83b4ee1d70bbae3930839fee9cf3a5`.
- Method: extract all 25 pages to text and search the full text for the study's identifiers, not by
  title. The extracted text is 62,551 characters with `pypdf` (62,627 with the extractor used on
  2026-10-01; a character count is extractor-dependent, so it is not a property of the document), and
  it includes the supplementary reference list, which is numbered inline past 300 (highest entry seen,
  341). The reference-entry count is not stated here because the extracted numbering has gaps and a
  count is not reproducible from text.
- Result: **0 occurrences** of `Salih`, of PMID 20128890, of `BMC Med Genet`, and of the paper's
  village and population labels (`Um-Salala`, `Hausa`, `Massalit`).
- Control: the same text does contain Sudan studies — 8 occurrences of `Sudan`, all 8 named here
  (Bayoumi et al. 1985, Fur and Baggara tribes; Fleming et al. 1979, Sudan savanna of Nigeria; Foy et
  al. 1964, Kenya and the Southern Sudan; Lauder & Ibrahim 1970, south-west Kordofan; Nasr et al.
  2008, eastern Sudan; Omer et al. 1972, tribes of the Sudan; Roberts & Lehmann 1955, southern
  Sudanese peoples; Saha 1981, a Sudanese population). So the search finds Sudan entries when they
  exist, and this study is not among them.

**What this establishes.** Salih et al. 2010 (BMC Med Genet 11:21, PMID 20128890) is not a cited
source of the Piel 2010 assembly. For this corpus row the duplicate risk against the Piel path is
therefore not merely unresolved: at the level of that source list there is no Piel survey record
for a study published in January 2010 to collide with, and the row is an addition to the region
rather than a re-count of a cohort already in the P1 build.

**What this step does not cover.** It reads the 2010 assembly's source list. The layer the parity
run actually consumes is a later and larger release, so a match against that layer is a separate
check, and it is the one Step 2 runs. No identity was inferred from geography or from a title.

### Step 2 — the layer the parity run consumes, and the live layer, both checked

Run 2026-10-07. The input Step 1 could not reach is fetched by this repository's own tool rather than
reconstructed: `scripts/fetch_map_hbs.py --out <path>` writes the `Explorer:HbS_Data` WFS response
(`outputFormat=csv`, no credentials).

- Fetch window 2026-10-07T22:08:31Z to 22:08:33Z, repeated at 22:14:06Z to 22:14:07Z. Both responses
  are 402,028 bytes with 1,287 data rows.
- The response is **not byte-stable**, and the reason is exactly one column: GeoServer's `FID` is a
  per-request feature id (`HbS_Data.fid-...-6220`, `...-6728`, `...-6764` across three requests). With
  `FID` removed every request is identical: data-column SHA-256
  `3d6a4f6040c0806dbb4331745918999a220c56afa83d7befd7ca54e48c0702f1`, reproduced on all three
  fetches. Whole-response SHA-256 varies per request by design of that column and three observed
  values are `457ea3ab...`, `a5a5bf38...` and `26ad330d...`; none of them identifies the layer. A
  later check compares the data-column hash with the byte count and the row count, and does not read a
  changed `FID` as a changed layer.
- Second layer checked: the committed artifact the P1 path holds,
  `website/public/data/atlas/hbs-rs334.observations.json`, `data_version` `map-2026-08`, 1,071 survey
  records. Every one of its 1,071 survey ids is present in the live layer.
- The live layer has **grown**: 216 survey ids are in today's response and not in the committed
  artifact (1,071 to 1,287). The comparison was therefore run twice, once against the immutable
  artifact and once against the live layer, because a match found only in the newer layer could not
  bind the P1 path.

**Result: no collision, in either layer.**

- Study identity: **0 occurrences** of `Salih`, of PMID 20128890, of `BMC Med Genet`, of `Um-Salala`
  and of `Massalit`, in the committed artifact (1,071 records) and in the live layer (1,287 rows).
- All 41 Sudan rows in the live layer are also in the committed artifact, and none of them is this
  study. They resolve to ten other studies: Foy 1964 (13 rows), Vella 1966 (7), Omer 1972 (7),
  Lauder & Ibrahim 1970 (3), Roberts & Lehmann 1955 (3), Saha & Patgunarajah 1981 (3), Vella 1965
  (1), Saha 1981 (1), Samuel 1981 (1), Bayoumi 1985 (1) and Nasr 2008 (1).
- Count identity, in the layer's own units. The allele counts are not read from a column; they are
  derived, and the derivation is fixed by the committed artifact rather than chosen: **an = 2 x (AA +
  AS + SS)**, with a blank `hbaa` cell recovered as `sample_size - hbas - hbss`, and **ac = hbas + 2 x
  hbss** with a blank `hbss` read as zero. That rule reproduces the committed payload's `an` and `ac`
  exactly on **1,071 of 1,071** records, 0 mismatches, so it is the layer's unit definition and any
  comparison has to use it. Deriving `an` as `2 x sample_size` instead is wrong for 207 of those
  1,071 records, and an earlier draft of this section made exactly that error.
- Under that rule the comparison covers **1,185 of the 1,287 live rows**; 102 rows are not derivable
  because the cells the rule needs are empty. The two corpus rows carry an/ac of 448/121 (Hausa) and
  492/98 (Massalit). **No row in either layer carries either pair.** The nearest rows, named so the
  refusal is checkable: at an 492, id 1193 Schiliro 1986 (Italy) has ac 5 and id 879 (Burkina Faso)
  has ac 19; the rows carrying ac 98 are id 406 (Kenya, an 916), id 994 (Gambia, an 994) and id 1034
  (India, an 1018); and the single row carrying ac 121 is id 1075 (Belgium, an 19,150). No row in the
  layer has a `sample_size` of 224 at all; the two rows at 246 are id 1193 (Italy, genotype total 246,
  ac 5) and id 91 Arends 1973 (Venezuela, genotype total 243, ac 27).
- **Homonym control.** The single population-label hit is survey id 12: Adamson 1951, *Nigeria*,
  "Haematological and biochemical findings in Hausa males", present in both layers. Hausa is an
  ethnicity across Nigeria, Niger and Sudan, so a match taken on the population label alone would
  have reported that Nigerian 1951 survey as a duplicate of the Salih Hausa row. The match is
  refused, and this is the concrete case behind the contract's rule that a label resolves through a
  reviewed alias and that identity is never inferred.

**What this establishes for #151.** For both Salih 2010 rows the duplicate risk against the MAP/Piel
path is now checked at three levels: the 2010 assembly's own source list (Step 1), the committed
artifact the P1 path consumes, and the live layer as of 2026-10-07. No level produces a match, by
study identity or by exact counts, so the rows are additions to the region rather than re-counts of a
cohort the P1 path already holds. A match appearing in a later layer would not change this: the
artifact is keyed by data version, and a superseded version is superseded rather than current.

**What it still does not establish.** Promotion status is unchanged. Both rows stay refused for the
reasons already recorded above: verification pending, methods `not_reviewed`, and no reviewed
`literature` P0 alias for either population label. Reconciliation is about duplicate identity, and it
does not satisfy promotion. The 216 ids the live layer has gained since `map-2026-08` are recorded
here as a fact about the layer, not as a reason to refresh an immutable artifact.

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
