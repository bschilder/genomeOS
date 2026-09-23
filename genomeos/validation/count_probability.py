"""Bounded direct beta-binomial probabilities (design §7, §8).

Implements direct-probability v2 spec §§4–6 and the accepted Task 2 full-law and
fixed-order proofs. Each lane visits its complete finite support from a legal
anchor. Right chunks precede left chunks; copied Hillis–Steele prefixes feed
complete adjacent partition sums; equal-sized tokens carry with the older block
on the left and occupied levels fold upward. Generic normalization remains
separate from the adapter that retains original inputs for analytical identities.

With ``v=2**-106``, the accepted ratio bound is ``69v``. A distance-d weight
adds d ratio and d product errors, giving ``77*d*v``; at most 17 partition-tree
edges add ``68v``. The fixed two-add normalization and divider yield the proved
component bound ``(308*n+368)*v``. A 128-leaf draw tree, binary carries, fold and
exact-draw division yield ``(616*n+1304)*v`` for the streamed mean. Both are less
than ``32*(n+1)*2**-98`` for ``1<=n<=65536``.

Generic support work is decomposed into at most 256 independent scalar lanes,
while the outer mean still streams 128 draws by four rows. With K=1024, one
support-shaped float64/int64 array is 2 MiB and one boolean array is 0.25 MiB.
Including retained locals and expression outputs, the five successive phase
peaks are 30/16/10, 44/17/10, 32/11/10, 28/9/10 and 38/13/10 arrays for
float64/int64/boolean. A further conservative 4/4/1 MiB covers every simultaneous
lane-sized and outer working array, yielding byte peaks of 64/36/3.5, 92/38/3.5,
68/26/3.5, 60/22/3.5 and 80/30/3.5 MiB. These stay below the separate
256/64/4 MiB ceilings without pooling dtype budgets.

Scalar identity pairs and ``(lanes, 1)`` shape views are broadcasts, not
support grids.
Support and validity are released before every residual primitive, reconstructed
for ratio masking, released for the prefix, then reconstructed for partition
masks. Previous-stage and previous-chunk references are explicitly cleared. No
dimension spans AN.

Eager array namespaces evaluate safe inactive factors and some masked token
merges, but invalid support positions are replaced by exact one before prefixes
and never enter a logical token.
Per-lane token occupancy requires one ``xp.any`` synchronization per traversed
binary-carry level; this preserves the proved nonempty-token trace and is an
explicit performance cost for a device namespace. Each direction also transfers
one host scalar for its maximum real lane distance, avoiding wholly empty global
chunks without changing any lane's token stream.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from genomeos.validation.count_scaled import (
    ScaledPair,
    add,
    divide,
    from_float64,
    from_int64,
    multiply,
    subtract,
)

SUPPORT_CHUNK_SIZE = 1024
DRAW_CHUNK_SIZE = 128
ROW_CHUNK_SIZE = 4
GENERIC_LANE_CHUNK_SIZE = 256
_LEGAL_SUPPORT_CHUNKS = (32, 256, 1024)


@dataclass(frozen=True)
class ProbabilityPartitions:
    """Unnormalized complete-support weights around the queried count."""

    below: ScaledPair
    equal: ScaledPair
    above: ScaledPair


@dataclass(frozen=True)
class NormalizedProbabilities:
    """Direct target mass, inclusive lower tail and strict upper tail."""

    mass: ScaledPair
    lower: ScaledPair
    upper: ScaledPair


def _zeros(shape: tuple[int, ...], xp: Any) -> ScaledPair:
    return from_int64(xp.zeros(shape, dtype=xp.int64), array_module=xp)


def _ones(shape: tuple[int, ...], xp: Any) -> ScaledPair:
    return from_int64(xp.ones(shape, dtype=xp.int64), array_module=xp)


def _copy(value: ScaledPair) -> ScaledPair:
    return ScaledPair(value.hi.copy(), value.lo.copy(), value.exponent.copy())


def _where(mask: Any, yes: ScaledPair, no: ScaledPair, xp: Any) -> ScaledPair:
    return ScaledPair(
        xp.where(mask, yes.hi, no.hi),
        xp.where(mask, yes.lo, no.lo),
        xp.where(mask, yes.exponent, no.exponent),
    )


def _scatter(mask: Any, compact: ScaledPair, shape: tuple[int, ...], xp: Any) -> ScaledPair:
    result = _zeros(shape, xp)
    result.hi[mask] = compact.hi
    result.lo[mask] = compact.lo
    result.exponent[mask] = compact.exponent
    return result


def _where_probabilities(
    mask: Any, yes: NormalizedProbabilities, no: NormalizedProbabilities, xp: Any
) -> NormalizedProbabilities:
    return NormalizedProbabilities(
        _where(mask, yes.mass, no.mass, xp),
        _where(mask, yes.lower, no.lower, xp),
        _where(mask, yes.upper, no.upper, xp),
    )


def _merge(left: ProbabilityPartitions, right: ProbabilityPartitions, xp: Any) -> ProbabilityPartitions:
    return ProbabilityPartitions(
        add(left.below, right.below, array_module=xp),
        add(left.equal, right.equal, array_module=xp),
        add(left.above, right.above, array_module=xp),
    )


def _zero_partitions(shape: tuple[int, ...], xp: Any) -> ProbabilityPartitions:
    return ProbabilityPartitions(*(_zeros(shape, xp) for _ in range(3)))


def _where_partitions(
    mask: Any, yes: ProbabilityPartitions, no: ProbabilityPartitions, xp: Any
) -> ProbabilityPartitions:
    return ProbabilityPartitions(
        _where(mask, yes.below, no.below, xp),
        _where(mask, yes.equal, no.equal, xp),
        _where(mask, yes.above, no.above, xp),
    )


def _prefix_products(values: ScaledPair, xp: Any) -> ScaledPair:
    result = _copy(values)
    step = 1
    while step < result.hi.shape[-1]:
        previous = _copy(result)
        product = multiply(
            ScaledPair(
                previous.hi[..., :-step],
                previous.lo[..., :-step],
                previous.exponent[..., :-step],
            ),
            ScaledPair(
                previous.hi[..., step:],
                previous.lo[..., step:],
                previous.exponent[..., step:],
            ),
            array_module=xp,
        )
        result.hi[..., step:] = product.hi
        result.lo[..., step:] = product.lo
        result.exponent[..., step:] = product.exponent
        del previous, product
        step *= 2
    return result


def _sum_last(values: ScaledPair, xp: Any) -> ScaledPair:
    result = values
    while result.hi.shape[-1] > 1:
        result = add(
            ScaledPair(result.hi[..., ::2], result.lo[..., ::2], result.exponent[..., ::2]),
            ScaledPair(result.hi[..., 1::2], result.lo[..., 1::2], result.exponent[..., 1::2]),
            array_module=xp,
        )
    return ScaledPair(result.hi[..., 0], result.lo[..., 0], result.exponent[..., 0])


def _mode(p: Any, c: Any, n: Any, xp: Any) -> Any:
    log_c = xp.log(c)
    small_alpha = xp.log(p) + log_c <= 0.0
    lower_half = p < 0.5
    safe_p = xp.where(lower_half, 0.0, p)
    small_beta = xp.where(
        lower_half,
        c <= 1.0 / (1.0 - p),
        xp.log1p(-safe_p) + log_c <= 0.0,
    )
    both_large = ~small_alpha & ~small_beta
    safe_c = xp.where(both_large, c, 3.0)
    inverse = 1.0 / safe_c
    candidate = xp.floor((n + 1) * (p - inverse) / (1 - 2 * inverse))
    candidate = xp.minimum(n, xp.maximum(0, candidate)).astype(xp.int64)
    endpoint = xp.where(small_alpha & (~small_beta | (p <= 0.5)), 0, n)
    return xp.where(both_large, candidate, endpoint)


def _enqueue(
    levels: list[ProbabilityPartitions],
    occupied: list[Any],
    token: ProbabilityPartitions,
    active: Any,
    xp: Any,
) -> None:
    level = 0
    zero = _zero_partitions(active.shape, xp)
    while bool(xp.any(active)):
        if level == len(levels):
            levels.append(zero)
            occupied.append(xp.zeros(active.shape, dtype=xp.bool_))
        present = occupied[level]
        merging = active & present
        placing = active & ~present
        merged = _merge(levels[level], token, xp)
        levels[level] = _where_partitions(
            placing,
            token,
            _where_partitions(merging, zero, levels[level], xp),
            xp,
        )
        occupied[level] = xp.where(active, ~present, present)
        token = _where_partitions(merging, merged, token, xp)
        active = merging
        level += 1


def _fold(levels: list[ProbabilityPartitions], occupied: list[Any], shape: tuple[int, ...], xp: Any):
    result = _zero_partitions(shape, xp)
    active = xp.zeros(shape, dtype=xp.bool_)
    for values, present in zip(levels, occupied, strict=True):
        merging = active & present
        taking = ~active & present
        merged = _merge(values, result, xp)
        result = _where_partitions(
            merging, merged, _where_partitions(taking, values, result, xp), xp
        )
        active = active | present
    if bool(xp.any(~active)):
        raise RuntimeError("complete-support token stream lost its anchor")
    return result


def _direction(
    direction: int,
    alpha: ScaledPair,
    beta: ScaledPair,
    anchor: Any,
    n: Any,
    target: Any,
    max_count: int,
    chunk_size: int,
    levels: list[ProbabilityPartitions],
    occupied: list[Any],
    xp: Any,
) -> None:
    shape = anchor.shape
    carry = _ones(shape, xp)
    one_scalar = _ones((), xp)
    zero_scalar = _zeros((), xp)
    alpha_grid = ScaledPair(alpha.hi[:, None], alpha.lo[:, None], alpha.exponent[:, None])
    beta_grid = ScaledPair(beta.hi[:, None], beta.lo[:, None], beta.exponent[:, None])
    distance = n - anchor if direction == 1 else anchor
    maximum_distance = int(xp.max(distance).item())
    if maximum_distance > max_count:
        raise ValueError("max_count is smaller than an admitted support")
    for start in range(1, maximum_distance + 1, chunk_size):
        offsets = xp.arange(start, start + chunk_size, dtype=xp.int64)
        support = anchor[:, None] + direction * offsets[None, :]
        valid = (support >= 0) & (support <= n[:, None])
        active = xp.any(valid, axis=-1)
        valid_count = xp.sum(valid, axis=-1, dtype=xp.int64)
        k = xp.where(valid, support - (1 if direction == 1 else 0), 0).astype(xp.int64)
        failures = n[:, None] - k - 1
        del support, valid
        success = add(alpha_grid, from_int64(k, array_module=xp), array_module=xp)
        failure = add(beta_grid, from_int64(failures, array_module=xp), array_module=xp)
        del failures
        numerator = multiply(
            from_int64(n[:, None] - k, array_module=xp), success, array_module=xp
        )
        del success
        denominator = multiply(from_int64(k + 1, array_module=xp), failure, array_module=xp)
        del failure, k, offsets
        ratio = (
            divide(numerator, denominator, array_module=xp)
            if direction == 1
            else divide(denominator, numerator, array_module=xp)
        )
        del numerator, denominator
        offsets = xp.arange(start, start + chunk_size, dtype=xp.int64)
        support = anchor[:, None] + direction * offsets[None, :]
        valid = (support >= 0) & (support <= n[:, None])
        ratio = _where(valid, ratio, one_scalar, xp)
        del support, valid, offsets
        prefix = _prefix_products(ratio, xp)
        del ratio
        expanded_carry = ScaledPair(carry.hi[:, None], carry.lo[:, None], carry.exponent[:, None])
        weights = multiply(expanded_carry, prefix, array_module=xp)
        del expanded_carry, prefix
        last = xp.maximum(valid_count - 1, 0)[:, None]
        gathered = ScaledPair(
            xp.take_along_axis(weights.hi, last, axis=-1)[:, 0],
            xp.take_along_axis(weights.lo, last, axis=-1)[:, 0],
            xp.take_along_axis(weights.exponent, last, axis=-1)[:, 0],
        )
        del last, valid_count
        carry = _where(active, gathered, carry, xp)
        offsets = xp.arange(start, start + chunk_size, dtype=xp.int64)
        support = anchor[:, None] + direction * offsets[None, :]
        valid = (support >= 0) & (support <= n[:, None])
        below_values = _where(valid & (support < target[:, None]), weights, zero_scalar, xp)
        equal_values = _where(valid & (support == target[:, None]), weights, zero_scalar, xp)
        above_values = _where(valid & (support > target[:, None]), weights, zero_scalar, xp)
        del support, valid, offsets, weights
        below = _sum_last(below_values, xp)
        del below_values
        equal = _sum_last(equal_values, xp)
        del equal_values
        above = _sum_last(above_values, xp)
        del above_values
        token = ProbabilityPartitions(below, equal, above)
        _enqueue(levels, occupied, token, active, xp)
        del below, equal, above, gathered, token


def _batch(p: Any, c: Any, n: Any, target: Any, max_count: int, chunk_size: int, xp: Any):
    shape = p.shape
    p_pair = from_float64(p, array_module=xp)
    c_pair = from_float64(c, array_module=xp)
    one = _ones(shape, xp)
    alpha = multiply(p_pair, c_pair, array_module=xp)
    beta = multiply(subtract(one, p_pair, array_module=xp), c_pair, array_module=xp)
    anchor = _mode(p, c, n, xp)
    zero = _zeros(shape, xp)
    anchor_token = ProbabilityPartitions(
        _where(anchor < target, one, zero, xp),
        _where(anchor == target, one, zero, xp),
        _where(anchor > target, one, zero, xp),
    )
    levels: list[ProbabilityPartitions] = []
    occupied: list[Any] = []
    _enqueue(levels, occupied, anchor_token, xp.ones(shape, dtype=xp.bool_), xp)
    for direction in (1, -1):
        _direction(
            direction,
            alpha,
            beta,
            anchor,
            n,
            target,
            max_count,
            chunk_size,
            levels,
            occupied,
            xp,
        )
    return _fold(levels, occupied, shape, xp)


def _validate_chunk_size(support_chunk_size: int) -> None:
    if support_chunk_size not in _LEGAL_SUPPORT_CHUNKS:
        raise ValueError("support_chunk_size must be one of 32, 256 or 1024")


def _beta_binomial_probability_partitions(
    mean: Any,
    concentration: Any,
    an: Any,
    ac: Any,
    *,
    array_module: Any,
    max_count: int,
    support_chunk_size: int,
) -> ProbabilityPartitions:
    """Run the fixed trace for caller-prevalidated interior numerical inputs."""
    _validate_chunk_size(support_chunk_size)
    xp = array_module
    arrays = xp.broadcast_arrays(mean, concentration, an, ac)
    shape = arrays[0].shape
    aligned = [value.reshape(-1) for value in arrays]
    fields = [
        [xp.empty(aligned[0].shape, dtype=dtype) for dtype in (xp.float64, xp.float64, xp.int64)]
        for _ in range(3)
    ]
    for start in range(0, aligned[0].size, GENERIC_LANE_CHUNK_SIZE):
        section = slice(start, start + GENERIC_LANE_CHUNK_SIZE)
        result = _batch(*(value[section] for value in aligned), max_count, support_chunk_size, xp)
        for output, pair in zip(fields, (result.below, result.equal, result.above), strict=True):
            for destination, value in zip(output, (pair.hi, pair.lo, pair.exponent), strict=True):
                destination[section] = value
    return ProbabilityPartitions(
        *(ScaledPair(*(field.reshape(shape) for field in output)) for output in fields)
    )


def beta_binomial_probability_partitions(
    mean: Any,
    concentration: Any,
    an: Any,
    ac: Any,
    *,
    array_module: Any,
    max_count: int,
) -> ProbabilityPartitions:
    """Return raw partitions for caller-prevalidated interior numerical inputs.

    Inputs must broadcast to at most 512 scalar lanes; floats must be finite
    float64 with ``0 < mean < 1`` and usable positive concentration; counts must
    be int64 with
    ``1 <= an <= max_count <= 65_536`` and ``-1 <= ac <= an``. The future public
    adapter owns this scientific-domain policy. This helper checks only numerical
    representation, shape, chunk and internal range conditions.
    """
    return _beta_binomial_probability_partitions(
        mean,
        concentration,
        an,
        ac,
        array_module=array_module,
        max_count=max_count,
        support_chunk_size=SUPPORT_CHUNK_SIZE,
    )


def normalize_partitions(
    parts: ProbabilityPartitions, *, array_module: Any
) -> NormalizedProbabilities:
    """Normalize caller-validated nonnegative parts with a positive total."""
    if not isinstance(parts, ProbabilityPartitions):
        raise TypeError("Expected ProbabilityPartitions")
    xp = array_module
    combined = add(parts.below, parts.equal, array_module=xp)
    total = add(combined, parts.above, array_module=xp)
    return NormalizedProbabilities(
        divide(parts.equal, total, array_module=xp),
        divide(combined, total, array_module=xp),
        divide(parts.above, total, array_module=xp),
    )


def _analytical(
    generic: NormalizedProbabilities, p: Any, c: Any, n: Any, target: Any, xp: Any
) -> NormalizedProbabilities:
    shape = p.shape
    zero, one = _zeros(shape, xp), _ones(shape, xp)
    half = from_float64(xp.full(shape, 0.5, dtype=xp.float64), array_module=xp)
    p_pair = from_float64(p, array_module=xp)
    complement = subtract(one, p_pair, array_module=xp)

    degenerate = (p == 0.0) | (p == 1.0)
    point = xp.where(p == 0.0, 0, n)
    exact = NormalizedProbabilities(
        _where(target == point, one, zero, xp),
        _where(target >= point, one, zero, xp),
        _where(target < point, one, zero, xp),
    )
    result = _where_probabilities(degenerate, exact, generic, xp)

    bernoulli = NormalizedProbabilities(
        _where(target == 0, complement, _where(target == 1, p_pair, zero, xp), xp),
        _where(target < 0, zero, _where(target == 0, complement, one, xp), xp),
        _where(target < 0, one, _where(target == 0, p_pair, zero, xp), xp),
    )
    result = _where_probabilities(n == 1, bernoulli, result, xp)

    below_count = xp.maximum(target, 0).astype(xp.int64)
    equal_count = ((target >= 0) & (target <= n)).astype(xp.int64)
    above_count = xp.where(target < 0, n + 1, n - target).astype(xp.int64)
    uniform = normalize_partitions(
        ProbabilityPartitions(
            from_int64(below_count, array_module=xp),
            from_int64(equal_count, array_module=xp),
            from_int64(above_count, array_module=xp),
        ),
        array_module=xp,
    )
    result = _where_probabilities((p == 0.5) & (c == 2.0), uniform, result, xp)

    symmetry = (p == 0.5) & ((n % 2) == 1) & (target == n // 2)
    result = NormalizedProbabilities(
        result.mass,
        _where(symmetry, half, result.lower, xp),
        _where(symmetry, half, result.upper, xp),
    )
    result = NormalizedProbabilities(
        _where(target < 0, zero, result.mass, xp),
        _where(target < 0, zero, _where(target >= n, one, result.lower, xp), xp),
        _where(target < 0, one, _where(target >= n, zero, result.upper, xp), xp),
    )
    return result


def _beta_binomial_probabilities(
    mean: Any,
    concentration: Any,
    an: Any,
    ac: Any,
    *,
    array_module: Any,
    max_count: int,
    support_chunk_size: int,
) -> NormalizedProbabilities:
    xp = array_module
    p, c, n, target = xp.broadcast_arrays(mean, concentration, an, ac)
    # Check exact dtypes and finite floats before routing; callers own domain policy.
    from_float64(p, array_module=xp)
    from_float64(c, array_module=xp)
    from_int64(n, array_module=xp)
    from_int64(target, array_module=xp)
    analytical = (
        (p == 0.0)
        | (p == 1.0)
        | (n == 1)
        | ((p == 0.5) & (c == 2.0))
        | (target < 0)
    )
    generic_mask = ~analytical
    zero = _zeros(p.shape, xp)
    generic = NormalizedProbabilities(zero, zero, zero)
    if bool(xp.any(generic_mask)):
        parts = _beta_binomial_probability_partitions(
            p[generic_mask],
            c[generic_mask],
            n[generic_mask],
            target[generic_mask],
            array_module=xp,
            max_count=max_count,
            support_chunk_size=support_chunk_size,
        )
        compact = normalize_partitions(parts, array_module=xp)
        generic = NormalizedProbabilities(
            _scatter(generic_mask, compact.mass, p.shape, xp),
            _scatter(generic_mask, compact.lower, p.shape, xp),
            _scatter(generic_mask, compact.upper, p.shape, xp),
        )
    return _analytical(generic, p, c, n, target, xp)


def beta_binomial_probabilities(
    mean: Any,
    concentration: Any,
    an: Any,
    ac: Any,
    *,
    array_module: Any,
    max_count: int,
) -> NormalizedProbabilities:
    """Return analytical-aware probabilities for caller-prevalidated inputs.

    Inputs must broadcast to at most 512 scalar lanes; floats must be finite
    float64 with ``0 <= mean <= 1`` and usable positive concentration; counts
    must be int64 with
    ``1 <= an <= max_count <= 65_536`` and ``-1 <= ac <= an``. This numerical
    helper preserves accepted analytical identities but does not own the
    scientific-domain refusal policy required at future public integration.
    """
    return _beta_binomial_probabilities(
        mean,
        concentration,
        an,
        ac,
        array_module=array_module,
        max_count=max_count,
        support_chunk_size=SUPPORT_CHUNK_SIZE,
    )


def _identity_flags(p: Any, c: Any, n: Any, target: Any, xp: Any):
    uniform = (p == 0.5) & (c == 2.0)
    symmetry = (p == 0.5) & ((n % 2) == 1) & (target == n // 2)
    mass = (
        (target < 0) | ((p == 0.0) & (target != 0)) | ((p == 1.0) & (target != n)),
        (n == 1) & (p == 0.5) & ((target == 0) | (target == 1)),
        ((p == 0.0) & (target == 0)) | ((p == 1.0) & (target == n)),
    )
    lower = (
        (target < 0) | ((p == 1.0) & (target < n)),
        symmetry | (uniform & (2 * (target + 1) == n + 1)),
        (target >= n) | ((p == 0.0) & (target >= 0)),
    )
    upper = (
        (target >= n) | ((p == 0.0) & (target >= 0)),
        symmetry | (uniform & (2 * (n - target) == n + 1)),
        (target < 0) | ((p == 1.0) & (target < n)),
    )
    return mass, lower, upper


def _mean_core(
    mean: Any,
    concentration: Any,
    an: Any,
    ac: Any,
    *,
    array_module: Any,
    max_count: int,
    support_chunk_size: int,
) -> NormalizedProbabilities:
    xp = array_module
    p, c = xp.asarray(mean), xp.asarray(concentration)
    n, target = xp.asarray(an), xp.asarray(ac)
    if p.ndim != 2 or p.shape != c.shape:
        raise ValueError("mean and concentration must have identical (draws, observations) shape")
    draws, observations = p.shape
    if draws == 0 or n.shape != (observations,) or target.shape != (observations,):
        raise ValueError("an and ac must have the nonempty observation shape")
    output = [
        [xp.empty(observations, dtype=dtype) for dtype in (xp.float64, xp.float64, xp.int64)]
        for _ in range(3)
    ]
    for row in range(0, observations, ROW_CHUNK_SIZE):
        rows = slice(row, min(row + ROW_CHUNK_SIZE, observations))
        levels = [[] for _ in range(3)]
        occupied: list[bool] = []
        identity = xp.ones((3, 3, n[rows].size), dtype=xp.bool_)
        single: NormalizedProbabilities | None = None
        for draw in range(0, draws, DRAW_CHUNK_SIZE):
            draw_stop = min(draw + DRAW_CHUNK_SIZE, draws)
            pp = p[draw:draw_stop, rows].T
            cc = c[draw:draw_stop, rows].T
            nn = xp.broadcast_to(n[rows, None], pp.shape)
            tt = xp.broadcast_to(target[rows, None], pp.shape)
            components = _beta_binomial_probabilities(
                pp,
                cc,
                nn,
                tt,
                array_module=xp,
                max_count=max_count,
                support_chunk_size=support_chunk_size,
            )
            if draws == 1:
                single = NormalizedProbabilities(
                    ScaledPair(
                        components.mass.hi[:, 0],
                        components.mass.lo[:, 0],
                        components.mass.exponent[:, 0],
                    ),
                    ScaledPair(
                        components.lower.hi[:, 0],
                        components.lower.lo[:, 0],
                        components.lower.exponent[:, 0],
                    ),
                    ScaledPair(
                        components.upper.hi[:, 0],
                        components.upper.lo[:, 0],
                        components.upper.exponent[:, 0],
                    ),
                )
            padded = DRAW_CHUNK_SIZE - (draw_stop - draw)
            chunk_tokens = []
            for value in (components.mass, components.lower, components.upper):
                if padded:
                    zeros = _zeros((value.hi.shape[0], padded), xp)
                    value = ScaledPair(
                        xp.concatenate((value.hi, zeros.hi), axis=-1),
                        xp.concatenate((value.lo, zeros.lo), axis=-1),
                        xp.concatenate((value.exponent, zeros.exponent), axis=-1),
                    )
                chunk_tokens.append(_sum_last(value, xp))
            flags = _identity_flags(pp, cc, nn, tt, xp)
            flag_grid = xp.stack([xp.stack(values, axis=0) for values in flags], axis=0)
            identity &= xp.all(flag_grid, axis=-1)
            level = 0
            tokens = chunk_tokens
            while level < len(occupied) and occupied[level]:
                tokens = [add(levels[index][level], tokens[index], array_module=xp) for index in range(3)]
                occupied[level] = False
                level += 1
            if level == len(occupied):
                occupied.append(True)
                for index in range(3):
                    levels[index].append(tokens[index])
            else:
                occupied[level] = True
                for index in range(3):
                    levels[index][level] = tokens[index]
        if single is not None:
            result = single
        else:
            sums = []
            for observable in range(3):
                total = None
                for level, present in enumerate(occupied):
                    if present:
                        total = levels[observable][level] if total is None else add(
                            levels[observable][level], total, array_module=xp
                        )
                if total is None:
                    raise RuntimeError("draw stream produced no token")
                sums.append(total)
            divisor = from_int64(xp.full(n[rows].shape, draws, dtype=xp.int64), array_module=xp)
            result = NormalizedProbabilities(
                *(divide(value, divisor, array_module=xp) for value in sums)
            )
        zero, one = _zeros(n[rows].shape, xp), _ones(n[rows].shape, xp)
        half = from_float64(xp.full(n[rows].shape, 0.5, dtype=xp.float64), array_module=xp)
        values = []
        for observable, value in enumerate((result.mass, result.lower, result.upper)):
            zero_mask, half_mask, one_mask = identity[observable]
            values.append(
                _where(
                    one_mask,
                    one,
                    _where(half_mask, half, _where(zero_mask, zero, value, xp), xp),
                    xp,
                )
            )
        for destination, value in zip(output, values, strict=True):
            for field, item in zip(destination, (value.hi, value.lo, value.exponent), strict=True):
                field[rows] = item
    return NormalizedProbabilities(
        *(ScaledPair(*fields) for fields in output)
    )


def beta_binomial_probability_mean(
    mean: Any,
    concentration: Any,
    an: Any,
    ac: Any,
    *,
    array_module: Any,
    max_count: int,
) -> NormalizedProbabilities:
    """Stream probabilities for caller-prevalidated draws and observations.

    Mean and concentration must be finite float64 arrays of identical nonempty
    ``(draws, observations)`` shape; ``0 <= mean <= 1`` and concentration is
    positive and usable. Observation counts are int64 with
    ``1 <= an <= max_count <= 65_536`` and ``-1 <= ac <= an``. The helper
    streams at most 128 draws and four rows per numerical block. The future
    public adapter owns scientific-domain policy.
    """
    return _mean_core(
        mean,
        concentration,
        an,
        ac,
        array_module=array_module,
        max_count=max_count,
        support_chunk_size=SUPPORT_CHUNK_SIZE,
    )


def _beta_binomial_probability_mean(
    mean: Any,
    concentration: Any,
    an: Any,
    ac: Any,
    *,
    array_module: Any,
    max_count: int,
    support_chunk_size: int,
) -> NormalizedProbabilities:
    """Internal mean entry for proof-covered support-chunk comparisons."""
    _validate_chunk_size(support_chunk_size)
    return _mean_core(
        mean,
        concentration,
        an,
        ac,
        array_module=array_module,
        max_count=max_count,
        support_chunk_size=support_chunk_size,
    )
