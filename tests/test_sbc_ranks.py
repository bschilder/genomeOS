"""Discrete B0H rank/null tests (design §§ 5, 7–8, 12; #211)."""

from __future__ import annotations

import itertools
import math
from collections import Counter
from dataclasses import FrozenInstanceError

import numpy as np
import pytest

import genomeos.validation.sbc_ranks as sbc


@pytest.mark.parametrize(
    ("n", "expected"),
    [
        (1, {2: 1, 3: 2, 4: 2}),
        (2, {2: 2, 3: 6, 4: 9, 6: 6, 8: 2}),
    ],
)
def test_exact_small_n_null(n: int, expected: dict[int, int]) -> None:
    observed: Counter[int] = Counter()
    for ranks in itertools.product(range(5), repeat=n):
        counts = tuple(ranks.count(k) for k in range(5))
        observed[sbc.rank_ecdf_statistic(counts)] += 1
    assert dict(observed) == expected


def test_randomized_rank_has_exact_endpoints_and_partial_ties() -> None:
    assert sbc.randomized_rank(-1.0, (0.0, 1.0, 2.0, 3.0), seed=42) == 0
    assert sbc.randomized_rank(4.0, (0.0, 1.0, 2.0, 3.0), seed=42) == 4

    assert sbc.randomized_rank(2.0, (1.0, 2.0, 2.0, 2.0), seed=73) == 4


def test_randomized_rank_ties_are_literal_and_seeded() -> None:
    truth = 1.0
    just_above = math.nextafter(truth, math.inf)

    assert sbc.randomized_rank(truth, (truth, just_above, 2.0, 3.0), seed=0) == 1
    sequence = tuple(
        sbc.randomized_rank(truth, (truth,) * 4, seed=seed) for seed in range(12)
    )
    assert sequence == (4, 2, 4, 4, 3, 3, 2, 4, 3, 2, 3, 0)
    assert len(set(sequence)) > 1
    assert sequence == tuple(
        sbc.randomized_rank(truth, (truth,) * 4, seed=seed) for seed in range(12)
    )


@pytest.mark.parametrize("truth", [True, np.bool_(False), "1", np.nan, np.inf, -np.inf])
def test_randomized_rank_rejects_invalid_truth(truth: object) -> None:
    with pytest.raises(ValueError):
        sbc.randomized_rank(truth, (0.0, 1.0, 2.0, 3.0), seed=0)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "draws",
    [
        None,
        (),
        (0.0, 1.0, 2.0),
        (0.0, 1.0, 2.0, 3.0, 4.0),
        (0.0, 1.0, 2.0, True),
        (0.0, 1.0, 2.0, "3"),
        (0.0, 1.0, 2.0, np.nan),
        (0.0, 1.0, 2.0, np.inf),
        np.zeros((4, 1)),
    ],
)
def test_randomized_rank_rejects_invalid_draws(draws: object) -> None:
    with pytest.raises(ValueError):
        sbc.randomized_rank(0.0, draws, seed=0)  # type: ignore[arg-type]


@pytest.mark.parametrize("seed", [True, np.bool_(False), -1, 1.5, "1"])
def test_randomized_rank_rejects_invalid_seed(seed: object) -> None:
    with pytest.raises(ValueError):
        sbc.randomized_rank(0.0, (0.0,) * 4, seed=seed)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "counts",
    [
        None,
        (),
        (1, 1, 1, 1),
        (1, 1, 1, 1, 1, 1),
        (0, 0, 0, 0, 0),
        (1, 0, 0, 0, -1),
        (1, 0, 0, 0, True),
        (1, 0, 0, 0, 0.0),
        (1, 0, 0, 0, np.nan),
        np.ones((5, 1), dtype=np.int64),
    ],
)
def test_rank_ecdf_statistic_rejects_malformed_counts(counts: object) -> None:
    with pytest.raises(ValueError):
        sbc.rank_ecdf_statistic(counts)  # type: ignore[arg-type]


def test_rank_null_reference_validates_and_normalizes_immutable_statistics() -> None:
    statistics = [0, np.int64(4), 8]
    reference = sbc.RankNullReference(
        sample_size=np.int64(2), seed=np.int64(7), statistics=statistics
    )
    statistics[0] = 8

    assert reference == sbc.RankNullReference(sample_size=2, seed=7, statistics=(0, 4, 8))
    assert isinstance(reference.statistics, tuple)
    with pytest.raises(FrozenInstanceError):
        reference.seed = 8  # type: ignore[misc]


@pytest.mark.parametrize(
    ("sample_size", "seed", "statistics"),
    [
        (True, 0, (0,)),
        (0, 0, (0,)),
        (-1, 0, (0,)),
        (1.0, 0, (0,)),
        (1, True, (0,)),
        (1, -1, (0,)),
        (1, 1.0, (0,)),
        (1, 0, ()),
        (1, 0, (True,)),
        (1, 0, (-1,)),
        (1, 0, (5,)),
        (1, 0, (np.nan,)),
        (1, 0, np.ones((1, 1), dtype=np.int64)),
    ],
)
def test_rank_null_reference_rejects_invalid_values(
    sample_size: object, seed: object, statistics: object
) -> None:
    with pytest.raises(ValueError):
        sbc.RankNullReference(
            sample_size=sample_size,  # type: ignore[arg-type]
            seed=seed,  # type: ignore[arg-type]
            statistics=statistics,  # type: ignore[arg-type]
        )


def test_simulated_null_matches_literal_seeded_multinomial_fixture() -> None:
    result = sbc.simulate_rank_null(sample_size=3, replicates=6, seed=17)

    assert result == sbc.RankNullReference(
        sample_size=3,
        seed=17,
        statistics=(2, 6, 4, 9, 3, 9),
    )


@pytest.mark.parametrize(
    ("sample_size", "replicates", "seed"),
    [
        (True, 1, 0),
        (0, 1, 0),
        (1_000_001, 1, 0),
        (1.0, 1, 0),
        (1, True, 0),
        (1, 0, 0),
        (1, 1_000_001, 0),
        (1, 1.0, 0),
        (1, 1, True),
        (1, 1, -1),
        (1, 1, 0.0),
    ],
)
def test_simulated_null_rejects_invalid_or_oversized_arguments(
    sample_size: object, replicates: object, seed: object
) -> None:
    with pytest.raises(ValueError):
        sbc.simulate_rank_null(
            sample_size=sample_size,  # type: ignore[arg-type]
            replicates=replicates,  # type: ignore[arg-type]
            seed=seed,  # type: ignore[arg-type]
        )


def test_rank_uniformity_uses_inclusive_plus_one_p_value_and_bonferroni_cap() -> None:
    ranks = [0, 0]
    reference = sbc.RankNullReference(
        sample_size=2,
        seed=42,
        statistics=(7, 8, 8, 8),
    )
    original_ranks = ranks.copy()

    result = sbc.test_rank_uniformity(ranks, reference=reference)

    assert ranks == original_ranks
    assert result == sbc.RankTestResult(
        counts=(2, 0, 0, 0, 0),
        statistic=8,
        p_value=0.8,
        bonferroni_p_value=1.0,
    )
    with pytest.raises(FrozenInstanceError):
        result.statistic = 0  # type: ignore[misc]


def test_rank_uniformity_has_minimum_plus_one_p_value() -> None:
    reference = sbc.RankNullReference(sample_size=2, seed=9, statistics=(2, 4, 6, 6))

    result = sbc.test_rank_uniformity((0, 0), reference=reference)

    assert result.p_value == 0.2
    assert result.bonferroni_p_value == 1.0


@pytest.mark.parametrize(
    "ranks",
    [
        None,
        (),
        (0,),
        (0, 1, 2),
        (0, True),
        (0, -1),
        (0, 5),
        (0, 1.0),
        (0, np.nan),
        np.zeros((2, 1), dtype=np.int64),
    ],
)
def test_rank_uniformity_rejects_malformed_or_wrong_n_ranks(ranks: object) -> None:
    reference = sbc.RankNullReference(sample_size=2, seed=42, statistics=(2, 4))
    with pytest.raises(ValueError):
        sbc.test_rank_uniformity(ranks, reference=reference)  # type: ignore[arg-type]


def test_rank_uniformity_refuses_wrong_or_corrupt_reference() -> None:
    with pytest.raises(ValueError):
        sbc.test_rank_uniformity((0,), reference=object())  # type: ignore[arg-type]

    corrupt = object.__new__(sbc.RankNullReference)
    object.__setattr__(corrupt, "sample_size", 1)
    object.__setattr__(corrupt, "seed", 0)
    object.__setattr__(corrupt, "statistics", (math.nan,))
    with pytest.raises(ValueError):
        sbc.test_rank_uniformity((0,), reference=corrupt)


def test_rank_uniformity_is_not_a_pytest_test() -> None:
    assert sbc.test_rank_uniformity.__test__ is False
