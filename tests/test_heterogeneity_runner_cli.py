"""Offline command fixtures; no GPU initialization, science or cloud launch."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from heterogeneity_runner_fixtures import campaign

from genomeos.validation.heterogeneity_runner_store import PendingPublication, StoreUnavailable


def command():
    path = Path(__file__).parents[1] / "scripts/run_b0h_calibration.py"
    spec = importlib.util.spec_from_file_location("b0h_cli_fixture", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_help_is_offline(capsys):
    cli = command()
    with pytest.raises(SystemExit) as exited:
        cli.main(["--help"])
    assert exited.value.code == 0
    assert "prepare" in capsys.readouterr().out


def test_pending_publication_retries_same_packet_only(tmp_path, monkeypatch):
    cli = command()
    from heterogeneity_runner_fixtures import dataset
    from test_heterogeneity_runner_store import packet as make_packet
    from test_heterogeneity_runner_store import start_record

    manifest, admission, null = campaign(tmp_path)
    packet = make_packet(manifest, start_record(manifest, dataset()), dataset())
    pending = PendingPublication(packet, StoreUnavailable("synthetic unavailable store"))
    observed = []

    class Store:
        def publish_pending(self, received):
            observed.append(received)
            if len(observed) < 3:
                raise PendingPublication(received, StoreUnavailable("synthetic unavailable store"))

    elapsed = [0]
    monkeypatch.setattr(cli.time, "monotonic", lambda: elapsed[0])
    monkeypatch.setattr(cli.time, "sleep", lambda seconds: elapsed.__setitem__(0, elapsed[0] + seconds))
    cli.reconcile_publication(Store(), pending)
    assert observed == [packet, packet, packet]
    assert all(value is packet for value in observed)
    assert elapsed[0] == 180


def test_pending_expiry_keeps_packet_and_raises(tmp_path, monkeypatch):
    cli = command()
    from heterogeneity_runner_fixtures import dataset
    from test_heterogeneity_runner_store import packet as make_packet
    from test_heterogeneity_runner_store import start_record

    manifest, admission, null = campaign(tmp_path)
    packet = make_packet(manifest, start_record(manifest, dataset()), dataset())
    pending = PendingPublication(packet, StoreUnavailable("synthetic unavailable store"))
    observed = []

    class Store:
        def publish_pending(self, received):
            observed.append(received)
            raise PendingPublication(received, StoreUnavailable("synthetic unavailable store"))

    elapsed = [0]
    monkeypatch.setattr(cli.time, "monotonic", lambda: elapsed[0])
    monkeypatch.setattr(cli.time, "sleep", lambda seconds: elapsed.__setitem__(0, elapsed[0] + seconds))
    with pytest.raises(PendingPublication) as failed:
        cli.reconcile_publication(Store(), pending)
    assert failed.value.packet is packet
    assert elapsed[0] == 1800
    assert len(observed) == 29


def test_failed_admission_makes_no_null_or_case_call(tmp_path, monkeypatch):
    cli = command()
    observed = []

    def refused(*args, **kwargs):
        observed.append("actual-admission-boundary")
        raise ValueError("literal runtime mismatch")

    def forbidden(*args, **kwargs):
        raise AssertionError("science invoked after admission refusal")

    monkeypatch.setattr(cli, "observe_b0h_admission", refused)
    monkeypatch.setattr(cli, "simulate_rank_null", forbidden)
    monkeypatch.setattr(cli, "execute_b0h_case", forbidden)
    source_root = Path(cli.__file__).resolve().parents[1]
    assert (
        cli.main(
            [
                "admit",
                "--source-root",
                str(source_root),
                "--database-parent",
                str(tmp_path),
                "--out",
                str(tmp_path / "admission.json"),
            ]
        )
        == 2
    )
    assert observed == ["actual-admission-boundary"]
    assert not (tmp_path / "admission.json").exists()


def test_imported_entrypoints_refuse_wrong_checkout(tmp_path):
    from genomeos.validation.heterogeneity_runner_admission import require_execution_source

    with pytest.raises(ValueError, match="differs from attested source_root"):
        require_execution_source(tmp_path)


def test_command_refuses_wrong_checkout_before_admission(tmp_path, monkeypatch, capsys):
    cli = command()

    def forbidden(*args, **kwargs):
        raise AssertionError("admission/science ran for wrong command root")

    monkeypatch.setattr(cli, "observe_b0h_admission", forbidden)
    monkeypatch.setattr(cli, "simulate_rank_null", forbidden)
    monkeypatch.setattr(cli, "execute_b0h_case", forbidden)
    assert (
        cli.main(
            [
                "admit",
                "--source-root",
                str(tmp_path),
                "--database-parent",
                str(tmp_path),
                "--out",
                str(tmp_path / "admission.json"),
            ]
        )
        == 2
    )
    assert "adapter_refusal" in capsys.readouterr().err


def test_failed_null_preparation_publishes_no_campaign_and_calls_no_case(tmp_path, monkeypatch):
    from genomeos.validation.heterogeneity_runner_wire import runner_record_bytes

    cli = command()
    manifest, admission, null = campaign(tmp_path)
    admission_path = tmp_path / "admission.json"
    admission_path.write_bytes(runner_record_bytes(admission))
    observed = []
    monkeypatch.setattr(cli, "observe_b0h_admission", lambda *args: admission)

    def failed_null(**kwargs):
        observed.append(kwargs)
        raise ValueError("literal null preparation failure")

    def forbidden(*args, **kwargs):
        raise AssertionError("case science ran after failed null preparation")

    monkeypatch.setattr(cli, "simulate_rank_null", failed_null)
    monkeypatch.setattr(cli, "execute_b0h_case", forbidden)
    source_root = Path(cli.__file__).resolve().parents[1]
    assert (
        cli.main(
            [
                "prepare",
                "--source-root",
                str(source_root),
                "--admission",
                str(admission_path),
                "--null",
                str(tmp_path / "null.json"),
                "--manifest",
                str(tmp_path / "manifest.json"),
                "--worker-id",
                "worker0",
                "--max-metadata-bytes",
                "1048576",
                "--max-payload-bytes",
                "16777216",
            ]
        )
        == 2
    )
    assert observed == [{"sample_size": 512, "replicates": 100000, "seed": 1653499886}]
    assert not (tmp_path / "null.json").exists()
    assert not (tmp_path / "manifest.json").exists()
    assert not (tmp_path / "study.sqlite3").exists()


def test_timed_store_parent_methods_are_invoked(tmp_path, monkeypatch):
    cli = command()
    from heterogeneity_runner_fixtures import dataset
    from test_heterogeneity_runner_store import packet, publish, start_record

    manifest, admission, null = campaign(tmp_path)
    data = dataset()
    with cli._TimedStore.create(
        tmp_path / "study.sqlite3",
        manifest=manifest,
        admission=admission,
        null=null,
        owner_id="fixture-owner",
    ) as store:
        start = start_record(manifest, data)
        store.start(start)
        publish(store, packet(manifest, start, data))


def test_timing_closed_stdout_preserves_pending_publication(monkeypatch):
    cli = command()
    import io
    import json

    closed = io.StringIO()
    closed.close()
    monkeypatch.setattr(cli.sys, "stdout", closed)
    stderr = io.StringIO()
    monkeypatch.setattr(cli.sys, "stderr", stderr)
    sentinel = object()
    calls = []
    store = cli._TimedStore.__new__(cli._TimedStore)
    store._operation_sequence = 0
    store.owner_id = "fixture-owner"
    assert store._observe("phase", None, lambda: (calls.append(1), sentinel)[1]) is sentinel
    assert calls == [1]
    unavailable = [json.loads(line) for line in stderr.getvalue().splitlines()]
    assert unavailable and all(
        row == {"format": "b0h_timing_report_unavailable", "version": "1", "reason": "stdout_write_failed"}
        for row in unavailable
    )


def test_timing_closed_both_streams_does_not_replace_pending(monkeypatch):
    cli = command()
    import io

    closed_out = io.StringIO()
    closed_err = io.StringIO()
    closed_out.close()
    closed_err.close()
    monkeypatch.setattr(cli.sys, "stdout", closed_out)
    monkeypatch.setattr(cli.sys, "stderr", closed_err)
    sentinel = object()
    calls = []
    store = cli._TimedStore.__new__(cli._TimedStore)
    store._operation_sequence = 0
    store.owner_id = "fixture-owner"
    assert store._observe("phase", None, lambda: (calls.append(1), sentinel)[1]) is sentinel
    assert calls == [1]


def test_timing_serialization_error_propagates(monkeypatch):
    cli = command()

    class Broken:
        def __iter__(self):
            raise RuntimeError("serialization defect")

    with pytest.raises(TypeError):
        cli._emit_timing({"broken": Broken()})


@pytest.mark.parametrize("close_stderr", [False, True])
def test_timing_preserves_pending_exception_and_packet(tmp_path, monkeypatch, close_stderr):
    cli = command()
    import io

    from heterogeneity_runner_fixtures import dataset
    from test_heterogeneity_runner_store import packet, start_record

    manifest, admission, null = campaign(tmp_path)
    data = dataset()
    retained = packet(manifest, start_record(manifest, data), data)
    stdout = io.StringIO()
    stdout.close()
    monkeypatch.setattr(cli.sys, "stdout", stdout)
    if close_stderr:
        stderr = io.StringIO()
        stderr.close()
        monkeypatch.setattr(cli.sys, "stderr", stderr)
    else:
        stderr = io.StringIO()
        monkeypatch.setattr(cli.sys, "stderr", stderr)
    original = PendingPublication(retained, StoreUnavailable("synthetic"))
    calls = []

    def callback():
        calls.append(1)
        raise original

    with pytest.raises(PendingPublication) as caught:
        store = cli._TimedStore.__new__(cli._TimedStore)
        store._operation_sequence = 0
        store.owner_id = "fixture-owner"
        store._observe("phase", None, callback)
    assert caught.value is original and caught.value.packet is retained
    assert calls == [1]
    if not close_stderr:
        assert "b0h_timing_report_unavailable" in stderr.getvalue()


def collection_fixture(tmp_path):
    import json

    from genomeos.validation.heterogeneity_runner_store import LocalB0HStore

    execution = tmp_path / "execution"
    execution.mkdir()
    manifest, admission, null = campaign(execution)
    destination = tmp_path / "collection"
    with LocalB0HStore.create(
        execution / "study.sqlite3",
        manifest=manifest,
        admission=admission,
        null=null,
        owner_id="fixture-owner",
    ) as store:
        database_digest, inventory_digest = store.collect(destination)
    receipt = {
        "format": "b0h_collection",
        "version": "1",
        "database_sha256": database_digest,
        "inventory_sha256": inventory_digest,
    }
    command().frozen_file(
        destination / "collection.json",
        json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode("ascii"),
    )
    return destination, database_digest, inventory_digest, manifest, null


def test_collected_snapshot_reads_elsewhere_without_execution_authority(tmp_path, monkeypatch):
    import shutil

    import genomeos.validation.heterogeneity_runner_reader as reader_module
    from genomeos.validation.heterogeneity_reduction import reduce_b0h_study, reduction_bytes
    from genomeos.validation.heterogeneity_runner_records import restore_null
    from genomeos.validation.heterogeneity_runner_store import LocalB0HStore, StoreIntegrityError

    destination, database_digest, inventory_digest, manifest, null = collection_fixture(tmp_path)
    copied = tmp_path / "copied_elsewhere"
    shutil.copytree(destination, copied)
    before = {path.name: path.read_bytes() for path in copied.iterdir()}
    connection_modes = []
    original_connect = reader_module.sqlite3.connect

    def observed_connect(database_uri, **kwargs):
        connection_modes.append((database_uri, kwargs))
        return original_connect(database_uri, **kwargs)

    def forbidden(*args, **kwargs):
        raise AssertionError("collected reader attempted execution authority")

    monkeypatch.setattr(reader_module.sqlite3, "connect", observed_connect)
    monkeypatch.setattr(LocalB0HStore, "__enter__", forbidden)
    cli = command()
    monkeypatch.setattr(cli, "simulate_rank_null", forbidden)
    monkeypatch.setattr(cli, "execute_b0h_case", forbidden)
    snapshot = reader_module.read_collected_b0h_snapshot(
        copied, expected_database_sha256=database_digest, expected_inventory_sha256=inventory_digest
    )
    assert snapshot.manifest == manifest and snapshot.null == null
    assert tuple(case.case for case in snapshot.cases) == manifest.cases
    assert len(snapshot.cases) == 1938 and all(case.stages == () for case in snapshot.cases)
    assert connection_modes[0][0].endswith("?mode=ro")
    assert connection_modes[0][1]["uri"] is True and "immutable" not in connection_modes[0][0]
    assert {path.name: path.read_bytes() for path in copied.iterdir()} == before
    first = reduce_b0h_study(snapshot.manifest, snapshot.cases, restore_null(snapshot.null))
    second = reduce_b0h_study(snapshot.manifest, snapshot.cases, restore_null(snapshot.null))
    assert reduction_bytes(first) == reduction_bytes(second)
    with pytest.raises(StoreIntegrityError, match="filesystem differs"):
        LocalB0HStore(
            copied / "study.sqlite3",
            manifest=manifest,
            admission=campaign(tmp_path / "execution")[1],
            null=null,
            owner_id="new-owner",
        )


@pytest.mark.parametrize(
    "changed",
    ["expected_database", "expected_inventory", "receipt", "inventory", "database", "journal", "wal", "shm"],
)
def test_collected_snapshot_refuses_checksum_or_sidecar_drift(tmp_path, changed):
    from genomeos.validation.heterogeneity_runner_reader import (
        StoreIntegrityError,
        read_collected_b0h_snapshot,
    )

    destination, database_digest, inventory_digest, manifest, null = collection_fixture(tmp_path)
    if changed == "expected_database":
        database_digest = "0" * 64
    elif changed == "expected_inventory":
        inventory_digest = "0" * 64
    elif changed in ("receipt", "inventory"):
        name = "collection.json" if changed == "receipt" else "inventory.json"
        path = destination / name
        path.write_bytes(path.read_bytes() + b" ")
    elif changed == "database":
        with (destination / "study.sqlite3").open("ab") as stream:
            stream.write(b"literal corrupt trailing bytes")
    else:
        suffix = {"journal": "-journal", "wal": "-wal", "shm": "-shm"}[changed]
        (destination / ("study.sqlite3" + suffix)).write_bytes(b"")
    with pytest.raises(StoreIntegrityError):
        read_collected_b0h_snapshot(
            destination, expected_database_sha256=database_digest, expected_inventory_sha256=inventory_digest
        )


def test_command_storage_timing_is_outside_immutable_packet(tmp_path, monkeypatch, capsys):
    import json

    from heterogeneity_runner_fixtures import dataset
    from test_heterogeneity_runner_store import packet, publish, start_record

    cli = command()
    manifest, admission, null = campaign(tmp_path)
    data = dataset()
    start = start_record(manifest, data)
    retained = packet(manifest, start, data)
    elapsed = [0]
    monkeypatch.setattr(cli.time, "monotonic_ns", lambda: elapsed[0])
    with cli._TimedStore.create(
        tmp_path / "study.sqlite3",
        manifest=manifest,
        admission=admission,
        null=null,
        owner_id="fixture-owner",
    ) as store:
        original = store._commit

        def observed_commit():
            elapsed[0] += 11
            original()

        monkeypatch.setattr(store, "_commit", observed_commit)
        store.start(start)
        publish(store, retained)
        (stage,) = store.stages(data.case_id)
        assert stage.completion == retained.completion
        assert stage.completion.whole_call_elapsed_ns == 7
    reports = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    publication = [row for row in reports if row["phase"] == "result_publication"]
    assert publication[0]["elapsed_ns"] is None and publication[0]["unavailable_reason"] == "end_not_observed"
    assert publication[1]["elapsed_ns"] == 11
    assert publication[1]["interval"] == "before_begin_report_to_store_method_return_or_raise"
    assert publication[1]["outcome"] == "returned" and publication[1]["unavailable_reason"] is None
