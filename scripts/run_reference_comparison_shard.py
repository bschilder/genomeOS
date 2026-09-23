#!/usr/bin/env python3
"""Execute a bounded reference-comparison shard (design §§5,7–8,12; #337)."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) in sys.path:
    sys.path.remove(str(ROOT))
sys.path.insert(0, str(ROOT))

from genomeos.validation.offline_scheduler import (  # noqa: E402
    CommandBatchFailed,
    CommandResult,
    CommandTask,
    run_command_batch,
)

ADDED_TRANSITIVE_SOURCES = frozenset(
    {
        "genomeos/validation/count_legacy.py",
        "genomeos/validation/count_probability.py",
        "genomeos/validation/count_probability_adapter.py",
        "genomeos/validation/count_scaled.py",
    }
)
ORCHESTRATION_SOURCES = frozenset(
    {
        "genomeos/validation/offline_scheduler.py",
        "scripts/run_reference_comparison_shard.py",
    }
)
_VALIDATION_LOCK = threading.Lock()


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode(
        "ascii"
    )


def sha256_file(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def file_record(path: Path) -> dict[str, object]:
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"evidence member missing or not regular: {path}")
    return {"size_bytes": path.stat().st_size, "sha256": sha256_file(path)}


def read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if type(value) is not dict:
        raise ValueError(f"JSON evidence is not an object: {path}")
    return value


def write_new(path: Path, raw: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def git(source: Path, *arguments: str) -> bytes:
    return subprocess.run(
        ["git", *arguments], cwd=source, check=True, capture_output=True
    ).stdout


def verify_source(source: Path, source_sha: str, expected: dict[str, str]) -> None:
    if git(source, "rev-parse", "HEAD").decode().strip() != source_sha:
        raise ValueError("execution source revision differs from admitted source")
    if git(source, "status", "--porcelain=v1", "--untracked-files=all"):
        raise ValueError("execution source checkout is not clean")
    for relative, digest in expected.items():
        path = source / relative
        if file_record(path)["sha256"] != digest:
            raise ValueError(f"execution source hash differs from admission: {relative}")
        if path.read_bytes() != git(source, "show", f"HEAD:{relative}"):
            raise ValueError(f"execution source differs from committed bytes: {relative}")


def verify_inputs(root: Path, expected: dict[str, dict[str, Any]]) -> None:
    for name, identity in expected.items():
        if file_record(root / name) != identity:
            raise ValueError(f"execution input differs from admission: {name}")


def option(argv: list[str] | tuple[str, ...], name: str) -> str:
    if argv.count(name) != 1:
        raise ValueError(f"execution argv must contain {name} exactly once")
    position = argv.index(name) + 1
    if position == len(argv):
        raise ValueError(f"execution argv is missing a value for {name}")
    return argv[position]


def expected_configuration(argv: list[str] | tuple[str, ...]) -> dict[str, object]:
    return {
        "source_release": option(argv, "--source-release"),
        "cohort_stage": option(argv, "--cohort-stage"),
        "count_kind": option(argv, "--count-kind"),
        "evidence_role": option(argv, "--evidence-role"),
        "prior_alpha": float(option(argv, "--prior-alpha")),
        "prior_beta": float(option(argv, "--prior-beta")),
        "folds": int(option(argv, "--folds")),
        "seed": int(option(argv, "--seed")),
        "model": option(argv, "--model"),
        "rho_prior_alpha": float(option(argv, "--rho-prior-alpha")),
        "rho_prior_beta": float(option(argv, "--rho-prior-beta")),
        "draws": int(option(argv, "--draws")),
        "tune": int(option(argv, "--tune")),
        "chains": int(option(argv, "--chains")),
        "target_accept": float(option(argv, "--target-accept")),
        "cdf_backend": option(argv, "--cdf-backend"),
    }


def validate_manifest_identity(
    manifest: dict[str, Any],
    *,
    run: dict[str, Any],
    admission: dict[str, Any],
    summary: dict[str, Any],
    exit_status: int,
) -> None:
    source_sha = admission["source_sha"]
    if manifest.get("schema_version") != 2:
        raise ValueError("B0H publication manifest schema is not v2")
    if manifest.get("model") != "B0H_population_heterogeneity":
        raise ValueError("B0H publication model identity differs from admission")
    if manifest.get("configuration") != expected_configuration(run["execution_argv"]):
        raise ValueError("B0H publication configuration differs from execution argv")
    if manifest.get("git") != {"head": source_sha, "dirty": False}:
        raise ValueError("B0H publication source state differs from admission")
    runner_sources = {
        path: digest
        for path, digest in admission["source_files"].items()
        if path not in ADDED_TRANSITIVE_SOURCES | ORCHESTRATION_SOURCES
    }
    if manifest.get("science_source_sha256") != runner_sources:
        raise ValueError("B0H publication runner-declared science hashes differ from admission")
    counts_name = Path(option(run["execution_argv"], "--counts")).name
    dependencies_name = Path(option(run["execution_argv"], "--dependencies")).name
    expected_inputs = {
        "counts": admission["input_files"][counts_name],
        "dependencies": admission["input_files"][dependencies_name],
    }
    if manifest.get("input_files") != expected_inputs:
        raise ValueError("B0H publication input hashes differ from admission")
    complete = summary.get("comparison_complete")
    if type(complete) is not bool or (exit_status == 0) != complete:
        raise ValueError("B0H publication completeness contradicts runner exit status")


def verify_publication(
    output: Path,
    *,
    run: dict[str, Any],
    admission: dict[str, Any],
    exit_status: int,
    source: Path,
) -> dict[str, object]:
    expected_outputs = tuple(run["expected_outputs"])
    if not output.is_dir() or output.is_symlink():
        raise ValueError(f"run output is missing or not a plain directory: {output}")
    names = tuple(sorted(path.name for path in output.iterdir()))
    if names != tuple(sorted(expected_outputs)):
        raise ValueError(f"run output member set differs from contract: {run['run_id']}")
    records = {name: file_record(output / name) for name in expected_outputs}
    manifest = read_object(output / "manifest.json")
    summary = read_object(output / "summary.json")
    validate_manifest_identity(
        manifest, run=run, admission=admission, summary=summary, exit_status=exit_status
    )
    declared = manifest.get("output_files")
    if type(declared) is not dict:
        raise ValueError("B0H publication manifest lacks output hashes")
    for name in expected_outputs:
        if name != "manifest.json" and declared.get(name) != records[name]:
            raise ValueError(f"B0H output differs from its manifest: {name}")

    with _VALIDATION_LOCK:
        sys.path.insert(0, str(source))
        try:
            from genomeos.validation.reference_b0h_artifacts import validate_b0h_publication

            validate_b0h_publication(
                {name: (output / name).read_bytes() for name in expected_outputs}
            )
        finally:
            sys.path.remove(str(source))
    return {
        "run_id": run["run_id"],
        "exit_status": exit_status,
        "comparison_complete": summary["comparison_complete"],
        "manifest_sha256": records["manifest.json"]["sha256"],
        "output_files": records,
        "verification": "passed",
    }


def verify_admission_shard(admission_path: Path, shard_path: Path) -> tuple[dict, dict]:
    admission = read_object(admission_path)
    shard = read_object(shard_path)
    version = admission.get("version")
    source_sha = admission.get("source_sha")
    if (
        admission.get("format") != "b0h-comparison-admission"
        or type(version) is not str
        or not version
        or admission.get("status") != "admitted_not_executed"
        or type(source_sha) is not str
        or len(source_sha) != 40
        or any(value not in "0123456789abcdef" for value in source_sha)
    ):
        raise ValueError("comparison admission is not executable")
    if (
        shard.get("format") != "b0h-comparison-shard"
        or shard.get("version") != version
        or shard.get("status") != "admitted_not_executed"
        or shard.get("source_sha") != source_sha
        or shard.get("calibration") != admission.get("calibration")
    ):
        raise ValueError("comparison shard differs from admission")
    matches = [item for item in admission["shards"] if item["seed"] == shard["seed"]]
    if len(matches) != 1 or matches[0]["shard_sha256"] != sha256_file(shard_path):
        raise ValueError("comparison shard hash differs from admission")
    runs = shard.get("runs")
    if type(runs) is not list or not runs:
        raise ValueError("comparison shard requires at least one run")
    if matches[0]["run_ids"] != [run["run_id"] for run in runs]:
        raise ValueError("comparison shard run order differs from admission")
    if any(run.get("executed") is not False for run in runs):
        raise ValueError("comparison shard must contain only unexecuted runs")
    return admission, shard


def verify_hardware_attestation(path: Path) -> dict[str, object]:
    record = read_object(path)
    if (
        record.get("format") != "b0h-comparison-hardware-attestation"
        or record.get("jax", {}).get("default_backend") != "gpu"
        or record.get("jax", {}).get("enable_x64") is not True
        or record.get("cupy", {}).get("device_count", 0) < 1
        or record.get("cupy", {}).get("probe_dtype") != "float64"
    ):
        raise ValueError("hardware attestation does not prove JAX/CuPy GPU execution")
    return file_record(path)


def _result_document(
    result: CommandResult,
    verified: dict[str, dict[str, object]],
) -> dict[str, object]:
    if result.task_id in verified:
        document = dict(verified[result.task_id])
    else:
        document = {
            "run_id": result.task_id,
            "exit_status": result.exit_status,
            "comparison_complete": False,
            "verification": result.verification,
        }
    document.update(
        {
            "started_at_utc": result.started_at_utc,
            "elapsed_ns": result.elapsed_ns,
            "resumed": result.resumed,
        }
    )
    return document


def execute(
    *,
    admission_path: Path,
    shard_path: Path,
    source: Path,
    inputs: Path,
    runs: Path,
    operations: Path,
    receipt: Path,
    hardware_attestation: Path,
    workers: int,
) -> int:
    admission, shard = verify_admission_shard(admission_path, shard_path)
    verify_source(source, admission["source_sha"], admission["source_files"])
    verify_inputs(inputs, admission["input_files"])
    hardware_record = verify_hardware_attestation(hardware_attestation)
    if receipt.exists() or receipt.is_symlink():
        raise FileExistsError("shard receipt destination must be fresh")
    runs.mkdir(mode=0o700, parents=True, exist_ok=True)
    operations.mkdir(mode=0o700, parents=True, exist_ok=True)

    run_by_id = {run["run_id"]: run for run in shard["runs"]}
    tasks = []
    for run in shard["runs"]:
        argv = tuple(run["execution_argv"])
        output = Path(option(argv, "--out"))
        if output.parent != runs or output.name != run["run_id"]:
            raise ValueError(f"run output path differs from shard root: {run['run_id']}")
        tasks.append(
            CommandTask(
                task_id=run["run_id"],
                argv=argv,
                cwd=source,
                operation=operations / run["run_id"],
            )
        )

    verified: dict[str, dict[str, object]] = {}

    def verifier(task: CommandTask, exit_status: int) -> None:
        run = run_by_id[task.task_id]
        verified[task.task_id] = verify_publication(
            Path(option(task.argv, "--out")),
            run=run,
            admission=admission,
            exit_status=exit_status,
            source=source,
        )

    status = "terminal_all_runs_verified"
    exit_code = 0
    try:
        scheduled = run_command_batch(
            tasks,
            workers=workers,
            accepted_exit_codes=frozenset({0, 2}),
            verifier=verifier,
        )
    except CommandBatchFailed as error:
        scheduled = error.results
        status = "stopped_after_runner_failure"
        exit_code = 3
    results = [_result_document(result, verified) for result in scheduled]
    all_accounted = len(results) == len(tasks) and exit_code == 0
    document = {
        "format": "b0h-comparison-shard-execution",
        "version": admission["version"],
        "source_sha": admission["source_sha"],
        "seed": shard["seed"],
        "status": status,
        "workers": workers,
        "hardware_attestation": hardware_record,
        "admission": file_record(admission_path),
        "shard": file_record(shard_path),
        "source_files_sha256": hashlib.sha256(canonical(admission["source_files"])).hexdigest(),
        "results": results,
        "all_planned_runs_accounted": all_accounted,
        "complete_run_count": sum(item.get("comparison_complete") is True for item in results),
        "incomplete_run_count": sum(item.get("comparison_complete") is False for item in results),
    }
    write_new(receipt, canonical(document) + b"\n")
    return exit_code


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--admission", required=True, type=Path)
    parser.add_argument("--shard", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--inputs", required=True, type=Path)
    parser.add_argument("--runs", required=True, type=Path)
    parser.add_argument("--operations", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--hardware-attestation", required=True, type=Path)
    parser.add_argument("--workers", required=True, type=int)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    return execute(
        admission_path=args.admission,
        shard_path=args.shard,
        source=args.source,
        inputs=args.inputs,
        runs=args.runs,
        operations=args.operations,
        receipt=args.receipt,
        hardware_attestation=args.hardware_attestation,
        workers=args.workers,
    )


if __name__ == "__main__":
    raise SystemExit(main())
