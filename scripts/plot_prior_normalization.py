"""Plot the synthetic pointwise-prior contraction counterexample (design §7.1b; #266).

The fixed geometry isolates normalization from fitting: the hypothetical posterior SD equals
the independently calculated local approximate-prior SD at every evaluated query. Any apparent
contraction under a scalar reference therefore comes only from comparing different locations.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.collections import PolyCollection  # noqa: E402
from matplotlib.colors import Normalize  # noqa: E402

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


def compute_counterexample() -> dict[str, np.ndarray | float | int]:
    """Return the fully authored fixed-geometry no-update counterexample from issue #266."""
    anchor_cells, anchor_lat, anchor_lon = _regional_land_cells(1)
    inducing = h3_inducing_points(anchor_lat, anchor_lon, 16, reach_km=1500.0)
    inducing_lat, inducing_lon = _from_unit_sphere(inducing)
    query_cells, query_lat, query_lon = _regional_land_cells(2)
    local_sd = _conditional_frequency_sd(inducing, query_lat, query_lon)
    nearest_inducing_distance_km = _haversine_to_grid(
        query_lat, query_lon, inducing_lat, inducing_lon
    )
    # The old implementation used whichever observation happened to come first. Fix that
    # otherwise arbitrary ordering to a support cell near (20 N, 2 E), which is collocated with
    # an inducing location and therefore makes the scalar-denominator failure easy to inspect.
    reference_index = int(np.argmin((anchor_lat - 20.0) ** 2 + (anchor_lon - 2.0) ** 2))
    scalar_sd = float(
        _conditional_frequency_sd(
            inducing, anchor_lat[reference_index : reference_index + 1],
            anchor_lon[reference_index : reference_index + 1],
        )[0]
    )
    controls = np.array([[-75.0, -150.0], [-70.0, 150.0], [75.0, -150.0], [80.0, 160.0]])
    control_distance = _haversine_to_grid(
        controls[:, 0], controls[:, 1], anchor_lat, anchor_lon
    )
    return {
        "anchor_cells": anchor_cells,
        "anchor_lat": anchor_lat,
        "anchor_lon": anchor_lon,
        "inducing_lat": inducing_lat,
        "inducing_lon": inducing_lon,
        "query_cells": query_cells,
        "query_lat": query_lat,
        "query_lon": query_lon,
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


def render(out: Path) -> Path:
    """Map the approximation geometry, resulting scalar error, and corrected statistic."""
    result = compute_counterexample()
    scalar_ratio = result["scalar_ratio"]
    inducing_distance = result["nearest_inducing_distance_km"]
    distance_correlation = float(np.corrcoef(inducing_distance, scalar_ratio)[0, 1])
    false_support = scalar_ratio < SUPPORT_THRESHOLD
    polygons, kept = h3_polygons(result["query_cells"])
    kept = np.asarray(kept)
    fig, (geometry_ax, old_ax, local_ax) = plt.subplots(1, 3, figsize=(18.2, 5.7))
    norm = Normalize(vmin=0.75, vmax=1.0)
    for axis in (geometry_ax, old_ax, local_ax):
        axis.set_facecolor("#eceff1")
        axis.set(xlim=(-25, 73), ylim=(-35, 45), xlabel="longitude")
        axis.grid(color="white", linewidth=0.45, alpha=0.4)

    distance_surface = PolyCollection(
        polygons, array=inducing_distance[kept], cmap="viridis_r",
        norm=Normalize(vmin=0.0, vmax=2250.0), edgecolors="none", zorder=2,
    )
    geometry_ax.add_collection(distance_surface)
    draw_countries(geometry_ax, color="#374151", linewidth=0.55, zorder=3)
    geometry_ax.scatter(
        result["anchor_lon"], result["anchor_lat"], s=8, facecolor="#4b5563",
        edgecolor="none", zorder=4, label="59 synthetic H3 land support sites",
    )
    geometry_ax.scatter(
        result["inducing_lon"], result["inducing_lat"], s=24,
        facecolor="white", edgecolor="#111827", linewidth=0.8, zorder=5,
        label="16 computational inducing locations",
    )
    geometry_ax.set(
        ylabel="latitude",
        title="A. Computational geometry\nnearest inducing distance",
    )
    geometry_ax.legend(loc="lower left", fontsize=7.2, frameon=True)
    distance_colorbar = fig.colorbar(
        distance_surface, ax=geometry_ax, shrink=0.78, pad=0.025
    )
    distance_colorbar.set_label("distance to nearest inducing location (km)", fontsize=8.5)

    surface = PolyCollection(
        polygons, array=scalar_ratio[kept], cmap="Blues_r", norm=norm,
        edgecolors="none", zorder=2,
    )
    old_ax.add_collection(surface)
    false_polygons = [polygon for polygon, index in zip(polygons, kept, strict=True)
                      if false_support[index]]
    old_ax.add_collection(
        PolyCollection(
            false_polygons, facecolors="#7f1d1d20", edgecolors="#7f1d1d",
            linewidths=0.8, zorder=3,
        )
    )
    draw_countries(old_ax, color="#374151", linewidth=0.55, zorder=4)
    old_ax.scatter(
        result["anchor_lon"], result["anchor_lat"], s=8, facecolor="#4b5563",
        edgecolor="none", zorder=5, label="59 synthetic H3 land support sites",
    )
    old_ax.scatter(
        result["inducing_lon"], result["inducing_lat"], s=24,
        facecolor="white", edgecolor="#111827", linewidth=0.8, zorder=6,
        label="16 computational inducing locations",
    )
    reference_index = int(result["reference_index"])
    reference_lat = float(result["anchor_lat"][reference_index])
    reference_lon = float(result["anchor_lon"][reference_index])
    old_ax.scatter(
        [reference_lon], [reference_lat], marker="*", s=150, facecolor="#111827",
        edgecolor="white", linewidth=0.7, zorder=7, label="old denominator location",
    )
    old_ax.annotate(
        "one denominator site",
        xy=(reference_lon, reference_lat), xytext=(reference_lon + 8.0, reference_lat + 5.0),
        fontsize=7.5, color="#111827", ha="left",
        arrowprops={"arrowstyle": "->", "color": "#111827", "linewidth": 0.7},
        zorder=8,
    )
    old_ax.text(
        0.02, 0.97,
        f"{int(false_support.sum())}/{len(scalar_ratio)} land cells falsely cross 0.9\n"
        "Red borders mark the invented support",
        transform=old_ax.transAxes, va="top", fontsize=8.5,
        bbox={"boxstyle": "round,pad=0.35", "facecolor": "white", "alpha": 0.9, "edgecolor": "#7f1d1d"},
    )
    old_ax.set(
        title="B. Old scalar denominator\ninvented posterior contraction",
    )
    colorbar = fig.colorbar(surface, ax=old_ax, shrink=0.78, pad=0.025)
    colorbar.set_label("posterior SD / old scalar prior SD", fontsize=8.5)
    colorbar.set_ticks([0.76, 0.8, 0.9, 1.0])

    local_ax.add_collection(
        PolyCollection(polygons, facecolors="#d1fae5", edgecolors="none", zorder=2)
    )
    draw_countries(local_ax, color="#374151", linewidth=0.55, zorder=3)
    local_ax.scatter(
        result["anchor_lon"], result["anchor_lat"], s=8, facecolor="#4b5563",
        edgecolor="none", zorder=4,
    )
    local_ax.scatter(
        result["inducing_lon"], result["inducing_lat"], s=20,
        facecolor="white", edgecolor="#6b7280", linewidth=0.7, zorder=5,
    )
    local_ax.text(
        0.5, 0.52, "posterior SD / local prior SD\n= 1.0 everywhere",
        transform=local_ax.transAxes, ha="center", va="center", fontsize=12,
        color="#065f46", weight="bold",
    )
    local_ax.text(
        0.02, 0.97, f"{len(scalar_ratio)}/{len(scalar_ratio)} land cells remain prior-dominated",
        transform=local_ax.transAxes, va="top", fontsize=8.5,
        bbox={"boxstyle": "round,pad=0.35", "facecolor": "white", "alpha": 0.9,
              "edgecolor": "#047857"},
    )
    local_ax.set(title="C. Correct local denominator\nno invented contraction")
    fig.suptitle(
        "A spatial approximation artifact must not look like learning",
        fontsize=13.5,
    )
    fig.text(
        0.5, 0.91,
        "Land is the evaluation domain. Great-circle distance to the inducing locations drives "
        f"the old ratio (Pearson r = {distance_correlation:.3f}).",
        ha="center", fontsize=9.2, color="#374151",
    )
    fig.subplots_adjust(left=0.045, right=0.985, bottom=0.12, top=0.82, wspace=0.22)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=220)
    plt.close(fig)
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    print(render(args.out))


if __name__ == "__main__":
    main()
