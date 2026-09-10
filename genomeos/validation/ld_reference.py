"""Independent pairwise-complete ALT-dosage LD reference (CuGen pilot design §4).

The reference enumerates exact integer contingency counts independently of CuGen. Its pairwise
correlations are not a joint covariance model and are never projected, imputed, or PSD-repaired.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Integral, Real
from typing import Literal

import numpy as np

from genomeos.validation.ld_contract import (
    MAX_LD_PAIRS,
    MAX_LD_SAMPLES,
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


def _evidence_integer(value: object, name: str, maximum: int) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Integral):
        raise TypeError(f"{name} must be an exact integer")
    normalized = int(value)
    if not 0 <= normalized <= maximum:
        raise ValueError(f"{name} must be between 0 and {maximum}")
    return normalized


def _evidence_float(value: object, name: str, minimum: float, maximum: float) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise TypeError(f"{name} must be a real number")
    normalized = float(value)
    if not math.isfinite(normalized) or not minimum <= normalized <= maximum:
        raise ValueError(f"{name} must be finite and in [{minimum}, {maximum}]")
    return normalized


def _validate_moment(moment: VariantMoments) -> tuple[VariantMoments, tuple[int, int, int]]:
    n = _evidence_integer(moment.n_called, "moment n_called", MAX_LD_SAMPLES)
    ac = _evidence_integer(moment.ac, "moment ac", 2 * n)
    if n == 0:
        if ac != 0 or (moment.mean, moment.sxx, moment.maf) != (None, None, None):
            raise ValueError("an all-missing moment must have zero ac and undefined statistics")
        return VariantMoments(0, 0, None, None, None), (0, 0, 0)
    mean = _evidence_float(moment.mean, "moment mean", 0.0, 2.0)
    sxx = _evidence_float(moment.sxx, "moment sxx", 0.0, 4.0 * n)
    maf = _evidence_float(moment.maf, "moment maf", 0.0, 0.5)
    if mean != ac / n or maf != min(mean / 2.0, 1.0 - mean / 2.0):
        raise ValueError("moment mean or MAF disagrees with n_called and ac")
    for n_alt_homozygous in range(max(0, ac - n), ac // 2 + 1):
        n_heterozygous = ac - 2 * n_alt_homozygous
        n_reference = n - n_heterozygous - n_alt_homozygous
        expected_sxx = n_heterozygous + 4 * n_alt_homozygous - ac * ac / n
        if sxx == expected_sxx:
            return (
                VariantMoments(n, ac, mean, sxx, maf),
                (n_reference, n_heterozygous, n_alt_homozygous),
            )
    raise ValueError("moment sxx is not realizable by exact diploid hard calls")


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


def validate_ld_evidence(
    reference: object,
    variants: object,
    moments: object,
    *,
    genome_build: object,
    ploidy: object,
) -> tuple[tuple[LDPair, ...], tuple[VariantMoments, ...]]:
    """Validate and snapshot exact pair counts, correlations, and realizable moments."""
    block = validate_ld_variants(variants, genome_build=genome_build, ploidy=ploidy)
    if not isinstance(reference, (tuple, list)):
        raise TypeError("reference must contain LDPair records")
    if len(reference) > MAX_LD_PAIRS:
        raise ValueError(f"reference exceeds the pilot cap of {MAX_LD_PAIRS}")
    raw_pairs = tuple(reference)
    if any(not isinstance(pair, LDPair) for pair in raw_pairs):
        raise TypeError("reference must contain LDPair records")
    if not isinstance(moments, (tuple, list)):
        raise TypeError("moments must contain VariantMoments records")
    if len(moments) != len(block):
        raise ValueError("moments must exactly match variants in file-row order")
    raw_moments = tuple(moments)
    if any(not isinstance(moment, VariantMoments) for moment in raw_moments):
        raise TypeError("moments must contain VariantMoments records")
    validated_moments = tuple(_validate_moment(moment) for moment in raw_moments)
    moment_block = tuple(item[0] for item in validated_moments)
    genotype_counts = tuple(item[1] for item in validated_moments)
    seen: set[tuple[int, int]] = set()
    pairs: list[LDPair] = []
    for pair in raw_pairs:
        row_a = _evidence_integer(pair.row_a, "reference row_a", len(block) - 1)
        row_b = _evidence_integer(pair.row_b, "reference row_b", len(block) - 1)
        if row_a >= row_b:
            raise ValueError("reference contains an invalid row pair")
        identity = row_a, row_b
        if identity in seen:
            raise ValueError("reference contains a duplicate row pair")
        seen.add(identity)
        gidx_a = _evidence_integer(pair.gidx_a, "reference gidx_a", 2**63 - 1)
        gidx_b = _evidence_integer(pair.gidx_b, "reference gidx_b", 2**63 - 1)
        if (gidx_a, gidx_b) != (block[row_a].gidx, block[row_b].gidx):
            raise ValueError("reference gidx identity disagrees with variants")
        n_obs = _evidence_integer(pair.n_obs, "reference n_obs", MAX_LD_SAMPLES)
        if not isinstance(pair.counts, tuple) or len(pair.counts) != 9:
            raise ValueError("reference counts must be an exact nine-integer tuple")
        counts = tuple(_evidence_integer(count, "reference count", MAX_LD_SAMPLES) for count in pair.counts)
        if sum(counts) != n_obs:
            raise ValueError("reference counts must sum exactly to n_obs")
        expected = _pair_from_counts(row_a, row_b, block[row_a], block[row_b], counts)
        if pair.status != expected.status:
            raise ValueError("reference status disagrees with exact count precedence")
        if expected.r is None:
            if pair.r is not None or pair.r2 is not None:
                raise ValueError("undefined reference correlation values must be None")
            r, r2 = None, None
        else:
            r = _evidence_float(pair.r, "reference r", -1.0, 1.0)
            r2 = _evidence_float(pair.r2, "reference r2", 0.0, 1.0)
            if r != expected.r or r2 != expected.r2:
                raise ValueError("reference r or r2 disagrees with exact counts")
        marginals = (
            tuple(sum(counts[3 * dosage + other] for other in range(3)) for dosage in range(3)),
            tuple(sum(counts[3 * other + dosage] for other in range(3)) for dosage in range(3)),
        )
        if any(
            observed > available
            for observed_counts, available_counts in zip(
                marginals, (genotype_counts[row_a], genotype_counts[row_b]), strict=True
            )
            for observed, available in zip(observed_counts, available_counts, strict=True)
        ):
            raise ValueError("reference pair marginals disagree with variant moments")
        pairs.append(LDPair(row_a, row_b, gidx_a, gidx_b, n_obs, counts, expected.status, r, r2))
    return tuple(pairs), moment_block


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
