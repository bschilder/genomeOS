"""Plot the evidence, inferred surface and national HbS parity residuals (design §4, §8).

The four panels keep measured observations and inferred values separate, then paint burden
errors onto the countries that own them. Inputs are the private, checksum-recorded acceptance
artifacts; the resulting review figure and receipt are safe to commit independently of the large
posterior draw matrix.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.collections import PolyCollection  # noqa: E402
from matplotlib.colors import LogNorm, TwoSlopeNorm  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

from genomeos.geo.countries import feature_iso3  # noqa: E402
from genomeos.viz.basemap import draw_countries, h3_polygons, load_countries  # noqa: E402

LAND = "#e4e7eb"
WATER = "white"
ZERO_REFERENCE = "#7a5195"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def style_map(ax, title: str) -> None:
    ax.set_facecolor(WATER)
    ax.set_xlim(-180, 180)
    ax.set_ylim(-60, 84)
    ax.set_aspect("equal")
    ax.set_xticks(np.arange(-180, 181, 60))
    ax.set_yticks(np.arange(-60, 61, 30))
    ax.grid(color="#edf0f2", linewidth=0.5, zorder=0)
    ax.set_title(title, loc="left", fontsize=11, fontweight="bold")
    ax.set_xlabel("longitude")
    ax.set_ylabel("latitude")


def exterior_polygons(feature: dict) -> list[list[list[float]]]:
    geometry = feature["geometry"]
    polygons = (
        [geometry["coordinates"]]
        if geometry["type"] == "Polygon"
        else geometry["coordinates"]
    )
    return [polygon[0] for polygon in polygons if polygon and len(polygon[0]) >= 3]


def draw_observations(ax, observations: pd.DataFrame) -> None:
    frequency = (observations["ac"] / observations["an"]).to_numpy(dtype=float)
    sizes = 7.0 + 45.0 * np.sqrt(
        observations["an"].to_numpy(dtype=float) / observations["an"].max()
    )
    positive = frequency > 0
    norm = LogNorm(vmin=1e-4, vmax=0.2, clip=True)
    scatter = ax.scatter(
        observations.loc[positive, "lon"],
        observations.loc[positive, "lat"],
        c=frequency[positive],
        s=sizes[positive],
        cmap="viridis",
        norm=norm,
        edgecolor="#11151a",
        linewidth=0.25,
        alpha=0.82,
        zorder=3,
        rasterized=True,
    )
    ax.scatter(
        observations.loc[~positive, "lon"],
        observations.loc[~positive, "lat"],
        s=sizes[~positive],
        facecolor="white",
        edgecolor="#1769aa",
        linewidth=0.7,
        zorder=4,
        rasterized=True,
    )
    draw_countries(ax, color="#8b949e", linewidth=0.45, zorder=2)
    bar = plt.colorbar(scatter, ax=ax, shrink=0.72, pad=0.015)
    bar.set_label("measured HbS allele frequency")
    bar.set_ticks([1e-4, 1e-3, 1e-2, 1e-1])
    bar.set_ticklabels(["0.01%", "0.1%", "1%", "10%"])
    ax.legend(
        handles=[
            Patch(facecolor="white", edgecolor="#1769aa", label="measured zero (AC = 0)"),
            Patch(facecolor="#35b779", edgecolor="#11151a", label="measured presence"),
        ],
        loc="lower left",
        fontsize=8,
        framealpha=0.95,
    )


def draw_surface(ax, cells: pd.DataFrame) -> None:
    polygons, kept = h3_polygons(cells["h3_index"].tolist())
    kept = np.asarray(kept, dtype=int)
    shown = cells.iloc[kept].reset_index(drop=True)
    ax.add_collection(
        PolyCollection(
            polygons,
            facecolors=LAND,
            edgecolors="face",
            linewidths=0,
            zorder=1,
            rasterized=True,
        )
    )
    supported = shown["support"].isin(["observed", "interpolated"]).to_numpy()
    mesh = PolyCollection(
        [polygons[index] for index in np.flatnonzero(supported)],
        array=shown.loc[supported, "post_median"].to_numpy(dtype=float),
        cmap="viridis",
        norm=LogNorm(vmin=1e-4, vmax=0.2, clip=True),
        edgecolors="face",
        linewidths=0,
        zorder=2,
        rasterized=True,
    )
    ax.add_collection(mesh)
    draw_countries(ax, color="#737b84", linewidth=0.35, zorder=3)
    bar = plt.colorbar(mesh, ax=ax, shrink=0.72, pad=0.015)
    bar.set_label("posterior median HbS allele frequency")
    bar.set_ticks([1e-4, 1e-3, 1e-2, 1e-1])
    bar.set_ticklabels(["0.01%", "0.1%", "1%", "10%"])
    counts = cells["support"].value_counts()
    ax.legend(
        handles=[
            Patch(
                facecolor=LAND,
                edgecolor="#737b84",
                label=f"unknown — no surface claim ({int(counts.get('unknown', 0)):,} cells)",
            ),
            Patch(
                facecolor="#35b779",
                edgecolor="none",
                label=(
                    "supported inference "
                    f"({int(counts.get('observed', 0) + counts.get('interpolated', 0)):,} cells)"
                ),
            ),
        ],
        loc="lower left",
        fontsize=8,
        framealpha=0.95,
    )


def draw_country_ratios(ax, parity: pd.DataFrame, metric: str) -> None:
    indexed = parity.set_index("iso3")
    norm = TwoSlopeNorm(vmin=-4.0, vcenter=0.0, vmax=4.0)
    cmap = plt.get_cmap("RdBu_r")
    polygons: list = []
    colors: list = []
    no_claim = zero_reference = 0
    for feature in load_countries():
        iso3 = feature_iso3(feature)
        row = indexed.loc[iso3] if iso3 in indexed.index else None
        if row is None or pd.isna(row["point"]):
            color = LAND
            no_claim += 1
        elif row["published_point"] == 0:
            color = ZERO_REFERENCE
            zero_reference += 1
        else:
            log_ratio = np.log2(row["point"] / row["published_point"])
            color = cmap(norm(np.clip(log_ratio, -4.0, 4.0)))
        feature_polygons = exterior_polygons(feature)
        polygons.extend(feature_polygons)
        colors.extend([color] * len(feature_polygons))
    ax.add_collection(
        PolyCollection(
            polygons,
            facecolors=colors,
            edgecolors="#ffffff",
            linewidths=0.22,
            zorder=2,
            rasterized=True,
        )
    )
    draw_countries(ax, color="#747c84", linewidth=0.32, zorder=3)
    scalar = plt.cm.ScalarMappable(norm=norm, cmap=cmap)
    bar = plt.colorbar(scalar, ax=ax, shrink=0.72, pad=0.015)
    bar.set_label(f"log2(model / Piel) for {metric}")
    bar.set_ticks([-4, -2, 0, 2, 4])
    bar.set_ticklabels(["≤1/16×", "1/4×", "1×", "4×", "≥16×"])
    ax.legend(
        handles=[
            Patch(facecolor=LAND, edgecolor="#747c84", label=f"no estimate ({no_claim} polygons)"),
            Patch(
                facecolor=ZERO_REFERENCE,
                edgecolor="#747c84",
                label=f"Piel point = 0, model > 0 ({zero_reference} polygons)",
            ),
        ],
        loc="lower left",
        fontsize=8,
        framealpha=0.95,
    )


def render(
    *,
    cells_path: Path,
    observations_path: Path,
    results_path: Path,
    ss_parity_path: Path,
    as_parity_path: Path,
    out_path: Path,
    receipt_path: Path,
) -> None:
    cells = pd.read_parquet(cells_path)
    observations = pd.read_parquet(observations_path)
    results = json.loads(results_path.read_text())
    ss = pd.read_csv(ss_parity_path)
    as_frame = pd.read_csv(as_parity_path)

    figure, axes = plt.subplots(2, 2, figsize=(17, 10.5), constrained_layout=True)
    style_map(
        axes[0, 0],
        f"A  Measured evidence — {len(observations):,} Piel-comparable surveys",
    )
    draw_observations(axes[0, 0], observations)
    style_map(axes[0, 1], "B  Inferred surface — supported cells only")
    draw_surface(axes[0, 1], cells)
    style_map(axes[1, 0], "C  HbSS national residuals — country identity is the mark")
    draw_country_ratios(axes[1, 0], ss, "HbSS births")
    style_map(axes[1, 1], "D  HbAS national residuals — diffuse low-frequency leakage")
    draw_country_ratios(axes[1, 1], as_frame, "HbAS births")

    ss_run = results["runs"]["ss_supported_only"]
    as_run = results["runs"]["as_supported_only"]
    ss_target = results["published_global"]["ss"][0]
    as_target = results["published_global"]["as"][0]
    target_year = results["denominator_alignment"]["reference_year"]
    figure.suptitle(
        f"HbS Piel-parity diagnostic: {target_year} denominator aligned, calibration still fails\n"
        f"HbSS: {ss_run['point_inside_fraction']:.1%} inside IQR, global "
        f"{ss_run['global_total'][0]:,.0f} vs {ss_target:,.0f}  |  "
        f"HbAS: {as_run['point_inside_fraction']:.1%} inside IQR, global "
        f"{as_run['global_total'][0]:,.0f} vs {as_target:,.0f}",
        fontsize=14,
        fontweight="bold",
    )
    figure.text(
        0.5,
        0.002,
        "Observations and inferred surface are shown in separate panels. Grey means no claim. "
        "Country residuals use the canonical supported-only rollup; purple is a categorical "
        "published-zero mismatch, not a ratio.",
        ha="center",
        fontsize=9,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(out_path, dpi=150, facecolor="white")
    plt.close(figure)
    receipt = {
        "artifact": "hbs-piel994-geographic-diagnostic",
        "inputs": {
            name: {"artifact": path.name, "sha256": sha256(path)}
            for name, path in {
                "cells": cells_path,
                "observations": observations_path,
                "results": results_path,
                "ss_parity": ss_parity_path,
                "as_parity": as_parity_path,
            }.items()
        },
        "executed_source_sha256": sha256(Path(__file__)),
        "output": {"path": str(out_path), "sha256": sha256(out_path)},
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    print(out_path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cells", type=Path, required=True)
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--ss-parity", type=Path, required=True)
    parser.add_argument("--as-parity", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    render(
        cells_path=args.cells,
        observations_path=args.observations,
        results_path=args.results,
        ss_parity_path=args.ss_parity,
        as_parity_path=args.as_parity,
        out_path=args.out,
        receipt_path=args.receipt or args.out.with_suffix(".receipt.json"),
    )


if __name__ == "__main__":
    main()
