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
from matplotlib.lines import Line2D  # noqa: E402

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
    anchor_lat = np.array(
        [lat for lat in range(-30, 41, 10) for _ in range(-20, 69, 8)], dtype=float
    )
    anchor_lon = np.array(
        [lon for _ in range(-30, 41, 10) for lon in range(-20, 69, 8)], dtype=float
    )
    inducing = h3_inducing_points(anchor_lat, anchor_lon, 16, reach_km=1500.0)
    query_lat = np.array(
        [lat for lat in range(-25, 36, 10) for _ in range(-16, 65, 8)], dtype=float
    )
    query_lon = np.array(
        [lon for _ in range(-25, 36, 10) for lon in range(-16, 65, 8)], dtype=float
    )
    local_sd = _conditional_frequency_sd(inducing, query_lat, query_lon)
    scalar_sd = float(_conditional_frequency_sd(inducing, anchor_lat[:1], anchor_lon[:1])[0])
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
        "controls": controls,
        "control_distance_km": control_distance,
        "control_unknown": control_distance > 2.0 * LENGTHSCALE_KM,
    }


def render(out: Path) -> Path:
    """Render the counterexample as two support maps with a shared low-to-high ratio ramp."""
    result = compute_counterexample()
    query_lat = result["query_lat"]
    query_lon = result["query_lon"]
    controls = result["controls"]
    ratios = (result["scalar_ratio"], result["local_ratio"])
    titles = ("Scalar reference: false contraction", "Matched local prior: no update")
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.8))
    norm = plt.Normalize(
        min(float(np.min(ratio)) for ratio in ratios),
        max(float(np.max(ratio)) for ratio in ratios),
    )
    for ax, ratio, title in zip(axes, ratios, titles, strict=True):
        ax.set_facecolor("#eceff1")
        draw_countries(ax, color="#a4abb3", linewidth=0.45)
        prior_dominated = ratio >= SUPPORT_THRESHOLD
        ax.scatter(
            query_lon[~prior_dominated], query_lat[~prior_dominated], c=ratio[~prior_dominated],
            cmap="viridis", norm=norm, s=38, marker="o", edgecolor="black", linewidth=0.3,
            label="interpolated (<0.9)", zorder=3,
        )
        scatter = ax.scatter(
            query_lon[prior_dominated], query_lat[prior_dominated], c=ratio[prior_dominated],
            cmap="viridis", norm=norm, s=42, marker="s", edgecolor="black", linewidth=0.3,
            label="prior dominated (≥0.9)", zorder=3,
        )
        ax.scatter(
            result["anchor_lon"], result["anchor_lat"], marker="^", s=12,
            facecolor="none", edgecolor="#667085", linewidth=0.45, zorder=2,
        )
        ax.scatter(
            controls[:, 1], controls[:, 0], marker="x", s=45, color="#4b5563",
            linewidth=1.2, label="unknown (>2ρ)", zorder=4,
        )
        for control_lat, control_lon in controls:
            ax.annotate(
                f"({control_lat:.0f}, {control_lon:.0f})",
                (control_lon, control_lat),
                xytext=(4, 4),
                textcoords="offset points",
                fontsize=6.5,
                color="#4b5563",
            )
        ax.set(xlim=(-180, 180), ylim=(-90, 90), xlabel="longitude", ylabel="latitude", title=title)
        ax.text(-174, -84, "grey background: unevaluated", fontsize=8, color="#4b5563")
        ax.grid(color="white", linewidth=0.5, alpha=0.7)
    target = (query_lat == -25) & (query_lon == 64)
    axes[0].annotate(
        f"(-25°, 64°): {result['scalar_ratio'][target].item():.6f}",
        xy=(64, -25), xytext=(82, -55), arrowprops={"arrowstyle": "->", "lw": 0.8}, fontsize=8,
    )
    legend = [
        Line2D([], [], marker="o", linestyle="none", color="black", markerfacecolor="white",
               label="interpolated support"),
        Line2D([], [], marker="s", linestyle="none", color="black", markerfacecolor="white",
               label="prior-dominated support"),
        Line2D([], [], marker="x", linestyle="none", color="#4b5563", label="unknown control"),
        Line2D([], [], marker="^", linestyle="none", color="#667085", markerfacecolor="none",
               label="synthetic geometry anchor (not measured data)"),
    ]
    fig.legend(handles=legend, loc="lower center", bbox_to_anchor=(0.45, 0.015), ncol=4, fontsize=8)
    fig.suptitle(
        "Synthetic unchanged-distribution control: local posterior SD equals local prior SD",
        fontsize=13,
    )
    fig.subplots_adjust(left=0.06, right=0.88, bottom=0.18, top=0.86, wspace=0.12)
    fig.colorbar(
        scatter,
        ax=axes,
        shrink=0.72,
        label=(
            "posterior SD / reference prior SD "
            f"(full range {norm.vmin:.3f}–{norm.vmax:.3f}, low → high)"
        ),
    )
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
