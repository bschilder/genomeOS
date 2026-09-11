# Reference-window Preflight Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. The controller adopted the design with the bounded rulings recorded below; proceed under existing authorization without adding an approval pause.

**Goal:** Freeze 66 outcome-independent autosomal windows and a generation-bound, index-only transfer preflight for #254, advancing #189.

**Architecture:** Pure geometry and strict source/config contracts produce a local immutable manifest. A bounded pure TBI planner and thin repository-gcloud adapter produce the complete window ledger and merged transfer estimate. Genotype/count extraction is a subsequent task.

**Tech Stack:** Existing Python, NumPy, standard-library dataclasses/JSON/struct/zlib/hashlib/subprocess, pytest; installed native bgzip/tabix/bcftools for the independent synthetic oracle. No dependency changes.

**Spec:** [Reference-window selection and index preflight](../specs/2026-09-10-reference-window-preflight-design.md); read it with `AGENTS.md`, `docs/overview.md`, `docs/scientific-engineering-objectives.md`, Atlas §§4–8,12, `2026-09-09-global-af-modeling.md` WP0/WP1 and `docs/repo-gcloud-auth.md`.

## Global Constraints

- Exactly 66 windows: three per chr1,…,chr22, 10,000 bases, zero-based half-open; stratum j bounds `L*j//3`, `L*(j+1)//3`.
- Exclude chr22 `[20_000_000,20_010_000)` geometrically before drawing; no external mask, replacement or outcome-driven redraw.
- One `numpy.random.Generator(numpy.random.PCG64(42))`; `SEED = 42`; natural chromosome/stratum order; `integers(0,total,dtype=np.int64)`.
- Hard total planned compressed transfer cap `26_843_545_600` bytes; include all TBI objects, merged VCF chunks, 1 MiB header prefixes and 28-byte EOF reads.
- Only public TBI bodies and object metadata may be fetched. VCF prefix/tail/genotype bytes, count extraction and fitting are out of scope.
- The original 12 B0 and 24 B0H inputs remain immutable; development-only, `publication_eligible=false`, `p1_eligible=false`.
- Preserve future 4,117/4,094 stage and called/quality count semantics; `ReferenceCount` and existing P0/P1 schemas remain unchanged.
- Source generations are explicit on every request. No unversioned fallback, arbitrary URLs or credentials; all GCP calls use `scripts/gcloud_repo.py`.
- All 66 windows survive in the ledger. `no_index_chunks` means variant content not inspected, never an empty VCF or zero count.
- Pure modules have no filesystem/network/environment access. Target ≤500 logical lines/module; do not compensate with private cross-module imports.
- Scientific artifact JSON is canonical, strict, timestamp-free; output directories are exclusive and never overwritten. Record actual imported source hashes.

---

## File responsibilities and shared types

Task 1 creates `genomeos/validation/reference_window_types.py` (immutable records and source-pair/field validation), `genomeos/validation/reference_windows.py` (geometry), `genomeos/validation/reference_window_manifest.py` (byte codecs and raw source import), `scripts/freeze_reference_windows.py` (local composition), and matching tests. Task 2 creates `genomeos/validation/reference_tbi.py` (bounded binary parsing), `genomeos/validation/reference_byte_plan.py` (pure window/range/accounting records), `scripts/preflight_reference_windows.py` (public-index adapter), and matching tests. Geometry, codecs and CLI import Task 1 records directly from `reference_window_types`; types never import geometry or codecs, and no compatibility re-exports are needed. The types module validates normalized source-pair identities; the manifest module parses bytes into those types. Keep binary types/validation with their owning Task 2 modules; split a codec by responsibility if a module exceeds the size target. No package layout migration or edits to existing fitters.

All listed records are frozen dataclasses, constructors reject invalid values, and tuples are immutable. The following field declarations define the shared contract, not additional implementation tasks:

```python
# reference_window_types.py — all Task 1 records
from typing import Literal

EvidenceKind = Literal["synthetic_fixture", "public_reference_development"]
HashEntries = tuple[tuple[str, str], ...]

GenomicInterval(chrom: str, start0: int, end0: int)
StartRun(first: int, last: int)  # inclusive; first <= last
ReferenceWindow(window_id: str, chrom: str, stratum: int,
                stratum_start0: int, stratum_end0: int, start0: int, end0: int,
                eligible_runs: tuple[StartRun, ...], eligible_count: int, rank: int)

PublicObject(uri: str, generation: str, size_bytes: int,
             md5_b64: str, crc32c_b64: str)
SourcePair(chrom: str, vcf: PublicObject, tbi: PublicObject)
WindowConfig(schema_version: str, width: int, strata: int, seed: int,
             numpy_version: str, bit_generator: str, draw_method: str,
             exclusion: GenomicInterval, max_transfer_bytes: int,
             header_prefix_bytes: int, eof_bytes: int)
Provenance(data_version: str, evidence_kind: EvidenceKind, input_sha256: HashEntries,
           source_revision: str, imported_source_sha256: HashEntries,
           python_version: str, source_audit_locator: str)
WindowManifest(schema_version: str, config: WindowConfig,
               contig_lengths: tuple[tuple[str, int], ...],
               sources: tuple[SourcePair, ...], windows: tuple[ReferenceWindow, ...],
               provenance: Provenance, windows_sha256: str,
               omitted_source_chromosomes: tuple[str, ...],
               contig_evidence: str, source_evidence_status: str,
               count_contract: str, publication_eligible: Literal[False], p1_eligible: Literal[False])

# reference_tbi.py
VirtualChunk(begin: int, end: int)
TbiIndex(chrom: str, bins: tuple[tuple[int, tuple[VirtualChunk, ...]], ...],
         linear_offsets: tuple[int, ...], reference_bounds: VirtualChunk | None,
         mapped_count: int | None, unmapped_count: int | None,
         n_no_coor: int | None)

# reference_byte_plan.py
WindowState = Literal["index_chunks_planned", "no_index_chunks", "refused"]
ReceiptState = Literal["verified", "refused"]
BudgetStatus = Literal["within_cap", "over_cap", "incomplete"]
RefusalCode = Literal["metadata_mismatch", "generation_unavailable", "transfer_failed",
                      "size_mismatch", "checksum_mismatch", "index_invalid", "limit_exceeded"]
PolicyEntries = tuple[tuple[str, str | int], ...]

ByteRange(first: int, last: int)  # physical, inclusive
WindowBytePlan(window_id: str, state: WindowState, reason: RefusalCode | None,
               variant_content: Literal["not_inspected"], chunks: tuple[VirtualChunk, ...],
               ranges: tuple[ByteRange, ...])
IndexReceipt(chrom: str, state: ReceiptState, reason: RefusalCode | None,
             vcf_metadata_attempts: int, tbi_metadata_attempts: int,
             tbi_body_attempts: int, received_bytes: int, sha256: str | None)
SourceBytePlan(source: SourcePair, receipt: IndexReceipt,
               windows: tuple[WindowBytePlan, ...],
               merged_vcf_ranges: tuple[ByteRange, ...])
BytePreflight(schema_version: str, manifest_sha256: str, windows_sha256: str,
              sources: tuple[SourceBytePlan, ...], complete: bool,
              budget_status: BudgetStatus, known_planned_bytes: int,
              total_planned_bytes: int | None, max_transfer_bytes: int,
              provenance: Provenance, policy: PolicyEntries,
              publication_eligible: Literal[False], p1_eligible: Literal[False])
```

HashEntries and PolicyEntries require unique canonical key-sorted tuples; reject mutable mappings/lists at record boundaries. Explicit codecs may encode these as JSON objects and decode to sorted tuples after duplicate-key rejection. Frozen records contain no mutable dict fields. Validate Literal states at runtime, including that eligibility flags are the actual bool False. Close every remaining string-state vocabulary using the spec. Fixed config fields and parser limits have one implementation definition; callers cannot relax them. `source_evidence_status="supplied_audit_not_reperformed"`, `contig_evidence="saved_pilot_header_declarations"`, and `count_contract="pilot_stage_qc_semantics_unchanged_v1"` describe the actual evidence boundary. Input audit hashes bind the explanatory record without claiming a fresh source-terms review.

### Task 1: Freeze a deterministic local window manifest

**Scientific contract:** prepare outcome-independent development coverage; acceptance is 66 reproducible source-bound windows, exhaustive tiny-frame geometry and strict immutable artifacts. Pure geometry plus local freeze CLI produces it; invalid geometry/source evidence refuses and Task 2 consumes the manifest.

**Files:** create the four Task 1 modules above, `tests/test_reference_windows.py`, `tests/test_reference_window_manifest.py`, `tests/test_freeze_reference_windows_cli.py`, `tests/fixtures/reference_windows/synthetic-sources.json`, `synthetic-contigs.txt`, `synthetic-audit.md` in that fixture directory. Document usage in the design's handoff section. Real public captures stay caller inputs, not selector constants.

**Interfaces:** all record imports come directly from `genomeos.validation.reference_window_types`; the first three functions live in `reference_windows`, the remainder in `reference_window_manifest`.

```python
eligible_start_runs(stratum_start0: int, stratum_end0: int, width: int,
                    exclusions: tuple[tuple[int, int], ...]) -> tuple[StartRun, ...]
start_at_rank(runs: tuple[StartRun, ...], rank: int) -> int
select_reference_windows(lengths: tuple[tuple[str, int], ...],
                         config: WindowConfig) -> tuple[ReferenceWindow, ...]
parse_source_listing(raw: bytes) -> tuple[SourcePair, ...]
parse_contig_declarations(raw: bytes) -> tuple[tuple[str, int], ...]
windows_tsv(windows: tuple[ReferenceWindow, ...]) -> bytes
encode_manifest(manifest: WindowManifest) -> bytes
decode_manifest(raw: bytes, *, windows_bytes: bytes) -> WindowManifest
```

- [ ] **RED: geometry controls.** Put these exact oracles in `tests/test_reference_windows.py`; they do not regenerate expected geometry with the selector.

  ```python
  def test_forbidden_overlap_starts_match_exhaustive_frame():
      runs = eligible_start_runs(0, 12, 3, ((5, 7),))
      expected = [s for s in range(10) if s + 3 <= 5 or s >= 7]
      assert runs == (StartRun(0, 2), StartRun(7, 9))
      assert [start_at_rank(runs, k) for k in range(6)] == expected

  def test_touching_exclusion_is_allowed():
      runs = eligible_start_runs(0, 12, 3, ((5, 7),))
      assert start_at_rank(runs, 2) == 2  # [2,5)
      assert start_at_rank(runs, 3) == 7  # [7,10)

  def test_seeded_rank_oracle():
      rng = np.random.Generator(np.random.PCG64(42))
      # Independent recorded oracle under NumPy 2.4.6, eight eligible starts.
      assert [int(rng.integers(0, 8, dtype=np.int64)) for _ in range(3)] == [0, 6, 5]
      runs = (StartRun(0, 2), StartRun(7, 11))
      assert [start_at_rank(runs, k) for k in (0, 6, 5)] == [0, 10, 9]
  ```

  Extend exhaustive enumeration across widths 1…5, frame lengths width…15 and every exclusion inside that frame, checking exact eligible sets or refusal. Add direct negative/bool/fractional/out-of-range rank tests. Add full-manifest assertions for 66 IDs, natural order, each third's bounds, pilot nonoverlap and exact width; shuffle source input ordering and require identical normalized selection.
- [ ] **Run RED:** `PYTHONPATH=. python -m pytest tests/test_reference_windows.py -q`; expect import failure for the new module, then test failure until geometry exists.
- [ ] **GREEN: geometry.** Subtract clipped forbidden inclusive runs from `[a,b-width]`, sum lengths and map exactly one integer rank; no per-base arrays or redraw loops. Implement the public signatures with one generator at the full-selector composition boundary:

  ```python
  rng = np.random.Generator(np.random.PCG64(config.seed))
  # Within each natural-order chromosome/stratum, after calculating eligible runs:
  total = sum(run.last - run.first + 1 for run in runs)
  rank = int(rng.integers(0, total, dtype=np.int64))
  start = start_at_rank(runs, rank)
  ```

- [ ] **RED: strict source and byte contracts.** Synthetic fixture has 48 object listing entries forming 24 complete VCF/TBI pairs, obvious synthetic generation/checksum values, and artificial contig lengths sufficient for the chr22 pilot exclusion. No participant data. Use independently computed MD5/CRC metadata for synthetic bytes where body validation is needed. Add these byte-level controls, plus parameterized mutations of valid fixture/manifest JSON:

  ```python
  def test_manifest_rejects_duplicate_keys(valid_manifest_bytes, window_bytes):
      raw = valid_manifest_bytes.replace(b'{', b'{"schema_version":"bad",', 1)
      with pytest.raises(ValueError, match="duplicate"):
          decode_manifest(raw, windows_bytes=window_bytes)

  @pytest.mark.parametrize("value", [True, 1.5, "10000"])
  def test_width_requires_integer(valid_manifest_payload, window_bytes, value):
      valid_manifest_payload["config"]["width"] = value
      with pytest.raises(ValueError):
          decode_manifest(json.dumps(valid_manifest_payload).encode(),
                          windows_bytes=window_bytes)
  ```

  Test unknown/missing fields, invalid base64 lengths, URI generation mismatch, duplicates, wrong object family, missing chr22, unexpected chrM object, chromosome suffix mismatch, duplicate/malformed contigs, wrong assembly, seed/version/config changes, wrong TSV hash/row/order/coordinate and bool eligibility flags set true. Fixtures construct a valid manifest through the CLI once; mutation tests must fail for the stated independent invariant.
- [ ] **GREEN: implement codecs and local CLI.** Required CLI arguments: `--source-metadata`, `--contigs`, `--source-audit`, `--data-version`, `--evidence-kind {synthetic_fixture,public_reference_development}`, `--out`. Read bounded inputs (metadata/audit≤4 MiB each, contigs≤64 KiB), preserve their raw hashes, validate all inputs before exclusive output creation, and emit `windows.tsv` then `manifest.json`. No network import or subprocess command except local Git provenance. Use strict JSON duplicate detection and reject constants:

  ```python
  def unique_pairs(pairs):
      result = {}
      for key, value in pairs:
          if key in result:
              raise ValueError(f"duplicate JSON key: {key}")
          result[key] = value
      return result

  raw_json = (json.dumps(payload, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False) + "\n").encode("utf-8")
  ```

  The raw listing importer requires outer keys `url,type,metadata`, with literal `type="cloud_object"` for both VCF and TBI; metadata keys used are `bucket,name,generation,size,md5Hash,crc32c`. Recognized metadata-only string fields are `contentType,etag,id,kind,mediaLink,metageneration,selfLink,storageClass,timeCreated,timeFinalized,timeStorageClassUpdated,updated`; preserve their original bytes through the raw hash, omit from normalized identities explicitly, reject unexpected keys/types. Check `id` and pinned outer URL consistency; do not dereference `mediaLink`/`selfLink`. Convert only raw GCS decimal `size` into normalized integer after strict decimal validation; normalized codecs never coerce. Record explicit chrX/Y exclusions.
- [ ] **Verify Task 1 independently.** Run the three focused test files; CLI subprocess tests freeze twice into fresh directories and compare both output files byte-for-byte. Attempt overwrite and require nonzero without changing original bytes. Change one source generation or input byte and require the appropriate source/input hash to change. Assert imported paths outside this checkout refuse. Record a literal 66-window selection/hash oracle from the reviewed synthetic freeze and verify it independently from tiny-frame/RNG tests before fixing it in the test; never merely compare two calls to the same selector as correctness evidence.
- [ ] **Review and checkpoint.** Run smoke, lint, module-size and privacy; inspect staged paths and diff. Commit only this task's paths with `feat: freeze deterministic reference windows (refs #254)`; it advances the issue. No real source freeze is a prerequisite for reviewing the pure implementation. No model/calibration files are staged.

### Task 2: Plan bounded TBI bytes and preflight every frozen index

**Scientific contract:** determine whether all selected windows have a conservative generation-bound candidate-byte plan within 25 GiB, without inspecting variants. Acceptance is independent native synthetic coverage, strict parser/refusal controls and complete real-index ledger. Pure TBI/range functions plus the wrapper adapter produce it; unknown source/index coverage refuses and a future acquisition task consumes successful plans.

**Files:** create the three Task 2 modules above, `tests/test_reference_tbi.py`, `tests/test_reference_byte_plan.py`, `tests/test_preflight_reference_windows_cli.py`, and `tests/reference_tbi_fixture.py` (reproducible fixture builder, test-only BGZF encoder and independent block oracle). Check in `tests/fixtures/reference_windows/native/synthetic.vcf.gz`, `synthetic.vcf.gz.tbi`, and `expected-queries.json` containing native query arguments/stdout, native versions and SHA-256 of both fixture files; all are synthetic. Never check in the expanded long-record VCF. Use Task 1 public records/codecs without private imports. Add actual command/results to the issue/PR evidence through the controller.

**Interfaces:**

```python
parse_tbi(compressed: bytes, *, expected_chrom: str,
          vcf_size_bytes: int) -> TbiIndex
candidate_chunks(index: TbiIndex, start0: int, end0: int) -> tuple[VirtualChunk, ...]
chunk_byte_range(chunk: VirtualChunk, *, source_size_bytes: int) -> ByteRange
merge_byte_ranges(ranges: tuple[ByteRange, ...], *, source_size_bytes: int) -> tuple[ByteRange, ...]
plan_window(index: TbiIndex, window: ReferenceWindow, *, source_size_bytes: int) -> WindowBytePlan
assemble_preflight(manifest: WindowManifest, source_plans: tuple[SourceBytePlan, ...],
                   *, manifest_sha256: str, provenance: Provenance) -> BytePreflight
encode_preflight(preflight: BytePreflight) -> bytes
crc32c(data: bytes) -> int
# scripts/preflight_reference_windows.py — I/O only
fetch_public_index(source: SourcePair, *, wrapper: Path) -> tuple[bytes | None, IndexReceipt]
```

- [ ] **RED: physical byte and budget controls.** Test these exact arithmetic cases:

  ```python
  def test_physical_end_boundary_and_final_block_clamp():
      assert chunk_byte_range(VirtualChunk(100 << 16, 200 << 16),
                              source_size_bytes=1000) == ByteRange(100, 199)
      assert chunk_byte_range(VirtualChunk(100 << 16, (900 << 16) | 7),
                              source_size_bytes=1000) == ByteRange(100, 999)
      assert merge_byte_ranges((ByteRange(0, 9), ByteRange(8, 19),
                                ByteRange(20, 29)), source_size_bytes=1000) == (ByteRange(0, 29),)

  def test_crc32c_published_check_value():
      assert crc32c(b"123456789") == 0xe3069283
  ```

  Build small SourceBytePlan records with explicitly enumerated byte sets and compare union cardinality. Include overlap between index-selected prefix/tail ranges, distinct generations that must not merge, no-index windows, all-index fees and two-source totals. Test total equal to cap accepted and cap+1 refused using synthetic physical ranges; unknown ranges yield null total and incomplete status. Missing/duplicate/foreign windows or sources must refuse.
- [ ] **RED: native oracle plus portable CI evidence.** Generate/check the fixture locally with installed `bgzip`, `tabix`, `bcftools`; current CI does not install them. Ordinary tests read the checked-in tiny native fixture and saved query evidence, verify its hashes, and run the independent block-coverage oracle without invoking native tools. A separate `test_native_reference_tbi_oracle` regenerates in pytest's temporary directory and independently repeats native queries; skip that one test only when tools are absent. Acceptance before real index preflight requires this live test to pass locally with zero skips. Use repetitive long INFO values so records cross BGZF blocks while the committed compressed fixture stays tiny. Record native versions, and run the oracle on target `[16383,16384)` plus boundaries `[0,1)`, `[32768,32769)` and an interval beyond position100000.

  ```python
  long_info = "ACGT" * 45000  # long decompressed record, tiny compressed fixture
  header = ("##fileformat=VCFv4.2\n##contig=<ID=chr1,length=1000000>\n"
            '##INFO=<ID=X,Number=1,Type=String,Description="Synthetic">\n'
            "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n")
  records = [f"chr1\t{pos}\t.\tA\tC\t.\tPASS\tX={long_info}\n"
             for pos in (1, 16384, 32769, 100000)]
  vcf = tmp_path / "synthetic.vcf.gz"
  vcf.write_bytes(subprocess.run(["bgzip", "-c"], input=(header + "".join(records)).encode(),
                                check=True, capture_output=True).stdout)
  subprocess.run(["tabix", "-p", "vcf", str(vcf)], check=True)
  positions = subprocess.run(["bcftools", "query", "--regions-overlap", "0",
                              "-r", "chr1:16384-16384", "-f", "%POS\n", str(vcf)],
                             check=True, capture_output=True, text=True).stdout
  assert positions == "16384\n"
  ```

  Independently scan this **synthetic** BGZF file to associate native-selected record bytes with physical blocks; do not use planner internals for this oracle:

  ```python
  raw = vcf.read_bytes()
  blocks, expanded, offset = [], bytearray(), 0
  while offset < len(raw):
      block_size = int.from_bytes(raw[offset + 16:offset + 18], "little") + 1
      payload = zlib.decompress(raw[offset:offset + block_size], wbits=31)
      blocks.append((offset, offset + block_size - 1, len(expanded), len(expanded) + len(payload)))
      expanded.extend(payload)
      offset += block_size
  target = records[1].encode()
  begin = expanded.index(target)
  end = begin + len(target)
  touched = [(lo, hi) for lo, hi, a, b in blocks if a < end and b > begin]
  assert len(touched) >= 3
  index = parse_tbi(Path(str(vcf) + ".tbi").read_bytes(),
                    expected_chrom="chr1", vcf_size_bytes=len(raw))
  ranges = tuple(chunk_byte_range(c, source_size_bytes=len(raw))
                 for c in candidate_chunks(index, 16383, 16384))
  assert all(any(r.first <= lo and r.last >= hi for r in ranges) for lo, hi in touched)
  ```

  This fixture-only scanner relies on bgzip's emitted fixed header, not arbitrary public input. Test complete target records against native output, not just the first block. Queries beyond the last record must preserve `variant_content="not_inspected"` regardless of whether conservative bins yield chunks; no expected real-data emptiness assertion.
- [ ] **Run RED:** `PYTHONPATH=. python -m pytest tests/test_reference_tbi.py tests/test_reference_byte_plan.py -q`; record missing-module/test failures.
- [ ] **RED: adversarial index bytes.** Decompress the checked-in native synthetic TBI in the test helper, mutate little-endian fields, then re-encode with the standard-library test helper below so ordinary CI does not need native tools. Validate this helper against the native fixture decompression separately; it is not the coverage oracle. Test truncation at each header/count/chunk/linear boundary; n_ref=0/2; wrong preset/name; signed counts -1/2^31-1; duplicate/invalid bin37449; pseudo-bin37450 n_chunk≠2; ordinary reversed chunks; offsets beyond source and exclusive terminal end rules; zero linear sentinels; absent/zero/nonzero/partial n_no_coor; extraneous bytes; CRC corruption; BGZF size lies; expansion limits. Include a valid metadata-bin count pair with its numeric count exceeding VCF size: it must be retained as a count, not rejected as an offset. Include absent pseudo-bin and absent linear entries without inventing failure/emptiness. Caps must trigger before huge allocation; assert failure type/reason, not memory exhaustion.

  ```python
  def synthetic_bgzf(payload: bytes) -> bytes:
      def block(part: bytes) -> bytes:
          compressor = zlib.compressobj(wbits=-15)
          body = compressor.compress(part) + compressor.flush()
          size = 18 + len(body) + 8
          assert size <= 65536
          header = bytes.fromhex("1f8b08040000000000ff060042430200") + struct.pack("<H", size - 1)
          return header + body + struct.pack("<II", zlib.crc32(part), len(part))
      return b"".join(block(payload[i:i + 32768]) for i in range(0, len(payload), 32768)) + block(b"")
  ```

- [ ] **GREEN: strict parser and conservative plan.** Parse bounded BGZF members and bounded little-endian arrays per spec §5. Separate pseudo-bin fields from candidate chunks. `candidate_chunks` uses offsets/shifts `(0,0),(1,26),(9,23),(73,20),(585,17),(4681,14)` with root bin0 once, descending levels thereafter, and end-1 for half-open bins. Union chunks and sort deterministically. Parse linear data but apply no pruning; record `conservative_reg2bins_v1`. Implement physical endpoint formula and per-generation merges, then always add prefix/tail and all TBI fees. No VCF decoder or acquisition code is added.
- [ ] **RED: adapter confinement.** Fake `Popen` streams supply pinned metadata and synthetic index bodies, preserving byte boundaries. Assert argv contains the repository wrapper and exact `#generation`, anonymous/file-log-disable environment keys, and no VCF `storage cat` invocation. Test metadata generation/size/checksum mismatch; unavailable pinned generation; partial/oversized body; checksum mismatch; 120-second timeout; 1 MiB metadata/16 MiB compressed cap; malformed manifest causes zero process calls. Verify 22×3 retained ledger rows after one index failure, nonzero exit, incomplete/null total, and successful independent chromosomes. Count metadata attempts separately from index body attempts.
- [ ] **GREEN: implement bounded adapter/CLI.** Require `--manifest`, `--windows`, `--out`; verify input bytes and strict manifest before any network. Use argument arrays, `shell=False`, wrapper `storage objects describe` for pinned VCF and TBI identities, then `storage cat` only for verified pinned TBI. Enforce streaming size/time bounds; no unbounded `capture_output` for public body reads. One metadata request per object and at most one index-body request per pair; no retry. Build fixed-reason receipts, preserve body SHA-256 only after integrity checks, continue independent pairs, emit canonical `preflight.json` last and exit nonzero for any refusal or excess budget. Keep failed partial bodies out of successful caches. Hash imported modules/CLI/wrapper and record native/wrapper version evidence separately from scientific timing.
- [ ] **Verify Task 2 independently.** Run all six focused test files; on a machine with all three tools, run `python -m pytest tests/test_reference_tbi.py -k native_reference_tbi_oracle -q` and require at least one passing test and zero skips. Default CI may skip only this live-tool test, while saved native-fixture/query/block-coverage tests remain mandatory; then run the real index-only preflight on the independently reviewed local 66-window freeze. Retain `no_index_chunks` and failures without redraw. Inspect the generated totals and ledger before considering a future genotype acquisition task; this task never fetches planned VCF ranges.
- [ ] **Final verification and PR.** Run the commands below, report exact results and known baseline limitations, run privacy immediately before commit/push, inspect `git diff --cached --name-only`, and review generation binding, native block coverage and cap equality independently. Commit Task 2 with `feat: preflight bounded reference index bytes (closes #254)` only when acceptance passes; otherwise use `refs #254`. Open a PR that closes #254 only when complete and explicitly advances #189. Include scientific limitations and the index-only boundary; no map figure is required because no observations/surfaces/masks/burden are changed.

## Verification commands and handoff

Run from the isolated checkout with its intended Python environment. Source-tree imports must resolve here. If the sandbox makes the default compiler/plot cache unwritable, use temporary writable caches without changing runtime source:

```bash
export PYTHONPATH=.
export PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-reference-window-pytensor
export MPLCONFIGDIR=/private/tmp/genomeos-reference-window-mpl
export XDG_CACHE_HOME=/private/tmp/genomeos-reference-window-cache
python -m pytest tests/test_reference_windows.py tests/test_reference_window_manifest.py tests/test_freeze_reference_windows_cli.py tests/test_reference_tbi.py tests/test_reference_byte_plan.py tests/test_preflight_reference_windows_cli.py -q
python scripts/smoke.py
python -m ruff check .
python scripts/freeze_contract.py --check
python scripts/check_module_size.py
python scripts/check_private_files.py
python -m pytest
git diff --check
git diff --cached --name-only
```

These are planned checks, not a claim they have passed. No CI package-install change is needed: committed native fixture/evidence covers default CI, and the explicit local live-native gate is additional acceptance evidence. The controller must review the two independently testable deliverables and the complete preflight evidence. Genotype acquisition, header/sample reconciliation, count extraction and new model comparisons remain outside this plan.
