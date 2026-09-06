# Literature evidence curation contract

This is the operational guide for humans and agents preparing publication-derived allele-count
measurements for genomeOS. The normative design is
[`2026-09-05-literature-evidence-design.md`](superpowers/specs/2026-09-05-literature-evidence-design.md),
and the executable contracts are frozen in [`contract/`](../contract/). If this guide and the
schemas disagree, stop: update them together through a reviewed schema change.

## The non-negotiable distinction

One `literature_evidence` row is **one measurement of one allele in one independently sampled
population or sample stratum**. It is not one paper, one country, one table, or a summary assembled
across studies. Three populations in a paper produce three rows. Two independently recruited
samples of one population produce two rows with source-reported, distinct `sample_id` values.

Every header column is physically required. “Blank allowed” below means an empty TSV cell, parsed
as null. Never write `NA`, `N/A`, `unknown`, `none`, `null`, `-`, `TBD`, or `not reported` as a
surrogate null. Never put an inferred value in a cell merely to make a row complete. An unresolved
row is valid staging data; refusal to promote is a valid result.

Copy this exact 37-column header:

```text
source_record_id	corpus_id	variant_id	rsid	counted_allele	normalization_status	population_label	sample_id	cohort_id	assay	sampling_design	disease_ascertainment_excluded	date_lower	date_upper	an	ac_lower	ac_upper	reported_frequency	count_basis	denominator_basis	citation_id	citation_text	record_source_id	record_locator	record_source_url	verification_status	extraction_method	extracted_by	extracted_at	verified_by	verified_at	verification_reference	reuse_status	reuse_evidence	reuse_checked_at	notes	ingest_version
```

The canonical, schema-tested files are the safest templates:

- [fully promotable evidence](../tests/fixtures/literature/promotable/evidence.tsv) and its
  [19 field decisions](../tests/fixtures/literature/promotable/field_evidence.tsv);
- [valid but non-promotable evidence](../tests/fixtures/literature/non_promotable/evidence.tsv) and
  its [unresolved field decisions](../tests/fixtures/literature/non_promotable/field_evidence.tsv);
- [all allowed derivations](../tests/fixtures/literature/derived/evidence.tsv) and their
  [derivation evidence](../tests/fixtures/literature/derived/field_evidence.tsv);
- [named prohibited mutations](../tests/fixtures/literature/invalid/cases.json).

## Main evidence columns, exactly

In the tables below, **staging value** says whether the TSV cell may be blank. **Promotion** says
what must be true before the row can become a P1 observation. **Field row** says whether the
companion table must contain one of its 19 decisions for this field. Every main row always has
exactly 19 companion rows, including for nullable and optional fields.

### Identity and normalized allele

| Column | Staging value | Exact accepted representation | Promotion rule | Field row | Correct example | Prohibited example | Why prohibited |
|---|---|---|---|---|---|---|---|
| `source_record_id` | Required; loader-generated | `literature:<corpus_id>:<64 lowercase hex>`, exactly `sha256(record_source_id + "\n" + record_locator)` | Must be unique and recompute exactly | No | `literature:lct-rs4988235:f5fd55995c17abf484c03ca85bb786b2710ab49556baad33ad8e1099caa53afe` | `row-17`, a dataframe index, UUID, or hand-edited hash | Local positions change when files are reordered; random IDs cannot be regenerated or audited |
| `corpus_id` | Required | Lowercase hyphenated slug matching `^[a-z0-9]+(?:-[a-z0-9]+)*$` | Must match the namespaces in `source_record_id` and `ingest_version` | No | `lct-rs4988235` | `LCT pilot`, `lct_rs4988235` | A stable namespace is needed to prevent cross-corpus ID collisions |
| `variant_id` | Blank allowed | One normalized GRCh38 `chr-pos-ref-alt`; uppercase DNA alleles | Required and field status must be `reported` or allowlisted `derived` | Yes | `chr2-135851076-G-A` | GRCh37 coordinates, `LCT`, `rs4988235`, or a guessed nearby variant | P1 is keyed by one normalized allele; a gene or ambiguous build can join the wrong locus |
| `rsid` | Blank allowed | Lowercase `rs` followed by a positive integer | Optional, but its field row is always required | Yes | `rs4988235` | `RS4988235`, `4988235`, `rs4988235/rs182549` | Formatting aliases and multi-ID cells make identity ambiguous |
| `counted_allele` | Blank allowed | Uppercase literal DNA allele whose copies are counted by `ac_lower/ac_upper` | Required; must equal the ALT component of `variant_id` | Yes | `A` for `chr2-135851076-G-A` | `risk`, `derived`, a strand complement, or `G` for that variant | A correctly copied count on the wrong allele reverses the frequency |
| `normalization_status` | Required; recomputed | Exactly `verified`, `ambiguous`, or `unresolved` | Must recompute to `verified`; callers cannot choose it | No | `verified` after variant and counted-allele evidence resolve uniquely | `verified` because the rsID looks familiar | Self-certification hides build, strand, REF/ALT, and multiallelic errors |

### Sample, assay, ascertainment, and date

| Column | Staging value | Exact accepted representation | Promotion rule | Field row | Correct example | Prohibited example | Why prohibited |
|---|---|---|---|---|---|---|---|
| `population_label` | Required | Verbatim label used by the inspected source, with no spelling cleanup | Required; must resolve exactly through a P0 alias whose `source` is `literature` | Yes | `Sami` | `Finland`, a standardized ethnonym not printed by the source, or a country centroid | Population identity is not interchangeable with nationality or a guessed location |
| `sample_id` | Blank allowed | Verbatim stable sample/stratum identifier supplied by the source | Optional for one measurement; required and distinct when the same citation/population/cohort/variant has multiple measurements | Yes | `sample:north-1997` when that identifier is printed | `sample-1` assigned from row order | Invented sample IDs conceal possible duplicate cohorts instead of resolving them |
| `cohort_id` | Blank allowed | `cohort:<study-slug>:<cohort-slug>` backed by reported identity or an approved exact mapping | Always required | Yes | `cohort:liebert-2017:sami` | One new cohort ID per publication row or a fallback equal to population | The same recruited people can appear in several papers; treating them as independent double-weights evidence |
| `assay` | Blank allowed | Verbatim assay or an issue-approved controlled mapping | Always required | Yes | `targeted genotyping` with a located Methods statement | `genotyping` guessed from publication year | Assay uncertainty changes the interpretation of calls, no-calls, and denominators |
| `sampling_design` | Blank allowed | One of `population_random`, `healthy_reference`, `clinical_case`, `clinical_control`, `newborn_screening`, `carrier_screening`, `convenience` | Always required | Yes | `population_random` from an explicit population survey design | Defaulting every missing value to `convenience` | A default looks complete but fabricates the covariate used to correct ascertainment bias |
| `disease_ascertainment_excluded` | Blank allowed | Lowercase TSV `true` or `false`; parser produces nullable Boolean | Always required | Yes | `false` because recruitment was not disease-depleted, with located evidence | Blank coerced to `false`, or `false` because cases were not mentioned | Null means unresolved; `false` is a scientific assertion about recruitment |
| `date_lower` | Blank allowed, paired with `date_upper` | Non-negative integer years before present | Always required and `date_lower <= date_upper` | Yes | `0` from explicit evidence participants were contemporary/living | `0` inferred from publication year | Publication date is not sampling date; ancient and modern observations must not be conflated |
| `date_upper` | Blank allowed, paired with `date_lower` | Non-negative integer years before present | Always required and `date_lower <= date_upper` | Yes | `0` with the same modern-sample evidence as `date_lower` | A guessed range or only one bound populated | Half a date interval invents precision and cannot define the time support |

### Counts and frequency text

The three count cells are all-or-none in staging. Promotion additionally requires
`ac_lower == ac_upper`; interval counts and frequency-reconstructed counts remain useful evidence
but do not enter the current exact-count likelihood.

| Column | Staging value | Exact accepted representation | Promotion rule | Field row | Correct example | Prohibited example | Why prohibited |
|---|---|---|---|---|---|---|---|
| `an` | Blank allowed only when both AC bounds are blank | Positive integer number of **alleles called**, supported by the source | Always required | Yes | `58` explicitly reported, or exactly derived from 29 complete autosomal diploid calls | `60` from enrolled people when two genotypes were no-calls | The likelihood denominator is observed chromosomes, not recruited people or attempted calls |
| `ac_lower` | Blank allowed only with `an` and `ac_upper` blank | Integer `0 <= ac_lower <= ac_upper <= an` | Required and must equal `ac_upper` | Yes | `17` from a printed `17/58` | `18` from rounding `60 × 0.293` | Rounded frequencies can change an exact allele count and overstate certainty |
| `ac_upper` | Blank allowed only with `an` and `ac_lower` blank | Integer upper endpoint of the admissible count interval | Required and must equal `ac_lower` | Yes | `17` for an exact count; `16` and `18` may stage an honest interval | Selecting the midpoint of an interval | The present P1 likelihood cannot represent interval censoring; midpoint selection manufactures a measurement |
| `reported_frequency` | Blank allowed | Exact printed token as text, preserving decimals, percent signs, inequalities, and ranges | Optional; never used as the P1 likelihood input | Yes | `17/58`, `0.293`, `29.3%`, or `<0.01` exactly as printed | Parsing to float and writing `0.2929999999`, or recomputing `ac/an` | The literal is audit evidence; numeric reserialization destroys what the source actually stated |
| `count_basis` | Blank allowed | Exactly `reported`, `genotype_derived`, or `frequency_reconstructed` | Always required; `frequency_reconstructed` is refused | Yes | `reported` when exact AC is printed | `reported` merely because a compilation contains an integer AC | A compilation may have rounded `AN × frequency`; integer storage does not prove an exact source count |
| `denominator_basis` | Blank allowed | Exactly `reported_alleles`, `diploid_individuals`, or `hemizygous_males` | Always required | Yes | `hemizygous_males` for a located male-only X-linked call denominator | Always using `diploid_individuals`, including chrX males | Wrong ploidy changes AN and therefore the inferred frequency and uncertainty |

### Citation and immutable source anchor

| Column | Staging value | Exact accepted representation | Promotion rule | Field row | Correct example | Prohibited example | Why prohibited |
|---|---|---|---|---|---|---|---|
| `citation_id` | Blank allowed | One original-measurement ID: `pmid:<digits>`, lowercase `doi:10.…`, or `thesis:<repository>:<id>` | Always required | Yes | `pmid:29063188` after exact record resolution | Author-year text, a search URL, a fabricated PMID, or the compilation ID when the original is known | The row must resolve to the study that owns the measurement, not merely a secondary source |
| `citation_text` | Blank allowed | Human-readable citation sufficient to identify authors, title, venue/repository, and year | Always required | Yes | Full checked Liebert et al. citation | LLM-completed title, `Liebert et al.`, or a copied citation that disagrees with `citation_id` | Plausible citations are easy to fabricate and difficult to detect without a persistent-ID cross-check |
| `record_source_id` | Required | Persistent inspected source: citation ID or `repo:github.com/<owner>/<repo>@<40-hex>:<path>` | Must remain present; contributes to reuse checks | No | `repo:github.com/manpreetbola/protective-alleles-gnomad-v4@7c2b1cc6bb783b56fdfffaed5c44d8e8273da994:data/lct_rs4988235_observations.csv` | Moving `main` URL, local path, browser search result, or dataframe filename alone | The source record must remain recoverable after upstream files or branches change |
| `record_locator` | Required | Exact `table:…`, `figure:…`, `page:…`, `supplement:…`, or `dataset-record:…` locator for this measurement | Must remain present and combine with `record_source_id` to regenerate the ID | No | `table:3,row:sami` or `dataset-record:sha256:<64hex>` | `the paper`, `table:unknown`, or local row 17 | Generic or position-dependent locations cannot prove which measurement was transcribed |
| `record_source_url` | Blank allowed | Stable absolute HTTPS full-text, landing-page, or commit-pinned raw URL; no query/fragment | Optional | No | `https://pubmed.ncbi.nlm.nih.gov/29063188/` | Google result, `http://localhost`, or a signed expiring URL | Audit links must be safe and stable; access convenience is not source identity |

### Verification and extraction identity

| Column | Staging value | Exact accepted representation | Promotion rule | Field row | Correct example | Prohibited example | Why prohibited |
|---|---|---|---|---|---|---|---|
| `verification_status` | Required; recomputed | `original_source_verified`, `compilation_verified`, or `pending` | Must recompute to a verified state | No | `pending` for every automated proposal | Agent writes `original_source_verified` after extracting its own answer | Verification is an outcome of complete field evidence plus an independent verifier, never a confidence claim |
| `extraction_method` | Required | `manual_transcription`, `structured_table`, `ocr_reviewed`, or `automated_proposal` | Any value may promote if every other gate and independent verification passes | No | `automated_proposal` for `audit_lct_pilot.py` output | Calling raw OCR `structured_table`, or calling agent output manual transcription | Method labels communicate error modes and cannot be upgraded to imply review |
| `extracted_by` | Required | `human:<slug>`, `agent:<provider>:<model>`, or `import:<name>@<40-hex>` | Must differ from `verified_by` | No | `agent:openai:gpt-5` or a commit-pinned import identity | A person/model name without namespace, or the verifier identity | Stable identity is needed to audit independence and reproduce import behavior |
| `extracted_at` | Required | UTC `YYYY-MM-DDTHH:MM:SSZ`, not in the future | Must remain present | No | `2026-09-04T10:00:00Z` | Local time without zone, date only, or future timestamp | Extraction chronology is part of reproducibility and review independence |
| `verified_by` | Blank while pending | A valid identity in the same format as `extracted_by` | Required for verified rows; must be independent of extractor | No | `human:reviewer` | Same agent/human as `extracted_by`, or invented reviewer | Self-review cannot catch a shared transcription or interpretation error |
| `verified_at` | Blank while pending | UTC `YYYY-MM-DDTHH:MM:SSZ`, not in the future | Required for verified rows | No | `2026-09-04T11:00:00Z` | Timestamp present on a pending row | Verifier metadata on pending data falsely signals completed review |
| `verification_reference` | Blank while pending | Stable issue, PR, review record, or equivalent reference | Required for verified rows | No | `https://github.com/bschilder/genomeOS/issues/149` | `looks good`, branch name, chat assertion, or unresolvable local file | Review must leave an inspectable decision trail |

### Reuse and versioning

| Column | Staging value | Exact accepted representation | Promotion rule | Field row | Correct example | Prohibited example | Why prohibited |
|---|---|---|---|---|---|---|---|
| `reuse_status` | Required; recomputed | `explicitly_open`, `permission_granted`, `no_restriction_found`, `restricted`, or `not_checked` | Any except `restricted` and `not_checked`; absence of a named licence is not a restriction after documented checks | No | `no_restriction_found` after every contributing source surface was checked | `explicitly_open` because no licence was visible, or `restricted` merely because none was named | Missing terms are neither explicit permission nor an explicit prohibition; the check and its result must be represented honestly |
| `reuse_evidence` | Blank only when nothing was checked | Compact canonical JSON object `{"checks":[…]}` with one sorted, unique entry for every contributing source; exact keys depend on finding | Must cover `record_source_id` and every non-null field `evidence_source_id`; any explicit restriction wins | No | `{"checks":[{"checked_at":"2026-09-04","finding":"no_restriction_found","source_id":"pmid:29063188","surfaces":["https://pubmed.ncbi.nlm.nih.gov/29063188/"]}]}` | Free text `no license`, incomplete source list, unsorted JSON, or permission whose scope omits downstream reuse | Machine-recomputed policy prevents agents from turning vague or partial checks into eligibility |
| `reuse_checked_at` | Blank only when status recomputes to `not_checked` with no checks | UTC date `YYYY-MM-DD`, equal to the latest check in `reuse_evidence` | Required when any check exists | No | `2026-09-04` | Publication date, extraction date, or caller-selected date inconsistent with JSON | The timestamp describes the terms review, whose result can change over time |
| `notes` | Blank allowed | Concise caveats not represented elsewhere | Never satisfies a structured promotion field | No | `Original supplement was paywalled; field review remains pending.` | `radius about 100 km`, `probably random sampling`, or an allele guess | Narrative cannot bypass typed validation or make an unsupported fact computable |
| `ingest_version` | Required | Immutable `<corpus_id>@YYYY-MM-DD.<positive revision>` | Must match `corpus_id` | No | `lct-rs4988235@2026-09-05.1` | `latest`, mutable filename, or a version for another corpus | A cited evidence build must remain reproducible after curation changes |

## Companion field evidence, exactly

Copy this exact ten-column header and emit exactly one row for each of the 19 tracked fields per
`source_record_id`:

```text
source_record_id	field_name	evidence_status	raw_value	evidence_source_id	source_locator	checked_scope	derivation_method	decision_reference	notes
```

The 19 `field_name` values are exactly: `variant_id`, `rsid`, `counted_allele`,
`population_label`, `sample_id`, `cohort_id`, `an`, `ac_lower`, `ac_upper`,
`reported_frequency`, `count_basis`, `denominator_basis`, `citation_id`, `citation_text`, `assay`,
`sampling_design`, `disease_ascertainment_excluded`, `date_lower`, and `date_upper`.

| Column | Required value | Exact accepted representation | Correct example | Prohibited example | Why prohibited |
|---|---|---|---|---|---|
| `source_record_id` | Always | Exact parent ID; 19 rows per parent | The full `literature:lct-rs4988235:f5fd55995c17abf484c03ca85bb786b2710ab49556baad33ad8e1099caa53afe` on all 19 rows | Orphan ID, missing row, or 20th custom field | Completeness is checked per source record, not inferred from populated main cells |
| `field_name` | Always | One closed tracked name, exactly once | `sampling_design` | `radius_km`, `frequency`, duplicate `an` | The closed set ensures every promotion fact has one review decision |
| `evidence_status` | Always | `reported`, `derived`, `not_reported`, `ambiguous`, or `not_reviewed` | `not_reviewed` for an uninspected method | Generic `unresolved`, `verified`, confidence score, or blank | Each state has distinct claims about what was seen and checked |
| `raw_value` | For `reported`, `derived`, `ambiguous`; blank otherwise | Exact source token for reported/ambiguous; exact canonical derivation input for derived | `17/58` or canonical genotype JSON | Paraphrase, normalized decimal, placeholder, or any value on `not_reviewed` | Audit must reconstruct the cell from immutable evidence, not trust a summary |
| `evidence_source_id` | All except `not_reviewed` | Persistent citation/thesis/commit-pinned repository source | `pmid:29063188` | Moving branch, generated citation, or source on unreviewed status | The field claim must point to the document actually inspected |
| `source_locator` | `reported`, `derived`, `ambiguous`; blank for absence/unreviewed | Exact value location using an allowed locator prefix | `supplement:table-s3,row-386,column-frequency` | `the paper`, URL alone, guessed page, or locator for `not_reported` | A single value location proves a value, not that a value was absent everywhere |
| `checked_scope` | Only `not_reported` | Compact sorted unique JSON array of every exact section checked | `["page:methods-3-5","supplement:S3-methods"]` | `everywhere`, one guessed section, unsorted list, or scope on a reported value | An absence claim is only as strong as its documented search coverage |
| `derivation_method` | Only `derived` | One of the nine closed methods below | `counts_from_explicit_integer_fraction` | Free-text formula, `manual`, `LLM`, chained methods | Only executable, tested transformations may create typed values |
| `decision_reference` | Required for `derived`; optional for reported/ambiguous; blank for absence/unreviewed | Absolute GitHub issue/PR URL approving the mapping or method | Issue #149 URL | Chat link, branch, local path, or invented approval | Derivations are governed decisions, not private extractor judgement |
| `notes` | Required for `not_reported`, `ambiguous`, `not_reviewed`; optional otherwise | Specific explanation of what was absent, conflicting, or unfinished | `Recruitment design has not yet been reviewed in the Methods.` | `unknown`, `N/A`, or instructions to bypass promotion | The note explains the unresolved state but never supplies the missing value |

The five statuses form an exact matrix:

| Status | Main cell | Raw value | Evidence source | Value locator | Checked scope | Method | Notes |
|---|---|---|---|---|---|---|---|
| `reported` | Non-null | Required, exactly equal after typed parsing | Required | Required | Blank | Blank | Optional |
| `derived` | Non-null and exactly recomputable | Required canonical input | Required | Required | Blank | Required | Optional |
| `not_reported` | Null | Blank | Required | Blank | Required | Blank | Required |
| `ambiguous` | Null | Required literal conflicting/vague text | Required | Required | Blank | Blank | Required |
| `not_reviewed` | Null | Blank | Blank | Blank | Blank | Blank | Required |

### The only allowed derivations

The allowlist is closed: `variant_normalization`, `persistent_citation_resolution`,
`alternate_count_from_reference_count`, `allele_count_from_genotypes`,
`allele_denominator_from_complete_diploid_sample`,
`allele_denominator_from_hemizygous_males`, `counts_from_explicit_integer_fraction`,
`controlled_vocabulary_mapping`, and `modern_sample_to_zero_bp`. Exact inputs and operations are in
[design §5.3](superpowers/specs/2026-09-05-literature-evidence-design.md#53-literature_field_evidence)
and exercised by the [derived fixture](../tests/fixtures/literature/derived/field_evidence.tsv).
If a value requires another operation or a chain of operations, leave it unresolved and propose a
new tested method through an issue. Reviewer approval cannot turn a free-text calculation in a data
cell into an allowed derivation.

## Search manifest columns

Search results are discovery records, never observations and never automatic inclusion decisions.
Copy the exact header:

```text
search_id	corpus_id	database	query	executed_at	candidate_id	decision	decision_reason	manifest_version
```

| Column | Exact requirement | Correct example | Prohibited shortcut |
|---|---|---|---|
| `search_id` | Stable `pubmed:<sha256>` of database, exact query, and UTC execution timestamp | Output of `fetch_pubmed_manifest.py` | Random UUID or query name alone |
| `corpus_id` | Target corpus slug | `lct-rs4988235` | Gene name with spaces |
| `database` | Exactly `pubmed` | `pubmed` | `literature` or an unreviewed database alias |
| `query` | Exact submitted non-empty query | `rs4988235[All Fields]` | Paraphrase written after the search |
| `executed_at` | UTC timestamp with seconds and `Z` | `2026-09-05T12:00:00Z` | Date only or local time |
| `candidate_id` | One `pmid:<positive integer>` per result, unique within search | `pmid:29063188` | DOI, title, duplicate PMID, or bare integer |
| `decision` | `pending`, `included`, or `excluded` | `pending` on every fetched result | Auto-including based on title or model confidence |
| `decision_reason` | Required only for excluded; blank for pending | `not a population frequency study` | Reason on pending, or blank exclusion |
| `manifest_version` | Immutable version matching corpus | `lct-rs4988235@2026-09-05.1` | `latest` or in-place mutation |

## Promotion is recomputed, never requested

`publications.load(...)` validates both ledgers, recomputes normalization, verification, reuse,
count exactness, and duplicate conditions, then resolves the verbatim `population_label` through
exact P0 aliases with `source=literature`. It copies P0 `lat`, `lon`, and
`uncertainty_radius_km` exactly and asserts equality after P1 validation. Literature evidence has no
geography input column, and the adapter has no `force`, `eligible`, fallback-radius, or permissive
flag.

A row refuses promotion when any required field is unresolved, ALT orientation is ambiguous,
counts are intervals or frequency-reconstructed, verification is pending, reuse was not checked or
is explicitly restricted, a regional label is unresolved, or a cohort/sample would be duplicated.
An ordinary unmapped population label is a hard build error because its missing P0 work cannot be
silently discarded.

No named licence is **not** automatically a restriction. Check every contributing source’s stated
terms, repository surfaces, landing page, and relevant supplement surface; record
`no_restriction_found` when that completed check finds no explicit restriction. Conversely,
`not_checked` means the check did not happen and cannot be promoted. Any explicit restriction wins
over every permissive or unstated source in the aggregate.

## Minimum curation workflow

1. Snapshot discovery with `scripts/fetch_pubmed_manifest.py`; every candidate starts pending.
2. Assign one immutable source record and exact record locator per independent measurement.
3. Fill only source-supported main values and all 19 field decisions. Use `not_reviewed` before
   inspection, `not_reported` only after documenting the complete checked scope, and `ambiguous`
   for located conflicting/vague text.
4. Resolve variants, citations, counts, controlled mappings, or modern dates only through an
   allowlisted method with exact raw input and a decision reference.
5. Add population geography separately to P0 with provenance and a reviewed uncertainty radius;
   never copy a paper’s country or coordinates directly into the literature ledger.
6. Have an independent reviewer check allele orientation, called denominator, cohort identity,
   ascertainment, date, source locator, and reuse record.
7. Run schema validation and the publications adapter. Treat every reported refusal as work to
   resolve or preserve, never as a prompt to fill a plausible value.
