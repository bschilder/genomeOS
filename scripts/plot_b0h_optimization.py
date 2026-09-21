#!/usr/bin/env python3
"""Summarize and plot the B0H scheduler campaign (design §§5, 12; issue #337).

The input is performance evidence only. Every included configuration must have a terminal
controller receipt proving that the same set of scientific runs completed and passed publication
verification. The report selects a bounded worker count from repeated full-workflow measurements;
it never changes or interprets the scientific outputs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402


def _read_object(path: Path) -> dict[str, object]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise ValueError(f"JSON document must contain an object: {path}")
    return value


def _file_record(path: Path) -> dict[str, object]:
    return {
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "size_bytes": path.stat().st_size,
    }


def _number(value: object, *, name: str, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric")
    result = float(value)
    if not math.isfinite(result) or (positive and result <= 0):
        raise ValueError(f"{name} must be finite{' and positive' if positive else ''}")
    return result


def _verified_classifications(
    receipt: dict[str, object], *, workers: int
) -> list[dict[str, object]]:
    results = receipt.get("results")
    verified = (
        receipt.get("status") == "terminal_all_runs_verified"
        and receipt.get("workers") == workers
        and receipt.get("all_planned_runs_accounted") is True
        and isinstance(results, list)
        and bool(results)
        and all(
            isinstance(result, dict)
            and result.get("verification") == "passed"
            and isinstance(result.get("comparison_complete"), bool)
            and result.get("exit_status") in (0, 2)
            and (result.get("exit_status") == 0) is result.get("comparison_complete")
            for result in results
        )
    )
    if not verified:
        raise ValueError("every configuration requires a verified terminal receipt")
    identities = [result.get("run_id") for result in results]
    if any(not isinstance(identity, str) or not identity for identity in identities):
        raise ValueError("verified terminal receipt has an invalid run identity")
    if len(identities) != len(set(identities)):
        raise ValueError("verified terminal receipt repeats a run identity")
    return [
        {
            "exit_status": result["exit_status"],
            "comparison_complete": result["comparison_complete"],
        }
        for result in results
    ]


def _run_record(root: Path, config: dict[str, object], cost_per_hour: float) -> dict[str, object]:
    identity = config.get("identity")
    workers = config.get("workers")
    repetition = config.get("repetition")
    if (
        not isinstance(identity, str)
        or not identity
        or isinstance(workers, bool)
        or not isinstance(workers, int)
        or workers < 1
        or isinstance(repetition, bool)
        or not isinstance(repetition, int)
        or repetition < 1
    ):
        raise ValueError("campaign contains an invalid configuration")
    candidate = root / "candidates" / identity
    telemetry_path = candidate / "telemetry-summary.json"
    receipt_path = candidate / "receipt.json"
    telemetry = _read_object(telemetry_path)
    receipt = _read_object(receipt_path)
    if (
        telemetry.get("format") != "b0h_scheduler_telemetry_summary"
        or telemetry.get("version") != "1"
        or telemetry.get("exit_status") != 0
    ):
        raise ValueError(f"configuration has invalid telemetry: {identity}")
    classifications = _verified_classifications(receipt, workers=workers)
    case_count = len(classifications)
    elapsed = _number(telemetry.get("elapsed_seconds"), name="elapsed_seconds", positive=True)
    numeric = {
        name: _number(telemetry.get(name), name=name, positive=name.endswith("_peak_bytes"))
        for name in (
            "gpu_utilization_mean_percent",
            "gpu_utilization_p95_percent",
            "gpu_utilization_max_percent",
            "gpu_memory_peak_mib",
            "gpu_power_mean_watts",
            "process_cpu_mean_percent",
            "process_cpu_max_percent",
            "process_rss_peak_bytes",
            "process_threads_peak",
            "host_load_1m_peak",
            "host_memory_used_peak_bytes",
            "read_bytes_final",
            "write_bytes_final",
        )
    }
    return {
        "identity": identity,
        "workers": workers,
        "repetition": repetition,
        "case_count": case_count,
        "case_classifications": classifications,
        "elapsed_seconds": elapsed,
        "throughput_cases_per_hour": case_count * 3600.0 / elapsed,
        "cost_per_case_usd": cost_per_hour * elapsed / 3600.0 / case_count,
        **numeric,
        "input_files": {
            "telemetry_summary": _file_record(telemetry_path),
            "controller_receipt": _file_record(receipt_path),
        },
    }


def _aggregate(workers: int, rows: list[dict[str, object]]) -> dict[str, object]:
    def values(name: str) -> list[float]:
        return [float(row[name]) for row in rows]

    throughput = values("throughput_cases_per_hour")
    elapsed = values("elapsed_seconds")
    cost = values("cost_per_case_usd")
    return {
        "workers": workers,
        "repetition_count": len(rows),
        "elapsed_seconds": statistics.median(elapsed),
        "elapsed_seconds_range": [min(elapsed), max(elapsed)],
        "throughput_cases_per_hour": statistics.median(throughput),
        "throughput_range": [min(throughput), max(throughput)],
        "cost_per_case_usd": statistics.median(cost),
        "gpu_utilization_mean_percent": statistics.median(
            values("gpu_utilization_mean_percent")
        ),
        "gpu_utilization_p95_percent": statistics.median(
            values("gpu_utilization_p95_percent")
        ),
        "gpu_memory_peak_mib": max(values("gpu_memory_peak_mib")),
        "process_cpu_mean_percent": statistics.median(values("process_cpu_mean_percent")),
        "process_rss_peak_bytes": max(values("process_rss_peak_bytes")),
        "process_threads_peak": max(values("process_threads_peak")),
        "host_memory_used_peak_bytes": max(values("host_memory_used_peak_bytes")),
    }


def build_report(campaign_root: Path, *, cost_per_hour: float) -> dict[str, object]:
    """Verify repeated terminal runs and choose the bounded balanced-frontier configuration."""
    cost_per_hour = _number(cost_per_hour, name="cost_per_hour", positive=True)
    campaign_path = campaign_root / "campaign.json"
    hardware_path = campaign_root / "hardware-attestation.json"
    campaign = _read_object(campaign_path)
    hardware = _read_object(hardware_path)
    configurations = campaign.get("configurations")
    source_sha = campaign.get("source_sha")
    if (
        campaign.get("format") != "b0h-scheduler-optimization"
        or not isinstance(configurations, list)
        or not configurations
        or not isinstance(source_sha, str)
        or len(source_sha) != 40
        or any(character not in "0123456789abcdef" for character in source_sha)
    ):
        raise ValueError("campaign identity is invalid")
    runs = [_run_record(campaign_root, config, cost_per_hour) for config in configurations]
    identities = [row["identity"] for row in runs]
    if len(identities) != len(set(identities)):
        raise ValueError("campaign repeats a configuration identity")
    case_counts = {row["case_count"] for row in runs}
    if len(case_counts) != 1:
        raise ValueError("configurations do not contain the same case count")
    classifications = runs[0]["case_classifications"]
    if any(row["case_classifications"] != classifications for row in runs[1:]):
        raise ValueError("verified case classifications differ across configurations")
    by_workers: dict[int, list[dict[str, object]]] = {}
    for row in runs:
        by_workers.setdefault(int(row["workers"]), []).append(row)
    if 1 not in by_workers:
        raise ValueError("campaign has no serial oracle")
    aggregates = [_aggregate(workers, by_workers[workers]) for workers in sorted(by_workers)]
    serial = next(row for row in aggregates if row["workers"] == 1)
    serial_throughput = float(serial["throughput_cases_per_hour"])
    serial_cost = float(serial["cost_per_case_usd"])
    best_throughput = max(float(row["throughput_cases_per_hour"]) for row in aggregates)
    for row in aggregates:
        row["speedup_vs_serial"] = float(row["throughput_cases_per_hour"]) / serial_throughput
        row["within_best_throughput_fraction"] = (
            float(row["throughput_cases_per_hour"]) / best_throughput
        )
        row["cost_ratio_vs_serial"] = float(row["cost_per_case_usd"]) / serial_cost
        row["meets_acceptance"] = (
            row["speedup_vs_serial"] >= 2.0
            and row["within_best_throughput_fraction"] >= 0.9
            and row["cost_ratio_vs_serial"] <= 1.0 + 1e-12
        )
    eligible = [row for row in aggregates if row["meets_acceptance"]]
    selection: dict[str, object]
    if eligible:
        chosen = min(eligible, key=lambda row: int(row["workers"]))
        selection = {"status": "accepted", **chosen}
    else:
        selection = {
            "status": "no_configuration_met_acceptance",
            "workers": None,
            "required_speedup": 2.0,
            "required_best_throughput_fraction": 0.9,
            "maximum_cost_ratio_vs_serial": 1.0,
        }
    return {
        "format": "b0h-scheduler-optimization-report",
        "version": "1",
        "analysis_role": "performance_only_not_scientific_evidence",
        "source_sha": source_sha,
        "case_count_per_run": next(iter(case_counts)),
        "case_classifications": classifications,
        "cost_per_hour_usd": cost_per_hour,
        "hardware": hardware,
        "input_files": {
            "campaign": _file_record(campaign_path),
            "hardware_attestation": _file_record(hardware_path),
        },
        "runs": runs,
        "aggregates": aggregates,
        "serial": serial,
        "selection": selection,
    }


def build_figure(report: dict[str, object]):
    """Render throughput, utilization, cost, and memory from the verified report."""
    rows = report["aggregates"]
    workers = np.asarray([row["workers"] for row in rows], dtype=float)
    throughput = np.asarray([row["throughput_cases_per_hour"] for row in rows], dtype=float)
    ranges = np.asarray([row["throughput_range"] for row in rows], dtype=float)
    gpu = np.asarray([row["gpu_utilization_mean_percent"] for row in rows], dtype=float)
    gpu_p95 = np.asarray([row["gpu_utilization_p95_percent"] for row in rows], dtype=float)
    cost = np.asarray([row["cost_per_case_usd"] for row in rows], dtype=float)
    memory = np.asarray([row["process_rss_peak_bytes"] for row in rows], dtype=float) / 2**30
    selected = report["selection"].get("workers")
    colors = ["#167D9A" if value == selected else "#8AA8B5" for value in workers]

    figure, axes = plt.subplots(1, 3, figsize=(13.2, 4.2), constrained_layout=True)
    axes[0].errorbar(
        workers,
        throughput,
        yerr=np.vstack((throughput - ranges[:, 0], ranges[:, 1] - throughput)),
        fmt="none",
        ecolor="#56636A",
        capsize=4,
        zorder=1,
    )
    axes[0].scatter(workers, throughput, s=75, c=colors, zorder=2)
    axes[0].axhline(2 * throughput[workers == 1][0], color="#B44B4B", linestyle="--")
    axes[0].set(title="End-to-end throughput", xlabel="Concurrent case workers", ylabel="Cases / hour")

    axes[1].plot(workers, gpu, marker="o", color="#167D9A", label="mean")
    axes[1].plot(workers, gpu_p95, marker="s", color="#D17A22", label="95th percentile")
    axes[1].set(
        title="A100 utilization",
        xlabel="Concurrent case workers",
        ylabel="GPU utilization (%)",
        ylim=(0, 105),
    )
    axes[1].legend(frameon=False)

    axes[2].bar(workers - 0.16, cost, width=0.32, color="#7B5EA7", label="cost / case")
    axes[2].set(title="Resource trade-off", xlabel="Concurrent case workers", ylabel="USD / case")
    memory_axis = axes[2].twinx()
    memory_axis.bar(workers + 0.16, memory, width=0.32, color="#C89055", label="peak RSS")
    memory_axis.set_ylabel("Peak process RSS (GiB)")
    handles = axes[2].patches[:1] + memory_axis.patches[:1]
    axes[2].legend(handles, ["cost / case", "peak RSS"], frameon=False, loc="upper left")
    for axis in axes:
        axis.set_xticks(workers)
        axis.grid(axis="y", alpha=0.2)
    figure.suptitle(
        "B0H scheduler optimization — performance-only, verified scientific receipts",
        fontsize=12,
        fontweight="bold",
    )
    return figure


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", required=True, type=Path)
    parser.add_argument("--cost-per-hour", required=True, type=float)
    parser.add_argument("--out", required=True, type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        if args.out.exists():
            raise FileExistsError(f"output directory already exists: {args.out}")
        report = build_report(args.campaign, cost_per_hour=args.cost_per_hour)
        args.out.mkdir(parents=True)
        report_path = args.out / "report.json"
        figure_path = args.out / "optimization.png"
        report_path.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")
        figure = build_figure(report)
        figure.savefig(figure_path, dpi=180, metadata={"Software": "genomeOS"})
        plt.close(figure)
        receipt = {
            "format": "b0h-scheduler-optimization-render-receipt",
            "version": "1",
            "executed_source": _file_record(Path(__file__)),
            "output_files": {
                "report.json": _file_record(report_path),
                "optimization.png": _file_record(figure_path),
            },
        }
        (args.out / "render-receipt.json").write_text(
            json.dumps(receipt, sort_keys=True, indent=2) + "\n"
        )
    except (FileExistsError, OSError, ValueError) as error:
        print(f"FATAL: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
