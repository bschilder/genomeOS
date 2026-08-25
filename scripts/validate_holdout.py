"""Held-out predictive validation of the HbS surface (design §7, §8).

    python scripts/validate_holdout.py --observations data/raw/map_hbs_surveys.csv \
        --out data/validation --n-folds 5 --n-inducing 150

Runs both spatially blocked and random folds. The gap between them is the point: random folds
leak neighbours across the split, so the difference measures how much apparent skill is spatial
autocorrelation rather than predictive signal.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from genomeos.observations.sources import map_surveys
from genomeos.surfaces.fit import FitConfig
from genomeos.validation.crossval import cross_validate


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--observations", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--n-folds", type=int, default=5)
    # 150, not 800. Inducing points closer together than ~0.25 of the fitted correlation range
    # (~600 km for HbS) are redundant: they correlate at ~0.99, K_uu goes near-singular and NUTS
    # grinds at maximum tree depth. At M=800 the spacing is far inside that and a single fold
    # takes hours; at M=150 it is minutes. See `MIN_SPACING_FRACTION` in surfaces.fit.
    ap.add_argument("--n-inducing", type=int, default=150)
    ap.add_argument("--draws", type=int, default=600)
    args = ap.parse_args()

    observations, report = map_surveys.load(args.observations, "validation")
    print(report)

    config = FitConfig(
        draws=args.draws,
        tune=max(args.draws, 1000),
        approximation="inducing",
        n_inducing=args.n_inducing,
    )

    args.out.mkdir(parents=True, exist_ok=True)
    summary: dict[str, dict] = {}
    for strategy in ("spatial", "random"):
        # Spatial first: it is the honest test, so if the run is cut short it is the half worth
        # having. A previous run wrote nothing at all because results were only saved at the end.
        result = cross_validate(observations, config, args.n_folds, strategy)
        print(f"\n{result}")
        result.summary().to_csv(args.out / f"crossval_{strategy}.csv", index=False)
        # Flush after each strategy rather than only at the end.
        (args.out / f"crossval_{strategy}.json").write_text(str(result))
        summary[strategy] = {
            "folds_scored": len(result.folds),
            "folds_attempted": result.n_attempted,
            "folds_failed": [f.__dict__ for f in result.failures],
            "coverage_95": result._mean("coverage_95"),
            "coverage_50": result._mean("coverage_50"),
            "mae": result._mean("mae"),
            "rmse": result._mean("rmse"),
            "log_score": result._mean("log_score"),
            "baseline_log_score": result._mean("baseline_log_score"),
            "skill": result.skill,
        }

    (args.out / "crossval_summary.json").write_text(json.dumps(summary, indent=2))
    spatial, random = summary["spatial"], summary["random"]
    print("\n=== interpretation ===")
    for strategy, block in summary.items():
        if block["folds_scored"] == 0:
            print(f"{strategy}: NO fold converged — nothing to conclude")
        elif block["folds_failed"]:
            print(
                f"{strategy}: {block['folds_scored']}/{block['folds_attempted']} folds scored; "
                f"{len(block['folds_failed'])} excluded for non-convergence"
            )
    print(f"skill over baseline, spatial folds : {spatial['skill']:+.3f}")
    print(f"skill over baseline, random folds  : {random['skill']:+.3f}")
    print(
        "autocorrelation share of apparent skill: "
        f"{1 - spatial['skill'] / random['skill']:.0%}"
        if random["skill"] > 0
        else "baseline not beaten on random folds"
    )
    print(f"95% interval coverage, spatial     : {spatial['coverage_95']:.2f} (target 0.95)")


if __name__ == "__main__":
    main()
