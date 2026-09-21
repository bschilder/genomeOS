"""Offline one-call B0H case execution (design §§5,7–8,12; runner §4)."""
from __future__ import annotations

import resource
import sys
import time
from dataclasses import dataclass
from functools import partial

from genomeos.validation.heterogeneity_attempts import (
    FitAttemptResult,
    exercise_unavailable,
    plan_fit_attempt,
    run_fit_attempt,
)
from genomeos.validation.heterogeneity_codec import (
    B0HCodecLimits,
    B0HEvidence,
    encode_b0h_evidence,
)
from genomeos.validation.heterogeneity_runner_binding import (
    next_stage_key,
    require_paired_generations,
    validate_case_evidence,
)
from genomeos.validation.heterogeneity_runner_records import (
    CampaignManifest,
    CaseEvidence,
    PublicationPacket,
    StageCompletion,
    StageExecutionFailure,
    StageStart,
)
from genomeos.validation.heterogeneity_runner_store import LocalB0HStore, StoreIntegrityError
from genomeos.validation.heterogeneity_runner_wire import evidence_receipt, record_digest
from genomeos.validation.heterogeneity_sbc_quantities import selected_sbc_quantities
from genomeos.validation.heterogeneity_simulation import generate_sbc_case
from genomeos.validation.heterogeneity_simulation_types import SbcCaseId
from genomeos.validation.heterogeneity_summaries import summarize_heterogeneity_fit


@dataclass(frozen=True)
class B0HStageTask:
    start: StageStart
    limits: B0HCodecLimits
    dataset: B0HEvidence | None
    accepted: FitAttemptResult | None

    def __post_init__(self) -> None:
        if (
            type(self.start) is not StageStart
            or type(self.limits) is not B0HCodecLimits
        ):
            raise ValueError("stage task requires exact START and codec limits")


def load_b0h_case(manifest: CampaignManifest, case: SbcCaseId,
                  store: LocalB0HStore) -> CaseEvidence:
    if record_digest(store.manifest) != record_digest(manifest) or case not in manifest.cases:
        raise StoreIntegrityError("requested campaign/case mismatch")
    evidence = CaseEvidence(record_digest(manifest), case, store.stages(case))
    validate_case_evidence(manifest, evidence)
    if case.study_id != 0 and evidence.stages:
        paired = SbcCaseId(1 - case.track_id, case.study_id, case.case_id, case.replicate_id)
        other = CaseEvidence(record_digest(manifest), paired, store.stages(paired))
        validate_case_evidence(manifest, other)
        if other.stages:
            require_paired_generations(evidence.stages[0], other.stages[0])
    return evidence


def _resource_observation() -> tuple[int | None, str | None]:
    if sys.platform not in ("linux", "darwin"):
        return None, "process_peak_rss_unit_unavailable_on_platform"
    try:
        raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    except OSError as error:
        return None, type(error).__module__ + "." + type(error).__qualname__
    return int(raw) * (1024 if sys.platform == "linux" else 1), None


def _execution_error(start: StageStart, phase: str, error: Exception) -> StageExecutionFailure:
    return StageExecutionFailure(
        format="b0h_execution_failure", version="1", start_sha256=record_digest(start),
        phase=phase, exception_class=type(error).__module__ + "." + type(error).__qualname__,
        message_utf8hex=str(error).encode("utf-8", "surrogatepass").hex(),
    )


def prepare_b0h_stage(
    manifest: CampaignManifest,
    case: SbcCaseId,
    store: LocalB0HStore,
) -> B0HStageTask | None:
    """Commit one START and return its immutable science task."""
    evidence = load_b0h_case(manifest, case, store)
    if evidence.stages and evidence.stages[-1].completion is None:
        pending = evidence.stages[-1]
        if pending.start.owner_id != store.owner_id and pending.loss is None:
            store.record_owner_loss(pending.start)
        return None
    key = next_stage_key(manifest, evidence)
    if key is None:
        return None
    dataset = None if not evidence.stages else evidence.stages[0].value
    accepted = next(
        (
            stage.value
            for stage in evidence.stages
            if type(stage.value) is FitAttemptResult and stage.value.status == "accepted"
        ),
        None,
    )
    start = StageStart(
        format="b0h_start",
        version="1",
        key=key,
        worker_id=manifest.worker_id,
        owner_id=store.owner_id,
        source=manifest.source,
        runtime=manifest.runtime,
        cdf_backend=manifest.cdf_backend,
        prerequisites=tuple(record_digest(stage.completion) for stage in evidence.stages),
        started_unix_ns=time.time_ns(),
        started_monotonic_ns=time.monotonic_ns(),
    )
    store.start(start)
    return B0HStageTask(start, manifest.limits, dataset, accepted)


def execute_b0h_stage(task: B0HStageTask) -> PublicationPacket:
    """Execute one admitted stage without filesystem or SQLite access."""
    if type(task) is not B0HStageTask:
        raise ValueError("stage execution requires an exact task")
    start = task.start
    key = start.key
    spec = (
        plan_fit_attempt(task.dataset, attempt_id=key.attempt_id)
        if key.stage == "fit"
        else None
    )
    if key.stage == "generation":
        call = partial(generate_sbc_case, key.case)
    elif key.stage == "structural":
        call = partial(exercise_unavailable, task.dataset)
    elif key.stage == "fit":
        call = partial(run_fit_attempt, task.dataset, spec=spec)
    elif key.stage == "quantities":
        call = partial(selected_sbc_quantities, task.dataset, attempt=task.accepted)
    else:
        call = partial(
            summarize_heterogeneity_fit,
            task.dataset,
            attempt=task.accepted,
            cdf_backend=start.cdf_backend,
        )
    call_started = time.monotonic_ns()
    failure, receipt, encoded = None, None, None
    try:
        value = call()
    except Exception as error:
        elapsed = time.monotonic_ns() - call_started
        failure = _execution_error(start, "public_call", error)
    else:
        elapsed = time.monotonic_ns() - call_started
        encoded = encode_b0h_evidence(value, limits=task.limits)
        receipt = evidence_receipt(start, encoded, limits=task.limits)
    rss, unavailable = _resource_observation()
    completion = StageCompletion(
        format="b0h_completion",
        version="1",
        start_sha256=record_digest(start),
        receipt_sha256=None if receipt is None else record_digest(receipt),
        failure_sha256=None if failure is None else record_digest(failure),
        whole_call_elapsed_ns=elapsed,
        process_peak_rss_bytes=rss,
        resource_unavailable_reason=unavailable,
    )
    return PublicationPacket(start, completion, receipt, encoded, failure)


def execute_b0h_case(
    manifest: CampaignManifest,
    case: SbcCaseId,
    store: LocalB0HStore,
) -> CaseEvidence:
    while True:
        task = prepare_b0h_stage(manifest, case, store)
        if task is None:
            return load_b0h_case(manifest, case, store)
        store.publish_pending(execute_b0h_stage(task))
        load_b0h_case(manifest, case, store)
