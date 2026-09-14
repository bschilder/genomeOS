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
from matplotlib.colors import TwoSlopeNorm  # noqa: E402

from genomeos.surfaces.fit import (  # noqa: E402
    EARTH_RADIUS_KM,
    JITTER,
    h3_inducing_points,
    to_unit_sphere,
)
from genomeos.viz.basemap import draw_countries  # noqa: E402

SEED = 42
LENGTHSCALE_KM = 1500.0
SUPPORT_THRESHOLD = 0.9


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


def compute_counterexample() -> dict[str, np.ndarray | float]:
    """Return the fully authored fixed-geometry no-update counterexample from issue #266."""
    anchor_lon_grid, anchor_lat_grid = np.meshgrid(
        np.arange(-20.0, 69.0, 8.0), np.arange(-30.0, 41.0, 10.0)
    )
    anchor_lat, anchor_lon = anchor_lat_grid.ravel(), anchor_lon_grid.ravel()
    inducing = h3_inducing_points(anchor_lat, anchor_lon, 16, reach_km=1500.0)
    query_lon_grid, query_lat_grid = np.meshgrid(
        np.arange(-16.0, 65.0, 8.0), np.arange(-25.0, 36.0, 10.0)
    )
    query_lat, query_lon = query_lat_grid.ravel(), query_lon_grid.ravel()
    local_sd = _conditional_frequency_sd(inducing, query_lat, query_lon)
    scalar_sd = float(_conditional_frequency_sd(inducing, anchor_lat[:1], anchor_lon[:1])[0])
    surface_lon, surface_lat = np.meshgrid(
        np.linspace(-20.0, 68.0, 89), np.linspace(-30.0, 40.0, 71)
    )
    surface_ratio = _conditional_frequency_sd(
        inducing, surface_lat.ravel(), surface_lon.ravel()
    ).reshape(surface_lat.shape) / scalar_sd
    controls = np.array([[-75.0, -150.0], [-70.0, 150.0], [75.0, -150.0], [80.0, 160.0]])
    control_distance = _haversine_to_grid(
        controls[:, 0], controls[:, 1], anchor_lat, anchor_lon
    )
    return {
        "anchor_lat": anchor_lat,
        "anchor_lon": anchor_lon,
        "query_lat": query_lat,
        "query_lon": query_lon,
        "local_sd": local_sd,
        "scalar_sd": scalar_sd,
        "scalar_ratio": local_sd / scalar_sd,
        "local_ratio": local_sd / local_sd,
        "surface_lat": surface_lat,
        "surface_lon": surface_lon,
        "surface_ratio": surface_ratio,
        "controls": controls,
        "control_distance_km": control_distance,
        "control_unknown": control_distance > 2.0 * LENGTHSCALE_KM,
    }


def render(out: Path) -> Path:
    """Map the spatial denominator error and summarize its classification effect."""
    result = compute_counterexample()
    query_lat = result["query_lat"]
    query_lon = result["query_lon"]
    scalar_ratio = result["scalar_ratio"]
    false_support = scalar_ratio < SUPPORT_THRESHOLD
    fig, (map_ax, diagnostic_ax) = plt.subplots(
        1, 2, figsize=(13.5, 5.8), gridspec_kw={"width_ratios": (1.55, 1.0)}
    )
    norm = TwoSlopeNorm(
        vmin=float(np.min(result["surface_ratio"])),
        vcenter=1.0,
        vmax=float(np.max(result["surface_ratio"])),
    )
    map_ax.set_facecolor("#eceff1")
    draw_countries(map_ax, color="#9aa4af", linewidth=0.55)
    surface = map_ax.contourf(
        result["surface_lon"], result["surface_lat"], result["surface_ratio"],
        levels=24, cmap="RdBu_r", norm=norm, alpha=0.9, zorder=2,
    )
    map_ax.contour(
        result["surface_lon"], result["surface_lat"], result["surface_ratio"],
        levels=[SUPPORT_THRESHOLD], colors="#7f1d1d", linewidths=1.8, zorder=3,
    )
    map_ax.scatter(
        query_lon[false_support], query_lat[false_support], s=72, facecolor="none",
        edgecolor="#7f1d1d", linewidth=1.8, zorder=4,
    )
    reference_lat = float(result["anchor_lat"][0])
    reference_lon = float(result["anchor_lon"][0])
    map_ax.scatter(
        [reference_lon], [reference_lat], marker="*", s=150, facecolor="#111827",
        edgecolor="white", linewidth=0.7, zorder=5,
    )
    map_ax.annotate(
        "single prior used by old code",
        (reference_lon, reference_lat), xytext=(reference_lon + 9, reference_lat + 12),
        arrowprops={"arrowstyle": "->", "lw": 0.9}, fontsize=8.5,
    )
    map_ax.text(
        0.02, 0.97,
        f"{int(false_support.sum())} of {len(query_lat)} diagnostic cells falsely cross 0.9",
        transform=map_ax.transAxes, va="top", fontsize=9,
        bbox={"boxstyle": "round,pad=0.35", "facecolor": "white", "alpha": 0.9, "edgecolor": "#7f1d1d"},
    )
    map_ax.set(
        xlim=(-35, 82), ylim=(-42, 52), xlabel="longitude", ylabel="latitude",
        title="Error induced by one location's prior SD",
    )
    map_ax.grid(color="white", linewidth=0.5, alpha=0.45)
    colorbar = fig.colorbar(surface, ax=map_ax, shrink=0.82, pad=0.025)
    colorbar.set_label("local prior SD / single-location prior SD")
    colorbar.set_ticks([0.86, 0.9, 0.95, 1.0, 1.05, 1.1, 1.13])

    order = np.argsort(scalar_ratio)
    ranked = scalar_ratio[order]
    ranks = np.arange(1, len(ranked) + 1)
    diagnostic_ax.axvline(
        SUPPORT_THRESHOLD, color="#7f1d1d", linestyle="--", linewidth=1.4,
        label="support threshold (0.9)",
    )
    diagnostic_ax.axvline(1.0, color="#047857", linewidth=2.0, label="correct ratio = 1.0")
    diagnostic_ax.scatter(
        ranked, ranks, c=np.where(ranked < SUPPORT_THRESHOLD, "#7f1d1d", "#2563eb"),
        s=22, linewidth=0, label="old ratio at 77 query cells", zorder=3,
    )
    diagnostic_ax.annotate(
        "false support calls", xy=(ranked[0], 1), xytext=(0.925, 12),
        arrowprops={"arrowstyle": "->", "lw": 0.9, "color": "#7f1d1d"},
        color="#7f1d1d", fontsize=9,
    )
    diagnostic_ax.set(
        xlabel="posterior SD / prior SD", ylabel="query cells, sorted by old score",
        ylim=(0, len(ranked) + 2), title="The correction restores the no-update invariant",
    )
    diagnostic_ax.legend(loc="lower right", fontsize=8, frameon=True)
    diagnostic_ax.grid(axis="x", color="#d1d5db", linewidth=0.6)
    fig.suptitle(
        "A single-location denominator creates a geographic normalization error",
        fontsize=13.5,
    )
    fig.text(
        0.5, 0.925,
        "Synthetic no-update control: posterior SD equals the local prior SD everywhere; "
        "no populations or observations",
        ha="center", fontsize=9.5, color="#374151",
    )
    fig.subplots_adjust(left=0.065, right=0.98, bottom=0.12, top=0.84, wspace=0.23)
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
