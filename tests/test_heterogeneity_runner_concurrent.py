"""Concurrent B0H coordinator fixtures; no multiprocessing or GPU use."""

from __future__ import annotations

from collections import deque

import pytest
from heterogeneity_runner_fixtures import campaign, dataset
from test_heterogeneity_runner import mocked_runner

from genomeos.validation.heterogeneity_runner_store import LocalB0HStore
from genomeos.validation.heterogeneity_runner_wire import record_digest


class InlineWorkers:
    def __init__(self, subject, workers, *, fail_slot=None):
        self.subject = subject
        self.slots = tuple(range(workers))
        self.pending = deque()
        self.fail_slot = fail_slot
        self.failed = False
        self.closed = False

    def submit(self, slot, task):
        from genomeos.validation.heterogeneity_runner import execute_b0h_stage

        if slot == self.fail_slot and not self.failed:
            self.failed = True
            outcome = self.subject.WorkerOutcome(
                slot,
                record_digest(task.start),
                None,
                "builtins.RuntimeError",
                "synthetic worker failure",
            )
        else:
            outcome = self.subject.WorkerOutcome(
                slot,
                record_digest(task.start),
                execute_b0h_stage(task),
                None,
                None,
            )
        self.pending.append(outcome)

    def receive(self):
        if self.fail_slot is not None:
            return self.pending.popleft()
        return self.pending.pop()

    def close(self):
        self.closed = True

    def abort(self):
        self.closed = True


def _normalized(stages):
    return tuple(
        (
            stage.start.key.stage,
            stage.start.key.attempt_id,
            stage.receipt.root_type if stage.receipt is not None else None,
            stage.failure.phase if stage.failure is not None else None,
            stage.encoded,
        )
        for stage in stages
    )


def test_concurrent_cases_match_serial_scientific_evidence(tmp_path, monkeypatch):
    from genomeos.validation import heterogeneity_runner_concurrent as subject

    runner, serial_counts = mocked_runner(monkeypatch)
    serial_parent = tmp_path / "serial"
    serial_parent.mkdir()
    manifest, admission, null = campaign(serial_parent)
    cases = (dataset(0).case_id, dataset(1).case_id)
    with LocalB0HStore.create(
        serial_parent / "study.sqlite3",
        manifest=manifest,
        admission=admission,
        null=null,
        owner_id="serial-owner",
    ) as store:
        serial = tuple(runner.execute_b0h_case(manifest, case, store) for case in cases)

    concurrent_parent = tmp_path / "concurrent"
    concurrent_parent.mkdir()
    concurrent_manifest, concurrent_admission, concurrent_null = campaign(concurrent_parent)
    runner, concurrent_counts = mocked_runner(monkeypatch)
    workers = InlineWorkers(subject, 2)
    with LocalB0HStore.create(
        concurrent_parent / "study.sqlite3",
        manifest=concurrent_manifest,
        admission=concurrent_admission,
        null=concurrent_null,
        owner_id="concurrent-owner",
    ) as store:
        subject._run_cases(
            concurrent_manifest,
            cases,
            store,
            concurrent_parent / "publication-spool",
            workers=2,
            worker_group=workers,
        )
        concurrent = tuple(runner.load_b0h_case(concurrent_manifest, case, store) for case in cases)

    assert serial_counts == concurrent_counts
    assert tuple(_normalized(case.stages) for case in serial) == tuple(
        _normalized(case.stages) for case in concurrent
    )
    assert workers.closed is True


def test_worker_failure_stops_new_starts_and_drains_active_result(tmp_path, monkeypatch):
    from genomeos.validation import heterogeneity_runner_concurrent as subject

    runner, counts = mocked_runner(monkeypatch)
    manifest, admission, null = campaign(tmp_path)
    cases = (dataset(0).case_id, dataset(1).case_id, dataset(2).case_id)
    workers = InlineWorkers(subject, 2, fail_slot=0)
    with LocalB0HStore.create(
        tmp_path / "study.sqlite3",
        manifest=manifest,
        admission=admission,
        null=null,
        owner_id="fixture-owner",
    ) as store:
        with pytest.raises(subject.ConcurrentExecutionFailed, match="synthetic worker failure"):
            subject._run_cases(
                manifest,
                cases,
                store,
                tmp_path / "publication-spool",
                workers=2,
                worker_group=workers,
            )
        first, second, never_started = (store.stages(case) for case in cases)

    assert len(first) == 1 and first[0].completion is None
    assert len(second) == 1 and second[0].completion is not None
    assert never_started == ()
    assert counts["generation"] == 1
    assert workers.closed is True


def test_fixed_clock_serial_and_concurrent_completion_inventory_is_identical(
    tmp_path, monkeypatch
):
    from genomeos.validation import heterogeneity_runner_concurrent as subject

    runner, serial_counts = mocked_runner(monkeypatch)
    monkeypatch.setattr(runner.time, "time_ns", lambda: 100)
    monkeypatch.setattr(runner.time, "monotonic_ns", lambda: 200)
    monkeypatch.setattr(runner, "_resource_observation", lambda: (4096, None))
    manifest, admission, null = campaign(tmp_path)
    cases = (dataset(0).case_id, dataset(1).case_id)
    database = tmp_path / "study.sqlite3"
    with LocalB0HStore.create(
        database,
        manifest=manifest,
        admission=admission,
        null=null,
        owner_id="fixed-owner",
    ) as store:
        for case in cases:
            runner.execute_b0h_case(manifest, case, store)
        serial_inventory = store.inventory()

    database.unlink()
    runner, concurrent_counts = mocked_runner(monkeypatch)
    monkeypatch.setattr(runner.time, "time_ns", lambda: 100)
    monkeypatch.setattr(runner.time, "monotonic_ns", lambda: 200)
    monkeypatch.setattr(runner, "_resource_observation", lambda: (4096, None))
    workers = InlineWorkers(subject, 2)
    with LocalB0HStore.create(
        database,
        manifest=manifest,
        admission=admission,
        null=null,
        owner_id="fixed-owner",
    ) as store:
        subject._run_cases(
            manifest,
            cases,
            store,
            tmp_path / "publication-spool",
            workers=2,
            worker_group=workers,
        )
        concurrent_inventory = store.inventory()

    assert serial_counts == concurrent_counts
    assert serial_inventory == concurrent_inventory
