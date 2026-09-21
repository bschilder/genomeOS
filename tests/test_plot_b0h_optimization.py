"""Deterministic reporting for the B0H scheduler optimization (design §§5, 12)."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/plot_b0h_optimization.py"


def _plotter():
    spec = importlib.util.spec_from_file_location("b0h_optimization_plot", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _campaign(tmp_path: Path) -> Path:
    configurations = []
    elapsed = {1: (400.0, 420.0), 2: (210.0, 220.0), 3: (150.0, 155.0), 4: (145.0, 148.0)}
    for workers, repetitions in elapsed.items():
        for repetition, seconds in enumerate(repetitions, start=1):
            identity = f"workers-{workers}-repeat-{repetition}"
            configurations.append(
                {"identity": identity, "workers": workers, "repetition": repetition}
            )
            candidate = tmp_path / "candidates" / identity
            candidate.mkdir(parents=True)
            (candidate / "telemetry-summary.json").write_text(
                json.dumps(
                    {
                        "format": "b0h_scheduler_telemetry_summary",
                        "version": "1",
                        "elapsed_seconds": seconds,
                        "exit_status": 0,
                        "sample_count": 10,
                        "gpu_utilization_mean_percent": 20.0 + workers * 10,
                        "gpu_utilization_p95_percent": 30.0 + workers * 10,
                        "gpu_utilization_max_percent": 40.0 + workers * 10,
                        "gpu_memory_peak_mib": 1000.0 * workers,
                        "gpu_power_mean_watts": 100.0,
                        "process_cpu_mean_percent": 100.0 * workers,
                        "process_cpu_max_percent": 120.0 * workers,
                        "process_rss_peak_bytes": 2_000_000_000 * workers,
                        "process_threads_peak": 8 * workers,
                        "host_load_1m_peak": float(workers),
                        "host_memory_used_peak_bytes": 3_000_000_000 * workers,
                        "read_bytes_final": 100,
                        "write_bytes_final": 200,
                    }
                )
                + "\n"
            )
            (candidate / "receipt.json").write_text(
                json.dumps(
                    {
                        "status": "terminal_all_runs_verified",
                        "workers": workers,
                        "all_planned_runs_accounted": True,
                        "results": [
                            {
                                "run_id": f"run-{index}",
                                "verification": "passed",
                                "comparison_complete": True,
                                "exit_status": 0,
                            }
                            for index in range(4)
                        ],
                    }
                )
                + "\n"
            )
    (tmp_path / "campaign.json").write_text(
        json.dumps(
            {
                "format": "b0h-scheduler-optimization",
                "version": "optimization-v1",
                "source_sha": "a" * 40,
                "workers": [1, 2, 3, 4],
                "repetitions": [1, 2],
                "configurations": configurations,
            }
        )
        + "\n"
    )
    (tmp_path / "hardware-attestation.json").write_text(
        json.dumps(
            {
                "gpu": {"name": "NVIDIA A100-SXM4-80GB", "memory_total_mib": 81920},
                "packages": {"jax": "0.11.1", "pymc": "6.3.2"},
            }
        )
        + "\n"
    )
    return tmp_path


def _calibration_campaign(tmp_path: Path) -> Path:
    configurations = []
    elapsed = {1: (400.0, 420.0), 2: (210.0, 220.0), 3: (150.0, 155.0), 4: (145.0, 148.0)}
    science = [{"case_id": "study=0/case=0", "stages": [{"outcome": "evidence"}]}]
    science_raw = json.dumps(science, sort_keys=True, separators=(",", ":")).encode("ascii")
    science_sha256 = __import__("hashlib").sha256(science_raw).hexdigest()
    for workers, repetitions in elapsed.items():
        for repetition, seconds in enumerate(repetitions, start=1):
            identity = f"workers-{workers}-repeat-{repetition}"
            configurations.append(
                {"identity": identity, "workers": workers, "repetition": repetition}
            )
            candidate = tmp_path / "candidates" / identity
            result = candidate / "result"
            result.mkdir(parents=True)
            (result / "result.json").write_text(
                json.dumps(
                    {
                        "format": "b0h-calibration-optimization-result",
                        "version": "1",
                        "identity": identity,
                        "workers": workers,
                        "case_count": 16,
                        "elapsed_seconds": seconds - 2,
                        "science_sha256": science_sha256,
                        "science": science,
                        "store_inventory": [["study=0/case=0", [f"digest-{workers}"]]],
                    }
                )
                + "\n"
            )
            (candidate / "telemetry-summary.json").write_text(
                json.dumps(
                    {
                        "format": "b0h_scheduler_telemetry_summary",
                        "version": "1",
                        "elapsed_seconds": seconds,
                        "exit_status": 0,
                        "sample_count": 10,
                        "gpu_utilization_mean_percent": 20.0 + workers * 10,
                        "gpu_utilization_p95_percent": 30.0 + workers * 10,
                        "gpu_utilization_max_percent": 40.0 + workers * 10,
                        "gpu_memory_peak_mib": 1000.0 * workers,
                        "gpu_power_mean_watts": 100.0,
                        "process_cpu_mean_percent": 100.0 * workers,
                        "process_cpu_max_percent": 120.0 * workers,
                        "process_rss_peak_bytes": 2_000_000_000 * workers,
                        "process_threads_peak": 8 * workers,
                        "host_load_1m_peak": float(workers),
                        "host_memory_used_peak_bytes": 3_000_000_000 * workers,
                        "read_bytes_final": 100,
                        "write_bytes_final": 200,
                    }
                )
                + "\n"
            )
    (tmp_path / "campaign-result.json").write_text(
        json.dumps(
            {
                "format": "b0h-calibration-optimization-campaign-result",
                "version": "1",
                "source_sha": "b" * 40,
                "completed": configurations,
                "science_sha256": science_sha256,
            }
        )
        + "\n"
    )
    (tmp_path / "hardware-attestation.json").write_text(
        json.dumps({"gpu": {"name": "NVIDIA A100-SXM4-80GB"}}) + "\n"
    )
    return tmp_path


def test_report_selects_smallest_configuration_on_balanced_frontier(tmp_path):
    report = _plotter().build_report(_campaign(tmp_path), cost_per_hour=1.59)
    assert report["source_sha"] == "a" * 40
    assert report["case_count_per_run"] == 4
    assert report["selection"]["workers"] == 3
    assert report["selection"]["speedup_vs_serial"] >= 2
    assert report["selection"]["within_best_throughput_fraction"] >= 0.9
    assert report["selection"]["cost_per_case_usd"] <= report["serial"]["cost_per_case_usd"]
    assert [row["workers"] for row in report["aggregates"]] == [1, 2, 3, 4]
    assert all(row["repetition_count"] == 2 for row in report["aggregates"])


def test_report_refuses_incomplete_or_unverified_receipt(tmp_path):
    campaign = _campaign(tmp_path)
    receipt = campaign / "candidates/workers-2-repeat-1/receipt.json"
    value = json.loads(receipt.read_bytes())
    value["results"][0]["verification"] = "failed"
    receipt.write_text(json.dumps(value) + "\n")
    with pytest.raises(ValueError, match="verified terminal receipt"):
        _plotter().build_report(campaign, cost_per_hour=1.59)


def test_report_accepts_verified_refusals_but_requires_matching_classifications(tmp_path):
    campaign = _campaign(tmp_path)
    for receipt in campaign.glob("candidates/*/receipt.json"):
        value = json.loads(receipt.read_bytes())
        for result in value["results"]:
            result["exit_status"] = 2
            result["comparison_complete"] = False
        receipt.write_text(json.dumps(value) + "\n")
    report = _plotter().build_report(campaign, cost_per_hour=1.59)
    assert report["case_classifications"] == [
        {"comparison_complete": False, "exit_status": 2} for _ in range(4)
    ]

    mismatched = campaign / "candidates/workers-4-repeat-2/receipt.json"
    value = json.loads(mismatched.read_bytes())
    value["results"][0]["exit_status"] = 0
    value["results"][0]["comparison_complete"] = True
    mismatched.write_text(json.dumps(value) + "\n")
    with pytest.raises(ValueError, match="classifications differ"):
        _plotter().build_report(campaign, cost_per_hour=1.59)


def test_report_corrects_negative_cpu_transition_deltas_from_bound_raw_samples(tmp_path):
    campaign = _campaign(tmp_path)
    candidate = campaign / "candidates/workers-1-repeat-1"
    (candidate / "telemetry.jsonl").write_text(
        "\n".join(
            json.dumps({"cpu_percent": value}) for value in (None, -100.0, 100.0, 200.0)
        )
        + "\n"
    )
    report = _plotter().build_report(campaign, cost_per_hour=1.59)
    run = next(row for row in report["runs"] if row["identity"] == "workers-1-repeat-1")
    assert run["process_cpu_mean_percent"] == pytest.approx(100.0)
    assert run["process_cpu_max_percent"] == pytest.approx(200.0)
    assert run["cpu_transition_correction"] == {
        "method": "clamp_negative_aggregate_jiffy_deltas_to_zero",
        "negative_interval_count": 1,
        "observed_interval_count": 3,
    }
    assert "telemetry_samples" in run["input_files"]


def test_calibration_report_rehashes_science_and_selects_frontier(tmp_path):
    campaign = _calibration_campaign(tmp_path)
    report = _plotter().build_calibration_report(campaign, cost_per_hour=1.59)
    assert report["format"] == "b0h-calibration-optimization-report"
    assert report["source_sha"] == "b" * 40
    assert report["case_count_per_run"] == 16
    assert report["selection"]["workers"] == 3
    assert report["scientific_equivalence"]["all_science_sha256_equal"] is True


def test_calibration_report_refuses_tampered_or_different_science(tmp_path):
    campaign = _calibration_campaign(tmp_path)
    result = campaign / "candidates/workers-2-repeat-1/result/result.json"
    value = json.loads(result.read_bytes())
    value["science"][0]["stages"][0]["outcome"] = "failure"
    result.write_text(json.dumps(value) + "\n")
    with pytest.raises(ValueError, match="scientific digest"):
        _plotter().build_calibration_report(campaign, cost_per_hour=1.59)


def test_cli_writes_reviewable_figure_and_refuses_overwrite(tmp_path):
    campaign = _campaign(tmp_path / "campaign")
    out = tmp_path / "out"
    command = [
        sys.executable,
        str(SCRIPT),
        "--campaign",
        str(campaign),
        "--cost-per-hour",
        "1.59",
        "--out",
        str(out),
    ]
    first = subprocess.run(command, capture_output=True, text=True, check=False)
    assert first.returncode == 0, first.stderr
    report = json.loads((out / "report.json").read_bytes())
    assert report["selection"]["workers"] == 3
    assert (out / "optimization.png").stat().st_size > 20_000
    second = subprocess.run(command, capture_output=True, text=True, check=False)
    assert second.returncode == 2
    assert "already exists" in second.stderr
