# Literature Evidence Foundation — Design

**Status:** proposed, pending human review
**Date:** 2026-09-05
**Scope:** issue #149; the reusable publications evidence contract, deterministic P1 adapter,
rs4988235 lactase-persistence pilot integration path, and tracker repair. HBB and G6PD corpus work
are follow-on sub-projects with separate scientific acceptance evidence.

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
- `LITERATURE_FIELD_EVIDENCE_SCHEMA` records whether every promotion-critical field was reported,
  deterministically derived, or remains unresolved.
- `LITERATURE_SEARCHES_SCHEMA` validates reproducible discovery and screening records.
- `publications.load(...) -> tuple[pd.DataFrame, pd.DataFrame, IngestReport]` validates evidence and
  field evidence, computes eligibility, resolves population aliases through P0, returns P1
  observations plus the retained evidence rows, and reports scientific refusals.
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
  be detected rather than counted twice;
- an LLM or automated extractor may propose a value but may never mark its own extraction as
  verified; automated output enters the ledger as `pending` or `unresolved`;
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
- stable provenance linkage from P1 to source-native rows;
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
                     -- source-native measurement, missingness, provenance
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

One row per independently sampled population measurement:

| column | type | rule |
|---|---|---|
| `source_record_id` | string | globally unique, stable, source-native row identity |
| `corpus_id` | string | corpus owning the extraction |
| `variant_id` | nullable string | normalized GRCh38 `chr-pos-ref-alt`; null while unresolved |
| `rsid` | nullable string | source identifier when present |
| `counted_allele` | nullable string | literal allele whose copies `ac` represents |
| `normalization_status` | enum | `verified`, `ambiguous`, or `unresolved`; only verified enters P1 |
| `population_label` | string | verbatim label used by the source |
| `sample_id` | nullable string | sample within a study; distinguishes legitimate replicated samples |
| `cohort_id` | nullable string | contributing cohort across sites and publications |
| `an` | nullable positive integer | allele denominator supported by the source |
| `ac_lower`, `ac_upper` | nullable integers | admissible count interval when known |
| `reported_frequency` | nullable string | verbatim printed value, preserving decimals and symbols |
| `count_basis` | nullable enum | `reported`, `genotype_derived`, or `frequency_reconstructed` |
| `denominator_basis` | nullable enum | `reported_alleles`, `diploid_individuals`, or `hemizygous_males` |
| `citation_id` | string | namespaced persistent ID: `pmid:`, `doi:`, or `thesis:` |
| `citation_text` | string | human-readable citation |
| `source_locator` | nullable string | table, figure, page, supplement, and row; null while unresolved |
| `source_url` | nullable string | stable full-text or landing-page URL |
| `assay` | nullable string | what produced the measurement |
| `sampling_design` | nullable P1 enum | no default; null means unresolved, never `convenience` by fallback |
| `disease_ascertainment_excluded` | nullable boolean | null remains unresolved rather than coercing to false |
| `date_lower`, `date_upper` | nullable non-negative integers | years BP; lower <= upper when known |
| `verification_status` | enum | `original_source_verified`, `compilation_verified`, `pending` |
| `extraction_method` | enum | `manual_transcription`, `structured_table`, `ocr_reviewed`, or `automated_proposal` |
| `extracted_by` | string | named curator, import, or agent run that created the extraction |
| `extracted_at` | UTC timestamp string | when the extraction was created |
| `verified_by` | nullable string | independent reviewer identity; required for either verified status |
| `verified_at` | nullable UTC timestamp string | required for either verified status |
| `verification_reference` | nullable string | stable review record; required for either verified status |
| `reuse_status` | enum | `explicitly_open`, `permission_granted`, `no_restriction_found`, `restricted`, or `not_checked` |
| `reuse_evidence` | nullable string | terms URL, permission record, or where the absence-of-terms check was performed |
| `reuse_checked_at` | nullable date string | required unless `reuse_status=not_checked` |
| `notes` | nullable string | caveats; never substitutes for a structured field |
| `ingest_version` | string | immutable corpus version |

Nullability here is intentional and exists only in the evidence staging layer. Missingness must be
representable so an extractor has no reason to make up a value to satisfy a schema. The promotion
gate requires every P1 field; `OBSERVATIONS_SCHEMA` remains non-nullable and fail-closed.

`ac_lower == ac_upper` is required for P1 emission. The emitted `ac` is that shared integer.
Interval-valued rows remain useful evidence and remain visible in the refusal report, but the
existing binomial likelihood must not receive a fabricated point count. If one bound is present,
both bounds and `an` must be present and satisfy `0 <= ac_lower <= ac_upper <= an`.

`reported_frequency` is a string deliberately. A value printed as `0.16` does not carry the same
rounding interval as `0.1600`, and parsing both to binary float destroys the distinction needed to
audit reconstruction.

A verified row requires non-null `verified_by`, `verified_at`, and `verification_reference`, and
`verified_by` must differ from `extracted_by`. A pending row requires all three verification fields
to be null. This does not make reviewer identity cryptographically trustworthy; it makes the
required separation visible and testable in the record and pull-request history.

`reuse_status=no_restriction_found` is promotable under the owner's policy. `restricted` and
`not_checked` are not. `reuse_evidence` must describe the checked source surfaces; the bare phrase
“no license” is insufficient because it does not show that a check occurred.

The reuse fields record a search for restrictions rather than manufacture a legal conclusion:

- `explicitly_open` requires the named licence or public-domain statement and its URL;
- `permission_granted` requires a stable reference to the permission record;
- `no_restriction_found` requires `reuse_checked_at` and a concrete inventory such as “journal
  landing page, article footer, supplement landing page, and repository root checked; no reuse
  restriction stated”;
- `restricted` records the restriction and the operation it disallows;
- `not_checked` is the only state permitted without a completed terms check, and it cannot promote.

### 5.3 `literature_field_evidence`

One row for every promotion-critical field of every source record. The closed field list is
`variant_id`, `counted_allele`, `population_label`, `sample_id`, `cohort_id`, `an`, `ac_lower`,
`ac_upper`, `count_basis`, `denominator_basis`, `source_locator`, `assay`, `sampling_design`,
`disease_ascertainment_excluded`, `date_lower`, and `date_upper`.

| column | type | rule |
|---|---|---|
| `source_record_id` | string | foreign key to `literature_evidence` |
| `field_name` | enum | every field required to promote the row into P1 |
| `evidence_status` | enum | `reported`, `derived`, or `unresolved` |
| `raw_value` | nullable string | literal source value; required for reported and derived fields |
| `source_locator` | nullable string | exact source location; required for reported and derived fields |
| `derivation_method` | nullable enum | required only for derived fields; closed allowlist |
| `decision_reference` | nullable string | issue/PR recording an approved scientific adjudication |
| `notes` | nullable string | required when unresolved |

There must be exactly one row for each critical field. A present value paired with `unresolved`, or
a missing value paired with `reported`/`derived`, is a hard error. A derived value is accepted only
when its method is implemented as deterministic code that recomputes the stored value from
`raw_value`; free-text derivations cannot pass promotion. The initial allowlist is limited to
genotype-to-allele counting, ploidy conversion from explicitly documented sample composition, and
recovery from an explicitly printed integer fraction such as `40/200`. A decimal frequency, even
one with many digits, is never an exact-fraction derivation.

The schemas reject placeholder strings such as empty text, `unknown`, `n/a`, `not reported`,
`none`, and `tbd` wherever evidence is claimed as reported or derived. `source_locator` follows a
closed structured form (`table:`, `figure:`, `page:`, `supplement:`, or `dataset-record:` followed
by a non-placeholder identifier) so “the paper” or “the supplement” cannot masquerade as an exact
location. Unresolved fields use the explicit status and a non-placeholder reason instead.

The adapter computes eligibility from the two evidence tables. There is no `eligible`, `verified`,
or `force` argument that a caller or agent can set to bypass the checks. Automated discovery and
migration scripts always emit `pending` verification and may not expose a command-line option to
self-certify their output. `extraction_method=automated_proposal` is required to pair with
`verification_status=pending`.

### 5.4 P1 linkage

`OBSERVATIONS_SCHEMA` gains required non-empty `source_record_id`. Every adapter must construct it
from stable source-native identifiers; row positions in a local dataframe are not stable IDs.

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
   field-evidence row for every critical field. It validates and promotes through a synthetic P0
   registry entry.
2. `unresolved/` contains a valid staging record whose missing `sampling_design` is null in
   `literature_evidence`; the matching field-evidence row has `evidence_status=unresolved`, null
   `raw_value`, null `source_locator`, and a specific note. It validates as evidence and is refused
   by promotion.
3. `derived/` contains one example for every allowlisted transformation. Each example includes the
   literal raw value, structured locator, derivation method, and decision reference, and tests
   recompute the output.

The guide shows these exact field-level patterns (values below are illustrative, not scientific
records):

| situation | value in `literature_evidence` | matching `literature_field_evidence` |
|---|---|---|
| source reports denominator | `an=200` | `an`, `reported`, `raw_value="200 chromosomes"`, `source_locator="supplement:table-S3,row-17"` |
| source omits sampling design | `sampling_design=null` | `sampling_design`, `unresolved`, null raw value/locator, `notes="Recruitment method not stated in methods or supplement"` |
| deterministic genotype count | `ac_lower=40`, `ac_upper=40` | `ac_lower` and `ac_upper`, `derived`, literal genotype counts, exact locator, `derivation_method="genotype_to_allele_count"`, and an issue/PR decision reference |
| terms checked but unstated | `reuse_status="no_restriction_found"` | evidence row records the surfaces checked and `reuse_checked_at`; it does not say only `"no license"` |

An `invalid/` directory contains one minimal fixture per prohibited shortcut and a manifest naming
the expected validation error or refusal. At minimum it demonstrates:

| do not provide | provide instead |
|---|---|
| `radius_km=500` because a country is large | no radius column in literature evidence; resolve an exact P0 entry or refuse |
| `sampling_design="convenience"` because recruitment is unclear | null plus an `unresolved` field-evidence row |
| `ac=round(0.16 * 201)` | preserve `reported_frequency="0.16"`, count interval unresolved, and refuse exact-count promotion |
| `source_locator="the paper"` or `"supplement"` | a structured locator such as `supplement:table-S3,row-17` |
| `verification_status="original_source_verified"` after an LLM extraction | `pending` with null verifier fields until a separate reviewer checks the cited location and records the review |
| coordinates copied from a gazetteer or nearby population | a separately reviewed P0 registry record and exact alias join |
| `reuse_status="no_restriction_found"`, `reuse_evidence="no license"` | list the journal/repository surfaces actually checked and the check date |
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

Promotion emits a machine-readable coverage report with one row per critical field: total records,
reported, derived, unresolved, promoted, and refused. The totals must reconcile. A PR that reduces
unresolved counts must show which source records changed and the evidence rows that justified each
change; a shrinking refusal count alone is not success.

## 9. Agent safeguards

`AGENTS.md` gains a “No invented completeness” invariant applying to every data source, not only
publications:

- missing is a valid scientific state; preserve it and refuse promotion;
- never invent, estimate, borrow, interpolate, or choose a “conservative” value for a required
  field merely to satisfy a schema or increase retention;
- every derived required field must cite the raw source value and locator and use a named,
  deterministic, tested transformation approved by the issue/spec;
- an agent may create `pending` or `unresolved` evidence but may not mark its own extraction
  `original_source_verified` or `compilation_verified`, or convert an unresolved field to
  reported/derived without directly inspectable source evidence;
- an LLM summary, generated citation, inferred geographic centroid, or another dataset's value is
  not source evidence for the publication being curated;
- do not add `force`, fallback, permissive mode, or config switches around scientific refusals;
- every data PR reports input, promoted, refused-by-reason, and unresolved-by-field counts, and
  explains every reduction in refusals.

The same section states the reuse rule operationally: check and record the applicable source
surfaces before promotion; an explicit restriction is enforced, `not_checked` is refused, and a
completed check finding no explicit restriction is accepted with attribution. The absence of a
named licence alone is not a blocker.

`AGENTS.md` links directly to the canonical curation guide and includes a compact “right / wrong”
example for missing radius, ascertainment, exact counts, verification, source locators, and reuse
evidence. It warns that examples are contracts, not suggestions: new ingestion work copies the
checked fixture layout and must not replace nulls merely to obtain a green build.

The deliberate-behaviours table adds that a row remaining in staging is not a failed ingest; it is
the correct result when publication evidence is incomplete. The repository layout section names
the evidence schemas so future agents discover the staging/promotion boundary before editing P1.

## 10. Testing and review evidence

Tests follow red-green-refactor and cover:

- evidence and search schemas accept explicit unresolved fields while P1 continues to reject them;
- every promotion-critical field has exactly one matching field-evidence row;
- deleting each critical value produces a structured refusal, never a substituted value;
- changing a field-evidence status without the required raw value/locator fails validation;
- placeholder strings cannot satisfy a reported/derived field or source locator;
- every allowlisted derivation is recomputed and compared with the stored value;
- automated proposals cannot be marked verified;
- a verified row requires an independently named reviewer, timestamp, and stable review reference;
  a pending row cannot carry verifier metadata, and extractor and verifier cannot be the same;
- `not_checked` and `restricted` reuse states are refused, while a fully recorded
  `no_restriction_found` state is accepted;
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
