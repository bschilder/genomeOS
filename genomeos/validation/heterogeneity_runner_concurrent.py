"""Concurrent B0H science with one publication owner (design §§5,7–8,12; #337)."""

from __future__ import annotations

import multiprocessing
import os
import queue
from collections import deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from genomeos.validation.heterogeneity_runner_records import CampaignManifest, PublicationPacket
from genomeos.validation.heterogeneity_runner_spool import (
    publication_packets,
    write_publication_packet,
)
from genomeos.validation.heterogeneity_runner_store import LocalB0HStore, StoreIntegrityError
from genomeos.validation.heterogeneity_runner_wire import record_digest
from genomeos.validation.heterogeneity_simulation_types import SbcCaseId

THREAD_CAPS = {
    "OMP_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
    "OPENBLAS_NUM_THREADS": "1",
    "NUMEXPR_NUM_THREADS": "1",
}


@dataclass(frozen=True)
class WorkerOutcome:
    slot: int
    start_sha256: str
    packet: PublicationPacket | None
    exception_class: str | None
    message: str | None

    def __post_init__(self) -> None:
        if (
            type(self.slot) is not int
            or self.slot < 0
            or type(self.start_sha256) is not str
            or len(self.start_sha256) != 64
            or (self.packet is None) == (self.exception_class is None)
            or (self.exception_class is None) != (self.message is None)
        ):
            raise ValueError("invalid worker outcome")


class ConcurrentExecutionFailed(RuntimeError):
    """Concurrent execution stopped before all admitted stages completed."""


def _worker_main(slot: int, inbound: Any, outbound: Any) -> None:
    os.environ.update(THREAD_CAPS)
    from genomeos.validation.heterogeneity_runner import execute_b0h_stage

    while True:
        task = inbound.get()
        if task is None:
            return
        start_sha256 = record_digest(task.start)
        try:
            packet = execute_b0h_stage(task)
        except BaseException as error:
            outbound.put(
                WorkerOutcome(
                    slot,
                    start_sha256,
                    None,
                    type(error).__module__ + "." + type(error).__qualname__,
                    str(error),
                )
            )
            return
        outbound.put(WorkerOutcome(slot, start_sha256, packet, None, None))


def _start_with_thread_caps(processes: Sequence[Any]) -> None:
    """Let spawn bootstrap import numerical libraries under bounded thread settings."""
    prior = {name: os.environ.get(name) for name in THREAD_CAPS}
    try:
        os.environ.update(THREAD_CAPS)
        for process in processes:
            process.start()
    finally:
        for name, value in prior.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


class ProcessWorkerGroup:
    """Long-lived spawned workers with one task queue per process."""

    def __init__(self, workers: int) -> None:
        if type(workers) is not int or workers < 1:
            raise ValueError("workers must be a positive integer")
        context = multiprocessing.get_context("spawn")
        self.slots = tuple(range(workers))
        self._outbound = context.Queue()
        self._inbound = tuple(context.Queue(maxsize=1) for _ in self.slots)
        self._processes = tuple(
            context.Process(
                target=_worker_main,
                args=(slot, self._inbound[slot], self._outbound),
                name=f"b0h-science-{slot}",
            )
            for slot in self.slots
        )
        _start_with_thread_caps(self._processes)
        self._active_start: dict[int, str] = {}
        self._reported_dead: set[int] = set()
        self._closed = False

    def submit(self, slot: int, task: object) -> None:
        if (
            self._closed
            or slot not in self.slots
            or slot in self._active_start
            or not self._processes[slot].is_alive()
        ):
            raise RuntimeError("worker group is closed or slot is invalid")
        self._active_start[slot] = record_digest(task.start)
        self._inbound[slot].put(task)

    def receive(self) -> WorkerOutcome:
        while True:
            try:
                outcome = self._outbound.get(timeout=0.5)
            except queue.Empty:
                dead = [
                    (slot, process.pid, process.exitcode)
                    for slot, process in zip(self.slots, self._processes, strict=True)
                    if (
                        process.exitcode is not None
                        and slot in self._active_start
                        and slot not in self._reported_dead
                    )
                ]
                if not dead:
                    continue
                try:
                    outcome = self._outbound.get(timeout=0.5)
                except queue.Empty:
                    slot, process_id, exit_status = dead[0]
                    self._reported_dead.add(slot)
                    return WorkerOutcome(
                        slot,
                        self._active_start.pop(slot),
                        None,
                        "genomeos.validation.heterogeneity_runner_concurrent.WorkerProcessLost",
                        f"worker pid={process_id} exited status={exit_status} without outcome",
                    )
            if type(outcome) is not WorkerOutcome:
                raise RuntimeError("worker returned an unsupported outcome")
            self._active_start.pop(outcome.slot, None)
            return outcome

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for process, inbound in zip(self._processes, self._inbound, strict=True):
            if process.is_alive():
                inbound.put(None)
        for process in self._processes:
            process.join()
        bad = [(process.pid, process.exitcode) for process in self._processes if process.exitcode != 0]
        if bad:
            raise RuntimeError(f"worker process exit failure: {bad}")

    def abort(self) -> None:
        self._closed = True
        for process in self._processes:
            if process.is_alive():
                process.terminate()
        for process in self._processes:
            process.join()


def reconcile_publication_spool(
    manifest: CampaignManifest,
    store: LocalB0HStore,
    spool: Path,
) -> int:
    """Publish every exact durable packet before admitting more science."""
    campaign_sha256 = record_digest(manifest)
    count = 0
    for packet in publication_packets(spool, limits=manifest.limits):
        if packet.start.key.campaign_sha256 != campaign_sha256:
            raise StoreIntegrityError("spooled publication belongs to another campaign")
        matching = tuple(
            stage for stage in store.stages(packet.start.key.case) if stage.start == packet.start
        )
        if len(matching) != 1:
            raise StoreIntegrityError("spooled publication lacks exactly one retained START")
        if packet.start.owner_id == store.owner_id:
            store.publish_pending(packet)
        else:
            store.publish_recovered(packet)
        count += 1
    return count


def _run_cases(
    manifest: CampaignManifest,
    cases: Sequence[SbcCaseId],
    store: LocalB0HStore,
    spool: Path,
    *,
    workers: int,
    worker_group: Any,
) -> None:
    """Coordinate a bounded case set; the public entry point always passes the full manifest."""
    from genomeos.validation.heterogeneity_runner import prepare_b0h_stage

    if type(workers) is not int or workers < 2 or len(worker_group.slots) != workers:
        raise ValueError("concurrent execution requires the declared worker count")
    ready = deque(cases)
    idle = set(worker_group.slots)
    active: dict[int, tuple[SbcCaseId, str]] = {}
    failures: list[str] = []
    abnormal = True
    try:
        while ready or active:
            while ready and idle and not failures:
                slot = min(idle)
                case = ready.popleft()
                try:
                    task = prepare_b0h_stage(manifest, case, store)
                except Exception as error:
                    failures.append(
                        type(error).__module__ + "." + type(error).__qualname__ + ": " + str(error)
                    )
                    break
                if task is None:
                    continue
                start_sha256 = record_digest(task.start)
                try:
                    worker_group.submit(slot, task)
                except Exception as error:
                    failures.append(
                        type(error).__module__
                        + "."
                        + type(error).__qualname__
                        + ": "
                        + str(error)
                    )
                    break
                idle.remove(slot)
                active[slot] = (case, start_sha256)
            if not active:
                break
            try:
                outcome = worker_group.receive()
            except Exception as error:
                failures.append(
                    type(error).__module__ + "." + type(error).__qualname__ + ": " + str(error)
                )
                break
            expected = active.pop(outcome.slot, None)
            idle.add(outcome.slot)
            if expected is None or expected[1] != outcome.start_sha256:
                failures.append("worker outcome does not match its admitted START")
                continue
            case = expected[0]
            if outcome.packet is None:
                failures.append(f"{outcome.exception_class}: {outcome.message}")
                continue
            try:
                write_publication_packet(spool, outcome.packet)
                store.publish_pending(outcome.packet)
            except Exception as error:
                failures.append(
                    type(error).__module__ + "." + type(error).__qualname__ + ": " + str(error)
                )
                continue
            if not failures:
                ready.append(case)
        while active:
            try:
                outcome = worker_group.receive()
            except Exception as error:
                failures.append(
                    type(error).__module__ + "." + type(error).__qualname__ + ": " + str(error)
                )
                break
            expected = active.pop(outcome.slot, None)
            if expected is None or expected[1] != outcome.start_sha256:
                failures.append("drained worker outcome does not match its admitted START")
            elif outcome.packet is None:
                failures.append(f"{outcome.exception_class}: {outcome.message}")
            else:
                try:
                    write_publication_packet(spool, outcome.packet)
                    store.publish_pending(outcome.packet)
                except Exception as error:
                    failures.append(
                        type(error).__module__
                        + "."
                        + type(error).__qualname__
                        + ": "
                        + str(error)
                    )
        abnormal = False
    finally:
        if abnormal:
            worker_group.abort()
        else:
            worker_group.close()
    if failures:
        raise ConcurrentExecutionFailed("; ".join(failures))


def run_b0h_concurrent(
    manifest: CampaignManifest,
    store: LocalB0HStore,
    spool: Path,
    *,
    workers: int,
    worker_group_factory: Callable[[int], Any] = ProcessWorkerGroup,
) -> None:
    if type(manifest) is not CampaignManifest or record_digest(store.manifest) != record_digest(manifest):
        raise StoreIntegrityError("concurrent runner campaign mismatch")
    reconcile_publication_spool(manifest, store, spool)
    group = worker_group_factory(workers)
    _run_cases(
        manifest,
        manifest.cases,
        store,
        spool,
        workers=workers,
        worker_group=group,
    )
