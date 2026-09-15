"""Validate reviewed preflight bytes before acquisition I/O (acquisition design §§1, 4.1)."""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

from genomeos.validation.reference_acquisition_types import RetainedIndex, ReviewReceipt
from genomeos.validation.reference_byte_plan import (
    POLICY,
    BytePreflight,
    ByteRange,
    IndexReceipt,
    SourceBytePlan,
    WindowBytePlan,
    assemble_preflight,
    crc32c,
    encode_preflight,
    fixed_vcf_ranges,
    merge_byte_ranges,
    plan_window,
)
from genomeos.validation.reference_tbi import VirtualChunk, parse_tbi
from genomeos.validation.reference_window_manifest import encode_manifest
from genomeos.validation.reference_window_types import (
    AUTOSOMES,
    Provenance,
    PublicObject,
    SourcePair,
    WindowManifest,
)

_TOP_KEYS = {
    "schema_version",
    "manifest_sha256",
    "windows_sha256",
    "sources",
    "complete",
    "budget_status",
    "known_planned_bytes",
    "total_planned_bytes",
    "max_transfer_bytes",
    "provenance",
    "policy",
    "publication_eligible",
    "p1_eligible",
}
_SOURCE_PLAN_KEYS = {"source", "receipt", "windows", "merged_vcf_ranges"}
_SOURCE_KEYS = {"chrom", "vcf", "tbi"}
_PUBLIC_OBJECT_KEYS = {"uri", "generation", "size_bytes", "md5_b64", "crc32c_b64"}
_RECEIPT_KEYS = {
    "chrom",
    "state",
    "reason",
    "vcf_metadata_attempts",
    "tbi_metadata_attempts",
    "tbi_body_attempts",
    "received_bytes",
    "sha256",
}
_WINDOW_KEYS = {"window_id", "state", "reason", "variant_content", "chunks", "ranges"}
_CHUNK_KEYS = {"begin", "end"}
_RANGE_KEYS = {"first", "last"}
_PROVENANCE_KEYS = {
    "data_version",
    "evidence_kind",
    "input_sha256",
    "source_revision",
    "imported_source_sha256",
    "python_version",
    "source_audit_locator",
}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate preflight key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"nonfinite preflight value: {value}")


def _json(raw: bytes) -> Any:
    _require(type(raw) is bytes and bool(raw), "preflight must be nonempty bytes")
    try:
        text = raw.decode("utf-8")
        return json.loads(text, object_pairs_hook=_unique_pairs, parse_constant=_reject_constant)
    except UnicodeDecodeError as error:
        raise ValueError("preflight must be UTF-8") from error
    except json.JSONDecodeError as error:
        raise ValueError("invalid preflight JSON") from error


def _object(value: object, keys: set[str], field: str) -> dict[str, Any]:
    _require(type(value) is dict and set(value) == keys, f"invalid {field} fields")
    return value


def _array(value: object, field: str) -> list[Any]:
    _require(type(value) is list, f"{field} must be an array")
    return value


def _text(value: object, field: str) -> str:
    _require(isinstance(value, str) and bool(value.strip()) and value == value.strip(), f"invalid {field}")
    return value


def _integer(value: object, field: str, *, minimum: int = 0) -> int:
    _require(type(value) is int and value >= minimum, f"{field} must be an integer >= {minimum}")
    return value


def _optional_integer(value: object, field: str) -> int | None:
    return None if value is None else _integer(value, field)


def _optional_text(value: object, field: str) -> str | None:
    return None if value is None else _text(value, field)


def _hash_entries(value: object, field: str) -> tuple[tuple[str, str], ...]:
    fields = value if type(value) is dict else None
    _require(fields is not None, f"{field} must be an object")
    return tuple(
        sorted(
            (_text(key, f"{field} key"), _text(digest, f"{field} digest"))
            for key, digest in fields.items()
        )
    )


def _public_object(value: object) -> PublicObject:
    fields = _object(value, _PUBLIC_OBJECT_KEYS, "public object")
    return PublicObject(
        _text(fields["uri"], "uri"),
        _text(fields["generation"], "generation"),
        _integer(fields["size_bytes"], "size_bytes", minimum=1),
        _text(fields["md5_b64"], "md5_b64"),
        _text(fields["crc32c_b64"], "crc32c_b64"),
    )


def _source(value: object) -> SourcePair:
    fields = _object(value, _SOURCE_KEYS, "source")
    return SourcePair(
        _text(fields["chrom"], "source chrom"),
        _public_object(fields["vcf"]),
        _public_object(fields["tbi"]),
    )


def _receipt(value: object) -> IndexReceipt:
    fields = _object(value, _RECEIPT_KEYS, "index receipt")
    return IndexReceipt(
        _text(fields["chrom"], "receipt chrom"),
        _text(fields["state"], "receipt state"),
        _optional_text(fields["reason"], "receipt reason"),
        _integer(fields["vcf_metadata_attempts"], "vcf_metadata_attempts"),
        _integer(fields["tbi_metadata_attempts"], "tbi_metadata_attempts"),
        _integer(fields["tbi_body_attempts"], "tbi_body_attempts"),
        _integer(fields["received_bytes"], "received_bytes"),
        _optional_text(fields["sha256"], "receipt sha256"),
    )


def _chunk(value: object) -> VirtualChunk:
    fields = _object(value, _CHUNK_KEYS, "virtual chunk")
    return VirtualChunk(_integer(fields["begin"], "chunk begin"), _integer(fields["end"], "chunk end"))


def _byte_range(value: object) -> ByteRange:
    fields = _object(value, _RANGE_KEYS, "byte range")
    return ByteRange(_integer(fields["first"], "range first"), _integer(fields["last"], "range last"))


def _window(value: object) -> WindowBytePlan:
    fields = _object(value, _WINDOW_KEYS, "window plan")
    return WindowBytePlan(
        _text(fields["window_id"], "window_id"),
        _text(fields["state"], "window state"),
        _optional_text(fields["reason"], "window reason"),
        _text(fields["variant_content"], "variant_content"),
        tuple(_chunk(item) for item in _array(fields["chunks"], "chunks")),
        tuple(_byte_range(item) for item in _array(fields["ranges"], "ranges")),
    )


def _source_plan(value: object) -> SourceBytePlan:
    fields = _object(value, _SOURCE_PLAN_KEYS, "source plan")
    return SourceBytePlan(
        _source(fields["source"]),
        _receipt(fields["receipt"]),
        tuple(_window(item) for item in _array(fields["windows"], "windows")),
        tuple(_byte_range(item) for item in _array(fields["merged_vcf_ranges"], "merged ranges")),
    )


def _provenance(value: object) -> Provenance:
    fields = _object(value, _PROVENANCE_KEYS, "preflight provenance")
    return Provenance(
        data_version=_text(fields["data_version"], "data_version"),
        evidence_kind=_text(fields["evidence_kind"], "evidence_kind"),
        input_sha256=_hash_entries(fields["input_sha256"], "input_sha256"),
        source_revision=_text(fields["source_revision"], "source_revision"),
        imported_source_sha256=_hash_entries(fields["imported_source_sha256"], "imported_source_sha256"),
        python_version=_text(fields["python_version"], "python_version"),
        source_audit_locator=_text(fields["source_audit_locator"], "source_audit_locator"),
    )


def _decode(raw: bytes) -> BytePreflight:
    fields = _object(_json(raw), _TOP_KEYS, "preflight")
    policy = fields["policy"]
    _require(type(policy) is dict, "policy must be an object")
    value = BytePreflight(
        schema_version=_text(fields["schema_version"], "schema_version"),
        manifest_sha256=_text(fields["manifest_sha256"], "manifest_sha256"),
        windows_sha256=_text(fields["windows_sha256"], "windows_sha256"),
        sources=tuple(_source_plan(item) for item in _array(fields["sources"], "sources")),
        complete=fields["complete"],
        budget_status=_text(fields["budget_status"], "budget_status"),
        known_planned_bytes=_integer(fields["known_planned_bytes"], "known_planned_bytes"),
        total_planned_bytes=_optional_integer(fields["total_planned_bytes"], "total_planned_bytes"),
        max_transfer_bytes=_integer(fields["max_transfer_bytes"], "max_transfer_bytes", minimum=1),
        provenance=_provenance(fields["provenance"]),
        policy=tuple(sorted(policy.items())),
        publication_eligible=fields["publication_eligible"],
        p1_eligible=fields["p1_eligible"],
    )
    _require(value.policy == POLICY, "unsupported preflight policy")
    _require(encode_preflight(value) == raw, "preflight JSON bytes are not canonical")
    return value


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _verify_index(retained: RetainedIndex, source_plan: SourceBytePlan):
    source = source_plan.source
    raw = retained.raw
    _require(retained.chrom == source.chrom, "retained index chromosome mismatch")
    _require(len(raw) == source.tbi.size_bytes == source_plan.receipt.received_bytes,
             "retained index size mismatch")
    _require(base64.b64encode(hashlib.md5(raw).digest()).decode("ascii") == source.tbi.md5_b64,
             "retained index MD5 mismatch")
    actual_crc = base64.b64encode(crc32c(raw).to_bytes(4, "big")).decode("ascii")
    _require(actual_crc == source.tbi.crc32c_b64, "retained index CRC32C mismatch")
    _require(_sha256(raw) == source_plan.receipt.sha256, "retained index SHA-256 mismatch")
    try:
        return parse_tbi(raw, expected_chrom=source.chrom, vcf_size_bytes=source.vcf.size_bytes)
    except ValueError as error:
        raise ValueError(f"retained index invalid for {source.chrom}") from error


def decode_reviewed_preflight(
    raw: bytes,
    *,
    manifest: WindowManifest,
    manifest_raw: bytes,
    indexes: tuple[RetainedIndex, ...],
    review: ReviewReceipt,
) -> BytePreflight:
    """Decode and fully regenerate an accepted #254 preflight without performing I/O."""
    _require(type(manifest) is WindowManifest, "manifest must be WindowManifest")
    _require(type(manifest_raw) is bytes and encode_manifest(manifest) == manifest_raw,
             "manifest bytes do not match the supplied manifest")
    _require(type(review) is ReviewReceipt, "review must be ReviewReceipt")
    manifest_sha = _sha256(manifest_raw)
    preflight_sha = _sha256(raw) if type(raw) is bytes else ""
    _require(review.manifest_sha256 == manifest_sha, "review manifest hash mismatch")
    _require(review.preflight_sha256 == preflight_sha, "review preflight hash mismatch")

    value = _decode(raw)
    _require(value.manifest_sha256 == manifest_sha, "preflight manifest hash mismatch")
    _require(value.windows_sha256 == manifest.windows_sha256, "preflight windows hash mismatch")
    _require(tuple(plan.source for plan in value.sources) == manifest.sources,
             "preflight sources do not match manifest")
    _require(value.complete is True and value.budget_status == "within_cap",
             "reviewed preflight is incomplete or over budget")
    _require(value.total_planned_bytes is not None and value.total_planned_bytes <= value.max_transfer_bytes,
             "reviewed preflight exceeds its transfer cap")
    _require(review.implementation_revision == value.provenance.source_revision,
             "review implementation revision mismatch")
    _require(review.implementation_sha256 == value.provenance.imported_source_sha256,
             "review implementation source map mismatch")

    _require(type(indexes) is tuple and all(type(item) is RetainedIndex for item in indexes),
             "indexes must be a tuple of RetainedIndex values")
    _require(tuple(item.chrom for item in indexes) == AUTOSOMES,
             "retained indexes must contain natural autosomes exactly once")
    rebuilt_sources = []
    for supplied, retained in zip(value.sources, indexes, strict=True):
        index = _verify_index(retained, supplied)
        windows = tuple(
            plan_window(index, window, source_size_bytes=supplied.source.vcf.size_bytes)
            for window in manifest.windows
            if window.chrom == supplied.source.chrom
        )
        required = fixed_vcf_ranges(
            supplied.source.vcf.size_bytes,
            header_prefix_bytes=manifest.config.header_prefix_bytes,
            eof_bytes=manifest.config.eof_bytes,
        ) + tuple(byte_range for window in windows for byte_range in window.ranges)
        ranges = merge_byte_ranges(required, source_size_bytes=supplied.source.vcf.size_bytes)
        rebuilt = SourceBytePlan(supplied.source, supplied.receipt, windows, ranges)
        _require(rebuilt == supplied, f"index-derived plan mismatch for {supplied.source.chrom}")
        rebuilt_sources.append(rebuilt)

    rebuilt = assemble_preflight(
        manifest,
        tuple(rebuilt_sources),
        manifest_sha256=manifest_sha,
        provenance=value.provenance,
    )
    _require(rebuilt == value and encode_preflight(rebuilt) == raw,
             "reviewed preflight does not match regenerated byte plan")
    return value
