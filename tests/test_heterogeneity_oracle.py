"""Independent B0H quadrature-oracle tests (design §§5, 7–8, 12; #211)."""

from __future__ import annotations

import math

import numpy as np
import pytest

from genomeos.validation.heterogeneity_oracle import (
    heterogeneity_log_mass,
    heterogeneity_quadrature,
)


def test_log_mass_matches_literal_an2_heterogeneity_anchor() -> None:
    masses = [
        np.exp(
            heterogeneity_log_mass(
                ac,
                2,
                mean=np.array([0.25]),
                rho=np.array([0.2]),
            )
        )[0]
        for ac in range(3)
    ]
    np.testing.assert_allclose(masses, [0.6, 0.3, 0.1], rtol=0, atol=1e-14)


def test_log_mass_reduces_to_binomial_at_zero_rho() -> None:
    masses = [
        np.exp(
            heterogeneity_log_mass(
                ac,
                2,
                mean=np.array([0.25]),
                rho=np.array([0.0]),
            )
        )[0]
        for ac in range(3)
    ]
    np.testing.assert_allclose(masses, [0.5625, 0.375, 0.0625], rtol=0, atol=1e-14)


def test_log_mass_broadcasts_and_complete_support_is_normalized() -> None:
    mean = np.array([[0.1], [0.4]])
    rho = np.array([[0.0, 0.2, 0.8]])
    logs = [heterogeneity_log_mass(ac, 5, mean=mean, rho=rho) for ac in range(6)]

    assert all(value.shape == (2, 3) for value in logs)
    np.testing.assert_allclose(np.sum(np.exp(logs), axis=0), 1.0, rtol=0, atol=1e-14)


def test_log_mass_an0_returns_zeros_in_broadcast_shape() -> None:
    result = heterogeneity_log_mass(
        0,
        0,
        mean=np.array([[0.2], [0.8]]),
        rho=np.array([0.0, 0.3, 0.9]),
    )

    np.testing.assert_array_equal(result, np.zeros((2, 3)))


def test_log_mass_has_allele_complement_symmetry() -> None:
    mean = np.array([[0.12], [0.61]])
    rho = np.array([0.0, 0.17, 0.83])

    actual = heterogeneity_log_mass(2, 7, mean=mean, rho=rho)
    complemented = heterogeneity_log_mass(5, 7, mean=1.0 - mean, rho=rho)

    np.testing.assert_allclose(actual, complemented, rtol=0, atol=1e-14)


@pytest.mark.parametrize(
    ("ac", "an"),
    [
        (True, 1),
        (0, False),
        (0.0, 1),
        (0, 1.0),
        (-1, 1),
        (0, -1),
        (2, 1),
        (0, 65),
    ],
)
def test_log_mass_rejects_invalid_counts(ac: object, an: object) -> None:
    with pytest.raises(ValueError):
        heterogeneity_log_mass(ac, an, mean=np.array([0.5]), rho=np.array([0.1]))  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("mean", "rho"),
    [
        (np.array([]), np.array([0.1])),
        (np.array([0.5]), np.array([])),
        (np.array([True]), np.array([0.1])),
        (np.array([0.5]), np.array([False])),
        (np.array(["0.5"]), np.array([0.1])),
        (np.array([0.5], dtype=object), np.array([0.1])),
        (np.array([0.5 + 0j]), np.array([0.1])),
        (np.array([np.nan]), np.array([0.1])),
        (np.array([0.5]), np.array([np.inf])),
        (np.array([0.0]), np.array([0.1])),
        (np.array([1.0]), np.array([0.1])),
        (np.array([0.5]), np.array([-0.1])),
        (np.array([0.5]), np.array([1.0])),
        (np.ones((2, 2)) * 0.5, np.ones(3) * 0.1),
    ],
)
def test_log_mass_rejects_invalid_parameter_arrays(mean: np.ndarray, rho: np.ndarray) -> None:
    with pytest.raises(ValueError):
        heterogeneity_log_mass(0, 1, mean=mean, rho=rho)


@pytest.mark.parametrize(
    (
        "counts",
        "mean_prior",
        "rho_prior",
        "evidence",
        "moments",
        "predictive",
    ),
    [
        (
            (),
            (1, 1),
            (1, 9),
            1.0,
            (1 / 2, 1 / 3, 1 / 10, 1 / 55, 1 / 20),
            (7 / 20, 3 / 10, 7 / 20),
        ),
        (
            ((0, 1), (1, 1), (1, 1), (0, 1), (1, 1)),
            (1, 1),
            (1, 9),
            1 / 60,
            (4 / 7, 5 / 14, 1 / 10, 1 / 55, 2 / 35),
            (33 / 140, 27 / 70, 53 / 140),
        ),
        (
            ((1, 2), (1, 2), (1, 2), (1, 2)),
            (1, 1),
            (1, 9),
            8 / 455,
            (1 / 2, 3 / 11, 1 / 14, 1 / 105, 1 / 28),
            (89 / 308, 65 / 154, 89 / 308),
        ),
        (
            (),
            (2, 3),
            (2, 5),
            1.0,
            (2 / 5, 1 / 5, 2 / 7, 3 / 28, 4 / 35),
            (16 / 35, 2 / 7, 9 / 35),
        ),
    ],
)
def test_order32_quadrature_matches_exact_posterior_anchors(
    counts: tuple[tuple[int, int], ...],
    mean_prior: tuple[float, float],
    rho_prior: tuple[float, float],
    evidence: float,
    moments: tuple[float, float, float, float, float],
    predictive: tuple[float, float, float],
) -> None:
    result = heterogeneity_quadrature(
        counts,
        mean_prior=mean_prior,
        rho_prior=rho_prior,
        predictive_an=2,
        order=32,
    )

    assert result.order == 32
    assert result.predictive_an == 2
    assert result.log_evidence == pytest.approx(math.log(evidence), abs=1e-12)
    np.testing.assert_allclose(
        (result.mean, result.mean_squared, result.rho, result.rho_squared, result.mean_rho),
        moments,
        rtol=0,
        atol=1e-12,
    )
    np.testing.assert_allclose(result.predictive_masses, predictive, rtol=0, atol=1e-12)
    assert isinstance(result.predictive_masses, tuple)


def test_an0_training_rows_do_not_change_quadrature() -> None:
    kwargs = {
        "mean_prior": (1.0, 1.0),
        "rho_prior": (1.0, 9.0),
        "predictive_an": 2,
        "order": 32,
    }
    without = heterogeneity_quadrature([(0, 1), (1, 1)], **kwargs)
    with_unavailable = heterogeneity_quadrature([(0, 0), (0, 1), (0, 0), (1, 1)], **kwargs)

    assert with_unavailable == without


def test_quadrature_copies_inputs_without_mutating_them() -> None:
    counts = [[0, 1], [1, 1]]
    mean_prior = [2.0, 3.0]
    rho_prior = [2.0, 5.0]
    original = ([row.copy() for row in counts], mean_prior.copy(), rho_prior.copy())

    heterogeneity_quadrature(
        counts,  # type: ignore[arg-type]
        mean_prior=mean_prior,  # type: ignore[arg-type]
        rho_prior=rho_prior,  # type: ignore[arg-type]
        predictive_an=2,
        order=8,
    )

    assert (counts, mean_prior, rho_prior) == original


@pytest.mark.parametrize(
    "counts",
    [
        [None],
        [(0,)],
        [(0, 1, 2)],
        [(True, 1)],
        [(0, False)],
        [(0.0, 1)],
        [(0, 1.0)],
        [(-1, 1)],
        [(0, -1)],
        [(2, 1)],
        [(0, 65)],
    ],
)
def test_quadrature_rejects_malformed_or_invalid_counts(counts: object) -> None:
    with pytest.raises(ValueError):
        heterogeneity_quadrature(
            counts,  # type: ignore[arg-type]
            mean_prior=(1, 1),
            rho_prior=(1, 9),
            predictive_an=2,
            order=8,
        )


@pytest.mark.parametrize(
    ("mean_prior", "rho_prior"),
    [
        ((1,), (1, 9)),
        ((1, 1, 1), (1, 9)),
        ((1, 1), (1,)),
        ((True, 1), (1, 9)),
        ((1, 1), (1, False)),
        ((0, 1), (1, 9)),
        ((1, -1), (1, 9)),
        ((1, 1), (0, 9)),
        ((1, 1), (1, np.inf)),
        (("1", 1), (1, 9)),
        ((1 + 0j, 1), (1, 9)),
    ],
)
def test_quadrature_rejects_invalid_prior_shapes(
    mean_prior: object, rho_prior: object
) -> None:
    with pytest.raises(ValueError):
        heterogeneity_quadrature(
            (),
            mean_prior=mean_prior,  # type: ignore[arg-type]
            rho_prior=rho_prior,  # type: ignore[arg-type]
            predictive_an=2,
            order=8,
        )


@pytest.mark.parametrize(
    ("predictive_an", "order"),
    [
        (True, 8),
        (1.0, 8),
        (-1, 8),
        (65, 8),
        (2, True),
        (2, 2.0),
        (2, 1),
        (2, 513),
    ],
)
def test_quadrature_rejects_invalid_predictive_count_or_order(
    predictive_an: object, order: object
) -> None:
    with pytest.raises(ValueError):
        heterogeneity_quadrature(
            (),
            mean_prior=(1, 1),
            rho_prior=(1, 9),
            predictive_an=predictive_an,  # type: ignore[arg-type]
            order=order,  # type: ignore[arg-type]
        )
