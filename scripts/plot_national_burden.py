"""Render national burden totals and the coverage they rest on (design §9, §10, §11).

    python scripts/national_estimates.py --synthetic --out data/national_ss.csv
    python scripts/plot_national_burden.py --rollup data/national_ss.csv \
        --out docs/figures/national_burden.png

Two panels, following the visual language `plot_surface.py` established — white water, flat grey
land as the no-claim base, the heatmap painted only where there is a claim, `turbo` for value:

1. **The national total**, painted onto the cells it was summed from. Countries we **refused**
   are left as bare grey land, exactly as masked cells are on the surface figure, because the
   alternative is that a refusal is drawn in the same colour as an estimate of zero. Those are
   opposite statements — "we will not say" against "nobody is affected" — and a map that renders
   them alike is the failure §4 exists to prevent.
2. **The mapped population share** behind each total. A national number covering 82% of a
   country's people and one covering 99% are different claims (`burden.national`), and panel 1
   cannot show the difference. This panel is also the explanation for panel 1's grey: a country
   below the coverage threshold appears here with its coverage and there with none.

Painted on H3 cells rather than filled country polygons, because those cells *are* what the
totals were summed over — a filled polygon would imply a within-country claim the rollup never
makes, and the product renders H3 too (§6).

The `source` column of the rollup is printed in the title, so a figure made from the synthetic
demonstration inputs says so on its face.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.collections import PolyCollection  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

from genomeos.geo.countries import assign_countries  # noqa: E402
from genomeos.viz.basemap import draw_countries, h3_land_cells, h3_polygons  # noqa: E402

WATER = "white"
LAND = "#e3e6ea"
# Same reasoning as plot_surface.py: turbo keeps adjacent values apart and never approaches the
# grey no-claim base or the white water, so an estimate is never confusable with an absence.
VALUE_CMAP = "turbo"
# A different family for coverage, so a share of population is not read as a burden.
COVERAGE_CMAP = "cividis"


def _panel(ax, polygons, *, values, mask, cmap, label, title, legend_label, vmin=None, vmax=None):
    """Grey land everywhere, colour only where there is a claim, outlines on top."""
    ax.set_facecolor(WATER)
    ax.add_collection(
        PolyCollection(polygons, facecolors=LAND, edgecolors="face", linewidths=0.0, zorder=1)
    )
    keep = np.flatnonzero(~mask)
    mesh = PolyCollection(
        [polygons[i] for i in keep],
        array=values[keep], cmap=cmap, edgecolors="face", linewidths=0.0, zorder=2,
    )
    mesh.set_clim(
        float(values[keep].min()) if vmin is None else vmin,
        float(values[keep].max()) if vmax is None else vmax,
    )
    ax.add_collection(mesh)
    draw_countries(ax, color="#8b949e", linewidth=0.4, zorder=3)
    ax.set_xlim(-180, 180)
    ax.set_ylim(-60, 84)
    ax.set_aspect("equal")
    ax.set_title(title, loc="left", fontsize=11)
    ax.legend(
        handles=[Patch(facecolor=LAND, label=legend_label)],
        loc="lower left", fontsize=8, framealpha=0.9,
    )
    plt.colorbar(mesh, ax=ax, label=label, shrink=0.72)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rollup", type=Path, required=True, help="csv from national_estimates.py")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--h3-res", type=int, default=4, help="resolution to paint (not to sum)")
    ap.add_argument("--dpi", type=int, default=140)
    args = ap.parse_args()

    rollup = pd.read_csv(args.rollup)
    source = rollup["source"].iloc[0] if "source" in rollup else args.rollup.name
    metric = rollup["metric"].iloc[0] if "metric" in rollup else "burden"
    threshold = float(rollup["min_mapped_population"].iloc[0])
    print(f"{len(rollup)} countries, {int(rollup['point'].notna().sum())} estimated ({source})")

    cells = h3_land_cells(args.h3_res)
    iso3 = assign_countries(cells)["iso3"]
    polygons, kept = h3_polygons(cells)
    iso3 = iso3.iloc[kept].to_numpy(dtype=object)

    indexed = rollup.set_index("iso3")
    point = np.array(
        [indexed["point"].get(code, np.nan) if isinstance(code, str) else np.nan for code in iso3]
    )
    coverage = np.array(
        [
            indexed["mapped_population_fraction"].get(code, np.nan)
            if isinstance(code, str) else np.nan
            for code in iso3
        ]
    )

    refused = int((rollup["point"].isna()).sum())
    fig, axes = plt.subplots(2, 1, figsize=(13, 9), constrained_layout=True)
    _panel(
        axes[0],
        polygons,
        # log10 because national burdens span five orders of magnitude; monotone, so the ramp
        # still reads low-to-high, and the +1 keeps a true zero on the scale instead of at -inf.
        values=np.log10(1.0 + point),
        mask=np.isnan(point),
        cmap=VALUE_CMAP,
        label=f"log10(1 + {metric} per year)",
        title=f"National {metric}, painted on the cells it was summed from",
        legend_label=f"no claim — refused or not estimated ({refused} countries)",
        vmin=0.0,
    )
    _panel(
        axes[1],
        polygons,
        values=coverage,
        mask=np.isnan(coverage),
        cmap=COVERAGE_CMAP,
        label="mapped population share",
        title=(
            f"Share of each country's population in unmasked cells — "
            f"below {threshold:.0%} the total above is refused"
        ),
        legend_label="no coverage figure (country absent from the rollup)",
        vmin=0.0,
        vmax=1.0,
    )
    fig.suptitle(
        f"National burden rollup — {source} — {int(rollup['point'].notna().sum())} of "
        f"{len(rollup)} countries estimated",
        fontsize=13,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.out, dpi=args.dpi, facecolor="white")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
