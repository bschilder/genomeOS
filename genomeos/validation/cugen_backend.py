"""Verified public CuGen source boundary (CuGen pilot design §§2, 7-8; Atlas §§4-5).

The loader admits one explicit pinned source tree before importing it and returns only the
three public callables used by the synthetic pilot, plus immutable byte provenance.
"""

from __future__ import annotations

import hashlib
import importlib
import inspect
import json
import re
import stat
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

_SOURCE_ALLOWLIST = Path(__file__).with_name("cugen_source.json")
_PINNED_REPOSITORY = "https://github.com/bschilder/cugen"
_PINNED_REVISION = "b95adbaabef1ca5ff2795b9435e9bb7d6aebb9a1"
_PUBLIC_SOURCES = (
    "cugen/__init__.py",
    "cugen/write.py",
    "cugen/subset.py",
    "cugen/ld.py",
)

SourceHashes = tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class VerifiedCuGenAPI:
    """Checked public CuGen callables and immutable executing-source provenance."""

    repository: str
    revision: str
    allowlist_files: SourceHashes
    imported_files: SourceHashes
    write_cugen: Callable[..., object]
    subset_cugen_file: Callable[..., object]
    ld_matrix: Callable[..., pd.DataFrame]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_manifest() -> dict[str, Any]:
    with _SOURCE_ALLOWLIST.open("r", encoding="utf-8") as stream:
        document = json.load(stream)
    if not isinstance(document, dict) or set(document) != {
        "schema_version",
        "repository",
        "revision",
        "files",
    }:
        raise ValueError("tracked CuGen source allowlist has an invalid schema")
    if (
        type(document["schema_version"]) is not int
        or document["schema_version"] != 1
        or document["repository"] != _PINNED_REPOSITORY
        or document["revision"] != _PINNED_REVISION
        or not isinstance(document["files"], list)
    ):
        raise ValueError("tracked CuGen source allowlist identity is invalid")
    return document


def _validate_source_root(root: Path) -> tuple[str, str, SourceHashes]:
    base = Path(root)
    if base.is_symlink() or not base.is_dir():
        raise ValueError("cugen_root must be a real source directory")
    document = _source_manifest()
    expected: dict[str, tuple[int, str]] = {}
    for record in document["files"]:
        if not isinstance(record, dict) or set(record) != {"path", "bytes", "sha256"}:
            raise ValueError("tracked CuGen source file record is invalid")
        relative = record["path"]
        if (
            not isinstance(relative, str)
            or Path(relative).is_absolute()
            or ".." in Path(relative).parts
            or relative in expected
            or type(record["bytes"]) is not int
            or record["bytes"] < 0
            or not isinstance(record["sha256"], str)
            or re.fullmatch(r"[0-9a-f]{64}", record["sha256"]) is None
        ):
            raise ValueError("tracked CuGen source file record is invalid")
        expected[relative] = record["bytes"], record["sha256"]
    discovered = {str(path.relative_to(base)) for path in (base / "cugen").rglob("*.py")}
    discovered.update(
        name for name in ("LICENSE", "README.md", "pyproject.toml") if (base / name).exists()
    )
    if discovered != set(expected):
        raise ValueError("cugen_root tracked public source set does not match the allowlist")
    hashes: list[tuple[str, str]] = []
    for relative in sorted(expected):
        expected_bytes, expected_hash = expected[relative]
        path = base / relative
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise ValueError("cugen_root source members must be regular non-symlink files")
        if metadata.st_size != expected_bytes or _sha256(path) != expected_hash:
            raise ValueError(f"cugen_root source hash mismatch for {relative}")
        hashes.append((relative, expected_hash))
    return document["repository"], document["revision"], tuple(hashes)


def _ensure_existing_modules_use_root(base: Path) -> None:
    for name, module in tuple(sys.modules.items()):
        if name == "cugen" or name.startswith("cugen."):
            location = getattr(module, "__file__", None)
            if location is None or not Path(location).resolve().is_relative_to(base):
                raise ValueError("an already imported CuGen module resolved outside cugen_root")


def _import_from_root(base: Path) -> tuple[object, object]:
    _ensure_existing_modules_use_root(base)
    sys.path.insert(0, str(base))
    try:
        importlib.invalidate_caches()
        package = importlib.import_module("cugen")
        writer_module = importlib.import_module("cugen.write")
    finally:
        try:
            sys.path.remove(str(base))
        except ValueError:
            pass
    return package, writer_module


def load_verified_cugen_api(root: Path) -> VerifiedCuGenAPI:
    """Validate the complete pinned tree, then load and source-check its public API."""
    repository, revision, allowlist_files = _validate_source_root(Path(root))
    base = Path(root).resolve()
    package, writer_module = _import_from_root(base)
    write_cugen = getattr(writer_module, "write_cugen", None)
    subset_cugen_file = getattr(package, "subset_cugen_file", None)
    ld_matrix = getattr(package, "ld_matrix", None)
    if not all(callable(item) for item in (write_cugen, subset_cugen_file, ld_matrix)):
        raise ValueError("pinned CuGen does not expose the required public functions")
    public_objects = (
        ("cugen/__init__.py", package),
        ("cugen/write.py", write_cugen),
        ("cugen/subset.py", subset_cugen_file),
        ("cugen/ld.py", ld_matrix),
    )
    expected_hashes = dict(allowlist_files)
    imported: list[tuple[str, str]] = []
    for relative, imported_object in public_objects:
        source = inspect.getsourcefile(imported_object)
        if source is None or Path(source).resolve() != (base / relative).resolve():
            raise ValueError(f"imported public CuGen source does not resolve to {relative}")
        digest = _sha256(Path(source))
        if digest != expected_hashes[relative]:
            raise ValueError(f"imported public CuGen source hash mismatch for {relative}")
        imported.append((relative, digest))
    if tuple(path for path, _ in imported) != _PUBLIC_SOURCES:
        raise AssertionError("internal public-source order drift")
    return VerifiedCuGenAPI(
        repository=repository,
        revision=revision,
        allowlist_files=allowlist_files,
        imported_files=tuple(imported),
        write_cugen=write_cugen,
        subset_cugen_file=subset_cugen_file,
        ld_matrix=ld_matrix,
    )
