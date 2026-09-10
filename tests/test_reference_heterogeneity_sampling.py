"""Actual synthetic NUTS proof for B0H (design §§5, 7–8, 12; #211)."""

from __future__ import annotations

import json
from fractions import Fraction
from time import perf_counter

import arviz as az
import numpy as np

from genomeos.surfaces.heterogeneity_types import PopulationHeterogeneityConfig
from genomeos.surfaces.reference_heterogeneity import (
    fit_reference_population_heterogeneity,
    predict_reference_population_heterogeneity,
)
from genomeos.validation.reference_counts import ReferenceCount


def _row(group: str, variant: str, ac: int, an: int) -> ReferenceCount:
    return ReferenceCount(
        record_id=f"{group}:{variant}",
        variant_id=variant,
        group_id=group,
        region_id=f"region-{group}",
        variant_group="synthetic-exact-oracle",
        ac=ac,
        an=an,
    )


def _training_rows() -> tuple[ReferenceCount, ...]:
    bernoulli = tuple(
        _row(f"bernoulli-{index}", "bernoulli", ac, 1)
        for index, ac in enumerate((0, 1, 1, 0, 1))
    )
    central = tuple(
        _row(f"central-{index}", "central-an2", 1, 2) for index in range(4)
    )
    return (
        *bernoulli,
        _row("bernoulli-unavailable", "bernoulli", 0, 0),
        *central,
        _row("central-unavailable", "central-an2", 0, 0),
    )


def _complement(rows: tuple[ReferenceCount, ...]) -> tuple[ReferenceCount, ...]:
    return tuple(
        ReferenceCount(
            record_id=row.record_id,
            variant_id=row.variant_id,
            group_id=row.group_id,
            region_id=row.region_id,
            variant_group=row.variant_group,
            ac=row.an - row.ac,
            an=row.an,
        )
        for row in rows
    )


def _mcse(values: np.ndarray) -> float:
    result = float(az.mcse(values, method="mean", chain_axis=0, draw_axis=1))
    assert np.isfinite(result)
    assert 0.0 < result <= 0.01
    return result


def _check(
    evidence: dict[str, dict[str, float]],
    name: str,
    values: np.ndarray,
    expected: Fraction,
    *,
    actual: float | None = None,
) -> None:
    estimate = float(np.mean(values)) if actual is None else actual
    mcse = _mcse(values)
    discrepancy = abs(estimate - float(expected))
    tolerance = max(5.0 * mcse, 0.003)
    evidence[name] = {
        "estimate": estimate,
        "exact": float(expected),
        "mcse": mcse,
        "absolute_discrepancy": discrepancy,
        "tolerance": tolerance,
    }
    assert discrepancy <= tolerance


def test_actual_nuts_matches_two_exact_posterior_distributions() -> None:
    config = PopulationHeterogeneityConfig(
        mean_prior_alpha=1,
        mean_prior_beta=1,
        rho_prior_alpha=1,
        rho_prior_beta=9,
        draws=1000,
        tune=1000,
        chains=4,
        target_accept=0.9,
        seed=42,
    )
    started = perf_counter()
    fitted = fit_reference_population_heterogeneity(_training_rows(), config=config)
    runtime_seconds = perf_counter() - started
    assert fitted.variant_ids == ("bernoulli", "central-an2")
    assert fitted.unavailable_training_ids == (
        "bernoulli-unavailable:bernoulli",
        "central-unavailable:central-an2",
    )

    predicted = predict_reference_population_heterogeneity(
        fitted,
        (
            _row("query-bernoulli", "bernoulli", 1, 2),
            _row("query-central", "central-an2", 1, 2),
        ),
    )
    predicted_mass_one = np.exp(predicted.marginal_predictive.log_prob([1, 1], [2, 2]))
    predicted_mass_zero = predicted.marginal_predictive.cdf([0, 0], [2, 2])

    evidence: dict[str, dict[str, float]] = {}
    exact = {
        "bernoulli": {
            "mean": Fraction(4, 7),
            "mean_squared": Fraction(5, 14),
            "rho": Fraction(1, 10),
            "rho_squared": Fraction(1, 55),
            "mass_one": Fraction(27, 70),
            "mass_zero": Fraction(33, 140),
        },
        "central-an2": {
            "mean": Fraction(1, 2),
            "mean_squared": Fraction(3, 11),
            "rho": Fraction(1, 14),
            "rho_squared": Fraction(1, 105),
            "mass_one": Fraction(65, 154),
            "mass_zero": Fraction(89, 308),
        },
    }
    for index, variant_id in enumerate(fitted.variant_ids):
        mean = fitted.mean_draws[:, :, index]
        rho = fitted.rho_draws[:, :, index]
        mass_one = 2.0 * mean * (1.0 - mean) * (1.0 - rho)
        mass_two = mean - mass_one / 2.0
        mass_zero = 1.0 - mass_one - mass_two
        _check(evidence, f"{variant_id}.mean", mean, exact[variant_id]["mean"])
        _check(
            evidence,
            f"{variant_id}.mean_squared",
            mean**2,
            exact[variant_id]["mean_squared"],
        )
        _check(evidence, f"{variant_id}.rho", rho, exact[variant_id]["rho"])
        _check(
            evidence,
            f"{variant_id}.rho_squared",
            rho**2,
            exact[variant_id]["rho_squared"],
        )
        _check(
            evidence,
            f"{variant_id}.predictive_mass_one",
            mass_one,
            exact[variant_id]["mass_one"],
            actual=float(predicted_mass_one[index]),
        )
        _check(
            evidence,
            f"{variant_id}.predictive_mass_zero",
            mass_zero,
            exact[variant_id]["mass_zero"],
            actual=float(predicted_mass_zero[index]),
        )

    repeat_started = perf_counter()
    repeated = fit_reference_population_heterogeneity(_training_rows(), config=config)
    repeat_runtime_seconds = perf_counter() - repeat_started
    np.testing.assert_array_equal(repeated.mean_draws, fitted.mean_draws)
    np.testing.assert_array_equal(repeated.rho_draws, fitted.rho_draws)

    complement_started = perf_counter()
    complemented = fit_reference_population_heterogeneity(
        _complement(_training_rows()), config=config
    )
    complement_runtime_seconds = perf_counter() - complement_started
    assert complemented.unavailable_training_ids == fitted.unavailable_training_ids
    complemented_prediction = predict_reference_population_heterogeneity(
        complemented,
        (
            _row("complement-query-bernoulli", "bernoulli", 1, 2),
            _row("complement-query-central", "central-an2", 1, 2),
        ),
    )
    complemented_mass_one = np.exp(
        complemented_prediction.marginal_predictive.log_prob([1, 1], [2, 2])
    )
    complemented_mass_zero = complemented_prediction.marginal_predictive.cdf(
        [0, 0], [2, 2]
    )
    complemented_exact = {
        "bernoulli": {
            "mean": Fraction(3, 7),
            "mean_squared": Fraction(3, 14),
            "rho": Fraction(1, 10),
            "rho_squared": Fraction(1, 55),
            "mass_one": Fraction(27, 70),
            "mass_zero": Fraction(53, 140),
        },
        "central-an2": exact["central-an2"],
    }
    for index, variant_id in enumerate(complemented.variant_ids):
        mean = complemented.mean_draws[:, :, index]
        rho = complemented.rho_draws[:, :, index]
        mass_one = 2.0 * mean * (1.0 - mean) * (1.0 - rho)
        mass_two = mean - mass_one / 2.0
        mass_zero = 1.0 - mass_one - mass_two
        _check(
            evidence,
            f"complement.{variant_id}.mean",
            mean,
            complemented_exact[variant_id]["mean"],
        )
        _check(
            evidence,
            f"complement.{variant_id}.mean_squared",
            mean**2,
            complemented_exact[variant_id]["mean_squared"],
        )
        _check(
            evidence,
            f"complement.{variant_id}.rho",
            rho,
            complemented_exact[variant_id]["rho"],
        )
        _check(
            evidence,
            f"complement.{variant_id}.rho_squared",
            rho**2,
            complemented_exact[variant_id]["rho_squared"],
        )
        _check(
            evidence,
            f"complement.{variant_id}.predictive_mass_one",
            mass_one,
            complemented_exact[variant_id]["mass_one"],
            actual=float(complemented_mass_one[index]),
        )
        _check(
            evidence,
            f"complement.{variant_id}.predictive_mass_zero",
            mass_zero,
            complemented_exact[variant_id]["mass_zero"],
            actual=float(complemented_mass_zero[index]),
        )

    print(
        json.dumps(
            {
                "runtime_seconds": {
                    "initial": runtime_seconds,
                    "identical_seed_repeat": repeat_runtime_seconds,
                    "complement": complement_runtime_seconds,
                },
                "diagnostics": [item.__dict__ for item in fitted.diagnostics],
                "complement_diagnostics": [
                    item.__dict__ for item in complemented.diagnostics
                ],
                "divergence_count": fitted.divergence_count,
                "complement_divergence_count": complemented.divergence_count,
                "identical_seed_draws_equal": True,
                "evidence": evidence,
            },
            indent=2,
            sort_keys=True,
        )
    )
