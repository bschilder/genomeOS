"""Compact positive-basis count inference for B1G (design §§4–8, 12; #331).

Scientific objective
    Test whether a low global background plus nonnegative compact local residuals improves held-out
    HbS count prediction without broad positive spatial smearing.
Measurable output
    A converged posterior over the fixed B1G basis model and draw-aligned beta-binomial predictive
    parameters for complete held-out survey footprints.
Engineering interface
    :func:`fit_b1g` fits one training fold; :func:`predict_b1g` evaluates fixed training-only
    centres and returns the shared :class:`~genomeos.validation.predictive.CountPredictive` type.
Assumptions and refusals
    The preregistered priors, beta-binomial likelihood, design/cohort effects, and footprint-edge
    basis are fixed. Phenotypes, dated observations, leaked query IDs, changed likelihoods,
    observation nuggets, and non-converged samples fail explicitly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
import pymc as pm
import xarray as xr

from genomeos.surfaces.config import FitConfig
from genomeos.surfaces.convergence import (
    SamplerDiagnostics,
    convergence_failure,
    summarize_sampler_diagnostics,
)
from genomeos.surfaces.observation import (
    ObservationModelMetadata,
    SurveyQueries,
    compose_unseen_observations,
)
from genomeos.validation.b1g_basis import (
    B1GBasisConfig,
    B1GBasisMatrix,
    B1GCentreSet,
    build_b1g_basis_from_centres,
    select_b1g_centres,
)
from genomeos.validation.benchmark import validate_allele_observations
from genomeos.validation.predictive import CountPredictive


class B1GConvergenceError(RuntimeError):
    """The retained B1G posterior failed a frozen sampler gate."""

    def __init__(self, reason: str, diagnostics: SamplerDiagnostics) -> None:
        super().__init__(reason)
        self.diagnostics = diagnostics


@dataclass(frozen=True)
class B1GFit:
    """One fitted training fold and the immutable state required for prediction."""

    variant_id: str
    basis_config: B1GBasisConfig
    fit_config: FitConfig
    centres: B1GCentreSet
    training_source_record_ids: tuple[str, ...]
    prediction_metadata: ObservationModelMetadata
    sampler_diagnostics: SamplerDiagnostics
    idata: Any = field(repr=False)
    model: Any = field(repr=False)

    @property
    def centre_source_record_ids(self) -> tuple[str, ...]:
        return self.centres.source_record_ids


@dataclass(frozen=True)
class B1GPrediction:
    """Shared count predictive draws and the exact basis used to produce them."""

    observation_ids: tuple[str, ...]
    predictive: CountPredictive
    basis: B1GBasisMatrix


def _validated_training(observations: pd.DataFrame) -> pd.DataFrame:
    training = validate_allele_observations(observations)
    if training.empty:
        raise ValueError("training observations must not be empty")
    variants = tuple(sorted(set(training["variant_id"])))
    if len(variants) != 1 or variants[0].startswith("phenotype:"):
        raise ValueError("B1G requires one non-phenotype variant")
    if ((training["date_lower"] != 0) | (training["date_upper"] != 0)).any():
        raise ValueError("B1G requires modern observations")
    return training.sort_values("source_record_id").reset_index(drop=True)


def _observation_structure(
    observations: pd.DataFrame, reference_design: str
) -> tuple[tuple[str, ...], np.ndarray, tuple[str, ...], np.ndarray, bool]:
    present = list(dict.fromkeys(observations["sampling_design"]))
    ordered = [label for label in (reference_design, *sorted(present)) if label in present]
    designs = tuple(dict.fromkeys(ordered))
    design_index = observations["sampling_design"].map(
        {label: index for index, label in enumerate(designs)}
    ).to_numpy(dtype=np.intp)
    cohorts = tuple(sorted(observations["cohort_id"].unique()))
    cohort_index = observations["cohort_id"].map(
        {label: index for index, label in enumerate(cohorts)}
    ).to_numpy(dtype=np.intp)
    return designs, design_index, cohorts, cohort_index, len(cohorts) < len(observations)


def _sample_kwargs(config: FitConfig) -> dict[str, object]:
    kwargs: dict[str, object] = {
        "draws": config.draws,
        "tune": config.tune,
        "chains": config.chains,
        "random_seed": config.seed,
        "progressbar": False,
        "target_accept": config.target_accept,
    }
    if config.nuts_sampler == "pymc":
        kwargs["cores"] = 1
    else:
        kwargs["nuts_sampler"] = config.nuts_sampler
        kwargs["nuts"] = {"chain_method": "vectorized"}
    return kwargs


def fit_b1g(
    training_observations: pd.DataFrame,
    *,
    basis_config: B1GBasisConfig,
    fit_config: FitConfig,
) -> B1GFit:
    """Fit the preregistered B1G model to one training fold."""
    if not isinstance(basis_config, B1GBasisConfig):
        raise TypeError("basis_config must be a B1GBasisConfig")
    if not isinstance(fit_config, FitConfig):
        raise TypeError("fit_config must be a FitConfig")
    if fit_config.likelihood != "beta_binomial":
        raise ValueError("B1G requires the frozen beta_binomial likelihood")
    if fit_config.nugget:
        raise ValueError("B1G does not admit an observation nugget")

    training = _validated_training(training_observations)
    centres = select_b1g_centres(training, config=basis_config)
    basis = build_b1g_basis_from_centres(training, centres=centres, config=basis_config)
    designs, design_index, cohorts, cohort_index, cohort_effect = _observation_structure(
        training, fit_config.reference_design
    )
    ac = training["ac"].to_numpy(dtype=np.int64, copy=True)
    an = training["an"].to_numpy(dtype=np.int64, copy=True)

    with pm.Model() as model:
        basis_obs = pm.Data("basis_obs", basis.values)
        intercept = pm.Normal("intercept", mu=-3.5, sigma=1.5)
        amplitude = pm.HalfNormal("amplitude", sigma=2.0)
        mixture_weights = pm.Dirichlet(
            "mixture_weights",
            a=np.full(basis_config.basis_count, 0.5),
        )
        latent_logit = pm.Deterministic(
            "latent_logit",
            intercept + amplitude * (basis_obs @ mixture_weights),
        )
        logit = latent_logit

        if len(designs) > 1:
            beta_design = pm.Normal("beta_design", mu=0.0, sigma=1.5, shape=len(designs) - 1)
            padded_design = pm.math.concatenate([[0.0], beta_design])
            logit = logit + padded_design[design_index]

        if cohort_effect:
            cohort_sd = pm.HalfNormal("cohort_sd", sigma=0.5)
            cohort_z = pm.Normal("cohort_z", mu=0.0, sigma=1.0, shape=len(cohorts))
            beta_cohort = pm.Deterministic("beta_cohort", cohort_sd * cohort_z)
            logit = logit + beta_cohort[cohort_index]

        probability = pm.Deterministic("p", pm.math.invlogit(logit))
        concentration = pm.HalfNormal("concentration", sigma=100.0)
        pm.BetaBinomial(
            "obs",
            n=an,
            alpha=probability * concentration,
            beta=(1.0 - probability) * concentration,
            observed=ac,
        )
        idata = pm.sample(**_sample_kwargs(fit_config))

    diagnostics = summarize_sampler_diagnostics(
        idata,
        chains=fit_config.chains,
        draws=fit_config.draws,
    )
    failure = convergence_failure(
        diagnostics,
        max_rhat=fit_config.max_rhat,
        min_ess=fit_config.min_ess,
    )
    if failure is not None:
        raise B1GConvergenceError(failure, diagnostics)

    return B1GFit(
        variant_id=str(training["variant_id"].iloc[0]),
        basis_config=basis_config,
        fit_config=fit_config,
        centres=centres,
        training_source_record_ids=tuple(training["source_record_id"]),
        prediction_metadata=ObservationModelMetadata(
            convention="new_cohort_count_v1",
            fitted_designs=designs,
            training_cohort_ids=cohorts,
            cohort_effect_applied=cohort_effect,
            nugget_applied=False,
            likelihood="beta_binomial",
        ),
        sampler_diagnostics=diagnostics,
        idata=idata,
        model=model,
    )


def _posterior_draws(
    posterior: xr.Dataset | xr.DataTree,
    name: str,
    *,
    event_size: int | None = None,
) -> tuple[np.ndarray, tuple[tuple[int, int], ...]]:
    if name not in posterior:
        raise ValueError(f"fitted posterior is missing required variable {name!r}")
    variable = posterior[name]
    if not isinstance(variable, xr.DataArray) or "chain" not in variable.dims or "draw" not in variable.dims:
        raise ValueError(f"posterior {name} must have named chain and draw dimensions")
    event_dims = tuple(dimension for dimension in variable.dims if dimension not in {"chain", "draw"})
    if len(event_dims) != (0 if event_size is None else 1):
        raise ValueError(f"posterior {name} has an unexpected event shape")
    chains = tuple(sorted(int(value) for value in variable.coords["chain"].to_numpy()))
    draws = tuple(sorted(int(value) for value in variable.coords["draw"].to_numpy()))
    ordered = variable.sel(chain=list(chains), draw=list(draws))
    if event_size is not None:
        dimension = event_dims[0]
        if ordered.sizes[dimension] != event_size:
            raise ValueError(f"posterior {name} event size does not match the fitted model")
        ordered = ordered.transpose("chain", "draw", dimension)
        shape = (len(chains) * len(draws), event_size)
    else:
        ordered = ordered.transpose("chain", "draw")
        shape = (len(chains) * len(draws),)
    values = ordered.to_numpy().reshape(shape).astype(np.float64, copy=False)
    if not np.isfinite(values).all():
        raise ValueError(f"posterior {name} must be finite")
    draw_ids = tuple((chain, draw) for chain in chains for draw in draws)
    return values, draw_ids


def predict_b1g(
    fit: B1GFit,
    query_observations: pd.DataFrame,
    *,
    seed: int = 42,
    cdf_backend: str = "scipy",
) -> B1GPrediction:
    """Return vectorized count-predictive draws for complete unseen survey footprints."""
    if not isinstance(fit, B1GFit):
        raise TypeError("fit must be a B1GFit")
    queries = validate_allele_observations(query_observations)
    overlap = sorted(set(queries["source_record_id"]) & set(fit.training_source_record_ids))
    if overlap:
        raise ValueError(f"training and query source_record_id values overlap: {overlap}")
    variants = tuple(sorted(set(queries["variant_id"])))
    if variants != (fit.variant_id,):
        raise ValueError("query observations must match the fitted single variant")
    queries = queries.sort_values("source_record_id").reset_index(drop=True)
    basis = build_b1g_basis_from_centres(
        queries,
        centres=fit.centres,
        config=fit.basis_config,
    )
    posterior = getattr(fit.idata, "posterior", None)
    if not isinstance(posterior, (xr.Dataset, xr.DataTree)):
        raise ValueError("fitted posterior must be an xarray Dataset or DataTree")

    intercept, draw_ids = _posterior_draws(posterior, "intercept")
    amplitude, amplitude_ids = _posterior_draws(posterior, "amplitude")
    weights, weight_ids = _posterior_draws(
        posterior,
        "mixture_weights",
        event_size=fit.basis_config.basis_count,
    )
    if draw_ids != amplitude_ids or draw_ids != weight_ids:
        raise ValueError("B1G posterior draw coordinates do not align")
    latent = intercept[:, None] + amplitude[:, None] * (weights @ basis.values.T)

    contrasts = len(fit.prediction_metadata.fitted_designs) - 1
    if contrasts:
        design, design_ids = _posterior_draws(
            posterior,
            "beta_design",
            event_size=contrasts,
        )
        if design_ids != draw_ids:
            raise ValueError("design posterior draw coordinates do not align")
    else:
        design = np.empty((len(draw_ids), 0), dtype=np.float64)
    if fit.prediction_metadata.cohort_effect_applied:
        cohort_sd, cohort_ids = _posterior_draws(posterior, "cohort_sd")
        if cohort_ids != draw_ids:
            raise ValueError("cohort posterior draw coordinates do not align")
    else:
        cohort_sd = None
    concentration, concentration_ids = _posterior_draws(posterior, "concentration")
    if concentration_ids != draw_ids:
        raise ValueError("concentration posterior draw coordinates do not align")

    survey_queries = SurveyQueries(
        observation_ids=tuple(queries["source_record_id"]),
        cohort_ids=tuple(queries["cohort_id"]),
        sampling_designs=tuple(queries["sampling_design"]),
        lat=tuple(queries["lat"]),
        lon=tuple(queries["lon"]),
    )
    parameters = compose_unseen_observations(
        latent,
        draw_ids=draw_ids,
        queries=survey_queries,
        metadata=fit.prediction_metadata,
        design_effect_draws=design,
        cohort_sd_draws=cohort_sd,
        nugget_sd_draws=None,
        concentration_draws=concentration,
        seed=seed,
    )
    return B1GPrediction(
        observation_ids=survey_queries.observation_ids,
        predictive=CountPredictive(
            parameters.mean_draws,
            concentration=parameters.concentration,
            cdf_backend=cdf_backend,
        ),
        basis=basis,
    )
