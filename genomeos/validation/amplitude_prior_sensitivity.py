"""GP-amplitude prior sensitivity preflight (design §§7–8; issue #103).

The current HbS surface has a supported non-endemic frequency floor and flattened endemic peaks.
One proposed response is a tighter prior on the spatial-field amplitude. This module answers the
smallest useful question before another fit: under self-normalized importance reweighting, does a
tighter HalfNormal prior move the retained posterior in the required direction with adequate
effective sample size?

This is a development diagnostic. It does not refit the model, score held-out counts, change a
surface, or establish publication eligibility. Array operations keep cells and posterior draws
batched; no population-by-cell or draw-by-cell Python loop is used.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np
from scipy.special import expit


@dataclass(frozen=True)
class WeightedSummary:
    """Weighted posterior summary for one scalar diagnostic."""

    q025: float
    q25: float
    median: float
    q75: float
    q975: float
    mean: float


@dataclass(frozen=True)
class PriorCandidateSensitivity:
    """Importance diagnostics and scientific direction for one prior scale."""

    scale: float
    effective_sample_size: float
    maximum_normalized_weight: float
    importance_diagnostics_pass: bool
    advance_to_full_refit: bool
    decision_reason: str
    summaries: Mapping[str, WeightedSummary]


@dataclass(frozen=True)
class AmplitudeSensitivityResult:
    """Complete result for the frozen candidate-prior comparison."""

    n_draws: int
    n_cells: int
    nordic_cells: int
    peak_cells: int
    nordic_population_weight: float
    peak_population_weight: float
    candidates: tuple[PriorCandidateSensitivity, ...]


_QUANTITY_NAMES = (
    "amplitude",
    "intercept",
    "invlogit_intercept",
    "population_weighted_nordic_frequency",
    "population_weighted_endemic_peak_frequency",
    "endemic_minus_nordic_frequency",
)
_QUANTILES = (0.025, 0.25, 0.5, 0.75, 0.975)


def _numeric_array(value: object, name: str, *, ndim: int) -> np.ndarray:
    try:
        raw = np.asarray(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be a numeric {ndim}-dimensional array") from error
    if raw.ndim != ndim:
        raise ValueError(f"{name} must be {ndim}-dimensional")
    if np.issubdtype(raw.dtype, np.bool_) or not np.issubdtype(raw.dtype, np.number):
        raise ValueError(f"{name} must be numeric, not Boolean or text")
    if np.issubdtype(raw.dtype, np.complexfloating):
        raise ValueError(f"{name} must contain real values")
    numeric = raw.astype(float)
    if not np.isfinite(numeric).all():
        raise ValueError(f"{name} must contain finite values")
    return numeric


def _positive_scalar(value: object, name: str) -> float:
    if isinstance(value, (bool, np.bool_)):
        raise ValueError(f"{name} must be numeric, not Boolean")
    try:
        numeric = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be numeric") from error
    if not np.isfinite(numeric) or numeric <= 0.0:
        raise ValueError(f"{name} must be positive and finite")
    return numeric


def _mask(value: object, name: str, n_cells: int) -> np.ndarray:
    raw = np.asarray(value)
    if raw.ndim != 1 or raw.shape != (n_cells,) or raw.dtype != np.dtype(bool):
        raise ValueError(f"{name} must be a Boolean vector aligned to cells")
    if not raw.any():
        raise ValueError(f"{name} must select at least one cell")
    return raw


def half_normal_importance_weights(
    amplitude: object,
    *,
    original_scale: object,
    candidate_scale: object,
) -> np.ndarray:
    """Return normalized posterior importance weights for a HalfNormal scale change."""
    samples = _numeric_array(amplitude, "amplitude", ndim=1)
    if not len(samples):
        raise ValueError("amplitude must contain posterior draws")
    if np.any(samples < 0.0):
        raise ValueError("amplitude must be nonnegative for a HalfNormal prior")
    original = _positive_scalar(original_scale, "original_scale")
    candidate = _positive_scalar(candidate_scale, "candidate_scale")
    log_weight = (
        np.log(original / candidate)
        - 0.5 * samples**2 * (1.0 / candidate**2 - 1.0 / original**2)
    )
    log_weight -= float(np.max(log_weight))
    weight = np.exp(log_weight)
    total = float(np.sum(weight, dtype=np.float64))
    if not np.isfinite(total) or total <= 0.0:
        raise ValueError("importance weights are numerically unusable")
    return weight / total


def _weighted_summaries(
    values: np.ndarray, weights: np.ndarray
) -> dict[str, WeightedSummary]:
    order = np.argsort(values, axis=1, kind="stable")
    ordered_values = np.take_along_axis(values, order, axis=1)
    ordered_weights = np.take_along_axis(
        np.broadcast_to(weights, values.shape), order, axis=1
    )
    cumulative = np.cumsum(ordered_weights, axis=1)
    quantile_values = []
    for probability in _QUANTILES:
        index = np.argmax(cumulative >= probability, axis=1)
        quantile_values.append(
            np.take_along_axis(ordered_values, index[:, None], axis=1)[:, 0]
        )
    means = values @ weights
    return {
        name: WeightedSummary(
            q025=float(quantile_values[0][row]),
            q25=float(quantile_values[1][row]),
            median=float(quantile_values[2][row]),
            q75=float(quantile_values[3][row]),
            q975=float(quantile_values[4][row]),
            mean=float(means[row]),
        )
        for row, name in enumerate(_QUANTITY_NAMES)
    }


def _candidate_scales(
    values: object, *, original_scale: float
) -> tuple[float, ...]:
    try:
        scales = tuple(_positive_scalar(value, "candidate scale") for value in values)  # type: ignore[arg-type]
    except TypeError as error:
        raise ValueError("candidate_scales must be an iterable of positive scales") from error
    if not scales:
        raise ValueError("candidate_scales must be nonempty")
    if len(set(scales)) != len(scales):
        raise ValueError("candidate scales must be unique")
    if scales.count(original_scale) != 1:
        raise ValueError("candidate scales must contain the original scale exactly once")
    if any(scale > original_scale for scale in scales):
        raise ValueError("candidate scales must be no greater than the original scale")
    return scales


def evaluate_amplitude_prior_sensitivity(
    amplitude: object,
    intercept: object,
    frequency_draws: object,
    population: object,
    nordic_mask: object,
    peak_mask: object,
    *,
    original_scale: object,
    candidate_scales: object,
    minimum_effective_sample_size: object,
    maximum_single_weight: object,
) -> AmplitudeSensitivityResult:
    """Evaluate frozen tighter-amplitude candidates on aligned posterior fields.

    The two geographic masks are caller-declared diagnostics. They must be nonempty, disjoint,
    and aligned to ``frequency_draws`` columns. Candidate advancement here only means that a
    full refit could be worth running; it is never model or scientific acceptance.
    """
    amplitude_array = _numeric_array(amplitude, "amplitude", ndim=1)
    intercept_array = _numeric_array(intercept, "intercept", ndim=1)
    fields = _numeric_array(frequency_draws, "frequency_draws", ndim=2)
    population_array = _numeric_array(population, "population", ndim=1)
    n_draws, n_cells = fields.shape
    if n_draws < 2 or n_cells < 2:
        raise ValueError("frequency_draws must contain at least two draws and two cells")
    if amplitude_array.shape != (n_draws,) or intercept_array.shape != (n_draws,):
        raise ValueError("amplitude and intercept must be draw-aligned to frequency_draws")
    if population_array.shape != (n_cells,):
        raise ValueError("population must be cell-aligned to frequency_draws")
    if np.any(amplitude_array < 0.0):
        raise ValueError("amplitude must be nonnegative")
    if np.any((fields < 0.0) | (fields > 1.0)):
        raise ValueError("frequency_draws must be between zero and one")
    if np.any(population_array < 0.0):
        raise ValueError("population must be nonnegative")
    nordic = _mask(nordic_mask, "nordic_mask", n_cells)
    peak = _mask(peak_mask, "peak_mask", n_cells)
    if np.any(nordic & peak):
        raise ValueError("nordic and peak masks must be disjoint")

    masked_population = population_array[:, None] * np.column_stack((nordic, peak))
    population_totals = np.sum(masked_population, axis=0, dtype=np.float64)
    if np.any(population_totals <= 0.0):
        raise ValueError("each diagnostic mask must have positive population weight")
    group_weights = masked_population / population_totals
    group_frequencies = fields @ group_weights
    quantities = np.vstack(
        (
            amplitude_array,
            intercept_array,
            expit(intercept_array),
            group_frequencies[:, 0],
            group_frequencies[:, 1],
            group_frequencies[:, 1] - group_frequencies[:, 0],
        )
    )

    original = _positive_scalar(original_scale, "original_scale")
    scales = _candidate_scales(candidate_scales, original_scale=original)
    minimum_ess = _positive_scalar(
        minimum_effective_sample_size, "minimum_effective_sample_size"
    )
    if minimum_ess > n_draws:
        raise ValueError("minimum_effective_sample_size cannot exceed the number of draws")
    maximum_weight = _positive_scalar(maximum_single_weight, "maximum_single_weight")
    if maximum_weight > 1.0:
        raise ValueError("maximum_single_weight must be at most one")

    baseline_weights = half_normal_importance_weights(
        amplitude_array, original_scale=original, candidate_scale=original
    )
    baseline = _weighted_summaries(quantities, baseline_weights)
    candidates = []
    for scale in scales:
        weights = half_normal_importance_weights(
            amplitude_array, original_scale=original, candidate_scale=scale
        )
        effective_sample_size = float(1.0 / np.sum(np.square(weights), dtype=np.float64))
        largest_weight = float(np.max(weights))
        diagnostics_pass = (
            effective_sample_size >= minimum_ess and largest_weight <= maximum_weight
        )
        summaries = _weighted_summaries(quantities, weights)
        if scale == original:
            advance = False
            reason = "reference_prior"
        else:
            lowers_nordic = (
                summaries["population_weighted_nordic_frequency"].median
                < baseline["population_weighted_nordic_frequency"].median
            )
            preserves_contrast = (
                summaries["endemic_minus_nordic_frequency"].median
                >= baseline["endemic_minus_nordic_frequency"].median
            )
            advance = bool(diagnostics_pass and lowers_nordic and preserves_contrast)
            reason = (
                "passes_preflight_for_full_refit"
                if advance
                else "fails_importance_diagnostics_or_background_peak_direction"
            )
        candidates.append(
            PriorCandidateSensitivity(
                scale=scale,
                effective_sample_size=effective_sample_size,
                maximum_normalized_weight=largest_weight,
                importance_diagnostics_pass=diagnostics_pass,
                advance_to_full_refit=advance,
                decision_reason=reason,
                summaries=summaries,
            )
        )

    return AmplitudeSensitivityResult(
        n_draws=n_draws,
        n_cells=n_cells,
        nordic_cells=int(np.count_nonzero(nordic)),
        peak_cells=int(np.count_nonzero(peak)),
        nordic_population_weight=float(population_totals[0]),
        peak_population_weight=float(population_totals[1]),
        candidates=tuple(candidates),
    )
