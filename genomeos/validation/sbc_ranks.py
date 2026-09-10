"""Discrete B0H simulation-calibration ranks (design §§ 5, 7–8, 12; #211)."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from numbers import Integral, Real

import numpy as np

SEED = 42
_DRAW_COUNT = 4
_RANK_COUNT = _DRAW_COUNT + 1
_MAX_SIMULATION_SIZE = 1_000_000
_BONFERRONI_TESTS = 12


def _integer(value: object, name: str, *, minimum: int = 0) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Integral):
        raise ValueError(f"{name} must be an integer >= {minimum}")
    normalized = int(value)
    if normalized < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return normalized


def _finite_real(value: object, name: str) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a finite real scalar")
    try:
        normalized = float(value)
    except OverflowError as error:
        raise ValueError(f"{name} must be a finite real scalar") from error
    if not math.isfinite(normalized):
        raise ValueError(f"{name} must be a finite real scalar")
    return normalized


def _sequence(value: object, name: str) -> tuple[object, ...]:
    try:
        return tuple(value)  # type: ignore[arg-type]
    except TypeError as error:
        raise ValueError(f"{name} must be a sequence") from error


def _counts(value: object) -> tuple[int, ...]:
    consumed = _sequence(value, "counts")
    if len(consumed) != _RANK_COUNT:
        raise ValueError("counts must contain exactly five integers")
    normalized = tuple(_integer(item, "count") for item in consumed)
    if sum(normalized) == 0:
        raise ValueError("counts must have a positive total")
    return normalized


def _ranks(value: object) -> tuple[int, ...]:
    consumed = _sequence(value, "ranks")
    if not consumed:
        raise ValueError("ranks must be nonempty")
    normalized = tuple(_integer(item, "rank") for item in consumed)
    if any(rank >= _RANK_COUNT for rank in normalized):
        raise ValueError("ranks must contain only integers from 0 through 4")
    return normalized


def randomized_rank(truth: float, draws: Sequence[float], *, seed: int) -> int:
    """Rank a literal truth among exactly four draws, randomizing exact ties."""
    normalized_truth = _finite_real(truth, "truth")
    consumed_draws = _sequence(draws, "draws")
    if len(consumed_draws) != _DRAW_COUNT:
        raise ValueError("draws must contain exactly four values")
    normalized_draws = tuple(
        _finite_real(draw, f"draws[{index}]")
        for index, draw in enumerate(consumed_draws)
    )
    normalized_seed = _integer(seed, "seed")
    less = sum(draw < normalized_truth for draw in normalized_draws)
    tied = sum(draw == normalized_truth for draw in normalized_draws)
    rng = np.random.default_rng(normalized_seed)
    return less + int(rng.integers(0, tied + 1))


def rank_ecdf_statistic(counts: Sequence[int]) -> int:
    """Return the exact integer ECDF discrepancy for five rank-bin counts."""
    normalized = _counts(counts)
    sample_size = sum(normalized)
    return max(
        abs(_RANK_COUNT * sum(normalized[: k + 1]) - sample_size * (k + 1))
        for k in range(_DRAW_COUNT)
    )


@dataclass(frozen=True)
class RankNullReference:
    """Immutable discrete-null statistics for one exact study sample size."""

    sample_size: int
    seed: int
    statistics: tuple[int, ...]

    def __post_init__(self) -> None:
        sample_size = _integer(self.sample_size, "sample_size", minimum=1)
        seed = _integer(self.seed, "seed")
        consumed = _sequence(self.statistics, "statistics")
        if not consumed:
            raise ValueError("statistics must be nonempty")
        statistics = tuple(_integer(value, "statistic") for value in consumed)
        if any(value > _DRAW_COUNT * sample_size for value in statistics):
            raise ValueError("statistics must be between 0 and 4 * sample_size")
        object.__setattr__(self, "sample_size", sample_size)
        object.__setattr__(self, "seed", seed)
        object.__setattr__(self, "statistics", statistics)


@dataclass(frozen=True)
class RankTestResult:
    """Observed rank histogram, discrepancy, and raw and adjusted p-values."""

    counts: tuple[int, ...]
    statistic: int
    p_value: float
    bonferroni_p_value: float

    def __post_init__(self) -> None:
        counts = _counts(self.counts)
        statistic = _integer(self.statistic, "statistic")
        if statistic != rank_ecdf_statistic(counts):
            raise ValueError("statistic does not match counts")
        p_value = _finite_real(self.p_value, "p_value")
        adjusted = _finite_real(self.bonferroni_p_value, "bonferroni_p_value")
        if not 0.0 <= p_value <= 1.0 or not 0.0 <= adjusted <= 1.0:
            raise ValueError("p-values must be between 0 and 1")
        if adjusted != min(1.0, _BONFERRONI_TESTS * p_value):
            raise ValueError("bonferroni_p_value does not match p_value")
        object.__setattr__(self, "counts", counts)
        object.__setattr__(self, "statistic", statistic)
        object.__setattr__(self, "p_value", p_value)
        object.__setattr__(self, "bonferroni_p_value", adjusted)


def simulate_rank_null(
    *, sample_size: int, replicates: int, seed: int
) -> RankNullReference:
    """Simulate the exact five-category multinomial null for rank histograms."""
    normalized_size = _integer(sample_size, "sample_size", minimum=1)
    normalized_replicates = _integer(replicates, "replicates", minimum=1)
    normalized_seed = _integer(seed, "seed")
    if normalized_size > _MAX_SIMULATION_SIZE:
        raise ValueError("sample_size must be <= 1_000_000")
    if normalized_replicates > _MAX_SIMULATION_SIZE:
        raise ValueError("replicates must be <= 1_000_000")
    rng = np.random.default_rng(normalized_seed)
    counts = rng.multinomial(
        normalized_size,
        (1.0 / _RANK_COUNT,) * _RANK_COUNT,
        size=normalized_replicates,
    )
    statistics = tuple(rank_ecdf_statistic(row) for row in counts)
    return RankNullReference(
        sample_size=normalized_size,
        seed=normalized_seed,
        statistics=statistics,
    )


def _validated_reference(reference: object) -> RankNullReference:
    if not isinstance(reference, RankNullReference):
        raise ValueError("reference must be a RankNullReference")
    try:
        return RankNullReference(
            sample_size=reference.sample_size,
            seed=reference.seed,
            statistics=reference.statistics,
        )
    except (AttributeError, TypeError, ValueError) as error:
        raise ValueError("reference must contain valid immutable null values") from error


def test_rank_uniformity(
    ranks: Sequence[int], *, reference: RankNullReference
) -> RankTestResult:
    """Compare complete five-bin ranks with their exact-size discrete null."""
    normalized_reference = _validated_reference(reference)
    normalized_ranks = _ranks(ranks)
    if len(normalized_ranks) != normalized_reference.sample_size:
        raise ValueError("ranks length must equal reference sample_size")
    counts = tuple(normalized_ranks.count(rank) for rank in range(_RANK_COUNT))
    statistic = rank_ecdf_statistic(counts)
    exceedances = sum(
        null_statistic >= statistic
        for null_statistic in normalized_reference.statistics
    )
    p_value = (1 + exceedances) / (1 + len(normalized_reference.statistics))
    return RankTestResult(
        counts=counts,
        statistic=statistic,
        p_value=p_value,
        bonferroni_p_value=min(1.0, _BONFERRONI_TESTS * p_value),
    )


test_rank_uniformity.__test__ = False
