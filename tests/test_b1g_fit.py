"""B1G count-likelihood fit and prediction tests (design §§4–8, 12; #331)."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from genomeos.surfaces.config import FitConfig
from genomeos.surfaces.convergence import SamplerDiagnostics
from genomeos.validation.b1g_basis import (
    B1GBasisConfig,
    build_b1g_basis_from_centres,
    select_b1g_centres,
)
from genomeos.validation.b1g_fit import fit_b1g, predict_b1g

VARIANT = "chr11-5227002-T-A"


def _observations(rows: int = 12) -> pd.DataFrame:
    records = []
    for index in range(rows):
        records.append(
            {
                "variant_id": VARIANT,
                "rsid": "rs334",
                "population_id": f"population-{index}",
                "lat": float(index * 2),
                "lon": float(index * 3),
                "radius_km": float(10 + index),
                "ac": 1 + index % 3,
                "an": 100 + index,
                "source_record_id": f"observation-{index:02d}",
                "source": "synthetic",
                "assay": "genotype",
                "date_lower": 0,
                "date_upper": 0,
                "sampling_design": (
                    "population_random" if index % 2 == 0 else "healthy_reference"
                ),
                "disease_ascertainment_excluded": bool(index % 2),
                "cohort_id": f"cohort-{index // 2}",
                "ingest_version": "test",
            }
        )
    return pd.DataFrame.from_records(records)


def _posterior(*, basis_count: int, designs: int, cohort_effect: bool = True):
    chains, draws = 2, 3
    shape = (chains, draws)
    variables: dict[str, tuple[tuple[str, ...], np.ndarray]] = {
        "intercept": (("chain", "draw"), np.full(shape, -3.0)),
        "amplitude": (("chain", "draw"), np.full(shape, 2.0)),
        "mixture_weights": (
            ("chain", "draw", "mixture_weights_dim_0"),
            np.full((*shape, basis_count), 1.0 / basis_count),
        ),
        "concentration": (("chain", "draw"), np.full(shape, 40.0)),
    }
    if designs:
        variables["beta_design"] = (
            ("chain", "draw", "beta_design_dim_0"),
            np.zeros((*shape, designs)),
        )
    if cohort_effect:
        variables["cohort_sd"] = (("chain", "draw"), np.zeros(shape))
    return SimpleNamespace(
        posterior=xr.Dataset(
            variables,
            coords={"chain": np.arange(chains), "draw": np.arange(draws)},
        )
    )


@pytest.fixture
def fitted(monkeypatch: pytest.MonkeyPatch):
    posterior = _posterior(basis_count=8, designs=1)
    diagnostics = SamplerDiagnostics(1.0, "intercept", 300.0, "intercept", 300.0, "intercept", 0)
    monkeypatch.setattr("genomeos.validation.b1g_fit.pm.sample", lambda **_kwargs: posterior)
    monkeypatch.setattr(
        "genomeos.validation.b1g_fit.summarize_sampler_diagnostics",
        lambda *_args, **_kwargs: diagnostics,
    )
    return fit_b1g(
        _observations(),
        basis_config=B1GBasisConfig(radius_km=1000, basis_count=8, query_chunk_size=2),
        fit_config=FitConfig(draws=3, tune=4, chains=2),
    )


def test_fit_builds_the_preregistered_positive_mixture_and_existing_count_terms(fitted):
    assert fitted.centre_source_record_ids == (
        "observation-00",
        "observation-11",
        "observation-05",
        "observation-08",
        "observation-02",
        "observation-01",
        "observation-03",
        "observation-04",
    )
    assert {
        "intercept",
        "amplitude",
        "mixture_weights",
        "beta_design",
        "cohort_sd",
        "concentration",
        "obs",
    } <= set(fitted.model.named_vars)
    assert "lengthscale" not in fitted.model.named_vars
    assert fitted.prediction_metadata.fitted_designs == (
        "population_random",
        "healthy_reference",
    )
    assert fitted.prediction_metadata.cohort_effect_applied is True
    assert fitted.prediction_metadata.likelihood == "beta_binomial"


def test_prediction_matches_the_vectorized_basis_formula_and_preserves_query_order(fitted):
    queries = _observations(2).copy()
    queries["source_record_id"] = ["query-z", "query-a"]
    queries["cohort_id"] = ["new-cohort-z", "new-cohort-a"]
    queries["sampling_design"] = "population_random"

    result = predict_b1g(fitted, queries, seed=17)

    assert result.observation_ids == ("query-a", "query-z")
    assert result.predictive.mean_draws.shape == (6, 2)
    expected_logit = -3.0 + 2.0 * result.basis.values.mean(axis=1)
    expected = 1.0 / (1.0 + np.exp(-expected_logit))
    np.testing.assert_allclose(result.predictive.mean_draws, np.broadcast_to(expected, (6, 2)))
    np.testing.assert_allclose(result.predictive.concentration, np.full((6, 2), 40.0))


def test_prediction_uses_query_footprint_radius(fitted):
    small = _observations(1).copy()
    small["source_record_id"] = "small-query"
    small["cohort_id"] = "small-cohort"
    small["lat"] = 0.0
    small["lon"] = 8.0
    small["radius_km"] = 1.0
    large = small.copy()
    large["source_record_id"] = "large-query"
    large["cohort_id"] = "large-cohort"
    large["radius_km"] = 500.0

    small_result = predict_b1g(fitted, small, seed=9)
    large_result = predict_b1g(fitted, large, seed=9)

    assert large_result.basis.values.sum() > small_result.basis.values.sum()
    assert np.all(large_result.predictive.mean_draws > small_result.predictive.mean_draws)


def test_prediction_refuses_training_overlap(fitted):
    queries = _observations(1)
    with pytest.raises(ValueError, match="overlap"):
        predict_b1g(fitted, queries)


@pytest.mark.parametrize(
    "fit_config,match",
    [
        (FitConfig(likelihood="binomial"), "beta_binomial"),
        (FitConfig(nugget=True), "nugget"),
    ],
)
def test_fit_refuses_changes_to_the_frozen_observation_model(fit_config, match):
    with pytest.raises(ValueError, match=match):
        fit_b1g(
            _observations(),
            basis_config=B1GBasisConfig(radius_km=500, basis_count=8),
            fit_config=fit_config,
        )


def test_fit_refuses_nonconverged_sampling(monkeypatch: pytest.MonkeyPatch):
    posterior = _posterior(basis_count=8, designs=1)
    diagnostics = SamplerDiagnostics(1.2, "amplitude", 20.0, "amplitude", 20.0, "amplitude", 1)
    monkeypatch.setattr("genomeos.validation.b1g_fit.pm.sample", lambda **_kwargs: posterior)
    monkeypatch.setattr(
        "genomeos.validation.b1g_fit.summarize_sampler_diagnostics",
        lambda *_args, **_kwargs: diagnostics,
    )

    with pytest.raises(RuntimeError, match="did not converge"):
        fit_b1g(
            _observations(),
            basis_config=B1GBasisConfig(radius_km=500, basis_count=8),
            fit_config=FitConfig(draws=3, tune=4, chains=2),
        )


def test_actual_numpyro_fit_converges_and_predicts_seeded_b1g_counts():
    rng = np.random.default_rng(42)
    rows = 80
    observations = pd.DataFrame(
        {
            "variant_id": VARIANT,
            "rsid": "rs334",
            "population_id": [f"generated-{index:03d}" for index in range(rows)],
            "lat": np.linspace(-55.0, 55.0, rows),
            "lon": np.linspace(-170.0, 170.0, rows),
            "radius_km": 5.0,
            "ac": 1,
            "an": 200,
            "source_record_id": [f"generated:{index:03d}" for index in range(rows)],
            "source": "synthetic",
            "assay": "genotype",
            "date_lower": 0,
            "date_upper": 0,
            "sampling_design": "population_random",
            "disease_ascertainment_excluded": False,
            "cohort_id": [f"generated-cohort-{index:03d}" for index in range(rows)],
            "ingest_version": "test",
        }
    )
    basis_config = B1GBasisConfig(radius_km=2000, basis_count=8, query_chunk_size=128)
    centres = select_b1g_centres(observations, config=basis_config)
    basis = build_b1g_basis_from_centres(
        observations,
        centres=centres,
        config=basis_config,
    )
    mixture = np.array([0.55, 0.20, 0.10, 0.05, 0.04, 0.03, 0.02, 0.01])
    mean = 1.0 / (1.0 + np.exp(-(-4.2 + 3.0 * (basis.values @ mixture))))
    sampled_mean = rng.beta(mean * 60.0, (1.0 - mean) * 60.0)
    observations["ac"] = rng.binomial(observations["an"].to_numpy(), sampled_mean)
    observations.loc[observations["ac"] == 0, "ac"] = 1

    fit = fit_b1g(
        observations,
        basis_config=basis_config,
        fit_config=FitConfig(draws=500, tune=800, chains=4, target_accept=0.9),
    )
    queries = observations.iloc[:3].copy()
    queries["source_record_id"] = ("heldout-a", "heldout-b", "heldout-c")
    queries["cohort_id"] = ("heldout-cohort-a", "heldout-cohort-b", "heldout-cohort-c")
    prediction = predict_b1g(fit, queries, seed=99)

    assert fit.sampler_diagnostics.max_rhat <= 1.05
    assert fit.sampler_diagnostics.min_bulk_ess >= 200
    assert fit.sampler_diagnostics.min_tail_ess >= 200
    assert fit.sampler_diagnostics.divergence_count == 0
    assert prediction.predictive.mean_draws.shape == (2000, 3)
    assert np.isfinite(prediction.predictive.mean_draws).all()
