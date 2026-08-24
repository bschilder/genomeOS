"""Render the fitted surface with its data-support mask (design §7, §11).

Two panels, because §11 makes the mean/uncertainty comparison the default view for a surface:
the posterior mean, and the posterior standard deviation. Both carry the mask.

**The mask is the point of this figure.** §4's structural answer to Novembre & Stephens 2008 is
that a fitted surface must state where it does not know, so cells with no observation within 2ρ,
and cells whose posterior never moved off the prior, are hatched rather than coloured. A version
of this figure without the mask would be exactly the persuasive-but-unfounded cline the design
exists to avoid.

    python scripts/plot_surface.py --observations data/raw/map_hbs_surveys.csv \
        --out docs/figures/hbs_surface.png

Evaluated on a regular lat/lon grid rather than H3 cells purely for legibility at this scale;
the product renders H3 hexagons (§6). The mask logic is the same `classify_support` the pipeline
uses, not a reimplementation.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from genomeos.observations.sources import map_surveys  # noqa: E402
from genomeos.surfaces.fit import FitConfig, fit_surface  # noqa: E402
from genomeos.surfaces.mask import MaskConfig, classify_support  # noqa: E402
from genomeos.viz.basemap import draw_countries, land_mask  # noqa: E402

MASKED = ("unknown", "prior_dominated", "unpopulated")


def _haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0088
    dlat, dlon = np.radians(lat2 - lat1), np.radians(lon2 - lon1)
    a = (
        np.sin(dlat / 2) ** 2
        + np.cos(np.radians(lat1)) * np.cos(np.radians(lat2)) * np.sin(dlon / 2) ** 2
    )
    return 2 * r * np.arcsin(np.sqrt(a))


def _observation_markers(ax, obs) -> None:
    """Overlay the surveys, with presence and absence as different shapes.

    Same encoding as the observations figure and as Piel et al.'s Figure 1A. On a fitted surface
    this matters more, not less: an absence survey sitting inside a warm region is the clearest
    visual signal that the model is smoothing over contrary evidence, and it disappears entirely
    if every observation is drawn as the same dot.
    """
    absent = (obs["ac"] == 0).to_numpy()
    ax.scatter(
        obs["lon"][~absent], obs["lat"][~absent], s=5, marker="o",
        c="#0969da", alpha=0.75, linewidth=0, zorder=4,
        label=f"presence ({int((~absent).sum())})",
    )
    ax.scatter(
        obs["lon"][absent], obs["lat"][absent], s=11, marker="^",
        facecolor="none", edgecolor="#0b3d91", linewidth=0.6, zorder=5,
        label=f"absence — AC=0 ({int(absent.sum())})",
    )


def _panel(ax, lons, lats, values, support, obs, *, cmap, label, title, vmax=None):
    ax.set_facecolor("#f6f8fa")
    shown = np.where(np.isin(support, MASKED), np.nan, values)
    mesh = ax.pcolormesh(
        lons, lats, shown, cmap=cmap, shading="auto", vmin=0.0, vmax=vmax, zorder=1
    )
    # Masked cells are hatched, not blank: blank reads as "zero", hatched reads as "no claim".
    ax.contourf(
        lons, lats, np.isin(support, MASKED).astype(float), levels=[0.5, 1.5],
        colors="none", hatches=["////"], zorder=2,
    )
    draw_countries(ax, color="#57606a", linewidth=0.4, zorder=3)
    _observation_markers(ax, obs)
    ax.set_xlim(-180, 180)
    ax.set_ylim(-60, 80)
    ax.set_aspect("equal")
    ax.set_title(title, loc="left", fontsize=11)
    ax.legend(loc="lower left", fontsize=8, framealpha=0.9, markerscale=1.6)
    plt.colorbar(mesh, ax=ax, label=label, shrink=0.72)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--observations", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--step", type=float, default=1.5, help="grid step in degrees")
    ap.add_argument("--draws", type=int, default=400)
    ap.add_argument("--contraction-threshold", type=float, default=0.9)
    ap.add_argument("--hsgp-m", type=int, default=6, help="HSGP basis functions per dimension")
    args = ap.parse_args()

    observations, report = map_surveys.load(args.observations, "figure")
    print(report)

    fit = fit_surface(
        observations,
        FitConfig(
            draws=args.draws,
            tune=args.draws,
            hsgp_m=(args.hsgp_m,) * 3,  # the GP lives on the unit sphere, so three dimensions
        ),
    )
    print(f"correlation range {fit.correlation_range_km:.0f} km, prior sd {fit.prior_frequency_sd:.3f}")

    lon_edges = np.arange(-180.0, 180.0 + args.step, args.step)
    lat_edges = np.arange(-60.0, 80.0 + args.step, args.step)
    lon_grid, lat_grid = np.meshgrid(lon_edges, lat_edges)
    flat_lat, flat_lon = lat_grid.ravel(), lon_grid.ravel()

    predicted = fit.predict(lat=flat_lat, lon=flat_lon)
    central = predicted["post_median"].to_numpy()
    sd = predicted["post_sd"].to_numpy()

    obs_lat = observations["lat"].to_numpy()
    obs_lon = observations["lon"].to_numpy()
    distance = np.min(
        _haversine_km(flat_lat[:, None], flat_lon[:, None], obs_lat[None, :], obs_lon[None, :]),
        axis=1,
    )
    # No people, no claim. See the note in `land_mask` and #101: §7's states are all about
    # observation proximity, so without this the surface paints open ocean.
    on_land = land_mask(flat_lon, flat_lat)

    config = MaskConfig(contraction_threshold=args.contraction_threshold)
    support = classify_support(
        has_observation_centre=distance < 50.0,
        dist_nearest_obs_km=distance,
        posterior_contraction=sd / fit.prior_frequency_sd,
        correlation_range_km=fit.correlation_range_km,
        config=config,
    )
    support = np.where(on_land, support, "unpopulated")
    counts = {state: int((support == state).sum()) for state in set(support)}
    print("support states:", counts)
    contraction = sd / fit.prior_frequency_sd
    land = contraction[on_land]
    print(
        f"posterior_contraction on land: median {np.median(land):.2f}  "
        f"p90 {np.quantile(land, 0.9):.2f}  max {land.max():.2f}"
    )

    shape = lon_grid.shape
    fig, axes = plt.subplots(2, 1, figsize=(13, 13), constrained_layout=True)
    _panel(
        axes[0], lon_grid, lat_grid, central.reshape(shape), support.reshape(shape), observations,
        cmap="YlOrRd", label="posterior median HbS allele frequency",
        title="Fitted surface — posterior MEDIAN (hatched = no claim: unknown, prior-dominated, unpopulated)",
        vmax=float(np.nanmax(np.where(np.isin(support, MASKED), np.nan, central))),
    )
    _panel(
        axes[1], lon_grid, lat_grid, sd.reshape(shape), support.reshape(shape), observations,
        cmap="Purples", label="posterior standard deviation",
        title="Posterior uncertainty — where the surface is least trustworthy",
    )
    fig.suptitle(
        f"HbS (rs334) fitted from {len(observations)} MAP surveys — "
        f"correlation range {fit.correlation_range_km:.0f} km",
        fontsize=13,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.out, dpi=130, facecolor="white")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
