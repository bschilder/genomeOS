"""Reference-comparison scheduling fixtures; no model fitting or GPU use."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def _command():
    path = Path(__file__).parents[1] / "scripts/run_reference_comparison_shard.py"
    spec = importlib.util.spec_from_file_location("reference_shard_fixture", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _documents(
    tmp_path: Path,
    statuses: tuple[int, ...],
    delays: tuple[float, ...] | None = None,
):
    delays = (0.1,) * len(statuses) if delays is None else delays
    if len(delays) != len(statuses):
        raise ValueError("fixture delays must match statuses")
    runs = []
    for index, (status, delay) in enumerate(zip(statuses, delays, strict=True)):
        run_id = f"run-{index}"
        runs.append(
            {
                "run_id": run_id,
                "executed": False,
                "execution_argv": (
                    sys.executable,
                    "-c",
                    f"import time; time.sleep({delay!r}); raise SystemExit({status})",
                    "--out",
                    str(tmp_path / "runs" / run_id),
                ),
                "expected_outputs": ["manifest.json"],
            }
        )
    admission = {
        "format": "b0h-comparison-admission",
        "version": "fixture-v1",
        "status": "admitted_not_executed",
        "source_sha": "a" * 40,
        "source_files": {},
        "input_files": {},
        "calibration": {"fixture": True},
        "shards": [],
    }
    shard = {
        "format": "b0h-comparison-shard",
        "version": "fixture-v1",
        "status": "admitted_not_executed",
        "source_sha": "a" * 40,
        "calibration": {"fixture": True},
        "seed": 42,
        "runs": runs,
    }
    admission_path = tmp_path / "admission.json"
    shard_path = tmp_path / "shard.json"
    admission_path.write_text(json.dumps(admission))
    shard_path.write_text(json.dumps(shard))
    return admission_path, shard_path, admission, shard


def test_execute_uses_bounded_scheduler_and_preserves_plan_order(tmp_path, monkeypatch):
    subject = _command()
    admission_path, shard_path, admission, shard = _documents(tmp_path, (0, 0, 0, 0))
    monkeypatch.setattr(subject, "verify_admission_shard", lambda *args: (admission, shard))
    monkeypatch.setattr(subject, "verify_source", lambda *args: None)
    monkeypatch.setattr(subject, "verify_inputs", lambda *args: None)
    monkeypatch.setattr(subject, "verify_hardware_attestation", lambda *args: {"sha256": "b" * 64})
    monkeypatch.setattr(
        subject,
        "verify_publication",
        lambda output, *, run, **kwargs: {
            "run_id": run["run_id"],
            "exit_status": 0,
            "comparison_complete": True,
            "manifest_sha256": "c" * 64,
            "output_files": {"manifest.json": {"sha256": "d" * 64, "size_bytes": 1}},
            "verification": "passed",
        },
    )
    hardware = tmp_path / "hardware.json"
    hardware.write_text("{}")
    receipt = tmp_path / "receipt.json"

    assert subject.execute(
        admission_path=admission_path,
        shard_path=shard_path,
        source=tmp_path,
        inputs=tmp_path,
        runs=tmp_path / "runs",
        operations=tmp_path / "operations",
        receipt=receipt,
        hardware_attestation=hardware,
        workers=2,
    ) == 0
    document = json.loads(receipt.read_bytes())
    assert document["workers"] == 2
    assert document["status"] == "terminal_all_runs_verified"
    assert [item["run_id"] for item in document["results"]] == [
        "run-0",
        "run-1",
        "run-2",
        "run-3",
    ]


def test_execute_stops_queued_runs_after_unexpected_exit(tmp_path, monkeypatch):
    subject = _command()
    admission_path, shard_path, admission, shard = _documents(
        tmp_path, (7, 0, 0), delays=(0.0, 0.5, 0.5)
    )
    monkeypatch.setattr(subject, "verify_admission_shard", lambda *args: (admission, shard))
    monkeypatch.setattr(subject, "verify_source", lambda *args: None)
    monkeypatch.setattr(subject, "verify_inputs", lambda *args: None)
    monkeypatch.setattr(subject, "verify_hardware_attestation", lambda *args: {"sha256": "b" * 64})
    monkeypatch.setattr(
        subject,
        "verify_publication",
        lambda output, *, run, **kwargs: {
            "run_id": run["run_id"],
            "exit_status": 0,
            "comparison_complete": True,
            "manifest_sha256": "c" * 64,
            "output_files": {},
            "verification": "passed",
        },
    )
    hardware = tmp_path / "hardware.json"
    hardware.write_text("{}")
    receipt = tmp_path / "receipt.json"

    assert subject.execute(
        admission_path=admission_path,
        shard_path=shard_path,
        source=tmp_path,
        inputs=tmp_path,
        runs=tmp_path / "runs",
        operations=tmp_path / "operations",
        receipt=receipt,
        hardware_attestation=hardware,
        workers=2,
    ) == 3
    document = json.loads(receipt.read_bytes())
    assert document["status"] == "stopped_after_runner_failure"
    assert document["all_planned_runs_accounted"] is False
    assert [item["run_id"] for item in document["results"]] == ["run-0", "run-1"]
    assert not (tmp_path / "operations" / "run-2").exists()
