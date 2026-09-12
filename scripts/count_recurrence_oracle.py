"""Absolute Decimal beta-binomial oracle, independent of production (design §7, §8).

Inputs are exact binary64 reals. P(0) is an absolute product; no oracle probability is
renormalized. Both tails are summed directly, including probabilities below float range.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext
from functools import lru_cache


@dataclass(frozen=True)
class Oracle:
    log_mass: tuple[Decimal, ...]
    lower: tuple[Decimal, ...]
    upper: tuple[Decimal, ...]
    normalization: Decimal
    mean: Decimal
    variance: Decimal
    fourth_central: Decimal


@lru_cache(maxsize=32)
def absolute_law(
    n: int,
    p: float,
    c: float,
    counts: tuple[int, ...],
    precision: int,
    swapped: bool = False,
) -> Oracle:
    with localcontext() as context:
        context.prec = precision
        context.Emin = -999999999
        context.Emax = 999999999
        mean, concentration = Decimal.from_float(p), Decimal.from_float(c)
        alpha, beta = mean * concentration, (1 - mean) * concentration
        if swapped:
            alpha, beta = beta, alpha
            mean = 1 - mean
        mass = Decimal(1)
        for j in range(n):
            mass *= (beta + j) / (concentration + j)
        total = Decimal(0)
        lower = [Decimal(0) for _ in counts]
        upper = [Decimal(0) for _ in counts]
        logs = [Decimal(0) for _ in counts]
        expectation = n * mean
        variance = n * mean * (1 - mean) * (n + concentration) / (1 + concentration)
        fourth = Decimal(0)
        for k in range(n + 1):
            total += mass
            fourth += mass * (k - expectation) ** 4
            for index, count in enumerate(counts):
                if k <= count:
                    lower[index] += mass
                else:
                    upper[index] += mass
                if k == count:
                    logs[index] = mass.ln()
            if k < n:
                mass *= Decimal(n - k) / (k + 1) * (alpha + k) / (beta + n - k - 1)
        return Oracle(tuple(logs), tuple(lower), tuple(upper), total, expectation, variance, fourth)


def verified_law(
    n: int,
    p: float,
    c: float,
    counts: tuple[int, ...],
    swapped: bool = False,
) -> Oracle:
    first = absolute_law(n, p, c, counts, 400, swapped)
    second = absolute_law(n, p, c, counts, 480, swapped)
    for result in (first, second):
        assert abs(result.normalization - 1) <= Decimal("1e-70")
    for x, y in zip(first.log_mass, second.log_mass, strict=True):
        assert abs(x - y) <= Decimal("1e-70")
    return second
