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
from dataclasses import replace
from pathlib import Path

import pandas as pd

from genomeos.observations.sources import map_g6pd, map_surveys
from genomeos.surfaces.batch import jobs_from_sources, run_batch, write_exclusions
from genomeos.surfaces.fit import FitConfig, save_fit

#: Loaders keyed by the CLI flag that supplies their export.
LAYERS = {"hbs": map_surveys.load, "g6pd": map_g6pd.load}

#: Per-variant prior sd on log lengthscale, where the default does not suit the variant.
#:
#: This is a **prior belief about the biology stated per variant**, not a tuning knob, so it lives
#: here in the open rather than in a CLI flag someone forgets to pass. The default (0.7, roughly
#: 220-3,400 km at 95%) suits a variant whose data pins the correlation range down; HbS does, and
#: is deliberately absent from this table.
#:
#: G6PD does not. Its deficiency phenotype pools ~200 alleles with different geographic origins —
#: A- across Africa, Mediterranean through the Middle East and South Asia, Mahidol in Southeast
#: Asia — so no single spatial scale describes their sum, and the chains slide along the ridge
#: where a very long lengthscale is indistinguishable from `intercept`. Measured: r_hat 1.469 at
#: the default, versus r_hat passing and ESS rising 8 -> 111 at 0.4 with everything else equal
#: (#116). Narrowing the prior asserts the field is spatial rather than constant; it does not
#: assert the composite is a good model, which #116 still questions.
LENGTHSCALE_SIGMA: dict[str, float] = {"phenotype:g6pd-deficiency": 0.4}


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
    jobs = [
        replace(job, config=replace(job.config, lengthscale_sigma=sigma))
        if (sigma := LENGTHSCALE_SIGMA.get(job.variant_id)) is not None
        else job
        for job in jobs_from_sources(sources, config)
    ]
    print(f"===== fitting {len(jobs)} variants =====")
    for job in jobs:
        print(
            f"  {job.variant_id}: {len(job.observations)} observations, "
            f"lengthscale_sigma={job.config.lengthscale_sigma}"
        )

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
