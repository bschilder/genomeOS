"""Basemap geometry used by the review figures.

The antimeridian test is the one that matters. An H3 cell straddling ±180° has boundary vertices
near both +179° and −179°; drawn as a polygon in lon/lat it becomes a band across the entire map,
and because it renders as *plausible colour* rather than as an error it is the kind of bug that
ships inside a figure unnoticed.
"""

from __future__ import annotations

import h3
import numpy as np

from genomeos.viz.basemap import h3_land_cells, h3_polygons, land_mask

RESOLUTION = 2  # coarse: this exercises the geometry, not the resolution ladder


def test_land_mask_separates_land_from_ocean():
    lons = np.array([2.35, 78.04, -30.0, -140.0])  # Paris, Delhi, mid-Atlantic, mid-Pacific
    lats = np.array([48.85, 27.17, 0.0, 10.0])
    assert land_mask(lons, lats).tolist() == [True, True, False, False]


def test_h3_land_cells_are_all_on_land():
    cells = h3_land_cells(RESOLUTION)
    assert cells, "no land cells found"
    centres = np.array([h3.cell_to_latlng(cell) for cell in cells])
    assert land_mask(centres[:, 1], centres[:, 0]).all()
    # Land is roughly 29% of the globe; centre-in-polygon on a coarse basemap should land nearby.
    assert 0.15 < len(cells) / len(list(h3.get_res0_cells())) / 7**RESOLUTION < 0.45


def test_h3_polygons_never_span_the_antimeridian():
    polygons, kept = h3_polygons(h3_land_cells(RESOLUTION))
    assert polygons
    for polygon in polygons:
        lons = [lon for lon, _ in polygon]
        assert max(lons) - min(lons) <= 180.0
    assert len(kept) == len(polygons)


def test_h3_polygons_kept_indices_align_with_input_cells():
    """Callers subset their per-cell values by `kept`, so a misaligned index silently mislocates
    every value after the first dropped cell — a wrong map, not a crash."""
    cells = h3_land_cells(RESOLUTION)
    polygons, kept = h3_polygons(cells)
    for polygon, index in zip(polygons, kept, strict=True):
        centre_lat, centre_lon = h3.cell_to_latlng(cells[index])
        lons = [lon for lon, _ in polygon]
        lats = [lat for _, lat in polygon]
        assert min(lons) <= centre_lon <= max(lons)
        assert min(lats) <= centre_lat <= max(lats)
