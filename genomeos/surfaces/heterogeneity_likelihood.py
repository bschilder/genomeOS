"""Bounded beta-binomial likelihood evaluation (design §7.1; #214).

The expression is intended for an observed PyMC ``CustomDist``. Direct random
generation is deliberately unsupported; the public prediction path continues
to use ``CountPredictive``.
"""

from __future__ import annotations

import math

import pytensor.tensor as pt
from pymc.distributions.dist_math import check_parameters
from pytensor.tensor.variable import TensorVariable

_EXACT_PREFIX = 16
_SMALL_TAIL_BOUND = 1.0 / 8.0
_STIRLING_CORRECTIONS = (
    (1, 1.0 / 12.0),
    (3, -1.0 / 360.0),
    (5, 1.0 / 1260.0),
    (7, -1.0 / 1680.0),
    (9, 1.0 / 1188.0),
    (11, -691.0 / 360360.0),
)


def _log1p_ratio_minus_one(t: TensorVariable) -> TensorVariable:
    """Evaluate log1p(t) / t - 1 without a singular inactive branch."""
    small = pt.le(t, _SMALL_TAIL_BOUND)
    polynomial_argument = pt.where(small, t, _SMALL_TAIL_BOUND)
    polynomial = pt.as_tensor_variable(1.0 / 25.0)
    for power in range(23, 0, -1):
        polynomial = (-1.0) ** power / (power + 1) + polynomial_argument * polynomial
    polynomial_value = polynomial_argument * polynomial
    direct_argument = pt.where(small, _SMALL_TAIL_BOUND, t)
    direct_value = pt.log1p(direct_argument) / direct_argument - 1.0
    return pt.where(small, polynomial_value, direct_value)


def _log_rising_factorial(
    loga: TensorVariable, logr: TensorVariable, n: TensorVariable
) -> TensorVariable:
    """Evaluate ``sum(log(a + j*r), j=0..n-1)`` with bounded row-vector work."""
    exact = pt.zeros_like(loga + logr + n * 0.0)
    for index in range(_EXACT_PREFIX):
        factor = (
            loga
            if index == 0
            else pt.logaddexp(loga, math.log(index) + logr)
        )
        exact += pt.where(pt.gt(n, index), factor, 0.0)

    remaining = pt.maximum(n - _EXACT_PREFIX, 0)
    log_shifted = pt.logaddexp(loga, math.log(_EXACT_PREFIX) + logr)
    inverse_shifted = pt.exp(logr - log_shifted)
    tail_extent = remaining * inverse_shifted
    log_tail_ratio = pt.log1p(tail_extent)
    correction = pt.zeros_like(log_shifted + remaining * 0.0)
    for power, coefficient in _STIRLING_CORRECTIONS:
        correction += (
            coefficient
            * inverse_shifted**power
            * pt.expm1(-power * log_tail_ratio)
        )
    tail = (
        remaining * log_shifted
        + remaining * _log1p_ratio_minus_one(tail_extent)
        + (remaining - 0.5) * log_tail_ratio
        + correction
    )
    return exact + tail


def beta_binomial_logp(
    value: TensorVariable,
    n: TensorVariable,
    mean: TensorVariable,
    rho: TensorVariable,
) -> TensorVariable:
    """Return normalized per-observation beta-binomial log masses.

    Counts are scalar-support integers with ``0 <= value <= n``. ``mean`` and
    ``rho`` must lie strictly inside (0, 1). The fitter validates these domains
    before graph construction; checks here preserve the distribution boundary
    when the expression is evaluated directly.
    """
    value = pt.as_tensor_variable(value)
    n = pt.as_tensor_variable(n)
    mean = pt.as_tensor_variable(mean)
    rho = pt.as_tensor_variable(rho)

    log_rho = pt.log(rho)
    log_one_minus_rho = pt.log1p(-rho)
    log_mean_shape = pt.log(mean) + log_one_minus_rho
    log_complement_shape = pt.log1p(-mean) + log_one_minus_rho
    smaller_count = pt.minimum(value, n - value)
    log_choose = pt.where(
        pt.eq(smaller_count, 0),
        0.0,
        pt.gammaln(n + 1)
        - pt.gammaln(smaller_count + 1)
        - pt.gammaln(n - smaller_count + 1),
    )
    logp = (
        log_choose
        + _log_rising_factorial(log_mean_shape, log_rho, value)
        + _log_rising_factorial(log_complement_shape, log_rho, n - value)
        - _log_rising_factorial(log_one_minus_rho, log_rho, n)
    )
    supported = (
        pt.ge(value, 0)
        & pt.le(value, n)
        & pt.eq(value, pt.floor(value))
    )
    logp = pt.where(supported, logp, -math.inf)
    logp = check_parameters(
        logp,
        pt.ge(n, 0),
        pt.eq(n, pt.floor(n)),
        msg="n must be a nonnegative integer",
    )
    return check_parameters(
        logp,
        pt.gt(mean, 0),
        pt.lt(mean, 1),
        pt.gt(rho, 0),
        pt.lt(rho, 1),
        msg="mean and rho must be strictly between 0 and 1",
    )
