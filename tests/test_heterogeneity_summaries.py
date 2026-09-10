"""Constructed B0H summary evidence; no sampler execution (design §§7–8,12)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace

import numpy as np
import pandas as pd
import pytest

import genomeos.validation.heterogeneity_summaries as summaries
from genomeos.surfaces.heterogeneity_types import (
    PopulationHeterogeneityFit,
    VariantHeterogeneityDiagnostics,
    VariantTrainingCounts,
)
from genomeos.surfaces.reference_heterogeneity import (
    predict_reference_population_heterogeneity,
)
from genomeos.validation.heterogeneity_attempts import (
    AttemptError,
    FitAttemptResult,
    FitIdentityError,
    plan_fit_attempt,
)
from genomeos.validation.heterogeneity_diagnostic_seeds import DiagnosticSeedIdentity
from genomeos.validation.heterogeneity_sbc_controls import DiagnosticCallError
from genomeos.validation.heterogeneity_simulation_types import (
    AllUnavailableDataset,
    GeneratedDataset,
    GenerationProvenance,
    HeldoutTarget,
    ParameterTruth,
    SbcCaseId,
    SharedHistory,
    fixed_simulation_truth,
    generation_id,
    sbc_seed_identity,
    simulation_reference_count,
    simulation_training_an,
)
from genomeos.validation.heterogeneity_summary_types import (
    ParameterPosteriorSummary,
    predictive_summary_rows,
)
from genomeos.validation.predictive import CountPredictive


def ordinary_target():
    case = SbcCaseId(0, 0, 0, 0)
    row = simulation_reference_count(generation_id(case), "heldout", "fresh_population", 2, 20)
    return HeldoutTarget("fresh_population", row, 0.5, None, None, None, None)


def literal_frame():
    return pd.DataFrame(
        {
            "log_score": [-np.inf],
            "absolute_error": [0.4],
            "squared_error": [0.16],
            "coverage_50": [False],
            "interval_width_50": [0.5],
            "coverage_80": [True],
            "interval_width_80": [0.8],
            "coverage_95": [True],
            "interval_width_95": [1.0],
            "randomized_pit": [0.1],
        }
    )


def test_literal_parameter_interval_and_error_evidence():
    item = ParameterPosteriorSummary("mean", 0.25, 0.5, (0.1, 0.2, 0.25, 0.5, 0.75, 0.8, 0.9), 2000)
    assert item.absolute_error == 0.25
    assert item.squared_error == 0.0625
    assert item.coverage == (True, True, True)
    assert item.interval_width == pytest.approx((0.5, 0.6, 0.8), rel=0, abs=2e-15)
    with pytest.raises(FrozenInstanceError):
        item.estimate = 0.25
    for changes in (
        {"parameter": "latent_frequency"},
        {"draw_count": True},
        {"truth": np.nan},
        {"estimate": 0.0},
        {"quantiles": (0.2,)},
        {"quantiles": [0.1, 0.2, 0.25, 0.5, 0.75, 0.8, 0.9]},
        {"quantiles": (0.1, 0.2, 0.75, 0.5, 0.25, 0.8, 0.9)},
    ):
        with pytest.raises(ValueError):
            replace(item, **changes)


def test_negative_infinite_log_score_is_retained():
    target = ordinary_target()
    rows = predictive_summary_rows(literal_frame(), targets=(target,))
    assert rows[0].target == target
    assert rows[0].log_score == -np.inf
    assert rows[0].coverage == (False, True, True)
    assert rows[0].interval_width == (0.5, 0.8, 1.0)
    assert rows[0].randomized_pit == 0.1


@pytest.mark.parametrize(
    "field,value",
    [
        ("log_score", np.nan),
        ("log_score", np.inf),
        ("log_score", 0.01),
        ("absolute_error", np.inf),
        ("squared_error", -0.1),
        ("interval_width_80", 1.1),
        ("randomized_pit", np.nan),
        ("randomized_pit", 1.1),
    ],
)
def test_nonfinite_or_out_of_domain_frame_is_a_defect(field, value):
    frame = literal_frame()
    frame[field] = [value]
    with pytest.raises(ValueError):
        predictive_summary_rows(frame, targets=(ordinary_target(),))


def test_malformed_frames_are_not_coerced():
    frame = literal_frame()
    malformed = (
        frame.to_dict(),
        frame.iloc[:0],
        frame.assign(extra=0),
        frame.rename(index={0: "row0"}),
        frame.drop(columns="log_score"),
        frame.loc[:, frame.columns[::-1]],
        frame.astype({"absolute_error": "object"}),
        frame.astype({"squared_error": "float32"}),
        frame.astype({"randomized_pit": "complex128"}),
        frame.assign(coverage_50=1),
        frame.assign(absolute_error=True),
        frame.assign(coverage_50=True, coverage_80=False),
        frame.assign(interval_width_50=0.9),
        pd.concat([frame, frame]),
    )
    for bad in malformed:
        with pytest.raises(ValueError):
            predictive_summary_rows(bad, targets=(ordinary_target(),))


def test_output_rows_retain_no_mutable_dataframe_reference():
    frame = literal_frame()
    rows = predictive_summary_rows(frame, targets=(ordinary_target(),))
    frame.loc[0, "randomized_pit"] = 0.9
    assert rows[0].randomized_pit == 0.1
    with pytest.raises(FrozenInstanceError):
        rows[0].randomized_pit = 0.9


def literal_dataset(study=0, case_number=0, track=0):
    case = SbcCaseId(track, study, case_number, 0)
    generation = generation_id(case)
    provenance = GenerationProvenance(
        generation, tuple(sbc_seed_identity(case, purpose_id=purpose, attempt_id=0) for purpose in range(4))
    )
    truth = fixed_simulation_truth(case) or ParameterTruth(0.5, 0.2)
    ans = simulation_training_an(case)
    counts = tuple(int(an * truth.mean) if study == 4 else an // 2 for an in ans)
    training = tuple(
        simulation_reference_count(generation, "train", str(i), ac, an)
        for i, (ac, an) in enumerate(zip(counts, ans, strict=True))
    )
    history = None
    if study == 2:
        history = SharedHistory((0.2, 0.8), (0.4,) * 16, (True,) * 8 + (False,) * 8)
        latents = (0.2,) * 8 + (0.4,) * 8
        heldouts = (
            HeldoutTarget(
                "shared_cluster0",
                simulation_reference_count(generation, "heldout", "shared_cluster0", 2, 20),
                0.2,
                0,
                0.2,
                0.3,
                True,
            ),
            HeldoutTarget(
                "fresh_cluster",
                simulation_reference_count(generation, "heldout", "fresh_cluster", 17, 20),
                0.7,
                2,
                0.9,
                0.7,
                False,
            ),
        )
    else:
        latent = truth.mean if truth.rho == 0.0 else 0.5
        latents = (latent,) * 16
        ac = int(20 * truth.mean) if study == 4 else 2
        heldouts = (
            HeldoutTarget(
                "fresh_population",
                simulation_reference_count(generation, "heldout", "fresh_population", ac, 20),
                latent,
                None,
                None,
                None,
                None,
            ),
        )
    return GeneratedDataset(case, provenance, truth, training, latents, history, heldouts, 0, 0)


def literal_attempt(dataset, attempt_id=0, grid=False):
    spec = plan_fit_attempt(dataset, attempt_id=attempt_id)
    shape = (4, spec.config.draws, 1)
    if grid:
        size = 4 * spec.config.draws
        mean = ((np.arange(size, dtype=np.float64) + 1) / (size + 1)).reshape(shape)
        rho = mean / 2
    else:
        mean = np.full(shape, 0.5, dtype=np.float64)
        rho = np.full(shape, 1 / 3, dtype=np.float64)
    variant = dataset.training[0].variant_id
    available = tuple(row for row in dataset.training if row.an > 0)
    fit = PopulationHeterogeneityFit(
        spec.config,
        (variant,),
        mean,
        rho,
        tuple(sorted(row.record_id for row in dataset.training)),
        tuple(sorted({row.group_id for row in dataset.training})),
        tuple(sorted(row.record_id for row in dataset.training if row.an == 0)),
        (
            VariantTrainingCounts(
                variant, len(available), sum(row.ac for row in available), sum(row.an for row in available)
            ),
        ),
        (VariantHeterogeneityDiagnostics(variant, 1.0, 250.0, 250.0),),
        0,
    )
    return FitAttemptResult(spec, "accepted", fit, None, (), None)


def raising(error):
    def fail(*args, **kwargs):
        raise error

    return fail


def test_all_draw_linear_quantiles_survive_predictor_failure(monkeypatch):
    data = literal_dataset()
    attempt = literal_attempt(data, grid=True)
    monkeypatch.setattr(
        summaries,
        "predict_reference_population_heterogeneity",
        raising(ArithmeticError("literal predictor failure")),
    )
    result = summaries.summarize_heterogeneity_fit(data, attempt=attempt, cdf_backend="scipy")
    expected = tuple((1 + 1999 * p) / 2001 for p in (0.025, 0.1, 0.25, 0.5, 0.75, 0.9, 0.975))
    mean, rho = result.parameters
    assert mean.quantiles == pytest.approx(expected, rel=0, abs=2e-15)
    assert rho.quantiles == pytest.approx(tuple(q / 2 for q in expected), rel=0, abs=2e-15)
    assert mean.estimate == pytest.approx(0.5, rel=0, abs=2e-15)
    assert rho.estimate == pytest.approx(0.25, rel=0, abs=2e-15)
    assert mean.draw_count == rho.draw_count == 2000
    assert rho.absolute_error == pytest.approx(0.05, rel=0, abs=2e-15)
    assert rho.squared_error == pytest.approx(0.0025, rel=0, abs=2e-15)
    assert result.predictive.status == "prediction_failed"
    assert result.predictive.prediction is None and result.predictive.rows == ()
    assert result.predictive.error == DiagnosticCallError(
        "builtins.ArithmeticError", "literal predictor failure"
    )
    assert result.h_ess_status == result.h_mcse_status == "not_computed"


@pytest.mark.parametrize(
    "bad",
    [
        [0.5] * 7,
        np.full(7, "0.5"),
        np.full(7, 0.5, dtype=np.float32),
        np.full((1, 7), 0.5),
        np.full(6, 0.5),
        np.full(7, np.nan),
        np.full(7, np.inf),
        np.full(7, True),
        np.full(7, 0.5 + 0j),
    ],
)
def test_malformed_quantiles_propagate_before_seed_or_prediction(monkeypatch, bad):
    data = literal_dataset()
    attempt = literal_attempt(data)
    monkeypatch.setattr(summaries.np, "quantile", lambda *a, **k: bad)
    sentinel = raising(AssertionError("diagnostic work must not begin"))
    monkeypatch.setattr(summaries, "DiagnosticSeedIdentity", sentinel)
    monkeypatch.setattr(summaries, "predict_reference_population_heterogeneity", sentinel)
    with pytest.raises(ValueError, match="posterior quantiles"):
        summaries.summarize_heterogeneity_fit(data, attempt=attempt, cdf_backend="scipy")


@pytest.mark.parametrize("bad", [True, "0.5", np.float32(0.5), np.nan, np.inf, np.array(0.5)])
def test_malformed_mean_propagates_without_conversion(monkeypatch, bad):
    data = literal_dataset()
    attempt = literal_attempt(data)
    monkeypatch.setattr(summaries.np, "mean", lambda *a, **k: bad)
    sentinel = raising(AssertionError("diagnostic work must not begin"))
    monkeypatch.setattr(summaries, "DiagnosticSeedIdentity", sentinel)
    monkeypatch.setattr(summaries, "predict_reference_population_heterogeneity", sentinel)
    with pytest.raises(ValueError, match="posterior mean"):
        summaries.summarize_heterogeneity_fit(data, attempt=attempt, cdf_backend="scipy")


def test_actual_predictor_and_scorer_uniform_count_anchor_and_vector_pit():
    data = literal_dataset(study=2)
    attempt = literal_attempt(data)
    result = summaries.summarize_heterogeneity_fit(data, attempt=attempt, cdf_backend="scipy")
    evidence = result.predictive
    assert evidence.status == "complete"
    assert tuple(row.target.kind for row in evidence.rows) == ("shared_cluster0", "fresh_cluster")
    assert tuple(row.target.row.ac for row in evidence.rows) == (2, 17)
    assert evidence.prediction.observation_ids == tuple(t.row.record_id for t in data.heldouts)
    assert evidence.prediction.marginal_predictive.mean_draws.shape == (2000, 2)
    assert np.all(evidence.prediction.marginal_predictive.mean_draws == 0.5)
    np.testing.assert_allclose(evidence.prediction.marginal_predictive.concentration, 2.0, rtol=0, atol=2e-14)
    assert [row.log_score for row in evidence.rows] == pytest.approx([-np.log(21)] * 2, rel=0, abs=2e-12)
    assert [row.absolute_error for row in evidence.rows] == pytest.approx([0.4, 0.35], rel=0, abs=2e-15)
    assert [row.squared_error for row in evidence.rows] == pytest.approx([0.16, 0.1225], rel=0, abs=2e-15)
    assert all(row.coverage == (False, True, True) for row in evidence.rows)
    assert all(
        row.interval_width == pytest.approx((0.5, 0.8, 1.0), rel=0, abs=2e-15) for row in evidence.rows
    )
    entropy = (42, 211, 1, 0, 2, 0, 0, 7, 0)
    words = tuple(int(word) for word in np.random.SeedSequence(entropy).generate_state(4, dtype=np.uint32))
    scalar = sum(word << (32 * i) for i, word in enumerate(words))
    assert evidence.seed.entropy == entropy and evidence.seed.spawn_key == ()
    assert evidence.seed_words == words and evidence.seed_uint128 == scalar
    uniforms = np.random.Generator(np.random.PCG64(scalar)).random(2)
    assert [row.randomized_pit for row in evidence.rows] == pytest.approx(
        ((2 + uniforms[0]) / 21, (17 + uniforms[1]) / 21), rel=0, abs=2e-12
    )
    assert result.parameters[0].truth == 0.01
    assert result.parameters[1].truth == 0.1


def test_one_original_order_vector_call_and_actual_scalar_seed(monkeypatch):
    data = literal_dataset(study=2, track=1)
    attempt = literal_attempt(data, attempt_id=1)
    predictor = summaries.predict_reference_population_heterogeneity
    events = []

    def predicted(fitted, testing, *, cdf_backend):
        events.append(("predictor", fitted is attempt.fit, tuple(testing), cdf_backend))
        return predictor(fitted, testing, cdf_backend=cdf_backend)

    def diagnosed(predictive, ac, an, seed):
        events.append(("diagnostics", tuple(ac), tuple(an), seed))
        first = literal_frame()
        second = literal_frame().assign(absolute_error=0.35, squared_error=0.1225, randomized_pit=0.85)
        return pd.concat((first, second), ignore_index=True)

    monkeypatch.setattr(summaries, "predict_reference_population_heterogeneity", predicted)
    monkeypatch.setattr(summaries, "predictive_diagnostics", diagnosed)
    result = summaries.summarize_heterogeneity_fit(data, attempt=attempt, cdf_backend="scipy")
    assert len(events) == 2
    assert events[0] == ("predictor", True, tuple(t.row for t in data.heldouts), "scipy")
    assert events[1] == ("diagnostics", (2, 17), (20, 20), result.predictive.seed_uint128)
    assert result.predictive.seed == DiagnosticSeedIdentity(data.case_id, 1, 7, ())
    assert result.parameters[0].draw_count == result.predictive.draw_count == 4000
    assert [(r.target.kind, r.absolute_error, r.randomized_pit) for r in result.predictive.rows] == [
        ("shared_cluster0", 0.4, 0.1),
        ("fresh_cluster", 0.35, 0.85),
    ]


def test_scorer_exception_retains_actual_prediction_and_parameters(monkeypatch):
    data = literal_dataset()
    attempt = literal_attempt(data)
    returned = predict_reference_population_heterogeneity(
        attempt.fit, tuple(t.row for t in data.heldouts), cdf_backend="cupy"
    )
    monkeypatch.setattr(summaries, "predict_reference_population_heterogeneity", lambda *a, **k: returned)
    monkeypatch.setattr(summaries, "predictive_diagnostics", raising(RuntimeError("")))
    result = summaries.summarize_heterogeneity_fit(data, attempt=attempt, cdf_backend="cupy")
    assert result.predictive.status == "diagnostics_failed"
    assert result.predictive.prediction is returned
    assert result.predictive.cdf_backend == "cupy"
    assert result.predictive.error == DiagnosticCallError("builtins.RuntimeError", "")
    assert result.predictive.rows == ()
    assert result.parameters[0].estimate == 0.5


@pytest.mark.parametrize("study,case_number,expected_mean", [(1, 0, 0.001), (4, 0, 0.0), (4, 1, 1.0)])
def test_stress_truth_retained_without_a_posterior_boundary_atom(
    monkeypatch, study, case_number, expected_mean
):
    data = literal_dataset(study=study, case_number=case_number)
    attempt = literal_attempt(data)
    monkeypatch.setattr(
        summaries,
        "predict_reference_population_heterogeneity",
        raising(ValueError("fixture")),
    )
    result = summaries.summarize_heterogeneity_fit(data, attempt=attempt, cdf_backend="scipy")
    assert result.parameters[0].truth == expected_mean
    assert result.parameters[1].truth == 0.0
    assert result.parameters[1].coverage == (False, False, False)
    assert result.parameters[0].quantiles == (0.5,) * 7


def test_identity_refusal_precedes_summary_work_and_seed_state(monkeypatch):
    data = literal_dataset()
    attempt = literal_attempt(data)
    fit = replace(attempt.fit, training_counts=(replace(attempt.fit.training_counts[0], training_ac=1),))
    wrong = replace(attempt, fit=fit)
    sentinel = raising(AssertionError("diagnostic work must not begin"))
    monkeypatch.setattr(summaries.np, "quantile", sentinel)
    monkeypatch.setattr(summaries.np.random, "default_rng", sentinel)
    monkeypatch.setattr(summaries, "DiagnosticSeedIdentity", sentinel)
    monkeypatch.setattr(summaries, "predict_reference_population_heterogeneity", sentinel)
    with pytest.raises(FitIdentityError) as caught:
        summaries.summarize_heterogeneity_fit(data, attempt=wrong, cdf_backend="scipy")
    assert caught.value.mismatches == ("training_counts",)


def test_refuse_ineligible_callers_before_prediction(monkeypatch):
    data = literal_dataset()
    accepted = literal_attempt(data)
    failure = FitAttemptResult(
        accepted.spec,
        "failed",
        None,
        AttemptError("value", "builtins.ValueError", "bad", None, None, None),
        (),
        None,
    )
    case = SbcCaseId(0, 3, 0, 0)
    generation = generation_id(case)
    unavailable = AllUnavailableDataset(
        case,
        GenerationProvenance(
            generation, tuple(sbc_seed_identity(case, purpose_id=p, attempt_id=0) for p in range(4))
        ),
        tuple(simulation_reference_count(generation, "train", str(i), 0, 0) for i in range(16)),
    )
    monkeypatch.setattr(
        summaries,
        "predict_reference_population_heterogeneity",
        raising(AssertionError("predictor must not run")),
    )
    for dataset, attempt, backend in (
        (unavailable, accepted, "scipy"),
        (data, failure, "scipy"),
        (data, accepted, "auto"),
    ):
        with pytest.raises(ValueError):
            summaries.summarize_heterogeneity_fit(dataset, attempt=attempt, cdf_backend=backend)


def test_wrong_prediction_identity_shape_or_backend_propagates(monkeypatch):
    data = literal_dataset(study=2)
    attempt = literal_attempt(data)
    actual = predict_reference_population_heterogeneity(attempt.fit, tuple(t.row for t in data.heldouts))
    reversed_ids = replace(actual, observation_ids=actual.observation_ids[::-1])
    wrong_backend = replace(
        actual,
        marginal_predictive=CountPredictive(
            actual.marginal_predictive.mean_draws, actual.marginal_predictive.concentration, "cupy"
        ),
    )
    wrong_draws = replace(
        actual, marginal_predictive=CountPredictive(np.full((4, 2), 0.5), np.full((4, 2), 2.0))
    )
    binomial = replace(actual, marginal_predictive=CountPredictive(np.full((2000, 2), 0.5)))
    monkeypatch.setattr(
        summaries,
        "predictive_diagnostics",
        raising(AssertionError("scorer must not see malformed predictions")),
    )
    for returned in (object(), reversed_ids, wrong_backend, wrong_draws, binomial):
        monkeypatch.setattr(
            summaries, "predict_reference_population_heterogeneity", lambda *a, value=returned, **k: value
        )
        with pytest.raises(ValueError):
            summaries.summarize_heterogeneity_fit(data, attempt=attempt, cdf_backend="scipy")


def test_malformed_scorer_return_and_baseexception_propagate(monkeypatch):
    data = literal_dataset()
    attempt = literal_attempt(data)
    monkeypatch.setattr(
        summaries,
        "predictive_diagnostics",
        lambda *a, **k: literal_frame().assign(log_score=np.nan),
    )
    with pytest.raises(ValueError):
        summaries.summarize_heterogeneity_fit(data, attempt=attempt, cdf_backend="scipy")
    monkeypatch.setattr(summaries, "predictive_diagnostics", raising(KeyboardInterrupt()))
    with pytest.raises(KeyboardInterrupt):
        summaries.summarize_heterogeneity_fit(data, attempt=attempt, cdf_backend="scipy")


def test_enclosing_summary_binds_valid_predictive_evidence_to_its_attempt(monkeypatch):
    data = literal_dataset(study=2)
    attempt = literal_attempt(data)
    monkeypatch.setattr(
        summaries,
        "predict_reference_population_heterogeneity",
        raising(ValueError("fixture")),
    )
    result = summaries.summarize_heterogeneity_fit(data, attempt=attempt, cdf_backend="scipy")
    for seed in (
        DiagnosticSeedIdentity(SbcCaseId(1, 2, 0, 0), 0, 7, ()),
        DiagnosticSeedIdentity(data.case_id, 1, 7, ()),
    ):
        changed = replace(
            result.predictive, seed=seed, seed_words=seed.scalar_words, seed_uint128=seed.scalar_uint128
        )
        with pytest.raises(ValueError, match="predictive seed"):
            replace(result, predictive=changed)


def test_enclosing_records_reject_inconsistent_evidence(monkeypatch):
    data = literal_dataset()
    attempt = literal_attempt(data)
    monkeypatch.setattr(
        summaries, "predict_reference_population_heterogeneity", raising(ValueError("fixture"))
    )
    result = summaries.summarize_heterogeneity_fit(data, attempt=attempt, cdf_backend="scipy")
    for changes in (
        {"parameters": result.parameters[::-1]},
        {"variant_id": "other"},
        {"parameters": (replace(result.parameters[0], draw_count=4), result.parameters[1])},
    ):
        with pytest.raises(ValueError):
            replace(result, **changes)
    evidence = result.predictive
    for changes in (
        {"seed_uint128": True},
        {"seed_words": (0, 0, 0, 0)},
        {"error": None},
        {"status": "complete"},
        {"rows": []},
        {"seed": DiagnosticSeedIdentity(SbcCaseId(1, 0, 0, 0), 0, 7, ())},
    ):
        with pytest.raises(ValueError):
            replace(evidence, **changes)
