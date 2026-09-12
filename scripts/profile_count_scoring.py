#!/usr/bin/env python3
"""Profile complete synthetic count diagnostics on CPU and GPU (design §7, §8; #189).

This thin adapter measures the same public ``predictive_diagnostics`` workflow with explicit
SciPy and CuPy CDF backends. It produces computational evidence only: generated inputs and all
outputs are nonpublication synthetic performance probes, never allele-frequency benchmarks.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) in sys.path:
    sys.path.remove(str(ROOT))
sys.path.insert(0, str(ROOT))

import genomeos.validation.count_recurrence as count_recurrence_module  # noqa: E402
import genomeos.validation.predictive as predictive_module  # noqa: E402
import genomeos.validation.predictive_cupy as predictive_cupy_module  # noqa: E402
from genomeos.validation.predictive import CountPredictive, predictive_diagnostics  # noqa: E402
from genomeos.validation.predictive_cupy import (  # noqa: E402
    CDF_DRAW_CHUNK_SIZE,
    CDF_ROW_CHUNK_SIZE,
    CDF_SUPPORT_CHUNK_SIZE,
    MAX_TEMPORARY_ELEMENTS,
)

RTOL = 1e-9
ATOL = 1e-11
QUANTILE_LEVELS = np.array([0.025, 0.1, 0.25, 0.5, 0.75, 0.9, 0.975])
REVISION_PATTERN = re.compile(r"[0-9a-fA-F]{40}")
SCIENCE_SOURCE_FILES = {
    "genomeos/validation/predictive.py": Path(predictive_module.__file__).resolve(),
    "genomeos/validation/count_recurrence.py": Path(count_recurrence_module.__file__).resolve(),
    "genomeos/validation/predictive_cupy.py": Path(predictive_cupy_module.__file__).resolve(),
    "scripts/profile_count_scoring.py": Path(__file__).resolve(),
}


def _positive_integer(value: str) -> int:
    try:
        result = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a positive integer") from error
    if result <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return result


def _nonnegative_integer(value: str) -> int:
    try:
        result = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a nonnegative integer") from error
    if result < 0:
        raise argparse.ArgumentTypeError("must be a nonnegative integer")
    return result


def _positive_float(value: str) -> float:
    try:
        result = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a positive finite number") from error
    if not np.isfinite(result) or result <= 0.0:
        raise argparse.ArgumentTypeError("must be a positive finite number")
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Profile exact synthetic count diagnostics on SciPy and CuPy CDF backends."
    )
    parser.add_argument("--draws", required=True, type=_positive_integer)
    parser.add_argument("--observations", required=True, type=_positive_integer)
    parser.add_argument("--an", required=True, type=_positive_integer)
    parser.add_argument("--concentration", required=True, type=_positive_float)
    parser.add_argument("--repeats", required=True, type=_positive_integer)
    parser.add_argument("--seed", required=True, type=_nonnegative_integer)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--source-revision")
    return parser


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _array_hash(arrays: dict[str, np.ndarray]) -> str:
    digest = hashlib.sha256()
    for name, array in sorted(arrays.items()):
        contiguous = np.ascontiguousarray(array)
        digest.update(name.encode())
        digest.update(str(contiguous.dtype).encode())
        digest.update(json.dumps(contiguous.shape).encode())
        digest.update(contiguous.tobytes())
    return digest.hexdigest()


def _resolved_sources() -> dict[str, str]:
    result: dict[str, str] = {}
    for relative, actual in SCIENCE_SOURCE_FILES.items():
        expected = (ROOT / relative).resolve()
        if actual != expected:
            raise ValueError(
                f"imported scoring source {relative!r} resolved outside this checkout: {actual}"
            )
        result[relative] = _sha256(actual)
    return result


def _revision(supplied: str | None) -> dict[str, str]:
    if supplied is not None:
        if REVISION_PATTERN.fullmatch(supplied) is None:
            raise ValueError("source_revision must be a 40-character hexadecimal commit")
        return {"revision": supplied.lower(), "provenance": "supplied"}
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    revision = completed.stdout.strip()
    if REVISION_PATTERN.fullmatch(revision) is None:
        raise ValueError("Git-observed source revision is unavailable or malformed")
    return {"revision": revision.lower(), "provenance": "git_observed"}


def _installed_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for distribution in importlib.metadata.distributions():
        name = distribution.metadata.get("Name")
        if name:
            versions[name] = distribution.version
    return dict(sorted(versions.items(), key=lambda item: item[0].lower()))


def _cuda_preflight() -> tuple[Any, dict[str, object], float]:
    started = time.perf_counter()
    try:
        import cupy as cp
    except (ImportError, ModuleNotFoundError) as error:
        raise RuntimeError(
            "CUDA comparison requires CuPy; install the pinned CUDA-compatible scoring environment"
        ) from error
    try:
        if cp.cuda.runtime.getDeviceCount() < 1:
            raise RuntimeError("CUDA comparison requires at least one visible CUDA device")
        device = cp.cuda.Device()
        properties = cp.cuda.runtime.getDeviceProperties(device.id)
        cp.cuda.Stream.null.synchronize()
    except cp.cuda.runtime.CUDARuntimeError as error:
        raise RuntimeError(
            "CUDA comparison requires an accessible device; check the driver and CUDA_VISIBLE_DEVICES"
        ) from error
    elapsed = time.perf_counter() - started
    name = properties["name"]
    if isinstance(name, bytes):
        name = name.decode()
    record = {
        "device_id": int(device.id),
        "device_name": str(name),
        "compute_capability": f"{properties['major']}.{properties['minor']}",
        "cuda_driver_version": int(cp.cuda.runtime.driverGetVersion()),
        "cuda_runtime_version": int(cp.cuda.runtime.runtimeGetVersion()),
    }
    return cp, record, elapsed


def _diagnostics(
    mean: np.ndarray,
    concentration: np.ndarray,
    ac: np.ndarray,
    an: np.ndarray,
    seed: int,
    backend: str,
) -> pd.DataFrame:
    predictive = CountPredictive(mean, concentration=concentration, cdf_backend=backend)
    return predictive_diagnostics(predictive, ac, an, seed=seed)


def _time_cpu(call, repeats: int) -> tuple[pd.DataFrame, float, list[float]]:
    started = time.perf_counter()
    result = call()
    cold = time.perf_counter() - started
    warm: list[float] = []
    for _ in range(repeats):
        started = time.perf_counter()
        result = call()
        warm.append(time.perf_counter() - started)
    return result, cold, warm


def _time_gpu(cp: Any, call, repeats: int) -> tuple[pd.DataFrame, float, list[float]]:
    cp.cuda.Stream.null.synchronize()
    started = time.perf_counter()
    result = call()
    cp.cuda.Stream.null.synchronize()
    cold = time.perf_counter() - started
    warm: list[float] = []
    for _ in range(repeats):
        cp.cuda.Stream.null.synchronize()
        started = time.perf_counter()
        result = call()
        cp.cuda.Stream.null.synchronize()
        warm.append(time.perf_counter() - started)
    return result, cold, warm


def _memory_probe(cp: Any, call) -> dict[str, object]:
    """Sample device-wide use separately so memory polling does not contaminate timings."""
    pool = cp.get_default_memory_pool()
    pool.free_all_blocks()
    cp.cuda.Stream.null.synchronize()
    free_before, total = cp.cuda.runtime.memGetInfo()
    reserved_before = int(pool.total_bytes())
    stop = threading.Event()
    minimum_free = [int(free_before)]

    def sample() -> None:
        while not stop.wait(0.0005):
            free, _ = cp.cuda.runtime.memGetInfo()
            minimum_free[0] = min(minimum_free[0], int(free))

    sampler = threading.Thread(target=sample, daemon=True)
    sampler.start()
    try:
        call()
        cp.cuda.Stream.null.synchronize()
        free_after_call, _ = cp.cuda.runtime.memGetInfo()
        minimum_free[0] = min(minimum_free[0], int(free_after_call))
    finally:
        stop.set()
        sampler.join()
    return {
        "measurement_run_separate_from_timing": True,
        "sampling_interval_seconds": 0.0005,
        "device_total_bytes": int(total),
        "device_used_bytes_before": int(total - free_before),
        "sampled_peak_additional_device_bytes": max(0, int(free_before) - minimum_free[0]),
        "pool_reserved_bytes_before": reserved_before,
        "pool_reserved_bytes_after": int(pool.total_bytes()),
        "pool_used_bytes_after": int(pool.used_bytes()),
        "semantics": (
            "sampled_peak_additional_device_bytes is a 0.5 ms sampled, device-wide high-water "
            "delta and may include other processes; pool_reserved_bytes is allocator reservation, "
            "not peak live memory"
        ),
    }


def _parity(
    cpu: pd.DataFrame,
    gpu: pd.DataFrame,
    cpu_samples: np.ndarray,
    gpu_samples: np.ndarray,
    *,
    cpu_quantiles: np.ndarray,
    gpu_quantiles: np.ndarray,
) -> dict[str, object]:
    exact_columns = [
        "absolute_error",
        "squared_error",
        "coverage_50",
        "interval_width_50",
        "coverage_80",
        "interval_width_80",
        "coverage_95",
        "interval_width_95",
    ]
    exact = {column: bool(np.array_equal(cpu[column], gpu[column])) for column in exact_columns}
    tolerance_columns = ["log_score", "randomized_pit"]
    within_tolerance = {
        column: bool(np.allclose(cpu[column], gpu[column], rtol=RTOL, atol=ATOL))
        for column in tolerance_columns
    }
    max_absolute = {
        column: float(np.max(np.abs(cpu[column].to_numpy() - gpu[column].to_numpy())))
        for column in tolerance_columns
    }
    sample_counts_equal = bool(np.array_equal(cpu_samples, gpu_samples))
    count_quantiles_equal = bool(np.array_equal(cpu_quantiles, gpu_quantiles))
    maximum_quantile_discrepancy = int(
        np.max(np.abs(cpu_quantiles.astype(np.int64) - gpu_quantiles.astype(np.int64)))
    )
    passed = (
        all(exact.values())
        and all(within_tolerance.values())
        and sample_counts_equal
        and count_quantiles_equal
    )
    return {
        "passed": passed,
        "rtol": RTOL,
        "atol": ATOL,
        "exact_columns": exact,
        "tolerance_columns": within_tolerance,
        "maximum_absolute_discrepancy": max_absolute,
        "seeded_sample_counts_equal": sample_counts_equal,
        "count_quantile_levels": QUANTILE_LEVELS.tolist(),
        "count_quantiles_equal": count_quantiles_equal,
        "maximum_absolute_count_quantile_discrepancy": maximum_quantile_discrepancy,
        "cpu_count_quantiles": cpu_quantiles.tolist(),
        "gpu_count_quantiles": gpu_quantiles.tolist(),
        "quantile_endpoint_policy": (
            "interval widths and coverage require exact equality, including discrete CDF ties"
        ),
    }


def run(args: argparse.Namespace) -> int:
    """Run one cold and all requested warm complete-diagnostics comparisons."""
    if args.out.exists():
        raise ValueError(f"output directory already exists: {args.out}")
    revision = _revision(args.source_revision)
    source_hashes = _resolved_sources()
    if args.an > predictive_module.MAX_COUNT:
        raise ValueError(f"an exceeds the supported maximum {predictive_module.MAX_COUNT}")

    cp, device, preflight_seconds = _cuda_preflight()
    rng = np.random.default_rng(args.seed)
    mean = rng.uniform(0.001, 0.999, size=(args.draws, args.observations))
    concentration = np.full(mean.shape, args.concentration, dtype=np.float64)
    an = np.full(args.observations, args.an, dtype=np.int64)
    ac = rng.binomial(an, np.mean(mean, axis=0)).astype(np.int64)
    input_hash = _array_hash(
        {"mean_draws": mean, "concentration": concentration, "ac": ac, "an": an}
    )

    def cpu_call() -> pd.DataFrame:
        return _diagnostics(mean, concentration, ac, an, args.seed, "scipy")

    def gpu_call() -> pd.DataFrame:
        return _diagnostics(mean, concentration, ac, an, args.seed, "cupy")

    cpu, cpu_cold, cpu_warm = _time_cpu(cpu_call, args.repeats)
    gpu, gpu_first, gpu_warm = _time_gpu(cp, gpu_call, args.repeats)
    memory = _memory_probe(cp, gpu_call)

    cpu_predictive = CountPredictive(mean, concentration=concentration, cdf_backend="scipy")
    gpu_predictive = CountPredictive(mean, concentration=concentration, cdf_backend="cupy")
    cpu_samples = cpu_predictive.sample_counts(an, seed=args.seed)
    gpu_samples = gpu_predictive.sample_counts(an, seed=args.seed)
    cpu_quantiles = cpu_predictive.quantiles(an, QUANTILE_LEVELS)
    gpu_quantiles = gpu_predictive.quantiles(an, QUANTILE_LEVELS)
    parity = _parity(
        cpu,
        gpu,
        cpu_samples,
        gpu_samples,
        cpu_quantiles=cpu_quantiles,
        gpu_quantiles=gpu_quantiles,
    )
    configuration = {
        "draws": args.draws,
        "observations": args.observations,
        "an": args.an,
        "concentration": args.concentration,
        "repeats": args.repeats,
        "seed": args.seed,
    }
    report = {
        "schema_version": 1,
        "evidence_kind": "synthetic_performance_probe",
        "publication_eligible": False,
        "interpretation": (
            "complete count-diagnostic computational comparison; not model-accuracy or "
            "allele-frequency benchmark evidence"
        ),
        "configuration": configuration,
        "input_sha256": input_hash,
        "input_dtype": "float64",
        "count_dtype": "int64",
        "source_revision": revision,
        "executed_source_sha256": source_hashes,
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "installed_distributions": _installed_versions(),
        },
        "device": device,
        "implementation_bounds": {
            "row_chunk_size": CDF_ROW_CHUNK_SIZE,
            "draw_chunk_size": CDF_DRAW_CHUNK_SIZE,
            "support_chunk_size": CDF_SUPPORT_CHUNK_SIZE,
            "maximum_temporary_log_mass_elements": MAX_TEMPORARY_ELEMENTS,
        },
        "timing": {
            "scope": (
                "each measurement constructs CountPredictive and runs full predictive_diagnostics; "
                "GPU measurements include host/device transfers and explicit synchronization"
            ),
            "imports_and_input_generation_included": False,
            "gpu_preflight_context_seconds": preflight_seconds,
            "cpu_first_seconds": cpu_cold,
            "gpu_first_scoring_seconds": gpu_first,
            "gpu_cold_context_plus_first_scoring_seconds": preflight_seconds + gpu_first,
            "cpu_warm_seconds": cpu_warm,
            "gpu_warm_seconds": gpu_warm,
        },
        "gpu_memory": memory,
        "parity": parity,
        "transfer_policy": (
            "mean/concentration and each CDF threshold batch transfer host-to-device; each CDF "
            "batch returns device-to-host; log mass, errors, sampling, and final frame stay on CPU"
        ),
    }
    args.out.mkdir(parents=True, exist_ok=False)
    args.out.joinpath("report.json").write_text(
        json.dumps(report, allow_nan=False, indent=2, sort_keys=True) + "\n"
    )
    return 0 if parity["passed"] else 1


def main() -> int:
    parser = _parser()
    args = parser.parse_args()
    try:
        return run(args)
    except (OSError, RuntimeError, TypeError, ValueError, subprocess.SubprocessError) as error:
        parser.exit(2, f"error: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
