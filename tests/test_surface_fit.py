"""Surface fit tests (design §7). Sampling is small and seeded; see FAST_CONFIG."""

import numpy as np
import pandas as pd
import pandera.errors
import pytest

from genomeos.observations.schema import OBSERVATIONS_SCHEMA
from genomeos.surfaces.fit import (
    ConvergenceError,
    FitConfig,
    fit_surface,
    h3_inducing_points,
    inducing_points,
    to_unit_sphere,
)

# Enough draws to actually converge: fit_surface now refuses a fit that has not mixed (§12),
# so a too-short chain is a failure rather than a fast approximation. numpyro keeps it quick.
FAST_CONFIG = FitConfig(draws=800, tune=1000, chains=4)

HBS = "chr11-5227002-T-A"


def _observations(
    n: int = 70,
    beta_design: float = -1.0,
    designs: tuple[str, ...] = ("population_random", "healthy_reference"),
    concentration: float = 40.0,
    seed: int = 7,
) -> pd.DataFrame:
    """Synthetic observations with a known east-west cline and a known design effect.

    The first entry of `designs` is the reference level, so its true offset is 0.
    """
    rng = np.random.default_rng(seed)
    lon = rng.uniform(-10.0, 10.0, n)
    lat = rng.uniform(-10.0, 10.0, n)
    design_idx = rng.integers(0, len(designs), n)
    logit = -1.5 + 0.15 * lon + beta_design * (design_idx != 0)
    p = 1.0 / (1.0 + np.exp(-logit))
    an = np.full(n, 200)
    # Overdispersed, like the real corpus: two surveys of one locality differ by more than
    # binomial sampling error, because they differ in method, sub-population and decade. Exactly
    # binomial fixtures would also leave the beta-binomial concentration unidentified at the top
    # end, so the fixture matches both reality and the default likelihood.
    ac = rng.binomial(an, rng.beta(p * concentration, (1.0 - p) * concentration))

    return OBSERVATIONS_SCHEMA.validate(
        pd.DataFrame(
            {
                "variant_id": HBS,
                "rsid": "rs334",
                "population_id": [f"pop-{i:03d}" for i in range(n)],
                "lat": lat,
                "lon": lon,
                "radius_km": 25.0,
                "ac": ac,
                "an": an,
                "source": "synthetic",
                "assay": "genotype",
                "date_lower": 0,
                "date_upper": 0,
                "sampling_design": [designs[i] for i in design_idx],
                "disease_ascertainment_excluded": [bool(i != 0) for i in design_idx],
                "cohort_id": [f"cohort-{i % 4}" for i in range(n)],
                "ingest_version": "test",
            }
        )
    )


@pytest.fixture(scope="module")
def fit():
    return fit_surface(_observations(), FAST_CONFIG)


def test_fit_recovers_the_design_effect_when_designs_contrast(fit):
    """β_design is identified by contrast between designs — the reason MAP surveys are in P1."""
    effects = fit.design_effects()
    row = effects.loc[effects["sampling_design"] == "healthy_reference"].iloc[0]
    assert row["q025"] < -1.0 < row["q975"], f"true -1.0 outside CI: {row.to_dict()}"


def test_fit_records_which_designs_were_applied(fit):
    assert fit.beta_design_applied is True
    assert set(fit.design_effects()["sampling_design"]) == {"healthy_reference"}


def test_predictions_carry_uncertainty_and_lie_on_the_frequency_scale(fit):
    pred = fit.predict(lat=[0.0, 5.0], lon=[-8.0, 8.0])
    assert list(pred.columns) == [
        "lat", "lon", "post_median", "post_mean", "post_sd", "q025", "q975", "q25", "q75",
    ]
    for column in ("post_median", "post_mean"):
        assert ((pred[column] > 0) & (pred[column] < 1)).all()
    assert (pred["post_sd"] > 0).all()
    assert (pred["q025"] <= pred["q25"]).all()
    assert (pred["q25"] <= pred["post_median"]).all()
    assert (pred["post_median"] <= pred["q75"]).all()
    assert (pred["q75"] <= pred["q975"]).all()


def test_the_median_is_reported_because_the_mean_is_skewed_where_data_is_thin(fit):
    """Allele frequency is bounded and its posterior is right-tailed, so the mean runs high
    exactly where there is least data — the failure Piel et al. document in their appendix (#102).
    """
    pred = fit.predict(lat=[0.0], lon=[0.0])
    assert "post_median" in pred.columns
    assert "q25" in pred.columns and "q75" in pred.columns, "IQR needed for like-for-like §8 (#92)"


def test_prediction_follows_the_simulated_cline(fit):
    """The synthetic surface rises west-to-east; the fit must reproduce that ordering."""
    pred = fit.predict(lat=[0.0, 0.0], lon=[-8.0, 8.0])
    assert pred["post_median"].iloc[0] < pred["post_median"].iloc[1]


def test_fit_is_deterministic_given_the_same_seed():
    obs = _observations()
    a = fit_surface(obs, FAST_CONFIG).design_effects()["mean"].to_numpy()
    b = fit_surface(obs, FAST_CONFIG).design_effects()["mean"].to_numpy()
    assert np.allclose(a, b), "same (data, config, seed) must give the same fit (§5)"


def test_single_design_omits_beta_design_rather_than_pretending_to_estimate_it():
    """With one design there is no contrast, so β_design is unidentifiable (§7.1a)."""
    obs = _observations(designs=("population_random",))
    fit = fit_surface(obs, FAST_CONFIG)
    assert fit.beta_design_applied is False
    assert fit.design_effects().empty


def test_beta_binomial_likelihood_is_selectable():
    """Overdispersion relative to binomial is a documented failure mode here (#83)."""
    obs = _observations()
    fit = fit_surface(obs, FitConfig(draws=800, tune=1000, chains=4, likelihood="beta_binomial"))
    assert fit.config.likelihood == "beta_binomial"
    assert (fit.predict(lat=[0.0], lon=[0.0])["post_sd"] > 0).all()


def test_more_than_one_variant_is_refused():
    """Surfaces are fitted per variant (§7); a mixed frame is a caller error, not a merge."""
    obs = pd.concat([_observations(n=20), _observations(n=20)], ignore_index=True)
    obs.loc[obs.index[:20], "variant_id"] = "chr7-117559590-ATCT-A"
    with pytest.raises(ValueError, match="exactly one variant"):
        fit_surface(obs, FAST_CONFIG)


def test_an_invalid_observation_frame_is_refused():
    obs = _observations(n=20)
    obs.loc[obs.index[0], "sampling_design"] = "unknown"
    with pytest.raises(pandera.errors.SchemaError):
        fit_surface(obs, FAST_CONFIG)


def test_unknown_likelihood_is_refused():
    with pytest.raises(ValueError, match="likelihood"):
        fit_surface(_observations(n=20), FitConfig(likelihood="poisson"))


def test_a_fit_that_has_not_converged_is_refused_not_published():
    """§12: a variant whose fit does not converge is excluded from the surface set.

    A non-converged chain produces a confident-looking map that nothing downstream can
    distinguish from a good one, so this has to fail loudly at the source.
    """
    with pytest.raises(ConvergenceError, match="did not converge"):
        fit_surface(_observations(n=30), FitConfig(draws=5, tune=5, chains=4))


def test_the_binomial_likelihood_remains_selectable():
    """Beta-binomial is the default, but the binomial §7 specifies must stay reachable (#83)."""
    assert FitConfig().likelihood == "beta_binomial"
    assert FitConfig(likelihood="binomial").likelihood == "binomial"


# --- inducing-point approximation (#103): degrees of freedom where the data is ---


def test_inducing_points_lie_on_the_sphere_and_follow_the_data():
    """Centroids are re-projected: the mean of points on a sphere sits inside it."""
    observations = _observations(n=120)
    x = to_unit_sphere(observations["lat"], observations["lon"])
    points = inducing_points(x, 30, seed=42)
    assert len(points) <= 30
    assert np.allclose(np.linalg.norm(points, axis=1), 1.0)


def test_inducing_placement_is_deterministic_given_the_seed():
    observations = _observations(n=120)
    x = to_unit_sphere(observations["lat"], observations["lon"])
    assert np.allclose(inducing_points(x, 25, seed=7), inducing_points(x, 25, seed=7))


def test_the_inducing_approximation_fits_and_predicts():
    observations = _observations(n=70)
    fit = fit_surface(
        observations,
        FitConfig(draws=400, tune=800, chains=4, approximation="inducing", n_inducing=40),
    )
    pred = fit.predict(lat=[0.0, 0.0], lon=[-8.0, 8.0])
    assert ((pred["post_median"] > 0) & (pred["post_median"] < 1)).all()
    assert pred["post_median"].iloc[0] < pred["post_median"].iloc[1], "must follow the cline"


def test_inducing_resolution_is_set_by_point_count_not_by_a_global_grid():
    """The whole reason for this engine: HSGP resolves 2L/m everywhere, this follows density."""
    observations = _observations(n=200)
    x = to_unit_sphere(observations["lat"], observations["lon"])
    coarse = inducing_points(x, 20, seed=1)
    fine = inducing_points(x, 80, seed=1)
    assert len(fine) > len(coarse)


def test_an_unknown_approximation_is_refused():
    with pytest.raises(ValueError, match="approximation"):
        FitConfig(approximation="kriging")


def test_too_few_inducing_points_is_refused():
    with pytest.raises(ValueError, match="n_inducing"):
        FitConfig(n_inducing=1)


# --- H3 geodesic placement ---


def test_h3_inducing_points_cover_the_observations_not_an_arbitrary_index_block():
    """Selecting by H3 index order once put every point in the Arctic, 8,800 km from the data.

    Uniform spacing is necessary and nowhere near sufficient; coverage is the real test.
    """
    observations = _observations(n=120)
    lat = observations["lat"].to_numpy()
    lon = observations["lon"].to_numpy()
    points = h3_inducing_points(lat, lon, 200, reach_km=1500.0)

    degrees = np.degrees(
        np.column_stack([np.arcsin(points[:, 2]), np.arctan2(points[:, 1], points[:, 0])])
    )
    assert degrees[:, 0].min() <= lat.min() + 15
    assert degrees[:, 0].max() >= lat.max() - 15
    assert np.allclose(np.linalg.norm(points, axis=1), 1.0), "must lie on the sphere surface"


def test_h3_placement_is_deterministic_and_needs_no_seed():
    observations = _observations(n=100)
    lat, lon = observations["lat"].to_numpy(), observations["lon"].to_numpy()
    first = h3_inducing_points(lat, lon, 120, reach_km=1500.0)
    second = h3_inducing_points(lat, lon, 120, reach_km=1500.0)
    assert np.array_equal(first, second)


def test_more_budget_buys_finer_spacing():
    observations = _observations(n=150)
    lat, lon = observations["lat"].to_numpy(), observations["lon"].to_numpy()
    assert len(h3_inducing_points(lat, lon, 300, 1500.0)) > len(
        h3_inducing_points(lat, lon, 80, 1500.0)
    )


def test_h3_is_the_default_placement():
    """It aligns with §6's artifact grid and does not depend on a seed."""
    assert FitConfig().inducing_placement == "h3"


def test_an_unknown_placement_is_refused():
    with pytest.raises(ValueError, match="inducing_placement"):
        FitConfig(inducing_placement="poisson-disc")
