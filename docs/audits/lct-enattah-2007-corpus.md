# LCT rs4988235 corpus slice (Enattah 2007) — coverage report

Date: 2026-09-06. Staged under tests/fixtures/literature/lct-enattah-2007/.
Corpus: lct-rs4988235. Source paper: Enattah et al. 2007 Am J Hum Genet
81:615 (PMID 17701907, PMC1950831), Table 2 genotype counts (N, CC/CT/TT
for rs4988235 = their SNP4 C/T-13910).

## Coverage (per issue #149 recommended reporting)

- Candidates screened: 2 source papers at table level
  (Enattah 2007 used; Bersaglieri 2004 documented as frequency-only refusals)
- Records staged: 12 (one per population measurement)
- Field-evidence decisions: 228 (19 per record)
- Records promoted to P1: 0
- Refusals at the promotion gate (expected, documented reasons):
  - verification pending: 12 (automated extraction cannot verify itself)
  - reuse restricted: 12 (PMC surface carries "(c) 2007 by the American
    Society of Human Genetics. All rights reserved."; explicit restriction
    wins under the documented reuse rule)
  - methods fields (assay, sampling design, dates, cohort identity):
    not_reviewed on all 12 (2007 article full text omits Methods in
    PMC/Europe PMC HTML; published PDF required)
- Distinct populations/regions: 12 across Russia, Finland, France,
  Pakistan, Iran
- Overlap with existing corpus: pilot repo manpreetbola/
  protective-alleles-gnomad-v4 rows citing PMID 17701907 (34 matched; 24
  exact, 9 corrected upstream at commit 31eda87, 1 French row internally
  inconsistent in the source and left for adjudication)

## Validator state (frozen contracts)

- validate_literature_tables: PASS (12 evidence + 228 field rows)
- normalization_status recomputed: verified (all 12)
- reuse_status recomputed: restricted (all 12)
- verifier fields: absent (pending)

## Open questions for review

1. Reuse policy: should journal "(c) all rights reserved" boilerplate on an
   article surface be treated as a data restriction under the literature
   reuse rule (rows cannot promote), or is no_restriction_found appropriate
   for factual genotype counts restated with citation? Current staging says
   restricted (letter of the rule). cf. AFND #117 precedent.
2. P0 proposals: populations.tsv/aliases.tsv are proposals; uncertainty
   radii need registry review.
3. Whether to run publications.load on this staged corpus (expected result:
   all rows refuse until verification + reuse resolve).

## Adjudication backlog (not in this PR)

- Ob-Ugric: source paper has two sample panels (Table 1 N=20 vs Table 2
  N=62); which panel the compiled corpus intended is unclear.
- French (France): source Table 2 row internally inconsistent (N=17 but
  CC+CT+TT=16; genotype counts imply T=11/34, printed C/T frequencies imply
  T=13/34).
