"""GP-amplitude prior sensitivity tests (Atlas design §§7–8; issue #103)."""

from __future__ import annotations

import numpy as np
import pytest

from genomeos.validation.amplitude_prior_sensitivity import (
    AmplitudeSensitivityResult,
    evaluate_amplitude_prior_sensitivity,
    half_normal_importance_weights,
)


def _synthetic_inputs() -> dict[str, np.ndarray]:
    nordic = np.array([0.005, 0.006, 0.010, 0.020])
    peak = np.array([0.150, 0.140, 0.120, 0.100])
    return {
        "amplitude": np.array([0.1, 0.5, 1.0, 2.0]),
        "intercept": np.array([-5.4, -5.2, -4.8, -4.2]),
        "frequency_draws": np.column_stack([nordic, nordic, peak, peak]),
        "population": np.array([1.0, 3.0, 2.0, 2.0]),
        "nordic_mask": np.array([True, True, False, False]),
        "peak_mask": np.array([False, False, True, True]),
    }


def test_half_normal_importance_weights_match_density_ratio() -> None:
    amplitude = np.array([0.25, 1.0, 2.0])

    weights = half_normal_importance_weights(
        amplitude, original_scale=1.0, candidate_scale=0.5
    )

    expected = 2.0 * np.exp(-0.5 * amplitude**2 * (4.0 - 1.0))
    expected /= expected.sum()
    np.testing.assert_allclose(weights, expected, rtol=1e-15, atol=0.0)
    assert weights.sum() == pytest.approx(1.0)


def test_vectorized_sensitivity_preserves_draw_alignment_and_applies_gate() -> None:
    result = evaluate_amplitude_prior_sensitivity(
        **_synthetic_inputs(),
        original_scale=1.0,
        candidate_scales=(1.0, 0.5),
        minimum_effective_sample_size=1.0,
        maximum_single_weight=1.0,
    )

    assert isinstance(result, AmplitudeSensitivityResult)
    assert result.n_draws == 4
    assert result.n_cells == 4
    assert result.nordic_cells == 2
    assert result.peak_cells == 2
    baseline, tighter = result.candidates
    assert baseline.scale == 1.0
    assert baseline.decision_reason == "reference_prior"
    assert not baseline.advance_to_full_refit
    assert tighter.scale == 0.5
    assert tighter.importance_diagnostics_pass
    assert tighter.advance_to_full_refit
    assert tighter.summaries["population_weighted_nordic_frequency"].mean < (
        baseline.summaries["population_weighted_nordic_frequency"].mean
    )
    assert tighter.summaries["endemic_minus_nordic_frequency"].median >= (
        baseline.summaries["endemic_minus_nordic_frequency"].median
    )


def test_candidate_fails_when_tighter_prior_raises_background() -> None:
    values = _synthetic_inputs()
    values["frequency_draws"] = values["frequency_draws"][::-1].copy()

    result = evaluate_amplitude_prior_sensitivity(
        **values,
        original_scale=1.0,
        candidate_scales=(1.0, 0.5),
        minimum_effective_sample_size=1.0,
        maximum_single_weight=1.0,
    )

    candidate = result.candidates[1]
    assert not candidate.advance_to_full_refit
    assert candidate.decision_reason == (
        "fails_importance_diagnostics_or_background_peak_direction"
    )


@pytest.mark.parametrize(
    ("change", "match"),
    [
        ({"amplitude": np.array([0.1, np.nan, 1.0, 2.0])}, "amplitude"),
        ({"frequency_draws": np.ones((3, 4))}, "draw"),
        ({"frequency_draws": np.full((4, 4), 1.01)}, "between zero and one"),
        ({"population": np.array([1.0, -1.0, 2.0, 2.0])}, "population"),
        ({"nordic_mask": np.array([False, False, False, False])}, "nordic"),
        ({"peak_mask": np.array([True, False, True, True])}, "disjoint"),
    ],
)
def test_sensitivity_refuses_malformed_aligned_inputs(
    change: dict[str, np.ndarray], match: str
) -> None:
    values = {**_synthetic_inputs(), **change}

    with pytest.raises(ValueError, match=match):
        evaluate_amplitude_prior_sensitivity(
            **values,
            original_scale=1.0,
            candidate_scales=(1.0, 0.5),
            minimum_effective_sample_size=1.0,
            maximum_single_weight=1.0,
        )


@pytest.mark.parametrize(
    ("scales", "match"),
    [
        ((0.75, 0.5), "original scale exactly once"),
        ((1.0, 1.0, 0.5), "unique"),
        ((1.0, 1.25), "no greater"),
        ((1.0, 0.0), "positive"),
    ],
)
def test_sensitivity_refuses_unfrozen_candidate_sets(
    scales: tuple[float, ...], match: str
) -> None:
    with pytest.raises(ValueError, match=match):
        evaluate_amplitude_prior_sensitivity(
            **_synthetic_inputs(),
            original_scale=1.0,
            candidate_scales=scales,
            minimum_effective_sample_size=1.0,
            maximum_single_weight=1.0,
        )


def test_importance_gate_failure_cannot_advance_candidate() -> None:
    result = evaluate_amplitude_prior_sensitivity(
        **_synthetic_inputs(),
        original_scale=1.0,
        candidate_scales=(1.0, 0.2),
        minimum_effective_sample_size=3.9,
        maximum_single_weight=0.3,
    )

    candidate = result.candidates[1]
    assert not candidate.importance_diagnostics_pass
    assert not candidate.advance_to_full_refit
