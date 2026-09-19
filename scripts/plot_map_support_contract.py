#!/usr/bin/env python3
"""Plot the synthetic MAP support boundary (Atlas design §§4, 6–8, 12).

    python scripts/plot_map_support_contract.py --out docs/figures/map_support_contract.png

This is an observation-contract demonstration. It draws no fitted frequency surface and treats
all space outside the accepted synthetic coordinates as unqualified.
"""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

from genomeos.observations.sources import map_surveys  # noqa: E402

ROOT = Path(__file__).parents[1]
SYNTHETIC_FIXTURE = ROOT / "tests" / "fixtures" / "map_hbs_curated_synthetic.csv"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise SystemExit(f"refusing to overwrite existing output: {args.out}")

    observations, report = map_surveys.load(SYNTHETIC_FIXTURE, "synthetic-contract")
    source = pd.read_csv(SYNTHETIC_FIXTURE).set_index("id")
    accepted = observations.assign(
        survey_id=observations["source_record_id"].str.rsplit(":", n=1).str[-1].astype(int)
    )

    with tempfile.TemporaryDirectory() as temporary:
        area_only = Path(temporary) / "area-only.csv"
        pd.read_csv(SYNTHETIC_FIXTURE).drop(columns=list(map_surveys.SUPPORT_COLUMNS)).to_csv(
            area_only, index=False
        )
        try:
            map_surveys.load(area_only, "synthetic-contract")
        except ValueError as error:
            refusal = str(error)
        else:
            raise RuntimeError("area-only MAP input unexpectedly produced P1 observations")
    if "explicit spatial support" not in refusal:
        raise RuntimeError(f"unexpected area-only refusal: {refusal}")

    fig, (axis, note) = plt.subplots(
        1, 2, figsize=(12, 5.4), gridspec_kw={"width_ratios": [3.0, 1.25]}
    )
    axis.add_patch(
        Rectangle(
            (-180, -90),
            360,
            180,
            facecolor="#eef0f2",
            edgecolor="#a8adb3",
            hatch="////",
            linewidth=0.8,
            zorder=0,
        )
    )
    axis.scatter(
        accepted["lon"],
        accepted["lat"],
        s=45,
        color="#1769aa",
        edgecolor="white",
        linewidth=0.7,
        zorder=2,
    )
    for row in accepted.itertuples(index=False):
        radius = float(source.loc[row.survey_id, "radius_km"])
        axis.annotate(
            f"{row.survey_id}: {radius:g} km",
            (row.lon, row.lat),
            xytext=(5, 5),
            textcoords="offset points",
            fontsize=8,
            zorder=3,
        )
    axis.set(xlim=(-180, 180), ylim=(-90, 90), xlabel="longitude", ylabel="latitude")
    axis.set_title(
        f"{report.retained} accepted synthetic observations\n"
        "labels are exact declared bounding radii; hatching is unqualified space",
        loc="left",
        fontsize=10,
    )
    axis.grid(color="white", linewidth=0.6)

    note.axis("off")
    note.text(
        0.0,
        0.95,
        "AREA-ONLY INPUT\nREFUSED",
        color="#a32620",
        fontsize=16,
        fontweight="bold",
        va="top",
    )
    note.text(
        0.0,
        0.70,
        "The actual loader was called on a copy\n"
        "without the four support columns.\n\n"
        "Result: hard error before any P1\n"
        "observation frame was emitted.\n\n"
        "Area classes do not supply a\n"
        "sampling bounding-disc radius.",
        fontsize=10,
        va="top",
        linespacing=1.35,
    )
    fig.suptitle(
        "SYNTHETIC — contract demonstration, not scientific results",
        fontsize=15,
        fontweight="bold",
    )
    fig.tight_layout()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.out, dpi=180, facecolor="white")
    plt.close(fig)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
