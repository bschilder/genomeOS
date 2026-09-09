from __future__ import annotations

from dataclasses import asdict

import pytest

import genomeos.surfaces.config as config
import genomeos.surfaces.fit as fit_module


def test_existing_import_path_is_the_same_configuration_class() -> None:
    assert fit_module.FitConfig is config.FitConfig
    assert asdict(config.FitConfig()) == asdict(fit_module.FitConfig())
    assert config.FitConfig().draws == 500
    assert config.FitConfig().tune == 1000
    assert config.FitConfig().chains == 4
    assert config.FitConfig().max_rhat == 1.05
    assert config.FitConfig().min_ess == 200.0


def test_configuration_defaults_are_unchanged() -> None:
    assert asdict(config.FitConfig()) == {
        "likelihood": "beta_binomial",
        "approximation": "hsgp",
        "inducing_placement": "h3",
        "n_inducing": 200,
        "inducing_reach_km": 1500.0,
        "hsgp_m": (6, 6, 6),
        "hsgp_c": 1.5,
        "draws": 500,
        "tune": 1000,
        "chains": 4,
        "nuts_sampler": "numpyro",
        "target_accept": 0.8,
        "lengthscale_prior": "derived",
        "lengthscale_mu": -2.0,
        "lengthscale_sigma": 0.7,
        "nugget": False,
        "max_rhat": 1.05,
        "min_ess": 200.0,
        "seed": 42,
        "reference_design": "population_random",
    }


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("likelihood", "poisson", "unknown likelihood"),
        ("hsgp_c", 1.0, "hsgp_c must be > 1"),
        ("lengthscale_sigma", 0.0, "lengthscale_sigma must be > 0"),
        ("lengthscale_prior", "vibes", "unknown lengthscale_prior"),
        ("max_rhat", 0.99, "max_rhat must be >= 1.0"),
        ("target_accept", 0.0, "target_accept must be strictly between 0 and 1"),
        ("target_accept", 1.0, "target_accept must be strictly between 0 and 1"),
        ("approximation", "kriging", "unknown approximation"),
        ("n_inducing", 1, "n_inducing must be >= 2"),
        ("inducing_placement", "poisson-disc", "unknown inducing_placement"),
        ("nuts_sampler", "stan", "unknown nuts_sampler"),
    ],
)
def test_configuration_validation_is_unchanged(field: str, value: object, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        config.FitConfig(**{field: value})


def test_named_constants_remain_available_from_both_modules() -> None:
    expected = {
        "SEED": 42,
        "LIKELIHOODS": ("binomial", "beta_binomial"),
        "LENGTHSCALE_PRIORS": ("derived", "fixed"),
        "NUTS_SAMPLERS": ("pymc", "numpyro", "blackjax", "nutpie"),
        "APPROXIMATIONS": ("hsgp", "inducing"),
        "INDUCING_PLACEMENTS": ("h3", "kmeans"),
        "JITTER": 1e-4,
        "MIN_SPACING_FRACTION": 0.25,
        "MAX_INDUCING_FRACTION": 0.6,
        "REFERENCE_DESIGN": "population_random",
        "EARTH_RADIUS_KM": 6371.0088,
        "LENGTHSCALE_REGIONS": 4,
        "MIN_LENGTHSCALE_ANCHOR_KM": 25.0,
        "MAX_LENGTHSCALE_ANCHOR_KM": 2500.0,
    }
    for name, value in expected.items():
        assert getattr(config, name) == value
        assert getattr(fit_module, name) == value
