"""Dependency-light reference count records (reference acquisition design §5)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from numbers import Integral


def _literal_id(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonempty literal string")
    return value


def _integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise ValueError(f"{name} must be an integer")
    return int(value)


@dataclass(frozen=True)
class ReferenceCount:
    """One qualified reference-resource allele count."""

    record_id: str
    variant_id: str
    group_id: str
    region_id: str
    variant_group: str
    ac: int
    an: int

    def __post_init__(self) -> None:
        for name in (
            "record_id",
            "variant_id",
            "group_id",
            "region_id",
            "variant_group",
        ):
            object.__setattr__(self, name, _literal_id(getattr(self, name), name))
        ac = _integer(self.ac, "ac")
        an = _integer(self.an, "an")
        if an < 0:
            raise ValueError("an must be a nonnegative integer")
        if ac < 0 or ac > an:
            raise ValueError("ac must satisfy 0 <= ac <= an")
        object.__setattr__(self, "ac", ac)
        object.__setattr__(self, "an", an)


def validate_reference_counts(
    rows: Sequence[ReferenceCount],
) -> tuple[ReferenceCount, ...]:
    """Validate a nonempty reference table while preserving its row order."""
    normalized = tuple(rows)
    if not normalized:
        raise ValueError("reference counts must be nonempty")
    if any(not isinstance(row, ReferenceCount) for row in normalized):
        raise ValueError("rows must contain only ReferenceCount values")

    record_ids = tuple(row.record_id for row in normalized)
    if len(set(record_ids)) != len(record_ids):
        raise ValueError("record_id values must be unique")
    group_variants = tuple((row.group_id, row.variant_id) for row in normalized)
    if len(set(group_variants)) != len(group_variants):
        raise ValueError("(group_id, variant_id) values must be unique")

    group_regions: dict[str, str] = {}
    variant_groups: dict[str, str] = {}
    for row in normalized:
        previous_region = group_regions.setdefault(row.group_id, row.region_id)
        if previous_region != row.region_id:
            raise ValueError("each group_id must have exactly one region_id")
        previous_group = variant_groups.setdefault(row.variant_id, row.variant_group)
        if previous_group != row.variant_group:
            raise ValueError("each variant_id must have exactly one variant_group")
    return normalized
