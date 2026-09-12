"""Finite beta-binomial relative weights for offline scoring (design §7, §8).

The caller owns validation: broadcast inputs must contain interior means, usable positive
finite concentrations, positive integer AN, and integer thresholds from -1 through AN.
``max_count`` is a positive host-known upper bound on AN. NumPy and CuPy are the two
supported explicit namespaces; this module imports neither backend nor any I/O dependency.

Complete support is traversed from a legal mode in both directions. Working batches contain
at most four query rows and 128 draws, and support buffers contain at most 1024 entries.
The row/draw axes are flattened inside each working batch (at most 512 scalar laws).
Hillis-Steele tree prefixes use a current and a copied prefix
buffer; ratio/factor temporaries, support indices, masks and reduction exponentials are also
bounded by that grid. Carries, compensation and three partitions are one value per law.
Output/broadcast input storage scales with requested laws, never with complete support.
These bounds describe live arrays, not allocator pools, process RSS or device-driver memory;
actual peak measurements must state which of those they include.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

SUPPORT_CHUNK_SIZE = 1024
DRAW_CHUNK_SIZE = 128
ROW_CHUNK_SIZE = 4


@dataclass(frozen=True)
class LogPartitions:
    """Below, equal and above threshold log weights, with a common arbitrary scale."""

    below: Any
    equal: Any
    above: Any

    def log_mass(self, *, array_module: Any) -> Any:
        xp = array_module
        return -xp.logaddexp(0.0, xp.logaddexp(self.below, self.above) - self.equal)

    def tails(self, *, array_module: Any) -> tuple[Any, Any]:
        """Return P(Y<=AC) and P(Y>AC), evaluating the smaller tail directly."""
        xp = array_module
        lower = xp.logaddexp(self.below, self.equal)
        upper = self.above
        log_lower = -xp.logaddexp(0.0, upper - lower)
        log_upper = -xp.logaddexp(0.0, lower - upper)
        return (
            xp.where(lower <= upper, xp.exp(log_lower), -xp.expm1(log_upper)),
            xp.where(upper <= lower, xp.exp(log_upper), -xp.expm1(log_lower)),
        )


def _tree_prefix(values: Any, xp: Any) -> Any:
    result = values.copy()
    step = 1
    while step < result.shape[-1]:
        previous = result.copy()
        result[..., step:] = previous[..., step:] + previous[..., :-step]
        step *= 2
    return result


def _logsum(values: Any, xp: Any) -> Any:
    maximum = xp.max(values, axis=-1)
    safe = xp.where(xp.isfinite(maximum), maximum, 0.0)
    total = xp.sum(xp.exp(values - safe[..., None]), axis=-1)
    # Empty partitions are exact -inf without log(0) warnings.
    return xp.where(total > 0, safe + xp.log(xp.where(total > 0, total, 1.0)), -xp.inf)


def _mode(p: Any, c: Any, n: Any, xp: Any) -> Any:
    small_alpha = xp.log(p) + xp.log(c) <= 0.0
    small_beta = xp.log1p(-p) + xp.log(c) <= 0.0
    both_large = ~small_alpha & ~small_beta
    safe_c = xp.where(both_large, c, 3.0)
    inverse = 1.0 / safe_c
    candidate = xp.floor((n + 1) * (p - inverse) / (1 - 2 * inverse))
    candidate = xp.minimum(n, xp.maximum(0, candidate)).astype(xp.int64)
    endpoint = xp.where(small_alpha & (~small_beta | (p <= 0.5)), 0, n)
    return xp.where(both_large, candidate, endpoint)


def _batch(p: Any, c: Any, n: Any, target: Any, max_count: int, xp: Any) -> LogPartitions:
    anchor = _mode(p, c, n, xp)
    below = xp.where(anchor < target, 0.0, -xp.inf)
    equal = xp.where(anchor == target, 0.0, -xp.inf)
    above = xp.where(anchor > target, 0.0, -xp.inf)
    log_scale = xp.log(xp.maximum(1.0, c))
    # Cancel log(c)-log(scale) exactly when c>=1, before adding log(p).
    log_shape_scale = xp.where(c >= 1.0, 0.0, xp.log(c))
    log_alpha = xp.log(p) + log_shape_scale
    log_beta = xp.log1p(-p) + log_shape_scale
    for direction in (1, -1):
        carry = xp.zeros(p.shape, dtype=xp.float64)
        compensation = xp.zeros_like(carry)
        for start in range(1, max_count + 1, SUPPORT_CHUNK_SIZE):
            offsets = xp.arange(start, min(start + SUPPORT_CHUNK_SIZE, max_count + 1))
            support = anchor[:, None] + direction * offsets[None, :]
            valid = (support >= 0) & (support <= n[:, None])
            # Invalid padded lanes contribute neither a ratio nor a weight.
            k = xp.where(valid, support - (direction == 1), 0)
            failure_index = n[:, None] - k - 1
            log_k = xp.log(xp.maximum(k, 1)) - log_scale[:, None]
            log_failure = xp.log(xp.maximum(failure_index, 1)) - log_scale[:, None]
            success = xp.logaddexp(log_alpha[:, None], xp.where(k > 0, log_k, -xp.inf))
            failure = xp.logaddexp(log_beta[:, None], xp.where(failure_index > 0, log_failure, -xp.inf))
            ratios = (xp.log(n[:, None] - k) - xp.log(k + 1)) + (success - failure)
            prefix = _tree_prefix(xp.where(valid, direction * ratios, 0.0), xp)
            weights = carry[:, None] + (prefix - compensation[:, None])
            increment = prefix[:, -1] - compensation
            updated = carry + increment
            compensation = (updated - carry) - increment
            carry = updated
            below = xp.logaddexp(
                below, _logsum(xp.where(valid & (support < target[:, None]), weights, -xp.inf), xp)
            )
            equal = xp.logaddexp(
                equal, _logsum(xp.where(valid & (support == target[:, None]), weights, -xp.inf), xp)
            )
            above = xp.logaddexp(
                above, _logsum(xp.where(valid & (support > target[:, None]), weights, -xp.inf), xp)
            )
    # AN=1 is exactly Bernoulli, including representable nearly certain negative logs.
    one = n == 1
    below = xp.where(one, xp.where(target == 1, xp.log1p(-p), -xp.inf), below)
    equal = xp.where(
        one, xp.where(target == 0, xp.log1p(-p), xp.where(target == 1, xp.log(p), -xp.inf)), equal
    )
    above = xp.where(one, xp.where(target < 0, 0.0, xp.where(target == 0, xp.log(p), -xp.inf)), above)
    return LogPartitions(below, equal, above)


def beta_binomial_log_partitions(
    mean: Any, concentration: Any, an: Any, ac: Any, *, array_module: Any, max_count: int
) -> LogPartitions:
    """Return complete-support log partitions with the aligned broadcast input shape.

    Inputs and host maximum must already satisfy the documented numeric domain. No support
    truncation, beta normalizer, probability clipping or limiting distribution is used.
    """
    xp = array_module
    arrays = xp.broadcast_arrays(mean, concentration, an, ac)
    shape = arrays[0].shape
    draws = shape[-1] if shape else 1
    # The last axis is draws; leading axes are query rows. Scalars/1-D inputs
    # form one query row. Collapse axes only within a bounded working batch.
    aligned = [a.reshape(-1, draws) for a in arrays]
    outputs = [xp.empty(aligned[0].shape, dtype=xp.float64) for _ in range(3)]
    for row in range(0, aligned[0].shape[0], ROW_CHUNK_SIZE):
        for draw in range(0, draws, DRAW_CHUNK_SIZE):
            section = (slice(row, row + ROW_CHUNK_SIZE), slice(draw, draw + DRAW_CHUNK_SIZE))
            batch_shape = aligned[0][section].shape
            p, c, n, target = (a[section].reshape(-1) for a in aligned)
            result = _batch(p, c, n, target, max_count, xp)
            for output, values in zip(outputs, (result.below, result.equal, result.above), strict=True):
                output[section] = values.reshape(batch_shape)
    return LogPartitions(*(output.reshape(shape) for output in outputs))


def beta_binomial_cdf(
    mean: Any, concentration: Any, an: Any, ac: Any, *, array_module: Any, max_count: int
) -> Any:
    """CDF from the same partitions, retaining exact analytical quantile ties."""
    xp = array_module
    parts = beta_binomial_log_partitions(mean, concentration, an, ac, array_module=xp, max_count=max_count)
    lower, _ = parts.tails(array_module=xp)
    lower = xp.where((mean == 0.5) & (an % 2 == 1) & (ac == an // 2), 0.5, lower)
    lower = xp.where((mean == 0.5) & (concentration == 2.0), (ac + 1) / (an + 1), lower)
    lower = xp.where((an == 1) & (ac == 0), 1.0 - mean, lower)
    return xp.where(ac < 0, 0.0, xp.where(ac >= an, 1.0, lower))
