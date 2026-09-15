"""Numerical likelihood regressions for B0H (design §7.1; #214)."""

from __future__ import annotations

import math
from collections.abc import Iterator
from decimal import Decimal, localcontext

import jax
import jax.numpy as jnp
import numpy as np
import pymc as pm
import pytensor
import pytensor.tensor as pt
import pytest
from pymc.logprob.utils import ParameterValueError
from pymc.sampling.jax import get_jaxified_graph
from pytensor.graph.traversal import io_toposort
from pytensor.scan.op import Scan

from genomeos.surfaces.heterogeneity_types import PopulationHeterogeneityConfig
from genomeos.surfaces.reference_heterogeneity import fit_reference_population_heterogeneity
from genomeos.validation.reference_counts import ReferenceCount

FAILURE_MEAN = 0.9120608465340185
FAILURE_RHO = 8.091265212637455e-18
FAILURE_COUNTS = ((0, 1), (1, 2), (2, 4), (3, 9), (12, 20))
COUNT_PAIRS = (
    (0, 1),
    (1, 2),
    (12, 20),
    (0, 65536),
    (1, 65536),
    (32768, 65536),
    (65535, 65536),
    (65536, 65536),
    (17, 33),
)
PARAMETER_POINTS = (
    (0.9120608465340185, 8.091265212637455e-18),
    (0.5, 0.1),
    (0.01, 0.8),
    (0.999999, 0.999999),
    (1e-12, 1e-20),
    (1e-100, 1e-100),
    (1e-250, 1e-250),
    (0.5, 1e-300),
    (1e-250, 0.8),
    (0.5, np.nextafter(1.0, 0.0)),
)

# Bernoulli numbers B_2 through B_22. This test oracle evaluates ordinary
# logGamma/digamma with 400-digit Decimal arithmetic; it does not use the
# candidate rising-factorial/Stirling kernel or a production scoring helper.
_BERNOULLI = (
    (1, 6),
    (-1, 30),
    (1, 42),
    (-1, 30),
    (5, 66),
    (-691, 2730),
    (7, 6),
    (-3617, 510),
    (43867, 798),
    (-174611, 330),
    (854513, 138),
)


@pytest.fixture(autouse=True)
def _jax_float64() -> Iterator[None]:
    """Enable required test-local precision and restore the prior JAX setting."""
    previous = bool(jax.config.x64_enabled)
    jax.config.update("jax_enable_x64", True)
    try:
        yield
    finally:
        jax.config.update("jax_enable_x64", previous)


class _ModelCaptured(RuntimeError):
    pass


def _capture_model(monkeypatch: pytest.MonkeyPatch) -> pm.Model:
    captured: dict[str, pm.Model] = {}

    def capture_sample(**_: object) -> None:
        captured["model"] = pm.Model.get_context()
        raise _ModelCaptured

    monkeypatch.setattr("genomeos.surfaces.reference_heterogeneity.pm.sample", capture_sample)
    rows = tuple(
        ReferenceCount(
            record_id=f"failure-{index}",
            variant_id="unequal-an",
            group_id=f"failure-group-{index}",
            region_id=f"failure-region-{index}",
            variant_group="synthetic-likelihood-regression",
            ac=ac,
            an=an,
        )
        for index, (ac, an) in enumerate(FAILURE_COUNTS)
    )
    config = PopulationHeterogeneityConfig(1, 1, 1, 9)
    with pytest.raises(_ModelCaptured):
        fit_reference_population_heterogeneity(rows, config=config)
    return captured["model"]


def _logit(probability: float) -> float:
    return math.log(probability) - math.log1p(-probability)


def _decimal_gamma_and_digamma(value: Decimal) -> tuple[Decimal, Decimal]:
    shifted_logs = Decimal(0)
    shifted_reciprocals = Decimal(0)
    while value < 128:
        shifted_logs += value.ln()
        shifted_reciprocals += 1 / value
        value += 1
    log_gamma = (value - Decimal(".5")) * value.ln() - value
    digamma = value.ln() - 1 / (2 * value)
    for order, (numerator, denominator) in enumerate(_BERNOULLI, 1):
        bernoulli = Decimal(numerator) / denominator
        log_gamma += bernoulli / (
            2 * order * (2 * order - 1) * value ** (2 * order - 1)
        )
        digamma -= bernoulli / (2 * order * value ** (2 * order))
    return log_gamma - shifted_logs, digamma - shifted_reciprocals


def _decimal_reference(
    logits: tuple[float, float], value: int, n: int
) -> tuple[float, tuple[float, float]]:
    """Return ordinary logGamma/digamma results at the exact binary64 logits."""
    if n == 0:
        return 0.0, (0.0, 0.0)
    with localcontext() as context:
        context.prec = 400
        mean_logit, rho_logit = map(Decimal.from_float, logits)
        mean = 1 / (1 + (-mean_logit).exp())
        rho = 1 / (1 + (-rho_logit).exp())
        concentration = (1 - rho) / rho
        alpha = mean * concentration
        beta = (1 - mean) * concentration
        log_alpha, psi_alpha = _decimal_gamma_and_digamma(alpha)
        log_alpha_count, psi_alpha_count = _decimal_gamma_and_digamma(alpha + value)
        log_beta, psi_beta = _decimal_gamma_and_digamma(beta)
        log_beta_count, psi_beta_count = _decimal_gamma_and_digamma(beta + n - value)
        log_concentration, psi_concentration = _decimal_gamma_and_digamma(concentration)
        log_total, psi_total = _decimal_gamma_and_digamma(concentration + n)
        logp = (
            Decimal(math.comb(n, value)).ln()
            + log_alpha_count
            - log_alpha
            + log_beta_count
            - log_beta
            - log_total
            + log_concentration
        )
        mean_gradient = (
            mean
            * (1 - mean)
            * concentration
            * (
                psi_alpha_count
                - psi_alpha
                - psi_beta_count
                + psi_beta
            )
        )
        rho_gradient = -concentration * (
            mean * (psi_alpha_count - psi_alpha)
            + (1 - mean) * (psi_beta_count - psi_beta)
            - (psi_total - psi_concentration)
        )
    return float(logp), (float(mean_gradient), float(rho_gradient))


def _jaxified_logp(
    values: tuple[int, ...], totals: tuple[int, ...]
) -> object:
    from genomeos.surfaces.heterogeneity_likelihood import beta_binomial_logp

    logits = pt.dvector("logits")
    mean = pt.sigmoid(logits[0])
    rho = pt.sigmoid(logits[1])
    expression = beta_binomial_logp(
        pt.as_tensor_variable(np.asarray(values, dtype=np.int64)),
        pt.as_tensor_variable(np.asarray(totals, dtype=np.int64)),
        mean,
        rho,
    )
    graph = get_jaxified_graph(inputs=[logits], outputs=[expression])

    @jax.jit
    def evaluate(point: jax.Array) -> tuple[jax.Array, jax.Array]:
        values_at_point = graph(point)[0]
        gradients = jax.jacrev(lambda z: graph(z)[0])(point)
        return values_at_point, gradients

    return evaluate


def test_actual_model_restores_captured_logp_and_logit_gradient(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Replacing the bounded observed kernel with gamma differences recreates +6160/zero."""
    model = _capture_model(monkeypatch)
    mean_value = model.rvs_to_values[model["mean"]]
    rho_value = model.rvs_to_values[model["rho"]]
    observed_logp = model.logp(vars=[model["obs"]], jacobian=False)
    graph = get_jaxified_graph(
        inputs=[mean_value, rho_value], outputs=[observed_logp]
    )

    def evaluate(logits: jax.Array) -> jax.Array:
        return graph(logits[:1], logits[1:])[0]

    logits = jnp.asarray([_logit(FAILURE_MEAN), _logit(FAILURE_RHO)])
    actual, gradient = jax.jit(jax.value_and_grad(evaluate))(logits)

    assert float(actual) == pytest.approx(-26.757334358778397, rel=0, abs=5e-10)
    np.testing.assert_allclose(
        np.asarray(gradient),
        [-14.834190475224663, 2.7841657124119296e-15],
        rtol=1e-12,
        atol=1e-9,
    )


def test_logp_and_logit_gradients_match_400_digit_decimal_reference() -> None:
    """The bounded kernel disagrees if cancellation, a constant, or a derivative is wrong."""
    values = tuple(value for value, _ in COUNT_PAIRS)
    totals = tuple(n for _, n in COUNT_PAIRS)
    evaluate = _jaxified_logp(values, totals)
    for mean, rho in PARAMETER_POINTS:
        logits = (_logit(mean), _logit(rho))
        actual, actual_gradients = evaluate(jnp.asarray(logits, dtype=jnp.float64))
        references = tuple(
            _decimal_reference(logits, value, n) for value, n in COUNT_PAIRS
        )
        np.testing.assert_allclose(
            np.asarray(actual),
            [reference[0] for reference in references],
            rtol=1e-14,
            atol=5e-10,
        )
        np.testing.assert_allclose(
            np.asarray(actual_gradients),
            [reference[1] for reference in references],
            rtol=1e-12,
            atol=1e-9,
        )


def test_an1_an2_and_zero_an_have_exact_values_and_gradients() -> None:
    """Dropping normalization, rho cancellation, or the empty product breaks an identity."""
    mean = 0.37
    rho = 0.23
    logits = jnp.asarray([_logit(mean), _logit(rho)], dtype=jnp.float64)
    evaluate = _jaxified_logp((0, 1, 1, 0), (1, 1, 2, 0))
    actual, gradients = evaluate(logits)
    np.testing.assert_allclose(
        np.asarray(actual),
        [math.log1p(-mean), math.log(mean), math.log(2 * mean * (1 - mean) * (1 - rho)), 0],
        rtol=0,
        atol=1e-14,
    )
    np.testing.assert_allclose(
        np.asarray(gradients),
        [[-mean, 0], [1 - mean, 0], [1 - 2 * mean, -rho], [0, 0]],
        rtol=0,
        atol=1e-14,
    )


@pytest.mark.parametrize("n", [33, 64, 65536])
def test_tail_join_and_both_sides_match_high_precision(n: int) -> None:
    """Using min/max or mismatched branch predicates corrupts the exact join gradient."""
    value = n
    concentration = (8 * (n - 16) - 16) / 0.5
    evaluate = _jaxified_logp((value,), (n,))
    for factor in (1 - 1e-10, 1.0, 1 + 1e-10):
        rho = 1 / (1 + concentration * factor)
        logits = (_logit(0.5), _logit(rho))
        actual, gradient = evaluate(jnp.asarray(logits, dtype=jnp.float64))
        reference, reference_gradient = _decimal_reference(logits, value, n)
        np.testing.assert_allclose(actual, [reference], rtol=1e-14, atol=5e-10)
        np.testing.assert_allclose(
            gradient, [reference_gradient], rtol=1e-12, atol=1e-9
        )


def test_small_tail_helper_has_exact_join_value_and_derivative() -> None:
    """The branch join itself stays covered even if transformed rho rounds away from it."""
    from genomeos.surfaces.heterogeneity_likelihood import _log1p_ratio_minus_one

    argument = pt.dscalar("argument")
    expression = _log1p_ratio_minus_one(argument)
    graph = get_jaxified_graph(inputs=[argument], outputs=[expression])

    def evaluate(value: jax.Array) -> jax.Array:
        return graph(value)[0]

    value_and_gradient = jax.jit(jax.value_and_grad(evaluate))
    for value in (np.nextafter(0.125, 0.0), 0.125, np.nextafter(0.125, 1.0)):
        actual, gradient = value_and_gradient(jnp.asarray(value, dtype=jnp.float64))
        expected = math.log1p(value) / value - 1
        expected_gradient = (value / (1 + value) - math.log1p(value)) / value**2
        assert float(actual) == pytest.approx(expected, rel=0, abs=2e-16)
        assert float(gradient) == pytest.approx(expected_gradient, rel=0, abs=2e-15)


@pytest.mark.parametrize("n", [1, 2, 16, 17, 32, 64])
@pytest.mark.parametrize(
    ("mean", "rho"),
    [(0.01, 0.8), (0.5, 0.1), (FAILURE_MEAN, FAILURE_RHO)],
)
def test_pmf_normalization_and_complement_symmetry(n: int, mean: float, rho: float) -> None:
    """An omitted constant or asymmetric factor breaks normalized complementary masses."""
    values = tuple(range(n + 1))
    totals = (n,) * (n + 1)
    evaluate = _jaxified_logp(values, totals)
    logits = jnp.asarray([_logit(mean), _logit(rho)], dtype=jnp.float64)
    complemented_logits = logits.at[0].set(-logits[0])
    log_masses, _ = evaluate(logits)
    complement_masses, _ = evaluate(complemented_logits)
    assert float(jnp.exp(jax.scipy.special.logsumexp(log_masses))) == pytest.approx(
        1.0, rel=0, abs=1e-13
    )
    np.testing.assert_allclose(
        np.asarray(log_masses), np.asarray(complement_masses)[::-1], rtol=0, atol=5e-13
    )


def test_supplied_value_and_count_support_are_enforced() -> None:
    """Closing over observed counts or accepting noninteger/out-of-range values is a bug."""
    from genomeos.surfaces.heterogeneity_likelihood import beta_binomial_logp

    value = pt.dscalar("value")
    n = pt.dscalar("n")
    expression = beta_binomial_logp(
        value, n, pt.as_tensor(np.float64(0.25)), pt.as_tensor(np.float64(0.2))
    )
    evaluate = pytensor.function([value, n], expression)
    assert float(evaluate(0, 2)) == pytest.approx(math.log(0.6), abs=1e-14)
    assert float(evaluate(1, 2)) == pytest.approx(math.log(0.3), abs=1e-14)
    assert float(evaluate(2, 2)) == pytest.approx(math.log(0.1), abs=1e-14)
    assert np.isneginf(evaluate(-1, 2))
    assert np.isneginf(evaluate(3, 2))
    assert np.isneginf(evaluate(0.5, 2))
    with pytest.raises(ParameterValueError, match="n.*nonnegative integer"):
        evaluate(1, 1.5)


@pytest.mark.parametrize(("mean", "rho"), [(0, 0.2), (1, 0.2), (0.5, 0), (0.5, 1)])
def test_parameter_domain_is_checked(mean: float, rho: float) -> None:
    """Removing strict interior parameter checks permits an undeclared model domain."""
    from genomeos.surfaces.heterogeneity_likelihood import beta_binomial_logp

    expression = beta_binomial_logp(
        pt.as_tensor(1), pt.as_tensor(2), pt.as_tensor(mean), pt.as_tensor(rho)
    )
    evaluate = pytensor.function([], expression)
    with pytest.raises(
        ParameterValueError, match="mean and rho.*strictly between 0 and 1"
    ):
        evaluate()


def test_graph_work_is_bounded_and_row_vector_only() -> None:
    """A scan, support-sized matrix, or per-AN unrolling violates the bounded-work contract."""
    from genomeos.surfaces.heterogeneity_likelihood import beta_binomial_logp

    value = pt.lvector("value")
    n = pt.lvector("n")
    mean = pt.dvector("mean")
    rho = pt.dvector("rho")
    expression = beta_binomial_logp(value, n, mean, rho)
    nodes = io_toposort([value, n, mean, rho], [expression])
    assert expression.ndim == 1
    assert all(output.ndim <= 1 for node in nodes for output in node.outputs)
    assert len(nodes) < 1200
    assert not any(isinstance(node.op, Scan) for node in nodes)
    assert not any(type(node.op).__module__.startswith("genomeos") for node in nodes)


def test_custom_observed_node_has_no_direct_random_generator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Adding hidden PyMC random generation would bypass the public CountPredictive path."""
    model = _capture_model(monkeypatch)
    assert model["obs"].dtype == "int64"
    with pytest.raises(NotImplementedError, match="random.*had not been provided"):
        pm.draw(model["obs"], random_seed=42, mode="FAST_COMPILE")
