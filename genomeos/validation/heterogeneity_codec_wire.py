"""Canonical B0H representation primitives (design §§5,7–8,12; codec §§3,5–6).

Byte budgets bound transport size, not RSS. No science, RNG, storage or I/O.
"""

from __future__ import annotations

import hashlib
import json
import re
import struct
import sys
from dataclasses import dataclass
from typing import TypeAlias

import numpy as np

Scalar: TypeAlias = bool | int | float | str | None
JsonValue: TypeAlias = bool | str | list["JsonValue"] | dict[str, "JsonValue"] | None


class B0HCodecError(ValueError):
    """Unsupported or malformed evidence representation; never a science failure."""


def _fail(message: str) -> None:
    raise B0HCodecError(message)


def _hex(value: object, length: int | None) -> str:
    if type(value) is not str or (length is not None and len(value) != length):
        _fail("hexadecimal field has invalid type or length")
    if len(value) % 2 or re.fullmatch("[0-9a-f]*", value) is None:
        _fail("hexadecimal field is not canonical")
    return value


def scalar_node(value: Scalar) -> JsonValue:
    if value is None or type(value) is bool:
        return value
    if type(value) is int:
        return ["i", format(value, "x")]
    if type(value) is float:
        return ["f", struct.pack(">d", value).hex()]
    if type(value) is str:
        return ["s", value.encode("utf-8", "surrogatepass").hex()]
    _fail("unsupported scalar class")


def read_scalar(node: JsonValue) -> Scalar:
    if node is None or type(node) is bool:
        return node
    if type(node) is not list or len(node) != 2 or type(node[0]) is not str:
        _fail("scalar node has invalid shape")
    tag, value = node
    if tag == "i":
        if type(value) is not str or re.fullmatch("0|-?[1-9a-f][0-9a-f]*", value) is None:
            _fail("integer node is not canonical")
        return int(value, 16)
    if tag == "f":
        return struct.unpack(">d", bytes.fromhex(_hex(value, 16)))[0]
    if tag == "s":
        raw = bytes.fromhex(_hex(value, None))
        try:
            decoded = raw.decode("utf-8", "surrogatepass")
        except UnicodeDecodeError as error:
            raise B0HCodecError("string node is not valid surrogatepass UTF-8") from error
        if decoded.encode("utf-8", "surrogatepass") != raw:
            _fail("string node does not re-encode exactly")
        return decoded
    _fail("unknown scalar tag")


def _depth_preflight(data: bytes) -> None:
    depth = 0
    quoted = escaped = False
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
            if depth > 64:
                _fail("metadata exceeds depth 64")
        elif byte in (93, 125):
            depth -= 1
            if depth < 0:
                _fail("metadata has unmatched delimiters")


def _json_preflight(value: JsonValue, depth: int = 0) -> None:
    if value is None or type(value) in (bool, str):
        return
    if type(value) not in (list, dict):
        _fail("unsupported JSON value class")
    if depth >= 64:
        _fail("metadata exceeds depth 64")
    if type(value) is dict:
        if any(type(key) is not str for key in value):
            _fail("JSON object keys must be literal strings")
        children = value.values()
    else:
        children = value
    for child in children:
        _json_preflight(child, depth + 1)


def canonical_bytes(value: JsonValue, *, max_bytes: int) -> bytes:
    if type(max_bytes) is not int or max_bytes <= 0:
        _fail("metadata budget must be a positive integer")
    _json_preflight(value)
    encoder = json.JSONEncoder(ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":"))
    parts = []
    total = 0
    for text in encoder.iterencode(value):
        part = text.encode("ascii")
        if len(part) > max_bytes - total:
            _fail("metadata byte budget exceeded")
        total += len(part)
        parts.append(part)
    result = b"".join(parts)
    _depth_preflight(result)
    return result


def _pairs(values: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
    result = {}
    for name, value in values:
        if name in result:
            _fail("duplicate JSON object key")
        result[name] = value
    return result


def _no_number(value: str) -> None:
    _fail("JSON numeric literals are forbidden")


def parse_metadata(data: bytes, *, max_bytes: int) -> JsonValue:
    if type(max_bytes) is not int or max_bytes <= 0:
        _fail("metadata budget must be a positive integer")
    if type(data) is not bytes or len(data) > max_bytes:
        _fail("metadata type or actual byte budget is invalid")
    _depth_preflight(data)
    try:
        value = json.loads(
            data.decode("ascii"),
            object_pairs_hook=_pairs,
            parse_int=_no_number,
            parse_float=_no_number,
            parse_constant=_no_number,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise B0HCodecError("invalid metadata JSON") from error
    if canonical_bytes(value, max_bytes=max_bytes) != data:
        _fail("metadata JSON bytes are not canonical")
    return value


class PayloadPool:
    """One-call byte budget, collision check and exact reference accounting."""

    def __init__(self, max_bytes: int, entries: tuple[tuple[str, bytes], ...] = ()) -> None:
        if type(max_bytes) is not int or max_bytes < 0 or type(entries) is not tuple:
            _fail("invalid payload budget or entries container")
        total = 0
        previous = None
        for entry in entries:
            if type(entry) is not tuple or len(entry) != 2:
                _fail("payload entry must be a digest/bytes pair")
            digest, raw = entry
            _hex(digest, 64)
            if type(raw) is not bytes or (previous is not None and digest <= previous):
                _fail("payload entries must be bytes with strictly increasing digests")
            if len(raw) > max_bytes - total:
                _fail("payload byte budget exceeded")
            total += len(raw)
            previous = digest
        self.max_bytes = max_bytes
        self.total = total
        self.buffers: dict[str, bytes] = dict(entries)
        self.used: set[str] = set()
        for digest, raw in entries:
            if hashlib.sha256(raw).hexdigest() != digest:
                _fail("payload digest mismatch")

    def add(self, raw: bytes) -> str:
        if type(raw) is not bytes:
            _fail("payload must be immutable bytes")
        digest = hashlib.sha256(raw).hexdigest()
        if digest in self.buffers:
            if self.buffers[digest] != raw:
                _fail("payload hash collision")
        else:
            if len(raw) > self.max_bytes - self.total:
                _fail("payload byte budget exceeded")
            self.buffers[digest] = raw
            self.total += len(raw)
        return digest

    def entries(self) -> tuple[tuple[str, bytes], ...]:
        return tuple(sorted(self.buffers.items()))

    def require_complete(self) -> None:
        if self.used != set(self.buffers):
            _fail("supplied payload set differs from referenced payload set")


@dataclass(frozen=True)
class ArrayReference:
    shape: tuple[int, ...]
    nbytes: int
    sha256: str

    def node(self) -> JsonValue:
        return [
            "a",
            {
                "dtype": "<f8",
                "order": "C",
                "nbytes": scalar_node(self.nbytes),
                "sha256": self.sha256,
                "shape": ["t", [scalar_node(x) for x in self.shape]],
            },
        ]


def array_reference(array: np.ndarray, pool: PayloadPool) -> ArrayReference:
    if (
        type(array) is not np.ndarray
        or array.dtype != np.dtype(np.float64)
        or array.flags.writeable
        or not array.shape
        or 0 in array.shape
    ):
        _fail("array must be immutable native float64 with positive dimensions")
    if array.nbytes > pool.max_bytes:
        _fail("single array exceeds payload byte budget")
    raw = array.tobytes(order="C") if np.little_endian else array.byteswap().tobytes(order="C")
    digest = pool.add(raw)
    return ArrayReference(tuple(int(x) for x in array.shape), len(raw), digest)


def read_array_reference(node: JsonValue, pool: PayloadPool) -> ArrayReference:
    if type(node) is not list or len(node) != 2 or node[0] != "a":
        _fail("array node shape is invalid")
    fields = node[1]
    if type(fields) is not dict or set(fields) != {"dtype", "order", "nbytes", "sha256", "shape"}:
        _fail("array descriptor fields are invalid")
    if fields["dtype"] != "<f8" or fields["order"] != "C":
        _fail("unsupported array dtype or order")
    digest = _hex(fields["sha256"], 64)
    if digest not in pool.buffers:
        _fail("missing array payload")
    raw = pool.buffers[digest]
    nbytes = read_scalar(fields["nbytes"])
    if type(nbytes) is not int or nbytes != len(raw) or nbytes % 8:
        _fail("array byte length mismatch")
    shape_node = fields["shape"]
    if (
        type(shape_node) is not list
        or len(shape_node) != 2
        or shape_node[0] != "t"
        or type(shape_node[1]) is not list
        or not shape_node[1]
    ):
        _fail("array shape must be a nonempty tuple node")
    shape = tuple(read_scalar(x) for x in shape_node[1])
    elements = 1
    available = len(raw) // 8
    bound = min(sys.maxsize, int(np.iinfo(np.intp).max))
    for dimension in shape:
        if (
            type(dimension) is not int
            or dimension <= 0
            or dimension > bound
            or dimension > available // elements
        ):
            _fail("array shape exceeds actual payload or index bounds")
        elements *= dimension
    if elements != available:
        _fail("array shape product differs from payload length")
    pool.used.add(digest)
    return ArrayReference(shape, nbytes, digest)


def materialize_array(reference: ArrayReference, pool: PayloadPool) -> np.ndarray:
    checked = read_array_reference(reference.node(), pool)
    raw = pool.buffers[checked.sha256]
    if not np.little_endian:
        raw = np.frombuffer(raw, dtype="<u8").byteswap().tobytes()
    return np.frombuffer(raw, dtype=np.float64).reshape(checked.shape)
