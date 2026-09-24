"""Exclusive filesystem adapter for activity-preflight task results (design §§5, 8; #384)."""

from __future__ import annotations

import os
from pathlib import Path

from genomeos.validation.spatial_activity_codec import (
    decode_spatial_activity_task_result,
    encode_spatial_activity_task_result,
)
from genomeos.validation.spatial_activity_tasks import SpatialActivityTaskResult


class SpatialActivityArtifactError(ValueError):
    """A task-result filesystem layout contradicts the artifact contract."""


def _directory(value: str | Path, *, create: bool) -> Path:
    path = Path(value)
    if create:
        path.mkdir(parents=True, exist_ok=True)
    if not path.is_dir():
        raise SpatialActivityArtifactError(f"task-result directory does not exist: {path}")
    return path


def write_spatial_activity_task_result(
    directory: str | Path,
    result: SpatialActivityTaskResult,
) -> Path:
    """Durably create one task-ID-named artifact and refuse every overwrite."""
    encoded = encode_spatial_activity_task_result(result)
    root = _directory(directory, create=True)
    path = root / f"{result.task.task_id}.json"
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError as error:
        raise FileExistsError(f"refusing to overwrite existing task result: {path}") from error
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return path


def read_spatial_activity_task_result(path: str | Path) -> SpatialActivityTaskResult:
    """Read one bounded artifact and verify its filename against its task identity."""
    source = Path(path)
    try:
        encoded = source.read_bytes()
    except OSError as error:
        raise SpatialActivityArtifactError(f"cannot read task-result artifact: {source}") from error
    result = decode_spatial_activity_task_result(encoded)
    expected = f"{result.task.task_id}.json"
    if source.name != expected:
        raise SpatialActivityArtifactError(
            f"artifact filename {source.name!r} does not match task identity {expected!r}"
        )
    return result


def load_spatial_activity_task_results(
    directory: str | Path,
) -> tuple[SpatialActivityTaskResult, ...]:
    """Load a closed directory of task artifacts in canonical task-ID order."""
    root = _directory(directory, create=False)
    entries = tuple(root.iterdir())
    unexpected = sorted(path.name for path in entries if not path.is_file() or path.suffix != ".json")
    if unexpected:
        raise SpatialActivityArtifactError(f"task-result directory has unexpected entries: {unexpected}")
    results = tuple(read_spatial_activity_task_result(path) for path in sorted(entries))
    task_ids = tuple(result.task.task_id for result in results)
    if len(set(task_ids)) != len(task_ids):
        raise SpatialActivityArtifactError("task-result directory contains duplicate task identities")
    return results
