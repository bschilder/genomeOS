"""Bounded immutable artifact I/O (reference acquisition design §6.2)."""

from __future__ import annotations

import hashlib
import os
import re
import stat
from collections.abc import Iterator
from pathlib import Path, PurePosixPath

from genomeos.validation.reference_acquisition_types import ArtifactRef

TSV_LINE_LIMIT = 16_777_216


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def artifact_root(directory: Path) -> Path:
    require(
        isinstance(directory, Path) and directory.is_dir() and not directory.is_symlink(),
        "invalid artifact root",
    )
    return directory.resolve(strict=True)


def artifact_path(root: Path, relative: str) -> Path:
    value = PurePosixPath(relative)
    require(
        isinstance(relative, str)
        and bool(relative)
        and not value.is_absolute()
        and "\\" not in relative
        and all(part not in ("", ".", "..") for part in value.parts)
        and str(value) == relative,
        "invalid artifact path",
    )
    candidate = root / relative
    cursor = root
    for part in value.parts:
        cursor /= part
        require(not cursor.is_symlink(), "artifact path contains a symlink")
    require(
        candidate.is_file() and candidate.resolve(strict=True).is_relative_to(root),
        "artifact is unavailable",
    )
    return candidate


def artifact_identity(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(1_048_576):
            size += len(chunk)
            digest.update(chunk)
    return size, digest.hexdigest()


def read_bounded(path: Path, limit: int, label: str) -> bytes:
    """Read one unchanged regular file up to its declared ceiling."""
    with path.open("rb") as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and before.st_size <= limit,
                f"{label} exceeds its bound")
        raw = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
    before_identity = (
        before.st_dev, before.st_ino, before.st_mode, before.st_size,
        before.st_mtime_ns, before.st_ctime_ns,
    )
    after_identity = (
        after.st_dev, after.st_ino, after.st_mode, after.st_size,
        after.st_mtime_ns, after.st_ctime_ns,
    )
    require(before_identity == after_identity and len(raw) <= limit,
            f"{label} exceeds its bound")
    return raw


def read_bounded_ref(root: Path, reference: ArtifactRef, limit: int, label: str) -> bytes:
    path = artifact_path(root, reference.path)
    require(
        path.stat().st_size <= limit and reference.size_bytes <= limit,
        f"{label} exceeds its bound",
    )
    require(path.stat().st_size == reference.size_bytes, "artifact identity mismatch")
    raw = read_bounded(path, limit, label)
    require(hashlib.sha256(raw).hexdigest() == reference.sha256, "artifact identity mismatch")
    return raw


def checked_ref(root: Path, reference: ArtifactRef) -> Path:
    path = artifact_path(root, reference.path)
    require(path.stat().st_size == reference.size_bytes, "artifact identity mismatch")
    require(artifact_identity(path) == (reference.size_bytes, reference.sha256),
            "artifact identity mismatch")
    return path


def iter_tsv(path: Path, columns: tuple[str, ...]) -> Iterator[tuple[str, ...]]:
    expected_header = ("\t".join(columns) + "\n").encode()
    with path.open("rb") as handle:
        require(handle.readline(TSV_LINE_LIMIT + 1) == expected_header, "TSV columns mismatch")
        while raw := handle.readline(TSV_LINE_LIMIT + 1):
            require(
                len(raw) <= TSV_LINE_LIMIT
                and raw.endswith(b"\n")
                and b"\r" not in raw
                and b"\0" not in raw,
                "TSV must use bounded LF rows",
            )
            try:
                row = tuple(raw[:-1].decode("utf-8").split("\t"))
            except UnicodeDecodeError as error:
                raise ValueError("TSV must be UTF-8") from error
            require(len(row) == len(columns), "TSV row width mismatch")
            yield row


def natural(token: str, field: str) -> int:
    require(re.fullmatch(r"0|[1-9][0-9]*", token) is not None, f"invalid {field}")
    return int(token)


def nullable(value: object) -> str:
    return "NA" if value is None else str(value)


def write_exclusive(path: Path, raw: bytes) -> None:
    """Fsync and atomically publish new bytes without replacing an existing artifact."""
    partial = path.with_name(f"{path.name}.partial")
    descriptor = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    published = False
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(partial, path)
        published = True
        partial.unlink()
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except BaseException:
        if published:
            path.unlink(missing_ok=True)
        partial.unlink(missing_ok=True)
        raise
    finally:
        os.close(descriptor)
