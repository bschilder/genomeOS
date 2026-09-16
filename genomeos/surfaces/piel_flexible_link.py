"""Piel's empirical cubic-link preflight (design §7, §8; issue #103).

Piel et al. 2013 replaced an inverse-logit link after its right tail produced implausible HbS
burden. Web Appendix 1 maps a Gaussian latent value through ``expit(h(x))``, where ``h`` is a
monotone cubic estimated outside the spatial fit. The appendix does not publish its coefficients,
and its printed smoothed-frequency equation conflicts with the stated uniform-prior binomial
model. This module preserves both equations as separately named research arms. It does not choose
between them or connect either arm to the production surface fitter.

The appendix also leaves details of its empirical-CDF fit implicit. This preflight names its
interpretation: average ranks with Hazen plotting positions, a plug-in normal MLE, and monotone
quantile matching. The cubic is globally invertible because its derivative is parameterized as a
positive constant plus a squared line. These choices are experimental evidence, not a claim of
bitwise reproduction of the unpublished Piel implementation.
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
