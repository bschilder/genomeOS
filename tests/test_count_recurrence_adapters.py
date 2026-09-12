"""Tiny injected receipt/renderer checks, never the full matrix (design §7, §8)."""

from __future__ import annotations

import argparse
import json
from decimal import Decimal

import numpy as np
import pytest

from scripts import count_recurrence_evaluate as evaluate
from scripts import plot_count_recurrence as plot
from scripts import validate_count_recurrence as validate
from scripts.count_recurrence_oracle import absolute_law


def case(identifier="injected:tiny", *, refuse=False):
    return {
        "case_id": identifier,
        "an": 1,
        "mean": 0.5,
        "mean_hex": (0.5).hex(),
        "concentration": 20.0,
        "concentration_hex": (20.0).hex(),
        "queried_ac": [0, 1],
        "expected_operation": "refuse_numeric_domain" if refuse else "evaluate",
        "expected_refusal_reason": "injected refusal" if refuse else None,
    }


@pytest.fixture
def inputs(tmp_path):
    matrix = tmp_path / "matrix.json"
    validate.write_json(matrix, {"spec_sha256": "a" * 64, "small": [case()], "long": []})
    declaration = tmp_path / "declaration.json"
    validate.write_json(
        declaration,
        {
            "spec_sha256": "a" * 64,
            "matrix_sha256": validate.sha256(matrix),
            "absolute_log_tolerance": "5e-8",
            "evidence_limitation": "Not two-rounded-input invariance.",
        },
    )
    source = tmp_path / "source.json"
    validate.write_json(
        source,
        {
            "revision": "b" * 40,
            "files": {path: validate.sha256(validate.ROOT / path) for path in validate.SOURCE_PATHS},
        },
    )
    return argparse.Namespace(
        out=tmp_path / "result",
        matrix=matrix,
        expected_matrix_sha256=validate.sha256(matrix),
        complement_declaration=declaration,
        expected_complement_sha256=validate.sha256(declaration),
        expected_source_revision="b" * 40,
        source_hashes=source,
        source_mode="snapshot",
        backend="scipy",
    )


@pytest.mark.parametrize(
    "fault", ["existing", "bad_revision", "absent_sources", "bad_hash", "wrong_matrix", "wrong_declaration"]
)
def test_provenance_refuses_before_output(inputs, fault):
    if fault == "existing":
        inputs.out.mkdir()
    elif fault == "bad_revision":
        inputs.expected_source_revision = "not-a-revision"
    elif fault == "absent_sources":
        inputs.source_hashes.unlink()
    elif fault == "bad_hash":
        payload = json.loads(inputs.source_hashes.read_text())
        payload["files"][validate.SOURCE_PATHS[0]] = "0" * 64
        validate.write_json(inputs.source_hashes, payload)
    elif fault == "wrong_matrix":
        inputs.expected_matrix_sha256 = "0" * 64
    else:
        inputs.expected_complement_sha256 = "0" * 64
    with pytest.raises((ValueError, OSError)):
        validate.run(inputs)
    if fault != "existing":
        assert not inputs.out.exists()


def test_snapshot_provenance_never_invokes_git(inputs, monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("snapshot mode invoked Git")

    monkeypatch.setattr(validate.subprocess, "check_output", fail)
    _, _, source = validate.provenance(inputs)
    assert source["revision_provenance"] == "supplied_snapshot_bound_to_source_manifest"


def test_cli_requires_explicit_provenance(monkeypatch):
    monkeypatch.setattr(validate.sys, "argv", ["validate_count_recurrence", "--backend", "scipy"])
    with pytest.raises(SystemExit) as error:
        validate.main()
    assert error.value.code == 2


def injected_matrix(monkeypatch, cases):
    # Only receipt tests inject this inventory; the CLI exposes no subset/threshold option.
    monkeypatch.setattr(validate, "validate_matrix", lambda _: [("small", item) for item in cases])
    monkeypatch.setattr(validate.count_recurrence_controls, "CONTROLS", {})


def test_matrix_requires_fixed_accounting():
    with pytest.raises(ValueError, match="480 small and 68 long"):
        validate.validate_matrix({"small": [case()], "long": []})


def test_failure_retention_and_nonzero(inputs, monkeypatch):
    cases = [case("first"), case("second"), case("third")]
    injected_matrix(monkeypatch, cases)

    def fake(item, *args):
        if item["case_id"] == "first":
            raise ArithmeticError("injected evaluation failure")
        return {"status": "candidate_mismatch", "points": []}

    monkeypatch.setattr(evaluate, "evaluate_case", fake)
    assert validate.run(inputs) == 1
    receipt = json.loads((inputs.out / "receipt.json").read_text())
    assert receipt["summary"]["completed_laws"] == 3
    assert receipt["summary"]["law_status_counts"] == {
        "unexpected_evaluation_failure": 1,
        "candidate_mismatch": 2,
    }
    events = [json.loads(line) for line in (inputs.out / "events.jsonl").read_text().splitlines()]
    assert [item["case_id"] for item in events if item["event"] == "started"] == ["first", "second", "third"]
    assert "injected evaluation failure" in (inputs.out / "events.jsonl").read_text()


def test_backend_absence_retains_incomplete_inventory(inputs, monkeypatch):
    injected_matrix(monkeypatch, [case()])
    monkeypatch.setattr(
        validate, "environment", lambda _: (_ for _ in ()).throw(RuntimeError("injected absent GPU"))
    )
    assert validate.run(inputs) == 1
    summary = json.loads((inputs.out / "receipt.json").read_text())["summary"]
    assert summary["fatal"]["status"] == "backend_absence"
    assert summary["incomplete_laws"] == 1 and summary["completed_laws"] == 0
    assert (inputs.out / "plan.json").exists()


@pytest.mark.parametrize("p,c", [(0.05, 20.0), (np.nextafter(0.0, 1.0), 1e300)])
def test_tiny_evaluator_independent_decimal_and_reflection(p, c):
    item = case()
    item.update(mean=p, mean_hex=float(p).hex(), concentration=c, concentration_hex=float(c).hex())
    result = evaluate.evaluate_case(item, "small", "scipy", np)
    assert result["status"] == "pass"
    assert len(result["points"]) == 2
    assert result["reflected_oracle"]["checks"]["queried_log_precision"]
    assert isinstance(result["oracle"]["precision_480"]["log_mass"][0], str)
    assert result["points"][0]["candidate_upper"] > 0


def test_swapped_shape_oracle_is_new_absolute_evaluation():
    p = np.nextafter(0.0, 1.0)
    original = absolute_law(1, p, 1e300, (0, 1), 480)
    reflected = absolute_law(1, p, 1e300, (1, 0), 480, True)
    assert abs(original.log_mass[1] - reflected.log_mass[1]) <= Decimal("1e-70")
    assert reflected.log_mass[1].is_finite()


def test_refusal_is_distinct_from_numerical_pass(monkeypatch):
    def refuse(*args, **kwargs):
        raise ValueError("injected refusal")

    monkeypatch.setattr(evaluate, "CountPredictive", refuse)
    result = evaluate.evaluate_case(case(refuse=True), "small", "scipy", np)
    assert result["status"] == "expected_domain_refusal" and not result["points"]


def test_probability_underflow_is_explicit():
    result = evaluate.probability_check(0.0, Decimal("1e-400"))
    assert result["float_underflow"]
    assert not evaluate.probability_check(0.0, Decimal("1e-200"))["passed"]


def test_oracle_is_journaled_before_candidate_failure(monkeypatch):
    class FailingLaw:
        def __init__(self, *args, **kwargs):
            pass

        def log_prob(self, *args):
            raise ArithmeticError("injected candidate failure after oracle")

    monkeypatch.setattr(evaluate, "CountPredictive", FailingLaw)
    events = []
    with pytest.raises(ArithmeticError):
        evaluate.evaluate_case(case(), "small", "scipy", np, events.append)
    assert [item["event"] for item in events] == ["oracle", "reflected_oracle"]


def test_explicit_unavailable_control_and_cpu_import_isolation():
    result = validate.count_recurrence_controls.unavailable_backend("scipy", np)
    assert result["returncode"] == 0
    assert "CuPy is required" in result["stdout"]


def test_control_failure_evidence_is_retained(inputs, monkeypatch):
    injected_matrix(monkeypatch, [case()])
    monkeypatch.setattr(
        validate.count_recurrence_controls,
        "CONTROLS",
        {"injected": lambda *args: {"passed": False, "observed_variance": 1.23}},
    )
    assert validate.run(inputs) == 1
    events = [json.loads(line) for line in (inputs.out / "events.jsonl").read_text().splitlines()]
    control = next(item for item in events if item["event"] == "control_outcome")
    assert control["status"] == "control_failure"
    assert control["evidence"]["observed_variance"] == 1.23


def tiny_receipt(inputs, monkeypatch):
    injected_matrix(monkeypatch, [case()])
    assert validate.run(inputs) == 0
    path = inputs.out / "receipt.json"
    receipt = json.loads(path.read_text())
    # A tiny fixture is explicitly injected, not passed off as comprehensive evidence.
    receipt["planned_points"] = 2
    validate.write_json(path, receipt)
    return path


def test_renderer_labels_point_accounting_and_hashes(inputs, monkeypatch, tmp_path):
    path = tiny_receipt(inputs, monkeypatch)
    out = tmp_path / "plots"
    result = plot.render([[str(path), validate.sha256(path)]], [], out)
    assert result["numerical"][0]["evaluated_points"] == 2
    assert result["numerical"][0]["planned_points"] == 2
    assert "Synthetic" in result["label"] and "no calibration claim" in result["label"]
    assert "two-rounded-input" in result["complement_limitation"]
    assert (out / "numerical-errors.png").stat().st_size > 1000
    (inputs.out / "events.jsonl").write_text("changed")
    with pytest.raises(ValueError, match="hash mismatch"):
        plot.read_run(path, validate.sha256(path))


def test_renderer_refuses_accounting_mismatch(inputs, monkeypatch):
    path = tiny_receipt(inputs, monkeypatch)
    receipt = json.loads(path.read_text())
    receipt["summary"]["evaluated_points"] = 1
    validate.write_json(path, receipt)
    with pytest.raises(ValueError, match="accounting mismatch"):
        plot.read_run(path, validate.sha256(path))


def test_runtime_renderer_requires_identical_inputs(tmp_path):
    entries = []
    for index in range(2):
        path = tmp_path / f"profile{index}.json"
        validate.write_json(
            path,
            {
                "evidence_kind": "synthetic_performance_probe",
                "configuration": {"repeats": 1},
                "source_revision": "b" * 40,
                "executed_source_sha256": {"source.py": "c" * 64},
                "input_sha256": str(index) * 64,
                "timing": {"cpu_warm_seconds": [1.0], "gpu_warm_seconds": [0.5]},
            },
        )
        entries.append([str(index), str(path), validate.sha256(path)])
    with pytest.raises(ValueError, match="inputs do not match"):
        plot.runtime_profiles(entries)


def test_runtime_renderer_retains_all_cold_and_warm_points(tmp_path):
    path = tmp_path / "profile.json"
    validate.write_json(
        path,
        {
            "evidence_kind": "synthetic_performance_probe",
            "configuration": {"repeats": 2},
            "source_revision": "b" * 40,
            "executed_source_sha256": {"source.py": "c" * 64},
            "input_sha256": "d" * 64,
            "timing": {
                "cpu_warm_seconds": [1.0, 1.1],
                "gpu_warm_seconds": [0.5, 0.6],
                "cpu_first_seconds": 1.2,
                "gpu_cold_context_plus_first_scoring_seconds": 2.3,
            },
        },
    )
    result = plot.render(
        [], [["injected synthetic", str(path), validate.sha256(path)]], tmp_path / "runtime-plots"
    )
    assert result["runtime"][0]["profile"]["timing"]["cpu_warm_seconds"] == [1.0, 1.1]
    assert (tmp_path / "runtime-plots" / "full-runtime.png").stat().st_size > 1000
