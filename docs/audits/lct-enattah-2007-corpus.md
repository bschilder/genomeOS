# LCT rs4988235 corpus slice (Enattah 2007) — coverage report

Date: 2026-09-06 (v2 after maintainer review; review 5125800984).
Staged under tests/fixtures/literature/lct-enattah-2007/.
Corpus: lct-rs4988235. Source paper: Enattah et al. 2007 Am J Hum Genet
81:615 (PMID 17701907, PMC1950831), Table 3 genotype counts (N, CC/CT/TT
for rs4988235 = their SNP4 C/T-13910).

## Coverage (per issue #149 recommended reporting)

- Candidates screened: 2 source papers at table level
  (Enattah 2007 used; Bersaglieri 2004 documented as frequency-only refusals)
- Records staged: 12 (one per population measurement)
- Field-evidence decisions: 228 (19 per record)
- Records promoted to P1: 0
- Refusals at the promotion gate (expected, documented reasons):
  - verification pending: 12 (automated extraction cannot verify itself;
    independent reviewer required)
  - methods fields (assay, sampling design, dates, cohort identity):
    not_reviewed on all 12 (2007 article full text omits Methods in
    PMC/Europe PMC HTML; published PDF required)
- Distinct populations/regions: 12 across Russia, Finland, France,
  Pakistan, Iran
- Overlap with existing corpus: pilot repo manpreetbola/
  protective-alleles-gnomad-v4 rows citing PMID 17701907 (34 matched; 24
  exact, 9 corrected upstream at commit 31eda87, 1 French row internally
  inconsistent in the source and left for adjudication)

## Corrections applied after maintainer review (2026-09-06)

1. Locators corrected: the CC/CT/TT genotype counts are in Table 3 of
   Enattah et al. 2007, not Table 2. record_locator, field-evidence
   source_locator, notes, and this audit updated. Because source_record_id
   incorporates record_locator, all 12 record IDs and their 228 child
   field-evidence rows were regenerated with the project's
   make_source_record_id helper. The counts themselves were unchanged
   (maintainer spot-checked them against Table 3 and they agree).
2. Citation text corrected from PMID metadata: second author is Aimee
   Trudeau (Enattah NS, Trudeau A, et al.), not "Trivedi M".
3. Extraction origin corrected to automated_proposal: records are
   agent-transcribed, no deterministic structured importer exists, and no
   human extractor has checked them. verification_status stays pending.
4. Reuse policy resolved per maintainer guidance: the PMC surface carries
   an ASHG "(c) all rights reserved" boilerplate notice, which does not
   specifically restrict the proposed factual-data reuse. reuse_status is
   now no_restriction_found on all rows with the terms check recorded on
   the PMC surface (https://www.ncbi.nlm.nih.gov/pmc/articles/PMC1950831/).
5. Search manifest regenerated with the project's deterministic
   make_search_id helper (database, query, executed_at), and the corpus
   test now validates searches.tsv in addition to the evidence ledgers.

## Provenance backfill and discovery correction (2026-09-10, issue #237)

The slice was merged without a committed builder and without the raw ESearch
payloads, so nothing in the repository could reproduce the 37-row manifest or
re-derive the 12 record identifiers. #237 asked for that to be fixed.

Added: `scripts/build_lct_enattah_fixture.py` (every path through `argparse`,
replay by default, `--extracted-at` required, field rows driven off
`TRACKED_FIELDS`), `payloads/Q1.json`–`Q3.json` (unmodified ESearch response
bytes), and `PROVENANCE.json`. The builder reproduces `evidence.tsv` and
`field_evidence.tsv` byte-for-byte, and all 12 `source_record_id` values
re-derive through the project's `make_source_record_id` helper.

**The merged manifest was truncated, and nothing recorded it.** Re-executing the
three queries against PubMed (2026-09-12, reproducing the 2026-09-10 re-capture
byte-for-byte):

| query | merged candidates | PubMed `count` |
|---|---|---|
| Q1 `Enattah[Author] AND 13910[All Fields]` | 11 | 11 |
| Q2 `Bersaglieri[Author] AND lactase[All Fields]` | 1 | 1 |
| Q3 `rs4988235[All Fields] AND (population[Title/Abstract] OR frequency[Title/Abstract])` | 25 | **58** |

Q1 and Q2 reproduce exactly. Q3 does not, and the cause is not a changed index:
all 25 merged candidates are still present in the 58, and they are exactly the
set PubMed returns when the same query is run with `retmax=25`. The merged
capture was truncated at 25 and the manifest never recorded the cap.

This is the failure mode `docs/literature-evidence-curation.md` names when it
explains why the manifest reader refuses a `count` that disagrees with the
returned `idlist`: "a truncated or paginated response otherwise becomes a short,
confident-looking manifest." `scripts/fetch_pubmed_manifest.py` fetches with
`retmax=100000` and rejects that disagreement, so the merged file could not have
come from the documented tool.

Corrected state:

- `searches.pending.tsv` — 70 rows, all pending, `lct-rs4988235@2026-09-12.1`,
  `build_manifest()` applied to the committed payloads.
- `searches.tsv` — **not rewritten.** It remains the merged 37-row manifest at
  `lct-rs4988235@2026-09-06.1`, with its two `included` and 35 `pending`
  decisions exactly as merged.

Re-deriving a manifest from a re-capture changes `search_id` by construction,
because the id hashes `(database, query, executed_at)`. Superseding a published
manifest version is therefore a data revision rather than a backfill, and it is
tracked separately (issue #272). While that is open the two files deliberately
share no identifier: the published revision describes the truncated capture, and
`searches.pending.tsv` is the corrected snapshot committed beside it. No
candidate was dropped (0 removed, 33 added).

Payload hashes as committed:

| payload | bytes | sha256 |
|---|---|---|
| `Q1.json` | 464 | `7b7b22d6edefdf69b40c51a3baaf53ce347fd3e5f5f4030947a22fd3b831741b` |
| `Q2.json` | 1033 | `f474ffb457fdcad2bfe82aa5189a503e8cef76f7c628284f1b4c0ed0f3d33f3b` |
| `Q3.json` | 1035 | `fe440da7c93ebad7442cfa6be31570762cbe701c78d6597757e765efa4297edf` |

Consequence for the slice: 33 real matches for the third query were never
recorded, so the discovery half of this corpus was less complete than its
coverage report stated. They are now visible as unscreened, which is the honest
state. Screening them, and republishing the manifest over the corrected
snapshot, are not part of this backfill.

## Validator state (frozen contracts)

- validate_literature_tables: PASS (12 evidence + 228 field rows)
- validate_search_manifest: PASS (searches.pending.tsv 70 candidate rows, 3 unique
  searches; the merged searches.tsv 37 candidate rows, 3 unique searches, left as
  merged — see the provenance backfill above)
- normalization_status recomputed: verified (all 12)
- reuse_status recomputed: no_restriction_found (all 12)
- extraction_method: automated_proposal (all 12)
- verifier fields: absent (pending)

## Population registry proposals (UNRESOLVED — not in the P0 fixture)

The following P0 population entries were removed from the schema-valid
fixture because their uncertainty_radius_km values are proposals awaiting
registry review, and the frozen contract gives radius no provisional
default. They remain audit material only. Coordinates come from the pilot
coordinate table (protective-alleles-gnomad-v4@v2, Liebert 2017 coords);
location_type ancestral requires evidence before any registry use.

| population_label (verbatim) | lat | lon | proposed radius (km) | proposed population_id |
|---|---|---|---|---|
| Komi | 63.863054 | 54.831269 | 200 | literature-komi |
| Udmurts | 56.833333 | 53.183316 | 200 | literature-udmurts |
| Mokshas | 54.236944 | 44.068397 | 200 | literature-mokshas |
| Erzas | 54.212315 | 43.584157 | 200 | literature-erzas |
| Saami | 68.258009 | 26.193792 | 450 | literature-saami |
| Finns, eastern | 65.0 | 29.0 | 250 | literature-finns-eastern |
| Finns, western | 64.0 | 24.0 | 250 | literature-finns-western |
| Basques | 43.395495 | -1.454917 | 120 | literature-basques |
| Pathan | 32.667476 | 69.859741 | 200 | literature-pathan |
| Sindi | 24.893501 | 67.028062 | 200 | literature-sindi |
| Brahui | 30.209572 | 67.019672 | 200 | literature-brahui |
| Qashqai | 29.616538 | 52.533901 | 120 | literature-qashqai |

Proposed alias table (same status): each label above maps to its proposed
population_id through the literature source. None of these entries is
usable for promotion until radii and location_type are reviewed in the
registry (cf. issue #21 uncertainty radii).

## Open questions for review

1. Whether to run publications.load on this staged corpus now (expected:
   all rows refuse until verification resolves and P0 geography is
   reviewed).
2. P0 registry review of the population proposals above (radii,
   location_type evidence, biocultural notice).

## Adjudication backlog (not in this PR)

- Ob-Ugric: the source paper reports different sample sizes for this group
  across its tables (one panel N=20, genotype table N=62); which panel the
  compiled corpus intended is unclear.
- French (France): the genotype table row is internally inconsistent
  (N=17 but CC+CT+TT=16; genotype counts imply T=11/34, printed C/T
  frequencies imply T=13/34).
