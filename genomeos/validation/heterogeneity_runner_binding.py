"""Pure B0H receipt and dataset binding (design §§5,7–8,12; runner §§3–6)."""

from __future__ import annotations

import json
import struct

from genomeos.validation.heterogeneity_attempts import (
    FitAttemptResult,
    StructuralCheckResult,
    plan_fit_attempt,
    require_fit_identity,
)
from genomeos.validation.heterogeneity_codec import encode_b0h_evidence
from genomeos.validation.heterogeneity_runner_records import (
    CampaignManifest,
    CaseEvidence,
    StageKey,
    StoredStage,
)
from genomeos.validation.heterogeneity_runner_wire import evidence_receipt, record_digest
from genomeos.validation.heterogeneity_sbc_quantity_types import SelectedSbcQuantities
from genomeos.validation.heterogeneity_simulation_types import (
    AllUnavailableDataset,
    GeneratedDataset,
    GenerationFailure,
)
from genomeos.validation.heterogeneity_summary_types import HeterogeneityFitSummary


def _equal_float(left: float, right: float) -> bool:
    return struct.pack(">d", left) == struct.pack(">d", right)


def _next(manifest: CampaignManifest, evidence: CaseEvidence) -> StageKey | None:
    stages = evidence.stages
    stage, attempt = "generation", None
    if stages:
        latest = stages[-1]
        if latest.completion is None:
            return None
        name = latest.start.key.stage
        value = latest.value
        if name == "generation":
            if type(value) is GeneratedDataset:
                stage, attempt = "fit", 0
            elif type(value) is AllUnavailableDataset:
                stage, attempt = "structural", None
            else:
                return None
        elif name == "fit":
            if type(value) is not FitAttemptResult:
                return None
            if value.status == "convergence_failed" and value.spec.attempt_id == 0:
                stage, attempt = "fit", 1
            elif value.status == "accepted":
                stage = "quantities" if evidence.case.study_id == 0 else "summary"
                attempt = value.spec.attempt_id
            else:
                return None
        elif name == "quantities":
            stage, attempt = "summary", latest.start.key.attempt_id
        else:
            return None
    return StageKey(
        campaign_sha256=evidence.campaign_sha256, case=evidence.case, stage=stage, attempt_id=attempt
    )


def _bind_root(
    manifest: CampaignManifest, stage: StoredStage, dataset: object, accepted: FitAttemptResult | None
) -> None:
    value, key = stage.value, stage.start.key
    if value is None:
        return
    if key.stage == "generation":
        if type(value) not in (GeneratedDataset, AllUnavailableDataset, GenerationFailure):
            raise ValueError("generation has wrong root")
        if value.case_id != key.case:
            raise ValueError("generation case mismatch")
    elif key.stage == "structural":
        if type(dataset) is not AllUnavailableDataset or type(value) is not StructuralCheckResult:
            raise ValueError("structural root or dataset mismatch")
        if value.case != key.case:
            raise ValueError("structural case mismatch")
    elif key.stage == "fit":
        if type(dataset) is not GeneratedDataset or type(value) is not FitAttemptResult:
            raise ValueError("fit root or dataset mismatch")
        if value.spec != plan_fit_attempt(dataset, attempt_id=key.attempt_id):
            raise ValueError("fit spec differs from stage")
        if value.status == "accepted":
            require_fit_identity(dataset, spec=value.spec, fit=value.fit)
    else:
        if type(dataset) is not GeneratedDataset or accepted is None:
            raise ValueError("diagnostics require accepted dataset-bound fit")
        expected_type = SelectedSbcQuantities if key.stage == "quantities" else HeterogeneityFitSummary
        if type(value) is not expected_type:
            raise ValueError("diagnostic root mismatch")
        require_fit_identity(dataset, spec=accepted.spec, fit=accepted.fit)
        if value.spec != accepted.spec or key.attempt_id != accepted.spec.attempt_id:
            raise ValueError("diagnostic attempt mismatch")
        if key.stage == "quantities":
            if type(value) is not SelectedSbcQuantities:
                raise ValueError("quantities root mismatch")
            expected = ((dataset.truth.mean, dataset.truth.rho),) + tuple(
                (float(accepted.fit.mean_draws[c, d, 0]), float(accepted.fit.rho_draws[c, d, 0]))
                for c, d in value.selected_indices
            )
            if value.points[:5] != expected:
                raise ValueError("selected points differ from retained truth/paired draws")
        else:
            if type(value) is not HeterogeneityFitSummary:
                raise ValueError("summary root mismatch")
            if (
                value.variant_id != dataset.training[0].variant_id
                or value.predictive.targets != dataset.heldouts
                or value.predictive.cdf_backend != manifest.cdf_backend
                or not _equal_float(value.parameters[0].truth, dataset.truth.mean)
                or not _equal_float(value.parameters[1].truth, dataset.truth.rho)
            ):
                raise ValueError("summary truth/targets/backend binding mismatch")


def validate_case_evidence(manifest: CampaignManifest, evidence: CaseEvidence) -> None:
    if type(evidence) is not CaseEvidence or evidence.campaign_sha256 != record_digest(manifest):
        raise ValueError("case campaign identity mismatch")
    if evidence.case not in manifest.cases or type(evidence.stages) is not tuple:
        raise ValueError("case membership or stage sequence mismatch")
    prior = CaseEvidence(evidence.campaign_sha256, evidence.case, ())
    dataset, accepted = None, None
    for stage in evidence.stages:
        if type(stage) is not StoredStage or stage.start.key != _next(manifest, prior):
            raise ValueError("unexplained stage or orphan scientific retry")
        start = stage.start
        dependencies = tuple(record_digest(s.completion) for s in prior.stages)
        if (
            start.prerequisites != dependencies
            or start.worker_id != manifest.worker_id
            or start.source != manifest.source
            or start.runtime != manifest.runtime
            or start.cdf_backend != manifest.cdf_backend
        ):
            raise ValueError("START dependency/runtime/assignment mismatch")
        start_digest = record_digest(start)
        if stage.completion is None:
            if any(x is not None for x in (stage.receipt, stage.failure, stage.encoded, stage.value)):
                raise ValueError("receipt/result without COMPLETE")
            if stage.loss is not None and (
                stage.loss.start_sha256 != start_digest or stage.loss.previous_owner_id != start.owner_id
            ):
                raise ValueError("owner loss identity mismatch")
        else:
            if stage.loss is not None or stage.completion.start_sha256 != start_digest:
                raise ValueError("completion/loss START mismatch")
            record_digest(stage.completion)
            if stage.receipt is not None:
                if (
                    stage.failure is not None
                    or stage.encoded is None
                    or stage.value is None
                    or stage.completion.receipt_sha256 != record_digest(stage.receipt)
                    or stage.completion.failure_sha256 is not None
                    or evidence_receipt(start, stage.encoded, limits=manifest.limits) != stage.receipt
                    or encode_b0h_evidence(stage.value, limits=manifest.limits) != stage.encoded
                ):
                    raise ValueError("receipt/scientific bytes mismatch")
                _bind_root(manifest, stage, dataset, accepted)
            elif (
                stage.failure is None
                or stage.encoded is not None
                or stage.value is not None
                or stage.completion.receipt_sha256 is not None
                or stage.completion.failure_sha256 != record_digest(stage.failure)
                or stage.failure.start_sha256 != start_digest
            ):
                raise ValueError("execution failure envelope mismatch")
        if start.key.stage == "generation":
            dataset = stage.value
        if type(stage.value) is FitAttemptResult and stage.value.status == "accepted":
            accepted = stage.value
        prior = CaseEvidence(prior.campaign_sha256, prior.case, prior.stages + (stage,))


def next_stage_key(manifest: CampaignManifest, evidence: CaseEvidence) -> StageKey | None:
    validate_case_evidence(manifest, evidence)
    return _next(manifest, evidence)


def require_paired_generations(left: StoredStage, right: StoredStage) -> None:
    a, b = left.start.key.case, right.start.key.case
    if (
        a.study_id == 0
        or (a.study_id, a.case_id, a.replicate_id) != (b.study_id, b.case_id, b.replicate_id)
        or {a.track_id, b.track_id} != {0, 1}
    ):
        raise ValueError("paired generation identity mismatch")
    if left.encoded is None or right.encoded is None:
        return

    def content(encoded):
        document = json.loads(encoded.metadata)
        root = document["root"]
        return (root[1], {key: value for key, value in root[2].items() if key != "case_id"}, encoded.payloads)

    if content(left.encoded) != content(right.encoded):
        raise ValueError("paired stress generation content differs")
