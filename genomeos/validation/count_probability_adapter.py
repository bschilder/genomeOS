"""Vectorized count-probability integration (design §§7–8; #341 design §4).

The reviewed numerical core keeps its frozen source identity. This module owns
the production-facing shape transformation and chooses one of the core's three
proved support widths from a validated host count bound. NumPy and CuPy remain
explicit caller-supplied namespaces; no backend is imported or selected here.
"""

from __future__ import annotations

from typing import Any

from genomeos.validation.count_probability import (
    NormalizedProbabilities,
    _beta_binomial_probability_mean,
)
from genomeos.validation.count_scaled import ScaledPair, to_float64


def support_chunk_for_bound(max_count: int) -> int:
    """Return the smallest proved support chunk that covers the host bound."""
    if isinstance(max_count, bool) or not isinstance(max_count, int):
        raise TypeError("max_count must be a host integer, excluding bool")
    if not 1 <= max_count <= 65_536:
        raise ValueError("max_count must be within 1..65536")
    if max_count <= 32:
        return 32
    if max_count <= 256:
        return 256
    return 1024


def _reshape(value: ScaledPair, shape: tuple[int, int]) -> ScaledPair:
    return ScaledPair(
        value.hi.reshape(shape),
        value.lo.reshape(shape),
        value.exponent.reshape(shape),
    )


def beta_binomial_probability_queries(
    mean: Any,
    concentration: Any,
    an: Any,
    ac: Any,
    *,
    array_module: Any,
    max_count: int,
) -> NormalizedProbabilities:
    """Evaluate a query-by-observation matrix without scalar scientific dispatch.

    ``mean`` and ``concentration`` have shape ``(draws, observations)``;
    ``an`` has shape ``(observations,)`` and ``ac`` has shape
    ``(queries, observations)``. The caller owns scientific-domain validation.
    Query and observation axes are flattened into the reviewed core's observation
    axis while posterior draws remain vectorized.
    """
    xp = array_module
    if mean.ndim != 2 or concentration.shape != mean.shape:
        raise ValueError("mean and concentration must share a two-dimensional shape")
    if an.ndim != 1 or an.shape != (mean.shape[1],):
        raise ValueError("an must have the predictive observation shape")
    if ac.ndim != 2 or ac.shape[1] != mean.shape[1] or ac.shape[0] == 0:
        raise ValueError("ac must have a nonempty query-by-observation shape")

    queries, observations = ac.shape
    expanded_shape = (mean.shape[0], queries, observations)
    expanded_mean = xp.broadcast_to(mean[:, None, :], expanded_shape).reshape(mean.shape[0], -1)
    expanded_concentration = xp.broadcast_to(
        concentration[:, None, :], expanded_shape
    ).reshape(mean.shape[0], -1)
    expanded_an = xp.broadcast_to(an[None, :], (queries, observations)).reshape(-1)
    result = _beta_binomial_probability_mean(
        expanded_mean,
        expanded_concentration,
        expanded_an,
        ac.reshape(-1),
        array_module=xp,
        max_count=max_count,
        support_chunk_size=support_chunk_for_bound(max_count),
    )
    shape = (queries, observations)
    return NormalizedProbabilities(
        _reshape(result.mass, shape),
        _reshape(result.lower, shape),
        _reshape(result.upper, shape),
    )


def probability_float64(value: ScaledPair, *, array_module: Any) -> Any:
    """Correctly round a direct-core probability at the public float64 boundary."""
    return to_float64(value, array_module=array_module)


def probability_log(value: ScaledPair, *, array_module: Any) -> Any:
    """Return a finite-support log probability without physical underflow."""
    xp = array_module
    to_float64(value, array_module=xp)
    zero = value.hi == 0
    high = xp.where(zero, 0.5, value.hi)
    residual = xp.where(zero, 0.0, value.lo)
    return xp.where(
        zero,
        -xp.inf,
        xp.log(high)
        + xp.log1p(residual / high)
        + value.exponent.astype(xp.float64) * xp.log(2.0),
    )
