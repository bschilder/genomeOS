"""Source-exact Piel 2013 cubic-link preflight (design §7, §8; issue #103).

Web Appendix 1 page 15 publishes the cubic used by Piel et al. The polynomial is not
globally monotone: it is decreasing on the source-data branch to the right of its upper
turning point. This module preserves the printed coefficients and inverts only that branch.

The source and current inverse-logit latent scales are arbitrary. Comparisons therefore align
empirical quantiles, with an explicit orientation reversal because the published branch is
decreasing. This is a nonspatial diagnostic and does not install the link in the surface fitter.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.special import expit, logit
from scipy.stats import norm, rankdata

from genomeos.surfaces.piel_flexible_link import (
    MIN_DISTINCT_FREQUENCIES,
    MIN_ELIGIBLE_ROWS,
    PLOTTING_POSITION,
    smooth_piel_frequencies,
)

PIEL_PUBLISHED_COEFFICIENTS = (
    0.02125477,
    0.02261485,
    0.28125179,
    -1.48556762,
)
PIEL_PUBLISHED_FORMULA = (
    "-1.48556762*x^3 + 0.28125179*x^2 + 0.02261485*x + 0.02125477"
)
PIEL_PUBLISHED_SOURCE = "Piel et al. 2013 Web Appendix 1 page 15"
PIEL_APPENDIX_SHA256 = "7fa25e9d3c6a442f410425bafd891a166be7e800c71927ea36ba3e997208295e"
_BISECTION_STEPS = 80
_INVERSE_TOLERANCE = 1e-10


def _latent_array(value: object) -> np.ndarray:
    try:
        latent = np.asarray(value, dtype=float)
    except (TypeError, ValueError) as error:
        raise ValueError("latent values must be numeric") from error
    if not np.all(np.isfinite(latent)):
        raise ValueError("latent values must be finite")
    return latent


@dataclass(frozen=True)
class PublishedPielLink:
    """The exact published cubic restricted to its decreasing HbS branch."""

    coefficients: tuple[float, float, float, float]
    branch_lower_bound: float

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
class PublishedPielLinkPreflight:
    """Published-link evaluation aligned to the current empirical quantiles."""

    source: str
    source_appendix_sha256: str
    formula: str
    min_an: int
    n_total: int
    n_eligible: int
    n_below_min_an: int
    n_distinct_frequencies: int
    plotting_position: str
    link: PublishedPielLink
    source_latent_location: float
    source_latent_scale: float
    baseline_logit_location: float
    baseline_logit_scale: float
    quantile_orientation: float
    minimum_fitted_latent: float
    maximum_fitted_latent: float
    rmse_logit: float
    inverse_max_abs_error: float

    def aligned_source_latent(self, baseline_latent: object) -> np.ndarray:
        """Map current inverse-logit latents to the matching source-data quantiles."""
        baseline = _latent_array(baseline_latent)
        standardized = (
            baseline - self.baseline_logit_location
        ) / self.baseline_logit_scale
        return self.source_latent_location + (
            self.quantile_orientation * self.source_latent_scale * standardized
        )

    def aligned_frequency(self, baseline_latent: object) -> np.ndarray:
        """Evaluate the source link at the matching current-logit empirical quantile."""
        aligned = self.aligned_source_latent(baseline_latent)
        if np.any(aligned < self.link.branch_lower_bound):
            raise ValueError("aligned values leave the published Piel decreasing branch")
        return self.link.frequency(aligned)


def _published_link() -> PublishedPielLink:
    c0, c1, c2, c3 = PIEL_PUBLISHED_COEFFICIENTS
    del c0
    discriminant = (2.0 * c2) ** 2 - 4.0 * (3.0 * c3) * c1
    if discriminant <= 0.0:
        raise RuntimeError("published Piel cubic does not have the expected turning points")
    roots = np.sort(
        np.asarray(
            [
                (-2.0 * c2 - np.sqrt(discriminant)) / (6.0 * c3),
                (-2.0 * c2 + np.sqrt(discriminant)) / (6.0 * c3),
            ]
        )
    )
    branch_lower_bound = float(roots[-1])
    link = PublishedPielLink(
        coefficients=PIEL_PUBLISHED_COEFFICIENTS,
        branch_lower_bound=branch_lower_bound,
    )
    if float(link.derivative(branch_lower_bound + 1e-6)) >= 0.0:
        raise RuntimeError("published Piel branch is not decreasing above its turning point")
    return link


def _invert_decreasing_branch(link: PublishedPielLink, target: np.ndarray) -> np.ndarray:
    branch_maximum = float(link.polynomial(link.branch_lower_bound))
    if np.any(target > branch_maximum):
        raise ValueError("target logits fall outside the published Piel branch")
    upper = max(1.0, 2.0 * link.branch_lower_bound)
    while float(link.polynomial(upper)) > float(np.min(target)):
        upper *= 2.0
        if not np.isfinite(upper):
            raise RuntimeError("could not bracket the published Piel branch")
    lower_values = np.full(target.shape, link.branch_lower_bound)
    upper_values = np.full(target.shape, upper)
    for _ in range(_BISECTION_STEPS):
        middle = (lower_values + upper_values) / 2.0
        move_lower = link.polynomial(middle) > target
        lower_values = np.where(move_lower, middle, lower_values)
        upper_values = np.where(move_lower, upper_values, middle)
    latent = (lower_values + upper_values) / 2.0
    error = float(np.max(np.abs(link.polynomial(latent) - target)))
    if error > _INVERSE_TOLERANCE:
        raise RuntimeError(f"published Piel inverse error {error} exceeds tolerance")
    return latent


def fit_published_piel_link(
    ac: object,
    an: object,
    *,
    min_an: int = 50,
) -> PublishedPielLinkPreflight:
    """Evaluate the exact source polynomial on the printed-equation HbS branch."""
    if isinstance(min_an, (bool, np.bool_)) or not isinstance(
        min_an, (int, np.integer)
    ) or min_an <= 0:
        raise ValueError("min_an must be a positive integer chromosome-count threshold")
    smoothed = smooth_piel_frequencies(ac, an, rule="piel_printed_2013")
    total = np.asarray(an, dtype=float)
    eligible = total >= min_an
    n_eligible = int(np.sum(eligible))
    if n_eligible < MIN_ELIGIBLE_ROWS:
        raise ValueError(f"at least {MIN_ELIGIBLE_ROWS} eligible rows are required")
    frequency = np.sort(smoothed[eligible], kind="stable")
    distinct = int(np.unique(frequency).size)
    if distinct < MIN_DISTINCT_FREQUENCIES:
        raise ValueError(
            f"at least {MIN_DISTINCT_FREQUENCIES} distinct smoothed frequencies are required"
        )
    target = logit(frequency)
    baseline_location = float(np.mean(target))
    baseline_scale = float(np.std(target, ddof=0))
    if not np.isfinite(baseline_scale) or baseline_scale <= 0.0:
        raise ValueError("smoothed logits require positive finite normal scale")

    link = _published_link()
    source_latent = _invert_decreasing_branch(link, target)
    source_location = float(np.mean(source_latent))
    source_scale = float(np.std(source_latent, ddof=0))
    if not np.isfinite(source_scale) or source_scale <= 0.0:
        raise ValueError("published Piel latents require positive finite scale")

    probability = (rankdata(target, method="average") - 0.5) / n_eligible
    baseline_quantile = baseline_location + baseline_scale * norm.ppf(probability)
    aligned_source = source_location - source_scale * (
        (baseline_quantile - baseline_location) / baseline_scale
    )
    predicted_logit = link.polynomial(aligned_source)
    rmse = float(np.sqrt(np.mean(np.square(predicted_logit - target))))
    inverse_error = float(np.max(np.abs(link.polynomial(source_latent) - target)))
    if not np.isfinite(rmse):
        raise RuntimeError("published Piel alignment produced nonfinite error")

    return PublishedPielLinkPreflight(
        source=PIEL_PUBLISHED_SOURCE,
        source_appendix_sha256=PIEL_APPENDIX_SHA256,
        formula=PIEL_PUBLISHED_FORMULA,
        min_an=int(min_an),
        n_total=len(total),
        n_eligible=n_eligible,
        n_below_min_an=int(len(total) - n_eligible),
        n_distinct_frequencies=distinct,
        plotting_position=PLOTTING_POSITION,
        link=link,
        source_latent_location=source_location,
        source_latent_scale=source_scale,
        baseline_logit_location=baseline_location,
        baseline_logit_scale=baseline_scale,
        quantile_orientation=-1.0,
        minimum_fitted_latent=float(np.min(source_latent)),
        maximum_fitted_latent=float(np.max(source_latent)),
        rmse_logit=rmse,
        inverse_max_abs_error=inverse_error,
    )
