"""Bounded offline subprocess scheduling (design §§7–8; #337).

Scientific commands remain isolated processes.  The coordinator only admits,
observes and verifies them, dispatches incrementally, and never redelivers an
operation whose prior outcome is uncertain.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CommandTask:
    task_id: str
    argv: tuple[str, ...]
    cwd: Path
    operation: Path
    environment: tuple[tuple[str, str], ...] = ()
    cpu_ids: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if (
            type(self.task_id) is not str
            or not self.task_id
            or type(self.argv) is not tuple
            or not self.argv
            or any(type(item) is not str or not item for item in self.argv)
            or not isinstance(self.cwd, Path)
            or not isinstance(self.operation, Path)
            or type(self.environment) is not tuple
            or any(
                type(item) is not tuple
                or len(item) != 2
                or any(type(value) is not str or not value for value in item)
                for item in self.environment
            )
            or len(dict(self.environment)) != len(self.environment)
            or type(self.cpu_ids) is not tuple
            or any(type(value) is not int or value < 0 for value in self.cpu_ids)
            or len(set(self.cpu_ids)) != len(self.cpu_ids)
        ):
            raise ValueError("invalid offline command task")


@dataclass(frozen=True)
class CommandResult:
    task_id: str
    exit_status: int
    started_at_utc: str
    elapsed_ns: int
    verification: str
    resumed: bool


class CommandBatchFailed(RuntimeError):
    """The batch stopped admitting queued commands after one uncertain result."""

    def __init__(self, message: str, results: tuple[CommandResult, ...]) -> None:
        super().__init__(message)
        self.results = results


Verifier = Callable[[CommandTask, int], None]


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode(
        "ascii"
    )


def _write_new(path: Path, raw: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _command(task: CommandTask) -> tuple[str, ...]:
    if task.cpu_ids and sys.platform == "linux" and shutil.which("taskset") is not None:
        return ("taskset", "--cpu-list", ",".join(str(value) for value in task.cpu_ids), *task.argv)
    return task.argv


def _environment(task: CommandTask) -> dict[str, str]:
    result = dict(os.environ)
    for name in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        result[name] = "1"
    result.update(task.environment)
    return result


def _read_exit(path: Path) -> int:
    raw = path.read_bytes()
    if not raw.endswith(b"\n") or not raw[:-1].isdigit():
        raise ValueError("retained exit status is not a nonnegative integer")
    return int(raw[:-1])


def _verify(task: CommandTask, exit_status: int, verifier: Verifier | None) -> str:
    if verifier is None:
        return "passed"
    try:
        verifier(task, exit_status)
    except Exception as error:
        return (
            "failed:"
            + type(error).__module__
            + "."
            + type(error).__qualname__
            + ":"
            + str(error)
        )
    return "passed"


def _run_one(
    task: CommandTask,
    verifier: Verifier | None,
    accepted_exit_codes: frozenset[int],
) -> CommandResult:
    argv_raw = _canonical(list(task.argv)) + b"\n"
    started_at = dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z")
    if task.operation.exists():
        expected = {"argv.json", "stdout.log", "stderr.log", "exit-status"}
        if (
            not task.operation.is_dir()
            or task.operation.is_symlink()
            or {path.name for path in task.operation.iterdir()} != expected
            or (task.operation / "argv.json").read_bytes() != argv_raw
            or any((task.operation / name).is_symlink() for name in expected)
        ):
            raise ValueError(f"incomplete prior operation refuses redelivery: {task.task_id}")
        exit_status = _read_exit(task.operation / "exit-status")
        started = time.monotonic_ns()
        verification = (
            _verify(task, exit_status, verifier)
            if exit_status in accepted_exit_codes
            else "not_attempted_unexpected_exit"
        )
        return CommandResult(
            task.task_id,
            exit_status,
            started_at,
            time.monotonic_ns() - started,
            verification,
            True,
        )

    task.operation.parent.mkdir(parents=True, exist_ok=True)
    task.operation.mkdir(mode=0o700)
    _write_new(task.operation / "argv.json", argv_raw)
    started = time.monotonic_ns()
    with (task.operation / "stdout.log").open("xb") as stdout, (
        task.operation / "stderr.log"
    ).open("xb") as stderr:
        process = subprocess.run(
            _command(task),
            cwd=task.cwd,
            env=_environment(task),
            stdout=stdout,
            stderr=stderr,
            check=False,
        )
        stdout.flush()
        stderr.flush()
        os.fsync(stdout.fileno())
        os.fsync(stderr.fileno())
    elapsed = time.monotonic_ns() - started
    _write_new(task.operation / "exit-status", f"{process.returncode}\n".encode("ascii"))
    _fsync_directory(task.operation)
    verification = (
        _verify(task, process.returncode, verifier)
        if process.returncode in accepted_exit_codes
        else "not_attempted_unexpected_exit"
    )
    return CommandResult(task.task_id, process.returncode, started_at, elapsed, verification, False)


def run_command_batch(
    tasks: Sequence[CommandTask],
    *,
    workers: int,
    accepted_exit_codes: frozenset[int],
    verifier: Verifier | None = None,
) -> tuple[CommandResult, ...]:
    """Run incrementally admitted commands and stop the queue after a failure."""
    planned = tuple(tasks)
    if type(workers) is not int or workers < 1:
        raise ValueError("workers must be a positive integer")
    if (
        type(accepted_exit_codes) is not frozenset
        or not accepted_exit_codes
        or any(type(value) is not int or value < 0 for value in accepted_exit_codes)
    ):
        raise ValueError("accepted exit codes must be nonnegative integers")
    if (
        len({task.task_id for task in planned}) != len(planned)
        or len({task.operation for task in planned}) != len(planned)
    ):
        raise ValueError("task identities and operation directories must be unique")
    if not planned:
        return ()

    indexed = {task.task_id: index for index, task in enumerate(planned)}
    results: dict[str, CommandResult] = {}
    failures: list[str] = []
    next_index = 0
    futures: dict[Future[CommandResult], CommandTask] = {}

    def submit(executor: ThreadPoolExecutor) -> None:
        nonlocal next_index
        task = planned[next_index]
        next_index += 1
        futures[executor.submit(_run_one, task, verifier, accepted_exit_codes)] = task

    with ThreadPoolExecutor(max_workers=min(workers, len(planned))) as executor:
        while next_index < min(workers, len(planned)):
            submit(executor)
        while futures:
            done, _ = wait(futures, return_when=FIRST_COMPLETED)
            for future in done:
                task = futures.pop(future)
                try:
                    result = future.result()
                except Exception as error:
                    failures.append(f"{task.task_id}: {error}")
                else:
                    results[task.task_id] = result
                    if result.exit_status not in accepted_exit_codes:
                        failures.append(
                            f"{task.task_id}: unexpected exit status {result.exit_status}"
                        )
                    elif result.verification != "passed":
                        failures.append(f"{task.task_id}: {result.verification}")
            while not failures and next_index < len(planned) and len(futures) < workers:
                submit(executor)

    ordered = tuple(sorted(results.values(), key=lambda item: indexed[item.task_id]))
    if failures:
        raise CommandBatchFailed("; ".join(failures), ordered)
    return ordered
