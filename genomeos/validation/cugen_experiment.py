"""Deterministic synthetic CuGen experiment cases (CuGen pilot design §§4, 8).

These fixtures exercise bounded training-only LD and leakage controls. They contain no real
genotypes and make no allele-frequency, haplotype, covariance, or publication claim.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from genomeos.validation.ld_contract import (
    LDVariant,
    TrainingSelection,
    validate_hard_calls,
    validate_ld_variants,
    validate_training_selection,
)

SEED = 42
PrecisionControl = tuple[int, bool, bool, int, int]


@dataclass(frozen=True)
class SyntheticLDCase:
    """One validated synthetic source and explicit execution configuration."""

    name: str
    calls: np.ndarray
    variants: tuple[LDVariant, ...]
    selection: TrainingSelection
    window_variants: int | None
    window_bp: int | None
    chunk_size: int
    tile_size: int
    precision_controls: tuple[PrecisionControl, ...] = ()


def _variants(count: int) -> tuple[LDVariant, ...]:
    items = tuple(
        LDVariant(
            gidx=(row * 17) % count,
            variant_id=f"1-{101 + row * 100}-A-C",
            chrom="1",
            position=101 + row * 100,
            ref="A",
            alt="C",
        )
        for row in range(count)
    )
    return validate_ld_variants(items, genome_build="GRCh38", ploidy="autosomal_diploid")


def _selection(
    sample_count: int,
    training_indices: tuple[int, ...],
    held_out_indices: tuple[int, ...],
) -> TrainingSelection:
    sample_ids = tuple(f"synthetic-sample-{row:04d}" for row in range(sample_count))
    assigned = set(training_indices) | set(held_out_indices)
    excluded_indices = tuple(row for row in range(sample_count) if row not in assigned)
    return validate_training_selection(
        sample_ids,
        training_indices,
        held_out_ids=tuple(sample_ids[row] for row in held_out_indices),
        excluded_ids=tuple(sample_ids[row] for row in excluded_indices),
    )


def _hand_case() -> SyntheticLDCase:
    calls = np.array(
        [
            [0, 0, 2, 3, 1, 0, 3],
            [1, 1, 1, 3, 1, 3, 3],
            [2, 2, 0, 3, 1, 2, 3],
            [0, 2, 0, 3, 1, 3, 0],
            [2, 0, 2, 3, 1, 1, 1],
            [1, 2, 0, 3, 1, 2, 3],
            [0, 1, 1, 3, 1, 0, 0],
            [2, 0, 2, 3, 1, 2, 3],
        ],
        dtype=np.uint8,
    )
    gidx = (30, 10, 70, 20, 60, 40, 50)
    variants = validate_ld_variants(
        tuple(
            LDVariant(
                gidx=gidx[row],
                variant_id=f"1-{101 + row * 100}-A-C",
                chrom="1",
                position=101 + row * 100,
                ref="A",
                alt="C",
            )
            for row in range(7)
        ),
        genome_build="GRCh38",
        ploidy="autosomal_diploid",
    )
    return SyntheticLDCase(
        name="hand",
        calls=validate_hard_calls(calls),
        variants=variants,
        selection=_selection(8, (4, 0, 2, 1), (3,)),
        window_variants=None,
        window_bp=None,
        chunk_size=3,
        tile_size=3,
    )


def _scale_case(seed: int) -> SyntheticLDCase:
    rows = np.arange(4096, dtype=np.int64)[:, None]
    columns = np.arange(64, dtype=np.int64)[None, :]
    pattern = (rows * 17 + columns * 13 + seed) % 23
    calls = (pattern % 3).astype(np.uint8)
    calls[pattern == 22] = 3
    return SyntheticLDCase(
        name="scale",
        calls=validate_hard_calls(calls),
        variants=_variants(64),
        selection=_selection(4096, tuple(range(3072)), tuple(range(3072, 3584))),
        window_variants=None,
        window_bp=None,
        chunk_size=64,
        tile_size=64,
    )


def _precision_case() -> SyntheticLDCase:
    controls: tuple[PrecisionControl, ...] = (
        (3072, False, False, 0, 1),
        (3072, False, True, 2, 3),
        (3072, True, False, 4, 5),
        (3072, True, True, 6, 7),
        (4096, False, False, 8, 9),
        (4096, False, True, 10, 11),
        (4096, True, False, 12, 13),
        (4096, True, True, 14, 15),
    )
    calls = np.full((4096, 16), 3, dtype=np.uint8)
    for sample_count, overlap, flipped, left, right in controls:
        baseline = 0 if flipped else 2
        calls[:sample_count, left] = baseline
        calls[:sample_count, right] = baseline
        calls[0, left] = 1
        calls[[0, 1] if overlap else [1, 2], right] = 1
    return SyntheticLDCase(
        name="precision",
        calls=validate_hard_calls(calls),
        variants=_variants(16),
        selection=_selection(4096, tuple(range(4096)), ()),
        window_variants=1,
        window_bp=None,
        chunk_size=3,
        tile_size=3,
        precision_controls=controls,
    )


def build_synthetic_case(name: str, *, seed: int = SEED) -> SyntheticLDCase:
    """Return one immutable validated synthetic case under the fixed pilot seed."""
    if type(seed) is not int or seed != SEED:
        raise ValueError(f"seed must be the fixed synthetic pilot seed {SEED}")
    if name == "hand":
        return _hand_case()
    if name == "scale":
        return _scale_case(seed)
    if name == "precision":
        return _precision_case()
    raise ValueError("case must be one of: hand, scale, precision")


def mutate_held_out(case: SyntheticLDCase) -> SyntheticLDCase:
    """Change every held-out genotype while preserving all selected training calls."""
    if not isinstance(case, SyntheticLDCase):
        raise TypeError("case must be a SyntheticLDCase")
    if not case.selection.held_out_ids:
        raise ValueError("held-out mutation requires at least one held-out sample")
    row_by_id = {sample_id: row for row, sample_id in enumerate(case.selection.sample_ids)}
    held_rows = np.asarray([row_by_id[item] for item in case.selection.held_out_ids], dtype=np.int64)
    changed = case.calls.copy()
    changed[held_rows] = (changed[held_rows] + 1) % 4
    return replace(case, calls=validate_hard_calls(changed))
