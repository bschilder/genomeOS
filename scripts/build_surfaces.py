"""Fit every variant in one batch, and publish what was excluded (design §12, P2; #40).

    python scripts/build_surfaces.py --hbs data/raw/map_hbs_surveys.csv \
        --g6pd data/raw/map_g6pd_surveys.csv --out data/surfaces

This is the multi-variant entry point. It exists to make one property true: **every variant that
goes in comes out either as a saved fit or as a row in the exclusion list.** A variant that
merely fails to appear is the outcome §12 forbids, because a consumer cannot tell a refused
variant from one with no data.

Fits are saved with `save_fit` so figures, national rollups and validation can be produced later
without repeating the inference — a palette change should not cost nine minutes of NUTS.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from genomeos.observations.sources import map_g6pd, map_surveys
from genomeos.surfaces.batch import jobs_from_sources, run_batch, write_exclusions
from genomeos.surfaces.fit import FitConfig, save_fit

#: Loaders keyed by the CLI flag that supplies their export.
LAYERS = {"hbs": map_surveys.load, "g6pd": map_g6pd.load}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hbs", type=Path, help="MAP HbS survey export CSV")
    ap.add_argument("--g6pd", type=Path, help="MAP G6PD survey export CSV")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--data-version", default="map-2026-08")
    ap.add_argument("--n-inducing", type=int, default=150)
    ap.add_argument("--draws", type=int, default=400)
    args = ap.parse_args()

    sources: dict[str, pd.DataFrame] = {}
    for layer, loader in LAYERS.items():
        path = getattr(args, layer)
        if path is None:
            continue
        observations, report = loader(path, args.data_version)
        print(f"===== {layer} =====\n{report}\n")
        sources[layer] = observations
    if not sources:
        raise SystemExit("supply at least one of --hbs or --g6pd")

    config = FitConfig(
        draws=args.draws, tune=args.draws, approximation="inducing", n_inducing=args.n_inducing
    )
    jobs = list(jobs_from_sources(sources, config))
    print(f"===== fitting {len(jobs)} variants =====")
    for job in jobs:
        print(f"  {job.variant_id}: {len(job.observations)} observations")

    result = run_batch(jobs, on_progress=lambda v, n: print(f"----- {v} ({n} obs) -----", flush=True))

    args.out.mkdir(parents=True, exist_ok=True)
    for variant_id, fit in result.fitted.items():
        # ':' and '-' are fine on POSIX but ':' is not on every filesystem a consumer might use.
        stem = variant_id.replace(":", "__")
        path = save_fit(fit, args.out / f"{stem}.fit.pkl")
        print(f"saved {variant_id} -> {path.name}  (rho {fit.correlation_range_km:.0f} km)")

    listed = write_exclusions(result, args.out / "exclusions.json", data_version=args.data_version)
    print(f"\n{result}")
    print(f"exclusion list: {listed}")
    if result.exclusions:
        print(result.exclusion_frame().to_string(index=False))


if __name__ == "__main__":
    main()
