"""B1G comparison artifact and figure adapter tests (design §§4–8, 12; issue #331)."""

from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd
import pytest
from matplotlib.markers import MarkerStyle

from scripts.plot_hbs_b1g_benchmark import _verify_output_files, build_figure, plt


def _report() -> dict[str, object]:
    metrics = {
        "coverage_50": 0.5,
        "coverage_80": 0.8,
        "coverage_95": 0.95,
    }
    return {
        "scientific_promotion_decision": "not_made",
        "comparisons": {
            "B2-current": {
                "matched_observation_count": 3,
                "candidate_benchmark": {"metrics": metrics},
                "baseline_benchmark": {
                    "metrics": {
                        "coverage_50": 0.48,
                        "coverage_80": 0.79,
                        "coverage_95": 0.94,
                    }
                },
                "balanced_macro_metric_differences": {
                    "mean_log_score": {"available": True, "value": 0.25, "reason": None},
                    "relative_mae_improvement": 0.06,
                },
                "paired_outer_block_log_score_interval": {
                    "available": True,
                    "lower": 0.01,
                    "upper": 0.40,
                },
            }
        },
    }


def _matched() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "lon": [-75.0, 5.0, 80.0],
            "lat": [40.0, 10.0, 20.0],
            "log_score_delta": [-1.0, 0.0, 2.0],
            "absolute_error_improvement": [-0.02, 0.0, 0.03],
        }
    )


def test_figure_uses_geographic_circle_marks_and_green_for_improvement():
    figure = build_figure(_report(), _matched())
    try:
        for axis in figure.axes[:2]:
            points = [collection for collection in axis.collections if collection.get_offsets().shape[0] == 3]
            assert len(points) == 1
            scatter = points[0]
            expected_circle = MarkerStyle("o").get_path().transformed(
                MarkerStyle("o").get_transform()
            ).vertices
            assert scatter.get_paths()[0].vertices == pytest.approx(expected_circle)
            negative = scatter.cmap(scatter.norm(-1.0))
            positive = scatter.cmap(scatter.norm(1.0))
            assert negative[0] > negative[1]
            assert positive[1] > positive[0]
    finally:
        plt.close(figure)


def test_undefined_paired_score_stays_visible_as_an_outlined_circle():
    matched = _matched()
    matched.loc[1, "log_score_delta"] = np.nan
    figure = build_figure(_report(), matched)
    try:
        log_axis = figure.axes[0]
        points = [
            collection
            for collection in log_axis.collections
            if collection.get_offsets().shape[0] == 3
        ][0]
        assert points.get_edgecolors()[:, 3].max() == pytest.approx(0.82)
        assert log_axis.get_legend() is not None
        assert [text.get_text() for text in log_axis.get_legend().get_texts()] == [
            "Undefined paired score"
        ]
    finally:
        plt.close(figure)


def test_output_inventory_rejects_a_changed_artifact(tmp_path):
    artifact = tmp_path / "artifact"
    artifact.mkdir()
    output = artifact / "predictions.tsv"
    output.write_text("a\n")
    content = output.read_bytes()
    manifest = {
        "output_files": {
            output.name: {
                "sha256": hashlib.sha256(content).hexdigest(),
                "size_bytes": len(content),
            }
        }
    }
    _verify_output_files(artifact, manifest)

    output.write_text("changed\n")
    with pytest.raises(ValueError, match="differs from its manifest"):
        _verify_output_files(artifact, manifest)
