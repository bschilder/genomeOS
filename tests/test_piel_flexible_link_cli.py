"""Offline Piel-link preflight artifact tests (design §7, §8; issue #103)."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def _input(path: Path) -> Path:
    frame = pd.DataFrame(
        {
            "source_record_id": [f"survey-{index}" for index in range(12)],
            "ac": [0, 0, 1, 2, 4, 8, 12, 18, 25, 35, 50, 70],
            "an": [50, 100, 80, 120, 100, 150, 120, 150, 180, 200, 250, 300],
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
            "scripts/preflight_piel_flexible_link.py",
            "--observations",
            str(input_path),
            "--diagnostic-latent",
            "-4.6",
            "--out",
            str(out),
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
    )


def test_cli_writes_a_reproducible_nonpublication_comparison(tmp_path: Path) -> None:
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
    assert set(report["arms"]) == {
        "piel_printed_2013",
        "uniform_binomial_conjugate",
    }
    assert set(report["stukel_arms"]) == set(report["arms"])
    assert report["published_piel_arm"]["formula"].startswith("-1.48556762*x^3")
    assert report["published_piel_arm"]["quantile_orientation"] == -1.0
    assert report["primary_source"]["published_coefficients_page"] == 15
    assert all(
        arm["positive_branch_fitted"] is False
        for arm in report["stukel_arms"].values()
    )
    assert report["configuration"]["normal_fit"] == "plug_in_mle"
    assert report["configuration"]["plotting_position"] == "hazen_rank_average"
    assert report["diagnostics"]["latent"] == [-4.6]
    assert set(report["diagnostics"]["stukel_aligned_frequency"]) == set(report["arms"])
    assert report["inputs"]["observations"]["sha256"] == hashlib.sha256(
        input_path.read_bytes()
    ).hexdigest()
    assert report["limitations"]

    curves = pd.read_csv(first / "link_curves.csv")
    for column in [
        "inverse_logit",
        "piel_published_2013",
        "piel_printed_2013",
        "uniform_binomial_conjugate",
        "stukel_piel_printed_2013",
        "stukel_uniform_binomial_conjugate",
    ]:
        assert np.all(np.diff(curves[column]) > 0)
    quantiles = pd.read_csv(first / "smoothed_frequency_quantiles.csv")
    printed = quantiles["smoothing_rule"] == "piel_printed_2013"
    assert quantiles.loc[printed, "published_piel_link_frequency"].notna().all()
    assert quantiles.loc[~printed, "published_piel_link_frequency"].isna().all()
    assert (first / "piel-flexible-link-preflight.png").stat().st_size > 10_000
    assert (first / "report.json").read_bytes() == (second / "report.json").read_bytes()
    assert (first / "link_curves.csv").read_bytes() == (
        second / "link_curves.csv"
    ).read_bytes()


def test_cli_refuses_overwrite_and_malformed_input(tmp_path: Path) -> None:
    input_path = _input(tmp_path / "observations.parquet")
    out = tmp_path / "existing"
    out.mkdir()
    existing = _run(input_path, out)
    assert existing.returncode != 0
    assert "already exists" in existing.stderr

    malformed = tmp_path / "malformed.parquet"
    pd.DataFrame({"ac": [0] * 8}).to_parquet(malformed, index=False)
    bad = _run(malformed, tmp_path / "bad")
    assert bad.returncode != 0
    assert "missing required columns" in bad.stderr
    assert not (tmp_path / "bad").exists()
