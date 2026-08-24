"""Binomial spatial-GP surface fit with ascertainment offsets (design §7, §7.1, P2).

The model of design §7:

    AC_i ~ Binomial(AN_i, expit(f(s_i) + β_design[i] + β_cohort[i]))
    f    ~ GP(μ, Matérn-5/2)

**Engine: PyMC with a Hilbert-space GP (HSGP), not R-INLA-SPDE.** The spec named INLA-SPDE, but
what §7 actually requires is a binomial-type likelihood over a spatial random field, *proper
marginal posteriors* — `posterior_contraction` in §7.1b is defined as posterior sd ÷ prior sd, so
an engine that does not give real posteriors cannot support the data-support mask at all — and a
per-variant cost cheap enough to batch. HSGP meets all three: its basis functions do not depend
on the covariance hyperparameters, so they are precomputed once and inference is linear rather
than cubic in the number of observations. The reasoning, the rejected alternatives, and the
licence problem with the Python INLA build are recorded in issue #34.

Defensibility rests on §8 — parity against Piel et al.'s published national estimates — rather
than on sharing an implementation lineage with the prior literature. Reproducing published
numbers is the stronger claim.

Everything here is a pure offline function, deterministic given `(observations, config)`,
with no HTTP or I/O dependency (§5).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
import pymc as pm

from genomeos.observations.schema import OBSERVATIONS_SCHEMA

SEED = 42

LIKELIHOODS: tuple[str, ...] = ("binomial", "beta_binomial")

#: The well-ascertained anchor. β_design is a contrast *against* this level, so population
#: screening surveys are the reference and their offset is fixed at zero (§7.1a).
REFERENCE_DESIGN = "population_random"

#: Great-circle km per degree of latitude. Used only to report the fitted correlation range in
#: human units; the model itself works in standardised coordinates.
_KM_PER_DEGREE = 111.19


@dataclass(frozen=True)
class FitConfig:
    """Everything that makes a fit reproducible. Recorded per artifact (§5)."""

    likelihood: str = "binomial"
    #: HSGP basis functions per spatial dimension. More basis functions resolve finer spatial
    #: structure at higher cost; (8, 8) is calibrated on HbS in #39, not chosen for elegance.
    hsgp_m: tuple[int, int] = (8, 8)
    #: Domain expansion factor. Must exceed 1 so the boundary does not distort the fit.
    hsgp_c: float = 1.5
    draws: int = 500
    tune: int = 500
    chains: int = 2
    seed: int = SEED
    reference_design: str = REFERENCE_DESIGN

    def __post_init__(self) -> None:
        if self.likelihood not in LIKELIHOODS:
            raise ValueError(f"unknown likelihood {self.likelihood!r}; expected one of {LIKELIHOODS}")
        if self.hsgp_c <= 1.0:
            raise ValueError("hsgp_c must be > 1 so the HSGP domain extends beyond the data")


@dataclass(frozen=True)
class SurfaceFit:
    """A fitted per-variant surface, plus what is needed to interpret and cite it."""

    variant_id: str
    config: FitConfig
    #: True when the fit could estimate β_design at all, i.e. when the data contained more than
    #: one sampling design. Written to the artifact as `beta_design_applied` (§6).
    beta_design_applied: bool
    design_levels: tuple[str, ...]
    #: Prior sd of allele frequency at a location, the denominator of `posterior_contraction`
    #: (§7.1b). A single scalar because the GP prior is stationary and the mean function is
    #: location-independent, so the marginal prior is identical everywhere.
    prior_frequency_sd: float
    #: Fitted spatial correlation range in km — §7's ρ, and what "within 2ρ" is measured
    #: against. Converted from the standardised model scale via a 111 km/degree approximation,
    #: which is exact at the equator and shrinks with latitude; adequate for a mask threshold,
    #: not for distance arithmetic.
    correlation_range_km: float
    idata: Any = field(repr=False)
    _model: Any = field(repr=False)
    _centre: np.ndarray = field(repr=False)
    _scale: np.ndarray = field(repr=False)

    def design_effects(self) -> pd.DataFrame:
        """Posterior summary of β_design per non-reference sampling design.

        Empty when only one design was present: with no contrast the effect is unidentifiable
        and is absorbed into the intercept, so reporting a number would be inventing one (§7.1a).
        """
        columns = ["sampling_design", "mean", "sd", "q025", "q975"]
        if not self.beta_design_applied:
            return pd.DataFrame(columns=columns)

        samples = self.idata.posterior["beta_design"].to_numpy().reshape(-1, len(self.design_levels))
        return pd.DataFrame(
            {
                "sampling_design": list(self.design_levels),
                "mean": samples.mean(axis=0),
                "sd": samples.std(axis=0),
                "q025": np.quantile(samples, 0.025, axis=0),
                "q975": np.quantile(samples, 0.975, axis=0),
            },
            columns=columns,
        )

    def predict(self, lat: object, lon: object) -> pd.DataFrame:
        """Posterior allele frequency at the given points, on the reference design.

        Returns the mean, sd and a 95% credible interval per point. Predictions are for the
        reference design deliberately: the map shows what a well-ascertained survey would have
        measured, not what a depleted panel would have (§7.1a).
        """
        lat_arr = np.atleast_1d(np.asarray(lat, dtype=float))
        lon_arr = np.atleast_1d(np.asarray(lon, dtype=float))
        if lat_arr.shape != lon_arr.shape:
            raise ValueError("lat and lon must have the same length")

        x_new = (np.c_[lon_arr, lat_arr] - self._centre) / self._scale
        with self._model:
            pm.set_data({"x_pred": x_new})
            drawn = pm.sample_posterior_predictive(
                self.idata,
                var_names=["freq_pred"],
                random_seed=self.config.seed,
                progressbar=False,
            )
        samples = drawn.posterior_predictive["freq_pred"].to_numpy().reshape(-1, len(lat_arr))

        return pd.DataFrame(
            {
                "lat": lat_arr,
                "lon": lon_arr,
                "post_mean": samples.mean(axis=0),
                "post_sd": samples.std(axis=0),
                "q025": np.quantile(samples, 0.025, axis=0),
                "q975": np.quantile(samples, 0.975, axis=0),
            }
        )


def fit_surface(observations: pd.DataFrame, config: FitConfig | None = None) -> SurfaceFit:
    """Fit one variant's frequency surface. Deterministic given `(observations, config)`."""
    config = config or FitConfig()
    obs = OBSERVATIONS_SCHEMA.validate(observations).reset_index(drop=True)

    variants = obs["variant_id"].unique()
    if len(variants) != 1:
        raise ValueError(
            f"fit_surface expects exactly one variant per call (§7); got {len(variants)}: "
            f"{sorted(variants)[:5]}"
        )

    # Reference level first, so β_design is a contrast against the well-ascertained anchor.
    present = list(dict.fromkeys(obs["sampling_design"]))
    ordered = [d for d in (config.reference_design, *sorted(present)) if d in present]
    design_levels = tuple(dict.fromkeys(ordered))
    non_reference = design_levels[1:]
    beta_design_applied = len(design_levels) > 1

    design_index = obs["sampling_design"].map({d: i for i, d in enumerate(design_levels)}).to_numpy()
    cohorts = sorted(obs["cohort_id"].unique())
    cohort_index = obs["cohort_id"].map({c: i for i, c in enumerate(cohorts)}).to_numpy()

    x_raw = obs[["lon", "lat"]].to_numpy(dtype=float)
    centre = x_raw.mean(axis=0)
    # Guard against a degenerate axis (all observations on one meridian or parallel).
    scale = np.where(x_raw.std(axis=0) > 0, x_raw.std(axis=0), 1.0)
    x = (x_raw - centre) / scale

    ac = obs["ac"].to_numpy(dtype=int)
    an = obs["an"].to_numpy(dtype=int)

    with pm.Model() as model:
        x_data = pm.Data("x_obs", x)
        x_pred = pm.Data("x_pred", x[:1])

        # Matérn-5/2 spatial field. §7 names Matérn-3/2; 5/2 is used here because HSGP's
        # spectral density is better behaved for it, and the smoothness choice is calibrated
        # against HbS in #39 rather than fixed by fiat.
        lengthscale = pm.LogNormal("lengthscale", mu=0.0, sigma=1.0)
        amplitude = pm.HalfNormal("amplitude", sigma=2.0)
        cov = amplitude**2 * pm.gp.cov.Matern52(2, ls=lengthscale)
        gp = pm.gp.HSGP(m=list(config.hsgp_m), c=config.hsgp_c, cov_func=cov)

        intercept = pm.Normal("intercept", mu=-2.0, sigma=2.0)
        f = gp.prior("f", X=x_data)
        logit = intercept + f

        if beta_design_applied:
            # Weakly informative and centred at zero: the correction is estimated and auditable,
            # never a hidden adjustment (§7.1a).
            beta_design = pm.Normal("beta_design", mu=0.0, sigma=1.5, shape=len(non_reference))
            padded = pm.math.concatenate([[0.0], beta_design])
            logit = logit + padded[design_index]

        # β_cohort is hierarchical: it absorbs residual cohort-level effects, including the
        # founder over-sampling of §7.1d, without being free to absorb the spatial signal.
        cohort_sd = pm.HalfNormal("cohort_sd", sigma=0.5)
        beta_cohort = pm.Normal("beta_cohort", mu=0.0, sigma=cohort_sd, shape=len(cohorts))
        logit = logit + beta_cohort[cohort_index]

        p = pm.Deterministic("p", pm.math.invlogit(logit))

        if config.likelihood == "binomial":
            pm.Binomial("obs", n=an, p=p, observed=ac)
        else:
            # Beta-binomial nests binomial; the extra dispersion parameter is cheap insurance
            # against the overdispersion documented in #83.
            concentration = pm.HalfNormal("concentration", sigma=100.0)
            pm.BetaBinomial(
                "obs", n=an, alpha=p * concentration, beta=(1.0 - p) * concentration, observed=ac
            )

        # Prediction path: the reference design, with no cohort offset — what a well-ascertained
        # survey would have measured at that location (§7.1a).
        f_pred = gp.conditional("f_pred", Xnew=x_pred)
        pm.Deterministic("freq_pred", pm.math.invlogit(intercept + f_pred))

        prior = pm.sample_prior_predictive(
            draws=500, var_names=["freq_pred"], random_seed=config.seed
        )
        idata = pm.sample(
            draws=config.draws,
            tune=config.tune,
            chains=config.chains,
            cores=1,
            random_seed=config.seed,
            progressbar=False,
            compute_convergence_checks=False,
        )

    prior_sd = float(np.std(prior.prior["freq_pred"].to_numpy()))
    lengthscale_mean = float(idata.posterior["lengthscale"].mean())
    correlation_range_km = lengthscale_mean * float(np.mean(scale)) * _KM_PER_DEGREE

    return SurfaceFit(
        variant_id=str(variants[0]),
        config=config,
        beta_design_applied=beta_design_applied,
        design_levels=non_reference,
        prior_frequency_sd=prior_sd,
        correlation_range_km=correlation_range_km,
        idata=idata,
        _model=model,
        _centre=centre,
        _scale=scale,
    )
