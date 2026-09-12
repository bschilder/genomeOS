"""Tiny injected receipt/renderer checks, never the full matrix (design §7, §8)."""

from __future__ import annotations

import argparse
import json
from decimal import Decimal
from types import SimpleNamespace

import numpy as np
import pandas as pd
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


def test_extreme_domain_plot_displays_every_point_and_status(monkeypatch, tmp_path):
    outcomes = [
        {"group": "small", "concentration": c, "points": [{"log_absolute_error": "1e-12"}]}
        for c in (1e-10, 2.0, 1e100, 1e300)
    ]
    statuses = {
        "pass": 513,
        "expected_domain_refusal": 24,
        "candidate_mismatch": 11,
        "unexpected_evaluation_failure": 1,
    }
    accounting = {
        "evaluated_points": 4,
        "planned_points": 4,
        "law_status_counts": statuses,
        "incomplete_laws": 0,
        "zero_log_errors": 0,
        "float_underflow_comparisons": 12,
    }
    receipt = {
        "backend": "scipy",
        "matrix_sha256": "a",
        "complement_sha256": "b",
        "source_sha256": {"source": "c"},
        "complement_limitation": "not rounded inputs",
    }
    monkeypatch.setattr(plot, "read_run", lambda *args: (receipt, outcomes, accounting))
    figures = []
    monkeypatch.setattr(plot.plt, "close", figures.append)
    plot.render([["injected", "d"]], [], tmp_path / "domain-plot")
    figure = next(figure for figure in figures if hasattr(figure, "axes"))
    axis, inventory = figure.axes
    figure.canvas.draw()
    coordinates = np.concatenate([artist.get_offsets() for artist in axis.collections])
    assert len(coordinates) == 4
    for dimension, limits in enumerate((axis.get_xlim(), axis.get_ylim())):
        assert np.all(coordinates[:, dimension] >= limits[0])
        assert np.all(coordinates[:, dimension] <= limits[1])
    renderer = figure.canvas.get_renderer()
    for artist in inventory.texts:
        bounds = artist.get_window_extent(renderer)
        assert inventory.bbox.contains(bounds.x0, bounds.y0)
        assert inventory.bbox.contains(bounds.x1, bounds.y1)
    inventory_text = "\n".join(artist.get_text() for artist in inventory.texts)
    for name, count in statuses.items():
        assert f"{name}: {count}" in inventory_text


@pytest.mark.parametrize(
    "exception, status",
    [(ArithmeticError, "unexpected_evaluation_failure"), (KeyboardInterrupt, "incomplete_execution")],
)
def test_late_sampler_failure_preserves_receipt_and_rendered_points(
    inputs, monkeypatch, tmp_path, exception, status
):
    injected_matrix(monkeypatch, [case()])

    def fail(*args, **kwargs):
        raise exception("injected late sampler failure")

    monkeypatch.setattr(evaluate.CountPredictive, "sample_counts", fail)
    assert validate.run(inputs) == 1
    path = inputs.out / "receipt.json"
    receipt = json.loads(path.read_text())
    assert receipt["summary"]["evaluated_points"] == 2
    assert receipt["summary"]["law_status_counts"] == {status: 1}
    assert receipt["summary"]["incomplete_laws"] == (exception is KeyboardInterrupt)
    receipt["planned_points"] = 2
    validate.write_json(path, receipt)
    result = plot.render([[str(path), validate.sha256(path)]], [], tmp_path / "late-failure-plot")
    assert result["numerical"][0]["evaluated_points"] == 2
    assert result["numerical"][0]["law_status_counts"] == {status: 1}


def test_control_subcases_continue_and_account_for_dependencies(monkeypatch):
    controls = validate.count_recurrence_controls

    class FakeLaw:
        def __init__(self, *args, **kwargs):
            pass

        def cdf(self, *args):
            return np.zeros(5)

        def sample_counts(self, *args, **kwargs):
            values = np.zeros((129, 5), dtype=int)
            values[1, 1] = 3
            return values

    monkeypatch.setattr(controls, "CountPredictive", FakeLaw)
    monkeypatch.setattr(controls, "verified_law", lambda *args: SimpleNamespace(lower=[0.5]))
    monkeypatch.setattr(controls, "predictive_diagnostics", lambda *args, **kwargs: pd.DataFrame({"x": [1]}))
    chunks = []

    def partitions(*args, **kwargs):
        chunks.append(controls.recurrence.SUPPORT_CHUNK_SIZE)
        if len(chunks) == 1:
            raise ArithmeticError("injected first chunk failure")
        return SimpleNamespace(
            log_mass=lambda **kwargs: np.zeros((5, 129)),
            tails=lambda **kwargs: (np.zeros((5, 129)), np.zeros((5, 129))),
        )

    monkeypatch.setattr(controls.recurrence, "beta_binomial_log_partitions", partitions)
    events = []
    result = controls.mixture("scipy", np, events.append)
    statuses = {row["subcase_id"]: row["status"] for row in result["subcases"]}
    assert not result["passed"]
    assert statuses["mixture_cdf"] == "fail"
    assert statuses["chunk_default"] == "fail"
    assert statuses["chunk_257"] == "pass"
    assert statuses["chunk_log_mass"] == "incomplete"
    assert statuses["sample_determinism"] == "pass"
    assert statuses["diagnostic_determinism"] == "pass"
    assert chunks == [1024, 257]
    assert len(statuses) == len(result["planned_subcases"])
    assert {event["subcase_id"] for event in events if event.get("event") == "subcase_outcome"} == set(
        statuses
    )


def test_control_receipt_accounts_for_interrupted_and_unattempted_subcases(inputs, monkeypatch, tmp_path):
    from scripts.count_recurrence_control_plan import execute_subcases, subcase

    injected_matrix(monkeypatch, [case()])
    plan = [
        subcase("first"),
        subcase("blocked", "first"),
        subcase("independent"),
        subcase("interrupt"),
        subcase("unattempted"),
    ]
    visited = []

    def fail():
        raise AssertionError("injected early failure")

    def independent():
        visited.append("independent")
        return {"passed": True}

    def interrupt():
        raise KeyboardInterrupt("injected interruption")

    actions = {
        "first": fail,
        "blocked": lambda: {},
        "independent": independent,
        "interrupt": interrupt,
        "unattempted": lambda: {},
    }
    monkeypatch.setattr(validate.count_recurrence_controls, "CONTROL_SUBCASES", {"injected": plan})
    monkeypatch.setattr(
        validate.count_recurrence_controls,
        "CONTROLS",
        {"injected": lambda backend, xp, record: execute_subcases(plan, actions, record)},
    )
    assert validate.run(inputs) == 1
    path = inputs.out / "receipt.json"
    receipt = json.loads(path.read_text())
    assert visited == ["independent"]
    assert receipt["accounting_version"] == 2
    assert receipt["summary"]["control_subcase_status_counts"] == {"fail": 1, "pass": 1, "incomplete": 3}
    assert receipt["summary"]["accounted_control_subcases"] == 5
    assert receipt["summary"]["incomplete_control_subcases"] == 3
    receipt["planned_points"] = 2
    validate.write_json(path, receipt)
    result = plot.render([[str(path), validate.sha256(path)]], [], tmp_path / "interrupted-controls")
    assert result["numerical"][0]["control_subcase_status_counts"] == {"fail": 1, "pass": 1, "incomplete": 3}
    assert not result["numerical"][0]["run_passed"]


def test_sampler_independent_fixtures_survive_first_generation_failure(monkeypatch):
    controls = validate.count_recurrence_controls
    calls = []

    class FakeLaw:
        def __init__(self, *args, **kwargs):
            calls.append(1)
            if len(calls) == 1:
                raise ArithmeticError("injected first sampler fixture failure")

        def sample_counts(self, *args, **kwargs):
            return np.full((20000, 1), 2, dtype=int)

    monkeypatch.setattr(controls, "CountPredictive", FakeLaw)
    monkeypatch.setattr(
        controls,
        "verified_law",
        lambda *args: SimpleNamespace(mean=Decimal(2), variance=Decimal(0), fourth_central=Decimal(0)),
    )
    result = controls.sampler("scipy", np)
    statuses = [item["status"] for item in result["subcases"]]
    assert len(calls) == 3 and len(statuses) == 15
    assert statuses.count("fail") == 1 and statuses.count("incomplete") == 4
    assert statuses.count("pass") == 10 and not result["passed"]


def test_domain_accepted_bad_parameter_does_not_hide_later_cases(monkeypatch):
    controls = validate.count_recurrence_controls
    original = controls.CountPredictive

    def accept_first_invalid(means, concentrations, **kwargs):
        if concentrations[0, 0] == np.nextafter(1e300, np.inf):
            concentrations = np.array([[20.0]])
        return original(means, concentrations, **kwargs)

    monkeypatch.setattr(controls, "CountPredictive", accept_first_invalid)
    result = controls.domain("scipy", np)
    statuses = {item["subcase_id"]: item["status"] for item in result["subcases"]}
    assert statuses["invalid_parameter:0"] == "fail"
    assert statuses["invalid_parameter:5"] == "pass"
    assert statuses["invalid_counts:4"] == "pass"
    assert statuses["degenerate_scope"] == "pass"
    assert len(statuses) == len(result["planned_subcases"])
    assert list(statuses.values()).count("fail") == 1


def test_quantile_failure_keeps_later_ties_and_diagnostics(monkeypatch):
    controls = validate.count_recurrence_controls
    original = controls.CountPredictive
    calls = []

    def wrong_first_cdf(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            return SimpleNamespace(cdf=lambda *args: np.array([0.25]))
        return original(*args, **kwargs)

    monkeypatch.setattr(controls, "CountPredictive", wrong_first_cdf)
    result = controls.quantiles_and_diagnostics("scipy", np)
    statuses = {item["subcase_id"]: item["status"] for item in result["subcases"]}
    assert statuses["tie:0:cdf"] == "fail"
    assert statuses["tie:2:level_one"] == "pass"
    assert statuses["uniform:129"] == "pass"
    assert statuses["diagnostic_values"] == "pass"
    assert statuses["diagnostic_determinism"] == "pass"
    assert list(statuses.values()).count("fail") == 1
    assert len(statuses) == len(result["planned_subcases"])


def test_legacy_complete_failed_receipt_renders_without_mutation(inputs, monkeypatch, tmp_path):
    path = tiny_receipt(inputs, monkeypatch)
    receipt = json.loads(path.read_text())
    receipt.pop("accounting_version")
    receipt.pop("planned_control_subcases")
    for key in list(receipt["summary"]):
        if "subcase" in key:
            receipt["summary"].pop(key)
    receipt["summary"]["passed"] = False
    receipt["summary"]["law_status_counts"] = {"candidate_mismatch": 1}
    journal = inputs.out / "events.jsonl"
    events = [json.loads(line) for line in journal.read_text().splitlines()]
    for event in events:
        if event["event"] == "outcome":
            event["status"] = "candidate_mismatch"
    journal.write_text("".join(json.dumps(event) + "\n" for event in events))
    receipt["file_sha256"]["events.jsonl"] = validate.sha256(journal)
    validate.write_json(path, receipt)
    before = {item: validate.sha256(item) for item in (path, journal)}
    result = plot.render([[str(path), validate.sha256(path)]], [], tmp_path / "legacy-plot")
    assert result["numerical"][0]["control_subcase_accounting"] == "not_recorded_by_legacy_adapter"
    assert result["numerical"][0]["law_status_counts"] == {"candidate_mismatch": 1}
    assert not result["numerical"][0]["run_passed"]
    assert before == {item: validate.sha256(item) for item in before}
