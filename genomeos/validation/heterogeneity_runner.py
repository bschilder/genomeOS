"""Offline one-call B0H case execution (design §§5,7–8,12; runner §4)."""
from __future__ import annotations

import resource
import sys
import time
from functools import partial

from genomeos.validation.heterogeneity_attempts import (
    FitAttemptResult,
    exercise_unavailable,
    plan_fit_attempt,
    run_fit_attempt,
)
from genomeos.validation.heterogeneity_codec import encode_b0h_evidence
from genomeos.validation.heterogeneity_runner_binding import (
    next_stage_key,
    require_paired_generations,
    validate_case_evidence,
)
from genomeos.validation.heterogeneity_runner_records import (
    CampaignManifest,
    CaseEvidence,
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


def execute_b0h_case(manifest: CampaignManifest, case: SbcCaseId,
                     store: LocalB0HStore) -> CaseEvidence:
    while True:
        evidence = load_b0h_case(manifest, case, store)
        if evidence.stages and evidence.stages[-1].completion is None:
            pending = evidence.stages[-1]
            if pending.start.owner_id != store.owner_id and pending.loss is None:
                store.record_owner_loss(pending.start)
            return load_b0h_case(manifest, case, store)
        key = next_stage_key(manifest, evidence)
        if key is None:
            return evidence
        dataset = None if not evidence.stages else evidence.stages[0].value
        accepted = next((s.value for s in evidence.stages
                         if type(s.value) is FitAttemptResult and s.value.status == "accepted"), None)
        spec = plan_fit_attempt(dataset, attempt_id=key.attempt_id) if key.stage == "fit" else None
        if key.stage == "generation":
            call = partial(generate_sbc_case, case)
        elif key.stage == "structural":
            call = partial(exercise_unavailable, dataset)
        elif key.stage == "fit":
            call = partial(run_fit_attempt, dataset, spec=spec)
        elif key.stage == "quantities":
            call = partial(selected_sbc_quantities, dataset, attempt=accepted)
        else:
            call = partial(summarize_heterogeneity_fit, dataset, attempt=accepted,
                           cdf_backend=manifest.cdf_backend)
        start = StageStart(
            format="b0h_start", version="1", key=key, worker_id=manifest.worker_id,
            owner_id=store.owner_id, source=manifest.source, runtime=manifest.runtime,
            cdf_backend=manifest.cdf_backend,
            prerequisites=tuple(record_digest(s.completion) for s in evidence.stages),
            started_unix_ns=time.time_ns(), started_monotonic_ns=time.monotonic_ns(),
        )
        store.start(start)
        call_started = time.monotonic_ns()
        failure, receipt, encoded = None, None, None
        try:
            value = call()
        except Exception as error:
            elapsed = time.monotonic_ns() - call_started
            failure = _execution_error(start, "public_call", error)
        else:
            elapsed = time.monotonic_ns() - call_started
            encoded = encode_b0h_evidence(value, limits=manifest.limits)
            receipt = evidence_receipt(start, encoded, limits=manifest.limits)
        rss, unavailable = _resource_observation()
        completion = StageCompletion(
            format="b0h_completion", version="1", start_sha256=record_digest(start),
            receipt_sha256=None if receipt is None else record_digest(receipt),
            failure_sha256=None if failure is None else record_digest(failure),
            whole_call_elapsed_ns=elapsed, process_peak_rss_bytes=rss,
            resource_unavailable_reason=unavailable,
        )
        store.complete(start, completion, receipt=receipt, encoded=encoded, failure=failure)
        load_b0h_case(manifest, case, store)
