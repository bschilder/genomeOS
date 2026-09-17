"""Production routing checks for direct count probabilities (design §§7–8; #341)."""

from __future__ import annotations

import numpy as np
import pytest

from genomeos.validation import count_probability_adapter as adapter
from genomeos.validation.count_scaled import ScaledPair


@pytest.mark.parametrize(
    ("bound", "expected"),
    [(1, 32), (20, 32), (32, 32), (33, 256), (256, 256), (257, 1024), (65_536, 1024)],
)
def test_support_chunk_uses_smallest_proved_width(bound: int, expected: int) -> None:
    assert adapter.support_chunk_for_bound(bound) == expected


@pytest.mark.parametrize("invalid", [True, 0, 65_537, 20.0])
def test_support_chunk_refuses_values_outside_proved_domain(invalid: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        adapter.support_chunk_for_bound(invalid)  # type: ignore[arg-type]


def test_queries_are_vectorized_into_one_core_call_with_short_support(monkeypatch) -> None:
    calls: list[tuple[tuple[int, ...], tuple[int, ...], int]] = []
    original = adapter._beta_binomial_probability_mean

    def observed(mean, concentration, an, ac, **kwargs):
        calls.append((mean.shape, ac.shape, kwargs["support_chunk_size"]))
        return original(mean, concentration, an, ac, **kwargs)

    monkeypatch.setattr(adapter, "_beta_binomial_probability_mean", observed)
    result = adapter.beta_binomial_probability_queries(
        np.full((3, 2), 0.5),
        np.full((3, 2), 2.0),
        np.asarray([4, 20], dtype=np.int64),
        np.asarray([[0, 1], [2, 10], [4, 20]], dtype=np.int64),
        array_module=np,
        max_count=20,
    )

    assert calls == [((3, 6), (6,), 32)]
    np.testing.assert_array_equal(
        adapter.probability_float64(result.mass, array_module=np),
        [[0.2, 1 / 21], [0.2, 1 / 21], [0.2, 1 / 21]],
    )
    np.testing.assert_array_equal(
        adapter.probability_float64(result.lower, array_module=np),
        [[0.2, 2 / 21], [0.6, 11 / 21], [1.0, 1.0]],
    )


def test_log_conversion_retains_probability_below_physical_float64_range() -> None:
    probability = ScaledPair(
        np.asarray([0.5]),
        np.asarray([0.0]),
        np.asarray([-1074], dtype=np.int64),
    )

    assert adapter.probability_float64(probability, array_module=np)[0] == 0.0
    assert adapter.probability_log(probability, array_module=np)[0] == pytest.approx(
        -1075 * np.log(2.0)
    )
