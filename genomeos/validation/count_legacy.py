"""Validated lower-concentration count arithmetic (design §§7–8; #341 design §5).

These routines retain the pre-#341 finite-product log mass and shorter-tail CDF
for concentrations through ``1 / sqrt(float64 epsilon)``. The predictive policy
module decides which draws may use this route; this module performs no fallback
or distribution substitution.
"""

from __future__ import annotations

import numpy as np
from scipy.special import betaln, gammaln, logsumexp

_CHUNK_SIZE = 4096
_DRAW_CHUNK_SIZE = 128
_LOG_HALF = float(np.log(0.5))


def beta_product_log_mass(k: int, n: int, mean: np.ndarray, c: np.ndarray) -> np.ndarray:
    """Evaluate stable beta-binomial log masses for validated aligned draws."""
    result = np.zeros(mean.shape)
    smaller = min(k, n - k)
    log_choose = 0.0
    for start in range(1, smaller + 1, _CHUNK_SIZE):
        index = np.arange(start, min(start + _CHUNK_SIZE, smaller + 1))
        log_choose += float(np.sum(np.log1p((n - smaller) / index)))
    for draw_start in range(0, mean.size, _DRAW_CHUNK_SIZE):
        stop = draw_start + _DRAW_CHUNK_SIZE
        p = mean[draw_start:stop, None]
        concentration = c[draw_start:stop, None]
        alpha, beta = p * concentration, (1.0 - p) * concentration
        total = np.full(p.shape[0], log_choose)
        for start in range(0, n, _CHUNK_SIZE):
            index = np.arange(start, min(start + _CHUNK_SIZE, n))[None, :]
            success = index < k
            numerator = np.where(success, alpha + index, beta + (index - k))
            denominator = concentration + index
            complement = np.where(success, beta, alpha + k) / denominator
            terms = np.log(numerator) - np.log(denominator)
            near_one = complement < 0.5
            terms[near_one] = np.log1p(-complement[near_one])
            if start == 0:
                terms[:, 0] = np.log(p[:, 0]) if k else np.log1p(-p[:, 0])
            total += np.sum(terms, axis=1)
        result[draw_start:stop] = total
    if np.any(~np.isfinite(result)) or np.any(result > 0.0):
        raise FloatingPointError("beta-binomial log mass is outside the stable numeric domain")
    return result


def _log_combination(n: int | np.ndarray, k: np.ndarray) -> np.ndarray:
    return gammaln(np.asarray(n) + 1) - gammaln(k + 1) - gammaln(np.asarray(n) - k + 1)


def _log_mass(k: np.ndarray, n: int, alpha: float, beta: float) -> np.ndarray:
    return _log_combination(n, k) + betaln(k + alpha, n - k + beta) - betaln(alpha, beta)


def _tail_logsum(start: int, stop: int, n: int, alpha: float, beta: float) -> float:
    total = -np.inf
    for chunk_start in range(start, stop, _CHUNK_SIZE):
        chunk_stop = min(chunk_start + _CHUNK_SIZE, stop)
        support = np.arange(chunk_start, chunk_stop, dtype=np.int64)
        total = float(np.logaddexp(total, logsumexp(_log_mass(support, n, alpha, beta))))
    return total


def beta_binomial_cdf(k: int, n: int, mean: float, concentration: float) -> float:
    """Evaluate one validated lower-concentration beta-binomial CDF."""
    if k < 0:
        return 0.0
    if k >= n:
        return 1.0
    if mean == 0.0:
        return 1.0
    if mean == 1.0:
        return 0.0

    alpha = mean * concentration
    beta = (1.0 - mean) * concentration
    lower_terms = k + 1
    upper_terms = n - k
    if lower_terms <= upper_terms:
        log_cdf = _tail_logsum(0, k + 1, n, alpha, beta)
        if log_cdf <= _LOG_HALF:
            result = float(np.exp(log_cdf))
        else:
            log_survival = _tail_logsum(k + 1, n + 1, n, alpha, beta)
            result = float(-np.expm1(log_survival))
    else:
        log_survival = _tail_logsum(k + 1, n + 1, n, alpha, beta)
        if log_survival <= _LOG_HALF:
            result = float(-np.expm1(log_survival))
        else:
            result = float(np.exp(_tail_logsum(0, k + 1, n, alpha, beta)))
    if not np.isfinite(result) or not 0.0 <= result <= 1.0:
        raise FloatingPointError("beta-binomial CDF is outside the stable numeric domain")
    return result
