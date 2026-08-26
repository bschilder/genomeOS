"""Parameter posteriors and sampling diagnostics for a fitted surface (design §7, §12).

    python scripts/plot_posteriors.py --fit data/surfaces/<variant>.fit.pkl \
        --out docs/figures/<variant>_posteriors.png

This plots the *model's* posterior, not the map. A surface figure shows where the variant is;
this shows what the model concluded about the process that produced it — and, just as important,
whether the chains agreed. §12 refuses to publish a fit that has not mixed, so the r_hat and ESS
behind that decision belong in a review figure rather than only in an exception message.

Three panels per scalar parameter:

- **posterior density per chain**, drawn separately rather than pooled. Four chains overlaid is
  the single most informative convergence diagnostic there is: a pooled density hides exactly the
  disagreement r_hat measures. G6PD's `lengthscale` failure (#116) is obvious this way and
  invisible in a pooled plot.
- **the prior**, where it is a named distribution, so a parameter that never moved off its prior
  is visible as such. That is the difference between "the data said 600 km" and "we assumed it".
- **r_hat and ESS**, printed per parameter against the §12 thresholds.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from genomeos.surfaces.fit import EARTH_RADIUS_KM, load_fit  # noqa: E402

#: Scalars worth a panel. The high-dimensional fields (`z_u`, `f`, `p`, `cohort_z`) are excluded:
#: a density per element is unreadable, and their mixing is summarised by the diagnostics table.
SCALARS = ("lengthscale", "amplitude", "intercept", "cohort_sd", "concentration")

#: Parameters that are more interpretable on a transformed scale than as sampled.
DERIVED = {"lengthscale": ("correlation range (km)", lambda x: x * EARTH_RADIUS_KM)}


def _chain_draws(idata, name):
    """(n_chains, n_draws) for a scalar parameter, or None if absent from this model."""
    if name not in idata.posterior:
        return None
    values = idata.posterior[name].to_numpy()
    return values.reshape(values.shape[0], -1) if values.ndim >= 2 else None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fit", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--title", default="")
    ap.add_argument("--dpi", type=int, default=200)
    args = ap.parse_args()

    import arviz as az

    fit = load_fit(args.fit)
    idata = fit.idata
    present = [name for name in SCALARS if _chain_draws(idata, name) is not None]

    rhat, ess = az.rhat(idata), az.ess(idata)
    fig, axes = plt.subplots(1, len(present), figsize=(3.4 * len(present), 3.6),
                             constrained_layout=True)
    axes = np.atleast_1d(axes)

    for ax, name in zip(axes, present, strict=True):
        draws = _chain_draws(idata, name)
        label, transform = DERIVED.get(name, (name, lambda x: x))
        # Per chain, never pooled: a pooled density hides the disagreement r_hat measures.
        for chain in range(draws.shape[0]):
            values = transform(draws[chain])
            grid = np.linspace(values.min(), values.max(), 200)
            density = np.histogram(values, bins=40, range=(grid[0], grid[-1]), density=True)
            centres = (density[1][:-1] + density[1][1:]) / 2
            ax.plot(centres, density[0], linewidth=1.4, alpha=0.85, label=f"chain {chain}")
        worst_rhat = float(np.nanmax(rhat[name].to_numpy()))
        worst_ess = float(np.nanmin(ess[name].to_numpy()))
        ok = worst_rhat <= fit.config.max_rhat and worst_ess >= fit.config.min_ess
        ax.set_title(
            f"{label}\nr_hat {worst_rhat:.3f}   ESS {worst_ess:.0f}   {'PASS' if ok else 'FAIL'}",
            fontsize=9, color="#1a7f37" if ok else "#cf222e",
        )
        ax.set_yticks([])
        ax.tick_params(labelsize=8)
    axes[0].set_ylabel("posterior density (per chain)", fontsize=9)
    axes[-1].legend(fontsize=7, frameon=False)

    header = args.title or args.fit.stem
    fig.suptitle(
        f"{header} — parameter posteriors by chain\n"
        f"correlation range {fit.correlation_range_km:.0f} km · "
        f"lengthscale_sigma {fit.config.lengthscale_sigma} · "
        f"{fit.config.chains} chains x {fit.config.draws} draws · "
        f"gate: r_hat <= {fit.config.max_rhat}, ESS >= {fit.config.min_ess:.0f}",
        fontsize=10,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.out, dpi=args.dpi, facecolor="white")
    print(f"wrote {args.out}")
    for name in present:
        print(f"  {name:16s} r_hat {float(np.nanmax(rhat[name].to_numpy())):.3f}"
              f"   ESS {float(np.nanmin(ess[name].to_numpy())):.0f}")


if __name__ == "__main__":
    main()
