"""Outcome-blind nested-fold grouping contracts (global modeling plan; #374)."""

from __future__ import annotations

import pandas as pd
import pytest

from genomeos.validation.nested_folds import (
    THREE_INNER_FOLD_ALGORITHM,
    apply_three_inner_folds,
    plan_three_inner_folds,
)


def _assignments() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "source_record_id": ["a1", "a2", "a3", "a4", "b1", "b2", "b3", "c1", "c2", "d1"],
            "block_id": ["a", "a", "a", "a", "b", "b", "b", "c", "c", "d"],
        }
    )


def test_all_source_blocks_are_balanced_into_exactly_three_inner_folds():
    assignments = _assignments()

    plan = plan_three_inner_folds(assignments)
    grouped = apply_three_inner_folds(assignments, plan)

    assert plan.algorithm == THREE_INNER_FOLD_ALGORITHM
    assert [(group.inner_block_id, group.source_block_ids, group.record_count) for group in plan.groups] == [
        ("inner-0", ("a",), 4),
        ("inner-1", ("b",), 3),
        ("inner-2", ("c", "d"), 3),
    ]
    assert grouped["source_record_id"].tolist() == sorted(assignments["source_record_id"])
    assert grouped["block_id"].value_counts().sort_index().to_dict() == {
        "inner-0": 4,
        "inner-1": 3,
        "inner-2": 3,
    }


def test_grouping_is_deterministic_under_row_order_and_literal_ties():
    assignments = pd.DataFrame(
        {
            "source_record_id": ["d1", "c1", "b1", "a1"],
            "block_id": ["d", "c", "b", "a"],
        }
    )

    original = plan_three_inner_folds(assignments)
    reordered = plan_three_inner_folds(assignments.sample(frac=1.0, random_state=17))

    assert original == reordered
    assert [(group.inner_block_id, group.source_block_ids) for group in original.groups] == [
        ("inner-0", ("a", "d")),
        ("inner-1", ("b",)),
        ("inner-2", ("c",)),
    ]


@pytest.mark.parametrize(
    ("assignments", "match"),
    [
        (pd.DataFrame({"source_record_id": ["a"], "block_id": ["a"]}), "at least three"),
        (
            pd.DataFrame({"source_record_id": ["a", "a", "b"], "block_id": ["a", "b", "c"]}),
            "unique",
        ),
        (
            pd.DataFrame({"source_record_id": ["a", "b", "c"], "block_id": ["a", "", "c"]}),
            "nonempty",
        ),
    ],
)
def test_invalid_grouping_inputs_are_refused(assignments: pd.DataFrame, match: str):
    with pytest.raises(ValueError, match=match):
        plan_three_inner_folds(assignments)
