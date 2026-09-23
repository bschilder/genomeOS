"""Nested B1G benchmark tests (design §§4–8, 12; #331)."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd

from genomeos.surfaces.config import FitConfig
from genomeos.surfaces.convergence import SamplerDiagnostics
from genomeos.validation.b1g_benchmark import (
    B1GBenchmarkConfig,
    evaluate_b1g_benchmark,
    evaluate_b1g_fold,
    finalize_b1g_benchmark,
    plan_b1g_benchmark,
)
from genomeos.validation.predictive import CountPredictive

VARIANT = "chr11-5227002-T-A"
GOOD_DIAGNOSTICS = SamplerDiagnostics(
    1.0, "intercept", 300.0, "intercept", 300.0, "intercept", 0
)


def _inputs(
    coordinates: dict[str, float] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    records = []
    assignments = []
    if coordinates is None:
        coordinates = {"a": -150.0, "b": -50.0, "c": 50.0, "d": 150.0}
    for block, lon in coordinates.items():
        for index in range(2):
            record_id = f"{block}-{index}"
            records.append(
                {
                    "variant_id": VARIANT,
                    "rsid": "rs334",
                    "population_id": f"population-{record_id}",
                    "lat": float(index),
                    "lon": lon,
                    "radius_km": 1.0,
                    "ac": index,
                    "an": 100,
                    "source_record_id": record_id,
                    "source": "synthetic",
                    "assay": "genotype",
                    "date_lower": 0,
                    "date_upper": 0,
                    "sampling_design": "population_random",
                    "disease_ascertainment_excluded": False,
                    "cohort_id": f"cohort-{record_id}",
                    "ingest_version": "test",
                }
            )
            assignments.append(
                {
                    "source_record_id": record_id,
                    "block_id": block,
                    "region_id": f"region-{block}",
                    "variant_group": "hbs",
                }
            )
    return pd.DataFrame.from_records(records), pd.DataFrame.from_records(assignments)


def _config() -> B1GBenchmarkConfig:
    return B1GBenchmarkConfig(
        fit_config=FitConfig(draws=3, tune=4, chains=2),
        query_chunk_size=2,
    )


def _fake_functions(*, fail_candidate: tuple[float, int] | None = None):
    calls: list[tuple[tuple[str, ...], float, int, int]] = []

    def fit_function(training, *, basis_config, fit_config):
        identity = (basis_config.radius_km, basis_config.basis_count)
        calls.append(
            (
                tuple(sorted(training["source_record_id"])),
                basis_config.radius_km,
                basis_config.basis_count,
                fit_config.seed,
            )
        )
        if identity == fail_candidate:
            raise RuntimeError("synthetic candidate failure")
        return SimpleNamespace(
            basis_config=basis_config,
            sampler_diagnostics=GOOD_DIAGNOSTICS,
        )

    def predict_function(fit, testing, *, seed, cdf_backend):
        ordered = testing.sort_values("source_record_id")
        mean = np.full((6, len(ordered)), 0.01)
        return SimpleNamespace(
            observation_ids=tuple(ordered["source_record_id"]),
            predictive=CountPredictive(
                mean,
                concentration=np.full(mean.shape, 40.0),
                cdf_backend=cdf_backend,
            ),
        )

    return calls, fit_function, predict_function


def test_nested_selection_uses_the_fixed_grid_and_exact_tie_break():
    observations, assignments = _inputs()
    plan = plan_b1g_benchmark(
        observations,
        assignments,
        (),
        buffer_km=1.0,
        data_version="fixture-v1",
        config=_config(),
        seed=42,
    )
    calls, fit_function, predict_function = _fake_functions()

    result = evaluate_b1g_fold(
        plan,
        plan.splits[0],
        fit_function=fit_function,
        predict_function=predict_function,
    )

    assert result.status.status == "completed"
    assert result.status.selected_radius_km == 500.0
    assert result.status.selected_basis_count == 8
    assert len(result.candidate_scores) == 9
    assert all(score.eligible for score in result.candidate_scores)
    assert all(len(score.inner_folds) == 3 for score in result.candidate_scores)
    assert all(
        inner.status == "completed" and inner.sampler_diagnostics == GOOD_DIAGNOSTICS
        for score in result.candidate_scores
        for inner in score.inner_folds
    )
    assert all(
        inner.fit_seed != inner.predictive_seed
        for score in result.candidate_scores
        for inner in score.inner_folds
    )
    assert len(calls) == 28  # 9 candidates × 3 inner folds, then one outer fit.
    assert len(result.predictions) == 2


def test_five_outer_blocks_still_use_exactly_three_inner_folds():
    observations, assignments = _inputs(
        {"a": -160.0, "b": -80.0, "c": 0.0, "d": 80.0, "e": 160.0}
    )
    plan = plan_b1g_benchmark(
        observations,
        assignments,
        (),
        buffer_km=1.0,
        data_version="fixture-v1",
        config=_config(),
        seed=42,
    )
    calls, fit_function, predict_function = _fake_functions()

    result = evaluate_b1g_fold(
        plan,
        plan.splits[0],
        fit_function=fit_function,
        predict_function=predict_function,
    )

    assert result.status.status == "completed"
    assert all(len(score.inner_folds) == 3 for score in result.candidate_scores)
    assert len(calls) == 28  # 9 candidates × 3 inner folds, then one outer fit.
    first_candidate = result.candidate_scores[0]
    source_blocks = [set(inner.source_block_ids) for inner in first_candidate.inner_folds]
    assert set.union(*source_blocks) == {"b", "c", "d", "e"}
    assert sum(len(blocks) for blocks in source_blocks) == 4


def test_inner_selection_skips_interval_diagnostics(monkeypatch):
    observations, assignments = _inputs()
    plan = plan_b1g_benchmark(
        observations,
        assignments,
        (),
        buffer_km=1.0,
        data_version="fixture-v1",
        config=_config(),
        seed=42,
    )
    _, fit_function, predict_function = _fake_functions()
    quantile_calls: list[tuple[float, ...]] = []
    original_quantiles = CountPredictive.quantiles

    def tracked_quantiles(self, an, probabilities):
        quantile_calls.append(tuple(float(value) for value in probabilities))
        return original_quantiles(self, an, probabilities)

    monkeypatch.setattr(CountPredictive, "quantiles", tracked_quantiles)

    result = evaluate_b1g_fold(
        plan,
        plan.splits[0],
        fit_function=fit_function,
        predict_function=predict_function,
    )

    assert result.status.status == "completed"
    assert quantile_calls == [(0.025, 0.1, 0.25, 0.5, 0.75, 0.9, 0.975)]


def test_outer_counts_cannot_change_training_only_selection():
    observations, assignments = _inputs()
    changed = observations.copy()
    changed.loc[changed["source_record_id"].str.startswith("a-"), "ac"] = 100
    kwargs = {
        "block_assignments": assignments,
        "dependencies": (),
        "buffer_km": 1.0,
        "data_version": "fixture-v1",
        "config": _config(),
        "seed": 42,
    }
    original_plan = plan_b1g_benchmark(observations, **kwargs)
    changed_plan = plan_b1g_benchmark(changed, **kwargs)
    original_split = next(split for split in original_plan.splits if split.block_id == "a")
    changed_split = next(split for split in changed_plan.splits if split.block_id == "a")
    original_calls, original_fit, original_predict = _fake_functions()
    changed_calls, changed_fit, changed_predict = _fake_functions()

    original = evaluate_b1g_fold(
        original_plan,
        original_split,
        fit_function=original_fit,
        predict_function=original_predict,
    )
    mutated = evaluate_b1g_fold(
        changed_plan,
        changed_split,
        fit_function=changed_fit,
        predict_function=changed_predict,
    )

    assert original.status.selected_radius_km == mutated.status.selected_radius_km
    assert original.status.selected_basis_count == mutated.status.selected_basis_count
    assert original_calls == changed_calls


def test_failed_inner_candidate_is_preserved_and_cannot_win():
    observations, assignments = _inputs()
    plan = plan_b1g_benchmark(
        observations,
        assignments,
        (),
        buffer_km=1.0,
        data_version="fixture-v1",
        config=_config(),
    )
    _, fit_function, predict_function = _fake_functions(fail_candidate=(500.0, 8))

    result = evaluate_b1g_fold(
        plan,
        plan.splits[0],
        fit_function=fit_function,
        predict_function=predict_function,
    )

    failed = next(
        score
        for score in result.candidate_scores
        if score.radius_km == 500.0 and score.basis_count == 8
    )
    assert failed.eligible is False
    assert failed.failed_inner_fold_count == 3
    assert all("synthetic candidate failure" in reason for reason in failed.failure_reasons)
    assert {inner.status for inner in failed.inner_folds} == {"failed"}
    assert all(inner.sampler_diagnostics is None for inner in failed.inner_folds)
    assert all(inner.failure_reason for inner in failed.inner_folds)
    assert (result.status.selected_radius_km, result.status.selected_basis_count) == (1000.0, 8)


def test_complete_outer_benchmark_uses_the_shared_macro_report():
    observations, assignments = _inputs()
    plan = plan_b1g_benchmark(
        observations,
        assignments,
        (),
        buffer_km=1.0,
        data_version="fixture-v1",
        config=_config(),
    )
    _, fit_function, predict_function = _fake_functions()

    result = evaluate_b1g_benchmark(
        plan,
        fit_function=fit_function,
        predict_function=predict_function,
    )

    assert len(result.fold_status) == 4
    assert result.summary["comparison_complete"] is True
    assert result.summary["scored_observation_count"] == len(observations)
    assert len(result.predictions) == len(observations)
    assert len(result.candidate_scores) == 36


def test_public_finalizer_refuses_an_incomplete_outer_fold_ledger():
    observations, assignments = _inputs()
    plan = plan_b1g_benchmark(
        observations,
        assignments,
        (),
        buffer_km=1.0,
        data_version="fixture-v1",
        config=_config(),
    )
    _, fit_function, predict_function = _fake_functions()
    first = evaluate_b1g_fold(
        plan,
        plan.splits[0],
        fit_function=fit_function,
        predict_function=predict_function,
    )

    with np.testing.assert_raises_regex(ValueError, "exactly one result"):
        finalize_b1g_benchmark(plan, (first,))
