"""Independent pairwise-complete ALT-dosage LD reference (CuGen pilot design §4).

The reference enumerates exact integer contingency counts independently of CuGen. Its pairwise
correlations are not a joint covariance model and are never projected, imputed, or PSD-repaired.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Integral
from typing import Literal

import numpy as np

from genomeos.validation.ld_contract import (
    LDVariant,
    validate_hard_calls,
    validate_ld_variants,
)

LDStatus = Literal["observed", "insufficient_observations", "zero_variance"]


@dataclass(frozen=True)
class LDPair:
    """Exact evidence and correlation state for one requested unordered row pair."""

    row_a: int
    row_b: int
    gidx_a: int
    gidx_b: int
    n_obs: int
    counts: tuple[int, int, int, int, int, int, int, int, int]
    status: LDStatus
    r: float | None
    r2: float | None


@dataclass(frozen=True)
class VariantMoments:
    """Biological hard-call moments for one variant; missing calls are excluded."""

    n_called: int
    ac: int
    mean: float | None
    sxx: float | None
    maf: float | None


def _window(value: object, name: str, *, positive: bool) -> int | None:
    if value is None:
        return None
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Integral):
        qualifier = "positive" if positive else "nonnegative"
        raise TypeError(f"{name} must be a {qualifier} integer or None")
    normalized = int(value)
    if normalized < int(positive):
        qualifier = "positive" if positive else "nonnegative"
        raise ValueError(f"{name} must be a {qualifier} integer or None")
    return normalized


def requested_pairs(
    variants: object, *, window_variants: object, window_bp: object
) -> tuple[tuple[int, int], ...]:
    """Return unordered row pairs satisfying both explicit inclusive window predicates."""
    block = validate_ld_variants(
        variants, genome_build="GRCh38", ploidy="autosomal_diploid"
    )
    row_window = _window(window_variants, "window_variants", positive=True)
    bp_window = _window(window_bp, "window_bp", positive=False)
    pairs: list[tuple[int, int]] = []
    for row_a, variant_a in enumerate(block):
        for row_b in range(row_a + 1, len(block)):
            variant_b = block[row_b]
            if row_window is not None and row_b - row_a > row_window:
                continue
            if bp_window is not None and variant_b.position - variant_a.position > bp_window:
                continue
            pairs.append((row_a, row_b))
    return tuple(pairs)


def variant_moments(calls: object) -> tuple[VariantMoments, ...]:
    """Compute exact-count per-variant moments with undefined all-missing biology explicit."""
    snapshot = validate_hard_calls(calls)
    moments: list[VariantMoments] = []
    for row in range(snapshot.shape[1]):
        called = snapshot[:, row]
        called = called[called != 3]
        n_called = int(called.size)
        if n_called == 0:
            moments.append(VariantMoments(0, 0, None, None, None))
            continue
        values = tuple(int(value) for value in called)
        ac = sum(values)
        sumsq = sum(value * value for value in values)
        mean = ac / n_called
        sxx = sumsq - ac * ac / n_called
        maf = min(mean / 2.0, 1.0 - mean / 2.0)
        moments.append(VariantMoments(n_called, ac, mean, sxx, maf))
    return tuple(moments)


def _pair_from_counts(
    row_a: int,
    row_b: int,
    variant_a: LDVariant,
    variant_b: LDVariant,
    counts: tuple[int, int, int, int, int, int, int, int, int],
) -> LDPair:
    n = sum(counts)
    sum_x = sum((cell // 3) * count for cell, count in enumerate(counts))
    sum_y = sum((cell % 3) * count for cell, count in enumerate(counts))
    sum_xx = sum((cell // 3) ** 2 * count for cell, count in enumerate(counts))
    sum_yy = sum((cell % 3) ** 2 * count for cell, count in enumerate(counts))
    sum_xy = sum((cell // 3) * (cell % 3) * count for cell, count in enumerate(counts))
    numerator = n * sum_xy - sum_x * sum_y
    var_x = n * sum_xx - sum_x * sum_x
    var_y = n * sum_yy - sum_y * sum_y

    if n < 2:
        status, r, r2 = "insufficient_observations", None, None
    elif var_x == 0 or var_y == 0:
        status, r, r2 = "zero_variance", None, None
    else:
        r = numerator / math.sqrt(var_x * var_y)
        status, r2 = "observed", r * r
    return LDPair(
        row_a,
        row_b,
        variant_a.gidx,
        variant_b.gidx,
        n,
        counts,
        status,
        r,
        r2,
    )


def reference_ld(
    calls: object,
    variants: object,
    *,
    genome_build: object,
    ploidy: object,
    window_variants: object,
    window_bp: object,
) -> tuple[LDPair, ...]:
    """Compute requested pairwise-complete correlations from exact nine-cell counts."""
    snapshot = validate_hard_calls(calls)
    block = validate_ld_variants(variants, genome_build=genome_build, ploidy=ploidy)
    if snapshot.shape[1] != len(block):
        raise ValueError("calls columns must exactly match variants in file-row order")
    planned_pairs = requested_pairs(
        block, window_variants=window_variants, window_bp=window_bp
    )
    result: list[LDPair] = []
    for row_a, row_b in planned_pairs:
        count_list = [0] * 9
        for dosage_a, dosage_b in zip(snapshot[:, row_a], snapshot[:, row_b], strict=True):
            value_a, value_b = int(dosage_a), int(dosage_b)
            if value_a != 3 and value_b != 3:
                count_list[value_a * 3 + value_b] += 1
        counts = tuple(count_list)
        result.append(_pair_from_counts(row_a, row_b, block[row_a], block[row_b], counts))
    return tuple(result)
