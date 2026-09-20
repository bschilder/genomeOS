"""Plot the geography-aware pointwise-prior contraction counterexample (design §7.1b; #266).

Reviewed MAP HbS survey coordinates determine the approximation geometry, but no allele-frequency
value enters the calculation. The hypothetical posterior SD equals the independently calculated
local approximate-prior SD at every query, so any apparent contraction under a scalar reference
comes only from comparing different locations.

    python scripts/plot_prior_normalization.py \
        --observations data/curated/map_hbs_surveys.csv \
        --out docs/figures/prior_normalization.png
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.collections import PolyCollection  # noqa: E402
from matplotlib.colors import Normalize  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from genomeos.observations.sources import map_surveys  # noqa: E402
from genomeos.surfaces.fit import (  # noqa: E402
    EARTH_RADIUS_KM,
    JITTER,
    h3_inducing_points,
    to_unit_sphere,
)
from genomeos.viz.basemap import (  # noqa: E402
    draw_countries,
    h3_land_cells,
    h3_polygons,
)

SEED = 42
LENGTHSCALE_KM = 1500.0
SUPPORT_THRESHOLD = 0.9
REGION = (-20.0, 68.0, -30.0, 40.0)
N_INDUCING = 64


def _matern52(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    distance = np.linalg.norm(left[:, None, :] - right[None, :, :], axis=-1)
    scaled = np.sqrt(5.0) * distance / (LENGTHSCALE_KM / EARTH_RADIUS_KM)
    return (1.0 + scaled + scaled**2 / 3.0) * np.exp(-scaled)


def _logistic_normal_sd(variance: np.ndarray) -> np.ndarray:
    nodes, weights = np.polynomial.hermite.hermgauss(256)
    latent = -3.5 + np.sqrt(2.0 * variance[:, None]) * nodes
    frequency = 1.0 / (1.0 + np.exp(-latent))
    mean = (frequency * weights).sum(axis=1) / np.sqrt(np.pi)
    second = (frequency**2 * weights).sum(axis=1) / np.sqrt(np.pi)
    return np.sqrt(second - mean**2)


def _conditional_frequency_sd(
    inducing: np.ndarray, lat: np.ndarray, lon: np.ndarray
) -> np.ndarray:
    query = to_unit_sphere(lat, lon)
    kuu = _matern52(inducing, inducing) + JITTER * np.eye(len(inducing))
    kux = _matern52(inducing, query)
    # diag(K_xu @ solve(K_uu, K_ux)), independently evaluated from the PyMC graph.
    solved = np.linalg.solve(kuu, kux)
    field_variance = np.einsum("ij,ji->i", kux.T, solved)
    return _logistic_normal_sd(1.5**2 + field_variance)


def _haversine_to_grid(
    lat: np.ndarray, lon: np.ndarray, anchor_lat: np.ndarray, anchor_lon: np.ndarray
) -> np.ndarray:
    lat1 = np.radians(lat[:, None])
    lon1 = np.radians(lon[:, None])
    lat2 = np.radians(anchor_lat[None, :])
    lon2 = np.radians(anchor_lon[None, :])
    a = (
        np.sin((lat2 - lat1) / 2.0) ** 2
        + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2.0) ** 2
    )
    return (2.0 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))).min(axis=1)


def _from_unit_sphere(points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return latitude/longitude for plotting the actual inducing locations."""
    latitude = np.degrees(np.arcsin(np.clip(points[:, 2], -1.0, 1.0)))
    longitude = np.degrees(np.arctan2(points[:, 1], points[:, 0]))
    return latitude, longitude


def _regional_land_cells(resolution: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return deterministic H3 land cells inside the authored geographic extent."""
    import h3

    cells = np.asarray(h3_land_cells(resolution))
    centres = np.asarray([h3.cell_to_latlng(cell) for cell in cells], dtype=float)
    west, east, south, north = REGION
    keep = (
        (centres[:, 0] >= south)
        & (centres[:, 0] <= north)
        & (centres[:, 1] >= west)
        & (centres[:, 1] <= east)
    )
    cells, centres = cells[keep], centres[keep]
    order = np.lexsort((centres[:, 1], centres[:, 0]))
    return cells[order], centres[order, 0], centres[order, 1]


def _spatially_balanced_sites(
    cells: np.ndarray,
    lat: np.ndarray,
    lon: np.ndarray,
    n_sites: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Select deterministic maximin centers from survey-supported H3 cells."""
    if not 1 <= n_sites <= len(cells):
        raise ValueError("n_sites must be between 1 and the number of candidate cells")

    # Each selection depends on the previous one, but the expensive geographic work is one
    # vectorized distance matrix. Millimetre rounding makes numerical ties platform-stable.
    lat1 = np.radians(lat[:, None])
    lon1 = np.radians(lon[:, None])
    lat2 = np.radians(lat[None, :])
    lon2 = np.radians(lon[None, :])
    a = (
        np.sin((lat2 - lat1) / 2.0) ** 2
        + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2.0) ** 2
    )
    pairwise_km = 2.0 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))
    west, east, south, north = REGION
    centre_lat = np.asarray([(south + north) / 2.0])
    centre_lon = np.asarray([(west + east) / 2.0])
    centre_distance = _haversine_to_grid(lat, lon, centre_lat, centre_lon)

    chosen = np.empty(n_sites, dtype=int)
    chosen[0] = int(np.argmin(np.round(centre_distance, 6)))
    available = np.ones(len(cells), dtype=bool)
    available[chosen[0]] = False
    nearest_km = pairwise_km[:, chosen[0]].copy()
    for index in range(1, n_sites):
        score = np.where(available, np.round(nearest_km, 6), -np.inf)
        chosen[index] = int(np.argmax(score))
        available[chosen[index]] = False
        nearest_km = np.minimum(nearest_km, pairwise_km[:, chosen[index]])
    return cells[chosen], lat[chosen], lon[chosen]


def _survey_supported_sites(
    observation_lat: np.ndarray,
    observation_lon: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Derive balanced res-4 model centers from cells containing measured surveys."""
    import h3

    cells = np.asarray(
        sorted(
            {
                h3.latlng_to_cell(float(lat), float(lon), 4)
                for lat, lon in zip(observation_lat, observation_lon, strict=True)
            }
        )
    )
    centres = np.asarray([h3.cell_to_latlng(cell) for cell in cells], dtype=float)
    return _spatially_balanced_sites(
        cells,
        centres[:, 0],
        centres[:, 1],
        min(N_INDUCING, len(cells)),
    )


def _load_regional_geometry(observations: Path) -> tuple[np.ndarray, np.ndarray]:
    """Load reviewed observation coordinates without using their measured values."""
    frame, _report = map_surveys.load(observations, "prior-normalization-figure")
    west, east, south, north = REGION
    regional = frame[
        frame["lat"].between(south, north) & frame["lon"].between(west, east)
    ]
    if len(regional) < 2:
        raise ValueError("at least two retained observations are required in the map region")
    return regional["lat"].to_numpy(float), regional["lon"].to_numpy(float)


def compute_counterexample(
    observation_lat: np.ndarray,
    observation_lon: np.ndarray,
) -> dict[str, np.ndarray | float | int]:
    """Return the fixed no-update counterexample for an explicit sampling geography."""
    observation_lat = np.asarray(observation_lat, dtype=float)
    observation_lon = np.asarray(observation_lon, dtype=float)
    if (
        observation_lat.ndim != 1
        or observation_lon.ndim != 1
        or observation_lat.shape != observation_lon.shape
        or len(observation_lat) < 2
        or not np.isfinite(observation_lat).all()
        or not np.isfinite(observation_lon).all()
    ):
        raise ValueError("observation coordinates must be matching finite vectors of length >= 2")
    support_cells, support_lat, support_lon = _survey_supported_sites(
        observation_lat,
        observation_lon,
    )
    inducing = h3_inducing_points(
        support_lat,
        support_lon,
        len(support_cells),
        reach_km=1500.0,
    )
    inducing_lat, inducing_lon = _from_unit_sphere(inducing)
    inducing_order = np.lexsort((inducing_lon, inducing_lat))
    inducing = inducing[inducing_order]
    inducing_lat, inducing_lon = inducing_lat[inducing_order], inducing_lon[inducing_order]
    query_cells, query_lat, query_lon = _regional_land_cells(2)
    local_sd = _conditional_frequency_sd(inducing, query_lat, query_lon)
    nearest_observation_distance_km = _haversine_to_grid(
        query_lat, query_lon, observation_lat, observation_lon
    )
    nearest_inducing_distance_km = _haversine_to_grid(
        query_lat, query_lon, inducing_lat, inducing_lon
    )
    # The old implementation used whichever observation happened to come first. Make the
    # arbitrariness of a single scalar denominator visible by pinning the reference to a fixed
    # interior point instead, so it does not move with input order.
    #
    # (5 N, 20 E) is a fixed point inside REGION, not its centroid — that would be (5, 24). Any
    # fixed interior point demonstrates the same thing, so this is left as it is rather than
    # regenerating a published figure to move a reference marker four degrees east (#298).
    REFERENCE_LAT, REFERENCE_LON = 5.0, 20.0
    reference_index = int(
        np.argmin(
            (observation_lat - REFERENCE_LAT) ** 2 + (observation_lon - REFERENCE_LON) ** 2
        )
    )
    scalar_sd = float(
        _conditional_frequency_sd(
            inducing,
            observation_lat[reference_index : reference_index + 1],
            observation_lon[reference_index : reference_index + 1],
        )[0]
    )
    controls = np.array([[-75.0, -150.0], [-70.0, 150.0], [75.0, -150.0], [80.0, 160.0]])
    control_distance = _haversine_to_grid(
        controls[:, 0], controls[:, 1], observation_lat, observation_lon
    )
    return {
        "observation_lat": observation_lat,
        "observation_lon": observation_lon,
        "support_cells": support_cells,
        "support_lat": support_lat,
        "support_lon": support_lon,
        "inducing_lat": inducing_lat,
        "inducing_lon": inducing_lon,
        "query_cells": query_cells,
        "query_lat": query_lat,
        "query_lon": query_lon,
        "nearest_observation_distance_km": nearest_observation_distance_km,
        "nearest_inducing_distance_km": nearest_inducing_distance_km,
        "local_sd": local_sd,
        "scalar_sd": scalar_sd,
        "scalar_ratio": local_sd / scalar_sd,
        "local_ratio": local_sd / local_sd,
        "reference_index": reference_index,
        "controls": controls,
        "control_distance_km": control_distance,
        "control_unknown": control_distance > 2.0 * LENGTHSCALE_KM,
    }


def build_figure(observations: Path) -> tuple[Figure, dict[str, Any]]:
    """Map sampling geography, resulting scalar error, and its computational mechanism.

    Returns the figure alongside the values it was drawn from, so a test can check that each panel
    is bound to the quantity it claims to show. Saving is `render`'s job. Splitting the two is what
    makes the panel bindings testable at all: a figure that has already been written and closed can
    only be checked by looking at it (#298).
    """
    observation_lat, observation_lon = _load_regional_geometry(observations)
    result = compute_counterexample(observation_lat, observation_lon)
    scalar_ratio = result["scalar_ratio"]
    inducing_distance = result["nearest_inducing_distance_km"]
    distance_correlation = float(np.corrcoef(inducing_distance, scalar_ratio)[0, 1])
    false_support = scalar_ratio < SUPPORT_THRESHOLD
    polygons, kept = h3_polygons(result["query_cells"])
    kept = np.asarray(kept)
    result["kept"] = kept
    fig, (geometry_ax, old_ax, mechanism_ax) = plt.subplots(1, 3, figsize=(18.2, 5.7))
    norm = Normalize(vmin=0.75, vmax=1.0)
    for axis in (geometry_ax, old_ax):
        axis.set_facecolor("#eceff1")
        axis.set(xlim=(-25, 73), ylim=(-35, 45), xlabel="longitude")
        axis.grid(color="white", linewidth=0.45, alpha=0.4)

    distance_surface = PolyCollection(
        polygons,
        array=result["nearest_inducing_distance_km"][kept],
        cmap="viridis_r",
        norm=Normalize(vmin=0.0, vmax=1500.0),
        edgecolors="none",
        zorder=2,
    )
    geometry_ax.add_collection(distance_surface)
    draw_countries(geometry_ax, color="#374151", linewidth=0.55, zorder=3)
    geometry_ax.scatter(
        result["observation_lon"],
        result["observation_lat"],
        s=5,
        facecolor="#111827",
        edgecolor="none",
        alpha=0.55,
        zorder=4,
        label=f"{len(observation_lat)} retained MAP HbS survey sites",
    )
    geometry_ax.scatter(
        result["support_lon"],
        result["support_lat"],
        s=24,
        facecolor="white",
        edgecolor="#111827",
        linewidth=0.75,
        zorder=5,
        label=f"{len(result['support_lat'])} balanced model centers derived from survey cells",
    )
    geometry_ax.set(
        ylabel="latitude",
        title="A. Evidence defines the model geometry\ndistance to nearest retained model location",
    )
    geometry_ax.legend(loc="lower left", fontsize=7.2, frameon=True)
    distance_colorbar = fig.colorbar(
        distance_surface, ax=geometry_ax, shrink=0.78, pad=0.025
    )
    distance_colorbar.set_label("distance to nearest model location (km)", fontsize=8.5)

    surface = PolyCollection(
        polygons,
        array=scalar_ratio[kept],
        cmap="Blues_r",
        norm=norm,
        edgecolors="none",
        zorder=2,
    )
    old_ax.add_collection(surface)
    false_polygons = [
        polygon
        for polygon, index in zip(polygons, kept, strict=True)
        if false_support[index]
    ]
    old_ax.add_collection(
        PolyCollection(
            false_polygons,
            facecolors="#7f1d1d20",
            edgecolors="#7f1d1d",
            linewidths=0.8,
            zorder=3,
        )
    )
    draw_countries(old_ax, color="#374151", linewidth=0.55, zorder=4)
    old_ax.scatter(
        result["observation_lon"],
        result["observation_lat"],
        s=3,
        facecolor="#111827",
        edgecolor="none",
        alpha=0.28,
        zorder=5,
    )
    old_ax.scatter(
        result["inducing_lon"],
        result["inducing_lat"],
        s=24,
        facecolor="white",
        edgecolor="#111827",
        linewidth=0.75,
        zorder=6,
        label="retained model locations",
    )
    reference_index = int(result["reference_index"])
    reference_lat = float(result["observation_lat"][reference_index])
    reference_lon = float(result["observation_lon"][reference_index])
    old_ax.scatter(
        [reference_lon],
        [reference_lat],
        marker="*",
        s=150,
        facecolor="#111827",
        edgecolor="white",
        linewidth=0.7,
        zorder=7,
        label="old denominator location",
    )
    old_ax.annotate(
        "one denominator site",
        xy=(reference_lon, reference_lat),
        xytext=(reference_lon + 8.0, reference_lat + 5.0),
        fontsize=7.5,
        color="#111827",
        ha="left",
        arrowprops={"arrowstyle": "->", "color": "#111827", "linewidth": 0.7},
        zorder=8,
    )
    old_ax.text(
        0.02,
        0.97,
        f"{int(false_support.sum())}/{len(scalar_ratio)} land cells falsely cross 0.9\n"
        "Red borders mark the invented support",
        transform=old_ax.transAxes,
        va="top",
        fontsize=8.5,
        bbox={
            "boxstyle": "round,pad=0.35",
            "facecolor": "white",
            "alpha": 0.9,
            "edgecolor": "#7f1d1d",
        },
    )
    old_ax.set(
        title="B. The same model geometry\ncreates an artificial spatial pattern",
    )
    old_ax.legend(loc="lower left", fontsize=7.2, frameon=True)
    colorbar = fig.colorbar(surface, ax=old_ax, shrink=0.78, pad=0.025)
    colorbar.set_label("posterior SD / old scalar prior SD", fontsize=8.5)
    colorbar.set_ticks([0.76, 0.8, 0.9, 1.0])

    mechanism_ax.scatter(
        inducing_distance,
        scalar_ratio,
        s=14,
        color="#2a9d8f",
        alpha=0.75,
        edgecolor="none",
        label="old scalar denominator",
    )
    mechanism_ax.axhline(
        1.0,
        color="#047857",
        linewidth=2.0,
        label="correct local denominator",
    )
    mechanism_ax.axhline(
        SUPPORT_THRESHOLD,
        color="#7f1d1d",
        linewidth=0.9,
        linestyle="--",
        label="support threshold",
    )
    mechanism_ax.set(
        xlabel="distance to nearest inducing location (km)",
        ylabel="posterior SD / prior SD",
        ylim=(0.75, 1.01),
        title="C. Mechanism check\nerror follows computational distance",
    )
    mechanism_ax.grid(color="#e5e7eb", linewidth=0.6)
    mechanism_ax.legend(loc="lower left", fontsize=7.5, frameon=True)
    mechanism_ax.text(
        0.98,
        0.04,
        f"Pearson r = {distance_correlation:.3f}\nlocal ratio = 1.0 in every cell",
        transform=mechanism_ax.transAxes,
        ha="right",
        va="bottom",
        fontsize=8.5,
        color="#374151",
    )
    fig.suptitle(
        "Uneven sampling geography exposes a scalar prior-normalization artifact",
        fontsize=13.5,
    )
    fig.text(
        0.5,
        0.91,
        "Dots are measured survey coordinates; rings are the retained model locations that "
        "generate both mapped distance and error. Allele frequencies are not used.",
        ha="center",
        fontsize=9.2,
        color="#374151",
    )
    fig.text(
        0.5,
        0.025,
        "Country borders are orientation only; the covariance uses spherical distance and the "
        "display is clipped to land.",
        ha="center",
        fontsize=8.2,
        color="#4b5563",
    )
    fig.subplots_adjust(left=0.045, right=0.985, bottom=0.14, top=0.82, wspace=0.22)
    return fig, result


def render(out: Path, observations: Path) -> Path:
    """Write the review figure to `out` and return the path written."""
    fig, _ = build_figure(observations)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=220)
    plt.close(fig)
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    print(render(args.out, args.observations))


if __name__ == "__main__":
    main()
