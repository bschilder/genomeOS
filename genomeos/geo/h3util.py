"""H3 spatial indexing and the resolution ladder (design §6, P1).

H3 rather than a raster format because design §6 needs region aggregation to become a
`WHERE h3_parent IN (...)` predicate pushdown in DuckDB, and because deck.gl's `H3HexagonLayer`
consumes the indexes directly — one geometry stack instead of two.

Ladder: res 4 (~1,770 km²/cell, 288,122 cells globally) is the global default. Res 5 (~253 km²)
and res 6 (~36 km²) are populated only where observation density supports promotion (§7). Res 6
is the finest v1 emits — finer exceeds what any open georeferenced panel justifies (§4).
"""

from __future__ import annotations

from math import asin, cos, radians, sin, sqrt

import h3

GLOBAL_RESOLUTION: int = 4
RESOLUTION_LADDER: tuple[int, ...] = (4, 5, 6)

_EARTH_RADIUS_KM = 6371.0088


def _check_resolution(res: int) -> None:
    if res not in RESOLUTION_LADDER:
        raise ValueError(f"resolution {res} is not in the ladder {RESOLUTION_LADDER}")


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * _EARTH_RADIUS_KM * asin(sqrt(a))


def cell_for(lat: float, lon: float, res: int) -> str:
    _check_resolution(res)
    return h3.latlng_to_cell(lat, lon, res)


def parent_of(cell: str, res: int) -> str:
    _check_resolution(res)
    if res > h3.get_resolution(cell):
        raise ValueError(
            f"cannot take a res-{res} parent of a res-{h3.get_resolution(cell)} cell"
        )
    return h3.cell_to_parent(cell, res)


def cells_within_km(lat: float, lon: float, radius_km: float, res: int) -> list[str]:
    """Every res-`res` cell whose centre lies within `radius_km` of (lat, lon).

    Used to place an observation as a disc of its `radius_km` rather than as a point (§7), and to
    compute `eff_n_in_range` for the data-support mask (§7).
    """
    _check_resolution(res)
    if radius_km <= 0:
        raise ValueError("radius_km must be > 0")

    origin = h3.latlng_to_cell(lat, lon, res)
    edge_km = h3.average_hexagon_edge_length(res, unit="km")
    rings = max(1, int(radius_km / edge_km) + 1)
    return [
        cell
        for cell in h3.grid_disk(origin, rings)
        if _haversine_km(lat, lon, *h3.cell_to_latlng(cell)) <= radius_km
    ]
