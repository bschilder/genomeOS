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
from typing import Any

import numpy as np
import pandas as pd
import pymc as pm
import pytensor.tensor as pt

from genomeos.observations.schema import OBSERVATIONS_SCHEMA
from genomeos.surfaces.config import APPROXIMATIONS as APPROXIMATIONS
from genomeos.surfaces.config import EARTH_RADIUS_KM as EARTH_RADIUS_KM
from genomeos.surfaces.config import INDUCING_PLACEMENTS as INDUCING_PLACEMENTS
from genomeos.surfaces.config import JITTER as JITTER
from genomeos.surfaces.config import LENGTHSCALE_PRIORS as LENGTHSCALE_PRIORS
from genomeos.surfaces.config import LENGTHSCALE_REGIONS as LENGTHSCALE_REGIONS
from genomeos.surfaces.config import LIKELIHOODS as LIKELIHOODS
from genomeos.surfaces.config import MAX_INDUCING_FRACTION as MAX_INDUCING_FRACTION
from genomeos.surfaces.config import MAX_LENGTHSCALE_ANCHOR_KM as MAX_LENGTHSCALE_ANCHOR_KM
from genomeos.surfaces.config import MIN_LENGTHSCALE_ANCHOR_KM as MIN_LENGTHSCALE_ANCHOR_KM
from genomeos.surfaces.config import MIN_SPACING_FRACTION as MIN_SPACING_FRACTION
from genomeos.surfaces.config import NUTS_SAMPLERS as NUTS_SAMPLERS
from genomeos.surfaces.config import REFERENCE_DESIGN as REFERENCE_DESIGN
from genomeos.surfaces.config import SEED as SEED
from genomeos.surfaces.config import FitConfig as FitConfig
from genomeos.surfaces.observation import (
    ObservationModelMetadata,
    ObservationParameters,
    SurveyQueries,
)


class ConvergenceError(RuntimeError):
    """The sampler did not converge, so this variant yields no surface.

    §12 specifies exactly this: a fit that fails to converge means the variant is excluded from
    the surface set and logged to a published exclusion list. Publishing the draws anyway would
    be the worst available outcome — a non-converged chain produces a confident-looking map, and
    nothing downstream can tell it from a good one.
    """

#: Keeps logit/Beta arithmetic away from the 0 and 1 boundaries in the predictive path.
_EPS = 1e-9


def derive_lengthscale_prior(lat: np.ndarray, lon: np.ndarray) -> tuple[float, float, float, float]:
    """A LogNormal prior on lengthscale, derived from where the observations actually are.

    Returns ``(mu, sigma, lower_km, upper_km)`` with mu and sigma in the chordal units the kernel
    uses, and the two anchors in km for the record.

    The fixed prior this replaces (`LogNormal(-2.0, 0.7)`, median 861 km) cannot be right for every
    variant, and hand-setting it per variant does not survive 767 alleles (#122). Two anchors, both
    read off the data:

    - **lower** — three times the median nearest-neighbour spacing. Below that there are not enough
      distinct separations for correlation decay to be visible at all.
    - **upper** — the domain extent divided by ``2 * LENGTHSCALE_REGIONS``. Above it the field
      barely varies across the region the data covers, which is #116's degenerate regime where a
      long range is indistinguishable from the intercept.

    The prior is centred on the geometric mean of the two and spread so ~95% of its mass lies
    between them. Note what this does *not* do: it never forbids a range, it only makes an
    implausible one expensive. A variant with genuinely global structure can still reach it if the
    data insists.
    """
    lat_arr = np.asarray(lat, dtype=float)
    lon_arr = np.asarray(lon, dtype=float)
    if len(lat_arr) < 2:
        raise ValueError("a lengthscale prior needs at least two observation locations")

    distance = _haversine_matrix(lat_arr, lon_arr)
    np.fill_diagonal(distance, np.inf)
    nearest = float(np.median(distance.min(axis=1)))
    np.fill_diagonal(distance, 0.0)
    extent = float(np.quantile(distance, 0.95))

    upper = min(extent / (2.0 * LENGTHSCALE_REGIONS), MAX_LENGTHSCALE_ANCHOR_KM)
    lower = max(3.0 * nearest, MIN_LENGTHSCALE_ANCHOR_KM)
    if not lower < upper:
        # Sparse or tightly clustered data, where the spacing floor meets the physical ceiling.
        # Back the lower anchor off rather than inverting the prior or letting it run to a range
        # longer than the planet.
        lower = upper / 10.0
    mu = float(np.log(np.sqrt(lower * upper) / EARTH_RADIUS_KM))
    sigma = float(np.log(upper / lower) / (2.0 * 1.96))
    return mu, sigma, lower, upper


def _haversine_matrix(lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    """Pairwise great-circle distances in km."""
    rlat, rlon = np.radians(lat), np.radians(lon)
    dlat = rlat[:, None] - rlat[None, :]
    dlon = rlon[:, None] - rlon[None, :]
    a = np.sin(dlat / 2) ** 2 + np.cos(rlat)[:, None] * np.cos(rlat)[None, :] * np.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


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
class SurfaceFit:
    """A fitted per-variant surface, plus what is needed to interpret and cite it."""

    variant_id: str
    config: FitConfig
    #: True when the fit could estimate β_design at all, i.e. when the data contained more than
    #: one sampling design. Written to the artifact as `beta_design_applied` (§6).
    beta_design_applied: bool
    #: The 95% anchors of the lengthscale prior in km, or NaN when it was fixed. Recorded because
    #: a fitted range is only interpretable against the prior that produced it, and under a derived
    #: prior that differs per variant.
    lengthscale_prior_km: tuple[float, float]
    #: True when the cohort effect was estimated at all. False when the source gives one cohort
    #: per observation, which is not a cohort effect but an observation-level overdispersion term
    #: — see the note in `fit_surface`.
    beta_cohort_applied: bool
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
    prediction_metadata: ObservationModelMetadata | None = None

    def predict_new_cohort_parameters(
        self, queries: SurveyQueries, *, seed: int = SEED
    ) -> ObservationParameters:
        """Return draw-aligned parameters for explicit genuinely unseen survey cohorts."""
        from genomeos.surfaces.observation_prediction import predict_new_cohort_parameters

        return predict_new_cohort_parameters(self, queries, seed=seed)

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

        if not self.beta_cohort_applied:
            # No cohort effect was estimated, so there is none to integrate over. The predictive
            # then differs from the latent field only by sampling noise.
            cohort_sd = np.zeros(len(freq))
        else:
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
    if config.lengthscale_prior == "derived":
        lengthscale_mu, lengthscale_sigma, anchor_low, anchor_high = derive_lengthscale_prior(
            obs["lat"].to_numpy(), obs["lon"].to_numpy()
        )
    else:
        lengthscale_mu, lengthscale_sigma = config.lengthscale_mu, config.lengthscale_sigma
        anchor_low = anchor_high = float("nan")

    cohorts = sorted(obs["cohort_id"].unique())
    # A cohort effect needs replication within cohorts to be identified. One level per observation
    # gives none, so the term is dropped rather than fitted into a ridge.
    beta_cohort_applied = len(cohorts) < len(obs)
    if not beta_cohort_applied:
        warnings.warn(
            f"{len(cohorts)} cohorts for {len(obs)} observations: the cohort effect has no "
            "within-cohort replication to identify it and is not estimated. Overdispersion is "
            "carried by the likelihood instead.",
            stacklevel=2,
        )
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
        lengthscale = pm.LogNormal("lengthscale", mu=lengthscale_mu, sigma=lengthscale_sigma)
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
        # Only when the cohorts are actually grouped. A source with one study per population —
        # AFND is one — gives `cohort_id == population_id`, so this term would have one level per
        # observation. That is not the study-level effect §7.1d wants: it is an observation-level
        # overdispersion term, competing with the beta-binomial `concentration` to explain the
        # same residual, and the two are not jointly identifiable. Screening ten HLA alleles,
        # `cohort_sd` was the worst-mixing parameter in four of five failures (r_hat up to 1.12,
        # ESS 23) while the same model fits MAP data, which has 419 cohorts for 1,071 surveys.
        #
        # Fitting it anyway does not merely waste a parameter: an unidentified per-observation
        # term is free to absorb the spatial signal the GP exists to explain.
        if beta_cohort_applied:
            cohort_sd = pm.HalfNormal("cohort_sd", sigma=0.5)
            cohort_z = pm.Normal("cohort_z", mu=0.0, sigma=1.0, shape=len(cohorts))
            beta_cohort = pm.Deterministic("beta_cohort", cohort_sd * cohort_z)
            logit = logit + beta_cohort[cohort_index]

        if config.nugget:
            # Non-centred, like every other hierarchical term here (Neal's funnel). Competes with
            # the beta-binomial `concentration` for the same per-observation deviation, so
            # `likelihood="binomial"` is the arm that tests the nugget alone (#137).
            nugget_sd = pm.HalfNormal("nugget_sd", sigma=1.0)
            nugget_z = pm.Normal("nugget_z", mu=0.0, sigma=1.0, shape=len(observations))
            logit = logit + nugget_sd * nugget_z

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
        pm.Deterministic("latent_logit_pred", f_pred_expr)
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
            # Top level, which reaches numpyro and PyMC's own NUTS alike, and is accepted
            # alongside the `nuts` dict below on both 5.x and 6.x. Measured, not inferred:
            # `scripts/env_report.py` reports what actually arrives at the sampler.
            "target_accept": config.target_accept,
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
            #
            # `nuts` is the channel to pass it in, and which channel works is version-dependent
            # rather than settled: PyMC changed how NUTS options are routed between 5.x and 6.x,
            # and `nuts_sampler_kwargs` — which is the one that works on 5.x — is deprecated on
            # the pinned 6.3.1 in favour of this one. Do not re-litigate that from the PyMC
            # source, which is what produced a wrong answer in #120; run `scripts/env_report.py`,
            # which measures where each channel actually lands in the environment you have.
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
        beta_cohort_applied=beta_cohort_applied,
        lengthscale_prior_km=(anchor_low, anchor_high),
        design_levels=non_reference,
        prior_frequency_sd=prior_sd,
        inducing_spacing_ratio=spacing_ratio,
        correlation_range_km=correlation_range_km,
        idata=idata,
        _model=model,
        _centre=centre,
        _scale=scale,
        prediction_metadata=ObservationModelMetadata(
            convention="new_cohort_count_v1",
            fitted_designs=design_levels,
            training_cohort_ids=tuple(cohorts),
            cohort_effect_applied=beta_cohort_applied,
            nugget_applied=config.nugget,
            likelihood=config.likelihood,
        ),
    )


# Re-exported for the call sites that import them from here. `surfaces.persistence` is where they
# live; the import is at the foot of the module because that module imports `SurfaceFit` from
# this one.
from genomeos.surfaces.persistence import FIT_FORMAT, load_fit, save_fit  # noqa: E402, F401
