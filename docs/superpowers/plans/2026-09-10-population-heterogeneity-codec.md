# B0H Lossless Evidence Codec Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve the seven B0H public outcome roots and their 35 closed record types in deterministic, strictly validated, lossless version-1 metadata and immutable array payloads.

**Architecture:** Three modules separate canonical wire primitives, the explicit record contract/public construction boundary, and buffer orchestration. Decode first parses and checks the entire tree and payload set, then constructs children before parents; encode uses that same internal restoration check without calling the public decoder. Existing scientific constructors remain authoritative.

**Tech Stack:** Existing pinned Python 3.12, NumPy and public genomeOS records; standard-library JSON, struct, hashlib, dataclasses and typing. No dependency change.

**Spec:** `docs/superpowers/specs/2026-09-10-population-heterogeneity-codec-design.md` (root-reviewed specification). Adopted plan: `docs/superpowers/plans/2026-09-10-population-heterogeneity-codec.md`.

## Global Constraints

- Root personally read and corrected this complete plan before adoption; scoped task execution is authorized.
- Source authority is `/private/tmp/genomeos-b0h-summaries.8tf98k` at `df0b71dfca1edd2c209abe8f9829cd103feaffdd`. Read its public contracts and adopted SBC/summary specs; do not inspect SDD directories.
- Representation correctness, not calibration, invocation provenance, durability or recovery, is the claim. Preserve class and normalized retained field values, exact integers, binary64 bits, ordered tuples and array axes.
- Scope excludes filesystem/environment/network/HTTP, fitting/scoring, random draws, execution identity/events, storage paths, publication protocols, locks, fsync/probes, retry admission, scheduling, reducers, CLI and resource pilots.
- Existing constructors' deterministic seed-identity expansion is validation; the codec never constructs a Generator or consumes a scientific random stream.
- No pickle/cloudpickle/eval/importlib, object hooks invoking named classes, dynamic imports, arbitrary dataclass traversal or extensible type registry.
- Both limit fields are exact Python integers, not bool; no defaults. `max_metadata_bytes` must be positive; `max_total_payload_bytes` may be zero.
- Budgets bound encoded bytes, not peak process memory: parsed trees, validation and public constructor copies require additional memory. No RSS guarantee.
- Only exact listed root classes are accepted, not their subclasses or tuples of roots. PredictiveSummaryEvidence is nested under HeterogeneityFitSummary.
- Metadata envelope is exactly `{"format":"b0h_evidence","root":NODE,"version":"1"}`. Unknown format/version is a hard refusal. No migration or extension bag.
- Parse depth ceiling is 64, enforced before JSON parsing. Metadata is canonical ASCII, with sorted keys and compact separators; no JSON numeric literals or nonfinite tokens.
- Integer grammar is `0` or `-?[1-9a-f][0-9a-f]*`. Binary64 words are exactly 16 lowercase hexadecimal digits. Scientific strings use UTF-8 surrogatepass bytes as lowercase hexadecimal.
- Runtime field introspection only checks drift of the 35 explicitly named classes; runtime annotations never determine accepted fields or node types.
- Native immutable float64 arrays only; wire bytes are C-order little-endian binary64. Strides, sharing and identity are not retained evidence.
- Payload entries are unique digest/bytes pairs in strictly increasing digest order. Deduplicate identical raw bytes even for different shapes.
- Fit dimensions are `(chains, draws, variants)`; predictions are `(draws, targets)`. Retained fits use their own config, including identity-rejected and unexpected structural returns.
- Check dimensions, index representability, lengths and complete payload identity before array materialization. No allocation may be sized solely from declared shape.
- Reconstructed arrays must refuse re-enabling their write flag. Compare fields and payloads by canonical nodes/bits, never numeric tolerance or NaN equality.
- Known representation/constructor TypeError, ValueError and OverflowError become B0HCodecError with a bounded path and chained cause. Unexpected RuntimeError, MemoryError and BaseException propagate.
- No changes to existing science modules, config, seeds, priors, thresholds, clinical gates, P1/production schemas or global promotion defaults. No new dependency or runtime installation.
- Three production modules target at most 500 logical lines each and remain below 800 lines/50 KiB. The explicit contract may exceed 500 only if measured formatting expands its 35 closed cases; document that exact cause rather than create a fourth abstraction.
- All test data below are literal constructed synthetic evidence. They are not realized sampler, scorer or reference results and make no scientific success claim.
- Advance #211/#189; close neither. Root owns issue history review, branch adoption, final stable full suite, final review and push/PR. Workers own focused tests, smoke/static/privacy checks and scoped commits.
- Use this exact prefix for every Python command in this plan: `env PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib /private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python`.

---

## Scientific contract and file ownership

The product claim is deterministic lossless representation. Acceptance is literal byte/bit anchors, every legal public state, every missing/extra field refusal, complete payload-set checking, immutable restoration and side-effect traps. The engineering interface is `encode_b0h_evidence(value, *, limits)` / `decode_b0h_evidence(encoded, *, limits)`. Assumptions are the pinned compatible constructor runtime and IEEE-754 binary64; unsupported objects, malformed states and exhausted budgets refuse. Future offline storage/reduction adapters consume these buffers; metadata hashes are not authorship or externally anchored integrity.

| Task | Owns | Public output consumed later |
| --- | --- | --- |
| 1 | `genomeos/validation/heterogeneity_codec_wire.py`, `tests/test_heterogeneity_codec_wire.py` | Scalar/JSON/array grammar; `ArrayReference`, `PayloadPool`, `B0HCodecError` |
| 2 | `genomeos/validation/heterogeneity_codec_contract.py`, `tests/test_heterogeneity_codec_contract.py` | `B0HEvidence`, `RecordNode`, closed field/type validation and explicit constructors |
| 3 | `genomeos/validation/heterogeneity_codec.py`, `tests/heterogeneity_codec_fixtures.py`, `tests/test_heterogeneity_codec.py`, `docs/research/population-heterogeneity-codec-2026-09-10.md` | Exact public buffer API and exhaustive outcome evidence |

The root adopts the corrected spec and this plan in its dedicated branch before dispatch. Existing source files, contracts, dependencies and tests are read-only inputs. No renderable product layer changes, so this unit requires no map figure.

## Task 1: Canonical wire primitives and bounded array payloads

**Files:** Create the two Task-1 paths in the ownership table.

**Interfaces:** Consumes only standard library and NumPy. Produces `JsonValue`, `Scalar`, `B0HCodecError`, `ArrayReference`, `PayloadPool`; `scalar_node(value: Scalar) -> JsonValue`, `read_scalar(node: JsonValue) -> Scalar`, `canonical_bytes(value: JsonValue, *, max_bytes: int) -> bytes`, `parse_metadata(data: bytes, *, max_bytes: int) -> JsonValue`, `array_reference(array: np.ndarray, pool: PayloadPool) -> ArrayReference`, `read_array_reference(node: JsonValue, pool: PayloadPool) -> ArrayReference`, `materialize_array(reference: ArrayReference, pool: PayloadPool) -> np.ndarray`. `ArrayReference.node()` returns the canonical descriptor node. `PayloadPool` stores validated unique buffers and used references, never I/O.

- [ ] Write `tests/test_heterogeneity_codec_wire.py`:

```python
"""Literal codec grammar anchors; no scientific execution."""

from __future__ import annotations

import hashlib
import struct

import numpy as np
import pytest

from genomeos.validation.heterogeneity_codec_wire import (
    B0HCodecError, PayloadPool, array_reference, canonical_bytes,
    materialize_array, parse_metadata, read_array_reference, read_scalar,
    scalar_node,
)


@pytest.mark.parametrize("value,expected", [
    (None, b"null"), (True, b"true"), (False, b"false"),
    (0, b'["i","0"]'), (-42, b'["i","-2a"]'),
    (2**128 - 1, b'["i","ffffffffffffffffffffffffffffffff"]'),
    (0.0, b'["f","0000000000000000"]'),
    (-0.0, b'["f","8000000000000000"]'),
    (0.5, b'["f","3fe0000000000000"]'),
    (1.0, b'["f","3ff0000000000000"]'),
    (float("inf"), b'["f","7ff0000000000000"]'),
    (-float("inf"), b'["f","fff0000000000000"]'),
    ("", b'["s",""]'), ("A\n", b'["s","410a"]'),
    ("é", b'["s","c3a9"]'), ("\x00", b'["s","00"]'),
    ("\ud800", b'["s","eda080"]'), ("\U00010000", b'["s","f0908080"]'),
    ("\ud800\udc00", b'["s","eda080edb080"]'),
])
def test_literal_scalar_bytes(value, expected):
    assert canonical_bytes(scalar_node(value), max_bytes=1000) == expected
    actual = read_scalar(parse_metadata(expected, max_bytes=1000))
    assert type(actual) is type(value)
    if type(value) is float:
        assert struct.pack(">d", actual) == struct.pack(">d", value)
    else:
        assert actual == value


@pytest.mark.parametrize("word", [
    "7ff8000000000001", "fff8000000000042", "7ff0000000000001",
])
def test_nan_bits(word):
    value = struct.unpack(">d", bytes.fromhex(word))[0]
    assert scalar_node(value) == ["f", word]
    assert struct.pack(">d", read_scalar(["f", word])).hex() == word


@pytest.mark.parametrize("sign", [-1, 1])
def test_huge_integer_without_decimal_conversion(sign):
    value = sign * (1 << 16000)
    node = scalar_node(value)
    assert read_scalar(node) == value
    assert read_scalar(parse_metadata(canonical_bytes(node, max_bytes=5000),
                                      max_bytes=5000)) == value


@pytest.mark.parametrize("data", [
    b'{"a":null,"a":null}', b"1", b"1.0", b"NaN", b"Infinity",
    b"-Infinity", b"null\n", b" null", b"null null", b"[", b"\xef\xbb\xbfnull",
    b'{"z":null,"a":null}', b'"\\/"', b'"\\u0041"',
    b"[" * 65 + b"null" + b"]" * 65,
])
def test_json_refusals(data):
    with pytest.raises(B0HCodecError):
        parse_metadata(data, max_bytes=10000)


@pytest.mark.parametrize("budget", [True, 0, -1, 1.0, "10", None])
def test_metadata_budget_types_refused_by_both_helpers(budget):
    with pytest.raises(B0HCodecError):
        canonical_bytes(None, max_bytes=budget)
    with pytest.raises(B0HCodecError):
        parse_metadata(b"null", max_bytes=budget)


def test_writer_checks_depth_and_types_before_json_recursion(monkeypatch):
    import genomeos.validation.heterogeneity_codec_wire as wire
    deep = None
    for _ in range(2000):
        deep = [deep]
    def forbidden(*args, **kwargs):
        raise AssertionError("encoder reached invalid wire input")
    monkeypatch.setattr(wire.json.JSONEncoder, "iterencode", forbidden)
    for value in (deep, 1, 0.5, {1: None}, (None,), object()):
        with pytest.raises(B0HCodecError):
            canonical_bytes(value, max_bytes=10000)


@pytest.mark.parametrize("raw", [bytearray(b"abc"), memoryview(b"abc"), "abc"])
def test_payload_pool_add_requires_immutable_bytes(raw):
    with pytest.raises(B0HCodecError):
        PayloadPool(100).add(raw)


@pytest.mark.parametrize("node", [
    ["i", "-0"], ["i", "00"], ["i", "+1"], ["i", "A"],
    ["i", "0x1"], ["i", " 1"], ["f", "3FF0000000000000"],
    ["f", "0"], ["s", "C3A9"], ["s", "0"], ["s", "c080"],
    ["s", "f4908080"], ["s", "80"], ["i", "1", None], [],
])
def test_noncanonical_scalar_refusals(node):
    with pytest.raises(B0HCodecError):
        read_scalar(node)


def test_literal_array_bytes_shape_and_immutable_restore():
    raw = bytes.fromhex(
        "000000000000c03f000000000000d03f000000000000e03f000000000000e83f"
    )
    expected = np.array([[0.125, 0.25], [0.5, 0.75]], dtype=np.float64)
    expected.setflags(write=False)
    pool = PayloadPool(32)
    reference = array_reference(expected, pool)
    assert pool.entries() == ((hashlib.sha256(raw).hexdigest(), raw),)
    assert reference.shape == (2, 2)
    assert reference.nbytes == 32
    restored = materialize_array(read_array_reference(reference.node(), pool), pool)
    assert restored.tobytes() == expected.tobytes()
    with pytest.raises(ValueError):
        restored.setflags(write=True)


def test_payload_identity_dedup_and_hash_anchor():
    assert hashlib.sha256(b"abc").hexdigest() == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )
    raw = bytes.fromhex("000000000000e03f" * 4)
    pool = PayloadPool(32)
    a = np.frombuffer(raw, dtype="<f8").astype(np.float64)
    a.setflags(write=False)
    first = array_reference(a.reshape(2, 2), pool)
    second = array_reference(a.reshape(4, 1), pool)
    assert first.sha256 == second.sha256
    assert len(pool.entries()) == 1
    bad = PayloadPool(3, ((hashlib.sha256(b"abc").hexdigest(), b"abc"),))
    node = ["a", {"dtype": "<f8", "nbytes": ["i", "3"], "order": "C",
                  "sha256": hashlib.sha256(b"abc").hexdigest(),
                  "shape": ["t", [["i", "1"]]]}]
    with pytest.raises(B0HCodecError):
        read_array_reference(node, bad)


def test_array_layouts_and_endian_anchor():
    expected = np.array([[0.125, 0.25], [0.5, 0.75]], dtype=np.float64)
    layouts = (expected.copy(), np.asfortranarray(expected),
               np.repeat(expected, 2, axis=1)[:, ::2])
    encodings = []
    for array in layouts:
        array.setflags(write=False)
        pool = PayloadPool(32)
        encodings.append((array_reference(array, pool).node(), pool.entries()))
    assert encodings[0] == encodings[1] == encodings[2]
    assert encodings[0][1][0][1][:8] == bytes.fromhex("000000000000c03f")
    wrong_endian = expected.astype(">f8" if np.little_endian else "<f8")
    wrong_endian.setflags(write=False)
    with pytest.raises(B0HCodecError):
        array_reference(wrong_endian, PayloadPool(32))


@pytest.mark.parametrize("shape", [(), (0,), (-1,), (2**200,), (2, 2**200), (True,)])
def test_shape_refusal_precedes_allocation(shape, monkeypatch):
    pool = PayloadPool(8)
    source = np.frombuffer(bytes.fromhex("000000000000e03f"), dtype=np.float64)
    node = array_reference(source, pool).node()
    node[1]["shape"] = ["t", [scalar_node(x) for x in shape]]
    def forbidden(*args, **kwargs):
        raise AssertionError("allocation before dimension validation")
    monkeypatch.setattr(np, "frombuffer", forbidden)
    with pytest.raises(B0HCodecError):
        read_array_reference(node, pool)


def test_budget_and_payload_refusals():
    with pytest.raises(B0HCodecError):
        canonical_bytes(["s", "aa" * 100], max_bytes=20)
    with pytest.raises(B0HCodecError):
        parse_metadata(b"null", max_bytes=3)
    raw = b"12345678"
    entry = (hashlib.sha256(raw).hexdigest(), raw)
    for entries in ((entry, entry), ((entry[0], raw + b"x"),),
                    (("A" * 64, raw),), (("0" * 64, raw),)):
        with pytest.raises(B0HCodecError):
            PayloadPool(100, entries)
    with pytest.raises(B0HCodecError):
        PayloadPool(7, (entry,))
    with pytest.raises(B0HCodecError):
        PayloadPool(8, (entry,)).require_complete()


def test_collision_refusal_and_each_descriptor_field(monkeypatch):
    pool = PayloadPool(16)
    class FixedDigest:
        def hexdigest(self):
            return "0" * 64
    monkeypatch.setattr(hashlib, "sha256", lambda raw: FixedDigest())
    assert pool.add(b"12345678") == "0" * 64
    with pytest.raises(B0HCodecError, match="collision"):
        pool.add(b"87654321")
    source = np.frombuffer(b"12345678", dtype=np.float64)
    node = array_reference(source, pool).node()
    for field in tuple(node[1]):
        old = node[1].pop(field)
        with pytest.raises(B0HCodecError):
            read_array_reference(node, pool)
        node[1][field] = old
    node[1]["extra"] = None
    with pytest.raises(B0HCodecError):
        read_array_reference(node, pool)


@pytest.mark.parametrize("dtype", [np.float32, complex, object, np.int64, bool])
def test_readonly_wrong_dtype_refused(dtype):
    source = np.ones((2, 2), dtype=dtype)
    source.setflags(write=False)
    with pytest.raises(B0HCodecError):
        array_reference(source, PayloadPool(100))


def test_forbidden_scalar_classes():
    class CustomString(str):
        pass
    class CustomInt(int):
        pass
    class CustomFloat(float):
        pass
    for value in (np.str_("x"), CustomString("x"), CustomInt(1), CustomFloat(0.5),
                  np.longdouble(0.5), complex(0.5), [0.5], {"value": 0.5}):
        with pytest.raises(B0HCodecError):
            scalar_node(value)


@pytest.mark.parametrize("array", [
    np.ones((2, 2)), np.ones((2, 2), dtype=np.float32),
    np.ones((2, 2), dtype=complex), [[0.5]],
])
def test_unsupported_arrays(array):
    with pytest.raises(B0HCodecError):
        array_reference(array, PayloadPool(100))
```

- [ ] RED: run the following. Expected collection failure: missing `genomeos.validation.heterogeneity_codec_wire`.

```bash
env PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib /private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python -m pytest -o addopts='' -q tests/test_heterogeneity_codec_wire.py
```

- [ ] Create `genomeos/validation/heterogeneity_codec_wire.py`:

```python
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
    encoder = json.JSONEncoder(ensure_ascii=True, allow_nan=False,
                               sort_keys=True, separators=(",", ":"))
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
        value = json.loads(data.decode("ascii"), object_pairs_hook=_pairs,
                           parse_int=_no_number, parse_float=_no_number,
                           parse_constant=_no_number)
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
        return ["a", {"dtype": "<f8", "order": "C", "nbytes": scalar_node(self.nbytes),
                      "sha256": self.sha256,
                      "shape": ["t", [scalar_node(x) for x in self.shape]]}]


def array_reference(array: np.ndarray, pool: PayloadPool) -> ArrayReference:
    if (type(array) is not np.ndarray or array.dtype != np.dtype(np.float64)
            or array.flags.writeable or not array.shape or 0 in array.shape):
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
    if (type(shape_node) is not list or len(shape_node) != 2
            or shape_node[0] != "t" or type(shape_node[1]) is not list or not shape_node[1]):
        _fail("array shape must be a nonempty tuple node")
    shape = tuple(read_scalar(x) for x in shape_node[1])
    elements = 1
    available = len(raw) // 8
    bound = min(sys.maxsize, int(np.iinfo(np.intp).max))
    for dimension in shape:
        if (type(dimension) is not int or dimension <= 0 or dimension > bound
                or dimension > available // elements):
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
```

- [ ] GREEN and mandatory smoke/static checks:

```bash
/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/ruff format genomeos/validation/heterogeneity_codec_wire.py tests/test_heterogeneity_codec_wire.py
/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/ruff check --select I --fix genomeos/validation/heterogeneity_codec_wire.py tests/test_heterogeneity_codec_wire.py
env PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib /private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python -m pytest -o addopts='' -q tests/test_heterogeneity_codec_wire.py
env PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib /private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python scripts/smoke.py
/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/ruff check genomeos/validation/heterogeneity_codec_wire.py tests/test_heterogeneity_codec_wire.py
env PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib /private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python scripts/check_module_size.py
env PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib /private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python scripts/check_private_files.py
git add genomeos/validation/heterogeneity_codec_wire.py tests/test_heterogeneity_codec_wire.py
git diff --cached --name-only
git diff --cached --check
git commit -m "feat: add canonical B0H wire primitives; advance #211 and #189"
```

Expected GREEN: focused tests and smoke pass, ruff/size/privacy exit zero. Inspect staged paths before committing; only this task's files are allowed. Report actual output, including any failures; the commands here are planned evidence only.

## Task 2: Closed record fields, types and public reconstruction

**Files:** Create `genomeos/validation/heterogeneity_codec_contract.py` and `tests/test_heterogeneity_codec_contract.py`.

**Interfaces:** Consumes public `ArrayReference`, `B0HCodecError` from Task 1 and the 35 named public record constructors. Produces `B0HEvidence`, `ROOT_TYPES`, `RecordNode(tag: str, fields: dict[str, object])`, `check_contract_drift() -> None`, `record_fields(value: object) -> tuple[str, dict[str, object]]`, `check_record_fields(tag: str, fields: dict[str, object]) -> dict[str, object]`, `construct_record(tag: str, fields: dict[str, object]) -> object`. `RecordNode` is a checked intermediate representation, never a scientific root. The checking function accepts typed child records during encoding and checked `RecordNode` children during preflight; it normalizes only permitted scalar implementations. Array fields accept only strict native immutable ndarrays or byte-validated `ArrayReference` intermediates. The orchestration module owns replacing those intermediates with arrays before construction.

- [ ] Write `tests/test_heterogeneity_codec_contract.py`:

```python
"""Closed field contracts are independent of numerical execution."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pytest

from genomeos.validation.heterogeneity_codec_contract import (
    ROOT_TYPES, RecordNode, check_contract_drift, check_record_fields,
    construct_record, record_fields,
)
from genomeos.validation.heterogeneity_codec_wire import ArrayReference, B0HCodecError
from genomeos.validation.heterogeneity_dependence import DependencePointReference
from genomeos.validation.heterogeneity_simulation_types import SbcCaseId


def test_case_contract_and_exact_fields():
    check_contract_drift()
    tag, fields = record_fields(SbcCaseId(0, 0, 0, 0))
    assert tag == "SbcCaseId"
    assert fields == dict(track_id=0, study_id=0, case_id=0, replicate_id=0)
    assert construct_record(tag, fields) == SbcCaseId(0, 0, 0, 0)
    assert len(ROOT_TYPES) == 7
    for field in fields:
        with pytest.raises(B0HCodecError):
            check_record_fields(tag, {key: value for key, value in fields.items() if key != field})
    with pytest.raises(B0HCodecError):
        check_record_fields(tag, {**fields, "new_defaulted_field": None})


@pytest.mark.parametrize("bad", [True, 0.0, "0", np.bool_(False)])
def test_bool_and_coercible_integer_fields_refused(bad):
    with pytest.raises(B0HCodecError):
        check_record_fields("SbcCaseId", dict(track_id=bad, study_id=0, case_id=0, replicate_id=0))


def test_known_numpy_values_normalize_at_declared_fields():
    fields = dict(track_id=np.int64(0), study_id=0, case_id=0, replicate_id=0)
    result = check_record_fields("SbcCaseId", fields)
    assert type(result["track_id"]) is int
    reference = DependencePointReference(
        np.float32(0.5), np.float16(0.25), ((0.0,) * 4,) * 3,
        (0.0,) * 3, np.float64(-0.0), 0.0, False,
    )
    _, normalized = record_fields(reference)
    assert type(normalized["mean"]) is float
    assert type(normalized["rho"]) is float
    for bad in (np.longdouble(0.5), complex(0.5), True, 1):
        with pytest.raises(B0HCodecError):
            check_record_fields("DependencePointReference", {**normalized, "mean": bad})


def test_exact_class_only_and_field_drift(monkeypatch):
    @dataclass(frozen=True)
    class Child(SbcCaseId):
        pass
    with pytest.raises(B0HCodecError):
        record_fields(Child(0, 0, 0, 0))
    import genomeos.validation.heterogeneity_codec_contract as contract
    original = contract.fields
    def drifted(cls):
        actual = original(cls)
        return actual[:-1] if cls is SbcCaseId else actual
    monkeypatch.setattr(contract, "fields", drifted)
    with pytest.raises(B0HCodecError, match="drift"):
        check_contract_drift()


def test_shape_context_uses_retained_fit_config():
    config = RecordNode("PopulationHeterogeneityConfig", dict(
        mean_prior_alpha=1.0, mean_prior_beta=1.0, rho_prior_alpha=1.0,
        rho_prior_beta=9.0, draws=2, tune=1, chains=4, target_accept=0.9, seed=42,
    ))
    reference = ArrayReference((4, 2, 1), 64, "0" * 64)
    fields = dict(config=config, variant_ids=("v",), mean_draws=reference,
                  rho_draws=reference, training_record_ids=("r",),
                  training_group_ids=("g",), unavailable_training_ids=(),
                  training_counts=(), diagnostics=(), divergence_count=0)
    assert check_record_fields("PopulationHeterogeneityFit", fields)["mean_draws"] == reference
    with pytest.raises(B0HCodecError, match="shape"):
        check_record_fields("PopulationHeterogeneityFit", {
            **fields, "rho_draws": ArrayReference((8, 1, 1), 64, "0" * 64),
        })


def test_validation_wraps_only_known_constructor_defects(monkeypatch):
    fields = dict(track_id=0, study_id=0, case_id=0, replicate_id=0)
    def known(self):
        raise ValueError("invalid test fixture")
    monkeypatch.setattr(SbcCaseId, "__post_init__", known)
    with pytest.raises(B0HCodecError) as caught:
        construct_record("SbcCaseId", fields)
    assert isinstance(caught.value.__cause__, ValueError)
    def unexpected(self):
        raise RuntimeError("implementation defect")
    monkeypatch.setattr(SbcCaseId, "__post_init__", unexpected)
    with pytest.raises(RuntimeError, match="implementation defect"):
        construct_record("SbcCaseId", fields)
```

- [ ] RED: expected missing `heterogeneity_codec_contract` collection error.

```bash
env PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib /private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python -m pytest -o addopts='' -q tests/test_heterogeneity_codec_contract.py
```

- [ ] Create `genomeos/validation/heterogeneity_codec_contract.py`:

```python
"""Closed B0H v1 records (design §§5,7–8,12; codec §§2,4,6).

Explicit field checks and public constructors; no inference, I/O or RNG draws.
The tuple helpers check this fixed record set, not a general type language.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass, fields
from typing import TypeAlias

import numpy as np

from genomeos.surfaces.heterogeneity_types import (
    PopulationHeterogeneityConfig, PopulationHeterogeneityFit,
    ReferenceHeterogeneityPrediction, VariantHeterogeneityDiagnostics,
    VariantTrainingCounts,
)
from genomeos.validation.heterogeneity_attempts import (
    AttemptError, FitAttemptResult, FitAttemptSpec, StructuralCheckResult,
)
from genomeos.validation.heterogeneity_codec_wire import ArrayReference, B0HCodecError
from genomeos.validation.heterogeneity_dependence import (
    DependenceComparisons, DependencePointReference, HeterogeneityDependenceReference,
)
from genomeos.validation.heterogeneity_diagnostic_seeds import DiagnosticSeedIdentity
from genomeos.validation.heterogeneity_sbc_controls import (
    DiagnosticCallError, PriorControlFailure, PriorControlResult,
)
from genomeos.validation.heterogeneity_sbc_quantity_types import (
    QuantityRankEvidence, ScalarQuantityEvidence, SelectedSbcQuantities,
)
from genomeos.validation.heterogeneity_simulation_types import (
    AllUnavailableDataset, GeneratedDataset, GenerationFailure, GenerationId,
    GenerationProvenance, HeldoutTarget, ParameterTruth, SbcCaseId, SeedIdentity,
    SharedHistory,
)
from genomeos.validation.heterogeneity_summary_types import (
    HeldoutPredictiveSummary, HeterogeneityFitSummary, ParameterPosteriorSummary,
    PredictiveSummaryEvidence,
)
from genomeos.validation.predictive import CountPredictive
from genomeos.validation.reference_counts import ReferenceCount

B0HEvidence: TypeAlias = (
    GeneratedDataset | AllUnavailableDataset | GenerationFailure | FitAttemptResult
    | StructuralCheckResult | SelectedSbcQuantities | HeterogeneityFitSummary
)
ROOT_TYPES = (GeneratedDataset, AllUnavailableDataset, GenerationFailure, FitAttemptResult,
              StructuralCheckResult, SelectedSbcQuantities, HeterogeneityFitSummary)

# Literal frozen constructor fields. No runtime field discovery populates this map.
_RECORDS = (
    (SbcCaseId, "track_id study_id case_id replicate_id"),
    (GenerationId, "track_id study_id case_id replicate_id"),
    (SeedIdentity, "entropy"),
    (ParameterTruth, "mean rho"),
    (GenerationProvenance, "generation_id seeds"),
    (SharedHistory, "cluster_frequencies candidate_frequencies uses_cluster"),
    (HeldoutTarget, "kind row latent_frequency cluster_id cluster_frequency "
     "candidate_frequency uses_cluster"),
    (GeneratedDataset, "case_id provenance truth training latent_frequencies "
     "shared_history heldouts beta_zero_draws beta_one_draws"),
    (AllUnavailableDataset, "case_id provenance training"),
    (GenerationFailure, "case_id provenance stage index reason truth sampled_mean "
     "sampled_rho offending_value exception_type exception_message"),
    (ReferenceCount, "record_id variant_id group_id region_id variant_group ac an"),
    (FitAttemptSpec, "case attempt_id seed config"),
    (AttemptError, "category exception_class message reason diagnostics divergence_count"),
    (FitAttemptResult, "spec status fit error identity_mismatches returned_type"),
    (StructuralCheckResult, "case status error fit returned_type"),
    (PopulationHeterogeneityConfig, "mean_prior_alpha mean_prior_beta rho_prior_alpha "
     "rho_prior_beta draws tune chains target_accept seed"),
    (VariantTrainingCounts, "variant_id training_observation_count training_ac training_an"),
    (VariantHeterogeneityDiagnostics, "variant_id max_rhat min_bulk_ess min_tail_ess"),
    (PopulationHeterogeneityFit, "config variant_ids mean_draws rho_draws training_record_ids "
     "training_group_ids unavailable_training_ids training_counts diagnostics divergence_count"),
    (ReferenceHeterogeneityPrediction, "marginal_predictive observation_ids unavailable_ids"),
    (CountPredictive, "mean_draws concentration cdf_backend"),
    (DiagnosticSeedIdentity, "case attempt_id purpose_id spawn_key"),
    (DiagnosticCallError, "exception_class message"),
    (PriorControlFailure, "chain parameter reason sampled_mean sampled_rho returned_type error"),
    (PriorControlResult, "seed pairs failure"),
    (DependencePointReference, "mean rho components raw_values value error_bound resolved"),
    (HeterogeneityDependenceReference, "orders analytic_separability points"),
    (DependenceComparisons, "status comparisons_by_order comparisons"),
    (ScalarQuantityEvidence, "quantity_id values error failed_training_row"),
    (QuantityRankEvidence, "mode_id quantity_id seed status rank comparisons error"),
    (SelectedSbcQuantities, "spec selected_indices selection_seeds control point_slots "
     "points scalar_quantities reference reference_error ranks"),
    (ParameterPosteriorSummary, "parameter truth estimate quantiles draw_count"),
    (HeldoutPredictiveSummary, "target log_score absolute_error squared_error coverage "
     "interval_width randomized_pit"),
    (PredictiveSummaryEvidence, "seed seed_words seed_uint128 cdf_backend draw_count "
     "targets status prediction rows error"),
    (HeterogeneityFitSummary, "spec variant_id parameters predictive"),
)


@dataclass(frozen=True)
class RecordNode:
    tag: str
    fields: dict[str, object]


def _definition(tag: str) -> tuple[type, tuple[str, ...]]:
    if type(tag) is str:
        for cls, names in _RECORDS:
            if tag == cls.__name__:
                return cls, tuple(names.split())
    raise B0HCodecError("unknown record tag")


def check_contract_drift() -> None:
    for cls, names in _RECORDS:
        expected = set(names.split())
        actual = {field.name for field in fields(cls) if field.init}
        signature = inspect.signature(cls)
        if actual != expected or set(signature.parameters) != expected:
            raise B0HCodecError(f"{cls.__name__}: constructor field drift")


def _integer(value: object) -> int:
    if type(value) is int or type(value) in (
        np.int8, np.int16, np.int32, np.int64, np.uint8, np.uint16, np.uint32, np.uint64,
        np.longlong, np.ulonglong,
    ):
        return int(value)
    raise B0HCodecError("expected a non-Boolean integer")


def _float(value: object) -> float:
    if type(value) not in (float, np.float16, np.float32, np.float64):
        raise B0HCodecError("expected a binary64-or-narrower floating scalar")
    return float(value)


def _numeric(value: object) -> float | int:
    return _float(value) if type(value) in (float, np.float16, np.float32, np.float64) else _integer(value)


def _string(value: object) -> str:
    if type(value) is not str:
        raise B0HCodecError("expected a literal string")
    return value


def _boolean(value: object) -> bool:
    if type(value) is not bool:
        raise B0HCodecError("expected a literal Boolean")
    return value


def _coverage(value: object) -> bool:
    if type(value) not in (bool, np.bool_):
        raise B0HCodecError("expected a Boolean coverage scalar")
    return bool(value)


def _tuple(value: object, check: Callable[[object], object], length: int | None = None) -> tuple:
    if type(value) is not tuple or length is not None and len(value) != length:
        raise B0HCodecError("expected an immutable tuple with the declared arity")
    return tuple(check(item) for item in value)


def _optional(value: object, check: Callable[[object], object]) -> object:
    return None if value is None else check(value)


def _record(value: object, cls: type) -> object:
    if type(value) is cls or type(value) is RecordNode and value.tag == cls.__name__:
        return value
    raise B0HCodecError(f"expected exact {cls.__name__} record")


def _array(value: object) -> object:
    if type(value) is ArrayReference:
        return value
    if (type(value) is np.ndarray and value.dtype == np.dtype(np.float64)
            and not value.flags.writeable and value.ndim and 0 not in value.shape):
        return value
    raise B0HCodecError("expected immutable native float64 array")


def _field(record: object, name: str) -> object:
    return record.fields[name] if type(record) is RecordNode else getattr(record, name)


def _shapes(tag: str, values: dict[str, object]) -> None:
    if tag == "PopulationHeterogeneityFit":
        config = values["config"]
        shape = (_field(config, "chains"), _field(config, "draws"), len(values["variant_ids"]))
        if any(values[name].shape != shape for name in ("mean_draws", "rho_draws")):
            raise B0HCodecError("fit shape differs from its retained config")
    elif tag == "CountPredictive":
        shape = values["mean_draws"].shape
        concentration = values["concentration"]
        if len(shape) != 2 or concentration is not None and concentration.shape != shape:
            raise B0HCodecError("predictive arrays require aligned two-dimensional shape")
    elif tag == "PredictiveSummaryEvidence" and values["prediction"] is not None:
        marginal = _field(values["prediction"], "marginal_predictive")
        shape = (values["draw_count"], len(values["targets"]))
        for name in ("mean_draws", "concentration"):
            array = _field(marginal, name)
            if array is None or array.shape != shape:
                raise B0HCodecError("summary prediction shape differs from draw/target axes")


def check_record_fields(tag: str, fields: dict[str, object]) -> dict[str, object]:
    _, names = _definition(tag)
    if type(fields) is not dict or any(type(key) is not str for key in fields) or set(fields) != set(names):
        raise B0HCodecError("record has missing or extra fields")
    # These accessors name a concrete field; failures retain only the known field path.
    def apply(name, check):
        try:
            return check(fields[name])
        except B0HCodecError as error:
            raise B0HCodecError(f"{tag}.{name}: invalid field representation") from error
    def i(name):
        return apply(name, _integer)
    def f(name):
        return apply(name, _float)
    def s(name):
        return apply(name, _string)
    def b(name):
        return apply(name, _boolean)
    def r(name, cls):
        return apply(name, lambda value: _record(value, cls))
    def t(name, check, length=None):
        return apply(name, lambda value: _tuple(value, check, length))
    def o(name, check):
        return apply(name, lambda value: _optional(value, check))
    def rr(cls):
        return lambda value: _record(value, cls)
    def pair(value):
        return _tuple(value, _float, 2)
    match tag:
        case "SbcCaseId" | "GenerationId":
            checked = tuple(i(name) for name in names)
        case "SeedIdentity":
            checked = (t("entropy", _integer, 9),)
        case "ParameterTruth":
            checked = (f("mean"), f("rho"))
        case "GenerationProvenance":
            checked = (r("generation_id", GenerationId), t("seeds", rr(SeedIdentity), 4))
        case "SharedHistory":
            checked = (t("cluster_frequencies", _float, 2), t("candidate_frequencies", _float, 16),
                       t("uses_cluster", _boolean, 16))
        case "HeldoutTarget":
            checked = (s("kind"), r("row", ReferenceCount), f("latent_frequency"), o("cluster_id", _integer),
                       o("cluster_frequency", _float), o("candidate_frequency", _float), o("uses_cluster", _boolean))
        case "GeneratedDataset":
            checked = (r("case_id", SbcCaseId), r("provenance", GenerationProvenance), r("truth", ParameterTruth),
                       t("training", rr(ReferenceCount), 16), t("latent_frequencies", _float, 16),
                       o("shared_history", rr(SharedHistory)), t("heldouts", rr(HeldoutTarget)),
                       i("beta_zero_draws"), i("beta_one_draws"))
        case "AllUnavailableDataset":
            checked = (r("case_id", SbcCaseId), r("provenance", GenerationProvenance), t("training", rr(ReferenceCount), 16))
        case "GenerationFailure":
            checked = (r("case_id", SbcCaseId), r("provenance", GenerationProvenance), s("stage"), o("index", _integer),
                       s("reason"), o("truth", rr(ParameterTruth)), o("sampled_mean", _numeric), o("sampled_rho", _numeric),
                       o("offending_value", _numeric), o("exception_type", _string), o("exception_message", _string))
        case "ReferenceCount":
            checked = tuple(s(name) for name in names[:5]) + (i("ac"), i("an"))
        case "FitAttemptSpec":
            checked = (r("case", SbcCaseId), i("attempt_id"), r("seed", SeedIdentity), r("config", PopulationHeterogeneityConfig))
        case "AttemptError":
            checked = (s("category"), s("exception_class"), s("message"), o("reason", _string),
                       o("diagnostics", lambda value: _tuple(value, rr(VariantHeterogeneityDiagnostics))), o("divergence_count", _integer))
        case "FitAttemptResult":
            checked = (r("spec", FitAttemptSpec), s("status"), o("fit", rr(PopulationHeterogeneityFit)),
                       o("error", rr(AttemptError)), t("identity_mismatches", _string), o("returned_type", _string))
        case "StructuralCheckResult":
            checked = (r("case", SbcCaseId), s("status"), o("error", rr(AttemptError)),
                       o("fit", rr(PopulationHeterogeneityFit)), o("returned_type", _string))
        case "PopulationHeterogeneityConfig":
            checked = tuple(f(name) for name in names[:4]) + (i("draws"), i("tune"), i("chains"), f("target_accept"), i("seed"))
        case "VariantTrainingCounts":
            checked = (s("variant_id"), i("training_observation_count"), i("training_ac"), i("training_an"))
        case "VariantHeterogeneityDiagnostics":
            checked = (s("variant_id"), f("max_rhat"), f("min_bulk_ess"), f("min_tail_ess"))
        case "PopulationHeterogeneityFit":
            checked = (r("config", PopulationHeterogeneityConfig), t("variant_ids", _string), apply("mean_draws", _array),
                       apply("rho_draws", _array), t("training_record_ids", _string), t("training_group_ids", _string),
                       t("unavailable_training_ids", _string), t("training_counts", rr(VariantTrainingCounts)),
                       t("diagnostics", rr(VariantHeterogeneityDiagnostics)), i("divergence_count"))
        case "ReferenceHeterogeneityPrediction":
            checked = (r("marginal_predictive", CountPredictive), t("observation_ids", _string), t("unavailable_ids", _string))
        case "CountPredictive":
            checked = (apply("mean_draws", _array), o("concentration", _array), s("cdf_backend"))
        case "DiagnosticSeedIdentity":
            checked = (r("case", SbcCaseId), i("attempt_id"), i("purpose_id"), t("spawn_key", _integer))
        case "DiagnosticCallError":
            checked = (s("exception_class"), s("message"))
        case "PriorControlFailure":
            checked = (i("chain"), s("parameter"), s("reason"), o("sampled_mean", _numeric), o("sampled_rho", _numeric),
                       o("returned_type", _string), o("error", rr(DiagnosticCallError)))
        case "PriorControlResult":
            checked = (r("seed", DiagnosticSeedIdentity), t("pairs", pair), o("failure", rr(PriorControlFailure)))
        case "DependencePointReference":
            checked = (f("mean"), f("rho"), t("components", lambda value: _tuple(value, _float, 4), 3),
                       t("raw_values", _float, 3), f("value"), f("error_bound"), b("resolved"))
        case "HeterogeneityDependenceReference":
            checked = (t("orders", _integer, 3), b("analytic_separability"), t("points", rr(DependencePointReference)))
        case "DependenceComparisons":
            checked = (s("status"), t("comparisons_by_order", lambda value: _tuple(value, _integer, 4), 3),
                       o("comparisons", lambda value: _tuple(value, _integer, 4)))
        case "ScalarQuantityEvidence":
            checked = (i("quantity_id"), o("values", lambda value: _tuple(value, _float)),
                       o("error", rr(DiagnosticCallError)), o("failed_training_row", _integer))
        case "QuantityRankEvidence":
            checked = (i("mode_id"), i("quantity_id"), r("seed", DiagnosticSeedIdentity), s("status"), o("rank", _integer),
                       o("comparisons", rr(DependenceComparisons)), o("error", rr(DiagnosticCallError)))
        case "SelectedSbcQuantities":
            checked = (r("spec", FitAttemptSpec), t("selected_indices", lambda value: _tuple(value, _integer, 2), 4),
                       t("selection_seeds", rr(DiagnosticSeedIdentity), 4), r("control", PriorControlResult),
                       t("point_slots", _integer), t("points", pair), t("scalar_quantities", rr(ScalarQuantityEvidence), 5),
                       o("reference", rr(HeterogeneityDependenceReference)), o("reference_error", rr(DiagnosticCallError)),
                       t("ranks", rr(QuantityRankEvidence), 18))
        case "ParameterPosteriorSummary":
            checked = (s("parameter"), f("truth"), f("estimate"), t("quantiles", _float, 7), i("draw_count"))
        case "HeldoutPredictiveSummary":
            checked = (r("target", HeldoutTarget), f("log_score"), f("absolute_error"), f("squared_error"),
                       t("coverage", _coverage, 3), t("interval_width", _float, 3), f("randomized_pit"))
        case "PredictiveSummaryEvidence":
            checked = (r("seed", DiagnosticSeedIdentity), t("seed_words", _integer, 4), i("seed_uint128"), s("cdf_backend"),
                       i("draw_count"), t("targets", rr(HeldoutTarget)), s("status"),
                       o("prediction", rr(ReferenceHeterogeneityPrediction)), t("rows", rr(HeldoutPredictiveSummary)),
                       o("error", rr(DiagnosticCallError)))
        case "HeterogeneityFitSummary":
            checked = (r("spec", FitAttemptSpec), s("variant_id"), t("parameters", rr(ParameterPosteriorSummary), 2),
                       r("predictive", PredictiveSummaryEvidence))
        case _:
            raise B0HCodecError("unknown record tag")
    result = dict(zip(names, checked, strict=True))
    _shapes(tag, result)
    return result


def record_fields(value: object) -> tuple[str, dict[str, object]]:
    for cls, names in _RECORDS:
        if type(value) is cls:
            tag = cls.__name__
            return tag, check_record_fields(tag, {name: getattr(value, name) for name in names.split()})
    raise B0HCodecError("unsupported record class")


def construct_record(tag: str, fields: dict[str, object]) -> object:
    values = check_record_fields(tag, fields)
    try:
        match tag:
            case "SbcCaseId": return SbcCaseId(**values)
            case "GenerationId": return GenerationId(**values)
            case "SeedIdentity": return SeedIdentity(**values)
            case "ParameterTruth": return ParameterTruth(**values)
            case "GenerationProvenance": return GenerationProvenance(**values)
            case "SharedHistory": return SharedHistory(**values)
            case "HeldoutTarget": return HeldoutTarget(**values)
            case "GeneratedDataset": return GeneratedDataset(**values)
            case "AllUnavailableDataset": return AllUnavailableDataset(**values)
            case "GenerationFailure": return GenerationFailure(**values)
            case "ReferenceCount": return ReferenceCount(**values)
            case "FitAttemptSpec": return FitAttemptSpec(**values)
            case "AttemptError": return AttemptError(**values)
            case "FitAttemptResult": return FitAttemptResult(**values)
            case "StructuralCheckResult": return StructuralCheckResult(**values)
            case "PopulationHeterogeneityConfig": return PopulationHeterogeneityConfig(**values)
            case "VariantTrainingCounts": return VariantTrainingCounts(**values)
            case "VariantHeterogeneityDiagnostics": return VariantHeterogeneityDiagnostics(**values)
            case "PopulationHeterogeneityFit": return PopulationHeterogeneityFit(**values)
            case "ReferenceHeterogeneityPrediction": return ReferenceHeterogeneityPrediction(**values)
            case "CountPredictive": return CountPredictive(**values)
            case "DiagnosticSeedIdentity": return DiagnosticSeedIdentity(**values)
            case "DiagnosticCallError": return DiagnosticCallError(**values)
            case "PriorControlFailure": return PriorControlFailure(**values)
            case "PriorControlResult": return PriorControlResult(**values)
            case "DependencePointReference": return DependencePointReference(**values)
            case "HeterogeneityDependenceReference": return HeterogeneityDependenceReference(**values)
            case "DependenceComparisons": return DependenceComparisons(**values)
            case "ScalarQuantityEvidence": return ScalarQuantityEvidence(**values)
            case "QuantityRankEvidence": return QuantityRankEvidence(**values)
            case "SelectedSbcQuantities": return SelectedSbcQuantities(**values)
            case "ParameterPosteriorSummary": return ParameterPosteriorSummary(**values)
            case "HeldoutPredictiveSummary": return HeldoutPredictiveSummary(**values)
            case "PredictiveSummaryEvidence": return PredictiveSummaryEvidence(**values)
            case "HeterogeneityFitSummary": return HeterogeneityFitSummary(**values)
    except (TypeError, ValueError, OverflowError) as error:
        raise B0HCodecError(f"{tag}: public constructor rejected evidence") from error
    raise B0HCodecError("unknown record tag")
```

- [ ] GREEN and mandatory smoke/static checks. Expected all listed checks pass.

```bash
/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/ruff format genomeos/validation/heterogeneity_codec_contract.py tests/test_heterogeneity_codec_contract.py
/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/ruff check --select I --fix genomeos/validation/heterogeneity_codec_contract.py tests/test_heterogeneity_codec_contract.py
env PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib /private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python -m pytest -o addopts='' -q tests/test_heterogeneity_codec_contract.py tests/test_heterogeneity_codec_wire.py
env PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib /private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python scripts/smoke.py
/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/ruff check genomeos/validation/heterogeneity_codec_contract.py tests/test_heterogeneity_codec_contract.py
env PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib /private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python scripts/check_module_size.py
env PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib /private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python scripts/check_private_files.py
git add genomeos/validation/heterogeneity_codec_contract.py tests/test_heterogeneity_codec_contract.py
git diff --cached --name-only
git diff --cached --check
git commit -m "feat: freeze B0H codec record construction; advance #211 and #189"
```

## Task 3: Public buffer codec and complete retained-outcome coverage

**Files:** Create `genomeos/validation/heterogeneity_codec.py`, `tests/heterogeneity_codec_fixtures.py`, `tests/test_heterogeneity_codec.py` and `docs/research/population-heterogeneity-codec-2026-09-10.md`. Task 1/2 files are dependencies, not worker-owned edits.

**Interfaces:** Consumes exactly the public interfaces listed in Tasks 1/2. Produces frozen `B0HCodecLimits(max_metadata_bytes: int, max_total_payload_bytes: int)` and `EncodedB0HEvidence(metadata: bytes, payloads: tuple[tuple[str, bytes], ...])`, re-exports `B0HEvidence` and `B0HCodecError`, and implements `encode_b0h_evidence(value: B0HEvidence, *, limits: B0HCodecLimits) -> EncodedB0HEvidence` / `decode_b0h_evidence(encoded: EncodedB0HEvidence, *, limits: B0HCodecLimits) -> B0HEvidence`. No public entry point invokes another public entry point.

- [ ] Create the complete literal fixture module `tests/heterogeneity_codec_fixtures.py`. Its helpers are newly defined public test helpers; they do not import private helpers from existing tests. The deterministic seed properties below expand identity, not a scientific random stream.

```python
"""Synthetic constructor-valid codec cases; no realized science is claimed."""

from __future__ import annotations

from dataclasses import replace

import numpy as np

from genomeos.surfaces.heterogeneity_types import (
    PopulationHeterogeneityConfig, PopulationHeterogeneityFit,
    ReferenceHeterogeneityPrediction, VariantHeterogeneityDiagnostics,
    VariantTrainingCounts,
)
from genomeos.validation.heterogeneity_attempts import (
    AttemptError, FitAttemptResult, FitAttemptSpec, StructuralCheckResult,
)
from genomeos.validation.heterogeneity_dependence import (
    DependenceComparisons, DependencePointReference, HeterogeneityDependenceReference,
)
from genomeos.validation.heterogeneity_diagnostic_seeds import DiagnosticSeedIdentity
from genomeos.validation.heterogeneity_sbc_controls import (
    DiagnosticCallError, PriorControlFailure, PriorControlResult,
)
from genomeos.validation.heterogeneity_sbc_quantity_types import (
    QuantityRankEvidence, ScalarQuantityEvidence, SelectedSbcQuantities,
)
from genomeos.validation.heterogeneity_simulation_types import (
    AllUnavailableDataset, GeneratedDataset, GenerationFailure, GenerationProvenance,
    HeldoutTarget, ParameterTruth, SbcCaseId, SharedHistory, fixed_simulation_truth,
    generation_id, sbc_seed_identity, simulation_reference_count, simulation_training_an,
)
from genomeos.validation.heterogeneity_summary_types import (
    HeldoutPredictiveSummary, HeterogeneityFitSummary, ParameterPosteriorSummary,
    PredictiveSummaryEvidence,
)
from genomeos.validation.predictive import CountPredictive


def provenance(case):
    return GenerationProvenance(generation_id(case), tuple(
        sbc_seed_identity(case, purpose_id=purpose, attempt_id=0) for purpose in range(4)
    ))


def dataset(study=0, case_index=0, track=0):
    case = SbcCaseId(track, study, case_index, 0)
    prov = provenance(case)
    truth = fixed_simulation_truth(case)
    if study == 0:
        truth = ParameterTruth(0.25, 0.125)
    training = tuple(simulation_reference_count(
        prov.generation_id, "train", str(index),
        an if study == 4 and case_index == 1 else 0, an,
    ) for index, an in enumerate(simulation_training_an(case)))
    if study == 3:
        return AllUnavailableDataset(case, prov, training)
    if study == 2:
        history = SharedHistory((0.125, 0.75), (0.25, 0.5) * 8, (True, False) * 8)
        latents = tuple(history.cluster_frequencies[index // 8] if use else candidate
                        for index, (use, candidate) in enumerate(zip(
                            history.uses_cluster, history.candidate_frequencies, strict=True)))
        heldouts = (
            HeldoutTarget("shared_cluster0", simulation_reference_count(
                prov.generation_id, "heldout", "shared_cluster0", 2, 20),
                0.125, 0, 0.125, 0.375, True),
            HeldoutTarget("fresh_cluster", simulation_reference_count(
                prov.generation_id, "heldout", "fresh_cluster", 17, 20),
                0.875, 2, 0.625, 0.875, False),
        )
        raw = (*history.cluster_frequencies, *history.candidate_frequencies,
               0.375, 0.625, 0.875)
    else:
        history = None
        latents = (truth.mean,) * 16 if truth.rho == 0.0 else (0.0, 1.0, 0.25, 0.75) * 4
        frequency = truth.mean if truth.rho == 0.0 else 0.375
        ac = 20 if study == 4 and case_index == 1 else 0
        heldouts = (HeldoutTarget("fresh_population", simulation_reference_count(
            prov.generation_id, "heldout", "fresh_population", ac, 20),
            frequency, None, None, None, None),)
        raw = (*latents, frequency) if truth.rho > 0 else ()
    return GeneratedDataset(case, prov, truth, training, latents, history, heldouts,
                            raw.count(0.0), raw.count(1.0))


def attempt_spec(data, attempt=0):
    seed = sbc_seed_identity(data.case_id, purpose_id=4, attempt_id=attempt)
    config = PopulationHeterogeneityConfig(
        1.0, 1.0, 1.0, 9.0 if data.case_id.track_id == 0 else 4.0,
        500 if attempt == 0 else 1000, 1000 if attempt == 0 else 2000,
        4, 0.9, seed.fit_uint32,
    )
    return FitAttemptSpec(data.case_id, attempt, seed, config)


def fitted(data, spec, *, own_draws=None, variants=1):
    config = spec.config if own_draws is None else replace(spec.config, draws=own_draws)
    variant = data.training[0].variant_id
    ids = (variant,) if variants == 1 else (variant, variant + "z")
    shape = (config.chains, config.draws, variants)
    grid = np.arange(np.prod(shape), dtype=np.float64).reshape(shape)
    mean = 0.125 + (grid % 17) / 64.0
    rho = 0.0625 + (grid % 11) / 64.0
    available = tuple(row for row in data.training if row.an > 0)
    counts = (VariantTrainingCounts(variant, len(available), 0, sum(row.an for row in available)),)
    records = tuple(sorted(row.record_id for row in data.training))
    groups = tuple(sorted(row.group_id for row in data.training))
    if variants == 2:
        records += ("z-extra-record",)
        groups += ("z-extra-group",)
        counts += (VariantTrainingCounts(ids[1], 1, 0, 20),)
    return PopulationHeterogeneityFit(
        config, ids, mean, rho, records, groups,
        tuple(sorted(row.record_id for row in data.training if row.an == 0)), counts,
        tuple(VariantHeterogeneityDiagnostics(v, 1.01, 250.0, 300.0) for v in ids), 0,
    )


def generation_failures():
    results = []
    rng_stages = (
        (0, "truth_mean", (None,)), (0, "truth_rho", (None,)),
        (2, "training_cluster", (0, 1)), (2, "training_population", tuple(range(16))),
        (2, "training_switch", tuple(range(16))), (2, "training_count", tuple(range(16))),
        (2, "heldout_cluster", (1,)), (2, "heldout_population", (0, 1)),
        (2, "heldout_switch", (0, 1)), (2, "heldout_count", (0, 1)),
        (0, "training_population", (0,)), (0, "training_count", (0,)),
        (0, "heldout_population", (0,)), (0, "heldout_count", (0,)),
    )
    for track in (0, 1):
        for study, stage, indices in rng_stages:
            data = dataset(study, track=track)
            truth_stage = stage.startswith("truth_")
            truth = None if truth_stage else data.truth
            mean = 0.25 if study == 0 and stage != "truth_mean" else None
            rho = 0.125 if study == 0 and not truth_stage else None
            for index in indices:
                for exception in ("ValueError", "FloatingPointError", "OverflowError"):
                    results.append(GenerationFailure(
                        data.case_id, data.provenance, stage, index, "rng_exception",
                        truth, mean, rho, None, exception, "",
                    ))
                for bad in (None, -1, -float("inf")):
                    results.append(GenerationFailure(
                        data.case_id, data.provenance, stage, index, "invalid_rng_scalar", truth,
                        bad if stage == "truth_mean" else mean,
                        bad if stage == "truth_rho" else rho, bad, None, None,
                    ))
        prior = dataset(track=track)
        for mean, rho in ((0.0, 0.125), (1.0, 0.125), (0.25, 0.0), (0.25, 1.0)):
            results.append(GenerationFailure(
                prior.case_id, prior.provenance, "truth_validation", None,
                "rounded_prior_boundary", None, mean, rho,
                mean if mean in (0.0, 1.0) else rho, None, None,
            ))
        for data in (prior, dataset(1, 2, track), dataset(2, track=track)):
            mean, rho = (0.25, 0.125) if data.case_id.study_id == 0 else (None, None)
            for bad in (0, -1, float("inf"), -float("inf")):
                results.append(GenerationFailure(
                    data.case_id, data.provenance, "beta_shapes", None, "invalid_beta_shapes",
                    data.truth, mean, rho, bad, None, None,
                ))
            for exception in ("ValueError", "FloatingPointError", "OverflowError"):
                results.append(GenerationFailure(
                    data.case_id, data.provenance, "beta_shapes", None, "invalid_beta_shapes",
                    data.truth, mean, rho, None, exception, "shape failure",
                ))
    return tuple(results)


def attempt_outcomes():
    results = []
    for track in (0, 1):
        data = dataset(track=track)
        for attempt in (0, 1):
            spec = attempt_spec(data, attempt)
            results.append(FitAttemptResult(spec, "accepted", fitted(data, spec), None, (), None))
            for diagnostics in ((), (VariantHeterogeneityDiagnostics("v", 1.2, 2.0, 3.0),)):
                for divergence in (None, 0, 8):
                    error = AttemptError("convergence", "builtins.RuntimeError", "", "fixture", diagnostics, divergence)
                    results.append(FitAttemptResult(spec, "convergence_failed", None, error, (), None))
            for category in ("reference_infeasible", "value", "arithmetic", "runtime", "unexpected_exception"):
                error = AttemptError(category, "builtins.ValueError", "", None, None, None)
                results.append(FitAttemptResult(spec, "failed", None, error, (), None))
            results.append(FitAttemptResult(spec, "identity_rejected", fitted(data, spec, own_draws=2, variants=2),
                                            None, ("config", "variant_ids", "mean_draws.shape", "rho_draws.shape"), None))
            results.append(FitAttemptResult(spec, "identity_rejected", None, None, ("return_type",), "builtins.dict"))
        case = dataset(3, track=track).case_id
        for status, category in (("expected_refusal", "reference_infeasible"),
                                 ("unexpected_exception", "unexpected_exception")):
            results.append(StructuralCheckResult(case, status, AttemptError(
                category, "builtins.ValueError", "", None, None, None), None, None))
        results.append(StructuralCheckResult(case, "unexpected_return", None,
                                             fitted(data, spec, own_draws=3), None))
        results.append(StructuralCheckResult(case, "unexpected_return", None, None, "builtins.list"))
    return tuple(results)


def selected(*, failure=None, failed_quantity=None, reference_status="resolved",
             rank_failure=False, attempt=0, track=0):
    data = dataset(track=track)
    spec = attempt_spec(data, attempt)
    seed = DiagnosticSeedIdentity(spec.case, attempt, 8, (1,))
    prior_pairs = ((0.625, 0.0625), (0.75, 0.125), (0.875, 0.25), (0.5, 0.375))
    control = PriorControlResult(seed, prior_pairs if failure is None else prior_pairs[:failure.chain], failure)
    correct = ((0.125, 0.25), (0.25, 0.375), (0.375, 0.5), (0.5, 0.625))
    cyclic = ((0.125, 0.625), (0.25, 0.25), (0.375, 0.375), (0.5, 0.5))
    points = ((0.25, 0.125),) + correct + (prior_pairs if failure is None else ()) + cyclic
    slots = tuple(range(13)) if failure is None else (0, 1, 2, 3, 4, 9, 10, 11, 12)
    error = DiagnosticCallError("builtins.ArithmeticError", "synthetic retained failure")
    values = (tuple(p[0] for p in points), tuple(p[1] for p in points),
              tuple(p[0] * p[1] for p in points), (-2.0,) * len(points), (-3.0,) * len(points))
    scalars = tuple(ScalarQuantityEvidence(q, None, error, 3 if q == 3 else None)
                    if q == failed_quantity else ScalarQuantityEvidence(q, value, None, None)
                    for q, value in enumerate(values))
    reference = None if reference_status == "reference_failed" else HeterogeneityDependenceReference(
        (64, 128, 256), False, tuple(DependencePointReference(
            mean, rho, ((1.0, 2.0, 3.0, 4.0),) * 3,
            (0.0, 0.0, 0.0), 0.0, 0.0, reference_status != "dependence_reference_unresolved",
        ) for mean, rho in points),
    )
    ranks = []
    for mode in range(3):
        for quantity in range(6):
            comparison = None
            call_error = None
            rank = None
            if mode == 1 and failure is not None:
                status = "control_failed"
            elif quantity == failed_quantity:
                status = "quantity_failed"
            elif quantity < 5:
                status = "rank_failed" if rank_failure else "ranked"
                rank = None if rank_failure else 2
                call_error = error if rank_failure else None
            elif reference_status in ("reference_failed", "comparison_failed"):
                status = reference_status
                call_error = error if status == "comparison_failed" else None
            else:
                unresolved = reference_status.startswith("dependence_")
                comparison = DependenceComparisons(
                    reference_status if unresolved else "resolved", ((0, 0, 0, 0),) * 3,
                    None if unresolved else (0, 0, 0, 0),
                )
                status = reference_status if unresolved else "rank_failed" if rank_failure else "ranked"
                rank = 2 if status == "ranked" else None
                call_error = error if status == "rank_failed" else None
            ranks.append(QuantityRankEvidence(mode, quantity,
                DiagnosticSeedIdentity(spec.case, attempt, 6, (mode, quantity)),
                status, rank, comparison, call_error))
    return SelectedSbcQuantities(
        spec, ((0, 0), (1, 3), (2, 6), (3, 9)),
        tuple(DiagnosticSeedIdentity(spec.case, attempt, 5, (chain,)) for chain in range(4)),
        control, slots, points, scalars, reference, error if reference is None else None, tuple(ranks),
    )


def control_failures():
    result = []
    error = DiagnosticCallError("builtins.RuntimeError", "")
    for chain in range(4):
        for parameter in ("mean", "rho"):
            for reason, bad, returned, failure_error in (
                ("rng_exception", None, None, error),
                ("invalid_scalar", -1, None, None),
                ("invalid_scalar", float("inf"), None, None),
                ("invalid_scalar", None, "builtins.list", None),
                ("rounded_boundary", 0, None, None),
                ("rounded_boundary", 1.0, None, None),
            ):
                result.append(PriorControlFailure(
                    chain, parameter, reason, bad if parameter == "mean" else 0.25,
                    bad if parameter == "rho" else None, returned, failure_error,
                ))
    return tuple(result)


def summary(study=0, case_index=0, track=0, attempt=0, backend="scipy", status="complete"):
    data = dataset(study, case_index, track)
    spec = attempt_spec(data, attempt)
    count = spec.config.chains * spec.config.draws
    seed = DiagnosticSeedIdentity(spec.case, attempt, 7, ())
    parameters = tuple(ParameterPosteriorSummary(
        parameter, truth, 0.5, (0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.875), count,
    ) for parameter, truth in (("mean", data.truth.mean), ("rho", data.truth.rho)))
    prediction = None
    if status != "prediction_failed":
        grid = np.arange(count * len(data.heldouts), dtype=np.float64).reshape(count, len(data.heldouts))
        prediction = ReferenceHeterogeneityPrediction(
            CountPredictive(0.125 + grid % 17 / 64, 2.0 + grid % 11, backend),
            tuple(target.row.record_id for target in data.heldouts), (),
        )
    rows = tuple(HeldoutPredictiveSummary(
        target, -float("inf") if index == 0 else -2.0, 0.25, 0.125,
        (False, True, True), (0.25, 0.5, 0.75), 0.25 if index == 0 else 0.875,
    ) for index, target in enumerate(data.heldouts)) if status == "complete" else ()
    predictive = PredictiveSummaryEvidence(
        seed, seed.scalar_words, seed.scalar_uint128, backend, count, data.heldouts, status,
        prediction, rows, None if status == "complete" else DiagnosticCallError("builtins.RuntimeError", ""),
    )
    return HeterogeneityFitSummary(spec, data.training[0].variant_id, parameters, predictive)


def all_outcomes():
    generated = tuple(dataset(study, index, track) for track in (0, 1)
                      for study, size in ((0, 1), (1, 24), (2, 4), (3, 1), (4, 2))
                      for index in range(size))
    quantities = tuple(selected(failure=failure) for failure in control_failures()) + tuple(
        selected(attempt=attempt, track=track, reference_status=status, rank_failure=failed)
        for attempt in (0, 1) for track in (0, 1)
        for status in ("resolved", "reference_failed", "dependence_reference_unresolved",
                       "dependence_rank_order_unresolved", "comparison_failed")
        for failed in (False, True)
    ) + (selected(failed_quantity=3), selected(failed_quantity=4))
    summaries = tuple(summary(study, 0, track, attempt, backend, status)
                      for study in (0, 1, 2, 4) for track in (0, 1) for attempt in (0, 1)
                      for backend in ("scipy", "cupy")
                      for status in ("complete", "prediction_failed", "diagnostics_failed"))
    return generated + generation_failures() + attempt_outcomes() + quantities + summaries
```

- [ ] Write `tests/test_heterogeneity_codec.py`:

```python
"""B0H codec coverage of retained states, bytes, refusals and no-science boundary."""

from __future__ import annotations

import builtins
import hashlib
import json
import socket
import struct
from dataclasses import fields, is_dataclass, replace
from pathlib import Path

import numpy as np
import pytest
from heterogeneity_codec_fixtures import (
    all_outcomes, attempt_outcomes, dataset, generation_failures, selected, summary,
)

from genomeos.validation.heterogeneity_codec import (
    B0HCodecError, B0HCodecLimits, EncodedB0HEvidence, decode_b0h_evidence,
    encode_b0h_evidence,
)
from genomeos.validation.heterogeneity_codec_contract import ROOT_TYPES
from genomeos.validation.heterogeneity_simulation_types import GenerationFailure, SbcCaseId

LIMITS = B0HCodecLimits(2_000_000, 2_000_000)


def buffers(value):
    return encode_b0h_evidence(value, limits=LIMITS)


def restored(encoded):
    return decode_b0h_evidence(encoded, limits=LIMITS)


def document(encoded):
    return json.loads(encoded.metadata)


def rewritten(encoded, doc):
    return replace(encoded, metadata=json.dumps(doc, sort_keys=True, separators=(",", ":")).encode("ascii"))


def record_nodes(node):
    if type(node) is list:
        if len(node) == 3 and node[0] == "r":
            yield node
        for child in node:
            yield from record_nodes(child)
    elif type(node) is dict:
        for child in node.values():
            yield from record_nodes(child)


def array_nodes(node):
    if type(node) is list:
        if len(node) == 2 and node[0] == "a":
            yield node
        for child in node:
            yield from array_nodes(child)
    elif type(node) is dict:
        for child in node.values():
            yield from array_nodes(child)


def assert_exact(left, right):
    assert type(left) is type(right)
    if type(left) is float:
        assert struct.pack(">d", left) == struct.pack(">d", right)
    elif type(left) is np.ndarray:
        assert left.dtype == right.dtype == np.dtype(np.float64)
        assert left.shape == right.shape
        assert left.tobytes(order="C") == right.tobytes(order="C")
        with pytest.raises(ValueError):
            right.setflags(write=True)
    elif type(left) is tuple:
        assert len(left) == len(right)
        for a, b in zip(left, right, strict=True):
            assert_exact(a, b)
    elif is_dataclass(left):
        for field in fields(left):
            assert_exact(getattr(left, field.name), getattr(right, field.name))
    else:
        assert left == right


@pytest.fixture(scope="module")
def outcomes():
    return all_outcomes()


def test_every_outcome_bits_and_byte_identity(outcomes):
    tags = set()
    statuses = set()
    for value in outcomes:
        encoded = buffers(value)
        decoded = restored(encoded)
        assert_exact(value, decoded)
        assert buffers(value) == encoded == buffers(decoded)
        tags.update(node[1] for node in record_nodes(document(encoded)))
        if type(value).__name__ == "SelectedSbcQuantities":
            statuses.update(rank.status for rank in value.ranks)
    assert {type(value) for value in outcomes} == set(ROOT_TYPES)
    assert len(tags) == 35
    assert statuses == {"ranked", "control_failed", "quantity_failed", "reference_failed",
                        "dependence_reference_unresolved", "dependence_rank_order_unresolved",
                        "comparison_failed", "rank_failed"}
    assert {value.stage for value in outcomes if type(value) is GenerationFailure} == {
        "truth_mean", "truth_rho", "truth_validation", "beta_shapes", "training_cluster",
        "training_population", "training_switch", "training_count", "heldout_cluster",
        "heldout_population", "heldout_switch", "heldout_count",
    }


def test_independent_nested_case_anchor():
    encoded = buffers(dataset())
    assert (b'["r","SbcCaseId",{"case_id":["i","0"],"replicate_id":["i","0"],'
            b'"study_id":["i","0"],"track_id":["i","0"]}]') in encoded.metadata
    assert encoded.metadata.startswith(b'{"format":"b0h_evidence","root":')
    assert encoded.metadata.endswith(b',"version":"1"}')


def test_every_record_field_is_required_and_extra_refused(outcomes):
    seen = set()
    for value in outcomes:
        encoded = buffers(value)
        doc = document(encoded)
        for record in tuple(record_nodes(doc)):
            tag = record[1]
            if tag in seen:
                continue
            seen.add(tag)
            for name in tuple(record[2]):
                old = record[2].pop(name)
                with pytest.raises(B0HCodecError):
                    restored(rewritten(encoded, doc))
                record[2][name] = old
            record[2]["extra_field"] = None
            with pytest.raises(B0HCodecError):
                restored(rewritten(encoded, doc))
            del record[2]["extra_field"]
    assert len(seen) == 35


@pytest.mark.parametrize("word", ["7ff8000000000001", "fff8000000000042", "7ff0000000000001"])
def test_nonfinite_failure_payloads_are_not_labels(word):
    number = struct.unpack(">d", bytes.fromhex(word))[0]
    prior = dataset()
    value = GenerationFailure(prior.case_id, prior.provenance, "truth_mean", None,
                              "invalid_rng_scalar", None, number, None, number, None, None)
    actual = restored(buffers(value))
    assert struct.pack(">d", actual.sampled_mean).hex() == word
    assert struct.pack(">d", actual.offending_value).hex() == word
    control = selected().control
    from genomeos.validation.heterogeneity_sbc_controls import PriorControlFailure
    failure = PriorControlFailure(0, "mean", "invalid_scalar", number, None, None, None)
    outcome = selected(failure=failure)
    actual = restored(buffers(outcome)).control.failure
    assert struct.pack(">d", actual.sampled_mean).hex() == word
    assert control.status == "complete"


@pytest.mark.parametrize("value", [1 << 16000, -(1 << 16000), -0.0, float("inf"), -float("inf")])
def test_huge_and_signed_failure_scalars(value):
    data = dataset()
    if value == 0.0:
        failure = GenerationFailure(data.case_id, data.provenance, "truth_validation", None,
            "rounded_prior_boundary", None, value, 0.125, value, None, None)
    else:
        failure = GenerationFailure(data.case_id, data.provenance, "truth_mean", None,
            "invalid_rng_scalar", None, value, None, value, None, None)
    assert_exact(failure, restored(buffers(failure)))


@pytest.mark.parametrize("message", ["", "A\n\x00é", "\ud800", "\U00010000", "\ud800\udc00"])
def test_arbitrary_exception_text(message):
    failure = next(value for value in generation_failures() if value.reason == "rng_exception")
    value = replace(failure, exception_message=message)
    assert restored(buffers(value)).exception_message == message


def test_payload_corruption_extra_missing_duplicates_and_order():
    encoded = buffers(summary(study=2))
    assert len(encoded.payloads) == 2
    digest, raw = encoded.payloads[0]
    for entries in (
        encoded.payloads[1:], encoded.payloads + (encoded.payloads[0],),
        tuple(reversed(encoded.payloads)),
        ((digest, bytes([raw[0] ^ 1]) + raw[1:]),) + encoded.payloads[1:],
        tuple(sorted(encoded.payloads + ((hashlib.sha256(b"extra").hexdigest(), b"extra"),))),
    ):
        with pytest.raises(B0HCodecError):
            restored(replace(encoded, payloads=entries))


@pytest.mark.parametrize("key,bad", [
    ("shape", ["t", [["i", "1"], ["i", "1" + "0" * 5000]]]),
    ("shape", ["t", [["i", "0"]]]), ("nbytes", ["i", "0"]),
    ("dtype", ">f8"), ("dtype", "float64"), ("order", "F"),
    ("sha256", "0" * 64), ("sha256", "A" * 64),
])
def test_array_descriptor_refusals_before_materialization(key, bad, monkeypatch):
    encoded = buffers(summary(study=2))
    doc = document(encoded)
    next(array_nodes(doc))[1][key] = bad
    import genomeos.validation.heterogeneity_codec as codec
    def forbidden(*args, **kwargs):
        raise AssertionError("materialized malformed metadata")
    monkeypatch.setattr(codec, "materialize_array", forbidden)
    with pytest.raises(B0HCodecError):
        restored(rewritten(encoded, doc))


def test_axis_alignment_and_seed_refusals():
    encoded = buffers(summary(study=2))
    for mutate in ("target_order", "seed", "words", "count", "finite", "shape"):
        doc = document(encoded)
        records = tuple(record_nodes(doc))
        predictive = next(node[2] for node in records if node[1] == "PredictiveSummaryEvidence")
        if mutate == "target_order":
            predictive["targets"][1].reverse()
        elif mutate == "seed":
            predictive["seed_uint128"] = ["i", "0"]
        elif mutate == "words":
            predictive["seed_words"][1][0] = ["i", "0"]
        elif mutate == "count":
            predictive["draw_count"] = ["i", "1"]
        elif mutate == "finite":
            next(node[2] for node in records if node[1] == "ParameterPosteriorSummary")["estimate"] = ["f", "7ff0000000000000"]
        else:
            descriptor = next(array_nodes(doc))[1]
            descriptor["shape"][1].reverse()
        with pytest.raises(B0HCodecError):
            restored(rewritten(encoded, doc))


@pytest.mark.parametrize("kind", ["version", "format", "root", "tag", "numeric", "null", "tuple", "extra"])
def test_wrong_node_positions_and_envelope(kind):
    encoded = buffers(dataset())
    doc = document(encoded)
    if kind == "version":
        doc["version"] = "2"
    elif kind == "format":
        doc["format"] = "pickle"
    elif kind == "root":
        doc["root"] = doc["root"][2]["case_id"]
    elif kind == "tag":
        doc["root"][1] = "os.system"
    elif kind == "numeric":
        doc["root"][2]["beta_zero_draws"] = 8
    elif kind == "null":
        doc["root"][2]["case_id"] = None
    elif kind == "tuple":
        doc["root"][2]["training"] = ["s", ""]
    else:
        doc["extra"] = None
    with pytest.raises(B0HCodecError):
        restored(rewritten(encoded, doc))


def test_limits_and_exact_transport_types():
    for args in ((True, 0), (0, 0), (1, -1), (1, False), (1.0, 0)):
        with pytest.raises(B0HCodecError):
            B0HCodecLimits(*args)
    encoded = buffers(dataset())
    assert encode_b0h_evidence(dataset(), limits=B0HCodecLimits(len(encoded.metadata), 0)) == encoded
    with pytest.raises(B0HCodecError):
        encode_b0h_evidence(dataset(), limits=B0HCodecLimits(len(encoded.metadata) - 1, 0))
    for bad in ((encoded.metadata, encoded.payloads),
                EncodedB0HEvidence(bytearray(encoded.metadata), ()),
                EncodedB0HEvidence(encoded.metadata, [])):
        with pytest.raises(B0HCodecError):
            restored(bad)
    for value in (SbcCaseId(0, 0, 0, 0), (dataset(),), summary().predictive):
        with pytest.raises(B0HCodecError):
            buffers(value)
    with pytest.raises(B0HCodecError):
        encode_b0h_evidence(summary(), limits=B0HCodecLimits(2_000_000, 0))


def test_no_constructor_normalization_changes_wire_evidence():
    encoded = buffers(dataset())
    doc = document(encoded)
    truth = next(node for node in record_nodes(doc) if node[1] == "ParameterTruth")
    truth[2]["mean"] = ["i", "0"]
    with pytest.raises(B0HCodecError):
        restored(rewritten(encoded, doc))


@pytest.mark.parametrize("word", ["7ff8000000000001", "7ff0000000000000"])
def test_invalid_nonfinite_summary_scores(word):
    encoded = buffers(summary())
    doc = document(encoded)
    row = next(node[2] for node in record_nodes(doc) if node[1] == "HeldoutPredictiveSummary")
    row["log_score"] = ["f", word]
    with pytest.raises(B0HCodecError):
        restored(rewritten(encoded, doc))


def test_nonfinite_array_payload_is_refused_even_with_updated_digest():
    encoded = buffers(summary())
    doc = document(encoded)
    descriptor = next(array_nodes(doc))[1]
    old_digest = descriptor["sha256"]
    raw = dict(encoded.payloads)[old_digest]
    bad_raw = bytes.fromhex("010000000000f87f") + raw[8:]
    new_digest = hashlib.sha256(bad_raw).hexdigest()
    descriptor["sha256"] = new_digest
    entries = tuple(sorted((new_digest, bad_raw) if digest == old_digest else (digest, payload)
                           for digest, payload in encoded.payloads))
    with pytest.raises(B0HCodecError):
        restored(rewritten(replace(encoded, payloads=entries), doc))


def test_changed_constructor_normalization_is_refused(monkeypatch):
    value = dataset()
    encoded = buffers(value)
    import genomeos.validation.heterogeneity_codec as codec
    original = codec.construct_record
    def changed(tag, fields):
        result = original(tag, fields)
        if tag == "GeneratedDataset":
            return replace(result, truth=replace(result.truth, mean=0.375))
        return result
    monkeypatch.setattr(codec, "construct_record", changed)
    for operation in (lambda: restored(encoded), lambda: buffers(value)):
        with pytest.raises(B0HCodecError, match="changed retained evidence"):
            operation()


def test_encoder_refuses_retained_string_subclass_and_root_subclass():
    data = dataset()
    class CustomString(str):
        pass
    row = replace(data.training[0], record_id=CustomString(data.training[0].record_id))
    value = replace(data, training=(row,) + data.training[1:])
    with pytest.raises(B0HCodecError):
        buffers(value)
    class DatasetSubclass(type(data)):
        pass
    child = DatasetSubclass(**{field.name: getattr(data, field.name) for field in fields(data)})
    with pytest.raises(B0HCodecError):
        buffers(child)


def test_depth_and_transport_refusal_before_parse(monkeypatch):
    encoded = buffers(dataset())
    import genomeos.validation.heterogeneity_codec as codec
    def forbidden(*args, **kwargs):
        raise AssertionError("parsed before actual byte-budget checks")
    monkeypatch.setattr(codec, "parse_metadata", forbidden)
    with pytest.raises(B0HCodecError):
        decode_b0h_evidence(encoded, limits=B0HCodecLimits(1, 0))
    digest = hashlib.sha256(b"12345678").hexdigest()
    with pytest.raises(B0HCodecError):
        decode_b0h_evidence(replace(encoded, payloads=((digest, b"12345678"),)),
                            limits=B0HCodecLimits(2_000_000, 0))


def test_codec_does_not_call_science_or_io(monkeypatch):
    values = (dataset(), summary(study=2), selected(), attempt_outcomes()[0])
    encoded_values = tuple(buffers(value) for value in values)
    from genomeos.validation import heterogeneity_attempts as attempts
    from genomeos.validation import heterogeneity_dependence as dependence
    from genomeos.validation import heterogeneity_sbc_controls as controls
    from genomeos.validation import predictive
    def forbidden(*args, **kwargs):
        raise AssertionError("codec called a forbidden operation")
    with monkeypatch.context() as patch:
        for owner, names in (
            (np.random, ("default_rng", "Generator", "PCG64")),
            (attempts, ("fit_reference_population_heterogeneity", "run_fit_attempt")),
            (dependence, ("heterogeneity_dependence_reference", "dependence_comparisons")),
            (controls, ("draw_prior_control",)),
            (predictive, ("predictive_diagnostics",)),
            (predictive.CountPredictive, ("log_prob", "cdf", "quantiles", "sample_counts")),
            (builtins, ("open",)), (Path, ("open", "read_bytes", "write_bytes")),
            (socket, ("socket",)),
        ):
            for name in names:
                patch.setattr(owner, name, forbidden)
        for value, encoded in zip(values, encoded_values, strict=True):
            assert buffers(value) == encoded
            assert_exact(value, restored(encoded))


@pytest.mark.parametrize("failure", [RuntimeError, MemoryError, KeyboardInterrupt, SystemExit])
def test_unexpected_errors_propagate(failure, monkeypatch):
    encoded = buffers(dataset())
    import genomeos.validation.heterogeneity_codec as codec
    def raise_failure(*args, **kwargs):
        raise failure("synthetic defect")
    monkeypatch.setattr(codec, "construct_record", raise_failure)
    with pytest.raises(failure):
        restored(encoded)
```

- [ ] RED: expected collection failure for missing `heterogeneity_codec`.

```bash
env PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib /private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python -m pytest -o addopts='' -q tests/test_heterogeneity_codec.py
```

- [ ] Create `genomeos/validation/heterogeneity_codec.py`:

```python
"""Lossless B0H evidence buffers (design §§5,7–8,12; codec §§1–6).

This proves representation only: no science calls, I/O, provenance, recovery or
durability. Public constructor validation and explicit wire types both apply.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

import numpy as np

from genomeos.validation.heterogeneity_codec_contract import (
    ROOT_TYPES, B0HEvidence, RecordNode, check_contract_drift, check_record_fields,
    construct_record, record_fields,
)
from genomeos.validation.heterogeneity_codec_wire import (
    ArrayReference, B0HCodecError, JsonValue, PayloadPool, array_reference,
    canonical_bytes, materialize_array, parse_metadata, read_array_reference,
    read_scalar, scalar_node,
)

__all__ = ["B0HCodecError", "B0HCodecLimits", "B0HEvidence", "EncodedB0HEvidence",
           "decode_b0h_evidence", "encode_b0h_evidence"]


@dataclass(frozen=True)
class B0HCodecLimits:
    max_metadata_bytes: int
    max_total_payload_bytes: int

    def __post_init__(self) -> None:
        if (type(self.max_metadata_bytes) is not int or self.max_metadata_bytes <= 0
                or type(self.max_total_payload_bytes) is not int or self.max_total_payload_bytes < 0):
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


def _verify_reconstruction(value: B0HEvidence, metadata: bytes,
                           pool: PayloadPool, limits: B0HCodecLimits) -> None:
    checked_pool = PayloadPool(limits.max_total_payload_bytes)
    checked = canonical_bytes(_envelope(_node(value, checked_pool)),
                              max_bytes=limits.max_metadata_bytes)
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
    if (type(doc) is not dict or set(doc) != {"format", "root", "version"}
            or doc["format"] != "b0h_evidence" or doc["version"] != "1"):
        raise B0HCodecError("unsupported metadata envelope or version")
    check_contract_drift()
    reconstructed = _checked_root(doc["root"], pool)
    _verify_reconstruction(reconstructed, encoded.metadata, pool, limits)
    return reconstructed
```

- [ ] GREEN plus mandatory checks. Run ruff formatting and import-only fixes before the read-only lint gate; inspect those mechanical diffs. Expected focused tests and every listed check pass. Do not edit scientific thresholds to satisfy any test.

```bash
/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/ruff format genomeos/validation/heterogeneity_codec.py tests/heterogeneity_codec_fixtures.py tests/test_heterogeneity_codec.py
/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/ruff check --select I --fix genomeos/validation/heterogeneity_codec.py tests/heterogeneity_codec_fixtures.py tests/test_heterogeneity_codec.py
env PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib /private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python -m pytest -o addopts='' -q tests/test_heterogeneity_codec.py tests/test_heterogeneity_codec_wire.py tests/test_heterogeneity_codec_contract.py tests/test_heterogeneity_summaries.py tests/test_heterogeneity_sbc_quantities.py tests/test_heterogeneity_attempts.py tests/test_heterogeneity_simulation.py
env PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib /private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python scripts/smoke.py
/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/ruff check .
env PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib /private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python scripts/freeze_contract.py --check
env PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib /private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python scripts/check_module_size.py
```

- [ ] Create `docs/research/population-heterogeneity-codec-2026-09-10.md` with the following content, then append the literal commands and their actual outputs from the completed gates in this task. Do not pre-populate a passing count or claim a gate ran when it did not.

```markdown
# B0H codec evidence — 2026-09-10

The codec represents seven existing outcome roots using 35 closed records,
canonical version-1 metadata and SHA-256-keyed little-endian float64 payloads.
It advances #211/#189 without completing either issue. The design authority is
the population-heterogeneity codec specification, implementing Atlas §§5,7–8,12.

The acceptance fixtures are literal constructor-valid synthetic records.
Their fitted arrays, diagnostic numbers, reference components, comparison
matrices and ranks are representation fixtures, not realized scientific output.
No NUTS, scoring, reference integration, RNG draw or real-data operation is part
of codec verification. Deterministic seed identity expansion is retained public
validation and does not establish RNG consumption.

Tests require exact field types/values, binary64 bit patterns, array axes,
immutable reconstructed arrays and repeatable canonical bytes. Independent
anchors include signed zero, infinities, distinct NaN payloads, surrogatepass
strings, arbitrary-size integers, literal case metadata and raw array bytes.
Missing/extra fields, malformed nodes, canonicalization defects, budgets and
payload identity errors refuse. Existing scientific constructors remain the
authority for valid scientific record states.

Byte budgets do not bound peak RSS. Metadata is canonical but is not externally
authenticated: self-consistent replacement cannot be detected without an
external metadata anchor. Constructor/runtime compatibility requires a pinned
compatible implementation. The codec establishes no fit/dataset provenance,
calibration, durability, recovery, publication eligibility or full-study result.

## Executed verification

Only commands actually run and their captured results are recorded below.
```

- [ ] Inspect and commit only owned paths after privacy and staged-path checks:

```bash
env PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib /private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python scripts/check_private_files.py
git add genomeos/validation/heterogeneity_codec.py tests/heterogeneity_codec_fixtures.py tests/test_heterogeneity_codec.py docs/research/population-heterogeneity-codec-2026-09-10.md
git diff --cached --name-only
git diff --cached --check
git commit -m "feat: round-trip B0H evidence buffers; advance #211 and #189"
```

## Root adoption and final handoff

- [ ] Personally read the corrected spec and this entire draft. Check coverage, absence of incomplete implementation steps, type names, actual public imports, interface agreement and scope. Root may correct the neutral draft before adoption; this drafter claims no adoption or execution evidence.
- [ ] Search open and closed issue history for #211/#189 and codec work before writing repository files. Adopt only under the future spec/plan paths above on a dedicated branch, through a PR.
- [ ] After all implementation tasks and reviews stabilize, run the final full-suite gate once on that stable tree; broaden/repeat only for new code changes, failures or unresolved concerns.

```bash
env PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib /private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python -m pytest -o addopts='' -q
```

- [ ] Record actual final evidence, retain existing science gates, run privacy before push, and open the coherent codec PR advancing #211/#189. Worker commits deliberately use “advance” because codecs alone complete neither parent issue. Root owns review, push and PR; no worker cloud/pilot/full-study action is authorized by this plan.
