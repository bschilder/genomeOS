"""Piel cubic and Stukel-link preflights (design §7, §8; issue #103).

Piel et al. 2013 replaced an inverse-logit link after its right tail produced implausible HbS
burden. Web Appendix 1 maps a Gaussian latent value through ``expit(h(x))``, where ``h`` is a
monotone cubic estimated outside the spatial fit. The appendix publishes the final source-data
coefficients, evaluated separately in :mod:`genomeos.surfaces.piel_published_link`, while this
module reconstructs the empirical fitting procedure on the current data. Its printed
smoothed-frequency equation conflicts with the stated uniform-prior binomial model, so both
interpretations remain separately named. Neither module connects an arm to the production fitter.

The appendix also leaves details of its empirical-CDF fit implicit. This preflight names its
interpretation: average ranks with Hazen plotting positions, a plug-in normal MLE, and monotone
quantile matching. The cubic is globally invertible because its derivative is parameterized as a
positive constant plus a squared line. These choices are experimental evidence, not a claim of
bitwise reproduction of the unpublished Piel implementation.

The module also implements Stukel's two-piece generalized logistic link (JASA 1988,
doi:10.1080/01621459.1988.10478613). The HbS observations identify only its negative-latent
branch, so the positive-branch shape is fixed at zero and reported as unfitted. Candidate
frequencies are compared after affine quantile alignment; applying two separately fitted links
at the same raw latent number would compare different empirical quantiles.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import least_squares
from scipy.special import expit, logit
from scipy.stats import norm, rankdata

SMOOTHING_RULES = ("piel_printed_2013", "uniform_binomial_conjugate")
SMOOTHING_FORMULAS = {
    "piel_printed_2013": "(AC + 1) / (AN + AC + 2)",
    "uniform_binomial_conjugate": "(AC + 1) / (AN + 2)",
}
PLOTTING_POSITION = "hazen_rank_average"
NORMAL_FIT = "plug_in_mle"
MIN_ELIGIBLE_ROWS = 8
MIN_DISTINCT_FREQUENCIES = 4
_DERIVATIVE_EPSILON = 1e-10
_START_SLOPES = (-0.2, -0.05, 0.0, 0.05, 0.2)
_STUKEL_START_SHAPES = (-1.0, -0.5, 0.0, 0.5, 1.0)
_STUKEL_ZERO_TOLERANCE = 1e-12


def _finite_array(value: object, name: str) -> np.ndarray:
    try:
        objects = np.asarray(value, dtype=object)
        raw = np.asarray(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be numeric") from error
    if raw.ndim != 1:
        raise ValueError(f"{name} must be a one-dimensional count vector")
    if np.issubdtype(raw.dtype, np.bool_) or any(
        isinstance(item, (bool, np.bool_)) for item in objects
    ):
        raise ValueError(f"{name} must be numeric, not Boolean")
    if not np.issubdtype(raw.dtype, np.number) or np.issubdtype(
        raw.dtype, np.complexfloating
    ):
        raise ValueError(f"{name} must be numeric")
    numeric = raw.astype(float)
    if not np.all(np.isfinite(numeric)):
        raise ValueError(f"{name} must contain finite counts")
    if not np.all(numeric == np.floor(numeric)):
        raise ValueError(f"{name} must contain integer counts")
    return numeric


def _counts(ac: object, an: object) -> tuple[np.ndarray, np.ndarray]:
    alternate = _finite_array(ac, "ac")
    total = _finite_array(an, "an")
    if alternate.shape != total.shape:
        raise ValueError("ac and an must have the same shape")
    if not len(alternate):
        raise ValueError("ac and an must contain at least one observation")
    if np.any(total <= 0):
        raise ValueError("an must contain positive denominators")
    if np.any(alternate < 0) or np.any(alternate > total):
        raise ValueError("ac must be between zero and AN")
    return alternate, total


def _rule(rule: str) -> str:
    if not isinstance(rule, str) or rule not in SMOOTHING_RULES:
        raise ValueError(f"smoothing rule must be one of {SMOOTHING_RULES}")
    return rule


def smooth_piel_frequencies(ac: object, an: object, *, rule: str) -> np.ndarray:
    """Apply one explicitly named interpretation of Web Appendix 1's frequency equation."""
    rule = _rule(rule)
    alternate, total = _counts(ac, an)
    denominator = total + 2.0
    if rule == "piel_printed_2013":
        denominator = denominator + alternate
    return (alternate + 1.0) / denominator


def _latent_array(value: object) -> np.ndarray:
    try:
        latent = np.asarray(value, dtype=float)
    except (TypeError, ValueError) as error:
        raise ValueError("latent values must be numeric") from error
    if not np.all(np.isfinite(latent)):
        raise ValueError("latent values must be finite")
    return latent


@dataclass(frozen=True)
class MonotoneCubicLink:
    """A globally increasing cubic followed by inverse-logit."""

    coefficients: tuple[float, float, float, float]
    derivative_floor: float

    def polynomial(self, latent: object) -> np.ndarray:
        x = _latent_array(latent)
        c0, c1, c2, c3 = self.coefficients
        return c0 + c1 * x + c2 * x**2 + c3 * x**3

    def derivative(self, latent: object) -> np.ndarray:
        x = _latent_array(latent)
        _, c1, c2, c3 = self.coefficients
        return c1 + 2.0 * c2 * x + 3.0 * c3 * x**2

    def frequency(self, latent: object) -> np.ndarray:
        return expit(self.polynomial(latent))


@dataclass(frozen=True)
class PielFlexibleLinkPreflight:
    """Frozen output of one equation arm; never a fitted spatial surface."""

    smoothing_rule: str
    smoothing_formula: str
    min_an: int
    n_total: int
    n_eligible: int
    n_below_min_an: int
    n_distinct_frequencies: int
    normal_location: float
    normal_scale: float
    normal_fit: str
    plotting_position: str
    link: MonotoneCubicLink
    rmse_logit: float
    smoothed_frequency_min: float
    smoothed_frequency_max: float
    optimization_starts: int


@dataclass(frozen=True)
class StukelLink:
    """Stukel's two-piece transform followed by inverse-logit."""

    alpha_positive: float
    alpha_negative: float

    def __post_init__(self) -> None:
        if not np.isfinite(self.alpha_positive) or not np.isfinite(self.alpha_negative):
            raise ValueError("Stukel shape parameters must be finite")

    def transform(self, latent: object) -> np.ndarray:
        x = _latent_array(latent)
        transformed = np.empty_like(x)
        positive = x > 0.0
        upper = x[positive]
        lower = -x[~positive]

        if self.alpha_positive > _STUKEL_ZERO_TOLERANCE:
            transformed[positive] = np.expm1(self.alpha_positive * upper) / self.alpha_positive
        elif self.alpha_positive < -_STUKEL_ZERO_TOLERANCE:
            transformed[positive] = (
                -np.log1p(-self.alpha_positive * upper) / self.alpha_positive
            )
        else:
            transformed[positive] = upper

        if self.alpha_negative > _STUKEL_ZERO_TOLERANCE:
            transformed[~positive] = (
                -np.expm1(self.alpha_negative * lower) / self.alpha_negative
            )
        elif self.alpha_negative < -_STUKEL_ZERO_TOLERANCE:
            transformed[~positive] = (
                np.log1p(-self.alpha_negative * lower) / self.alpha_negative
            )
        else:
            transformed[~positive] = -lower
        return transformed

    def frequency(self, latent: object) -> np.ndarray:
        return expit(self.transform(latent))


@dataclass(frozen=True)
class StukelLinkPreflight:
    """One negative-tail Stukel fit aligned to the empirical-logit baseline."""

    smoothing_rule: str
    smoothing_formula: str
    min_an: int
    n_total: int
    n_eligible: int
    n_below_min_an: int
    n_distinct_frequencies: int
    normal_location: float
    normal_scale: float
    stukel_location: float
    stukel_scale: float
    link: StukelLink
    positive_branch_fitted: bool
    minimum_fitted_latent: float
    maximum_fitted_latent: float
    rmse_logit: float
    optimization_starts: int
    successful_starts: int
    optimization_objective_spread: float

    def aligned_frequency(self, baseline_latent: object) -> np.ndarray:
        """Evaluate at the same empirical quantile as a baseline-logit latent value."""
        baseline = _latent_array(baseline_latent)
        aligned = self.stukel_location + self.stukel_scale * (
            (baseline - self.normal_location) / self.normal_scale
        )
        return self.link.frequency(aligned)


def _softplus(value: float) -> float:
    return float(np.logaddexp(0.0, value))


def _link_from_parameters(parameters: np.ndarray) -> MonotoneCubicLink:
    intercept, raw_floor, square_intercept, square_slope = parameters
    floor = _softplus(float(raw_floor)) + _DERIVATIVE_EPSILON
    coefficients = (
        float(intercept),
        float(floor + square_intercept**2),
        float(square_intercept * square_slope),
        float(square_slope**2 / 3.0),
    )
    return MonotoneCubicLink(coefficients=coefficients, derivative_floor=floor)


def _fit_link(latent_quantiles: np.ndarray, target_logits: np.ndarray) -> tuple[MonotoneCubicLink, float]:
    half = 0.5
    raw_half = float(np.log(np.expm1(half)))
    starts = [
        np.array([0.0, raw_half, np.sqrt(half), slope], dtype=float)
        for slope in _START_SLOPES
    ]

    def residual(parameters: np.ndarray) -> np.ndarray:
        return _link_from_parameters(parameters).polynomial(latent_quantiles) - target_logits

    results = [
        least_squares(
            residual,
            start,
            bounds=(
                np.array([-50.0, -30.0, -20.0, -20.0]),
                np.array([50.0, 10.0, 20.0, 20.0]),
            ),
            max_nfev=100_000,
            ftol=1e-13,
            xtol=1e-13,
            gtol=1e-13,
        )
        for start in starts
    ]
    successful = [result for result in results if result.success and np.all(np.isfinite(result.fun))]
    if not successful:
        raise RuntimeError("monotone cubic optimization did not converge")
    best = min(successful, key=lambda result: float(np.dot(result.fun, result.fun)))
    link = _link_from_parameters(best.x)
    rmse = float(np.sqrt(np.mean(np.square(best.fun))))
    if not np.isfinite(rmse):
        raise RuntimeError("monotone cubic optimization produced nonfinite error")
    return link, rmse


def fit_piel_flexible_link(
    ac: object,
    an: object,
    *,
    rule: str,
    min_an: int = 50,
) -> PielFlexibleLinkPreflight:
    """Fit the explicitly interpreted empirical cubic without touching the spatial model.

    ``AN`` is the number of chromosomes, equal to ``2*n_i`` in Web Appendix 1. Rows below the
    appendix's threshold are reported in the result rather than disappearing from provenance.
    The normal model uses a plug-in MLE because the appendix does not specify enough posterior
    fitting detail to reproduce its Bayesian calculation exactly.
    """
    rule = _rule(rule)
    if isinstance(min_an, (bool, np.bool_)) or not isinstance(
        min_an, (int, np.integer)
    ) or min_an <= 0:
        raise ValueError("min_an must be a positive integer chromosome-count threshold")
    alternate, total = _counts(ac, an)
    eligible = total >= min_an
    n_eligible = int(np.sum(eligible))
    if n_eligible < MIN_ELIGIBLE_ROWS:
        raise ValueError(f"at least {MIN_ELIGIBLE_ROWS} eligible rows are required")

    # Canonical order makes floating reductions and optimization identical under input row
    # reordering. No observation identity is used in this explicitly nonspatial preflight.
    frequency = np.sort(
        smooth_piel_frequencies(alternate[eligible], total[eligible], rule=rule),
        kind="stable",
    )
    distinct = int(np.unique(frequency).size)
    if distinct < MIN_DISTINCT_FREQUENCIES:
        raise ValueError(
            f"at least {MIN_DISTINCT_FREQUENCIES} distinct smoothed frequencies are required"
        )
    target = logit(frequency)
    location = float(np.mean(target))
    scale = float(np.std(target, ddof=0))
    if not np.isfinite(scale) or scale <= 0.0:
        raise ValueError("smoothed logits require positive finite normal scale")

    empirical_probability = (rankdata(target, method="average") - 0.5) / n_eligible
    latent = location + scale * norm.ppf(empirical_probability)
    link, rmse = _fit_link(latent, target)

    return PielFlexibleLinkPreflight(
        smoothing_rule=rule,
        smoothing_formula=SMOOTHING_FORMULAS[rule],
        min_an=int(min_an),
        n_total=len(total),
        n_eligible=n_eligible,
        n_below_min_an=int(len(total) - n_eligible),
        n_distinct_frequencies=distinct,
        normal_location=location,
        normal_scale=scale,
        normal_fit=NORMAL_FIT,
        plotting_position=PLOTTING_POSITION,
        link=link,
        rmse_logit=rmse,
        smoothed_frequency_min=float(np.min(frequency)),
        smoothed_frequency_max=float(np.max(frequency)),
        optimization_starts=len(_START_SLOPES),
    )


def fit_stukel_link(
    ac: object,
    an: object,
    *,
    rule: str,
    min_an: int = 50,
) -> StukelLinkPreflight:
    """Fit the Stukel negative-tail branch without touching the spatial model.

    The observed HbS range supplies no positive Stukel latent values. ``alpha_positive`` is
    therefore fixed at the inverse-logit value zero instead of reporting an arbitrary optimizer
    output as identified. The fit refuses data whose optimum enters that unfitted branch.
    """
    rule = _rule(rule)
    if isinstance(min_an, (bool, np.bool_)) or not isinstance(
        min_an, (int, np.integer)
    ) or min_an <= 0:
        raise ValueError("min_an must be a positive integer chromosome-count threshold")
    alternate, total = _counts(ac, an)
    eligible = total >= min_an
    n_eligible = int(np.sum(eligible))
    if n_eligible < MIN_ELIGIBLE_ROWS:
        raise ValueError(f"at least {MIN_ELIGIBLE_ROWS} eligible rows are required")

    frequency = np.sort(
        smooth_piel_frequencies(alternate[eligible], total[eligible], rule=rule),
        kind="stable",
    )
    distinct = int(np.unique(frequency).size)
    if distinct < MIN_DISTINCT_FREQUENCIES:
        raise ValueError(
            f"at least {MIN_DISTINCT_FREQUENCIES} distinct smoothed frequencies are required"
        )
    target = logit(frequency)
    normal_location = float(np.mean(target))
    normal_scale = float(np.std(target, ddof=0))
    if not np.isfinite(normal_scale) or normal_scale <= 0.0:
        raise ValueError("smoothed logits require positive finite normal scale")
    probability = (rankdata(target, method="average") - 0.5) / n_eligible
    standard_quantile = norm.ppf(probability)

    def residual(parameters: np.ndarray) -> np.ndarray:
        location, log_scale, alpha_negative = parameters
        latent = location + np.exp(log_scale) * standard_quantile
        link = StukelLink(alpha_positive=0.0, alpha_negative=float(alpha_negative))
        return link.transform(latent) - target

    starts = [
        np.array([normal_location, np.log(normal_scale), shape], dtype=float)
        for shape in _STUKEL_START_SHAPES
    ]
    results = [
        least_squares(
            residual,
            start,
            bounds=(
                np.array([-50.0, -10.0, -5.0]),
                np.array([20.0, 10.0, 5.0]),
            ),
            max_nfev=100_000,
            ftol=1e-13,
            xtol=1e-13,
            gtol=1e-13,
        )
        for start in starts
    ]
    successful = [result for result in results if result.success and np.all(np.isfinite(result.fun))]
    if not successful:
        raise RuntimeError("Stukel optimization did not converge")
    objectives = np.asarray([np.dot(result.fun, result.fun) for result in successful], dtype=float)
    best = successful[int(np.argmin(objectives))]
    location, log_scale, alpha_negative = (float(value) for value in best.x)
    scale = float(np.exp(log_scale))
    fitted_latent = location + scale * standard_quantile
    if np.any(fitted_latent > 0.0):
        raise ValueError("Stukel fit enters the unfitted positive-latent branch")
    rmse = float(np.sqrt(np.mean(np.square(best.fun))))
    if not np.isfinite(rmse):
        raise RuntimeError("Stukel optimization produced nonfinite error")

    return StukelLinkPreflight(
        smoothing_rule=rule,
        smoothing_formula=SMOOTHING_FORMULAS[rule],
        min_an=int(min_an),
        n_total=len(total),
        n_eligible=n_eligible,
        n_below_min_an=int(len(total) - n_eligible),
        n_distinct_frequencies=distinct,
        normal_location=normal_location,
        normal_scale=normal_scale,
        stukel_location=location,
        stukel_scale=scale,
        link=StukelLink(alpha_positive=0.0, alpha_negative=alpha_negative),
        positive_branch_fitted=False,
        minimum_fitted_latent=float(np.min(fitted_latent)),
        maximum_fitted_latent=float(np.max(fitted_latent)),
        rmse_logit=rmse,
        optimization_starts=len(starts),
        successful_starts=len(successful),
        optimization_objective_spread=float(np.max(objectives) - np.min(objectives)),
    )
