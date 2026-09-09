"""Observation-aware GP adapter tests (design §§4–5, 7.1, 8, 12; #191)."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from unittest import mock

import numpy as np
import pymc as pm
import pytest
import xarray as xr

from genomeos.surfaces.fit import FitConfig, SurfaceFit, to_unit_sphere
from genomeos.surfaces.observation import ObservationModelMetadata, SurveyQueries
from genomeos.surfaces.observation_prediction import predict_new_cohort_parameters


def _metadata(
    *,
    fitted_designs: tuple[str, ...] = ("reference", "design-a", "design-b"),
    cohort_effect_applied: bool = True,
    nugget_applied: bool = False,
    likelihood: str = "beta_binomial",
) -> ObservationModelMetadata:
    return ObservationModelMetadata(
        convention="new_cohort_count_v1",
        fitted_designs=fitted_designs,
        training_cohort_ids=("training-a", "training-b"),
        cohort_effect_applied=cohort_effect_applied,
        nugget_applied=nugget_applied,
        likelihood=likelihood,
    )


def _posterior_variables() -> dict[str, xr.DataArray]:
    design = xr.DataArray(
        np.array(
            [
                [[0.1, 0.2], [0.3, 0.4]],
                [[0.5, 0.6], [0.7, 0.8]],
            ]
        ),
        dims=("chain", "draw", "design_position"),
        coords={"chain": [0, 1], "draw": [2, 3], "design_position": [0, 1]},
    )
    cohort_sd = xr.DataArray(
        np.zeros((2, 2)),
        dims=("chain", "draw"),
        coords={"chain": [0, 1], "draw": [2, 3]},
    )
    concentration = xr.DataArray(
        np.array([[10.0, 20.0], [30.0, 40.0]]),
        dims=("chain", "draw"),
        coords={"chain": [0, 1], "draw": [2, 3]},
    )
    return {
        "beta_design": design.sel(
            chain=[1, 0], draw=[3, 2], design_position=[1, 0]
        ).transpose("design_position", "draw", "chain"),
        "cohort_sd": cohort_sd.sel(chain=[1, 0], draw=[3, 2]).transpose("draw", "chain"),
        "concentration": concentration.sel(chain=[1, 0], draw=[3, 2]).transpose(
            "draw", "chain"
        ),
    }


def _model(*, latent_node: bool = True) -> pm.Model:
    with pm.Model() as model:
        x_pred = pm.Data("x_pred", np.zeros((1, 3), dtype=np.float64))
        if latent_node:
            pm.Deterministic("latent_logit_pred", x_pred[:, 0])
    return model


def _fit(
    *,
    metadata: ObservationModelMetadata | None = None,
    posterior: dict[str, xr.DataArray] | None = None,
    latent_node: bool = True,
) -> SurfaceFit:
    prediction_metadata = metadata if metadata is not None else _metadata()
    return SurfaceFit(
        variant_id="chr11-5227002-T-A",
        config=FitConfig(),
        beta_design_applied=len(prediction_metadata.fitted_designs) > 1,
        lengthscale_prior_km=(100.0, 1_000.0),
        beta_cohort_applied=prediction_metadata.cohort_effect_applied,
        design_levels=prediction_metadata.fitted_designs[1:],
        prior_frequency_sd=0.1,
        inducing_spacing_ratio=None,
        correlation_range_km=500.0,
        idata=SimpleNamespace(
            posterior=_posterior_variables() if posterior is None else posterior
        ),
        _model=_model(latent_node=latent_node),
        _centre=np.zeros(3),
        _scale=np.ones(3),
        prediction_metadata=prediction_metadata,
    )


def _queries() -> SurveyQueries:
    return SurveyQueries(
        observation_ids=("observation-b", "observation-a"),
        cohort_ids=("new-cohort", "new-cohort"),
        sampling_designs=("design-b", "reference"),
        lat=(5.0, 0.0),
        lon=(10.0, 0.0),
    )


def _known_latent_boundary(expected_points: np.ndarray | None = None):
    def sample_posterior_predictive(idata, *, var_names, random_seed, progressbar):
        del idata
        assert var_names == ["latent_logit_pred"]
        assert random_seed == 42
        assert progressbar is False
        if expected_points is not None:
            model = pm.modelcontext(None)
            np.testing.assert_array_equal(model["x_pred"].get_value(), expected_points)
        latent = xr.DataArray(
            np.array(
                [
                    [[1.0, 2.0], [3.0, 4.0]],
                    [[5.0, 6.0], [7.0, 8.0]],
                ]
            ),
            dims=("chain", "draw", "point_position"),
            coords={"chain": [0, 1], "draw": [2, 3], "point_position": [0, 1]},
        )
        reordered = latent.sel(
            chain=[1, 0], draw=[3, 2], point_position=[1, 0]
        ).transpose("point_position", "draw", "chain")
        return SimpleNamespace(posterior_predictive={"latent_logit_pred": reordered})

    return sample_posterior_predictive


def test_adapter_aligns_named_draw_and_design_axes_before_composition():
    fit = _fit()
    queries = _queries()
    expected_points = to_unit_sphere([0.0, 5.0], [0.0, 10.0])

    with mock.patch(
        "pymc.sample_posterior_predictive",
        side_effect=_known_latent_boundary(expected_points),
    ):
        parameters = predict_new_cohort_parameters(fit, queries)

    assert parameters.draw_ids == ((0, 2), (0, 3), (1, 2), (1, 3))
    np.testing.assert_array_equal(
        parameters.mean_draws,
        np.array(
            [
                [0.9002495108803148, 0.7310585786300049],
                [0.9878715650157257, 0.9525741268224334],
                [0.9986414800495711, 0.9933071490757153],
                [0.9998492896419403, 0.9990889488055994],
            ]
        ),
    )
    np.testing.assert_array_equal(
        parameters.concentration,
        np.array([[10.0, 10.0], [20.0, 20.0], [30.0, 30.0], [40.0, 40.0]]),
    )


def test_surface_fit_public_method_delegates_to_the_aligned_adapter():
    fit = _fit()
    with mock.patch("pymc.sample_posterior_predictive", side_effect=_known_latent_boundary()):
        direct = predict_new_cohort_parameters(fit, _queries())
        public = fit.predict_new_cohort_parameters(_queries())
    assert public.draw_ids == direct.draw_ids
    np.testing.assert_array_equal(public.mean_draws, direct.mean_draws)
    np.testing.assert_array_equal(public.concentration, direct.concentration)


@pytest.mark.parametrize("cohort_applied", [False, True])
@pytest.mark.parametrize("nugget_applied", [False, True])
def test_adapter_extracts_every_fitted_and_omitted_random_effect_combination(
    cohort_applied, nugget_applied
):
    metadata = _metadata(
        cohort_effect_applied=cohort_applied,
        nugget_applied=nugget_applied,
    )
    posterior = _posterior_variables()
    if not cohort_applied:
        posterior.pop("cohort_sd")
    if nugget_applied:
        scalar = xr.DataArray(
            np.zeros((2, 2)),
            dims=("chain", "draw"),
            coords={"chain": [0, 1], "draw": [2, 3]},
        )
        posterior["nugget_sd"] = scalar.sel(chain=[1, 0], draw=[3, 2]).transpose(
            "draw", "chain"
        )
    fit = _fit(metadata=metadata, posterior=posterior)

    with mock.patch("pymc.sample_posterior_predictive", side_effect=_known_latent_boundary()):
        parameters = predict_new_cohort_parameters(fit, _queries())

    assert parameters.mean_draws.shape == (4, 2)
    assert np.isfinite(parameters.mean_draws).all()
    np.testing.assert_array_equal(
        parameters.concentration,
        np.array([[10.0, 10.0], [20.0, 20.0], [30.0, 30.0], [40.0, 40.0]]),
    )


def test_coordinate_equivalences_are_sampled_once_and_expanded_in_submission_order():
    metadata = _metadata(
        fitted_designs=("reference",),
        cohort_effect_applied=False,
        likelihood="binomial",
    )
    fit = _fit(metadata=metadata, posterior={})
    queries = SurveyQueries(
        observation_ids=("a", "b", "c", "d", "e", "f"),
        cohort_ids=("new",) * 6,
        sampling_designs=("reference",) * 6,
        lat=(10.0, 10.0, 0.0, 0.0, 90.0, 90.0),
        lon=(20.0, 20.0, -180.0, 180.0, -170.0, 170.0),
    )
    expected_points = to_unit_sphere([0.0, 10.0, 90.0], [180.0, 20.0, 0.0])

    def boundary(idata, *, var_names, random_seed, progressbar):
        del idata, var_names, random_seed, progressbar
        model = pm.modelcontext(None)
        np.testing.assert_array_equal(model["x_pred"].get_value(), expected_points)
        latent = xr.DataArray(
            np.array([[[0.1, 0.2, 0.3]], [[0.4, 0.5, 0.6]]]),
            dims=("chain", "draw", "point_position"),
            coords={"chain": [1, 0], "draw": [3], "point_position": [0, 1, 2]},
        ).transpose("point_position", "draw", "chain")
        return SimpleNamespace(posterior_predictive={"latent_logit_pred": latent})

    with mock.patch("pymc.sample_posterior_predictive", side_effect=boundary):
        parameters = predict_new_cohort_parameters(fit, queries)

    assert parameters.draw_ids == ((0, 3), (1, 3))
    np.testing.assert_array_equal(
        parameters.mean_draws[:, 0], parameters.mean_draws[:, 1]
    )
    np.testing.assert_array_equal(
        parameters.mean_draws[:, 2], parameters.mean_draws[:, 3]
    )
    np.testing.assert_array_equal(
        parameters.mean_draws[:, 4], parameters.mean_draws[:, 5]
    )


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ("metadata", "metadata"),
        ("node", "latent_logit_pred"),
        ("unsupported_design", "not fitted"),
        ("seen_cohort", "seen cohort"),
        ("seed", "seed"),
    ],
)
def test_capability_and_query_refusals_precede_the_pymc_draw_boundary(change, message):
    fit = _fit()
    queries = _queries()
    seed: object = 42
    if change == "metadata":
        object.__setattr__(fit, "prediction_metadata", None)
    elif change == "node":
        object.__setattr__(fit, "_model", _model(latent_node=False))
    elif change == "unsupported_design":
        queries = replace(queries, sampling_designs=("missing", "reference"))
    elif change == "seen_cohort":
        queries = replace(queries, cohort_ids=("training-a", "training-a"))
    else:
        seed = True

    with mock.patch(
        "pymc.sample_posterior_predictive",
        side_effect=AssertionError("the expensive draw boundary must not be called"),
    ):
        with pytest.raises(ValueError, match=message):
            predict_new_cohort_parameters(fit, queries, seed=seed)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("missing", "metadata", "message"),
    [
        ("beta_design", _metadata(), "beta_design"),
        ("cohort_sd", _metadata(), "cohort_sd"),
        (
            "nugget_sd",
            _metadata(cohort_effect_applied=False, nugget_applied=True),
            "nugget_sd",
        ),
        ("concentration", _metadata(), "concentration"),
    ],
)
def test_missing_required_posterior_variables_refuse_before_sampling(missing, metadata, message):
    posterior = _posterior_variables()
    if metadata.nugget_applied:
        posterior["nugget_sd"] = posterior["cohort_sd"]
    if not metadata.cohort_effect_applied:
        posterior.pop("cohort_sd")
    if metadata.likelihood == "binomial":
        posterior.pop("concentration")
    posterior.pop(missing)
    fit = _fit(metadata=metadata, posterior=posterior)
    with mock.patch(
        "pymc.sample_posterior_predictive",
        side_effect=AssertionError("the expensive draw boundary must not be called"),
    ):
        with pytest.raises(ValueError, match=message):
            predict_new_cohort_parameters(fit, _queries())


def test_design_effect_requires_one_positional_event_axis_before_sampling():
    posterior = _posterior_variables()
    posterior["beta_design"] = posterior["cohort_sd"]
    fit = _fit(posterior=posterior)
    with mock.patch(
        "pymc.sample_posterior_predictive",
        side_effect=AssertionError("the expensive draw boundary must not be called"),
    ):
        with pytest.raises(ValueError, match="event axis"):
            predict_new_cohort_parameters(fit, _queries())


@pytest.mark.parametrize("effect", ["beta_design", "cohort_sd", "nugget_sd", "concentration"])
def test_posterior_effects_cannot_be_silently_ignored_when_metadata_omits_them(effect):
    metadata = _metadata(
        fitted_designs=("reference",) if effect == "beta_design" else ("reference", "design-a"),
        cohort_effect_applied=effect != "cohort_sd",
        nugget_applied=effect != "nugget_sd",
        likelihood="binomial" if effect == "concentration" else "beta_binomial",
    )
    posterior = _posterior_variables()
    posterior["nugget_sd"] = posterior["cohort_sd"]
    if len(metadata.fitted_designs) == 2:
        posterior["beta_design"] = posterior["beta_design"].sel(design_position=[0])
    if not metadata.cohort_effect_applied and effect != "cohort_sd":
        posterior.pop("cohort_sd")
    if not metadata.nugget_applied and effect != "nugget_sd":
        posterior.pop("nugget_sd")
    if metadata.likelihood == "binomial" and effect != "concentration":
        posterior.pop("concentration")
    fit = _fit(metadata=metadata, posterior=posterior)

    with mock.patch(
        "pymc.sample_posterior_predictive",
        side_effect=AssertionError("the expensive draw boundary must not be called"),
    ):
        with pytest.raises(ValueError, match=effect):
            predict_new_cohort_parameters(
                fit,
                replace(_queries(), sampling_designs=(metadata.fitted_designs[-1], "reference")),
            )


@pytest.mark.parametrize("coordinate_problem", ["repeated", "different"])
def test_posterior_coordinate_labels_must_be_unique_and_equal_before_sampling(
    coordinate_problem,
):
    posterior = _posterior_variables()
    if coordinate_problem == "repeated":
        posterior["cohort_sd"] = xr.DataArray(
            np.zeros((2, 2)),
            dims=("chain", "draw"),
            coords={"chain": [0, 0], "draw": [2, 3]},
        )
        message = "unique"
    else:
        posterior["cohort_sd"] = xr.DataArray(
            np.zeros((2, 2)),
            dims=("chain", "draw"),
            coords={"chain": [0, 2], "draw": [2, 3]},
        )
        message = "coordinate labels"
    fit = _fit(posterior=posterior)
    with mock.patch(
        "pymc.sample_posterior_predictive",
        side_effect=AssertionError("the expensive draw boundary must not be called"),
    ):
        with pytest.raises(ValueError, match=message):
            predict_new_cohort_parameters(fit, _queries())


@pytest.mark.parametrize("malformation", ["missing", "event_axis", "different_coordinates"])
def test_named_latent_output_is_required_and_draw_aligned(malformation):
    fit = _fit()

    def boundary(idata, *, var_names, random_seed, progressbar):
        del idata, var_names, random_seed, progressbar
        if malformation == "missing":
            return SimpleNamespace(posterior_predictive={})
        dims = ("chain", "draw") if malformation == "event_axis" else (
            "chain",
            "draw",
            "point_position",
        )
        shape = (2, 2) if malformation == "event_axis" else (2, 2, 2)
        coords = {"chain": [0, 1], "draw": [2, 3]}
        if malformation == "different_coordinates":
            coords["chain"] = [0, 2]
        if len(shape) == 3:
            coords["point_position"] = [0, 1]
        variable = xr.DataArray(np.zeros(shape), dims=dims, coords=coords)
        return SimpleNamespace(posterior_predictive={"latent_logit_pred": variable})

    with mock.patch("pymc.sample_posterior_predictive", side_effect=boundary):
        with pytest.raises(ValueError, match="latent_logit_pred"):
            predict_new_cohort_parameters(fit, _queries())
