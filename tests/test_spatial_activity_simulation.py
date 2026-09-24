"""Registered synthetic regimes for the spatial activity preflight (#384)."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from genomeos.surfaces.fit import to_unit_sphere


def _inputs():
    record_ids = tuple(f"record-{index:02d}" for index in range(12))
    cohort_ids = tuple(f"cohort-{index // 2:02d}" for index in range(12))
    coordinates = to_unit_sphere(
        np.linspace(-25.0, 30.0, 12),
        np.linspace(-40.0, 90.0, 12),
    )
    denominators = np.arange(40, 160, 10)
    return record_ids, cohort_ids, coordinates, denominators


def test_default_grid_is_frozen_and_covers_every_registered_sensitivity() -> None:
    from genomeos.validation.spatial_activity_simulation import (
        DEFAULT_SEEDS,
        default_spatial_activity_scenarios,
    )

    scenarios = default_spatial_activity_scenarios()

    assert DEFAULT_SEEDS == (42, 43, 44)
    assert len(scenarios) == 18
    assert len({scenario.scenario_id for scenario in scenarios}) == len(scenarios)
    assert {scenario.truth for scenario in scenarios} == {
        "null",
        "localized_weak",
        "localized_strong",
    }
    assert {scenario.seed for scenario in scenarios} == set(DEFAULT_SEEDS)
    assert {scenario.denominator_multiplier for scenario in scenarios} == {0.25, 1.0, 4.0}
    assert {scenario.cohort_sd for scenario in scenarios} == {0.0, 0.5}
    assert all(
        scenario.denominator_multiplier == 1.0 and scenario.cohort_sd == 0.0
        for scenario in scenarios
        if scenario.truth in {"null", "localized_weak"}
    )


def test_null_truth_is_exactly_ordinary_beta_binomial() -> None:
    from genomeos.validation.spatial_activity_simulation import (
        default_spatial_activity_scenarios,
        simulate_spatial_activity_scenario,
    )

    record_ids, cohorts, coordinates, denominators = _inputs()
    scenario = next(
        item
        for item in default_spatial_activity_scenarios()
        if item.truth == "null" and item.seed == 42
    )
    result = simulate_spatial_activity_scenario(
        record_ids,
        coordinates,
        denominators,
        cohort_ids=cohorts,
        scenario=scenario,
    )

    assert result.scenario == scenario
    assert result.record_ids == record_ids
    assert result.an == tuple(int(value) for value in denominators)
    assert result.activity_probability_truth == (1.0,) * len(record_ids)
    np.testing.assert_allclose(
        result.marginal_mean_truth,
        result.observation_conditional_mean_truth,
    )
    assert set(result.cohort_logit_offset_truth) == {0.0}


def test_localized_fields_encode_weak_and_strong_component_separation() -> None:
    from genomeos.validation.spatial_activity_simulation import (
        default_spatial_activity_scenarios,
        simulate_spatial_activity_scenario,
    )

    record_ids, cohorts, coordinates, denominators = _inputs()
    by_truth = {
        scenario.truth: simulate_spatial_activity_scenario(
            record_ids,
            coordinates,
            denominators,
            cohort_ids=cohorts,
            scenario=scenario,
        )
        for scenario in default_spatial_activity_scenarios()
        if scenario.seed == 42
        and scenario.denominator_multiplier == 1.0
        and scenario.cohort_sd == 0.0
    }

    weak_q = np.asarray(by_truth["localized_weak"].activity_probability_truth)
    weak_p = np.asarray(by_truth["localized_weak"].reference_conditional_mean_truth)
    strong_q = np.asarray(by_truth["localized_strong"].activity_probability_truth)
    strong_p = np.asarray(by_truth["localized_strong"].reference_conditional_mean_truth)
    assert np.ptp(weak_q) > 0.3
    assert np.ptp(strong_q) > 0.7
    assert np.corrcoef(weak_q, weak_p)[0, 1] > 0.9
    assert abs(np.corrcoef(strong_q, strong_p)[0, 1]) < 0.75


def test_denominator_and_cohort_sensitivities_are_explicit() -> None:
    from genomeos.validation.spatial_activity_simulation import (
        default_spatial_activity_scenarios,
        simulate_spatial_activity_scenario,
    )

    record_ids, cohorts, coordinates, denominators = _inputs()
    scenarios = default_spatial_activity_scenarios()
    selected = {
        (scenario.denominator_multiplier, scenario.cohort_sd): scenario
        for scenario in scenarios
        if scenario.truth == "localized_strong" and scenario.seed == 43
    }
    low = simulate_spatial_activity_scenario(
        record_ids,
        coordinates,
        denominators,
        cohort_ids=cohorts,
        scenario=selected[(0.25, 0.0)],
    )
    high = simulate_spatial_activity_scenario(
        record_ids,
        coordinates,
        denominators,
        cohort_ids=cohorts,
        scenario=selected[(4.0, 0.0)],
    )
    heterogeneous = simulate_spatial_activity_scenario(
        record_ids,
        coordinates,
        denominators,
        cohort_ids=cohorts,
        scenario=selected[(1.0, 0.5)],
    )

    assert low.an == tuple(int(round(value * 0.25)) for value in denominators)
    assert high.an == tuple(int(value * 4) for value in denominators)
    offsets = np.asarray(heterogeneous.cohort_logit_offset_truth)
    for index in range(0, len(offsets), 2):
        assert offsets[index] == offsets[index + 1]
    assert np.std(offsets) > 0.0


def test_simulation_is_deterministic_under_row_reordering() -> None:
    from genomeos.validation.spatial_activity_simulation import (
        default_spatial_activity_scenarios,
        simulate_spatial_activity_scenario,
    )

    record_ids, cohorts, coordinates, denominators = _inputs()
    scenario = next(
        item
        for item in default_spatial_activity_scenarios()
        if item.truth == "localized_strong"
        and item.seed == 44
        and item.cohort_sd == 0.5
    )
    expected = simulate_spatial_activity_scenario(
        record_ids,
        coordinates,
        denominators,
        cohort_ids=cohorts,
        scenario=scenario,
    )
    order = np.array([7, 0, 11, 3, 9, 1, 5, 2, 8, 4, 10, 6])
    reordered = simulate_spatial_activity_scenario(
        tuple(record_ids[index] for index in order),
        coordinates[order],
        denominators[order],
        cohort_ids=tuple(cohorts[index] for index in order),
        scenario=scenario,
    )
    by_id = {
        record_id: (
            reordered.ac[index],
            reordered.active[index],
            reordered.reference_conditional_mean_truth[index],
            reordered.observation_conditional_mean_truth[index],
            reordered.activity_probability_truth[index],
            reordered.cohort_logit_offset_truth[index],
        )
        for index, record_id in enumerate(reordered.record_ids)
    }
    for index, record_id in enumerate(expected.record_ids):
        assert by_id[record_id] == (
            expected.ac[index],
            expected.active[index],
            expected.reference_conditional_mean_truth[index],
            expected.observation_conditional_mean_truth[index],
            expected.activity_probability_truth[index],
            expected.cohort_logit_offset_truth[index],
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("truth", "unknown"),
        ("denominator_multiplier", 0.0),
        ("cohort_sd", -0.1),
        ("concentration", 0.0),
        ("seed", -1),
    ],
)
def test_scenario_refuses_invalid_values(field: str, value: object) -> None:
    from genomeos.validation.spatial_activity_simulation import (
        default_spatial_activity_scenarios,
    )

    with pytest.raises(ValueError):
        replace(default_spatial_activity_scenarios()[0], **{field: value})


@pytest.mark.parametrize(
    ("mutator", "match"),
    [
        (
            lambda ids, cohorts, x, an: (ids[:-1], cohorts, x, an),
            "record_ids",
        ),
        (
            lambda ids, cohorts, x, an: (ids, cohorts[:-1], x, an),
            "cohort_ids",
        ),
        (
            lambda ids, cohorts, x, an: (ids, cohorts, x[:, :2], an),
            "coordinates",
        ),
        (
            lambda ids, cohorts, x, an: (ids, cohorts, x * 2.0, an),
            "unit-sphere",
        ),
        (
            lambda ids, cohorts, x, an: (ids, cohorts, x, an.astype(float) + 0.5),
            "integer",
        ),
        (
            lambda ids, cohorts, x, an: ((ids[0],) * len(ids), cohorts, x, an),
            "unique",
        ),
        (
            lambda ids, cohorts, x, an: (ids, cohorts, np.repeat(x[:1], len(x), axis=0), an),
            "distinct",
        ),
    ],
)
def test_simulation_refuses_invalid_inputs(mutator, match: str) -> None:
    from genomeos.validation.spatial_activity_simulation import (
        default_spatial_activity_scenarios,
        simulate_spatial_activity_scenario,
    )

    record_ids, cohorts, coordinates, denominators = _inputs()
    record_ids, cohorts, coordinates, denominators = mutator(
        record_ids,
        cohorts,
        coordinates,
        denominators,
    )
    with pytest.raises(ValueError, match=match):
        simulate_spatial_activity_scenario(
            record_ids,
            coordinates,
            denominators,
            cohort_ids=cohorts,
            scenario=default_spatial_activity_scenarios()[0],
        )
