"""Fit/prediction boundary tests for the simulation-only activity model (#384)."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest
import xarray as xr

from genomeos.surfaces.convergence import SamplerDiagnostics
from genomeos.surfaces.fit import to_unit_sphere
from genomeos.surfaces.spatial_activity_model import (
    SpatialActivityModelConfig,
    build_spatial_activity_model,
)


def _model_config() -> SpatialActivityModelConfig:
    return SpatialActivityModelConfig(
        hsgp_m=(2, 2, 2),
        hsgp_c=1.5,
        lengthscale_mu=-2.0,
        lengthscale_sigma=0.4,
        conditional_intercept_mu=-3.5,
        conditional_intercept_sigma=1.5,
        conditional_amplitude_sigma=1.0,
        activity_intercept_mu=2.5,
        activity_intercept_sigma=1.0,
        activity_amplitude_sigma=1.0,
        concentration_sigma=100.0,
        cohort_sd_sigma=0.5,
    )


def _graph(*, mode: str = "spatial_activity", repeated_cohorts: bool = True):
    x = to_unit_sphere(
        np.array([-8.0, 0.0, 9.0, 15.0]),
        np.array([-12.0, 2.0, 18.0, 28.0]),
    )
    x_pred = to_unit_sphere(np.array([-4.0, 4.0, 12.0]), np.array([-6.0, 8.0, 22.0]))
    cohorts = np.array([0, 0, 1, 1]) if repeated_cohorts else np.arange(4)
    return build_spatial_activity_model(
        x,
        np.array([0, 1, 3, 0]),
        np.array([20, 30, 40, 25]),
        x_pred,
        cohort_index=cohorts,
        mode=mode,
        config=_model_config(),
    )


def _sampler_config():
    from genomeos.surfaces.spatial_activity_fit import SpatialActivitySamplerConfig

    return SpatialActivitySamplerConfig(
        draws=3,
        tune=4,
        chains=4,
        target_accept=0.9,
        nuts_sampler="numpyro",
        max_rhat=1.05,
        min_ess=200.0,
        seed=42,
    )


def _idata(*, cohort_effect: bool = True):
    shape = (4, 3)
    variables: dict[str, tuple[tuple[str, ...], np.ndarray]] = {
        "concentration": (("chain", "draw"), np.full(shape, 40.0)),
    }
    if cohort_effect:
        variables["cohort_sd"] = (("chain", "draw"), np.full(shape, 0.4))
    return SimpleNamespace(
        posterior=xr.Dataset(
            variables,
            coords={"chain": np.arange(4), "draw": np.arange(3)},
        )
    )


def _posterior_predictive(*, activity: float = 0.8):
    shape = (4, 3, 3)
    return SimpleNamespace(
        posterior_predictive=xr.Dataset(
            {
                "conditional_mean_pred": (
                    ("chain", "draw", "prediction"),
                    np.broadcast_to(np.array([0.1, 0.2, 0.3]), shape),
                ),
                "activity_probability_pred": (
                    ("chain", "draw", "prediction"),
                    np.full(shape, activity),
                ),
            },
            coords={
                "chain": np.arange(4),
                "draw": np.arange(3),
                "prediction": np.arange(3),
            },
        )
    )


def _diagnostics() -> SamplerDiagnostics:
    return SamplerDiagnostics(
        max_rhat=1.01,
        max_rhat_parameter="conditional_field_hsgp_coeffs",
        min_bulk_ess=350.0,
        min_bulk_ess_parameter="activity_intercept",
        min_tail_ess=310.0,
        min_tail_ess_parameter="concentration",
        divergence_count=0,
    )


def test_fit_samples_matched_graph_and_retains_aligned_prediction_draws(monkeypatch) -> None:
    from genomeos.surfaces.spatial_activity_fit import fit_spatial_activity_graph

    calls = {}

    def sample(**kwargs):
        calls["sample"] = kwargs
        return _idata()

    def posterior_predictive(idata, **kwargs):
        calls["posterior_predictive"] = (idata, kwargs)
        return _posterior_predictive()

    monkeypatch.setattr("genomeos.surfaces.spatial_activity_fit.pm.sample", sample)
    monkeypatch.setattr(
        "genomeos.surfaces.spatial_activity_fit.pm.sample_posterior_predictive",
        posterior_predictive,
    )
    def diagnostics(*args, **kwargs):
        calls["diagnostics"] = (args, kwargs)
        return _diagnostics()

    monkeypatch.setattr(
        "genomeos.surfaces.spatial_activity_fit.summarize_sampler_diagnostics", diagnostics
    )

    graph = _graph()
    fitted = fit_spatial_activity_graph(graph, config=_sampler_config())

    assert calls["sample"] == {
        "draws": 3,
        "tune": 4,
        "chains": 4,
        "random_seed": 42,
        "progressbar": False,
        "target_accept": 0.9,
        "nuts_sampler": "numpyro",
        "nuts": {"chain_method": "vectorized"},
    }
    assert calls["posterior_predictive"][0] is fitted.idata
    assert calls["posterior_predictive"][1] == {
        "var_names": ["conditional_mean_pred", "activity_probability_pred"],
        "random_seed": 42,
        "progressbar": False,
    }
    diagnostic_names = calls["diagnostics"][1]["var_names"]
    assert diagnostic_names == tuple(variable.name for variable in graph.model.free_RVs)
    assert "activity_intercept" in diagnostic_names
    assert fitted.mode == "spatial_activity"
    assert fitted.conditional_mean_draws.shape == (12, 3)
    assert fitted.activity_probability_draws.shape == (12, 3)
    assert fitted.concentration_draws.shape == (12,)
    assert fitted.cohort_sd_draws.shape == (12,)
    assert fitted.diagnostics == _diagnostics()


def test_ordinary_diagnostics_exclude_analytic_activity_constant(monkeypatch) -> None:
    from genomeos.surfaces.spatial_activity_fit import fit_spatial_activity_graph

    calls = {}
    monkeypatch.setattr(
        "genomeos.surfaces.spatial_activity_fit.pm.sample", lambda **_kwargs: _idata()
    )
    monkeypatch.setattr(
        "genomeos.surfaces.spatial_activity_fit.pm.sample_posterior_predictive",
        lambda *_args, **_kwargs: _posterior_predictive(activity=1.0),
    )

    def diagnostics(*_args, **kwargs):
        calls["var_names"] = kwargs["var_names"]
        return _diagnostics()

    monkeypatch.setattr(
        "genomeos.surfaces.spatial_activity_fit.summarize_sampler_diagnostics", diagnostics
    )
    graph = _graph(mode="ordinary")

    fit_spatial_activity_graph(graph, config=_sampler_config())

    assert calls["var_names"] == tuple(variable.name for variable in graph.model.free_RVs)
    assert "activity_probability" not in calls["var_names"]
    assert not any(name.startswith("activity_") for name in calls["var_names"])


def test_fit_refuses_nonconvergence_before_predictive_sampling(monkeypatch) -> None:
    from genomeos.surfaces.spatial_activity_fit import (
        SpatialActivityConvergenceError,
        fit_spatial_activity_graph,
    )

    failed = replace(_diagnostics(), max_rhat=1.20, divergence_count=2)
    monkeypatch.setattr(
        "genomeos.surfaces.spatial_activity_fit.pm.sample", lambda **_kwargs: _idata()
    )
    monkeypatch.setattr(
        "genomeos.surfaces.spatial_activity_fit.summarize_sampler_diagnostics",
        lambda *_args, **_kwargs: failed,
    )
    predictive_called = False

    def posterior_predictive(*_args, **_kwargs):
        nonlocal predictive_called
        predictive_called = True

    monkeypatch.setattr(
        "genomeos.surfaces.spatial_activity_fit.pm.sample_posterior_predictive",
        posterior_predictive,
    )

    with pytest.raises(SpatialActivityConvergenceError, match="did not converge") as error:
        fit_spatial_activity_graph(_graph(), config=_sampler_config())
    assert error.value.diagnostics == failed
    assert predictive_called is False


def test_fit_refuses_misaligned_or_invalid_draws(monkeypatch) -> None:
    from genomeos.surfaces.spatial_activity_fit import fit_spatial_activity_graph

    malformed = _posterior_predictive()
    malformed.posterior_predictive["activity_probability_pred"] = (
        ("chain", "draw", "other_prediction"),
        np.full((4, 3, 2), 0.8),
    )
    monkeypatch.setattr(
        "genomeos.surfaces.spatial_activity_fit.pm.sample", lambda **_kwargs: _idata()
    )
    monkeypatch.setattr(
        "genomeos.surfaces.spatial_activity_fit.pm.sample_posterior_predictive",
        lambda *_args, **_kwargs: malformed,
    )
    monkeypatch.setattr(
        "genomeos.surfaces.spatial_activity_fit.summarize_sampler_diagnostics",
        lambda *_args, **_kwargs: _diagnostics(),
    )

    with pytest.raises(ValueError, match="activity_probability_pred"):
        fit_spatial_activity_graph(_graph(), config=_sampler_config())


def test_predictive_draws_one_new_offset_per_shared_heldout_cohort(monkeypatch) -> None:
    from genomeos.surfaces.spatial_activity_fit import (
        fit_spatial_activity_graph,
        predict_spatial_activity_counts,
    )

    monkeypatch.setattr(
        "genomeos.surfaces.spatial_activity_fit.pm.sample", lambda **_kwargs: _idata()
    )
    monkeypatch.setattr(
        "genomeos.surfaces.spatial_activity_fit.pm.sample_posterior_predictive",
        lambda *_args, **_kwargs: _posterior_predictive(),
    )
    monkeypatch.setattr(
        "genomeos.surfaces.spatial_activity_fit.summarize_sampler_diagnostics",
        lambda *_args, **_kwargs: _diagnostics(),
    )
    fitted = fit_spatial_activity_graph(_graph(), config=_sampler_config())

    first = predict_spatial_activity_counts(
        fitted,
        prediction_cohort_index=np.array([0, 0, 1]),
        seed=17,
    )
    second = predict_spatial_activity_counts(
        fitted,
        prediction_cohort_index=np.array([0, 0, 1]),
        seed=17,
    )

    np.testing.assert_array_equal(first.conditional_mean_draws, second.conditional_mean_draws)
    np.testing.assert_array_equal(first.activity_probability_draws, np.full((12, 3), 0.8))
    np.testing.assert_array_equal(first.concentration_draws, np.full((12, 3), 40.0))
    base_logit = np.log(0.1 / 0.9)
    adjusted_logit = np.log(
        first.conditional_mean_draws[:, 0] / (1.0 - first.conditional_mean_draws[:, 0])
    )
    same_cohort_offset = np.log(
        first.conditional_mean_draws[:, 1] / (1.0 - first.conditional_mean_draws[:, 1])
    ) - np.log(0.2 / 0.8)
    np.testing.assert_allclose(adjusted_logit - base_logit, same_cohort_offset)


def test_ordinary_without_training_cohort_effect_preserves_reference_draws(monkeypatch) -> None:
    from genomeos.surfaces.spatial_activity_fit import (
        fit_spatial_activity_graph,
        predict_spatial_activity_counts,
    )

    monkeypatch.setattr(
        "genomeos.surfaces.spatial_activity_fit.pm.sample",
        lambda **_kwargs: _idata(cohort_effect=False),
    )
    monkeypatch.setattr(
        "genomeos.surfaces.spatial_activity_fit.pm.sample_posterior_predictive",
        lambda *_args, **_kwargs: _posterior_predictive(activity=1.0),
    )
    monkeypatch.setattr(
        "genomeos.surfaces.spatial_activity_fit.summarize_sampler_diagnostics",
        lambda *_args, **_kwargs: _diagnostics(),
    )
    fitted = fit_spatial_activity_graph(
        _graph(mode="ordinary", repeated_cohorts=False),
        config=_sampler_config(),
    )

    predictive = predict_spatial_activity_counts(
        fitted,
        prediction_cohort_index=np.array([0, 0, 1]),
        seed=99,
        cdf_backend="cupy",
    )

    np.testing.assert_array_equal(
        predictive.conditional_mean_draws,
        np.broadcast_to(np.array([0.1, 0.2, 0.3]), (12, 3)),
    )
    np.testing.assert_array_equal(predictive.activity_probability_draws, np.ones((12, 3)))
    assert predictive.cdf_backend == "cupy"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("draws", 0),
        ("tune", 0),
        ("chains", 3),
        ("target_accept", 1.0),
        ("nuts_sampler", "unknown"),
        ("max_rhat", 0.99),
        ("min_ess", -1.0),
        ("seed", -1),
    ],
)
def test_sampler_config_refuses_invalid_values(field: str, value: object) -> None:
    with pytest.raises(ValueError):
        replace(_sampler_config(), **{field: value})


@pytest.mark.parametrize(
    "cohorts",
    [np.array([0, 0]), np.array([0, 0, 2]), np.array([0.0, 0.5, 1.0])],
)
def test_prediction_refuses_invalid_cohort_index(cohorts: np.ndarray) -> None:
    from genomeos.surfaces.spatial_activity_fit import (
        SpatialActivityFit,
        predict_spatial_activity_counts,
    )

    fitted = SpatialActivityFit(
        mode="ordinary",
        config=_sampler_config(),
        idata=object(),
        conditional_mean_draws=np.full((12, 3), 0.2),
        activity_probability_draws=np.ones((12, 3)),
        concentration_draws=np.full(12, 40.0),
        cohort_sd_draws=None,
        diagnostics=_diagnostics(),
    )
    with pytest.raises(ValueError, match="prediction_cohort_index"):
        predict_spatial_activity_counts(
            fitted,
            prediction_cohort_index=cohorts,
        )
