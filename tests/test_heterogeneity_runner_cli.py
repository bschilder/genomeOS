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
    with cli._TimedStore.create(tmp_path / "study.sqlite3", manifest=manifest,
                                admission=admission, null=null, owner_id="fixture-owner") as store:
        start = start_record(manifest, data)
        store.start(start)
        publish(store, packet(manifest, start, data))


def test_timing_closed_stdout_preserves_pending_publication(monkeypatch):
    cli = command()
    import io
    closed = io.StringIO()
    closed.close()
    monkeypatch.setattr(cli.sys, "stdout", closed)
    cli._emit_timing({"format": "b0h_storage_interval", "version": "1"})


def test_timing_closed_both_streams_does_not_replace_pending(monkeypatch):
    cli = command()
    import io
    closed_out = io.StringIO()
    closed_err = io.StringIO()
    closed_out.close()
    closed_err.close()
    monkeypatch.setattr(cli.sys, "stdout", closed_out)
    monkeypatch.setattr(cli.sys, "stderr", closed_err)
    cli._emit_timing({"format": "b0h_storage_interval", "version": "1"})


def test_timing_serialization_error_propagates(monkeypatch):
    cli = command()
    class Broken:
        def __iter__(self):
            raise RuntimeError("serialization defect")
    with pytest.raises(TypeError):
        cli._emit_timing({"broken": Broken()})
