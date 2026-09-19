"""Offline HbS parity adapter uses the benchmark's declared reference year (design §8, §9)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import h3
import numpy as np
import pandas as pd
import pytest

from genomeos.reference.piel2013 import REFERENCE_YEAR, national_estimates

ROOT = Path(__file__).resolve().parents[1]


def test_real_parity_run_aligns_spatial_weights_to_piel_2010(tmp_path: Path) -> None:
    cell_ids = np.array(
        [
            h3.latlng_to_cell(5.56, -0.205, 4),
            h3.latlng_to_cell(9.0765, 7.3986, 4),
        ]
    )
    draws_path = tmp_path / "draws.npz"
    np.savez(
        draws_path,
        h3_index=cell_ids,
        support=np.array(["observed", "observed"]),
        draws=np.full((20, 2), 0.1),
    )
    population_path = tmp_path / "weights.csv"
    pd.DataFrame(
        {"h3_index": cell_ids, "population": [13.0, 29.0]}
    ).to_csv(population_path, index=False)
    out = tmp_path / "rollup.csv"

    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT)
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/national_estimates.py",
            "--draws",
            str(draws_path),
            "--population-cells",
            str(population_path),
            "--population-source",
            "test-grid",
            "--population-version",
            "2020",
            "--metric",
            "ss",
            "--out",
            str(out),
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr

    result = pd.read_csv(out).set_index("iso3")
    published = national_estimates().set_index("iso3")
    for iso3, raw_weight in {"GHA": 13.0, "NGA": 29.0}.items():
        target = published.loc[iso3, "population_thousands"] * 1_000.0
        birth_rate = published.loc[iso3, "crude_birth_rate"]
        assert result.loc[iso3, "point"] == pytest.approx(target * birth_rate * 0.1**2)
        assert result.loc[iso3, "population_weight_total"] == raw_weight
        assert result.loc[iso3, "target_population"] == target
        assert result.loc[iso3, "population_scale_factor"] == pytest.approx(target / raw_weight)
        assert result.loc[iso3, "population_target_year"] == REFERENCE_YEAR == 2010
    assert (result["population_weight_source"] == "test-grid@2020").all()
    assert result["population_target_source"].str.contains("Piel").all()


def test_real_parity_run_requires_versioned_population_provenance(tmp_path: Path) -> None:
    cell = h3.latlng_to_cell(5.56, -0.205, 4)
    draws_path = tmp_path / "draws.npz"
    np.savez(
        draws_path,
        h3_index=np.array([cell]),
        support=np.array(["observed"]),
        draws=np.full((5, 1), 0.1),
    )
    population_path = tmp_path / "weights.csv"
    pd.DataFrame({"h3_index": [cell], "population": [13.0]}).to_csv(
        population_path, index=False
    )

    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT)
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/national_estimates.py",
            "--draws",
            str(draws_path),
            "--population-cells",
            str(population_path),
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
    )
    assert completed.returncode != 0
    assert "--population-source and --population-version" in completed.stderr
