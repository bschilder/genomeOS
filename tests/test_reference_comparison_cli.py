"""Synthetic complete-matrix CLI tests (paired-report design Matrix CLI)."""

from __future__ import annotations

import hashlib
import importlib.util
import itertools
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from reference_comparison_synthetic import publication, refresh

from genomeos.validation.reference_b0h_artifacts import json_bytes

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "compare_reference_counts.py"
STAGES = ("technical_qc_4117", "paper_ancestry_exclusion_4094")
KINDS = ("called", "quality")
SEEDS = (42, 43, 44)
RHOS = (9, 4)
MATRIX = tuple(itertools.product(STAGES, KINDS, SEEDS, RHOS))


def _configured_publication(
    *, stage: str, kind: str, seed: int, rho: int | None = None, failed=(), infeasible=()
):
    files = publication(heterogeneity=rho is not None, rho=rho or 9, failed=failed, infeasible=infeasible)
    manifest = json.loads(files["manifest.json"])
    manifest["configuration"].update(cohort_stage=stage, count_kind=kind, seed=seed)
    manifest["seeds"]["root"] = seed
    files["manifest.json"] = json_bytes(manifest)
    splits = json.loads(files["splits.json"])
    splits["configuration"] = manifest["configuration"]
    refresh(files, "splits.json", json_bytes(splits))
    return files


def _write_publication(directory: Path, files: dict[str, bytes]) -> None:
    directory.mkdir(parents=True)
    for name, data in files.items():
        (directory / name).write_bytes(data)


def _update_configuration(directory: Path, **updates: object) -> None:
    files = {path.name: path.read_bytes() for path in directory.iterdir()}
    manifest = json.loads(files["manifest.json"])
    manifest["configuration"].update(updates)
    if "seed" in updates:
        manifest["seeds"]["root"] = updates["seed"]
    files["manifest.json"] = json_bytes(manifest)
    splits = json.loads(files["splits.json"])
    splits["configuration"] = manifest["configuration"]
    refresh(files, "splits.json", json_bytes(splits))
    for name, data in files.items():
        (directory / name).write_bytes(data)


def _matrix_spec(base: Path, *, unavailable: tuple[str, str, int, int] | None = None):
    records = []
    for stage, kind, seed, rho in MATRIX:
        b0 = Path("publications") / "b0" / stage / kind / str(seed)
        b0h = Path("publications") / "b0h" / stage / kind / str(seed) / str(rho)
        if not (base / b0).exists():
            _write_publication(
                base / b0,
                _configured_publication(stage=stage, kind=kind, seed=seed),
            )
        if (stage, kind, seed, rho) != unavailable:
            _write_publication(
                base / b0h,
                _configured_publication(stage=stage, kind=kind, seed=seed, rho=rho),
            )
        records.append(
            {
                "cohort_stage": stage,
                "count_kind": kind,
                "seed": seed,
                "rho_prior_beta": rho,
                "b0_directory": b0.as_posix(),
                "b0h_directory": b0h.as_posix(),
            }
        )
    specification = {"schema_version": 1, "pairs": records}
    path = base / "pairs.json"
    path.write_bytes(json_bytes(specification))
    return path, specification


def _run(pairs: Path, out: Path, *, cwd: Path | None = None):
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT)
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--pairs", str(pairs), "--out", str(out)],
        cwd=cwd,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def test_complete_matrix_resolves_relative_paths_and_writes_deterministic_report(tmp_path):
    specification_dir = tmp_path / "specification"
    specification_dir.mkdir()
    pairs, specification = _matrix_spec(specification_dir)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    first_out, second_out = tmp_path / "first", tmp_path / "second"

    first = _run(pairs, first_out, cwd=elsewhere)
    second = _run(pairs, second_out, cwd=elsewhere)

    assert first.returncode == second.returncode == 0, first.stderr
    assert {path.name for path in first_out.iterdir()} == {"report.json", "manifest.json"}
    assert (first_out / "report.json").read_bytes() == (second_out / "report.json").read_bytes()
    report = json.loads((first_out / "report.json").read_bytes())
    assert report["schema_version"] == 1
    assert report["matrix_complete"] is True
    assert report["available_pair_count"] == 24
    assert report["not_available_pair_count"] == 0
    assert [
        (row["cohort_stage"], row["count_kind"], row["seed"], row["rho_prior_beta"])
        for row in report["pairs"]
    ] == list(MATRIX)
    assert all(row["status"] == "available" and row["comparison"] for row in report["pairs"])
    manifest = json.loads((first_out / "manifest.json").read_bytes())
    specification_bytes = pairs.read_bytes()
    report_bytes = (first_out / "report.json").read_bytes()
    assert manifest["input_specification"] == {
        "sha256": hashlib.sha256(specification_bytes).hexdigest(),
        "size_bytes": len(specification_bytes),
    }
    assert manifest["output_files"]["report.json"] == {
        "sha256": hashlib.sha256(report_bytes).hexdigest(),
        "size_bytes": len(report_bytes),
    }
    assert len(manifest["consumed_publications"]) == 24
    assert all(
        set(row["publication_fingerprints"]) == {"b0", "b0h"} for row in manifest["consumed_publications"]
    )
    assert manifest["package_versions"]["numpy"]
    assert manifest["package_versions"]["pandas"]
    assert set(manifest["executed_source_sha256"]) == {
        "genomeos/validation/benchmark.py",
        "genomeos/validation/reference_b0h_artifacts.py",
        "genomeos/validation/reference_comparison.py",
        "genomeos/validation/reference_comparison_inputs.py",
        "scripts/compare_reference_counts.py",
    }
    assert specification["pairs"][0]["b0_directory"].startswith("publications/")


@pytest.mark.parametrize("absent", ["b0", "b0h", "both"])
def test_absent_directory_retains_expected_identity_and_exits_two(tmp_path, absent):
    missing = ("paper_ancestry_exclusion_4094", "quality", 44, 4)
    pairs, specification = _matrix_spec(tmp_path, unavailable=missing if absent != "b0" else None)
    declaration = specification["pairs"][-1]
    if absent != "b0h":
        (tmp_path / declaration["b0_directory"]).rename(tmp_path / "retained-b0")
    out = tmp_path / "out"

    completed = _run(pairs, out)

    assert completed.returncode == 2, completed.stderr
    report = json.loads((out / "report.json").read_bytes())
    assert report["matrix_complete"] is False
    # B0 is reused by both rho tracks; its absence affects two requested pairs.
    unavailable = 1 if absent == "b0h" else 2
    assert report["available_pair_count"] == 24 - unavailable
    assert report["not_available_pair_count"] == unavailable
    identity_fields = ("cohort_stage", "count_kind", "seed", "rho_prior_beta")
    row = next(row for row in report["pairs"] if tuple(row[k] for k in identity_fields) == missing)
    assert row["status"] == "not_available"
    assert row["comparison"] is None
    assert (
        row["reason"]
        == {
            "b0": "b0 publication directory is absent",
            "b0h": "b0h publication directory is absent",
            "both": "b0 and b0h publication directories are absent",
        }[absent]
    )
    manifest = json.loads((out / "manifest.json").read_bytes())
    assert manifest["matrix_complete"] is False
    assert len(manifest["consumed_publications"]) == (23 if absent == "both" else 24)
    retained = [
        row for row in manifest["consumed_publications"] if tuple(row[k] for k in identity_fields) == missing
    ]
    if absent == "both":
        assert retained == []
    else:
        present = "b0h" if absent == "b0" else "b0"
        source = (tmp_path / declaration[present + "_directory"] / "manifest.json").read_bytes()
        assert retained[0]["publication_fingerprints"] == {
            present: {"sha256": hashlib.sha256(source).hexdigest(), "size_bytes": len(source)},
        }


@pytest.mark.parametrize("state", ["failed", "infeasible", "no_common_completed"])
def test_all_present_incomplete_comparison_publishes_evidence_and_exits_two(tmp_path, state):
    pairs, specification = _matrix_spec(tmp_path)
    declaration = specification["pairs"][-1]
    directory = tmp_path / declaration["b0h_directory"]
    directory.rename(tmp_path / "retained-complete-b0h")
    failed = tuple(range(5)) if state == "no_common_completed" else ((4,) if state == "failed" else ())
    files = _configured_publication(
        stage="paper_ancestry_exclusion_4094",
        kind="quality",
        seed=44,
        rho=4,
        failed=failed,
        infeasible=(4,) if state == "infeasible" else (),
    )
    _write_publication(directory, files)
    out = tmp_path / "out"
    result = _run(pairs, out)
    assert result.returncode == 2, result.stderr
    report = json.loads((out / "report.json").read_bytes())
    manifest = json.loads((out / "manifest.json").read_bytes())
    assert report["available_pair_count"] == 24
    assert report["not_available_pair_count"] == 0
    assert all(row["status"] == "available" for row in report["pairs"])
    assert report["matrix_complete"] is manifest["matrix_complete"] is False
    comparison = report["pairs"][-1]["comparison"]
    assert comparison["comparison_complete"] is False
    assert comparison["full_pair"]["available"] is False
    assert comparison["full_pair"]["differences"] is None
    conditional = comparison["completed_fold_conditional"]
    assert conditional["available"] is (state != "no_common_completed")
    assert len(conditional["split_ids"]) == (0 if state == "no_common_completed" else 4)
    if state != "no_common_completed":
        assert conditional["differences"]["mae"]["value"] == pytest.approx(-0.025)
    else:
        assert conditional["reason"] == "no_common_completed_folds"
    final_fold = comparison["fold_outcomes"][-1]["b0h"]
    assert final_fold["status"] == ("infeasible" if state == "infeasible" else "failed")
    assert final_fold["failure_reason"] == (
        "synthetic preflight refusal" if state == "infeasible" else "ValueError: synthetic scoring failure"
    )
    assert len(comparison["fold_outcomes"]) == 5
    assert comparison["counts"]["failed_rows_b0h"] == (7 if state == "no_common_completed" else 1)
    assert len(manifest["consumed_publications"]) == 24


@pytest.mark.parametrize("present", ["b0", "b0h"])
@pytest.mark.parametrize("problem", ["corrupt", "identity"])
def test_present_publication_is_still_validated_without_counterpart(tmp_path, present, problem):
    pairs, specification = _matrix_spec(tmp_path)
    declaration = specification["pairs"][-1]
    absent = "b0h" if present == "b0" else "b0"
    (tmp_path / declaration[absent + "_directory"]).rename(tmp_path / "retained-counterpart")
    if present == "b0":
        # Both B0H tracks share this B0; isolate the absent-counterpart path in both.
        (tmp_path / specification["pairs"][-2]["b0h_directory"]).rename(tmp_path / "retained-other-track")
    directory = tmp_path / declaration[present + "_directory"]
    if problem == "corrupt":
        (directory / "predictions.tsv").write_bytes(b"corrupt\n")
    else:
        _update_configuration(directory, count_kind="called")
    out = tmp_path / "out"
    result = _run(pairs, out)
    assert result.returncode == 2
    assert ("publication" if problem == "corrupt" else "configuration") in result.stderr
    assert not out.exists()


@pytest.mark.parametrize("mode", ["duplicate", "missing"])
def test_matrix_declarations_must_be_exactly_complete(tmp_path, mode):
    pairs, specification = _matrix_spec(tmp_path)
    if mode == "duplicate":
        specification["pairs"][-1] = specification["pairs"][0]
    else:
        specification["pairs"].pop()
    pairs.write_bytes(json_bytes(specification))
    out = tmp_path / "out"

    completed = _run(pairs, out)

    assert completed.returncode == 2
    assert "matrix" in completed.stderr.lower()
    assert not out.exists()


@pytest.mark.parametrize("field", ["cohort_stage", "count_kind", "seed", "rho_prior_beta"])
def test_declared_identity_must_match_publication_configuration(tmp_path, field):
    pairs, specification = _matrix_spec(tmp_path)
    record = specification["pairs"][0]
    replacement = {
        "cohort_stage": "paper_ancestry_exclusion_4094",
        "count_kind": "quality",
        "seed": 43,
        "rho_prior_beta": 4,
    }[field]
    sides = ("b0h_directory",) if field == "rho_prior_beta" else ("b0_directory", "b0h_directory")
    for side in sides:
        _update_configuration(tmp_path / record[side], **{field: replacement})
    out = tmp_path / "out"

    completed = _run(pairs, out)

    assert completed.returncode == 2
    assert field in completed.stderr
    assert "configuration" in completed.stderr
    assert not out.exists()


@pytest.mark.parametrize("mode", ["partial", "corrupt"])
def test_present_invalid_publication_is_a_hard_error_without_output(tmp_path, mode):
    pairs, specification = _matrix_spec(tmp_path)
    directory = tmp_path / specification["pairs"][0]["b0h_directory"]
    if mode == "partial":
        (directory / "predictions.tsv").rename(directory / "predictions.tsv.held")
    else:
        (directory / "predictions.tsv").write_bytes(b"corrupt\n")
    out = tmp_path / "out"

    completed = _run(pairs, out)

    assert completed.returncode == 2
    assert "publication" in completed.stderr.lower()
    assert not out.exists()


def test_existing_output_is_refused_without_mutation(tmp_path):
    pairs, _ = _matrix_spec(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    marker = out / "retain.txt"
    marker.write_text("retain\n")

    completed = _run(pairs, out)

    assert completed.returncode == 2
    assert "already exists" in completed.stderr
    assert marker.read_text() == "retain\n"
    assert {path.name for path in out.iterdir()} == {"retain.txt"}


def test_manifest_write_failure_preserves_partial_output(tmp_path, monkeypatch):
    specification_dir = tmp_path / "specification"
    specification_dir.mkdir()
    pairs, _ = _matrix_spec(specification_dir)
    spec = importlib.util.spec_from_file_location("paired_runner", SCRIPT)
    assert spec is not None and spec.loader is not None
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    out = tmp_path / "out"
    args = runner._parser().parse_args(["--pairs", str(pairs), "--out", str(out)])
    original = Path.write_bytes

    def interrupted(path: Path, data: bytes):
        if path.name == "manifest.json":
            raise OSError("synthetic manifest interruption")
        return original(path, data)

    monkeypatch.setattr(Path, "write_bytes", interrupted)
    with pytest.raises(OSError, match="synthetic manifest interruption"):
        runner.run(args)
    assert (out / "report.json").exists()
    assert not (out / "manifest.json").exists()
