"""Synthetic pointwise-prior review figure tests (Atlas design §7.1b; issue #266)."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from scripts.plot_prior_normalization import (
    _haversine_to_grid,
    _load_regional_geometry,
    compute_counterexample,
    render,
)


def test_conditional_counterexample_matches_the_authored_numeric_control():
    fixture = Path(__file__).parent / "fixtures" / "map_hbs_surveys.csv"
    observation_lat, observation_lon = _load_regional_geometry(fixture)
    result = compute_counterexample(observation_lat, observation_lon)
    assert len(result["observation_lat"]) == 6
    assert len(result["query_lat"]) == 414
    assert len(result["inducing_lat"]) == 6
    assert len(result["inducing_lon"]) == 6
    assert len(result["support_lat"]) == 6
    assert _haversine_to_grid(
        result["support_lat"],
        result["support_lon"],
        result["inducing_lat"],
        result["inducing_lon"],
    ).max() < 1e-6
    np.testing.assert_array_equal(result["local_ratio"], np.ones(414))
    assert len(result["nearest_inducing_distance_km"]) == 414
    assert len(result["nearest_observation_distance_km"]) == 414
    relationship = np.corrcoef(
        result["nearest_inducing_distance_km"], result["scalar_ratio"]
    )[0, 1]
    assert relationship < -0.8
    assert float(result["scalar_ratio"].min()) < 0.75
    assert int((result["scalar_ratio"] < 0.9).sum()) > 250
    assert result["control_unknown"].tolist() == [True, True, True, True]

    reversed_result = compute_counterexample(observation_lat[::-1], observation_lon[::-1])
    np.testing.assert_allclose(
        reversed_result["inducing_lat"], result["inducing_lat"], rtol=0.0, atol=1e-12
    )
    np.testing.assert_allclose(
        reversed_result["inducing_lon"], result["inducing_lon"], rtol=0.0, atol=1e-12
    )
    np.testing.assert_allclose(
        reversed_result["scalar_ratio"], result["scalar_ratio"], rtol=0.0, atol=1e-12
    )


def test_prior_normalization_figure_is_created_standalone(tmp_path):
    out = tmp_path / "prior-normalization.png"
    fixture = Path(__file__).parent / "fixtures" / "map_hbs_surveys.csv"
    assert render(out, fixture) == out
    assert out.stat().st_size > 10_000
