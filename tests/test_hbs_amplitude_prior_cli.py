"""Amplitude-prior preflight artifact tests (Atlas design §§7–8; issue #103)."""

from __future__ import annotations

import hashlib
import json
import pickle
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from scripts.preflight_hbs_amplitude_prior import run

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/preflight_hbs_amplitude_prior.py"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _inputs(tmp_path: Path) -> dict[str, Path]:
    amplitude = np.array([0.1, 0.5, 1.0, 2.0])
    intercept = np.array([-5.4, -5.2, -4.8, -4.2])
    fit = SimpleNamespace(
        idata=SimpleNamespace(
            posterior={"amplitude": amplitude, "intercept": intercept}
        )
    )
    fit_path = tmp_path / "fit.pkl"
    fit_path.write_bytes(pickle.dumps({"format": 1, "fit": fit}))

    manifest_path = tmp_path / "draws-manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "available_draws": 4,
                "selected_draw_indices": [0, 1, 2, 3],
                "n_draws": 4,
                "n_cells": 4,
            }
        )
        + "\n"
    )
    nordic = np.array([0.005, 0.006, 0.010, 0.020])
    peak = np.array([0.150, 0.140, 0.120, 0.100])
    frequency_path = tmp_path / "frequency.npy"
    np.save(frequency_path, np.column_stack([nordic, nordic, peak, peak]))
    cells_path = tmp_path / "cells.parquet"
    pd.DataFrame(
        {
            "lat": [60.0, 65.0, 2.0, 4.0],
            "lon": [10.0, 20.0, 15.0, 20.0],
            "population": [1.0, 3.0, 2.0, 2.0],
            "post_median": [0.01, 0.01, 0.09, 0.10],
            "support": ["interpolated", "observed", "observed", "interpolated"],
        }
    ).to_parquet(cells_path, index=False)

    preregistration_path = tmp_path / "preregistration.json"
    preregistration_path.write_text(
        json.dumps(
            {
                "schema": "hbs-amplitude-prior-sensitivity-preregistration-v1",
                "issue": 103,
                "method": "self_normalized_importance_reweighting",
                "original_prior": {"family": "HalfNormal", "scale": 1.0},
                "candidate_scales": [1.0, 0.5],
                "draw_alignment": "selected_draw_indices",
                "diagnostics": {
                    "minimum_effective_sample_size": 1.0,
                    "maximum_single_normalized_weight": 1.0,
                    "nordic_supported_box": {
                        "latitude_degrees": [55.0, 72.0],
                        "longitude_degrees": [4.0, 32.0],
                        "support_in": ["observed", "interpolated"],
                    },
                    "endemic_peak_cells": {
                        "baseline_post_median_at_least": 0.08,
                        "support_in": ["observed", "interpolated"],
                    },
                    "summaries": [
                        "amplitude",
                        "intercept",
                        "invlogit_intercept",
                        "population_weighted_nordic_frequency",
                        "population_weighted_endemic_peak_frequency",
                        "endemic_minus_nordic_frequency",
                    ],
                    "posterior_summary": "weighted median and central 50/95 percent intervals",
                },
                "decision_rule": "frozen test rule",
                "inputs": {
                    "fit_sha256": _sha256(fit_path),
                    "draw_manifest_sha256": _sha256(manifest_path),
                    "frequency_draws_sha256": _sha256(frequency_path),
                    "cells_sha256": _sha256(cells_path),
                },
                "claims_excluded": ["full_refit_equivalence", "model_promotion"],
                "environmental_covariates_used": False,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    return {
        "fit": fit_path,
        "manifest": manifest_path,
        "frequency": frequency_path,
        "cells": cells_path,
        "preregistration": preregistration_path,
    }


def test_run_writes_bound_deterministic_result_and_geographic_figure(
    tmp_path: Path,
) -> None:
    inputs = _inputs(tmp_path)
    first = tmp_path / "first"
    second = tmp_path / "second"

    run(out=first, **inputs)
    run(out=second, **inputs)

    result = json.loads((first / "result.json").read_text())
    assert result["schema"] == "hbs-amplitude-prior-sensitivity-result-v1"
    assert result["scientific_acceptance"] is False
    assert result["publication_eligible"] is False
    assert result["environmental_covariates_used"] is False
    assert result["strata"]["nordic_supported_cells"] == 2
    assert result["strata"]["endemic_peak_cells"] == 2
    assert result["any_candidate_advances_to_full_refit"] is True
    assert result["inputs"]["fit"]["sha256"] == _sha256(inputs["fit"])
    assert result["sources"]["science_module"]["sha256"] == _sha256(
        ROOT / "genomeos/validation/amplitude_prior_sensitivity.py"
    )
    assert (first / "amplitude-prior-sensitivity.png").read_bytes().startswith(
        b"\x89PNG\r\n\x1a\n"
    )
    assert (first / "result.json").read_bytes() == (second / "result.json").read_bytes()


def test_run_refuses_hash_mismatch_without_creating_output(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path)
    preregistration = json.loads(inputs["preregistration"].read_text())
    preregistration["inputs"]["cells_sha256"] = "0" * 64
    inputs["preregistration"].write_text(json.dumps(preregistration) + "\n")
    out = tmp_path / "out"

    with pytest.raises(ValueError, match="cells SHA-256"):
        run(out=out, **inputs)

    assert not out.exists()


def test_cli_executes_this_checkout_and_refuses_overwrite(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path)
    out = tmp_path / "cli-out"
    command = [
        sys.executable,
        str(SCRIPT),
        "--fit",
        str(inputs["fit"]),
        "--draw-manifest",
        str(inputs["manifest"]),
        "--frequency-draws",
        str(inputs["frequency"]),
        "--cells",
        str(inputs["cells"]),
        "--preregistration",
        str(inputs["preregistration"]),
        "--out",
        str(out),
    ]

    first = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    second = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)

    assert first.returncode == 0, first.stderr
    assert json.loads(first.stdout)["result"] == str(out / "result.json")
    assert second.returncode != 0
    assert "already exists" in second.stderr
