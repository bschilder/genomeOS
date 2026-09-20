"""B1 local-count artifact runner integration (design §§4–8, 12; #307)."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "benchmark_local_count.py"
FIXTURES = ROOT / "tests" / "fixtures" / "local_count"


def _command(out: Path) -> list[str]:
    return [
        sys.executable,
        str(SCRIPT),
        "--observations",
        str(FIXTURES / "observations.tsv"),
        "--assignments",
        str(FIXTURES / "assignments.tsv"),
        "--dependencies",
        str(FIXTURES / "dependencies.tsv"),
        "--data-version",
        "fixture-v1",
        "--bandwidth-km",
        "300",
        "--bandwidth-km",
        "800",
        "--prior-alpha",
        "1",
        "--prior-beta",
        "9",
        "--buffer-km",
        "100",
        "--minimum-inner-emission-fraction",
        "0.5",
        "--minimum-training-observations",
        "1",
        "--minimum-effective-alleles",
        "1",
        "--posterior-draws",
        "64",
        "--query-chunk-size",
        "3",
        "--seed",
        "42",
        "--evidence-kind",
        "synthetic_fixture",
        "--analysis-role",
        "synthetic_validation",
        "--assignment-review-status",
        "reviewed",
        "--dependency-review-status",
        "not_checked",
        "--out",
        str(out),
    ]


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT)
    return subprocess.run(command, capture_output=True, text=True, env=environment, check=False)


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text())


def test_runner_writes_source_neutral_nonpublication_evidence(tmp_path):
    output = tmp_path / "run"

    completed = _run(_command(output))

    assert completed.returncode == 0, completed.stderr
    assert sorted(path.name for path in output.iterdir()) == [
        "bandwidth_selection.tsv",
        "fold_status.tsv",
        "inventory.json",
        "manifest.json",
        "predictions.tsv",
        "summary.json",
        "support.tsv",
    ]
    manifest = _json(output / "manifest.json")
    assert manifest["model"] == {
        "model_id": "B1-local-count",
        "name": "compact_triweight_spherical_weighted_count_power_posterior",
        "kernel": "compact_triweight",
        "distance": "great_circle_footprint_edge_km",
        "posterior_semantics": "weighted_count_generalized_bayes_power_posterior",
        "environmental_covariates": False,
        "source_specific_features": False,
    }
    assert manifest["publication_eligible"] is False
    assert manifest["analysis_role"] == "synthetic_validation"
    assert manifest["qualification"] == {
        "assignment_review_status": "reviewed",
        "dependency_review_status": "not_checked",
        "scientific_promotion_decision": "not_made",
    }
    assert manifest["configuration"]["candidate_bandwidths_km"] == [300.0, 800.0]
    assert len(manifest["code_revision"]) == 40
    assert set(manifest["science_source_sha256"]) == {
        "genomeos/observations/schema.py",
        "genomeos/validation/benchmark.py",
        "genomeos/validation/local_count.py",
        "genomeos/validation/local_count_benchmark.py",
        "genomeos/validation/local_count_selection.py",
        "genomeos/validation/local_count_evidence.py",
        "genomeos/validation/predictive.py",
        "genomeos/validation/splits.py",
        "scripts/benchmark_local_count.py",
    }
    for name, record in manifest["output_files"].items():
        contents = (output / name).read_bytes()
        assert record == {
            "sha256": hashlib.sha256(contents).hexdigest(),
            "size_bytes": len(contents),
        }

    support = pd.read_csv(output / "support.tsv", sep="\t")
    predictions = pd.read_csv(output / "predictions.tsv", sep="\t")
    selection = pd.read_csv(output / "bandwidth_selection.tsv", sep="\t")
    statuses = pd.read_csv(output / "fold_status.tsv", sep="\t", keep_default_na=False)
    assert len(support) == 8
    assert set(support["status"]) == {"emitted"}
    assert len(predictions) == 8
    assert set(predictions["bandwidth_km"]) == {800.0}
    assert len(selection) == 8
    assert set(selection["bandwidth_km"]) == {300.0, 800.0}
    assert set(selection["inner_failure_reasons"]) == {"[]"}
    assert statuses["expected_test_ids"].str.startswith("[").all()
    summary = _json(output / "summary.json")["benchmark"]
    assert summary["requested_observation_count"] == 8
    assert summary["emitted_observation_count"] == 8
    assert summary["excluded_fraction"] == 0.0


def test_outputs_are_byte_reproducible(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"

    first_run = _run(_command(first))
    second_run = _run(_command(second))

    assert first_run.returncode == second_run.returncode == 0
    assert {path.name: path.read_bytes() for path in first.iterdir()} == {
        path.name: path.read_bytes() for path in second.iterdir()
    }


def test_existing_output_and_unsorted_candidate_grid_are_refused(tmp_path):
    output = tmp_path / "existing"
    output.mkdir()

    existing = _run(_command(output))
    unsorted_command = _command(tmp_path / "unsorted")
    first = unsorted_command.index("300")
    second = unsorted_command.index("800")
    unsorted_command[first], unsorted_command[second] = (
        unsorted_command[second],
        unsorted_command[first],
    )
    unsorted = _run(unsorted_command)

    assert existing.returncode == 2
    assert "already exists" in existing.stderr
    assert unsorted.returncode == 2
    assert "strictly increasing" in unsorted.stderr


def test_writer_revalidates_results_before_creating_output(tmp_path, monkeypatch):
    import runpy
    from dataclasses import replace

    import pytest

    runner = runpy.run_path(str(SCRIPT))
    run = runner["run"]
    evaluate = run.__globals__["evaluate_local_count_benchmark"]

    def contradictory(plan):
        result = evaluate(plan)
        support = result.support.copy()
        support["status"] = "unknown"
        return replace(result, support=support)

    monkeypatch.setitem(run.__globals__, "evaluate_local_count_benchmark", contradictory)
    output = tmp_path / "invalid"
    args = runner["_parser"]().parse_args(_command(output)[2:])
    with pytest.raises(ValueError, match="support status"):
        run(args)
    assert not output.exists()
