from __future__ import annotations

import numpy as np
import pytest

from genomeos.surfaces.fit import to_unit_sphere


def _inputs() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    observed = to_unit_sphere(
        np.array([-8.0, 0.0, 9.0, 15.0]),
        np.array([-12.0, 2.0, 18.0, 28.0]),
    )
    predicted = to_unit_sphere(np.array([-4.0, 12.0]), np.array([-6.0, 22.0]))
    return observed, np.array([0, 1, 3, 0]), np.array([20, 30, 40, 25]), predicted


def _config():
    from genomeos.surfaces.spatial_activity_model import SpatialActivityModelConfig

    return SpatialActivityModelConfig(
        hsgp_m=(2, 2, 2),
        hsgp_c=1.5,
        lengthscale_mu=-2.0,
        lengthscale_sigma=0.4,
        conditional_intercept_mu=-3.5,
        conditional_intercept_sigma=1.5,
        conditional_amplitude_sigma=1.0,
        activity_intercept_mu=2.5,
        activity_intercept_sigma=1.0,
        activity_amplitude_sigma=1.0,
        concentration_sigma=100.0,
        cohort_sd_sigma=0.5,
    )


def test_candidate_builds_two_continuous_fields_and_marginalized_observation() -> None:
    from genomeos.surfaces.spatial_activity_model import build_spatial_activity_model

    x, ac, an, x_pred = _inputs()
    graph = build_spatial_activity_model(
        x,
        ac,
        an,
        x_pred,
        cohort_index=np.array([0, 0, 1, 1]),
        mode="spatial_activity",
        config=_config(),
    )

    assert graph.mode == "spatial_activity"
    assert graph.cohort_effect_applied is True
    assert graph.n_observations == 4
    assert graph.n_predictions == 2
    assert {
        "conditional_mean",
        "conditional_mean_pred",
        "activity_probability",
        "activity_probability_pred",
        "concentration",
        "obs",
    } <= set(graph.model.named_vars)
    assert "beta_cohort" in graph.model.named_vars
    assert not any("active" in variable.name for variable in graph.model.free_RVs)
    assert np.isfinite(graph.model.compile_logp()(graph.model.initial_point()))


def test_ordinary_arm_uses_same_contract_with_activity_fixed_to_one() -> None:
    from genomeos.surfaces.spatial_activity_model import build_spatial_activity_model

    x, ac, an, x_pred = _inputs()
    graph = build_spatial_activity_model(
        x,
        ac,
        an,
        x_pred,
        cohort_index=np.arange(len(ac)),
        mode="ordinary",
        config=_config(),
    )

    assert graph.cohort_effect_applied is False
    assert "activity_field" not in graph.model.named_vars
    assert "activity_lengthscale" not in graph.model.named_vars
    assert "beta_cohort" not in graph.model.named_vars
    assert np.array_equal(graph.model["activity_probability"].eval(), np.ones(len(ac)))
    assert np.array_equal(
        graph.model["activity_probability_pred"].eval(), np.ones(len(x_pred))
    )
    assert np.isfinite(graph.model.compile_logp()(graph.model.initial_point()))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("hsgp_m", (2, 0, 2)),
        ("hsgp_m", (2, 2)),
        ("hsgp_c", 1.0),
        ("lengthscale_sigma", 0.0),
        ("conditional_intercept_sigma", np.inf),
        ("conditional_amplitude_sigma", -1.0),
        ("activity_intercept_sigma", 0.0),
        ("activity_amplitude_sigma", np.nan),
        ("concentration_sigma", 0.0),
        ("cohort_sd_sigma", -0.5),
    ],
)
def test_config_refuses_invalid_values(field: str, value: object) -> None:
    from dataclasses import replace

    with pytest.raises(ValueError):
        replace(_config(), **{field: value})


@pytest.mark.parametrize("mode", ["activity", "", None, 1])
def test_model_refuses_unknown_mode(mode: object) -> None:
    from genomeos.surfaces.spatial_activity_model import build_spatial_activity_model

    x, ac, an, x_pred = _inputs()
    with pytest.raises(ValueError, match="mode"):
        build_spatial_activity_model(
            x,
            ac,
            an,
            x_pred,
            cohort_index=np.array([0, 0, 1, 1]),
            mode=mode,
            config=_config(),
        )


@pytest.mark.parametrize(
    ("mutator", "match"),
    [
        (lambda x, ac, an, xp, ci: (x[:, :2], ac, an, xp, ci), "x_observed"),
        (
            lambda x, ac, an, xp, ci: (x * 2.0, ac, an, xp, ci),
            "unit-sphere",
        ),
        (lambda x, ac, an, xp, ci: (x, ac[:-1], an, xp, ci), "ac and an"),
        (lambda x, ac, an, xp, ci: (x, ac + 0.5, an, xp, ci), "integer"),
        (lambda x, ac, an, xp, ci: (x, ac, np.zeros_like(an), xp, ci), "positive"),
        (lambda x, ac, an, xp, ci: (x, an + 1, an, xp, ci), "between zero and AN"),
        (lambda x, ac, an, xp, ci: (x, ac, an, xp[:0], ci), "x_prediction"),
        (
            lambda x, ac, an, xp, ci: (x, ac, an, xp, np.array([0, 0, 2, 2])),
            "contiguous",
        ),
        (lambda x, ac, an, xp, ci: (x, ac, an, xp, ci[:-1]), "cohort_index"),
    ],
)
def test_model_refuses_invalid_inputs(mutator, match: str) -> None:
    from genomeos.surfaces.spatial_activity_model import build_spatial_activity_model

    values = _inputs() + (np.array([0, 0, 1, 1]),)
    x, ac, an, x_pred, cohort_index = mutator(*values)
    with pytest.raises(ValueError, match=match):
        build_spatial_activity_model(
            x,
            ac,
            an,
            x_pred,
            cohort_index=cohort_index,
            mode="spatial_activity",
            config=_config(),
        )


def test_model_refuses_wrong_config_type() -> None:
    from genomeos.surfaces.spatial_activity_model import build_spatial_activity_model

    x, ac, an, x_pred = _inputs()
    with pytest.raises(ValueError, match="config"):
        build_spatial_activity_model(
            x,
            ac,
            an,
            x_pred,
            cohort_index=np.array([0, 0, 1, 1]),
            mode="spatial_activity",
            config=object(),
        )
