"""Offline covariate-registry inspection CLI tests (design §7; issue #290)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from genomeos.covariates.registry import default_registry_bytes

REPO = Path(__file__).parents[1]
SCRIPT = REPO / "scripts" / "inspect_covariate_asset.py"


def _run(*arguments: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(REPO)
    return subprocess.run(
        [sys.executable, str(SCRIPT), *arguments],
        cwd=REPO,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def test_list_is_deterministic_and_reports_candidate_state():
    first = _run("--list")
    second = _run("--list")

    assert first.returncode == 0, first.stderr
    assert first.stdout == second.stdout
    assert json.loads(first.stdout) == [
        {
            "admission_status": "candidate_only",
            "asset_id": "GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL",
            "asset_key": "google_satellite_embedding_v1_annual",
            "commercial_compatibility": "compatible",
            "dataset_version": "1.1",
            "extraction_status": "not_run",
        }
    ]


def test_show_emits_the_validated_canonical_asset_record():
    result = _run("--asset-key", "google_satellite_embedding_v1_annual")

    assert result.returncode == 0, result.stderr
    record = json.loads(result.stdout)
    assert record["band_names"] == [f"A{index:02d}" for index in range(64)]
    assert record["commercial_use"]["finding"] == "explicitly_open"
    assert record["extraction_receipt_sha256"] is None


def test_unknown_asset_is_a_clear_nonzero_refusal():
    result = _run("--asset-key", "missing")

    assert result.returncode != 0
    assert result.stdout == ""
    assert "unknown covariate asset" in result.stderr


def test_an_invalid_external_registry_is_refused(tmp_path):
    payload = json.loads(default_registry_bytes())
    payload["assets"][0]["available_years"] = [2017, 2019]
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")

    result = _run("--registry", str(path), "--list")

    assert result.returncode != 0
    assert "continuous annual interval" in result.stderr


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ((), "one of the arguments --list --asset-key is required"),
        (("--list", "--asset-key", "x"), "not allowed with argument --list"),
    ],
)
def test_exactly_one_inspection_mode_is_required(arguments, message):
    result = _run(*arguments)

    assert result.returncode != 0
    assert message in result.stderr
