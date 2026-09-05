"""Render the synthetic literature promotion fixture for review (design §§4, 5.4, 11).

This figure proves the publication-to-P0-to-P1 wiring only. It draws one measured observation and
its registry-owned uncertainty extent, never a fitted surface. The fixture is synthetic and the
title says so; the 426 pending LCT audit proposals are not plotted as scientific observations.

    python scripts/plot_literature_fixture.py \
        --out docs/figures/literature_lct_fixture_observation.png
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from genomeos.observations.sources import publications  # noqa: E402
from genomeos.viz.basemap import draw_countries  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "literature" / "promotable"
EARTH_RADIUS_KM = 6371.0088


def _geodesic_disc(lat: float, lon: float, radius_km: float) -> tuple[np.ndarray, np.ndarray]:
    """Boundary points radius_km from one WGS84-like spherical coordinate."""
    bearings = np.linspace(0.0, 2.0 * np.pi, 361)
    angular = radius_km / EARTH_RADIUS_KM
    lat1 = np.radians(lat)
    lon1 = np.radians(lon)
    lat2 = np.arcsin(
        np.sin(lat1) * np.cos(angular)
        + np.cos(lat1) * np.sin(angular) * np.cos(bearings)
    )
    lon2 = lon1 + np.arctan2(
        np.sin(bearings) * np.sin(angular) * np.cos(lat1),
        np.cos(angular) - np.sin(lat1) * np.sin(lat2),
    )
    return np.degrees(lat2), np.degrees(lon2)


def _load_fixture():
    populations = pd.read_csv(FIXTURE / "populations.tsv", sep="\t")
    aliases = pd.read_csv(FIXTURE / "aliases.tsv", sep="\t")
    return publications.load(
        FIXTURE / "evidence.tsv",
        FIXTURE / "field_evidence.tsv",
        populations,
        aliases,
        "observations@2026-09-05.1",
    )


def plot(out: Path) -> None:
    observations, _, report = _load_fixture()
    if len(observations) != 1 or report.refusals:
        raise ValueError("review figure requires exactly one promoted fixture and no refusals")
    row = observations.iloc[0]
    frequency = row["ac"] / row["an"]
    disc_lat, disc_lon = _geodesic_disc(row["lat"], row["lon"], row["radius_km"])

    fig, ax = plt.subplots(figsize=(10, 7), constrained_layout=True)
    ax.set_facecolor("#f6f8fa")
    for lat in range(55, 76, 5):
        ax.axhline(lat, color="#e4e8ec", lw=0.6, zorder=0)
    for lon in range(0, 51, 10):
        ax.axvline(lon, color="#e4e8ec", lw=0.6, zorder=0)
    draw_countries(ax, color="#8c959f", linewidth=0.7, zorder=1)
    ax.fill(
        disc_lon,
        disc_lat,
        facecolor="#58a6ff",
        edgecolor="#0969da",
        linewidth=1.2,
        alpha=0.23,
        label=f"P0 uncertainty extent ({row['radius_km']:.0f} km; copied, not inferred)",
        zorder=2,
    )
    ax.scatter(
        [row["lon"]],
        [row["lat"]],
        s=115,
        marker="o",
        facecolor="#e85d04",
        edgecolor="#24292f",
        linewidth=0.9,
        label=f"measured fixture: AC/AN = {row['ac']}/{row['an']} ({frequency:.1%})",
        zorder=3,
    )
    ax.annotate(
        "Sami fixture\nexact P0 alias",
        (row["lon"], row["lat"]),
        xytext=(18, -34),
        textcoords="offset points",
        arrowprops={"arrowstyle": "-", "color": "#57606a"},
        fontsize=10,
    )
    ax.set_xlim(0, 50)
    ax.set_ylim(55, 76)
    ax.set_aspect("equal")
    ax.set_xlabel("longitude (WGS84)")
    ax.set_ylabel("latitude (WGS84)")
    fig.suptitle(
        "Synthetic LCT literature fixture — promotion path diagnostic, not a scientific result",
        x=0.1,
        ha="left",
        fontsize=12,
    )
    ax.set_title(
        "One P1 observation only; no interpolation or fitted surface. The 426-row pilot audit "
        "remains pending evidence.",
        loc="left",
        fontsize=9,
        color="#57606a",
        pad=8,
    )
    ax.legend(loc="lower left", framealpha=0.95)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=160, facecolor="white")
    plt.close(fig)
    print(f"wrote synthetic literature fixture map to {out}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    plot(args.out)


if __name__ == "__main__":
    main()
