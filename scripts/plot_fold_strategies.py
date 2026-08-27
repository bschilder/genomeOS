"""What each cross-validation fold strategy does to the studies it splits (#127).

    python scripts/plot_fold_strategies.py --observations data/raw/map_hbs_surveys.csv \
        --out docs/figures/fold_strategies.png

`cohort_id` is the contributing study, and a study effect is identified by *within-study
replication*: the sites one study contributes in more than one place. A random split scatters
those sites across folds, so in training the study becomes a singleton — one observation, one
level — at which point `cohort_sd * cohort_z` and the beta-binomial `concentration` describe the
same single residual and are not jointly identifiable (#127).

The top row shows where each fold's surveys are. The bottom row is the point: how many folds each
multi-site study ends up spanning. One bar at 1 means every study survived intact; mass to the
right of 1 is studies that were torn apart, and each of those has lost the replication its cohort
term is estimated from.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from genomeos.observations.sources import map_surveys  # noqa: E402
from genomeos.validation.crossval import (  # noqa: E402
    make_folds,
    studies_split_across_folds,
)
from genomeos.viz.basemap import draw_countries  # noqa: E402

#: Ordered worst-to-best on study integrity, so the figure reads left to right as an improvement.
STRATEGIES = ("random", "spatial", "grouped")

_BLURB = {
    "random": "shuffles rows: neighbours leak AND studies shatter",
    "spatial": "holds out whole regions: the honest test of spatial skill",
    "grouped": "assigns whole studies: leaks neighbours, keeps studies intact",
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--observations", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--n-folds", type=int, default=5)
    ap.add_argument("--dpi", type=int, default=170)
    args = ap.parse_args()

    observations, report = map_surveys.load(args.observations, "figure")
    print(report)
    observations = observations.reset_index(drop=True)

    fig, axes = plt.subplots(2, len(STRATEGIES), figsize=(6.2 * len(STRATEGIES), 8.6),
                             constrained_layout=True,
                             gridspec_kw={"height_ratios": [2.0, 1.0]})

    for column, strategy in enumerate(STRATEGIES):
        folds = make_folds(observations, args.n_folds, strategy)
        split, multi_site = studies_split_across_folds(observations["cohort_id"], folds)

        top = axes[0, column]
        top.set_facecolor("white")
        draw_countries(top, color="#b8c0c8", linewidth=0.3, zorder=1)
        top.scatter(
            observations["lon"], observations["lat"], c=folds, cmap="tab10", vmin=0, vmax=9,
            s=7, linewidth=0.15, edgecolor="#11151a", zorder=2,
        )
        top.set_xlim(-125, 105)
        top.set_ylim(-40, 60)
        top.set_aspect("equal")
        top.set_title(
            f"{strategy}\n{_BLURB[strategy]}", loc="left", fontsize=10,
        )

        # How many folds each multi-site study spans. 1 is intact; anything above 1 has lost the
        # within-study replication the cohort term is identified by.
        frame = pd.DataFrame({"cohort": observations["cohort_id"], "fold": folds})
        per_study = frame.groupby("cohort")["fold"].agg(["nunique", "size"])
        spans = per_study.loc[per_study["size"] > 1, "nunique"].to_numpy()

        bottom = axes[1, column]
        counts = np.bincount(spans, minlength=args.n_folds + 1)[1:]
        colours = ["#2f9e44"] + ["#c0392b"] * (len(counts) - 1)
        bottom.bar(range(1, len(counts) + 1), counts, color=colours, edgecolor="#11151a",
                   linewidth=0.5)
        for x, height in enumerate(counts, start=1):
            if height:
                bottom.text(x, height, f" {height}", ha="center", va="bottom", fontsize=8)
        bottom.set_xticks(range(1, args.n_folds + 1))
        bottom.set_xlabel("folds this study's sites were spread across")
        bottom.set_ylabel("multi-site studies")
        bottom.set_ylim(0, multi_site * 1.15)
        share = split / multi_site if multi_site else 0.0
        bottom.set_title(
            f"{split}/{multi_site} multi-site studies split  ({share:.0%})",
            loc="left", fontsize=10,
            color="#c0392b" if share > 0.5 else "#11151a",
        )
        print(f"  {strategy:<8} {split}/{multi_site} split ({share:.0%})")

    fig.suptitle(
        "Cross-validation fold strategy decides whether the cohort effect is identifiable at all "
        f"({len(observations)} MAP HbS surveys, {args.n_folds} folds)  —  green = study intact, "
        "red = study shattered",
        fontsize=12,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.out, dpi=args.dpi, facecolor="white")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
