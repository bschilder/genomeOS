"""Durable spatial-benchmark fold checkpoints (design §§5, 7–8, 12; #319, #333).

Scientific objective
    Preserve terminal offline fold evidence across infrastructure interruption without changing,
    retrying, or selectively omitting any scientific result.
Acceptance evidence
    A checkpoint is a contiguous prefix of immutable, integrity-hashed fold artifacts under an
    exact versioned identity covering inputs, configuration, splits, seeds, code, and packages.
Engineering interface
    :func:`initialize_checkpoint`, :func:`write_fold_checkpoint`, and
    :func:`load_fold_checkpoints` are the filesystem adapter around the pure fold functions in
    :mod:`genomeos.validation.spatial_gp_benchmark`.
Assumptions and refusals
    Only terminal folds are checkpointed. Resume refuses identity drift, corrupt or unknown
    artifacts, noncontiguous progress, and attempts to overwrite an existing fold.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from math import isfinite
from numbers import Integral, Real
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from genomeos.surfaces.convergence import SamplerDiagnostics
from genomeos.validation.benchmark import BenchmarkFoldStatus
from genomeos.validation.spatial_gp_benchmark import (
    PREDICTION_COLUMNS,
    SpatialGPFoldResult,
)
from genomeos.validation.splits import BenchmarkSplit

CHECKPOINT_SCHEMA_VERSION = 2
HEADER_FILENAME = "checkpoint.json"
FOLD_DIRECTORY = "folds"
_HEADER_BODY_FIELDS = (
    "schema_version",
    "model_id",
    "evidence_kind",
    "qualification",
    "configuration",
    "configuration_sha256",
    "input_files",
    "inputs_sha256",
    "planned_splits",
    "planned_splits_sha256",
    "seed_schedule",
    "seed_schedule_sha256",
    "code_revision",
    "science_source_sha256",
    "package_versions",
)
_HEADER_FIELDS = _HEADER_BODY_FIELDS + ("header_sha256",)
_ARTIFACT_BODY_FIELDS = (
    "schema_version",
    "ordinal",
    "split_id",
    "block_id",
    "expected_test_ids",
    "status",
    "failure_reason",
    "sampler_diagnostics",
    "prediction_columns",
    "prediction_rows",
)
_ARTIFACT_FIELDS = _ARTIFACT_BODY_FIELDS + ("artifact_sha256",)


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()


def _canonical_hash(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _json_value(value: object, field: str) -> Any:
    try:
        return json.loads(_canonical_bytes(value))
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field} must be finite JSON-compatible data") from error


def _label(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a nonempty string")
    return value


def build_checkpoint_header(
    *,
    model_id: str,
    evidence_kind: str,
    qualification: Mapping[str, object],
    configuration: Mapping[str, object],
    input_files: Mapping[str, object],
    planned_splits: Sequence[Mapping[str, object]],
    seed_schedule: Sequence[Mapping[str, object]],
    code_revision: str,
    science_source_sha256: Mapping[str, str],
    package_versions: Mapping[str, str],
) -> dict[str, object]:
    """Build the canonical versioned identity that an explicit resume must match."""
    split_records = _json_value(list(planned_splits), "planned_splits")
    seed_records = _json_value(list(seed_schedule), "seed_schedule")
    config_record = _json_value(dict(configuration), "configuration")
    input_records = _json_value(dict(input_files), "input_files")
    body = {
        "schema_version": CHECKPOINT_SCHEMA_VERSION,
        "model_id": _label(model_id, "model_id"),
        "evidence_kind": _label(evidence_kind, "evidence_kind"),
        "qualification": _json_value(dict(qualification), "qualification"),
        "configuration": config_record,
        "configuration_sha256": _canonical_hash(config_record),
        "input_files": input_records,
        "inputs_sha256": _canonical_hash(input_records),
        "planned_splits": split_records,
        "planned_splits_sha256": _canonical_hash(split_records),
        "seed_schedule": seed_records,
        "seed_schedule_sha256": _canonical_hash(seed_records),
        "code_revision": _label(code_revision, "code_revision"),
        "science_source_sha256": _json_value(
            dict(science_source_sha256), "science_source_sha256"
        ),
        "package_versions": _json_value(dict(package_versions), "package_versions"),
    }
    return {**body, "header_sha256": _canonical_hash(body)}


def _validate_header(document: object) -> dict[str, object]:
    if not isinstance(document, dict) or set(document) != set(_HEADER_FIELDS):
        raise ValueError("checkpoint header fields are invalid")
    body = {field: document[field] for field in _HEADER_BODY_FIELDS}
    if document["schema_version"] != CHECKPOINT_SCHEMA_VERSION:
        raise ValueError("checkpoint schema version is unsupported")
    if document["header_sha256"] != _canonical_hash(body):
        raise ValueError("checkpoint header integrity check failed")
    return document


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, allow_nan=False, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode()


def _atomic_write_new(path: Path, data: bytes) -> None:
    if path.exists():
        raise FileExistsError(f"immutable checkpoint artifact already exists: {path}")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.tmp-", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError as error:
            raise FileExistsError(
                f"immutable checkpoint artifact already exists: {path}"
            ) from error
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"checkpoint JSON contains duplicate key {key!r}")
        result[key] = value
    return result


def _read_json(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(), object_pairs_hook=_unique_object)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"checkpoint JSON is unreadable: {path}") from error
    if not isinstance(value, dict):
        raise ValueError(f"checkpoint JSON must contain an object: {path}")
    return value


def initialize_checkpoint(path: Path, header: Mapping[str, object]) -> None:
    """Create a new checkpoint directory and publish its immutable identity."""
    path = Path(path)
    validated = _validate_header(dict(header))
    if path.exists():
        raise ValueError(f"checkpoint directory already exists: {path}")
    path.mkdir(parents=True, exist_ok=False)
    (path / FOLD_DIRECTORY).mkdir()
    _atomic_write_new(path / HEADER_FILENAME, _json_bytes(validated))


def _encode_scalar(value: object, column: str) -> object:
    if isinstance(value, np.generic):
        value = value.item()
    if value is None or isinstance(value, (str, bool, Integral)):
        return value
    if isinstance(value, Real):
        number = float(value)
        if isfinite(number):
            return number
        if column == "log_score" and number == float("-inf"):
            return "-Infinity"
    raise ValueError(f"checkpoint prediction {column} contains a non-JSON value")


def _validate_fold_result(
    split: BenchmarkSplit, result: SpatialGPFoldResult
) -> pd.DataFrame:
    if not isinstance(result, SpatialGPFoldResult):
        raise TypeError("result must be a SpatialGPFoldResult")
    if result.status.split_id != split.split_id:
        raise ValueError("fold result split_id does not match checkpoint split")
    if result.status.expected_test_ids != split.test_ids:
        raise ValueError("fold result expected_test_ids do not match checkpoint split")
    frame = result.predictions
    if not isinstance(frame, pd.DataFrame) or tuple(frame.columns) != PREDICTION_COLUMNS:
        raise ValueError("fold checkpoint predictions have invalid columns")
    if result.status.status == "completed":
        if frame["source_record_id"].duplicated().any() or set(
            frame["source_record_id"]
        ) != set(split.test_ids):
            raise ValueError("completed fold predictions must match expected_test_ids exactly")
        if set(frame["split_id"]) != {split.split_id} or set(frame["block_id"]) != {
            split.block_id
        }:
            raise ValueError("completed fold predictions have the wrong split identity")
    elif not frame.empty:
        raise ValueError("failed or infeasible fold checkpoints must not contain predictions")
    return frame


def _artifact_document(
    ordinal: int,
    split: BenchmarkSplit,
    result: SpatialGPFoldResult,
) -> dict[str, object]:
    if isinstance(ordinal, bool) or not isinstance(ordinal, Integral) or ordinal < 0:
        raise ValueError("fold ordinal must be a nonnegative integer")
    frame = _validate_fold_result(split, result)
    rows = [
        [_encode_scalar(value, column) for value, column in zip(row, PREDICTION_COLUMNS, strict=True)]
        for row in frame.itertuples(index=False, name=None)
    ]
    body = {
        "schema_version": CHECKPOINT_SCHEMA_VERSION,
        "ordinal": int(ordinal),
        "split_id": split.split_id,
        "block_id": split.block_id,
        "expected_test_ids": list(split.test_ids),
        "status": result.status.status,
        "failure_reason": result.status.failure_reason,
        "sampler_diagnostics": (
            asdict(result.sampler_diagnostics)
            if result.sampler_diagnostics is not None
            else None
        ),
        "prediction_columns": list(PREDICTION_COLUMNS),
        "prediction_rows": rows,
    }
    return {**body, "artifact_sha256": _canonical_hash(body)}


def write_fold_checkpoint(
    path: Path,
    ordinal: int,
    split: BenchmarkSplit,
    result: SpatialGPFoldResult,
) -> None:
    """Atomically publish one immutable terminal-fold artifact."""
    root = Path(path)
    folds = root / FOLD_DIRECTORY
    if not (root / HEADER_FILENAME).is_file() or not folds.is_dir():
        raise ValueError(f"checkpoint directory is incomplete: {root}")
    document = _artifact_document(ordinal, split, result)
    _atomic_write_new(folds / f"{ordinal:04d}.json", _json_bytes(document))


def _decode_artifact(
    path: Path, ordinal: int, split: BenchmarkSplit
) -> SpatialGPFoldResult:
    document = _read_json(path)
    if set(document) != set(_ARTIFACT_FIELDS):
        raise ValueError(f"checkpoint fold artifact fields are invalid: {path.name}")
    body = {field: document[field] for field in _ARTIFACT_BODY_FIELDS}
    if document["artifact_sha256"] != _canonical_hash(body):
        raise ValueError(f"checkpoint fold artifact integrity check failed: {path.name}")
    if document["schema_version"] != CHECKPOINT_SCHEMA_VERSION:
        raise ValueError("checkpoint fold schema version is unsupported")
    if (
        document["ordinal"] != ordinal
        or document["split_id"] != split.split_id
        or document["block_id"] != split.block_id
        or document["expected_test_ids"] != list(split.test_ids)
        or document["prediction_columns"] != list(PREDICTION_COLUMNS)
    ):
        raise ValueError(f"checkpoint fold identity mismatch: {path.name}")
    rows = document["prediction_rows"]
    if not isinstance(rows, list) or any(
        not isinstance(row, list) or len(row) != len(PREDICTION_COLUMNS) for row in rows
    ):
        raise ValueError(f"checkpoint prediction rows are invalid: {path.name}")
    decoded = []
    for row in rows:
        values = list(row)
        log_index = PREDICTION_COLUMNS.index("log_score")
        if values[log_index] == "-Infinity":
            values[log_index] = float("-inf")
        decoded.append(values)
    frame = pd.DataFrame(decoded, columns=PREDICTION_COLUMNS)
    try:
        status = BenchmarkFoldStatus(
            split_id=split.split_id,
            status=document["status"],
            expected_test_ids=split.test_ids,
            failure_reason=document["failure_reason"],
        )
    except (TypeError, ValueError) as error:
        raise ValueError(f"checkpoint fold status is invalid: {path.name}") from error
    diagnostics_record = document["sampler_diagnostics"]
    try:
        diagnostics = (
            None
            if diagnostics_record is None
            else SamplerDiagnostics(**diagnostics_record)
        )
    except (TypeError, ValueError) as error:
        raise ValueError(
            f"checkpoint sampler diagnostics are invalid: {path.name}"
        ) from error
    try:
        result = SpatialGPFoldResult(
            status=status,
            predictions=frame,
            sampler_diagnostics=diagnostics,
        )
    except (TypeError, ValueError) as error:
        raise ValueError(f"checkpoint fold result is invalid: {path.name}") from error
    _validate_fold_result(split, result)
    return result


def _visible_names(path: Path) -> set[str]:
    return {entry.name for entry in path.iterdir() if not entry.name.startswith(".")}


def load_fold_checkpoints(
    path: Path,
    expected_header: Mapping[str, object],
    splits: Sequence[BenchmarkSplit],
) -> tuple[SpatialGPFoldResult, ...]:
    """Validate an explicit checkpoint and return its contiguous terminal prefix."""
    root = Path(path)
    if not root.is_dir():
        raise ValueError(f"resume checkpoint directory does not exist: {root}")
    if _visible_names(root) != {HEADER_FILENAME, FOLD_DIRECTORY}:
        raise ValueError("checkpoint directory contains unknown or missing artifacts")
    folds = root / FOLD_DIRECTORY
    if not folds.is_dir():
        raise ValueError("checkpoint fold directory is missing")
    actual_header = _validate_header(_read_json(root / HEADER_FILENAME))
    expected = _validate_header(dict(expected_header))
    if actual_header != expected:
        raise ValueError("checkpoint header mismatch; resume identity changed")

    split_tuple = tuple(splits)
    expected_names = {f"{ordinal:04d}.json" for ordinal in range(len(split_tuple))}
    actual_names = _visible_names(folds)
    if not actual_names <= expected_names:
        raise ValueError("checkpoint fold directory contains unknown artifacts")
    present = [f"{ordinal:04d}.json" in actual_names for ordinal in range(len(split_tuple))]
    completed_count = sum(present)
    if present != [ordinal < completed_count for ordinal in range(len(split_tuple))]:
        raise ValueError("checkpoint folds must form a contiguous prefix")
    return tuple(
        _decode_artifact(folds / f"{ordinal:04d}.json", ordinal, split_tuple[ordinal])
        for ordinal in range(completed_count)
    )
