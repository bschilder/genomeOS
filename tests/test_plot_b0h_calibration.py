"""Offline B0H calibration report tests (report design §§1,3–4; Atlas §§5,7–8,12)."""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import stat
import struct
import subprocess
import sys
from collections import Counter
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pytest

from genomeos.validation.heterogeneity_reduction import reduction_bytes, study_claim_reasons
from genomeos.validation.heterogeneity_report import read_study_reduction

GROUP_DENOMINATORS = {0: 512, 1: 384, 2: 64, 3: 1, 4: 8}
ROOT = Path(__file__).parents[1]
PYTENSOR_CACHE = "/private/tmp/genomeos-calibration-report-cache-20260911"
MODE_LABELS = ("correct", "prior-only", "cyclic-rho")
QUANTITY_LABELS = (
    "mean",
    "rho",
    "mean*rho",
    "training log likelihood",
    "log mass AC0/AN20",
    "dependence quantity",
)


def test_authored_demo_is_deterministic_complete_and_scientifically_ineligible():
    demo = importlib.import_module("scripts.build_calibration_report_demo")

    first = demo.build_demo_reduction()
    second = demo.build_demo_reduction()
    data = reduction_bytes(first)

    assert data == reduction_bytes(second)
    assert read_study_reduction(data) == first
    assert len(first.cases) == 1938
    assert len(first.ranks) == 36
    assert Counter((row.case.track_id, row.case.study_id) for row in first.cases) == {
        (track, study): denominator
        for track in (0, 1)
        for study, denominator in GROUP_DENOMINATORS.items()
    }
    assert {row.generation for row in first.cases} >= {
        "available",
        "all_unavailable",
        "generation_failed",
    }
    assert {row.structural for row in first.cases} >= {
        "not_admitted",
        "expected_refusal",
        "unexpected_return",
    }
    assert {row.attempt0 for row in first.cases} >= {
        "accepted",
        "convergence_failed",
        "execution_failed",
        "started_unresolved",
        "not_admitted",
    }
    assert {row.attempt1 for row in first.cases} >= {"accepted", "not_admitted"}
    assert {row.quantities for row in first.cases} >= {"complete", "incomplete", "not_admitted"}
    assert {row.summary for row in first.cases} >= {
        "complete",
        "diagnostics_failed",
        "not_admitted",
    }
    assert (first.ranks[0].actual_n, first.ranks[0].missing_n, first.ranks[0].test) == (511, 1, None)
    assert (first.ranks[23].actual_n, first.ranks[23].missing_n, first.ranks[23].test) == (
        0,
        512,
        None,
    )
    assert any(row.role == "correct_family" and row.decision == "reject" for row in first.ranks)
    assert any(row.role == "required_control" and row.decision == "reject" for row in first.ranks)
    assert any(row.role == "required_control" and row.decision == "not_reject" for row in first.ranks)
    assert first.claim_reasons == study_claim_reasons(first.cases, first.ranks)
    assert first.claim_reasons == (
        "unresolved_case_or_required_diagnostic_outcomes",
        "incomplete_rank_outcomes",
        "correct_family_discrepancy_detected",
        "predeclared_control_sensitivity_limited",
    )
    assert first.unconditional_claim_eligible is False
    assert first.permitted_claim is None


def test_rank_figure_artists_bind_all_frozen_rows_counts_labels_and_decisions():
    demo = importlib.import_module("scripts.build_calibration_report_demo")
    renderer = importlib.import_module("scripts.plot_b0h_calibration")
    reduction = read_study_reduction(reduction_bytes(demo.build_demo_reduction()))

    figure = renderer.build_rank_figure(reduction, "synthetic_fixture")
    try:
        assert "AUTHORED SYNTHETIC REPORTING FIXTURE" in figure._suptitle.get_text()
        axes = {axis.get_gid(): axis for axis in figure.axes if axis.get_gid()}
        assert set(axes) == {
            "rank-counts-track0",
            "rank-metadata-track0",
            "rank-counts-track1",
            "rank-metadata-track1",
            "rank-footer",
        }
        for track in (0, 1):
            axis = axes[f"rank-counts-track{track}"]
            metadata_axis = axes[f"rank-metadata-track{track}"]
            expected_rows = [row for row in reduction.ranks if row.track_id == track]
            assert axis.get_title(loc="left").startswith(f"track {track}")
            assert [label.get_text() for label in axis.get_xticklabels()] == [
                "bin 0",
                "bin 1",
                "bin 2",
                "bin 3",
                "bin 4",
                "missing",
            ]
            assert [label.get_text() for label in axis.get_yticklabels()] == [
                f"m{row.mode_id}/q{row.quantity_id} · "
                f"{MODE_LABELS[row.mode_id]} / {QUANTITY_LABELS[row.quantity_id]}"
                for row in expected_rows
            ]
            image = axis.images[0]
            assert (image.norm.vmin, image.norm.vmax) == (0, 512)
            assert np.array_equal(
                np.asarray(image.get_array()),
                np.asarray([(*row.counts, row.missing_n) for row in expected_rows]),
            )
            assert {text.get_gid(): text.get_text() for text in axis.texts} == {
                f"rank-count-{track}-{row_index}-{column_index}": str(value)
                for row_index, row in enumerate(expected_rows)
                for column_index, value in enumerate((*row.counts, row.missing_n))
            }
            annotations = {text.get_gid(): text.get_text() for text in metadata_axis.texts}
            assert annotations == {
                f"rank-{row.track_id}-{row.mode_id}-{row.quantity_id}": (
                    f"N={row.actual_n}/512 | {row.role} | {row.decision}\n"
                    + (
                        "raw p: unavailable | adjusted p: unavailable"
                        if row.test is None
                        else f"raw p: {row.test.p_value:.6g} | "
                        f"adjusted p: {row.test.bonferroni_p_value:.6g}"
                    )
                    + "\nmissing: "
                    + (
                        ", ".join(
                            f"{status}={count}" for status, count in row.failure_status_counts
                        )
                        if row.failure_status_counts
                        else "none"
                    )
                )
                for row in expected_rows
            }
            assert all(text.get_fontsize() >= 8 for text in metadata_axis.texts)
        footer = axes["rank-footer"]
        assert not footer.axison
        assert "publication eligible: false" in "\n".join(
            text.get_text() for text in footer.texts
        )
    finally:
        plt.close(figure)


def test_accounting_figure_artists_bind_every_case_once_in_each_stage_panel():
    demo = importlib.import_module("scripts.build_calibration_report_demo")
    renderer = importlib.import_module("scripts.plot_b0h_calibration")
    reduction = read_study_reduction(reduction_bytes(demo.build_demo_reduction()))

    figure = renderer.build_accounting_figure(reduction, "synthetic_fixture")
    groups = [(track, study) for track in (0, 1) for study in range(5)]
    try:
        assert "AUTHORED SYNTHETIC REPORTING FIXTURE" in figure._suptitle.get_text()
        stage_axes = {axis.get_gid(): axis for axis in figure.axes if axis.images}
        assert set(stage_axes) == {
            "accounting-generation",
            "accounting-structural",
            "accounting-attempt0",
            "accounting-attempt1",
            "accounting-quantities",
            "accounting-summary",
        }
        for stage in (
            "generation",
            "structural",
            "attempt0",
            "attempt1",
            "quantities",
            "summary",
        ):
            axis = stage_axes[f"accounting-{stage}"]
            assert axis.get_title() == stage
            status_labels = [label.get_text() for label in axis.get_xticklabels()]
            group_labels = [label.get_text() for label in axis.get_yticklabels()]
            assert group_labels == [
                f"track{track}/study{study} (N={GROUP_DENOMINATORS[study]})"
                for track, study in groups
            ]
            expected = np.array(
                [
                    [
                        sum(
                            row.case.track_id == track
                            and row.case.study_id == study
                            and getattr(row, stage) == status
                            for row in reduction.cases
                        )
                        for status in status_labels
                    ]
                    for track, study in groups
                ]
            )
            image = axis.images[0]
            actual = np.asarray(image.get_array())
            assert (image.norm.vmin, image.norm.vmax) == (0, 512)
            assert np.array_equal(actual, expected)
            assert int(actual.sum()) == 1938
            assert tuple(actual.sum(axis=1)) == tuple(
                GROUP_DENOMINATORS[study] for _, study in groups
            )
            assert set(status_labels) == {getattr(row, stage) for row in reduction.cases}
            assert len(axis.texts) == actual.size
            assert {text.get_position(): text.get_text() for text in axis.texts} == {
                (column_index, row_index): str(int(actual[row_index, column_index]))
                for row_index, column_index in np.ndindex(actual.shape)
            }
            assert all(text.get_fontsize() >= 8 for text in axis.texts)
            assert all(label.get_fontsize() >= 9 for label in axis.get_xticklabels())
            assert all(label.get_fontsize() >= 9 for label in axis.get_yticklabels())
        footer = next(axis for axis in figure.axes if axis.get_gid() == "accounting-footer")
        assert not footer.axison
        expected_claim = (
            "recorded claim eligibility: false | publication eligible: false\n"
            f"claim reasons: {', '.join(reduction.claim_reasons)}"
        )
        expected_limitation = (
            "Each panel counts all 1,938 cases exactly once on a shared sequential blue "
            "0–512 ramp. Stages share cases and are not independent observations; "
            "not_admitted can mean an unnecessary retry or a blocked downstream stage."
        )
        assert [text.get_text() for text in footer.texts] == [
            expected_claim,
            expected_limitation,
        ]
    finally:
        plt.close(figure)


def _subprocess_environment() -> dict[str, str]:
    return {
        **os.environ,
        "PYTHONPATH": str(ROOT),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTENSOR_FLAGS": (
            f"base_compiledir={PYTENSOR_CACHE}/pytensor-base,"
            f"compiledir={PYTENSOR_CACHE}/pytensor"
        ),
        "MPLCONFIGDIR": f"{PYTENSOR_CACHE}/mpl",
        "XDG_CACHE_HOME": f"{PYTENSOR_CACHE}/xdg",
    }


def _run_report(
    input_path: Path,
    digest: str,
    output: Path,
    *,
    evidence_kind: str = "synthetic_fixture",
):
    return subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "plot_b0h_calibration.py"),
            "--reduction",
            str(input_path),
            "--expected-reduction-sha256",
            digest,
            "--evidence-kind",
            evidence_kind,
            "--out",
            str(output),
        ],
        cwd=ROOT,
        env=_subprocess_environment(),
        capture_output=True,
        text=True,
    )


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_cli_copies_exact_input_attests_outputs_and_writes_complete_receipt_last(tmp_path):
    demo = importlib.import_module("scripts.build_calibration_report_demo")
    reduction = demo.build_demo_reduction()
    source = reduction_bytes(reduction)
    source_path = tmp_path / "authored-reduction.json"
    source_path.write_bytes(source)
    source_path.chmod(0o444)
    original_mode = stat.S_IMODE(source_path.stat().st_mode)
    output = tmp_path / "report-a"

    completed = _run_report(source_path, _sha256(source), output)

    assert completed.returncode == 0, completed.stderr
    assert set(path.name for path in output.iterdir()) == {
        "reduction.json",
        "ranks.png",
        "accounting.png",
        "receipt.json",
    }
    assert (output / "reduction.json").read_bytes() == source
    assert source_path.read_bytes() == source
    assert stat.S_IMODE(source_path.stat().st_mode) == original_mode
    receipt_bytes = (output / "receipt.json").read_bytes()
    receipt = json.loads(receipt_bytes)
    assert receipt["format"] == "b0h_calibration_report_receipt"
    assert receipt["version"] == "1"
    assert receipt["evidence_kind"] == "synthetic_fixture"
    assert receipt["publication_eligible"] is False
    assert receipt["input"] == {"sha256": _sha256(source), "size_bytes": len(source)}
    assert receipt["versions"]["reduction_format"] == "b0h_reduction"
    assert receipt["versions"]["reduction_version"] == "1"
    assert receipt["versions"]["renderer_version"] == "1"
    assert receipt["source_sha256"] == {
        relative: {
            "sha256": _sha256((ROOT / relative).read_bytes()),
            "size_bytes": (ROOT / relative).stat().st_size,
        }
        for relative in (
            "scripts/plot_b0h_calibration.py",
            "genomeos/validation/heterogeneity_report.py",
            "genomeos/validation/heterogeneity_reduction.py",
        )
    }
    for name in ("reduction.json", "ranks.png", "accounting.png"):
        contents = (output / name).read_bytes()
        assert receipt["outputs"][name] == {
            "sha256": _sha256(contents),
            "size_bytes": len(contents),
        }
        assert (output / "receipt.json").stat().st_mtime_ns >= (output / name).stat().st_mtime_ns
    assert str(tmp_path) not in receipt_bytes.decode("ascii")

    rank_records = [row for panel in receipt["rank_panels"] for row in panel["rows"]]
    assert len(rank_records) == 36
    for actual, expected in zip(rank_records, reduction.ranks, strict=True):
        assert actual["track_id"] == expected.track_id
        assert actual["mode_id"] == expected.mode_id
        assert actual["quantity_id"] == expected.quantity_id
        assert actual["counts"] == list(expected.counts)
        assert actual["actual_n"] == expected.actual_n
        assert actual["missing_n"] == expected.missing_n
        assert actual["failure_status_counts"] == [list(item) for item in expected.failure_status_counts]
        assert actual["role"] == expected.role
        assert actual["decision"] == expected.decision
        if expected.test is None:
            assert actual["test"] is None
        else:
            assert actual["test"] == {
                "statistic": expected.test.statistic,
                "p_value_bits": struct.pack(">d", expected.test.p_value).hex(),
                "bonferroni_p_value_bits": struct.pack(
                    ">d", expected.test.bonferroni_p_value
                ).hex(),
            }

    groups = [(track, study) for track in (0, 1) for study in range(5)]
    for panel in receipt["accounting_panels"]:
        assert panel["total_cases"] == 1938
        assert len(panel["groups"]) == 10
        stage = panel["stage"]
        for actual, (track, study) in zip(panel["groups"], groups, strict=True):
            expected_counts = Counter(
                getattr(row, stage)
                for row in reduction.cases
                if row.case.track_id == track and row.case.study_id == study
            )
            assert actual["track_id"] == track
            assert actual["study_id"] == study
            assert actual["denominator"] == GROUP_DENOMINATORS[study]
            assert actual["status_counts"] == {
                status: expected_counts.get(status, 0) for status in panel["statuses"]
            }
            assert sum(actual["status_counts"].values()) == GROUP_DENOMINATORS[study]
    assert receipt["claim"] == {
        "unconditional_claim_eligible": False,
        "claim_reasons": list(reduction.claim_reasons),
        "permitted_claim": None,
    }

    second_output = tmp_path / "report-b"
    second = _run_report(source_path, _sha256(source), second_output)
    assert second.returncode == 0, second.stderr
    for name in ("reduction.json", "ranks.png", "accounting.png", "receipt.json"):
        assert _sha256((output / name).read_bytes()) == _sha256((second_output / name).read_bytes())


@pytest.mark.parametrize(
    "failure",
    ["wrong_hash", "malformed_hash", "noncanonical", "invalid_evidence", "existing_output"],
)
def test_cli_refuses_invalid_or_existing_outputs_before_false_success(tmp_path, failure):
    demo = importlib.import_module("scripts.build_calibration_report_demo")
    source = reduction_bytes(demo.build_demo_reduction())
    source_path = tmp_path / "reduction.json"
    source_path.write_bytes(b"{}" if failure == "noncanonical" else source)
    digest = _sha256(source_path.read_bytes())
    if failure == "wrong_hash":
        digest = "f" * 64 if digest != "f" * 64 else "e" * 64
    elif failure == "malformed_hash":
        digest = "ABC"
    output = tmp_path / "report"
    if failure == "existing_output":
        output.mkdir()
        (output / "marker").write_text("preserve", encoding="ascii")

    completed = _run_report(
        source_path,
        digest,
        output,
        evidence_kind="observational_research" if failure == "invalid_evidence" else "synthetic_fixture",
    )

    assert completed.returncode == 2
    assert "error:" in completed.stderr
    if failure == "existing_output":
        assert sorted(path.name for path in output.iterdir()) == ["marker"]
        assert (output / "marker").read_text(encoding="ascii") == "preserve"
    else:
        assert not output.exists()


def test_demo_cli_writes_deterministic_canonical_bytes_and_refuses_overwrite(tmp_path):
    outputs = [tmp_path / "demo-a.json", tmp_path / "demo-b.json"]
    records = []
    for output in outputs:
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "build_calibration_report_demo.py"),
                "--out",
                str(output),
            ],
            cwd=ROOT,
            env=_subprocess_environment(),
            capture_output=True,
            text=True,
        )
        assert completed.returncode == 0, completed.stderr
        records.append(json.loads(completed.stdout))
    assert outputs[0].read_bytes() == outputs[1].read_bytes()
    assert read_study_reduction(outputs[0].read_bytes()).format == "b0h_reduction"
    assert records[0] == records[1] == {
        "evidence_kind": "synthetic_fixture",
        "publication_eligible": False,
        "sha256": _sha256(outputs[0].read_bytes()),
        "size_bytes": len(outputs[0].read_bytes()),
    }

    unchanged = outputs[0].read_bytes()
    refused = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "build_calibration_report_demo.py"),
            "--out",
            str(outputs[0]),
        ],
        cwd=ROOT,
        env=_subprocess_environment(),
        capture_output=True,
        text=True,
    )
    assert refused.returncode == 2
    assert outputs[0].read_bytes() == unchanged


def test_renderer_refuses_modules_imported_from_a_different_checkout(monkeypatch):
    renderer = importlib.import_module("scripts.plot_b0h_calibration")
    monkeypatch.setattr(renderer.report_module, "__file__", "/tmp/other/genomeos/report.py")

    with pytest.raises(ValueError, match="different checkout"):
        renderer.source_hashes()


def test_plot_failure_preserves_partial_evidence_without_receipt(tmp_path, monkeypatch):
    demo = importlib.import_module("scripts.build_calibration_report_demo")
    renderer = importlib.import_module("scripts.plot_b0h_calibration")
    source = reduction_bytes(demo.build_demo_reduction())
    source_path = tmp_path / "reduction.json"
    source_path.write_bytes(source)
    output = tmp_path / "partial-report"

    def fail_accounting(*args, **kwargs):
        raise RuntimeError("injected accounting render failure")

    monkeypatch.setattr(renderer, "build_accounting_figure", fail_accounting)
    with pytest.raises(RuntimeError, match="injected"):
        renderer.render_report(
            source_path,
            expected_reduction_sha256=_sha256(source),
            evidence_kind="synthetic_fixture",
            output=output,
        )

    assert (output / "reduction.json").read_bytes() == source
    assert (output / "ranks.png").stat().st_size > 10_000
    assert not (output / "accounting.png").exists()
    assert not (output / "receipt.json").exists()


def test_reporting_decodes_once_without_fitting_reducing_or_simulating(tmp_path, monkeypatch):
    demo = importlib.import_module("scripts.build_calibration_report_demo")
    renderer = importlib.import_module("scripts.plot_b0h_calibration")
    ranks = importlib.import_module("genomeos.validation.sbc_ranks")
    simulation = importlib.import_module("genomeos.validation.heterogeneity_simulation")
    runner = importlib.import_module("genomeos.validation.heterogeneity_runner")
    source = reduction_bytes(demo.build_demo_reduction())
    source_path = tmp_path / "reduction.json"
    source_path.write_bytes(source)
    decoder = renderer.report_module.read_study_reduction
    calls = 0

    def counted_decoder(data):
        nonlocal calls
        calls += 1
        return decoder(data)

    def forbidden(*args, **kwargs):
        raise AssertionError("reporting called a scientific or execution path")

    monkeypatch.setattr(renderer.report_module, "read_study_reduction", counted_decoder)
    monkeypatch.setattr(renderer.reduction_module, "reduce_b0h_study", forbidden)
    monkeypatch.setattr(renderer.reduction_module, "rank_reduction", forbidden)
    monkeypatch.setattr(ranks, "test_rank_uniformity", forbidden)
    monkeypatch.setattr(ranks, "simulate_rank_null", forbidden)
    monkeypatch.setattr(simulation, "generate_sbc_case", forbidden)
    monkeypatch.setattr(runner, "execute_b0h_case", forbidden)

    renderer.render_report(
        source_path,
        expected_reduction_sha256=_sha256(source),
        evidence_kind="synthetic_fixture",
        output=tmp_path / "report",
    )

    assert calls == 1
