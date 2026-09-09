"""Unseen-cohort observation parameter tests (design §§4–5, 7.1, 8, 12; #191)."""

from __future__ import annotations

import numpy as np
import pytest
from scipy.special import expit

from genomeos.surfaces.observation import (
    ObservationModelMetadata,
    ObservationParameters,
    SurveyQueries,
    compose_unseen_observations,
)
from genomeos.validation.predictive import CountPredictive


def _queries(
    *,
    observation_ids: tuple[str, ...] = ("z", "a", "m"),
    cohort_ids: tuple[str, ...] = ("cohort_b", "cohort_a", "cohort_b"),
    sampling_designs: tuple[str, ...] = ("reference", "reference", "reference"),
    lat: tuple[float, ...] = (0.0, 1.0, 2.0),
    lon: tuple[float, ...] = (3.0, 4.0, 5.0),
) -> SurveyQueries:
    return SurveyQueries(observation_ids, cohort_ids, sampling_designs, lat, lon)


def _metadata(
    *,
    fitted_designs: tuple[str, ...] = ("reference",),
    cohort_effect_applied: bool = False,
    nugget_applied: bool = False,
    likelihood: str = "binomial",
) -> ObservationModelMetadata:
    return ObservationModelMetadata(
        convention="new_cohort_count_v1",
        fitted_designs=fitted_designs,
        training_cohort_ids=("training_a", "training_b"),
        cohort_effect_applied=cohort_effect_applied,
        nugget_applied=nugget_applied,
        likelihood=likelihood,
    )


def _compose(
    *,
    queries: SurveyQueries | None = None,
    metadata: ObservationModelMetadata | None = None,
    latent_logit_draws: object | None = None,
    draw_ids: object = ((4, 8), (4, 9)),
    design_effect_draws: object | None = None,
    cohort_sd_draws: object | None = None,
    nugget_sd_draws: object | None = None,
    concentration_draws: object | None = None,
    seed: object = 42,
) -> ObservationParameters:
    queries = _queries() if queries is None else queries
    metadata = _metadata() if metadata is None else metadata
    latent_logit_draws = (
        np.zeros((2, len(queries.observation_ids)))
        if latent_logit_draws is None
        else latent_logit_draws
    )
    design_effect_draws = (
        np.empty((2, len(metadata.fitted_designs) - 1))
        if design_effect_draws is None
        else design_effect_draws
    )
    return compose_unseen_observations(
        latent_logit_draws,
        draw_ids=draw_ids,
        queries=queries,
        metadata=metadata,
        design_effect_draws=design_effect_draws,
        cohort_sd_draws=cohort_sd_draws,
        nugget_sd_draws=nugget_sd_draws,
        concentration_draws=concentration_draws,
        seed=seed,
    )


def test_design_contrasts_use_the_actual_fitted_reference():
    queries = SurveyQueries(
        observation_ids=("a", "b"), cohort_ids=("new", "new"),
        sampling_designs=("healthy_reference", "population_random"),
        lat=(0.0, 1.0), lon=(0.0, 1.0),
    )
    metadata = ObservationModelMetadata(
        convention="new_cohort_count_v1",
        fitted_designs=("healthy_reference", "population_random"),
        training_cohort_ids=("training",), cohort_effect_applied=False,
        nugget_applied=False, likelihood="beta_binomial",
    )
    result = compose_unseen_observations(
        np.array([[-2.0, -2.0], [-1.0, -1.0]]),
        draw_ids=((0, 0), (0, 1)), queries=queries, metadata=metadata,
        design_effect_draws=np.array([[0.5], [1.0]]),
        cohort_sd_draws=None, nugget_sd_draws=None,
        concentration_draws=np.array([20.0, 40.0]), seed=42,
    )
    np.testing.assert_allclose(result.mean_draws, expit([[-2.0, -1.5], [-1.0, 0.0]]))
    np.testing.assert_array_equal(result.concentration, [[20.0, 20.0], [40.0, 40.0]])
    assert result.draw_ids == ((0, 0), (0, 1))
    assert result.queries == queries


@pytest.mark.parametrize("cohort_applied", [False, True])
@pytest.mark.parametrize("nugget_applied", [False, True])
def test_seeded_effect_streams_follow_sorted_identities_and_query_permutations(
    cohort_applied, nugget_applied
):
    queries = _queries()
    metadata = _metadata(
        cohort_effect_applied=cohort_applied,
        nugget_applied=nugget_applied,
    )
    latent = np.array([[0.1, 0.2, 0.3], [1.0, 1.1, 1.2]])
    cohort_sd = np.array([0.5, 1.5]) if cohort_applied else None
    nugget_sd = np.array([0.25, 2.0]) if nugget_applied else None

    result = _compose(
        queries=queries,
        metadata=metadata,
        latent_logit_draws=latent,
        cohort_sd_draws=cohort_sd,
        nugget_sd_draws=nugget_sd,
    )

    cohort_seed, nugget_seed = np.random.SeedSequence(42).spawn(2)
    expected_cohort_z = np.random.default_rng(cohort_seed).normal(size=(2, 2))
    expected_nugget_z = np.random.default_rng(nugget_seed).normal(size=(2, 3))
    expected_logits = latent.copy()
    if cohort_applied:
        # Sorted cohorts are (cohort_a, cohort_b), so submitted rows map to (1, 0, 1).
        expected_logits += cohort_sd[:, None] * expected_cohort_z[:, [1, 0, 1]]
    if nugget_applied:
        # Sorted observations are (a, m, z), so submitted rows map to (2, 0, 1).
        expected_logits += nugget_sd[:, None] * expected_nugget_z[:, [2, 0, 1]]
    np.testing.assert_array_equal(result.mean_draws, expit(expected_logits))
    if cohort_applied:
        shared = (
            expected_logits[:, [0, 2]]
            - latent[:, [0, 2]]
            - (
                nugget_sd[:, None] * expected_nugget_z[:, [2, 1]]
                if nugget_applied
                else 0.0
            )
        )
        np.testing.assert_allclose(shared[:, 0], shared[:, 1], rtol=0.0, atol=5e-16)

    permutation = np.array([2, 0, 1])
    permuted_queries = SurveyQueries(
        observation_ids=tuple(queries.observation_ids[index] for index in permutation),
        cohort_ids=tuple(queries.cohort_ids[index] for index in permutation),
        sampling_designs=tuple(queries.sampling_designs[index] for index in permutation),
        lat=tuple(queries.lat[index] for index in permutation),
        lon=tuple(queries.lon[index] for index in permutation),
    )
    permuted = _compose(
        queries=permuted_queries,
        metadata=metadata,
        latent_logit_draws=latent[:, permutation],
        cohort_sd_draws=cohort_sd,
        nugget_sd_draws=nugget_sd,
    )
    inverse = np.argsort(permutation)
    np.testing.assert_array_equal(permuted.mean_draws[:, inverse], result.mean_draws)


def test_omitting_cohort_effect_does_not_shift_the_nugget_stream():
    latent = np.zeros((2, 3))
    nugget_sd = np.array([0.5, 1.5])
    with_cohort = _compose(
        metadata=_metadata(cohort_effect_applied=True, nugget_applied=True),
        latent_logit_draws=latent,
        cohort_sd_draws=np.array([0.75, 1.25]),
        nugget_sd_draws=nugget_sd,
    )
    without_cohort = _compose(
        metadata=_metadata(nugget_applied=True),
        latent_logit_draws=latent,
        nugget_sd_draws=nugget_sd,
    )
    cohort_seed = np.random.SeedSequence(42).spawn(2)[0]
    cohort_z = np.random.default_rng(cohort_seed).normal(size=(2, 2))
    cohort_increment = np.array([0.75, 1.25])[:, None] * cohort_z[:, [1, 0, 1]]
    np.testing.assert_allclose(
        np.log(with_cohort.mean_draws / (1.0 - with_cohort.mean_draws)) - cohort_increment,
        np.log(without_cohort.mean_draws / (1.0 - without_cohort.mean_draws)),
    )


def test_zero_fitted_scales_and_binomial_none_leave_latents_unchanged():
    latent = np.array([[-3.0, 0.0, 3.0], [-2.0, 1.0, 2.0]])
    result = _compose(
        metadata=_metadata(cohort_effect_applied=True, nugget_applied=True),
        latent_logit_draws=latent,
        cohort_sd_draws=np.zeros(2),
        nugget_sd_draws=np.zeros(2),
    )
    np.testing.assert_array_equal(result.mean_draws, expit(latent))
    assert result.concentration is None


def test_composed_binomial_parameters_feed_the_exact_count_scorer():
    p = 0.2
    queries = _queries(
        observation_ids=("a",),
        cohort_ids=("new",),
        sampling_designs=("reference",),
        lat=(0.0,),
        lon=(0.0,),
    )
    result = _compose(
        queries=queries,
        latent_logit_draws=np.full((2, 1), np.log(p / (1.0 - p))),
    )
    scorer = CountPredictive(result.mean_draws, result.concentration)
    np.testing.assert_allclose(
        np.exp(scorer.log_prob(ac=np.array([1]), an=np.array([4]))),
        [4 * 0.2 * 0.8**3],
    )


@pytest.mark.parametrize(
    ("replacement", "match"),
    [
        ({"observation_ids": (), "cohort_ids": (), "sampling_designs": (), "lat": (), "lon": ()}, "nonempty"),
        ({"lon": (3.0, 4.0)}, "same length"),
        ({"observation_ids": ("z", "z", "m")}, "unique"),
        ({"observation_ids": ("z", "", "m")}, "observation_ids"),
        ({"cohort_ids": ("cohort_b", 1, "cohort_b")}, "cohort_ids"),
        ({"sampling_designs": ("reference", " ", "reference")}, "sampling_designs"),
        ({"lat": (False, 1.0, 2.0)}, "lat"),
        ({"lat": (np.nan, 1.0, 2.0)}, "lat"),
        ({"lat": (91.0, 1.0, 2.0)}, "lat"),
        ({"lon": (3.0, np.inf, 5.0)}, "lon"),
        ({"lon": (3.0, 181.0, 5.0)}, "lon"),
        ({"lon": (3.0, "4", 5.0)}, "lon"),
    ],
)
def test_survey_queries_refuse_malformed_fields(replacement, match):
    values = {
        "observation_ids": ("z", "a", "m"),
        "cohort_ids": ("cohort_b", "cohort_a", "cohort_b"),
        "sampling_designs": ("reference", "reference", "reference"),
        "lat": (0.0, 1.0, 2.0),
        "lon": (3.0, 4.0, 5.0),
    }
    values.update(replacement)
    with pytest.raises(ValueError, match=match):
        SurveyQueries(**values)


@pytest.mark.parametrize(
    ("replacement", "match"),
    [
        ({"convention": "legacy"}, "convention"),
        ({"likelihood": "normal"}, "likelihood"),
        ({"fitted_designs": ()}, "fitted_designs"),
        ({"fitted_designs": ("reference", "reference")}, "unique"),
        ({"fitted_designs": ("",)}, "fitted_designs"),
        ({"fitted_designs": (1,)}, "fitted_designs"),
        ({"training_cohort_ids": ()}, "training_cohort_ids"),
        ({"training_cohort_ids": ("training_b", "training_a")}, "sorted"),
        ({"training_cohort_ids": ("training_a", "training_a")}, "unique"),
        ({"training_cohort_ids": ("training_a", "")}, "training_cohort_ids"),
        ({"cohort_effect_applied": 1}, "cohort_effect_applied"),
        ({"nugget_applied": 0}, "nugget_applied"),
    ],
)
def test_model_metadata_refuses_malformed_fields(replacement, match):
    values = {
        "convention": "new_cohort_count_v1",
        "fitted_designs": ("reference",),
        "training_cohort_ids": ("training_a", "training_b"),
        "cohort_effect_applied": False,
        "nugget_applied": False,
        "likelihood": "binomial",
    }
    values.update(replacement)
    with pytest.raises(ValueError, match=match):
        ObservationModelMetadata(**values)


@pytest.mark.parametrize(
    ("replacement", "match"),
    [
        ({"draw_ids": ((4, 8), (4, 8))}, "unique"),
        ({"draw_ids": ((False, 8), (4, 9))}, "integer"),
        ({"draw_ids": ((4.5, 8), (4, 9))}, "integer"),
        ({"draw_ids": ((4, 8, 1), (4, 9))}, "pair"),
        ({"draw_ids": ((4, 8),)}, "length"),
        ({"queries": _queries(cohort_ids=("training_a", "new", "new"))}, "seen cohort"),
        ({"queries": _queries(sampling_designs=("reference", "unknown", "reference"))}, "design"),
        ({"latent_logit_draws": np.zeros((2, 2))}, "latent_logit_draws"),
        ({"latent_logit_draws": np.zeros((2, 3, 1))}, "latent_logit_draws"),
        ({"latent_logit_draws": np.array([[0.0, np.nan, 0.0], [0.0, 0.0, 0.0]])}, "finite"),
        ({"design_effect_draws": np.zeros((2, 1))}, "design_effect_draws"),
        ({"design_effect_draws": np.zeros((1, 0))}, "design_effect_draws"),
        (
            {
                "design_effect_draws": np.array([[np.inf], [0.0]]),
                "metadata": _metadata(fitted_designs=("reference", "alternate")),
                "queries": _queries(
                    sampling_designs=("reference", "alternate", "reference")
                ),
            },
            "finite",
        ),
        ({"seed": True}, "seed"),
        ({"seed": 1.5}, "seed"),
        ({"seed": -1}, "seed"),
    ],
)
def test_composition_refuses_malformed_alignment_and_inputs(replacement, match):
    with pytest.raises(ValueError, match=match):
        _compose(**replacement)


@pytest.mark.parametrize(
    ("effect", "applied", "draws", "match"),
    [
        ("cohort", True, None, "cohort_sd_draws.*required"),
        ("cohort", False, np.ones(2), "cohort_sd_draws.*None"),
        ("cohort", True, np.ones((2, 1)), "cohort_sd_draws"),
        ("cohort", True, np.array([1.0, -1.0]), "nonnegative"),
        ("cohort", True, np.array([1.0, np.nan]), "finite"),
        ("nugget", True, None, "nugget_sd_draws.*required"),
        ("nugget", False, np.ones(2), "nugget_sd_draws.*None"),
        ("nugget", True, np.ones((2, 1)), "nugget_sd_draws"),
        ("nugget", True, np.array([1.0, -1.0]), "nonnegative"),
        ("nugget", True, np.array([1.0, np.inf]), "finite"),
    ],
)
def test_composition_refuses_missing_extra_or_invalid_scale_draws(
    effect, applied, draws, match
):
    metadata = _metadata(
        cohort_effect_applied=applied if effect == "cohort" else False,
        nugget_applied=applied if effect == "nugget" else False,
    )
    kwargs = {"metadata": metadata, f"{effect}_sd_draws": draws}
    with pytest.raises(ValueError, match=match):
        _compose(**kwargs)


@pytest.mark.parametrize(
    ("likelihood", "concentration", "match"),
    [
        ("beta_binomial", None, "concentration_draws.*required"),
        ("binomial", np.ones(2), "concentration_draws.*None"),
        ("beta_binomial", np.ones((2, 1)), "concentration_draws"),
        ("beta_binomial", np.array([1.0, 0.0]), "positive"),
        ("beta_binomial", np.array([1.0, -1.0]), "positive"),
        ("beta_binomial", np.array([1.0, np.inf]), "finite"),
    ],
)
def test_composition_refuses_inconsistent_concentration(likelihood, concentration, match):
    with pytest.raises(ValueError, match=match):
        _compose(
            metadata=_metadata(likelihood=likelihood),
            concentration_draws=concentration,
        )


@pytest.mark.parametrize(
    ("mean_draws", "concentration", "match"),
    [
        (np.empty((0, 3)), None, "draw"),
        (np.zeros((2, 2)), None, "shape"),
        (np.zeros((2, 3, 1)), None, "two-dimensional"),
        (np.array([[0.0, np.nan, 0.0], [0.0, 0.0, 0.0]]), None, "finite"),
        (np.array([[0.0, -0.1, 0.0], [0.0, 0.0, 0.0]]), None, "between"),
        (np.zeros((2, 3)), np.ones((2, 2)), "shape"),
        (np.zeros((2, 3)), np.array([[1.0, 0.0, 1.0], [1.0, 1.0, 1.0]]), "positive"),
        (np.zeros((2, 3)), np.array([[1.0, np.inf, 1.0], [1.0, 1.0, 1.0]]), "finite"),
    ],
)
def test_observation_parameters_refuse_invalid_public_arrays(mean_draws, concentration, match):
    with pytest.raises(ValueError, match=match):
        ObservationParameters(
            queries=_queries(),
            metadata=_metadata(likelihood="binomial" if concentration is None else "beta_binomial"),
            draw_ids=((4, 8), (4, 9)),
            mean_draws=mean_draws,
            concentration=concentration,
        )


@pytest.mark.parametrize(
    ("likelihood", "concentration", "match"),
    [
        ("binomial", np.ones((2, 3)), "None"),
        ("beta_binomial", None, "required"),
    ],
)
def test_observation_parameters_refuse_likelihood_concentration_mismatch(
    likelihood, concentration, match
):
    with pytest.raises(ValueError, match=match):
        ObservationParameters(
            queries=_queries(),
            metadata=_metadata(likelihood=likelihood),
            draw_ids=((4, 8), (4, 9)),
            mean_draws=np.full((2, 3), 0.5),
            concentration=concentration,
        )


def test_inputs_are_copied_and_returned_arrays_cannot_be_made_writeable():
    latent = np.zeros((2, 3))
    design = np.empty((2, 0))
    cohort_sd = np.ones(2)
    nugget_sd = np.ones(2)
    concentration = np.array([20.0, 40.0])
    result = _compose(
        metadata=_metadata(
            cohort_effect_applied=True,
            nugget_applied=True,
            likelihood="beta_binomial",
        ),
        latent_logit_draws=latent,
        design_effect_draws=design,
        cohort_sd_draws=cohort_sd,
        nugget_sd_draws=nugget_sd,
        concentration_draws=concentration,
    )
    expected_mean = result.mean_draws.copy()
    expected_concentration = result.concentration.copy()

    latent[:] = 10.0
    cohort_sd[:] = 10.0
    nugget_sd[:] = 10.0
    concentration[:] = 10.0
    np.testing.assert_array_equal(result.mean_draws, expected_mean)
    np.testing.assert_array_equal(result.concentration, expected_concentration)
    with pytest.raises(ValueError):
        result.mean_draws.setflags(write=True)
    with pytest.raises(ValueError):
        result.concentration.setflags(write=True)


def test_extreme_finite_logits_retain_expit_endpoints_without_clipping():
    queries = _queries(
        observation_ids=("low", "high"),
        cohort_ids=("new", "new"),
        sampling_designs=("reference", "reference"),
        lat=(-90.0, 90.0),
        lon=(-180.0, 180.0),
    )
    result = _compose(
        queries=queries,
        latent_logit_draws=np.array([[-1e308, 1e308], [-1e300, 1e300]]),
    )
    np.testing.assert_array_equal(result.mean_draws, [[0.0, 1.0], [0.0, 1.0]])
