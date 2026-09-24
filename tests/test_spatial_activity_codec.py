"""Canonical spatial-activity worker-result codec tests (#384)."""

from __future__ import annotations

import json
from dataclasses import replace

import pandas as pd
import pytest

from genomeos.surfaces.convergence import SamplerDiagnostics
from genomeos.surfaces.spatial_activity_model import SpatialActivityModelConfig
from genomeos.validation.benchmark import BenchmarkFoldStatus
from genomeos.validation.spatial_activity_assessment import (
    ActivityNullFalseSupport,
    ActivityPredictionAssessment,
    ActivityStratumMetrics,
    ActivityTruthRecovery,
)
from genomeos.validation.spatial_activity_runner import (
    SpatialActivityFitAttempt,
    SpatialActivityFoldResult,
)
from genomeos.validation.spatial_activity_tasks import (
    SpatialActivityTask,
    SpatialActivityTaskResult,
)


def _diagnostics() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "observed_ac": [1, 0],
            "observed_an": [20, 20],
            "log_score": [-1.25, float("-inf")],
            "absolute_error": [0.15, 0.15],
            "squared_error": [0.0225, 0.0225],
            "coverage_50": [True, False],
            "interval_width_50": [0.20, 0.25],
            "coverage_80": [True, True],
            "interval_width_80": [0.35, 0.40],
            "coverage_95": [True, True],
            "interval_width_95": [0.50, 0.55],
            "randomized_pit": [0.30, 0.70],
        }
    )


def _stratum(
    count: int,
    score: float | None,
    *,
    coverage_50: float = 0.50,
) -> ActivityStratumMetrics:
    return ActivityStratumMetrics(
        n_observations=count,
        mean_log_score=score,
        mae=None if count == 0 else 0.15,
        coverage_50=None if count == 0 else coverage_50,
        coverage_80=None if count == 0 else 1.00,
        coverage_95=None if count == 0 else 1.00,
    )


def _record(*, fitted: object | None = None) -> SpatialActivityTaskResult:
    task = SpatialActivityTask.create(
        scenario_id="null-denom-1-cohort-0-seed-42",
        mode="spatial_activity",
        split_role="outer",
        outer_split_id="outer-africa",
        split_id="outer-africa",
    )
    sampler_diagnostics = SamplerDiagnostics(
        max_rhat=1.01,
        max_rhat_parameter="activity_field",
        min_bulk_ess=350.0,
        min_bulk_ess_parameter="concentration",
        min_tail_ess=280.0,
        min_tail_ess_parameter="conditional_field",
        divergence_count=0,
    )
    model_config = SpatialActivityModelConfig(
        hsgp_m=(2, 3, 4),
        hsgp_c=1.5,
        lengthscale_mu=-2.0,
        lengthscale_sigma=0.4,
        conditional_intercept_mu=-3.5,
        conditional_intercept_sigma=1.5,
        conditional_amplitude_sigma=1.0,
        activity_intercept_mu=2.5,
        activity_intercept_sigma=1.0,
        activity_amplitude_sigma=1.0,
        concentration_sigma=100.0,
        cohort_sd_sigma=0.5,
    )
    assessment = ActivityPredictionAssessment(
        diagnostics=_diagnostics(),
        all_rows=_stratum(2, float("-inf")),
        zero_rows=_stratum(1, float("-inf"), coverage_50=0.0),
        positive_rows=_stratum(1, -1.25, coverage_50=1.0),
        recovery=ActivityTruthRecovery(
            marginal_mean_mae=0.12,
            conditional_mean_mae=0.08,
            activity_probability_mae=0.07,
            mean_absolute_component_correlation=0.65,
            correlated_observation_count=2,
        ),
        null_false_support=ActivityNullFalseSupport(
            mean_inactive_probability=0.03,
            fraction_draws_below_threshold=0.04,
            activity_threshold=0.9,
        ),
    )
    result = SpatialActivityFoldResult(
        scenario_id=task.scenario_id,
        mode=task.mode,
        split_role=task.split_role,
        status=BenchmarkFoldStatus(
            split_id=task.split_id,
            status="completed",
            expected_test_ids=("record-1", "record-2"),
            failure_reason=None,
        ),
        fit_seed=11,
        predictive_seed=12,
        model_config=model_config,
        attempts=(
            SpatialActivityFitAttempt(
                attempt=1,
                draws=500,
                tune=1000,
                seed=11,
                status="completed",
                failure_reason=None,
                diagnostics=sampler_diagnostics,
            ),
        ),
        assessment=assessment,
        fitted=fitted,
    )
    return SpatialActivityTaskResult(task=task, result=result)


def test_codec_is_deterministic_lossless_and_drops_live_fit() -> None:
    from genomeos.validation.spatial_activity_codec import (
        decode_spatial_activity_task_result,
        encode_spatial_activity_task_result,
    )

    record = _record(fitted=object())
    first = encode_spatial_activity_task_result(record)
    second = encode_spatial_activity_task_result(record)
    decoded = decode_spatial_activity_task_result(first)

    assert first == second
    assert first.endswith(b"\n")
    assert decoded.task == record.task
    assert decoded.result.status == record.result.status
    assert decoded.result.model_config == record.result.model_config
    assert decoded.result.attempts == record.result.attempts
    assert decoded.result.assessment.all_rows == record.result.assessment.all_rows
    assert decoded.result.assessment.recovery == record.result.assessment.recovery
    assert decoded.result.assessment.null_false_support == (
        record.result.assessment.null_false_support
    )
    pd.testing.assert_frame_equal(
        decoded.result.assessment.diagnostics,
        record.result.assessment.diagnostics,
    )
    assert decoded.result.fitted is None


def test_codec_retains_terminal_failure_without_fabricating_assessment() -> None:
    from genomeos.validation.spatial_activity_codec import (
        decode_spatial_activity_task_result,
        encode_spatial_activity_task_result,
    )

    record = _record()
    failed_attempt = replace(
        record.result.attempts[0],
        status="nonconverged",
        failure_reason="r_hat exceeded gate",
    )
    failed_result = replace(
        record.result,
        status=BenchmarkFoldStatus(
            split_id=record.task.split_id,
            status="failed",
            expected_test_ids=record.result.status.expected_test_ids,
            failure_reason="sampler did not converge after retry",
        ),
        attempts=(failed_attempt,),
        assessment=None,
    )
    failed = SpatialActivityTaskResult(task=record.task, result=failed_result)

    decoded = decode_spatial_activity_task_result(
        encode_spatial_activity_task_result(failed)
    )

    assert decoded.result.status.status == "failed"
    assert decoded.result.status.failure_reason == "sampler did not converge after retry"
    assert decoded.result.attempts[0].diagnostics is not None
    assert decoded.result.assessment is None


def test_decoder_refuses_tampering_unknown_fields_and_noncanonical_bytes() -> None:
    from genomeos.validation.spatial_activity_codec import (
        SpatialActivityCodecError,
        decode_spatial_activity_task_result,
        encode_spatial_activity_task_result,
    )

    encoded = encode_spatial_activity_task_result(_record())
    document = json.loads(encoded)
    document["payload"]["result"]["fit_seed"] = 999
    tampered = (json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n").encode()
    with pytest.raises(SpatialActivityCodecError, match="digest"):
        decode_spatial_activity_task_result(tampered)

    document = json.loads(encoded)
    document["payload"]["unexpected"] = True
    payload = json.dumps(
        document["payload"], sort_keys=True, separators=(",", ":")
    ).encode()
    import hashlib

    document["payload_sha256"] = hashlib.sha256(payload).hexdigest()
    extra = (json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n").encode()
    with pytest.raises(SpatialActivityCodecError, match="fields"):
        decode_spatial_activity_task_result(extra)

    with pytest.raises(SpatialActivityCodecError, match="canonical"):
        decode_spatial_activity_task_result(encoded.replace(b":", b": ", 1))


@pytest.mark.parametrize("value", [b"", b"[]\n", b"not-json\n"])
def test_decoder_refuses_invalid_envelopes(value: bytes) -> None:
    from genomeos.validation.spatial_activity_codec import (
        SpatialActivityCodecError,
        decode_spatial_activity_task_result,
    )

    with pytest.raises(SpatialActivityCodecError):
        decode_spatial_activity_task_result(value)


def test_codec_refuses_completed_result_without_assessment() -> None:
    from genomeos.validation.spatial_activity_codec import (
        SpatialActivityCodecError,
        encode_spatial_activity_task_result,
    )

    record = _record()
    invalid = SpatialActivityTaskResult(
        task=record.task,
        result=replace(record.result, assessment=None),
    )
    with pytest.raises(SpatialActivityCodecError, match="assessment"):
        encode_spatial_activity_task_result(invalid)


def test_codec_refuses_unauditable_strata_or_missing_completed_attempt() -> None:
    from genomeos.validation.spatial_activity_codec import (
        SpatialActivityCodecError,
        encode_spatial_activity_task_result,
    )

    record = _record()
    missing_counts = replace(
        record.result.assessment,
        diagnostics=record.result.assessment.diagnostics.drop(
            columns=["observed_ac", "observed_an"]
        ),
    )
    with pytest.raises(SpatialActivityCodecError, match="observed"):
        encode_spatial_activity_task_result(
            SpatialActivityTaskResult(
                task=record.task,
                result=replace(record.result, assessment=missing_counts),
            )
        )
    with pytest.raises(SpatialActivityCodecError, match="completed attempt"):
        encode_spatial_activity_task_result(
            SpatialActivityTaskResult(
                task=record.task,
                result=replace(record.result, attempts=()),
            )
        )
