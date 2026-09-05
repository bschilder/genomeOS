# Literature Evidence Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a frozen, auditable literature-evidence ledger and a deterministic fail-closed path that promotes only independently verified publication measurements into P1 observations.

**Architecture:** Keep verbose extraction and field provenance in staging contracts owned by `genomeos.observations.evidence`; keep publication-to-P1 translation in a pure source adapter; obtain all geography exclusively from the P0 registry; add only a stable `source_record_id` foreign key to the P1 hot table. Network discovery and pilot migration remain scripts around these pure contracts.

**Tech Stack:** Python 3.12, pandas, pandera, pyarrow, pytest, standard-library `urllib`/JSON, GitHub CLI.

**Spec:** [`docs/superpowers/specs/2026-09-05-literature-evidence-design.md`](../specs/2026-09-05-literature-evidence-design.md)

## Global Constraints

- Follow design §§1, 4–7 and AGENTS.md's P0/P1 invariants; module docstrings cite the implemented sections.
- Never invent a coordinate, uncertainty radius, sample/cohort identity, sampling design, assay, date, denominator, allele count, citation, source location, reviewer, or reuse check.
- Loaders reject malformed structure and dishonest metadata. The publications adapter reports scientifically incomplete but structurally valid staging rows as refusals.
- `normalization_status`, `verification_status`, `reuse_status`, and promotion eligibility are recomputed; no caller-supplied `eligible`, `force`, fallback, or permissive flag exists.
- Tests use checked-in tiny fixtures and no network. Generated contracts are the only generated files committed by the schema work.
- Do not touch unrelated untracked artifact and team-update files in the shared worktree.

---

### Task 1: Freeze the exact evidence vocabularies and structural contracts

**Files:**
- Create: `genomeos/observations/evidence.py`
- Test: `tests/test_literature_evidence_schema.py`

- [x] Write failing tests asserting the exact 37-column evidence header, exact 10-column field-evidence header, exact search-manifest header, nullable/non-nullable fields, enums, identifier patterns, and strict column order.
- [x] Add table-level failing tests for fake missing strings, placeholder locators, noncanonical DOI/JSON, mismatched corpus IDs, duplicate `source_record_id`, invalid count intervals, reversed dates, same extractor/verifier, verifier fields on pending rows, inconsistent field-evidence cardinality, orphan field evidence, duplicate field names, and incomplete search decisions.
- [x] Run `pytest tests/test_literature_evidence_schema.py -q` and confirm the import/test failures are about missing implementation.
- [x] Implement constants for all ordered columns, 19 evidence-tracked fields, 16 unconditional promotion fields, conditional `sample_id`, five evidence statuses, extraction/normalization/verification/reuse enums, and the nine-method derivation allowlist.
- [x] Implement strict pandera schemas plus pure cross-row validators. Provide `validate_literature_tables(evidence, field_evidence)` and `validate_search_manifest(frame)`; return validated copies and raise hard errors for structural dishonesty.
- [x] Implement `make_source_record_id(corpus_id, record_source_id, record_locator)` as the full lowercase SHA-256 of UTF-8 `record_source_id + "\n" + record_locator`, and verify caller-supplied IDs match it.
- [x] Recompute and compare all three status columns. Reuse checks aggregate `record_source_id` and non-null field `evidence_source_id` values from canonical JSON evidence; any restriction wins, unchecked sources produce `not_checked`, and a checked source with no named licence may produce `no_restriction_found`.
- [x] Run `pytest tests/test_literature_evidence_schema.py -q` and make it pass.

### Task 2: Add canonical good, unresolved, derived, and prohibited examples

**Files:**
- Create: `tests/fixtures/literature/promotable/evidence.tsv`
- Create: `tests/fixtures/literature/promotable/field_evidence.tsv`
- Create: `tests/fixtures/literature/promotable/populations.tsv`
- Create: `tests/fixtures/literature/promotable/aliases.tsv`
- Create: `tests/fixtures/literature/non_promotable/evidence.tsv`
- Create: `tests/fixtures/literature/non_promotable/field_evidence.tsv`
- Create: `tests/fixtures/literature/derived/evidence.tsv`
- Create: `tests/fixtures/literature/derived/field_evidence.tsv`
- Create: `tests/fixtures/literature/invalid/cases.json`
- Modify: `tests/test_literature_evidence_schema.py`

- [x] Build one fully promotable rs4988235 record with an exact alias-backed P0 location and all 19 field-evidence rows.
- [x] Build one valid pending record whose absent fields explicitly distinguish `not_reported`, `ambiguous`, and `not_reviewed`.
- [x] Build reviewed examples exercising every allowed derivation method; each derived field names raw input, evidence source/location, and deterministic method.
- [x] Define representative invalid mutations in `cases.json`: invented country radius, default convenience sampling, fake singleton cohort, rounded count, guessed allele, self-verification, placeholder source locator, fabricated citation, unchecked reuse promoted as reusable, and omitted field-evidence row.
- [x] Parameterize fixture validation tests so good/pending/derived files validate and every prohibited shortcut raises the named invariant.
- [x] Run `pytest tests/test_literature_evidence_schema.py -q`.

### Task 3: Implement deterministic publication promotion through P0

**Files:**
- Create: `genomeos/observations/sources/publications.py`
- Modify: `genomeos/observations/sources/__init__.py`
- Create: `tests/test_publications_source.py`

- [x] Write failing tests for `load(evidence_path, field_evidence_path, populations, aliases, ingest_version)` returning `(observations, retained_evidence, report)`.
- [x] Cover the full promotable fixture; exact-copy assertions for `population_id`, `lat`, `lon`, and `radius_km`; one-to-one `source_record_id`; deterministic result order; and an empty refusal report.
- [x] Cover refusal reasons for pending verification, unresolved/ambiguous normalization, interval or frequency-reconstructed counts, missing required evidence, unresolved alias, duplicate source record, duplicate cohort/sample measurement, counted allele not equal to ALT, and restricted/not-checked reuse.
- [x] Cover conditional `sample_id`: two measurements with equal `(citation_id, population_label, cohort_id, variant_id)` require distinct source-reported sample IDs.
- [x] Implement an immutable `IngestReport` with total, retained, and reason counts. Validate both ledgers first, recompute promotion facts, and never parse narrative text.
- [x] Resolve aliases only where `source == "literature"`, require exactly one alias and one P0 row, and copy `lat`, `lon`, and `uncertainty_radius_km` verbatim. Assert emitted values equal the resolved registry values after P1 validation.
- [x] Emit exact counts only (`ac_lower == ac_upper`), use source `literature:<corpus_id>`, retain matching evidence rows, and expose no eligibility override.
- [x] Run `pytest tests/test_publications_source.py -q`.

### Task 4: Put stable source identities on every existing P1 allele-count observation

**Files:**
- Modify: `genomeos/observations/schema.py`
- Modify: `genomeos/observations/sources/gnomad_hgdp_1kg.py`
- Modify: `genomeos/observations/sources/map_surveys.py`
- Modify: `genomeos/observations/sources/map_g6pd.py`
- Modify: `genomeos/observations/sources/afnd_frequencies.py`
- Modify: `genomeos/observations/sources/afnd_cytokines.py`
- Modify: `scripts/build_demo_artifacts.py`
- Modify: `tests/test_observations_schema.py`
- Modify: `tests/test_gnomad_source.py`
- Modify: `tests/test_map_surveys.py`
- Modify: `tests/test_map_g6pd.py`
- Modify: `tests/test_afnd_frequencies.py`
- Modify: `tests/test_afnd_carriers_and_cytokines.py`
- Modify: `tests/test_surface_fit.py`
- Modify: `tests/test_batch.py`

- [x] First require a non-empty globally namespaced `source_record_id` in `OBSERVATIONS_SCHEMA` and update direct test frames; run focused tests to expose every adapter still missing it.
- [x] Generate stable IDs from source-native immutable identities: gnomAD variant/population record; MAP survey IDs; and AFND record/locus/population identities. Hash a canonical tuple only where the source supplies no single accession; never use dataframe index or random UUID.
- [x] Add adapter assertions for uniqueness and deterministic IDs across repeat loads.
- [x] Do not add the field to `CARRIER_OBSERVATIONS_SCHEMA`, because this task changes the allele-count P1 relation only.
- [x] Run `pytest tests/test_observations_schema.py tests/test_gnomad_source.py tests/test_map_surveys.py tests/test_map_g6pd.py tests/test_afnd_frequencies.py tests/test_afnd_carriers_and_cytokines.py tests/test_surface_fit.py tests/test_batch.py -q`.

### Task 5: Compose literature evidence into the offline observation build

**Files:**
- Modify: `scripts/build_observations.py`
- Modify: `tests/test_build_scripts.py`

- [x] Write a failing CLI test invoking the build with `--literature-evidence`, `--literature-field-evidence`, registry fixtures, and the existing source fixtures.
- [x] Add the two options as an all-or-neither pair; load P0 parquet tables; invoke `publications.load`; append only promoted observations; and print its refusal report.
- [x] Write retained evidence to `literature_evidence.parquet` beside `observations.parquet`, preserving the stable foreign-key target. Do not put evidence text in the P1 table.
- [x] Assert the fixture-backed rs4988235 row survives the complete script and its coordinates/radius exactly equal the P0 fixture.
- [x] Run `pytest tests/test_build_scripts.py tests/test_publications_source.py -q`.

### Task 6: Freeze the new public contracts

**Files:**
- Modify: `scripts/freeze_contract.py`
- Modify: `contract/observations.schema.json`
- Create: `contract/literature_evidence.schema.json`
- Create: `contract/literature_field_evidence.schema.json`
- Create: `contract/literature_searches.schema.json`
- Modify: `tests/test_contracts.py`

- [x] Write/extend a failing contract test requiring all three literature schemas and the new observation key.
- [x] Register all evidence schemas in `PANDERA_SCHEMAS` and run `python scripts/freeze_contract.py`.
- [x] Inspect the contract diff for exact field names/order, nullability, enums, and `source_record_id`.
- [x] Run `python scripts/freeze_contract.py --check` and `pytest tests/test_contracts.py -q`.

### Task 7: Add reproducible PubMed discovery without putting network I/O in science code

**Files:**
- Create: `scripts/fetch_pubmed_manifest.py`
- Create: `tests/fixtures/pubmed/esearch_rs4988235.json`
- Create: `tests/test_fetch_pubmed_manifest.py`

- [x] Write failing pure-parser tests for PubMed ESearch JSON, stable `search_id`, UTC execution timestamp, namespaced PMID candidates, pending decisions, manifest version, ordering, and duplicate rejection.
- [x] Implement a pure `build_manifest(payload, corpus_id, query, executed_at, manifest_version)` and a thin CLI using standard-library HTTPS. Require explicit query, date/version, and output; do not infer screening decisions.
- [x] Validate output through `LITERATURE_SEARCHES_SCHEMA`, write TSV in contract order, and make HTTP/API failures fatal.
- [x] Run `pytest tests/test_fetch_pubmed_manifest.py -q`.

### Task 8: Audit the complete LCT pilot without manufacturing P1 metadata

**Files:**
- Create: `scripts/audit_lct_pilot.py`
- Create: `tests/fixtures/literature/lct_pilot_sample.csv`
- Create: `tests/test_audit_lct_pilot.py`
- Create after audit: `docs/audits/lct-rs4988235-pilot.json`

- [x] Write failing tests that a small upstream-format CSV receives stable `dataset-record:` locators and source IDs pinned to `repo:github.com/manpreetbola/protective-alleles-gnomad-v4@<40-hex-commit>:data/lct_rs4988235_observations.csv`.
- [x] Assert migration output is `automated_proposal`/`pending`, has blank verifier fields, records source-present values only, emits all 19 evidence rows, and does not invent cohort, assay, sampling design, dates, field locators, P0 geography, or radius.
- [x] Implement CSV inventory and reconciliation reporting: input/output row counts, duplicate immutable anchors, country-label count, missingness by target field, exact-vs-reconstructed count inventory, and whether all 426 rows were assigned exactly one anchor.
- [x] Fetch the exact upstream CSV at its pinned commit, run the audit, and commit only the compact JSON audit report—not article text or a silently curated P1 table. The report must show 426/426 reconciliation or fail.
- [x] Run `pytest tests/test_audit_lct_pilot.py -q` and the exact audit command recorded in the JSON report.

### Task 9: Write the agent/human curation contract and wire project documentation

**Files:**
- Create: `docs/literature-evidence-curation.md`
- Modify: `AGENTS.md`
- Modify: `docs/overview.md`
- Modify: `docs/scientific-engineering-objectives.md`
- Modify: `docs/superpowers/specs/2026-09-05-literature-evidence-design.md`

- [x] Mark the approved spec status accurately and link this implementation plan.
- [x] Document every column in copyable header order with: whether a staging value is required, exact accepted representation, promotion rule, evidence-row requirement, one correct example, one prohibited example, and why the shortcut is scientifically unsafe.
- [x] Include complete good, unresolved, and derived records by linking the schema-tested TSV fixtures; explain row granularity, immutable anchors, 19-row completeness, status recomputation, exact counts, P0-only geography, duplicate/cohort semantics, independent verification, and reuse checks.
- [x] Add explicit agent instructions: never convert uncertainty to plausible metadata; no unverified value may be represented as `reported`/`derived`; absence of a named licence is not itself a restriction but every aggregate source must be checked and logged; refusal is a valid output.
- [x] Add publications to the overview source table and P1 objective/evidence while preserving the observation/surface boundary.
- [x] Run documentation link/search checks available in the suite and `python scripts/check_module_size.py`.

### Task 10: Update the issue tracker to match the implemented dependency graph

**External state:** GitHub issues #7, #8, #45, #117, #149 plus two new follow-on issues.

- [x] Re-read open and closed issue state immediately before mutation; do not overwrite intervening human decisions.
- [x] Reopen #45 if still closed without completed HbS parity evidence, and comment with the specific remaining acceptance run.
- [x] Comment on #7 and #8 with the P0 alias/geography and P1 literature-evidence interfaces now implemented.
- [x] Close #117 as completed only if its remaining question is exactly resolved by the approved checked-terms/no-explicit-restriction policy; record the decision and retain explicit-restriction handling.
- [x] Rewrite #149 to describe the delivered foundation and remaining curation, apply the four repository label families, and leave it open until the PR merges.
- [x] Open one HBB round-trip issue tied to HbS parity and one G6PD literature-ingestion issue tied to X-linked/parity acceptance. Do not claim those scientific validations are complete.
- [x] Record all resulting issue URLs/numbers in the PR body.

Tracker results: [#7](https://github.com/bschilder/genomeOS/issues/7),
[#8](https://github.com/bschilder/genomeOS/issues/8),
[#45](https://github.com/bschilder/genomeOS/issues/45),
[#117](https://github.com/bschilder/genomeOS/issues/117),
[#149](https://github.com/bschilder/genomeOS/issues/149),
[#150](https://github.com/bschilder/genomeOS/issues/150), and
[#151](https://github.com/bschilder/genomeOS/issues/151).

### Task 11: Verify, review, commit, and open the pull request

**Files:** all files above.

- [ ] Run focused suites after each task, then run the mandatory full gates:

```bash
ruff check .
python scripts/freeze_contract.py --check
python scripts/check_module_size.py
python scripts/check_private_files.py
python scripts/smoke.py
pytest
```

- [ ] Inspect `git diff --check`, `git status --short`, `git diff --stat`, and the complete diff. Confirm unrelated untracked artifacts remain unstaged.
- [ ] Use `superpowers:requesting-code-review` for a spec/implementation review and address findings before completion.
- [ ] Run `python scripts/check_private_files.py` again, stage only named task files, and inspect `git diff --cached --name-only`.
- [ ] Commit coherent units with imperative messages containing `closes #149` on the implementation commit; push `feat/149-literature-evidence`.
- [ ] Open a PR whose body states the scientific claim, design sections, schema/promotion refusals, LCT 426-row audit result, exact verification commands/results, follow-on issues, and `Closes #149`. Request expert review of allele orientation, denominator derivations, cohort semantics, and the reuse-evidence policy.
