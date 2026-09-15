"""Literal codec grammar anchors; no scientific execution."""

from __future__ import annotations

import hashlib
import struct

import numpy as np
import pytest

from genomeos.validation.heterogeneity_codec_wire import (
    B0HCodecError,
    PayloadPool,
    array_reference,
    canonical_bytes,
    materialize_array,
    parse_metadata,
    read_array_reference,
    read_scalar,
    scalar_node,
)


@pytest.mark.parametrize(
    "value,expected",
    [
        (None, b"null"),
        (True, b"true"),
        (False, b"false"),
        (0, b'["i","0"]'),
        (-42, b'["i","-2a"]'),
        (2**128 - 1, b'["i","ffffffffffffffffffffffffffffffff"]'),
        (0.0, b'["f","0000000000000000"]'),
        (-0.0, b'["f","8000000000000000"]'),
        (0.5, b'["f","3fe0000000000000"]'),
        (1.0, b'["f","3ff0000000000000"]'),
        (float("inf"), b'["f","7ff0000000000000"]'),
        (-float("inf"), b'["f","fff0000000000000"]'),
        ("", b'["s",""]'),
        ("A\n", b'["s","410a"]'),
        ("é", b'["s","c3a9"]'),
        ("\x00", b'["s","00"]'),
        ("\ud800", b'["s","eda080"]'),
        ("\U00010000", b'["s","f0908080"]'),
        ("\ud800\udc00", b'["s","eda080edb080"]'),
    ],
)
def test_literal_scalar_bytes(value, expected):
    assert canonical_bytes(scalar_node(value), max_bytes=1000) == expected
    actual = read_scalar(parse_metadata(expected, max_bytes=1000))
    assert type(actual) is type(value)
    if type(value) is float:
        assert struct.pack(">d", actual) == struct.pack(">d", value)
    else:
        assert actual == value


@pytest.mark.parametrize("word", ["7ff8000000000001", "fff8000000000042", "7ff0000000000001"])
def test_nan_bits(word):
    value = struct.unpack(">d", bytes.fromhex(word))[0]
    assert scalar_node(value) == ["f", word]
    assert struct.pack(">d", read_scalar(["f", word])).hex() == word


@pytest.mark.parametrize("sign", [-1, 1])
def test_huge_integer_without_decimal_conversion(sign):
    value = sign * (1 << 16000)
    node = scalar_node(value)
    assert read_scalar(node) == value
    assert read_scalar(parse_metadata(canonical_bytes(node, max_bytes=5000), max_bytes=5000)) == value


@pytest.mark.parametrize(
    "data",
    [
        b'{"a":null,"a":null}',
        b"1",
        b"1.0",
        b"NaN",
        b"Infinity",
        b"-Infinity",
        b"null\n",
        b" null",
        b"null null",
        b"[",
        b"\xef\xbb\xbfnull",
        b'{"z":null,"a":null}',
        b'"\\/"',
        b'"\\u0041"',
        b"[" * 65 + b"null" + b"]" * 65,
    ],
)
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


@pytest.mark.parametrize(
    "node",
    [
        ["i", "-0"],
        ["i", "00"],
        ["i", "+1"],
        ["i", "A"],
        ["i", "0x1"],
        ["i", " 1"],
        ["f", "3FF0000000000000"],
        ["f", "0"],
        ["s", "C3A9"],
        ["s", "0"],
        ["s", "c080"],
        ["s", "f4908080"],
        ["s", "80"],
        ["i", "1", None],
        [],
    ],
)
def test_noncanonical_scalar_refusals(node):
    with pytest.raises(B0HCodecError):
        read_scalar(node)


def test_literal_array_bytes_shape_and_immutable_restore():
    raw = bytes.fromhex("000000000000c03f000000000000d03f000000000000e03f000000000000e83f")
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
    assert (
        hashlib.sha256(b"abc").hexdigest()
        == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
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
    node = [
        "a",
        {
            "dtype": "<f8",
            "nbytes": ["i", "3"],
            "order": "C",
            "sha256": hashlib.sha256(b"abc").hexdigest(),
            "shape": ["t", [["i", "1"]]],
        },
    ]
    with pytest.raises(B0HCodecError):
        read_array_reference(node, bad)


def test_array_layouts_and_endian_anchor():
    expected = np.array([[0.125, 0.25], [0.5, 0.75]], dtype=np.float64)
    layouts = (expected.copy(), np.asfortranarray(expected), np.repeat(expected, 2, axis=1)[:, ::2])
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
    for entries in ((entry, entry), ((entry[0], raw + b"x"),), (("A" * 64, raw),), (("0" * 64, raw),)):
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

    for value in (
        np.str_("x"),
        CustomString("x"),
        CustomInt(1),
        CustomFloat(0.5),
        np.longdouble(0.5),
        complex(0.5),
        [0.5],
        {"value": 0.5},
    ):
        with pytest.raises(B0HCodecError):
            scalar_node(value)


@pytest.mark.parametrize(
    "array", [np.ones((2, 2)), np.ones((2, 2), dtype=np.float32), np.ones((2, 2), dtype=complex), [[0.5]]]
)
def test_unsupported_arrays(array):
    with pytest.raises(B0HCodecError):
        array_reference(array, PayloadPool(100))
