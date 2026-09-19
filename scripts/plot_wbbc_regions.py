"""Derive and plot WBBC regional support discs (Atlas design §§4, 6; issue #325).

Usage:
    python scripts/plot_wbbc_regions.py \
      --natural-earth /path/to/ne_10m_admin_1_states_provinces.geojson \
      --out-tsv docs/research/wbbc-regions-2026-09-17.tsv \
      --out docs/figures/wbbc-regions-2026-09-17.png

The pinned Natural Earth v5.1.1 file is public domain.  Its SHA-256 is checked before any
derivation.  Region membership comes from Cong et al. 2022 Supplementary Figure 1.  A region's
coordinate is the centre of a minimum covering great-circle disc over all member-province boundary
vertices; its uncertainty radius is rounded upward to the next 25 km.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Patch

EARTH_RADIUS_KM = 6371.0088
NATURAL_EARTH_SHA256 = "22d0e3ad85eb3e27f17cabf8ba2d50e554fbc27a87796ff891d958185da62fb5"
PROVENANCE = (
    "doi:10.1038/s41467-022-30526-x;"
    "natural-earth:v5.1.1:ne_10m_admin_1_states_provinces"
)
REGIONS = {
    "North": (
        "Gansu",
        "Hebei",
        "Heilongjiang",
        "Henan",
        "Inner Mongolia",
        "Jilin",
        "Liaoning",
        "Ningxia",
        "Qinghai",
        "Shaanxi",
        "Shandong",
        "Shanxi",
        "Tianjin",
    ),
    "Central": ("Anhui", "Jiangsu"),
    "South": (
        "Chongqing",
        "Fujian",
        "Guizhou",
        "Hubei",
        "Hunan",
        "Jiangxi",
        "Sichuan",
        "Yunnan",
        "Zhejiang",
    ),
    "Lingnan": ("Guangxi", "Guangdong", "Hainan"),
}
REGIONAL_AN = {"North": 448, "Central": 100, "South": 8070, "Lingnan": 126}
COLORS = {
    "North": "#4C78A8",
    "Central": "#F58518",
    "South": "#54A24B",
    "Lingnan": "#B279A2",
}


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _rings(geometry: dict[str, Any]) -> list[list[list[float]]]:
    if geometry["type"] == "Polygon":
        return geometry["coordinates"]
    if geometry["type"] == "MultiPolygon":
        return [ring for polygon in geometry["coordinates"] for ring in polygon]
    raise ValueError(f"unsupported Natural Earth geometry: {geometry['type']!r}")


def _points(feature: dict[str, Any]) -> np.ndarray:
    return np.asarray(
        [coordinate[:2] for ring in _rings(feature["geometry"]) for coordinate in ring],
        dtype=float,
    )


def _maximum_distances(centres: np.ndarray, points: np.ndarray) -> np.ndarray:
    centre_lon = np.radians(centres[:, 0])[:, None]
    centre_lat = np.radians(centres[:, 1])[:, None]
    point_lon = np.radians(points[:, 0])[None, :]
    point_lat = np.radians(points[:, 1])[None, :]
    delta_lon = point_lon - centre_lon
    delta_lat = point_lat - centre_lat
    haversine = (
        np.sin(delta_lat / 2.0) ** 2
        + np.cos(centre_lat) * np.cos(point_lat) * np.sin(delta_lon / 2.0) ** 2
    )
    distances = 2.0 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(np.clip(haversine, 0.0, 1.0)))
    return distances.max(axis=1)


def _nelder_mead(points: np.ndarray, start: np.ndarray) -> tuple[np.ndarray, float]:
    """Two-dimensional deterministic minimax search without an extra plotting dependency."""
    extent = np.maximum(points.max(axis=0) - points.min(axis=0), 0.1)
    simplex = np.asarray([start, start + [0.05 * extent[0], 0.0], start + [0.0, 0.05 * extent[1]]])
    values = _maximum_distances(simplex, points)
    for _ in range(1000):
        order = np.argsort(values)
        simplex = simplex[order]
        values = values[order]
        if np.abs(simplex[1:] - simplex[0]).max() < 1e-9:
            break
        centroid = simplex[:2].mean(axis=0)
        reflected = 2.0 * centroid - simplex[2]
        reflected_value = float(_maximum_distances(reflected[None, :], points)[0])
        if values[0] <= reflected_value < values[1]:
            simplex[2], values[2] = reflected, reflected_value
            continue
        if reflected_value < values[0]:
            expanded = centroid + 2.0 * (reflected - centroid)
            expanded_value = float(_maximum_distances(expanded[None, :], points)[0])
            if expanded_value < reflected_value:
                simplex[2], values[2] = expanded, expanded_value
            else:
                simplex[2], values[2] = reflected, reflected_value
            continue
        if reflected_value < values[2]:
            contracted = centroid + 0.5 * (reflected - centroid)
            threshold = reflected_value
        else:
            contracted = centroid + 0.5 * (simplex[2] - centroid)
            threshold = values[2]
        contracted_value = float(_maximum_distances(contracted[None, :], points)[0])
        if contracted_value < threshold:
            simplex[2], values[2] = contracted, contracted_value
            continue
        simplex[1:] = simplex[0] + 0.5 * (simplex[1:] - simplex[0])
        values[1:] = _maximum_distances(simplex[1:], points)
    best = int(values.argmin())
    return simplex[best], float(values[best])


def minimum_covering_disc(points: np.ndarray) -> tuple[float, float, float]:
    """Return a deterministic minimax great-circle centre and its covering radius."""
    points = np.asarray(points, dtype=float)
    if points.ndim != 2 or points.shape[1] != 2 or len(points) == 0:
        raise ValueError("points must be a non-empty (n, 2) longitude/latitude array")
    if not np.isfinite(points).all():
        raise ValueError("points must be finite")
    starts = (
        points.mean(axis=0),
        (points.min(axis=0) + points.max(axis=0)) / 2.0,
    )
    centre, radius = min(
        (_nelder_mead(points, start) for start in starts), key=lambda result: result[1]
    )
    return float(centre[0]), float(centre[1]), radius


def round_covering_radius(radius_km: float) -> float:
    """Round upward to a reviewable 25 km support without shrinking an exact multiple."""
    if not math.isfinite(radius_km) or radius_km <= 0:
        raise ValueError("radius must be finite and positive")
    return float(math.ceil((radius_km - 1e-9) / 25.0) * 25)


def _load_china(path: Path) -> dict[str, dict[str, Any]]:
    actual = _digest(path)
    if actual != NATURAL_EARTH_SHA256:
        raise ValueError(
            f"{path}: Natural Earth SHA-256 {actual} does not match pinned {NATURAL_EARTH_SHA256}"
        )
    payload = json.loads(path.read_text(encoding="utf-8"))
    features = {
        feature["properties"]["name_en"]: feature
        for feature in payload["features"]
        if feature["properties"].get("adm0_a3") == "CHN"
        and feature["properties"].get("name_en")
    }
    required = set().union(*map(set, REGIONS.values()))
    missing = sorted(required - set(features))
    if missing:
        raise ValueError(f"Natural Earth is missing WBBC member divisions: {missing}")
    return features


def derive_regions(features: dict[str, dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for region, members in REGIONS.items():
        points = np.concatenate([_points(features[name]) for name in members])
        lon, lat, measured_radius = minimum_covering_disc(points)
        rows.append(
            {
                "region": region,
                "latitude": round(lat, 6),
                "longitude": round(lon, 6),
                "uncertainty_radius_km": round_covering_radius(measured_radius),
                "member_divisions": "|".join(members),
                "provenance": PROVENANCE,
                "measured_covering_radius_km": measured_radius,
            }
        )
    return pd.DataFrame(rows)


def _circle(lon: float, lat: float, radius_km: float) -> tuple[np.ndarray, np.ndarray]:
    bearings = np.linspace(0.0, 2.0 * np.pi, 361)
    angular = radius_km / EARTH_RADIUS_KM
    lat1 = math.radians(lat)
    lon1 = math.radians(lon)
    lat2 = np.arcsin(
        math.sin(lat1) * math.cos(angular)
        + math.cos(lat1) * math.sin(angular) * np.cos(bearings)
    )
    lon2 = lon1 + np.arctan2(
        np.sin(bearings) * math.sin(angular) * math.cos(lat1),
        math.cos(angular) - math.sin(lat1) * np.sin(lat2),
    )
    return np.degrees(lon2), np.degrees(lat2)


def plot_regions(
    features: dict[str, dict[str, Any]], regions: pd.DataFrame, out: Path
) -> None:
    membership = {
        division: region for region, divisions in REGIONS.items() for division in divisions
    }
    fig, ax = plt.subplots(figsize=(12.5, 8.2))
    for name, feature in features.items():
        region = membership.get(name)
        face = COLORS[region] if region else "#ECEFF1"
        for ring in _rings(feature["geometry"]):
            coordinates = np.asarray(ring)
            ax.fill(
                coordinates[:, 0],
                coordinates[:, 1],
                facecolor=face,
                edgecolor="white",
                linewidth=0.35,
                alpha=0.84 if region else 0.45,
                zorder=1,
            )
    for row in regions.itertuples(index=False):
        circle_lon, circle_lat = _circle(
            row.longitude, row.latitude, row.uncertainty_radius_km
        )
        color = COLORS[row.region]
        ax.plot(circle_lon, circle_lat, color=color, linewidth=1.5, linestyle="--", zorder=3)
        ax.scatter(
            row.longitude,
            row.latitude,
            s=58,
            marker="o",
            facecolor="white",
            edgecolor=color,
            linewidth=2,
            zorder=4,
        )
        ax.annotate(
            row.region,
            (row.longitude, row.latitude),
            xytext=(5, 6),
            textcoords="offset points",
            fontsize=10,
            fontweight="bold",
            color="#17212B",
            zorder=5,
        )
    handles = [
        Patch(
            facecolor=COLORS[region],
            edgecolor="none",
            label=(
                f"{region}: AN={REGIONAL_AN[region]:,}; radius="
                f"{int(regions.set_index('region').loc[region, 'uncertainty_radius_km']):,} km"
            ),
        )
        for region in REGIONS
    ]
    ax.legend(handles=handles, loc="lower left", frameon=True, title="Source strata")
    ax.set(
        xlim=(68, 144),
        ylim=(14, 62),
        xlabel="Longitude",
        ylabel="Latitude",
        title="WBBC regional allele counts have broad, explicit geographic support",
    )
    ax.text(
        0.01,
        0.985,
        "Measured source strata only — no fitted surface",
        transform=ax.transAxes,
        va="top",
        fontsize=9,
        color="#44515C",
    )
    ax.set_aspect(1.0 / math.cos(math.radians(35.0)))
    ax.grid(color="#D8DEE4", linewidth=0.5, alpha=0.55)
    fig.subplots_adjust(left=0.07, right=0.985, top=0.92, bottom=0.13)
    fig.text(
        0.5,
        0.035,
        "Filled provinces are the source-defined strata. Open circles are inferred disc centres; "
        "dashed lines are province-covering uncertainty radii. Natural Earth v5.1.1 "
        "(public domain).",
        ha="center",
        fontsize=9,
        color="#44515C",
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=180, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--natural-earth", type=Path, required=True)
    parser.add_argument("--out-tsv", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    features = _load_china(args.natural_earth)
    regions = derive_regions(features)
    args.out_tsv.parent.mkdir(parents=True, exist_ok=True)
    regions.drop(columns="measured_covering_radius_km").to_csv(
        args.out_tsv, sep="\t", index=False, float_format="%.6f"
    )
    plot_regions(features, regions, args.out)
    for row in regions.itertuples(index=False):
        print(
            f"{row.region}: ({row.latitude:.6f}, {row.longitude:.6f}), "
            f"measured={row.measured_covering_radius_km:.3f} km, "
            f"published={row.uncertainty_radius_km:.0f} km"
        )


if __name__ == "__main__":
    main()
