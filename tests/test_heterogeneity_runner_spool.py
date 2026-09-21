"""Durable B0H publication-spool fixtures; no scientific calls."""

from __future__ import annotations

from dataclasses import replace

import pytest
from heterogeneity_runner_fixtures import campaign, dataset
from test_heterogeneity_runner_store import packet as make_packet
from test_heterogeneity_runner_store import start_record

from genomeos.validation.heterogeneity_runner_store import LocalB0HStore, StoreIntegrityError


def test_packet_spool_round_trips_exact_bytes_and_is_idempotent(tmp_path):
    from genomeos.validation import heterogeneity_runner_spool as subject

    execution = tmp_path / "execution"
    execution.mkdir()
    manifest, admission, null = campaign(execution)
    packet = make_packet(manifest, start_record(manifest, dataset()), dataset())
    spool = execution / "publication-spool"

    path = subject.write_publication_packet(spool, packet)
    assert subject.read_publication_packet(path, limits=manifest.limits) == packet
    assert subject.write_publication_packet(spool, packet) == path
    assert subject.publication_packets(spool, limits=manifest.limits) == (packet,)


def test_packet_spool_rejects_same_start_with_different_completion(tmp_path):
    from genomeos.validation import heterogeneity_runner_spool as subject

    execution = tmp_path / "execution"
    execution.mkdir()
    manifest, admission, null = campaign(execution)
    packet = make_packet(manifest, start_record(manifest, dataset()), dataset())
    spool = execution / "publication-spool"
    subject.write_publication_packet(spool, packet)
    changed = replace(
        packet,
        completion=packet.completion.model_copy(
            update={"whole_call_elapsed_ns": packet.completion.whole_call_elapsed_ns + 1}
        ),
    )

    with pytest.raises(StoreIntegrityError, match="conflict"):
        subject.write_publication_packet(spool, changed)


def test_packet_spool_rejects_corrupt_scientific_bytes(tmp_path):
    from genomeos.validation import heterogeneity_runner_spool as subject

    execution = tmp_path / "execution"
    execution.mkdir()
    manifest, admission, null = campaign(execution)
    packet = make_packet(manifest, start_record(manifest, dataset()), dataset())
    path = subject.write_publication_packet(
        execution / "publication-spool", packet
    )
    payload = path / "metadata.bin"
    payload.write_bytes(payload.read_bytes() + b"corrupt")

    with pytest.raises(StoreIntegrityError, match="fingerprint"):
        subject.read_publication_packet(path, limits=manifest.limits)


def test_recovered_packet_can_publish_after_owner_restart(tmp_path):
    from genomeos.validation import heterogeneity_runner_spool as subject

    manifest, admission, null = campaign(tmp_path)
    data = dataset()
    path = tmp_path / "study.sqlite3"
    with LocalB0HStore.create(
        path,
        manifest=manifest,
        admission=admission,
        null=null,
        owner_id="first-owner",
    ) as store:
        start = start_record(manifest, data, owner="first-owner")
        store.start(start)
        packet = make_packet(manifest, start, data)
        spool_path = subject.write_publication_packet(tmp_path / "publication-spool", packet)

    recovered = subject.read_publication_packet(spool_path, limits=manifest.limits)
    with LocalB0HStore(
        path,
        manifest=manifest,
        admission=admission,
        null=null,
        owner_id="replacement-owner",
    ) as store:
        store.publish_recovered(recovered)
        stage = store.stages(data.case_id)[0]
        assert stage.completion == packet.completion
        assert stage.loss is None
