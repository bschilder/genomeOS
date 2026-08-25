"""Country outlines for review figures, and the country geometry behind them.

Natural Earth 1:110m admin-0 boundaries, simplified to 0.01 degree (~1 km) and stripped to
`iso_a3` plus `name` — 170 KB, small enough to commit so figures are reproducible offline and a
regenerated figure differs only where the data changed.

Plotted with plain matplotlib rather than cartopy or geopandas: outlines are line segments, and
neither dependency earns its install cost for that. `iso_a3` is carried because #94 needs to
assign H3 cells to countries, and joining on ISO3 rather than on country name avoids the
"United Republic of Tanzania" problem across MAP, Piel and Natural Earth.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

COUNTRIES_PATH = Path(__file__).resolve().parents[2] / "reference" / "ne_110m_countries.geojson"

SOURCE = "Natural Earth 1:110m admin-0 (public domain)"


@lru_cache(maxsize=1)
def load_countries() -> list[dict[str, Any]]:
    """GeoJSON features with `iso_a3`, `name` and geometry."""
    return json.loads(COUNTRIES_PATH.read_text())["features"]


def _rings(geometry: dict[str, Any]) -> list[list[list[float]]]:
    if geometry["type"] == "Polygon":
        return geometry["coordinates"]
    return [ring for polygon in geometry["coordinates"] for ring in polygon]


def draw_countries(ax, *, color: str = "#8c959f", linewidth: float = 0.4, zorder: int = 1) -> None:
    """Draw country outlines onto a lat/lon axes.

    Outlines only, never filled: a filled basemap invites reading land colour as data, which is
    the opposite of what the data-support mask is for.
    """
    for feature in load_countries():
        for ring in _rings(feature["geometry"]):
            xs = [point[0] for point in ring]
            ys = [point[1] for point in ring]
            ax.plot(xs, ys, color=color, linewidth=linewidth, zorder=zorder, solid_capstyle="round")


@lru_cache(maxsize=1)
def _land_paths() -> tuple:
    """Exterior rings of every country, each with its bounding box.

    The bounding box is stored so `land_mask` can reject most (point, polygon) pairs with two
    comparisons instead of a ray cast. Nearly every point misses nearly every country, so this
    prefilter is the difference between minutes and seconds on a global grid.
    """
    import numpy as np
    from matplotlib.path import Path as MplPath

    paths = []
    for feature in load_countries():
        geometry = feature["geometry"]
        polygons = (
            [geometry["coordinates"]]
            if geometry["type"] == "Polygon"
            else geometry["coordinates"]
        )
        for polygon in polygons:
            ring = polygon[0] if polygon else None
            if ring and len(ring) >= 3:
                arr = np.asarray(ring, dtype=float)
                paths.append((MplPath(arr), arr[:, 0].min(), arr[:, 0].max(),
                              arr[:, 1].min(), arr[:, 1].max()))
    return tuple(paths)


def land_mask(lons, lats):
    """True where a point falls on land.

    A fitted allele-frequency surface is only meaningful where there are people, and there are
    none in the ocean. §7's four support states are all about *observation proximity* — none of
    them asks whether a cell is inhabited — so without this a surface paints open water in
    confident colour. Clipping to land is the §9 "no denominator, no number" refusal applied one
    stage earlier; see #101.

    Natural Earth land polygons are a coarse stand-in for the real test, which is whether the
    cell has any population at all (`genomeos.geo.population`).
    """
    import numpy as np

    points = np.column_stack([np.asarray(lons).ravel(), np.asarray(lats).ravel()])
    on_land = np.zeros(len(points), dtype=bool)
    xs, ys = points[:, 0], points[:, 1]
    for path, x0, x1, y0, y1 in _land_paths():
        candidate = ~on_land & (xs >= x0) & (xs <= x1) & (ys >= y0) & (ys <= y1)
        if not candidate.any():
            continue
        index = np.flatnonzero(candidate)
        on_land[index] = path.contains_points(points[index])
    return on_land.reshape(np.asarray(lons).shape)


def h3_land_cells(resolution: int) -> list[str]:
    """Every H3 cell at `resolution` whose centre falls on land.

    The model is defined on H3, so the figure should be too: a lat/lon pcolormesh has cells that
    stretch at the equator and shrink toward the poles, which is precisely the distortion the
    spherical kernel and geodesic placement exist to remove. Rendering onto it reintroduces the
    distortion at the last step.
    """
    import h3
    import numpy as np

    cells = [
        child
        for base in h3.get_res0_cells()
        for child in h3.cell_to_children(base, resolution)
    ]
    centres = np.array([h3.cell_to_latlng(cell) for cell in cells], dtype=float)
    on_land = land_mask(centres[:, 1], centres[:, 0])
    return [cell for cell, keep in zip(cells, on_land, strict=True) if keep]


def h3_polygons(cells) -> tuple[list, list[int]]:
    """Cell boundaries as (lon, lat) polygons, dropping any that cross the antimeridian.

    A cell straddling +-180 has vertices near both +179 and -179; drawn as-is it becomes a
    full-width streak across the map. There are only a handful, all in the Pacific, so they are
    dropped rather than split. Returns the polygons and the indices they came from, so callers
    can subset their values to match.
    """
    import h3

    polygons, kept = [], []
    for index, cell in enumerate(cells):
        boundary = h3.cell_to_boundary(cell)
        lons = [point[1] for point in boundary]
        if max(lons) - min(lons) > 180.0:
            continue
        polygons.append([(point[1], point[0]) for point in boundary])
        kept.append(index)
    return polygons, kept
