"""Synthetic pointwise-prior review figure tests (Atlas design §7.1b; issue #266)."""

from __future__ import annotations

import numpy as np
import pytest

from scripts.plot_prior_normalization import (
    _haversine_to_grid,
    compute_counterexample,
    render,
)


def test_conditional_counterexample_matches_the_authored_numeric_control():
    result = compute_counterexample()
    target = int(result["scalar_ratio"].argmin())
    assert result["scalar_ratio"][target] == pytest.approx(0.8323790673599101, abs=1e-10)
    assert result["local_ratio"][target] == 1.0
    assert len(result["anchor_lat"]) == 16
    assert len(result["query_lat"]) == 414
    assert len(result["inducing_lat"]) == 16
    assert len(result["inducing_lon"]) == 16
    assert _haversine_to_grid(
        result["anchor_lat"],
        result["anchor_lon"],
        result["inducing_lat"],
        result["inducing_lon"],
    ).max() < 1e-6
    assert len(result["nearest_inducing_distance_km"]) == 414
    relationship = np.corrcoef(
        result["nearest_inducing_distance_km"], result["scalar_ratio"]
    )[0, 1]
    assert relationship == pytest.approx(-0.8970193211246551, abs=1e-10)
    assert int((result["scalar_ratio"] < 0.9).sum()) == 12
    assert result["control_unknown"].tolist() == [True, True, True, True]


def test_prior_normalization_figure_is_created_standalone(tmp_path):
    out = tmp_path / "prior-normalization.png"
    assert render(out) == out
    assert out.stat().st_size > 10_000
