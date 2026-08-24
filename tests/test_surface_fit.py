"""Surface fit tests (design §7). Sampling is small and seeded; see FAST_CONFIG."""

import numpy as np
import pandas as pd
import pandera.errors
import pytest

from genomeos.observations.schema import OBSERVATIONS_SCHEMA
from genomeos.surfaces.fit import FitConfig, fit_surface

FAST_CONFIG = FitConfig(draws=150, tune=150, chains=2)

HBS = "chr11-5227002-T-A"


def _observations(
    n: int = 40,
    beta_design: float = -1.0,
    designs: tuple[str, ...] = ("population_random", "healthy_reference"),
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
    ac = rng.binomial(an, p)

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
    assert list(pred.columns) == ["lat", "lon", "post_mean", "post_sd", "q025", "q975"]
    assert ((pred["post_mean"] > 0) & (pred["post_mean"] < 1)).all()
    assert (pred["post_sd"] > 0).all()
    assert (pred["q025"] < pred["post_mean"]).all()
    assert (pred["post_mean"] < pred["q975"]).all()


def test_prediction_follows_the_simulated_cline(fit):
    """The synthetic surface rises west-to-east; the fit must reproduce that ordering."""
    pred = fit.predict(lat=[0.0, 0.0], lon=[-8.0, 8.0])
    assert pred["post_mean"].iloc[0] < pred["post_mean"].iloc[1]


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
    fit = fit_surface(obs, FitConfig(draws=150, tune=150, chains=2, likelihood="beta_binomial"))
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
