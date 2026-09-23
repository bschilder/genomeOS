"""Offline zero-inflated count-preflight artifact tests (design §§7–8; issue #103)."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]


def _input(path: Path) -> Path:
    groups = [f"cohort-{index:02d}" for index in range(25) for _ in range(4)]
    frame = pd.DataFrame(
        {
            "source_record_id": [f"survey-{index:03d}" for index in range(100)],
            "cohort_id": groups,
            "ac": np.tile([0, 1, 2, 6], 25),
            "an": np.tile([100, 100, 200, 500], 25),
        }
    )
    frame.to_parquet(path, index=False)
    return path


def _run(input_path: Path, out: Path) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment["MPLCONFIGDIR"] = str(input_path.parent / ".matplotlib")
    return subprocess.run(
        [
            sys.executable,
            "scripts/preflight_zero_inflated_counts.py",
            "--observations",
            str(input_path),
            "--out",
            str(out),
            "--profile-max",
            "0.2",
            "--profile-points",
            "5",
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
    )


def test_cli_writes_a_reproducible_nonspatial_decision_artifact(tmp_path: Path) -> None:
    input_path = _input(tmp_path / "observations.parquet")
    first = tmp_path / "first"
    second = tmp_path / "second"

    completed = _run(input_path, first)
    repeated = _run(input_path, second)

    assert completed.returncode == 0, completed.stderr
    assert repeated.returncode == 0, repeated.stderr
    report = json.loads((first / "report.json").read_text())
    assert report["evidence_kind"] == "method_preflight"
    assert report["publication_eligible"] is False
    assert report["spatial_fit_performed"] is False
    assert report["environmental_covariates_used"] == []
    assert report["configuration"]["fold_strategy"] == "cohort_grouped"
    assert report["comparison"]["groups_split"] == 0
    assert set(report["decision"]["gate_checks"]) == {
        "at_least_four_of_five_folds_improve",
        "cohort_macro_log_score_improves",
        "no_positive_count_log_score_regression",
        "optimizer_starts_all_succeed",
    }
    assert report["inputs"]["observations"]["sha256"] == hashlib.sha256(
        input_path.read_bytes()
    ).hexdigest()
    assert report["limitations"]

    folds = pd.read_csv(first / "fold_metrics.csv")
    profile = pd.read_csv(first / "structural_zero_profile.csv")
    assert len(folds) == 5
    assert list(profile["structural_zero_probability"]) == pytest.approx(
        [0.0, 0.05, 0.10, 0.15, 0.20]
    )
    assert (first / "zero-inflated-count-preflight.png").stat().st_size > 10_000
    for name in ("report.json", "fold_metrics.csv", "structural_zero_profile.csv"):
        assert (first / name).read_bytes() == (second / name).read_bytes()


def test_cli_refuses_overwrite_and_missing_cohort_identity(tmp_path: Path) -> None:
    input_path = _input(tmp_path / "observations.parquet")
    out = tmp_path / "existing"
    out.mkdir()
    existing = _run(input_path, out)
    assert existing.returncode != 0
    assert "already exists" in existing.stderr

    malformed = tmp_path / "malformed.parquet"
    pd.read_parquet(input_path).drop(columns="cohort_id").to_parquet(malformed, index=False)
    failed = _run(malformed, tmp_path / "malformed-output")
    assert failed.returncode != 0
    assert "cohort_id" in failed.stderr
