"""Pointwise latent-prior prediction tests (Atlas design §7.1b)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

import numpy as np
import pymc as pm
import pytest

from genomeos.surfaces import prior as prior_module
from genomeos.surfaces.prior import PRIOR_DRAWS, latent_prior_frequency_sd


def _model(coordinates: np.ndarray):
    with pm.Model() as model:
        x_pred = pm.Data("x_pred", coordinates)
        intercept = pm.Normal("intercept", -2.0, 1.0)
        slope = pm.Normal("slope", 0.0, 0.8)
        pm.Deterministic("freq_pred", pm.math.invlogit(intercept + slope * x_pred[:, 0]))
    return model


def test_actual_prior_prediction_matches_direct_pymc_sampling_and_restores_data():
    original = np.array([[1.0, 0.0, 0.0]])
    query = np.array([[0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
    model = _model(original)

    actual = latent_prior_frequency_sd(model, query, seed=42)
    with model:
        pm.set_data({"x_pred": query})
        direct = pm.sample_prior_predictive(
            draws=PRIOR_DRAWS, var_names=["freq_pred"], random_seed=42
        )
        pm.set_data({"x_pred": original})
    expected = direct.prior["freq_pred"].to_numpy().reshape(PRIOR_DRAWS, 2).std(axis=0)

    np.testing.assert_allclose(actual, expected, rtol=0, atol=1e-10)
    np.testing.assert_array_equal(model["x_pred"].get_value(), original)


def test_prior_prediction_replays_across_order_and_batch_boundaries(monkeypatch):
    query = np.array(
        [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]], dtype=float
    )
    model = _model(query[:1])
    expected = latent_prior_frequency_sd(model, query, seed=7)
    order = np.array([2, 0, 1])
    np.testing.assert_allclose(
        latent_prior_frequency_sd(model, query[order], seed=7), expected[order], rtol=0, atol=1e-10
    )
    monkeypatch.setattr(prior_module, "PRIOR_BATCH_SIZE", 2)
    np.testing.assert_allclose(
        latent_prior_frequency_sd(model, query, seed=7), expected, rtol=0, atol=1e-10
    )
    repeated = latent_prior_frequency_sd(model, query[[1, 1]], seed=7)
    np.testing.assert_allclose(repeated, [expected[1], expected[1]], rtol=0, atol=1e-10)
    assert not np.allclose(latent_prior_frequency_sd(model, query, seed=8), expected)


def test_prior_prediction_restores_data_after_sampling_failure():
    original = np.array([[1.0, 0.0, 0.0]])
    model = _model(original)
    with mock.patch.object(pm, "sample_prior_predictive", side_effect=RuntimeError("boom")):
        with pytest.raises(RuntimeError, match="boom"):
            latent_prior_frequency_sd(model, np.array([[0.0, 1.0, 0.0]]), seed=42)
    np.testing.assert_array_equal(model["x_pred"].get_value(), original)


@pytest.mark.parametrize(
    "draws,match",
    [
        (np.arange(PRIOR_DRAWS, dtype=float).reshape(PRIOR_DRAWS // 2, 2), "wrong shape"),
        (np.full((PRIOR_DRAWS, 1), np.nan), "finite"),
        (np.ones((PRIOR_DRAWS, 1)), "positive"),
    ],
)
def test_prior_prediction_refuses_malformed_draws_and_restores_data(draws, match):
    class Draws:
        def to_numpy(self):
            return draws

    original = np.array([[1.0, 0.0, 0.0]])
    model = _model(original)
    result = SimpleNamespace(prior={"freq_pred": Draws()})
    with mock.patch.object(pm, "sample_prior_predictive", return_value=result):
        with pytest.raises(ValueError, match=match):
            latent_prior_frequency_sd(model, np.array([[0.0, 1.0, 0.0]]), seed=42)
    np.testing.assert_array_equal(model["x_pred"].get_value(), original)


@pytest.mark.parametrize(
    "coordinates,seed,match",
    [
        (np.empty((0, 3)), 42, "nonempty"),
        (np.ones((2, 2)), 42, "shape"),
        (np.array([[np.nan, 0.0, 1.0]]), 42, "finite"),
        (np.array([[2.0, 0.0, 0.0]]), 42, "unit sphere"),
        (np.array([[1.0, 0.0, 0.0]]), -1, "seed"),
        (np.array([[1.0, 0.0, 0.0]]), True, "seed"),
    ],
)
def test_prior_prediction_refuses_invalid_inputs(coordinates, seed, match):
    with pytest.raises(ValueError, match=match):
        latent_prior_frequency_sd(_model(np.array([[1.0, 0.0, 0.0]])), coordinates, seed=seed)
