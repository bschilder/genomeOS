# Reference-window selection and index preflight

**Status:** adopted by the controller under existing owner authorization, including shared immutable types and portable native-fixture verification; bounded implementation for [#254](https://github.com/bschilder/genomeOS/issues/254), advancing #189. Implements Atlas §§4–8, 12 and global AF WP0/WP1. No genotype acquisition or fitting is authorized by completing this design.

## 1. Scientific contract

1. **Claim:** outcome-independent additional genomic coverage can prepare a broader development dataset from the same released gnomAD v3.1.2 dense adjusted HGDP+1KG calls. This is neither resident-population qualification nor a claim of independent loci/studies.
2. **Output/evidence:** exactly 66 frozen coordinate windows and generation-bound VCF/TBI identities; reproducible bytes/hashes; a complete index-preflight ledger and conservative transfer plan with a hard 25 GiB cap. Tiny-frame enumeration, adversarial binary tests and independent native tabix/bcftools coverage establish engineering correctness. Real index results establish transfer feasibility only.
3. **Component/interface:** pure typed coordinate selection, source-manifest validation and TBI byte planning, surrounded by a local freeze CLI and one public-index acquisition adapter. They output versioned JSON/TSV, never `ReferenceCount` rows.
4. **Assumptions/refusals/consumers:** the audited release, header declarations and source terms remain explicit inputs. Invalid or unresolved generation identity, corrupt index, unsupported format, invalid bounds and over-budget plans refuse. Subsequent separately specified acquisition/count extraction consumes the immutable plan. Missing windows remain missing evidence.

The original 12 B0 and 24 B0H input/run sets remain immutable. Expanded evidence is development-only, `publication_eligible=false`, `p1_eligible=false`; no release, P1 geography, counts, model comparison or live calibration changes occur here.

## 2. Source evidence and frozen interpretation

Use the September 10 metadata audit's `public-object-metadata.json` (SHA-256 `afdeebe980f41b9d66fd4f05e372502ecfb2bc26fdb7f6b47dfc7a7bab0b35bc`), `pilot-contigs.txt` and `report.md` as explicit local inputs. Their temporary location is supplied by the caller, not embedded into package code. Fixture source metadata is synthetic; the real freeze is a generated output.

The audited listing contains 24 VCF/TBI pairs; select exactly chr1–chr22 and record chrX/chrY as out of scope. Autosome VCF metadata total 3,475,690,484,247 bytes and TBI metadata total 3,000,550 bytes. These are inventory sizes, not an estimated transfer. The [official download definition](https://github.com/broadinstitute/gnomad-browser/blob/16e39929a8938c334a8eee4d7d0c7a67e6624153/browser/src/DataPage/GnomadV3Downloads.tsx) agrees with published VCF checksum metadata according to that audit; whole VCF bytes have not been verified.

Lengths come literally from the previously inspected header's `assembly=gnomAD_GRCh38` declarations. Record this as `saved_pilot_header_declarations`, not verification of all chromosome headers, a FASTA digest or current residence. No VCF prefix is fetched during this issue. Later acquisition must separately check each header and sample identities before count extraction.

Freeze these downstream compatibility constraints without implementing them: 80 literal source population labels; 4,117 technical-QC and 4,094 paper-ancestry cohorts separately; called and quality sensitivities separately; PASS biallelic A/C/G/T SNPs; complete diploid dosage and missing calls excluded from AN; existing GQ≥20, DP≥10 and heterozygote each-allele AD/DP≥0.2 rules unchanged. The source audit describes these rules; this task does not re-verify them or inspect participants. No INFO-count substitution, new QC, mask, MAF filter or replacement callset.

`ReferenceCount(record_id, variant_id, group_id, region_id, variant_group, ac, an)` remains unchanged. It permits AN=0 but the table validator rejects an empty table. A missing/empty window never becomes a dummy variant or zero-frequency row. Future window acquisition status, source generations, stage/QC and block assignments stay in sidecars. Population holdouts and whole-window/chromosome holdouts remain separate future comparisons; physical separation does not remove participant, kinship, ancestry, discovery or QC dependencies.

## 3. Deterministic geometry

- Exactly three windows per chromosome in natural chr1,…,chr22 order, stratum order j=0,1,2. Width is 10,000 bases. Coordinates are zero-based half-open.
- For chromosome length L, stratum bounds are `a=L*j//3`, `b=L*(j+1)//3`. Candidate integer starts are `[a,b-width]` inclusive.
- Exclude overlap with chr22 `[20_000_000,20_010_000)` **before randomization**: remove forbidden starts `[20_000_000-width+1,20_010_000-1]`, clipped to the candidate interval. Endpoint-touching windows are eligible.
- Represent remaining starts as sorted, disjoint inclusive integer runs. Draw one rank uniformly from their total cardinality, then map the rank into the runs; no rejection/redraw loop. Refuse an empty eligible stratum.
- Use one `numpy.random.Generator(numpy.random.PCG64(42))`, one `integers(0,total,dtype=np.int64)` call per stratum, in the declared order. Declare `SEED = 42`. Record NumPy version, bit-generator, draw method/dtype/order, seed and algorithm version. A version mismatch refuses replay; it never silently changes the frozen generator.
- Window IDs are `chrN-sJ` with J=1,2,3. Preserve bounds, eligible runs/cardinality, chosen rank, start/end and source-pair identity for each ID. No external mask, replacement, minimum-distance rule or independence claim. Starts crossing strata are not in this sampling frame; equal chromosome allocation is not uniform genomic-base sampling.

Pure geometry helpers accept small integer frames for testing. The production manifest validates the exact fixed 22×3 design, including pilot exclusion; these invariants are not CLI override switches. Reject bools, fractional values, invalid chromosome identities, duplicate/missing lengths, nonpositive lengths, length≥2^29 and insufficient stratum width.

## 4. Artifact and provenance contract

Task 1 immutable dataclasses live in `reference_window_types.py`; geometry, byte codecs and CLI import them directly, with no reverse dependency or compatibility re-export. Normalized source-pair validation belongs with the types; byte decoding belongs in `reference_window_manifest.py`. Use immutable typed records with runtime validation and strict versioned JSON schemas represented by checked-in synthetic examples/tests. Do not change P0/P1 frozen contracts. Hash/provenance and parser-policy mappings are stored as unique canonical key-sorted tuples of key/value pairs, never mutable dict fields; an explicit JSON codec may render them as objects after strict duplicate-key validation. State vocabularies use closed Literal types plus runtime validation. Unknown/missing normalized fields, coercion of bool/float/string into integer fields, duplicate JSON keys, nonfinite JSON and unrecognized schema versions refuse.

| Artifact | Required contents |
| --- | --- |
| `windows.tsv` | Header `window_id,chrom,stratum,stratum_start0,stratum_end0,start0,end0` using tabs and LF; 66 rows, natural chromosome/stratum order. Integers as decimal ASCII, no index column. |
| `manifest.json` (`reference_windows_v1`) | Design constants and restrictions; data-version and evidence kind (`synthetic_fixture` or `public_reference_development`); source-audit/raw-metadata/contig/config SHA-256; normalized source pairs; all geometry decisions; source terms/audit locators; inherited count-contract description; code revision, actual imported source hashes, Python/NumPy versions; `windows.tsv` hash; eligibility flags. |
| `preflight.json` (`reference_index_preflight_v1`) | Exact manifest and window-byte hashes; parser/range policy and limits; acquisition receipts; every window's state and candidate virtual/physical ranges; per-generation merged VCF ranges; all TBI sizes and total planned bytes; completeness, budget and eligibility flags; code/tool provenance. |

`PublicObject` fields are `uri`, `generation`, `size_bytes`, `md5_b64`, `crc32c_b64`. Generation is a positive decimal string, size a positive integer, checksums strict base64 of 16/4 bytes. URI has no embedded generation/query and must exactly match the audited public family `gs://gcp-public-data--gnomad/release/3.1.2/vcf/genomes/gnomad.genomes.v3.1.2.hgdp_tgp.chrN.vcf.bgz[.tbi]`. Reject credentials, traversal, encoded separators, whitespace, wildcards and other schemes/buckets/releases. Source-pair chromosome, suffixes and VCF/index associations must match exactly. Build pinned requests from these fields, never from arbitrary metadata `mediaLink`.

The raw listing importer accepts the audited `[{url,type,metadata}]` shape with `type="cloud_object"` for both VCF and TBI (an object kind, not MIME), validates used metadata field types, URL/generation/bucket/name/size consistency and 24 complete distinct pairs, preserves the input byte hash, then explicitly projects the five fields above. Recognized metadata-only fields are `contentType,etag,id,kind,mediaLink,metageneration,selfLink,storageClass,timeCreated,timeFinalized,timeStorageClassUpdated,updated`; require strings, check `id` consistency, and reject unknown keys. These fields remain traceable through the raw hash but are explicitly omitted by projection; this is not permissive normalized-manifest parsing. The importer may explicitly omit chrX/Y, with an exclusion ledger, but cannot silently discard unexpected objects. The contig importer accepts only exact contig declaration lines; retain X/Y/M declarations as out-of-scope provenance and require each autosome once with the declared assembly. Never read a VCF or sample header to make these inputs.

Canonical JSON is `json.dumps(payload, sort_keys=True, separators=(",",":"), ensure_ascii=True, allow_nan=False) + "\n"`, UTF-8. Arrays have explicit natural chromosome/window or URI+generation/range order. Label source evidence `supplied_audit_not_reperformed`; an input audit/hash is not a new inspector due-diligence claim. Hash exact emitted bytes with SHA-256; the artifact's own hash is computed externally, avoiding self-reference. Scientific artifacts contain no timestamps, elapsed durations, absolute workstation paths or command environment. Runtime attempt timings belong in a separate log. Hashes bind raw inputs as well as normalized content.

Use a new output directory, exclusive creation and no overwrite. Verify actual imported module paths resolve inside this checkout and record their relative paths/hashes plus CLI/wrapper hashes and Git revision. No private implementation imports. Write the completion manifest last; a partial output is not successful. Consumers revalidate strict fields, expected 66 IDs, coordinate/hash/config consistency and source binding rather than trusting the file name.

## 5. Bounded TBI interpretation

This is deliberately an autosomal, single-contig, VCF-preset TBI implementation. Use the [TBI specification](https://samtools.github.io/hts-specs/tabix.pdf) for binary layout and bins; preserve the metadata-bin distinction in [HTSlib 1.23.1](https://github.com/samtools/htslib/blob/1.23.1/hts.c). No CSI, multi-contig or generic-index fallback.

The fixed parser limits are 16 MiB compressed and 64 MiB decompressed per TBI, 64 name bytes, one reference, 37,450 distinct bins maximum, 1,000,000 chunks total and 32,768 linear entries. Validate signed counts before multiplication/allocation/iteration against both these caps and remaining bytes. Limit BGZF block expansion to 65,536 bytes and total output before accumulation; validate BGZF framing, lengths, CRC/ISIZE and complete consumption, including truncated members and trailing garbage. Do not call unbounded `gzip.decompress` on untrusted input.

Require magic `TBI\1`, n_ref=1, `(format,col_seq,col_beg,col_end,meta,skip)=(2,1,2,0,35,0)` and one NUL-terminated exact expected chromosome name. Ordinary bin IDs are 0…37448; 37449 is invalid. Optional pseudo-bin 37450 has exactly two pairs: virtual reference boundaries, then mapped/unmapped **counts**. Validate each according to its meaning; never treat its counts as offsets or candidate chunks. Optional trailing `n_no_coor` is absent or exactly eight bytes, retained as unknown/explicit value; this VCF scope refuses nonzero unmapped counts or `n_no_coor`. Reject duplicate bins, reversed/zero-width ordinary chunks, invalid physical offsets and mapped counts above 2^63-1.

Parse and validate linear virtual offsets, permitting zero sentinel entries; do not require unavailable entries beyond the recorded length or infer emptiness from them. **Policy `conservative_reg2bins_v1`: union all ordinary chunks from the six overlapping TBI bin levels without linear-offset pruning.** This intentionally overplans bytes and avoids reproducing subtle native iterator lower-bound logic. Validate offsets against object size; do not clamp malformed offsets into bounds. The extra cost is visible in the final plan and subject to the same cap.

For virtual chunk `[u,v)`, physical start is `u>>16`. If `v & 65535 == 0`, physical inclusive end is `(v>>16)-1`; otherwise end is `min(size_bytes-1,(v>>16)+65535)` to cover the entire final BGZF block conservatively. Permit an exclusive terminal `(size_bytes<<16)` only for an end boundary with low bits zero. Start offsets and nonzero end-block offsets must lie within the source. BGZF block validity inside VCFs cannot be checked without later VCF acquisition; this is a source-size-bound plan, not verified genotype coverage of the real objects.

Merge touching/overlapping physical inclusive ranges within each `(uri,generation)` using integer arithmetic. Include predetermined VCF header prefix `[0,min(size,2^20)-1]` and final 28-byte EOF range `[size-28,size-1]`, refusing size<28. These ranges are **planned only** during #254; no header/sample/genotype/tail byte request is issued. A later header that exceeds the frozen prefix budget is a refusal, not automatic prefix growth.

Total planned compressed transfer is the sum of merged VCF range lengths plus every complete TBI object once. Include all 22 source pairs even for windows without candidate chunks. Hard limit is `25*1024**3 = 26_843_545_600` bytes; equality passes, exceeding it refuses without selecting replacement coordinates. There is no complete total when an index failed; preserve known partial accounting with `total_planned_bytes=null`, never report zero for unknown ranges. Actual index-transfer bytes/attempts are separate from the eventual full-plan byte count.

## 6. Index-only adapter and state ledger

Before byte acquisition, validate the whole input manifest and freeze parser policy/limits; check all declared TBI sizes and planned fixed overhead. Read every pinned VCF/TBI object's metadata through `python scripts/gcloud_repo.py run storage objects describe 'gs://…#GENERATION' --raw --format=json`; match raw API fields `generation`, decimal-string `size`, `md5Hash` and `crc32c`. The installed CLI's default output renames checksum fields and converts sizes; requesting the observed raw API shape avoids a second implicit metadata codec. Use anonymous credentials-disabled, file-logging-disabled wrapper invocations with argument arrays and no shell. Never display environment values or inspect auth stores.

Fetch only pinned `.tbi#GENERATION` bodies through the wrapper's `storage cat`, reading at most declared size+1 and the compressed cap+1; terminate on overflow or fixed timeout (120 seconds/request). One metadata attempt per VCF/TBI object and at most one TBI-body attempt per pair in v1, recorded in separate receipt counters; no automatic retry/unversioned fallback. Verify exact body size, MD5 and CRC32C, and record SHA-256. Use a bounded implementation or existing available standard dependency for CRC32C; no dependency change is required. A small pure CRC32C helper must have the independent `b"123456789" -> 0xe3069283` control. Metadata reads are capped at 1 MiB/request. Real VCF bytes never enter this process.

Each selected window has exactly one state: `index_chunks_planned`, `no_index_chunks`, or `refused`, with a reason code and source identity. Both non-refusal states have `variant_content="not_inspected"`; neither says “empty VCF”, “no SNPs”, or “zero frequency”. Candidate chunks can contain no matching records. An index failure marks all its chromosome's windows refused; continue the bounded independent index checks to retain all 66 outcomes. Budget refusal is a global result retaining successful per-window states and ranges. A malformed input manifest fails before network access.

Refused source receipts record a fixed reason (`metadata_mismatch`, `generation_unavailable`, `transfer_failed`, `size_mismatch`, `checksum_mismatch`, `index_invalid`, `limit_exceeded`) and attempt count without dumping stderr/private paths. Finish a failure ledger and exit nonzero. A complete under-budget preflight may succeed with `no_index_chunks` windows, while retaining unknown variant content. New genotype extraction and its `no_records`/`no_pass_snps`/AN=0 states are a separate task.

## 7. Acceptance and handoff

Task 1 can be accepted independently from deterministic geometry and strict local artifacts. Task 2 requires bounded parser/adapter refusal tests, exact range-accounting controls and a native synthetic coverage oracle. Check in tiny synthetic BGZF/TBI files with saved native query stdout, tool versions and fixture hashes; standard CI must run those fixture/block-coverage tests without native tools. A separate live native regeneration/query test may skip when tools are absent from CI, but must pass locally with zero skips before real index preflight. Use repetitive long INFO data to keep compressed fixtures tiny while testing long records, including a long VCF record crossing BGZF blocks and a query beyond the last indexed record. Native comparison verifies that candidate byte ranges cover independently queried variants; it does not demand byte-minimal equivalence. No passing parser self-roundtrip alone counts as the native oracle.

Freeze Task 1 from the repository root with caller-supplied, previously saved local inputs:

```bash
PYTHONPATH=. python scripts/freeze_reference_windows.py \
    --source-metadata /path/to/public-object-metadata.json \
    --contigs /path/to/pilot-contigs.txt \
    --source-audit /path/to/report.md \
    --data-version YOUR_IMMUTABLE_DATA_VERSION \
    --evidence-kind public_reference_development \
    --out /path/to/new-reference-window-directory
```

The output directory must not exist. The command validates and hashes every input before creating
it, writes `windows.tsv`, and writes the completion artifact `manifest.json` last. This local freeze
does not fetch an index or VCF byte, inspect genotypes, extract counts, or make either artifact
eligible for P1 or publication.

Run focused tests and mandatory smoke after each implementation task, then lint, contract drift, module-size, privacy and full pytest before PR. Record exact commands/results, including pre-existing failures or missing native tools. Review source generation binding, compressed/decompressed limits, final-block coverage, full-window failure retention and budget equality independently before real index preflight. Successful #254 closes only this preflight issue and advances #189. Actual genotype acquisition/count extraction and any new real-model run remain separately specified and gated.
