# Literature Evidence Foundation — Design

**Status:** approved by the user on 2026-09-05
**Date:** 2026-09-05
**Scope:** issue #149; the reusable publications evidence contract, deterministic P1 adapter,
rs4988235 lactase-persistence pilot integration path, and tracker repair. HBB and G6PD corpus work
are follow-on sub-projects with separate scientific acceptance evidence.

**Implementation plan:**
[`2026-09-05-literature-evidence-foundation.md`](../plans/2026-09-05-literature-evidence-foundation.md)

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

1. frozen `literature_evidence` and `literature_field_evidence` contracts preserve both unresolved
   fields and the source text needed to audit every supplied or derived value, including the
   literal reported frequency rather than a binary-float rendering of it;
2. a frozen `literature_searches` contract records the database, exact query, execution date,
   every candidate identifier, and an explicit inclusion, exclusion, or pending decision;
3. every P1 allele-count row carries a globally unique `source_record_id`, including rows from
   existing gnomAD, MAP, and AFND adapters;
4. a deterministic promotion gate—not a caller-supplied eligibility flag—allows an exact, verified
   literature row to resolve through P0 and produce a schema-valid P1 observation linked back to
   exactly one evidence row;
5. reconstructed or interval-valued counts, unverified source rows, ambiguous variants,
   unregistered population labels, and duplicate source records are refused for stated reasons;
6. a fixture-backed rs4988235 lactase-persistence build demonstrates the full path, while an audit
   of the user-supplied pilot reconciles all 426 rows without pretending its missing P1 metadata
   has been curated;
7. a contributor guide and schema-checked example files show a promotable record, a valid
   unresolved staging record, every allowed derivation, and representative prohibited shortcuts;
8. the frozen contracts, focused tests, smoke suite, full test suite, lint, module-size check, and
   private-file check pass.

### Engineering component and public interfaces

- `LITERATURE_EVIDENCE_SCHEMA` validates extracted measurements and their provenance.
- `LITERATURE_FIELD_EVIDENCE_SCHEMA` records whether every evidence-tracked field was reported,
  deterministically derived, absent after review, ambiguous, or not yet reviewed.
- `LITERATURE_SEARCHES_SCHEMA` validates reproducible discovery and screening records.
- `publications.load(...) -> tuple[pd.DataFrame, pd.DataFrame, IngestReport]` validates evidence and
  field evidence, computes eligibility, resolves population aliases through P0, returns P1
  observations plus the retained evidence rows, and reports scientific refusals.
- `OBSERVATIONS_SCHEMA.source_record_id` links every measurement to its source-stable record.
- `scripts/fetch_pubmed_manifest.py` snapshots PubMed ESearch results; it performs network I/O but
  contains no scientific interpretation.
- `scripts/audit_lct_pilot.py` inventories a user-supplied pilot CSV and produces a curation report;
  it assigns only source-anchored IDs and dataset-record locators and does not fill missing
  ascertainment, radius, cohort, or original-study field locators.
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
  be detected rather than counted twice;
- an LLM or automated extractor may propose a value but may never mark its own extraction as
  verified; automated output enters with row status `pending` and explicit per-field non-value
  states wherever support has not been inspected;
- source terms are checked and recorded; when no explicit reuse restriction is found, the project
  presumes the extracted factual data reusable by downstream users with attribution. This is the
  repository owner's policy decision, not a legal conclusion.

Refuse entry into P1 when:

- the count is interval-valued or reconstructed from a rounded frequency;
- the evidence row remains `pending` rather than verified against its stated source location;
- the counted allele, strand, reference build, or GRCh38 normalization is ambiguous;
- `sampling_design`, `disease_ascertainment_excluded`, cohort identity, assay, or dates are absent;
- the population label does not resolve through P0 to coordinates and a non-default radius;
- one record spans multiple countries without a defensible regional population entry and radius;
- a duplicate source record or duplicate cohort/sample measurement would create
  pseudo-replication;
- explicit source terms prohibit the proposed repository or artifact operation, or terms have not
  yet been checked. Checked sources with no explicit restriction are not refused.

“Conservative” is not an exemption. A large radius, `convenience` sampling design, singleton
cohort, nearest known coordinate, modal assay, zero count, or copied value from another population
is still an invented substitute unless an approved source-specific derivation names the raw input,
source locator, transformation, and bound it establishes.

The evidence ledger is consumed by the P1 publications adapter and by reviewers. P1 observations
are consumed unchanged by P2 surface fitting and P4 observation serving. No publication parsing,
variant normalization, or scientific adjudication occurs on the serving path.

## 2. Scope boundaries

### Included

- publication discovery manifests;
- normalized, frozen literature evidence and per-field evidence contracts;
- stable provenance linkage from P1 to source-stable rows;
- fail-closed population, count, variant, verification, and duplicate handling;
- a canonical curation guide backed by valid and invalid fixture files;
- an rs4988235 lactase-persistence pilot fixture and audit/migration path;
- compatibility updates for every existing allele-count adapter;
- tracker corrections for #7, #8, #45, #117, and #149;
- separate issues specifying HBB round-trip validation and G6PD literature ingestion.

### Excluded

- a generic PDF, OCR, table, or LLM extraction engine;
- automatic acceptance of model-generated or OCR-derived numbers;
- a comprehensive ingest of all PubMed allele-frequency papers;
- a likelihood for interval-censored or uncertain allele counts;
- closing HbS or G6PD golden tests without their real acceptance runs;
- redistributing article text, tables, or supplements rather than extracted factual records;
- using a source whose explicit terms prohibit the proposed operation;
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
literature_evidence + literature_field_evidence
                     -- source-stable measurement, missingness, provenance
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

`genomeos.observations.evidence` owns the search, record, and per-field evidence schemas and their
controlled vocabularies. It performs no network or filesystem I/O.

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

One row represents one measurement of one allele in one independently sampled population or
sample stratum. It does **not** represent one paper, one country, one table, or one population name
aggregated across studies. If a table reports three sampled populations, it produces three rows. If
one population has two independently recruited samples, it produces two rows with distinct
`sample_id` values.

Every column below must appear exactly once in the UTF-8 TSV header, in the documented order.
“May be blank” means an empty TSV cell, which the loader reads as null; strings such as `NA`,
`N/A`, `unknown`, `none`, `null`, `-`, and `TBD` are data and are rejected as fake missingness.
Whitespace is trimmed only at the outside of a cell and is never used to rewrite a source value.
Literal tabs, carriage returns, and newlines inside cells are rejected. Structured multi-value cells
use compact canonical JSON with double-quoted keys, sorted keys, and no insignificant whitespace.
The canonical header has 37 columns: concatenate the column names in §§5.2.1–5.2.6 from top to
bottom. The checked fixture in §5.5 contains the copyable literal header.

Identifiers use these anchored patterns; examples do not widen them:

```text
corpus_id          ^[a-z0-9]+(?:-[a-z0-9]+)*$
source_record_id   ^literature:([a-z0-9]+(?:-[a-z0-9]+)*):[0-9a-f]{64}$
rsid               ^rs[1-9][0-9]*$
cohort_id          ^cohort:[a-z0-9][a-z0-9.-]*:[a-z0-9][a-z0-9.-]*$
ingest_version     ^([a-z0-9]+(?:-[a-z0-9]+)*)@[0-9]{4}-[0-9]{2}-[0-9]{2}\.[1-9][0-9]*$
PMID citation      ^pmid:[1-9][0-9]*$
DOI citation       ^doi:10\.[0-9]{4,9}/\S+$  (stored lowercase)
thesis citation    ^thesis:[a-z0-9][a-z0-9.-]*:[A-Za-z0-9][A-Za-z0-9._/-]*$
repository source  ^repo:github\.com/[a-z0-9_.-]+/[a-z0-9_.-]+@[0-9a-f]{40}:[^\t\r\n]+$
source_locator     ^(table|figure|page|supplement|dataset-record):[^\t\r\n]+$
human identity     ^human:[a-z0-9](?:[a-z0-9-]{0,37}[a-z0-9])?$
agent identity     ^agent:[a-z0-9][a-z0-9.-]*:[a-z0-9][a-z0-9._-]*$
import identity    ^import:[a-z0-9][a-z0-9._/-]*@[0-9a-f]{40}$
```

The captured corpus segment in `source_record_id` and `ingest_version` must equal the row's
`corpus_id` exactly. Locator syntax is necessary but not sufficient: generic payloads such as
`table:unknown`, `page:the-paper`, or `supplement:supplement` are rejected as placeholders.

The requirement columns have literal meanings:

- **Staging value:** `required` means a non-null value is required even for an incomplete record;
  `may be blank` means the incomplete record remains valid evidence.
- **Promotion value:** `required` means a non-null, evidence-backed value is necessary to emit P1;
  `optional` means absence does not block P1; `conditional` states the exact condition.
- Every field named in §5.3 also needs its own field-evidence row. A non-null cell alone is never
  proof that the value was reported or validly derived.

#### 5.2.1 Identity and variant columns

| column | type | staging value | promotion value | exact meaning and format | reject or refuse |
|---|---|---|---|---|---|
| `source_record_id` | string | required | required | Loader-generated immutable ID `literature:<corpus_id>:<digest>`. `<digest>` is the complete 64-character lowercase hexadecimal SHA-256 over UTF-8 `record_source_id + "\n" + record_locator` at first staging. | A caller-chosen ID, local dataframe row number, random UUID, mutable population name, regenerated ID after correction, or one ID reused for two measurements. |
| `corpus_id` | string | required | required | Issue-approved lowercase kebab-case corpus, for example `lct-rs4988235`; every row in one corpus build uses the same value. | A paper title, free-form topic, branch name, or value that changes between runs. |
| `variant_id` | nullable string | may be blank | required | One-based, minimal, reference-forward GRCh38 ID `chr<chrom>-<pos>-<ref>-<alt>` matching the P1 variant pattern. It names the allele represented after normalization, not merely the source's printed build. | GRCh37 coordinates relabelled as GRCh38, an rsID in this column, an unverified liftover, or a guessed REF/ALT orientation. |
| `rsid` | nullable string | may be blank | optional | Lowercase dbSNP ID `rs<digits>` only when printed by the source or returned by the same reviewed normalization record used for `variant_id`. A field-evidence row is still required. | Gene symbols, internal marker names, multiple IDs in one cell, or an rsID guessed from nearby coordinates. |
| `counted_allele` | nullable string | may be blank | required | Uppercase normalized allele counted by `ac_lower`/`ac_upper`; at promotion it must equal the ALT component of `variant_id`. The source's literal allele remains in field evidence as `raw_value`. | Effect/risk/derived/ancestral labels treated as DNA bases, strand complements without normalization evidence, or an allele inconsistent with ALT. |
| `normalization_status` | enum | required but recomputed | must be `verified` | `verified` when the validated variant/allele field evidence deterministically yields one GRCh38 REF/ALT orientation; `ambiguous` when it yields multiple valid mappings; `unresolved` when inputs or a mapping are absent. | A caller-chosen status or marking verified because an rsID “looks right”; ambiguous and unresolved are valid staging states but never promote. |

`variant_id` and `counted_allele` describe the normalized output. Their field-evidence rows preserve
the literal source notation and the exact normalization method. If a source reports the reference
allele count, the alternate count may be derived as `an - source_ac` only through the named
reference-to-alternate derivation; silently relabelling the source count is forbidden.

For example, first-stage inputs
`repo:github.com/example/example@0000000000000000000000000000000000000000:data.tsv` and
`dataset-record:row-17` hash to
`7220defbe35cb5adbb8ee065f2d2460e03079f6d6cfacbc130477ca655543568`, yielding that digest after
the `literature:lct-rs4988235:` prefix. If one source row contains multiple measurements, each
locator must name the exact cell/column as well as the row so the identities remain distinct.

#### 5.2.2 Population, sampling, and time columns

| column | type | staging value | promotion value | exact meaning and format | reject or refuse |
|---|---|---|---|---|---|
| `population_label` | string | required | required | Exact source label for the sampled group, preserving spelling, punctuation, and language after outer-whitespace trimming. P0 resolves this literal label through an explicit alias. | ISO3 substitution, translation, country expansion, inferred ethnicity, or splitting one regional label into several rows. |
| `sample_id` | nullable string | may be blank | conditional | Verbatim source sample/stratum identifier. It is required when the same original citation, population, cohort, and variant have more than one separately reported measurement; otherwise it may remain blank. | Invented `sample1`, local dataframe row numbers, or using a population label as a sample ID. |
| `cohort_id` | nullable string | may be blank | required | Stable project ID for the actual participant group, `cohort:<citation-key>:<cohort-key>`, where citation key identifies the issue-approved source-defining study rather than whichever paper is being ingested. A project ID is assigned only after review decides which rows share participants; every publication reusing them uses the same ID. | Giving every row a singleton cohort to evade duplicate detection, using each current paper as a new cohort, using one paper as the cohort when it reports several, or merging cohorts merely because labels match. |
| `assay` | nullable string | may be blank | required | Source-reported measurement technology or an approved controlled mapping, such as `targeted genotyping`; field evidence contains the literal method text and locator. | `genotyping`, `sequencing`, or another modal assay guessed from the era, journal, or variant. |
| `sampling_design` | nullable enum | may be blank | required | Exactly one P1 value: `population_random`, `healthy_reference`, `clinical_case`, `clinical_control`, `newborn_screening`, `carrier_screening`, or `convenience`. A source phrase maps through reviewed controlled-vocabulary evidence. | Choosing `convenience` as a conservative catch-all, inferring random sampling from a country label, or treating “controls” as healthy without recruitment evidence. |
| `disease_ascertainment_excluded` | nullable boolean | may be blank | required | Lowercase TSV boolean `true` or `false`. `true` means the design excluded or depleted disease-associated participants; it does not mean the source simply omitted disease discussion. | Blank coerced to `false`, “healthy” inferred from silence, or numeric/string surrogates such as `0`, `1`, `yes`, or `no`. |
| `date_lower` | nullable integer | may be blank | required | Inclusive younger bound in integer years before present, using P1's time convention; modern is `0` only with evidence that the sampled people are contemporary. | Publication year converted to sample date, negative years, decimal years, or `0` as a missing-value default. |
| `date_upper` | nullable integer | may be blank | required | Inclusive older bound in integer years before present, with `date_lower <= date_upper`; it uses the same source statement and conversion as `date_lower`. | Reversing bounds, widening an interval without evidence, or copying `date_lower` merely to obtain a point date. |

No latitude, longitude, population ID, or radius belongs in this table. Those values come only from
the single P0 row resolved from `population_label`; §5.4 defines the equality check.

#### 5.2.3 Count columns

| column | type | staging value | promotion value | exact meaning and format | reject or refuse |
|---|---|---|---|---|---|
| `an` | nullable positive integer | may be blank | required | Total number of called allele copies eligible for this measurement, as a base-10 integer with no commas or decimal point. It is chromosomes/copies, not automatically participants. | `2 × N` when missing genotypes are possible, number enrolled rather than successfully assayed, or an interval/estimate. |
| `ac_lower` | nullable non-negative integer | may be blank | required and equal to `ac_upper` | Inclusive lower bound on copies of `counted_allele`, base-10 integer. Exact reported/derived counts use the same value in both bounds. | Rounded `frequency × an`, prevalence percent treated as a count, or a lower confidence limit. |
| `ac_upper` | nullable non-negative integer | may be blank | required and equal to `ac_lower` | Inclusive upper bound on copies of `counted_allele`, base-10 integer, satisfying `ac_upper <= an`. | Rounded `frequency × an`, a confidence limit, or a value supplied only to make an interval exact. |
| `reported_frequency` | nullable string | may be blank | optional | Exact printed token, including decimal precision, percent sign, inequality, or range; for example `0.16`, `16%`, or `<0.01`. It is audit evidence, has a field-evidence row, and is never the P1 likelihood input. | Recalculated frequency, normalized decimal spelling, float parsing followed by reserialization, or a value absent from the source. |
| `count_basis` | nullable enum | may be blank | required and not `frequency_reconstructed` | `reported` when integer counts are explicit; `genotype_derived` when exact genotype counts deterministically yield allele counts; `frequency_reconstructed` when only frequency and denominator imply a count or interval. | Labelling rounded `frequency × an` as reported or genotype-derived because the product happens to be an integer. |
| `denominator_basis` | nullable enum | may be blank | required | `reported_alleles` for an explicit allele-copy denominator; `diploid_individuals` only for reviewed `2N` conversion with complete autosomal calls; `hemizygous_males` only for one X-linked copy per assayed male. | Assuming diploidy, ignoring no-calls, applying `2N` to male X-linked data, or mixing people and allele copies. |

If either count bound is present, both bounds and `an` must be present and satisfy
`0 <= ac_lower <= ac_upper <= an`. Only `ac_lower == ac_upper` promotes. An interval remains useful
staging evidence but the adapter never selects its midpoint, endpoint, or rounded expectation.

#### 5.2.4 Citation and immutable record-anchor columns

| column | type | staging value | promotion value | exact meaning and format | reject or refuse |
|---|---|---|---|---|---|
| `citation_id` | nullable string | may be blank | required | Persistent ID of the **original study owning the measurement**: `pmid:<digits>`, lowercase `doi:<doi>`, or `thesis:<stable-repository-id>`. Its field-evidence row states where that attribution appears. | A search-result URL, author-year alone, title alone, fabricated PMID/DOI, or the compilation ID when the original study is known. |
| `citation_text` | nullable string | may be blank | required | Full human-readable citation for `citation_id`, sufficient to identify authors, title, venue/repository, and year. Its field-evidence row preserves the compilation's literal citation text when applicable. | An LLM-generated citation not checked against the persistent ID, `et al.` alone, or a title fragment. |
| `record_source_id` | string | required | required | Immutable persistent ID of the source record from which this evidence row was first staged. A paper uses `pmid:`, `doi:`, or `thesis:`; a repository dataset uses `repo:github.com/<owner>/<repo>@<40-hex-commit>:<path>`. It never changes when later field curation inspects another source. | A moving branch such as `main`, search-result/session URL, source inferred after import, or replacing the anchor during later verification. |
| `record_locator` | string | required | required | Immutable exact measurement-record location inside `record_source_id`, using the locator grammar above. If a row contains several measurements, it includes the exact cell/column as well as row. | `the paper`, `results`, `supplement`, a PDF URL without page/table/row, a local dataframe row, or changing the locator after first staging. |
| `record_source_url` | nullable string | may be blank | optional | Stable absolute `https://` landing-page or full-text URL for `record_source_id`; persistent IDs remain authoritative when URLs move. | Search-result, session, signed, localhost, or temporary download URLs. |

The record anchor identifies the immutable imported row; it is not a claim that every scientific
field was verified there. Each §5.3 field-evidence row separately identifies the exact document and
location supporting that field. A compilation row therefore remains stably anchored to the
compilation even if later curation checks some or all values against the original paper.

#### 5.2.5 Extraction and independent-verification columns

| column | type | staging value | promotion value | exact meaning and format | reject or refuse |
|---|---|---|---|---|---|
| `verification_status` | enum | required but recomputed | must be verified | `pending` unless every required field is resolved and independent verifier metadata is present. Then compute `original_source_verified` when every required scientific field named below was checked at `citation_id`; otherwise compute `compilation_verified`. | A caller-chosen status, an extractor certifying its own row, a citation lookup treated as measurement verification, or original-source status while a required scientific field relies only on a compilation. |
| `extraction_method` | enum | required | required | `manual_transcription` = person transcribed inspected content; `structured_table` = deterministic import from machine-readable content; `ocr_reviewed` = extractor checked OCR against its image; `automated_proposal` = LLM/OCR/model output not checked by its extractor. This origin value never changes during later review. | Calling LLM extraction manual, calling unreviewed OCR structured, or changing the method after review to conceal automation. |
| `extracted_by` | string | required | required | Auditable identity `human:<github-user>`, `agent:<system>:<run-or-pr-id>`, or `import:<script>@<git-commit>`. | `agent`, `AI`, `unknown`, a fictional person, or an identity changed after review. |
| `extracted_at` | UTC timestamp | required | required | RFC 3339 UTC `YYYY-MM-DDTHH:MM:SSZ`, recording when this version of the extraction was made. | Local time without offset, date only, future time, or source publication time. |
| `verified_by` | nullable string | may be blank | required when status is verified | Independent reviewer using the same identity grammar as `extracted_by`; it must differ from `extracted_by`. Blank for `pending`. | The extractor under another spelling, an invented reviewer, or any value on an automated pending row. |
| `verified_at` | nullable UTC timestamp | may be blank | required when status is verified | RFC 3339 UTC time of independent source comparison; blank for `pending`. | Extraction time copied automatically, date only, future time, or any value without an actual review. |
| `verification_reference` | nullable string | may be blank | required when status is verified | Stable GitHub review URL or immutable curation-manifest record documenting what the reviewer checked; blank for `pending`. | A branch name, chat statement, mutable local path, `looks good`, or a link that does not identify the reviewed record. |

Migration and extraction tools always create `automated_proposal` rows as `pending` with blank
verifier fields and expose no self-certification option. A separate reviewer may publish a new
immutable evidence version after checking every stated source location; that version retains
`extraction_method=automated_proposal`, adds independent verifier metadata, and receives the
recomputed verification status. Extractor and reviewer separation is enforced in data and remains
visible in Git history.

For verification classification, the required scientific fields are `variant_id`,
`counted_allele`, `population_label`, `cohort_id`, `an`, `ac_lower`, `ac_upper`, `count_basis`,
`denominator_basis`, `assay`, `sampling_design`, `disease_ascertainment_excluded`, `date_lower`, and
`date_upper`, plus `sample_id` when conditionally required. `citation_id` and `citation_text` remain
promotion-required but may use `persistent_citation_resolution`; consulting a bibliographic
authority does not turn otherwise original-source measurement verification into compilation-only
verification.

#### 5.2.6 Reuse, notes, and version columns

| column | type | staging value | promotion value | exact meaning and format | reject or refuse |
|---|---|---|---|---|---|
| `reuse_status` | enum | required but recomputed | must be admissible | Computed over `record_source_id` plus every non-null §5.3 `evidence_source_id`: `explicitly_open`, `permission_granted`, `no_restriction_found`, `restricted`, or `not_checked`. The first three are admissible; the last two refuse promotion. | A caller-chosen status, treating absence of a licence as restricted, or marking no restriction while any contributing source is unchecked. |
| `reuse_evidence` | nullable canonical JSON string | may be blank | complete source coverage required | Object `{"checks":[...]}` with one source-specific check per contributing source. Every check has `source_id`, `checked_at`, and a finding-specific URL/reference structure defined below. Partial checks are valid staging evidence and compute `not_checked`. | Only `no license`, an LLM's terms summary, duplicate source checks, a finding without checked surfaces, malformed/non-canonical JSON, or checks for unrelated sources. |
| `reuse_checked_at` | nullable date | blank only when there are no checks | required | UTC `YYYY-MM-DD`, exactly the latest `checked_at` among `reuse_evidence.checks`; it is recomputed, not supplied independently. | Publication/extraction date, a date inconsistent with the checks, partial dates, or future dates. |
| `notes` | nullable string | may be blank | optional | Source-specific caveat that does not fit a structured field. It may explain uncertainty but cannot supply a required value. | `N/A`, duplicated required fields, hidden transformations, or instructions to ignore a refusal. |
| `ingest_version` | string | required | required | Immutable corpus release `<corpus_id>@YYYY-MM-DD.<revision>`, for example `lct-rs4988235@2026-09-05.1`; corrections publish a new version without changing stable record IDs. | `latest`, branch names, mutable file names, timestamps that change on every run, or overwriting a prior release. |

Under the owner's policy, a completed check that finds no explicit restriction is not a licensing
block and does not limit use to particular downstream users. This is recorded as
`no_restriction_found`, not `explicitly_open`: the former states what was checked and found, while
the latter asserts a named licence or public-domain statement.

Each object in `reuse_evidence.checks` has exactly one of these shapes; extra keys are rejected.
Checks are sorted by `source_id`, and every `surfaces` array is unique and lexicographically sorted:

```json
{"checked_at":"2026-09-05","finding":"explicitly_open","licence":"CC0-1.0","source_id":"doi:10.0000/example","terms_url":"https://example.org/terms"}
{"checked_at":"2026-09-05","finding":"permission_granted","permission_reference":"https://example.org/permission-record","scope":"public redistribution and downstream reuse","source_id":"doi:10.0000/example"}
{"checked_at":"2026-09-05","finding":"no_restriction_found","source_id":"doi:10.0000/example","surfaces":["https://example.org/article","https://example.org/supplement"]}
{"checked_at":"2026-09-05","finding":"restricted","restriction":"non-commercial reuse only","source_id":"doi:10.0000/example","terms_url":"https://example.org/terms"}
```

The examples use synthetic identifiers and URLs; production values must resolve. Status is computed
in this order: any restriction that prohibits public redistribution/downstream reuse yields
`restricted`; otherwise any missing source check yields `not_checked`; otherwise any qualifying
permission yields `permission_granted`; otherwise all-open yields `explicitly_open`; otherwise at
least one checked-and-unstated source yields `no_restriction_found`. Permission is admissible only
when its recorded scope covers public redistribution and downstream reuse, not merely this project.

### 5.3 `literature_field_evidence`

This companion table answers “why is this exact cell allowed to contain that value?” It has exactly
19 rows per `source_record_id`: one for each of `variant_id`, `rsid`, `counted_allele`,
`population_label`, `sample_id`, `cohort_id`, `an`, `ac_lower`, `ac_upper`, `reported_frequency`,
`count_basis`, `denominator_basis`, `citation_id`, `citation_text`, `assay`, `sampling_design`,
`disease_ascertainment_excluded`, `date_lower`, and `date_upper`. `source_locator` is not in this
list because it is itself the pointer used by these rows; requiring evidence for an evidence pointer
would be recursive.

Sixteen fields are always promotion-required. `sample_id` is conditional under §5.2.2. `rsid` and
`reported_frequency` are optional. An unresolved conditional or optional field does not by itself
block promotion, but `sample_id` becomes an error when multiple otherwise-identical measurements
need it for disambiguation.

Every column below is physically required in the field-evidence TSV. Its canonical header has the
ten names below in exactly this order:

| column | type | exact requirement | accepted example | reject |
|---|---|---|---|---|
| `source_record_id` | string | Must exactly match one loader-generated `literature_evidence.source_record_id`; every source record has exactly 19 field rows. | `literature:lct-rs4988235:7220defbe35cb5adbb8ee065f2d2460e03079f6d6cfacbc130477ca655543568` | Orphans, missing field rows, a local row index, or more than one row for the same field. |
| `field_name` | enum | Exactly one of the 19 closed names above, once per source record. | `sampling_design` | Spelling variants, arbitrary new fields, or duplicates. |
| `evidence_status` | enum | Exactly `reported`, `derived`, `not_reported`, `ambiguous`, or `not_reviewed`, with the conditional rules below. | `not_reported` | Generic `unresolved`, `verified`, `inferred`, confidence scores, or blank. |
| `raw_value` | nullable string | Exact source token/quote for `reported` and `ambiguous`; exact derivation input for `derived`, using canonical JSON when multi-valued. Blank for `not_reported` and `not_reviewed`. A placeholder-like token is allowed only for `ambiguous` when it is the literal source text. | `{"AA":"10","AG":"20","GG":"70"}` | Paraphrased values, normalized/reformatted source text, unnamed comma lists, agent-supplied placeholders, or values in absent/unreviewed states. |
| `evidence_source_id` | nullable string | Persistent inspected document ID for every status except `not_reviewed`, where it is blank. | `repo:github.com/example/example@0000000000000000000000000000000000000000:data.tsv` (synthetic fixture only) | Generated citation, moving branch, omitted compilation identity, or a value for `not_reviewed`. |
| `source_locator` | nullable string | Required exact value location for `reported`, `derived`, and `ambiguous`. Blank for `not_reported` and `not_reviewed`. | `dataset-record:row-17,column-frequency` | `the paper`, URL alone, guessed location, a value for not-reviewed, or one value location pretending to prove absence. |
| `checked_scope` | nullable canonical JSON array | Required only for `not_reported`: non-empty, unique, sorted structured locators covering every section actually checked. Blank for all other statuses. | `["page:methods-3-5","supplement:S3-methods"]` | `everywhere`, an unsorted/duplicate list, unchecked sections, or a scope on reported/derived/ambiguous/not-reviewed evidence. |
| `derivation_method` | nullable enum | Required only for `derived`; exactly one allowlisted method below. Blank for every other status. | `allele_count_from_genotypes` | Free-text formulas, method chains, `manual`, `LLM`, or a method on a non-derived row. |
| `decision_reference` | nullable string | Required for `derived`: absolute GitHub issue/PR URL approving the method or mapping. Optional for `reported`/`ambiguous`; blank for `not_reported`/`not_reviewed`. | `https://github.com/bschilder/genomeOS/issues/149` | Branch names, chat links, mutable local paths, or approval invented by the extractor. |
| `notes` | nullable string | Required for `not_reported`, `ambiguous`, and `not_reviewed`; must state what was checked, what conflicts, or why review has not happened. Optional for `reported`/`derived`. | `Recruitment design is absent from the checked Methods and Supplement S3 sections.` | `unknown`, `N/A`, bare `not reported`, or instructions to bypass promotion. |

The three statuses impose these cross-table rules:

| status | main evidence cell | raw value | evidence source | value locator | checked scope | method | promotion effect |
|---|---|---|---|---|---|---|---|
| `reported` | non-null and equal to typed literal | required | required | required | blank | blank | eligible if every other gate passes |
| `derived` | non-null and exactly recomputable | required | required | required | blank | required | eligible if every other gate passes |
| `not_reported` | blank | blank | required | blank | required | blank | refuses required field; documents genuine source absence |
| `ambiguous` | blank | required | required | required | blank | blank | refuses required field; preserves conflicting/vague source text |
| `not_reviewed` | blank | blank | blank | blank | blank | blank | refuses required field; identifies unfinished curation |

The initial derivation allowlist is closed:

| method | allowed output fields | required raw input | exact operation |
|---|---|---|---|
| `variant_normalization` | `variant_id`, `rsid`, `counted_allele` | canonical JSON naming printed variant/build/strand/alleles and reference resource version | Deterministic identifier resolution, liftover, and minimal normalization against the named GRCh38 reference; ambiguity refuses. |
| `persistent_citation_resolution` | `citation_id`, `citation_text` | canonical JSON containing the literal cited reference plus the matched PubMed/Crossref/repository record and retrieval version | Emit a persistent ID and full citation only for one exact match; zero or multiple plausible matches remain unresolved. |
| `alternate_count_from_reference_count` | `ac_lower`, `ac_upper` | JSON integers `an` and `reference_ac` | Compute `an - reference_ac`; counted-allele normalization must independently verify the ALT allele. |
| `allele_count_from_genotypes` | `ac_lower`, `ac_upper` | JSON genotype counts with allele labels | Sum exact called allele copies; no Hardy-Weinberg reconstruction or missing-genotype imputation. |
| `allele_denominator_from_complete_diploid_sample` | `an` | JSON integer `called_individuals` plus explicit complete-call and autosomal evidence | Compute `2 * called_individuals`. Enrolled or attempted samples are not called individuals. |
| `allele_denominator_from_hemizygous_males` | `an` | JSON integer `called_males` plus explicit X-linked male evidence | Compute `called_males`; mixed-sex samples require genotype-level accounting. |
| `counts_from_explicit_integer_fraction` | `an`, `ac_lower`, `ac_upper` | A source token explicitly printed as integer `numerator/denominator` | Parse the two integers exactly. Decimal or percent frequencies are excluded even when multiplication yields an integer. |
| `controlled_vocabulary_mapping` | `cohort_id`, `count_basis`, `denominator_basis`, `assay`, `sampling_design`, `disease_ascertainment_excluded` | Literal source quote/identifier and a versioned mapping key | Apply only an issue-approved exact mapping; no nearest category or semantic guess. |
| `modern_sample_to_zero_bp` | `date_lower`, `date_upper` | Literal evidence that sampled participants were contemporary/living | Emit `0`; publication year or silence alone is insufficient. |

One derivation row invokes one method. If producing a final value would require an unlisted chain,
the field remains unresolved until a new method with one deterministic implementation, tests, and
an approved design decision is added. A reviewer cannot approve a free-text calculation into the
allowlist through a data cell.

`population_label`, `sample_id`, and `reported_frequency` are never derived: they are either
transcribed exactly with `evidence_status=reported` or use one of the three explicit non-value
states.

The schemas reject placeholder strings such as empty text, `unknown`, `n/a`, `not reported`,
`none`, and `tbd` wherever evidence is claimed as reported or derived. `ambiguous.raw_value` may
preserve such a token only as literal, located source text; the normalized main-table cell remains
blank. Coverage reports may aggregate `not_reported`, `ambiguous`, and `not_reviewed` as unresolved,
but the stored status never collapses those states.

The adapter computes verification status and eligibility from the two evidence tables. There is no
`eligible`, `verified`, or `force` argument that a caller or agent can set to bypass the checks.
Automated discovery and migration scripts always emit `pending` verification and may not expose a
command-line option to self-certify their output.

### 5.4 P1 linkage

`OBSERVATIONS_SCHEMA` gains required non-empty `source_record_id`. Every adapter must construct it
from stable source identifiers; row positions in a local dataframe are not stable IDs. Literature
uses the project-assigned, source-anchored format in §5.2.1.

The combined observation build rejects duplicate `source_record_id` values. A publication
evidence build also rejects duplicate `(variant_id, population_id, cohort_id, sample_id)` rows,
because publishing the same cohort twice would give it twice the statistical weight.

The evidence ledger is not joined onto P2 inputs. Audit consumers join it to observations through
`source_record_id` only when provenance is requested.

Publication evidence never supplies `lat`, `lon`, or `radius_km` to P1. The adapter must copy all
three from the single P0 row resolved through the source alias, then assert equality after building
the observation. Adding a literature population is separate P0 work. Its radius must have source
provenance and a reviewed source-specific derivation; the publications adapter cannot create a
registry row, accept a caller-provided radius, or fall back to a nearby population.

### 5.5 Canonical formatting examples

Implementation adds `docs/literature-evidence-curation.md` plus checked-in TSV examples under
`tests/fixtures/literature/`. The files, not copied snippets in prompts, are the canonical agent
template. They contain all columns in schema order and are loaded by tests, so a schema change
cannot silently leave the instructions stale.

The positive examples cover three distinct outcomes:

1. `promotable/` contains one wholly synthetic, clearly labelled record with exact counts and one
   field-evidence row for every evidence-tracked field. It validates and promotes through a synthetic P0
   registry entry.
2. `non_promotable/` contains separate valid staging records for `not_reported`, `ambiguous`, and
   `not_reviewed`. They demonstrate the different raw-value, evidence-source, locator,
   `checked_scope`, and note requirements and all refuse promotion.
3. `derived/` contains one example for every allowlisted transformation. Each example includes the
   literal raw value, structured locator, derivation method, and decision reference, and tests
   recompute the output.

The guide shows these exact field-level patterns (values below are illustrative, not scientific
records):

| situation | value in `literature_evidence` | matching `literature_field_evidence` |
|---|---|---|
| source reports denominator | `an=200` | `an`, `reported`, `raw_value="200 chromosomes"`, exact `evidence_source_id`, and `source_locator="supplement:table-S3,row-17"` |
| checked source omits sampling design | `sampling_design=<empty TSV cell>` | `sampling_design`, `not_reported`, empty raw value/locator, exact evidence source, checked locator array, and a specific note |
| sampling design has not been reviewed | `sampling_design=<empty TSV cell>` | `sampling_design`, `not_reviewed`, empty raw value/evidence source/locator/scope, and a note explaining why review is pending |
| deterministic genotype count | `ac_lower=40`, `ac_upper=40` | `ac_lower` and `ac_upper`, `derived`, canonical JSON genotype counts, exact evidence source/locator, `derivation_method="allele_count_from_genotypes"`, and an issue/PR decision reference |
| terms checked but unstated | computed `reuse_status="no_restriction_found"`; `reuse_evidence` has a source-specific check with `finding="no_restriction_found"` and every inspected surface | `reuse_checked_at` equals the latest check date; it does not say only `"no license"` |

An `invalid/` directory contains one minimal fixture per prohibited shortcut and a manifest naming
the expected validation error or refusal. At minimum it demonstrates:

| do not provide | provide instead |
|---|---|
| `radius_km=500` because a country is large | no radius column in literature evidence; resolve an exact P0 entry or refuse |
| `sampling_design="convenience"` because recruitment is unclear | an empty TSV cell plus `ambiguous` with the literal source wording and exact locator, or `not_reported`/`not_reviewed` as applicable |
| `ac=round(0.16 * 201)` | preserve `reported_frequency="0.16"`, count interval unresolved, and refuse exact-count promotion |
| `source_locator="the paper"` or `"supplement"` | a structured locator such as `supplement:table-S3,row-17` |
| `verification_status="original_source_verified"` after an LLM extraction | `pending` with null verifier fields until a separate reviewer checks the cited location and records the review |
| coordinates copied from a gazetteer or nearby population | a separately reviewed P0 registry record and exact alias join |
| caller sets `reuse_status="no_restriction_found"`, `reuse_evidence="no license"` | source-specific canonical JSON checks; let the validator compute status and latest check date |
| one row duplicated across several countries | one defensible registered regional population, or a refusal |

The guide includes the exact build command, file encoding, delimiter, null representation, date
format, boolean spelling, enum vocabulary, ID construction rules, and disposition/coverage output
expected after validation. It explicitly instructs agents to copy the example directory and replace
values only with directly inspectable evidence; changing a value solely to make a test pass is a
data-integrity failure.

## 6. rs4988235 lactase-persistence pilot policy

The external pilot contains 426 rows from 88 country strings. Its current audit identifies 116
frequency-reconstructed rows, 34 `small_n` rows, eight thesis rows without PMIDs, and eight
corrected no-call denominators. It is primarily a structured extraction from Liebert et al. 2017
Supplementary Table 3, with original citations attached; ten rows carry an upstream flag that an
original paper was checked. The audit does not equate that flag with this contract's
`original_source_verified` status unless every required scientific field satisfies §5.3.

The repository will not label the corpus “complete.” It has two levels:

- `original_source_verified`: every required scientific field was independently checked at the
  original paper/table;
- `compilation_verified`: every required field was independently checked, but at least one
  required scientific field still relies on the accessible compilation rather than the original.

Both may enter P1 only when the count interval is exact and all other refusal conditions pass.
`pending` never enters P1. `small_n` is not itself a refusal: the denominator belongs in the
likelihood, so a small exact measurement is weak evidence rather than invalid evidence.

The current external CSV is a curation input, not yet a `literature_evidence` table: it does not
contain uncertainty radii, sampling designs, cohort/sample identities, original-study field
locators, or verification state for each row. The first migration tool therefore inventories all
426 rows, pins the repository commit, creates a stable `dataset-record:` locator for each imported
CSV row, and reports what still requires curation. It does not manufacture the missing scientific
fields or emit P1 observations. Once a reviewed evidence table exists, the publications adapter
emits only eligible exact rows. It never coerces country strings into ISO3 identifiers. Labels such
as `Angola, Namibia Botswana` require an explicit regional P0 entry with a defensible uncertainty
radius or are refused.

The complete pilot CSV may be copied into the staging area with its exact upstream URL and commit
hash. Its upstream repository exposes no explicit reuse restriction, so it records
`reuse_status=no_restriction_found` under the owner's policy. That status permits staging and
eventual promotion and does not by itself limit reuse to particular downstream users, but it does
not waive the scientific metadata checks above. A small synthetic fixture still exercises every
adapter path without making the full corpus part of the unit suite.

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
- `required_field_unresolved`
- `field_evidence_missing`
- `reuse_not_checked`
- `reuse_restricted`

An entirely unmapped ordinary population label raises `UnmappedPopulationError`, matching the
existing P0/P1 invariant. The regional refusal exists only for labels that explicitly span several
countries and cannot honestly be represented as one registered locality.

Duplicate identifiers, inconsistent count intervals, contradictory aliases, and duplicate
cohort/sample measurements raise rather than enter a refusal report; they make the dataset
internally ambiguous and must be corrected at source.

Promotion emits a machine-readable coverage report with one row per evidence-tracked field: total
records, reported, derived, not reported, ambiguous, not reviewed, promoted, and refused. It also
reports the aggregate unresolved count as the sum of the three non-value states. The totals must
reconcile. A PR that reduces unresolved counts must show which source records changed and the
evidence rows that justified each change; a shrinking refusal count alone is not success.

## 9. Agent safeguards

`AGENTS.md` gains a “No invented completeness” invariant applying to every data source, not only
publications:

- missing is a valid scientific state; preserve it and refuse promotion;
- never invent, estimate, borrow, interpolate, or choose a “conservative” value for a required
  field merely to satisfy a schema or increase retention;
- every derived required field must cite the raw source value and locator and use a named,
  deterministic, tested transformation approved by the issue/spec;
- an agent may create `pending`, `not_reviewed`, `not_reported`, or `ambiguous` evidence but may not
  mark its own extraction verified, conflate those three field states, or convert one to
  reported/derived without directly inspectable source evidence;
- an LLM summary, generated citation, inferred geographic centroid, or another dataset's value is
  not source evidence for the publication being curated;
- do not add `force`, fallback, permissive mode, or config switches around scientific refusals;
- every data PR reports input, promoted, refused-by-reason, and per-field counts for not reported,
  ambiguous, and not reviewed, and explains every reduction in refusals.

The same section states the reuse rule operationally: check and record the applicable source
surfaces before promotion; an explicit restriction is enforced, `not_checked` is refused, and a
completed check finding no explicit restriction is accepted with attribution. The absence of a
named licence alone is not a blocker.

`AGENTS.md` links directly to the canonical curation guide and includes a compact “right / wrong”
example for missing radius, ascertainment, exact counts, verification, source locators, and reuse
evidence. It warns that examples are contracts, not suggestions: new ingestion work copies the
checked fixture layout and must not replace empty cells merely to obtain a green build.

The deliberate-behaviours table adds that a row remaining in staging is not a failed ingest; it is
the correct result when publication evidence is incomplete. The repository layout section names
the evidence schemas so future agents discover the staging/promotion boundary before editing P1.

## 10. Testing and review evidence

Tests follow red-green-refactor and cover:

- the literature TSV header contains every documented column exactly once and rejects missing,
  extra, duplicated, or reordered columns;
- empty TSV cells round-trip as null while placeholder strings, implicit boolean spellings,
  malformed timestamps/dates, moving repository references, and unstable IDs fail validation;
- source record IDs equal the documented digest of their immutable record source and locator;
- stored normalization status equals the result recomputed from variant/allele field evidence;
- evidence schemas accept each explicit non-value state while P1 continues to reject required
  fields in all three states;
- every source record has exactly the 19 evidence-tracked field rows, including unresolved optional
  fields, and no others;
- deleting each always-required promotion value produces a structured refusal, never a substituted
  value; conditional and optional fields follow only their documented rules;
- every field-evidence status enforces its exact raw value, evidence source, value locator,
  checked-scope, method, decision-reference, and notes matrix;
- `population_label`, `sample_id`, and `reported_frequency` reject derived status;
- placeholder strings cannot satisfy a reported/derived field or source locator;
- every allowlisted derivation is recomputed and compared with the stored value;
- a decimal/percent frequency cannot use `counts_from_explicit_integer_fraction`, and rounded
  `frequency * an` never becomes an exact count;
- automated tools cannot initially emit verified rows or accept a self-certification option;
  independently reviewed automated proposals retain their extraction method and receive only the
  recomputed status;
- a verified row requires an independently named reviewer, timestamp, and stable review reference;
  rows with unresolved required fields remain pending, pending rows cannot carry verifier
  metadata, and extractor and verifier cannot be the same;
- original verification requires every required scientific field's `evidence_source_id` to equal
  `citation_id`; compilation verification requires at least one distinct compilation source;
  unresolved original citations stage but do not promote;
- `not_checked` and `restricted` reuse states are refused, while a fully recorded
  `no_restriction_found` state with grammar-valid source coverage is accepted; stored reuse status
  and check date must equal recomputed values;
- every documented positive example validates, the promotable example emits exactly one P1 row,
  the unresolved example emits none, and every invalid example fails for its named reason;
- citation namespaces, count interval ordering, date ordering, and conditional search-decision
  rules are frozen into the contracts;
- the literal reported frequency survives CSV and Parquet round trips unchanged;
- an exact verified row maps through P0 and yields the expected P1 row;
- emitted latitude, longitude, and radius equal the resolved registry row exactly;
- the publications loader exposes no radius, ascertainment, eligibility, force, or fallback
  defaults;
- approximate, pending, ambiguous, and multi-country rows receive their stated refusal reason;
- an unmapped ordinary population raises;
- duplicate source IDs and duplicate cohort/sample measurements raise;
- all existing source adapters emit deterministic, non-empty source record IDs;
- the combined store rejects cross-source ID collisions;
- the PubMed parser preserves all returned PMIDs and starts each as `pending`;
- the rs4988235 fixture produces disposition and per-field coverage reports whose totals reconcile
  exactly.

The PR must report focused test commands and every mandatory repository gate. Because the schema
changes, `python scripts/freeze_contract.py` must regenerate and commit the contract diff.

## 11. Tracker changes

After this spec is approved:

1. Reopen #45 and comment that PR #91 explicitly advanced rather than closed it; the real parity
   acceptance run has not passed.
2. Comment on #7 and #8 with the foundations already delivered by PR #81 and checklists of their
   still-open definition-of-done items.
3. Close #117 as completed with the owner's decision that checked-and-absent terms are presumed
   reusable with attribution, while explicit restrictions are honored. Link PR #124 and keep #66
   separate because it governs publication of derived indigenous-population surfaces.
4. Rewrite #149 around this evidence-ledger design, correct the pilot claims and link, apply
   `type:data`, `P1:observations`, `skill:popgen`, `priority:medium`, and
   `wants-expert-review`, and keep it open until the implementation PR satisfies this spec.
5. File one HBB round-trip issue and one G6PD literature issue with the distinct acceptance targets
   in §7. Neither issue closes a golden test.

## 12. Documentation changes

The implementation updates the architecture source list in `docs/overview.md` to add publications
as a source class and explains that the ledger, not arbitrary paper parsing, is the reusable unit.
It updates `docs/scientific-engineering-objectives.md` so observation provenance and exact-count
refusal are acceptance evidence. It adds the schema-checked curation guide specified in §5.5 and
updates `AGENTS.md` with both no-invention and checked-terms rules. The module docstrings cite
design §6 and §7.1 and this spec.

No published scientific result, fitted surface, or burden artifact is added by this sub-project.
