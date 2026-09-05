# Literature Evidence Foundation — Design

**Status:** proposed, pending human review
**Date:** 2026-09-05
**Scope:** issue #149; the reusable publications evidence contract, deterministic P1 adapter,
LCT/MCM6 pilot integration path, and tracker repair. HBB and G6PD corpus work are follow-on
sub-projects with separate scientific acceptance evidence.

---

## 1. Scientific contract

### Objective and product claim

genomeOS can use measurements extracted from publications as a first-class P1 source without
making a paper-derived row less auditable than a database-derived row. A publication-derived
observation may enter P1 only when its counted allele, denominator, contributing cohort,
ascertainment design, geographic support, and exact source location are all explicit.

The claim is deliberately narrower than “genomeOS can parse the literature.” Publications do not
share a machine-readable format, and extraction remains curation. The reusable component is a
versioned evidence ledger and a deterministic adapter from reviewed evidence into P1.

### Measurable output and acceptance evidence

This sub-project is accepted when:

1. a frozen `literature_evidence` contract preserves the source text needed to audit every count,
   including the literal reported frequency rather than a binary-float rendering of it;
2. a frozen `literature_searches` contract records the database, exact query, execution date,
   every candidate identifier, and an explicit inclusion, exclusion, or pending decision;
3. every P1 allele-count row carries a globally unique `source_record_id`, including rows from
   existing gnomAD, MAP, and AFND adapters;
4. an exact, verified literature row resolves through P0 and produces a schema-valid P1
   observation linked back to exactly one evidence row;
5. reconstructed or interval-valued counts, unverified source rows, ambiguous variants,
   unregistered population labels, and duplicate source records are refused for stated reasons;
6. a fixture-backed LCT/MCM6 build demonstrates the full path, while an audit of the user-supplied
   pilot reconciles all 426 rows without pretending its missing P1 metadata has been curated;
7. the frozen contracts, focused tests, smoke suite, full test suite, lint, module-size check, and
   private-file check pass.

### Engineering component and public interfaces

- `LITERATURE_EVIDENCE_SCHEMA` validates extracted measurements and their provenance.
- `LITERATURE_SEARCHES_SCHEMA` validates reproducible discovery and screening records.
- `publications.load(...) -> tuple[pd.DataFrame, pd.DataFrame, IngestReport]` validates evidence,
  resolves population aliases through P0, returns P1 observations plus the retained evidence rows,
  and reports scientific refusals.
- `OBSERVATIONS_SCHEMA.source_record_id` links every measurement to its source-native record.
- `scripts/fetch_pubmed_manifest.py` snapshots PubMed ESearch results; it performs network I/O but
  contains no scientific interpretation.
- `scripts/audit_lct_pilot.py` inventories a user-supplied pilot CSV and produces a curation report;
  it does not fill missing ascertainment, radius, cohort, or source-locator fields.
- `scripts/build_observations.py --literature-evidence ...` composes the offline adapter with the
  existing P1 build.

### Assumptions, refusal conditions, and downstream consumers

Assumptions:

- literature extraction is reviewed curation, not an automated truth source;
- coordinates describe either the sampling location or the source's stated population locality,
  and P0 records which through `location_type` and `uncertainty_radius_km`;
- an exact count means one integer allele count is supported by the source, not merely selected by
  rounding a printed frequency;
- study and cohort identities are stable across papers so repeated publication of one cohort can
  be detected rather than counted twice.

Refuse entry into P1 when:

- the count is interval-valued or reconstructed from a rounded frequency;
- the evidence row remains `pending` rather than verified against its stated source location;
- the counted allele, strand, reference build, or GRCh38 normalization is ambiguous;
- `sampling_design`, `disease_ascertainment_excluded`, cohort identity, assay, or dates are absent;
- the population label does not resolve through P0 to coordinates and a non-default radius;
- one record spans multiple countries without a defensible regional population entry and radius;
- a duplicate source record or duplicate cohort/sample measurement would create
  pseudo-replication;
- source access or reuse terms do not permit the proposed repository or artifact operation.

The evidence ledger is consumed by the P1 publications adapter and by reviewers. P1 observations
are consumed unchanged by P2 surface fitting and P4 observation serving. No publication parsing,
variant normalization, or scientific adjudication occurs on the serving path.

## 2. Scope boundaries

### Included

- publication discovery manifests;
- a normalized, frozen literature evidence contract;
- stable provenance linkage from P1 to source-native rows;
- fail-closed population, count, variant, verification, and duplicate handling;
- an LCT/MCM6 rs4988235 pilot fixture and audit/migration path;
- compatibility updates for every existing allele-count adapter;
- tracker corrections for #7, #8, #45, #117, and #149;
- separate issues specifying HBB round-trip validation and G6PD literature ingestion.

### Excluded

- a generic PDF, OCR, table, or LLM extraction engine;
- automatic acceptance of model-generated or OCR-derived numbers;
- a comprehensive ingest of all PubMed allele-frequency papers;
- a likelihood for interval-censored or uncertain allele counts;
- closing HbS or G6PD golden tests without their real acceptance runs;
- redistributing article text, tables, supplements, or a corpus with unsettled reuse terms;
- ancient-DNA fitting, which remains P6 even though evidence rows retain dates.

## 3. Approaches considered

### A. One generic publication parser

Rejected. Papers vary across prose, tables, figures, supplements, allele orientation, sample
definitions, and ascertainment. A parser that emits P1 directly would hide judgement inside an
adapter and make false exactness hard to review.

### B. Add all provenance columns directly to P1

Rejected. PMID, DOI, table location, reported strings, extraction method, and verification state
are evidence metadata, not inputs to the spatial model. Repeating them on every observation would
bloat the hot table and couple P2 to curation details it does not consume.

### C. Evidence ledger plus a stable P1 foreign key

Selected. The ledger retains the verbose audit trail; P1 gains only `source_record_id`. The
adapter is small because it translates already-reviewed evidence rather than interpreting papers.
The same design scales from a hand-curated pilot to thousands of candidates without weakening the
P1 contract.

## 4. Data flow and component boundaries

```text
PubMed query / known compilation
              |
              v
literature_searches  -- every candidate and screening decision
              |
              v
human-reviewed extraction
              |
              v
literature_evidence  -- source-native measurement + provenance
        |                              |
        | variant/count checks         | population alias
        v                              v
                      P0 registry
                           |
                           v
                    publications.load
                           |
             +-------------+-------------+
             |                           |
             v                           v
      P1 observations             retained evidence
      source_record_id             reviewer/audit path
             |
             v
       offline P2 fitting
```

`genomeos.observations.evidence` owns only the two evidence schemas and their controlled
vocabularies. It performs no network or filesystem I/O.

`genomeos.observations.sources.publications` owns evidence-to-P1 translation and refusal reporting.
It consumes validated P0 tables and does not fetch papers or interpret free text.

`scripts/fetch_pubmed_manifest.py` owns PubMed ESearch I/O. Its output is a versioned screening
table, not observations. Re-running a query creates a new manifest version rather than mutating a
past screening decision.

## 5. Contracts

### 5.1 `literature_searches`

One row per candidate returned by one reproducible search:

| column | type | rule |
|---|---|---|
| `search_id` | string | stable identifier for database + query + execution |
| `corpus_id` | string | target corpus, for example `lct-rs4988235` |
| `database` | enum | initially `pubmed`; widening requires a contract change |
| `query` | string | exact submitted query, non-empty |
| `executed_at` | UTC timestamp string | the date-dependent search is reproducible |
| `candidate_id` | string | `pmid:<digits>` initially |
| `decision` | enum | `included`, `excluded`, or `pending` |
| `decision_reason` | nullable string | required for `excluded`; absent for `pending` |
| `manifest_version` | string | immutable data version |

Candidate identifiers are unique within a `search_id`. A search result begins as `pending` and is
changed only by publishing a new manifest version.

### 5.2 `literature_evidence`

One row per independently sampled population measurement:

| column | type | rule |
|---|---|---|
| `source_record_id` | string | globally unique, stable, source-native row identity |
| `corpus_id` | string | corpus owning the extraction |
| `variant_id` | string | normalized GRCh38 `chr-pos-ref-alt` |
| `rsid` | nullable string | source identifier when present |
| `counted_allele` | string | literal allele whose copies `ac` represents |
| `normalization_status` | enum | `verified` or `ambiguous`; only verified enters P1 |
| `population_label` | string | verbatim label used by the source |
| `sample_id` | string | sample within a study; distinguishes legitimate replicated samples |
| `cohort_id` | string | contributing cohort across sites and publications |
| `an` | positive integer | allele denominator supported by the source |
| `ac_lower`, `ac_upper` | integers | admissible allele-count interval, `0 <= lower <= upper <= an` |
| `reported_frequency` | nullable string | verbatim printed value, preserving decimals and symbols |
| `count_basis` | enum | `reported`, `genotype_derived`, or `frequency_reconstructed` |
| `denominator_basis` | enum | `reported_alleles`, `diploid_individuals`, or `hemizygous_males` |
| `citation_id` | string | namespaced persistent ID: `pmid:`, `doi:`, or `thesis:` |
| `citation_text` | string | human-readable citation |
| `source_locator` | string | table, figure, page, supplement, and row where possible |
| `source_url` | nullable string | stable full-text or landing-page URL |
| `assay` | string | what produced the measurement |
| `sampling_design` | P1 enum | no default |
| `disease_ascertainment_excluded` | boolean | nullable representation forbidden |
| `date_lower`, `date_upper` | non-negative integers | years BP; lower <= upper |
| `verification_status` | enum | `original_source_verified`, `compilation_verified`, `pending` |
| `extraction_method` | enum | `manual_transcription`, `structured_table`, or `ocr_reviewed` |
| `notes` | nullable string | caveats; never substitutes for a structured field |
| `ingest_version` | string | immutable corpus version |

`ac_lower == ac_upper` is required for P1 emission. The emitted `ac` is that shared integer.
Interval-valued rows remain useful evidence and remain visible in the refusal report, but the
existing binomial likelihood must not receive a fabricated point count.

`reported_frequency` is a string deliberately. A value printed as `0.16` does not carry the same
rounding interval as `0.1600`, and parsing both to binary float destroys the distinction needed to
audit reconstruction.

### 5.3 P1 linkage

`OBSERVATIONS_SCHEMA` gains required non-empty `source_record_id`. Every adapter must construct it
from stable source-native identifiers; row positions in a local dataframe are not stable IDs.

The combined observation build rejects duplicate `source_record_id` values. A publication
evidence build also rejects duplicate `(variant_id, population_id, cohort_id, sample_id)` rows,
because publishing the same cohort twice would give it twice the statistical weight.

The evidence ledger is not joined onto P2 inputs. Audit consumers join it to observations through
`source_record_id` only when provenance is requested.

## 6. LCT/MCM6 pilot policy

The external pilot contains 426 rows from 88 country strings. Its current audit identifies 116
frequency-reconstructed rows, 34 `small_n` rows, eight thesis rows without PMIDs, and eight
corrected no-call denominators. It is primarily a structured extraction from Liebert et al. 2017
Supplementary Table 3, with original citations attached; ten rows were verified against an
original paper.

The repository will not label the corpus “complete.” It has two levels:

- `original_source_verified`: the underlying paper/table was checked directly;
- `compilation_verified`: the accessible compilation was checked, but the original measurement
  was not independently inspected.

Both may enter P1 only when the count interval is exact and all other refusal conditions pass.
`pending` never enters P1. `small_n` is not itself a refusal: the denominator belongs in the
likelihood, so a small exact measurement is weak evidence rather than invalid evidence.

The current external CSV is a curation input, not yet a `literature_evidence` table: it does not
contain uncertainty radii, sampling designs, cohort/sample identities, exact source locators, or
verification state for each row. The first migration tool therefore inventories all 426 rows and
reports what must be curated; it does not manufacture those fields or emit P1 observations. Once a
reviewed evidence table exists, the publications adapter emits only eligible exact rows. It never
coerces country strings into ISO3 identifiers. Labels such as `Angola, Namibia Botswana` require an
explicit regional P0 entry with a defensible uncertainty radius or are refused.

The complete CSV is not copied into this repository until its owner/contributor supplies explicit
reuse terms or directly contributes it under clearly stated terms. Until then, a small synthetic
fixture exercises every adapter path and the audit tool accepts a user-supplied local file without
publishing it.

## 7. Expansion strategy

Expansion is driven by the curated variant set (#32), not by the raw size of a PubMed query. Each
corpus gets a versioned search manifest and a locus-specific issue stating its scientific target.

### HBB round-trip sub-project

Extract rs334 measurements independently from publications, then compare retained rows with the
MAP compilation already ingested by `map_surveys`. Acceptance is not equality of row count; it is
that matched source/cohort measurements agree on allele orientation, counts, denominator, site,
and study grouping. Differences become explicit adjudication records. This validates the
literature workflow against a known corpus without claiming HbS burden parity.

### G6PD sub-project

Keep named G6PD variants separate from MAP's `phenotype:g6pd-deficiency` enzyme-activity composite.
Literature genotype rows use variant IDs and X-linked denominators; activity-assay prevalence rows
remain the phenotype. No adapter may merge them. The sub-project must state whether it supports
variant surfaces, phenotype parity, or both before extraction starts.

### Later corpora

Only variants accepted into #32 receive full extraction. Discovery may be automated, but every
included evidence row remains review-gated. Search manifests make non-English sources, excluded
papers, and geographic gaps visible rather than allowing curation to become an undocumented
convenience sample.

## 8. Error handling and refusals

Schema violations are hard errors. They identify malformed evidence, not scientifically ineligible
evidence.

Scientifically well-formed but P1-ineligible rows are counted in `IngestReport.refusals` under
stable reasons:

- `count_not_exact`
- `source_not_verified`
- `variant_ambiguous`
- `population_region_unresolved`

An entirely unmapped ordinary population label raises `UnmappedPopulationError`, matching the
existing P0/P1 invariant. The regional refusal exists only for labels that explicitly span several
countries and cannot honestly be represented as one registered locality.

Duplicate identifiers, inconsistent count intervals, contradictory aliases, and duplicate
cohort/sample measurements raise rather than enter a refusal report; they make the dataset
internally ambiguous and must be corrected at source.

## 9. Testing and review evidence

Tests follow red-green-refactor and cover:

- evidence and search schemas accept complete rows and reject every required-field omission;
- citation namespaces, count interval ordering, date ordering, and conditional search-decision
  rules are frozen into the contracts;
- the literal reported frequency survives CSV and Parquet round trips unchanged;
- an exact verified row maps through P0 and yields the expected P1 row;
- approximate, pending, ambiguous, and multi-country rows receive their stated refusal reason;
- an unmapped ordinary population raises;
- duplicate source IDs and duplicate cohort/sample measurements raise;
- all existing source adapters emit deterministic, non-empty source record IDs;
- the combined store rejects cross-source ID collisions;
- the PubMed parser preserves all returned PMIDs and starts each as `pending`;
- the LCT fixture produces a disposition report whose totals reconcile exactly.

The PR must report focused test commands and every mandatory repository gate. Because the schema
changes, `python scripts/freeze_contract.py` must regenerate and commit the contract diff.

## 10. Tracker changes

After this spec is approved:

1. Reopen #45 and comment that PR #91 explicitly advanced rather than closed it; the real parity
   acceptance run has not passed.
2. Comment on #7 and #8 with the foundations already delivered by PR #81 and checklists of their
   still-open definition-of-done items.
3. Retitle #117 to the remaining AFND reuse/redistribution-terms decision and replace its obsolete
   access/adapter description with links to PR #124 and #66.
4. Rewrite #149 around this evidence-ledger design, correct the pilot claims and link, apply
   `type:data`, `P1:observations`, `skill:popgen`, `priority:medium`, and
   `wants-expert-review`, and keep it open until the implementation PR satisfies this spec.
5. File one HBB round-trip issue and one G6PD literature issue with the distinct acceptance targets
   in §7. Neither issue closes a golden test.

## 11. Documentation changes

The implementation updates the architecture source list in `docs/overview.md` to add publications
as a source class and explains that the ledger, not arbitrary paper parsing, is the reusable unit.
It updates `docs/scientific-engineering-objectives.md` so observation provenance and exact-count
refusal are acceptance evidence. The module docstrings cite design §6 and §7.1 and this spec.

No published scientific result, fitted surface, or burden artifact is added by this sub-project.
