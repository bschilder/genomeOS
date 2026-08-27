"""Render the fitted surface with its data-support mask (design §7, §11).

Two panels, because §11 makes the mean/uncertainty comparison the default view for a surface:
the posterior median, and the posterior standard deviation. Both carry the mask.

**The mask is the point of this figure.** §4's structural answer to Novembre & Stephens 2008 is
that a fitted surface must state where it does not know, so cells with no observation within 2ρ,
and cells whose posterior never moved off the prior, are left as bare grey land rather than
coloured. A version of this figure without the mask would be exactly the persuasive-but-unfounded
cline the design exists to avoid.

    python scripts/plot_surface.py --observations data/raw/map_hbs_surveys.csv \
        --out docs/figures/hbs_surface.png

Evaluated and drawn on **H3 cells**, the same geodesic tessellation §6 specifies for the product
and the same one the inducing points are placed on. An earlier version of this script used a
lat/lon `pcolormesh`, which draws rectangles whose ground area varies by a factor of two between
the equator and 60°N — reintroducing at the rendering step precisely the distortion that the
spherical kernel and the geodesic inducing grid exist to remove. The mask logic is the same
`classify_support` the pipeline uses, not a reimplementation.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.collections import PolyCollection  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

from genomeos.observations.sources import (  # noqa: E402
    afnd_frequencies,
    map_g6pd,
    map_surveys,
)
from genomeos.surfaces.fit import FitConfig, fit_surface, load_fit, save_fit  # noqa: E402
from genomeos.surfaces.mask import MaskConfig, classify_support  # noqa: E402
from genomeos.viz.basemap import draw_countries, h3_land_cells, h3_polygons  # noqa: E402

MASKED = ("unknown", "prior_dominated", "unpopulated")
# Water is white and land is a flat light grey, with the heatmap painted over the grey. The
# grey land base *is* the no-claim state, so the hatching an earlier version used to separate
# "no claim" from "zero" is no longer needed: an uncoloured cell reads as plain land, not as a
# frequency of zero. One base layer replaces the hatch layer.
WATER = "white"
LAND = "#e3e6ea"
# `turbo` rather than `coolwarm` or `jet`. Two properties matter here and they are measurable:
# adjacent-value contrast (turbo 3.6 vs coolwarm 2.2, so neighbouring frequencies stay apart),
# and distance from the two non-data colours. A *diverging* map like coolwarm passes through
# neutral grey at its midpoint and lands 0.07 from the grey land base — under the ~0.10
# just-noticeable threshold — so cells near 8% HbS became indistinguishable from "no data".
# turbo never approaches grey (0.70) or white (0.80), which is what lets the land stay light.
VALUE_CMAP = "turbo"

#: Presence markers are scaled by observed allele frequency, area-proportional, which is the
#: cartographic convention for a proportional-symbol map. The bounds are the whole design: about
#: half of all presences sit below a quarter of the maximum frequency (measured on DRB1*01:01,
#: A*02:01 and HbS alike), so without a floor most of the evidence shrinks to invisibility, and
#: without a ceiling the dense European clusters merge into one opaque mass and hide the surface
#: they are drawn on.
PRESENCE_AREA_MIN = 4.0
PRESENCE_AREA_MAX = 32.0

_LAYER_TITLE = {
    "hbs": "HbS (rs334)",
    "g6pd": "G6PD deficiency (X-linked, hemizygous males)",
}
_VALUE_LABEL = {
    "hbs": "posterior median HbS allele frequency",
    "g6pd": "posterior median G6PD-deficiency allele frequency (males)",
}
#: The source each layer is credited to in the figure caption. AFND surveys are not MAP surveys
#: and captioning them as such would misattribute the data (§4 provenance).
_LAYER_SOURCE = {"hbs": "MAP surveys", "g6pd": "MAP surveys", "afnd": "AFND populations"}


def hla_display_name(variant_id: str) -> str:
    """``hla:drb1-15-01`` -> ``HLA-DRB1*15:01``.

    AFND has 767 modelable alleles, so a hand-maintained title table is not an option; the name
    is reconstructed from the variant_id instead. Anything that is not an `hla:` id is returned
    unchanged rather than mangled.
    """
    if not variant_id.startswith("hla:"):
        return variant_id
    gene, _, fields = variant_id[len("hla:") :].partition("-")
    return f"HLA-{gene.upper()}*{fields.replace('-', ':')}" if fields else f"HLA-{gene.upper()}"
# A different family for uncertainty: two panels drawn in one palette invite reading a
# standard deviation as a frequency.
UNCERTAINTY_CMAP = "magma"


def _haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0088
    dlat, dlon = np.radians(lat2 - lat1), np.radians(lon2 - lon1)
    a = (
        np.sin(dlat / 2) ** 2
        + np.cos(np.radians(lat1)) * np.cos(np.radians(lat2)) * np.sin(dlon / 2) ** 2
    )
    return 2 * r * np.arcsin(np.sqrt(a))


def _observation_markers(ax, obs, *, area_min=PRESENCE_AREA_MIN, area_max=PRESENCE_AREA_MAX) -> list:
    """Overlay the surveys, with presence and absence as different shapes.

    Same encoding as the observations figure and as Piel et al.'s Figure 1A. On a fitted surface
    this matters more, not less: an absence survey sitting inside a warm region is the clearest
    visual signal that the model is smoothing over contrary evidence, and it disappears entirely
    if every observation is drawn as the same dot.

    Translucent white fill with an opaque dark stroke, because these markers have to stay legible
    over five different backgrounds: turbo's dark navy low end, its bright yellow middle, its dark
    red top, the light grey no-claim land, and white water. White alone vanishes on the yellow,
    the grey and the water; dark alone vanishes on the navy and the red. The fill is passed as
    RGBA rather than through `alpha=` so the stroke stays fully opaque instead of fading with it.

    The stroke carries more weight than it looks like it should. Over open water the white fill
    contributes nothing at all, so the stroke is the entire marker — and that is the case for the
    island surveys of maritime Southeast Asia, whose land cells are too small to render beneath
    them. A hairline stroke loses precisely the points that have no other visual support.
    """
    absent = (obs["ac"] == 0).to_numpy()
    fill = (1.0, 1.0, 1.0, 0.75)
    frequency = (obs["ac"] / obs["an"]).to_numpy(dtype=float)
    present = ~absent

    lon = obs["lon"].to_numpy()
    lat = obs["lat"].to_numpy()
    handles: list = []
    if present.any():
        f_present = frequency[present]
        f_max = float(f_present.max())
        span = area_max - area_min
        area = area_min + span * (f_present / f_max if f_max > 0 else 0.0)
        # Largest first, so a small marker inside a dense cluster lands on top of its big
        # neighbours instead of underneath them and stays findable.
        order = np.argsort(-area)
        ax.scatter(
            lon[present][order], lat[present][order], s=area[order], marker="o",
            facecolor=[fill], edgecolor="#11151a", linewidth=0.4, zorder=4,
        )
        # Size is meaningless without exemplars, so the legend carries three real frequencies
        # rather than a single "presence" swatch at some arbitrary size.
        from matplotlib.lines import Line2D

        exemplars = [f_max * 0.15, f_max * 0.5, f_max]
        for value in exemplars:
            a = area_min + span * (value / f_max)
            handles.append(
                Line2D(
                    [], [], marker="o", linestyle="none", markersize=float(np.sqrt(a)),
                    markerfacecolor=fill, markeredgecolor="#11151a", markeredgewidth=0.4,
                    label=f"presence — {value:.1%}",
                )
            )
        handles[-1].set_label(f"presence — {f_max:.1%} (max of {int(present.sum())})")
    ax.scatter(
        lon[absent], lat[absent], s=19, marker="^",
        facecolor=[fill], edgecolor="#11151a", linewidth=0.55, zorder=5,
        label=f"absence — AC=0 ({int(absent.sum())})",
    )
    return handles


def _panel(ax, polygons, values, masked, obs, *, cmap, label, title, vmax=None,
           area_min=PRESENCE_AREA_MIN, area_max=PRESENCE_AREA_MAX):
    """Draw one hexagon panel: grey land base, heatmap over the cells that carry a claim.

    `edgecolors="face"` rather than no edge at all: without it, antialiasing leaves a hairline of
    background between neighbouring hexagons and the surface reads as a dot screen rather than a
    continuous field.
    """
    ax.set_facecolor(WATER)
    ax.add_collection(
        PolyCollection(polygons, facecolors=LAND, edgecolors="face", linewidths=0.0, zorder=1)
    )
    keep = np.flatnonzero(~masked)
    mesh = PolyCollection(
        [polygons[i] for i in keep],
        array=values[keep], cmap=cmap, edgecolors="face", linewidths=0.0, zorder=2,
    )
    mesh.set_clim(0.0, vmax if vmax is not None else float(values[keep].max()))
    ax.add_collection(mesh)

    draw_countries(ax, color="#8b949e", linewidth=0.4, zorder=3)
    size_handles = _observation_markers(ax, obs, area_min=area_min, area_max=area_max)
    ax.set_xlim(-180, 180)
    ax.set_ylim(-60, 84)
    ax.set_aspect("equal")
    ax.set_title(title, loc="left", fontsize=11)
    handles = size_handles + list(ax.get_legend_handles_labels()[0])
    handles.append(Patch(facecolor=LAND, label=f"no claim ({int(masked.sum())} cells)"))
    # markerscale stays 1.0: the size exemplars only mean anything if the legend draws them at
    # the size the map does.
    ax.legend(handles=handles, loc="lower left", fontsize=8, framealpha=0.9, markerscale=1.0)
    plt.colorbar(mesh, ax=ax, label=label, shrink=0.72)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--layer", choices=("hbs", "g6pd", "afnd"), default="hbs")
    ap.add_argument("--observations", type=Path, required=True)
    # AFND ships one file holding every allele, so a surface needs to be told which one.
    ap.add_argument("--populations", type=Path, help="AFND population table (--layer afnd)")
    ap.add_argument("--variant", help="AFND variant_id, e.g. hla:drb1-15-01 (--layer afnd)")
    ap.add_argument(
        "--min-populations", type=int, default=30,
        help="AFND: drop alleles measured in fewer populations than this",
    )
    ap.add_argument("--data-version", default="afnd-2026-08")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--h3-res", type=int, default=3, help="H3 resolution for the rendered cells")
    ap.add_argument("--draws", type=int, default=400)
    ap.add_argument("--contraction-threshold", type=float, default=0.9)
    ap.add_argument("--hsgp-m", type=int, default=6, help="HSGP basis functions per dimension")
    ap.add_argument("--approximation", choices=("hsgp", "inducing"), default="hsgp")
    ap.add_argument("--n-inducing", type=int, default=200)
    # Two levels, because the two things you iterate on have different costs. `--fit` skips
    # inference but still predicts, so it survives a change of resolution or extent. `--cache`
    # additionally skips prediction, so it is only valid for the identical cell set — which is
    # exactly the case when all you changed was a colour.
    ap.add_argument(
        "--fit",
        type=Path,
        help="reuse the trained model from this file if it exists, else write it there. "
        "Skips inference; still predicts, so any resolution or extent works.",
    )
    ap.add_argument(
        "--cache",
        type=Path,
        help="reuse per-cell predictions from this file if it exists, else write them to it. "
        "Skips prediction too, so it is valid only for the same --h3-res.",
    )
    ap.add_argument("--cmap", default=VALUE_CMAP, help="matplotlib colormap for the value panel")
    ap.add_argument(
        "--marker-area-min", type=float, default=PRESENCE_AREA_MIN,
        help="marker area for the rarest presence; the floor that keeps it visible",
    )
    ap.add_argument(
        "--marker-area-max", type=float, default=PRESENCE_AREA_MAX,
        help="marker area for the most frequent presence; lower it for dense layers like HbS",
    )
    ap.add_argument("--dpi", type=int, default=220)
    args = ap.parse_args()

    if args.layer == "afnd":
        if not args.populations or not args.variant:
            raise SystemExit("--layer afnd needs both --populations and --variant")
        observations, report = afnd_frequencies.load(
            args.observations, args.populations, args.data_version,
            min_populations=args.min_populations,
        )
        print(report)
        observations = observations[observations["variant_id"] == args.variant].reset_index(
            drop=True
        )
        if observations.empty:
            raise SystemExit(
                f"{args.variant} has no observations at --min-populations "
                f"{args.min_populations}; it is not a modelable allele in this release"
            )
        layer_title = hla_display_name(args.variant)
        value_label = f"posterior median {layer_title} allele frequency"
    else:
        loader = {"hbs": map_surveys.load, "g6pd": map_g6pd.load}[args.layer]
        observations, report = loader(args.observations, "figure")
        print(report)
        layer_title = _LAYER_TITLE[args.layer]
        value_label = _VALUE_LABEL[args.layer]

    cells = h3_land_cells(args.h3_res)
    polygons, kept = h3_polygons(cells)
    import h3

    cell_edge_km = h3.average_hexagon_edge_length(args.h3_res, unit="km")

    centres = np.array([h3.cell_to_latlng(cells[i]) for i in kept], dtype=float)
    cell_lat, cell_lon = centres[:, 0], centres[:, 1]
    print(f"H3 res {args.h3_res}: {len(cells)} land cells, {len(polygons)} drawable")

    if args.cache and args.cache.exists():
        cached = np.load(args.cache, allow_pickle=False)
        if len(cached["central"]) != len(cell_lat):
            raise SystemExit(
                f"{args.cache} holds {len(cached['central'])} cells but H3 res {args.h3_res} "
                f"has {len(cell_lat)}; delete the cache or match the resolution"
            )
        central, sd = cached["central"], cached["sd"]
        correlation_range_km, prior_sd = float(cached["range_km"]), float(cached["prior_sd"])
        print(f"reused predictions from {args.cache} (no refit)")
    else:
        if args.fit and args.fit.exists():
            fit = load_fit(args.fit)
            print(f"reused trained model from {args.fit} (no refit)")
        else:
            fit = fit_surface(
                observations,
                FitConfig(
                    draws=args.draws,
                    tune=args.draws,
                    hsgp_m=(args.hsgp_m,) * 3,  # the GP lives on the unit sphere, so 3 dimensions
                    approximation=args.approximation,
                    n_inducing=args.n_inducing,
                ),
            )
            if args.fit:
                print(f"saved trained model to {save_fit(fit, args.fit)}")
        predicted = fit.predict(lat=cell_lat, lon=cell_lon)
        central = predicted["post_median"].to_numpy()
        sd = predicted["post_sd"].to_numpy()
        correlation_range_km, prior_sd = fit.correlation_range_km, fit.prior_frequency_sd
        if args.cache:
            args.cache.parent.mkdir(parents=True, exist_ok=True)
            np.savez(
                args.cache, central=central, sd=sd,
                range_km=correlation_range_km, prior_sd=prior_sd,
            )
            print(f"cached predictions to {args.cache}")
    print(f"correlation range {correlation_range_km:.0f} km, prior sd {prior_sd:.3f}")

    obs_lat = observations["lat"].to_numpy()
    obs_lon = observations["lon"].to_numpy()
    distance = np.min(
        _haversine_km(cell_lat[:, None], cell_lon[:, None], obs_lat[None, :], obs_lon[None, :]),
        axis=1,
    )

    config = MaskConfig(contraction_threshold=args.contraction_threshold)
    contraction = sd / prior_sd
    support = classify_support(
        has_observation_centre=distance < 50.0,
        dist_nearest_obs_km=distance,
        posterior_contraction=contraction,
        correlation_range_km=correlation_range_km,
        config=config,
    )
    counts = {state: int((support == state).sum()) for state in set(support)}
    print("support states:", counts)
    print(
        f"posterior_contraction on land: median {np.median(contraction):.2f}  "
        f"p90 {np.quantile(contraction, 0.9):.2f}  max {contraction.max():.2f}"
    )
    masked = np.isin(support, MASKED)

    fig, axes = plt.subplots(2, 1, figsize=(13, 13), constrained_layout=True)
    _panel(
        axes[0], polygons, central, masked, observations,
        cmap=args.cmap, label=value_label,
        title=f"{layer_title} — posterior median   |   {len(observations)} populations"
              f"  ·  correlation range {correlation_range_km:.0f} km"
              f"  ·  H3 res-{args.h3_res} cells, {cell_edge_km:.0f} km edge",
        vmax=float(central[~masked].max()),
        area_min=args.marker_area_min, area_max=args.marker_area_max,
    )
    _panel(
        axes[1], polygons, sd, masked, observations,
        cmap=UNCERTAINTY_CMAP, label="posterior standard deviation",
        title=f"{layer_title} — posterior standard deviation   |   same cells",
        area_min=args.marker_area_min, area_max=args.marker_area_max,
    )
    fig.suptitle(
        f"{layer_title} fitted from {len(observations)} {_LAYER_SOURCE[args.layer]} — "
        f"correlation range {correlation_range_km:.0f} km, "
        f"rendered on H3 res-{args.h3_res} cells",
        fontsize=13,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.out, dpi=args.dpi, facecolor="white")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
