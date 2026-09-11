# Immutable Registry Publication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close #262 by publishing stable, input-bound P0 identities and refusing overwritten, incomplete or altered registry releases at the P1 boundary.

**Architecture:** A pure identity/manifest module and an offline writer/verified reader surround the unchanged registry assembler and source adapters. Two existing Parquet schemas remain frozen; an atomic completion manifest binds exact input bytes, logical contents and serialized files.

**Tech Stack:** Existing Python, pandas, pandera, pyarrow and Pydantic; standard-library hashing, JSON and local filesystem operations. No new dependency.

**Spec:** `docs/superpowers/specs/2026-09-11-registry-publication-design.md`.

## Global Constraints

- Keep the canonical Parquet schemas unchanged.
- `registry_version` becomes the **full exact string** `RELEASE+sha256.DIGEST`, where RELEASE is an explicitly supplied normal semver `MAJOR.MINOR.PATCH` and DIGEST is all 64 lowercase SHA-256 hex characters.
- The CLI requires `--release-version`; no inferred or hard-coded release label remains.
- Row order is preserved and significant; DataFrame indexes are excluded.
- For populations, omit only `registry_version` to avoid a circular hash.
- Refuse any pre-existing output path, including an empty directory, regular file, symlink or dangling symlink.
- A failure at any earlier step leaves an incomplete owned directory for inspection; it is never resumed, overwritten or automatically removed.
- The fully written manifest's appearance is the logical commit point.
- No schema, dependencies, serving, model, actual registry or source qualification changes.
- Pure identity functions perform no filesystem/network/environment I/O; `build_registry` and source adapter contracts remain unchanged.
- All tests use small synthetic inputs; preserve existing artifacts and unrelated files. All changes go through a dedicated branch/PR; no main commit, merge or force push.
- Run smoke after implementation changes, focused tests while iterating, full CI before commit/PR, privacy and staged-path inspection before every commit/push.

## Files and responsibility

- Create `genomeos/registry/release_contract.py`: strict input/file/manifest types, a typed
  validated-release result, canonical table hashing, full identity calculation, and checked pure
  release/manifest operations consumed across module boundaries.
- Create `genomeos/registry/publication.py`: local publication, implementation/runtime metadata capture, verified reader, byte-level failure boundaries.
- Modify `scripts/build_registry.py`: argument validation, original-byte snapshots, existing adapter composition, publication call.
- Modify `scripts/build_observations.py`: verified P0 reader before existing P1 assembly.
- Create `tests/test_registry_publication.py`: contract, round-trip, corruption, failure and concurrency evidence.
- Modify `tests/test_build_scripts.py`: real CLI preservation, source-snapshot and P1 refusal/promotion tests.
- Create `docs/registry-publication.md`; update `docs/hgdp-registry-input.md`, the current fixture commands in `AGENTS.md`, and add a supersession note above historical Task4 in the data-foundation plan. Change only invocation examples/pointers needed for this interface. README has no current registry-build invocation to update.
- Include this plan and its spec in the implementation commit. No generated registry/figure/data file is committed.

## Task 1: Publish and consume immutable registry releases

This is one coherent unit: a completion marker without an enforcing P1 reader does
not fix the observed failure. Keep writer, reader, CLI and integration tests in one
task/review. Implements the spec in full, including all named acceptance cases.

**Files:**
- Create `genomeos/registry/release_contract.py`, `genomeos/registry/publication.py`, `tests/test_registry_publication.py`, `docs/registry-publication.md`.
- Modify `scripts/build_registry.py`, `scripts/build_observations.py`, `tests/test_build_scripts.py`, `docs/hgdp-registry-input.md`, `AGENTS.md`, `docs/superpowers/plans/2026-08-22-atlas-data-foundation.md`.
- Include controller-authored `docs/superpowers/plans/2026-09-11-registry-publication.md` and `docs/superpowers/specs/2026-09-11-registry-publication-design.md` in the task commit; update plan progress truthfully after verification.

Read `docs/superpowers/specs/2026-09-11-registry-publication-design.md` after this brief; it is the full authority for the canonical identity, local publication, reader and CLI contracts. `release_contract.py` owns pure metadata/identity validation. `publication.py` owns local I/O and runtime/source snapshot records. Both existing scripts remain thin composition boundaries. The pure assembler, source adapters and frozen schemas are unchanged.

**Interfaces:** consumes `build_registry(loaded: list[tuple[pd.DataFrame, pd.DataFrame]]) -> tuple[pd.DataFrame, pd.DataFrame]`, existing `hgdp.load(path, registry_version)` and `afnd.load(path, registry_version)`. Produces the following public API; additional private helpers stay in the responsible module:

```python
# release_contract.py
class RegistryInput(BaseModel):
    kind: Literal["source", "implementation"]
    role: str
    sha256: str
    size_bytes: int

class RegistryFile(BaseModel):
    path: Literal["populations.parquet", "population_aliases.parquet"]
    sha256: str
    size_bytes: int
    row_count: int
    logical_sha256: str

class RegistryManifest(BaseModel):
    schema_version: Literal["registry-publication-v1"]
    release_version: str
    registry_version: str
    inputs: tuple[RegistryInput, ...]
    files: tuple[RegistryFile, ...]
    software_versions: dict[str, str]

@dataclass(frozen=True)
class RegistryRelease:
    populations: pd.DataFrame
    aliases: pd.DataFrame
    inputs: tuple[RegistryInput, ...]
    release_version: str
    registry_version: str
    populations_logical_sha256: str
    aliases_logical_sha256: str

def identify_input(kind: Literal["source", "implementation"], role: str,
                   payload: bytes) -> RegistryInput:
    return RegistryInput(kind=kind, role=role,
                         sha256=hashlib.sha256(payload).hexdigest(),
                         size_bytes=len(payload))

```

Additional exact function signatures are
`registry_identity(populations: pd.DataFrame, aliases: pd.DataFrame, inputs: tuple[RegistryInput, ...], release_version: str) -> str`
in `release_contract.py`, and
`publish_registry(populations: pd.DataFrame, aliases: pd.DataFrame, *, inputs: tuple[RegistryInput, ...], release_version: str, out: Path) -> RegistryManifest`
and `read_registry(path: Path) -> tuple[pd.DataFrame, pd.DataFrame]` in
`publication.py`. Their required algorithms and refusal cases are specified below
and in the design; no unfinished function body is committed. Use
`ConfigDict(extra="forbid", frozen=True)` and strict fields/validators: reject
Boolean/nonstrict sizes/counts, malformed hashes, blank roles, duplicate input
pairs, invalid release syntax, wrong full-version syntax, and any file tuple that
does not contain each fixed filename exactly once. The required software keys are
`python`, `pandas`, `pyarrow`, `pandera`, each with a nonblank string. Identity helper
uses supplied input records; publication adds/validates the four core implementation
records before computing it. Reader uses recorded input records, not current code.
The additional reviewed module-boundary operations are `validate_release_version(release_version:
str) -> str`, `prepare_registry_release(populations, aliases, inputs, release_version) ->
RegistryRelease`, `verify_registry_manifest(populations, aliases, manifest) -> RegistryRelease`,
`encode_registry_manifest(manifest) -> bytes`, and `parse_registry_manifest(payload: bytes) ->
RegistryManifest`. They perform the checks implied by their names; production consumers do not
import private hashing or already-validated helpers.

- [x] **Step 1 — RED on the real repeat-build bug and new contract.** Add CLI
  regressions before implementation, using the existing `_run` and
  `_registry_command` helpers. Extend the command with required release argument
  in the helper, then prove old CLI refuses the new argument and lacks publication.
  Separately retain the original old-argument overwrite failure before extending
  the helper, so an argparse failure cannot replace evidence for #262.

  ```python
  def test_registry_repeat_build_preserves_every_existing_byte(tmp_path):
      out = tmp_path / "registry"
      first = _run(_registry_command(FIXTURES / "hgdp_populations.tsv", out))
      assert first.returncode == 0, first.stderr
      before = {p.name: p.read_bytes() for p in out.iterdir() if p.is_file()}
      second = _run(_registry_command(FIXTURES / "hgdp_populations.tsv", out))
      assert second.returncode != 0
      assert {p.name: p.read_bytes() for p in out.iterdir() if p.is_file()} == before
  ```

  Write small one-row fictional HGDP inputs with exact five-column headers and
  distinct latitude/radius/provenance variants. Use 1,2,2.5 and
  `synthetic:registry-publication#one` as the original values. Snapshot every old
  output byte before each changed build and assert old `read_registry` still works.
  Record all expected RED failures in the task report.

- [x] **Step 2 — GREEN pure contract and publication.** Implement exactly the spec.
  The canonical encoder and identity composition are:

  ```python
  def _canonical(value: object) -> bytes:
      return json.dumps(value, sort_keys=True, separators=(",", ":"),
                        ensure_ascii=False, allow_nan=False).encode("utf-8")

  payload = {
      "identity_schema": "registry-identity-v1",
      "release_version": release_version,
      "inputs": [record.model_dump(mode="json") for record in sorted(
          inputs, key=lambda item: (item.kind, item.role))],
      "populations_sha256": populations_logical_sha256,
      "population_aliases_sha256": aliases_logical_sha256,
  }
  full_version = release_version + "+sha256." + hashlib.sha256(_canonical(payload)).hexdigest()
  ```

  Produce logical hashes using frozen schema column order, exact scalar values,
  preserved row order and null notices as specified. Validate/copy frames through
  the existing pure assembler plus finite numeric checks. Validate incoming versions
  against RELEASE before assigning the computed version on a copy. Capture actual
  core source-file bytes and runtime versions at the I/O boundary; no Git command,
  timestamps or personal paths. Validate all preconditions before claiming output.
  Use exclusive `mkdir`, exclusive binary file handles for Parquet, flush/fsync,
  retained-byte read-back verification, then complete pending-manifest write and
  exclusive hard-link publication. Handle post-commit errors distinctly. No cleanup
  of failed output directories, overwrite mode, or retry.

- [x] **Step 3 — GREEN verified reader and CLI composition.** Read/hash each fixed
  file once, parse those same bytes and verify every contract field before returning
  tables. Parse JSON with a duplicate-key-rejecting object-pairs hook and reject
  nonfinite constants; do not deserialize arbitrary paths. In build CLI, validate
  release/out first, snapshot selected inputs in a `TemporaryDirectory`, call
  existing adapters on those snapshots, then the publisher with exact input/code
  records. Preserve AFND reporting. P1 changes only its two raw Parquet reads:

  ```python
  from genomeos.registry.publication import read_registry
  populations, aliases = read_registry(args.registry)
  ```

  Update the combined synthetic literature registry test helper to call
  `publish_registry` with hashes of the actual fixture bytes (HGDP and both curated
  literature tables). Keep real CLI subprocess invocation pinned to this checkout's
  package with `PYTHONPATH` in all build tests.

- [x] **Step 4 — boundary and failure evidence.** Complete every spec acceptance
  case in `tests/test_registry_publication.py` and `tests/test_build_scripts.py`.
  Use actual temporary Parquet files and filesystem reads; mock only the specific
  failing write/fsync/commit boundary or synchronization needed to force a race.
  A two-writer test must coordinate the final exclusive directory claim and assert
  one succeeds, one raises/refuses, and the winner's complete release verifies.
  For changed-content tampering, update the file hash/size in manifest after editing
  a coordinate and assert identity/logical checks still refuse. Test source snapshot
  mutation by replacing the original source after capture but before adapter load;
  adapter must consume captured bytes and the manifest must hash them. Test the P1
  subprocess with legacy and incomplete registry inputs: no P1 output exists.

  ```python
  def test_reader_refuses_missing_completion_manifest(tmp_path):
      incomplete = tmp_path / "incomplete"
      incomplete.mkdir()
      (incomplete / "populations.parquet").write_bytes(b"incomplete")
      with pytest.raises(ValueError, match="manifest"):
          read_registry(incomplete)
  ```

  Normalize missing/invalid publication errors as actionable `ValueError` at reader
  boundary; preserve `FileExistsError` for publication destination collisions.
  Lower-level exceptions should retain causes. Do not catch broad errors and return
  empty tables or success. Run focused tests and smoke once GREEN is reached.

- [x] **Step 5 — documentation and full verification.** Write the user guide with
  exact command, complete identity semantics, required manifest/P1 migration,
  incomplete versus committed-after-error behavior, source-review limits, local
  filesystem scope and no-overwrite rule. Update current examples only; preserve
  historical Task4 code behind a supersession pointer. Run `ruff check .`,
  `python scripts/freeze_contract.py --check`, `python scripts/check_module_size.py`,
  `python scripts/check_private_files.py`, `python scripts/smoke.py`, and full `pytest`.
  Retain complete command output and warning summaries in the private task report.
  The new modules should each stay below500 logical lines; if a coherent split is
  needed, report the responsibility/interface proposal to the controller first.

- [x] **Step 6 — self-review, stage exact files, privacy gate and commit.** Inspect
  the full diff, run `git diff --check`, stage only listed task files, inspect
  `git diff --cached --name-only`, run privacy again and commit with
  `fix: publish immutable registry identities; closes #262`. Keep all raw data,
  runtime logs and SDD files untracked. Do not push or open a PR as implementer;
  return the full report for controller task review followed by final branch review.

## Execution notes

Base is PR263 head43b636520eacde74e93e0de0699b191febe48bdb; its exact CI passed571
tests plus all gates/containerHTTP. New-worktree baseline independently passed84
focused cases with this checkout import path verified. Existing root locked Python
environment can be reused with explicit `PYTHONPATH=.`; do not reinstall/re-resolve
dependencies or alter the original environment. Local cache locations and exact
interpreter path belong only in the private task brief/report.

Controller self-review checks spec coverage, file/interface consistency, exact
canonical JSON fields, literal version marker, pre/post-commit failure behavior,
P1 enforcement and all failure/identity tests. Any newly discovered requirement
conflict receives an explicit ledger ruling before implementation changes scope.

Round-1 review fix: the controller authorized the smallest additional typed pure interface needed
to remove production imports of private `release_contract` helpers. The checked `RegistryRelease`
and release/manifest operations above preserve all originally mandated signatures and behavior.
