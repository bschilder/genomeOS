"""Independent B0H posterior-dependence reference (design §§5, 7–8, 12; #211).

This pure validation module evaluates the continuous dependence diagnostic from
the B0H simulation-calibration design. Its finite-order comparisons are
empirical numerical guards, not proofs of quadrature error or sampler quality.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from numbers import Integral, Real

import numpy as np
from scipy.special import logsumexp

from genomeos.validation.heterogeneity_oracle import (
    beta_prior_quadrature,
    heterogeneity_log_mass,
    heterogeneity_quadrature,
)

_ORDERS = (64, 128, 256)
_CONVERGENCE_TOLERANCE = 1e-6
_ROUNDING_MULTIPLIER = 64.0
_POINT_SCALAR_TYPES = (float, np.float16, np.float32, np.float64)


@dataclass(frozen=True)
class DependencePointReference:
    """Finite-order dependence evidence at one interior parameter point."""

    mean: float
    rho: float
    components: tuple[tuple[float, float, float, float], ...]
    raw_values: tuple[float, ...]
    value: float
    error_bound: float
    resolved: bool


@dataclass(frozen=True)
class HeterogeneityDependenceReference:
    """Ordered point references under one likelihood and pair of priors."""

    orders: tuple[int, ...]
    analytic_separability: bool
    points: tuple[DependencePointReference, ...]


@dataclass(frozen=True)
class DependenceComparisons:
    """Four draw orderings and an order-major 3-by-4 raw comparison tuple."""

    status: str
    comparisons_by_order: tuple[tuple[int, ...], ...]
    comparisons: tuple[int, ...] | None


def _finite_interior_scalar(value: object, name: str) -> float:
    if type(value) not in _POINT_SCALAR_TYPES:
        raise ValueError(
            f"{name} must be a built-in float or NumPy float16, float32, or "
            "float64 scalar strictly inside (0, 1)"
        )
    normalized = float(value)
    if not math.isfinite(normalized) or not 0.0 < normalized < 1.0:
        raise ValueError(f"{name} must be a finite scalar strictly inside (0, 1)")
    return normalized


def _parameter_points(value: object) -> tuple[tuple[float, float], ...]:
    try:
        consumed = tuple(value)  # type: ignore[arg-type]
    except TypeError as error:
        raise ValueError("points must be a nonempty sequence of (mean, rho) pairs") from error
    if not consumed:
        raise ValueError("points must be a nonempty sequence of (mean, rho) pairs")
    normalized = []
    for item in consumed:
        try:
            pair = tuple(item)  # type: ignore[arg-type]
        except TypeError as error:
            raise ValueError("points must contain only (mean, rho) pairs") from error
        if len(pair) != 2:
            raise ValueError("points must contain only (mean, rho) pairs")
        normalized.append(
            (
                _finite_interior_scalar(pair[0], "mean"),
                _finite_interior_scalar(pair[1], "rho"),
            )
        )
    return tuple(normalized)


def _consume_counts(value: object) -> tuple[object, ...]:
    try:
        return tuple(value)  # type: ignore[arg-type]
    except TypeError as error:
        raise ValueError("counts must be a sequence of (ac, an) pairs") from error


def _training_log_likelihood(
    counts: tuple[tuple[int, int], ...], *, mean: object, rho: object
) -> np.ndarray:
    mean_array, rho_array = np.broadcast_arrays(
        np.asarray(mean, dtype=np.float64), np.asarray(rho, dtype=np.float64)
    )
    result = np.zeros(mean_array.shape, dtype=np.float64)
    for ac, an in counts:
        result += heterogeneity_log_mass(ac, an, mean=mean_array, rho=rho_array)
    if not np.all(np.isfinite(result)):
        raise ArithmeticError("dependence likelihood must be finite")
    return result


def _finite_logsumexp(values: np.ndarray, name: str) -> float:
    if not np.all(np.isfinite(values)):
        raise ArithmeticError(f"{name} log integrand must be finite")
    result = float(logsumexp(values))
    if not math.isfinite(result):
        raise ArithmeticError(f"{name} integral must be finite")
    return result


def _is_analytically_separable(counts: tuple[tuple[int, int], ...]) -> bool:
    return all(
        an == 0 or an == 1 or (ac == 1 and an == 2)
        for ac, an in counts
    )


def heterogeneity_dependence_reference(
    counts: Sequence[tuple[int, int]],
    *,
    mean_prior: tuple[float, float],
    rho_prior: tuple[float, float],
    points: Sequence[tuple[float, float]],
) -> HeterogeneityDependenceReference:
    """Evaluate h at fixed points with the frozen three-order numerical guard."""
    normalized_points = _parameter_points(points)
    consumed_counts = _consume_counts(counts)
    components_by_point: list[list[tuple[float, float, float, float]]] = [
        [] for _ in normalized_points
    ]
    raw_by_point: list[list[float]] = [[] for _ in normalized_points]
    normalized_counts: tuple[tuple[int, int], ...] | None = None

    for order in _ORDERS:
        quadrature = heterogeneity_quadrature(
            consumed_counts,  # type: ignore[arg-type]
            mean_prior=mean_prior,
            rho_prior=rho_prior,
            predictive_an=0,
            order=order,
        )
        if normalized_counts is None:
            normalized_counts = tuple(
                (int(pair[0]), int(pair[1]))  # type: ignore[index]
                for pair in consumed_counts
            )
        mean_nodes, mean_weights = beta_prior_quadrature(mean_prior, order=order)
        rho_nodes, rho_weights = beta_prior_quadrature(rho_prior, order=order)
        log_mean_weights = np.log(mean_weights)
        log_rho_weights = np.log(rho_weights)

        for index, (mean, rho) in enumerate(normalized_points):
            log_likelihood = float(
                _training_log_likelihood(
                    normalized_counts, mean=np.array(mean), rho=np.array(rho)
                )
            )
            log_fixed_mean = _finite_logsumexp(
                log_rho_weights
                + _training_log_likelihood(
                    normalized_counts, mean=mean, rho=rho_nodes
                ),
                "fixed-mean",
            )
            log_fixed_rho = _finite_logsumexp(
                log_mean_weights
                + _training_log_likelihood(
                    normalized_counts, mean=mean_nodes, rho=rho
                ),
                "fixed-rho",
            )
            components = (
                log_likelihood,
                quadrature.log_evidence,
                log_fixed_mean,
                log_fixed_rho,
            )
            if not all(math.isfinite(term) for term in components):
                raise ArithmeticError("dependence components must be finite")
            raw_value = (
                log_likelihood
                + quadrature.log_evidence
                - log_fixed_mean
                - log_fixed_rho
            )
            if not math.isfinite(raw_value):
                raise ArithmeticError("dependence value must be finite")
            components_by_point[index].append(components)
            raw_by_point[index].append(raw_value)

    if normalized_counts is None:  # pragma: no cover - the frozen order tuple is nonempty
        raise AssertionError("dependence orders must be nonempty")
    analytic_separability = _is_analytically_separable(normalized_counts)
    point_results = []
    epsilon = np.finfo(np.float64).eps
    for (mean, rho), component_rows, raw_values in zip(
        normalized_points, components_by_point, raw_by_point, strict=True
    ):
        component_scale = max(
            1.0 + sum(abs(term) for term in row) for row in component_rows
        )
        gaps = (
            abs(raw_values[1] - raw_values[0]),
            abs(raw_values[2] - raw_values[1]),
        )
        error_bound = max(*gaps, _ROUNDING_MULTIPLIER * epsilon * component_scale)
        if not math.isfinite(error_bound):
            raise ArithmeticError("dependence error bound must be finite")
        resolved = all(gap <= _CONVERGENCE_TOLERANCE for gap in gaps)
        if analytic_separability:
            resolved = resolved and all(
                abs(value) <= _CONVERGENCE_TOLERANCE for value in raw_values
            )
        point_results.append(
            DependencePointReference(
                mean=mean,
                rho=rho,
                components=tuple(component_rows),
                raw_values=tuple(raw_values),
                value=0.0 if analytic_separability else raw_values[-1],
                error_bound=error_bound,
                resolved=resolved,
            )
        )
    return HeterogeneityDependenceReference(
        orders=_ORDERS,
        analytic_separability=analytic_separability,
        points=tuple(point_results),
    )


def _finite_reference_scalar(value: object, name: str) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a finite real scalar")
    normalized = float(value)
    if not math.isfinite(normalized):
        raise ArithmeticError(f"{name} must be finite")
    return normalized


def _validate_reference(reference: object) -> HeterogeneityDependenceReference:
    if not isinstance(reference, HeterogeneityDependenceReference):
        raise ValueError("reference must be a HeterogeneityDependenceReference")
    if reference.orders != _ORDERS:
        raise ValueError("reference orders must be exactly (64, 128, 256)")
    if not isinstance(reference.analytic_separability, bool):
        raise ValueError("analytic_separability must be Boolean")
    if not isinstance(reference.points, tuple) or not reference.points:
        raise ValueError("reference points must be a nonempty tuple")
    for point in reference.points:
        if not isinstance(point, DependencePointReference):
            raise ValueError("reference contains a malformed point")
        _finite_interior_scalar(point.mean, "point mean")
        _finite_interior_scalar(point.rho, "point rho")
        if not isinstance(point.components, tuple) or len(point.components) != len(_ORDERS):
            raise ValueError("point components must match the reference orders")
        for components in point.components:
            if not isinstance(components, tuple) or len(components) != 4:
                raise ValueError("each point component row must contain four terms")
            for term in components:
                _finite_reference_scalar(term, "point component")
        if not isinstance(point.raw_values, tuple) or len(point.raw_values) != len(_ORDERS):
            raise ValueError("point raw values must match the reference orders")
        for raw_value in point.raw_values:
            _finite_reference_scalar(raw_value, "point raw value")
        _finite_reference_scalar(point.value, "point value")
        error_bound = _finite_reference_scalar(point.error_bound, "point error bound")
        if error_bound < 0.0:
            raise ValueError("point error bound must be nonnegative")
        if not isinstance(point.resolved, bool):
            raise ValueError("point resolved must be Boolean")
    return reference


def _reference_index(value: object, name: str, *, point_count: int) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Integral):
        raise ValueError(f"{name} must be an integer")
    normalized = int(value)
    if not 0 <= normalized < point_count:
        raise ValueError(f"{name} is outside the reference points")
    return normalized


def dependence_comparisons(
    reference: HeterogeneityDependenceReference,
    *,
    truth_index: int,
    draw_indices: Sequence[int],
) -> DependenceComparisons:
    """Resolve four draws and retain signs by order, then draw-index position."""
    validated = _validate_reference(reference)
    normalized_truth = _reference_index(
        truth_index, "truth_index", point_count=len(validated.points)
    )
    try:
        consumed_draws = tuple(draw_indices)
    except TypeError as error:
        raise ValueError("draw_indices must contain exactly four indices") from error
    if len(consumed_draws) != 4:
        raise ValueError("draw_indices must contain exactly four indices")
    normalized_draws = tuple(
        _reference_index(item, "draw index", point_count=len(validated.points))
        for item in consumed_draws
    )
    if normalized_truth in normalized_draws or len(set(normalized_draws)) != 4:
        raise ValueError("draw indices must be distinct and different from truth_index")

    truth = validated.points[normalized_truth]
    comparisons_by_order = tuple(
        tuple(
            (validated.points[draw_index].raw_values[order_index] > truth.raw_values[order_index])
            - (validated.points[draw_index].raw_values[order_index] < truth.raw_values[order_index])
            for draw_index in normalized_draws
        )
        for order_index in range(len(_ORDERS))
    )
    used_points = (truth, *(validated.points[index] for index in normalized_draws))
    if any(not point.resolved for point in used_points):
        return DependenceComparisons(
            status="dependence_reference_unresolved",
            comparisons_by_order=comparisons_by_order,
            comparisons=None,
        )

    resolved_comparisons = []
    rank_order_resolved = True
    for draw_position, draw_index in enumerate(normalized_draws):
        draw = validated.points[draw_index]
        if validated.analytic_separability or (
            draw.mean == truth.mean and draw.rho == truth.rho
        ):
            resolved_comparisons.append(0)
            continue
        signs = tuple(row[draw_position] for row in comparisons_by_order)
        contrast = abs(draw.raw_values[-1] - truth.raw_values[-1])
        guard_sum = draw.error_bound + truth.error_bound
        if not math.isfinite(contrast) or not math.isfinite(guard_sum):
            raise ArithmeticError("dependence comparison arithmetic must be finite")
        if signs[0] == 0 or len(set(signs)) != 1 or contrast <= guard_sum:
            rank_order_resolved = False
        resolved_comparisons.append(signs[-1])

    if not rank_order_resolved:
        return DependenceComparisons(
            status="dependence_rank_order_unresolved",
            comparisons_by_order=comparisons_by_order,
            comparisons=None,
        )
    return DependenceComparisons(
        status="resolved",
        comparisons_by_order=comparisons_by_order,
        comparisons=tuple(resolved_comparisons),
    )
