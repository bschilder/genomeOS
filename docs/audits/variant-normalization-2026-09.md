# Variant-normalization audit — first cytokine batch, 2026-09

Design: [`2026-09-10-variant-normalization-registry-design.md`](../superpowers/specs/2026-09-10-variant-normalization-registry-design.md)
(§5 contract, §6 resolution pipeline). Registry: `data/registry/variant_normalization.tsv`.

**Who did the work.** Every row in this batch was resolved by an agent
(`agent:anthropic:claude-opus-5`) on 2026-09-11 UTC. Every value below was retrieved from a live
service in that session; nothing was recalled. All four rows are `verification_status: pending`
and stay that way until [#242](https://github.com/bschilder/genomeOS/issues/242) decides who may
verify an agent-resolved row. **Until they are verified the four loci are not eligible for a
coordinate-keyed external resource** (spec §9).

## Counts

The AFND cytokine corpus holds **60 distinct loci**, of which the Atlas publishes **4** (spec §2).
This batch is those 4, deliberately, so the refusal rate is measured before the rest is scheduled.

| State | Count | Which |
|---|---:|---|
| resolved (pending verification) | 4 | `cyt:il-6-174-c`, `cyt:il-10-1082-g`, `cyt:il-10-819-t`, `cyt:tnfalpha-308-a` |
| refused (`unresolved` row written) | 0 | — |
| not attempted (no row at all) | 56 | the unpublished remainder of the 60-locus corpus |
| **total cytokine loci** | **60** | |

Outside the cytokine corpus the registry also holds 1 self-identity row, `chr11-5227002-T-A`
(HbS), which is a coordinate already and required no external resolution.

The observed refusal rate for the published batch is **0/4**. That number is not a claim about the
remaining 56: this batch is the four most-studied promoter SNPs in the corpus, the loci with the
largest literature and therefore the easiest naming trail. The refusal rate on the tail should be
expected to be much higher, and the 0/4 here is close to worthless as an estimate of it.

`data/raw/afnd_frequencies.tsv` is not tracked in the repository, so the 60-locus denominator is
taken from spec §2 rather than recounted here. Anyone rebuilding the raw AFND pull should confirm
it before scheduling the follow-on.

## Method actually followed

Per locus, in order, exactly as spec §6 requires:

1. **Propose** — LitVar2 autocomplete (`https://www.ncbi.nlm.nih.gov/research/litvar2-api/variant/autocomplete/?query=…`),
   queried both by gene symbol and by the legacy name. LitVar2 proposes; it never decides.
2. **Resolve twice, independently** — Ensembl release 116 Variant Recoder
   (`https://rest.ensembl.org/variant_recoder/human/<rsid>`) and NCBI dbSNP build 157 RefSNP API
   (`https://api.ncbi.nlm.nih.gov/variation/v0/refsnp/<n>`, the same endpoint
   `scripts/fetch_external_variant_info.py` already uses). LitVar2 was **not** counted as the
   second resource: it is NCBI, so agreeing with dbSNP is not corroboration.
3. **Naming citation** — LitVar2's publication trail for the candidate rsID, then the abstracts of
   the first 200 PMIDs in that trail fetched through E-utilities `efetch` and searched for the
   literal legacy offset. A citation was only accepted if **the abstract prints the legacy name and
   the rsID together**, so the row does not rest on LitVar2's own text-mining decision.
4. **Palindromy** — checked per row. One of the four (`G/C`) is palindromic and is dealt with
   separately below.

Supporting placement evidence, used for the strand argument and for the naming sanity checks, came
from Ensembl 116 `lookup/symbol`, `lookup/id?expand=1` and VEP
(`https://rest.ensembl.org/vep/human/id/<rsid>`).

## Per locus

### `cyt:il-6-174-c` — IL-6 −174, printed `G/C` — **resolved, strand evidence required**

- **Candidate.** LitVar2 autocomplete for `IL6` returned `rs1800795`, named `c.-174G>C`, gene
  `IL6`/`IL6-AS1`, 2,896 PMIDs — the top hit by a wide margin. Querying the legacy name directly
  (`IL6 -174`) returned the same rsID plus `rs1800797` (`c.-597G>A`, a different offset) and one
  unassigned `c.-174G>C` entry with 3 PMIDs. No second rsID competes for the name.
- **Resolution 1 — Ensembl release 116 Variant Recoder:** `NC_000007.14:22727025:C:G`
  (`NC_000007.14:g.22727026C>G`), and a second alternate `:C:T`.
- **Resolution 2 — NCBI dbSNP build 157 RefSNP API:** `NC_000007.14:22727025:C:G` and
  `NC_000007.14:22727025:C:T` on GRCh38.p14. **The two agree exactly.**
- **Allele chosen.** `C>G`, the alternate the printed `G/C` pair selects. `C>T` is the same rsID's
  other alternate and is not this observation.
- **Normalized identity.** `chr7-22727026-C-G`.
- **Naming citation.** `pmid:25526459` (*Medicine (Baltimore)* 2014;93(28):e278) — "SNP in the IL-6
  gene rs1800795 (-174 G/C)". Corroborated by `pmid:37904417` (*Medicine* 2023;102(43):e35697) —
  "the IL-6 gene -174G/C locus (rs1800795)". Both are in LitVar2's trail for rs1800795, and both
  print the legacy name and the rsID in the same sentence.
- **Strand evidence (required — `G/C` is palindromic).** The round-trip has no discriminating power
  here at all: complementing `G/C` returns `G/C`. Strand was established from a **co-named,
  non-palindromic locus in the same numbering scheme**:
  - `pmid:10747905` (Terry, Loukaci & Green, *J Biol Chem* 2000;275(24):18138-44) names
    "-597G-->A, -572G-->C, -373A(n)T(n), -174G-->C" as one IL6-promoter haplotype scheme, so
    −597 and −174 are printed under a single convention.
  - LitVar2 maps the −597 name to `rs1800797`. Ensembl 116 Variant Recoder and dbSNP 157 both
    place rs1800797 at `NC_000007.14:22726601:A:G` — plus-strand reference **A**.
  - The literature's −597 pair `G/A` is **not** palindromic. Reading that scheme on the minus
    strand would print `C/T` there, a pair containing neither the reference allele nor the common
    alternate. Only the plus-strand reading is consistent. The scheme therefore prints plus-strand
    letters, and so does its −174 entry.
  - Independently: Ensembl 116 annotates IL6 (`ENSG00000136244`) on **strand +1**, and VEP reports
    rs1800795 as an `upstream_gene_variant` at **distance 174** from the canonical transcript
    `ENST00000258743` — the legacy offset measured along the plus strand.
- **What this evidence does not establish.** It does not verify the letters against a published
  promoter sequence; no full text was retrieved. The residual assumption is the ordinary one — that
  a promoter offset and its allele letters are quoted on the same (sense) strand. A human verifier
  should check that assumption against the Terry 2000 sequence figure before this row is promoted.
- **Two honest wrinkles, recorded rather than smoothed over:**
  - GRCh38 carries **C** at chr7:22727026, so the literature's leading "G" is *not* the reference
    allele. The identical pattern holds at −597 (literature "G>A", reference A), which is what makes
    the strand argument self-consistent rather than alarming, but it is worth a reviewer's eye.
  - The legacy numbering is not internally consistent to the base: VEP distance is 174 for −174 but
    **598** for −597. The offset arithmetic was therefore used as corroboration, never as proof.
  - `pmid:22839439` writes the same locus as "G(-174)A of IL6 gene (rs1800795)" — an allele pair
    that contradicts every other source. It was not used, and it is a reminder that a single
    abstract is not sufficient.

### `cyt:il-10-1082-g` — IL-10 −1082, printed `A/G` — **resolved**

- **Candidate.** LitVar2 autocomplete for `IL10` returned `rs1800896`, named `c.-1082G>A`, 2,047
  PMIDs. Querying `IL10 -1082` returned only rs1800896 plus one unassigned entry (2 PMIDs). No
  competing rsID.
- **Resolution 1 — Ensembl 116 Variant Recoder:** `NC_000001.11:206773551:T:C`
  (`NC_000001.11:g.206773552T>C`); also `LRG_1230:3942:A:G` in gene orientation.
- **Resolution 2 — dbSNP build 157:** `NC_000001.11:206773551:T:C` on GRCh38.p14, alongside `T>A`
  and `T>G`. **The two agree exactly.**
- **Normalized identity.** `chr1-206773552-T-C` (the `T>C` alternate, selected by the printed pair).
- **Naming citation.** `pmid:29802545` (*World J Pediatr* 2018;14(6):594-600) — "IL10 gene rs1800896
  (- 1082A/G) polymorphism"; the same abstract names the −819 locus with its rsID, so one paper
  covers both IL-10 rows. In LitVar2's trail for rs1800896.
- **Strand.** `minus`. `A/G` is not palindromic, so the round-trip is decisive: only the minus-strand
  reading complements to the GRCh38 pair `T/C`. Consistent with Ensembl 116 annotating IL10
  (`ENSG00000136634`) on strand −1 and with dbSNP's gene-oriented `NG_012088.1:g.3943A>G`.
- **Naming sanity check.** VEP places the variant 1,058 bp upstream of the canonical transcript
  `ENST00000423557` — 24 bp short of the legacy 1,082. The −819 locus is short by the **same** 24 bp,
  so both legacy offsets imply one common TSS at chr1:206772470, and the 263 bp between the two
  variants equals 1082 − 819 exactly. Two independently proposed rsIDs reconciling to one implied
  TSS is strong corroboration that this pair is what the legacy names denote.

### `cyt:il-10-819-t` — IL-10 −819, printed `C/T` — **resolved**

- **Candidate.** LitVar2 autocomplete for `IL10` returned `rs1800871`, named `c.-819C>T`, 1,371
  PMIDs. Querying `IL10 -819` also surfaced `rs1800872`, but LitVar2 names that one `c.-592C>A` — a
  different offset, so the two are separable on the evidence rather than by preference.
- **Resolution 1 — Ensembl 116 Variant Recoder:** `NC_000001.11:206773288:A:G`
  (`NC_000001.11:g.206773289A>G`); also `LRG_1230:4205:T:C`.
- **Resolution 2 — dbSNP build 157:** `NC_000001.11:206773288:A:G` on GRCh38.p14, alongside `A>C`
  and `A>T`. **The two agree exactly.**
- **Normalized identity.** `chr1-206773289-A-G`.
- **Naming citation.** `pmid:29802545` — "IL10 single nucleotide polymorphisms (SNPs) at … rs1800871
  (- 819C/T)". The printed pair `C/T` matches the citation's pair exactly. In LitVar2's trail for
  rs1800871.
- **Strand.** `minus`. `C/T` is not palindromic; only the minus-strand reading complements to the
  GRCh38 pair `A/G`. Consistent with IL10 on strand −1 and with `NG_012088.1:g.4206T>C`.
- **Naming sanity check.** VEP distance 795 vs the legacy 819 — the same 24 bp shift as −1082.

### `cyt:tnfalpha-308-a` — TNF-α −308, printed `G/A` — **resolved**

- **Candidate.** LitVar2 autocomplete for `TNF` returned `rs1800629`, named `c.-308G>A`, 3,969
  PMIDs. Querying `TNF -308` returned **only** rs1800629.
- **Resolution 1 — Ensembl 116 Variant Recoder:** `NC_000006.12:31575253:G:A`
  (`NC_000006.12:g.31575254G>A`), plus six MHC alt-contig placements.
- **Resolution 2 — dbSNP build 157:** `NC_000006.12:31575253:G:A` on GRCh38.p14. **The two agree
  exactly** on the primary assembly.
- **Normalized identity.** `chr6-31575254-G-A`.
- **Naming citation.** `pmid:22749237` (*Cytokine* 2012;60(1):249-56) — the legacy name and the rsID
  are in the **title**: "Tumor necrosis factor -308 polymorphism (rs1800629) is associated with
  mortality and ventilator duration in 1057 Caucasian patients". In LitVar2's trail for rs1800629.
- **Strand.** `plus`. `G/A` is not palindromic; only the plus-strand reading matches the GRCh38 pair
  (a minus-strand reading would require `C/T`). Consistent with Ensembl 116 annotating TNF
  (`ENSG00000232810`) on strand +1.
- **Alt-contig hazard, recorded.** dbSNP 157 also places rs1800629 on six MHC alt contigs, and on
  `HSCHR6_MHC_COX_CTG1` the reference allele is **A**, not G. Only the primary-assembly placement is
  in the registry, and an alt-contig placement must never be substituted for it.
- **Naming sanity check.** VEP places the variant 311 bp upstream of the canonical transcript
  `ENST00000449264` (and 304 bp from `ENST00001140822`), so no current transcript start reproduces
  the legacy 308 exactly. The legacy TSS differs from the present annotation by a few bases. The
  offset was therefore not used as evidence for this row; the citation and the two agreeing
  placements are.

## Refusals

**None in this batch.** No locus reached a refusal condition: every candidate was unique on the
evidence, both resources agreed on every placement, every row has a citation that prints the legacy
name and the rsID together, and the one palindromic locus had independent strand evidence available.

Had any of those failed, the row would have been written as `unresolved` with `rsid`,
`normalized_variant_id` and `strand` empty and `refusal_reason` naming what was tried. The registry
records that state as a row precisely so the same dead end is not re-investigated; there is simply
nothing to record for these four.

## What a verifier should check

1. That Terry 2000 (`pmid:10747905`) prints the IL-6 promoter sequence in the sense orientation, so
   the `cyt:il-6-174-c` strand argument rests on a printed sequence rather than on the naming
   convention alone. **This is the weakest link in the batch.**
2. That `pmid:29802545` is an acceptable naming citation for both IL-10 rows, given it is a single
   paper carrying both.
3. That the alternate-allele choice is right where the rsID is multi-allelic — rs1800795 (`C>G` vs
   `C>T`), rs1800896 (`T>C` vs `T>A`/`T>G`), rs1800871 (`A>G` vs `A>C`/`A>T`).
4. That the legacy-offset discrepancies (IL-10 −24 bp, TNF +3 bp, IL-6 −597 off by one) are
   acceptable as annotation drift rather than a sign that a different locus is meant.
