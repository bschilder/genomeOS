"""Publish and verify immutable local registry releases (publication design §§storage, reader)."""

from __future__ import annotations

import hashlib
import io
import json
import os
import platform
import stat
from pathlib import Path
from typing import NoReturn

import pandas as pd
import pandera
import pyarrow

from genomeos.registry.release_contract import (
    RegistryFile,
    RegistryInput,
    RegistryManifest,
    _canonical,
    _identity_from_validated,
    _logical_sha256,
    _validate_inputs,
    _validate_release_version,
    _validated_tables,
    identify_input,
)
from genomeos.registry.schema import ALIASES_SCHEMA, POPULATIONS_SCHEMA

_POPULATIONS = "populations.parquet"
_ALIASES = "population_aliases.parquet"
_MANIFEST = "manifest.json"
_PENDING_MANIFEST = ".manifest.pending"


def _path_exists(path: Path) -> bool:
    return os.path.lexists(os.fspath(path))


def _core_implementation_inputs() -> tuple[RegistryInput, ...]:
    registry_dir = Path(__file__).resolve().parent
    files = {
        "genomeos/registry/release_contract.py": registry_dir / "release_contract.py",
        "genomeos/registry/publication.py": registry_dir / "publication.py",
        "genomeos/registry/build.py": registry_dir / "build.py",
        "genomeos/registry/schema.py": registry_dir / "schema.py",
    }
    return tuple(
        identify_input("implementation", role, path.read_bytes())
        for role, path in files.items()
    )


def _publication_inputs(inputs: tuple[RegistryInput, ...]) -> tuple[RegistryInput, ...]:
    supplied = _validate_inputs(inputs)
    records = {(item.kind, item.role): item for item in supplied}
    for core in _core_implementation_inputs():
        key = (core.kind, core.role)
        existing = records.get(key)
        if existing is not None and existing != core:
            raise ValueError(f"implementation input does not match current bytes: {core.role}")
        records[key] = core
    return _validate_inputs(tuple(records.values()))


def _software_versions() -> dict[str, str]:
    return {
        "python": platform.python_version(),
        "pandas": pd.__version__,
        "pyarrow": pyarrow.__version__,
        "pandera": pandera.__version__,
    }


def _claim_output_directory(path: Path) -> None:
    path.mkdir(exist_ok=False)


def _write_parquet_file(frame: pd.DataFrame, path: Path) -> bytes:
    with path.open("xb") as handle:
        frame.to_parquet(handle, index=False)
        handle.flush()
        os.fsync(handle.fileno())
    return path.read_bytes()


def _write_pending_manifest(path: Path, payload: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _remove_pending_manifest(path: Path) -> None:
    path.unlink()


def _deserialize_table(payload: bytes, filename: str) -> pd.DataFrame:
    try:
        return pd.read_parquet(io.BytesIO(payload))
    except Exception as exc:
        raise ValueError(f"invalid registry Parquet file {filename}") from exc


def _verify_retained_tables(
    population_bytes: bytes,
    alias_bytes: bytes,
    *,
    registry_version: str,
    populations_logical_sha256: str,
    aliases_logical_sha256: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    populations = _deserialize_table(population_bytes, _POPULATIONS)
    aliases = _deserialize_table(alias_bytes, _ALIASES)
    if list(populations.columns) != list(POPULATIONS_SCHEMA.columns):
        raise ValueError(f"invalid registry column order in {_POPULATIONS}")
    if list(aliases.columns) != list(ALIASES_SCHEMA.columns):
        raise ValueError(f"invalid registry column order in {_ALIASES}")
    try:
        populations, aliases = _validated_tables(populations, aliases)
    except Exception as exc:
        raise ValueError("invalid registry table contract") from exc
    if not populations.empty and not populations["registry_version"].eq(registry_version).all():
        raise ValueError("population rows have wrong embedded registry_version")
    if _logical_sha256(populations, omit_registry_version=True) != populations_logical_sha256:
        raise ValueError("populations logical hash mismatch")
    if _logical_sha256(aliases, omit_registry_version=False) != aliases_logical_sha256:
        raise ValueError("population aliases logical hash mismatch")
    return populations, aliases


def publish_registry(
    populations: pd.DataFrame,
    aliases: pd.DataFrame,
    *,
    inputs: tuple[RegistryInput, ...],
    release_version: str,
    out: Path,
) -> RegistryManifest:
    """Publish a new local registry directory and refuse every existing destination."""
    out = Path(out)
    if _path_exists(out):
        raise FileExistsError(f"registry publication destination already exists: {out}")
    release_version = _validate_release_version(release_version)
    validated_populations, validated_aliases = _validated_tables(populations, aliases)
    if not validated_populations.empty and not validated_populations["registry_version"].eq(
        release_version
    ).all():
        raise ValueError("incoming population registry_version must equal release_version")
    publication_inputs = _publication_inputs(inputs)
    registry_version, populations_logical_sha256, aliases_logical_sha256 = (
        _identity_from_validated(
            validated_populations,
            validated_aliases,
            publication_inputs,
            release_version,
        )
    )
    published_populations = validated_populations.copy(deep=True)
    published_populations["registry_version"] = registry_version
    software_versions = _software_versions()

    out.parent.mkdir(parents=True, exist_ok=True)
    _claim_output_directory(out)
    population_bytes = _write_parquet_file(published_populations, out / _POPULATIONS)
    alias_bytes = _write_parquet_file(validated_aliases, out / _ALIASES)
    retained_populations, retained_aliases = _verify_retained_tables(
        population_bytes,
        alias_bytes,
        registry_version=registry_version,
        populations_logical_sha256=populations_logical_sha256,
        aliases_logical_sha256=aliases_logical_sha256,
    )
    files = (
        RegistryFile(
            path=_POPULATIONS,
            sha256=hashlib.sha256(population_bytes).hexdigest(),
            size_bytes=len(population_bytes),
            row_count=len(retained_populations),
            logical_sha256=populations_logical_sha256,
        ),
        RegistryFile(
            path=_ALIASES,
            sha256=hashlib.sha256(alias_bytes).hexdigest(),
            size_bytes=len(alias_bytes),
            row_count=len(retained_aliases),
            logical_sha256=aliases_logical_sha256,
        ),
    )
    manifest = RegistryManifest(
        schema_version="registry-publication-v1",
        release_version=release_version,
        registry_version=registry_version,
        inputs=publication_inputs,
        files=files,
        software_versions=software_versions,
    )
    pending = out / _PENDING_MANIFEST
    _write_pending_manifest(pending, _canonical(manifest.model_dump(mode="json")))
    committed = False
    try:
        os.link(pending, out / _MANIFEST)
        committed = True
        _fsync_directory(out)
        _remove_pending_manifest(pending)
        _fsync_directory(out)
    except Exception as exc:
        if committed:
            raise RuntimeError(
                "registry publication may already be committed; verify it with read_registry"
            ) from exc
        raise
    return manifest


def _duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key in registry manifest: {key}")
        result[key] = value
    return result


def _nonfinite_constant(value: str) -> NoReturn:
    raise ValueError(f"nonfinite JSON constant in registry manifest: {value}")


def _read_regular_file(path: Path, description: str) -> bytes:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise ValueError(f"registry {description} is missing: {path.name}") from exc
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
        raise ValueError(f"registry {description} must be a regular non-symlink file")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise ValueError(f"could not read registry {description}: {path.name}") from exc


def _parse_manifest(payload: bytes) -> RegistryManifest:
    try:
        raw = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_duplicate_keys,
            parse_constant=_nonfinite_constant,
        )
        return RegistryManifest.model_validate(raw)
    except Exception as exc:
        if isinstance(exc, ValueError) and (
            "duplicate JSON key" in str(exc) or "nonfinite JSON constant" in str(exc)
        ):
            raise
        raise ValueError("invalid registry manifest") from exc


def _verify_file_bytes(path: Path, record: RegistryFile) -> bytes:
    payload = _read_regular_file(path, f"file {record.path}")
    if len(payload) != record.size_bytes:
        raise ValueError(f"registry file size mismatch: {record.path}")
    if hashlib.sha256(payload).hexdigest() != record.sha256:
        raise ValueError(f"registry file hash mismatch: {record.path}")
    return payload


def read_registry(path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Read a complete registry only after verifying its full publication contract."""
    path = Path(path)
    manifest_bytes = _read_regular_file(path / _MANIFEST, "manifest")
    manifest = _parse_manifest(manifest_bytes)
    records = {record.path: record for record in manifest.files}
    population_bytes = _verify_file_bytes(path / _POPULATIONS, records[_POPULATIONS])
    alias_bytes = _verify_file_bytes(path / _ALIASES, records[_ALIASES])
    populations, aliases = _verify_retained_tables(
        population_bytes,
        alias_bytes,
        registry_version=manifest.registry_version,
        populations_logical_sha256=records[_POPULATIONS].logical_sha256,
        aliases_logical_sha256=records[_ALIASES].logical_sha256,
    )
    if len(populations) != records[_POPULATIONS].row_count:
        raise ValueError(f"registry row count mismatch: {_POPULATIONS}")
    if len(aliases) != records[_ALIASES].row_count:
        raise ValueError(f"registry row count mismatch: {_ALIASES}")
    computed_version, populations_hash, aliases_hash = _identity_from_validated(
        populations,
        aliases,
        manifest.inputs,
        manifest.release_version,
    )
    if populations_hash != records[_POPULATIONS].logical_sha256:
        raise ValueError("registry populations logical hash mismatch")
    if aliases_hash != records[_ALIASES].logical_sha256:
        raise ValueError("registry aliases logical hash mismatch")
    if computed_version != manifest.registry_version:
        raise ValueError("registry identity mismatch")
    return populations, aliases
