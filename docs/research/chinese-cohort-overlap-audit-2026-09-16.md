# Chinese genomic-resource participant-overlap audit

- **Issue:** [#326](https://github.com/bschilder/genomeOS/issues/326)
- **Audit date:** 2026-09-16
- **Scope:** PGG.Han, ChinaMAP, WBBC, NyuWa, and CMDB

## Decision

The public primary sources inspected here do not establish participant independence for any of
the ten resource pairs. No primary source explicitly reports participant sharing among the five,
but silence and different lead institutions are not evidence that the participants are disjoint.

**Operational rule:** genomeOS may ingest one of these resources by itself. It must not combine
any two in one fitted surface, pooled count, or validation fold as if they were independent until
that pair has either:

1. a written data-custodian statement that the released participant sets are disjoint; or
2. a deterministic participant-level overlap check using permitted identifiers or genomic
   fingerprints, with the method and result retained in provenance.

Geographic separation, recruitment-centre differences, non-overlapping published cohort names,
or aggregate allele-frequency comparisons do not clear a pair. This audit therefore advances
#326 but does not close it.

## Scientific contract

### Objective and claim

Determine whether the five Chinese genomic resources can be combined without counting the same
participants more than once. The only positive claim this audit can support is that a pair has a
documented shared source or has been cleared by direct evidence. A literature search that finds no
shared source is an unresolved result, not proof of independence.

### Measurable output and acceptance evidence

The output is a cited inventory of each resource's named source cohorts, recruitment setting and
time information, plus a complete ten-pair decision matrix. A pair is eligible for combination
only with one of the two acceptance records named above. Participant-disjoint sample identifiers
or genomic-fingerprint results are stronger than centre- or cohort-level statements and should be
preferred when lawful and available.

### Engineering boundary and consumers

This is a P1 observation-provenance decision. It changes no schema, source adapter, model, or
serving interface. Observation builders, dependency manifests, and benchmark split builders are
the consumers: unresolved pairs must stay in separate builds or be declared dependent rather than
treated as independent evidence.

### Assumptions and refusal conditions

- Published sample totals describe releases, not necessarily mutually exclusive people.
- A shared cohort proves possible or actual dependence; a shared city or hospital only raises a
  question.
- A variant-catalogue overlap is not participant overlap evidence.
- The audit refuses to infer independence from missing statements, different institutions,
  different assays, sex or age differences, or apparently distinct recruitment purposes.
- If custodians cannot answer and participant-level checking is unavailable, refusal to merge is
  the final valid result.

## Evidence vocabulary

| State | Meaning | Merge consequence |
|---|---|---|
| `documented_shared_source` | A primary source identifies a shared constituent cohort or released participant set. | Do not combine as independent; deduplicate or model the dependency. |
| `no_named_overlap_found` | Inspected primary sources name different source cohorts, but do not certify disjoint participants. | Do not combine yet. Seek custodian confirmation or direct checking. |
| `source_inventory_incomplete` | At least one resource does not enumerate the studies supplying its participants. | Do not combine; this is the highest-priority provenance gap. |
| `participant_independence_verified` | Custodian confirmation or permitted participant-level comparison establishes disjoint released sets. | Pair may be combined, retaining the verification record. |

No pair reached `participant_independence_verified` in this audit.

## Resource inventory

### PGG.Han

The PGG.Han paper reports 114,783 people. Its approximately 12,000 whole genomes include 319
deep-sequenced samples from cited published datasets, 11,670 low-pass genomes from CONVERGE, and
208 low-pass genomes cited to the 1000 Genomes Project. The other 102,586 high-density genotyped
samples came from “previous GWAS projects”; only non-patient controls were retained. The paper
does not enumerate those GWAS projects or their recruitment centres and years. Geographic origin
was available for 56,308 of those samples.

This unnamed 102,586-sample block makes PGG.Han the central unresolved overlap risk. Its named
CONVERGE and 1000 Genomes inputs also demonstrate that PGG.Han is an aggregation of reused cohorts,
not a single independent recruitment.

Primary source: [Gao et al., *Nucleic Acids Research* 2020](https://doi.org/10.1093/nar/gkz829).

### ChinaMAP

ChinaMAP reports 10,588 deep whole genomes randomly selected without disease-based filtering from
three named source cohorts:

- China Noncommunicable Disease Surveillance 2010;
- Risk Evaluation of cAncers in Chinese diabeTic Individuals: a lONgitudinal study (REACTION);
- Community-based Cardiovascular Risk During Urbanization in Shanghai.

The source cohorts together contained about 450,000 participants. The sequenced release covers
eight ethnic populations across 27 provinces; the reported mean age was 54 years and 64.8% were
women. The paper does not state whether the released participants also occur in any of the other
four resources.

Primary source: [Cao et al., *Cell Research* 2020](https://doi.org/10.1038/s41422-020-0322-9).

### WBBC

The WBBC pilot paper reports 10,376 analyzed people: 4,535 whole-genome-sequenced participants and
6,025 array-genotyped participants, including 184 in both assay groups. After removing contaminated
and duplicated WGS samples, 4,480 remained. The Westlake recruitment had enrolled 14,726 people
aged 14–25 across 29 administrative divisions; Xiangya Hospital supplied another 3,335 people aged
51–89, including 1,973 Parkinson's disease patients and 1,362 healthy controls. The paper identifies
Westlake University and Xiangya Hospital as the collection sources but does not state whether any
participants occur in the other four resources.

Primary source: [Cong et al., *Nature Communications* 2022](https://doi.org/10.1038/s41467-022-30526-x).

### NyuWa

NyuWa reports 2,999 deep whole genomes from diabetes cases and controls collected through hospitals
or physical-examination centres in 23 administrative divisions. Most samples were collected in
Shanghai, Guangdong, and Beijing. The paper assigns geography from native place when available and
otherwise from the collection province; it explicitly notes that native place was missing for many
participants and treats the collecting hospital as an approximation.

A later primary analysis establishes that the NyuWa accession OEP002803 includes WGS from the
MARCH randomized trial. MARCH recruited 788 people with newly diagnosed type 2 diabetes from 11
clinical centres between November 2008 and June 2011; 604 passed the later analysis filters. This
creates a specific question for ChinaMAP because both resources contain metabolic/diabetes clinical
recruitment, but it does not prove participant sharing with REACTION or either other ChinaMAP cohort.

Primary sources:

- [Zhang et al., *Cell Reports* 2021](https://doi.org/10.1016/j.celrep.2021.110017).
- [Wang et al., *Communications Medicine* 2023](https://doi.org/10.1038/s43856-023-00258-0).

### CMDB

CMDB reports low-coverage genomes from 141,431 unrelated healthy pregnant women recruited for BGI
non-invasive fetal-trisomy testing in 2012–2013. The release covers 31 administrative divisions,
Han participants, and 36 other ethnic groups. This is a named and unusually specific source cohort,
but the paper does not certify that none of these participants later entered one of the other four
resources.

Primary source: [Li et al., *Nucleic Acids Research* 2023](https://doi.org/10.1093/nar/gkac638).

## Pairwise decision matrix

| Pair | Literature finding | State | Current decision |
|---|---|---|---|
| PGG.Han × ChinaMAP | No named shared source found. PGG.Han's 102,586 prior-GWAS controls are not enumerated, so ChinaMAP's three cohorts cannot be excluded. | `source_inventory_incomplete` | Refuse merge. Ask PGG.Han custodians for the constituent-study inventory and both custodians for a direct check. |
| PGG.Han × WBBC | No named shared source found. PGG.Han's prior-GWAS block prevents exclusion of WBBC contributors or controls. | `source_inventory_incomplete` | Refuse merge. |
| PGG.Han × NyuWa | No named shared source found. PGG.Han's prior-GWAS block prevents exclusion of NyuWa hospital, examination-centre, or MARCH participants. | `source_inventory_incomplete` | Refuse merge. |
| PGG.Han × CMDB | No named shared source found. CMDB's NIPT cohort is specific, but PGG.Han does not enumerate all contributing GWAS controls. | `source_inventory_incomplete` | Refuse merge. |
| ChinaMAP × WBBC | Named source cohorts and lead collection programmes differ; no primary-source statement certifies participant independence. | `no_named_overlap_found` | Refuse merge pending confirmation or direct check. |
| ChinaMAP × NyuWa | No named shared cohort found. ChinaMAP includes REACTION and other metabolic cohorts; NyuWa includes diabetes samples and MARCH across 11 clinical centres. Shared participants remain plausible enough to ask directly. | `no_named_overlap_found` | Refuse merge; prioritize a targeted custodian query. |
| ChinaMAP × CMDB | ChinaMAP's three named cohorts differ from CMDB's 2012–2013 NIPT cohort; no independence statement was found. | `no_named_overlap_found` | Refuse merge pending confirmation or direct check. |
| WBBC × NyuWa | Named collection programmes differ; no independence statement was found. | `no_named_overlap_found` | Refuse merge pending confirmation or direct check. |
| WBBC × CMDB | Named collection programmes and reported participant profiles differ; no independence statement was found. | `no_named_overlap_found` | Refuse merge pending confirmation or direct check. |
| NyuWa × CMDB | Hospital/examination-centre diabetes recruitment differs from CMDB's NIPT cohort; no independence statement was found. | `no_named_overlap_found` | Refuse merge pending confirmation or direct check. |

The NyuWa paper's comparison with ChinaMAP concerns overlap among variants in their catalogues. It
does not address whether the same people appear in both resources and must not be used as clearance.

## Questions prepared for data custodians

These questions are prepared for review. They have not been sent.

### PGG.Han

1. Which named studies, accessions, recruitment centres, and recruitment years supplied the
   102,586 genotyped controls described as coming from previous GWAS projects?
2. Do the released PGG.Han samples include anyone in the released ChinaMAP, WBBC, NyuWa/OEP002803
   (including MARCH), or CMDB participant sets?
3. Can the custodians perform a privacy-preserving identifier or genomic-fingerprint comparison
   against those releases and report pairwise overlap counts?

### ChinaMAP and NyuWa

1. Do any NyuWa/OEP002803 participants, including MARCH participants, occur in ChinaMAP's
   REACTION, China NCD Surveillance 2010, or Shanghai urbanization source cohorts?
2. Did the MARCH and REACTION programmes share any recruiting centres during overlapping years,
   and if so, were duplicate participants checked across releases?
3. Can the custodians report the result of a cross-release identifier or genomic-fingerprint
   comparison without disclosing identities?

### All five custodians

1. Were any released participants contributed to another resource in this audit under a different
   project or sample identifier?
2. Which exact release/version did the comparison cover, and were withdrawn or QC-excluded samples
   included in the check?
3. If overlap exists, can the custodian provide a reusable dependency mapping or aggregate overlap
   count adequate to prevent double counting?

## Required next evidence

The fastest useful path is a PGG.Han constituent-study inventory, followed by a targeted
ChinaMAP–NyuWa query. Those address the two concrete uncertainties found in the literature. Generic
requests to all authors can proceed after review, but author contact must not be represented as
completed until a message is actually sent and its response retained.

If individual-level data become available under compatible terms, the stronger check is a
privacy-preserving genomic fingerprint comparison across the exact released sample sets. That work
requires its own reviewed protocol for consent, access, allowed derivatives, relatedness thresholds,
build/allele alignment, and false-match handling. It must not be approximated from public aggregate
allele frequencies.
