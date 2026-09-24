"""Differentiable activity-mixture likelihood tests (design §§7–8; issue #384)."""

from __future__ import annotations

import math

import numpy as np
import pytensor
import pytensor.tensor as pt
import pytest
from pymc.logprob.utils import ParameterValueError
from pytensor.graph.traversal import io_toposort
from pytensor.scan.op import Scan

from genomeos.validation.spatial_activity_preflight import ActivityCountPredictive


def _evaluate(
    ac: np.ndarray,
    an: np.ndarray,
    mean: np.ndarray,
    activity: np.ndarray,
    concentration: np.ndarray,
) -> np.ndarray:
    from genomeos.surfaces.activity_likelihood import activity_beta_binomial_logp

    expression = activity_beta_binomial_logp(
        pt.as_tensor_variable(ac),
        pt.as_tensor_variable(an),
        pt.as_tensor_variable(mean),
        pt.as_tensor_variable(activity),
        pt.as_tensor_variable(concentration),
    )
    return np.asarray(pytensor.function([], expression)())


def test_hand_calculated_masses_include_both_zero_paths_and_normalize() -> None:
    log_mass = _evaluate(
        np.array([0, 1, 2]),
        np.array([2, 2, 2]),
        np.full(3, 0.5),
        np.full(3, 0.75),
        np.full(3, 2.0),
    )

    np.testing.assert_allclose(np.exp(log_mass), [0.5, 0.25, 0.25], rtol=0, atol=1e-14)
    assert float(np.exp(log_mass).sum()) == pytest.approx(1.0, abs=1e-14)


def test_symbolic_logp_matches_the_one_draw_numpy_oracle() -> None:
    ac = np.array([0, 1, 4, 10])
    an = np.array([1, 2, 10, 20])
    mean = np.array([0.02, 0.25, 0.4, 0.7])
    activity = np.array([0.1, 0.5, 0.8, 1.0])
    concentration = np.array([5.0, 20.0, 50.0, 100.0])
    oracle = ActivityCountPredictive(
        conditional_mean_draws=mean[np.newaxis, :],
        activity_probability_draws=activity[np.newaxis, :],
        concentration_draws=concentration[np.newaxis, :],
    )

    actual = _evaluate(ac, an, mean, activity, concentration)

    np.testing.assert_allclose(actual, oracle.log_prob(ac, an), rtol=0, atol=2e-13)


def test_activity_boundaries_are_exact() -> None:
    inactive = _evaluate(
        np.array([0, 1]),
        np.array([2, 2]),
        np.full(2, 0.5),
        np.zeros(2),
        np.full(2, 2.0),
    )
    ordinary = _evaluate(
        np.array([0, 1]),
        np.array([2, 2]),
        np.full(2, 0.5),
        np.ones(2),
        np.full(2, 2.0),
    )

    assert inactive[0] == pytest.approx(0.0)
    assert np.isneginf(inactive[1])
    np.testing.assert_allclose(ordinary, np.log([1 / 3, 1 / 3]), rtol=0, atol=1e-14)


@pytest.mark.parametrize("ac", [0, 1])
def test_an_one_has_exact_logit_gradients(ac: int) -> None:
    from genomeos.surfaces.activity_likelihood import activity_beta_binomial_logp

    logits = pt.dvector("logits")
    mean = pt.sigmoid(logits[0])
    activity = pt.sigmoid(logits[1])
    concentration = pt.exp(logits[2])
    logp = activity_beta_binomial_logp(ac, 1, mean, activity, concentration)
    gradient = pt.grad(logp, logits)
    evaluate = pytensor.function([logits], [logp, gradient])
    point = np.array([math.log(0.2 / 0.8), math.log(0.5 / 0.5), math.log(10.0)])

    actual, actual_gradient = evaluate(point)

    marginal = 0.1
    expected_logp = math.log(marginal if ac else 1.0 - marginal)
    if ac:
        expected_gradient = np.array([0.8, 0.5, 0.0])
    else:
        expected_gradient = np.array(
            [-(0.5 * 0.2 * 0.8) / (1.0 - marginal), -(0.2 * 0.5 * 0.5) / (1.0 - marginal), 0.0]
        )
    assert float(actual) == pytest.approx(expected_logp, abs=1e-14)
    np.testing.assert_allclose(actual_gradient, expected_gradient, rtol=0, atol=2e-14)


@pytest.mark.parametrize(
    ("mean", "activity", "concentration", "message"),
    [
        (0.0, 0.5, 20.0, "mean.*strictly between"),
        (1.0, 0.5, 20.0, "mean.*strictly between"),
        (0.2, -0.1, 20.0, "activity_probability.*between"),
        (0.2, 1.1, 20.0, "activity_probability.*between"),
        (0.2, 0.5, 0.0, "concentration.*positive"),
    ],
)
def test_parameter_domain_is_checked(
    mean: float,
    activity: float,
    concentration: float,
    message: str,
) -> None:
    from genomeos.surfaces.activity_likelihood import activity_beta_binomial_logp

    expression = activity_beta_binomial_logp(1, 2, mean, activity, concentration)
    evaluate = pytensor.function([], expression)
    with pytest.raises(ParameterValueError, match=message):
        evaluate()


def test_graph_is_bounded_and_row_vector_only() -> None:
    from genomeos.surfaces.activity_likelihood import activity_beta_binomial_logp

    value = pt.lvector("value")
    n = pt.lvector("n")
    mean = pt.dvector("mean")
    activity = pt.dvector("activity")
    concentration = pt.dvector("concentration")
    expression = activity_beta_binomial_logp(value, n, mean, activity, concentration)
    nodes = io_toposort([value, n, mean, activity, concentration], [expression])

    assert expression.ndim == 1
    assert all(output.ndim <= 1 for node in nodes for output in node.outputs)
    assert not any(isinstance(node.op, Scan) for node in nodes)
