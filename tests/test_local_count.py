"""B1 spherical local count smoother tests (design §§4–8, 12; #307)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from genomeos.validation.local_count import LocalCountConfig, fit_local_count


def _observations(*rows: tuple[object, ...]) -> pd.DataFrame:
    records = []
    for record_id, cohort_id, lat, lon, radius_km, ac, an in rows:
        records.append(
            {
                "variant_id": "chr11-5227002-T-A",
                "rsid": "rs334",
                "population_id": f"population-{record_id}",
                "lat": lat,
                "lon": lon,
                "radius_km": radius_km,
                "ac": ac,
                "an": an,
                "source_record_id": record_id,
                "source": "fixture",
                "assay": "fixture-assay",
                "date_lower": 0,
                "date_upper": 0,
                "sampling_design": "population_random",
                "disease_ascertainment_excluded": True,
                "cohort_id": cohort_id,
                "ingest_version": "fixture-v1",
            }
        )
    return pd.DataFrame.from_records(records)


def _config(**changes: object) -> LocalCountConfig:
    values = {
        "bandwidth_km": 500.0,
        "prior_alpha": 1.0,
        "prior_beta": 9.0,
        "posterior_draws": 128,
        "minimum_training_observations": 1,
        "minimum_effective_alleles": 1.0,
        "query_chunk_size": 2,
    }
    values.update(changes)
    return LocalCountConfig(**values)


def test_vectorized_kernel_uses_counts_denominators_and_footprint_edges():
    training = _observations(
        ("near-zero", "c1", 0.0, 0.0, 20.0, 0, 100),
        ("near-positive", "c2", 0.0, 2.0, 20.0, 20, 100),
        ("outside", "c3", 0.0, 20.0, 20.0, 100, 100),
    )
    query = _observations(("query", "q", 0.0, 0.5, 20.0, 0, 50))

    fit = fit_local_count(training, query, config=_config(), seed=42)

    support = fit.support[0]
    assert support.status == "emitted"
    assert support.training_observation_count == 2
    assert support.nearest_edge_distance_km == pytest.approx(15.5975, abs=0.01)
    assert support.effective_allele_count < 200.0
    assert support.alpha > 1.0
    assert support.beta > 9.0
    assert support.posterior_mean < 0.1
    assert fit.observation_ids == ("query",)
    assert fit.predictive is not None
    assert fit.predictive.mean_draws.shape == (128, 1)


def test_compact_support_refuses_queries_without_enough_local_rows():
    training = _observations(
        ("one", "c1", 0.0, 0.0, 1.0, 1, 20),
        ("two", "c2", 0.0, 2.0, 1.0, 2, 20),
    )
    query = _observations(
        ("near", "q1", 0.0, 1.0, 1.0, 0, 20),
        ("far", "q2", 0.0, 40.0, 1.0, 0, 20),
    )

    fit = fit_local_count(
        training,
        query,
        config=_config(bandwidth_km=300.0, minimum_training_observations=2),
        seed=42,
    )

    by_id = {row.source_record_id: row for row in fit.support}
    assert by_id["near"].status == "emitted"
    assert by_id["near"].refusal_reason is None
    assert by_id["far"].status == "unknown"
    assert by_id["far"].refusal_reason == "insufficient_local_training_observations"
    assert by_id["far"].training_observation_count == 0
    assert fit.observation_ids == ("near",)
    assert fit.predictive is not None
    assert fit.predictive.mean_draws.shape == (128, 1)


def test_all_refused_returns_no_predictive_and_preserves_every_query():
    training = _observations(("train", "c1", 0.0, 0.0, 1.0, 1, 20))
    query = _observations(
        ("far-b", "q2", 0.0, 80.0, 1.0, 0, 20),
        ("far-a", "q1", 0.0, 40.0, 1.0, 0, 20),
    )

    fit = fit_local_count(training, query, config=_config(bandwidth_km=100.0), seed=42)

    assert fit.predictive is None
    assert fit.observation_ids == ()
    assert tuple(row.source_record_id for row in fit.support) == ("far-a", "far-b")
    assert all(row.status == "unknown" for row in fit.support)


def test_effective_allele_gate_refuses_weak_denominator_despite_local_row():
    training = _observations(("train", "c1", 0.0, 0.0, 1.0, 1, 20))
    query = _observations(("query", "q1", 0.0, 0.0, 1.0, 0, 20))

    fit = fit_local_count(
        training,
        query,
        config=_config(minimum_effective_alleles=25.0),
        seed=42,
    )

    assert fit.predictive is None
    assert fit.support[0].training_observation_count == 1
    assert fit.support[0].effective_allele_count == pytest.approx(20.0)
    assert fit.support[0].refusal_reason == "insufficient_effective_alleles"


def test_test_counts_and_row_order_do_not_influence_predictions():
    training = _observations(
        ("b", "c2", 0.0, 2.0, 1.0, 4, 40),
        ("a", "c1", 0.0, 0.0, 1.0, 0, 20),
    )
    query = _observations(
        ("q2", "q2", 0.0, 1.5, 1.0, 1, 10),
        ("q1", "q1", 0.0, 0.5, 1.0, 2, 10),
    )
    changed_query = query.iloc[::-1].reset_index(drop=True)
    changed_query.loc[:, "ac"] = [10, 0]
    changed_query.loc[:, "an"] = [10, 100]

    first = fit_local_count(training, query, config=_config(), seed=123)
    second = fit_local_count(
        training.iloc[::-1].reset_index(drop=True),
        changed_query,
        config=_config(),
        seed=123,
    )

    assert first.observation_ids == second.observation_ids == ("q1", "q2")
    assert first.support == second.support
    assert first.predictive is not None and second.predictive is not None
    np.testing.assert_array_equal(first.predictive.mean_draws, second.predictive.mean_draws)


@pytest.mark.parametrize(
    ("changes", "match"),
    [
        ({"bandwidth_km": 0.0}, "bandwidth_km"),
        ({"prior_alpha": float("inf")}, "prior_alpha"),
        ({"posterior_draws": True}, "posterior_draws"),
        ({"minimum_training_observations": 0}, "minimum_training_observations"),
        ({"minimum_effective_alleles": 0.0}, "minimum_effective_alleles"),
        ({"query_chunk_size": 0}, "query_chunk_size"),
    ],
)
def test_config_refuses_invalid_scientific_and_execution_values(changes, match):
    with pytest.raises(ValueError, match=match):
        _config(**changes)


def test_model_refuses_overlap_variant_mismatch_and_historical_rows():
    training = _observations(("train", "c1", 0.0, 0.0, 1.0, 1, 20))
    query = _observations(("query", "q1", 0.0, 1.0, 1.0, 1, 20))

    overlap = query.copy()
    overlap.loc[:, "source_record_id"] = "train"
    with pytest.raises(ValueError, match="overlap"):
        fit_local_count(training, overlap, config=_config(), seed=42)

    different_variant = query.copy()
    different_variant.loc[:, "variant_id"] = "chr11-5227003-A-G"
    with pytest.raises(ValueError, match="same single variant"):
        fit_local_count(training, different_variant, config=_config(), seed=42)

    historical = query.copy()
    historical.loc[:, ["date_lower", "date_upper"]] = [100, 200]
    with pytest.raises(ValueError, match="modern"):
        fit_local_count(training, historical, config=_config(), seed=42)
