from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import pytest

from genomeos.observations.schema import OBSERVATIONS_SCHEMA
from genomeos.surfaces.config import FitConfig
from genomeos.surfaces.observation import (
    ObservationModelMetadata,
    ObservationParameters,
    SurveyQueries,
)
from genomeos.validation.spatial_gp_benchmark import evaluate_single_variant_gp

VARIANT = "chr11-5227002-T-A"


def _observations(*, large_denominator: bool = False) -> pd.DataFrame:
    denominator = [100, 120, 140, 160]
    if large_denominator:
        denominator[2] = 65_537
    return OBSERVATIONS_SCHEMA.validate(
        pd.DataFrame(
            {
                "variant_id": VARIANT,
                "rsid": "rs334",
                "population_id": ["pop-a", "pop-b", "pop-c", "pop-d"],
                "lat": [-45.0, -15.0, 15.0, 45.0],
                "lon": [-120.0, -40.0, 40.0, 120.0],
                "radius_km": 1.0,
                "ac": [1, 2, 3, 4],
                "an": denominator,
                "source_record_id": ["obs-a", "obs-b", "obs-c", "obs-d"],
                "source": "synthetic",
                "assay": "genotype",
                "date_lower": 0,
                "date_upper": 0,
                "sampling_design": "population_random",
                "disease_ascertainment_excluded": True,
                "cohort_id": ["cohort-a", "cohort-b", "cohort-c", "cohort-d"],
                "ingest_version": "test-v1",
            }
        )
    )


def _assignments() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "source_record_id": ["obs-a", "obs-b", "obs-c", "obs-d"],
            "block_id": ["block-a", "block-b", "block-c", "block-d"],
            "region_id": ["region-1", "region-1", "region-2", "region-2"],
            "variant_group": "hbs",
        }
    )


@dataclass
class _FakeFit:
    training_cohorts: tuple[str, ...]
    likelihood: str
    fail_prediction: bool = False

    def predict_new_cohort_parameters(
        self, queries: SurveyQueries, *, seed: int
    ) -> ObservationParameters:
        if self.fail_prediction:
            raise RuntimeError("deliberate prediction failure")
        assert not set(queries.cohort_ids) & set(self.training_cohorts)
        draws = 8
        mean = np.broadcast_to(
            np.linspace(0.01, 0.08, len(queries.observation_ids)),
            (draws, len(queries.observation_ids)),
        )
        concentration = None
        if self.likelihood == "beta_binomial":
            concentration = np.full(mean.shape, 30.0)
        return ObservationParameters(
            queries=queries,
            metadata=ObservationModelMetadata(
                convention="new_cohort_count_v1",
                fitted_designs=("population_random",),
                training_cohort_ids=self.training_cohorts,
                cohort_effect_applied=True,
                nugget_applied=False,
                likelihood=self.likelihood,
            ),
            draw_ids=tuple((0, draw) for draw in range(draws)),
            mean_draws=mean,
            concentration=concentration,
        )


def _recording_fit(calls: list[tuple[str, ...]], *, fail_on: str | None = None):
    def fit(observations: pd.DataFrame, config: FitConfig) -> _FakeFit:
        record_ids = tuple(sorted(observations["source_record_id"]))
        calls.append(record_ids)
        return _FakeFit(
            tuple(sorted(observations["cohort_id"].unique())),
            config.likelihood,
            fail_prediction=fail_on is not None and fail_on not in record_ids,
        )

    return fit


def _evaluate(
    observations: pd.DataFrame,
    *,
    config: FitConfig,
    fit_function,
    assignments: pd.DataFrame | None = None,
):
    return evaluate_single_variant_gp(
        observations,
        _assignments() if assignments is None else assignments,
        (),
        buffer_km=10.0,
        data_version="test-v1",
        config=config,
        fit_function=fit_function,
    )


def test_evaluator_fits_each_fold_and_scores_test_rows_in_batches():
    calls: list[tuple[str, ...]] = []
    result = _evaluate(
        _observations(),
        config=FitConfig(likelihood="binomial"),
        fit_function=_recording_fit(calls),
    )

    assert len(calls) == 4
    assert all(len(call) == 3 for call in calls)
    assert [status.status for status in result.fold_status] == ["completed"] * 4
    assert list(result.predictions["source_record_id"]) == [
        "obs-a",
        "obs-b",
        "obs-c",
        "obs-d",
    ]
    assert result.summary["comparison_complete"] is True
    assert result.summary["scored_observation_count"] == 4
    assert set(result.predictions["variant_id"]) == {VARIANT}
    assert list(result.predictions["observed_an"]) == [100, 120, 140, 160]
    assert (result.predictions["fit_seed"] != result.predictions["predictive_seed"]).all()


def test_evaluator_is_deterministic_under_input_row_reordering():
    config = FitConfig(likelihood="binomial")
    first = _evaluate(
        _observations(),
        config=config,
        fit_function=_recording_fit([]),
    )
    second = _evaluate(
        _observations().iloc[::-1].reset_index(drop=True),
        assignments=_assignments().iloc[::-1].reset_index(drop=True),
        config=config,
        fit_function=_recording_fit([]),
    )

    pd.testing.assert_frame_equal(first.predictions, second.predictions)
    assert first.fold_status == second.fold_status
    assert first.splits == second.splits


def test_evaluator_refuses_cohort_assignments_across_blocks_before_fitting():
    assignments = _assignments()
    observations = _observations()
    observations.loc[observations["source_record_id"] == "obs-b", "cohort_id"] = "cohort-a"
    calls: list[tuple[str, ...]] = []

    with pytest.raises(ValueError, match="whole cohort"):
        _evaluate(
            observations,
            assignments=assignments,
            config=FitConfig(likelihood="binomial"),
            fit_function=_recording_fit(calls),
        )

    assert calls == []


def test_large_beta_binomial_denominator_reaches_every_fold(
    monkeypatch: pytest.MonkeyPatch,
):
    def diagnostics(*args, **kwargs):
        observations = len(args[1])
        return pd.DataFrame(
            {
                "log_score": np.full(observations, -1.0),
                "absolute_error": np.full(observations, 0.1),
                "squared_error": np.full(observations, 0.01),
                "coverage_50": np.ones(observations, dtype=bool),
                "interval_width_50": np.full(observations, 0.1),
                "coverage_80": np.ones(observations, dtype=bool),
                "interval_width_80": np.full(observations, 0.2),
                "coverage_95": np.ones(observations, dtype=bool),
                "interval_width_95": np.full(observations, 0.3),
                "randomized_pit": np.full(observations, 0.5),
            }
        )

    monkeypatch.setattr(
        "genomeos.validation.spatial_gp_benchmark.predictive_diagnostics", diagnostics
    )
    calls: list[tuple[str, ...]] = []
    result = _evaluate(
        _observations(large_denominator=True),
        config=FitConfig(likelihood="beta_binomial"),
        fit_function=_recording_fit(calls),
    )

    assert len(calls) == 4
    assert [status.status for status in result.fold_status] == ["completed"] * 4
    assert result.summary["comparison_complete"] is True
    assert result.summary["split_counts"] == {
        "planned": 4,
        "completed": 4,
        "failed": 0,
        "infeasible": 0,
    }


def test_one_failed_fold_is_retained_without_discarding_completed_folds():
    result = _evaluate(
        _observations(),
        config=FitConfig(likelihood="binomial"),
        fit_function=_recording_fit([], fail_on="obs-c"),
    )

    assert [status.status for status in result.fold_status].count("failed") == 1
    assert [status.status for status in result.fold_status].count("completed") == 3
    failed = next(status for status in result.fold_status if status.status == "failed")
    assert failed.expected_test_ids == ("obs-c",)
    assert "deliberate prediction failure" in failed.failure_reason
    assert set(result.predictions["source_record_id"]) == {"obs-a", "obs-b", "obs-d"}
    assert result.summary["comparison_complete"] is False


def test_evaluator_refuses_multiple_variants_before_fitting():
    observations = _observations()
    observations.loc[0, "variant_id"] = "chr11-5227003-A-C"
    calls: list[tuple[str, ...]] = []

    with pytest.raises(ValueError, match="exactly one variant"):
        _evaluate(
            observations,
            config=FitConfig(likelihood="binomial"),
            fit_function=_recording_fit(calls),
        )

    assert calls == []
