"""What refusing the donor-registry ancestry strata did to the surfaces (#141).

    python scripts/plot_registry_refusal.py --before data/store/screen \
        --after data/store/screen_no_registries --out docs/figures/registry_refusal.png

Three panels per allele: the surface with the registries included, the surface with them refused,
and the difference. The difference panel is the one worth reading. The global maps look nearly
identical because 905 geographic populations were already setting the broad structure; what the
registries did was overwrite a small area very confidently, at their own coordinate.

Both sides must be fitted at the same draw budget or the comparison measures the sampler rather
than the data.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import h3  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.collections import PolyCollection  # noqa: E402

from genomeos.observations.sources import afnd_frequencies  # noqa: E402
from genomeos.registry.sources import afnd as afnd_registry  # noqa: E402
from genomeos.surfaces.fit import load_fit  # noqa: E402
from genomeos.viz.basemap import draw_countries, h3_land_cells, h3_polygons  # noqa: E402

LAND = "#e3e6ea"
#: Diverging, because the difference has a meaningful zero and a sign. A sequential ramp here
#: would hide which direction the registries were pushing the surface.
DIFFERENCE_CMAP = "RdBu_r"

#: Marker area bounds, as in `plot_surface`. Area is proportional to observed frequency, so the
#: figure shows how much evidence each point carries rather than only where it is.
AREA_MIN, AREA_MAX = 5.0, 70.0


def hla_display_name(variant_id: str) -> str:
    """``hla:c-03-03`` -> ``HLA-C*03:03``."""
    gene, _, fields = variant_id[len("hla:") :].partition("-")
    return f"HLA-{gene.upper()}*{fields.replace('-', ':')}"


def _markers(ax, frame, f_max, *, edge, zorder):
    """Observations as proportional symbols, area ~ observed frequency."""
    if frame is None or not len(frame):
        return
    freq = (frame["ac"] / frame["an"]).to_numpy(dtype=float)
    area = AREA_MIN + (AREA_MAX - AREA_MIN) * np.clip(freq / f_max, 0.0, 1.0)
    order = np.argsort(-area)          # largest first, so small markers stay findable
    ax.scatter(
        frame["lon"].to_numpy()[order], frame["lat"].to_numpy()[order], s=area[order],
        facecolor=[(1.0, 1.0, 1.0, 0.75)], edgecolor=edge, linewidth=0.45, zorder=zorder,
    )


def _panel(ax, polygons, values, *, cmap, vmin, vmax, title,
           observations=None, removed=None, f_max=1.0):
    ax.set_facecolor("white")
    ax.add_collection(PolyCollection(polygons, facecolors=LAND, edgecolors="face", zorder=1))
    mesh = PolyCollection(polygons, array=values, cmap=cmap, edgecolors="face", zorder=2)
    mesh.set_clim(vmin, vmax)
    ax.add_collection(mesh)
    draw_countries(ax, color="#8b949e", linewidth=0.3, zorder=3)
    _markers(ax, observations, f_max, edge="#11151a", zorder=4)
    # Crimson edge, drawn on top: these are the registry strata, present in the BEFORE fit and
    # absent from the AFTER one. Seeing where they sit is the point of the comparison.
    _markers(ax, removed, f_max, edge="#c0392b", zorder=5)
    ax.set_xlim(-180, 180)
    ax.set_ylim(-60, 84)
    ax.set_aspect("equal")
    ax.set_title(title, loc="left", fontsize=10)
    return mesh


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--before", type=Path, required=True)
    ap.add_argument("--after", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--frequencies", type=Path, default=Path("data/raw/afnd_frequencies.tsv"))
    ap.add_argument("--populations", type=Path, default=Path("data/raw/afnd_populations.tsv"))
    ap.add_argument("--variants", nargs="+",
                    default=["hla:c-03-03", "hla:a-02-01", "hla:drb1-01-01"])
    ap.add_argument("--h3-res", type=int, default=3)
    ap.add_argument("--dpi", type=int, default=120)
    args = ap.parse_args()

    cells = h3_land_cells(args.h3_res)
    polygons, kept = h3_polygons(cells)
    centres = np.array([h3.cell_to_latlng(cells[i]) for i in kept], dtype=float)
    lat, lon = centres[:, 0], centres[:, 1]

    observations, report = afnd_frequencies.load(
        args.frequencies, args.populations, "afnd-2026-08", min_populations=30
    )
    print(report)

    # The refused rows, rebuilt for display only. The adapter has no switch to disable a
    # data-quality refusal and should not grow one (§ "no config switch for an invariant"), so
    # the diagnostic reconstructs them from the raw table and the registry's own coordinates.
    import pandas as pd

    raw = pd.read_csv(args.frequencies, sep="\t", dtype=str, keep_default_na=False)
    registry, aliases, _ = afnd_registry.load(args.populations, registry_version="afnd-2026-08")
    placed = registry.set_index("population_id")[["lat", "lon"]]
    name_to_id = dict(zip(aliases["label"], aliases["population_id"], strict=True))
    is_registry = raw["population"].str.contains(
        "|".join(afnd_frequencies.DONOR_REGISTRIES), case=False, regex=True, na=False
    )
    refused = raw[is_registry].copy()
    refused["variant_id"] = [
        afnd_frequencies.variant_id(g, a, grp)
        for g, a, grp in zip(refused["gene"], refused["allele"], refused["group"], strict=True)
    ]
    refused["an"] = 2 * pd.to_numeric(
        refused["n"].str.replace(",", "", regex=False), errors="coerce"
    )
    refused["af"] = pd.to_numeric(refused["alleles_over_2n"], errors="coerce")
    refused["ac"] = (refused["af"] * refused["an"]).round()
    ids = refused["population"].map(name_to_id)
    geo = placed.reindex(ids.to_numpy())
    refused["lat"] = geo["lat"].to_numpy()
    refused["lon"] = geo["lon"].to_numpy()
    refused = refused.dropna(subset=["lat", "lon", "ac", "an"])
    print(f"  {len(refused)} refused registry rows reconstructed for the BEFORE panel")

    fig, axes = plt.subplots(len(args.variants), 3,
                             figsize=(30, 5.2 * len(args.variants)), constrained_layout=True)
    axes = np.atleast_2d(axes)

    for row, variant_id in enumerate(args.variants):
        stem = variant_id.replace(":", "__")
        before = load_fit(args.before / f"{stem}.fit.pkl")
        after = load_fit(args.after / f"{stem}.fit.pkl")
        b = before.predict(lat=lat, lon=lon)["post_median"].to_numpy()
        a = after.predict(lat=lat, lon=lon)["post_median"].to_numpy()
        difference = a - b
        # One scale across before and after, or the eye reads a colourbar change as a data change.
        vmax = float(max(b.max(), a.max()))
        kept_rows = observations[observations["variant_id"] == variant_id]
        gone_rows = refused[refused["variant_id"] == variant_id]
        # One marker scale across both panels, or a dot changes size for the wrong reason.
        f_max = max(
            float((kept_rows["ac"] / kept_rows["an"]).max()) if len(kept_rows) else 0.0,
            float((gone_rows["ac"] / gone_rows["an"]).max()) if len(gone_rows) else 0.0,
            1e-9,
        )
        limit = float(np.abs(difference).max())
        name = hla_display_name(variant_id)

        mesh = _panel(axes[row, 0], polygons, b, cmap="turbo", vmin=0.0, vmax=vmax,
                      title=f"{name} BEFORE — registries included   |   "
                            f"range {before.correlation_range_km:.0f} km   "
                            f"({len(kept_rows)} populations + {len(gone_rows)} registry, red)",
                      observations=kept_rows, removed=gone_rows, f_max=f_max)
        plt.colorbar(mesh, ax=axes[row, 0], shrink=0.7, label="allele frequency")

        mesh = _panel(axes[row, 1], polygons, a, cmap="turbo", vmin=0.0, vmax=vmax,
                      title=f"{name} AFTER — registries refused   |   "
                            f"range {after.correlation_range_km:.0f} km   "
                            f"({len(kept_rows)} populations)",
                      observations=kept_rows, f_max=f_max)
        plt.colorbar(mesh, ax=axes[row, 1], shrink=0.7, label="allele frequency")

        mesh = _panel(axes[row, 2], polygons, difference, cmap=DIFFERENCE_CMAP,
                      vmin=-limit, vmax=limit,
                      title=f"DIFFERENCE (after − before)   |   max shift {limit:.3f} "
                            f"({100 * limit / vmax:.0f}% of the scale), "
                            f"mean {np.abs(difference).mean():.4f}")
        plt.colorbar(mesh, ax=axes[row, 2], shrink=0.7, label="change in allele frequency")
        print(f"  {variant_id}: rho {before.correlation_range_km:.0f} -> "
              f"{after.correlation_range_km:.0f} km, max |shift| {limit:.4f}")

    fig.suptitle(
        "Refusing donor-registry ancestry strata (#141): 37 populations that carried 91% of the "
        "corpus weight at two coordinates",
        fontsize=14,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.out, dpi=args.dpi, facecolor="white")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
