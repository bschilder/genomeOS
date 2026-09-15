#!/usr/bin/env python3
"""Run the synthetic-only CuGen training LD experiment (CuGen pilot design §8)."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

_CONTROLS = {
    "CUPY_TF32": "0",
    "NVIDIA_TF32_OVERRIDE": "0",
    "USE_PINNED_READER": "0",
}
for _name, _value in _CONTROLS.items():
    os.environ[_name] = _value

_REVISION = re.compile(r"[0-9a-fA-F]{40}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cugen-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--data-version", required=True)
    parser.add_argument("--case", choices=("hand", "scale", "precision"), required=True)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--source-revision")
    return parser


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_hashes(root: Path) -> dict[str, str]:
    package_root = Path(root).resolve()
    paths = (
        "scripts/pilot_cugen_ld.py",
        "genomeos/validation/cugen_backend.py",
        "genomeos/validation/cugen_experiment.py",
        "genomeos/validation/cugen_measurement.py",
        "genomeos/validation/cugen_pilot.py",
        "genomeos/validation/cugen_artifact.py",
        "genomeos/validation/cugen_format.py",
        "genomeos/validation/cugen_source.json",
        "genomeos/validation/ld_comparison.py",
        "genomeos/validation/ld_contract.py",
        "genomeos/validation/ld_reference.py",
    )
    result: dict[str, str] = {}
    for relative in paths:
        path = package_root / relative
        if path.is_symlink() or not path.is_file() or path.resolve() != path:
            raise ValueError(f"executing genomeOS source path is invalid: {relative}")
        result[relative] = _sha256(path)
    return result


def _genomeos_revision(root: Path, supplied: str | None) -> tuple[str, str]:
    if supplied is not None:
        return supplied.lower(), "supplied"
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise ValueError("Git-observed source revision is unavailable") from error
    revision = completed.stdout.strip()
    if _REVISION.fullmatch(revision) is None:
        raise ValueError("Git-observed source revision must be a 40-character hexadecimal commit")
    return revision.lower(), "git_observed"


def _planned(case: Any, repeats: int) -> list[dict[str, Any]]:
    plans: list[dict[str, Any]] = []
    mutations = (False, True) if case.selection.held_out_ids else (False,)
    for repeat in range(repeats):
        for mutated in mutations:
            suffix = "held-out-mutated" if mutated else "baseline"
            plans.append(
                {
                    "run_id": f"{case.name}-repeat-{repeat:03d}-{suffix}",
                    "repeat": repeat,
                    "cold": not plans,
                    "held_out_mutated": mutated,
                    "status": "planned",
                }
            )
    return plans


def _failure(error: BaseException, stage: str) -> dict[str, str]:
    return {"stage": stage, "error_type": type(error).__name__, "message": str(error)}


def _write_summary(out: Path, summary: dict[str, Any]) -> None:
    summary["completed_count"] = sum(item["status"] == "completed" for item in summary["planned_runs"])
    summary["failed_count"] = sum(item["status"] == "failed" for item in summary["planned_runs"])
    summary["status"] = (
        "completed"
        if summary["completed_count"] == summary["planned_count"]
        and all(item.get("passed") is True for item in summary["held_out_invariance"])
        else "failed"
    )
    path = out / "experiment.json"
    with path.open("x", encoding="utf-8") as stream:
        json.dump(summary, stream, sort_keys=True, separators=(",", ":"))
        stream.write("\n")


def _cuda_preflight() -> tuple[Any, dict[str, Any]]:
    try:
        import cupy as cp
    except Exception as error:
        raise RuntimeError(f"CUDA device preflight failed: CuPy is unavailable: {error}") from error
    try:
        if cp.cuda.runtime.getDeviceCount() < 1:
            raise RuntimeError("CUDA device preflight failed: no visible CUDA device")
        device = cp.cuda.Device()
        device.use()
        cp.cuda.runtime.deviceSynchronize()
        properties = cp.cuda.runtime.getDeviceProperties(device.id)
    except Exception as error:
        if isinstance(error, RuntimeError) and str(error).startswith("CUDA device preflight failed"):
            raise
        raise RuntimeError(f"CUDA device preflight failed: {error}") from error
    raw_name = properties.get("name", "unknown")
    name = raw_name.decode() if isinstance(raw_name, bytes) else str(raw_name)
    return cp, {
        "device_id": int(device.id),
        "device_name": name,
        "device_total_memory_bytes": int(properties.get("totalGlobalMem", 0)),
        "driver_version": int(cp.cuda.runtime.driverGetVersion()),
        "runtime_version": int(cp.cuda.runtime.runtimeGetVersion()),
        "cupy_version": str(cp.__version__),
        "python_version": sys.version,
        "installed_distributions": sorted(
            (
                {
                    "name": distribution.metadata.get("Name", "unknown"),
                    "version": distribution.version,
                }
                for distribution in importlib.metadata.distributions()
            ),
            key=lambda item: (item["name"].lower(), item["version"]),
        ),
    }


def _mark_all_failed(plans: list[dict[str, Any]], error: BaseException, stage: str) -> None:
    for plan in plans:
        if plan["status"] == "planned":
            plan["status"] = "failed"
            plan["failure"] = _failure(error, stage)


def _invariance(out: Path, plans: list[dict[str, Any]], repeats: int) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    by_key = {(item["repeat"], item["held_out_mutated"]): item for item in plans}
    for repeat in range(repeats):
        baseline = by_key.get((repeat, False))
        mutated = by_key.get((repeat, True))
        if mutated is None:
            continue
        record: dict[str, Any] = {"repeat": repeat, "passed": False}
        if baseline is None or baseline["status"] != "completed" or mutated["status"] != "completed":
            record["reason"] = "paired_artifacts_not_completed"
            results.append(record)
            continue
        baseline_manifest = json.loads(
            (out / "runs" / baseline["run_id"] / "manifest.json").read_text(encoding="utf-8")
        )
        mutated_manifest = json.loads(
            (out / "runs" / mutated["run_id"] / "manifest.json").read_text(encoding="utf-8")
        )
        same_members = ("training.cugen", "reference.json", "cpu.tsv", "gpu.tsv", "validation.json")
        record["source_hash_changed"] = (
            baseline_manifest["files"]["source.cugen"]
            != mutated_manifest["files"]["source.cugen"]
        )
        record["training_evidence_hashes_equal"] = all(
            baseline_manifest["files"][name] == mutated_manifest["files"][name]
            for name in same_members
        )
        record["passed"] = (
            record["source_hash_changed"] and record["training_evidence_hashes_equal"]
        )
        results.append(record)
    return results


def main() -> int:
    startup_started = time.perf_counter()
    parser = _parser()
    args = parser.parse_args()
    if args.repeats < 3:
        parser.error("--repeats must be at least 3")
    if args.seed != 42:
        parser.error("--seed must be the fixed synthetic pilot seed 42")
    if not args.data_version or args.data_version != args.data_version.strip():
        parser.error("--data-version must be a nonempty whitespace-trimmed string")
    if args.source_revision is not None and _REVISION.fullmatch(args.source_revision) is None:
        parser.error("--source-revision must be a 40-character hexadecimal commit")
    if os.path.lexists(args.out):
        parser.error("output path already exists")

    import numpy as np

    from genomeos.validation.cugen_backend import load_verified_cugen_api
    from genomeos.validation.cugen_experiment import build_synthetic_case, mutate_held_out
    from genomeos.validation.cugen_format import decode_cugen_bytes
    from genomeos.validation.cugen_measurement import (
        PilotMeasurementObserver,
        cupy_pool_snapshot,
        process_rss_high_water_bytes,
    )
    from genomeos.validation.cugen_pilot import run_cugen_pilot

    case = build_synthetic_case(args.case, seed=args.seed)
    plans = _planned(case, args.repeats)
    args.out.mkdir()
    (args.out / "sources").mkdir()
    (args.out / "runs").mkdir()
    summary: dict[str, Any] = {
        "schema_version": 1,
        "status": "running",
        "evidence_kind": "synthetic_fixture",
        "publication_eligible": False,
        "joint_covariance_admitted": False,
        "case": args.case,
        "seed": args.seed,
        "repeats": args.repeats,
        "data_version": args.data_version,
        "planned_count": len(plans),
        "completed_count": 0,
        "failed_count": 0,
        "planned_runs": plans,
        "controls": dict(_CONTROLS),
        "measurement_scope": {
            "startup": (
                "main_entry_through_argument_parsing_imports_case_construction_planning_"
                "and_output_initialization"
            ),
            "full_workflow": "adapter_entry_through_serialized_completed_reader_return",
            "ld_only": "synchronized_stage_intervals",
            "memory": "rss_high_water_and_stage_boundary_pool_snapshots_not_total_cuda_peaks",
            "report_finalization_included": False,
            "workflow_kind": "independent_reference_plus_cugen_cpu_and_gpu_admission",
        },
        "held_out_invariance": [],
    }
    summary["startup_seconds"] = time.perf_counter() - startup_started
    try:
        source_load_started = time.perf_counter()
        api = load_verified_cugen_api(args.cugen_root)
        summary["source_load_seconds"] = time.perf_counter() - source_load_started
        summary["sources"] = {
            "cugen": {
                "repository": api.repository,
                "revision": api.revision,
                "allowlist_files": dict(api.allowlist_files),
                "imported_files": dict(api.imported_files),
            },
        }
        package_root = Path(__file__).resolve().parents[1]
        revision, provenance = _genomeos_revision(package_root, args.source_revision)
        summary["sources"]["genomeos"] = {
            "revision": revision,
            "revision_provenance": provenance,
            "executing_files": _source_hashes(package_root),
        }
    except Exception as error:
        _mark_all_failed(plans, error, "cugen_import")
        _write_summary(args.out, summary)
        print(str(error), file=sys.stderr)
        return 2

    for plan in plans:
        run_case = mutate_held_out(case) if plan["held_out_mutated"] else case
        source = args.out / "sources" / f"{plan['run_id']}.cugen"
        generated_at = time.perf_counter()
        try:
            api.write_cugen(
                source,
                run_case.calls,
                gidx=np.asarray([item.gidx for item in run_case.variants], dtype=np.int64),
                encoding=0,
            )
            decode_cugen_bytes(
                source.read_bytes(),
                run_case.variants,
                expected_samples=len(run_case.selection.sample_ids),
            )
            plan["source_generation_seconds"] = time.perf_counter() - generated_at
            plan["source_sha256"] = _sha256(source)
        except Exception as error:
            plan["status"] = "failed"
            plan["failure"] = _failure(error, "source_generation")

    cuda_started = time.perf_counter()
    try:
        cp, hardware = _cuda_preflight()
        summary["cuda_preflight_seconds"] = time.perf_counter() - cuda_started
        summary["hardware"] = hardware
        hardware_identity = {"controls": summary["controls"], "hardware": hardware}
        summary["hardware_environment_sha256"] = hashlib.sha256(
            json.dumps(hardware_identity, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    except Exception as error:
        summary["cuda_preflight_seconds"] = time.perf_counter() - cuda_started
        summary["hardware"] = {"available": False, "failure": _failure(error, "cuda_preflight")}
        _mark_all_failed(plans, error, "cuda_preflight")
        summary["held_out_invariance"] = _invariance(args.out, plans, args.repeats)
        _write_summary(args.out, summary)
        print(str(error), file=sys.stderr)
        return 2

    for plan in plans:
        if plan["status"] == "failed":
            continue
        run_case = mutate_held_out(case) if plan["held_out_mutated"] else case
        observer = PilotMeasurementObserver(
            synchronize=cp.cuda.runtime.deviceSynchronize,
            rss_high_water=process_rss_high_water_bytes,
            pool_snapshot=lambda: cupy_pool_snapshot(cp),
        )
        full_started = time.perf_counter()
        try:
            manifest = run_cugen_pilot(
                args.out / "sources" / f"{plan['run_id']}.cugen",
                variants=run_case.variants,
                selection=run_case.selection,
                genome_build="GRCh38",
                ploidy="autosomal_diploid",
                evidence_kind="synthetic_fixture",
                data_version=args.data_version,
                cugen_root=args.cugen_root,
                window_variants=run_case.window_variants,
                window_bp=run_case.window_bp,
                chunk_size=run_case.chunk_size,
                tile_size=run_case.tile_size,
                out=args.out / "runs" / plan["run_id"],
                source_revision=args.source_revision,
                observer=observer,
            )
            plan["full_workflow_seconds"] = time.perf_counter() - full_started
            plan["artifact_manifest_sha256"] = _sha256(manifest)
            manifest_document = json.loads(manifest.read_text(encoding="utf-8"))
            plan["numeric_validation"] = manifest_document["validation"]
            plan["stage_measurements"] = [asdict(item) for item in observer.records]
            plan["status"] = "completed"
        except Exception as error:
            plan["full_workflow_seconds"] = time.perf_counter() - full_started
            plan["stage_measurements"] = [asdict(item) for item in observer.records]
            plan["status"] = "failed"
            failure_path = args.out / "runs" / plan["run_id"] / "failure.json"
            if failure_path.is_file():
                plan["failure"] = json.loads(failure_path.read_text(encoding="utf-8"))
            else:
                plan["failure"] = _failure(error, "workflow")

    summary["held_out_invariance"] = _invariance(args.out, plans, args.repeats)
    _write_summary(args.out, summary)
    if summary["status"] != "completed":
        print("one or more planned synthetic GPU runs failed", file=sys.stderr)
        return 2
    print(args.out / "experiment.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
