"""Nonconjugate B0H NUTS/quadrature checks (design §§5, 7–8, 12; #211)."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict

import arviz as az
import numpy as np
import pytest
import xarray as xr

from genomeos.surfaces.heterogeneity_types import (
    HeterogeneityConvergenceError,
    PopulationHeterogeneityConfig,
    PopulationHeterogeneityFit,
)
from genomeos.surfaces.reference_heterogeneity import (
    fit_reference_population_heterogeneity,
    predict_reference_population_heterogeneity,
)
from genomeos.validation.heterogeneity_oracle import (
    HeterogeneityQuadrature,
    heterogeneity_log_mass,
    heterogeneity_quadrature,
)
from genomeos.validation.reference_counts import ReferenceCount

SEED = 42
CASES = {
    "mixed": ((0, 2), (1, 3), (4, 5), (8, 8), (2, 6)),
    "rare": ((0, 20), (0, 12), (1, 18), (0, 5), (0, 0)),
    "unequal_an": ((0, 1), (1, 2), (2, 4), (3, 9), (12, 20), (0, 0)),
}
ORDERS = (32, 64, 128, 256)
RHO_PRIORS = ((1.0, 9.0), (1.0, 4.0))
MEAN_PRIOR = (1.0, 1.0)
PREDICTIVE_AN = 5
REFINEMENT_ATOL = 1e-8
MCSE_MAX = 0.005
SAMPLER_FLOOR = 0.003
SAMPLER_CONFIG = {
    "draws": 2000,
    "tune": 2000,
    "chains": 4,
    "target_accept": 0.9,
    "seed": SEED,
}
MOMENT_NAMES = ("mean", "mean_squared", "rho", "rho_squared", "mean_rho")


def _oriented_counts(
    orientation: str, counts: tuple[tuple[int, int], ...]
) -> tuple[tuple[int, int], ...]:
    if orientation == "original":
        return counts
    assert orientation == "complement"
    return tuple((an - ac, an) for ac, an in counts)


def _quadrature_values(result: HeterogeneityQuadrature) -> dict[str, float]:
    values = {name: float(getattr(result, name)) for name in MOMENT_NAMES}
    values["log_evidence"] = result.log_evidence
    values.update(
        {f"predictive_ac_{ac}": mass for ac, mass in enumerate(result.predictive_masses)}
    )
    return values


def _references(
    rho_prior: tuple[float, float],
) -> dict[tuple[str, str], tuple[HeterogeneityQuadrature, ...]]:
    return {
        (orientation, case): tuple(
            heterogeneity_quadrature(
                _oriented_counts(orientation, counts),
                mean_prior=MEAN_PRIOR,
                rho_prior=rho_prior,
                predictive_an=PREDICTIVE_AN,
                order=order,
            )
            for order in ORDERS
        )
        for orientation in ("original", "complement")
        for case, counts in CASES.items()
    }


def _row(
    *, orientation: str, case: str, index: int, ac: int, an: int, query: bool = False
) -> ReferenceCount:
    role = "query" if query else "training"
    group = f"synthetic-quadrature-{role}-{orientation}-{case}-{index}"
    return ReferenceCount(
        record_id=f"{group}:case-{case}",
        variant_id=f"case-{case}",
        group_id=group,
        region_id=f"synthetic-region-{role}-{orientation}-{case}-{index}",
        variant_group="synthetic-quadrature-source",
        ac=ac,
        an=an,
    )


def _training_rows(orientation: str) -> tuple[ReferenceCount, ...]:
    return tuple(
        _row(
            orientation=orientation,
            case=case,
            index=index,
            ac=ac,
            an=an,
        )
        for case, counts in CASES.items()
        for index, (ac, an) in enumerate(_oriented_counts(orientation, counts))
    )


def _query_rows(orientation: str) -> tuple[ReferenceCount, ...]:
    return tuple(
        _row(
            orientation=orientation,
            case=case,
            index=0,
            ac=0,
            an=PREDICTIVE_AN,
            query=True,
        )
        for case in CASES
    )


def _labeled_draws(fitted: PopulationHeterogeneityFit) -> xr.Dataset:
    coordinates = {
        "chain": np.arange(fitted.config.chains),
        "draw": np.arange(fitted.config.draws),
        "variant": list(fitted.variant_ids),
    }
    return xr.Dataset(
        {
            "mean": (("chain", "draw", "variant"), fitted.mean_draws),
            "rho": (("chain", "draw", "variant"), fitted.rho_draws),
        },
        coords=coordinates,
    )


def _mcse(values: np.ndarray) -> float:
    result = float(az.mcse(values, method="mean", chain_axis=0, draw_axis=1))
    assert np.isfinite(result) and 0.0 < result <= MCSE_MAX
    return result


def _check_sampling_quantity(
    evidence: list[dict[str, object]],
    *,
    prior: tuple[float, float],
    orientation: str,
    case: str,
    quantity: str,
    values: np.ndarray,
    reference: float,
    actual: float | None = None,
) -> None:
    estimate = float(np.mean(values)) if actual is None else actual
    mcse = _mcse(values)
    bound = max(5.0 * mcse, SAMPLER_FLOOR)
    discrepancy = abs(estimate - reference)
    evidence.append(
        {
            "rho_prior": prior,
            "orientation": orientation,
            "case": case,
            "quantity": quantity,
            "estimate": estimate,
            "reference": reference,
            "mcse": mcse,
            "absolute_discrepancy": discrepancy,
            "bound": bound,
        }
    )
    assert discrepancy <= bound


@pytest.mark.parametrize("rho_prior", RHO_PRIORS)
def test_quadrature_refines_and_preserves_complement_symmetry(
    rho_prior: tuple[float, float],
) -> None:
    references = _references(rho_prior)
    refinement_evidence: list[dict[str, object]] = []
    for (orientation, case), results in references.items():
        values_by_order = tuple(_quadrature_values(result) for result in results)
        for earlier, later, earlier_values, later_values in zip(
            ORDERS[:-1], ORDERS[1:], values_by_order[:-1], values_by_order[1:], strict=True
        ):
            gaps = {
                name: abs(later_values[name] - earlier_values[name])
                for name in earlier_values
            }
            refinement_evidence.append(
                {
                    "rho_prior": rho_prior,
                    "orientation": orientation,
                    "case": case,
                    "orders": (earlier, later),
                    "gaps": gaps,
                }
            )
            if earlier >= 64:
                assert all(gap <= REFINEMENT_ATOL for gap in gaps.values())

        original = references[("original", case)][-1]
        complement = references[("complement", case)][-1]
        assert complement.log_evidence == pytest.approx(
            original.log_evidence, rel=0, abs=REFINEMENT_ATOL
        )
        assert complement.rho == pytest.approx(original.rho, rel=0, abs=REFINEMENT_ATOL)
        assert complement.rho_squared == pytest.approx(
            original.rho_squared, rel=0, abs=REFINEMENT_ATOL
        )
        assert complement.mean == pytest.approx(
            1.0 - original.mean, rel=0, abs=REFINEMENT_ATOL
        )
        assert complement.mean_squared == pytest.approx(
            1.0 - 2.0 * original.mean + original.mean_squared,
            rel=0,
            abs=REFINEMENT_ATOL,
        )
        assert complement.mean_rho == pytest.approx(
            original.rho - original.mean_rho, rel=0, abs=REFINEMENT_ATOL
        )
        assert complement.predictive_masses == pytest.approx(
            original.predictive_masses[::-1], rel=0, abs=REFINEMENT_ATOL
        )

    print(json.dumps({"quadrature_refinement": refinement_evidence}, sort_keys=True))


@pytest.mark.parametrize("rho_prior", RHO_PRIORS)
@pytest.mark.parametrize("orientation", ("original", "complement"))
def test_actual_nuts_and_predictor_match_nonconjugate_quadrature(
    rho_prior: tuple[float, float], orientation: str
) -> None:
    references = _references(rho_prior)
    evidence: list[dict[str, object]] = []
    config = PopulationHeterogeneityConfig(
        mean_prior_alpha=MEAN_PRIOR[0],
        mean_prior_beta=MEAN_PRIOR[1],
        rho_prior_alpha=rho_prior[0],
        rho_prior_beta=rho_prior[1],
        **SAMPLER_CONFIG,
    )
    try:
        fitted = fit_reference_population_heterogeneity(
            _training_rows(orientation), config=config
        )
    except HeterogeneityConvergenceError as error:
        print(
            json.dumps(
                {
                    "sampling_failure": {
                        "rho_prior": rho_prior,
                        "orientation": orientation,
                        "reason": error.reason,
                        "divergence_count": error.divergence_count,
                        "diagnostics": [asdict(item) for item in error.diagnostics],
                    }
                },
                sort_keys=True,
            )
        )
        raise

    unavailable = tuple(
        row.record_id for row in _training_rows(orientation) if row.an == 0
    )
    assert fitted.unavailable_training_ids == tuple(sorted(unavailable))
    assert fitted.divergence_count == 0

    predicted = predict_reference_population_heterogeneity(fitted, _query_rows(orientation))
    assert not set(fitted.training_group_ids) & {
        row.group_id for row in _query_rows(orientation)
    }
    assert predicted.unavailable_ids == ()
    actual_predictive = {
        ac: np.exp(
            predicted.marginal_predictive.log_prob(
                np.full(len(CASES), ac), np.full(len(CASES), PREDICTIVE_AN)
            )
        )
        for ac in range(PREDICTIVE_AN + 1)
    }
    draws = _labeled_draws(fitted)
    fit_evidence = {
        "rho_prior": rho_prior,
        "orientation": orientation,
        "divergence_count": fitted.divergence_count,
        "diagnostics": [asdict(item) for item in fitted.diagnostics],
    }

    for case in CASES:
        variant = f"case-{case}"
        mean = draws["mean"].sel(variant=variant).transpose("chain", "draw").to_numpy()
        rho = draws["rho"].sel(variant=variant).transpose("chain", "draw").to_numpy()
        final_reference = references[(orientation, case)][-1]
        moment_values: Mapping[str, np.ndarray] = {
            "mean": mean,
            "mean_squared": mean**2,
            "rho": rho,
            "rho_squared": rho**2,
            "mean_rho": mean * rho,
        }
        for quantity, values in moment_values.items():
            _check_sampling_quantity(
                evidence,
                prior=rho_prior,
                orientation=orientation,
                case=case,
                quantity=quantity,
                values=values,
                reference=float(getattr(final_reference, quantity)),
            )

        prediction_index = predicted.observation_ids.index(
            f"synthetic-quadrature-query-{orientation}-{case}-0:case-{case}"
        )
        for ac, reference_mass in enumerate(final_reference.predictive_masses):
            per_draw_mass = np.exp(
                heterogeneity_log_mass(ac, PREDICTIVE_AN, mean=mean, rho=rho)
            )
            _check_sampling_quantity(
                evidence,
                prior=rho_prior,
                orientation=orientation,
                case=case,
                quantity=f"predictive_ac_{ac}",
                values=per_draw_mass,
                reference=reference_mass,
                actual=float(actual_predictive[ac][prediction_index]),
            )

    print(
        json.dumps(
            {"sampler_fit": fit_evidence, "sampling_comparisons": evidence},
            sort_keys=True,
        )
    )
