"""Reference-panel count baseline tests (design §§ 5, 7, 8; #189)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import numpy as np
import pytest
from scipy.stats import betabinom

from genomeos.validation.count_baseline import B0InfeasibleError
from genomeos.validation.reference_counts import (
    ReferenceCount,
    ReferenceFold,
    ReferenceInfeasibleError,
    fit_reference_b0,
    reference_group_folds,
    validate_reference_counts,
)


def row(
    group: str,
    ac: int = 1,
    an: int = 4,
    *,
    variant: str = "v",
    region: str = "r",
    variant_group: str = "block",
    suffix: str = "",
) -> ReferenceCount:
    return ReferenceCount(
        f"{group}:{variant}{suffix}",
        variant,
        group,
        region,
        variant_group,
        ac,
        an,
    )


def test_missing_denominator_is_retained_but_not_scored():
    missing = row("missing", 0, 0)

    assert validate_reference_counts([missing]) == (missing,)
    fit = fit_reference_b0([row("train")], [missing, row("test")], prior_alpha=1, prior_beta=1)

    assert fit.unavailable_ids == ("missing:v",)
    assert fit.observation_ids == ("test:v",)


def test_exact_marginal_matches_beta_binomial():
    fit = fit_reference_b0([row("train", 1, 4)], [row("test", 2, 5)], prior_alpha=1, prior_beta=1)

    np.testing.assert_allclose(
        fit.marginal_predictive.log_prob([2], [5]),
        [betabinom.logpmf(2, 5, 2, 4)],
    )
    np.testing.assert_allclose(
        fit.marginal_predictive.cdf([2], [5]),
        [betabinom.cdf(2, 5, 2, 4)],
    )
    np.testing.assert_array_equal(
        fit.marginal_predictive.quantiles([5], [0.25, 0.5, 0.75]),
        np.asarray([[betabinom.ppf(q, 5, 2, 4)] for q in (0.25, 0.5, 0.75)]),
    )


def test_fit_does_not_leak_test_counts_into_parameters():
    first = fit_reference_b0([row("train")], [row("test", 0, 4)], prior_alpha=1, prior_beta=1)
    changed = fit_reference_b0([row("train")], [row("test", 4, 4)], prior_alpha=1, prior_beta=1)

    assert first.posteriors == changed.posteriors
    np.testing.assert_array_equal(
        first.marginal_predictive.mean_draws,
        changed.marginal_predictive.mean_draws,
    )


def test_reference_outputs_are_immutable():
    count = row("a")
    fold = ReferenceFold("reference-0", ("b:v",), ("a:v",), ("a",))

    with pytest.raises(FrozenInstanceError):
        count.ac = 2
    with pytest.raises(FrozenInstanceError):
        fold.split_id = "changed"


@pytest.mark.parametrize("field", ["record_id", "variant_id", "group_id", "region_id", "variant_group"])
@pytest.mark.parametrize("invalid", ["", "  ", 1])
def test_reference_ids_must_be_literal_nonempty_strings(field, invalid):
    values = {
        "record_id": "a:v",
        "variant_id": "v",
        "group_id": "a",
        "region_id": "r",
        "variant_group": "block",
        "ac": 1,
        "an": 4,
    }
    values[field] = invalid

    with pytest.raises(ValueError):
        ReferenceCount(**values)


@pytest.mark.parametrize(
    ("ac", "an"),
    [(True, 4), (1, False), (1.0, 4), (1, 4.0), (-1, 4), (5, 4), (1, 0), (0, -1)],
)
def test_reference_counts_are_lossless_and_zero_an_requires_zero_ac(ac, an):
    with pytest.raises(ValueError):
        row("a", ac, an)


def test_numpy_integer_counts_normalize_to_python_ints():
    count = row("a", np.int64(0), np.uint64(0))

    assert count.ac == 0 and type(count.ac) is int
    assert count.an == 0 and type(count.an) is int


def test_table_validation_preserves_order_and_rejects_non_rows_or_empty():
    rows = (row("b"), row("a"))

    assert validate_reference_counts(rows) == rows
    with pytest.raises(ValueError):
        validate_reference_counts([])
    with pytest.raises(ValueError):
        validate_reference_counts([rows[0], "not-a-row"])


@pytest.mark.parametrize(
    "rows",
    [
        (
            row("a"),
            ReferenceCount("a:v", "v", "b", "r", "block", 1, 4),
        ),
        (row("a"), row("a", suffix=":again")),
        (row("a", region="r1"), row("a", variant="w", region="r2")),
        (row("a", variant="v", variant_group="x"), row("b", variant="v", variant_group="y")),
    ],
)
def test_table_rejects_duplicate_or_inconsistent_identifiers(rows):
    with pytest.raises(ValueError):
        validate_reference_counts(rows)


def _fold_rows() -> tuple[ReferenceCount, ...]:
    return tuple(row(group, index % 5, 4) for index, group in enumerate("abcdef"))


def _membership(folds):
    return tuple(sorted((fold.test_groups, fold.test_ids, fold.train_ids) for fold in folds))


def test_folds_keep_transitive_components_together_and_hold_out_every_row_once():
    rows = _fold_rows()
    folds = reference_group_folds(rows, dependency_edges=(("a", "b"), ("b", "c")), n_folds=3, seed=42)

    assert tuple(fold.split_id for fold in folds) == (
        "reference-0",
        "reference-1",
        "reference-2",
    )
    held_out = [record_id for fold in folds for record_id in fold.test_ids]
    assert sorted(held_out) == sorted(item.record_id for item in rows)
    assert len(held_out) == len(set(held_out))
    assert any(set(("a", "b", "c")) <= set(fold.test_groups) for fold in folds)
    for fold in folds:
        assert not set(fold.train_ids) & set(fold.test_ids)


def test_fold_membership_ignores_row_edge_order_and_counts():
    rows = _fold_rows()
    changed = tuple(
        ReferenceCount(r.record_id, r.variant_id, r.group_id, r.region_id, r.variant_group, 0, r.an)
        for r in reversed(rows)
    )
    first = reference_group_folds(rows, dependency_edges=(("a", "b"), ("b", "c")), n_folds=3, seed=7)
    second = reference_group_folds(changed, dependency_edges=(("c", "b"), ("b", "a")), n_folds=3, seed=7)

    assert _membership(first) == _membership(second)


@pytest.mark.parametrize(
    "edges",
    [(("a", "unknown"),), (("a", "a"),), (("a", "b"), ("b", "a")), (("a", "b", "c"),), ("ab",)],
)
def test_invalid_dependency_edges_are_refused(edges):
    with pytest.raises(ValueError):
        reference_group_folds(_fold_rows(), dependency_edges=edges, n_folds=3)


@pytest.mark.parametrize("n_folds", [True, 1, 2.5, 7])
def test_invalid_or_excessive_fold_counts_are_refused(n_folds):
    with pytest.raises(ValueError):
        reference_group_folds(_fold_rows(), dependency_edges=(("a", "b"), ("b", "c")), n_folds=n_folds)


@pytest.mark.parametrize("seed", [True, 1.5, -1])
def test_invalid_seeds_are_refused(seed):
    with pytest.raises(ValueError):
        reference_group_folds(_fold_rows(), dependency_edges=(), n_folds=3, seed=seed)


def test_nonnegative_python_integer_seed_has_no_undocumented_upper_bound():
    folds = reference_group_folds(_fold_rows(), dependency_edges=(), n_folds=3, seed=2**128)

    assert len(folds) == 3


def test_fit_requires_disjoint_records_and_groups():
    with pytest.raises(ValueError):
        fit_reference_b0([row("a")], [row("a")], prior_alpha=1, prior_beta=1)
    with pytest.raises(ValueError):
        fit_reference_b0([row("a")], [row("a", variant="w")], prior_alpha=1, prior_beta=1)


def test_fit_requires_nonempty_valid_tables():
    with pytest.raises(ValueError):
        fit_reference_b0([], [row("test")], prior_alpha=1, prior_beta=1)
    with pytest.raises(ValueError):
        fit_reference_b0([row("train")], [], prior_alpha=1, prior_beta=1)


def test_all_missing_testing_is_typed_infeasibility():
    with pytest.raises(ReferenceInfeasibleError):
        fit_reference_b0([row("train")], [row("test", 0, 0)], prior_alpha=1, prior_beta=1)


def test_absent_positive_training_variant_is_kernel_infeasibility():
    with pytest.raises(B0InfeasibleError) as caught:
        fit_reference_b0([row("train", 0, 0)], [row("test")], prior_alpha=1, prior_beta=1)

    assert caught.value.absent_variants == ("v",)


def test_test_labels_need_not_exist_in_training():
    fit = fit_reference_b0(
        [row("train", region="r1", variant_group="train-block")],
        [row("test", region="r2", variant_group="test-block")],
        prior_alpha=1,
        prior_beta=1,
    )

    assert fit.observation_ids == ("test:v",)


def test_rounded_boundary_marginal_is_refused_not_clipped():
    with pytest.raises(ValueError, match="stable numeric domain"):
        fit_reference_b0(
            [row("train", 10**16, 10**16)],
            [row("test")],
            prior_alpha=1,
            prior_beta=1,
        )
