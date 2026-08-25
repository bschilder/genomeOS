"""Data-support mask tests (design §7, §7.1b, §10)."""

import numpy as np
import pandas as pd
import pytest
from test_surface_fit import _observations

from genomeos.surfaces.fit import FitConfig, fit_surface
from genomeos.surfaces.mask import (
    SUPPORT_STATES,
    MaskConfig,
    aggregate_cells,
    candidate_cells,
    classify_support,
    evaluate_cells,
)

# Enough draws to converge: fit_surface refuses an unmixed fit (§12).
FAST_CONFIG = FitConfig(draws=800, tune=1000, chains=4)
RANGE_KM = 500.0


def _classify(**kwargs) -> str:
    defaults = {
        "has_observation_centre": np.array([False]),
        "dist_nearest_obs_km": np.array([100.0]),
        "posterior_contraction": np.array([0.3]),
    }
    defaults.update({k: np.array([v]) for k, v in kwargs.items()})
    return classify_support(
        correlation_range_km=RANGE_KM, config=MaskConfig(contraction_threshold=0.9), **defaults
    )[0]


# --- classification rule: tested without sampling; this is the honesty guarantee (§7.1b) ---


def test_cell_containing_an_observation_centre_is_observed():
    assert _classify(has_observation_centre=True) == "observed"


def test_cell_with_no_observation_within_two_ranges_is_unknown():
    assert _classify(dist_nearest_obs_km=2 * RANGE_KM + 1.0) == "unknown"
    assert _classify(dist_nearest_obs_km=np.inf) == "unknown"


def test_cell_in_range_whose_posterior_did_not_contract_is_prior_dominated():
    """Data in range but the value shown is mostly prior — §7.1b's third state."""
    assert _classify(posterior_contraction=0.95) == "prior_dominated"


def test_cell_in_range_with_a_contracted_posterior_is_interpolated():
    assert _classify(posterior_contraction=0.3) == "interpolated"


def test_unknown_beats_prior_dominated_when_there_is_no_data_at_all():
    """No observation in range is a stronger statement than a slack posterior."""
    assert _classify(dist_nearest_obs_km=np.inf, posterior_contraction=0.99) == "unknown"


def test_every_state_produced_is_in_the_declared_enum():
    states = classify_support(
        has_observation_centre=np.array([True, False, False, False]),
        dist_nearest_obs_km=np.array([0.0, 100.0, 100.0, np.inf]),
        posterior_contraction=np.array([0.1, 0.3, 0.95, 0.5]),
        correlation_range_km=RANGE_KM,
        config=MaskConfig(),
    )
    assert set(states) <= set(SUPPORT_STATES)
    assert list(states) == ["observed", "interpolated", "prior_dominated", "unknown"]


# --- §10: masked cells are excluded, and the excluded fraction is returned with the result ---


def _cells(states: list[str], values: list[float]) -> pd.DataFrame:
    return pd.DataFrame({"support": states, "post_mean": values})


def test_prior_dominated_and_unknown_are_excluded_from_statistics():
    cells = _cells(
        ["observed", "interpolated", "prior_dominated", "unknown"], [0.10, 0.20, 0.90, 0.90]
    )
    result = aggregate_cells(cells)
    assert result.value == pytest.approx(0.15), "the two masked cells must not pull the mean up"
    assert result.n_included == 2


def test_the_unmapped_fraction_is_reported_with_the_result():
    cells = _cells(["observed", "unknown", "unknown", "prior_dominated"], [0.1, 0.9, 0.9, 0.9])
    result = aggregate_cells(cells)
    assert result.unmapped_fraction == pytest.approx(0.75)


def test_an_entirely_unmapped_region_yields_no_number_rather_than_a_wrong_one():
    """§9 refusal: emit no number rather than a wrong one."""
    result = aggregate_cells(_cells(["unknown", "prior_dominated"], [0.9, 0.9]))
    assert result.value is None
    assert result.unmapped_fraction == 1.0


def test_sum_statistic_is_supported_and_also_excludes_masked_cells():
    cells = _cells(["observed", "interpolated", "unknown"], [0.1, 0.2, 99.0])
    assert aggregate_cells(cells, statistic="sum").value == pytest.approx(0.3)


def test_unknown_statistic_is_refused():
    with pytest.raises(ValueError, match="statistic"):
        aggregate_cells(_cells(["observed"], [0.1]), statistic="median-ish")


@pytest.fixture(scope="module")
def fitted():
    obs = _observations(n=30)
    return fit_surface(obs, FAST_CONFIG), obs


def test_evaluate_cells_produces_the_spec_columns(fitted):
    fit, obs = fitted
    cells = candidate_cells(obs, MaskConfig())
    frame = evaluate_cells(fit, obs, cells[:12], MaskConfig())
    assert set(frame.columns) == {
        "h3_index", "lat", "lon", "post_mean", "post_sd", "q025", "q975",
        "posterior_contraction", "dist_nearest_obs_km", "eff_n_in_range", "support",
    }
    assert len(frame) == 12
    assert set(frame["support"]) <= set(SUPPORT_STATES)


def test_posterior_contraction_is_a_ratio_against_the_prior(fitted):
    fit, obs = fitted
    frame = evaluate_cells(fit, obs, candidate_cells(obs, MaskConfig())[:12], MaskConfig())
    assert (frame["posterior_contraction"] > 0).all()
    assert fit.prior_frequency_sd > 0


def test_cells_near_observations_carry_effective_sample_size(fitted):
    fit, obs = fitted
    frame = evaluate_cells(fit, obs, candidate_cells(obs, MaskConfig())[:12], MaskConfig())
    assert (frame["eff_n_in_range"] >= 0).all()
    assert frame["eff_n_in_range"].max() > 0, "some cell must be within range of an observation"
