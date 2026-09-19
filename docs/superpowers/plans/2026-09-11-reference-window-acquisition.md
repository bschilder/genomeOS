# Frozen Reference-window Acquisition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Execution stays within the owner's authorized global AF campaign; the controller reviews each task and exact source before real retrieval. This document does not itself attest that #254 or this implementation has passed independent review.

**Goal:** Package exact generation-bound acquisition and four traceable count inputs over the original 66 frozen reference windows for #255, advancing #189 WP0/WP1.

**Architecture:** A strict consumer of reviewed #254 artifacts supplies bounded sparse acquisition. An original-token adapter preserves raw GT/QC semantics, pure cohort/count functions derive AC/AN, and native extraction/cohort-total controls validate distinct parts of the result. Immutable manifest-last writers retain complete window and failure accounting.

**Tech Stack:** Existing Python 3.12 locked environment; standard-library dataclasses, typing, csv/json, hashlib, struct/zlib and subprocess; existing NumPy and pytest; native bcftools/HTSlib/tabix/bgzip 1.23.1; repository gcloud wrapper. No package or lock changes.

**Spec:** `docs/superpowers/specs/2026-09-11-reference-window-acquisition.md`; read that whole design, AGENTS.md, overview/scientific objectives and Atlas §§4–8,12 before this plan. The upstream contract is `docs/superpowers/specs/2026-09-10-reference-window-preflight-design.md`. Original behavior is evidenced by the retained diagnostic scripts and `docs/research/hgdp-count-pilot-2026-09-09.md`, not automatically endorsed by a script's existence.

## Global Constraints

- Exactly 66 frozen windows, chr1–chr22 ×3, 10,000 bases; consume original coordinates, no redraw/replacement.
- Hard planned compressed transfer cap 26,843,545,600 bytes, including all 22 retained indexes, merged VCF ranges, 1,048,576-byte prefix and 28-byte EOF per source.
- No VCF bytes until complete #254 preflight and exact acquisition/count source have passed independent review; no duplicate index body acquisition.
- Two fixed cohorts: `technical_qc_4117`, `paper_ancestry_exclusion_4094`; 80 literal populations; four separate called/quality tables.
- PASS, distinct biallelic uppercase A/C/G/T SNPs; complete diploid GT; missing GT reduces AN; AN=0 stays unavailable.
- Preserve lazy sequential GQ≥20, DP≥10, heterozygote each AD×5≥DP, including missing/arity/left-to-right short-circuit order. Unused tokens remain uninspected.
- `ReferenceCount` and P0/P1 schemas unchanged; `publication_eligible=false`, `p1_eligible=false`, `benchmark_admitted=false`.
- Preserve 77 reported-edge population components; source `Genetic.region` is an operational label, not verified resident geography.
- Every GCP operation uses `scripts/gcloud_repo.py`; explicit source generation; no application retry/source fallback/range expansion.
- `CLOUDSDK_STORAGE_MAX_RETRIES=0`; adapter invocation counters are not HTTP request counters. Metadata HTTP attempts and total wire bytes remain unobserved, with bounded invocation time/output.
- No production inference, GPU, public participant/count dataset, new geography/date or modifications to original pilot/B0/B0H artifacts.
- Pure modules have no I/O/network/environment imports; immutable types with runtime checks; no private implementation imports.
- Exclusive 0700 output directories/0600 files, canonical timestamp-free manifests written last, never overwrite/resume.
- Limits: BGZF member compressed/decompressed≤65,536 bytes; header≤8,388,608; record≤16,777,216; decoded bytes/window≤2,147,483,648; records/window≤1,000,000; metadata≤1MiB/120s; VCF range/native task≤1,800s. Limit failure refuses, never truncates into a result.
- Native stdout ceilings: BCF/key/token/total streams≤2,147,483,648 bytes; sample-ID queries≤1,048,576; version/help≤65,536. Every native/gcloud stderr≤1,048,576. Retain at most cap+1 sentinel bytes on overflow, kill the process group immediately, and mark retained prefixes refused.
- Production module target≤500 logical lines; split by responsibility before 800 logical lines/50KiB. `from __future__ import annotations` and design section docstrings required.

---

## Files and interfaces shared by every task

Use a dedicated branch/worktree from the reviewed #254 base at execution time. Read open and closed #255/#254/#189 issue history before code. Do not edit another agent's checkout. This is a coherent six-task PR; intermediate commits say “advance #255”; only the final completed unit uses `closes #255`.

| File | Owner task and responsibility |
| --- | --- |
| `genomeos/validation/reference_acquisition_types.py` | 1: immutable review/range/source/window acquisition contracts. |
| `genomeos/validation/reference_preflight_input.py` | 1: strict upstream consumer and review/index revalidation. |
| `genomeos/validation/reference_cohorts.py` | 2: pure metadata projection, exact cohort selection, header-order joins. |
| `genomeos/validation/reference_vcf_tokens.py` | 3: bounded BGZF/header/record token codecs. |
| `genomeos/validation/reference_genotypes.py` | 3: lazy QC and population count arithmetic. |
| `scripts/reference_window_io.py` | 4: bounded body transfer, sparse coverage and raw/native readers. |
| `scripts/reference_runtime.py` | 6: bounded native/transport version checks and executable/library/plugin/SDK hashes. |
| `genomeos/validation/reference_preparation_types.py` | 5: preparation-only manifest/stage/track/dependency records. |
| `genomeos/validation/reference_acquisition_codec.py` | 5: pure strict acquisition manifest codec. |
| `genomeos/validation/reference_preparation_codec.py` | 5: pure strict preparation manifest codec. |
| `genomeos/validation/reference_preparation.py` | 5: count/sidecar projection and reconciliation. |
| `scripts/reference_window_artifacts.py` | 5: exclusive manifest writers/read-back validation. |
| `scripts/reference_artifact_io.py`, `scripts/reference_artifact_inventory.py` | 5: bounded immutable file primitives, exact role-derived inventories and ledger checks. |
| `scripts/reference_cohort_artifacts.py` | 5: retained cohort-file qualification and hash binding. |
| `scripts/reference_count_artifacts.py`, `scripts/reference_count_replay.py`, `scripts/reference_count_rows.py` | 5: disk-backed count validation, source/native replay and strict row streaming. |
| `scripts/reference_native_stage.py`, `scripts/reference_preparation_outputs.py` | 6: native stage orchestration plus preparation fragment/ledger emission. |
| `scripts/acquire_reference_windows.py` | 6: acquisition composition/CLI. |
| `scripts/prepare_reference_window_counts.py` | 6: offline preparation composition/CLI. |
| `tests/reference_acquisition_fixture.py` | 1/4: synthetic source/manifest/native evidence fixture factory, no network. |
| `tests/test_reference_preflight_input.py`, `test_reference_cohorts.py`, `test_reference_vcf_tokens.py`, `test_reference_genotypes.py`, `test_reference_window_io.py`, `test_reference_preparation.py`, `test_reference_window_artifacts.py`, `test_reference_window_clis.py` | Matching task tests; never import private real participant values. |
| `tests/fixtures/reference_acquisition/native/` | 4: tiny synthetic BGZF/TBI, original-token controls, saved native queries/versions/hashes. |
| `docs/research/reference-window-acquisition-2026-09-11.md` | 6: software-only aggregate evidence in Task 6; real-data addendum belongs to the controller phase. |

The design's artifact field sets are normative. Constructor declarations below are exact public interfaces, not executable Python syntax; actual implementation uses frozen dataclasses and closed Literal aliases. Each task owns constructors it introduces. No opaque mutable dictionaries cross pure-domain boundaries.

```text
# Task 1, reference_acquisition_types
# ReviewReceipt has the exact reference_preflight_review_v1 fields
# declared in Shared artifact contracts below.
RetainedIndex(chrom: str, raw: bytes)
# Complete RangeReceipt/VerifiedSource/AcquisitionWindowReceipt definitions are
# in Shared artifact contracts below. PreparationWindowReceipt is separate.
# Reasons closed by Task 1: invalid_input, review_mismatch, metadata_mismatch,
# generation_unavailable, transfer_failed, size_mismatch, timeout, limit_exceeded,
# index_invalid, coverage_gap, header_invalid, sample_mismatch, record_invalid,
# native_encoding_refused, native_count_unavailable, native_mismatch, artifact_mismatch.

# Task 2, reference_cohorts
Sample(sample_id: str, population: str, region: str, hard_filtered: bool)
CohortExclusions(control_id: str, contamination_ids: tuple[str,str])
Cohort(stage: str, samples: tuple[Sample,...])
CohortColumn(sample_id: str, sample_index: int, population: str, region: str)
select_cohorts(samples: tuple[Sample,...], exclusions: CohortExclusions,
               outliers: tuple[str,...]) -> tuple[Cohort,Cohort]
qualify_real_cohorts(metadata: bytes, outliers: bytes, exclusions: bytes,
                     technical_samples: bytes, paper_samples: bytes) -> tuple[Cohort,Cohort]
cohort_columns(header_samples: tuple[str,...], cohort: Cohort) -> tuple[CohortColumn,...]

# Task 3, reference_vcf_tokens / reference_genotypes
HeaderEvidence(samples: tuple[str,...], contigs: tuple[tuple[str,int,str],...],
               formats: tuple[tuple[str,str,str],...], raw_sha256: str)
SourceRecord(chrom: str, pos1: int, ref: str, alt: str, filter: str,
             format_keys: tuple[str,...], sample_ids: tuple[str,...],
             sample_tokens: tuple[str,...],
             source_virtual_offset: int, raw_sha256: str)
CallTokens(gt: str, gq: str, dp: str, ad: str,
           presence: tuple[tuple[str,str],...])
# presence states: present, literal_dot, omitted_trailing, absent_record_format.
project_call(format_keys: tuple[str,...], sample_token: str) -> CallTokens
NativeVariantTokens(variant_id: str, sample_ids: tuple[str,...],
                    tokens: tuple[str,...])
MissingOriginCount(field: Literal['gt','gq','dp','ad'],
                   origin: Literal['literal_dot','omitted_trailing','absent_record_format'],
                   count: int)
CallAssessment(dosage: int | None, disposition: str, inspected_fields: tuple[str,...])
PopulationCount(population: str, region: str, sample_count: int,
                called_ac: int, called_an: int, quality_ac: int, quality_an: int)
QcTally(dispositions: tuple[tuple[str,int],...],
         inspection_totals: tuple[tuple[str,int],...],
         missing_origins: tuple[MissingOriginCount,...])
VariantCounts(variant_id: str, populations: tuple[PopulationCount,...], qc: QcTally)
decode_bgzf_member(raw: bytes) -> bytes
parse_header(raw: bytes, *, expected_contigs: tuple[tuple[str,int],...],
             source_chrom: str, expected_samples: tuple[str,...]) -> HeaderEvidence
parse_record(raw: bytes, *, source_virtual_offset: int,
             header: HeaderEvidence) -> SourceRecord
site_disposition(record: SourceRecord, window: ReferenceWindow) -> str
assess_call(gt: str, gq: str, dp: str, ad: str) -> CallAssessment
count_variant(record: SourceRecord, columns: tuple[CohortColumn,...]) -> VariantCounts
check_native_interpretation(record: SourceRecord, columns: tuple[CohortColumn,...],
                            native: NativeVariantTokens) -> None

# Task 4, scripts/reference_window_io — adapters only
fetch_range(source: PublicObject, byte_range: ByteRange, *, wrapper: Path,
            artifact_root: Path, destination: Path) -> RangeReceipt
stage_sparse(source: SourceBytePlan, receipts: tuple[RangeReceipt,...], *,
             artifact_root: Path, index: ArtifactRef, sparse_path: str) -> VerifiedSource
validate_verified_source(verified: VerifiedSource, plan: SourceBytePlan, *,
                         artifact_root: Path) -> None
iter_original_records(verified: VerifiedSource, plan: SourceBytePlan,
                      window: ReferenceWindow, header: HeaderEvidence, *,
                      artifact_root: Path, raw_destination: Path,
                      offsets_destination: Path) -> Iterator[SourceRecord]
extract_native(verified: VerifiedSource, plan: SourceBytePlan,
               window: ReferenceWindow, *, artifact_root: Path, bcftools: Path,
               stdout_path: str, stderr_path: str) -> NativeRunReceipt
query_native_tokens(bcf: ArtifactRef, *, artifact_root: Path, bcftools: Path,
                     output_prefix: str) -> NativeTokenFiles
iter_native_tokens(query: NativeTokenFiles, *,
                   artifact_root: Path) -> Iterator[NativeVariantTokens]
native_called_totals(bcf: ArtifactRef, cohort_samples: ArtifactRef, *,
                     acquisition_root: Path, artifact_root: Path, bcftools: Path,
                     output_prefix: str) -> NativeCountFiles
iter_native_totals(control: NativeCountFiles, *,
                   artifact_root: Path) -> Iterator[tuple[str,int,int]]
# NativeCountFiles is specified below. Missing native AC/AN raises
# native_count_unavailable after raw stdout/stderr receipts have been retained.

# Task 5, reference_preparation
prepare_rows(window: ReferenceWindow, counts: tuple[VariantCounts,...], *,
             kind: Literal['called','quality']) -> tuple[ReferenceCount,...]
check_native_totals(counts: tuple[VariantCounts,...],
                    native: tuple[tuple[str,int,int],...]) -> None
validate_acquisition_window_accounting(expected_ids: tuple[str,...],
    receipts: tuple[AcquisitionWindowReceipt,...]) -> None
validate_preparation_window_accounting(expected_ids: tuple[str,...],
    receipts: tuple[PreparationWindowReceipt,...]) -> None
# Phase-specific writers/validators and full manifest records are defined below;
# validators return their phase-specific manifest, never a preflight or None.
```

`HashEntries` is the existing immutable tuple alias. Disposition/state strings above become runtime-validated Literals in their owning module. Header samples and cohort participant strings are private in memory/artifacts, never diagnostic message contents. Frozen real metadata/hash/cardinality qualification lives in `qualify_real_cohorts`; tiny hand fixtures exercise `select_cohorts` and domain functions without pretending to reproduce the real source. The CLI has no synthetic hash bypass flag. End-to-end synthetic tests inject validated synthetic inputs into composition functions, while separate CLI tests prove the real qualification wrapper cannot be bypassed.

## Shared verified-coverage, identity and process contract (normative design §4.1)

`stage_sparse` returns `VerifiedSource`, not None. It consumes the actual `RangeReceipt` tuple, verifies it exactly covers the source's reviewed merged plan, requires every receipt verified with a retained file, rehashes every complete range file and the retained index, writes sparse extents, and reads back/hashes those extents against the range files. `VerifiedSource.ranges` then lists the **actually acquired** source offsets and file hashes. It is not created from planned coordinates alone. The source pair/generations, exact logical size, index identity and actual extents must all match the reviewed source plan. Because the phase schema has no independently replayable sparse-stage failure receipt, a sparse construction/allocation failure aborts before final-manifest publication while leaving verified transport artifacts for diagnosis.

`validate_verified_source(verified, plan, artifact_root=...)` repeats these content/identity checks when a saved receipt is consumed: verify source identity and exact range union, each retained file size/hash, retained index size/checksums/SHA, sparse logical size, and SHA of **each populated extent** read from sparse storage. Never hash the complete logical sparse file. Source-root file paths are strictly relative, non-symlink and beneath the explicitly supplied root. The raw reader and native extractor invoke this validation before source reads, and the raw reader checks every header/block read interval against `VerifiedSource.ranges` as well as the upstream plan. Retained original range files are the authoritative read source for the raw iterator; it maps source offsets into their bounded file extents, so it cannot obtain bytes from sparse holes. Reuse the same open descriptors after verification, reject fstat identity/size changes during the operation, and mark files read-only after staging. This is integrity checking within the exclusive local run, not protection against a privileged adversary rewriting bytes concurrently. Native tools read only the already extent-verified sparse file, also read-only; no native remote URL or missing-index fallback is allowed.

The pure source record includes exact header sample IDs alongside tokens (the same immutable tuple can be shared across records). `cohort_columns` returns sample_id plus source sample_index. `check_native_interpretation` first checks each index/ID against `record.sample_ids`, then joins native IDs to tokens; no source index can index a native token vector. `NativeVariantTokens` requires unique IDs, equal ID/token length and exact variant identity. The expected native ID set is the cohort column ID set, without dropped, extra or forced samples. The actual native ordered sample IDs come from `query -l` on the **same content-hashed selected BCF** as `query -f`; `NativeTokenFiles` preserves both queried outputs and their invocation receipts. The iterator validates these files before yielding identity-carrying records. Reordering native columns is permitted only with the corresponding exact IDs; stale/swapped IDs refuse even if aggregate AC/AN happen to agree.

```text
# reference_cohorts.py and reference_vcf_tokens.py
CohortColumn(sample_id: str, sample_index: int, population: str, region: str)
SourceRecord(chrom: str, pos1: int, ref: str, alt: str, filter: str,
             format_keys: tuple[str,...], sample_ids: tuple[str,...],
             sample_tokens: tuple[str,...], source_virtual_offset: int, raw_sha256: str)
# reference_genotypes.py
NativeVariantTokens(variant_id: str, sample_ids: tuple[str,...], tokens: tuple[str,...])
check_native_interpretation(record: SourceRecord, columns: tuple[CohortColumn,...],
                            native: NativeVariantTokens) -> None
# scripts/reference_window_io.py; ArtifactRef paths resolve against artifact_root
fetch_range(source: PublicObject, byte_range: ByteRange, *, wrapper: Path,
            artifact_root: Path, destination: Path) -> RangeReceipt
stage_sparse(source: SourceBytePlan, receipts: tuple[RangeReceipt,...], *,
             artifact_root: Path, index: ArtifactRef, sparse_path: str) -> VerifiedSource
validate_verified_source(verified: VerifiedSource, plan: SourceBytePlan, *,
                         artifact_root: Path) -> None
iter_original_records(verified: VerifiedSource, plan: SourceBytePlan,
                      window: ReferenceWindow, header: HeaderEvidence, *,
                      artifact_root: Path, raw_destination: Path,
                      offsets_destination: Path) -> Iterator[SourceRecord]
extract_native(verified: VerifiedSource, plan: SourceBytePlan,
               window: ReferenceWindow, *, artifact_root: Path, bcftools: Path,
               stdout_path: str, stderr_path: str) -> NativeRunReceipt
query_native_tokens(bcf: ArtifactRef, *, artifact_root: Path, bcftools: Path,
                     output_prefix: str) -> NativeTokenFiles
iter_native_tokens(query: NativeTokenFiles, *,
                   artifact_root: Path) -> Iterator[NativeVariantTokens]
native_called_totals(bcf: ArtifactRef, cohort_samples: ArtifactRef, *,
                     acquisition_root: Path, artifact_root: Path, bcftools: Path,
                     output_prefix: str) -> NativeCountFiles
iter_native_totals(control: NativeCountFiles, *,
                   artifact_root: Path) -> Iterator[tuple[str,int,int]]
```

`extract_native` returns its complete/refused process receipt; successful BCF identity is `receipt.stdout`. `native_called_totals` resolves input_bcf under its explicit acquisition_root and the cohort list/outputs under artifact_root, validating both content references before spawning. It runs subset→fill-tags→sample-ID query→totals query, retaining each result/receipt in `NativeCountFiles`; it checks requested versus actual sample set and identity and never returns only unlabeled numbers. It may return a refused execution artifact after a native failure. `iter_native_totals` accepts only complete native artifacts, validates their hashes, then streams exact variant identity and integer AC/AN; missing native count tokens raise `native_count_unavailable` while their raw files/receipts remain retained. Only this final parser yields typed numeric tuples. `query_native_tokens` uses `output_prefix.samples.txt`, `.samples.stderr`, `.tokens.tsv`, `.tokens.stderr`; a failed first query sets token_query/tokens null and preserves its first receipt. A failed second query preserves both receipts and partial outputs. `iter_native_tokens` refuses any noncomplete query artifact; neither producer manufactures absent successful files.

Exact native subprocess ceilings: stdout is **2,147,483,648 bytes** for extraction/selection/fill-tags BCF and keys/tokens/totals queries, **1,048,576 bytes** for sample-ID queries and **65,536 bytes** for version/help queries. Stderr is **1,048,576 bytes per invocation** for every native or gcloud subprocess, including metadata. Native wall time is 1,800 seconds; metadata remains 120 seconds. Every native BCF/VCF output is streamed through stdout to the parent writer (omit native `-o`), so the same byte limiter covers artifacts and query text; no native command writes an uncapped output file behind the parent. Text line buffers have the 16,777,216-byte record ceiling. Metadata stdout remains 1 MiB and VCF body stdout remains requested range length plus the single overflow sentinel, independent of the native cap.

Drain stdout and stderr concurrently in bounded pieces to avoid pipe deadlock. At cap+1 on either stream, terminate the entire process group immediately and retain at most that stream's cap+1 observed bytes. Preserve the other stream's observed prefix and exact hash as well. End-state receipts set limit_exceeded true, state refused and reason limit_exceeded; timeout uses reason timeout. `.partial` suffixes remain on every incomplete native output. SHA/size describe exactly retained prefixes; no claim that all native output or stderr was observed. A zero exit after overflow cannot make the receipt complete. Success requires both streams uncapped, valid framing/row checks and zero exit. No retained stderr is printed in public reports; its private content hash and refusal reason are enough.

## Shared artifact contracts (normative design §6.1)

The following declarations freeze **every** JSON key and value type for the new manifest trees. They are constructor notation, not executable source. Implement frozen dataclasses; reject missing/extra keys, duplicate JSON keys, coercion, unknown Literal values and noncanonical bytes. Every declared field is emitted, including explicit null; there are no additional optional keys. Tuples encode as arrays in declared order, except `HashEntries` and fixed policy mappings encode as JSON objects after unique-key validation. Nested `SourcePair`, `PublicObject`, `ByteRange`, `SourceBytePlan` and their frozen wire shapes remain the reviewed #254 contracts; no alternate representation is introduced.

`Digest` means lowercase 64-character SHA-256; `Count` means exact int≥0 (bool disallowed); `RelPath` means a nonempty normalized POSIX path inside its artifact root (no absolute path, dot segments or symlinks). Content identity is the digest, never the path. `Stage` is exactly `technical_qc_4117|paper_ancestry_exclusion_4094`; `Kind` is `called|quality`. `Reason` is exactly `invalid_input|review_mismatch|metadata_mismatch|generation_unavailable|transfer_failed|size_mismatch|timeout|limit_exceeded|index_invalid|coverage_gap|header_invalid|sample_mismatch|record_invalid|native_encoding_refused|native_count_unavailable|native_mismatch|artifact_mismatch`. Nullable reasons must be null for successful states and a closed reason for refused states; not-attempted children inherit the ancestor refusal reason.

```text
# reference_acquisition_types.py — reusable file/process evidence and acquisition phase
ArtifactRef(path: RelPath, size_bytes: Count, sha256: Digest)
ReviewReceipt(schema_version: Literal['reference_preflight_review_v1'],
              manifest_sha256: Digest, preflight_sha256: Digest,
              implementation_revision: str, implementation_sha256: HashEntries,
              review_locator: str, review_sha256: Digest, status: Literal['accepted'])
CohortInputHashes(metadata: Digest, outliers: Digest, exclusions: Digest,
                  technical_samples: Digest, paper_samples: Digest, dependency_audit: Digest)
RunProvenance(code_revision: str, python_version: str,
              imported_source_sha256: HashEntries, tool_versions: tuple[tuple[str,str],...],
              executable_sha256: HashEntries, sdk_source_sha256: HashEntries)
AcquisitionInputs(window_manifest: ArtifactRef, windows: ArtifactRef,
                  preflight: ArtifactRef, review: ArtifactRef, cohort: CohortInputHashes)
RangeReceipt(chrom: str, generation: str, first: Count, last: Count,
             requested_bytes: Count, received_bytes: Count, adapter_invocations: Count,
             state: Literal['verified','partial','refused','not_attempted'],
             reason: Reason | None, sha256: Digest | None, retained: ArtifactRef | None,
             stderr: ArtifactRef | None, exit_code: int | None,
             stdout_limit_exceeded: bool, stderr_limit_exceeded: bool)
MetadataReceipt(state: Literal['verified','refused','not_attempted'], reason: Reason | None,
                adapter_invocations: Count, stdout_bytes: Count, retained: ArtifactRef | None,
                stderr: ArtifactRef | None, exit_code: int | None,
                stdout_limit_exceeded: bool, stderr_limit_exceeded: bool)
VerifiedRange(first: Count, last: Count, range_file: ArtifactRef)
VerifiedSource(source: SourcePair, ranges: tuple[VerifiedRange,...],
               sparse_path: RelPath, index: ArtifactRef,
               logical_size_bytes: Count, allocated_size_bytes: Count,
               full_object_verified: Literal[False])
HeaderReceipt(header: ArtifactRef, ordered_samples_sha256: Digest, sample_count: Count,
              sample_identity: Literal['exact_metadata_plus_control'],
              contig_identity: Literal['frozen_manifest_assembly_and_lengths'],
              required_formats: Literal['verified'])
NativeRunReceipt(operation: Literal['extract_bcf','query_keys','select_cohort','fill_tags',
                                   'query_samples','query_tokens','query_totals','version'],
                 argv_template: tuple[str,...], state: Literal['complete','refused'],
                 reason: Reason | None, exit_code: int | None,
                 stdout: ArtifactRef, stderr: ArtifactRef,
                 stdout_limit_bytes: Count, stderr_limit_bytes: Count,
                 stdout_limit_exceeded: bool, stderr_limit_exceeded: bool)
NativeTokenFiles(input_bcf: ArtifactRef, samples: ArtifactRef | None,
                 tokens: ArtifactRef | None, sample_query: NativeRunReceipt,
                 token_query: NativeRunReceipt | None,
                 state: Literal['complete','refused'], reason: Reason | None)
NativeCountFiles(input_bcf: ArtifactRef, requested_samples: ArtifactRef,
                  selected_bcf: ArtifactRef | None, recomputed_bcf: ArtifactRef | None,
                  selected_samples: ArtifactRef | None, totals: ArtifactRef | None,
                  runs: tuple[NativeRunReceipt,...], state: Literal['complete','refused'],
                  reason: Reason | None)
AcquisitionSourceReceipt(source: SourcePair, retained_index: ArtifactRef,
                         metadata: MetadataReceipt, ranges: tuple[RangeReceipt,...],
                         state: Literal['ready','refused'], reason: Reason | None,
                         verified: VerifiedSource | None, header: HeaderReceipt | None)
AcquisitionWindowReceipt(window_id: str, chrom: str,
                         state: Literal['records_acquired','no_records','refused'],
                         reason: Reason | None, raw_records: Count | None,
                         native_records: Count | None, raw: ArtifactRef | None,
                         offsets: ArtifactRef | None, native_bcf: ArtifactRef | None,
                         native_keys: ArtifactRef | None, native_runs: tuple[NativeRunReceipt,...])
AcquisitionTotals(planned_bytes_including_indexes: Count, retained_index_bytes: Count,
                   inherited_index_received_bytes: Count, vcf_requested_bytes: Count,
                   vcf_received_bytes: Count, range_adapter_invocations: Count,
                   metadata_adapter_invocations: Count, metadata_stdout_bytes: Count,
                   metadata_http_attempts: None, body_http_attempts: None, wire_bytes: None)
AcquisitionManifest(schema_version: Literal['reference_window_acquisition_v1'],
                    inputs: AcquisitionInputs, provenance: RunProvenance,
                    policy: tuple[tuple[str,str | int],...],
                    sources: tuple[AcquisitionSourceReceipt,...],
                    windows: tuple[AcquisitionWindowReceipt,...], files: tuple[ArtifactRef,...],
                    totals: AcquisitionTotals, complete: bool,
                    publication_eligible: Literal[False], p1_eligible: Literal[False],
                    benchmark_admitted: Literal[False])

# reference_genotypes.py — scientific QC records, also used by preparation manifests
MissingOriginCount(field: Literal['gt','gq','dp','ad'],
                   origin: Literal['literal_dot','omitted_trailing','absent_record_format'],
                   count: Count)
QcTally(dispositions: tuple[tuple[str,Count],...],
         inspection_totals: tuple[tuple[str,Count],...],
         missing_origins: tuple[MissingOriginCount,...])
VariantCounts(variant_id: str, populations: tuple[PopulationCount,...], qc: QcTally)

# reference_preparation_types.py — preparation phase only
PreparationInputs(acquisition: ArtifactRef, cohort: CohortInputHashes,
                   dependency_audit: ArtifactRef)
StageWindowSummary(sample_count: Count, population_count: Count, variants: Count,
                    rows: Count, called_unavailable: Count, quality_unavailable: Count,
                    called_ac_sum: Count, called_an_sum: Count,
                    quality_ac_sum: Count, quality_an_sum: Count,
                    native_ac_an_matches: Count, native_interpreted_calls: Count, qc: QcTally)
PreparationStageReceipt(stage: Stage, state: Literal['complete','refused','not_attempted'],
                        reason: Reason | None, summary: StageWindowSummary | None,
                        native_control: NativeCountFiles | None,
                        native_tokens: NativeTokenFiles | None)
PreparationWindowReceipt(window_id: str, chrom: str,
                          state: Literal['counts_prepared','no_records','no_pass_snps','refused'],
                          reason: Reason | None, raw_records: Count | None,
                          retained_variants: Count | None,
                          site_dispositions: tuple[tuple[str,Count],...] | None,
                          stages: tuple[PreparationStageReceipt,...])
TrackSummary(stage: Stage, kind: Kind, table: ArtifactRef, dependencies: ArtifactRef,
              rows: Count, variants: Count, represented_groups: Count,
              unavailable_rows: Count, ac_sum: Count, an_sum: Count)
PreparationManifest(schema_version: Literal['reference_window_counts_v1'],
                    inputs: PreparationInputs, provenance: RunProvenance,
                    policy: tuple[tuple[str,str | int],...],
                    windows: tuple[PreparationWindowReceipt,...],
                    tracks: tuple[TrackSummary,...], files: tuple[ArtifactRef,...],
                    status: Literal['complete_nonempty','complete_empty','refused'],
                    complete: bool, publication_eligible: Literal[False],
                    p1_eligible: Literal[False], benchmark_admitted: Literal[False])
DependencyEvidence(schema_version: Literal['reference_population_dependencies_v1'],
                    stage: Stage, populations: tuple[str,...],
                    edges: tuple[tuple[str,str],...], reported_pairs: Count,
                    component_count: Count, audit_sha256: Digest,
                    qualification: Literal['reported_edges_only_shared_source_dependence_remains'])
```

The acquisition `policy` object has exactly these key/value pairs (numeric values are ints): `schema_version="reference_acquisition_policy_v1"`, `request_attempt_accounting="wrapper_invocations"`, `storage_body_max_retries=0`, `metadata_http_attempts="unobserved"`, `max_transfer_bytes=26843545600`, `metadata_timeout_seconds=120`, `range_timeout_seconds=1800`, `native_timeout_seconds=1800`, `metadata_stdout_limit_bytes=1048576`, `native_stdout_limit_bytes=2147483648`, `native_sample_stdout_limit_bytes=1048576`, `native_version_stdout_limit_bytes=65536`, `stderr_limit_bytes=1048576`, `header_limit_bytes=8388608`, `record_limit_bytes=16777216`, `decoded_window_limit_bytes=2147483648`, `records_per_window_limit=1000000`, `bgzf_block_limit_bytes=65536`, `transfer_piece_limit_bytes=1048576`, `sparse_allocation_slack_bytes=16777216`, `source_complete="false"`.

The preparation `policy` object has exactly `schema_version="reference_preparation_policy_v1"`, `count_contract="pilot_stage_qc_semantics_unchanged_v1"`, `pos_selection="start0_lt_pos_le_end0"`, `site_selection="PASS_distinct_biallelic_uppercase_ACGT"`, `missingness="vcf42_explicit_origin_lazy_qc"`, `native_counts="exact_called_cohort_totals_missing_refuses"`, `native_timeout_seconds=1800`, `native_stdout_limit_bytes=2147483648`, `native_sample_stdout_limit_bytes=1048576`, `native_version_stdout_limit_bytes=65536`, `stderr_limit_bytes=1048576`, `record_limit_bytes=16777216`, `records_per_window_limit=1000000`. Policies are sorted unique immutable pairs in memory. No caller can relax their values.

Exact array sets/orders: sources and indexes use natural chr1–chr22; both window arrays use frozen manifest order and have exactly 66 entries. Every preparation window has exactly two stage receipts, technical then paper, even on failure. Stage native_control/native_tokens explicitly bind complete or partial native artifacts; no filename matching is used to infer their role. NativeCountFiles.input_bcf is the one parent-acquisition-root reference; all of its other ArtifactRefs and NativeTokenFiles.input_bcf resolve inside preparation. A complete nonempty stage requires complete control/token artifacts with native_tokens.input_bcf equal to native_control.selected_bcf. Empty stages carry null native artifacts and zero tested variants, not a synthetic native success. Complete manifests have four tracks ordered technical-called, technical-quality, paper-called, paper-quality; refused preparation has **zero admitted tracks** and retained partial products only in `files`. File inventories are path-sorted, unique, include every scientific file/partial file and every native stdout/stderr mentioned by nested records in that phase root (parent-acquisition input_bcf is validated against acquisition_root instead), and exclude only the manifest being written and sparse logical files represented by their exact range evidence. Repeated references to one file are permitted only with identical size/hash. Runtime evidence is inventoried like every other retained file. No sparse logical-file checksum appears in `files`; its actual range evidence and verified-source record are the identity. Runtime native `.partial` stdout/stderr files have hashes of their exact retained bytes, never a claim of complete native output.

Acquisition success requires all sources ready and all window states successful, even if all windows have no records. `verified` exists only after exact all-range/index/sparse validation; `header` exists only after header qualification. Retain verified coverage if later header failure refuses that source. A refused window may retain complete intermediate raw/native files and known counts, but no consumer may admit it; unknown counts remain null. `no_records` requires raw/native counts exactly zero, complete source qualification and complete native execution; required empty raw/offset files and header-only BCF still have real ArtifactRefs. All range receipts exist, including not-attempted planned ranges after metadata failure. Totals sum receipts exactly, while planned bytes equal the reviewed preflight total and retained-index sum counts each of 22 bodies once.

Range/metadata adapter_invocations is exactly 0 or 1. Not-attempted receipts have zero requested/received/stdout bytes, null retained/stderr/exit_code fields, and both overflow flags false. For attempted ranges requested_bytes=last−first+1, received_bytes≤requested_bytes+1 and retained.size_bytes=received_bytes with sha256=retained.sha256; retain even a zero-byte attempted stdout file. Attempted metadata retains stdout with size=stdout_bytes≤1,048,577. Every attempted transport invocation retains stderr, with size≤1,048,577; exit_code records the observed exit or is null only when unavailable. Range verified/metadata verified requires exact requested range length or qualified metadata respectively, zero exit and no overflow. Partial/refused receipts carry the failure reason and exact retained-prefix evidence; both are non-admissible. Any overflow requires limit_exceeded reason and refusal even after zero exit. Aggregate received/stdout totals include retained failed prefixes; they never represent unobserved output.

Preparation success requires both stage receipts complete for all 66 windows, identical four-table keys, valid dependency evidence and native controls. For `no_records`/`no_pass_snps`, both stage summaries explicitly have zero variants/rows/matches/interpreted calls and empty QC tally; this is absence of selected sites, not independent per-site validation. `counts_prepared` can have all rows AN=0. Native missing totals refuse the stage/window. A refused stage has null summary; any partially computed counts remain unadmitted artifacts in `files`. If either stage refuses, the window refuses, `retained_variants` is null and every stage summary is withdrawn; a known `raw_records` remains bound to the acquisition parent and completed native process artifacts remain retained but unadmitted. `complete_empty` requires no retained variants anywhere and four actual header-only tables; represented_groups=0. Complete nonempty tracks have 80 represented groups and rows=80×variants. This keeps unknown/refused content separate from scientifically empty output.

QC keys are closed: dispositions are exactly the eight original names (`accepted`, `missing_gt`, `missing_gq`, `low_gq`, `missing_dp`, `low_dp`, `missing_het_ad`, `low_het_balance`); inspection keys are exactly `gt,gq,dp,ad_missing,ad_arity,ad_ref,ad_alt`. Stored tuples contain only positive counters, sorted by key, with missing keys meaning **zero observed visits** inside an otherwise validated complete tally, never missing evidence. Constructor checks require gt visits=all dispositions, gq visits=all dispositions except missing_gt, dp visits=gq visits minus missing_gq/low_gq; AD counters require ad_arity=ad_missing−missing_het_ad, ad_ref=ad_arity, 0≤ad_alt≤ad_ref, ad_ref−ad_alt≤low_het_balance, and 0≤ad_ref−low_het_balance≤accepted. These aggregate identities alone cannot recover each genotype; the count function and artifact content validator also recompute actual traces from the source calls. Missing-origin entries are sorted unique (field,origin), positive, and reconcile exactly with the corresponding missing disposition. A visited partial AD dot token is `literal_dot`; an unvisited QC field contributes no missing-origin count. Count/AN identities and nonzero allele-balance visits further constrain the tally; pure constructor checks reject absent coverage when calls were present. Per-variant `QcTally` and accumulated stage/window tally use the same public type, so the writer cannot invent coverage after counting.

RunProvenance uses a 40-hex code revision, unique relative source paths and SHA hashes; tool_versions/executable keys include bcftools, bcftools_fill_tags, bcftools_htslib, tabix, bgzip, gcloud for acquisition and bcftools/bcftools_fill_tags/bcftools_htslib for preparation. Dynamic library/plugin file hashes use relative labeled entries in executable_sha256; SDK hashes use SDK-relative paths; preparation sdk_source_sha256 is the empty tuple because its parent acquisition carries transport evidence. No absolute process environment or local paths enter argv_template: executable is a tool label, each input/output argument is an artifact-root-relative path, an explicit `@acquisition/`-prefixed relative parent input, or a literal frozen region/format argument. Execution resolves these templates to absolute paths privately; no absolute path is serialized.

## Shared sidecar and writer contracts (normative design §6.2)

Every TSV has precisely the columns below, tabs/LF and canonical decimal counts. In acquisition `windows.tsv`: `window_id,chrom,state,reason,raw_records,native_records`; preparation `windows.tsv`: `window_id,chrom,state,reason,raw_records,retained_variants`. Nullable fields use literal `NA` and are permitted only where their typed counterpart is null; this sentinel never enters a count input. These TSV values must equal their manifest records.

`variant-windows.tsv` has the seven columns already declared. `qc-dispositions.tsv` is long-form with `window_id,stage,category,key,origin,count`: category is `disposition|inspection|missing_origin`; origin is `NA` for the first two categories and the closed missing origin for the third; key is the appropriate closed reason/inspection/field. Only positive entries from complete stage summaries are emitted. `native-controls.tsv` has `window_id,stage,state,variants,native_ac_an_matches,native_interpreted_calls`; refused/not-attempted stage quantities are `NA`, never zeros. `record-offsets.tsv` has `ordinal,source_virtual_offset,raw_sha256`; ordinal starts at 0 and advances only for emitted POS-selected original lines. It is content-validated against the exact original-line file, source window and acquired coverage.

Four count TSVs retain the unchanged `ReferenceCount` columns. Two dependency JSONs encode `DependencyEvidence` exactly. Preparation `inputs.json` encodes `PreparationInputs` exactly. Both phase roots retain exact private cohort input files under `inputs/cohort/`: `metadata.tsv`, `outliers.txt`, `exclusions.json`, `technical.samples.txt`, `paper.samples.txt`, `dependency-audit.json`, corresponding respectively to CohortInputHashes fields. These six fixed relative files are included in the inventory and rehashed/reparsed by validators, enabling reproducible identity/QC checks rather than leaving only inaccessible input digests. Preparation additionally copies the acquisition manifest into `inputs/acquisition.json`; its dependency_audit reference equals `inputs/cohort/dependency-audit.json`. The separate acquisition root is passed explicitly for deep content validation, not encoded as an absolute local path or silently located by a filename convention.

```text
# reference_acquisition_codec.py and reference_preparation_codec.py — pure codecs
encode_acquisition(value: AcquisitionManifest) -> bytes
decode_acquisition(raw: bytes) -> AcquisitionManifest
encode_preparation(value: PreparationManifest) -> bytes
decode_preparation(raw: bytes) -> PreparationManifest

# scripts/reference_window_artifacts.py — thin filesystem adapters; no native/network calls
write_acquisition_manifest(directory: Path, manifest: AcquisitionManifest, *,
                           preflight: BytePreflight,
                           cohort_inputs: QualifiedCohortInputs | None = None) -> ArtifactRef
validate_acquisition(directory: Path, *,
                     cohort_inputs: QualifiedCohortInputs | None = None) -> AcquisitionManifest
write_preparation_manifest(directory: Path, manifest: PreparationManifest, *,
                           acquisition_root: Path,
                           cohort_inputs: QualifiedCohortInputs | None = None) -> ArtifactRef
validate_preparation(directory: Path, *, acquisition_root: Path,
                     cohort_inputs: QualifiedCohortInputs | None = None) -> PreparationManifest
```

Each writer is called on an already exclusively created directory after artifact-producing steps, validates typed contents, existing-file hashes/sizes, exact file inventory, semantic sidecar/table counts and parent binding **before** exclusively writing its final manifest. It fsyncs/closes the manifest and returns its external ArtifactRef. It never creates an accepted review or changes complete/refused states to hide a failed check. Handled source, window, token and native failures after work begins receive a terminal manifest; an implementation-source identity change or storage write/fsync failure aborts without one because the writer cannot attest its own code or durable evidence. Validators re-read canonical bytes and all referenced real content; hashes alone do not certify row semantics. `validate_acquisition` redecodes its copied upstream manifest/preflight/review and revalidates retained indexes and actual coverage; its returned AcquisitionManifest contains verified source receipts for the caller. `validate_preparation` binds its copied acquisition-manifest hash to `acquisition_root/acquisition.json`, deeply validates that root and rechecks all four tables, exact row/site/window alignment, QC counts and dependency sidecars. Refused manifests may be decoded/validated as truthful ledgers but are rejected by acquisition→preparation consumers unless complete. Missing final manifests are never valid inputs.

## Task 1: Validate the reviewed immutable preflight before I/O

**Scientific contract:** establish that acquisition would use the same outcome-independent window/source plan; acceptance is adversarial canonical/hash/byte-plan tests with no requests. Pure preflight/review codecs expose the accepted `BytePreflight`; incomplete/mismatched plans refuse and acquisition is the consumer.

**Files:** create Task 1 modules and `tests/test_reference_preflight_input.py`, initial `tests/reference_acquisition_fixture.py`. Use upstream public types/functions without editing their workspace.

**Interfaces:**

```text
decode_reviewed_preflight(raw: bytes, *, manifest: WindowManifest,
                          manifest_raw: bytes, indexes: tuple[RetainedIndex,...],
                          review: ReviewReceipt) -> BytePreflight
```

Implement the complete validation steps below.

- [x] **RED: bind source identity and actual bytes.** Create `synthetic_preflight_case()` in the test helper returning `(manifest, manifest_raw, preflight_raw, indexes, review)`. It builds valid 22×3 synthetic source pairs using the upstream frozen config/window helpers, tiny test-only BGZF/TBI bytes for each expected contig using the upstream synthetic binary fixture idiom, explicit source object lengths/checksums and actual index SHA receipts; its manifest evidence kind is `synthetic_fixture`. Geometry still uses the real fixed-width rules, with synthetic 100,000-base autosome lengths. Use `assemble_preflight`/`encode_preflight` to encode the input, not to compute the assertion's expected byte union. Use empty ordinary-bin/chunk lists in this decoder fixture, one reference name equal to each source chromosome, VCF object size 2,097,152 and no unmapped records. Hand-enumerated first source ranges are `[0,1048575]` and `[2097124,2097151]`; all 66 window states are no_index_chunks. Native coverage evidence is a separate Task4 fixture; these codec tests run without native tools.

```python
from dataclasses import replace
import pytest
from genomeos.validation.reference_preflight_input import decode_reviewed_preflight
from tests.reference_acquisition_fixture import synthetic_preflight_case

def test_review_hash_mismatch_refuses_before_acquisition():
    manifest, raw_manifest, raw, indexes, review = synthetic_preflight_case()
    wrong = replace(review, preflight_sha256='0' * 64)
    with pytest.raises(ValueError, match='review'):
        decode_reviewed_preflight(raw, manifest=manifest, manifest_raw=raw_manifest,
                                  indexes=indexes, review=wrong)

def test_corrupt_retained_index_refuses():
    manifest, raw_manifest, raw, indexes, review = synthetic_preflight_case()
    broken = (replace(indexes[0], raw=indexes[0].raw[:-1]), *indexes[1:])
    with pytest.raises(ValueError, match='index'):
        decode_reviewed_preflight(raw, manifest=manifest, manifest_raw=raw_manifest,
                                  indexes=broken, review=review)
```

- [x] **RED: canonical/refusal coverage.** Parameterize raw JSON mutation cases with actual input transformations: `raw.replace(b'"complete":true', b'"complete":false')`; duplicate `schema_version` key; UTF-8 corruption; `NaN`; source generation digit changed; one extra range byte; omitted source/window; eligibility `true`; receipt `received_bytes=True`; noncanonical trailing space. Rehash the review where needed so deeper content checks are exercised, not always just review mismatch. Assert each refuses. Add relocation test with identical bytes/identities accepted; wrong retained index filename cannot rescue wrong bytes.
- [x] **Run RED:** `PYTHONPATH=. python -m pytest tests/test_reference_preflight_input.py -q`; expect missing new module/function, then substantive failures as stubs are replaced.
- [x] **GREEN: implement exact decoder.** Strict JSON loader uses `object_pairs_hook` duplicate rejection and `parse_constant` refusal; each level compares exact keys before constructing immutable upstream types. Verify `encode_preflight(parsed)==raw`, manifest/raw/window/review hashes and false flags. Recompute source windows through `parse_tbi`→`plan_window`, fixed prefix/EOF and `merge_byte_ranges`; reconstruct via `assemble_preflight` with original provenance and compare the complete encoding. Verify size/MD5/CRC32C/SHA of retained bytes before parsing. Reject unexpected/missing indexes even when a window has no chunks. Verify review source-map and current executed-source-map equality in composition, before networking. No private `_object_payload` import.

```python
# Critical recomputation shape inside the implementation:
rebuilt_windows = tuple(
    plan_window(index, window, source_size_bytes=source.vcf.size_bytes)
    for window in manifest.windows if window.chrom == source.chrom
)
if rebuilt_windows != supplied.windows:
    raise ValueError('index-derived window plan mismatch')
# Rebuild merged ranges and full preflight through the public upstream functions.
```

- [x] **GREEN/gates:** rerun this focused file; `PYTHONPATH=. python scripts/smoke.py`; `python scripts/check_module_size.py`; `python scripts/check_private_files.py`. Record outputs and independently review task. Inspect staged paths, then commit only these new code/synthetic files: `git commit -m "feat: validate reviewed reference preflight inputs; advance #255"`.

## Task 2: Reconstruct the exact two cohorts and source-order population join

**Scientific contract:** preserve release-defined participant stages and literal grouping; acceptance is exact real hash/list qualification plus synthetic identity/exclusion controls. Pure cohort selection and column mapping produce typed cohorts; missing labels, ambiguous region, wrong lists or exclusions refuse, and all chromosomes/counts consume those results.

**Files:** create `reference_cohorts.py`, `tests/test_reference_cohorts.py`; do not package real participants.

**Interfaces:** Task 2 declarations above; `select_cohorts` is cardinality-agnostic for small tests; `qualify_real_cohorts` imposes every design §2 hash/cardinality, with no override argument. `cohort_columns` maps retained source sample indices in actual header order and refuses missing/duplicate samples.

- [x] **RED: hand cohort, collisions and reordering.**

```python
import pytest
from genomeos.validation.reference_cohorts import (
    Sample, CohortExclusions, select_cohorts, cohort_columns,
)

def test_literal_groups_and_reordered_header():
    samples = (
        Sample('s1', 'Han', 'r1', False),
        Sample('s2', 'NorthernHan', 'r1', False),
        Sample('s3', 'PapuanHighlands', 'r2', False),
        Sample('s4', 'PapuanSepik', 'r2', False),
        Sample('hard', 'Han', 'r1', True),
        Sample('bad1', 'Han', 'r1', False),
        Sample('bad2', 'Han', 'r1', False),
    )
    technical, paper = select_cohorts(samples, CohortExclusions('control', ('bad1','bad2')),
                                      ('s2',))
    assert [s.sample_id for s in technical.samples] == ['s1','s2','s3','s4']
    assert [s.sample_id for s in paper.samples] == ['s1','s3','s4']
    header = ('s4','bad1','s2','control','s1','s3','hard','bad2')
    actual = cohort_columns(header, technical)
    assert [(c.sample_id,c.sample_index,c.population) for c in actual] == [
        ('s4',0,'PapuanSepik'),('s2',2,'NorthernHan'),
        ('s1',4,'Han'),('s3',5,'PapuanHighlands')]

@pytest.mark.parametrize('outliers', [('unknown',), ('s1','s1')])
def test_bad_outlier_identity_refuses(outliers):
    samples = (Sample('s1','p','r',False),Sample('bad1','p','r',False),
               Sample('bad2','p','r',False))
    with pytest.raises(ValueError):
        select_cohorts(samples, CohortExclusions('control',('bad1','bad2')),outliers)
```

- [x] **RED:** add exact-byte hash mutation tests for each real input using `qualify_real_cohorts(b'changed', ...)`, all supplied byte arguments explicit; assert hash refusal occurs before CSV projection. Add synthetic cases for duplicate metadata ID, contamination absent/duplicated/overlapping hard set, control inside metadata, blank/`NA`/trimmed population, inconsistent region within population, repeated source header sample and missing cohort member. Assert no exception exposes sample tokens.
- [x] **Run RED:** `PYTHONPATH=. python -m pytest tests/test_reference_cohorts.py -q`; expect missing implementation then exact failures.
- [x] **GREEN:** project the four declared TSV columns without touching coordinates; reject duplicate columns/row IDs and invalid literal flags. `select_cohorts` uses disjoint exact sets and sorted literal IDs. `qualify_real_cohorts` verifies the five frozen input hashes before parsing, reconstructs 4,117/4,094 lists and compares exact bytes, checks 80 groups and known collisions, and freezes hashes of original and projected content. The private recipe's exact three keys/schema/hash are mandatory. Outlier 23 uniqueness/membership is checked before subtraction. Column mapping uses a source-local ID→index map; never reuse chromosome-one positions.

```python
technical_ids = metadata_ids - hard_ids - set(exclusions.contamination_ids)
if not set(outliers) <= technical_ids or len(set(outliers)) != len(outliers):
    raise ValueError('invalid release outlier membership')
paper_ids = technical_ids - set(outliers)
# Both Cohort.samples tuples are sorted by exact sample_id, not population display name.
```

- [x] **GREEN/gates/review:** focused tests, smoke, module size and privacy; inspect staged paths; commit `feat: preserve exact reference cohort identities; advance #255`. During actual evidence run, the controller performs the local hash/list check and reports only counts/hashes. Synthetic tests are not a claim that real reconstruction was rerun by this implementation.

## Task 3: Preserve original genotype/QC tokens and count arithmetic

**Scientific contract:** derive the same called/quality dosage target without native normalization or missingness substitution. Acceptance is hand-calculated dosage/count/disposition/inspection controls and bounded codec tests. Pure codecs and count functions produce typed counts; structural/malformed encountered values refuse; preparation/native comparison consume the results.

**Files:** create `reference_vcf_tokens.py`, `reference_genotypes.py` and corresponding test files. Split BGZF codec to `reference_bgzf.py` if needed to keep ≤500 logical lines; then update imported-source provenance and tests explicitly.

**Interfaces:** Task 3 declarations above. `site_disposition` returns `outside_pos`, `not_pass`, `not_biallelic`, `not_acgt_snp` or `retained`. `assess_call` returns design §5's closed reasons and inspection trace, with no extra eager conversion.

- [x] **RED: exact lazy tree.**

```python
import pytest
from genomeos.validation.reference_genotypes import assess_call

@pytest.mark.parametrize('tokens,dosage,reason', [
    (('.', 'bad','bad','bad'),None,'missing_gt'),
    (('./.','bad','bad','bad'),None,'missing_gt'),
    (('0|1','20','10','2,8'),1,'accepted'),
    (('1/0','20','10','8,2'),1,'accepted'),
    (('1/1','20','10','bad'),2,'accepted'),
    (('0/1','.','bad','bad'),1,'missing_gq'),
    (('0/1','19','bad','bad'),1,'low_gq'),
    (('0/1','20','.','bad'),1,'missing_dp'),
    (('0/1','20','9','bad'),1,'low_dp'),
    (('0/1','20','10','.,bad,extra'),1,'missing_het_ad'),
    (('0/1','20','10','1,bad'),1,'low_het_balance'),
    (('0/1','20','10','8,1'),1,'low_het_balance'),
])
def test_preserved_lazy_dispositions(tokens,dosage,reason):
    answer = assess_call(*tokens)
    assert (answer.dosage,answer.disposition) == (dosage,reason)

@pytest.mark.parametrize('tokens', [
    ('0/.','20','10','2,8'),('1','20','10','2,8'),('0/1/1','20','10','2,8'),
    ('0/2','20','10','2,8'),('0/1','-1','10','2,8'),
    ('0/1','20','x','2,8'),('0/1','20','10','2,bad'),
    ('0/1','20','10','2,8,0'),('0/1','20.0','10','2,8'),
])
def test_encountered_invalid_encodings_refuse(tokens):
    with pytest.raises(ValueError): assess_call(*tokens)

def test_inspection_coverage_is_truthful():
    assert assess_call('.','bad','bad','bad').inspected_fields == ('gt',)
    assert assess_call('1/1','20','10','bad').inspected_fields == ('gt','gq','dp')
    assert assess_call('0/1','20','10','1,bad').inspected_fields == (
        'gt','gq','dp','ad_missing','ad_arity','ad_ref')
```

- [x] **RED: native sample identity survives independent reordering.**

```python
from dataclasses import replace
import pytest
from genomeos.validation.reference_cohorts import CohortColumn
from genomeos.validation.reference_vcf_tokens import SourceRecord
from genomeos.validation.reference_genotypes import NativeVariantTokens, check_native_interpretation

def test_native_tokens_join_by_id_not_source_index():
    record = SourceRecord('chr1',101,'A','G','PASS',('GT','GQ','DP','AD'),
                          ('s1','s2'),('0/0:20:10:.','1/1:20:10:.'),1<<16,'a'*64)
    columns = (CohortColumn('s1',0,'p','r'),CohortColumn('s2',1,'p','r'))
    reverse = NativeVariantTokens('GRCh38:chr1:101:A:G',('s2','s1'),
                                  ('1/1:20:10:.','0/0:20:10:.'))
    check_native_interpretation(record, columns, reverse)
    # Cohort total AC stays 2, but stale labels attach each GT to the wrong person.
    with pytest.raises(ValueError):
        check_native_interpretation(record, columns,
                                    replace(reverse, sample_ids=('s1','s2')))
    with pytest.raises(ValueError):
        check_native_interpretation(record,
                                    (replace(columns[0],sample_id='s2'),columns[1]),reverse)
```

Add duplicate/missing/extra native IDs, wrong variant ID and token/ID length mismatch refusals. `count_variant` also checks each source ID/index against record.sample_ids, so the identity requirement applies before Python aggregation as well as before native comparison.
- [x] **RED: literal population count control.** Construct `SourceRecord('chr1',101,'A','G','PASS',('GT','GQ','DP','AD'),('s1','s2','s3','s4'),('0/1:20:10:2,8','1/1:19:20:.','./.:.:.:.','0/0:20:10:.'),1<<16,'a'*64)` and columns `(CohortColumn('s1',0,'p1','r'),CohortColumn('s2',1,'p1','r'),CohortColumn('s3',2,'p2','r'),CohortColumn('s4',3,'p2','r'))`. Assert p1 `(called_ac,called_an,quality_ac,quality_an)=(3,4,1,2)` and p2 `(0,2,0,2)`; remove its last column and assert p2 `(0,0,0,0)`, retained. Assert `sum(n for _, n in result.qc.dispositions)` equals cohort size and missing_origins contains exactly the visited missing GT evidence. Repeat with sample/column permutation to prove mapping, and with REF/ALT reversed plus GT complemented to assert orientation changes explicitly rather than being inferred.
- [x] **RED: record/header/BGZF controls.** Use literal synthetic VCF bytes with exact header FORMAT declarations. Test POS at `start0`, `start0+1`, `end0`, `end0+1`; `PASS` versus `.`; `A/G` versus `A/G,T`, `N/G`, `A/A`; duplicate FORMAT names and nonfirst GT; valid absent-record-GT with missing-origin evidence; legal trailing QC omission versus literal `.` versus absent record QC key; empty interior/extra sample subfields; reordered QC FORMAT `GT:DP:AD:GQ`; source contig/length/assembly mismatch; duplicate header IDs; unsupported FORMAT Number/Type. In the tiny native BGZF fixture, flip CRC, truncate header/trailer, forge ISIZE, duplicate BC subfield, and encode an over-expanding member; assert refusal before unbounded allocation. Use a synthetic multi-block record  >65,536 bytes and under 16 MiB to establish cross-block support. Hand test a 17 MiB line refusal and uncompressed header limit.

- [x] **RED: VCF-defined missingness controls.**

```python
from genomeos.validation.reference_vcf_tokens import project_call

def test_trailing_omission_is_explicit_missing_evidence():
    a = project_call(('GT','GQ','DP','AD'), '0/1:20:10')
    assert (a.gt,a.gq,a.dp,a.ad) == ('0/1','20','10','.')
    assert dict(a.presence)['ad'] == 'omitted_trailing'
    b = project_call(('GT','DP','AD'), '0/1:10:2,8')
    assert b.gq == '.' and dict(b.presence)['gq'] == 'absent_record_format'
    assert assess_call(a.gt,a.gq,a.dp,a.ad).disposition == 'missing_het_ad'
    assert assess_call(b.gt,b.gq,b.dp,b.ad).disposition == 'missing_gq'
```

Add refusal cases `0/1::10:2,8`, `0/1:20:10:2,8:extra`, nonfirst GT, a dropped declared-GT sample token and a truncated record without LF. Add absent-record-GT projection to `missing_gt` with `absent_record_format` origin; this is valid VCF missingness, while missing native AC/AN subsequently refuses `native_count_unavailable`. The specification supports missingness projection, not malformed-token replacement. Native test fixture: one PASS A/G site with `FORMAT=GQ:DP:AD`, sample tokens `20:10:2,8` and `30:12:6,6`, and a second PASS A/C site with `FORMAT=GT:GQ:DP:AD`, samples `./.:20:10:2,8` and `.:30:12:6,6`. Native query must render absent GT as `.`, but +fill-tags must leave first-site AC/AN missing and return second-site 0/0 with 1.23.1. Assert the first cannot pass native-count validation; the second retains AN=0 cells. Preserve fixture bytes/native outputs/hashes.

- [x] **Run RED:** `PYTHONPATH=. python -m pytest tests/test_reference_vcf_tokens.py tests/test_reference_genotypes.py -q`.
- [x] **GREEN: implement frozen tree with explicit trace.** Parse natural integers with full-match `[0-9]+` only at visited nodes. The heterozygote loop is deliberately left-to-right and exits at first low balance; do not preparse AD into integers. Missing AD detection precedes arity. Implement bounded member decompression with `zlib.decompressobj` and output limit 65,537, then require EOF/no unused data/CRC/ISIZE. Parse selected records with exact 9+sample_count columns. Require unique FORMAT keys, GT first whenever present; enforce 1..FORMAT-length nonempty sample subfields and no dropped declared GT. `project_call` preserves literal lexemes, marks VCF-defined trailing omissions/absent record QC keys as explicit missing-origin evidence and supplies `.` to the unchanged scientific parser when needed. No interior empty token/extra field/dropped declared GT is repaired. Absent record GT projects to explicit `missing_gt`; no dosage is invented. Project QC by name, never assume its order. Count all populations even when AN=0; assert source IDs/indices match record.sample_ids, accumulate exact QcTally traces and visited MissingOriginCount entries, and apply integer subset/evenness/disposition identities.

```python
# The actual heterozygote acceptance predicate, after missingness/arity checks:
for field, token in zip(('ad_ref','ad_alt'), ad.split(','), strict=True):
    inspected.append(field)
    if natural(token) * 5 < depth:
        return CallAssessment(dosage, 'low_het_balance', tuple(inspected))
return CallAssessment(dosage, 'accepted', tuple(inspected))
```

Implement `check_native_interpretation` by assessing original tokens first, then comparing only its visited nodes with separately queried native values/missing states. Canonical numeric rendering may differ lexically while preserving the exact integer. Original malformed visited tokens refuse before comparison; native conversion of an original integer to `.` refuses. Add hand controls for original `020` versus native `20` equivalence, original large integer versus native `.` refusal, and a homozygote AD field remaining uninspected. The native typed record carries exact native sample IDs and equally long tokens; compare its variant_id to the source record, require duplicate-free native IDs whose set equals the source-column sample IDs, and build native ID→token lookup. First require record.sample_ids[column.sample_index]==column.sample_id for every column, with unique in-bounds source indices and IDs. For each source CohortColumn read original sample_tokens[sample_index] and native_by_id[sample_id]. Never reuse source indices on native tokens. The producer reads IDs with native query -l from the same hash-bound selected BCF, and the query artifact records both file hashes. Both IDs and tokens remain private.

- [x] **GREEN/gates/review:** both focused files, smoke, module size, privacy; inspect staged files; commit `feat: preserve original reference genotype count semantics; advance #255`. Review specifically checks old parser decision ordering and explicit validation coverage, not just numeric happy paths.

## Task 4: Acquire bounded ranges and prove original/native extraction coverage

**Scientific contract:** acquire exactly the approved source bytes and recover selected records without sparse-hole fabrication. Acceptance is wrapper fault tests, byte-accounting controls and full synthetic native-source versus sparse-source identity. Adapters produce range/window receipts and original/native files; incomplete requests/coverage/encoding refuse; Task5 consumes only qualified outputs.

**Files:** create `scripts/reference_window_io.py`, `tests/test_reference_window_io.py`, complete synthetic helper and `tests/fixtures/reference_acquisition/native/`. No network/native dependencies enter scientific modules. Adopt the controller-approved #254 transport policy amendment verbatim.

**Interfaces:** Task4 declarations above; local internal process helpers may be private to this adapter only. Freeze SDK 574.0.0 trace described in report; no monkeypatch of the installed SDK in production and no generic client framework.

- [x] **RED: wrapper fault control.** Create a test-local executable wrapper Python file that receives normal `run storage cat --range=... URI#GEN` arguments, appends only argv to a temporary invocation ledger, then writes a controlled byte body. It must reject unpinned URLs and assert `CLOUDSDK_STORAGE_MAX_RETRIES=='0'`. Use monkeypatch only to shorten private test timeout, never a real CLI override.

```python
# Content written into tests' temporary wrapper; fake data, no network.
import os, sys
assert os.environ['CLOUDSDK_STORAGE_MAX_RETRIES'] == '0'
assert sys.argv[1:4] == ['run','storage','cat']
assert '#' in sys.argv[-1]
sys.stdout.buffer.write(b'abc')
```

Test requested range `[10,12]` gives requested=received=3, adapter_invocations1 and SHA256(b'abc'). `[10,13]` gives partial/size mismatch, never verified. `[10,11]` emits the overflow sentinel and refuses. Nonzero exit after partial stdout retains exactly observed bytes and hash; timeout kills descendants; no second invocation. Existing destination refuses before spawn. Large stream test generates 64 MiB in 1 MiB blocks and asserts constant-bounded buffering rather than accumulating all bytes. Metadata tests mutate generation/size/checksum independently and assert zero VCF bodies; allow metadata internal HTTP unknown with explicit policy, not fake exact counts.
- [x] **RED: sparse coverage and duplicates.** Stage a small source with prefix/chunk/EOF overlaps already merged; hand enumerate unique bytes and assert no repeated range request. Corrupt/missing retained index refuses with no fetch; copying same exact index succeeds. Seek outside verified coverage in original reader and assert `coverage_gap` before read; terminate at an unacquired block/invalid virtual low offset and refuse. Overlapping virtual chunks emit each source offset once; separate offsets with duplicate variant key refuse. Missing tail, block CRC and native nonzero fail. Fake sparse filesystem allocation beyond payload + 16 MiB refuses.
- [x] **RED: the raw reader consumes verified content, not the plan alone.** Add `synthetic_coverage_case(tmp_path)` to the existing test fixture helper: it stages the checked-in tiny source using complete RangeReceipts with ArtifactRefs, calls stage_sparse, and returns `(plan, verified, window, header)` with paths rooted at tmp_path. This factory is synthetic only; expected source/native record keys still come from the independently retained full-source oracle.

```python
from dataclasses import replace
import pytest
from scripts.reference_window_io import validate_verified_source, iter_original_records
from tests.reference_acquisition_fixture import synthetic_coverage_case

def test_saved_coverage_requires_actual_range_bytes(tmp_path):
    plan, verified, window, header = synthetic_coverage_case(tmp_path)
    first = verified.ranges[0].range_file
    path = tmp_path / first.path
    original = path.read_bytes()
    path.chmod(0o600)
    path.write_bytes(bytes([original[0] ^ 1]) + original[1:])
    with pytest.raises(ValueError):
        validate_verified_source(verified, plan, artifact_root=tmp_path)
    with pytest.raises(ValueError):
        tuple(iter_original_records(verified, plan, window, header, artifact_root=tmp_path,
              raw_destination=tmp_path/'new.raw.tsv', offsets_destination=tmp_path/'new.offsets.tsv'))

def test_planned_ranges_cannot_replace_missing_acquired_coverage(tmp_path):
    plan, verified, window, header = synthetic_coverage_case(tmp_path)
    with pytest.raises(ValueError):
        validate_verified_source(replace(verified, ranges=verified.ranges[1:]),
                                 plan, artifact_root=tmp_path)
```

Also mutate a sparse populated extent without changing its retained range file and require validation failure before native invocation; corrupt index identity and wrong source generation likewise fail. Test a valid serialized/deserialized VerifiedSource against relocated identical root contents to show that hash/source identity, not original absolute path, controls use.

- [x] **RED: exact stdout/stderr limits and refused native outputs.** In the bounded-process helper unit test, use a small explicit helper-only limit and a fake child that emits cap+1 bytes; assert immediate group termination, retained prefix length cap+1, limit flag, noncomplete receipt and no second invocation. Production wrappers must pass exactly the operation-specific constants declared globally; separate argv/limit tests assert query_samples=1,048,576, version=65,536, all other native stdout=2,147,483,648 and every stderr=1,048,576. The helper-only test limit is not a CLI option or serialized production policy. Add stderr-first overflow while stdout blocks, stdout-first overflow while stderr blocks, timeout after partial output, and zero child exit after cap+1; all retain actual stream prefixes/hashes and refuse. BCF commands must omit `-o` and their stdout artifact size must equal receipt.stdout.size_bytes, including partial output on failure.
- [x] **RED: independent native fixture.** Generate tiny synthetic source from explicit lines covering lower/upper interval boundary, no-record/no-PASS windows, two ALT variants at one POS, missing GT, exact QC cutoffs, and a long INFO record crossing blocks. Use `bgzip -c`, `tabix -p vcf`, independently query full source using native bcftools with `--regions-overlap 0`, then acquire only planned ranges into synthetic sparse source. Compare raw source reader keys/hash and native full/sparse extraction keys. A separate deliberately malformed fixture includes original integer overflow/invalid QC: demonstrate original-token refusal; do not let native missing conversion pass. Check in compressed fixture+TBI+saved exact native stdout/version/hash evidence, never expanded long genotype text. Portable CI validates saved fixture hashes and hand/block controls without requiring native tools; a separate live test requires all tools and 1.23.1, and only it may skip when unavailable in CI.
- [x] **Run RED:** `PYTHONPATH=. python -m pytest tests/test_reference_window_io.py -q`; live native test must fail until adapter works, not be permanently skipped.
- [x] **GREEN: implement the bounded stream.** Start subprocess as its own process group, disable credentials/prompts/log files, set retry zero, stream stdout with a bounded reader, hash/write each piece and cap at expected+1. Timeout/overflow terminates process group and preserves partial receipt. Use explicit metadata/raw API field validation. Stage sparse only from verified receipts, verify copied indexes, create exact logical size, check allocation, qualify prefix/header/EOF. Raw reader merges virtual chunks and advances through complete BGZF members only inside verified acquired ranges, retains line start virtual offsets and refuses non-LF endpoints. A zero-low-offset chunk after physical byte zero must prove the preceding retained member ends in LF; unavailable predecessor coverage refuses without widening the reviewed plan. Write exact selected original LF lines and ordinal/first-virtual-offset/line-hash records to the two required exclusive destinations before yielding the parsed SourceRecord. It never reads an entire logical sparse file to hash it. Native commands are those in design §4, input always local. Log raw/native hashes and extraction exits without participant content.

```python
# Accounting invariants, asserted after every source:
assert sum(r.received_bytes for r in receipts) == observed_body_bytes
assert all(r.received_bytes <= r.requested_bytes + 1 for r in receipts)
assert all(r.adapter_invocations in (0,1) for r in receipts)
# Wire and HTTP bytes/counts are unavailable fields, never derived from this sum.
```

- [x] **GREEN/gates/review:** focused tests, mandatory live native full/sparse controls with zero local skips, smoke, module size, privacy. Save exact native/SDK source-hash/version evidence locally; inspect staged synthetic paths. Commit `feat: acquire and verify frozen reference byte ranges; advance #255`. No real VCF download in this task's test/review cycle.

## Task 5: Project four count inputs and validate every artifact and window

**Scientific contract:** preserve population/window/source identity and callable denominators in four reproducible development inputs. Acceptance is hand count projection, per-variant native equality, all 66 accounting and artifact tamper/failure tests. Pure preparation and thin writers expose unchanged ReferenceCount tables; missing/refused content never becomes an admitted complete dataset.

**Files:** create `reference_preparation_types.py`, `reference_acquisition_codec.py`, `reference_preparation_codec.py`, the Task 5 pure preparation and thin writer modules, and `tests/test_reference_preparation.py`, `tests/test_reference_window_artifacts.py`.

**Interfaces:** Task5 declarations; writers use design §6 exact schemas/column sets. Use the explicitly declared `reference_preparation_types.py`, `reference_acquisition_codec.py` and `reference_preparation_codec.py`; no shared mutable artifact dictionary contract. Nonempty table validation uses existing `validate_reference_counts`; all-empty preparation has a separate explicit complete_empty state.

- [x] **RED: identity/orientation/AN=0 projection.**

```python
import json
from genomeos.validation.reference_preparation import prepare_rows, check_native_totals
from genomeos.validation.reference_genotypes import (
    PopulationCount, VariantCounts, MissingOriginCount, QcTally,
)
from tests.reference_acquisition_fixture import synthetic_window

def test_reference_projection_keeps_unavailable_cell():
    w = synthetic_window('chr1', start0=100, end0=10100)
    counts = (VariantCounts('GRCh38:chr1:101:A:G', (
        PopulationCount('Han','r',2,3,4,1,2),
        PopulationCount('NorthernHan','r',1,0,0,0,0),
    ), QcTally((('accepted',1),('low_gq',1),('missing_gt',1)),
        (('ad_alt',1),('ad_arity',1),('ad_missing',1),('ad_ref',1),
         ('dp',1),('gq',2),('gt',3)),
        (MissingOriginCount('gt','literal_dot',1),))),)
    rows = prepare_rows(w, counts, kind='quality')
    keyed = {r.group_id:r for r in rows}
    assert (keyed['NorthernHan'].ac,keyed['NorthernHan'].an) == (0,0)
    assert keyed['Han'].variant_group == 'GRCh38:chr1:101-10100'
    assert keyed['Han'].record_id == json.dumps(['Han','GRCh38:chr1:101:A:G'],
                                                separators=(',',':'))
    check_native_totals(counts, (('GRCh38:chr1:101:A:G',3,4),))
```

The test helper `synthetic_window` constructs a legal ReferenceWindow for the given bounds: source stratum `[0,33333)`, eligible run `[0,23333]`, rank100, width10,000, stratum1; restrict helper to this explicitly declared toy geometry rather than relaxing the production type.

- [x] **RED: native and key mismatches.** Use the same count literal to assert that native `(AC,AN)=(2,4)`, missing native AC/AN tokens `.` (reason `native_count_unavailable`), reversed REF/ALT, duplicate keys, missing/extra keys and noninteger native count each refuse. Assert counts inequality/evenness/sample count invariants, region conflicts and duplicate group/variant refuse. Compare four track key sets; a deleted AN=0 row fails. Validate exactly 66 expected IDs with duplicate/missing/foreign receipts; `no_index_chunks` alone does not imply no_records. Add header-only complete_empty test, all-AN=0 nonempty test, `no_pass_snps` ledger and one refused window with final complete=false.
- [x] **RED: strict phase records and complete QC coverage.** Constructors/codecs reject an acquisition window state `counts_prepared` and a preparation window state `records_acquired`; incomplete windows remain the correct phase type. Start from the complete Task 5 hand QcTally above and assert that deleting gt/gq coverage or its MissingOriginCount refuses, even if AC/AN numbers still match. A no-record complete stage has QcTally((),(),()) and sample_count fixed for its cohort, variants/rows zero; a nonempty stage cannot reuse that empty tally.

```python
from dataclasses import replace
import pytest
from genomeos.validation.reference_genotypes import QcTally, MissingOriginCount

def test_missing_qc_coverage_is_not_a_valid_hand_control():
    good = QcTally((('accepted',1),('low_gq',1),('missing_gt',1)),
        (('ad_alt',1),('ad_arity',1),('ad_missing',1),('ad_ref',1),
         ('dp',1),('gq',2),('gt',3)),(MissingOriginCount('gt','literal_dot',1),))
    with pytest.raises(ValueError): replace(good, inspection_totals=())
    with pytest.raises(ValueError): replace(good, missing_origins=())
```

For each acquisition/preparation codec, mutate exact key sets at top level and each nested record, including files, range receipts, verified coverage, stage summary, missing-origin count, native token/control artifact, and policy map. Reject extra keys, omitted keys, duplicate keys, wrong Literal, bool count and altered policy values. Confirm write_acquisition_manifest returns the hash of exactly acquisition.json, and write_preparation_manifest returns exactly manifest.json. Validators return the respective typed phase record and reject a counts-root reference to a different acquisition manifest. Assert refused preparation tracks=() while all 66×2 stage outcomes remain explicit.
- [x] **RED: manifest-last failure and tamper controls.** Build a complete synthetic artifact in tmp_path, mutate each of range bytes, header bytes, original raw file, native file, count cell, variant-window mapping, dependency edge and source code hash; validator rejects each independently. Simulate disk failure before last manifest: downstream validation refuses missing manifest. Simulate a failure after one window: all 66 ledger entries remain, unknown counts null, partial products never listed as admitted four inputs. Reinvoke existing path: no file changed. Symlink input/out relative traversal refuses. Contradictory complete=true/failed window rejects even when the manifest bytes/hash are internally consistent.
- [x] **Run RED:** `PYTHONPATH=. python -m pytest tests/test_reference_preparation.py tests/test_reference_window_artifacts.py -q`.
- [x] **GREEN: exact projection/reconciliation.** Produce one row per literal population/site/stage/track, ID/block formulas above, sorted by record_id. Compare cohort called sums to native totals by exact variant ID, never by row position or zip alone. Confirm P stage participants subset T, all four keys identical and source/window assignments unique. Dependency JSON has exact three edges,80 nodes/77 components and explicit limitation/source hash. Counts windows/QC ledgers include all 66, every exclusion state and AN=0 unavailable total. Canonical writers use exclusive files and fsync-close before final manifest; hash each exact artifact and validate the same typed content on read. Last manifest complete=false is a truthful terminal failure record; complete=true requires all dependencies and evidence.

```python
native_by_id = {v:(ac,an) for v,ac,an in native}
if len(native_by_id) != len(native) or set(native_by_id) != {x.variant_id for x in counts}:
    raise ValueError('native variant identity mismatch')
for x in counts:
    expected = (sum(p.called_ac for p in x.populations),
                sum(p.called_an for p in x.populations))
    if native_by_id[x.variant_id] != expected:
        raise ValueError('native called count mismatch')
```

- [x] **GREEN/gates/review:** both focused files, smoke, module size/privacy, staged-path inspection; commit `feat: prepare traceable reference window count artifacts; advance #255`.

## Task 6: Compose and verify the software CLIs

**Scientific contract:** deliver reviewable reproducible acquisition/preparation software with enforced gates, without claiming real data were acquired or science gates passed. Acceptance is synthetic end-to-end/native/fault evidence and full software checks. Thin CLI composition produces phase-specific manifests; missing review/input/source evidence refuses. The controller alone runs real source acquisition after all software task and whole-branch reviews.

**Files:** create the two Task6 CLIs, `tests/test_reference_window_clis.py`, software-verification research note explicitly stating real acquisition has not run; add new focused smoke coverage only if it fits the existing smoke contract. Update design/plan paths on this branch. No figure is generated from unqualified geography.

**Interfaces:** both CLI `main(argv: list[str] | None = None) -> int`; flags and exact sequence from design §7. Reuse all public task interfaces. `--help` requires no inputs and performs no network/native call. Errors return nonzero and print only closed reason codes plus aggregate/hash diagnostics. Composition functions accept already validated typed cohort/source records so synthetic end-to-end tests do not need real participant bytes; production main always calls real hash qualification for public evidence.

- [x] **RED: CLI gate and failure ordering.**

```python
from scripts.acquire_reference_windows import main

def test_help_is_read_only(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('unexpected external operation')
    monkeypatch.setattr('subprocess.Popen', forbidden)
    assert main(['--help']) == 0
```

Implement help via a parser whose normal `SystemExit(0)` is converted by `main` to 0 if this direct-call convention is used; no other exceptions are swallowed. Add subprocess tests for missing review, changed source hash, wrong cohort bytes and existing out dir; fake wrapper ledger stays empty. Inject one source transfer failure into the synthetic composition case: final acquisition has 66 states and complete=false; preparation rejects it. Successful synthetic composition yields four exact hand-validated tables and independently native matched retained keys, then passes both content validators. Make a public-evidence CLI case using synthetic metadata and assert it refuses the real frozen hash gate.
- [x] **Run RED:** `PYTHONPATH=. python -m pytest tests/test_reference_window_clis.py -q`.
- [x] **GREEN:** implement CLI argument parsing with all design §7 required flags and no permissive options. Check imported module paths/revision/hashes and tool versions before VCF requests; check all inputs/review/indexes first, then acquire, qualify source header/sample order, recover raw/native windows, and write the final acquisition ledger. Offline preparation validates full acquisition, requalifies frozen cohort inputs, projects original tokens, runs native called controls per stage/window, writes private artifacts and validates them. No network in preparation. On local invalid input before an output exists, exit with no directory. Handled source, window, token and native failures after work begins preserve terminal manifest-last accounting. An implementation-source identity change or storage write/fsync failure aborts without a final manifest because the running writer cannot truthfully attest its code or durable evidence.
- [x] **Wire exact phase interfaces, without running real acquisition in the task.** Acquisition composition loads the reviewed preflight once, produces each actual RangeReceipt, then calls `stage_sparse` to obtain VerifiedSource. It passes that receipt and the matching SourceBytePlan to raw/native readers. Assemble AcquisitionSourceReceipt and AcquisitionWindowReceipt independently; call `write_acquisition_manifest(out, manifest, preflight=preflight)` last and then `validate_acquisition(out)`. Preparation starts with `parent = validate_acquisition(acquisition_root)` and explicitly requires parent.complete before any count work. For each cohort call `native_called_totals(parent_window.native_bcf, cohort_file, acquisition_root=acquisition_root, artifact_root=out, bcftools=bcftools, output_prefix=prefix)` and retain its NativeCountFiles in the stage.native_control field, then stream `iter_native_totals(control, artifact_root=out)`; call `query_native_tokens(control.selected_bcf, artifact_root=out, bcftools=bcftools, output_prefix=prefix)` after a complete control, retain it in stage.native_tokens, and join the ordered `iter_native_tokens(...)` stream to original records by exact variant identity. Create a separate PreparationWindowReceipt with exactly two PreparationStageReceipts for every expected window. Finalize with `write_preparation_manifest(out, manifest, acquisition_root=acquisition_root)` and `validate_preparation(out, acquisition_root=acquisition_root)`. The phase manifest schemas and writer interfaces remain unchanged; Task 6 adds the reviewed acquisition-bundle input contract and copies the exact private cohort inputs to their fixed local evidence paths before any final writer. Known complete intermediate files survive a refused result; phase complete flags never infer approval.
- [x] **Run full software gate:**

```bash
PYTHONPATH=. python -m pytest tests/test_reference_preflight_input.py tests/test_reference_cohorts.py tests/test_reference_vcf_tokens.py tests/test_reference_genotypes.py tests/test_reference_window_io.py tests/test_reference_preparation.py tests/test_reference_window_artifacts.py tests/test_reference_window_clis.py -q
PYTHONPATH=. python scripts/smoke.py
ruff check .
python scripts/freeze_contract.py --check
python scripts/check_module_size.py
python scripts/check_private_files.py
PYTHONPATH=. python -m pytest
```

Record exact passes/skips/warnings; locally required native full/sparse/count/normalization tests must have zero skips. A missing native tool is unresolved evidence, not a silently passing real-run gate. No schema/lock updates expected; any such proposed change requires explicit design reconciliation.
- [x] **Finish the software task:** document exact synthetic/fault/native/full-CI results and the unexecuted real-data status. Independently review Task 6. Run privacy gate and inspect staged paths; commit `feat: compose frozen reference window preparation CLIs; advance #255`. Hand off the clean revision and source hashes. The worker finishes here without creating a review approval receipt, acquiring real bytes, closing #255 or claiming actual data acceptance.

## Controller-only real-data phase: after all six software tasks and whole-branch review

This phase is **not a worker implementation task**. The controller conducts it under the already authorized campaign after Tasks 1–6 each have reviewed code/test commits and the full branch has an independent scientific-contract/implementation review. A worker may complete its task while real-data acceptance remains pending. The exact current source and reviewed complete #254 artifacts must be bound before retrieval.

- [x] **Independent pre-retrieval review:** exact-source review passed at `0e27e3f`, bound the complete #254 inputs and 22 retained indexes, and accepted the 2,351,476,474-byte plan under the fixed 25 GiB cap.
- [x] **Run real acquisition and offline count preparation:** the one-shot controller run retained all 109 planned VCF ranges, completed 65 nonempty windows plus one explicit no-record window, and produced the four immutable count tracks without a retry, replacement window, or fit.
- [x] **Independent real-evidence audit:** both terminal content validators exited zero. The audit verified all 66 windows, 22 generation-bound sources, 4,117/4,094 sample stages, 80 population labels, 32,415 native called-count matches per stage, four identical keysets, unavailable rows, and private-file exclusion. Aggregate evidence is recorded in `docs/research/reference-window-acquisition-2026-09-11.md`.
- [x] **Final documentation and PR:** the aggregate research note records commands, revisions, source identities, all-window outcomes, four-track totals, native matches, and limitations without private paths or row-level data. The final evidence commit updates PR #287 to close #255 and advance #189 under Atlas §§4–8,12; data preparation grants no calibration, model, or publication claim.

## Plan self-review and execution handoff

Each of the eight design sections has an implementation/acceptance task: source/review→1; cohorts/dependencies→2/5; transfer/sparse/raw/native→4; tokens/QC→3; tables/provenance/all 66→5; CLI/software evidence→6; actual acquisition and independent evidence audit→controller-only phase. Tests distinguish malformed visited QC from uninspected fields, native normalization from original tokens, private real input qualification from tiny synthetic tests, and complete-empty from incomplete acquisition. Shared signatures, field names and paths above are task-global.

This plan is delivered for controller self-review/adoption alongside #254; no code or acquisition has been executed by the design agent. Continue using the controller's authorized execution workflow after review, without adding an execution-choice permission pause.
