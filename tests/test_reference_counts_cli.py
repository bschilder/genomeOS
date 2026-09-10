"""Reference-count benchmark CLI integration (design §§ 5, 7, 8; #189)."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "benchmark_reference_counts.py"
FIXTURES = ROOT / "tests" / "fixtures" / "reference_counts"


def _command(out: Path, *, counts: Path | None = None, dependencies: Path | None = None, folds=2):
    return [
        sys.executable,
        str(SCRIPT),
        "--counts", str(counts or FIXTURES / "counts.tsv"),
        "--dependencies", str(dependencies or FIXTURES / "dependencies.json"),
        "--source-release", "synthetic-v1",
        "--cohort-stage", "synthetic",
        "--count-kind", "quality",
        "--evidence-role", "synthetic",
        "--prior-alpha", "1",
        "--prior-beta", "1",
        "--folds", str(folds),
        "--seed", "42",
        "--out", str(out),
    ]


def _run(command: list[str], *, pythonpath: Path = ROOT):
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(pythonpath)
    return subprocess.run(command, capture_output=True, text=True, env=environment, check=False)


def _json(path: Path):
    return json.loads(path.read_text())


def test_complete_run_writes_reproducible_artifact_contract(tmp_path):
    first_out = tmp_path / "first"
    second_out = tmp_path / "second"

    first = _run(_command(first_out))
    second = _run(_command(second_out))

    assert first.returncode == second.returncode == 0, first.stderr
    names = {
        "splits.json", "row_status.tsv", "predictions.tsv", "posteriors.tsv",
        "summary.json", "manifest.json",
    }
    assert {path.name for path in first_out.iterdir()} == names
    for name in names:
        assert (first_out / name).read_bytes() == (second_out / name).read_bytes()
    summary = _json(first_out / "summary.json")
    assert summary["target"] == "reference_panel_within_resource"
    assert summary["joint_prediction_supported"] is False
    assert summary["comparison_complete"] is True
    rows = pd.read_csv(first_out / "row_status.tsv", sep="\t", keep_default_na=False)
    inputs = pd.read_csv(FIXTURES / "counts.tsv", sep="\t", keep_default_na=False)
    assert len(rows) == len(inputs)
    assert set(rows.record_id) == set(inputs.record_id)
    assert rows.loc[rows.record_id == "f:v", "status"].item() == "unavailable_denominator"
    predictions = pd.read_csv(first_out / "predictions.tsv", sep="\t")
    scored = rows.loc[rows.status == "scored", ["split_id", "record_id"]]
    assert set(map(tuple, scored.to_records(index=False))) == set(
        map(tuple, predictions.loc[:, ["split_id", "source_record_id"]].to_records(index=False))
    )
    assert summary["scored_observation_count"] == len(predictions)
    manifest = _json(first_out / "manifest.json")
    assert manifest["input_files"] == {
        "counts": {
            "sha256": hashlib.sha256((FIXTURES / "counts.tsv").read_bytes()).hexdigest(),
            "size_bytes": len((FIXTURES / "counts.tsv").read_bytes()),
        },
        "dependencies": {
            "sha256": hashlib.sha256(
                (FIXTURES / "dependencies.json").read_bytes()
            ).hexdigest(),
            "size_bytes": len((FIXTURES / "dependencies.json").read_bytes()),
        },
    }
    for name, record in manifest["output_files"].items():
        contents = (first_out / name).read_bytes()
        assert record == {"sha256": hashlib.sha256(contents).hexdigest(), "size_bytes": len(contents)}
    expected_sources = {
        "genomeos/observations/schema.py",
        "genomeos/validation/benchmark.py",
        "genomeos/validation/count_baseline.py",
        "genomeos/validation/predictive.py",
        "genomeos/validation/reference_counts.py",
        "scripts/benchmark_reference_counts.py",
    }
    assert set(manifest["science_source_sha256"]) == expected_sources
    for relative, digest in manifest["science_source_sha256"].items():
        assert digest == hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
    split_sequence, pit_parent = np.random.SeedSequence(42).spawn(2)
    expected_split = int(split_sequence.generate_state(1, dtype=np.uint32)[0])
    expected_pit = tuple(
        int(child.generate_state(1, dtype=np.uint32)[0])
        for child in pit_parent.spawn(2)
    )
    assert manifest["seeds"] == {
        "root": 42,
        "split": expected_split,
        "pit_by_fold": {
            "reference-0": expected_pit[0],
            "reference-1": expected_pit[1],
        },
    }
    splits = _json(first_out / "splits.json")
    assert splits["split_seed"] == expected_split
    assert tuple(fold["pit_seed"] for fold in splits["folds"]) == expected_pit


def test_five_folds_retain_missing_only_infeasible_fold(tmp_path):
    out = tmp_path / "run"
    completed = _run(_command(out, folds=5))

    assert completed.returncode == 2
    summary = _json(out / "summary.json")
    assert summary["comparison_complete"] is False
    assert summary["split_counts"]["infeasible"] >= 1
    rows = pd.read_csv(out / "row_status.tsv", sep="\t", keep_default_na=False)
    assert rows.loc[rows.record_id == "f:v", "status"].item() == "unavailable_denominator"
    assert len(rows) == 6


def test_runner_bootstraps_checkout_and_preserves_literal_labels(tmp_path):
    counts = tmp_path / "counts.tsv"
    counts.write_text((FIXTURES / "counts.tsv").read_text().replace("a:v", "NA").replace("\ta\t", "\t001\t"))
    dependencies = tmp_path / "dependencies.json"
    dependencies.write_text('{"edges": [["001", "b"]], "qualification": "synthetic"}\n')
    conflicting = tmp_path / "wrong"
    (conflicting / "genomeos").mkdir(parents=True)
    (conflicting / "genomeos" / "__init__.py").write_text('raise RuntimeError("wrong checkout")\n')

    completed = _run(
        _command(tmp_path / "out", counts=counts, dependencies=dependencies),
        pythonpath=conflicting,
    )

    assert completed.returncode == 0, completed.stderr
    statuses = pd.read_csv(tmp_path / "out" / "row_status.tsv", sep="\t", dtype=str, keep_default_na=False)
    assert "NA" in set(statuses.record_id)
    splits = _json(tmp_path / "out" / "splits.json")
    assert any("001" in fold["test_groups"] for fold in splits["folds"])


@pytest.mark.parametrize(
    ("contents", "message"),
    [
        (
            "record_id\tvariant_id\tgroup_id\tregion_id\tvariant_group\tac\tan\n"
            "a\tv\tg\tr\tb\t1.0\t4\n",
            "base-10 integer",
        ),
        (
            "record_id\tvariant_id\tgroup_id\tregion_id\tvariant_group\tac\tan\n"
            "a\tv\tg\tr\tb\t1\t+4x\n",
            "base-10 integer",
        ),
        (
            "record_id\tvariant_id\tgroup_id\tregion_id\tvariant_group\tac\n"
            "a\tv\tg\tr\tb\t1\n",
            "columns must be exactly",
        ),
    ],
)
def test_invalid_count_structure_publishes_no_artifacts(tmp_path, contents, message):
    counts = tmp_path / "bad.tsv"
    counts.write_text(contents)
    out = tmp_path / "out"

    completed = _run(_command(out, counts=counts))

    assert completed.returncode != 0
    assert message in completed.stderr
    assert not out.exists()


@pytest.mark.parametrize(
    "row",
    [
        "discarded\ta:v\tv\ta\tr\tblock\t1\t4",
        "a:v\tv\ta\tr\tblock\t1",
    ],
)
def test_count_rows_require_exact_quote_aware_field_count(tmp_path, row):
    counts = tmp_path / "bad.tsv"
    counts.write_text(
        "record_id\tvariant_id\tgroup_id\tregion_id\tvariant_group\tac\tan\n"
        f"{row}\n"
    )
    out = tmp_path / "out"

    completed = _run(_command(out, counts=counts))

    assert completed.returncode != 0
    assert "exactly 7 fields" in completed.stderr
    assert not out.exists()


def test_quoted_literal_tokens_are_parsed_as_one_logical_field(tmp_path):
    counts = tmp_path / "quoted.tsv"
    counts.write_text(
        "record_id\tvariant_id\tgroup_id\tregion_id\tvariant_group\tac\tan\n"
        '"a:v"\tv\ta\t"r\t1"\tblock\t1\t4\n'
        "b:v\tv\tb\tr2\tblock\t2\t4\n"
    )
    dependencies = tmp_path / "dependencies.json"
    dependencies.write_text('{"edges": [], "qualification": "synthetic"}\n')
    out = tmp_path / "out"

    completed = _run(_command(out, counts=counts, dependencies=dependencies))

    assert completed.returncode == 0, completed.stderr
    predictions = pd.read_csv(out / "predictions.tsv", sep="\t", keep_default_na=False)
    assert "r\t1" in set(predictions.region_id)


@pytest.mark.parametrize(
    "document",
    [
        {"edges": [["a", "unknown"]], "qualification": "synthetic"},
        {"edges": [["a", "b"]]},
        {"edges": [], "qualification": ""},
        {"edges": [], "qualification": "synthetic", "extra": 1},
    ],
)
def test_invalid_dependencies_publish_no_artifacts(tmp_path, document):
    dependency_path = tmp_path / "bad.json"
    dependency_path.write_text(json.dumps(document))
    out = tmp_path / "out"

    completed = _run(_command(out, dependencies=dependency_path))

    assert completed.returncode != 0
    assert not out.exists()


def test_output_reuse_is_refused_without_modifying_artifacts(tmp_path):
    out = tmp_path / "run"
    assert _run(_command(out)).returncode == 0
    before = {path.name: path.read_bytes() for path in out.iterdir()}

    repeated = _run(_command(out))

    assert repeated.returncode != 0
    assert before == {path.name: path.read_bytes() for path in out.iterdir()}


@pytest.mark.parametrize(("option", "value"), [("--source-release", ""), ("--cohort-stage", "")])
def test_blank_source_metadata_publishes_no_artifacts(tmp_path, option, value):
    out = tmp_path / "run"
    command = _command(out)
    command[command.index(option) + 1] = value

    completed = _run(command)

    assert completed.returncode != 0
    assert not out.exists()


def test_missing_training_variant_and_all_missing_tests_remain_accounted(tmp_path):
    counts = tmp_path / "counts.tsv"
    counts.write_text(
        "record_id\tvariant_id\tgroup_id\tregion_id\tvariant_group\tac\tan\n"
        "a:x\tx\ta\tr\tb\t1\t4\n"
        "b:y\ty\tb\tr\tb\t1\t4\n"
        "c:z\tz\tc\tr\tb\t0\t0\n"
    )
    dependencies = tmp_path / "dependencies.json"
    dependencies.write_text('{"edges": [], "qualification": "synthetic"}\n')
    out = tmp_path / "out"

    completed = _run(_command(out, counts=counts, dependencies=dependencies, folds=3))

    assert completed.returncode == 2
    statuses = pd.read_csv(out / "row_status.tsv", sep="\t", keep_default_na=False)
    assert len(statuses) == 3
    assert set(statuses.status) == {"infeasible", "unavailable_denominator"}
    assert pd.read_csv(out / "predictions.tsv", sep="\t").empty
    assert pd.read_csv(out / "posteriors.tsv", sep="\t").empty


def test_injected_numeric_failure_is_published_and_other_folds_continue(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("reference_runner", SCRIPT)
    assert spec is not None and spec.loader is not None
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    real_fit = runner.fit_reference_b0
    calls = 0

    def fail_once(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ValueError("injected numeric failure")
        return real_fit(*args, **kwargs)

    monkeypatch.setattr(runner, "fit_reference_b0", fail_once)
    args = runner._parser().parse_args(_command(tmp_path / "run")[2:])

    assert runner.run(args) == 2
    summary = _json(tmp_path / "run" / "summary.json")
    assert summary["split_counts"] == {"planned": 2, "completed": 1, "failed": 1, "infeasible": 0}
    statuses = pd.read_csv(tmp_path / "run" / "row_status.tsv", sep="\t", keep_default_na=False)
    assert "failed" in set(statuses.status)
    assert "scored" in set(statuses.status)
    assert "injected numeric failure" in " ".join(statuses.reason)


@pytest.mark.parametrize("helper", ["_git_record", "_package_versions"])
def test_provenance_failure_publishes_no_output_directory(tmp_path, monkeypatch, helper):
    spec = importlib.util.spec_from_file_location("reference_runner", SCRIPT)
    assert spec is not None and spec.loader is not None
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    out = tmp_path / "run"
    args = runner._parser().parse_args(_command(out)[2:])

    def fail():
        raise ValueError("injected provenance failure")

    monkeypatch.setattr(runner, helper, fail)

    with pytest.raises(ValueError, match="injected provenance failure"):
        runner.run(args)
    assert not out.exists()


def test_inputs_are_hashed_from_consumed_snapshot_when_paths_change(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("reference_runner", SCRIPT)
    assert spec is not None and spec.loader is not None
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    counts = tmp_path / "counts.tsv"
    dependencies = tmp_path / "dependencies.json"
    original_counts = (FIXTURES / "counts.tsv").read_bytes()
    original_dependencies = (FIXTURES / "dependencies.json").read_bytes()
    counts.write_bytes(original_counts)
    dependencies.write_bytes(original_dependencies)
    out = tmp_path / "run"
    args = runner._parser().parse_args(
        _command(out, counts=counts, dependencies=dependencies)[2:]
    )
    real_fit = runner.fit_reference_b0
    changed = False

    def replace_inputs(*fit_args, **fit_kwargs):
        nonlocal changed
        if not changed:
            counts.write_text("replacement bytes that were not consumed\n")
            dependencies.unlink()
            changed = True
        return real_fit(*fit_args, **fit_kwargs)

    monkeypatch.setattr(runner, "fit_reference_b0", replace_inputs)

    assert runner.run(args) == 0
    manifest = _json(out / "manifest.json")
    assert manifest["input_files"] == {
        "counts": {
            "sha256": hashlib.sha256(original_counts).hexdigest(),
            "size_bytes": len(original_counts),
        },
        "dependencies": {
            "sha256": hashlib.sha256(original_dependencies).hexdigest(),
            "size_bytes": len(original_dependencies),
        },
    }
