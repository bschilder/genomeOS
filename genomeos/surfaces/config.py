"""Surface-fitting configuration and geometry constants (design §§5, 7)."""

from __future__ import annotations

from dataclasses import dataclass

SEED = 42

LIKELIHOODS: tuple[str, ...] = ("binomial", "beta_binomial")

#: How the lengthscale prior is chosen. "derived" reads it off the observation locations; "fixed"
#: uses the constants on `FitConfig` and exists so a published surface can be reproduced exactly.
LENGTHSCALE_PRIORS: tuple[str, ...] = ("derived", "fixed")

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


#: Independent regions the prior asks the field to show across the sampled domain. A Matern-5/2
#: decorrelates at roughly twice its range, so an upper anchor of `extent / (2 * K)` says "the
#: field should vary at least K times across where the data actually is". K=4 is a judgement, but
#: a stated one: it admits every credible fit measured so far (HbS 680 km, G6PD 547 km,
#: DRB1*16:02 750 km, DRB1*14:01 1,195 km) and excludes the degenerate ones (DRB1*12:01 3,143 km,
#: DRB1*04:04 4,111 km) without being tuned per variant.
LENGTHSCALE_REGIONS = 4

#: Floor on the lower anchor. Three nearest-neighbour spacings is the least that could show
#: correlation decaying at all; the constant stops a pathologically clustered corpus from driving
#: the anchor to zero.
MIN_LENGTHSCALE_ANCHOR_KM = 25.0

#: Ceiling on the upper anchor, and it is a physical statement rather than a tuning constant: a
#: correlation range of 2,500 km already means two populations 5,000 km apart are meaningfully
#: correlated, which is most of an inhabited hemisphere. Needed because the anchors are read off
#: the data and sparse data misreads them — five points spread across 30 degrees put the median
#: nearest-neighbour spacing at ~1,500 km and drove the prior to 47,000 km, a range longer than
#: the planet. `MIN_OBSERVATIONS` in `surfaces.batch` is 5, so that case is reachable.
MAX_LENGTHSCALE_ANCHOR_KM = 2500.0


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
    #: NUTS target acceptance rate. Higher means a smaller step size, so each draw costs more
    #: leapfrog steps but decorrelates better — the standard trade of wall-clock for ESS.
    #:
    #: 0.8 is PyMC's own default and is kept as ours, so the surfaces already published are
    #: unaffected. It is a field rather than a constant because cross-validation folds need a
    #: higher value than the full fit does: a fold trains on (k-1)/k of the data, and at
    #: draws=400 four of ten folds missed the ESS floor of 200, at 61-143 (#111). Raising it is
    #: opt-in at the call site that needs it — see `scripts/validate_holdout.py`.
    target_accept: float = 0.8
    #: Gelman-Rubin ceiling, applied to the *maximum* over every parameter. 1.01 is the modern
    #: standard for a single quantity of interest, but this model has ~1,500 latent parameters
    #: and the max over that many exceeds 1.01 by chance even when sampling is healthy — using
    #: it here rejected a fit with r_hat 1.018 and ESS 378. 1.05 is the classic Gelman-Rubin
    #: cutoff and is the defensible bar for a maximum.
    #: How the lengthscale prior is set. ``"derived"`` reads it off the observation locations —
    #: see `derive_lengthscale_prior` — and is the default because hand-setting it does not
    #: survive 767 alleles (#122): a screen of twenty HLA alleles fitted ranges of 1,036-4,111 km
    #: under the fixed prior, almost all in the degenerate regime where a long range is
    #: indistinguishable from the intercept. ``"fixed"`` uses `lengthscale_mu`/`lengthscale_sigma`
    #: and exists so a published surface can be reproduced exactly.
    lengthscale_prior: str = "derived"
    #: Prior mean of log lengthscale, in chordal units. Used only when `lengthscale_prior` is
    #: "fixed"; exp(-2.0) x Earth radius is about 861 km.
    lengthscale_mu: float = -2.0
    #: Prior sd of log lengthscale. The default spans roughly 220-3,400 km at 95%, which suits a
    #: variant whose data pins the range down. It does not suit every variant: a correlation range
    #: near the top of that span describes a field that is nearly constant globally, which is
    #: indistinguishable from `intercept` — a ridge the chains can slide along instead of mixing.
    #: G6PD does exactly that (r_hat 1.469 on `lengthscale`, #116), because a phenotype pooling
    #: ~200 alleles has no single spatial scale for the data to identify. Tightening this is a
    #: statement that the field is spatial rather than constant, and must be made deliberately
    #: per variant rather than defaulted, because it is a real prior belief about the biology.
    lengthscale_sigma: float = 0.7
    #: Spatially-uncorrelated variation in the latent field, on the logit scale. Off by default
    #: because turning it on changes every published range. Empirical semivariograms show 31-39%
    #: of the sill already at 0-250 km, which the model currently has nowhere to put; the
    #: evidence and the trade-off with `concentration` are in #137. Enters the likelihood but not
    #: the prediction path, so the published surface stays the smooth field.
    nugget: bool = False
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
        if self.lengthscale_prior not in LENGTHSCALE_PRIORS:
            raise ValueError(
                f"unknown lengthscale_prior {self.lengthscale_prior!r}; "
                f"expected one of {LENGTHSCALE_PRIORS}"
            )
        if self.max_rhat < 1.0:
            raise ValueError("max_rhat must be >= 1.0")
        if not 0.0 < self.target_accept < 1.0:
            raise ValueError("target_accept must be strictly between 0 and 1")
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
