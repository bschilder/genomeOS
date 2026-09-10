"""Independent B0H dependence-reference tests (design §§5, 7–8, 12; #211)."""

from __future__ import annotations

import math
from dataclasses import FrozenInstanceError, replace
from fractions import Fraction

import numpy as np
import pytest

import genomeos.validation.heterogeneity_dependence as dependence
import genomeos.validation.heterogeneity_oracle as oracle
from genomeos.validation.heterogeneity_dependence import (
    DependencePointReference,
    HeterogeneityDependenceReference,
    dependence_comparisons,
    heterogeneity_dependence_reference,
)
from genomeos.validation.heterogeneity_oracle import beta_prior_quadrature


@pytest.mark.parametrize("order", [2, 32])
@pytest.mark.parametrize("prior", [(1.0, 1.0), (2.0, 3.0), (3.0, 2.0)])
def test_public_beta_nodes_integrate_exact_moments(
    prior: tuple[float, float], order: int
) -> None:
    nodes, weights = beta_prior_quadrature(prior, order=order)
    alpha, beta = prior

    assert nodes.shape == weights.shape == (order,)
    assert float(np.sum(weights)) == pytest.approx(1.0, abs=1e-13)
    assert float(np.sum(weights * nodes)) == pytest.approx(
        alpha / (alpha + beta), abs=1e-13
    )
    assert float(np.sum(weights * nodes * nodes)) == pytest.approx(
        alpha * (alpha + 1) / ((alpha + beta) * (alpha + beta + 1)),
        abs=1e-13,
    )


@pytest.mark.parametrize("order", [True, np.bool_(False), 2.0, 1, 513])
def test_public_beta_nodes_reject_invalid_order(order: object) -> None:
    with pytest.raises(ValueError):
        beta_prior_quadrature((1.0, 1.0), order=order)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "prior",
    [
        None,
        (),
        (1.0,),
        (1.0, 1.0, 1.0),
        (True, 1.0),
        (1.0, False),
        (0.0, 1.0),
        (-1.0, 1.0),
        (1.0, 0.0),
        (1.0, np.nan),
        (np.inf, 1.0),
        ("1", 1.0),
        (1.0 + 0j, 1.0),
    ],
)
def test_public_beta_nodes_reject_invalid_prior(prior: object) -> None:
    with pytest.raises(ValueError):
        beta_prior_quadrature(prior, order=2)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("raw_nodes", "raw_weights"),
    [
        (np.array([0.0]), np.array([1.0, 1.0])),
        (np.array([0.0, np.nan]), np.array([1.0, 1.0])),
        (np.array([-1.0, 0.0]), np.array([1.0, 1.0])),
        (np.array([0.0, 0.0]), np.array([1.0, 1.0])),
        (np.array([-0.5, 0.5]), np.array([0.0, 1.0])),
        (np.array([-0.5, 0.5]), np.array([-1.0, 1.0])),
        (np.array([-0.5, 0.5]), np.array([np.nan, 1.0])),
    ],
)
def test_public_beta_nodes_refuse_degenerated_numerics(
    monkeypatch: pytest.MonkeyPatch,
    raw_nodes: np.ndarray,
    raw_weights: np.ndarray,
) -> None:
    monkeypatch.setattr(oracle, "roots_jacobi", lambda *args: (raw_nodes, raw_weights))

    with pytest.raises(ArithmeticError):
        beta_prior_quadrature((1.0, 1.0), order=2)


@pytest.mark.parametrize(
    ("mean_prior", "rho_prior", "z", "ratios", "fixed_mean", "fixed_rho"),
    [
        (
            (1.0, 1.0),
            (1.0, 1.0),
            5 / 12,
            (65 / 63, 13 / 11, 75 / 77),
            (21 / 32, 5 / 32, 21 / 32),
            (3 / 8, 11 / 24, 11 / 24),
        ),
        (
            (2.0, 3.0),
            (3.0, 2.0),
            13 / 25,
            (169 / 162, 169 / 154, 65 / 66),
            (27 / 40, 7 / 40, 27 / 40),
            (9 / 20, 11 / 20, 11 / 20),
        ),
    ],
)
def test_nonseparable_reference_has_independent_rational_anchors(
    mean_prior: tuple[float, float],
    rho_prior: tuple[float, float],
    z: float,
    ratios: tuple[float, float, float],
    fixed_mean: tuple[float, float, float],
    fixed_rho: tuple[float, float, float],
) -> None:
    likelihoods = (39 / 64, 13 / 64, 45 / 64)
    result = heterogeneity_dependence_reference(
        ((0, 2),),
        mean_prior=mean_prior,
        rho_prior=rho_prior,
        points=((0.25, 0.25), (0.75, 0.75), (0.25, 0.75)),
    )

    assert not result.analytic_separability
    assert result.orders == (64, 128, 256)
    for index, (point, ratio) in enumerate(zip(result.points, ratios, strict=True)):
        assert point.resolved
        assert point.value == pytest.approx(math.log(ratio), abs=1e-11)
        assert len(point.components) == len(point.raw_values) == 3
        for components in point.components:
            assert components[0] == pytest.approx(math.log(likelihoods[index]), abs=1e-11)
            assert components[1] == pytest.approx(math.log(z), abs=1e-11)
            assert components[2] == pytest.approx(math.log(fixed_mean[index]), abs=1e-11)
            assert components[3] == pytest.approx(math.log(fixed_rho[index]), abs=1e-11)
        expected_guard = max(
            abs(point.raw_values[1] - point.raw_values[0]),
            abs(point.raw_values[2] - point.raw_values[1]),
            64
            * np.finfo(np.float64).eps
            * max(1 + sum(abs(term) for term in row) for row in point.components),
        )
        assert point.error_bound == expected_guard


@pytest.mark.parametrize(
    "counts",
    [
        (),
        ((0, 0), (0, 0)),
        ((0, 1), (1, 1), (0, 1)),
        ((1, 2), (1, 2), (0, 0), (1, 2)),
    ],
)
@pytest.mark.parametrize("mean_prior,rho_prior", [((1.0, 1.0), (1.0, 9.0)), ((2.0, 3.0), (3.0, 2.0))])
def test_closed_separability_cases_return_literal_zero_and_raw_evidence(
    counts: tuple[tuple[int, int], ...],
    mean_prior: tuple[float, float],
    rho_prior: tuple[float, float],
) -> None:
    result = heterogeneity_dependence_reference(
        counts,
        mean_prior=mean_prior,
        rho_prior=rho_prior,
        points=((0.21, 0.13), (0.79, 0.87)),
    )

    assert result.analytic_separability
    for point in result.points:
        assert point.value == 0.0
        assert point.resolved
        assert all(abs(value) <= 1e-6 for value in point.raw_values)


def test_an0_insertion_does_not_change_nonseparable_reference() -> None:
    kwargs = {
        "mean_prior": (2.0, 3.0),
        "rho_prior": (3.0, 2.0),
        "points": ((0.25, 0.25), (0.75, 0.75)),
    }

    without = heterogeneity_dependence_reference(((0, 2),), **kwargs)
    with_unavailable = heterogeneity_dependence_reference(
        ((0, 0), (0, 2), (0, 0)), **kwargs
    )

    assert with_unavailable == without


def test_reference_has_allele_complement_symmetry() -> None:
    original = heterogeneity_dependence_reference(
        ((0, 2), (1, 3)),
        mean_prior=(2.0, 3.0),
        rho_prior=(3.0, 2.0),
        points=((0.23, 0.17), (0.68, 0.71)),
    )
    complemented = heterogeneity_dependence_reference(
        ((2, 2), (2, 3)),
        mean_prior=(3.0, 2.0),
        rho_prior=(3.0, 2.0),
        points=((0.77, 0.17), (0.32, 0.71)),
    )

    assert original.analytic_separability == complemented.analytic_separability
    for left, right in zip(original.points, complemented.points, strict=True):
        np.testing.assert_allclose(left.components, right.components, rtol=0, atol=1e-11)
        np.testing.assert_allclose(left.raw_values, right.raw_values, rtol=0, atol=1e-11)
        assert left.value == pytest.approx(right.value, abs=1e-11)
        assert left.resolved == right.resolved


def test_reference_preserves_point_order_repeats_and_inputs() -> None:
    counts = [[0, 2]]
    mean_prior = [2.0, 3.0]
    rho_prior = [3.0, 2.0]
    points = [[0.75, 0.75], [0.25, 0.25], [0.75, 0.75]]
    original = (
        [row.copy() for row in counts],
        mean_prior.copy(),
        rho_prior.copy(),
        [point.copy() for point in points],
    )

    result = heterogeneity_dependence_reference(
        counts,  # type: ignore[arg-type]
        mean_prior=mean_prior,  # type: ignore[arg-type]
        rho_prior=rho_prior,  # type: ignore[arg-type]
        points=points,  # type: ignore[arg-type]
    )

    assert tuple((point.mean, point.rho) for point in result.points) == (
        (0.75, 0.75),
        (0.25, 0.25),
        (0.75, 0.75),
    )
    assert result.points[0] == result.points[2]
    assert (counts, mean_prior, rho_prior, points) == original
    assert isinstance(result.points, tuple)
    assert all(isinstance(point.components, tuple) for point in result.points)
    with pytest.raises(FrozenInstanceError):
        result.points[0].value = 1.0  # type: ignore[misc]


@pytest.mark.parametrize(
    "points",
    [
        None,
        (),
        (None,),
        ((0.5,),),
        ((0.5, 0.5, 0.5),),
        ((True, 0.5),),
        ((0.5, False),),
        ((0.5 + 0j, 0.5),),
        (("0.5", 0.5),),
        ((np.nan, 0.5),),
        ((0.5, np.inf),),
        ((0.0, 0.5),),
        ((1.0, 0.5),),
        ((0.5, 0.0),),
        ((0.5, 1.0),),
    ],
)
def test_reference_rejects_malformed_or_invalid_points(points: object) -> None:
    with pytest.raises(ValueError):
        heterogeneity_dependence_reference(
            ((0, 2),),
            mean_prior=(1.0, 1.0),
            rho_prior=(1.0, 1.0),
            points=points,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    "point",
    [
        (Fraction(1, 4) + Fraction(1, 2**60), 0.25),
        (0.25, Fraction(1, 4) + Fraction(1, 2**60)),
        (np.longdouble("0.25"), 0.25),
        (0.25, np.longdouble("0.25")),
    ],
)
def test_reference_rejects_lossy_or_extended_precision_point_scalars(
    point: tuple[object, object],
) -> None:
    with pytest.raises(ValueError):
        heterogeneity_dependence_reference(
            ((0, 2),),
            mean_prior=(1.0, 1.0),
            rho_prior=(1.0, 1.0),
            points=(point,),  # type: ignore[arg-type]
        )


def test_reference_rejects_float_subclasses_without_conversion() -> None:
    class MisleadingFloat(float):
        def __float__(self) -> float:
            return 0.25

    with pytest.raises(ValueError):
        heterogeneity_dependence_reference(
            ((0, 2),),
            mean_prior=(1.0, 1.0),
            rho_prior=(1.0, 1.0),
            points=((MisleadingFloat(0.75), 0.25),),
        )


def test_reference_validates_counts_even_on_separable_path() -> None:
    with pytest.raises(ValueError):
        heterogeneity_dependence_reference(
            ((0, 1), (True, 0)),  # type: ignore[arg-type]
            mean_prior=(1.0, 1.0),
            rho_prior=(1.0, 1.0),
            points=((0.5, 0.5),),
        )


def test_reference_refuses_nonfinite_arithmetic(monkeypatch: pytest.MonkeyPatch) -> None:
    def nonfinite_log_mass(
        ac: int, an: int, *, mean: np.ndarray, rho: np.ndarray
    ) -> np.ndarray:
        return np.broadcast_arrays(mean, rho)[0] * np.nan

    monkeypatch.setattr(dependence, "heterogeneity_log_mass", nonfinite_log_mass)

    with pytest.raises(ArithmeticError):
        heterogeneity_dependence_reference(
            ((0, 2),),
            mean_prior=(1.0, 1.0),
            rho_prior=(1.0, 1.0),
            points=((0.5, 0.5),),
        )


def test_reference_retains_all_finite_evidence_when_order_gaps_do_not_resolve(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_quadrature = dependence.heterogeneity_quadrature

    def shifted_quadrature(*args: object, **kwargs: object) -> oracle.HeterogeneityQuadrature:
        result = original_quadrature(*args, **kwargs)  # type: ignore[arg-type]
        shift = {64: 0.0, 128: 2e-6, 256: 4e-6}[result.order]
        return replace(result, log_evidence=result.log_evidence + shift)

    monkeypatch.setattr(dependence, "heterogeneity_quadrature", shifted_quadrature)

    result = heterogeneity_dependence_reference(
        ((0, 2),),
        mean_prior=(1.0, 1.0),
        rho_prior=(1.0, 1.0),
        points=((0.25, 0.25),),
    )

    point = result.points[0]
    assert not point.resolved
    assert point.value == point.raw_values[-1]
    assert len(point.components) == len(point.raw_values) == 3
    assert abs((-1.0 + 2e-6) - -1.0) < 2e-6
    adjacent_gaps = tuple(
        abs(right - left)
        for left, right in zip(point.raw_values[:-1], point.raw_values[1:], strict=True)
    )
    rounding_floor = (
        64
        * np.finfo(np.float64).eps
        * max(1 + sum(abs(term) for term in row) for row in point.components)
    )
    assert point.error_bound == max(*adjacent_gaps, rounding_floor)
    assert point.error_bound > 1e-6


def _anchored_comparison_reference() -> HeterogeneityDependenceReference:
    return heterogeneity_dependence_reference(
        ((0, 2),),
        mean_prior=(1.0, 1.0),
        rho_prior=(1.0, 1.0),
        points=(
            (0.25, 0.25),
            (0.75, 0.75),
            (0.25, 0.75),
            (0.25, 0.25),
            (0.75, 0.75),
        ),
    )


def _raw_comparisons(
    reference: HeterogeneityDependenceReference,
    truth_index: int,
    draw_indices: tuple[int, int, int, int],
) -> tuple[tuple[int, ...], ...]:
    truth = reference.points[truth_index]
    return tuple(
        tuple(
            (reference.points[draw_index].raw_values[order_index] > truth.raw_values[order_index])
            - (reference.points[draw_index].raw_values[order_index] < truth.raw_values[order_index])
            for draw_index in draw_indices
        )
        for order_index in range(3)
    )


def test_comparisons_resolve_mixed_signs_and_identical_repeat() -> None:
    reference = _anchored_comparison_reference()
    draws = (1, 2, 3, 4)

    result = dependence_comparisons(reference, truth_index=0, draw_indices=draws)

    assert result.status == "resolved"
    assert result.comparisons == (1, -1, 0, 1)
    assert tuple(len(order) for order in result.comparisons_by_order) == (4, 4, 4)
    assert result.comparisons_by_order == _raw_comparisons(reference, 0, draws)


def test_supported_binary_float_representations_preserve_identical_ties() -> None:
    scalar_types = (float, np.float16, np.float32, np.float64)
    points = tuple(
        (scalar_type(0.25), scalar_type(0.25)) for scalar_type in scalar_types
    )
    reference = heterogeneity_dependence_reference(
        ((0, 2),),
        mean_prior=(1.0, 1.0),
        rho_prior=(1.0, 1.0),
        points=(*points, points[0]),
    )

    result = dependence_comparisons(
        reference, truth_index=0, draw_indices=(1, 2, 3, 4)
    )

    assert tuple((point.mean, point.rho) for point in reference.points) == (
        (0.25, 0.25),
    ) * 5
    assert result.status == "resolved"
    assert result.comparisons == (0, 0, 0, 0)


@pytest.mark.parametrize("toward", [0.0, 1.0])
def test_adjacent_binary64_points_do_not_use_identity_shortcut(toward: float) -> None:
    adjacent = np.nextafter(0.25, toward)
    reference = heterogeneity_dependence_reference(
        ((0, 2),),
        mean_prior=(1.0, 1.0),
        rho_prior=(1.0, 1.0),
        points=((0.25, 0.25), *((adjacent, 0.25),) * 4),
    )

    result = dependence_comparisons(
        reference, truth_index=0, draw_indices=(1, 2, 3, 4)
    )

    assert all(point.mean != reference.points[0].mean for point in reference.points[1:])
    assert result.status == "dependence_rank_order_unresolved"
    assert result.comparisons is None


def test_forged_mixed_supported_scalars_use_binary64_identity() -> None:
    point = DependencePointReference(
        mean=np.float32(0.25),
        rho=np.float32(0.25),
        components=((0.0, 0.0, 0.0, 0.0),) * 3,
        raw_values=(0.0, 0.0, 0.0),
        value=0.0,
        error_bound=0.0,
        resolved=True,
    )
    adjacent = replace(point, mean=float(np.nextafter(0.25, 1.0)))
    reference = HeterogeneityDependenceReference(
        orders=(64, 128, 256),
        analytic_separability=False,
        points=(point, adjacent, adjacent, adjacent, adjacent),
    )

    result = dependence_comparisons(
        reference, truth_index=0, draw_indices=(1, 2, 3, 4)
    )

    assert float(point.mean) != adjacent.mean
    assert result.status == "dependence_rank_order_unresolved"
    assert result.comparisons is None


def test_separable_comparisons_are_literal_ties_but_retain_raw_signs() -> None:
    reference = heterogeneity_dependence_reference(
        ((0, 1), (1, 2)),
        mean_prior=(2.0, 3.0),
        rho_prior=(3.0, 2.0),
        points=((0.1, 0.2), (0.2, 0.3), (0.3, 0.4), (0.4, 0.5), (0.5, 0.6)),
    )
    draws = (1, 2, 3, 4)

    result = dependence_comparisons(reference, truth_index=0, draw_indices=draws)

    assert result.status == "resolved"
    assert result.comparisons == (0, 0, 0, 0)
    assert result.comparisons_by_order == _raw_comparisons(reference, 0, draws)


def test_distinct_nonseparable_zero_dependence_is_not_declared_a_tie() -> None:
    reference = heterogeneity_dependence_reference(
        ((0, 2),),
        mean_prior=(1.0, 1.0),
        rho_prior=(1.0, 1.0),
        points=((0.25, 0.5), (0.75, 0.5), (0.75, 0.5), (0.75, 0.5), (0.75, 0.5)),
    )

    result = dependence_comparisons(
        reference, truth_index=0, draw_indices=(1, 2, 3, 4)
    )

    assert result.status == "dependence_rank_order_unresolved"
    assert result.comparisons is None
    assert result.comparisons_by_order == _raw_comparisons(reference, 0, (1, 2, 3, 4))


@pytest.mark.parametrize("mode", ["sign_change", "cancelling", "guard_equality"])
def test_comparisons_refuse_unstable_or_insufficient_ordering(mode: str) -> None:
    reference = _anchored_comparison_reference()
    truth = reference.points[0]
    draw = reference.points[1]
    if mode == "sign_change":
        raw_values = (
            truth.raw_values[0] - 0.1,
            truth.raw_values[1] + 0.1,
            truth.raw_values[2] + 0.1,
        )
        guard = 0.0
    elif mode == "cancelling":
        raw_values = truth.raw_values
        guard = 0.0
    else:
        truth = replace(truth, raw_values=(0.0, 0.0, 0.0), value=0.0, error_bound=0.01)
        guard = 0.01
        raw_values = (0.02, 0.02, 0.02)
    changed = replace(draw, raw_values=raw_values, value=raw_values[-1], error_bound=guard)
    forged = replace(reference, points=(truth, changed, *reference.points[2:]))

    result = dependence_comparisons(forged, truth_index=0, draw_indices=(1, 2, 3, 4))

    assert result.status == "dependence_rank_order_unresolved"
    assert result.comparisons is None
    assert result.comparisons_by_order == _raw_comparisons(forged, 0, (1, 2, 3, 4))


def test_comparisons_refuse_point_nonconvergence_and_retain_raw_signs() -> None:
    reference = _anchored_comparison_reference()
    changed = replace(reference.points[1], resolved=False)
    forged = replace(reference, points=(reference.points[0], changed, *reference.points[2:]))

    result = dependence_comparisons(forged, truth_index=0, draw_indices=(1, 2, 3, 4))

    assert result.status == "dependence_reference_unresolved"
    assert result.comparisons is None
    assert result.comparisons_by_order == _raw_comparisons(forged, 0, (1, 2, 3, 4))


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("components", ((0.0, 0.0, 0.0, 0.0),), ValueError),
        ("components", ((0.0, 0.0, 0.0, 0.0),) * 2 + ((0.0, np.inf, 0.0, 0.0),), ArithmeticError),
        ("raw_values", (0.0,), ValueError),
        ("raw_values", (0.0, np.nan, 0.0), ArithmeticError),
        ("value", np.inf, ArithmeticError),
        ("error_bound", -1.0, ValueError),
        ("error_bound", np.nan, ArithmeticError),
    ],
)
def test_comparisons_refuse_malformed_or_nonfinite_forged_points(
    field: str, value: object, error: type[Exception]
) -> None:
    reference = _anchored_comparison_reference()
    forged_point = replace(reference.points[1], **{field: value})
    forged = replace(
        reference, points=(reference.points[0], forged_point, *reference.points[2:])
    )

    with pytest.raises(error):
        dependence_comparisons(forged, truth_index=0, draw_indices=(1, 2, 3, 4))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("mean", Fraction(1, 4)),
        ("rho", Fraction(1, 4)),
        ("mean", np.longdouble("0.25")),
        ("rho", np.longdouble("0.25")),
    ],
)
def test_comparisons_reject_unsupported_forged_point_scalars(
    field: str, value: object
) -> None:
    reference = _anchored_comparison_reference()
    forged_point = replace(reference.points[1], **{field: value})
    forged = replace(
        reference, points=(reference.points[0], forged_point, *reference.points[2:])
    )

    with pytest.raises(ValueError):
        dependence_comparisons(forged, truth_index=0, draw_indices=(1, 2, 3, 4))


def test_comparisons_refuse_incorrect_order_tuple() -> None:
    reference = replace(_anchored_comparison_reference(), orders=(32, 64, 128))

    with pytest.raises(ValueError):
        dependence_comparisons(reference, truth_index=0, draw_indices=(1, 2, 3, 4))


@pytest.mark.parametrize(
    ("truth_index", "draw_indices"),
    [
        (True, (1, 2, 3, 4)),
        (0.0, (1, 2, 3, 4)),
        (-1, (1, 2, 3, 4)),
        (5, (1, 2, 3, 4)),
        (0, None),
        (0, (1, 2, 3)),
        (0, (1, 2, 3, 4, 4)),
        (0, (True, 2, 3, 4)),
        (0, (1.0, 2, 3, 4)),
        (0, (1, 2, 3, 5)),
        (0, (0, 2, 3, 4)),
        (0, (1, 1, 3, 4)),
    ],
)
def test_comparisons_reject_invalid_indices(
    truth_index: object, draw_indices: object
) -> None:
    with pytest.raises(ValueError):
        dependence_comparisons(
            _anchored_comparison_reference(),
            truth_index=truth_index,  # type: ignore[arg-type]
            draw_indices=draw_indices,  # type: ignore[arg-type]
        )


def test_comparisons_reject_non_reference_input() -> None:
    with pytest.raises(ValueError):
        dependence_comparisons(  # type: ignore[arg-type]
            object(), truth_index=0, draw_indices=(1, 2, 3, 4)
        )


def test_forged_point_constructor_documents_expected_shape() -> None:
    point = DependencePointReference(
        mean=0.5,
        rho=0.5,
        components=((0.0, 0.0, 0.0, 0.0),) * 3,
        raw_values=(0.0, 0.0, 0.0),
        value=0.0,
        error_bound=0.0,
        resolved=True,
    )
    reference = HeterogeneityDependenceReference(
        orders=(64, 128, 256), analytic_separability=True, points=(point,) * 5
    )

    result = dependence_comparisons(reference, truth_index=0, draw_indices=(1, 2, 3, 4))

    assert result.status == "resolved"
    assert result.comparisons == (0, 0, 0, 0)
