"""Closed offline B0H runner records (design §§5,7–8,12; runner §§2–5)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from genomeos.validation.heterogeneity_codec import B0HCodecLimits, B0HEvidence, EncodedB0HEvidence
from genomeos.validation.heterogeneity_simulation import enumerate_sbc_cases
from genomeos.validation.heterogeneity_simulation_types import SbcCaseId
from genomeos.validation.sbc_ranks import RankNullReference

Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Text = Annotated[str, Field(min_length=1)]
Natural = Annotated[int, Field(ge=0)]
Positive = Annotated[int, Field(gt=0)]
StageName = Literal["generation", "structural", "fit", "quantities", "summary"]
RootName = Literal[
    "GeneratedDataset",
    "AllUnavailableDataset",
    "GenerationFailure",
    "FitAttemptResult",
    "StructuralCheckResult",
    "SelectedSbcQuantities",
    "HeterogeneityFitSummary",
]


class ClosedRecord(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid", revalidate_instances="always")

    @model_validator(mode="before")
    @classmethod
    def literal_scalar_types(cls, value):
        if type(value) is dict:
            bool_fields = {
                "jax_float64",
                "cupy_float64",
                "exclusive_lock_observed",
                "rollback_observed",
                "commit_readback_observed",
                "directory_fsync_observed",
            }
            int_fields = {
                "sample_size",
                "replicates",
                "seed",
                "attempt_id",
                "accepted_attempt",
                "track_id",
                "study_id",
                "mode_id",
                "quantity_id",
                "planned_initial_fits",
                "planned_retry_slots",
            }
            for name, item in value.items():
                if name in bool_fields and type(item) is not bool:
                    raise ValueError("Boolean observation must be literal bool")
                if name in int_fields and item is not None and type(item) is not int:
                    raise ValueError("integer identity must be literal int")
        return value


class SourceIdentity(ClosedRecord):
    revision: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
    content_sha256: Digest
    lock_sha256: Digest


class RuntimeIdentity(ClosedRecord):
    python_version: Text
    platform: Text
    machine: Text
    environment_sha256: Digest
    jax_version: Text
    cupy_version: Text
    jax_device: Text
    cupy_device: Text
    driver_version: Text
    jax_float64: Literal[True]
    cupy_float64: Literal[True]


class StorageAdmission(ClosedRecord):
    database_parent: Annotated[str, Field(pattern=r"^/")]
    device_id: Natural
    mount_type: Text
    mount_options: Text
    free_bytes: Natural
    probe_sha256: Digest
    exclusive_lock_observed: Literal[True]
    rollback_observed: Literal[True]
    commit_readback_observed: Literal[True]
    directory_fsync_observed: Literal[True]


class AdmissionReceipt(ClosedRecord):
    format: Literal["b0h_admission"]
    version: Literal["1"]
    source: SourceIdentity
    runtime: RuntimeIdentity
    storage: StorageAdmission
    observed_unix_ns: Natural
    startup_elapsed_ns: Natural
    preflight_elapsed_ns: Natural
    device_total_bytes: Positive
    device_free_bytes: Natural
    process_peak_rss_bytes: Positive
    memory_observation_label: Text

    @model_validator(mode="after")
    def memory_bounds(self) -> Self:
        if self.device_free_bytes > self.device_total_bytes:
            raise ValueError("free memory exceeds device memory")
        return self


class PreparedNull(ClosedRecord):
    format: Literal["b0h_rank_null"]
    version: Literal["1"]
    entropy: tuple[int, int, int, int, int, int, int, int, int]
    sample_size: Literal[512]
    replicates: Literal[100000]
    seed: Literal[1653499886]
    statistics: Annotated[
        tuple[Annotated[int, Field(ge=0, le=2048)], ...], Field(min_length=100000, max_length=100000)
    ]

    @model_validator(mode="after")
    def identity(self) -> Self:
        if self.entropy != (42, 211, 1, 100, 0, 0, 0, 0, 0):
            raise ValueError("wrong null entropy")
        return self


class CampaignManifest(ClosedRecord):
    format: Literal["b0h_campaign"]
    version: Literal["1"]
    protocol: Literal["b0h_sbc_v1"]
    runner_version: Literal["1"]
    codec_version: Literal["1"]
    cdf_backend: Literal["cupy"]
    source: SourceIdentity
    runtime: RuntimeIdentity
    admission_sha256: Digest
    null_sha256: Digest
    max_metadata_bytes: Positive
    max_total_payload_bytes: Natural
    worker_id: Text
    cases: tuple[SbcCaseId, ...]

    @model_validator(mode="after")
    def planned_cases(self) -> Self:
        if self.cases != enumerate_sbc_cases():
            raise ValueError("campaign requires exact ordered 1938 cases")
        return self

    @property
    def limits(self) -> B0HCodecLimits:
        return B0HCodecLimits(self.max_metadata_bytes, self.max_total_payload_bytes)


class StageKey(ClosedRecord):
    campaign_sha256: Digest
    case: SbcCaseId
    stage: StageName
    attempt_id: Literal[0, 1] | None

    @model_validator(mode="after")
    def allowed_stage(self) -> Self:
        if self.stage in ("generation", "structural"):
            if self.attempt_id is not None:
                raise ValueError("generation/structural has no fit attempt")
        elif type(self.attempt_id) is not int:
            raise ValueError("fit-bearing stage requires attempt0/1")
        if self.stage == "structural" and self.case.study_id != 3:
            raise ValueError("structural requires study3")
        if self.stage not in ("generation", "structural") and self.case.study_id == 3:
            raise ValueError("study3 has no fit-bearing stage")
        if self.stage == "quantities" and self.case.study_id != 0:
            raise ValueError("quantities requires study0")
        return self


class StageStart(ClosedRecord):
    format: Literal["b0h_start"]
    version: Literal["1"]
    key: StageKey
    worker_id: Text
    owner_id: Text
    source: SourceIdentity
    runtime: RuntimeIdentity
    cdf_backend: Literal["cupy"]
    prerequisites: tuple[Digest, ...]
    started_unix_ns: Natural
    started_monotonic_ns: Natural

    @model_validator(mode="after")
    def unique_dependencies(self) -> Self:
        if len(set(self.prerequisites)) != len(self.prerequisites):
            raise ValueError("duplicate prerequisite")
        return self


class PayloadIdentity(ClosedRecord):
    sha256: Digest
    length: Natural


class EvidenceReceipt(ClosedRecord):
    format: Literal["b0h_receipt"]
    version: Literal["1"]
    start_sha256: Digest
    root_type: RootName
    metadata_sha256: Digest
    metadata_length: Positive
    payloads: tuple[PayloadIdentity, ...]

    @model_validator(mode="after")
    def payload_order(self) -> Self:
        identities = tuple(p.sha256 for p in self.payloads)
        if identities != tuple(sorted(set(identities))):
            raise ValueError("payload identities must be sorted and unique")
        return self


class StageExecutionFailure(ClosedRecord):
    format: Literal["b0h_execution_failure"]
    version: Literal["1"]
    start_sha256: Digest
    phase: Literal["public_call", "returned_evidence_validation", "codec_encoding"]
    exception_class: Annotated[str, Field(pattern=r"^[^.]+(?:\.[^.]+)+$")]
    message_utf8hex: Annotated[str, Field(pattern=r"^(?:[0-9a-f]{2})*$")]

    @model_validator(mode="after")
    def message_encoding(self) -> Self:
        raw = bytes.fromhex(self.message_utf8hex)
        if raw.decode("utf-8", "surrogatepass").encode("utf-8", "surrogatepass") != raw:
            raise ValueError("noncanonical exception message")
        return self


class StageCompletion(ClosedRecord):
    format: Literal["b0h_completion"]
    version: Literal["1"]
    start_sha256: Digest
    receipt_sha256: Digest | None
    failure_sha256: Digest | None
    whole_call_elapsed_ns: Natural
    process_peak_rss_bytes: Positive | None
    resource_unavailable_reason: Text | None

    @model_validator(mode="after")
    def exclusive_fields(self) -> Self:
        if (self.receipt_sha256 is None) == (self.failure_sha256 is None):
            raise ValueError("completion requires exactly one receipt or failure")
        if (self.process_peak_rss_bytes is None) == (self.resource_unavailable_reason is None):
            raise ValueError("resource value requires observation or unavailable reason")
        return self


class OwnerLoss(ClosedRecord):
    format: Literal["b0h_owner_loss"]
    version: Literal["1"]
    start_sha256: Digest
    previous_owner_id: Text
    observing_owner_id: Text
    observed_unix_ns: Natural
    evidence: Literal["prior_process_exclusion_released"]
    surviving_receipts: tuple[()]

    @model_validator(mode="after")
    def distinct_owner(self) -> Self:
        if self.previous_owner_id == self.observing_owner_id:
            raise ValueError("live owner cannot declare its own process loss")
        return self


RunnerRecord = (
    AdmissionReceipt
    | PreparedNull
    | CampaignManifest
    | StageStart
    | EvidenceReceipt
    | StageExecutionFailure
    | StageCompletion
    | OwnerLoss
)


@dataclass(frozen=True)
class PublicationPacket:
    start: StageStart
    completion: StageCompletion
    receipt: EvidenceReceipt | None
    encoded: EncodedB0HEvidence | None
    failure: StageExecutionFailure | None

    def __post_init__(self) -> None:
        from genomeos.validation.heterogeneity_runner_wire import record_digest

        if type(self.start) is not StageStart or type(self.completion) is not StageCompletion:
            raise ValueError("publication requires exact START and COMPLETE roots")
        digest = record_digest(self.start)
        record_digest(self.completion)
        if self.completion.start_sha256 != digest:
            raise ValueError("publication completion START mismatch")
        if self.receipt is not None:
            if (
                type(self.receipt) is not EvidenceReceipt
                or type(self.encoded) is not EncodedB0HEvidence
                or self.failure is not None
                or self.receipt.start_sha256 != digest
                or self.completion.receipt_sha256 != record_digest(self.receipt)
                or self.completion.failure_sha256 is not None
            ):
                raise ValueError("publication scientific fields mismatch")
        elif (
            type(self.failure) is not StageExecutionFailure
            or self.encoded is not None
            or self.failure.start_sha256 != digest
            or self.completion.failure_sha256 != record_digest(self.failure)
            or self.completion.receipt_sha256 is not None
        ):
            raise ValueError("publication failure fields mismatch")


@dataclass(frozen=True)
class StoredStage:
    start: StageStart
    completion: StageCompletion | None
    receipt: EvidenceReceipt | None
    failure: StageExecutionFailure | None
    loss: OwnerLoss | None
    encoded: EncodedB0HEvidence | None
    value: B0HEvidence | None


@dataclass(frozen=True)
class CaseEvidence:
    campaign_sha256: str
    case: SbcCaseId
    stages: tuple[StoredStage, ...]


def prepared_null(reference: RankNullReference) -> PreparedNull:
    if type(reference) is not RankNullReference:
        raise ValueError("null requires RankNullReference")
    if reference.sample_size != 512:
        raise ValueError("null sample_size must be 512")
    if len(reference.statistics) != 100000:
        raise ValueError("null requires 100000 statistics")
    if reference.seed != 1653499886:
        raise ValueError("null seed must be 1653499886")
    return PreparedNull(
        format="b0h_rank_null",
        version="1",
        entropy=(42, 211, 1, 100, 0, 0, 0, 0, 0),
        sample_size=512,
        replicates=100000,
        seed=1653499886,
        statistics=reference.statistics,
    )


def restore_null(record: PreparedNull) -> RankNullReference:
    checked = PreparedNull.model_validate(record)
    return RankNullReference(checked.sample_size, checked.seed, checked.statistics)
