"""Bounded offline command scheduling fixtures (design §§7–8; #337)."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest


def _task(subject, root: Path, task_id: str, body: str):
    return subject.CommandTask(
        task_id=task_id,
        argv=(sys.executable, "-c", body),
        cwd=root,
        operation=root / "operations" / task_id,
    )


def test_bounded_commands_run_concurrently_and_return_plan_order(tmp_path):
    from genomeos.validation import offline_scheduler as subject

    active = tmp_path / "active"
    active.mkdir()
    body = (
        "import pathlib,time; "
        f"p=pathlib.Path({str(active)!r}); "
        "mine=p/str(__import__('os').getpid()); mine.write_text('active'); "
        "time.sleep(0.35); mine.unlink()"
    )
    tasks = tuple(_task(subject, tmp_path, str(index), body) for index in range(4))
    started = time.monotonic()
    results = subject.run_command_batch(tasks, workers=2, accepted_exit_codes=frozenset({0}))
    elapsed = time.monotonic() - started

    assert tuple(result.task_id for result in results) == ("0", "1", "2", "3")
    assert all(result.exit_status == 0 and result.verification == "passed" for result in results)
    assert elapsed < 1.15
    for task in tasks:
        assert json.loads((task.operation / "argv.json").read_text()) == list(task.argv)
        assert (task.operation / "exit-status").read_text() == "0\n"
        assert (task.operation / "stdout.log").read_bytes() == b""
        assert (task.operation / "stderr.log").read_bytes() == b""


def test_failure_stops_queued_dispatch_but_retains_active_result(tmp_path):
    from genomeos.validation import offline_scheduler as subject

    tasks = (
        _task(subject, tmp_path, "failure", "raise SystemExit(7)"),
        _task(subject, tmp_path, "active", "import time; time.sleep(0.2)"),
        _task(subject, tmp_path, "must-not-start", "raise SystemExit(0)"),
    )
    with pytest.raises(subject.CommandBatchFailed) as failed:
        subject.run_command_batch(tasks, workers=2, accepted_exit_codes=frozenset({0}))

    assert tuple(result.task_id for result in failed.value.results) == ("failure", "active")
    assert failed.value.results[0].exit_status == 7
    assert failed.value.results[1].exit_status == 0
    assert not tasks[2].operation.exists()


def test_verified_completion_resumes_without_redelivery(tmp_path):
    from genomeos.validation import offline_scheduler as subject

    marker = tmp_path / "deliveries"
    body = (
        "from pathlib import Path; "
        f"p=Path({str(marker)!r}); "
        "p.write_text(p.read_text()+'x' if p.exists() else 'x')"
    )
    task = _task(subject, tmp_path, "only", body)
    first = subject.run_command_batch((task,), workers=1, accepted_exit_codes=frozenset({0}))
    second = subject.run_command_batch((task,), workers=1, accepted_exit_codes=frozenset({0}))

    assert marker.read_text() == "x"
    assert first[0].resumed is False
    assert second[0].resumed is True
    assert first[0].exit_status == second[0].exit_status == 0


def test_incomplete_operation_refuses_redelivery(tmp_path):
    from genomeos.validation import offline_scheduler as subject

    task = _task(subject, tmp_path, "uncertain", "raise SystemExit(0)")
    task.operation.mkdir(parents=True)
    (task.operation / "argv.json").write_text(json.dumps(list(task.argv), separators=(",", ":")) + "\n")
    (task.operation / "stdout.log").write_bytes(b"")
    (task.operation / "stderr.log").write_bytes(b"")

    with pytest.raises(subject.CommandBatchFailed, match="incomplete prior operation"):
        subject.run_command_batch((task,), workers=1, accepted_exit_codes=frozenset({0}))


def test_scheduler_caps_inherited_math_thread_pools(tmp_path, monkeypatch):
    from genomeos.validation import offline_scheduler as subject

    monkeypatch.setenv("OMP_NUM_THREADS", "64")
    task = _task(subject, tmp_path, "only", "raise SystemExit(0)")
    assert subject._environment(task)["OMP_NUM_THREADS"] == "1"


def test_verification_failure_is_retained_and_stops_queued_dispatch(tmp_path):
    from genomeos.validation import offline_scheduler as subject

    tasks = (
        _task(subject, tmp_path, "0", "raise SystemExit(0)"),
        _task(subject, tmp_path, "1", "import time; time.sleep(0.2)"),
        _task(subject, tmp_path, "2", "raise SystemExit(0)"),
    )

    def verify(task, exit_status):
        if task.task_id == "0":
            raise ValueError("synthetic verification failure")

    with pytest.raises(subject.CommandBatchFailed) as failed:
        subject.run_command_batch(
            tasks,
            workers=2,
            accepted_exit_codes=frozenset({0}),
            verifier=verify,
        )

    assert tuple(result.task_id for result in failed.value.results) == ("0", "1")
    assert failed.value.results[0].verification.startswith("failed:builtins.ValueError:")
    assert failed.value.results[1].verification == "passed"
    assert not tasks[2].operation.exists()
