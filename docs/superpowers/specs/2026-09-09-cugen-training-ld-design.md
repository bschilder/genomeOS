# Training-only CuGen LD admission design

Implements the owner-requested WP6 prerequisite in the global AF plan and issue #195;
advances #205. Atlas design §§4–5, 7–8, 12–13 remain binding. This is offline numerical
and engineering admission, not AF prediction, a surface, a haplotype estimate or publication.
The owner requested autonomous implementation without routine approval pauses.

## 1. Claim and evidence

Claim: an explicitly pinned CuGen can compute independently verified, correctly identified
training-only unphased ALT-dosage correlations from bounded autosomal diploid hard calls.
Acceptance is exact identity/count agreement; R absolute error <=1e-5 and R2 <=2e-5;
all requested pairs reconciled; independently decoded subset calls/statistics; and held-out
mutation invariance. Full-workflow timings and memory observations accompany correctness.
No speedup is presumed. No AF improvement or joint covariance admission follows.

Consumers are first a synthetic pilot report, then a separately evaluated LD-assisted model.
Marginal allele frequencies cannot supply these inputs. Sample partitions are supplied by
the caller, not inferred from labels; this adapter does not certify kinship or study independence.

## 2. Approach and boundaries

Use CuGen public APIs behind independent genomeOS validation. Direct unrestricted calls lack
the required identity and omission accounting. Reimplementing GPU LD in genomeOS would
duplicate the owner-selected library. Do not substitute pg_gpu or monkeypatch private CuGen.

Pin the tested owner-fork revision `b95adbaabef1ca5ff2795b9435e9bb7d6aebb9a1`
(bschilder/cugen PR #14), not the earlier diagnosed `03df168` revision. A checked-in source
hash allowlist identifies all tracked `cugen/**/*.py`, LICENSE, README.md and pyproject.toml
from that revision. Verify package bytes and actual imported public function paths. Do not
modify the original local CuGen checkout, install CuGen into default/serving dependencies,
or silently select another installation. CuGen remains optional and lazy.

Keep pure identity/count/reference and binary-decoding functions separate from file/device
orchestration. Use plain JSON and TSV, no pickle. No production observation/surface schema,
fitter, burden, serving, UI or dependency changes in this slice.

## 3. Input contract

Fixed pilot caps: 64 source variants, 4096 source samples, 2016 unordered pairs. Require at
least one source sample and variant; a reference with one variant has zero pairs, not an
error. Every public count/reference entry validates dimensions and values before allocation.

`LDVariant(gidx, variant_id, chrom, position, ref, alt)` is immutable. gidx is a nonnegative
signed-int64-range integer, chromosome is exactly one of strings `1` through `22`, position
is an integer in [1, 2147483647], ref/alt are nonempty unequal uppercase A/C/G/T sequences,
and variant_id is exactly `{chrom}-{position}-{ref}-{alt}`. A block has unique gidx and
variant_id, one chromosome, and nondecreasing positions in file-row order. Equal positions
are permitted for distinct variants. Genome build and ploidy are explicit `GRCh38` and
`autosomal_diploid`; refuse other values, do not infer them from numeric calls.

Sample IDs are nonempty whitespace-trimmed unique strings in actual source-row order. A
training selection requires explicit training indices, held_out_ids and excluded_ids.
Training is nonempty and preserves submitted order. The three sets partition every source
sample exactly once. Empty held-out or excluded sets are permitted explicitly (e.g. numeric
precision controls); a leakage experiment itself requires held-out people. Indices are
one-dimensional exact integers; reject booleans, fractional/integral floats, strings, duplicate,
negative and out-of-range indices before conversion. Reject nested/path/NPZ selectors.
No default partition labels or silent sorting. Snapshot mutable input sequences.

Calls are a 2D samples-by-variants integer array with values 0/1/2 (ALT dosage) or 3 (missing).
Reject bool, floating, object and complex arrays, negative or >3 values. Missing is never
dosage zero. Windows are explicit keyword arguments: window_variants positive integer or
None; window_bp nonnegative integer or None. Both predicates apply inclusively to file-row
distance and position difference. No diagonal/self pairs. Do not filter on MAF or R2.

## 4. Independent statistics

For every requested row pair, enumerate the nine jointly called genotype cells in row-major
(X dosage, Y dosage) order. Integer counts produce exact n, sums, squares and cross-product:

```text
numerator = n*sum_xy - sum_x*sum_y
var_x = n*sum_xx - sum_x*sum_x
var_y = n*sum_yy - sum_y*sum_y
r = numerator / sqrt(var_x*var_y)
```

Use Python integers or proven-safe int64 intermediates at the fixed caps; float64 only for
final root/division. Status precedence: n<2 `insufficient_observations`, else either variance
zero `zero_variance`, else `observed`. Undefined r/r2 are None, never zero/NaN. Preserve
all nine counts and pair identities. Do not project, impute or label the result PSD.

Per-variant moments retain called count and allele count. If no calls, biological mean/sxx/MAF
are None. Otherwise use sum/n, sumsq-sum²/n and min(mean/2,1-mean/2), independently of CuGen.
When validating storage, separately check CuGen's all-missing zero-stat convention.
Float32 storage budgets: mean absolute 2e-7; MAF absolute 1e-7; sxx absolute 1e-5*max(1,reference).

The eight-person/seven-variant fixture is:

```python
[[0,0,2,3,1,0,3], [1,1,1,3,1,3,3], [2,2,0,3,1,2,3], [0,2,0,3,1,3,0],
 [2,0,2,3,1,1,1], [1,2,0,3,1,2,3], [0,1,1,3,1,0,0], [2,0,2,3,1,2,3]]
```

Training order (4,0,2,1), gidx (30,10,70,20,60,40,50), chromosome 1 positions 101 through 701 by 100,
explicit A-to-C synthetic identities. All 21 pairs: 6 observed, 11 insufficient, 4 zero-variance.
Pair 0/1 has n=4, counts (1,0,0,0,1,0,1,0,1), R=5/11; pair 1/2 R=-1; pair 0/2 R=-5/11;
pair 0/5 R=sqrt(3)/2 with n=3. Variant 0 mean=1.25/sxx=2.75/MAF=.375; variant 1 mean=.75/sxx=2.75/MAF=.375.
Columns 0/1/5 have correlation determinant -3/121: a deliberate counterexample to joint PSD.
Precision controls include n=3072/4096 near-fixed disjoint and overlapping heterozygotes,
single/double flips, missingness, subset sizes 1/3/4/5, chunks and tiles 1/2/3.

## 5. Binary admission before CuGen import

Accept only canonical format1/encoding0 bytes: 256-byte header, magic CUPGEN01, unsigned
little-endian version/encoding at8/12, uint64 sample/variant/bpv/stats/data/gidx at16/24/32/
40/48/56, uint32flags at64. Header reserved bytes68:256 must be zero. Require HAS_GIDX_MAP=2;
only HAS_MISSING=1 may additionally be set. Require bpv=ceil(S/4), stats_offset256,
gidx_offset256+12V, data_offset256+20V, exact total length data_offset+V*bpv.
Header dimensions must satisfy caps before decoding. Statistics are three little-endian
float32 vectors (mean,sxx,MAF); gidx is little-endian int64. Packed calls are high-two-bits
first and variant-major. Padding beyond real S must be zero; it is not a sampled person.
Validate actual missing flag, every statistic, complete gidx order and expected sample count.
Reject unsupported layouts rather than claiming all other CuGen files are invalid.

## 6. Allocation admission

Let V,S,T be source variants/samples/training samples, P requested pairs, K=min(chunk,V),
B=min(tile,V), Qs=ceil(S/4), Qt=ceil(T/4). Require chunk and tile in [1,64]. Use these
deliberately conservative named workspace estimates, in bytes, in addition to dimension caps:

```text
host = 64*2**20 + 4*V*S + 8*P*T + 128*P + 64*V
       + 4*K*(T+Qs+Qt) + 2*V*(Qs+Qt)
device = 128*2**20 + 9*T + 4*V*Qt + 64*K*T + 24*B*T + 128*B*B + 64*P
```

Host accounts for full source/selection decode, pair-by-sample contingency work, metadata
and outputs. Device accounts for selection indices, packed copies, subset temporaries,
decoded float32 tiles and moment/mask/index/output work. Admission workspace budgets are
256MiB host and256MiB device. Estimates include reserves but are not proved total process
or CUDA-context peaks. Report measured peak RSS and stage-boundary pool used/retained bytes
separately; pool snapshots are not peak allocations. Do not relabel available device memory
or tile-only memory as a measured whole-workflow peak.

## 7. Offline execution and immutable artifacts

Require the caller's explicit evidence_kind=`synthetic_fixture`; refuse all other values in
this initial pilot. This declaration records caller provenance, not an authenticated proof
that arbitrary supplied bytes are synthetic. The provided CLI generates its own synthetic
inputs. Never manufacture the declaration from a filename, missing value or default.
Validate inputs/binary and estimate allocations before CuGen import. Check source file size
before reading; the largest canonical admitted file is67072bytes. Read at most67073bytes
and reject overflow/truncation or changed size rather than loading an unbounded source first.
The executing adapter refuses `no_requested_pairs` before importing CuGen: an empty pair
plan cannot demonstrate GPU LD execution. Pure reference/planning functions still return an
empty tuple for that case. Use an exclusive new output directory, reject source collisions
and existing paths including symlinks. Stage a
validated bounded source snapshot there so later source changes cannot alter the execution.
Use public subset_cugen_file with validated int64 training indices, explicit chunk_size,
use_pinned=False. Independently decode and compare output before LD. Public ld_matrix calls
are explicit numpy and gpu, stats(r,r2), sign_reference alt, missing pairwise, min_obs2,
maf_min0,min_r2=0, output_format pairs, output=None, explicit windows, tile and max_pairs2016.
Require exact bp->kb->rounded-bp round-trip. Never automatic backend/fallback.

Compare complete observed pair sets with reference; reject unexpected, duplicate, reversed,
omitted-valid or emitted-invalid pairs and any annotation/N_OBS disagreement. Verify emitted
MAF_A/MAF_B against the independent training moments within the float32 MAF storage budget.
Check finite
in-range R/R2 and reference budgets. An execution/numeric failure leaves a failed report,
nonzero CLI exit and no completion manifest. Reader warning #201 remains visible.

A completed artifact contains source.cugen, training.cugen, reference.json, cpu.tsv, gpu.tsv,
validation.json and runtime.json; manifest.json is written exclusively and last. Manifest
schema_version1, evidence_kind synthetic_fixture, publication_eligible false,
joint_covariance_admitted false, status completed; it records all sample/variant/partition,
window/chunk/tile identity, data_version, source revision/hash allowlists for both libraries,
input and every produced-file SHA256, explicit requested/executed public paths, and numeric
validation summary. For genomeOS, optional source_revision supplies a full 40-hex commit
label and is recorded as supplied, not Git-observed. If omitted, obtain a full commit from
Git at the actual executing package root; absence or malformed provenance is an error.
Always hash the actual relevant imported source files and verify their expected package paths;
neither a supplied nor Git-observed label certifies that uncommitted bytes equal that commit.
This permits a source-only GPU bundle without uploading private Git history. Scientific
identity excludes runtime measurements and runtime-file hashes; runtime is still independently
hashed in the manifest's file inventory.
The verifier requires the exact member set, rejects traversal/absolute paths/symlinks, verifies
all hashes, revalidates input/subset/partition identities and re-runs pure numeric reconciliation.
TSV reading preserves literal identity/count tokens: parse integer columns from canonical
base10 integer strings, never through floating CSV inference. Preserve literal labels such
as NA rather than treating them as missing. Float columns must parse finite in-range numbers.
Hashes prove consistency, not authenticity or source permissions. No implicit real-data admission.

## 8. Hardware experiment and acceptance

CLI generates only synthetic cases; fresh process controls CUPY_TF32=0,
NVIDIA_TF32_OVERRIDE=0, USE_PINNED_READER=0 before imports. Record the allowlisted controls,
versions, hardware, actual imported sources and method paths; do not claim instruction-level
TF32 measurement. CLI --source-revision supplies the explicit genomeOS revision for source-only
bundles, following §7; missing Git and missing supplied revision must refuse. CuPy unavailable
or no device is a failed requested experiment, not a skip.
Use seeded42 fixtures, at least3 repeated full workflows for a hand case and the64x4096
scale case, retaining cold/individual repeat times. Include creation, validation, subsetting,
independent CPU reference, library CPU/GPU LD, verification and serialization plus total wall
time, with synchronization. Report LD-only and whole-workflow times separately, not a fake
GPU-only workflow speedup obtained by excluding shared preparation/verification.

Mutate every held-out genotype in a separate source and rerun: full-source hash changes,
training bytes, statistics, pair identities/counts and CPU/GPU outputs remain identical.
Run source/binary/selection refusal tests locally before renting a GPU; then run real public
GPU execution and preserve failures. Upload only audited source and synthetic inputs to a
task-owned US/Canada pod. Retrieve/hash-check results before deletion. Source-specific real
genomes, actual predictive experiments, phased estimators and scale expansion remain follow-ups.
