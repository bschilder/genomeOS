"""Adversarial B1 evidence-reader regressions (design §§4–8, 12; #307)."""

from __future__ import annotations

import hashlib
import json
import runpy
import shutil
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/local_count"


@pytest.fixture(scope="module")
def artifacts(tmp_path_factory):
    root = tmp_path_factory.mktemp("local-report")
    runner = runpy.run_path(str(ROOT / "scripts/benchmark_local_count.py"))
    helper = runpy.run_path(str(ROOT / "tests/test_local_count_cli.py"))
    for name, role in [("primary", "prespecified_primary"), ("sensitivity", "posthoc_sensitivity")]:
        command = helper["_command"](root / name)[2:]
        command[command.index("synthetic_validation")] = role
        assert runner["run"](runner["_parser"]().parse_args(command)) == 0
    runner = runpy.run_path(str(ROOT / "scripts/benchmark_allele_frequency.py"))
    command = [
        "--observations",
        str(FIXTURES / "observations.tsv"),
        "--assignments",
        str(FIXTURES / "assignments.tsv"),
        "--dependencies",
        str(FIXTURES / "dependencies.tsv"),
        "--data-version",
        "fixture-v1",
        "--prior-alpha",
        "1",
        "--prior-beta",
        "9",
        "--buffer-km",
        "100",
        "--posterior-draws",
        "64",
        "--seed",
        "42",
        "--evidence-kind",
        "synthetic_fixture",
        "--out",
        str(root / "b0"),
    ]
    assert runner["run"](runner["_parser"]().parse_args(command)) == 0
    shutil.copy(FIXTURES / "observations.tsv", root / "observations.tsv")
    return root


def _build(root):
    reader = runpy.run_path(str(ROOT / "scripts/plot_hbs_local_count_benchmark.py"))
    return reader["_build_report"](
        root / "observations.tsv", root / "primary", root / "sensitivity", root / "b0"
    )


def _rehash(root, filename):
    path = root / "manifest.json"
    manifest = json.loads(path.read_text())
    data = (root / filename).read_bytes()
    manifest["output_files"][filename] = {"sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)}
    path.write_text(json.dumps(manifest))


def test_valid_complete_report_retains_every_query(artifacts):
    report, support, matched = _build(artifacts)
    assert len(support) == len(matched) == 8
    assert report["sensitivity"]["benchmark"]["requested_observation_count"] == 8


@pytest.mark.parametrize(
    "mutation",
    [
        "unhashed_score",
        "wrong_coordinates",
        "missing_coordinates",
        "incomplete_inventory",
        "rehashed_count",
        "rehashed_region",
        "rehashed_cohort",
        "rehashed_variant",
        "rehashed_support",
        "rehashed_missing_support",
        "rehashed_extra_prediction",
        "rehashed_missing_prediction",
        "rehashed_summary",
        "rehashed_candidate",
        "rehashed_fold_status",
        "summary_publication",
        "wrong_role",
        "wrong_schema",
        "wrong_split",
        "incomplete_inputs",
        "b0_rehashed_count",
    ],
)
def test_reader_refuses_corrupt_or_semantically_inconsistent_artifacts(artifacts, tmp_path, mutation):
    root = tmp_path / "copy"
    shutil.copytree(artifacts, root)
    arm, filename = "sensitivity", "predictions.tsv"
    if mutation in ("wrong_coordinates", "missing_coordinates"):
        path = root / "observations.tsv"
        frame = pd.read_csv(path, sep="\t")
        if mutation == "wrong_coordinates":
            frame["lon"] = 0.0
        else:
            frame = frame.iloc[:2]
        frame.to_csv(path, sep="\t", index=False)
    elif mutation in (
        "incomplete_inventory",
        "wrong_role",
        "wrong_schema",
        "wrong_split",
        "incomplete_inputs",
    ):
        path = root / arm / "manifest.json"
        manifest = json.loads(path.read_text())
        if mutation == "incomplete_inventory":
            del manifest["output_files"]["support.tsv"]
        elif mutation == "incomplete_inputs":
            del manifest["input_files"]["assignments"]
        elif mutation == "wrong_role":
            manifest["analysis_role"] = "prespecified_primary"
        elif mutation == "wrong_schema":
            manifest["schema_version"] = 2
        else:
            manifest["splits"][0]["test_ids"] = ["invented"]
            from genomeos.validation.local_count_artifact import canonical_hash

            manifest["split_manifest_sha256"] = canonical_hash(manifest["splits"])
        path.write_text(json.dumps(manifest))
    elif mutation in ("rehashed_summary", "summary_publication"):
        filename = "summary.json"
        path = root / arm / filename
        summary = json.loads(path.read_text())
        if mutation == "summary_publication":
            summary["publication_eligible"] = True
        else:
            summary["benchmark"]["excluded_fraction"] = -1.0
        path.write_text(json.dumps(summary))
        _rehash(root / arm, filename)
    else:
        if "support" in mutation:
            filename = "support.tsv"
        elif mutation == "rehashed_candidate":
            filename = "bandwidth_selection.tsv"
        elif mutation == "rehashed_fold_status":
            filename = "fold_status.tsv"
        if mutation == "b0_rehashed_count":
            arm = "b0"
        path = root / arm / filename
        frame = pd.read_csv(path, sep="\t", keep_default_na=False)
        if mutation == "unhashed_score":
            frame.loc[0, "log_score"] -= 10000
        elif mutation in ("rehashed_count", "b0_rehashed_count"):
            frame.loc[0, "observed_an"] += 1
        elif mutation in ("rehashed_region", "rehashed_cohort", "rehashed_variant"):
            frame.loc[0, mutation.removeprefix("rehashed_") + "_id"] = "invented"
        elif mutation == "rehashed_support":
            frame.loc[0, "status"] = "unknown"
        elif mutation in ("rehashed_missing_support", "rehashed_missing_prediction"):
            frame = frame.iloc[1:]
        elif mutation == "rehashed_extra_prediction":
            frame = pd.concat([frame, frame.iloc[:1]])
        elif mutation == "rehashed_candidate":
            frame.loc[0, "emission_fraction"] = 0.123
        elif mutation == "rehashed_fold_status":
            frame.loc[0, "expected_test_ids"] = '["invented"]'
        frame.to_csv(path, sep="\t", index=False)
        if mutation != "unhashed_score":
            _rehash(root / arm, filename)
    with pytest.raises(ValueError):
        _build(root)


def test_posthoc_strata_retain_all_requested_and_refused_rows(artifacts):
    report, _, _ = _build(artifacts)
    for arm in ("primary", "sensitivity"):
        strata = report[arm]["retained_evidence_strata"]
        assert strata["analysis_role"] == "posthoc_descriptive_strata"
        assert strata["endemic_background"]["acceptance_item"] == "open"
        for category in ("denominator", "distance_km"):
            assert sum(row["requested_count"] for row in strata[category]) == 8
            assert sum(row["emitted_count"] + row["refused_count"] for row in strata[category]) == 8
    assert report["b2_current"]["historical_snapshot"]["date"] == "2026-09-16"
    assert report["b2_current"]["later_development_result"]["completed_observation_count"] == 994
    assert not report["b2_current"]["valid_comparison_available"]


@pytest.mark.parametrize(
    "left,right,expected,available",
    [
        (float("-inf"), -2.0, "-Infinity", True),
        (-2.0, float("-inf"), "Infinity", True),
        (float("-inf"), float("-inf"), None, False),
    ],
)
def test_infinite_and_undefined_paired_scores_remain_explicit(left, right, expected, available):
    reader = runpy.run_path(str(ROOT / "scripts/plot_hbs_local_count_benchmark.py"))
    frame = pd.DataFrame(
        {
            "log_score_b1": [left],
            "log_score_b0": [right],
            "absolute_error_b1": [0.1],
            "absolute_error_b0": [0.2],
            "coverage_95_b1": [True],
            "coverage_95_b0": [False],
        }
    )
    metrics = reader["_json_safe"](reader["_row_metrics"](frame))
    assert metrics["mean_log_score_delta"] == expected
    assert metrics["paired_delta_available"] is available
    json.dumps(metrics, allow_nan=False)


@pytest.mark.parametrize(
    "arm,filename",
    [
        *[
            ("sensitivity", name)
            for name in (
                "predictions.tsv",
                "support.tsv",
                "summary.json",
                "fold_status.tsv",
                "inventory.json",
                "bandwidth_selection.tsv",
            )
        ],
        *[("b0", name) for name in ("predictions.tsv", "summary.json", "fold_status.tsv", "inventory.json")],
    ],
)
def test_every_required_output_is_hash_and_size_verified(artifacts, tmp_path, arm, filename):
    root = tmp_path / "copy"
    shutil.copytree(artifacts, root)
    path = root / arm / filename
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="hash/size"):
        _build(root)


def test_rehashed_score_change_requires_summary_replay(artifacts, tmp_path):
    root = tmp_path / "copy"
    shutil.copytree(artifacts, root)
    path = root / "sensitivity" / "predictions.tsv"
    frame = pd.read_csv(path, sep="\t")
    frame.loc[0, "log_score"] -= 100
    frame.to_csv(path, sep="\t", index=False)
    _rehash(root / "sensitivity", "predictions.tsv")
    with pytest.raises(ValueError, match="replayed B1 summary"):
        _build(root)


def test_opposite_infinities_do_not_become_a_finite_paired_estimate():
    reader = runpy.run_path(str(ROOT / "scripts/plot_hbs_local_count_benchmark.py"))
    frame = pd.DataFrame(
        {
            "log_score_b1": [float("-inf"), -2.0],
            "log_score_b0": [-2.0, float("-inf")],
            "absolute_error_b1": [0.1, 0.1],
            "absolute_error_b0": [0.2, 0.2],
            "coverage_95_b1": [True, True],
            "coverage_95_b0": [False, False],
        }
    )
    metrics = reader["_json_safe"](reader["_row_metrics"](frame))
    assert not metrics["paired_delta_available"]
    assert metrics["mean_log_score_delta"] is None
    assert metrics["paired_delta_unavailable_reason"] == "opposite_infinite_differences"
    json.dumps(metrics, allow_nan=False)


def _invoke_renderer(root, out, report, monkeypatch, namespace=None):
    import sys

    namespace = namespace or runpy.run_path(str(ROOT / "scripts/plot_hbs_local_count_benchmark.py"))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "plot",
            "--observations",
            str(root / "observations.tsv"),
            "--primary",
            str(root / "primary"),
            "--sensitivity",
            str(root / "sensitivity"),
            "--b0",
            str(root / "b0"),
            "--out",
            str(out),
            "--report",
            str(report),
        ],
    )
    return namespace["main"]()


@pytest.mark.parametrize("existing", ["figure", "report", "both", "figure_symlink", "report_symlink"])
def test_renderer_refuses_existing_targets_before_any_write(artifacts, tmp_path, monkeypatch, existing):
    out, report = tmp_path / "figure.png", tmp_path / "report.json"
    sentinel = tmp_path / "sentinel"
    sentinel.write_bytes(b"preserve sentinel")
    for name, path in [("figure", out), ("report", report)]:
        if existing in (name, "both"):
            path.write_bytes(("preserve " + name).encode())
        elif existing == name + "_symlink":
            path.symlink_to(sentinel)
    before = {path: path.read_bytes() if path.exists() else None for path in (out, report, sentinel)}
    with pytest.raises((ValueError, FileExistsError)):
        _invoke_renderer(artifacts, out, report, monkeypatch)
    for path, contents in before.items():
        assert path.read_bytes() == contents if contents is not None else not path.exists()


@pytest.mark.parametrize("kind", ["same", "parent_alias", "dangling_symlink", "nested"])
def test_renderer_refuses_aliased_or_dangling_targets(artifacts, tmp_path, monkeypatch, kind):
    out = tmp_path / "figure.png"
    if kind == "same":
        report = out
    elif kind == "nested":
        report = out / "report.json"
    elif kind == "parent_alias":
        alias = tmp_path / "alias"
        alias.symlink_to(tmp_path, target_is_directory=True)
        report = alias / "figure.png"
    else:
        report = tmp_path / "report.json"
        out.symlink_to(tmp_path / "missing")
    with pytest.raises((ValueError, FileExistsError)):
        _invoke_renderer(artifacts, out, report, monkeypatch)
    assert not out.exists()
    assert not report.exists()


def test_renderer_publish_collision_preserves_newly_appearing_sentinel(artifacts, tmp_path, monkeypatch):
    import os

    namespace = runpy.run_path(str(ROOT / "scripts/plot_hbs_local_count_benchmark.py"))
    out, report = tmp_path / "figure.png", tmp_path / "report.json"
    original = os.link

    def racing_link(source, destination, *args, **kwargs):
        if Path(destination) == report:
            report.write_bytes(b"new report sentinel")
        return original(source, destination, *args, **kwargs)

    monkeypatch.setattr(os, "link", racing_link)
    with pytest.raises(FileExistsError):
        _invoke_renderer(artifacts, out, report, monkeypatch, namespace)
    assert report.read_bytes() == b"new report sentinel"
    assert not out.exists()


def test_renderer_new_destinations_reproduce_bytes(artifacts, tmp_path, monkeypatch):
    outputs = []
    for index in (1, 2):
        out, report = tmp_path / f"figure{index}.png", tmp_path / f"report{index}.json"
        assert _invoke_renderer(artifacts, out, report, monkeypatch) == 0
        outputs.append((out.read_bytes(), report.read_bytes()))
    assert outputs[0] == outputs[1]


def test_renderer_second_publication_failure_leaves_no_partial_outputs(artifacts, tmp_path, monkeypatch):
    import os

    namespace = runpy.run_path(str(ROOT / "scripts/plot_hbs_local_count_benchmark.py"))
    out, report = tmp_path / "figure.png", tmp_path / "report.json"
    original = os.link

    def failing_link(source, destination, *args, **kwargs):
        if Path(destination) == report:
            raise OSError("simulated second publication failure")
        return original(source, destination, *args, **kwargs)

    monkeypatch.setattr(os, "link", failing_link)
    with pytest.raises(OSError, match="second publication"):
        _invoke_renderer(artifacts, out, report, monkeypatch, namespace)
    assert not out.exists()
    assert not report.exists()
