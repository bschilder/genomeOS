"""Lossless B0H evidence buffers (design §§5,7–8,12; codec §§1–6).

This proves representation only: no science calls, I/O, provenance, recovery or
durability. Public constructor validation and explicit wire types both apply.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

import numpy as np

from genomeos.validation.heterogeneity_codec_contract import (
    ROOT_TYPES,
    B0HEvidence,
    RecordNode,
    check_contract_drift,
    check_record_fields,
    construct_record,
    record_fields,
)
from genomeos.validation.heterogeneity_codec_wire import (
    ArrayReference,
    B0HCodecError,
    JsonValue,
    PayloadPool,
    array_reference,
    canonical_bytes,
    materialize_array,
    parse_metadata,
    read_array_reference,
    read_scalar,
    scalar_node,
)

__all__ = [
    "B0HCodecError",
    "B0HCodecLimits",
    "B0HEvidence",
    "EncodedB0HEvidence",
    "decode_b0h_evidence",
    "encode_b0h_evidence",
]


@dataclass(frozen=True)
class B0HCodecLimits:
    max_metadata_bytes: int
    max_total_payload_bytes: int

    def __post_init__(self) -> None:
        if (
            type(self.max_metadata_bytes) is not int
            or self.max_metadata_bytes <= 0
            or type(self.max_total_payload_bytes) is not int
            or self.max_total_payload_bytes < 0
        ):
            raise B0HCodecError("limits require positive metadata and nonnegative payload integer budgets")


@dataclass(frozen=True)
class EncodedB0HEvidence:
    metadata: bytes
    payloads: tuple[tuple[str, bytes], ...]


def _limits(limits: B0HCodecLimits) -> None:
    if type(limits) is not B0HCodecLimits:
        raise B0HCodecError("limits must be an exact B0HCodecLimits")
    B0HCodecLimits(limits.max_metadata_bytes, limits.max_total_payload_bytes)


def _node(value: object, pool: PayloadPool, depth: int = 0) -> JsonValue:
    if depth > 64:
        raise B0HCodecError("evidence nesting exceeds depth 64")
    if value is None or type(value) in (bool, int, float, str):
        return scalar_node(value)
    if type(value) is tuple:
        return ["t", [_node(item, pool, depth + 1) for item in value]]
    if type(value) is np.ndarray:
        return array_reference(value, pool).node()
    tag, fields = record_fields(value)
    return ["r", tag, {name: _node(item, pool, depth + 1) for name, item in fields.items()}]


def _preflight(node: JsonValue, pool: PayloadPool, depth: int = 0) -> object:
    if depth > 64:
        raise B0HCodecError("evidence nesting exceeds depth 64")
    if node is None or type(node) is bool:
        return node
    if type(node) is not list or not node or type(node[0]) is not str:
        raise B0HCodecError("invalid scientific node")
    tag = node[0]
    if tag in ("i", "f", "s"):
        return read_scalar(node)
    if tag == "a":
        return read_array_reference(node, pool)
    if tag == "t":
        if len(node) != 2 or type(node[1]) is not list:
            raise B0HCodecError("invalid tuple node")
        return tuple(_preflight(item, pool, depth + 1) for item in node[1])
    if tag == "r":
        if len(node) != 3 or type(node[1]) is not str or type(node[2]) is not dict:
            raise B0HCodecError("invalid record node")
        fields = {name: _preflight(item, pool, depth + 1) for name, item in node[2].items()}
        return RecordNode(node[1], check_record_fields(node[1], fields))
    raise B0HCodecError("unknown scientific node tag")


def _restore(value: object, pool: PayloadPool) -> object:
    if type(value) is RecordNode:
        fields = {name: _restore(item, pool) for name, item in value.fields.items()}
        return construct_record(value.tag, fields)
    if type(value) is ArrayReference:
        return materialize_array(value, pool)
    if type(value) is tuple:
        return tuple(_restore(item, pool) for item in value)
    return value


def _checked_root(node: JsonValue, pool: PayloadPool) -> B0HEvidence:
    tree = _preflight(node, pool)
    if type(tree) is not RecordNode or tree.tag not in tuple(cls.__name__ for cls in ROOT_TYPES):
        raise B0HCodecError("unsupported evidence root")
    pool.require_complete()
    return cast(B0HEvidence, _restore(tree, pool))


def _envelope(root: JsonValue) -> JsonValue:
    return {"format": "b0h_evidence", "root": root, "version": "1"}


def _verify_reconstruction(
    value: B0HEvidence, metadata: bytes, pool: PayloadPool, limits: B0HCodecLimits
) -> None:
    checked_pool = PayloadPool(limits.max_total_payload_bytes)
    checked = canonical_bytes(_envelope(_node(value, checked_pool)), max_bytes=limits.max_metadata_bytes)
    if checked != metadata or checked_pool.entries() != pool.entries():
        raise B0HCodecError("public construction changed retained evidence")


def encode_b0h_evidence(value: B0HEvidence, *, limits: B0HCodecLimits) -> EncodedB0HEvidence:
    _limits(limits)
    if type(value) not in ROOT_TYPES:
        raise B0HCodecError("unsupported evidence root")
    check_contract_drift()
    pool = PayloadPool(limits.max_total_payload_bytes)
    node = _node(value, pool)
    metadata = canonical_bytes(_envelope(node), max_bytes=limits.max_metadata_bytes)
    reconstructed = _checked_root(node, pool)
    _verify_reconstruction(reconstructed, metadata, pool, limits)
    return EncodedB0HEvidence(metadata, pool.entries())


def decode_b0h_evidence(encoded: EncodedB0HEvidence, *, limits: B0HCodecLimits) -> B0HEvidence:
    _limits(limits)
    if type(encoded) is not EncodedB0HEvidence:
        raise B0HCodecError("encoded must be an exact EncodedB0HEvidence")
    if type(encoded.metadata) is not bytes or len(encoded.metadata) > limits.max_metadata_bytes:
        raise B0HCodecError("metadata type or byte budget is invalid")
    pool = PayloadPool(limits.max_total_payload_bytes, encoded.payloads)
    doc = parse_metadata(encoded.metadata, max_bytes=limits.max_metadata_bytes)
    if (
        type(doc) is not dict
        or set(doc) != {"format", "root", "version"}
        or doc["format"] != "b0h_evidence"
        or doc["version"] != "1"
    ):
        raise B0HCodecError("unsupported metadata envelope or version")
    check_contract_drift()
    reconstructed = _checked_root(doc["root"], pool)
    _verify_reconstruction(reconstructed, encoded.metadata, pool, limits)
    return reconstructed
