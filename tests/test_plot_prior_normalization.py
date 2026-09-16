"""Synthetic pointwise-prior review figure tests (Atlas design §7.1b; issue #266)."""

from __future__ import annotations

from pathlib import Path

import matplotlib
import numpy as np
import pytest

from scripts.plot_prior_normalization import (
    SUPPORT_THRESHOLD,
    _haversine_to_grid,
    _load_regional_geometry,
    build_figure,
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


# ---------------------------------------------------------------------------
# What each panel actually draws (#298)
#
# The test below used to assert only that a file appeared and exceeded 10 kB. That would still pass
# if the two map panels were swapped, if latitude and longitude were exchanged in a plot call, or if
# a colour scale were reversed — each of which changes what the figure means to a reader while
# leaving a perfectly valid PNG behind. This project's review figures carry invariants, so those
# need a test rather than a person remembering to look.
# ---------------------------------------------------------------------------

FIXTURE = Path(__file__).parent / "fixtures" / "map_hbs_surveys.csv"


@pytest.fixture(scope="module")
def drawn():
    """The rendered figure and the values it was built from, for one fixture."""
    matplotlib.use("Agg")
    figure, result = build_figure(FIXTURE)
    yield figure, result
    matplotlib.pyplot.close(figure)


def _collections(axis):
    return [c for c in axis.collections if isinstance(c, matplotlib.collections.PolyCollection)]


def _surface(axis):
    """The one mapped field on an axis — the collection carrying scalar data."""
    mapped = [c for c in _collections(axis) if c.get_array() is not None]
    assert len(mapped) == 1, f"expected exactly one mapped field, found {len(mapped)}"
    return mapped[0]


def _luminance(rgba):
    red, green, blue = rgba[:3]
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def test_each_map_panel_is_bound_to_the_quantity_it_claims_to_show(drawn):
    """Swapping the two panels is the error this catches, and it looks like nothing on the page.

    Both panels draw the same cells over the same region, so a figure with the distance field and
    the ratio field exchanged renders cleanly and tells the reader the opposite story.
    """
    figure, result = drawn
    geometry_ax, old_ax, _ = figure.axes[:3]
    kept = np.asarray(result["kept"])

    np.testing.assert_array_equal(
        _surface(geometry_ax).get_array(), result["nearest_inducing_distance_km"][kept]
    )
    np.testing.assert_array_equal(_surface(old_ax).get_array(), result["scalar_ratio"][kept])


def test_every_scatter_plots_longitude_against_latitude(drawn):
    """A latitude/longitude swap in a plot call produces a map, just not of anywhere real."""
    figure, result = drawn
    geometry_ax, old_ax, _ = figure.axes[:3]

    expected = {
        "observations": (result["observation_lon"], result["observation_lat"]),
        "model locations": (result["support_lon"], result["support_lat"]),
    }
    drawn_pairs = [
        (scatter.get_offsets()[:, 0], scatter.get_offsets()[:, 1])
        for scatter in geometry_ax.collections
        if isinstance(scatter, matplotlib.collections.PathCollection)
    ]
    for label, (lon, lat) in expected.items():
        assert any(
            len(x) == len(lon)
            and np.allclose(np.asarray(x), lon)
            and np.allclose(np.asarray(y), lat)
            for x, y in drawn_pairs
        ), f"panel A does not plot {label} as (longitude, latitude)"

    # Selecting panel B's model-location layer by point count is not safe: on a small fixture the
    # observation layer can have the same number of points. Match on the coordinates instead.
    panel_b_pairs = [
        (scatter.get_offsets()[:, 0], scatter.get_offsets()[:, 1])
        for scatter in old_ax.collections
        if isinstance(scatter, matplotlib.collections.PathCollection)
    ]
    assert any(
        len(x) == len(result["inducing_lon"])
        and np.allclose(np.asarray(x), result["inducing_lon"])
        and np.allclose(np.asarray(y), result["inducing_lat"])
        for x, y in panel_b_pairs
    ), "panel B does not plot the model locations as (longitude, latitude)"


def test_the_mechanism_panel_plots_error_against_distance_not_the_reverse(drawn):
    """Panel C's whole claim is that error follows distance. Swapping the axes inverts the claim."""
    figure, result = drawn
    mechanism_ax = figure.axes[2]
    points = [
        scatter
        for scatter in mechanism_ax.collections
        if isinstance(scatter, matplotlib.collections.PathCollection)
    ]
    assert len(points) == 1
    offsets = points[0].get_offsets()
    np.testing.assert_allclose(offsets[:, 0], result["nearest_inducing_distance_km"])
    np.testing.assert_allclose(offsets[:, 1], result["scalar_ratio"])


def test_the_distance_ramp_reads_low_to_high_without_its_legend(drawn):
    """A reversed ramp inverts a map's meaning for anyone who only glances at it.

    Near is bright and far is dark on the distance panel, so the eye reads "lots of evidence here"
    where the evidence actually is.
    """
    figure, _ = drawn
    surface = _surface(figure.axes[0])
    norm, cmap = surface.norm, surface.cmap
    assert (norm.vmin, norm.vmax) == (0.0, 1500.0)
    assert _luminance(cmap(norm(norm.vmin))) > _luminance(cmap(norm(norm.vmax)))


def test_the_ratio_ramp_keeps_its_dark_is_worse_convention(drawn):
    """The error panel is deliberately the other way round: dark marks the understated cells."""
    figure, _ = drawn
    surface = _surface(figure.axes[1])
    norm, cmap = surface.norm, surface.cmap
    assert norm.vmin < norm.vmax
    assert _luminance(cmap(norm(norm.vmin))) < _luminance(cmap(norm(norm.vmax)))


def test_measured_sites_stay_visually_separable_from_derived_model_locations(drawn):
    """Observations and model geometry must never read as one layer (design §4).

    Same panel is fine and is the point of the figure; indistinguishable markers are not.
    """
    figure, _ = drawn
    scatters = [
        scatter
        for scatter in figure.axes[0].collections
        if isinstance(scatter, matplotlib.collections.PathCollection)
    ]
    assert len(scatters) >= 2
    sizes = {float(np.atleast_1d(scatter.get_sizes())[0]) for scatter in scatters}
    faces = {tuple(np.atleast_2d(scatter.get_facecolor())[0]) for scatter in scatters}
    assert len(sizes) >= 2, "the two point layers are drawn at the same size"
    assert len(faces) >= 2, "the two point layers are drawn in the same colour"


def test_the_false_support_overlay_marks_exactly_the_cells_that_cross_the_threshold(drawn):
    """The red outlines are the figure's headline count, so they must match the computed one."""
    figure, result = drawn
    kept = np.asarray(result["kept"])
    expected = int((result["scalar_ratio"][kept] < SUPPORT_THRESHOLD).sum())
    overlays = [c for c in _collections(figure.axes[1]) if c.get_array() is None]
    assert len(overlays) == 1
    assert len(overlays[0].get_paths()) == expected


def test_rendering_still_writes_the_file(tmp_path):
    out = tmp_path / "prior-normalization.png"
    assert render(out, FIXTURE) == out
    assert out.stat().st_size > 10_000
