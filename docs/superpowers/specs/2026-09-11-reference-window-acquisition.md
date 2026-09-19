# Frozen reference-window acquisition and count preparation

**Status:** adopted concrete design for #255, advancing the owner-authorized #189 global AF program WP0/WP1. Controller rulings on exact lazy QC, a downstream preflight codec, and original-token validation are incorporated. Design only; implementation and acquisition have not run. Implements Atlas §§4–8,12. Companion: `docs/superpowers/plans/2026-09-11-reference-window-acquisition.md`.

## 1. Scientific contract

1. **Claim:** the exact released original HGDP+1KG calls can produce traceable development AC/AN over the previously selected autosomal windows, preserving population identity, cohort stage, allele orientation, callability and QC sensitivity. Broader physical coverage does not establish independent loci, verified residents or predictive improvement.
2. **Output and acceptance:** a ledger covering all 66 frozen windows, generation-bound byte/header/sample receipts, and four count inputs (technical/paper × called/quality) with window and dependency sidecars. Exact synthetic controls, independent native extraction identity and native called cohort-total AC/AN controls must pass. Real-data completion additionally requires every selected window to have an explicit successful or scientifically empty outcome, all source/count/artifact validations, and independent implementation/evidence review. A refused window makes the dataset incomplete.
3. **Component and interface:** two narrow local research CLIs acquire the immutable byte plan and prepare counts offline. Pure typed cohort and genotype/count functions do the derivation; codecs, repository-gcloud subprocesses, sparse storage, native tools and artifact writers are adapters. Existing `ReferenceCount` and P0/P1 schemas do not change.
4. **Assumptions, refusals and consumers:** consume the complete independently reviewed #254 preflight, its original frozen manifest and its retained verified indexes, the same release metadata/exclusions and exact saved sample lists. Refuse changed identity, unsupported encoding, missing required source declaration, failed/over-budget acquisition, missing sparse coverage, native mismatch or incomplete artifact. Future research benchmarks consume the four tables plus the sidecars. No fitting, new window selection, geography/date inference, P1 admission, confirmation claim or release occurs; `publication_eligible=false`, `p1_eligible=false`, `benchmark_admitted=false` throughout.

The original single-block B0/B0H inputs and results remain immutable. This work does not authorize a new B0H fit before calibration passes. The known 77 reported-edge population components (74 singleton and CDX/Dai, Cambodian/Japanese, ITU/STU pairs) remain a lower bound on dependence. Participants, within-population kinship, linked loci, joint calling, shared discovery, source QC and ancestry exclusions remain shared dependencies.

## 2. Frozen inputs and trust boundary

`decode_manifest(raw, windows_bytes=...)` from `reference_window_manifest` remains the authoritative 66-window decoder. Import `WindowManifest`, `ReferenceWindow`, `SourcePair`, `PublicObject` directly from `reference_window_types`; import `BytePreflight`, `SourceBytePlan`, `ByteRange`, `IndexReceipt` and public planning functions from the reviewed #254 modules. There are no compatibility re-exports or private imports.

#254 specifies an encoder, not a downstream decoder. Create `reference_preflight_input.py` in #255 with `decode_reviewed_preflight`. It rejects duplicate/unknown/missing JSON keys, noncanonical bytes, nonfinite values, integer coercion and unsupported states/versions. It reconstructs the upstream immutable records, verifies byte-for-byte `encode_preflight` equality, matches the manifest/window hashes and exact 22 source pairs, and requires `complete=true`, `budget_status="within_cap"`, non-null total ≤26,843,545,600. For each retained TBI, verify complete size, MD5, CRC32C and SHA-256 against the receipt and source, parse using public `parse_tbi`, recompute every `plan_window` and merged range, and compare the assembled preflight. An upstream path is a locator; source tuple and receipt hashes establish identity.

A caller-supplied independent-review receipt binds the exact manifest hash, preflight hash, reviewed acquisition implementation revision/source-hash mapping, reviewer record locator/hash and status `accepted`. The controller supplies it after an actual independent review; the acquisition program never creates its own approval. Local validation cannot establish that a reviewer actually performed their work: it validates the controller's hash-bound attestation. This is the already-required review gate, not a new owner approval pause. All local inputs, retained indexes and required executables validate before any VCF request. #254 Task2's code is not accepted merely because its files exist.

Private cohort inputs remain local. Frozen original metadata TSV SHA-256 is `e18e7a29d0567b8063edc1a714bd31e57dc422823ba51af2c63fecef0dbc3cf1`; release outlier bytes SHA-256 is `592772fff79086a6b55ce07693f2871c9e4fbe9bdeff1ff926d87fcba884994f`. Technical/paper saved sorted-LF sample-list hashes are respectively `4a4cb8594e78e8d584dd61357d10b9c35b2e50c870a9a7bad0f42b326544d4e2` and `7e2a7260d7d9b138b535c1cc2c48496e534bad9b72b8f7d72da6107193e55aec`.

Represent the documented synthetic control and two named contamination exclusions in a **private local** canonical JSON recipe with exactly `schema_version="reference_cohort_exclusions_v1"`, `control_id` and sorted `contamination_ids`. Its canonical-byte SHA-256, calculated from the retained diagnostic's literal release exclusions during design, is `a2d7138d85ba0931d3de7edb20e714fd840bdc75d82e29ed7cd1c9392b544488`. No participant IDs enter public code, fixtures, docs or logs. The implementation executor creates this private recipe by extracting the already-inspected literal constants from the retained diagnostic, verifies the frozen hash, and does not print its contents.

Read the exact TSV schema, preserving its original bytes/hash. Project explicitly to `s`, `population`, `hgdp_tgp_meta.Genetic.region`, `sample_filters.hard_filtered`; projection does not mean unknown source columns were scientifically validated. Require 4,150 distinct metadata IDs, 31 literal `true` hard exclusions, otherwise literal `false`, and the two distinct documented contamination exclusions outside the hard set. Technical cohort is metadata minus those exclusions, size 4,117. Outlier file must contain exactly 23 unique IDs, all technical; subtract them for 4,094. Re-encode sorted LF sample lists and require byte identity with the saved lists and hashes. Do not substitute older flags or `high_quality` fields. Both stages retain the same 80 literal `population` keys; Han/NorthernHan and PapuanHighlands/PapuanSepik remain distinct. Every population must have one nonempty literal operational `Genetic.region`; no coordinate is read or inferred.

The preserved aggregate dependency audit SHA-256 is `a4f8a305d5b795bbea36672eb00ca27f69866695cfcd26e83e965689da51858e`. Import its three exact undirected population edges and stage-specific reported-pair totals (1,302 technical, 1,294 paper). Do not reconstruct individual pedigrees from the TSV relationship-category field. The receipt records supplied prior audit evidence, not a new relatedness qualification.

## 3. Acquisition, budget and failure policy

Consume exact 22 source generations, exact 66 coordinates and #254 merged inclusive VCF ranges. The hard planned-transfer cap remains **26,843,545,600 bytes**, including the 22 complete TBI objects already retained plus the union of VCF chunk ranges, 1,048,576-byte prefix and 28-byte EOF per source. Equality passes. No new index body is downloaded, no window is replaced, and no range is expanded. A fresh run never downloads a prefix separately and then downloads it again inside an overlapping merged range. Acquire each planned merged range once, in natural chromosome/range order. All source ranges must succeed before extracting that source. Process sources independently after failures, retaining all 66 states.

Requests use argument arrays through `scripts/gcloud_repo.py`, anonymous credentials-disabled, prompts/update checks/file logging disabled, and body retries disabled with `CLOUDSDK_STORAGE_MAX_RETRIES=0`. `storage cat --range=FIRST-LAST URI#GENERATION` has inclusive endpoints. `storage objects describe URI#GENERATION --raw --format=json` rechecks frozen generation, decimal-string size, md5Hash and crc32c before that source's ranges. Do not consume arbitrary media links or source fallback. [Google's cat reference](https://docs.cloud.google.com/sdk/gcloud/reference/storage/cat) documents range endpoints; [storage configuration](https://docs.cloud.google.com/sdk/gcloud/reference/config/set) documents retry configuration.

**Honest transport accounting:** freeze SDK version and installed source hashes for the body/metadata call chain. SDK 574.0.0 `cat` uses an internal metadata lookup plus a ONE_SHOT body request; storage retry zero prevents the apitools body retry, not the independent metadata API retry policy. Record metadata adapter invocations, range adapter invocations, planned requested body length, bytes actually observed on stdout, complete/partial status, and SHA-256 of exactly received bytes. HTTP request count, headers/TLS/wire bytes and unobserved bytes after termination are `null/not_observed`, never equated to adapter calls/body bytes. The controller adopted this amendment for #254/#255: `request_attempt_accounting="wrapper_invocations"`, `storage_body_max_retries=0`, `metadata_http_attempts="unobserved"`. Metadata API retries and cat's internal metadata lookup are disclosed in the transport receipt and bounded by invocation time/output; no SDK monkeypatch is added. No automatic application retry or resume is permitted. A later retry needs a separately recorded decision/run directory and cannot erase failure history.

Each range streams in ≤1 MiB pieces into a `.partial` file with incremental SHA-256. Limit stdout to requested length+1, metadata stdout to 1 MiB, subprocess wall time to 120 seconds for metadata and 1,800 seconds per VCF range; kill the process group on timeout/overflow. These runtime limits refuse without relaxing the planned cap. Complete range files become verified only after exact length and zero exit; retain failed partial bytes under explicit partial names. Body hashing is local content identity, not a server-supplied whole-object checksum. Metadata/full-VCF MD5 is recorded as **declared, unverified for whole VCF**. No checksum is assigned to a sparse file as proof of original whole-object identity.

No general cache in v1: the only required reuse is the retained #254 indexes, copied with content verification into the exclusive acquisition directory. Existing original pilot bytes remain untouched. Repeated invocation on any existing destination refuses before requests. Successful source bytes and failed range evidence are retained for audit; a failed run cannot be silently resumed or adopted as complete. Runtime timings/logs are separate from canonical scientific manifests. Inherited #254 attempt counters retain their existing field names but are explicitly interpreted through its reviewed wrapper-invocation accounting policy.

Stage each source as `sources/chrN/INCOMPLETE.original.vcf.bgz`, logical size equal to source object size, with only verified planned ranges written at exact offsets; copy the verified index to its `.tbi` sibling. Retain a sparse allocation/coverage receipt, inspect allocated versus logical bytes, and abort if sparse allocation exceeds verified payload plus 16 MiB per source. Holes are never decoded as source bytes. Check the exact canonical BGZF EOF marker from the planned tail. Read only complete BGZF members from the fixed prefix until the complete LF-terminated #CHROM line is found; truncated trailing prefix members are permitted only after that complete header. A larger header is refusal, not a second prefix request.

## 4. Original tokens, native extraction and bounds

A focused bounded original-BGZF adapter is necessary: [HTSlib 1.23.1 `vcf.c`](https://raw.githubusercontent.com/samtools/htslib/1.23.1/vcf.c) can convert extreme integer FORMAT encodings into missing values. Counts must not treat native-normalized text as proof of valid original tokens.

Keep #254's per-window virtual chunks and source merged physical ranges. For raw extraction, union overlapping/touching **virtual** chunks first, preserving exact boundaries. A virtual cursor maps physical compressed-block offset plus decompressed offset. Before reading any member, prove its framing bytes and complete block lie inside successfully acquired physical ranges. Validate BGZF flags/BC subfield, compressed length ≤65,536, bounded decompressed length ≤65,536, CRC/ISIZE and exact member consumption. No unbounded gzip decompression. Validate virtual offsets against actual block output length; each chunk starts/ends on a complete record boundary (or zero offset before EOF); refuse dangling/truncated records. A record crossing blocks is assembled once, with its first virtual offset and exact original LF-terminated byte hash. Overlapping chunks must not duplicate the same source offset; two different source offsets with the same variant key are a duplicate-record error, even if their bytes match.

Limits frozen before retrieval: 8,388,608 decompressed header bytes; 16,777,216 bytes per VCF record; 2,147,483,648 cumulative decoded bytes per selected window, including inspected candidate-chunk content; 1,000,000 records per window; 4,151 samples per real source; 1,800 seconds per native extraction/control; one source/window at a time. Native stdout streams to bounded files, never `capture_output=True` for genotype streams; line limit is checked before growing a line buffer. Limits are refusal conditions, not sampling/truncation criteria. These are engineering ceilings without claims that the real windows fit until measured.

Read each source header independently. Require VCFv4.2, exact standard 9 fixed columns, unique exact sample IDs equal to all 4,150 metadata IDs plus the recipe's synthetic control, and the expected autosome's contig length and `assembly=gnomAD_GRCh38` consistent with the frozen manifest. Validate the entire declared autosome contig mapping against that manifest when declarations are present; the source's own contig is mandatory. Required FORMAT declarations: GT Number=1 Type=String; GQ/DP Number=1 Type=Integer; AD Number=R Type=Integer; no duplicate definitions. Other known source declarations are retained without pretending to qualify their scientific content. No FASTA/reference-allele validation is claimed from header assembly text alone. Save exact header bytes, hash, ordered-sample-list hash and set-identity receipt privately. Map source sample columns by exact IDs; source orders may differ. Requery native selected sample order and separately map its columns.

For every candidate record inspect CHROM/POS and token shape without changing lexemes. Exact POS containment is `start0 < POS <= end0`, equivalent to zero-based half-open selection. Records outside POS scope are explicit iterator-overlap exclusions; no QC values are inspected there. In-scope record keys are `(chrom, POS, REF, ALT)`; require matching source chromosome, positive ASCII decimal POS, sorted nondecreasing POS and no duplicate exact key. Site dispositions are sequential `not_pass`, `not_biallelic`, `not_acgt_snp`, `retained`; `FILTER` must be literally `PASS`, REF and ALT distinct uppercase one-character A/C/G/T. There is no MAF/MAC, monomorphic, outcome or availability filter. A native "SNP" category alone is not the A/C/G/T predicate. Unsupported structural input (bad column count, duplicate FORMAT keys, wrong source contig, bad POS) refuses; unselected variant classes are accounted exclusions, not malformed-call refusals.

A selected record's FORMAT may omit GT; if present GT must occur exactly once and first. Duplicate keys refuse. GQ/DP/AD header definitions remain required, but these fields may be absent from an individual record FORMAT. Preserve explicit missingness origin (`literal_dot`, `omitted_trailing`, `absent_record_format`) separately from token values. The [VCF 4.2 specification §1.4.2](https://samtools.github.io/hts-specs/VCFv4.2.pdf) permits trailing sample subfields to be omitted except GT; project those omissions and absent record QC keys to an explicit missing state, consumed as `.` by the unchanged QC decision tree only when reached. Absent record GT is `absent_record_format` and assesses as `missing_gt`, never inferred dosage. This is grammar-defined missingness, never a fabricated number or proof that a value was reported. Empty interior tokens, extra subfields, a nonfirst GT, a dropped GT sample token when GT is declared, and truncated/non-LF records refuse. Missing record/tab columns are not trailing sample-subfield omission. Recognized unused FORMAT fields remain opaque. Project selected cohort fields in actual source header order; excluded participants' QC values are not scientifically validated. A missing GT token counts as missing in both tracks, never zero dosage. Retain field-presence evidence with original raw lines; only visited QC requirements contribute to missing-origin disposition counts.

Run an independent native extraction on the local sparse file only. The adapter sends each command stdout through its exact byte limiter into the named window/selected/recomputed artifact; these conceptual command lines intentionally omit native `-o`:

```text
bcftools view --no-version -r chrN:START1-END1 --regions-overlap 0 -Ob INCOMPLETE.original.vcf.bgz
bcftools query -f '%CHROM\t%POS\t%REF\t%ALT\t%FILTER\n' window.bcf
bcftools view --no-version -S STAGE.samples.txt -m2 -M2 -v snps -f PASS -Ob window.bcf
bcftools +fill-tags STAGE.selected.bcf --no-version -Ob -- -t AC,AN
bcftools query -l STAGE.recomputed.bcf
bcftools query -f '%CHROM\t%POS\t%REF\t%ALT\t%INFO/AC\t%INFO/AN\n' STAGE.recomputed.bcf
```

Apply the explicit A/C/G/T predicate to native keys before comparison; preserve discarded native non-ACGT keys in site-accounting totals. Require exact identity multiset and order agreement for all POS-selected records between raw and native extraction, then exact retained identity keys for each stage. Compare independently recomputed native called AC/AN with Python population sums at **every** retained variant for both cohorts, including total AN=0. Also query native selected GT/GQ/DP/AD with exact native sample order and compare the interpreted values at the original assessment's visited nodes, including explicit missing states. Legitimate lexical changes such as leading-zero integer formatting are equivalent only if the same natural integer and disposition result; a normalized invalid/overflow value becoming missing is not equivalent. Preserve native-query hashes and inspected-node comparison totals. The local synthetic native control showed absent-record GT produces native AC/AN missing, while explicit all-missing GT produces AC/AN=0. Treat missing native totals as `native_count_unavailable` and refuse the whole window; never substitute 0 or label them independent count matches. This preserves the original scratch `natural(expected_ac/an)` admission refusal while correctly identifying valid VCF missingness. Explicit all-missing GT remains valid AN=0/unavailable AF. Native parsing error or a normalization changing the interpretation of inspected GT/QC tokens refuses; do not mask it. No `--force`, no `--drop-missing` rescue for partial GT, no native `norm`, sample forcing or INFO fallback. [The version-pinned bcftools manual](https://raw.githubusercontent.com/samtools/bcftools/1.23.1/doc/bcftools.txt) establishes POS overlap and sample-order behavior. [The fill-tags documentation](https://samtools.github.io/bcftools/howtos/plugin.fill-tags.html) documents GT-derived AC/AN and its different default treatment of half-missing GT; those inputs fail our domain before count admission.

The native reader and raw count path are different implementations, but both use the same source/index plan, and native tools share HTSlib. Native tests cannot establish correctness of the real upstream genotype calls, independence, every population assignment or the quality sensitivity. Synthetic native full-file versus sparse extraction provides independent byte-coverage evidence; real-data native/Python count agreement provides called cohort-total evidence only. Population and quality cells rely on the reviewed derivation plus independent hand controls.

## 4.1 Explicit source coverage, identity and native I/O contract

`stage_sparse` returns `VerifiedSource`, not None. It consumes the actual `RangeReceipt` tuple, verifies it exactly covers the source's reviewed merged plan, requires every receipt verified with a retained file, rehashes every complete range file and the retained index, writes sparse extents, and reads back/hashes those extents against the range files. `VerifiedSource.ranges` then lists the **actually acquired** source offsets and file hashes. It is not created from planned coordinates alone. The source pair/generations, exact logical size, index identity and actual extents must all match the reviewed source plan. A failure returns no VerifiedSource and preserves a refused source/range ledger.

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
read_native_totals(control: NativeCountFiles, *,
                   artifact_root: Path) -> tuple[tuple[str,int,int],...]
```

`extract_native` returns its complete/refused process receipt; successful BCF identity is `receipt.stdout`. `native_called_totals` resolves input_bcf under its explicit acquisition_root and the cohort list/outputs under artifact_root, validating both content references before spawning. It runs subset→fill-tags→sample-ID query→totals query, retaining each result/receipt in `NativeCountFiles`; it checks requested versus actual sample set and identity and never returns only unlabeled numbers. It may return a refused execution artifact after a native failure. `read_native_totals` accepts only complete native artifacts, validates their hashes, then parses exact variant identity and integer AC/AN; missing native count tokens raise `native_count_unavailable` while their raw files/receipts remain retained. Only this final parser returns typed numeric tuples. `query_native_tokens` uses `output_prefix.samples.txt`, `.samples.stderr`, `.tokens.tsv`, `.tokens.stderr`; a failed first query sets token_query/tokens null and preserves its first receipt. A failed second query preserves both receipts and partial outputs. `iter_native_tokens` refuses any noncomplete query artifact; neither producer manufactures absent successful files.

Exact native subprocess ceilings: stdout is **2,147,483,648 bytes** for extraction/selection/fill-tags BCF and keys/tokens/totals queries, **1,048,576 bytes** for sample-ID queries and **65,536 bytes** for version/help queries. Stderr is **1,048,576 bytes per invocation** for every native or gcloud subprocess, including metadata. Native wall time is 1,800 seconds; metadata remains 120 seconds. Every native BCF/VCF output is streamed through stdout to the parent writer (omit native `-o`), so the same byte limiter covers artifacts and query text; no native command writes an uncapped output file behind the parent. Text line buffers have the 16,777,216-byte record ceiling. Metadata stdout remains 1 MiB and VCF body stdout remains requested range length plus the single overflow sentinel, independent of the native cap.

Drain stdout and stderr concurrently in bounded pieces to avoid pipe deadlock. At cap+1 on either stream, terminate the entire process group immediately and retain at most that stream's cap+1 observed bytes. Preserve the other stream's observed prefix and exact hash as well. End-state receipts set limit_exceeded true, state refused and reason limit_exceeded; timeout uses reason timeout. `.partial` suffixes remain on every incomplete native output. SHA/size describe exactly retained prefixes; no claim that all native output or stderr was observed. A zero exit after overflow cannot make the receipt complete. Success requires both streams uncapped, valid framing/row checks and zero exit. No retained stderr is printed in public reports; its private content hash and refusal reason are enough.

## 5. Exact preserved count semantics

Use pure `assess_call` and `count_variant` functions; no environment, I/O or native calls. Original dispositions are a **sequential decision tree**, not marginal QC failure flags:

1. GT `.`, `./.`, `.|.` → dosage null, `missing_gt`; do not inspect GQ/DP/AD.
2. Otherwise GT must match `[01][/|][01]` exactly; partial, haploid, triploid, invalid and non-biallelic GT refuse. Dosage is the sum of the two allele indices, regardless of delimiter. This called dosage contributes AC and AN+=2 even if quality later excludes it.
3. GQ `.` → `missing_gq`; otherwise decimal natural integer <20 → `low_gq`; otherwise continue. Invalid encoding encountered here refuses. No DP/AD check after either disposition.
4. DP `.` → `missing_dp`; otherwise decimal natural integer <10 → `low_dp`; otherwise continue. Invalid encoding encountered here refuses.
5. Only heterozygotes inspect AD. If AD is `.` or any comma token is `.` → `missing_het_ad` **before the two-token arity check**. Otherwise require exactly two entries, then check each left-to-right with `natural(entry)*5 < DP`. The first true predicate → `low_het_balance`; parsing short-circuits, so a later AD token can remain uninspected. Homozygotes never inspect AD. Do not add AD-sum/DP equality, max AD, eager validation, or new ploidy/missing-GT behavior.
6. Otherwise `accepted`, contributing dosage and AN+=2 to quality as well.

Return `CallAssessment(dosage, disposition, inspected_fields)` with ordered inspection names `gt,gq,dp,ad_missing,ad_arity,ad_ref,ad_alt` identifying exactly which tests occurred. This makes malformed **encountered** values distinguishable from explicit missing requirements; it does not claim unused QC tokens were valid. Missing AD detection itself inspects all delimiter tokens for `.` without parsing integers. Native normalization must never supply the original-token evidence. Production native parsing can impose a separate representation failure even on unused tokens; record this as `native_encoding_refused`, without relabeling it a QC disposition or modifying the defined scientific function.

For each retained site, emit every literal population once for each stage/track, including AC=0 and AN=0. Validate `0≤quality_ac≤called_ac≤called_an≤2*n`, `0≤quality_ac≤quality_an≤called_an`, and both AN even. Disposition counts sum to cohort size per site; called AN=2×nonmissing dispositions; quality AN=2×accepted. Stage P membership is a strict subset of T; no assumption that P allele frequencies are smaller. No AF column is produced, so AN=0 cannot be confused with AF=0.

The unchanged seven-column `ReferenceCount` table uses `variant_id="GRCh38:chrN:POS:REF:ALT"`, literal `group_id`, literal source operational `region_id`, `variant_group="GRCh38:chrN:START1-END1"`, and `record_id=json.dumps([group_id,variant_id], separators=(",",":"))`. Sort by record_id within each table, matching the original preparation idiom. Stage/track/source/window identity stays in sidecars. No arbitrary aliasing or display-label aggregation. Validate nonempty tables with existing `validate_reference_counts`. A genuinely all-empty result writes four header-only tables and a `complete_empty` preparation manifest; it is not passed to that nonempty validator or presented as a benchmark input. Unknown/missing windows never create dummy variants.

## 6. Artifacts and executable provenance

Use new directories (mode 0700) and exclusive files (0600). Avoid symlinks in inputs/outputs, absolute paths in scientific manifests and all participant/token content in stdout/stderr. Native stderr stays local bounded diagnostic material; public summaries contain closed reason codes and hashes only. Source/header/genotype/count artifacts remain private research data; commit only synthetic fixtures, code and aggregate evidence. Do not create a map from approximate origin labels for this task.

Acquisition layout:

```text
acquisition/
  inputs/windows.tsv, window-manifest.json, preflight.json, review.json
  inputs/indexes/chrN.tbi
  sources/chrN/ranges/FIRST-LAST.bin[.partial]
  sources/chrN/header.vcf
  sources/chrN/INCOMPLETE.original.vcf.bgz[.tbi]
  windows/chrN-sJ.original-records.tsv       # private raw original lines
  windows/chrN-sJ.native.bcf
  windows/chrN-sJ.record-offsets.tsv         # raw ordinal, first virtual offset, line hash
  windows.tsv                              # exactly 66 ledger rows
  runtime-attempts.jsonl                    # operational timing, no participant values
  acquisition.json                         # completion or explicit failure ledger, written last
```

`acquisition.json` schema `reference_window_acquisition_v1` records input/review hashes, exact code/imported-module/native/SDK provenance, fixed policy, source identities and verified range/partial receipts, sparse receipts, per-source header/sample qualifications, per-window original/native hashes, status and counts, file hashes/sizes, planned total including retained indexes, actual VCF body bytes, inherited index receipt bytes, actual metadata stdout bytes, adapter-invocation counts and explicitly unobserved HTTP/wire fields. Each window state is one of `records_acquired`, `no_records`, `refused`; original/native extraction must both establish `no_records`. `no_index_chunks` is retained as preflight state, never automatically upgraded to no records. Refused-source windows have no record count (`null`) and no success hashes. All 66 window IDs occur once. Any failure makes `complete=false` and exit nonzero; the last manifest is a final ledger, not unconditional evidence of success.

Preparation layout:

```text
counts/
  inputs.json
  technical_qc_4117.called.tsv
  technical_qc_4117.quality.tsv
  paper_ancestry_exclusion_4094.called.tsv
  paper_ancestry_exclusion_4094.quality.tsv
  technical_qc_4117.dependencies.json
  paper_ancestry_exclusion_4094.dependencies.json
  variant-windows.tsv
  windows.tsv                              # exactly 66 ledger rows
  qc-dispositions.tsv                       # per window/stage reason totals and coverage totals
  native-controls.tsv                      # per window/stage aggregate match counts and hashes
  manifest.json                            # reference_window_counts_v1; written last
```

Preparation accepts only complete acquisition. Window states are `counts_prepared`, `no_records`, `no_pass_snps`, `refused`, plus per-stage/track unavailable-row counts for AN=0. A window with all AN=0 is `counts_prepared` with every row unavailable, never empty. Failed preparation may retain partial working products but does not emit four admitted inputs; final manifest carries `complete=false`, known-versus-unknown accounting and hashes of whatever was actually written. On complete nonempty success, all four row-key sets and variant/window assignments agree, counts reconcile with local evidence, and dependency graphs cover exactly 80 populations/77 components. `variant-windows.tsv` fields: `variant_id,window_id,chrom,start0,end0,source_uri,source_generation`; each variant appears exactly once. Full source/range evidence remains bound via acquisition hash.

Canonical JSON is sorted keys, compact separators, ASCII escaping, no NaN, LF; immutable record hash mappings are sorted unique tuples in memory. TSV is UTF-8, tabs, LF, exact columns and decimal integer tokens. Scientific manifests contain no timestamps, runtime durations or local absolute paths. Validators recompute hashes/sizes, canonical serialization, identity joins, scope cardinalities, row accounting, count subset checks, control counts, sidecar relationships and false eligibility; they do not trust filenames or a boolean success flag. Hashes of BCF/container bytes establish retained artifact identity; byte reproducibility is required only within frozen tools/platform, while original records and count semantics have independent exact controls.

## 6.1 Exact versioned records and wire fields

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

Exact array sets/orders: sources and indexes use natural chr1–chr22; both window arrays use frozen manifest order and have exactly 66 entries. Every preparation window has exactly two stage receipts, technical then paper, even on failure. Stage native_control/native_tokens explicitly bind complete or partial native artifacts; no filename matching is used to infer their role. NativeCountFiles.input_bcf is the one parent-acquisition-root reference; all of its other ArtifactRefs and NativeTokenFiles.input_bcf resolve inside preparation. A complete nonempty stage requires complete control/token artifacts with native_tokens.input_bcf equal to native_control.selected_bcf. Empty stages carry null native artifacts and zero tested variants, not a synthetic native success. Complete manifests have four tracks ordered technical-called, technical-quality, paper-called, paper-quality; refused preparation has **zero admitted tracks** and retained partial products only in `files`. File inventories are path-sorted, unique, include every scientific file/partial file and every native stdout/stderr mentioned by nested records in that phase root (parent-acquisition input_bcf is validated against acquisition_root instead), and exclude the manifest being written and runtime timing logs. Repeated references to one file are permitted only with identical size/hash. No sparse logical-file checksum appears in `files`; its actual range evidence and verified-source record are the identity. Runtime native `.partial` stdout/stderr files have hashes of their exact retained bytes, never a claim of complete native output.

Acquisition success requires all sources ready and all window states successful, even if all windows have no records. `verified` exists only after exact all-range/index/sparse validation; `header` exists only after header qualification. Retain verified coverage if later header failure refuses that source. A refused window may retain complete intermediate raw/native files and known counts, but no consumer may admit it; unknown counts remain null. `no_records` requires raw/native counts exactly zero, complete source qualification and complete native execution; required empty raw/offset files and header-only BCF still have real ArtifactRefs. All range receipts exist, including not-attempted planned ranges after metadata failure. Totals sum receipts exactly, while planned bytes equal the reviewed preflight total and retained-index sum counts each of 22 bodies once.

Range/metadata adapter_invocations is exactly 0 or 1. Not-attempted receipts have zero requested/received/stdout bytes, null retained/stderr/exit_code fields, and both overflow flags false. For attempted ranges requested_bytes=last−first+1, received_bytes≤requested_bytes+1 and retained.size_bytes=received_bytes with sha256=retained.sha256; retain even a zero-byte attempted stdout file. Attempted metadata retains stdout with size=stdout_bytes≤1,048,577. Every attempted transport invocation retains stderr, with size≤1,048,577; exit_code records the observed exit or is null only when unavailable. Range verified/metadata verified requires exact requested range length or qualified metadata respectively, zero exit and no overflow. Partial/refused receipts carry the failure reason and exact retained-prefix evidence; both are non-admissible. Any overflow requires limit_exceeded reason and refusal even after zero exit. Aggregate received/stdout totals include retained failed prefixes; they never represent unobserved output.

Preparation success requires both stage receipts complete for all 66 windows, identical four-table keys, valid dependency evidence and native controls. For `no_records`/`no_pass_snps`, both stage summaries explicitly have zero variants/rows/matches/interpreted calls and empty QC tally; this is absence of selected sites, not independent per-site validation. `counts_prepared` can have all rows AN=0. Native missing totals refuse the stage/window. A refused stage has null summary; any partially computed counts remain unadmitted artifacts in `files`. A successful neighboring stage may retain its complete summary even when the window is refused. `complete_empty` requires no retained variants anywhere and four actual header-only tables; represented_groups=0. Complete nonempty tracks have 80 represented groups and rows=80×variants. This keeps unknown/refused content separate from scientifically empty output.

QC keys are closed: dispositions are exactly the eight original names (`accepted`, `missing_gt`, `missing_gq`, `low_gq`, `missing_dp`, `low_dp`, `missing_het_ad`, `low_het_balance`); inspection keys are exactly `gt,gq,dp,ad_missing,ad_arity,ad_ref,ad_alt`. Stored tuples contain only positive counters, sorted by key, with missing keys meaning **zero observed visits** inside an otherwise validated complete tally, never missing evidence. Constructor checks require gt visits=all dispositions, gq visits=all dispositions except missing_gt, dp visits=gq visits minus missing_gq/low_gq; AD counters require ad_arity=ad_missing−missing_het_ad, ad_ref=ad_arity, 0≤ad_alt≤ad_ref, ad_ref−ad_alt≤low_het_balance, and 0≤ad_ref−low_het_balance≤accepted. These aggregate identities alone cannot recover each genotype; the count function and artifact content validator also recompute actual traces from the source calls. Missing-origin entries are sorted unique (field,origin), positive, and reconcile exactly with the corresponding missing disposition. A visited partial AD dot token is `literal_dot`; an unvisited QC field contributes no missing-origin count. Count/AN identities and nonzero allele-balance visits further constrain the tally; pure constructor checks reject absent coverage when calls were present. Per-variant `QcTally` and accumulated stage/window tally use the same public type, so the writer cannot invent coverage after counting.

RunProvenance uses a 40-hex code revision, unique relative source paths and SHA hashes; tool_versions/executable keys include bcftools, bcftools_htslib, tabix, bgzip, gcloud for acquisition and bcftools/bcftools_htslib for preparation. Dynamic library/plugin file hashes use relative labeled entries in executable_sha256; SDK hashes use SDK-relative paths; preparation sdk_source_sha256 is the empty tuple because its parent acquisition carries transport evidence. No absolute process environment or local paths enter argv_template: executable is a tool label, each input/output argument is an artifact-root-relative path, an explicit `@acquisition/`-prefixed relative parent input, or a literal frozen region/format argument. Execution resolves these templates to absolute paths privately; no absolute path is serialized.

## 6.2 Fixed sidecar shapes and public artifact APIs

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
                           preflight: BytePreflight) -> ArtifactRef
validate_acquisition(directory: Path) -> AcquisitionManifest
write_preparation_manifest(directory: Path, manifest: PreparationManifest, *,
                           acquisition_root: Path) -> ArtifactRef
validate_preparation(directory: Path, *, acquisition_root: Path) -> PreparationManifest
```

Each writer is called on an already exclusively created directory after artifact-producing steps, validates typed contents, existing-file hashes/sizes, exact file inventory, semantic sidecar/table counts and parent binding **before** exclusively writing its final manifest. It fsyncs/closes the manifest and returns its external ArtifactRef. It never creates an accepted review or changes complete/refused states to hide a failed check. Validators re-read canonical bytes and all referenced real content; hashes alone do not certify row semantics. `validate_acquisition` redecodes its copied upstream manifest/preflight/review and revalidates retained indexes and actual coverage; its returned AcquisitionManifest contains verified source receipts for the caller. `validate_preparation` binds its copied acquisition-manifest hash to `acquisition_root/acquisition.json`, deeply validates that root and rechecks all four tables, exact row/site/window alignment, QC counts and dependency sidecars. Refused manifests may be decoded/validated as truthful ledgers but are rejected by acquisition→preparation consumers unless complete. Missing final manifests are never valid inputs.

## 7. Module boundaries and CLI

| File | Responsibility |
| --- | --- |
| `genomeos/validation/reference_acquisition_types.py` | Closed immutable acquisition, file/process evidence and verified-coverage records. |
| `genomeos/validation/reference_preflight_input.py` | Strict #254 consumer/review codec and retained-index revalidation. |
| `genomeos/validation/reference_vcf_tokens.py` | Pure BGZF-member and header/VCF token codecs; preserves original lexemes. |
| `genomeos/validation/reference_cohorts.py` | Pure exact cohort selection and source-order population mapping. |
| `genomeos/validation/reference_genotypes.py` | Pure lazy QC assessment and population count arithmetic. |
| `genomeos/validation/reference_preparation_types.py` | Preparation-only manifest/stage/track/dependency records. |
| `genomeos/validation/reference_acquisition_codec.py` | Pure strict acquisition manifest codec. |
| `genomeos/validation/reference_preparation_codec.py` | Pure strict preparation manifest codec. |
| `genomeos/validation/reference_preparation.py` | Pure ReferenceCount/sidecar projection and reconciliation. |
| `scripts/reference_window_io.py` | Bounded network/file/subprocess and sparse/raw/native extraction adapters. |
| `scripts/reference_window_artifacts.py` | Exclusive writers and content validators for acquisition/count manifests. |
| `scripts/acquire_reference_windows.py` | Composition: preflight/review/input checks → range acquisition → extraction → manifest. |
| `scripts/prepare_reference_window_counts.py` | Composition: validated local acquisition → cohort/count/native checks → tables/manifest. |

Target each production module ≤500 logical lines. Phase-specific types and codecs are split explicitly in the file table so neither writer invents a universal manifest. Do not cross 800 logical lines/50 KiB without the repository's explicit documented exception. No factories, registries, generic genomic framework or dependency additions.

```text
PYTHONPATH=. python scripts/acquire_reference_windows.py \
  --windows-dir FROZEN_WINDOWS --preflight-dir REVIEWED_PREFLIGHT \
  --review REVIEW_RECEIPT --metadata FROZEN_METADATA --outliers FROZEN_OUTLIERS \
  --cohort-exclusions PRIVATE_RECIPE --technical-samples ORIGINAL_TECHNICAL_LIST \
  --paper-samples ORIGINAL_PAPER_LIST --dependency-audit ORIGINAL_DEPENDENCY_AUDIT \
  --bcftools /opt/homebrew/bin/bcftools --tabix /opt/homebrew/bin/tabix \
  --bgzip /opt/homebrew/bin/bgzip --out NEW_ACQUISITION_DIRECTORY

PYTHONPATH=. python scripts/prepare_reference_window_counts.py \
  --acquisition COMPLETE_ACQUISITION_DIRECTORY --metadata FROZEN_METADATA \
  --outliers FROZEN_OUTLIERS --cohort-exclusions PRIVATE_RECIPE \
  --technical-samples ORIGINAL_TECHNICAL_LIST --paper-samples ORIGINAL_PAPER_LIST \
  --dependency-audit ORIGINAL_DEPENDENCY_AUDIT \
  --bcftools /opt/homebrew/bin/bcftools --out NEW_COUNTS_DIRECTORY
```

Paths are caller inputs, not embedded workstation paths. All flags are required; no relaxed-QC, increase-prefix, alternative-cohort, fallback-source, skip-review or retry switch. `--help` is read-only. Native versions must be bcftools/HTSlib/tabix/bgzip 1.23.1 for the real campaign; record resolved executable/plugin/library hashes and actual version stdout. Hash the executed checkout files after confirming imports resolve inside that checkout. No native/network process is permitted in pure domain tests.

## 8. Acceptance gates and scope limits

All six implementation tasks in the companion plan end with RED/GREEN evidence, focused tests, smoke/privacy checks and a reviewable software commit. Task 6 ends at verified software and explicitly unexecuted real-data status. A separate controller-only phase follows all six task reviews and whole-branch independent review; workers do not create a self-approval or acquire real bytes to finish their software task. In that controller-only phase, before retrieval, complete all synthetic adversarial/hand/native checks with the actual native versions and zero skipped required local native controls; obtain independent review of that exact acquisition/count source and the actual complete #254 preflight. Real acquisition then produces its own independently audited evidence, with no synthetic-only result labeled real data. Before a dedicated PR is complete run Ruff, frozen contracts, module size, privacy, smoke and full pytest, reporting exact counts/skips and failures.

This prepares research data. Population folds, whole-window/chromosome folds, model calibration/comparison, geographic eligibility, external confirmation and publication remain separate gates. No GPU or model is used. No source genomic/index bodies were acquired to write this design.
