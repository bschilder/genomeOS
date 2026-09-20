"""Scaled residual arithmetic for offline count probabilities (design §7, §8).

Implements direct-probability v2 rationale §§2–3,5 and its accepted Task 1 proof.
Each ScaledPair represents the exact real (hi+lo)*2**exponent. Operations accept
canonical finite float64/float64/int64 fields, broadcast operands, and return a
canonical pair. Manually supplied noncanonical pairs fail closed. No physical
probability is rounded to float64 until the [0,1]-only conversion boundary.

The local positive relative bounds are 4*u**2 for addition, 8*u**2 for product,
and 32*u**2 for quotient, u=2**-53. Signed addition/subtraction instead has the
4*u**2*(abs(A)+abs(B)) absolute bound. This is arithmetic, not a full-law proof.
The fixed cutoff is applied only to a normalized low after residual promotion;
alignment gaps greater than 120 discard the smaller operand with a bounded loss.

NumPy and CuPy are explicit caller-supplied namespaces; neither is imported.
Every elementary result is materialized: no fusion, FMA, or reassociation.
TwoSum is Shewchuk Theorem 7 (§2.3); Split/TwoProduct are Theorems 17/18 (§2.5),
https://people.eecs.berkeley.edu/~jrs/papers/robustr.pdf. Checked exponent failures
are errors, including intermediate overflow even if a later shift could undo it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

_MIN_EXPONENT = -(2**63)
_MAX_EXPONENT = 2**63 - 1
_LOW_CUTOFF = 2.0**-120


@dataclass(frozen=True)
class ScaledPair:
    """Canonical binary significand/residual and a separate signed int64 exponent.

    Fields have identical shapes. The high is the correctly rounded sum of high
    and low and has magnitude in [0.5,1); nonzero lows have magnitude >=2**-120.
    Zero is (+0,+0,0). Construction alone does not validate: every public
    arithmetic/conversion boundary validates both operands before using them.
    """

    hi: Any
    lo: Any
    exponent: Any


def _two_sum(a: Any, b: Any) -> tuple[Any, Any]:
    s = a + b
    bb = s - a
    aa = s - bb
    da = a - aa
    db = b - bb
    error = da + db
    return s, error


def _split(a: Any) -> tuple[Any, Any]:
    c = (2**27 + 1) * a
    big = c - a
    high = c - big
    low = a - high
    return high, low


def _two_product(a: Any, b: Any) -> tuple[Any, Any]:
    ah, al = _split(a)
    bh, bl = _split(b)
    p = a * b
    t1 = ah * bh
    e1 = p - t1
    t2 = al * bh
    e2 = e1 - t2
    t3 = ah * bl
    e3 = e2 - t3
    t4 = al * bl
    error = t4 - e3
    return p, error


def _checked_add(a: Any, b: Any, xp: Any) -> Any:
    positive = xp.maximum(b, 0)
    negative = xp.minimum(b, 0)
    too_high = a > _MAX_EXPONENT - positive
    too_low = a < _MIN_EXPONENT - negative
    if bool(xp.any(too_high | too_low)):
        raise OverflowError("ScaledPair exponent addition exceeds int64")
    return a + b


def _checked_subtract(a: Any, b: Any, xp: Any) -> Any:
    positive = xp.maximum(b, 0)
    negative = xp.minimum(b, 0)
    too_high = a > _MAX_EXPONENT + negative
    too_low = a < _MIN_EXPONENT + positive
    if bool(xp.any(too_high | too_low)):
        raise OverflowError("ScaledPair exponent subtraction exceeds int64")
    return a - b


def _array(value: Any, dtype: Any, xp: Any) -> Any:
    array = xp.asarray(value)
    if array.dtype != xp.dtype(dtype):
        raise TypeError("ScaledPair inputs require exact float64 or int64 dtypes")
    return array


def _validate(value: ScaledPair, xp: Any) -> ScaledPair:
    if not isinstance(value, ScaledPair):
        raise TypeError("Expected a ScaledPair")
    h = _array(value.hi, xp.float64, xp)
    low = _array(value.lo, xp.float64, xp)
    exponent = _array(value.exponent, xp.int64, xp)
    if h.shape != low.shape or h.shape != exponent.shape:
        raise ValueError("ScaledPair fields must have identical shapes")
    zero = h == 0
    valid_zero = (low == 0) & (exponent == 0) & ~xp.signbit(h) & ~xp.signbit(low)
    normal_high = (xp.abs(h) >= 0.5) & (xp.abs(h) < 1)
    retained_low = (low == 0) | (xp.abs(low) >= _LOW_CUTOFF)
    safe_high = xp.where(normal_high, h, 0.0)
    bounded_low = xp.abs(low) <= (2.0**-53) * xp.abs(safe_high)
    finite = xp.isfinite(h) & xp.isfinite(low)
    valid = finite & xp.where(zero, valid_zero, normal_high & retained_low & bounded_low)
    if bool(xp.any(~valid)):
        raise ValueError("Noncanonical ScaledPair")
    # The relative residual bound alone does not establish midpoint/tie behavior.
    rounded, residual = _two_sum(h, low)
    if bool(xp.any((rounded != h) | (residual != low))):
        raise ValueError("ScaledPair high/low must already be a canonical TwoSum expansion")
    return ScaledPair(h, low, exponent)


def _normalize(h: Any, low: Any, exponent: Any, xp: Any) -> ScaledPair:
    high, residual = _two_sum(h, low)
    # TwoSum promotes a nonzero residual before any low cutoff or zero decision.
    mantissa, shift = xp.frexp(high)
    shift = shift.astype(xp.int64)
    normalized_low = xp.ldexp(residual, -shift)
    active_exponent = xp.where(high != 0, exponent, 0)
    output_exponent = _checked_add(active_exponent, shift, xp)
    normalized_low = xp.where(xp.abs(normalized_low) < _LOW_CUTOFF, 0.0, normalized_low)
    mantissa = xp.where(high == 0, 0.0, mantissa)
    return ScaledPair(mantissa, normalized_low, output_exponent)


def from_float64(value: Any, *, array_module: Any) -> ScaledPair:
    """Pack every finite binary64 exactly, including physical subnormals and signs."""
    xp = array_module
    value = _array(value, xp.float64, xp)
    if bool(xp.any(~xp.isfinite(value))):
        raise ValueError("Only finite binary64 values can be packed")
    h, exponent = xp.frexp(value)
    h = xp.where(value == 0, 0.0, h)
    return ScaledPair(h, xp.zeros_like(h), exponent.astype(xp.int64))


def from_int64(value: Any, *, array_module: Any) -> ScaledPair:
    """Pack signed int64 exactly via safe Euclidean upper/lower32 decomposition."""
    xp = array_module
    value = _array(value, xp.int64, xp)
    upper = xp.floor_divide(value, 2**32)
    lower = xp.remainder(value, 2**32)
    high = xp.ldexp(upper.astype(xp.float64), 32)
    low = lower.astype(xp.float64)
    return _normalize(high, low, xp.zeros_like(value), xp)


def _aligned(a: ScaledPair, b: ScaledPair, xp: Any) -> tuple[Any, Any, Any, Any, Any]:
    # Canonical zero's exponent must not cause a small nonzero operand to be dropped.
    ea = xp.where(a.hi == 0, b.exponent, a.exponent)
    eb = xp.where(b.hi == 0, a.exponent, b.exponent)
    exponent = xp.maximum(ea, eb)

    def align(value: ScaledPair, operand_exponent: Any) -> tuple[Any, Any]:
        # Avoid forming exponent-operand_exponent when it could exceed int64.
        safe_limit = xp.minimum(operand_exponent, _MAX_EXPONENT - 120) + 120
        discard = (operand_exponent <= _MAX_EXPONENT - 120) & (exponent > safe_limit)
        safe_exponent = xp.where(discard, exponent, operand_exponent)
        gap = exponent - safe_exponent
        high = xp.ldexp(xp.where(discard, 0.0, value.hi), -gap)
        low = xp.ldexp(xp.where(discard, 0.0, value.lo), -gap)
        return high, low

    ah, al = align(a, ea)
    bh, bl = align(b, eb)
    return ah, al, bh, bl, exponent


def _add(a: ScaledPair, b: ScaledPair, xp: Any) -> ScaledPair:
    ah, al, bh, bl, exponent = _aligned(a, b, xp)
    s, error = _two_sum(ah, bh)
    t, f = _two_sum(al, bl)
    v, g = _two_sum(error, t)
    h, w = _two_sum(s, v)
    ell1 = w + g
    ell2 = ell1 + f
    high, low = _two_sum(h, ell2)
    return _normalize(high, low, exponent, xp)


def add(a: ScaledPair, b: ScaledPair, *, array_module: Any) -> ScaledPair:
    """Add canonical pairs; signed absolute error is <=4*u**2*(abs(A)+abs(B))."""
    xp = array_module
    return _add(_validate(a, xp), _validate(b, xp), xp)


def subtract(a: ScaledPair, b: ScaledPair, *, array_module: Any) -> ScaledPair:
    """Subtract with exact sign reflection and the signed addition error contract."""
    xp = array_module
    a, b = _validate(a, xp), _validate(b, xp)
    high = xp.where(b.hi == 0, 0.0, -b.hi)
    low = xp.where(b.lo == 0, 0.0, -b.lo)
    return _add(a, ScaledPair(high, low, b.exponent), xp)


def multiply(a: ScaledPair, b: ScaledPair, *, array_module: Any) -> ScaledPair:
    """Multiply without physical underflow; nonzero relative error is <=8*u**2."""
    xp = array_module
    a, b = _validate(a, xp), _validate(b, xp)
    active = (a.hi != 0) & (b.hi != 0)
    exponent = _checked_add(xp.where(active, a.exponent, 0), xp.where(active, b.exponent, 0), xp)
    p, error = _two_product(a.hi, b.hi)
    t = a.hi * b.lo
    v = a.lo * b.hi
    s1, e1 = _two_sum(t, v)
    w = a.lo * b.lo
    s2, e2 = _two_sum(error, s1)
    s3, e3 = _two_sum(s2, w)
    h, low = _two_sum(p, s3)
    r1 = low + e1
    r2 = r1 + e2
    r3 = r2 + e3
    high, residual = _two_sum(h, r3)
    return _normalize(high, residual, exponent, xp)


def _estimate(a: ScaledPair, b: ScaledPair, xp: Any) -> ScaledPair:
    active = a.hi != 0
    exponent = _checked_subtract(xp.where(active, a.exponent, 0), xp.where(active, b.exponent, 0), xp)
    quotient = a.hi / b.hi
    return _normalize(quotient, xp.zeros_like(quotient), exponent, xp)


def divide(a: ScaledPair, b: ScaledPair, *, array_module: Any) -> ScaledPair:
    """Divide by a strictly positive pair using exactly two residual corrections."""
    xp = array_module
    a, b = _validate(a, xp), _validate(b, xp)
    if bool(xp.any(b.hi <= 0)):
        raise ValueError("ScaledPair division requires a strictly positive divisor")
    q0 = _estimate(a, b, xp)
    product0 = multiply(b, q0, array_module=xp)
    r0 = subtract(a, product0, array_module=xp)
    q1 = _estimate(r0, b, xp)
    product1 = multiply(b, q1, array_module=xp)
    r1 = subtract(r0, product1, array_module=xp)
    q2 = _estimate(r1, b, xp)
    partial = add(q0, q1, array_module=xp)
    return add(partial, q2, array_module=xp)


def to_float64(value: ScaledPair, *, array_module: Any) -> Any:
    """Correctly round a represented probability in [0,1]; refuse all other values.

    The lattice branch rounds the exact pair approximation in units of 2**-1074,
    not an exact-law probability. Outside-domain values raise before underflow.
    """
    xp = array_module
    value = _validate(value, xp)
    h, low, exponent = value.hi, value.lo, value.exponent
    above_one = (exponent > 1) & (h > 0)
    above_at_one = (exponent == 1) & ((h > 0.5) | ((h == 0.5) & (low > 0)))
    if bool(xp.any((h < 0) | above_one | above_at_one)):
        raise ValueError("Probability conversion requires a represented value in [0,1]")
    lattice = (h > 0) & (exponent >= -1074) & (exponent <= -1021)
    shift = xp.where(lattice, exponent, -1074) + 1074
    high_units = xp.ldexp(xp.where(lattice, h, 0.0), shift)
    low_units = xp.ldexp(xp.where(lattice, low, 0.0), shift)
    integer = xp.floor(high_units).astype(xp.int64)
    remainder = high_units - integer.astype(xp.float64)
    fraction, residual = _two_sum(remainder, low_units)
    negative = (fraction < 0) | ((fraction == 0) & (residual < 0))
    # A negative fraction is possible only at an integral high, where it is L.
    adjusted, adjustment = _two_sum(xp.where(negative, 1.0, 0.0), xp.where(negative, low_units, 0.0))
    integer = integer - negative.astype(xp.int64)
    fraction = xp.where(negative, adjusted, fraction)
    residual = xp.where(negative, adjustment, residual)
    above_half = (fraction > 0.5) | ((fraction == 0.5) & (residual > 0))
    tie = (fraction == 0.5) & (residual == 0)
    increment = above_half | (tie & ((integer & 1) != 0))
    rounded_integer = integer + increment.astype(xp.int64)
    lattice_result = xp.ldexp(rounded_integer.astype(xp.float64), -1074)
    normal = (h > 0) & (exponent > -1021)
    rounded_significand = xp.where(normal, h, 0.0) + xp.where(normal, low, 0.0)
    normal_result = xp.ldexp(rounded_significand, xp.where(normal, exponent, 0))
    return xp.where(normal, normal_result, lattice_result)
