"""Synthetic pointwise-prior review figure tests (Atlas design §7.1b; issue #266)."""

from __future__ import annotations

import pytest

from scripts.plot_prior_normalization import compute_counterexample, render


def test_conditional_counterexample_matches_the_authored_numeric_control():
    result = compute_counterexample()
    target = (result["query_lat"] == -25) & (result["query_lon"] == 64)
    assert result["scalar_ratio"][target].item() == pytest.approx(0.8953380210217113, abs=1e-14)
    assert result["local_ratio"][target].item() == 1.0
    assert len(result["query_lat"]) == 77
    assert result["control_unknown"].tolist() == [True, True, True, True]


def test_prior_normalization_figure_is_created_standalone(tmp_path):
    out = tmp_path / "prior-normalization.png"
    assert render(out) == out
    assert out.stat().st_size > 10_000
