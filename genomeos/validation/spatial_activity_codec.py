"""Canonical worker-result transport for the activity preflight (design §§5, 8; #384).

The codec retains task identity, terminal status, sampler evidence, held-out diagnostics, and
synthetic-truth assessment. Live PyMC state is deliberately excluded. This module performs no
file or network I/O and makes no promotion decision.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import fields
from math import isfinite
from numbers import Integral, Real

import numpy as np
import pandas as pd

from genomeos.surfaces.convergence import SamplerDiagnostics
from genomeos.surfaces.spatial_activity_model import SpatialActivityModelConfig
from genomeos.validation.benchmark import (
    BenchmarkFoldStatus,
    validate_predictive_diagnostics,
)
from genomeos.validation.spatial_activity_assessment import (
    ActivityNullFalseSupport,
    ActivityPredictionAssessment,
    ActivityStratumMetrics,
    ActivityTruthRecovery,
    validate_activity_prediction_assessment,
)
from genomeos.validation.spatial_activity_runner import (
    SpatialActivityFitAttempt,
    SpatialActivityFoldResult,
)
from genomeos.validation.spatial_activity_tasks import (
    SpatialActivityTask,
    SpatialActivityTaskResult,
)

FORMAT = "spatial_activity_task_result"
VERSION = 1
MAX_ARTIFACT_BYTES = 4_000_000


class SpatialActivityCodecError(ValueError):
    """The worker result cannot be represented or reconstructed faithfully."""


def _fail(message: str) -> None:
    raise SpatialActivityCodecError(message)


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
    except (TypeError, ValueError) as error:
        raise SpatialActivityCodecError("result contains a non-JSON value") from error


def _mapping(value: object, names: Sequence[str], label: str) -> Mapping[str, object]:
    if type(value) is not dict or set(value) != set(names):
        _fail(f"{label} has missing or extra fields")
    return value


def _string(value: object, label: str, *, allow_empty: bool = False) -> str:
    if type(value) is not str or (not allow_empty and not value.strip()):
        _fail(f"{label} must be a literal nonempty string")
    return value


def _integer(value: object, label: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        _fail(f"{label} must be an integer of at least {minimum}")
    return value


def _number(value: object, label: str, *, negative_infinity: bool = False) -> float:
    if value == "-Infinity" and negative_infinity:
        return float("-inf")
    if type(value) not in (int, float):
        _fail(f"{label} must be a finite JSON number")
    result = float(value)
    if not isfinite(result):
        _fail(f"{label} must be a finite JSON number")
    return result


def _optional_number(
    value: object,
    label: str,
    *,
    negative_infinity: bool = False,
) -> float | None:
    return None if value is None else _number(value, label, negative_infinity=negative_infinity)


def _json_number(value: object, label: str, *, negative_infinity: bool = False) -> float | str:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        _fail(f"{label} must be numeric")
    result = float(value)
    if isfinite(result):
        return result
    if negative_infinity and result == float("-inf"):
        return "-Infinity"
    _fail(f"{label} contains an unsupported nonfinite number")


def _record(value: object) -> dict[str, object]:
    return {field.name: getattr(value, field.name) for field in fields(value)}


def _task_node(task: SpatialActivityTask) -> dict[str, object]:
    if not isinstance(task, SpatialActivityTask):
        _fail("task must be SpatialActivityTask")
    return _record(task)


def _task_from_node(value: object) -> SpatialActivityTask:
    node = _mapping(
        value,
        ("task_id", "scenario_id", "mode", "split_role", "outer_split_id", "split_id"),
        "task",
    )
    try:
        return SpatialActivityTask(
            task_id=_string(node["task_id"], "task.task_id"),
            scenario_id=_string(node["scenario_id"], "task.scenario_id"),
            mode=_string(node["mode"], "task.mode"),  # type: ignore[arg-type]
            split_role=_string(node["split_role"], "task.split_role"),
            outer_split_id=_string(node["outer_split_id"], "task.outer_split_id"),
            split_id=_string(node["split_id"], "task.split_id"),
        )
    except (TypeError, ValueError) as error:
        raise SpatialActivityCodecError("task failed public validation") from error


def _sampler_node(value: SamplerDiagnostics | None) -> dict[str, object] | None:
    if value is None:
        return None
    if not isinstance(value, SamplerDiagnostics):
        _fail("sampler diagnostics have the wrong type")
    return _record(value)


def _sampler_from_node(value: object) -> SamplerDiagnostics | None:
    if value is None:
        return None
    names = tuple(field.name for field in fields(SamplerDiagnostics))
    node = _mapping(value, names, "sampler_diagnostics")
    try:
        return SamplerDiagnostics(
            max_rhat=_number(node["max_rhat"], "max_rhat"),
            max_rhat_parameter=_string(node["max_rhat_parameter"], "max_rhat_parameter"),
            min_bulk_ess=_number(node["min_bulk_ess"], "min_bulk_ess"),
            min_bulk_ess_parameter=_string(
                node["min_bulk_ess_parameter"], "min_bulk_ess_parameter"
            ),
            min_tail_ess=_number(node["min_tail_ess"], "min_tail_ess"),
            min_tail_ess_parameter=_string(
                node["min_tail_ess_parameter"], "min_tail_ess_parameter"
            ),
            divergence_count=_integer(node["divergence_count"], "divergence_count"),
        )
    except (TypeError, ValueError) as error:
        raise SpatialActivityCodecError("sampler diagnostics failed public validation") from error


def _attempt_node(value: SpatialActivityFitAttempt) -> dict[str, object]:
    if not isinstance(value, SpatialActivityFitAttempt):
        _fail("attempts must contain SpatialActivityFitAttempt records")
    return {
        "attempt": value.attempt,
        "diagnostics": _sampler_node(value.diagnostics),
        "draws": value.draws,
        "failure_reason": value.failure_reason,
        "seed": value.seed,
        "status": value.status,
        "tune": value.tune,
    }


def _attempt_from_node(value: object) -> SpatialActivityFitAttempt:
    names = ("attempt", "diagnostics", "draws", "failure_reason", "seed", "status", "tune")
    node = _mapping(value, names, "attempt")
    reason = node["failure_reason"]
    if reason is not None:
        reason = _string(reason, "failure_reason")
    try:
        return SpatialActivityFitAttempt(
            attempt=_integer(node["attempt"], "attempt", minimum=1),
            draws=_integer(node["draws"], "draws", minimum=1),
            tune=_integer(node["tune"], "tune", minimum=1),
            seed=_integer(node["seed"], "seed"),
            status=_string(node["status"], "status"),  # type: ignore[arg-type]
            failure_reason=reason,
            diagnostics=_sampler_from_node(node["diagnostics"]),
        )
    except (TypeError, ValueError) as error:
        raise SpatialActivityCodecError("attempt failed public validation") from error


def _model_node(value: SpatialActivityModelConfig) -> dict[str, object]:
    if not isinstance(value, SpatialActivityModelConfig):
        _fail("model_config must be SpatialActivityModelConfig")
    node = _record(value)
    node["hsgp_m"] = list(value.hsgp_m)
    return node


def _model_from_node(value: object) -> SpatialActivityModelConfig:
    names = tuple(field.name for field in fields(SpatialActivityModelConfig))
    node = _mapping(value, names, "model_config")
    basis = node["hsgp_m"]
    if type(basis) is not list or len(basis) != 3:
        _fail("model_config.hsgp_m must be a three-element list")
    try:
        return SpatialActivityModelConfig(
            hsgp_m=tuple(_integer(item, "hsgp_m", minimum=1) for item in basis),  # type: ignore[arg-type]
            **{
                name: _number(node[name], f"model_config.{name}")
                for name in names
                if name != "hsgp_m"
            },
        )
    except (TypeError, ValueError) as error:
        raise SpatialActivityCodecError("model_config failed public validation") from error


def _stratum_node(value: ActivityStratumMetrics) -> dict[str, object]:
    if not isinstance(value, ActivityStratumMetrics):
        _fail("assessment strata have the wrong type")
    return {
        "coverage_50": value.coverage_50,
        "coverage_80": value.coverage_80,
        "coverage_95": value.coverage_95,
        "mae": value.mae,
        "mean_log_score": (
            None
            if value.mean_log_score is None
            else _json_number(value.mean_log_score, "mean_log_score", negative_infinity=True)
        ),
        "n_observations": value.n_observations,
    }


def _stratum_from_node(value: object) -> ActivityStratumMetrics:
    names = ("coverage_50", "coverage_80", "coverage_95", "mae", "mean_log_score", "n_observations")
    node = _mapping(value, names, "stratum")
    return ActivityStratumMetrics(
        n_observations=_integer(node["n_observations"], "n_observations"),
        mean_log_score=_optional_number(
            node["mean_log_score"], "mean_log_score", negative_infinity=True
        ),
        mae=_optional_number(node["mae"], "mae"),
        coverage_50=_optional_number(node["coverage_50"], "coverage_50"),
        coverage_80=_optional_number(node["coverage_80"], "coverage_80"),
        coverage_95=_optional_number(node["coverage_95"], "coverage_95"),
    )


def _diagnostic_node(value: pd.DataFrame) -> dict[str, object]:
    try:
        core = validate_predictive_diagnostics(value)
    except (TypeError, ValueError) as error:
        raise SpatialActivityCodecError("assessment diagnostics failed validation") from error
    missing = sorted({"observed_ac", "observed_an"} - set(value.columns))
    if missing:
        _fail(f"assessment diagnostics are missing observed count fields: {missing}")
    frame = pd.concat(
        [
            value.loc[:, ["observed_ac", "observed_an"]].reset_index(drop=True),
            core.reset_index(drop=True),
        ],
        axis=1,
    )
    rows: list[list[object]] = []
    for raw in frame.itertuples(index=False, name=None):
        row = []
        for column, item in zip(frame.columns, raw, strict=True):
            if column in ("observed_ac", "observed_an"):
                if isinstance(item, (bool, np.bool_)) or not isinstance(item, Integral):
                    _fail(f"diagnostic {column} must be an integer")
                row.append(int(item))
            elif column.startswith("coverage_"):
                if not isinstance(item, (bool, np.bool_)):
                    _fail(f"diagnostic {column} must be Boolean")
                row.append(bool(item))
            else:
                row.append(_json_number(item, column, negative_infinity=column == "log_score"))
        rows.append(row)
    return {"columns": list(frame.columns), "rows": rows}


def _diagnostic_from_node(value: object) -> pd.DataFrame:
    node = _mapping(value, ("columns", "rows"), "diagnostics")
    columns = node["columns"]
    rows = node["rows"]
    if type(columns) is not list or any(type(item) is not str for item in columns):
        _fail("diagnostic columns must be literal strings")
    if type(rows) is not list or any(type(row) is not list or len(row) != len(columns) for row in rows):
        _fail("diagnostic rows must align with columns")
    decoded: list[list[object]] = []
    for row in rows:
        decoded.append(
            [
                (
                    item
                    if column.startswith("coverage_")
                    else (
                        _integer(item, column)
                        if column in ("observed_ac", "observed_an")
                        else _number(item, column, negative_infinity=column == "log_score")
                    )
                )
                for column, item in zip(columns, row, strict=True)
            ]
        )
    try:
        frame = pd.DataFrame(decoded, columns=columns)
        core = validate_predictive_diagnostics(frame)
        if tuple(columns[:2]) != ("observed_ac", "observed_an"):
            _fail("assessment diagnostics must begin with observed count fields")
        return pd.concat(
            [frame.loc[:, ["observed_ac", "observed_an"]], core],
            axis=1,
        )
    except (TypeError, ValueError) as error:
        raise SpatialActivityCodecError("assessment diagnostics failed validation") from error


def _assessment_node(value: ActivityPredictionAssessment | None) -> dict[str, object] | None:
    if value is None:
        return None
    if not isinstance(value, ActivityPredictionAssessment):
        _fail("assessment has the wrong type")
    try:
        diagnostics = validate_activity_prediction_assessment(value)
    except (TypeError, ValueError) as error:
        raise SpatialActivityCodecError(
            f"assessment retained evidence is invalid: {error}"
        ) from error
    recovery = _record(value.recovery)
    false_support = None if value.null_false_support is None else _record(value.null_false_support)
    return {
        "all_rows": _stratum_node(value.all_rows),
        "diagnostics": _diagnostic_node(diagnostics),
        "null_false_support": false_support,
        "positive_rows": _stratum_node(value.positive_rows),
        "recovery": recovery,
        "zero_rows": _stratum_node(value.zero_rows),
    }


def _assessment_from_node(value: object) -> ActivityPredictionAssessment | None:
    if value is None:
        return None
    node = _mapping(
        value,
        ("all_rows", "diagnostics", "null_false_support", "positive_rows", "recovery", "zero_rows"),
        "assessment",
    )
    recovery_node = _mapping(
        node["recovery"],
        (
            "marginal_mean_mae",
            "conditional_mean_mae",
            "activity_probability_mae",
            "mean_absolute_component_correlation",
            "correlated_observation_count",
        ),
        "recovery",
    )
    recovery = ActivityTruthRecovery(
        marginal_mean_mae=_number(recovery_node["marginal_mean_mae"], "marginal_mean_mae"),
        conditional_mean_mae=_number(
            recovery_node["conditional_mean_mae"], "conditional_mean_mae"
        ),
        activity_probability_mae=_number(
            recovery_node["activity_probability_mae"], "activity_probability_mae"
        ),
        mean_absolute_component_correlation=_optional_number(
            recovery_node["mean_absolute_component_correlation"],
            "mean_absolute_component_correlation",
        ),
        correlated_observation_count=_integer(
            recovery_node["correlated_observation_count"], "correlated_observation_count"
        ),
    )
    false_support = None
    if node["null_false_support"] is not None:
        support_node = _mapping(
            node["null_false_support"],
            ("mean_inactive_probability", "fraction_draws_below_threshold", "activity_threshold"),
            "null_false_support",
        )
        false_support = ActivityNullFalseSupport(
            mean_inactive_probability=_number(
                support_node["mean_inactive_probability"], "mean_inactive_probability"
            ),
            fraction_draws_below_threshold=_number(
                support_node["fraction_draws_below_threshold"],
                "fraction_draws_below_threshold",
            ),
            activity_threshold=_number(support_node["activity_threshold"], "activity_threshold"),
        )
    assessment = ActivityPredictionAssessment(
        diagnostics=_diagnostic_from_node(node["diagnostics"]),
        all_rows=_stratum_from_node(node["all_rows"]),
        zero_rows=_stratum_from_node(node["zero_rows"]),
        positive_rows=_stratum_from_node(node["positive_rows"]),
        recovery=recovery,
        null_false_support=false_support,
    )
    try:
        validate_activity_prediction_assessment(assessment)
    except (TypeError, ValueError) as error:
        raise SpatialActivityCodecError(
            f"assessment retained evidence is invalid: {error}"
        ) from error
    return assessment


def _status_node(value: BenchmarkFoldStatus) -> dict[str, object]:
    if not isinstance(value, BenchmarkFoldStatus):
        _fail("status must be BenchmarkFoldStatus")
    node = _record(value)
    node["expected_test_ids"] = list(value.expected_test_ids)
    return node


def _status_from_node(value: object) -> BenchmarkFoldStatus:
    node = _mapping(value, ("split_id", "status", "expected_test_ids", "failure_reason"), "status")
    expected = node["expected_test_ids"]
    if type(expected) is not list:
        _fail("expected_test_ids must be a list")
    reason = node["failure_reason"]
    if reason is not None:
        reason = _string(reason, "failure_reason")
    try:
        return BenchmarkFoldStatus(
            split_id=_string(node["split_id"], "split_id"),
            status=_string(node["status"], "status"),  # type: ignore[arg-type]
            expected_test_ids=tuple(_string(item, "expected_test_ids") for item in expected),
            failure_reason=reason,
        )
    except (TypeError, ValueError) as error:
        raise SpatialActivityCodecError("status failed public validation") from error


def _payload(value: SpatialActivityTaskResult) -> dict[str, object]:
    if not isinstance(value, SpatialActivityTaskResult):
        _fail("value must be SpatialActivityTaskResult")
    result = value.result
    completed = result.status.status == "completed"
    if completed != (result.assessment is not None):
        _fail("completed results require an assessment and terminal refusals forbid one")
    if completed and (
        not result.attempts
        or result.attempts[-1].status != "completed"
        or len(result.attempts) > 2
        or len(result.attempts) == 2
        and result.attempts[0].status != "nonconverged"
    ):
        _fail("completed results require one terminal completed attempt after at most one retry")
    if completed and len(result.assessment.diagnostics) != len(result.status.expected_test_ids):
        _fail("completed assessment rows must match expected held-out identities")
    return {
        "result": {
            "assessment": _assessment_node(result.assessment),
            "attempts": [_attempt_node(item) for item in result.attempts],
            "fit_seed": result.fit_seed,
            "mode": result.mode,
            "model_config": _model_node(result.model_config),
            "predictive_seed": result.predictive_seed,
            "scenario_id": result.scenario_id,
            "split_role": result.split_role,
            "status": _status_node(result.status),
        },
        "task": _task_node(value.task),
    }


def _from_payload(value: object) -> SpatialActivityTaskResult:
    node = _mapping(value, ("result", "task"), "payload")
    task = _task_from_node(node["task"])
    result_node = _mapping(
        node["result"],
        (
            "assessment",
            "attempts",
            "fit_seed",
            "mode",
            "model_config",
            "predictive_seed",
            "scenario_id",
            "split_role",
            "status",
        ),
        "result",
    )
    attempts = result_node["attempts"]
    if type(attempts) is not list:
        _fail("attempts must be a list")
    result = SpatialActivityFoldResult(
        scenario_id=_string(result_node["scenario_id"], "scenario_id"),
        mode=_string(result_node["mode"], "mode"),  # type: ignore[arg-type]
        split_role=_string(result_node["split_role"], "split_role"),  # type: ignore[arg-type]
        status=_status_from_node(result_node["status"]),
        fit_seed=_integer(result_node["fit_seed"], "fit_seed"),
        predictive_seed=_integer(result_node["predictive_seed"], "predictive_seed"),
        model_config=_model_from_node(result_node["model_config"]),
        attempts=tuple(_attempt_from_node(item) for item in attempts),
        assessment=_assessment_from_node(result_node["assessment"]),
        fitted=None,
    )
    try:
        return SpatialActivityTaskResult(task=task, result=result)
    except (TypeError, ValueError) as error:
        raise SpatialActivityCodecError("result identity failed public validation") from error


def encode_spatial_activity_task_result(value: SpatialActivityTaskResult) -> bytes:
    """Return canonical authenticated JSON bytes without live sampler state."""
    payload = _payload(value)
    payload_bytes = _canonical(payload)
    document = {
        "format": FORMAT,
        "payload": payload,
        "payload_sha256": hashlib.sha256(payload_bytes).hexdigest(),
        "version": VERSION,
    }
    encoded = _canonical(document) + b"\n"
    if len(encoded) > MAX_ARTIFACT_BYTES:
        _fail(f"encoded result exceeds {MAX_ARTIFACT_BYTES} bytes")
    reconstructed = _from_payload(payload)
    if _payload(reconstructed) != payload:
        _fail("public reconstruction changed retained evidence")
    return encoded


def decode_spatial_activity_task_result(data: bytes) -> SpatialActivityTaskResult:
    """Validate and reconstruct one canonical authenticated worker result."""
    if type(data) is not bytes or not data or len(data) > MAX_ARTIFACT_BYTES:
        _fail("artifact bytes are empty, oversized, or have the wrong type")
    try:
        document = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SpatialActivityCodecError("artifact is not valid JSON") from error
    envelope = _mapping(
        document,
        ("format", "payload", "payload_sha256", "version"),
        "envelope",
    )
    if envelope["format"] != FORMAT or envelope["version"] != VERSION:
        _fail("artifact format or version is unsupported")
    digest = _string(envelope["payload_sha256"], "payload_sha256")
    if len(digest) != 64 or digest != hashlib.sha256(_canonical(envelope["payload"])).hexdigest():
        _fail("payload digest does not match retained evidence")
    result = _from_payload(envelope["payload"])
    if encode_spatial_activity_task_result(result) != data:
        _fail("artifact is not in canonical form")
    return result
