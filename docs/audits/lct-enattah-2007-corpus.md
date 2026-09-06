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

## Validator state (frozen contracts)

- validate_literature_tables: PASS (12 evidence + 228 field rows)
- validate_search_manifest: PASS (37 candidate rows, 3 unique searches)
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
