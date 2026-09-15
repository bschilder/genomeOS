"""Canonical B0H reporting decoder tests for design §§1–2,4."""
from __future__ import annotations

import importlib
import json
import math
import struct

import pytest
from heterogeneity_report_fixtures import synthetic_reduction

from genomeos.validation.heterogeneity_reduction import reduction_bytes


def _read(data: bytes):
    module = importlib.import_module("genomeos.validation.heterogeneity_report")
    return module.read_study_reduction(data)


def _document(data: bytes) -> dict[str, object]:
    return json.loads(data.decode("ascii"))


def _canonical(document: object) -> bytes:
    return json.dumps(
        document,
        sort_keys=True,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("ascii")


def _replace_once(data: bytes, old: bytes, new: bytes) -> bytes:
    assert data.count(old) == 1
    return data.replace(old, new)


def test_public_decoder_round_trips_all_cases_rows_and_binary64_p_values():
    expected = synthetic_reduction()
    data = reduction_bytes(expected)

    actual = _read(data)

    assert actual == expected
    assert reduction_bytes(actual) == data
    assert len(actual.cases) == 1938
    assert len(actual.ranks) == 36
    rank_document = _document(data)["ranks"][9]["test"]
    assert struct.pack(">d", actual.ranks[9].test.p_value).hex() == rank_document["p_value_bits"]
    assert (
        struct.pack(">d", actual.ranks[9].test.bonferroni_p_value).hex()
        == rank_document["bonferroni_p_value_bits"]
    )
    assert actual.rows[0].value_bits == "fff0000000000000"
    assert math.isinf(struct.unpack(">d", bytes.fromhex(actual.rows[0].value_bits))[0])
    assert actual.aggregates[1].actual_n == 0
    assert actual.aggregates[1].mean_bits is None


def test_decoder_preserves_unavailable_n511_and_n0_rank_rows():
    expected = synthetic_reduction(incomplete_ranks=True)

    actual = _read(reduction_bytes(expected))

    assert actual == expected
    assert (actual.ranks[0].actual_n, actual.ranks[0].missing_n, actual.ranks[0].test) == (511, 1, None)
    assert (actual.ranks[23].actual_n, actual.ranks[23].missing_n, actual.ranks[23].test) == (
        0,
        512,
        None,
    )


@pytest.mark.parametrize(
    "data",
    [
        b"null",
        b"[]",
        b'"b0h_reduction"',
        b"{}",
    ],
)
def test_decoder_refuses_malformed_roots(data):
    with pytest.raises(ValueError):
        _read(data)


def test_decoder_refuses_duplicate_keys_and_nonfinite_json_tokens():
    data = reduction_bytes(synthetic_reduction())
    duplicate = b'{"format":"b0h_reduction",' + data[1:]
    nonfinite = _replace_once(data, b'"planned_initial_fits":1936', b'"planned_initial_fits":NaN')

    with pytest.raises(ValueError, match="duplicate"):
        _read(duplicate)
    with pytest.raises(ValueError, match="nonfinite"):
        _read(nonfinite)


@pytest.mark.parametrize("version", ["0", "2", 1, None])
def test_decoder_refuses_wrong_versions(version):
    document = _document(reduction_bytes(synthetic_reduction()))
    document["version"] = version

    with pytest.raises(ValueError):
        _read(_canonical(document))


@pytest.mark.parametrize(
    "bits",
    [
        "",
        "0" * 15,
        "0" * 17,
        "G" * 16,
        "3FF0000000000000",
        "7ff0000000000000",
        "7ff8000000000000",
    ],
)
def test_decoder_refuses_malformed_rank_test_bit_strings(bits):
    document = _document(reduction_bytes(synthetic_reduction()))
    document["ranks"][0]["test"]["p_value_bits"] = bits

    with pytest.raises(ValueError):
        _read(_canonical(document))


def test_decoder_refuses_unknown_root_and_rank_test_fields():
    data = reduction_bytes(synthetic_reduction())
    root = _document(data)
    root["unexpected"] = "field"
    rank = _document(data)
    rank["ranks"][0]["test"]["p_value"] = 0.5

    with pytest.raises(ValueError):
        _read(_canonical(root))
    with pytest.raises(ValueError):
        _read(_canonical(rank))


def test_decoder_refuses_inconsistent_membership_rank_decisions_and_claim_reasons():
    data = reduction_bytes(synthetic_reduction())
    membership = _document(data)
    membership["cases"][0], membership["cases"][1] = membership["cases"][1], membership["cases"][0]
    role = _document(data)
    role["ranks"][0]["role"] = "other_control"
    decision = _document(data)
    decision["ranks"][0]["decision"] = "reject"
    claims = _document(data)
    claims["claim_reasons"] = ["invented_reason"]
    claims["unconditional_claim_eligible"] = False
    claims["permitted_claim"] = None

    for document in (membership, role, decision, claims):
        with pytest.raises(ValueError):
            _read(_canonical(document))


@pytest.mark.parametrize(
    "transform",
    [
        lambda data: data + b"\n",
        lambda data: json.dumps(_document(data), indent=2).encode("ascii"),
    ],
)
def test_decoder_refuses_noncanonical_bytes(transform):
    data = reduction_bytes(synthetic_reduction())

    with pytest.raises(ValueError, match="canonical"):
        _read(transform(data))


@pytest.mark.parametrize("data", ["{}", bytearray(b"{}"), memoryview(b"{}")])
def test_decoder_requires_exact_bytes(data):
    with pytest.raises(ValueError, match="exact bytes"):
        _read(data)


def test_decoder_never_calls_the_reducer_rank_test_simulator_or_runner(monkeypatch):
    report = importlib.import_module("genomeos.validation.heterogeneity_report")
    reduction = importlib.import_module("genomeos.validation.heterogeneity_reduction")
    ranks = importlib.import_module("genomeos.validation.sbc_ranks")
    simulation = importlib.import_module("genomeos.validation.heterogeneity_simulation")
    runner = importlib.import_module("genomeos.validation.heterogeneity_runner")

    def forbidden(*args, **kwargs):
        raise AssertionError("report decoding called a scientific or execution path")

    monkeypatch.setattr(reduction, "reduce_b0h_study", forbidden)
    monkeypatch.setattr(reduction, "rank_reduction", forbidden)
    monkeypatch.setattr(ranks, "test_rank_uniformity", forbidden)
    monkeypatch.setattr(ranks, "simulate_rank_null", forbidden)
    monkeypatch.setattr(simulation, "generate_sbc_case", forbidden)
    monkeypatch.setattr(runner, "execute_b0h_case", forbidden)

    data = reduction_bytes(synthetic_reduction())
    assert report.read_study_reduction(data) == synthetic_reduction()
