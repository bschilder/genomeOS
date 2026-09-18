"""Standalone direct count-probability checks (design §7, §8)."""

from __future__ import annotations

import numpy as np

from genomeos.validation import count_probability as cp
from genomeos.validation import count_scaled as cs


def floats(value):
    return cs.to_float64(value, array_module=np)


def assert_probabilities(actual, mass, lower, upper):
    np.testing.assert_array_equal(floats(actual.mass), mass)
    np.testing.assert_array_equal(floats(actual.lower), lower)
    np.testing.assert_array_equal(floats(actual.upper), upper)


def test_public_partition_signature_uses_fixed_chunk_and_preserves_inputs(monkeypatch):
    calls = []
    original = cp._beta_binomial_probability_partitions

    def observed(*args, **kwargs):
        calls.append(kwargs["support_chunk_size"])
        return original(*args, **kwargs)

    monkeypatch.setattr(cp, "_beta_binomial_probability_partitions", observed)
    inputs = [
        np.asarray([0.25, 0.75]),
        np.asarray([3.0, 4.0]),
        np.asarray([5, 6], dtype=np.int64),
        np.asarray([2, 3], dtype=np.int64),
    ]
    saved = [value.copy() for value in inputs]
    parts = cp.beta_binomial_probability_partitions(*inputs, array_module=np, max_count=6)
    assert calls == [1024]
    assert parts.below.hi.shape == (2,)
    for value, before in zip(inputs, saved, strict=True):
        np.testing.assert_array_equal(value, before)


def test_raw_normalizer_has_no_analytical_provenance():
    one = cs.from_int64(np.asarray(1, dtype=np.int64), array_module=np)
    parts = cp.ProbabilityPartitions(one, one, one)
    normalized = cp.normalize_partitions(parts, array_module=np)
    for value in (normalized.mass, normalized.lower, normalized.upper):
        assert 0.0 < float(floats(value)) < 1.0
    assert float(floats(normalized.mass)) == float(floats(normalized.upper))


def test_uniform_adapter_preserves_exact_cardinality_probabilities():
    counts = np.arange(-1, 5, dtype=np.int64)
    result = cp.beta_binomial_probabilities(
        np.asarray(0.5),
        np.asarray(2.0),
        np.asarray(4, dtype=np.int64),
        counts,
        array_module=np,
        max_count=4,
    )
    np.testing.assert_array_equal(floats(result.mass), [0.0, *([0.2] * 5)])
    np.testing.assert_array_equal(floats(result.lower), [0.0, 0.2, 0.4, 0.6, 0.8, 1.0])
    np.testing.assert_array_equal(floats(result.upper), [1.0, 0.8, 0.6, 0.4, 0.2, 0.0])


def test_bernoulli_and_degenerate_input_identities():
    p = np.asarray([np.nextafter(1.0, 0.0), 0.0, 1.0])
    result = cp.beta_binomial_probabilities(
        p,
        np.asarray([1e300, 2.0, 2.0]),
        np.asarray([1, 7, 7], dtype=np.int64),
        np.asarray([0, 0, 7], dtype=np.int64),
        array_module=np,
        max_count=7,
    )
    assert_probabilities(result, [1.0 - p[0], 1.0, 1.0], [1.0 - p[0], 1.0, 1.0], [p[0], 0.0, 0.0])


def test_smallest_positive_bernoulli_avoids_mode_underflow():
    p = np.asarray(np.nextafter(0.0, 1.0))
    with np.errstate(all="raise"):
        result = cp.beta_binomial_probabilities(
            p,
            np.asarray(1e300),
            np.asarray(1, dtype=np.int64),
            np.asarray(1, dtype=np.int64),
            array_module=np,
            max_count=1,
        )
    assert float(floats(result.mass)) == float(p)
    assert float(floats(result.lower)) == 1.0
    assert float(floats(result.upper)) == 0.0


def test_analytical_adapter_batches_only_genuinely_generic_lanes(monkeypatch):
    calls = []
    original = cp._beta_binomial_probability_partitions

    def observed(*args, **kwargs):
        calls.append(args[0].shape)
        return original(*args, **kwargs)

    monkeypatch.setattr(cp, "_beta_binomial_probability_partitions", observed)
    result = cp.beta_binomial_probabilities(
        np.asarray([0.0, 1.0, 0.5, 0.4, 0.5]),
        np.asarray([3.0, 3.0, 2.0, 3.0, 3.0]),
        np.asarray([5, 5, 5, 5, 5], dtype=np.int64),
        np.asarray([0, 5, 2, -1, 2], dtype=np.int64),
        array_module=np,
        max_count=5,
    )
    assert calls == [(1,)]
    assert float(floats(result.lower)[4]) == 0.5


def test_support_boundaries_and_central_symmetry_are_exact():
    p = np.asarray([0.3, 0.3, 0.5])
    result = cp.beta_binomial_probabilities(
        p,
        np.asarray([4.0, 4.0, 4.0]),
        np.asarray([5, 5, 5], dtype=np.int64),
        np.asarray([-1, 5, 2], dtype=np.int64),
        array_module=np,
        max_count=5,
    )
    assert float(floats(result.mass)[0]) == 0.0
    assert float(floats(result.lower)[0]) == 0.0
    assert float(floats(result.upper)[0]) == 1.0
    assert float(floats(result.lower)[1]) == 1.0
    assert float(floats(result.upper)[1]) == 0.0
    assert float(floats(result.lower)[2]) == 0.5
    assert float(floats(result.upper)[2]) == 0.5


def test_internal_legal_chunk_sizes_agree_with_public_default():
    args = (
        np.asarray([0.05, 0.5, 0.95]),
        np.asarray([2.0, 3.0, 134217728.0]),
        np.asarray([40, 40, 40], dtype=np.int64),
        np.asarray([0, 20, 40], dtype=np.int64),
    )
    public = cp.beta_binomial_probabilities(*args, array_module=np, max_count=40)
    for chunk in (32, 256):
        alternate = cp._beta_binomial_probabilities(
            *args, array_module=np, max_count=40, support_chunk_size=chunk
        )
        for expected, actual in zip(
            (public.mass, public.lower, public.upper),
            (alternate.mass, alternate.lower, alternate.upper),
            strict=True,
        ):
            np.testing.assert_allclose(floats(actual), floats(expected), rtol=1e-14, atol=0.0)


def test_generic_batch_preserves_all_lanes_across_storage_boundary():
    lanes = 300
    targets = np.arange(lanes, dtype=np.int64) % 3
    result = cp.beta_binomial_probabilities(
        np.full(lanes, 0.5),
        np.full(lanes, 3.0),
        np.full(lanes, 2, dtype=np.int64),
        targets,
        array_module=np,
        max_count=2,
    )
    # Beta-binomial(n=2, alpha=beta=3/2) has exact law 5/16, 6/16, 5/16.
    np.testing.assert_array_equal(
        floats(result.mass), np.asarray([0.3125, 0.375, 0.3125])[targets]
    )
    np.testing.assert_array_equal(
        floats(result.lower), np.asarray([0.3125, 0.6875, 1.0])[targets]
    )
    np.testing.assert_array_equal(
        floats(result.upper), np.asarray([0.6875, 0.3125, 0.0])[targets]
    )


def test_probability_mean_streams_draw_and_row_boundaries_with_identities():
    draws, observations = 129, 5
    means = np.full((draws, observations), 0.5)
    concentrations = np.full_like(means, 2.0)
    denominators = np.asarray([1, 4, 5, 7, 8], dtype=np.int64)
    counts = np.asarray([0, 1, 2, 3, 3], dtype=np.int64)
    result = cp.beta_binomial_probability_mean(
        means,
        concentrations,
        denominators,
        counts,
        array_module=np,
        max_count=8,
    )
    np.testing.assert_array_equal(floats(result.mass), 1.0 / (denominators + 1))
    np.testing.assert_array_equal(floats(result.lower), (counts + 1.0) / (denominators + 1.0))
    np.testing.assert_array_equal(floats(result.upper), (denominators - counts) / (denominators + 1.0))


def test_probability_mean_single_draw_returns_component_expansion_unchanged():
    means = np.asarray([[0.25, 0.75]])
    concentrations = np.asarray([[3.0, 4.0]])
    denominators = np.asarray([4, 5], dtype=np.int64)
    counts = np.asarray([1, 3], dtype=np.int64)
    expected = cp.beta_binomial_probabilities(
        means[0], concentrations[0], denominators, counts, array_module=np, max_count=5
    )
    actual = cp.beta_binomial_probability_mean(
        means, concentrations, denominators, counts, array_module=np, max_count=5
    )
    for left, right in zip(
        (expected.mass, expected.lower, expected.upper),
        (actual.mass, actual.lower, actual.upper),
        strict=True,
    ):
        np.testing.assert_array_equal(right.hi, left.hi)
        np.testing.assert_array_equal(right.lo, left.lo)
        np.testing.assert_array_equal(right.exponent, left.exponent)


def test_internal_chunk_size_and_mean_shapes_fail_closed():
    scalar = (np.asarray(0.5), np.asarray(3.0), np.asarray(4, dtype=np.int64), np.asarray(2, dtype=np.int64))
    for chunk in (0, 31, 64, 1025):
        try:
            cp._beta_binomial_probability_partitions(
                *scalar, array_module=np, max_count=4, support_chunk_size=chunk
            )
        except ValueError:
            pass
        else:
            raise AssertionError("illegal support chunk was accepted")
    try:
        cp.beta_binomial_probability_mean(
            np.asarray([0.5]),
            np.asarray([3.0]),
            np.asarray([4], dtype=np.int64),
            np.asarray([2], dtype=np.int64),
            array_module=np,
            max_count=4,
        )
    except ValueError:
        pass
    else:
        raise AssertionError("one-dimensional draw input was accepted")
