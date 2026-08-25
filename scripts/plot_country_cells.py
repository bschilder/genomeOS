"""Render the H3 → country assignment the national rollup depends on (design §9, §10, §11).

The national AS/SS totals golden test 1 is scored on are sums of per-cell burden *inside a
country boundary* (#94), and the admin choropleth (#61) aggregates the same way. Both rest
entirely on which country each H3 cell belongs to, and that assignment is invisible in the
numbers: a mis-assigned cell produces a plausible national total, not an error.

    python scripts/plot_country_cells.py --out docs/figures/h3_country_assignment.png

Two panels, because the assignment has two failure modes and they look nothing alike:

1. **Identity** — cells coloured by the country they were assigned to. This is where a wrong
   answer is visible by eye: an enclave swallowed by its neighbour (Lesotho), a dependency
   folded into a metropolitan feature (French Guiana inside France), a de facto territory
   assigned or not (Somaliland, N. Cyprus).
2. **Support** — cells coloured by how many cells their country got at all. A national total
   resting on two cells is not wrong, but it is a different kind of number from one resting on
   two thousand, and §10's honesty requirement is that the difference is visible rather than
   inferred. Countries with **no** cell at this resolution get no estimate at all; they are
   listed on the figure rather than left to be discovered downstream.

Drawn on H3 cells rather than a lat/lon mesh, for the same reason `plot_surface.py` is: the
model, the artifacts and the rollup all live on the geodesic tessellation, and a rectangular
mesh reintroduces the area distortion at the rendering step.
"""

from __future__ import annotations

import argparse
import textwrap
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.collections import PolyCollection  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

from genomeos.geo.countries import assign_countries  # noqa: E402
from genomeos.reference.piel2013 import national_estimates  # noqa: E402
from genomeos.viz.basemap import draw_countries, h3_polygons  # noqa: E402

WATER = "white"
# The no-claim colour, matching plot_surface.py: a cell in no country is drawn, not omitted.
UNASSIGNED = "#e3e6ea"
# Qualitative, so neighbouring countries are separable; identity has no order to encode.
IDENTITY_CMAP = "tab20"
# Sequential and perceptually uniform for the count panel, dark-to-light low-to-high.
SUPPORT_CMAP = "viridis"


def _cells(resolution: int) -> list[str]:
    import h3

    return [
        child
        for base in h3.get_res0_cells()
        for child in h3.cell_to_children(base, resolution)
    ]


def _panel(ax, polygons, colours, *, title, legend=None):
    ax.set_facecolor(WATER)
    ax.add_collection(
        PolyCollection(polygons, facecolors=colours, edgecolors="face", linewidths=0.0, zorder=1)
    )
    draw_countries(ax, color="#3d444d", linewidth=0.3, zorder=2)
    ax.set_xlim(-180, 180)
    ax.set_ylim(-60, 84)
    ax.set_aspect("equal")
    ax.set_title(title, loc="left", fontsize=11)
    if legend:
        ax.legend(handles=legend, loc="lower left", fontsize=8, framealpha=0.9)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--h3-res", type=int, default=4, help="H3 resolution to assign and draw")
    ap.add_argument("--dpi", type=int, default=140)
    args = ap.parse_args()

    cells = _cells(args.h3_res)
    assigned = assign_countries(cells)
    iso3 = assigned["iso3"].to_numpy(dtype=object)
    print(
        f"H3 res {args.h3_res}: {len(cells):,} cells, "
        f"{int(assigned['iso3'].notna().sum()):,} inside a country, "
        f"{assigned['iso3'].nunique()} countries"
    )

    polygons, kept = h3_polygons(cells)
    iso3 = iso3[kept]
    print(f"{len(polygons):,} drawable (antimeridian-crossing cells dropped)")

    counts = assigned["iso3"].value_counts()
    codes = sorted(counts.index)
    # Deterministic colour per country, cycling the qualitative palette (§5: same figure every
    # run). Adjacent countries can draw the same colour; the outlines keep them separable.
    palette = plt.get_cmap(IDENTITY_CMAP)
    identity = np.array(
        [
            palette(codes.index(code) % palette.N) if isinstance(code, str) else
            matplotlib.colors.to_rgba(UNASSIGNED)
            for code in iso3
        ]
    )

    support = np.array(
        [counts[code] if isinstance(code, str) else np.nan for code in iso3], dtype=float
    )
    log_support = np.log10(support)

    published = national_estimates()
    covered = set(codes)
    missing = published[~published["iso3"].isin(covered)]
    share = missing["ss_neonates_per_year"].sum() / published["ss_neonates_per_year"].sum()

    fig, axes = plt.subplots(2, 1, figsize=(13, 9), constrained_layout=True)
    _panel(
        axes[0],
        polygons,
        identity,
        title=(
            f"H3 res-{args.h3_res} cells by assigned country — "
            f"{assigned['iso3'].nunique()} countries, "
            f"{int(assigned['iso3'].isna().sum()):,} cells in no country"
        ),
        legend=[Patch(facecolor=UNASSIGNED, label="no country (ocean, or absent from 1:110m)")],
    )

    ax = axes[1]
    ax.set_facecolor(WATER)
    ax.add_collection(
        PolyCollection(
            [polygons[i] for i in np.flatnonzero(np.isnan(log_support))],
            facecolors=UNASSIGNED, edgecolors="face", linewidths=0.0, zorder=1,
        )
    )
    drawn = np.flatnonzero(~np.isnan(log_support))
    mesh = PolyCollection(
        [polygons[i] for i in drawn],
        array=log_support[drawn], cmap=SUPPORT_CMAP, edgecolors="face", linewidths=0.0, zorder=1,
    )
    ax.add_collection(mesh)
    draw_countries(ax, color="#3d444d", linewidth=0.3, zorder=2)
    ax.set_xlim(-180, 180)
    ax.set_ylim(-60, 84)
    ax.set_aspect("equal")
    ax.set_title(
        "How many cells each country's national total rests on (log10) — dark is few",
        loc="left", fontsize=11,
    )
    plt.colorbar(mesh, ax=ax, label=f"log10 res-{args.h3_res} cells in the country", shrink=0.72)
    ax.text(
        -178, -57,
        f"{len(missing)} of {len(published)} published countries receive no cell at this "
        f"resolution and can produce no\nestimate ({share:.2%} of published SS neonates): "
        + textwrap.fill(", ".join(missing["iso3"]), width=96),
        fontsize=7.5, va="bottom", zorder=6,
        bbox={"facecolor": "white", "edgecolor": "#8b949e", "boxstyle": "round,pad=0.4"},
    )

    fig.suptitle(
        "Country assignment for the national burden rollup — Natural Earth 1:110m, "
        "cell centre in polygon",
        fontsize=13,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.out, dpi=args.dpi, facecolor="white")
    print(f"wrote {args.out}")
    print(
        f"{len(missing)} published countries with no cell ({share:.2%} of published SS "
        f"neonates): {', '.join(missing['iso3'])}"
    )


if __name__ == "__main__":
    main()
