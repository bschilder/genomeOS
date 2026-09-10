"""Runner wire contract fixtures; no realized scientific evidence."""
from __future__ import annotations

import importlib

import pytest


def test_null_requires_complete_frozen_identity():
    records = importlib.import_module(
        "genomeos.validation.heterogeneity_runner_records"
    )
    from genomeos.validation.sbc_ranks import RankNullReference

    with pytest.raises(ValueError, match="512"):
        records.prepared_null(RankNullReference(511, 1653499886, (2,) * 100000))
    with pytest.raises(ValueError, match="100000"):
        records.prepared_null(RankNullReference(512, 1653499886, (2,)))
    with pytest.raises(ValueError, match="1653499886"):
        records.prepared_null(RankNullReference(512, 1, (2,) * 100000))


def test_canonical_null_bytes_and_rejected_json():
    wire = importlib.import_module("genomeos.validation.heterogeneity_runner_wire")
    records = importlib.import_module("genomeos.validation.heterogeneity_runner_records")
    from genomeos.validation.sbc_ranks import RankNullReference

    null = records.prepared_null(RankNullReference(512, 1653499886, (2,) * 100000))
    expected = (
        b'{"entropy":[42,211,1,100,0,0,0,0,0],"format":"b0h_rank_null",'
        b'"replicates":100000,"sample_size":512,"seed":1653499886,"statistics":['
        + b",".join([b"2"] * 100000) + b'],"version":"1"}'
    )
    assert wire.runner_record_bytes(null) == expected
    assert wire.read_runner_record(expected) == null
    for invalid in (
        expected + b"\n",
        expected.replace(b'"version":"1"', b'"version":"2"'),
        expected.replace(b'"version":"1"', b'"version":"1","version":"1"'),
        expected.replace(b'"replicates":100000', b'"replicates":true'),
        expected.replace(b'"sample_size":512', b'"sample_size":512,"extra":0'),
    ):
        with pytest.raises(ValueError):
            wire.read_runner_record(invalid)


def test_operational_root_admission_precedes_caller_methods():
    wire = importlib.import_module("genomeos.validation.heterogeneity_runner_wire")
    records = importlib.import_module("genomeos.validation.heterogeneity_runner_records")
    from genomeos.validation.sbc_ranks import RankNullReference

    class Malicious:
        def model_dump(self, **kwargs):
            pytest.fail("unsupported caller method invoked")

    with pytest.raises(ValueError, match="unsupported operational root"):
        wire.runner_record_bytes(Malicious())

    class Subclass(records.PreparedNull):
        def model_dump(self, **kwargs):
            pytest.fail("subclass caller method invoked")

    null = records.prepared_null(RankNullReference(512, 1653499886, (2,) * 100000))
    subclass = Subclass(**null.model_dump())
    with pytest.raises(ValueError, match="unsupported operational root"):
        wire.runner_record_bytes(subclass)
    for changes in ({"statistics": [2] * 100000}, {"sample_size": 512.0},
                    {"entropy": (True, 211, 1, 100, 0, 0, 0, 0, 0)}):
        invalid = null.model_copy(update=changes)
        with pytest.raises(ValueError):
            wire.runner_record_bytes(invalid)
