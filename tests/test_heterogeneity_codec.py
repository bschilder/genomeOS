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
    all_outcomes,
    attempt_outcomes,
    dataset,
    generation_failures,
    selected,
    summary,
)

from genomeos.validation.heterogeneity_codec import (
    B0HCodecError,
    B0HCodecLimits,
    EncodedB0HEvidence,
    decode_b0h_evidence,
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
    assert statuses == {
        "ranked",
        "control_failed",
        "quantity_failed",
        "reference_failed",
        "dependence_reference_unresolved",
        "dependence_rank_order_unresolved",
        "comparison_failed",
        "rank_failed",
    }
    assert {value.stage for value in outcomes if type(value) is GenerationFailure} == {
        "truth_mean",
        "truth_rho",
        "truth_validation",
        "beta_shapes",
        "training_cluster",
        "training_population",
        "training_switch",
        "training_count",
        "heldout_cluster",
        "heldout_population",
        "heldout_switch",
        "heldout_count",
    }


def test_independent_nested_case_anchor():
    encoded = buffers(dataset())
    assert (
        b'["r","SbcCaseId",{"case_id":["i","0"],"replicate_id":["i","0"],'
        b'"study_id":["i","0"],"track_id":["i","0"]}]'
    ) in encoded.metadata
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
    value = GenerationFailure(
        prior.case_id,
        prior.provenance,
        "truth_mean",
        None,
        "invalid_rng_scalar",
        None,
        number,
        None,
        number,
        None,
        None,
    )
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


@pytest.mark.parametrize(
    "value",
    [1 << 16000, -(1 << 16000), -0.0, float("inf"), -float("inf")],
    ids=["positive-huge", "negative-huge", "signed-zero", "positive-inf", "negative-inf"],
)
def test_huge_and_signed_failure_scalars(value):
    data = dataset()
    if value == 0.0:
        failure = GenerationFailure(
            data.case_id,
            data.provenance,
            "truth_validation",
            None,
            "rounded_prior_boundary",
            None,
            value,
            0.125,
            value,
            None,
            None,
        )
    else:
        failure = GenerationFailure(
            data.case_id,
            data.provenance,
            "truth_mean",
            None,
            "invalid_rng_scalar",
            None,
            value,
            None,
            value,
            None,
            None,
        )
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
        encoded.payloads[1:],
        encoded.payloads + (encoded.payloads[0],),
        tuple(reversed(encoded.payloads)),
        ((digest, bytes([raw[0] ^ 1]) + raw[1:]),) + encoded.payloads[1:],
        tuple(sorted(encoded.payloads + ((hashlib.sha256(b"extra").hexdigest(), b"extra"),))),
    ):
        with pytest.raises(B0HCodecError):
            restored(replace(encoded, payloads=entries))


@pytest.mark.parametrize(
    "key,bad",
    [
        ("shape", ["t", [["i", "1"], ["i", "1" + "0" * 5000]]]),
        ("shape", ["t", [["i", "0"]]]),
        ("nbytes", ["i", "0"]),
        ("dtype", ">f8"),
        ("dtype", "float64"),
        ("order", "F"),
        ("sha256", "0" * 64),
        ("sha256", "A" * 64),
    ],
)
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
            next(node[2] for node in records if node[1] == "ParameterPosteriorSummary")["estimate"] = [
                "f",
                "7ff0000000000000",
            ]
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
    for bad in (
        (encoded.metadata, encoded.payloads),
        EncodedB0HEvidence(bytearray(encoded.metadata), ()),
        EncodedB0HEvidence(encoded.metadata, []),
    ):
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
    entries = tuple(
        sorted(
            (new_digest, bad_raw) if digest == old_digest else (digest, payload)
            for digest, payload in encoded.payloads
        )
    )
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
        decode_b0h_evidence(
            replace(encoded, payloads=((digest, b"12345678"),)), limits=B0HCodecLimits(2_000_000, 0)
        )


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
            (builtins, ("open",)),
            (Path, ("open", "read_bytes", "write_bytes")),
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
