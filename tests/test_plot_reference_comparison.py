"""Replay paired plot values and visible states independently (design §§5, 8, 12)."""

from __future__ import annotations

import hashlib
import importlib.util
import itertools
import json
import subprocess
import sys
from pathlib import Path

import pytest
from reference_comparison_figure_synthetic import write_example_inputs

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/plot_reference_comparison.py"
METRICS = {
    "mae": "frequency",
    "mean_log_score": "natural_log",
    **{f"coverage_{level}": "percentage_points" for level in (50, 80, 95)},
    **{f"interval_width_{level}": "frequency" for level in (50, 80, 95)},
}


@pytest.fixture(scope="module")
def report_path(tmp_path_factory):
    base = tmp_path_factory.mktemp("synthetic_plot")
    pairs = write_example_inputs(base / "inputs")
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/compare_reference_counts.py"),
            "--pairs",
            str(pairs),
            "--out",
            str(base / "report"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2, result.stderr
    return base / "report/report.json"


def _plotter():
    assert SCRIPT.exists(), "The paired report plotting adapter has not been implemented"
    spec = importlib.util.spec_from_file_location("paired_plot", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_all24_artists_replay_report_values_states_and_units(report_path):
    plotter = _plotter()
    report = json.loads(report_path.read_bytes())
    figure, receipt = plotter.build_figure(report)
    expected_ids = set(
        itertools.product(
            ("technical_qc_4117", "paper_ancestry_exclusion_4094"),
            ("called", "quality"),
            (42, 43, 44),
            (9, 4),
        )
    )
    assert len(receipt["rows"]) == 24
    assert {
        tuple(row[k] for k in ("cohort_stage", "count_kind", "seed", "rho_prior_beta"))
        for row in receipt["rows"]
    } == expected_ids
    source = {
        (r["cohort_stage"], r["count_kind"], r["seed"], r["rho_prior_beta"]): r for r in report["pairs"]
    }
    artists = {a.get_gid(): a for a in figure.findobj() if a.get_gid()}
    observed_states, special = set(), set()
    for row in receipt["rows"]:
        identity = tuple(row[k] for k in ("cohort_stage", "count_kind", "seed", "rho_prior_beta"))
        original = source[identity]
        label = artists[row["label_artist"]].get_text()
        assert all(str(part) in label for part in identity[:3])
        assert f"rho_prior_beta={identity[3]}" in label
        if original["status"] == "not_available":
            expected_state, section = "not_available", None
            assert original["reason"] in label
        else:
            comparison = original["comparison"]
            if comparison["full_pair"]["available"]:
                expected_state, section = "complete", comparison["full_pair"]
            elif comparison["completed_fold_conditional"]["available"]:
                expected_state, section = "conditional", comparison["completed_fold_conditional"]
            else:
                expected_state, section = "failed", None
            if expected_state != "complete":
                for side in ("b0", "b0h"):
                    failures = sum(f[side]["status"] != "completed" for f in comparison["fold_outcomes"])
                    assert f"{side} failed/infeasible={failures}" in label
        observed_states.add(expected_state)
        assert row["status"] == expected_state
        assert expected_state in label
        for metric, unit in METRICS.items():
            record = row["metrics"][metric]
            assert record["unit"] == unit
            assert unit in artists[record["axis_artist"]].get_xlabel()
            assert "B0H minus B0" in artists[record["axis_artist"]].get_xlabel()
            expected = (
                section["differences"][metric]
                if section
                else {
                    "value": None,
                    "reason": expected_state,
                    "unit": unit,
                }
            )
            assert {k: record[k] for k in expected} == expected
            artist = artists[record["artist"]]
            value = expected["value"]
            if isinstance(value, (int, float)):
                assert list(artist.get_xdata()) == [value]
                assert float(artists[record["value_label_artist"]].get_text()) == pytest.approx(
                    value, abs=5e-5
                )
            else:
                special.add(value if value else expected["reason"])
                assert record["display"] == artist.get_text()
                assert (str(value) if value else expected["reason"]) in artist.get_text()
    assert observed_states == {"complete", "conditional", "failed", "not_available"}
    assert {"Infinity", "-Infinity", "both_negative_infinity"} <= special
    assert "SYNTHETIC" in figure._suptitle.get_text()
    plotter.plt.close(figure)


def test_cli_retains_hashes_and_refuses_overwrite(report_path, tmp_path):
    _plotter()
    command = [sys.executable, str(SCRIPT), "--report", str(report_path), "--out", str(tmp_path / "out")]
    first = subprocess.run(command, capture_output=True, text=True, check=False)
    assert first.returncode == 0, first.stderr
    out = tmp_path / "out"
    receipt = json.loads((out / "receipt.json").read_bytes())
    for path, actual in (
        (report_path, receipt["input_report"]),
        (out / "comparison.png", receipt["output_files"]["comparison.png"]),
        (SCRIPT, receipt["executed_source"]),
    ):
        assert actual == {
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "size_bytes": path.stat().st_size,
        }
    before = {p.name: p.read_bytes() for p in out.iterdir()}
    second = subprocess.run(command, capture_output=True, text=True, check=False)
    assert second.returncode == 2 and "already exists" in second.stderr
    assert before == {p.name: p.read_bytes() for p in out.iterdir()}


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "unit", "direction", "nonfinite"])
def test_malformed_plot_input_is_refused(report_path, tmp_path, mutation):
    _plotter()
    report = json.loads(report_path.read_bytes())
    if mutation == "missing":
        report["pairs"].pop()
    elif mutation == "duplicate":
        report["pairs"][-1] = report["pairs"][0]
    elif mutation == "direction":
        report["difference_direction"] = "B0_minus_B0H"
    else:
        metric = report["pairs"][0]["comparison"]["full_pair"]["differences"]["mae"]
        metric["unit" if mutation == "unit" else "value"] = (
            "percentage_points" if mutation == "unit" else float("nan")
        )
    source = tmp_path / "report.json"
    source.write_text(json.dumps(report))
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--report", str(source), "--out", str(tmp_path / "out")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert not (tmp_path / "out").exists()


def test_committed_report_is_exact_synthetic_cli_output(report_path):
    committed = ROOT / "docs/figures/reference_comparison_synthetic_report.json"
    assert committed.read_bytes() == report_path.read_bytes()
    report = json.loads(committed.read_bytes())
    differences = report["pairs"][0]["comparison"]["full_pair"]["differences"]
    assert differences["mae"]["value"] == pytest.approx(-0.025)
    assert differences["mean_log_score"]["value"] == 0
    assert differences["coverage_95"]["value"] == 100
    assert differences["interval_width_95"]["value"] == pytest.approx(0.2)
