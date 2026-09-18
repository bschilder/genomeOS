"""Project reference count tracks (reference acquisition design §5)."""

from __future__ import annotations

import json
import re
from typing import Literal

from genomeos.validation.reference_acquisition_types import AcquisitionWindowReceipt
from genomeos.validation.reference_counts import ReferenceCount, validate_reference_counts
from genomeos.validation.reference_genotypes import VariantCounts
from genomeos.validation.reference_preparation_types import PreparationWindowReceipt
from genomeos.validation.reference_window_types import ReferenceWindow

_VARIANT = re.compile(r"GRCh38:(chr(?:[1-9]|1[0-9]|2[0-2])):([1-9][0-9]*):([^:]+):([^:]+)\Z")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def prepare_rows(
    window: ReferenceWindow,
    counts: tuple[VariantCounts, ...],
    *,
    kind: Literal["called", "quality"],
) -> tuple[ReferenceCount, ...]:
    """Project one stage/window into a lossless called or quality count table."""
    _require(type(window) is ReferenceWindow and type(counts) is tuple, "invalid projection inputs")
    _require(kind in ("called", "quality"), "invalid count track kind")
    _require(all(type(value) is VariantCounts for value in counts), "invalid variant counts")
    variant_ids = tuple(value.variant_id for value in counts)
    _require(len(variant_ids) == len(set(variant_ids)), "duplicate variant counts")
    expected_groups: tuple[tuple[str, str], ...] | None = None
    rows: list[ReferenceCount] = []
    variant_group = f"GRCh38:{window.chrom}:{window.start0 + 1}-{window.end0}"
    for value in counts:
        match = _VARIANT.fullmatch(value.variant_id)
        _require(match is not None, "invalid count variant identity")
        chrom, pos = match.group(1), int(match.group(2))
        _require(chrom == window.chrom and window.start0 < pos <= window.end0,
                 "variant lies outside its window")
        groups = tuple((item.population, item.region) for item in value.populations)
        if expected_groups is None:
            expected_groups = groups
        _require(groups == expected_groups, "variant population keys differ")
        for population in value.populations:
            ac = population.called_ac if kind == "called" else population.quality_ac
            an = population.called_an if kind == "called" else population.quality_an
            record_id = json.dumps([population.population, value.variant_id], separators=(",", ":"))
            rows.append(
                ReferenceCount(
                    record_id,
                    value.variant_id,
                    population.population,
                    population.region,
                    variant_group,
                    ac,
                    an,
                )
            )
    result = tuple(sorted(rows, key=lambda row: row.record_id))
    if result:
        validate_reference_counts(result)
    return result


def check_native_totals(
    counts: tuple[VariantCounts, ...],
    native: tuple[tuple[str, int, int], ...],
) -> None:
    """Join native called totals by exact variant ID and compare every retained site."""
    _require(type(counts) is tuple and all(type(value) is VariantCounts for value in counts),
             "invalid Python counts")
    _require(type(native) is tuple, "native totals must be a tuple")
    native_by_id: dict[str, tuple[int, int]] = {}
    for entry in native:
        _require(type(entry) is tuple and len(entry) == 3, "invalid native total entry")
        variant_id, ac, an = entry
        _require(isinstance(variant_id, str) and type(ac) is int and type(an) is int,
                 "invalid native total value")
        _require(0 <= ac <= an and variant_id not in native_by_id, "invalid or duplicate native total")
        native_by_id[variant_id] = (ac, an)
    expected_ids = {value.variant_id for value in counts}
    _require(len(expected_ids) == len(counts) and set(native_by_id) == expected_ids,
             "native variant identity mismatch")
    for value in counts:
        expected = (
            sum(population.called_ac for population in value.populations),
            sum(population.called_an for population in value.populations),
        )
        _require(native_by_id[value.variant_id] == expected, "native called count mismatch")


def validate_acquisition_window_accounting(
    expected_ids: tuple[str, ...],
    receipts: tuple[AcquisitionWindowReceipt, ...],
) -> None:
    """Require one acquisition receipt for every expected window in frozen order."""
    _require(type(expected_ids) is tuple and len(expected_ids) == len(set(expected_ids)),
             "invalid expected window IDs")
    _require(type(receipts) is tuple and all(type(value) is AcquisitionWindowReceipt for value in receipts),
             "invalid acquisition receipts")
    _require(tuple(value.window_id for value in receipts) == expected_ids,
             "acquisition window accounting mismatch")


def validate_preparation_window_accounting(
    expected_ids: tuple[str, ...],
    receipts: tuple[PreparationWindowReceipt, ...],
) -> None:
    """Require one preparation receipt for every expected window in frozen order."""
    _require(type(expected_ids) is tuple and len(expected_ids) == len(set(expected_ids)),
             "invalid expected window IDs")
    _require(type(receipts) is tuple and all(type(value) is PreparationWindowReceipt for value in receipts),
             "invalid preparation receipts")
    _require(tuple(value.window_id for value in receipts) == expected_ids,
             "preparation window accounting mismatch")
