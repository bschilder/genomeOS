"""Screen many AFND alleles through the pipeline to find where it breaks (design §12; #40).

    python scripts/screen_alleles.py --frequencies data/raw/afnd.tsv \
        --populations data/raw/afnd_populations.tsv --out data/store/screen --top 12

This is a **diagnostic sweep, not a publication run**. It fits a set of alleles at a deliberately
modest draw budget and treats every failure as a result: a variant that will not converge, or
converges to something implausible, tells us more about the pipeline than one that fits quietly.
§12's published exclusion list is the primary output.

Chosen deliberately over fitting one allele carefully: HbS and G6PD are two variants and both were
curated by hand, so the pipeline's behaviour on *arbitrary* input is unmeasured. AFND supplies 767
alleles with the same shape and none of the curation.

A posterior figure is written per fitted allele, because the parameter that fails is what
distinguishes a budget problem from a mis-specified model — the distinction that took three pod
runs to establish for G6PD (#116).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from genomeos.observations.sources import afnd_frequencies as afnd_freq
from genomeos.surfaces.batch import VariantJob, run_batch, write_exclusions
from genomeos.surfaces.fit import FitConfig, save_fit


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frequencies", type=Path, required=True)
    ap.add_argument("--populations", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--top", type=int, default=12, help="alleles by population coverage")
    ap.add_argument("--min-populations", type=int, default=30)
    ap.add_argument("--draws", type=int, default=400)
    ap.add_argument("--n-inducing", type=int, default=150)
    ap.add_argument("--data-version", default="afnd-2026-08")
    args = ap.parse_args()

    observations, report = afnd_freq.load(
        args.frequencies, args.populations, args.data_version,
        min_populations=args.min_populations,
    )
    print(report, "\n")

    coverage = observations.groupby("variant_id")["population_id"].nunique().sort_values(
        ascending=False
    )
    chosen = list(coverage.head(args.top).index)
    print(f"screening {len(chosen)} of {len(coverage)} alleles, by population coverage:")
    for variant_id in chosen:
        print(f"  {variant_id:<24} {coverage[variant_id]:4d} populations")

    config = FitConfig(
        draws=args.draws, tune=args.draws, approximation="inducing", n_inducing=args.n_inducing
    )
    jobs = [
        VariantJob(
            variant_id=variant_id,
            observations=observations[observations["variant_id"] == variant_id].reset_index(
                drop=True
            ),
            config=config,
        )
        for variant_id in chosen
    ]

    args.out.mkdir(parents=True, exist_ok=True)
    result = run_batch(
        jobs, on_progress=lambda v, n: print(f"----- {v} ({n} obs) -----", flush=True)
    )

    summary = {}
    for variant_id, fit in result.fitted.items():
        stem = variant_id.replace(":", "__")
        save_fit(fit, args.out / f"{stem}.fit.pkl")
        summary[variant_id] = {
            "correlation_range_km": round(float(fit.correlation_range_km), 1),
            "prior_frequency_sd": round(float(fit.prior_frequency_sd), 5),
            "n_observations": len(jobs[chosen.index(variant_id)].observations),
            "inducing_spacing_ratio": (
                round(float(fit.inducing_spacing_ratio), 3)
                if fit.inducing_spacing_ratio is not None
                else None
            ),
        }
        print(f"  fitted {variant_id}: rho {fit.correlation_range_km:.0f} km", flush=True)

    write_exclusions(result, args.out / "exclusions.json", data_version=args.data_version)
    (args.out / "fitted.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(f"\n{result}")
    if result.exclusions:
        print(result.exclusion_frame().to_string(index=False))


if __name__ == "__main__":
    main()
