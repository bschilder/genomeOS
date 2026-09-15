"""Counted runner orchestration fixtures; no actual scientific computation."""
from __future__ import annotations

import importlib
from dataclasses import replace

import pytest
from heterogeneity_runner_fixtures import (
    accepted,
    campaign,
    dataset,
    failed,
    fit_summary,
    quantities,
)

from genomeos.validation.heterogeneity_attempts import FitAttemptResult
from genomeos.validation.heterogeneity_runner_store import LocalB0HStore


def mocked_runner(monkeypatch, *, retry=False, terminal=False):
    runner = importlib.import_module("genomeos.validation.heterogeneity_runner")
    counts = {"generation": 0, "fit": 0, "quantities": 0, "summary": 0}

    def generation(case):
        counts["generation"] += 1
        return dataset(case.study_id, case.case_id, case.track_id)

    def fit(data, *, spec):
        counts["fit"] += 1
        if spec.attempt_id == 0 and (retry or terminal):
            return failed(data, "failed" if terminal else "convergence_failed")
        return accepted(data, spec.attempt_id)

    def selected(data, *, attempt):
        counts["quantities"] += 1
        assert attempt.spec.attempt_id == (1 if retry else 0)
        assert attempt.fit.mean_draws.shape == (4, 1000 if retry else 500, 1)
        return quantities(data, attempt)

    def summary(data, *, attempt, cdf_backend):
        counts["summary"] += 1
        assert cdf_backend == "cupy"
        return fit_summary(data, attempt, cdf_backend)

    monkeypatch.setattr(runner, "generate_sbc_case", generation)
    monkeypatch.setattr(runner, "run_fit_attempt", fit)
    monkeypatch.setattr(runner, "selected_sbc_quantities", selected)
    monkeypatch.setattr(runner, "summarize_heterogeneity_fit", summary)
    return runner, counts


@pytest.mark.parametrize(
    "study,expected",
    [(0, {"generation": 1, "fit": 1, "quantities": 1, "summary": 1}),
     (1, {"generation": 1, "fit": 1, "quantities": 0, "summary": 1})],
)
def test_fresh_case_and_reuse_have_exact_counts(tmp_path, monkeypatch, study, expected):
    runner, counts = mocked_runner(monkeypatch)
    manifest, admission, null = campaign(tmp_path)
    case = dataset(study).case_id
    with LocalB0HStore.create(tmp_path / "study.sqlite3", manifest=manifest, admission=admission,
                              null=null, owner_id="fixture-owner") as store:
        result = runner.execute_b0h_case(manifest, case, store)
        before = store.inventory()
        assert counts == expected
        loaded = runner.execute_b0h_case(manifest, case, store)
        assert counts == expected
        assert store.inventory() == before
        assert tuple(s.encoded for s in loaded.stages) == tuple(s.encoded for s in result.stages)


def test_only_completed_convergence_failure_admits_retry(tmp_path, monkeypatch):
    runner, counts = mocked_runner(monkeypatch, retry=True)
    manifest, admission, null = campaign(tmp_path)
    with LocalB0HStore.create(tmp_path / "study.sqlite3", manifest=manifest, admission=admission,
                              null=null, owner_id="fixture-owner") as store:
        result = runner.execute_b0h_case(manifest, dataset().case_id, store)
    assert counts == {"generation": 1, "fit": 2, "quantities": 1, "summary": 1}
    attempts = tuple(s for s in result.stages if s.start.key.stage == "fit")
    assert tuple(s.value.status for s in attempts) == ("convergence_failed", "accepted")
    from genomeos.validation.heterogeneity_runner_wire import record_digest
    assert record_digest(attempts[0].completion) in attempts[1].start.prerequisites


def test_runtime_failure_has_no_retry_or_diagnostics(tmp_path, monkeypatch):
    runner, counts = mocked_runner(monkeypatch, terminal=True)
    manifest, admission, null = campaign(tmp_path)
    with LocalB0HStore.create(tmp_path / "study.sqlite3", manifest=manifest, admission=admission,
                              null=null, owner_id="fixture-owner") as store:
        runner.execute_b0h_case(manifest, dataset().case_id, store)
    assert counts == {"generation": 1, "fit": 1, "quantities": 0, "summary": 0}


def test_wrong_returned_fit_is_retained_without_retry(tmp_path, monkeypatch):
    runner, counts = mocked_runner(monkeypatch)

    def rejected(data, *, spec):
        counts["fit"] += 1
        return FitAttemptResult(spec, "identity_rejected", None, None,
                                ("return_type",), "builtins.dict")

    monkeypatch.setattr(runner, "run_fit_attempt", rejected)
    manifest, admission, null = campaign(tmp_path)
    with LocalB0HStore.create(tmp_path / "study.sqlite3", manifest=manifest, admission=admission,
                              null=null, owner_id="fixture-owner") as store:
        result = runner.execute_b0h_case(manifest, dataset().case_id, store)
    assert result.stages[-1].value.returned_type == "builtins.dict"
    assert counts == {"generation": 1, "fit": 1, "quantities": 0, "summary": 0}


def test_quantities_execution_failure_keeps_independent_summary(tmp_path, monkeypatch):
    runner, counts = mocked_runner(monkeypatch)

    def broken(data, *, attempt):
        counts["quantities"] += 1
        raise KeyError("literal adapter defect")

    monkeypatch.setattr(runner, "selected_sbc_quantities", broken)
    manifest, admission, null = campaign(tmp_path)
    with LocalB0HStore.create(tmp_path / "study.sqlite3", manifest=manifest, admission=admission,
                              null=null, owner_id="fixture-owner") as store:
        result = runner.execute_b0h_case(manifest, dataset().case_id, store)
    assert counts == {"generation": 1, "fit": 1, "quantities": 1, "summary": 1}
    assert result.stages[2].failure.exception_class == "builtins.KeyError"
    assert result.stages[3].value.predictive.status == "complete"


def test_restoration_rejects_changed_selected_pairing(tmp_path, monkeypatch):
    runner, _ = mocked_runner(monkeypatch)
    manifest, admission, null = campaign(tmp_path)
    with LocalB0HStore.create(tmp_path / "study.sqlite3", manifest=manifest, admission=admission,
                              null=null, owner_id="fixture-owner") as store:
        result = runner.execute_b0h_case(manifest, dataset().case_id, store)
    binding = importlib.import_module("genomeos.validation.heterogeneity_runner_binding")
    original = result.stages[2]
    altered = replace(original.value, selected_indices=((0, 1), (1, 3), (2, 6), (3, 9)))
    with pytest.raises(ValueError):
        binding.validate_case_evidence(manifest, replace(result, stages=(
            result.stages[0], result.stages[1], replace(original, value=altered), result.stages[3])))


def rebound_stage(manifest, stage, value):
    from genomeos.validation.heterogeneity_codec import encode_b0h_evidence
    from genomeos.validation.heterogeneity_runner_wire import evidence_receipt, record_digest
    encoded = encode_b0h_evidence(value, limits=manifest.limits)
    receipt = evidence_receipt(stage.start, encoded, limits=manifest.limits)
    completion = stage.completion.model_copy(update={"receipt_sha256": record_digest(receipt)})
    return replace(stage, completion=completion, receipt=receipt, encoded=encoded, value=value)


def test_equal_total_dataset_swap_breaks_retained_fit_prerequisite(tmp_path, monkeypatch):
    runner, _ = mocked_runner(monkeypatch)
    original = dataset()
    rows = list(original.training)
    rows[2] = replace(rows[2], ac=1)
    original = replace(original, training=tuple(rows))
    changed = list(original.training)
    changed[2], changed[3] = replace(changed[2], ac=0), replace(changed[3], ac=1)
    altered = replace(original, training=tuple(changed))
    assert sum(r.ac for r in original.training) == sum(r.ac for r in altered.training) == 1
    monkeypatch.setattr(runner, "generate_sbc_case", lambda case: original)

    # The shared codec fixture deliberately uses zero AC for its generic fits;
    # this test's changed-count dataset needs an input-bound typed count.
    def fit_with_input_counts(data, *, spec):
        attempt = accepted(data, spec.attempt_id)
        counts = tuple(
            replace(
                count,
                training_ac=sum(row.ac for row in data.training if row.an > 0),
                training_an=sum(row.an for row in data.training if row.an > 0),
            )
            for count in attempt.fit.training_counts
        )
        return replace(attempt, fit=replace(attempt.fit, training_counts=counts))

    monkeypatch.setattr(runner, "run_fit_attempt", fit_with_input_counts)
    manifest, admission, null = campaign(tmp_path)
    with LocalB0HStore.create(tmp_path / "study.sqlite3", manifest=manifest, admission=admission,
                              null=null, owner_id="fixture-owner") as store:
        result = runner.execute_b0h_case(manifest, original.case_id, store)
    binding = importlib.import_module("genomeos.validation.heterogeneity_runner_binding")
    replaced = rebound_stage(manifest, result.stages[0], altered)
    with pytest.raises(ValueError, match="dependency"):
        binding.validate_case_evidence(manifest, replace(result, stages=(replaced,) + result.stages[1:]))


def test_wrong_track_and_orphan_retry_are_rejected(tmp_path, monkeypatch):
    runner, _ = mocked_runner(monkeypatch, retry=True)
    manifest, admission, null = campaign(tmp_path)
    with LocalB0HStore.create(tmp_path / "study.sqlite3", manifest=manifest, admission=admission,
                              null=null, owner_id="fixture-owner") as store:
        result = runner.execute_b0h_case(manifest, dataset().case_id, store)
    binding = importlib.import_module("genomeos.validation.heterogeneity_runner_binding")
    other_track = rebound_stage(manifest, result.stages[2], accepted(dataset(track=1), 1))
    with pytest.raises(ValueError):
        binding.validate_case_evidence(manifest, replace(result,
            stages=result.stages[:2] + (other_track,) + result.stages[3:]))
    with pytest.raises(ValueError, match="orphan"):
        binding.validate_case_evidence(manifest, replace(result,
            stages=(result.stages[0],) + result.stages[2:]))


def test_changed_shared_heldout_retained_order_is_rejected(tmp_path, monkeypatch):
    runner, _ = mocked_runner(monkeypatch)
    manifest, admission, null = campaign(tmp_path)
    with LocalB0HStore.create(tmp_path / "study.sqlite3", manifest=manifest, admission=admission,
                              null=null, owner_id="fixture-owner") as store:
        result = runner.execute_b0h_case(manifest, dataset(2).case_id, store)
    binding = importlib.import_module("genomeos.validation.heterogeneity_runner_binding")
    original = result.stages[-1].value
    altered_predictive = object.__new__(type(original.predictive))
    for name in original.predictive.__dataclass_fields__:
        object.__setattr__(altered_predictive, name, getattr(original.predictive, name))
    object.__setattr__(altered_predictive, "targets", original.predictive.targets[::-1])
    altered = object.__new__(type(original))
    for name in original.__dataclass_fields__:
        object.__setattr__(altered, name, getattr(original, name))
    object.__setattr__(altered, "predictive", altered_predictive)
    with pytest.raises(ValueError):
        binding.validate_case_evidence(manifest, replace(result,
            stages=result.stages[:-1] + (replace(result.stages[-1], value=altered),)))


def test_unexpected_structural_return_is_retained_and_terminal(tmp_path, monkeypatch):
    from genomeos.validation.heterogeneity_attempts import StructuralCheckResult
    runner, counts = mocked_runner(monkeypatch)
    calls = []

    def structural(data):
        calls.append(data.case_id)
        return StructuralCheckResult(data.case_id, "unexpected_return", None, None, "builtins.dict")

    monkeypatch.setattr(runner, "exercise_unavailable", structural)
    manifest, admission, null = campaign(tmp_path)
    with LocalB0HStore.create(tmp_path / "study.sqlite3", manifest=manifest, admission=admission,
                              null=null, owner_id="fixture-owner") as store:
        result = runner.execute_b0h_case(manifest, dataset(3).case_id, store)
        runner.execute_b0h_case(manifest, dataset(3).case_id, store)
    assert calls == [dataset(3).case_id]
    assert result.stages[-1].value.status == "unexpected_return"
    assert counts == {"generation": 1, "fit": 0, "quantities": 0, "summary": 0}


def test_competing_process_cannot_deliver_a_scientific_stage(tmp_path, monkeypatch):
    import os
    import subprocess
    import sys
    from pathlib import Path
    runner, counts = mocked_runner(monkeypatch)
    manifest, admission, null = campaign(tmp_path)
    child_code = """
import sys
from pathlib import Path
from heterogeneity_runner_fixtures import campaign
from genomeos.validation.heterogeneity_runner_store import LocalB0HStore, StoreUnavailable
from genomeos.validation.heterogeneity_runner import execute_b0h_case
parent = Path(sys.argv[1])
manifest, admission, null = campaign(parent)
try:
    with LocalB0HStore(parent / "study.sqlite3", manifest=manifest,
                       admission=admission, null=null, owner_id="competing-process") as store:
        raise AssertionError("competing process acquired scientific admission")
except StoreUnavailable:
    print("blocked before any stage call")
"""
    with LocalB0HStore.create(tmp_path / "study.sqlite3", manifest=manifest, admission=admission,
                              null=null, owner_id="fixture-owner") as store:
        process = subprocess.run([sys.executable, "-c", child_code, str(tmp_path)], check=True,
            capture_output=True, text=True, env={**os.environ,
                "PYTHONPATH": str(Path(__file__).parent) + os.pathsep + os.environ.get("PYTHONPATH", "")})
        assert process.stdout.strip() == "blocked before any stage call"
        runner.execute_b0h_case(manifest, dataset().case_id, store)
    assert counts == {"generation": 1, "fit": 1, "quantities": 1, "summary": 1}


@pytest.mark.parametrize("where", ("before_call", "during_call", "after_return"))
def test_process_loss_never_redelivers(tmp_path, monkeypatch, where):
    runner, counts = mocked_runner(monkeypatch)
    manifest, admission, null = campaign(tmp_path)
    path = tmp_path / "study.sqlite3"
    with LocalB0HStore.create(path, manifest=manifest, admission=admission,
                              null=null, owner_id="fixture-owner") as store:
        if where == "before_call":
            original = store.start

            def interrupted(record):
                original(record)
                raise KeyboardInterrupt

            monkeypatch.setattr(store, "start", interrupted)
        elif where == "during_call":
            def interrupted(case):
                counts["generation"] += 1
                raise KeyboardInterrupt

            monkeypatch.setattr(runner, "generate_sbc_case", interrupted)
        else:
            def interrupted(*args, **kwargs):
                raise KeyboardInterrupt

            monkeypatch.setattr(runner, "encode_b0h_evidence", interrupted)
        with pytest.raises(KeyboardInterrupt):
            runner.execute_b0h_case(manifest, dataset().case_id, store)
    before = dict(counts)
    with LocalB0HStore(path, manifest=manifest, admission=admission,
                       null=null, owner_id="replacement-process") as store:
        result = runner.execute_b0h_case(manifest, dataset().case_id, store)
    assert counts == before
    assert counts["fit"] == counts["quantities"] == counts["summary"] == 0
    assert result.stages[0].loss is not None
    assert result.stages[0].completion is None


def test_generation_failure_has_no_fit_or_diagnostic_calls(tmp_path, monkeypatch):
    from genomeos.validation.heterogeneity_simulation_types import GenerationFailure
    runner, counts = mocked_runner(monkeypatch)

    def generation(case):
        counts["generation"] += 1
        data = dataset()
        return GenerationFailure(case, data.provenance, "truth_mean", None,
                                 "rng_exception", None, None, None, None,
                                 "ValueError", "literal synthetic generation failure")

    monkeypatch.setattr(runner, "generate_sbc_case", generation)
    manifest, admission, null = campaign(tmp_path)
    with LocalB0HStore.create(tmp_path / "study.sqlite3", manifest=manifest, admission=admission,
                              null=null, owner_id="fixture-owner") as store:
        runner.execute_b0h_case(manifest, dataset().case_id, store)
    assert counts == {"generation": 1, "fit": 0, "quantities": 0, "summary": 0}


def test_actual_structural_wrapper_refuses_before_graph_or_sampler(tmp_path, monkeypatch):
    import genomeos.surfaces.reference_heterogeneity as scientific
    import genomeos.validation.heterogeneity_attempts as attempts
    runner, counts = mocked_runner(monkeypatch)
    calls = {"structural": 0, "fitter": 0, "graph": 0, "sampler": 0}
    actual_wrapper = attempts.exercise_unavailable
    actual_fitter = attempts.fit_reference_population_heterogeneity

    def fitter(*args, **kwargs):
        calls["fitter"] += 1
        return actual_fitter(*args, **kwargs)

    def structural(data):
        calls["structural"] += 1
        return actual_wrapper(data)

    def graph(*args, **kwargs):
        calls["graph"] += 1
        raise AssertionError("structural case entered graph")

    def sampler(*args, **kwargs):
        calls["sampler"] += 1
        raise AssertionError("structural case entered sampler")

    monkeypatch.setattr(attempts, "fit_reference_population_heterogeneity", fitter)
    monkeypatch.setattr(runner, "exercise_unavailable", structural)
    monkeypatch.setattr(scientific.pm, "Model", graph)
    monkeypatch.setattr(scientific.pm, "sample", sampler)
    manifest, admission, null = campaign(tmp_path)
    with LocalB0HStore.create(tmp_path / "study.sqlite3", manifest=manifest, admission=admission,
                              null=null, owner_id="fixture-owner") as store:
        result = runner.execute_b0h_case(manifest, dataset(3).case_id, store)
    assert calls == {"structural": 1, "fitter": 1, "graph": 0, "sampler": 0}
    assert counts == {"generation": 1, "fit": 0, "quantities": 0, "summary": 0}
    assert result.stages[-1].value.status == "expected_refusal"
