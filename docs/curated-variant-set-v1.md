# Curated variant set v1 candidate

Issue [#32](https://github.com/bschilder/genomeOS/issues/32) asks which ClinVar pathogenic or
likely pathogenic variants have defensible penetrance, and adds CPIC Level A/B pharmacogenomic
and founder variants. This document records the first immutable candidate release. It implements
the data and refusal boundary needed to answer that question; it does not claim that clinical
review is complete.

## Scientific contract

**Claim.** The release is a bounded, reproducible list of entities for v1 surface development and
clinical-genetics review. Inclusion records why each entity was proposed. It does not claim that a
ClinVar classification supplies penetrance, that every allele in a CPIC gene is actionable, or
that a founder label describes present-day geography.

**Measurable output.** `data/registry/curated-v1-candidate.1/` contains a schema-valid candidate
table, all active CPIC Level A/B gene-drug pairs, a per-gene coverage report, hashes over every
output, and explicit counts of pending and unresolved rows. Rebuilding from the committed source
snapshot produces byte-identical files.

**Interface.** `genomeos.registry.curated.load` validates the table.
`select_for_frequency_surface` returns only resolved candidates whose project review is verified.
`select_for_affected_burden` additionally requires a Mendelian entity and independently verified
penetrance evidence. Both selectors currently return zero rows because this release intentionally
precedes clinical-genetics review.

**Assumptions and refusals.** CPIC and ClinVar are treated as sources for the claims they actually
make. CPIC provides gene-drug levels and allele functions; ClinVar aggregates clinical
classifications. Neither is treated as a generic penetrance database. An unresolved identity,
pending project review, or missing verified penetrance is a refusal. Current affected-count logic
does not reinterpret pharmacogenomic response as Mendelian penetrance.

## Frozen contents

The `v1-candidate.1` build contains 698 rows:

| Source path | Candidates | Meaning |
|---|---:|---|
| CPIC 1.60.0 | 689 | Named alleles with one of nine admitted CPIC clinical-functional states, plus five exact allele-status triggers |
| Manual clinical candidates | 9 | Existing parity anchors, carrier-screening targets, and selected founder variants |

The CPIC pair table retains all 128 active Level A/B pairs across 29 genes. The coverage table
does not hide unsupported targets:

- eight genes have no allele rows in the frozen CPIC API snapshot: `ABL2`, `ASL`, `ASS1`, `CPS1`,
  `HPRT1`, `NAGS`, `OTC`, and `SCN1A`;
- `CYP4F2` has 23 allele rows, but none has an admitted clinical-functional state or exact
  allele-status trigger under this release's rule;
- those nine genes and their pairs remain in the pair and coverage tables as refusals.

Normal, uncertain, unknown, and blank CPIC functional states are not candidate alleles. The
exception is an exact five-entry allowlist for allele-status recommendations:
`HLA-A*31:01`, `HLA-B*15:02`, `HLA-B*57:01`, `HLA-B*58:01`, and the `VKORC1` rs9923231 T allele.
This rule is executable in `build_cpic_candidates`, rather than implied by prose.
`cpic_level` appears only in the pair table because CPIC grades gene-drug pairs. Allele rows do
not inherit the best grade observed anywhere in their gene.

The manually authored rows are deliberately small and reviewable. They cover the existing HbS
parity target and Golden Test 3's CFTR, HEXA, SMN1, and β-thalassemia classes, plus the three
well-characterized Ashkenazi Jewish BRCA founder alleles. The set does not claim to exhaust
ClinVar P/LP variants or founder populations. Expansion requires the same evidence and review
fields, not an unconstrained ClinVar dump.

## Why SMN1 is unresolved

The screening target is an `SMN1` copy-number state, not a single sequence allele. A zero-copy
state, an intragenic pathogenic variant, and a silent `2+0` carrier have different measurement
and residual-risk semantics. The candidate row therefore has no canonical identifier and records
a refusal rather than forcing the locus into `chr-pos-ref-alt`. [GeneReviews describes both dosage
testing and the `2+0` limitation](https://www.ncbi.nlm.nih.gov/books/NBK1352/). A later contract
must admit copy-state identities before this target can be reviewed as resolved.

## Provenance and terms

The committed CPIC snapshot is release 1.60.0 data accessed on 2026-09-14. `SOURCE.json` records
the four exact API queries and SHA-256 hashes. CPIC publishes its curated content under CC0 and
asks users to record the URL, access date, and version; the snapshot includes the source license.
The latest 1.60.1 release was application-only, so 1.60.0 remains the corresponding data release.
[CPIC source repository](https://github.com/cpicpgx/cpic-data),
[CPIC 1.60.0 release](https://github.com/cpicpgx/cpic-data/releases/tag/v1.60.0).

The manual candidates link directly to their ClinVar VCV records and to NCBI GeneReviews pages
that identify potential penetrance evidence. ClinVar states that it aggregates submitter
classifications and calculates aggregate review status; the project must not turn that aggregation
into a penetrance estimate. [ClinVar classification documentation](https://www.ncbi.nlm.nih.gov/clinvar/docs/clinsig/),
[ClinVar review-status documentation](https://www.ncbi.nlm.nih.gov/clinvar/docs/review_status/).
`data/sources/curated/SOURCE.json` records the source checks. ClinVar asks for attribution when its
data are copied or distributed. GeneReviews has noncommercial reproduction terms, so the release
stores only evidence links and identifiers; it does not copy chapter prose or tables.

## Clinical-genetics review required

An expert reviewer should inspect every proposed manual row and the executable CPIC admission
rule. In particular, review should determine:

1. whether each disease and inheritance pairing is specific enough for the burden model;
2. whether the linked evidence supports variant-specific penetrance, genotype-level penetrance,
   or only broader gene-condition risk, including age, sex, treatment, and modifier strata;
3. whether each founder statement is accurate and should remain metadata rather than a geographic
   prior;
4. whether CPIC clinical-functional states and the five allele-status triggers are the right v1
   boundary;
5. whether each observation type matches data that can actually be ingested without converting
   absent alleles or copy states into biallelic zeros;
6. whether SMN1 should remain refused until a copy-number contract exists.

Every row records the identity and method that proposed it. The reviewer records an attributable
identity and date only after checking the linked sources, and the schema requires the reviewer to
differ from the proposer.
Rows rejected during review stay in the immutable candidate release; an accepted set is published
under a new version rather than mutating this one.

## Rebuild

From the repository root:

```bash
PYTHONPATH=. python scripts/build_curated_variant_set.py \
  --out /tmp/curated-v1-candidate.1
```

The command refuses an existing output directory. This preserves the repository's immutable
artifact rule and makes accidental overwrites visible.
