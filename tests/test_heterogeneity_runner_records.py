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


def _admission(records):
    digest = "a" * 64
    source = records.SourceIdentity(revision="b" * 40, content_sha256=digest,
                                    lock_sha256=digest)
    runtime = records.RuntimeIdentity(
        python_version="3.12", platform="darwin", machine="arm64",
        environment_sha256=digest, jax_version="1", cupy_version="1",
        jax_device="gpu", cupy_device="gpu", driver_version="1",
        jax_float64=True, cupy_float64=True)
    storage = records.StorageAdmission(
        database_parent="/tmp", device_id=1, mount_type="apfs",
        mount_options="rw", free_bytes=2, probe_sha256=digest,
        exclusive_lock_observed=True, rollback_observed=True,
        commit_readback_observed=True, directory_fsync_observed=True)
    return records.AdmissionReceipt(
        format="b0h_admission", version="1", source=source, runtime=runtime,
        storage=storage, observed_unix_ns=1, startup_elapsed_ns=1,
        preflight_elapsed_ns=1, device_total_bytes=2, device_free_bytes=1,
        process_peak_rss_bytes=1, memory_observation_label="observed")


def test_manifest_and_stage_case_roundtrip():
    wire = importlib.import_module("genomeos.validation.heterogeneity_runner_wire")
    records = importlib.import_module("genomeos.validation.heterogeneity_runner_records")
    from genomeos.validation.heterogeneity_codec import B0HCodecLimits
    from genomeos.validation.heterogeneity_simulation import enumerate_sbc_cases
    from genomeos.validation.sbc_ranks import RankNullReference

    admission = _admission(records)
    null = records.prepared_null(RankNullReference(512, 1653499886, (2,) * 100000))
    manifest = wire.build_manifest(admission, null, worker_id="worker",
                                   limits=B0HCodecLimits(1024, 0))
    assert len(manifest.cases) == 1938
    assert wire.read_runner_record(wire.runner_record_bytes(manifest)) == manifest
    key = records.StageKey(campaign_sha256=wire.record_digest(manifest),
                           case=enumerate_sbc_cases()[0], stage="generation",
                           attempt_id=None)
    start = records.StageStart(
        format="b0h_start", version="1", key=key, worker_id="worker",
        owner_id="owner", source=admission.source, runtime=admission.runtime,
        cdf_backend="cupy", prerequisites=(), started_unix_ns=1,
        started_monotonic_ns=1)
    assert wire.read_runner_record(wire.runner_record_bytes(start)) == start
