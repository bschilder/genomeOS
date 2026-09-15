# Variant-normalization independent verification — 2026-09-11

Verifier: `agent:anthropic:claude-sonnet-5`, acting under the policy on
[issue #242](https://github.com/bschilder/genomeOS/issues/242): an agent may verify a row
provided the verdict rests on links a human can independently follow and check. This document
is that trail — every URL fetched, the raw value it returned, and the verdict — for the four
**mapping** rows in `data/registry/variant_normalization.tsv` written by
`agent:anthropic:claude-opus-5` (see `docs/audits/variant-normalization-2026-09.md` for that
agent's own resolution notes). The fifth row, `chr11-5227002-T-A` (HbS), is an **identity** row
and is exempt from verification by design (`genomeos/registry/variants.py`); its
`verification_status` was not touched.

All fetches below were made live on 2026-09-11 against public NCBI/Ensembl services. Every URL is
directly re-fetchable by a human with no authentication.

## Schema note

`VARIANT_NORMALIZATION_SCHEMA` in `genomeos/registry/variants.py` has no `verified_by` column —
only `verification_status` (`verified`/`pending`) and `reviewed_by`. Per instruction, no such
column was invented. The verifier identity (`agent:anthropic:claude-sonnet-5`) and a pointer to
this document were appended to each verified row's `notes` field instead. `reviewed_by` was left
untouched, since it records who *resolved* the row (`agent:anthropic:claude-opus-5`), which is a
different fact than who verified it. **A follow-up should add a proper `verified_by` column** so
this identity does not have to live inside free-text notes.

---

## `cyt:il-10-1082-g` (rs1800896) — VERIFIED

**Coordinate / build.**

- `curl https://api.ncbi.nlm.nih.gov/variation/v0/refsnp/1800896` →
  `primary_snapshot_data.placements_with_allele` (is_ptlp, primary assembly): SPDI
  `NC_000001.11:206773551:T:T` / `:T:A` / `:T:C` / `:T:G`; `last_update_build_id: "157"`.
  SPDI position is 0-based → 1-based position **206773552**. Ref **T**, alts A/C/G.
  → Registry `chr1-206773552-T-C`: **matches** (T ref, C one of the alts).
- `curl -H "Content-Type: application/json" "https://rest.ensembl.org/variant_recoder/human/rs1800896?content-type=application/json;fields=spdi"`
  → `{"C":{"spdi":["NC_000001.11:206773551:T:C","LRG_1230:3942:A:G"],"input":"rs1800896"}}`.
  Matches dbSNP exactly on the primary assembly. **Two independent services agree.**
- `curl https://rest.ensembl.org/info/data/?content-type=application/json` → `{"releases":[116]}`.
  Ensembl release 116 confirmed current. dbSNP build 157 confirmed current (both queried rsIDs
  return `last_update_build_id: "157"` live).
- RefSeqGene cross-check: Ensembl's `LRG_1230:3942:A:G` is 0-based → 1-based **3943**. `curl
  "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=nuccore&id=NG_012088.1&retmode=json"`
  → title "Homo sapiens interleukin 10 (IL10), RefSeqGene (**LRG_1230**) on chromosome 1" —
  confirms `LRG_1230 = NG_012088.1`, so the row's `NG_012088.1:g.3943A>G` claim is **exact**.

**Gene strand.** `curl https://rest.ensembl.org/lookup/id/ENSG00000136634?content-type=application/json`
→ `"strand": -1`. Matches the row's "IL10 (ENSG00000136634) on strand -1" claim exactly.

**Round-trip.** printed `A/G`, strand `minus`. `complement("A/G") = "T/C"`; `{T,C}` = ref/alt set
of `chr1-206773552-T-C`. Non-palindromic (`{A,G}` is not in `{ {A,T}, {C,G} }`), so this is
decisive, per `genomeos/registry/variants.py::is_palindromic`/`validate_rows`.

**Naming citation.** `pmid:29802545`:
`curl "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id=29802545&rettype=abstract&retmode=text"`
→ Holster et al., *World J Pediatr* 2018;14(6):594-600, "Polymorphisms in the promoter region of
IL10 gene are associated with virus etiology of infant bronchiolitis." Abstract text (verbatim):
*"IL10 gene rs1800896 (- 1082A/G) polymorphism was associated with viral etiology of infant
bronchiolitis."* — **prints the legacy offset and the rsID together, exactly as the registry
quotes it.** (Note: the same abstract later also writes the same SNP as "rs1800896 (- 1082G/A)"
— the source itself is internally inconsistent about allele order; this does not affect the
citation match, which quotes the first, verbatim occurrence.)

**Naming sanity check (VEP).**
`curl -H "Content-Type: application/json" "https://rest.ensembl.org/vep/human/id/rs1800896?content-type=application/json"`
→ transcript `ENST00000423557` (`ENSG00000136634`, strand -1), `distance: 1058`. Row claims
"1058 bp upstream ... 24 bp short of the legacy -1082" (1082-1058=24): **exact match**.

**Verdict: VERIFIED.** Coordinate, build, strand, citation, and VEP corroboration all
independently reproduced exactly.

---

## `cyt:il-10-819-t` (rs1800871) — VERIFIED

**Coordinate / build.**

- `curl https://api.ncbi.nlm.nih.gov/variation/v0/refsnp/1800871` → SPDI `NC_000001.11:206773288:A:A`
  / `:A:C` / `:A:G` / `:A:T`; `last_update_build_id: "157"`. 0-based 206773288 → 1-based
  **206773289**. Ref **A**, alts C/G/T. → Registry `chr1-206773289-A-G`: **matches**.
- `curl -H "Content-Type: application/json" "https://rest.ensembl.org/variant_recoder/human/rs1800871?content-type=application/json;fields=spdi"`
  → `{"G":{"spdi":["NC_000001.11:206773288:A:G","LRG_1230:4205:T:C"],"input":"rs1800871"}}`.
  **Matches dbSNP exactly.**
- `LRG_1230:4205:T:C` is 0-based → 1-based **4206**; `LRG_1230 = NG_012088.1` (confirmed above),
  so the row's `NG_012088.1:g.4206T>C` claim is **exact**.

**Gene strand.** Same Ensembl gene lookup as above: IL10 (`ENSG00000136634`) strand **-1**.
Matches.

**Round-trip.** printed `C/T`, strand `minus`. `complement("C/T") = "G/A"`; `{G,A}` = ref/alt set
of `chr1-206773289-A-G`. Non-palindromic, decisive.

**Naming citation.** Same PMID, `pmid:29802545` (fetched above). Abstract (verbatim):
*"...IL10 single nucleotide polymorphisms (SNPs) at rs1800890 (- 3575A/T), **rs1800871
(- 819C/T)** or rs1800872 (- 592C/A)..."* — **prints the legacy offset and rsID together**,
exactly as quoted in the registry row.

**Naming sanity check (VEP).**
`curl -H "Content-Type: application/json" "https://rest.ensembl.org/vep/human/id/rs1800871?content-type=application/json"`
→ transcript `ENST00000423557`, `distance: 795`. Row claims "795 bp upstream ... 24 bp short of
the legacy -819" (819-795=24): **exact match**, the same 24 bp shift as the -1082 locus.
Cross-check: 206773552 (−1082 coordinate) − 206773289 (−819 coordinate) = **263** =
1082 − 819 exactly, and both loci's coordinate minus their legacy offset independently give the
same implied TSS, **chr1:206772470** (206773552−1082 = 206773289−819 = 206772470): **exact
match** to the row's own claim.

**Verdict: VERIFIED.** Coordinate, build, strand, citation, and VEP corroboration all
independently reproduced exactly.

---

## `cyt:tnfalpha-308-a` (rs1800629) — VERIFIED

**Coordinate / build.**

- `curl https://api.ncbi.nlm.nih.gov/variation/v0/refsnp/1800629` → primary-assembly SPDI
  `NC_000006.12:31575253:G:G` / `:G:A`; `last_update_build_id: "157"`. 0-based 31575253 →
  1-based **31575254**. Ref **G**, alt **A**. → Registry `chr6-31575254-G-A`: **matches exactly**
  (biallelic, no ambiguity).
- `curl -H "Content-Type: application/json" "https://rest.ensembl.org/variant_recoder/human/rs1800629?content-type=application/json;fields=spdi"`
  → `{"A":{"spdi":["NC_000006.12:31575253:G:A", <6 NT_* alt-contig SPDIs>]}, "G":{"spdi":["NT_113891.3:3052540:A:G"]}}`.
  Primary-assembly entry **matches dbSNP exactly**.
- Alt-contig hazard (row's note): full placement list from the dbSNP JSON shows six non-primary
  contigs — `NT_167245.2` (`HSCHR6_MHC_DBB_CTG1`), `NT_167246.2` (`HSCHR6_MHC_MANN_CTG1`),
  `NT_167247.2` (`HSCHR6_MHC_MCF_CTG1`), `NT_167248.2` (`HSCHR6_MHC_QBL_CTG1`), `NT_167249.2`
  (`HSCHR6_MHC_SSTO_CTG1`), and `NT_113891.3`. Titles fetched via
  `curl "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=nuccore&id=<acc>&retmode=json"`
  for each; `NT_113891.3` → "...alternate locus group ALT_REF_LOCI_2 **HSCHR6_MHC_COX_CTG1**".
  **Six MHC alt contigs confirmed exactly**, and on `NT_113891.3` (`HSCHR6_MHC_COX_CTG1`) the
  ref/alt pair is `A`/`G` — reference **A**, not G — **exactly** as the row's note states.

**Gene strand.** `curl https://rest.ensembl.org/lookup/id/ENSG00000232810?content-type=application/json`
→ `"strand": 1`. Matches "TNF (ENSG00000232810) on strand +1" exactly.

**Round-trip.** printed `G/A`, strand `plus`. `{G,A}` = ref/alt set directly (plus strand, no
complement needed). Non-palindromic, decisive.

**Naming citation.** `pmid:22749237`:
`curl "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&id=22749237&retmode=json"`
→ title (verbatim): *"Tumor necrosis factor -308 polymorphism (rs1800629) is associated with
mortality and ventilator duration in 1057 Caucasian patients."* *Cytokine* 2012;60(1):249-56.
**Exact match** to the registry's citation text; legacy offset and rsID appear together in the
title itself.

**Naming sanity check (VEP).**
`curl -H "Content-Type: application/json" "https://rest.ensembl.org/vep/human/id/rs1800629?content-type=application/json"`
→ transcript `ENST00000449264` (`ENSG00000232810`), `distance: 311`. Row claims "311 bp upstream
... 3 bp past the legacy -308" (311-308=3): **exact match**.

**Verdict: VERIFIED.** Coordinate, build, strand, alt-contig hazard, and citation all
independently reproduced exactly.

---

## `cyt:il-6-174-c` (rs1800795) — NOT VERIFIED (left `pending`)

This is the palindromic row (`G/C`), where the round-trip has no power and the strand rests
entirely on `strand_evidence`. Per the task, this got the most scrutiny.

**Coordinate / build — confirmed.**

- `curl https://api.ncbi.nlm.nih.gov/variation/v0/refsnp/1800795` → primary-assembly SPDI
  `NC_000007.14:22727025:C:C` / `:C:G` / `:C:T`; `last_update_build_id: "157"`. 0-based 22727025
  → 1-based **22727026**. Ref **C**, alts G/T. → Registry `chr7-22727026-C-G`: **matches**
  (multi-allelic C>G / C>T, exactly as the row's notes state).
- `curl -H "Content-Type: application/json" "https://rest.ensembl.org/variant_recoder/human/rs1800795?content-type=application/json;fields=spdi"`
  → `{"G":{"spdi":["NC_000007.14:22727025:C:G"]},"T":{"spdi":["NC_000007.14:22727025:C:T"]}}`.
  **Matches dbSNP exactly.**
- `curl https://rest.ensembl.org/info/data/?content-type=application/json` → release 116, current.

**Naming citations — confirmed.**

- `pmid:25526459`: `curl ".../efetch.fcgi?db=pubmed&id=25526459&rettype=abstract&retmode=text"` →
  Máchal et al., *Medicine (Baltimore)* 2014;93(28):e278. Verbatim: *"SNP in the IL-6 gene
  rs1800795 (-174 G/C) has been found to be a significant predictor of survival."* **Exact
  match.** The same abstract also states: *"This SNP was in a linkage disequilibrium with
  rs1800797 (-597 G/A) in the same gene (D'=1.0)"* — an independent, better citation than the
  row uses for the rs1800797/−597 linkage it needs for strand (see below).
- `pmid:37904417`: `curl ".../efetch.fcgi?db=pubmed&id=37904417&rettype=abstract&retmode=text"` →
  Xue et al., *Medicine (Baltimore)* 2023;102(43):e35697. Verbatim: *"...the IL-6 gene -174G/C
  locus (rs1800795), the risk of disease was 2.636..."* **Exact match.**

**Strand evidence, claim by claim.**

1. *"pmid:10747905 (Terry 2000, J Biol Chem 275:18138-44) names -597G-->A, -572G-->C and
   -174G-->C as one IL6 promoter haplotype scheme."*
   `curl ".../efetch.fcgi?db=pubmed&id=10747905&rettype=abstract&retmode=text"` → Terry, Loukaci,
   Green, *J Biol Chem* 2000;275(24):18138-44, "Cooperative influence of genetic polymorphisms on
   interleukin 6 transcriptional regulation." Verbatim: *"...four polymorphisms in the IL6
   promoter (-597G-->A, -572G-->C, -373A(n)T(n), -174G-->C)..."* **Confirmed** (the row omits the
   third, -373, polymorphism from its quote, which is immaterial).
2. *"LitVar2 maps -597G>A to rs1800797... plus-strand reference allele is A."*
   `curl https://api.ncbi.nlm.nih.gov/variation/v0/refsnp/1800797` → SPDI
   `NC_000007.14:22726601:A:A/:A:C/:A:G/:A:T`; ref **A**, alts C/G/T. `curl -H "Content-Type:
   application/json" "https://rest.ensembl.org/variant_recoder/human/rs1800797?content-type=application/json;fields=spdi"`
   → `{"C":{...":C"]},"G":{"spdi":["NC_000007.14:22726601:A:G"]},"T":{...":T"]}}`. **Both
   independently confirm plus-strand reference A — exact.** Independent corroboration found via
   PMID 25526459 (above): "rs1800797 (-597 G/A)" — literature "wild-type" G is not the GRCh38
   reference (A), the identical pattern the row calls out for -174 itself.
3. VEP corroboration: `curl -H "Content-Type: application/json"
   "https://rest.ensembl.org/vep/human/id/rs1800795?content-type=application/json"` → gene
   `ENSG00000136244` strand **1**, transcript `ENST00000258743` distance **174**. Same call for
   `rs1800797` → transcript `ENST00000258743` distance **598**. **Both exact matches** to the
   row's claims ("IL6 on strand +1", "distance 174", "the neighbouring -597 locus sits at VEP
   distance 598"). Independent math check: predicted -597 position from the -174 anchor's
   implied TSS (22727026 + 174 = 22727200 TSS; 22727200 − 597 = 22726603) lands 1 bp from
   rs1800797's actual position (22726602) — consistent with the row's own "off by one" caveat.
4. **Frequency claim — does NOT reproduce.** Row states: *"the allele the internal id calls
   minor (the -c suffix)... would map to plus-strand G, whose global frequency dbSNP build 157
   reports as 0.750 in TOPMED and 0.859 in 1000Genomes."*
   - `curl https://api.ncbi.nlm.nih.gov/variation/v0/refsnp/1800797`, `allele_annotations[].frequency`
     for the `G` (inserted_sequence) observation: **TOPMED** `allele_count=200141,
     total_count=264690` → **G frequency = 200141/264690 = 0.7561** (not 0.750; row is short by
     ~0.006, a 0.8% relative difference). **1000Genomes** `allele_count=4316, total_count=5008` →
     **0.8618** (1000Genomes_30X: `5507/6404 = 0.8599`); row states 0.859, which sits between
     these two 1000Genomes releases but does not exactly match either to 3 decimals.
   - Cross-checked via `curl
     "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=snp&id=1800797&retmode=json"`
     (`global_mafs`), which independently reports the **A** allele: `TOPMED
     "A=0.243866/64549"` → G = 1−0.243866 = **0.756134**, and `1000Genomes "A=0.138179/692"` →
     G = **0.861821**. Same numbers as the RefSNP API, confirming this is not a units/rounding
     artifact of one endpoint.
   - Also checked gnomAD v4 directly (`POST https://gnomad.broadinstitute.org/api`, GraphQL
     `variant(variantId: "7-22726602-A-G", dataset: gnomad_r4)`) as a further cross-check: genome
     AF **0.7230**, exome AF **0.5908** — neither matches 0.750 either, for what it's worth.
   - The row's qualitative conclusion is **not** undermined by this — the true TOPMED/1000Genomes
     figures (0.756, 0.862) are, if anything, *further* from 0.5 and from this repo's own 0.304
     median than the row's stated numbers, so a minus-strand reading is still irreconcilable with
     the data. But the specific numbers printed in `strand_evidence` — "0.750 in TOPMED and 0.859
     in 1000Genomes" — are not what the cited live resource (dbSNP build 157, the same resource
     named in `reference_resource`) returns today. A human following the same API call gets 0.756
     and 0.862, not 0.750 and 0.859.

**Own-observations claim — confirmed exactly.**
`website/public/data/atlas/cyt-il-6-174-c.observations.json` → 83 observation records, each with
`ac`/`an`. Computed `ac/an` per record: **median = 0.30434782608695654 ≈ 0.304**, **count with
af > 0.6 = 1 of 83**. **Both numbers match the row's claim exactly.**

**Verdict: NOT VERIFIED — left `pending`.** Everything else in this row (coordinate, build,
both naming citations, the Terry 2000 haplotype-scheme citation, the rs1800797 reference-allele
claim, the VEP distance/strand corroboration, and the repo's own 0.304/1-of-83 statistic)
reproduces exactly against live, independently-checkable sources — in several places *more*
precisely than the row itself asserts (e.g., PMID 25526459 directly states the rs1800797/−597
linkage the row only attributes informally to "LitVar2"). The one claim that does **not**
reproduce is the pair of external population-frequency figures ("0.750 in TOPMED and 0.859 in
1000Genomes"): the live dbSNP RefSNP API and esummary both return 0.7561 (TOPMED) and 0.8618–0.8599
(1000Genomes) for the same G allele of rs1800797, not 0.750/0.859. This does not change the
strand conclusion, but the printed figures are not what a human re-running the same query gets
today, so per the "a value does not match what the source says" standard this row is not marked
verified. A fix is simple — correct the two figures in `strand_evidence` (or requalify them, if
they were meant to name a specific ancestry subset rather than the aggregate) — and this row
should verify cleanly on a second pass.

---

## Summary

| variant_id | rsID | Verdict | Reason |
|---|---|---|---|
| `cyt:il-6-174-c` | rs1800795 | **pending** (not verified) | External TOPMED/1000Genomes frequency figures in `strand_evidence` (0.750, 0.859) do not match live dbSNP data (0.756, 0.862); everything else confirmed exactly |
| `cyt:il-10-1082-g` | rs1800896 | **verified** | Coordinate, build, strand, citation, VEP all confirmed exactly |
| `cyt:il-10-819-t` | rs1800871 | **verified** | Coordinate, build, strand, citation, VEP all confirmed exactly |
| `cyt:tnfalpha-308-a` | rs1800629 | **verified** | Coordinate, build, strand, alt-contig hazard, citation all confirmed exactly |
| `chr11-5227002-T-A` | rs334 | exempt (identity row) | not touched, per design |

3 of 4 mapping rows verified; 1 left `pending` with the specific numeric discrepancy documented
above.
