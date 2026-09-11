# Immutable registry publication

September 11, 2026. Implements the preservation requirement in #262 and Atlas
design §§5–6,12–13; advances #189 WP0. Depends on the explicit HGDP input fix
in #263. No real registry is rebuilt or published by this implementation.

## Scientific contract

1. **Claim:** a cited population registry identifies stable geographic evidence.
   Changing coordinates, support, provenance, aliases or consumed input bytes
   cannot silently reuse the same full registry identity.
2. **Acceptance:** actual synthetic CLI builds prove no overwrite, distinct
   identities for changed inputs/content, reproducible identity across directories,
   preserved old bytes, recorded input/output hashes, and refusal of incomplete or
   altered publications by the P1 build.
3. **Component:** a pure identity/manifest contract and an offline publication
   adapter around the existing pure `build_registry` and source adapters. Public
   `publish_registry` and `read_registry` functions write/read the existing two
   Parquet filenames plus `manifest.json`.
4. **Assumptions and refusals:** local filesystems on supported macOS/Linux hosts;
   SHA-256 collision resistance; ordinary concurrent builders, not a malicious
   process with the same filesystem authority. Invalid schemas, conflicting input
   roles, pre-existing outputs, incomplete publications and hash/identity mismatches
   are hard errors. Input metadata and integrity are not independent source review,
   sampling truth, scientific eligibility, signatures or access permission. P1 joins
   and later citable model provenance consume this boundary.

## Chosen identity policy

Keep the canonical Parquet schemas unchanged. `registry_version` becomes the
**full exact string** `RELEASE+sha256.DIGEST`, where RELEASE is an explicitly
supplied normal semver `MAJOR.MINOR.PATCH` and DIGEST is all 64 lowercase SHA-256
hex characters. The CLI requires `--release-version`; no inferred or hard-coded
release label remains. Leading zeros, whitespace, prerelease/build suffixes and
non-string release labels are refused by this narrow release-label interface.

The full string is the citation/cache/equality key. RELEASE alone is a human
release label and never sufficient identity. SemVer build metadata does not affect
precedence ([SemVer §10](https://semver.org/#spec-item-10)); this contract does not
order data releases using SemVer precedence. The content suffix distinguishes
builds even if an operator accidentally repeats the human label in a new directory.

The identity is SHA-256 of canonical UTF-8 JSON with `sort_keys=True`,
`separators=(",", ":")`, `ensure_ascii=False`, `allow_nan=False`, and no newline.
The object has exactly five fields: `identity_schema` is `registry-identity-v1`,
`release_version` is RELEASE, `inputs` is the validated sorted record list,
`populations_sha256` and `population_aliases_sha256` are the actual logical table
hashes. Each input record has
`kind` (`source` or `implementation`), `role`, `sha256`, and `size_bytes`; records
are sorted by `(kind, role)`, each pair unique, with at least one source. Roles
are nonblank strings used only as metadata, never filesystem paths to open.
Hash and integer fields are strict; Booleans are not sizes/counts. Source payloads
are identified by their exact consumed bytes, not filenames or absolute paths.

Logical table hashes use the same canonical JSON encoding of an object with
`columns` (the ordered column-name list) and `rows` (the ordered list of row-value
lists). Columns follow the frozen schema's
declared order. Row order is preserved and significant; DataFrame indexes are
excluded. For populations, omit only `registry_version` to avoid a circular hash.
Alias columns are all included. Use Python scalar values; the nullable biocultural
notice is JSON null when absent, never a stringified missing-value token. Numeric
coordinates and radii must be finite before hashing, with existing schema bounds
and positive-radius checks retained. No coordinate rounding or label normalization.

The publisher validates/copies inputs without mutating caller frames, requires
every nonempty population frame's incoming version to equal RELEASE, computes the
full identity, and embeds that exact identity in every published population row.
Empty schema-valid tables remain supported; they do not certify usable geography.

The pure module boundary exposes a typed `RegistryRelease` result plus checked operations to
validate a release label, prepare a release, verify decoded tables against a manifest, and
encode/parse strict manifest JSON. These operations own schema, input, identity, row-count,
embedded-version and logical-hash validation. The filesystem publisher and CLI consume those
public contracts; canonical encoders, logical hashing and already-validated identity helpers
remain private implementation details inside `release_contract.py`.

Input records include the exact bytes of the core implementation files
`genomeos/registry/{release_contract,publication,build,schema}.py`, observed by the
publisher. CLI composition adds the actual `scripts/build_registry.py` and
`genomeos/registry/sources/hgdp.py` bytes, and `afnd.py` when selected. Record these
as `kind=implementation`, using repository-relative roles. Do not run Git or store
absolute source paths. These records identify an implementation snapshot, not a
complete dynamic execution trace. Direct library callers supply truthful source
bindings; the library cannot independently establish how caller-provided frames
were curated. The CLI guarantees its own byte-to-adapter binding as described below.

Alternatives considered: directory refusal alone leaves cross-directory identity
conflicts; manual semver alone needs a shared reservation service to enforce
uniqueness; hashing serialized Parquet with the embedded final version is circular.
The chosen policy stays local, reproducible and compatible with the existing string
column while binding both original inputs and resulting logical tables.

The identity names logical data plus consumed inputs/implementation; exact Parquet
serialization is separately identified by each file's manifest hash. Different
supported serialization runtimes can encode the same logical registry differently;
that is not a changed coordinate/alias claim. Byte-exact consumers pin the file
hashes as well. The same-runtime repeat-build test requires identical full bytes.

## Completion and storage contract

The publication contains `populations.parquet`, `population_aliases.parquet`, and
`manifest.json`. The manifest is strict, versioned `registry-publication-v1`, and
contains RELEASE, the full identity, all input records, and one fixed-name entry
for each Parquet file with SHA-256, byte size, row count and logical table SHA-256.
It also records actual Python/pandas/pyarrow/pandera versions as build metadata.
No timestamps, absolute paths or environment values enter it. No private inputs or
source-code copies are included in the published directory.

Refuse any pre-existing output path, including an empty directory, regular file,
symlink or dangling symlink. The CLI checks this before source parsing; after all
source/schema/identity validation, the publisher claims the final directory using
exclusive `mkdir(exist_ok=False)`. That claim decides concurrent builders: only one
may write. Parents may be created, but existing output content is never modified.

Write the two Parquet files with exclusive file creation in the owned directory;
flush/fsync each and hash the exact serialized bytes. Read those bytes back to
verify the stored schemas, logical hashes, embedded version and row counts before
committing the manifest. A failure at any earlier step leaves an incomplete owned
directory for inspection; it is never resumed, overwritten or automatically removed.
Choose a new path for another attempt.

Write complete manifest bytes to `.manifest.pending`, flush/fsync and close it,
then publish the final name with an exclusive hard link (`os.link`) and fsync the
directory. A competing final manifest name must fail rather than replace it.
The fully written manifest's appearance is the logical commit point. Remove the
temporary link after commit and fsync the directory again. If post-commit cleanup
or durability confirmation fails, preserve the completed data and raise a clear
error stating that publication may already be committed; never delete final files
or retry automatically. The reader determines integrity, not the previous process's
exit code. This is not a distributed/object-store transaction or protection from
arbitrary disk/controller failure.

## Verified reader and P1 boundary

`read_registry(path)` requires a regular non-symlink manifest and two regular
non-symlink files at the fixed names. JSON duplicate keys, nonfinite constants,
unknown fields/schema versions, malformed/duplicate file entries, mismatched
versions, invalid sizes/hashes, missing files, and altered bytes are refused.
No caller-controlled file path from JSON is followed.

Read each file's bytes once, check size/hash, and deserialize those same bytes via
`BytesIO`, preventing a separate hash/read race. Validate both canonical schemas and
the existing alias collision/orphan rules; verify row counts and every embedded
registry version. Recompute both logical hashes and full identity from the retained
manifest input records. Do not require the currently installed code's hashes to
match an older release's recorded implementation: old valid publications remain
readable across code updates that support this manifest schema.

The P1 `scripts/build_observations.py` uses this reader before source ingestion or
output creation. It does not accept legacy unmanifested directories, bypass flags,
partial success or automatic manifest reconstruction. Legacy artifacts remain on
disk; reconstruct from known curated source inputs into a new directory. Never
retroactively invent unknown input provenance. The library returns the existing
population/alias DataFrame pair; the verified full version is available in the
population rows and manifest. P1's own output publication/version design is outside
this fix; no P1 schema or fitting behavior changes.

## CLI and compatibility

```sh
PYTHONPATH=. python scripts/build_registry.py --hgdp tests/fixtures/hgdp_populations.tsv \
  --release-version 0.1.0 --out data/registry-fixture-v1
```

Require `--release-version`; retain `--hgdp`, optional `--afnd` and `--out`.
Read each selected input exactly once into bytes; use private temporary snapshots
of those bytes for the unchanged path-based adapters. Hash the same bytes and
retain the roles `hgdp` and optional `afnd`. This prevents a changed original file
from making the manifest describe different data than the adapter consumed.
Temporary snapshots are not published and are cleaned when their context exits.
Print the complete registry identity and counts; keep AFND's refusal report visible.
All argument/source errors remain nonzero with no final output directory created.

Update current invocation examples and build-script fixtures. Preserve historical
plan implementation examples with a short supersession pointer. Do not rewrite
historical reports or add defaults to make them current. No schema, dependencies,
serving, model, actual registry or source qualification changes. No scientific
figure is required because no renderable evidence/artifact is changed.

## Acceptance tests

- Two identical CLI builds in separate fresh directories have identical full
  versions, manifests and Parquet bytes in the same runtime; input path relocation
  does not affect identity. The full manifests bind the actual input/file bytes.
- Repeating a build at the same destination refuses and preserves all bytes.
  Empty/file/symlink/dangling-symlink targets also refuse without modifying them.
- Changing latitude, radius, provenance, alias content, source bytes or release
  label changes full identity; previous complete publications remain readable.
- Mutating the original source after its snapshot does not change what is parsed
  or hashed. Test the actual CLI main's snapshot-to-adapter boundary.
- Injected second-Parquet and pre-manifest failures leave no final manifest and
  are refused by the reader/P1. A deterministic concurrent-directory-claim test
  proves one writer wins and the loser leaves the winner's bytes untouched.
- Tampered/truncated files, changed logical data with a freshly updated outer file
  hash, wrong embedded version, malformed manifest, duplicate JSON/input entries,
  invalid versions, sizes and nonfinite values are refused.
- A complete build round-trips exact labels, nullable notices, schemas and supplied
  geography. Existing synthetic literature P1 promotion still passes using a
  properly published combined registry; legacy P1 input refuses before output.
- Focused tests, smoke, Ruff, frozen contracts, module budget, privacy and full
  suite pass; retain full warning text and all test evidence before commit/PR.
