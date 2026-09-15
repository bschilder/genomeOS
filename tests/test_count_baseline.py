"""Pure pooled allele-count posterior tests (design §§ 5, 7, 8; #189)."""

from __future__ import annotations

import sys

import numpy as np
import pytest

from genomeos.validation.count_baseline import (
    B0InfeasibleError,
    B0VariantPosterior,
    PooledAlleleCount,
    pooled_beta_posteriors,
)


def test_posterior_pools_only_matching_variant():
    rows = [
        PooledAlleleCount("a", "v", 1, 4),
        PooledAlleleCount("b", "v", 3, 6),
        PooledAlleleCount("c", "w", 9, 10),
    ]

    result = pooled_beta_posteriors(rows, ["v"], prior_alpha=1, prior_beta=1)

    assert result == (B0VariantPosterior("v", 2, 4, 10, 5.0, 7.0),)


@pytest.mark.parametrize("ac,an", [(True, 4), (1.5, 4), (-1, 4), (5, 4), (0, 0)])
def test_invalid_counts_are_not_coerced(ac, an):
    with pytest.raises(ValueError):
        PooledAlleleCount("a", "v", ac, an)


@pytest.mark.parametrize(
    ("record_id", "variant_id"),
    [("", "v"), ("  ", "v"), (1, "v"), ("a", ""), ("a", "\t"), ("a", 1)],
)
def test_ids_must_be_nonempty_literal_strings(record_id, variant_id):
    with pytest.raises(ValueError):
        PooledAlleleCount(record_id, variant_id, 1, 4)


def test_numpy_integer_counts_normalize_losslessly():
    row = PooledAlleleCount("a", "v", np.int64(1), np.uint64(4))

    assert row.ac == 1 and type(row.ac) is int
    assert row.an == 4 and type(row.an) is int


def test_python_integer_sums_do_not_wrap_at_int64():
    rows = (
        PooledAlleleCount("a", "v", sys.maxsize, sys.maxsize),
        PooledAlleleCount("b", "v", 1, 1),
    )

    result = pooled_beta_posteriors(rows, ("v",), prior_alpha=1, prior_beta=1)

    assert result[0].training_ac == sys.maxsize + 1
    assert result[0].training_an == sys.maxsize + 1


@pytest.mark.parametrize(
    "rows",
    [
        [PooledAlleleCount("a", "v", 1, 2), PooledAlleleCount("a", "w", 1, 2)],
        [PooledAlleleCount("a", "v", 1, 2), "not-a-count"],
    ],
)
def test_training_rows_must_be_typed_with_unique_record_ids(rows):
    with pytest.raises(ValueError):
        pooled_beta_posteriors(rows, ("v",), prior_alpha=1, prior_beta=1)


@pytest.mark.parametrize("variants", [(), ("v", "v"), ("",), ("  ",), (1,)])
def test_requested_variants_must_be_nonempty_unique_literal_ids(variants):
    with pytest.raises(ValueError):
        pooled_beta_posteriors(
            (PooledAlleleCount("a", "v", 1, 2),),
            variants,
            prior_alpha=1,
            prior_beta=1,
        )


def test_absent_requested_variants_are_typed_infeasibility():
    with pytest.raises(B0InfeasibleError) as caught:
        pooled_beta_posteriors(
            (PooledAlleleCount("a", "v", 1, 2),),
            ("w", "v"),
            prior_alpha=1,
            prior_beta=1,
        )

    assert caught.value.absent_variants == ("w",)


@pytest.mark.parametrize("prior", [True, np.bool_(False), 0, -1, np.nan, np.inf, "1"])
@pytest.mark.parametrize("name", ["prior_alpha", "prior_beta"])
def test_priors_must_be_positive_finite_reals(prior, name):
    kwargs = {"prior_alpha": 1, "prior_beta": 1, name: prior}
    with pytest.raises(ValueError):
        pooled_beta_posteriors(
            (PooledAlleleCount("a", "v", 1, 2),), ("v",), **kwargs
        )


def test_unstable_posterior_shape_is_refused():
    enormous = 10**400

    with pytest.raises(ValueError, match="stable numeric domain"):
        pooled_beta_posteriors(
            (PooledAlleleCount("a", "v", enormous, enormous),),
            ("v",),
            prior_alpha=1,
            prior_beta=1,
        )


def test_output_is_sorted_independently_of_request_order():
    rows = (
        PooledAlleleCount("a", "v", 1, 2),
        PooledAlleleCount("b", "w", 2, 4),
    )

    result = pooled_beta_posteriors(rows, ("w", "v"), prior_alpha=1, prior_beta=1)

    assert tuple(item.variant_id for item in result) == ("v", "w")
