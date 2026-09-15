"""Canonical operational B0H bytes (design §§5,7–8,12; runner §§3,5)."""
from __future__ import annotations

import hashlib
import json
from typing import Annotated

from pydantic import Field, TypeAdapter

from genomeos.validation.heterogeneity_codec import (
    B0HCodecLimits,
    EncodedB0HEvidence,
    decode_b0h_evidence,
)
from genomeos.validation.heterogeneity_runner_records import (
    AdmissionReceipt,
    CampaignManifest,
    EvidenceReceipt,
    OwnerLoss,
    PayloadIdentity,
    PreparedNull,
    RunnerRecord,
    StageCompletion,
    StageExecutionFailure,
    StageStart,
)
from genomeos.validation.heterogeneity_simulation import enumerate_sbc_cases
from genomeos.validation.heterogeneity_simulation_types import SbcCaseId

MAX_OPERATION_BYTES = 8 * 1024 * 1024
_RECORDS = TypeAdapter(Annotated[RunnerRecord, Field(discriminator="format")])
_ROOT_TYPES = (AdmissionReceipt, PreparedNull, CampaignManifest, StageStart,
               EvidenceReceipt, StageExecutionFailure, StageCompletion, OwnerLoss)


def sha256(data: bytes) -> str:
    if type(data) is not bytes:
        raise ValueError("digest input must be exact bytes")
    return hashlib.sha256(data).hexdigest()


def _pairs(items: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _reject_number(value: str) -> None:
    raise ValueError("operational JSON admits no floating numeric literal")


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=True, allow_nan=False,
                      sort_keys=True, separators=(",", ":")).encode("ascii")


def _tuplify(value: object) -> object:
    if type(value) is list:
        return tuple(_tuplify(item) for item in value)
    if type(value) is dict:
        converted = {key: _tuplify(item) for key, item in value.items()}
        if set(converted) == {"track_id", "study_id", "case_id", "replicate_id"}:
            return SbcCaseId(**converted)
        return converted
    return value


def runner_record_bytes(record: RunnerRecord) -> bytes:
    if type(record) not in _ROOT_TYPES:
        raise ValueError("unsupported operational root")
    validated = _RECORDS.validate_python(record, strict=True)
    raw = _canonical(validated.model_dump(mode="json"))
    if len(raw) > MAX_OPERATION_BYTES:
        raise ValueError("operational record exceeds byte budget")
    # JSON arrays are the wire representation of tuple fields; materialize
    # those arrays as tuples before applying strict Python validation.
    checked = _RECORDS.validate_python(_tuplify(json.loads(raw)), strict=True)
    if type(checked) is not type(record) or _canonical(checked.model_dump(mode="json")) != raw:
        raise ValueError("operational constructor changed evidence")
    return raw


def read_runner_record(data: bytes) -> RunnerRecord:
    if type(data) is not bytes or len(data) > MAX_OPERATION_BYTES:
        raise ValueError("operational bytes type or budget")
    depth, quoted, escaped = 0, False, False
    for byte in data:
        if quoted:
            if escaped:
                escaped = False
            elif byte == 92:
                escaped = True
            elif byte == 34:
                quoted = False
        elif byte == 34:
            quoted = True
        elif byte in (91, 123):
            depth += 1
            if depth > 32:
                raise ValueError("operational nesting exceeds 32")
        elif byte in (93, 125):
            depth -= 1
    document = json.loads(data.decode("ascii"), object_pairs_hook=_pairs,
                          parse_float=_reject_number, parse_constant=_reject_number)
    if _canonical(document) != data:
        raise ValueError("noncanonical operational JSON")
    checked = _RECORDS.validate_python(_tuplify(document), strict=True)
    if runner_record_bytes(checked) != data:
        raise ValueError("operational normalization changed bytes")
    return checked


def record_digest(record: RunnerRecord) -> str:
    return sha256(runner_record_bytes(record))


def build_manifest(admission: AdmissionReceipt, null: PreparedNull, *,
                   worker_id: str, limits: B0HCodecLimits) -> CampaignManifest:
    admission = read_runner_record(runner_record_bytes(admission))
    null = read_runner_record(runner_record_bytes(null))
    if type(admission) is not AdmissionReceipt or type(null) is not PreparedNull:
        raise ValueError("manifest requires admission and prepared null")
    return CampaignManifest(
        format="b0h_campaign", version="1", protocol="b0h_sbc_v1",
        runner_version="1", codec_version="1", cdf_backend="cupy",
        source=admission.source, runtime=admission.runtime,
        admission_sha256=record_digest(admission), null_sha256=record_digest(null),
        max_metadata_bytes=limits.max_metadata_bytes,
        max_total_payload_bytes=limits.max_total_payload_bytes,
        worker_id=worker_id, cases=enumerate_sbc_cases(),
    )


def evidence_receipt(start: StageStart, encoded: EncodedB0HEvidence, *,
                     limits: B0HCodecLimits) -> EvidenceReceipt:
    value = decode_b0h_evidence(encoded, limits=limits)
    return EvidenceReceipt(
        format="b0h_receipt", version="1", start_sha256=record_digest(start),
        root_type=type(value).__name__, metadata_sha256=sha256(encoded.metadata),
        metadata_length=len(encoded.metadata),
        payloads=tuple(PayloadIdentity(sha256=digest, length=len(raw))
                       for digest, raw in encoded.payloads),
    )
