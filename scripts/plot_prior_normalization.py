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
from matplotlib.colors import ListedColormap, TwoSlopeNorm  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

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


def _from_unit_sphere(points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return latitude/longitude for plotting the actual inducing locations."""
    latitude = np.degrees(np.arcsin(np.clip(points[:, 2], -1.0, 1.0)))
    longitude = np.degrees(np.arctan2(points[:, 1], points[:, 0]))
    return latitude, longitude


def compute_counterexample() -> dict[str, np.ndarray | float]:
    """Return the fully authored fixed-geometry no-update counterexample from issue #266."""
    anchor_lon_grid, anchor_lat_grid = np.meshgrid(
        np.arange(-20.0, 69.0, 8.0), np.arange(-30.0, 41.0, 10.0)
    )
    anchor_lat, anchor_lon = anchor_lat_grid.ravel(), anchor_lon_grid.ravel()
    inducing = h3_inducing_points(anchor_lat, anchor_lon, 16, reach_km=1500.0)
    inducing_lat, inducing_lon = _from_unit_sphere(inducing)
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
        "inducing_lat": inducing_lat,
        "inducing_lon": inducing_lon,
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
    """Map the denominator error against its actual synthetic inducing geometry."""
    result = compute_counterexample()
    query_lat = result["query_lat"]
    query_lon = result["query_lon"]
    scalar_ratio = result["scalar_ratio"]
    false_support = scalar_ratio < SUPPORT_THRESHOLD
    fig, (old_ax, local_ax, locator_ax) = plt.subplots(
        1, 3, figsize=(16.2, 5.5),
        gridspec_kw={"width_ratios": (1.0, 1.0, 0.78)},
    )
    norm = TwoSlopeNorm(
        vmin=float(np.min(result["surface_ratio"])),
        vcenter=1.0,
        vmax=float(np.max(result["surface_ratio"])),
    )
    for axis in (old_ax, local_ax):
        axis.set_facecolor("#eceff1")
        draw_countries(axis, color="#a7afb8", linewidth=0.45)
        axis.set(xlim=(-25, 73), ylim=(-35, 45), xlabel="longitude")
        axis.grid(color="white", linewidth=0.45, alpha=0.4)

    surface = old_ax.contourf(
        result["surface_lon"], result["surface_lat"], result["surface_ratio"],
        levels=24, cmap="RdBu_r", norm=norm, alpha=0.88, zorder=2,
    )
    old_ax.contour(
        result["surface_lon"], result["surface_lat"], result["surface_ratio"],
        levels=[SUPPORT_THRESHOLD], colors="#7f1d1d", linewidths=1.8, zorder=3,
    )
    old_ax.scatter(
        result["inducing_lon"], result["inducing_lat"], s=24,
        facecolor="white", edgecolor="#111827", linewidth=0.8, zorder=4,
        label="16 computational inducing locations",
    )
    old_ax.scatter(
        query_lon[false_support], query_lat[false_support], s=72, facecolor="none",
        edgecolor="#7f1d1d", linewidth=1.8, zorder=4,
        label="2 false support cells",
    )
    reference_lat = float(result["anchor_lat"][0])
    reference_lon = float(result["anchor_lon"][0])
    old_ax.scatter(
        [reference_lon], [reference_lat], marker="*", s=150, facecolor="#111827",
        edgecolor="white", linewidth=0.7, zorder=5, label="old denominator location",
    )
    old_ax.text(
        0.02, 0.97,
        "Color follows inducing-basis coverage\n"
        f"{int(false_support.sum())}/{len(query_lat)} query cells falsely cross 0.9",
        transform=old_ax.transAxes, va="top", fontsize=8.5,
        bbox={"boxstyle": "round,pad=0.35", "facecolor": "white", "alpha": 0.9, "edgecolor": "#7f1d1d"},
    )
    old_ax.set(
        ylabel="latitude",
        title="Old: one location supplies every denominator",
    )
    old_ax.legend(loc="upper right", fontsize=7.2, frameon=True)
    colorbar = fig.colorbar(surface, ax=old_ax, shrink=0.78, pad=0.025)
    colorbar.set_label("posterior SD / old scalar prior SD", fontsize=8.5)
    colorbar.set_ticks([0.86, 0.9, 0.95, 1.0, 1.05, 1.1, 1.13])

    local_ax.contourf(
        result["surface_lon"], result["surface_lat"],
        np.ones_like(result["surface_ratio"]), levels=[0.5, 1.5],
        cmap=ListedColormap(["#d1fae5"]), zorder=2,
    )
    local_ax.scatter(
        result["inducing_lon"], result["inducing_lat"], s=20,
        facecolor="white", edgecolor="#6b7280", linewidth=0.7, zorder=3,
    )
    local_ax.text(
        0.5, 0.52, "posterior SD / local prior SD\n= 1.0 everywhere",
        transform=local_ax.transAxes, ha="center", va="center", fontsize=12,
        color="#065f46", weight="bold",
    )
    local_ax.text(
        0.02, 0.97, "77/77 query cells remain prior-dominated",
        transform=local_ax.transAxes, va="top", fontsize=8.5,
        bbox={"boxstyle": "round,pad=0.35", "facecolor": "white", "alpha": 0.9,
              "edgecolor": "#047857"},
    )
    local_ax.set(title="Correct: each location uses its own prior SD")

    locator_ax.set_facecolor("#f8fafc")
    draw_countries(locator_ax, color="#9aa4af", linewidth=0.42)
    locator_ax.add_patch(
        Rectangle((-20, -30), 88, 70, facecolor="#fef3c7", edgecolor="#92400e",
                  linewidth=1.3, alpha=0.65, zorder=2)
    )
    locator_ax.scatter(
        result["controls"][:, 1], result["controls"][:, 0], s=42,
        facecolor="white", edgecolor="#475569", linewidth=1.2, zorder=3,
    )
    for index, (latitude, longitude) in enumerate(result["controls"], start=1):
        horizontal = "right" if longitude > 0 else "left"
        x_offset = -5 if longitude > 0 else 5
        y_offset = -8 if latitude > 0 else 6
        locator_ax.annotate(
            f"U{index}: unknown", (longitude, latitude), xytext=(x_offset, y_offset),
            textcoords="offset points", ha=horizontal, fontsize=7.2, color="#334155",
        )
    locator_ax.scatter(
        [reference_lon], [reference_lat], marker="*", s=90,
        facecolor="#111827", edgecolor="white", linewidth=0.6, zorder=4,
    )
    locator_ax.set(
        xlim=(-180, 180), ylim=(-90, 90), xlabel="longitude", ylabel="latitude",
        title="Earth locator and far controls\n(country outlines are orientation only)",
    )
    locator_ax.set_xticks([-180, -90, 0, 90, 180])
    locator_ax.set_yticks([-90, -45, 0, 45, 90])
    locator_ax.grid(color="white", linewidth=0.5)
    fig.suptitle(
        "Synthetic no-update test: basis geometry must not look like learning",
        fontsize=13.5,
    )
    fig.text(
        0.5, 0.91,
        "Posterior SD equals local prior SD everywhere. The field follows computational "
        "inducing coverage, not population or political geography.",
        ha="center", fontsize=9.2, color="#374151",
    )
    fig.subplots_adjust(left=0.055, right=0.985, bottom=0.12, top=0.82, wspace=0.24)
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
