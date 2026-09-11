"""Pure deterministic reference-window geometry (design §§4–8, 12; preflight design §3)."""

from __future__ import annotations

import numpy as np

from genomeos.validation.reference_window_types import (
    AUTOSOMES,
    BIT_GENERATOR,
    DRAW_METHOD,
    EXCLUSION_CHROM,
    MAX_TRANSFER_BYTES,
    SEED,
    STRATA,
    WIDTH,
    ReferenceWindow,
    StartRun,
    WindowConfig,
)

__all__ = [
    "BIT_GENERATOR",
    "DRAW_METHOD",
    "MAX_TRANSFER_BYTES",
    "SEED",
    "eligible_start_runs",
    "select_reference_windows",
    "start_at_rank",
]


def _integer(value: object, field: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{field} must be an integer >= {minimum}")
    return value


def eligible_start_runs(
    stratum_start0: int,
    stratum_end0: int,
    width: int,
    exclusions: tuple[tuple[int, int], ...],
) -> tuple[StartRun, ...]:
    """Return sorted inclusive runs of starts whose half-open windows avoid exclusions."""
    start = _integer(stratum_start0, "stratum_start0")
    end = _integer(stratum_end0, "stratum_end0", minimum=1)
    window_width = _integer(width, "width", minimum=1)
    if start >= end or end - start < window_width:
        raise ValueError("stratum cannot contain a window of the requested width")
    if type(exclusions) is not tuple:
        raise TypeError("exclusions must be a tuple")

    candidate_last = end - window_width
    forbidden: list[tuple[int, int]] = []
    for exclusion in exclusions:
        if type(exclusion) is not tuple or len(exclusion) != 2:
            raise ValueError("each exclusion must be a two-tuple")
        left = _integer(exclusion[0], "exclusion start")
        right = _integer(exclusion[1], "exclusion end", minimum=1)
        if left >= right:
            raise ValueError("exclusion start must precede end")
        first = max(start, left - window_width + 1)
        last = min(candidate_last, right - 1)
        if first <= last:
            forbidden.append((first, last))

    merged: list[list[int]] = []
    for first, last in sorted(forbidden):
        if merged and first <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], last)
        else:
            merged.append([first, last])

    runs: list[StartRun] = []
    cursor = start
    for first, last in merged:
        if cursor < first:
            runs.append(StartRun(cursor, first - 1))
        cursor = last + 1
    if cursor <= candidate_last:
        runs.append(StartRun(cursor, candidate_last))
    if not runs:
        raise ValueError("stratum has no eligible window starts")
    return tuple(runs)


def start_at_rank(runs: tuple[StartRun, ...], rank: int) -> int:
    """Map one zero-based rank into sorted inclusive start runs."""
    if type(runs) is not tuple or not runs or any(type(run) is not StartRun for run in runs):
        raise ValueError("runs must be a nonempty tuple of StartRun values")
    target = _integer(rank, "rank")
    previous = -1
    for run in runs:
        if run.first <= previous:
            raise ValueError("runs must be sorted and disjoint")
        previous = run.last
    for run in runs:
        size = run.last - run.first + 1
        if target < size:
            return run.first + target
        target -= size
    raise ValueError("rank is outside eligible starts")


def select_reference_windows(
    lengths: tuple[tuple[str, int], ...], config: WindowConfig
) -> tuple[ReferenceWindow, ...]:
    """Select the fixed three-by-22 window design with one PCG64 generator."""
    if type(config) is not WindowConfig:
        raise TypeError("config must be WindowConfig")
    if config.numpy_version != np.__version__:
        raise ValueError("NumPy version does not match the frozen selection configuration")
    if type(lengths) is not tuple:
        raise TypeError("lengths must be a tuple")
    normalized: dict[str, int] = {}
    for entry in lengths:
        if type(entry) is not tuple or len(entry) != 2:
            raise ValueError("contig lengths must be two-tuples")
        chrom, length = entry
        if chrom not in AUTOSOMES or chrom in normalized:
            raise ValueError("contig lengths must contain each autosome exactly once")
        normalized[chrom] = _integer(length, "contig length", minimum=1)
    if set(normalized) != set(AUTOSOMES):
        raise ValueError("contig lengths must contain each autosome exactly once")
    if any(length >= 2**29 for length in normalized.values()):
        raise ValueError("contig length must be below 2^29")

    rng = np.random.Generator(np.random.PCG64(config.seed))
    windows: list[ReferenceWindow] = []
    for chrom in AUTOSOMES:
        length = normalized[chrom]
        for index in range(STRATA):
            stratum_start = length * index // STRATA
            stratum_end = length * (index + 1) // STRATA
            exclusions = (
                ((config.exclusion.start0, config.exclusion.end0),) if chrom == EXCLUSION_CHROM else ()
            )
            runs = eligible_start_runs(stratum_start, stratum_end, WIDTH, exclusions)
            total = sum(run.last - run.first + 1 for run in runs)
            rank = int(rng.integers(0, total, dtype=np.int64))
            start = start_at_rank(runs, rank)
            windows.append(
                ReferenceWindow(
                    window_id=f"{chrom}-s{index + 1}",
                    chrom=chrom,
                    stratum=index + 1,
                    stratum_start0=stratum_start,
                    stratum_end0=stratum_end,
                    start0=start,
                    end0=start + WIDTH,
                    eligible_runs=runs,
                    eligible_count=total,
                    rank=rank,
                )
            )
    return tuple(windows)
