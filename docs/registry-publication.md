# Immutable registry publication

Population registries are local, immutable releases. Build a fixture release with an explicit
normal semantic version:

```bash
PYTHONPATH=. python scripts/build_registry.py \
  --hgdp tests/fixtures/hgdp_populations.tsv \
  --release-version 0.1.0 \
  --out data/registry-fixture-v1
```

The output contains `populations.parquet`, `population_aliases.parquet`, and `manifest.json`.
`manifest.json` is the completion marker required by `scripts/build_observations.py`; P1 refuses
legacy directories containing only the two Parquet files and refuses directories left incomplete
by an interrupted publication. Rebuild a legacy registry from its known curated source inputs into
a new path. Do not invent missing input provenance or construct a manifest retrospectively.

## Registry identity

Every population row carries the full identity
`RELEASE+sha256.DIGEST`, for example `0.1.0+sha256.` followed by all 64 lowercase SHA-256
characters. `RELEASE` is the explicitly supplied human label. It is never sufficient as a
citation, cache key, or equality key on its own.

The digest binds:

- the release label;
- the exact bytes consumed for each selected source;
- the exact bytes of the registry publication, schema, assembler, CLI, and selected source-adapter
  implementations;
- the ordered logical population and alias tables, using the frozen schema column order and exact
  scalar values.

Row order is significant and DataFrame indexes are excluded. The population logical hash omits
only `registry_version` to avoid a circular digest. File records in the manifest separately bind
the exact Parquet bytes, sizes, row counts, and logical table hashes. Runtime versions for Python,
pandas, pyarrow, and pandera describe the serializer environment without changing the identity.

The CLI snapshots each source once before adapter parsing, so the input record and parsed table
refer to the same bytes even if the original path changes during a build. Input filenames,
absolute paths, timestamps, environment values, and Git state are not stored.

Library composition uses the public pure operations in `genomeos.registry.release_contract`:
`validate_release_version`, `prepare_registry_release`, `verify_registry_manifest`,
`encode_registry_manifest`, and `parse_registry_manifest`. Preparation and verification return a
typed `RegistryRelease` containing copied validated tables, sorted inputs, the full identity, and
both logical hashes. Filesystem code consumes that checked result; canonical encoding and
already-validated hashing helpers remain private to the pure contract module.

## Completion and failures

The output path must not already exist. An empty directory, regular file, symlink, or dangling
symlink is refused and remains untouched. There is no overwrite, resume, retry, or cleanup mode;
choose a fresh path for every attempt.

After validation, the publisher claims the directory exclusively, writes and verifies both
Parquet files, then publishes the fully written manifest as the logical commit point. A failure
before `manifest.json` appears leaves an incomplete owned directory for inspection, and verified
readers refuse it. An error after the manifest appears may mean the release was committed before a
cleanup or durability confirmation failed. Keep the directory and run `read_registry(path)` to
determine whether its contents verify; do not retry at the same path.

This protocol targets a local filesystem on supported macOS and Linux hosts. It is not an
object-store or distributed transaction protocol and does not defend against a malicious process
with the same filesystem authority.

## Scientific limits

Hashes prove byte and logical-table identity. They do not establish population identity,
coordinate meaning, sampling support, provenance truth, source review, signatures, scientific
eligibility, licensing, or access permission. Those checks precede publication. The HGDP fixture
remains synthetic, and publishing it does not qualify it for scientific use.
