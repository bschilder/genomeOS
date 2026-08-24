"""Render the observations layer for review (design §5, §11).

Figures for pull requests and issues. This plots **observations only** — measured allele counts
at their survey coordinates. It deliberately draws no fitted surface and no interpolation
between points, because §4's first invariant is that what was measured and what was inferred are
never conflated, and that applies to a review figure as much as to the product.

    python scripts/plot_observations.py --observations data/raw/map_hbs_surveys.csv \
        --out docs/figures/hbs_observations.png

Marker area is proportional to sample size, so a survey of 100 does not carry the same visual
weight as one of 10,000 — the same reason §11 encodes sample size as opacity in the map client.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from genomeos.observations.sources import map_surveys  # noqa: E402
from genomeos.viz.basemap import draw_countries  # noqa: E402


def plot(observations, report, out: Path, title: str) -> None:
    frequency = (observations["ac"] / observations["an"]).to_numpy()
    size = 10 + 70 * (observations["an"] / observations["an"].max()).to_numpy() ** 0.5

    fig, (ax, bar) = plt.subplots(
        2, 1, figsize=(13, 9), height_ratios=[5, 1], constrained_layout=True
    )

    ax.set_facecolor("#f6f8fa")
    for lat in (-60, -30, 0, 30, 60):
        ax.axhline(lat, color="#e4e8ec", lw=0.6, zorder=0)
    for lon in range(-180, 181, 30):
        ax.axvline(lon, color="#e4e8ec", lw=0.6, zorder=0)
    draw_countries(ax)

    # Presence and absence get different marker *shapes*, following the benchmark figure
    # (Piel et al. 2013, Figure 1A). AC=0 is measured absence, not missing data (§7.1b): plotted
    # as the bottom of a sequential colour ramp, the strongest negative evidence in the corpus
    # becomes invisible. Shape carries the categorical distinction; colour carries the magnitude.
    absent = frequency == 0.0
    ax.scatter(
        observations["lon"][absent], observations["lat"][absent],
        s=size[absent], marker="^", facecolor="#2f6fdb", edgecolor="#0b3d91", linewidth=0.3,
        alpha=0.85, label=f"absence — AC=0 ({int(absent.sum())} surveys)", zorder=2,
    )
    scatter = ax.scatter(
        observations["lon"][~absent], observations["lat"][~absent],
        # YlOrRd, not a reversed ramp: pale-to-saturated reads as low-to-high without having to
        # consult the legend, and matches the convention of the prevalence-mapping literature.
        c=frequency[~absent], s=size[~absent], cmap="YlOrRd", marker="o",
        vmin=0.0, vmax=float(frequency.max()),
        edgecolor="#24292f", linewidth=0.35, alpha=0.95, zorder=3,
        label=f"presence — AC>0 ({int((~absent).sum())} surveys)",
    )
    ax.set_xlim(-180, 180)
    ax.set_ylim(-60, 80)
    ax.set_aspect("equal")  # unequal axes would distort every distance the eye reads off this
    ax.set_xlabel("longitude")
    ax.set_ylabel("latitude")
    ax.set_title(title, loc="left", fontsize=13)
    ax.legend(loc="lower left", fontsize=9, framealpha=0.9)
    fig.colorbar(scatter, ax=ax, label="HbS allele frequency (measured)", shrink=0.7)

    reasons = dict(sorted(report.refusals.items(), key=lambda kv: kv[1]))
    bar.barh(list(reasons), list(reasons.values()), color="#8b949e")
    bar.barh(["retained"], [report.retained], color="#2f81f7")
    bar.set_xlabel("surveys")
    bar.set_title(
        f"{report.retained}/{report.total} retained — every refusal stated, none silent (§12)",
        loc="left",
        fontsize=10,
    )
    for spine in ("top", "right"):
        bar.spines[spine].set_visible(False)

    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=140, facecolor="white")
    print(f"wrote {out}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--observations", type=Path, required=True, help="MAP HbS survey export CSV")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    observations, report = map_surveys.load(args.observations, "figure")
    plot(
        observations,
        report,
        args.out,
        f"MAP HbS surveys — {len(observations)} measured allele frequencies (rs334, HBB)",
    )
    print(report)


if __name__ == "__main__":
    main()
