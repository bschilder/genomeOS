"""Independent B0H numerical reference (design §§5, 7–8, 12; #211).

This validation-only module evaluates the finite-product count likelihood and
Beta-weighted tensor-product quadrature without consuming production fitting or
scoring functions. A returned result is one finite-order quadrature estimate,
not a certificate that the quadrature sequence has converged.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from numbers import Integral, Real

import numpy as np
from scipy.special import roots_jacobi


def _bounded_integer(value: object, name: str, *, minimum: int, maximum: int) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Integral):
        raise ValueError(f"{name} must be an integer")
    normalized = int(value)
    if not minimum <= normalized <= maximum:
        raise ValueError(f"{name} must satisfy {minimum} <= {name} <= {maximum}")
    return normalized


def _parameter_array(value: object, name: str) -> np.ndarray:
    array = np.asarray(value)
    if array.size == 0:
        raise ValueError(f"{name} must be nonempty")
    if array.dtype.kind not in "iuf":
        raise ValueError(f"{name} must be a real numeric array")
    normalized = np.asarray(array, dtype=np.float64)
    if not np.all(np.isfinite(normalized)):
        raise ValueError(f"{name} must be finite")
    return normalized


def _broadcast_parameters(mean: object, rho: object) -> tuple[np.ndarray, np.ndarray]:
    mean_array = _parameter_array(mean, "mean")
    rho_array = _parameter_array(rho, "rho")
    try:
        mean_grid, rho_grid = np.broadcast_arrays(mean_array, rho_array)
    except ValueError as error:
        raise ValueError("mean and rho must have broadcast-compatible shapes") from error
    if np.any((mean_grid <= 0.0) | (mean_grid >= 1.0)):
        raise ValueError("mean must be strictly between 0 and 1")
    if np.any((rho_grid < 0.0) | (rho_grid >= 1.0)):
        raise ValueError("rho must satisfy 0 <= rho < 1")
    return mean_grid, rho_grid


def _count_pair(ac: object, an: object) -> tuple[int, int]:
    normalized_ac = _bounded_integer(ac, "ac", minimum=0, maximum=64)
    normalized_an = _bounded_integer(an, "an", minimum=0, maximum=64)
    if normalized_ac > normalized_an:
        raise ValueError("ac must not exceed an")
    return normalized_ac, normalized_an


def heterogeneity_log_mass(
    ac: int,
    an: int,
    *,
    mean: np.ndarray,
    rho: np.ndarray,
) -> np.ndarray:
    """Evaluate one beta-binomial count log mass by independent finite products."""
    normalized_ac, normalized_an = _count_pair(ac, an)
    mean_grid, rho_grid = _broadcast_parameters(mean, rho)
    if normalized_an == 0:
        return np.zeros(mean_grid.shape, dtype=np.float64)

    logp = np.full(
        mean_grid.shape,
        math.log(math.comb(normalized_an, normalized_ac)),
        dtype=np.float64,
    )
    with np.errstate(divide="ignore", invalid="ignore"):
        for j in range(normalized_ac):
            logp += np.log(mean_grid * (1.0 - rho_grid) + j * rho_grid)
        for j in range(normalized_an - normalized_ac):
            logp += np.log((1.0 - mean_grid) * (1.0 - rho_grid) + j * rho_grid)
        for j in range(normalized_an):
            logp -= np.log((1.0 - rho_grid) + j * rho_grid)
    if not np.all(np.isfinite(logp)):
        raise ArithmeticError("heterogeneity log mass must be finite")
    return logp


def _positive_real_pair(value: object, name: str) -> tuple[float, float]:
    try:
        pair = tuple(value)  # type: ignore[arg-type]
    except TypeError as error:
        raise ValueError(f"{name} must contain exactly two positive finite shapes") from error
    if len(pair) != 2:
        raise ValueError(f"{name} must contain exactly two positive finite shapes")
    normalized = []
    for item in pair:
        if isinstance(item, (bool, np.bool_)) or not isinstance(item, Real):
            raise ValueError(f"{name} shapes must be positive and finite")
        try:
            shape = float(item)
        except OverflowError as error:
            raise ValueError(f"{name} shapes must be positive and finite") from error
        if not math.isfinite(shape) or shape <= 0.0:
            raise ValueError(f"{name} shapes must be positive and finite")
        normalized.append(shape)
    return normalized[0], normalized[1]


def _counts(value: object) -> tuple[tuple[int, int], ...]:
    try:
        consumed = tuple(value)  # type: ignore[arg-type]
    except TypeError as error:
        raise ValueError("counts must be a sequence of (ac, an) pairs") from error
    normalized = []
    for item in consumed:
        try:
            pair = tuple(item)  # type: ignore[arg-type]
        except TypeError as error:
            raise ValueError("counts must contain only (ac, an) pairs") from error
        if len(pair) != 2:
            raise ValueError("counts must contain only (ac, an) pairs")
        normalized.append(_count_pair(pair[0], pair[1]))
    return tuple(normalized)


def _beta_quadrature(
    prior: tuple[float, float], order: int, name: str
) -> tuple[np.ndarray, np.ndarray]:
    alpha, beta = prior
    try:
        raw_nodes, raw_weights = roots_jacobi(order, beta - 1.0, alpha - 1.0)
    except (TypeError, ValueError) as error:
        raise ArithmeticError(f"{name} quadrature failed") from error
    nodes = (np.asarray(raw_nodes, dtype=np.float64) + 1.0) / 2.0
    weights = np.asarray(raw_weights, dtype=np.float64)
    if (
        nodes.shape != (order,)
        or not np.all(np.isfinite(nodes))
        or np.any((nodes <= 0.0) | (nodes >= 1.0))
        or weights.shape != (order,)
        or not np.all(np.isfinite(weights))
        or np.any(weights <= 0.0)
    ):
        raise ArithmeticError(f"{name} quadrature numerically degenerated")
    weight_sum = float(np.sum(weights))
    if not math.isfinite(weight_sum) or weight_sum <= 0.0:
        raise ArithmeticError(f"{name} quadrature weights failed normalization")
    normalized_weights = weights / weight_sum
    if (
        not np.all(np.isfinite(normalized_weights))
        or np.any(normalized_weights <= 0.0)
        or not math.isclose(float(np.sum(normalized_weights)), 1.0, rel_tol=0.0, abs_tol=1e-14)
    ):
        raise ArithmeticError(f"{name} quadrature weights failed normalization")
    return nodes, normalized_weights


@dataclass(frozen=True)
class HeterogeneityQuadrature:
    """Finite-order posterior moments, evidence, and one predictive count mass vector."""

    order: int
    log_evidence: float
    mean: float
    mean_squared: float
    rho: float
    rho_squared: float
    mean_rho: float
    predictive_an: int
    predictive_masses: tuple[float, ...]


def heterogeneity_quadrature(
    counts: Sequence[tuple[int, int]],
    *,
    mean_prior: tuple[float, float],
    rho_prior: tuple[float, float],
    predictive_an: int,
    order: int,
) -> HeterogeneityQuadrature:
    """Integrate one small B0H posterior on a Beta-weighted Jacobi product grid."""
    count_pairs = _counts(counts)
    normalized_mean_prior = _positive_real_pair(mean_prior, "mean_prior")
    normalized_rho_prior = _positive_real_pair(rho_prior, "rho_prior")
    normalized_predictive_an = _bounded_integer(
        predictive_an, "predictive_an", minimum=0, maximum=64
    )
    normalized_order = _bounded_integer(order, "order", minimum=2, maximum=512)

    mean_nodes, mean_weights = _beta_quadrature(
        normalized_mean_prior, normalized_order, "mean_prior"
    )
    rho_nodes, rho_weights = _beta_quadrature(
        normalized_rho_prior, normalized_order, "rho_prior"
    )
    mean_grid = mean_nodes[:, None]
    rho_grid = rho_nodes[None, :]
    log_grid = np.log(mean_weights[:, None]) + np.log(rho_weights[None, :])
    for ac, an in count_pairs:
        log_grid += heterogeneity_log_mass(ac, an, mean=mean_grid, rho=rho_grid)
    if not np.all(np.isfinite(log_grid)):
        raise ArithmeticError("quadrature log integrand must be finite")

    maximum = float(np.max(log_grid))
    shifted = np.exp(log_grid - maximum)
    shifted_sum = float(np.sum(shifted))
    if not math.isfinite(shifted_sum) or shifted_sum <= 0.0:
        raise ArithmeticError("quadrature evidence failed normalization")
    log_evidence = maximum + math.log(shifted_sum)
    posterior_weights = shifted / shifted_sum
    if (
        not math.isfinite(log_evidence)
        or not np.all(np.isfinite(posterior_weights))
        or np.any(posterior_weights < 0.0)
        or not math.isclose(
            float(np.sum(posterior_weights)), 1.0, rel_tol=0.0, abs_tol=1e-14
        )
    ):
        raise ArithmeticError("quadrature posterior failed normalization")

    def expectation(values: np.ndarray) -> float:
        result = float(np.sum(posterior_weights * values))
        if not math.isfinite(result):
            raise ArithmeticError("quadrature moment must be finite")
        return result

    predictive_masses = tuple(
        expectation(
            np.exp(
                heterogeneity_log_mass(
                    ac,
                    normalized_predictive_an,
                    mean=mean_grid,
                    rho=rho_grid,
                )
            )
        )
        for ac in range(normalized_predictive_an + 1)
    )
    predictive_sum = math.fsum(predictive_masses)
    if (
        any(not math.isfinite(mass) or mass < 0.0 for mass in predictive_masses)
        or not math.isclose(predictive_sum, 1.0, rel_tol=0.0, abs_tol=1e-10)
    ):
        raise ArithmeticError("predictive masses failed normalization")

    return HeterogeneityQuadrature(
        order=normalized_order,
        log_evidence=log_evidence,
        mean=expectation(mean_grid),
        mean_squared=expectation(mean_grid * mean_grid),
        rho=expectation(rho_grid),
        rho_squared=expectation(rho_grid * rho_grid),
        mean_rho=expectation(mean_grid * rho_grid),
        predictive_an=normalized_predictive_an,
        predictive_masses=predictive_masses,
    )
