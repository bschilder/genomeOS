"""Outcome-blind three-fold grouping for nested model selection (design §§4, 8, 12; #374).

Scientific objective
    Preserve the global modeling plan's three-inner-fold protocol when an outer-training set
    contains more than three original geographic blocks.
Measurable output
    A deterministic, content-hashed mapping from every original block to exactly one of three
    nonempty inner groups, balanced by training-record count without reading allele outcomes.
Engineering interface
    :func:`plan_three_inner_folds` freezes the mapping and :func:`apply_three_inner_folds` applies
    it to the exact assignments used to create the plan.
Assumptions and refusals
    Source-record identity and original block labels are the only inputs. Fewer than three blocks,
    duplicate identities, missing labels, changed assignments, or malformed plans are refused.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

import pandas as pd

THREE_INNER_FOLD_ALGORITHM = "balanced-training-block-count-v1"
THREE_INNER_FOLD_COUNT = 3
_COLUMNS = ("source_record_id", "block_id")


@dataclass(frozen=True)
class InnerFoldGroup:
    """Original blocks assigned to one outcome-blind inner fold."""

    inner_block_id: str
    source_block_ids: tuple[str, ...]
    record_count: int


@dataclass(frozen=True)
class ThreeInnerFoldPlan:
    """Immutable grouping evidence for exactly three inner folds."""

    algorithm: str
    input_sha256: str
    groups: tuple[InnerFoldGroup, ...]
    grouping_sha256: str


def _require_assignments(assignments: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(assignments, pd.DataFrame):
        raise TypeError("assignments must be a pandas DataFrame")
    if assignments.columns.duplicated().any() or tuple(assignments.columns) != _COLUMNS:
        raise ValueError(f"assignments columns must be exactly {list(_COLUMNS)}")
    result = assignments.loc[:, _COLUMNS].copy(deep=True)
    for column in _COLUMNS:
        if not result[column].map(lambda value: isinstance(value, str) and bool(value.strip())).all():
            raise ValueError(f"assignments {column} values must be nonempty strings")
    if result["source_record_id"].duplicated().any():
        raise ValueError("assignments source_record_id values must be unique")
    return result.sort_values("source_record_id").reset_index(drop=True)


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(value, separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(payload).hexdigest()


def _input_sha256(assignments: pd.DataFrame) -> str:
    return _canonical_sha256(assignments.to_dict(orient="records"))


def _grouping_sha256(
    algorithm: str,
    input_sha256: str,
    groups: tuple[InnerFoldGroup, ...],
) -> str:
    return _canonical_sha256(
        {
            "algorithm": algorithm,
            "groups": [asdict(group) for group in groups],
            "input_sha256": input_sha256,
        }
    )


def plan_three_inner_folds(assignments: pd.DataFrame) -> ThreeInnerFoldPlan:
    """Balance complete original blocks into exactly three deterministic inner groups."""
    validated = _require_assignments(assignments)
    counts = validated.groupby("block_id", sort=True).size().to_dict()
    if len(counts) < THREE_INNER_FOLD_COUNT:
        raise ValueError("at least three distinct source blocks are required")

    grouped_blocks: list[list[str]] = [[] for _ in range(THREE_INNER_FOLD_COUNT)]
    group_sizes = [0] * THREE_INNER_FOLD_COUNT
    ordered = sorted(counts.items(), key=lambda item: (-int(item[1]), item[0]))
    for source_block_id, count in ordered:
        group_index = min(range(THREE_INNER_FOLD_COUNT), key=lambda index: (group_sizes[index], index))
        grouped_blocks[group_index].append(source_block_id)
        group_sizes[group_index] += int(count)

    groups = tuple(
        InnerFoldGroup(
            inner_block_id=f"inner-{index}",
            source_block_ids=tuple(sorted(grouped_blocks[index])),
            record_count=group_sizes[index],
        )
        for index in range(THREE_INNER_FOLD_COUNT)
    )
    input_hash = _input_sha256(validated)
    return ThreeInnerFoldPlan(
        algorithm=THREE_INNER_FOLD_ALGORITHM,
        input_sha256=input_hash,
        groups=groups,
        grouping_sha256=_grouping_sha256(THREE_INNER_FOLD_ALGORITHM, input_hash, groups),
    )


def apply_three_inner_folds(
    assignments: pd.DataFrame,
    plan: ThreeInnerFoldPlan,
) -> pd.DataFrame:
    """Apply a frozen grouping only to the exact source assignments that produced it."""
    if not isinstance(plan, ThreeInnerFoldPlan):
        raise TypeError("plan must be a ThreeInnerFoldPlan")
    validated = _require_assignments(assignments)
    if plan.algorithm != THREE_INNER_FOLD_ALGORITHM:
        raise ValueError("inner-fold grouping algorithm is unsupported")
    if len(plan.groups) != THREE_INNER_FOLD_COUNT:
        raise ValueError("inner-fold plan must contain exactly three groups")
    if plan.input_sha256 != _input_sha256(validated):
        raise ValueError("inner-fold plan does not match assignments")
    if plan.grouping_sha256 != _grouping_sha256(plan.algorithm, plan.input_sha256, plan.groups):
        raise ValueError("inner-fold grouping hash is invalid")

    source_to_inner: dict[str, str] = {}
    for index, group in enumerate(plan.groups):
        if group.inner_block_id != f"inner-{index}" or not group.source_block_ids:
            raise ValueError("inner-fold plan groups are malformed")
        for source_block_id in group.source_block_ids:
            if source_block_id in source_to_inner:
                raise ValueError("source block appears in more than one inner group")
            source_to_inner[source_block_id] = group.inner_block_id
    actual_blocks = set(validated["block_id"])
    if set(source_to_inner) != actual_blocks:
        raise ValueError("inner-fold plan does not cover every source block exactly once")

    result = validated.copy()
    result["block_id"] = result["block_id"].map(source_to_inner)
    actual_sizes = result["block_id"].value_counts().to_dict()
    if any(actual_sizes.get(group.inner_block_id) != group.record_count for group in plan.groups):
        raise ValueError("inner-fold group record counts contradict assignments")
    return result
