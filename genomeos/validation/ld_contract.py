"""Bounded training-only LD identity contracts (CuGen pilot design §3; Atlas design §4).

These pure contracts describe autosomal diploid hard calls and an explicit three-way sample
partition. They do not infer genome build, ploidy, ancestry, relatedness, or study independence.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from numbers import Integral
from os import PathLike

import numpy as np

MAX_LD_VARIANTS = 64
MAX_LD_SAMPLES = 4096
MAX_LD_PAIRS = 2016
_MAX_GIDX = 2**63 - 1
_MAX_POSITION = 2**31 - 1
_AUTOSOMES = frozenset(str(chrom) for chrom in range(1, 23))
_BASES = frozenset("ACGT")


def _exact_integer(value: object, name: str, *, minimum: int, maximum: int) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Integral):
        raise TypeError(f"{name} must be an exact integer")
    normalized = int(value)
    if not minimum <= normalized <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return normalized


def _in_memory_1d(
    value: object, name: str, *, allow_empty: bool, maximum_length: int | None = None
) -> tuple[object, ...]:
    if isinstance(value, (str, bytes, bytearray, PathLike)):
        raise TypeError(f"{name} must be an in-memory one-dimensional sequence")
    if isinstance(value, np.ndarray):
        if value.ndim != 1:
            raise ValueError(f"{name} must be one-dimensional")
        length = int(value.shape[0])
        if maximum_length is not None and length > maximum_length:
            raise ValueError(f"{name} exceeds the pilot cap of {maximum_length}")
        result = tuple(value.tolist())
    elif isinstance(value, Sequence):
        length = len(value)
        if maximum_length is not None and length > maximum_length:
            raise ValueError(f"{name} exceeds the pilot cap of {maximum_length}")
        result = tuple(value)
    else:
        raise TypeError(f"{name} must be an in-memory one-dimensional sequence")
    if not allow_empty and not result:
        raise ValueError(f"{name} must not be empty")
    return result


def _sample_id_tuple(value: object, name: str, *, allow_empty: bool) -> tuple[str, ...]:
    raw = _in_memory_1d(
        value, name, allow_empty=allow_empty, maximum_length=MAX_LD_SAMPLES
    )
    labels: list[str] = []
    for label in raw:
        if not isinstance(label, str) or not label or label != label.strip():
            raise ValueError(f"{name} must contain nonempty whitespace-trimmed strings")
        labels.append(label)
    if len(labels) != len(set(labels)):
        raise ValueError(f"{name} must contain unique strings")
    return tuple(labels)


@dataclass(frozen=True)
class LDVariant:
    """One exact GRCh38-oriented variant identity in CuGen file-row order."""

    gidx: int
    variant_id: str
    chrom: str
    position: int
    ref: str
    alt: str

    def __post_init__(self) -> None:
        gidx = _exact_integer(self.gidx, "gidx", minimum=0, maximum=_MAX_GIDX)
        position = _exact_integer(
            self.position, "position", minimum=1, maximum=_MAX_POSITION
        )
        if not isinstance(self.chrom, str) or self.chrom not in _AUTOSOMES:
            raise ValueError("chrom must be exactly one of the strings '1' through '22'")
        for allele_name, allele in (("ref", self.ref), ("alt", self.alt)):
            if (
                not isinstance(allele, str)
                or not allele
                or any(base not in _BASES for base in allele)
            ):
                raise ValueError(f"{allele_name} must be a nonempty uppercase A/C/G/T sequence")
        if self.ref == self.alt:
            raise ValueError("ref and alt must differ")
        expected_id = f"{self.chrom}-{position}-{self.ref}-{self.alt}"
        if not isinstance(self.variant_id, str) or self.variant_id != expected_id:
            raise ValueError(f"variant_id must be exactly {expected_id!r}")
        object.__setattr__(self, "gidx", gidx)
        object.__setattr__(self, "position", position)


@dataclass(frozen=True)
class TrainingSelection:
    """An immutable complete training, held-out, and excluded sample partition."""

    sample_ids: tuple[str, ...]
    training_indices: tuple[int, ...]
    training_ids: tuple[str, ...]
    held_out_ids: tuple[str, ...]
    excluded_ids: tuple[str, ...]


def validate_ld_variants(
    variants: object, *, genome_build: object, ploidy: object
) -> tuple[LDVariant, ...]:
    """Validate and snapshot one bounded, ordered autosomal variant block."""
    if not isinstance(genome_build, str) or genome_build != "GRCh38":
        raise ValueError("genome_build must be exactly 'GRCh38'")
    if not isinstance(ploidy, str) or ploidy != "autosomal_diploid":
        raise ValueError("ploidy must be exactly 'autosomal_diploid'")
    raw = _in_memory_1d(
        variants, "variants", allow_empty=False, maximum_length=MAX_LD_VARIANTS
    )
    if any(not isinstance(variant, LDVariant) for variant in raw):
        raise TypeError("variants must contain only LDVariant records")
    snapshot = tuple(
        LDVariant(
            variant.gidx,
            variant.variant_id,
            variant.chrom,
            variant.position,
            variant.ref,
            variant.alt,
        )
        for variant in raw
    )
    gidx = tuple(variant.gidx for variant in snapshot)
    variant_ids = tuple(variant.variant_id for variant in snapshot)
    if len(set(gidx)) != len(gidx):
        raise ValueError("variants must have unique gidx values")
    if len(set(variant_ids)) != len(variant_ids):
        raise ValueError("variants must have unique variant_id values")
    if len({variant.chrom for variant in snapshot}) != 1:
        raise ValueError("variants must belong to one chromosome")
    positions = tuple(variant.position for variant in snapshot)
    if any(left > right for left, right in zip(positions, positions[1:], strict=False)):
        raise ValueError("variant positions must be nondecreasing in file-row order")
    return snapshot


def validate_hard_calls(calls: object) -> np.ndarray:
    """Validate and return a detached, bytes-backed uint8 samples-by-variants snapshot."""
    if isinstance(calls, (str, bytes, bytearray, PathLike)):
        raise TypeError("calls must be an in-memory two-dimensional integer array")
    if isinstance(calls, np.ndarray):
        if calls.ndim != 2:
            raise ValueError("calls must be two-dimensional")
        sample_count, variant_count = calls.shape
        if not 1 <= sample_count <= MAX_LD_SAMPLES:
            raise ValueError(f"calls sample count must be between 1 and {MAX_LD_SAMPLES}")
        if not 1 <= variant_count <= MAX_LD_VARIANTS:
            raise ValueError(f"calls variant count must be between 1 and {MAX_LD_VARIANTS}")
        if not np.issubdtype(calls.dtype, np.integer) or np.issubdtype(calls.dtype, np.bool_):
            raise TypeError("calls must contain exact integer hard calls")
        array = calls
    elif isinstance(calls, Sequence):
        if not 1 <= len(calls) <= MAX_LD_SAMPLES:
            raise ValueError(f"calls sample count must be between 1 and {MAX_LD_SAMPLES}")
        raw_rows = tuple(calls)
        rows: list[tuple[object, ...]] = []
        for row in raw_rows:
            if isinstance(row, (str, bytes, bytearray, PathLike)):
                raise TypeError("calls rows must be in-memory one-dimensional sequences")
            if isinstance(row, np.ndarray):
                if row.ndim != 1:
                    raise ValueError("calls must be two-dimensional")
                if not 1 <= row.shape[0] <= MAX_LD_VARIANTS:
                    raise ValueError(
                        f"calls variant count must be between 1 and {MAX_LD_VARIANTS}"
                    )
                if not np.issubdtype(row.dtype, np.integer) or np.issubdtype(
                    row.dtype, np.bool_
                ):
                    raise TypeError("calls must contain exact integer hard calls")
                values = tuple(row)
            elif isinstance(row, Sequence):
                if not 1 <= len(row) <= MAX_LD_VARIANTS:
                    raise ValueError(
                        f"calls variant count must be between 1 and {MAX_LD_VARIANTS}"
                    )
                values = tuple(row)
            else:
                raise ValueError("calls must be two-dimensional")
            for value in values:
                if isinstance(value, (bool, np.bool_)) or not isinstance(value, Integral):
                    raise TypeError("calls must contain exact integer hard calls")
                if value < 0 or value > 3:
                    raise ValueError("calls values must be ALT dosages 0/1/2 or missing value 3")
            rows.append(values)
        try:
            array = np.asarray(rows)
        except ValueError as error:
            raise ValueError("calls must be a rectangular two-dimensional array") from error
        if array.ndim != 2 or not np.issubdtype(array.dtype, np.integer):
            raise TypeError("calls must contain exact integer hard calls")
    else:
        raise TypeError("calls must be an in-memory two-dimensional integer array")

    sample_count, variant_count = array.shape
    if not 1 <= sample_count <= MAX_LD_SAMPLES:
        raise ValueError(f"calls sample count must be between 1 and {MAX_LD_SAMPLES}")
    if not 1 <= variant_count <= MAX_LD_VARIANTS:
        raise ValueError(f"calls variant count must be between 1 and {MAX_LD_VARIANTS}")
    if np.any(array < 0) or np.any(array > 3):
        raise ValueError("calls values must be ALT dosages 0/1/2 or missing value 3")
    contiguous = np.ascontiguousarray(array, dtype=np.uint8)
    return np.frombuffer(contiguous.tobytes(), dtype=np.uint8).reshape(contiguous.shape)


def validate_training_selection(
    sample_ids: object,
    training_indices: object,
    *,
    held_out_ids: object,
    excluded_ids: object,
) -> TrainingSelection:
    """Validate and snapshot one explicit, complete three-way source-sample partition."""
    samples = _sample_id_tuple(sample_ids, "sample_ids", allow_empty=False)
    if len(samples) > MAX_LD_SAMPLES:
        raise ValueError(f"sample_ids exceeds the pilot cap of {MAX_LD_SAMPLES}")
    raw_indices = _in_memory_1d(
        training_indices,
        "training_indices",
        allow_empty=False,
        maximum_length=len(samples),
    )
    indices = tuple(
        _exact_integer(index, "training_indices", minimum=0, maximum=len(samples) - 1)
        for index in raw_indices
    )
    if len(indices) != len(set(indices)):
        raise ValueError("training_indices must be unique")
    training = tuple(samples[index] for index in indices)
    held_out = _sample_id_tuple(held_out_ids, "held_out_ids", allow_empty=True)
    excluded = _sample_id_tuple(excluded_ids, "excluded_ids", allow_empty=True)

    partitions = (set(training), set(held_out), set(excluded))
    if partitions[0] & partitions[1] or partitions[0] & partitions[2] or partitions[1] & partitions[2]:
        raise ValueError("training, held-out, and excluded sample IDs must not overlap")
    if set.union(*partitions) != set(samples):
        raise ValueError("training, held-out, and excluded sample IDs must partition sample_ids")
    return TrainingSelection(samples, indices, training, held_out, excluded)
