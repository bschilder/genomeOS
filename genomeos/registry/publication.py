"""Publish and verify immutable local registry releases (publication design §§storage, reader)."""

from __future__ import annotations

import hashlib
import io
import os
import platform
import stat
from pathlib import Path

import pandas as pd
import pandera
import pyarrow

from genomeos.registry.release_contract import (
    RegistryFile,
    RegistryInput,
    RegistryManifest,
    encode_registry_manifest,
    identify_input,
    parse_registry_manifest,
    prepare_registry_release,
    verify_registry_manifest,
)

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
    records: dict[tuple[str, str], RegistryInput] = {}
    for raw_item in inputs:
        item = RegistryInput.model_validate(raw_item)
        key = (item.kind, item.role)
        if key in records:
            raise ValueError("duplicate registry input kind/role pair")
        records[key] = item
    for core in _core_implementation_inputs():
        key = (core.kind, core.role)
        existing = records.get(key)
        if existing is not None and existing != core:
            raise ValueError(f"implementation input does not match current bytes: {core.role}")
        records[key] = core
    return tuple(sorted(records.values(), key=lambda item: (item.kind, item.role)))


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
    publication_inputs = _publication_inputs(inputs)
    release = prepare_registry_release(
        populations,
        aliases,
        publication_inputs,
        release_version,
    )
    software_versions = _software_versions()

    out.parent.mkdir(parents=True, exist_ok=True)
    _claim_output_directory(out)
    population_bytes = _write_parquet_file(release.populations, out / _POPULATIONS)
    alias_bytes = _write_parquet_file(release.aliases, out / _ALIASES)
    retained_populations = _deserialize_table(population_bytes, _POPULATIONS)
    retained_aliases = _deserialize_table(alias_bytes, _ALIASES)
    files = (
        RegistryFile(
            path=_POPULATIONS,
            sha256=hashlib.sha256(population_bytes).hexdigest(),
            size_bytes=len(population_bytes),
            row_count=len(retained_populations),
            logical_sha256=release.populations_logical_sha256,
        ),
        RegistryFile(
            path=_ALIASES,
            sha256=hashlib.sha256(alias_bytes).hexdigest(),
            size_bytes=len(alias_bytes),
            row_count=len(retained_aliases),
            logical_sha256=release.aliases_logical_sha256,
        ),
    )
    manifest = RegistryManifest(
        schema_version="registry-publication-v1",
        release_version=release.release_version,
        registry_version=release.registry_version,
        inputs=release.inputs,
        files=files,
        software_versions=software_versions,
    )
    verify_registry_manifest(retained_populations, retained_aliases, manifest)
    pending = out / _PENDING_MANIFEST
    _write_pending_manifest(pending, encode_registry_manifest(manifest))
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
    manifest = parse_registry_manifest(manifest_bytes)
    records = {record.path: record for record in manifest.files}
    population_bytes = _verify_file_bytes(path / _POPULATIONS, records[_POPULATIONS])
    alias_bytes = _verify_file_bytes(path / _ALIASES, records[_ALIASES])
    release = verify_registry_manifest(
        _deserialize_table(population_bytes, _POPULATIONS),
        _deserialize_table(alias_bytes, _ALIASES),
        manifest,
    )
    return release.populations, release.aliases
