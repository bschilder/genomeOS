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

**Coordinates are 3-D Cartesian on the unit sphere, not (lon, lat).** An isotropic kernel over
raw or separately-standardised degrees is not isotropic on the Earth: a degree of longitude is
111 km at the equator and 47 km at 65°N, and standardising each axis by its own sample SD makes
the model's notion of "nearby" depend on where surveys happen to be rather than on geography. It
also tears at the antimeridian and degenerates at the poles. Mapping to the unit sphere puts the
kernel in chordal distance, which is monotone in great-circle distance, so `lengthscale` is a
real distance and `correlation_range_km` is just lengthscale × Earth radius.

Everything here is a pure offline function, deterministic given `(observations, config)`,
with no HTTP or I/O dependency (§5).
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pymc as pm
import pytensor.tensor as pt

from genomeos.observations.schema import OBSERVATIONS_SCHEMA

SEED = 42

LIKELIHOODS: tuple[str, ...] = ("binomial", "beta_binomial")


class ConvergenceError(RuntimeError):
    """The sampler did not converge, so this variant yields no surface.

    §12 specifies exactly this: a fit that fails to converge means the variant is excluded from
    the surface set and logged to a published exclusion list. Publishing the draws anyway would
    be the worst available outcome — a non-converged chain produces a confident-looking map, and
    nothing downstream can tell it from a good one.
    """

#: "numpyro" and "blackjax" route through JAX and will use a GPU if one is visible.
NUTS_SAMPLERS: tuple[str, ...] = ("pymc", "numpyro", "blackjax", "nutpie")

#: How the latent field is approximated.
#:
#: ``hsgp`` spans the ambient cube with a rectangular basis. Cost is m^3 and resolution is 2L/m
#: *everywhere*, so most coefficients describe open ocean and the Earth's interior. m=32 buys
#: 32,768 coefficients and still resolves only ~600 km; the 5 km the reference map renders at
#: would need m~3,800, i.e. 5e10 coefficients. It cannot get there, and no GPU changes that.
#:
#: ``inducing`` represents the field by its values at M points placed by clustering the
#: observations, so resolution follows data density rather than a global grid — fine where
#: surveys are dense, absent over empty ocean. Cost is O(N*M^2 + M^3) and is independent of the
#: rendering grid. Same idea as the SPDE meshes §7 originally named: put the degrees of freedom
#: where the data is.
APPROXIMATIONS: tuple[str, ...] = ("hsgp", "inducing")

#: Where inducing points are placed.
#:
#: ``h3`` uses H3 cell centres. H3 is an icosahedral — geodesic — tessellation of the sphere, so
#: spacing is near-uniform with no polar pile-up, placement is deterministic with no seed, and
#: the inducing points *are* the cells §6 already renders. It also lets §7's resolution-promotion
#: rule drive the model and not just the mask: start at res 4 and promote to 5/6 only where
#: observation density supports it.
#:
#: ``kmeans`` clusters the observations instead. Concentrates on data more aggressively, but the
#: placement depends on a seed and does not align with the artifact grid.
INDUCING_PLACEMENTS: tuple[str, ...] = ("h3", "kmeans")

#: Added to the inducing covariance diagonal. Not merely a positive-definiteness guard: with
#: inducing points spaced well inside the correlation range, K_uu is genuinely near-singular
#: (cond ~6e5 at M=400 here) and 1e-6 does not touch it. 1e-4 cuts that ~4x at negligible cost
#: to the model.
JITTER = 1e-4
#: Keeps logit/Beta arithmetic away from the 0 and 1 boundaries in the predictive path.
_EPS = 1e-9

#: Inducing spacing below this fraction of the fitted correlation range means the points are
#: redundant: adjacent ones correlate at ~0.99, so they add parameters without adding
#: information, K_uu approaches singular, and NUTS grinds against a near-degenerate posterior.
#: An M=400 fit at spacing/rho = 0.24 took 80 minutes on a saturated GPU; the same model at
#: spacing/rho ~ 0.65 is 40x better conditioned. More inducing points is not better.
MIN_SPACING_FRACTION = 0.25

#: Ceiling on inducing points as a fraction of observations. Above roughly this, the latent
#: dimension rivals the data and the posterior geometry degrades badly — see the check in
#: `fit_surface`. Not a performance guideline: M=800 against N=857 simply does not converge.
MAX_INDUCING_FRACTION = 0.6

#: The well-ascertained anchor. β_design is a contrast *against* this level, so population
#: screening surveys are the reference and their offset is fixed at zero (§7.1a).
REFERENCE_DESIGN = "population_random"

EARTH_RADIUS_KM = 6371.0088


def to_unit_sphere(lat: object, lon: object) -> np.ndarray:
    """(lat, lon) in degrees -> (x, y, z) on the unit sphere.

    Chordal distance in this space is monotone in great-circle distance, so an isotropic kernel
    here is isotropic on the Earth.
    """
    lat_rad = np.radians(np.asarray(lat, dtype=float))
    lon_rad = np.radians(np.asarray(lon, dtype=float))
    return np.column_stack(
        [
            np.cos(lat_rad) * np.cos(lon_rad),
            np.cos(lat_rad) * np.sin(lon_rad),
            np.sin(lat_rad),
        ]
    )


@dataclass(frozen=True)
class FitConfig:
    """Everything that makes a fit reproducible. Recorded per artifact (§5)."""

    #: Beta-binomial by default, not the binomial §7 specifies. Real surveys of the same
    #: locality disagree far more than binomial sampling error allows — many have AN in the
    #: thousands, which pins p to +-0.002 — so a binomial forces genuine between-survey
    #: heterogeneity into the spatial field and the cohort effects, which cannot represent it.
    #: Measured on the 857-survey HbS fit: binomial gives r_hat 2.61 / ESS 2 with amplitude
    #: running to 11.5; beta-binomial gives r_hat 1.02 / ESS 378 with amplitude 1.79. It is the
    #: difference between a fit and a failure, not a refinement (#83, #103).
    likelihood: str = "beta_binomial"
    approximation: str = "hsgp"
    inducing_placement: str = "h3"
    #: Budget on inducing points. The M^3 Cholesky per leapfrog step is the cost, so this is the
    #: accuracy/cost dial that replaces hsgp_m (#39).
    n_inducing: int = 200
    #: How far beyond the observations to place inducing points, as a multiple of the largest
    #: observation radius. Cells further out get no degrees of freedom, which is the point.
    inducing_reach_km: float = 1500.0
    #: HSGP basis functions per spatial dimension — three dimensions, since the GP lives on the
    #: unit sphere. Cost grows as the product, so this is the accuracy/cost dial calibrated in
    #: #39 rather than a value chosen for elegance.
    hsgp_m: tuple[int, ...] = (6, 6, 6)
    #: Domain expansion factor. Must exceed 1 so the boundary does not distort the fit. The
    #: sphere already lies inside [-1, 1]^3, so this pads it rather than rescaling anything.
    #: HSGP resolution goes as L/m, and L = c x max|x|, so shrinking c from 2.0 to 1.5 buys a
    #: third more spatial resolution at identical cost. 1.5 is the standard recommendation.
    hsgp_c: float = 1.5
    draws: int = 500
    tune: int = 1000
    #: Four, not two. r_hat is a between-chain statistic and is unreliable with two chains —
    #: arviz warns about exactly this — and the convergence gate below is only as trustworthy as
    #: the diagnostic feeding it. numpyro makes the extra chains cheap.
    chains: int = 4
    #: NUTS implementation. Defaults to numpyro, which compiles the model through JAX: on the
    #: 332-survey HbS fit it takes ~15 s where PyMC's own sampler did not finish in 20 minutes,
    #: because the spherical HSGP has a few hundred basis coefficients and PyTensor's Python
    #: loop dominates. The same path runs on a GPU when jax[cuda] is present (#104). "pymc"
    #: remains available and needs no extra install.
    nuts_sampler: str = "numpyro"
    #: Gelman-Rubin ceiling, applied to the *maximum* over every parameter. 1.01 is the modern
    #: standard for a single quantity of interest, but this model has ~1,500 latent parameters
    #: and the max over that many exceeds 1.01 by chance even when sampling is healthy — using
    #: it here rejected a fit with r_hat 1.018 and ESS 378. 1.05 is the classic Gelman-Rubin
    #: cutoff and is the defensible bar for a maximum.
    #: Prior sd of log lengthscale. The default spans roughly 220-3,400 km at 95%, which suits a
    #: variant whose data pins the range down. It does not suit every variant: a correlation range
    #: near the top of that span describes a field that is nearly constant globally, which is
    #: indistinguishable from `intercept` — a ridge the chains can slide along instead of mixing.
    #: G6PD does exactly that (r_hat 1.469 on `lengthscale`, #116), because a phenotype pooling
    #: ~200 alleles has no single spatial scale for the data to identify. Tightening this is a
    #: statement that the field is spatial rather than constant, and must be made deliberately
    #: per variant rather than defaulted, because it is a real prior belief about the biology.
    lengthscale_sigma: float = 0.7
    max_rhat: float = 1.05
    #: Effective sample size floor, per parameter. This is the discriminating statistic: the
    #: binomial fit that produced impossible >0.9 frequencies had ESS 2, the beta-binomial fit
    #: that replaced it has 378.
    min_ess: float = 200.0
    seed: int = SEED
    reference_design: str = REFERENCE_DESIGN

    def __post_init__(self) -> None:
        if self.likelihood not in LIKELIHOODS:
            raise ValueError(f"unknown likelihood {self.likelihood!r}; expected one of {LIKELIHOODS}")
        if self.hsgp_c <= 1.0:
            raise ValueError("hsgp_c must be > 1 so the HSGP domain extends beyond the data")
        if self.lengthscale_sigma <= 0.0:
            raise ValueError("lengthscale_sigma must be > 0")
        if self.max_rhat < 1.0:
            raise ValueError("max_rhat must be >= 1.0")
        if self.approximation not in APPROXIMATIONS:
            raise ValueError(
                f"unknown approximation {self.approximation!r}; expected one of {APPROXIMATIONS}"
            )
        if self.n_inducing < 2:
            raise ValueError("n_inducing must be >= 2")
        if self.inducing_placement not in INDUCING_PLACEMENTS:
            raise ValueError(
                f"unknown inducing_placement {self.inducing_placement!r}; "
                f"expected one of {INDUCING_PLACEMENTS}"
            )
        if self.nuts_sampler not in NUTS_SAMPLERS:
            raise ValueError(
                f"unknown nuts_sampler {self.nuts_sampler!r}; expected one of {NUTS_SAMPLERS}"
            )


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
    #: Median inducing-point spacing divided by the fitted correlation range. Below
    #: `MIN_SPACING_FRACTION` the inducing set is over-dense for the field it represents.
    inducing_spacing_ratio: float | None
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

    def _frequency_samples(self, lat_arr: np.ndarray, lon_arr: np.ndarray) -> np.ndarray:
        """Posterior draws of the latent frequency, shape (draws, points)."""
        x_new = to_unit_sphere(lat_arr, lon_arr)
        with self._model:
            pm.set_data({"x_pred": x_new})
            drawn = pm.sample_posterior_predictive(
                self.idata,
                var_names=["freq_pred"],
                random_seed=self.config.seed,
                progressbar=False,
            )
        return drawn.posterior_predictive["freq_pred"].to_numpy().reshape(-1, len(lat_arr))

    def _posterior_flat(self, name: str) -> np.ndarray:
        """Draws of a scalar parameter, flattened in the same (chain, draw) order as the
        posterior predictive, so the two align draw-for-draw."""
        return self.idata.posterior[name].to_numpy().reshape(-1)

    def predict_draws(self, lat: object, lon: object) -> np.ndarray:
        """Posterior draws of the latent frequency, shape ``(draws, points)`` (#112).

        `predict` summarises these into medians and quantiles; the burden path needs the draws
        themselves, and cannot be written any other way. A national total is a sum over cells
        *within* a draw, and the summary of a sum is not a function of the summaries of its
        terms — medians in particular do not sum, a shortfall #92 measures at 4-7% against Piel
        et al.'s own national medians, which is the size of error that reads as model failure.

        This exposes draws `predict` already computes rather than running new inference.
        """
        lat_arr = np.atleast_1d(np.asarray(lat, dtype=float))
        lon_arr = np.atleast_1d(np.asarray(lon, dtype=float))
        if lat_arr.shape != lon_arr.shape:
            raise ValueError("lat and lon must have the same length")
        return self._frequency_samples(lat_arr, lon_arr)

    def predict_observation(self, lat: object, lon: object, an: object) -> pd.DataFrame:
        """Posterior predictive for a **new survey** of `an` alleles at each point (§7; #110).

        `predict` describes the latent frequency — what the map claims about a place. This
        describes what a new survey there would actually measure, which is the quantity a
        calibration check must score against. It restores the two variance components the latent
        interval deliberately omits:

        - **a cohort offset**, drawn fresh from ``Normal(0, cohort_sd)``. A held-out survey
          belongs to a cohort the model never saw, so reusing a fitted ``cohort_z`` would leak
          information across the split and understate the interval.
        - **overdispersed sampling** of `an` alleles, through the same beta-binomial the
          likelihood uses. A beta-binomial draw is exactly ``p ~ Beta(alpha, beta)`` followed by
          ``Binomial(n, p)``, so it composes in numpy without rebuilding the model.

        Scoring observed frequencies against `predict`'s interval instead is the defect in #110:
        it compares an interval for a mean against a noisy realisation of that mean, and
        under-covers by construction however good the model is.
        """
        lat_arr = np.atleast_1d(np.asarray(lat, dtype=float))
        lon_arr = np.atleast_1d(np.asarray(lon, dtype=float))
        an_arr = np.atleast_1d(np.asarray(an, dtype=float))
        if not lat_arr.shape == lon_arr.shape == an_arr.shape:
            raise ValueError("lat, lon and an must have the same length")
        if (an_arr <= 0).any():
            raise ValueError("an must be positive; a survey of nobody has no predictive interval")

        rng = np.random.default_rng(self.config.seed)
        freq = np.clip(self._frequency_samples(lat_arr, lon_arr), _EPS, 1.0 - _EPS)

        cohort_sd = self._posterior_flat("cohort_sd")
        if len(cohort_sd) != len(freq):
            raise RuntimeError(
                f"posterior has {len(cohort_sd)} draws but the predictive has {len(freq)}; "
                "they must align draw-for-draw"
            )
        logit = np.log(freq / (1.0 - freq)) + rng.normal(
            0.0, np.broadcast_to(cohort_sd[:, None], freq.shape)
        )
        p = np.clip(1.0 / (1.0 + np.exp(-logit)), _EPS, 1.0 - _EPS)

        if self.config.likelihood == "beta_binomial":
            concentration = self._posterior_flat("concentration")[:, None]
            p = np.clip(rng.beta(p * concentration, (1.0 - p) * concentration), _EPS, 1.0 - _EPS)
        replicated = rng.binomial(np.rint(an_arr).astype(np.int64), p) / an_arr

        return pd.DataFrame(
            {
                "lat": lat_arr,
                "lon": lon_arr,
                "an": an_arr,
                "pred_median": np.median(replicated, axis=0),
                "pred_q025": np.quantile(replicated, 0.025, axis=0),
                "pred_q975": np.quantile(replicated, 0.975, axis=0),
                "pred_q25": np.quantile(replicated, 0.25, axis=0),
                "pred_q75": np.quantile(replicated, 0.75, axis=0),
            }
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

        samples = self._frequency_samples(lat_arr, lon_arr)

        return pd.DataFrame(
            {
                "lat": lat_arr,
                "lon": lon_arr,
                # The median is the defensible central estimate for this quantity, and the
                # reference we are scored against reports medians (see #102). Allele frequency
                # is bounded in [0, 1] and the inverse-logit link gives its posterior a long
                # right tail wherever the latent field is uncertain, so the mean is dragged
                # upward exactly where there is least data. Piel et al.'s own appendix records
                # hitting this: "the long right-hand tail ... contained enough mass to skew all
                # of the standard summary statistics."
                "post_median": np.median(samples, axis=0),
                "post_mean": samples.mean(axis=0),
                "post_sd": samples.std(axis=0),
                "q025": np.quantile(samples, 0.025, axis=0),
                "q975": np.quantile(samples, 0.975, axis=0),
                "q25": np.quantile(samples, 0.25, axis=0),
                "q75": np.quantile(samples, 0.75, axis=0),
            }
        )


def h3_inducing_points(
    lat: np.ndarray,
    lon: np.ndarray,
    n_inducing: int,
    reach_km: float,
) -> np.ndarray:
    """Inducing points on the H3 geodesic sphere, promoted where observations are dense.

    H3 tiles the sphere by subdividing an icosahedron, so cells are near-uniform in area and
    there is no polar pile-up — the failure mode of a lat/lon grid, where cells collapse to
    slivers at the poles and the model spends degrees of freedom on the Arctic. The inducing
    points are then the same cells §6 renders.

    Cells are seeded at the coarse end of §6's ladder within `reach_km` of an observation, then
    promoted to their children where the local observation count justifies it — §7's
    resolution-promotion rule applied to the *model* and not only to the mask.

    **Selection is by distance to the nearest observation, never by H3 index order.** Truncating
    a sorted index is geographically arbitrary: it once selected a contiguous block on a single
    icosahedral face, putting every inducing point in the Arctic a median 8,800 km from the data
    while looking beautifully uniform. Uniform spacing is necessary and nowhere near sufficient.
    """
    import h3

    from genomeos.geo.h3util import RESOLUTION_LADDER, _haversine_km, cells_within_km

    lat = np.asarray(lat, dtype=float)
    lon = np.asarray(lon, dtype=float)
    base, *finer = RESOLUTION_LADDER

    cells: set[str] = set()
    for point_lat, point_lon in zip(lat, lon, strict=True):
        cells.update(cells_within_km(float(point_lat), float(point_lon), reach_km, base))

    # Promote the cells holding the most observations: that is where finer resolution can
    # actually be identified from the data.
    for resolution in finer:
        if len(cells) >= n_inducing:
            break
        density: dict[str, int] = {}
        for point_lat, point_lon in zip(lat, lon, strict=True):
            cell = h3.latlng_to_cell(float(point_lat), float(point_lon), resolution - 1)
            density[cell] = density.get(cell, 0) + 1
        for parent in sorted(density, key=lambda c: -density[c]):
            if len(cells) >= n_inducing or parent not in cells:
                continue
            cells.discard(parent)
            cells.update(h3.cell_to_children(parent, resolution))

    centres = np.array([h3.cell_to_latlng(cell) for cell in sorted(cells)], dtype=float)
    if len(centres) == 0:
        raise ValueError("no H3 cells within reach of the observations")

    # Rank by distance to the nearest observation and keep the closest.
    distance = _haversine_km(
        centres[:, 0][:, None], centres[:, 1][:, None], lat[None, :], lon[None, :]
    ).min(axis=1)
    keep = np.argsort(distance)[:n_inducing]
    centres = centres[keep]
    return to_unit_sphere(centres[:, 0], centres[:, 1])


def inducing_points(x: np.ndarray, n_inducing: int, seed: int) -> np.ndarray:
    """Choose inducing locations on the unit sphere by clustering the observations.

    Clustering rather than gridding is the whole point: it puts the field's degrees of freedom
    where measurements are, so West Africa and the Indian tribal belt get fine spacing while the
    Pacific gets none. Centroids are re-projected onto the sphere, since the mean of points on a
    sphere lies inside it.
    """
    from scipy.cluster.vq import kmeans2

    n_inducing = min(n_inducing, len(x))
    centroids, _ = kmeans2(x, n_inducing, minit="++", seed=seed, iter=40)
    centroids = centroids[np.isfinite(centroids).all(axis=1)]
    norms = np.linalg.norm(centroids, axis=1)
    return centroids[norms > 0] / norms[norms > 0, None]


def _check_convergence(idata, config: FitConfig) -> None:
    """Raise unless every parameter mixed, naming the parameter that failed.

    The offending parameter is part of the message because it changes the diagnosis entirely.
    A starved `concentration` or `cohort_sd` is a reparameterisation problem and cheap to fix; a
    starved `z_u` is the spatial field itself failing and usually means the inducing set or the
    sampling budget is wrong. Without the name, every failure looks like "buy more draws" (#111).
    """
    import arviz as az

    rhat = az.rhat(idata)
    ess = az.ess(idata)
    worst_rhat, rhat_var = -np.inf, "?"
    for name in rhat.data_vars:
        value = float(np.nanmax(rhat[name].to_numpy()))
        if not np.isfinite(value) or value > worst_rhat:
            worst_rhat, rhat_var = value, name
    worst_ess, ess_var = np.inf, "?"
    for name in ess.data_vars:
        value = float(np.nanmin(ess[name].to_numpy()))
        if not np.isfinite(value) or value < worst_ess:
            worst_ess, ess_var = value, name

    problems = []
    if not np.isfinite(worst_rhat) or worst_rhat > config.max_rhat:
        problems.append(f"r_hat {worst_rhat:.3f} > {config.max_rhat} (worst: {rhat_var})")
    if not np.isfinite(worst_ess) or worst_ess < config.min_ess:
        problems.append(
            f"effective sample size {worst_ess:.0f} < {config.min_ess:.0f} (worst: {ess_var})"
        )
    if problems:
        raise ConvergenceError(
            "sampler did not converge (" + "; ".join(problems) + "). "
            "Per §12 this variant is excluded from the surface set rather than published."
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

    # No per-axis standardisation: the unit sphere is already the right scale in all three
    # dimensions, and rescaling axes independently is what made the kernel anisotropic.
    x = to_unit_sphere(obs["lat"], obs["lon"])
    centre = np.zeros(3)
    scale = np.ones(3)

    ac = obs["ac"].to_numpy(dtype=int)
    an = obs["an"].to_numpy(dtype=int)

    if config.approximation == "inducing" and config.n_inducing > MAX_INDUCING_FRACTION * len(obs):
        raise ValueError(
            f"n_inducing={config.n_inducing} is too close to the {len(obs)} observations. A sparse "
            f"approximation needs M well below N: at M=800 against N=857 the model carries more "
            f"latent parameters than data points, NUTS hits maximum tree depth fighting the "
            f"geometry, and a fit that converges in minutes at M=400 does not converge at all. "
            f"Keep n_inducing <= {int(MAX_INDUCING_FRACTION * len(obs))} here, or add data."
        )

    if config.approximation != "inducing":
        inducing = np.zeros((0, 3))
    elif config.inducing_placement == "h3":
        inducing = h3_inducing_points(
            obs["lat"].to_numpy(), obs["lon"].to_numpy(),
            config.n_inducing, config.inducing_reach_km,
        )
    else:
        inducing = inducing_points(x, config.n_inducing, config.seed)

    with pm.Model() as model:
        x_data = pm.Data("x_obs", x)
        x_pred = pm.Data("x_pred", x[:1])

        # Matérn-5/2 spatial field. §7 names Matérn-3/2; 5/2 is used here because HSGP's
        # spectral density is better behaved for it, and the smoothness choice is calibrated
        # against HbS in #39 rather than fixed by fiat.
        # Chordal units on the unit sphere: exp(-2.0) ~ 0.135 ~ 860 km, a scale consistent with
        # the continental structure the surveys show.
        lengthscale = pm.LogNormal("lengthscale", mu=-2.0, sigma=config.lengthscale_sigma)
        # The logit-scale field only needs to span roughly [-10, -1.4] to cover 0 to 0.2. Left
        # looser, the amplitude ran to 11.7 — enough to saturate invlogit at 0 and 1 and produce
        # the impossible >0.9 blobs. See #103.
        amplitude = pm.HalfNormal("amplitude", sigma=1.0)

        # The level lives in the GP's mean function rather than as a separate additive term.
        # A free intercept *plus* a zero-mean GP that can absorb any constant is two parameters
        # for one quantity: the chains wander along that ridge (r_hat 1.82 was observed) and the
        # amplitude inflates to cover the slop.
        intercept = pm.Normal("intercept", mu=-3.5, sigma=1.5)

        cov = amplitude**2 * pm.gp.cov.Matern52(3, ls=lengthscale)

        if config.approximation == "hsgp":
            gp = pm.gp.HSGP(
                m=list(config.hsgp_m),
                c=config.hsgp_c,
                cov_func=cov,
                mean_func=pm.gp.mean.Constant(intercept),
            )
            f = gp.prior("f", X=x_data)
            f_pred_expr = None
        else:
            # Sparse GP over inducing points, deterministic training conditional:
            #     u = L z,   f = K_fu K_uu^-1 u = K_fu L^-T z
            # Expressed as L^-T z rather than a solve against K_uu: one Cholesky per step, and
            # better conditioned. z is unit-normal, so this is non-centred by construction — the
            # same reason the cohort effects are (Neal's funnel).
            inducing_t = pt.as_tensor_variable(inducing)
            z_u = pm.Normal("z_u", mu=0.0, sigma=1.0, shape=len(inducing))
            chol_uu = pt.linalg.cholesky(cov(inducing_t) + JITTER * pt.eye(len(inducing)))
            weights = pt.linalg.solve_triangular(chol_uu.T, z_u, lower=False)
            f = pm.Deterministic("f", intercept + cov(x_data, inducing_t) @ weights)
            # Prediction reuses the identical expression, so there is no second code path that
            # can silently disagree with the training one.
            f_pred_expr = intercept + cov(x_pred, inducing_t) @ weights

        logit = f

        if beta_design_applied:
            # Weakly informative and centred at zero: the correction is estimated and auditable,
            # never a hidden adjustment (§7.1a).
            beta_design = pm.Normal("beta_design", mu=0.0, sigma=1.5, shape=len(non_reference))
            padded = pm.math.concatenate([[0.0], beta_design])
            logit = logit + padded[design_index]

        # β_cohort is hierarchical: it absorbs residual cohort-level effects, including the
        # founder over-sampling of §7.1d, without being free to absorb the spatial signal.
        #
        # Non-centred. Written as Normal(0, cohort_sd) this is Neal's funnel: small values of
        # cohort_sd force small effects, pinching the posterior into a geometry NUTS cannot
        # traverse. With 344 cohorts that was fatal — r_hat 2.7, ESS 2. Sampling a unit normal
        # and scaling it decouples the scale from the effects. (PyMC's HSGP already
        # non-centres its own coefficients by default; the cohort term needed the same.)
        cohort_sd = pm.HalfNormal("cohort_sd", sigma=0.5)
        cohort_z = pm.Normal("cohort_z", mu=0.0, sigma=1.0, shape=len(cohorts))
        beta_cohort = pm.Deterministic("beta_cohort", cohort_sd * cohort_z)
        logit = logit + beta_cohort[cohort_index]

        p = pm.Deterministic("p", pm.math.invlogit(logit))

        if config.likelihood == "binomial":
            pm.Binomial("obs", n=an, p=p, observed=ac)
        else:
            # Beta-binomial nests binomial: large concentration recovers it, so the data decide
            # how much overdispersion there is. The fitted value on HbS is ~36.
            concentration = pm.HalfNormal("concentration", sigma=100.0)
            pm.BetaBinomial(
                "obs", n=an, alpha=p * concentration, beta=(1.0 - p) * concentration, observed=ac
            )

        # Prediction path: the reference design, with no cohort offset — what a well-ascertained
        # survey would have measured at that location (§7.1a).
        if f_pred_expr is None:
            f_pred_expr = gp.conditional("f_pred", Xnew=x_pred)
        pm.Deterministic("freq_pred", pm.math.invlogit(f_pred_expr))

        prior = pm.sample_prior_predictive(
            draws=500, var_names=["freq_pred"], random_seed=config.seed
        )
        sample_kwargs: dict[str, Any] = {
            "draws": config.draws,
            "tune": config.tune,
            "chains": config.chains,
            "random_seed": config.seed,
            "progressbar": False,
        }
        if config.nuts_sampler == "pymc":
            # Deterministic given the seed only when chains are drawn sequentially.
            sample_kwargs["cores"] = 1
        else:
            sample_kwargs["nuts_sampler"] = config.nuts_sampler
            # chain_method="vectorized" batches every chain into one device. The default,
            # "parallel", wants one device per chain and silently falls back to drawing them
            # *sequentially* when there is only one — which is what a single GPU looks like, so
            # three quarters of the available speedup was being left on the table with a warning
            # that reads like a note about CPUs.
            sample_kwargs["nuts"] = {"chain_method": "vectorized"}
        idata = pm.sample(**sample_kwargs)

    _check_convergence(idata, config)

    prior_sd = float(np.std(prior.prior["freq_pred"].to_numpy()))
    # Chordal lengthscale on the unit sphere -> great-circle km. Exact for the chord; the
    # great-circle equivalent differs by <1% for ranges under ~1,500 km.
    lengthscale_mean = float(idata.posterior["lengthscale"].mean())
    correlation_range_km = lengthscale_mean * EARTH_RADIUS_KM

    spacing_ratio = None
    if len(inducing) > 1:
        gaps = np.linalg.norm(inducing[:, None, :] - inducing[None, :, :], axis=-1)
        np.fill_diagonal(gaps, np.inf)
        median_spacing_km = float(np.median(gaps.min(axis=1))) * EARTH_RADIUS_KM
        spacing_ratio = median_spacing_km / max(correlation_range_km, 1e-9)
        if spacing_ratio < MIN_SPACING_FRACTION:
            warnings.warn(
                f"inducing points are {median_spacing_km:.0f} km apart against a fitted "
                f"correlation range of {correlation_range_km:.0f} km "
                f"(ratio {spacing_ratio:.2f} < {MIN_SPACING_FRACTION}). They are redundant: "
                f"adjacent points correlate at ~0.99, K_uu is near-singular, and sampling will "
                f"be far slower than a smaller n_inducing. Reduce n_inducing.",
                stacklevel=2,
            )

    return SurfaceFit(
        variant_id=str(variants[0]),
        config=config,
        beta_design_applied=beta_design_applied,
        design_levels=non_reference,
        prior_frequency_sd=prior_sd,
        inducing_spacing_ratio=spacing_ratio,
        correlation_range_km=correlation_range_km,
        idata=idata,
        _model=model,
        _centre=centre,
        _scale=scale,
    )


#: Bumped whenever `SurfaceFit`'s fields change in a way that makes an older file unreadable.
FIT_FORMAT = 1


def save_fit(fit: SurfaceFit, path: str | Path) -> Path:
    """Persist a trained surface so predictions cost seconds instead of a refit.

    `SurfaceFit.predict` runs `sample_posterior_predictive` against a live PyMC model, so the
    model object and the posterior have to travel together — writing the InferenceData alone
    would leave nothing able to use it. cloudpickle handles the PyMC/pytensor graph that plain
    `pickle` cannot.

    Two limits worth knowing. The file is **coupled to this environment**: a PyMC or pytensor
    upgrade can make it unreadable, so it is a cache, never an archival artifact — §6 artifacts
    are the parquet outputs, not this. And pickle executes arbitrary code on load, so only ever
    load files you produced yourself.
    """
    import cloudpickle

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as stream:
        cloudpickle.dump({"format": FIT_FORMAT, "fit": fit}, stream)
    return path


def load_fit(path: str | Path) -> SurfaceFit:
    """Reload a surface written by `save_fit`. See its warning about trust and versioning."""
    import cloudpickle

    with Path(path).open("rb") as stream:
        payload = cloudpickle.load(stream)
    if not isinstance(payload, dict) or payload.get("format") != FIT_FORMAT:
        raise ValueError(
            f"{path} is not a surface fit of format {FIT_FORMAT}; refit rather than guessing at it"
        )
    return payload["fit"]
