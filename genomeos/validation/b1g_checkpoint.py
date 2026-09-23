"""Immutable parallel outer-fold artifacts for B1G (design §§4–8, 12; #331).

Scientific objective
    Preserve every independently computed outer fold without selective retry or identity drift.
Acceptance evidence
    Each shard is integrity-hashed, bound to the frozen campaign header and split ordinal, and
    retains outer and inner sampler diagnostics. Finalization requires the complete split ledger.
Engineering interface
    :func:`write_b1g_fold_shard`, :func:`load_b1g_fold_shards`, and
    :func:`finalize_b1g_checkpoint` support parallel workers writing disjoint fold ordinals.
Assumptions and refusals
    Shards are immutable. Header drift, unknown files, malformed evidence, contradictory sampler
    status, duplicate ordinals, and incomplete finalization fail explicitly.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from math import isfinite
from numbers import Integral, Real
from pathlib import Path

import numpy as np
import pandas as pd

from genomeos.surfaces.config import FitConfig
from genomeos.surfaces.convergence import (
    SamplerDiagnostics,
    convergence_failure,
)
from genomeos.validation.b1g_attempt import (
    B1GFitAttempt,
    validate_b1g_fit_attempts,
)
from genomeos.validation.b1g_benchmark import (
    PREDICTION_COLUMNS,
    B1GBenchmarkPlan,
    B1GBenchmarkResult,
    B1GCandidateScore,
    B1GFoldResult,
    B1GFoldStatus,
    B1GInnerFoldRecord,
    derive_b1g_seed,
    finalize_b1g_benchmark,
)
from genomeos.validation.nested_folds import (
    THREE_INNER_FOLD_ALGORITHM,
    THREE_INNER_FOLD_COUNT,
    plan_three_inner_folds,
)
from genomeos.validation.spatial_gp_checkpoint import (
    FOLD_DIRECTORY,
    HEADER_FILENAME,
    validate_checkpoint_splits,
)

SHARD_SCHEMA_VERSION = 3
_BODY_FIELDS = (
    "schema_version",
    "ordinal",
    "split_id",
    "block_id",
    "expected_test_ids",
    "status",
    "selected_radius_km",
    "selected_basis_count",
    "failure_reason",
    "sampler_diagnostics",
    "fit_attempts",
    "candidate_scores",
    "prediction_columns",
    "prediction_rows",
    "runtime",
)
_FIELDS = _BODY_FIELDS + ("artifact_sha256",)


@dataclass(frozen=True)
class B1GFoldRuntime:
    """Measured resource evidence for one complete outer-fold call."""

    elapsed_seconds: float
    peak_rss_bytes: int
    device: str
    query_chunk_size: int

    def __post_init__(self) -> None:
        if (
            isinstance(self.elapsed_seconds, bool)
            or not isinstance(self.elapsed_seconds, Real)
            or not isfinite(float(self.elapsed_seconds))
            or self.elapsed_seconds < 0.0
        ):
            raise ValueError("elapsed_seconds must be finite and nonnegative")
        for value, name in (
            (self.peak_rss_bytes, "peak_rss_bytes"),
            (self.query_chunk_size, "query_chunk_size"),
        ):
            if isinstance(value, bool) or not isinstance(value, Integral) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if not isinstance(self.device, str) or not self.device.strip():
            raise ValueError("device must be a nonempty string")


@dataclass(frozen=True)
class B1GFoldShard:
    """Decoded ordinal, terminal fold evidence, and measured runtime."""

    ordinal: int
    result: B1GFoldResult
    runtime: B1GFoldRuntime


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


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, allow_nan=False, indent=2, sort_keys=True) + "\n").encode()


def _read_json(path: Path) -> dict[str, object]:
    def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"JSON contains duplicate key {key!r}: {path}")
            result[key] = value
        return result

    try:
        value = json.loads(path.read_text(), object_pairs_hook=unique)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"checkpoint JSON is unreadable: {path}") from error
    if not isinstance(value, dict):
        raise ValueError(f"checkpoint JSON must contain an object: {path}")
    return value


def _atomic_write_new(path: Path, data: bytes) -> None:
    if path.exists():
        raise FileExistsError(f"immutable B1G fold shard already exists: {path}")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.tmp-", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError as error:
            raise FileExistsError(f"immutable B1G fold shard already exists: {path}") from error
    finally:
        temporary.unlink(missing_ok=True)


def _diagnostics_record(diagnostics: SamplerDiagnostics | None) -> dict[str, object] | None:
    return None if diagnostics is None else asdict(diagnostics)


def _attempt_record(attempt: B1GFitAttempt) -> dict[str, object]:
    return {
        "attempt": attempt.attempt,
        "config": asdict(attempt.config),
        "status": attempt.status,
        "reason": attempt.reason,
        "diagnostics": _diagnostics_record(attempt.diagnostics),
    }


def _encode_number(value: float | None) -> float | str | None:
    if value is None or isfinite(value):
        return value
    if value == float("-inf"):
        return "-Infinity"
    raise ValueError("B1G candidate score contains a non-JSON numeric value")


def _candidate_record(candidate: B1GCandidateScore) -> dict[str, object]:
    return {
        "radius_km": candidate.radius_km,
        "basis_count": candidate.basis_count,
        "requested_count": candidate.requested_count,
        "scored_count": candidate.scored_count,
        "mean_log_score": _encode_number(candidate.mean_log_score),
        "completed_inner_fold_count": candidate.completed_inner_fold_count,
        "failed_inner_fold_count": candidate.failed_inner_fold_count,
        "failure_reasons": list(candidate.failure_reasons),
        "eligible": candidate.eligible,
        "inner_folds": [
            {
                **asdict(inner),
                "expected_test_ids": list(inner.expected_test_ids),
                "source_block_ids": list(inner.source_block_ids),
                "sampler_diagnostics": _diagnostics_record(inner.sampler_diagnostics),
                "fit_attempts": [_attempt_record(attempt) for attempt in inner.fit_attempts],
            }
            for inner in candidate.inner_folds
        ],
    }


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
    raise ValueError(f"B1G prediction {column} contains a non-JSON value")


def _limits(header: Mapping[str, object]) -> tuple[float, float]:
    try:
        fit_config = header["configuration"]["fit_config"]
        maximum = float(fit_config["max_rhat"])
        minimum = float(fit_config["min_ess"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("B1G checkpoint convergence limits are unavailable") from error
    return maximum, minimum


def _validate_result(
    plan: B1GBenchmarkPlan,
    ordinal: int,
    result: B1GFoldResult,
    *,
    max_rhat: float,
    min_ess: float,
) -> pd.DataFrame:
    if not isinstance(result, B1GFoldResult):
        raise TypeError("result must be a B1GFoldResult")
    split = plan.splits[ordinal]
    if result.status.split_id != split.split_id or result.status.expected_test_ids != split.test_ids:
        raise ValueError("B1G fold status contradicts its frozen split")
    frame = result.predictions
    if not isinstance(frame, pd.DataFrame) or tuple(frame.columns) != PREDICTION_COLUMNS:
        raise ValueError("B1G fold predictions have invalid columns")
    if result.status.status == "completed":
        if result.sampler_diagnostics is None:
            raise ValueError("completed B1G fold must retain sampler diagnostics")
        reason = convergence_failure(
            result.sampler_diagnostics, max_rhat=max_rhat, min_ess=min_ess
        )
        if reason is not None:
            raise ValueError(f"completed B1G fold contradicts convergence gates: {reason}")
        if frame["source_record_id"].duplicated().any() or set(frame["source_record_id"]) != set(
            split.test_ids
        ):
            raise ValueError("completed B1G fold predictions must exactly cover held-out IDs")
    elif not frame.empty:
        raise ValueError("failed or infeasible B1G fold must not contain predictions")

    selected = (result.status.selected_radius_km, result.status.selected_basis_count)
    if (selected[0] is None) != (selected[1] is None):
        raise ValueError("B1G fold must retain both selected basis fields or neither")
    outer_started = all(value is not None for value in selected)
    if outer_started:
        radius_km, basis_count = selected
        initial_seed = derive_b1g_seed(plan.seed, split.split_id, radius_km, basis_count, "fit")
        retry_seed = derive_b1g_seed(
            plan.seed,
            split.split_id,
            radius_km,
            basis_count,
            "fit",
            "retry",
        )
        terminal_seed = validate_b1g_fit_attempts(
            result.fit_attempts,
            fit_config=plan.config.fit_config,
            initial_seed=initial_seed,
            retry_seed=retry_seed,
        )
        _validate_attempt_diagnostics(
            result.fit_attempts,
            max_rhat=max_rhat,
            min_ess=min_ess,
        )
        if result.status.status == "completed":
            if set(frame["fit_seed"]) != {terminal_seed}:
                raise ValueError("completed B1G fold predictions contradict accepted fit attempt")
            accepted = next(
                attempt for attempt in result.fit_attempts if attempt.status == "accepted"
            )
            if accepted.diagnostics != result.sampler_diagnostics:
                raise ValueError("completed B1G fold diagnostics contradict accepted fit attempt")
    elif result.fit_attempts:
        raise ValueError("B1G fold retains fit attempts although no outer fit was selected")

    expected_candidates = set(plan.config.candidate_configs)
    actual_candidates = {
        (score.radius_km, score.basis_count, plan.config.query_chunk_size)
        for score in result.candidate_scores
    }
    expected_tuples = {
        (config.radius_km, config.basis_count, config.query_chunk_size)
        for config in expected_candidates
    }
    grid_was_started = result.status.status == "completed" or bool(result.candidate_scores)
    if grid_was_started and (
        actual_candidates != expected_tuples or len(result.candidate_scores) != len(expected_tuples)
    ):
        raise ValueError("B1G fold must retain every fixed-grid candidate exactly once")
    expected_inner_evidence: tuple[tuple[str, tuple[str, ...], str, str], ...] | None = None
    expected_test_ids: dict[str, tuple[str, ...]] = {}
    if grid_was_started:
        training_ids = set(split.train_ids)
        outer_assignments = plan.assignments[
            plan.assignments["source_record_id"].isin(training_ids)
        ].loc[:, ["source_record_id", "block_id"]]
        grouping = plan_three_inner_folds(outer_assignments)
        expected_inner_evidence = tuple(
            (
                group.inner_block_id,
                group.source_block_ids,
                grouping.algorithm,
                grouping.grouping_sha256,
            )
            for group in grouping.groups
        )
        expected_test_ids = {
            group.inner_block_id: tuple(
                sorted(
                    outer_assignments.loc[
                        outer_assignments["block_id"].isin(group.source_block_ids),
                        "source_record_id",
                    ]
                )
            )
            for group in grouping.groups
        }
    for score in result.candidate_scores:
        if len(score.inner_folds) != THREE_INNER_FOLD_COUNT:
            raise ValueError("B1G candidate must retain exactly three inner folds")
        inner_evidence = tuple(
            (
                inner.inner_block_id,
                inner.source_block_ids,
                inner.grouping_algorithm,
                inner.grouping_sha256,
            )
            for inner in score.inner_folds
        )
        if inner_evidence != expected_inner_evidence:
            raise ValueError("B1G candidate disagrees with the frozen inner-fold grouping")
        if {inner.inner_block_id for inner in score.inner_folds} != {
            f"inner-{index}" for index in range(THREE_INNER_FOLD_COUNT)
        }:
            raise ValueError("B1G candidate inner-fold labels are invalid")
        if {inner.grouping_algorithm for inner in score.inner_folds} != {
            THREE_INNER_FOLD_ALGORITHM
        }:
            raise ValueError("B1G candidate inner-fold algorithm is invalid")
        grouping_hashes = {inner.grouping_sha256 for inner in score.inner_folds}
        if len(grouping_hashes) != 1 or any(
            len(value) != 64 or any(character not in "0123456789abcdef" for character in value)
            for value in grouping_hashes
        ):
            raise ValueError("B1G candidate inner-fold grouping hash is invalid")
        source_blocks = [
            source_block_id
            for inner in score.inner_folds
            for source_block_id in inner.source_block_ids
        ]
        if (
            not all(isinstance(value, str) and value.strip() for value in source_blocks)
            or len(source_blocks) != len(set(source_blocks))
            or any(not inner.source_block_ids for inner in score.inner_folds)
        ):
            raise ValueError("B1G candidate source blocks are not partitioned exactly once")
        completed = sum(inner.status == "completed" for inner in score.inner_folds)
        failed = len(score.inner_folds) - completed
        if (completed, failed) != (
            score.completed_inner_fold_count,
            score.failed_inner_fold_count,
        ):
            raise ValueError("B1G candidate inner-fold counts contradict retained records")
        for inner in score.inner_folds:
            if inner.expected_test_ids != expected_test_ids[inner.inner_block_id]:
                raise ValueError("B1G inner fold contradicts its frozen source-block membership")
            initial_seed = derive_b1g_seed(
                derive_b1g_seed(plan.seed, split.split_id, "selection"),
                inner.split_id,
                score.radius_km,
                score.basis_count,
                "fit",
            )
            retry_seed = derive_b1g_seed(
                derive_b1g_seed(plan.seed, split.split_id, "selection"),
                inner.split_id,
                score.radius_km,
                score.basis_count,
                "fit",
                "retry",
            )
            terminal_seed = validate_b1g_fit_attempts(
                inner.fit_attempts,
                fit_config=plan.config.fit_config,
                initial_seed=initial_seed,
                retry_seed=retry_seed,
            )
            _validate_attempt_diagnostics(
                inner.fit_attempts,
                max_rhat=max_rhat,
                min_ess=min_ess,
            )
            if inner.fit_seed != terminal_seed:
                raise ValueError("B1G inner fold fit seed contradicts retained attempts")
            terminal = next(
                attempt for attempt in inner.fit_attempts if attempt.config.seed == terminal_seed
            )
            if inner.sampler_diagnostics != terminal.diagnostics:
                raise ValueError("B1G inner-fold diagnostics contradict retained attempts")
            if inner.status == "completed":
                if inner.sampler_diagnostics is None:
                    raise ValueError("completed B1G inner fold lacks sampler diagnostics")
                reason = convergence_failure(
                    inner.sampler_diagnostics,
                    max_rhat=max_rhat,
                    min_ess=min_ess,
                )
                if reason is not None:
                    prefix = "eligible candidate" if score.eligible else "completed inner fold"
                    raise ValueError(f"{prefix} contradicts convergence gates: {reason}")
        if score.eligible and (
            failed
            or score.scored_count != score.requested_count
            or score.mean_log_score is None
        ):
            raise ValueError("eligible B1G candidate contradicts its retained evidence")
    eligible = {(score.radius_km, score.basis_count) for score in result.candidate_scores if score.eligible}
    if result.status.status == "completed" and selected not in eligible:
        raise ValueError("completed B1G fold selected an ineligible candidate")
    return frame


def _validate_attempt_diagnostics(
    attempts: tuple[B1GFitAttempt, ...],
    *,
    max_rhat: float,
    min_ess: float,
) -> None:
    for attempt in attempts:
        if attempt.diagnostics is None:
            continue
        reason = convergence_failure(
            attempt.diagnostics,
            max_rhat=max_rhat,
            min_ess=min_ess,
        )
        if (attempt.status == "accepted") != (reason is None):
            raise ValueError("B1G fit attempt status contradicts convergence gates")


def _document(
    plan: B1GBenchmarkPlan,
    ordinal: int,
    result: B1GFoldResult,
    runtime: B1GFoldRuntime,
    *,
    max_rhat: float,
    min_ess: float,
) -> dict[str, object]:
    frame = _validate_result(
        plan,
        ordinal,
        result,
        max_rhat=max_rhat,
        min_ess=min_ess,
    )
    split = plan.splits[ordinal]
    body = {
        "schema_version": SHARD_SCHEMA_VERSION,
        "ordinal": ordinal,
        "split_id": split.split_id,
        "block_id": split.block_id,
        "expected_test_ids": list(split.test_ids),
        "status": result.status.status,
        "selected_radius_km": result.status.selected_radius_km,
        "selected_basis_count": result.status.selected_basis_count,
        "failure_reason": result.status.failure_reason,
        "sampler_diagnostics": _diagnostics_record(result.sampler_diagnostics),
        "fit_attempts": [_attempt_record(attempt) for attempt in result.fit_attempts],
        "candidate_scores": [_candidate_record(score) for score in result.candidate_scores],
        "prediction_columns": list(PREDICTION_COLUMNS),
        "prediction_rows": [
            [_encode_scalar(value, column) for value, column in zip(row, PREDICTION_COLUMNS, strict=True)]
            for row in frame.itertuples(index=False, name=None)
        ],
        "runtime": asdict(runtime),
    }
    return {**body, "artifact_sha256": _canonical_hash(body)}


def _checkpoint_identity(
    path: Path, expected_header: Mapping[str, object], plan: B1GBenchmarkPlan
) -> Path:
    root = Path(path)
    folds = root / FOLD_DIRECTORY
    if not root.is_dir():
        raise ValueError(f"B1G checkpoint directory is incomplete: {root}")
    visible_names = {entry.name for entry in root.iterdir() if not entry.name.startswith(".")}
    if visible_names != {HEADER_FILENAME, FOLD_DIRECTORY}:
        raise ValueError("B1G checkpoint contains unknown or missing artifacts")
    if not folds.is_dir() or not (root / HEADER_FILENAME).is_file():
        raise ValueError(f"B1G checkpoint directory is incomplete: {root}")
    if _read_json(root / HEADER_FILENAME) != dict(expected_header):
        raise ValueError("B1G checkpoint header mismatch; campaign identity changed")
    validate_checkpoint_splits(expected_header, plan.splits)
    return folds


def write_b1g_fold_shard(
    path: Path,
    expected_header: Mapping[str, object],
    plan: B1GBenchmarkPlan,
    ordinal: int,
    result: B1GFoldResult,
    runtime: B1GFoldRuntime,
) -> None:
    """Atomically write one immutable outer-fold shard at its frozen ordinal."""
    if isinstance(ordinal, bool) or not isinstance(ordinal, Integral) or not 0 <= ordinal < len(plan.splits):
        raise ValueError("B1G fold ordinal is outside the frozen split ledger")
    if not isinstance(runtime, B1GFoldRuntime):
        raise TypeError("runtime must be a B1GFoldRuntime")
    folds = _checkpoint_identity(path, expected_header, plan)
    max_rhat, min_ess = _limits(expected_header)
    document = _document(
        plan,
        int(ordinal),
        result,
        runtime,
        max_rhat=max_rhat,
        min_ess=min_ess,
    )
    _atomic_write_new(folds / f"{ordinal:04d}.json", _json_bytes(document))


def _decode_diagnostics(value: object) -> SamplerDiagnostics | None:
    if value is None:
        return None
    try:
        return SamplerDiagnostics(**value)
    except (TypeError, ValueError) as error:
        raise ValueError("B1G shard contains invalid sampler diagnostics") from error


def _decode_attempt(value: object) -> B1GFitAttempt:
    if not isinstance(value, dict) or set(value) != {
        "attempt",
        "config",
        "status",
        "reason",
        "diagnostics",
    }:
        raise ValueError("B1G fit attempt record fields are invalid")
    config = value["config"]
    if not isinstance(config, dict):
        raise ValueError("B1G fit attempt config must be an object")
    config = dict(config)
    if isinstance(config.get("hsgp_m"), list):
        config["hsgp_m"] = tuple(config["hsgp_m"])
    try:
        return B1GFitAttempt(
            attempt=value["attempt"],
            config=FitConfig(**config),
            status=value["status"],
            reason=value["reason"],
            diagnostics=_decode_diagnostics(value["diagnostics"]),
        )
    except (TypeError, ValueError) as error:
        raise ValueError("B1G fit attempt record is invalid") from error


def _decode_candidate(value: object) -> B1GCandidateScore:
    if not isinstance(value, dict):
        raise ValueError("B1G candidate record must be an object")
    fields = dict(value)
    raw_inner = fields.pop("inner_folds", None)
    if not isinstance(raw_inner, list):
        raise ValueError("B1G candidate inner_folds must be a list")
    inner_folds = []
    for record in raw_inner:
        if not isinstance(record, dict):
            raise ValueError("B1G inner-fold record must be an object")
        item = dict(record)
        item["expected_test_ids"] = tuple(item["expected_test_ids"])
        item["source_block_ids"] = tuple(item["source_block_ids"])
        item["sampler_diagnostics"] = _decode_diagnostics(item["sampler_diagnostics"])
        raw_attempts = item["fit_attempts"]
        if not isinstance(raw_attempts, list):
            raise ValueError("B1G inner-fold fit_attempts must be a list")
        item["fit_attempts"] = tuple(_decode_attempt(attempt) for attempt in raw_attempts)
        inner_folds.append(B1GInnerFoldRecord(**item))
    fields["failure_reasons"] = tuple(fields["failure_reasons"])
    fields["inner_folds"] = tuple(inner_folds)
    if fields["mean_log_score"] == "-Infinity":
        fields["mean_log_score"] = float("-inf")
    try:
        return B1GCandidateScore(**fields)
    except (TypeError, ValueError) as error:
        raise ValueError("B1G candidate record is invalid") from error


def _decode_shard(
    path: Path,
    plan: B1GBenchmarkPlan,
    ordinal: int,
    *,
    max_rhat: float,
    min_ess: float,
) -> B1GFoldShard:
    document = _read_json(path)
    if set(document) != set(_FIELDS):
        raise ValueError(f"B1G shard fields are invalid: {path.name}")
    body = {field: document[field] for field in _BODY_FIELDS}
    if document["artifact_sha256"] != _canonical_hash(body):
        raise ValueError(f"B1G shard integrity check failed: {path.name}")
    split = plan.splits[ordinal]
    if (
        document["schema_version"] != SHARD_SCHEMA_VERSION
        or document["ordinal"] != ordinal
        or document["split_id"] != split.split_id
        or document["block_id"] != split.block_id
        or document["expected_test_ids"] != list(split.test_ids)
        or document["prediction_columns"] != list(PREDICTION_COLUMNS)
    ):
        raise ValueError(f"B1G shard identity mismatch: {path.name}")
    rows = document["prediction_rows"]
    if not isinstance(rows, list) or any(
        not isinstance(row, list) or len(row) != len(PREDICTION_COLUMNS) for row in rows
    ):
        raise ValueError(f"B1G shard prediction rows are invalid: {path.name}")
    log_index = PREDICTION_COLUMNS.index("log_score")
    decoded_rows = []
    for row in rows:
        values = list(row)
        if values[log_index] == "-Infinity":
            values[log_index] = float("-inf")
        decoded_rows.append(values)
    result = B1GFoldResult(
        status=B1GFoldStatus(
            split_id=split.split_id,
            status=document["status"],
            expected_test_ids=split.test_ids,
            selected_radius_km=document["selected_radius_km"],
            selected_basis_count=document["selected_basis_count"],
            failure_reason=document["failure_reason"],
        ),
        predictions=pd.DataFrame(decoded_rows, columns=PREDICTION_COLUMNS),
        candidate_scores=tuple(_decode_candidate(value) for value in document["candidate_scores"]),
        sampler_diagnostics=_decode_diagnostics(document["sampler_diagnostics"]),
        fit_attempts=tuple(_decode_attempt(value) for value in document["fit_attempts"]),
    )
    runtime = B1GFoldRuntime(**document["runtime"])
    _validate_result(plan, ordinal, result, max_rhat=max_rhat, min_ess=min_ess)
    return B1GFoldShard(ordinal, result, runtime)


def load_b1g_fold_shards(
    path: Path,
    expected_header: Mapping[str, object],
    plan: B1GBenchmarkPlan,
) -> tuple[B1GFoldShard, ...]:
    """Load any integrity-checked subset of independently written outer-fold shards."""
    folds = _checkpoint_identity(path, expected_header, plan)
    expected_names = {f"{ordinal:04d}.json" for ordinal in range(len(plan.splits))}
    actual_names = {entry.name for entry in folds.iterdir() if not entry.name.startswith(".")}
    if not actual_names <= expected_names:
        raise ValueError("B1G checkpoint contains unknown fold shards")
    max_rhat, min_ess = _limits(expected_header)
    ordinals = [ordinal for ordinal in range(len(plan.splits)) if f"{ordinal:04d}.json" in actual_names]
    return tuple(
        _decode_shard(
            folds / f"{ordinal:04d}.json",
            plan,
            ordinal,
            max_rhat=max_rhat,
            min_ess=min_ess,
        )
        for ordinal in ordinals
    )


def finalize_b1g_checkpoint(
    path: Path,
    expected_header: Mapping[str, object],
    plan: B1GBenchmarkPlan,
) -> B1GBenchmarkResult:
    """Finalize only a complete set of valid parallel outer-fold shards."""
    shards = load_b1g_fold_shards(path, expected_header, plan)
    return finalize_b1g_benchmark(plan, tuple(shard.result for shard in shards))
