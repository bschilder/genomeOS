"""Training-only B1 local-count benchmark tests (design §§4–8, 12; #307)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from genomeos.validation.local_count_benchmark import (
    evaluate_local_count_benchmark,
    evaluate_local_count_fold,
    plan_local_count_benchmark,
)
from genomeos.validation.local_count_selection import (
    LocalCountBenchmarkConfig,
    LocalCountInfeasibleError,
    select_local_count_bandwidth,
)


def _inputs() -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    assignment_rows = []
    block_longitudes = {"a": 0.0, "b": 5.0, "c": 10.0, "d": 15.0}
    for block_index, (block, longitude) in enumerate(block_longitudes.items()):
        for within in range(2):
            record_id = f"{block}-{within}"
            an = 100 + within * 20
            ac = block_index * 5 + within
            rows.append(
                {
                    "variant_id": "chr11-5227002-T-A",
                    "rsid": "rs334",
                    "population_id": f"population-{record_id}",
                    "lat": float(within) / 10.0,
                    "lon": longitude + float(within) / 10.0,
                    "radius_km": 10.0,
                    "ac": ac,
                    "an": an,
                    "source_record_id": record_id,
                    "source": "fixture",
                    "assay": "fixture-assay",
                    "date_lower": 0,
                    "date_upper": 0,
                    "sampling_design": "population_random",
                    "disease_ascertainment_excluded": True,
                    "cohort_id": f"cohort-{record_id}",
                    "ingest_version": "fixture-v1",
                }
            )
            assignment_rows.append(
                {
                    "source_record_id": record_id,
                    "block_id": block,
                    "region_id": f"region-{block}",
                    "variant_group": "hbs",
                }
            )
    return pd.DataFrame.from_records(rows), pd.DataFrame.from_records(assignment_rows)


def _config(**changes: object) -> LocalCountBenchmarkConfig:
    values = {
        "candidate_bandwidths_km": (300.0, 800.0),
        "prior_alpha": 1.0,
        "prior_beta": 9.0,
        "posterior_draws": 64,
        "minimum_training_observations": 1,
        "minimum_effective_alleles": 1.0,
        "minimum_inner_emission_fraction": 0.5,
        "query_chunk_size": 3,
    }
    values.update(changes)
    return LocalCountBenchmarkConfig(**values)


def test_training_only_selector_disqualifies_candidate_that_hides_geography():
    observations, assignments = _inputs()

    selection = select_local_count_bandwidth(
        observations,
        assignments,
        (),
        buffer_km=100.0,
        data_version="fixture-v1:inner",
        config=_config(),
        seed=42,
    )

    assert selection.selected_bandwidth_km == 800.0
    narrow, wide = selection.candidate_scores
    assert narrow.emission_fraction == 0.0
    assert narrow.eligible is False
    assert wide.emission_fraction == 1.0
    assert wide.eligible is True
    assert wide.inner_failure_reasons == ()
    assert wide.mean_log_score is not None and np.isfinite(wide.mean_log_score)


def test_selector_refuses_when_no_candidate_passes_emission_gate():
    observations, assignments = _inputs()

    with pytest.raises(LocalCountInfeasibleError, match="no bandwidth") as error:
        select_local_count_bandwidth(
            observations,
            assignments,
            (),
            buffer_km=100.0,
            data_version="fixture-v1:inner",
            config=_config(candidate_bandwidths_km=(100.0, 300.0)),
            seed=42,
        )

    assert len(error.value.scores) == 2
    assert all(not score.eligible for score in error.value.scores)


def test_complete_benchmark_keeps_requested_support_and_supported_scores_separate():
    observations, assignments = _inputs()
    plan = plan_local_count_benchmark(
        observations,
        assignments,
        (),
        buffer_km=100.0,
        data_version="fixture-v1",
        config=_config(),
        seed=42,
    )

    result = evaluate_local_count_benchmark(plan)

    assert len(result.fold_status) == 4
    assert {status.status for status in result.fold_status} == {"completed"}
    assert {status.selected_bandwidth_km for status in result.fold_status} == {800.0}
    assert len(result.support) == len(observations)
    assert set(result.support["status"]) == {"emitted"}
    assert len(result.predictions) == len(observations)
    assert len(result.candidate_scores) == 8
    assert result.summary["requested_observation_count"] == len(observations)
    assert result.summary["emitted_observation_count"] == len(observations)
    assert result.summary["excluded_fraction"] == 0.0
    supported = result.summary["supported_only_benchmark"]
    assert supported["scored_observation_count"] == len(observations)
    assert supported["comparison_complete"] is True


def test_outer_heldout_counts_cannot_change_bandwidth_or_local_posterior():
    observations, assignments = _inputs()
    changed = observations.copy()
    held_out = changed["source_record_id"].str.startswith("a-")
    changed.loc[held_out, "ac"] = changed.loc[held_out, "an"]
    kwargs = {
        "buffer_km": 100.0,
        "data_version": "fixture-v1",
        "config": _config(),
        "seed": 42,
    }
    original_plan = plan_local_count_benchmark(observations, assignments, (), **kwargs)
    changed_plan = plan_local_count_benchmark(changed, assignments, (), **kwargs)
    original_split = next(split for split in original_plan.splits if split.block_id == "a")
    changed_split = next(split for split in changed_plan.splits if split.block_id == "a")

    original = evaluate_local_count_fold(original_plan, original_split)
    mutated = evaluate_local_count_fold(changed_plan, changed_split)

    assert original.status.selected_bandwidth_km == mutated.status.selected_bandwidth_km
    posterior_columns = [
        "source_record_id",
        "bandwidth_km",
        "nearest_edge_distance_km",
        "training_observation_count",
        "effective_training_observations",
        "effective_allele_count",
        "posterior_alpha",
        "posterior_beta",
        "posterior_mean",
        "posterior_seed",
    ]
    pd.testing.assert_frame_equal(
        original.predictions.loc[:, posterior_columns].reset_index(drop=True),
        mutated.predictions.loc[:, posterior_columns].reset_index(drop=True),
    )
    assert not np.array_equal(
        original.predictions["log_score"].to_numpy(),
        mutated.predictions["log_score"].to_numpy(),
    )


def test_plan_refuses_cohort_split_across_geographic_blocks():
    observations, assignments = _inputs()
    observations.loc[observations["source_record_id"].isin(["a-0", "b-0"]), "cohort_id"] = "shared"

    with pytest.raises(ValueError, match="whole cohort"):
        plan_local_count_benchmark(
            observations,
            assignments,
            (),
            buffer_km=100.0,
            data_version="fixture-v1",
            config=_config(),
            seed=42,
        )


@pytest.mark.parametrize(
    "mutation",
    [
        "unknown_scored",
        "wrong_expected",
        "missing_support",
        "duplicate_emitted",
        "overlapping_refused",
        "extra_support",
        "wrong_split",
        "wrong_count",
        "wrong_region",
        "failed_predictions",
        "invalid_state",
        "missing_prediction",
        "posterior_on_unknown",
        "missing_posterior",
        "insufficient_support",
        "wrong_concentration",
    ],
)
def test_finalization_refuses_contradictory_retained_fold(mutation):
    from dataclasses import replace

    from genomeos.validation.local_count_benchmark import finalize_local_count_benchmark

    observations, assignments = _inputs()
    plan = plan_local_count_benchmark(
        observations, assignments, (), buffer_km=100.0, data_version="fixture-v1", config=_config()
    )
    folds = [evaluate_local_count_fold(plan, split) for split in plan.splits]
    fold = folds[0]
    support, predictions, status = fold.support.copy(), fold.predictions.copy(), fold.status
    if mutation == "unknown_scored":
        support["status"] = "unknown"
        support["refusal_reason"] = "refused"
        support[["posterior_alpha", "posterior_beta", "posterior_mean"]] = None
    elif mutation == "wrong_expected":
        status = replace(status, expected_test_ids=("invented",))
    elif mutation == "missing_support":
        support = support.iloc[:0]
    elif mutation == "duplicate_emitted":
        status = replace(status, emitted_test_ids=status.emitted_test_ids * 2)
    elif mutation == "overlapping_refused":
        status = replace(status, refused_test_ids=status.emitted_test_ids)
    elif mutation == "extra_support":
        support = pd.concat([support, support.iloc[:1]])
    elif mutation == "wrong_split":
        predictions["split_id"] = "invented"
    elif mutation == "wrong_count":
        predictions["observed_an"] += 1
    elif mutation == "wrong_region":
        predictions["region_id"] = "invented"
    elif mutation == "failed_predictions":
        status = replace(status, status="failed", failure_reason="failure")
    elif mutation == "invalid_state":
        status = replace(status, status="invented")
    elif mutation == "missing_prediction":
        predictions = predictions.iloc[:0]
    elif mutation == "posterior_on_unknown":
        status = replace(
            status,
            status="infeasible",
            emitted_test_ids=(),
            refused_test_ids=status.expected_test_ids,
            failure_reason="refused",
        )
        predictions = predictions.iloc[:0]
        support["status"] = "unknown"
        support["refusal_reason"] = "refused"
    elif mutation == "insufficient_support":
        support["effective_allele_count"] = 0.5
        predictions["effective_allele_count"] = 0.5
    elif mutation == "wrong_concentration":
        support["effective_allele_count"] += 1.0
        predictions["effective_allele_count"] += 1.0
    elif mutation == "missing_posterior":
        support["posterior_alpha"] = None
    folds[0] = replace(fold, status=status, predictions=predictions, support=support)
    with pytest.raises(ValueError):
        finalize_local_count_benchmark(plan, folds)


@pytest.mark.parametrize("state", ["failed", "infeasible"])
def test_valid_terminal_refusals_remain_visible_and_unscored(state):
    from dataclasses import replace

    from genomeos.validation.local_count_benchmark import finalize_local_count_benchmark

    observations, assignments = _inputs()
    plan = plan_local_count_benchmark(
        observations, assignments, (), buffer_km=100.0, data_version="fixture-v1", config=_config()
    )
    folds = [evaluate_local_count_fold(plan, split) for split in plan.splits]
    fold = folds[0]
    support = fold.support.copy()
    support["status"] = "unknown"
    support["refusal_reason"] = "retained terminal refusal"
    support[["posterior_alpha", "posterior_beta", "posterior_mean"]] = None
    status = replace(
        fold.status,
        status=state,
        emitted_test_ids=(),
        refused_test_ids=fold.status.expected_test_ids,
        failure_reason="retained terminal refusal",
    )
    folds[0] = replace(fold, status=status, support=support, predictions=fold.predictions.iloc[:0])
    result = finalize_local_count_benchmark(plan, folds)
    assert result.summary["requested_observation_count"] == 8
    assert result.summary["emitted_observation_count"] == 6
    assert result.summary["excluded_fraction"] == 0.25
    assert result.fold_status[0].status == state


def test_finalizer_rejects_plan_with_changed_split_membership():
    from dataclasses import replace

    from genomeos.validation.local_count_benchmark import finalize_local_count_benchmark

    observations, assignments = _inputs()
    plan = plan_local_count_benchmark(
        observations, assignments, (), buffer_km=100.0, data_version="fixture-v1", config=_config()
    )
    folds = [evaluate_local_count_fold(plan, split) for split in plan.splits]
    invalid = replace(plan, splits=(replace(plan.splits[0], test_ids=("invented",)), *plan.splits[1:]))
    with pytest.raises(ValueError, match="plan splits"):
        finalize_local_count_benchmark(invalid, folds)
