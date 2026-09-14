"""Training-only B0H fitter and withheld predictor (design §§5, 7–8, 12; #211)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

import arviz as az
import numpy as np
import pymc as pm
import xarray as xr

from genomeos.surfaces.heterogeneity_likelihood import beta_binomial_logp
from genomeos.surfaces.heterogeneity_types import (
    MAX_RHAT,
    MIN_ESS,
    HeterogeneityConvergenceError,
    PopulationHeterogeneityConfig,
    PopulationHeterogeneityFit,
    ReferenceHeterogeneityPrediction,
    VariantHeterogeneityDiagnostics,
    VariantTrainingCounts,
)
from genomeos.validation.count_baseline import B0InfeasibleError
from genomeos.validation.predictive import MAX_BETA_SCORING_COUNT, CountPredictive
from genomeos.validation.reference_counts import (
    ReferenceCount,
    ReferenceInfeasibleError,
    validate_reference_counts,
)

SEED = 42


def _posterior_array(
    dataset: xr.Dataset,
    name: str,
    *,
    config: PopulationHeterogeneityConfig,
    variant_ids: tuple[str, ...],
) -> np.ndarray:
    if name not in dataset:
        raise ValueError(f"posterior is missing {name!r}")
    variable = dataset[name]
    if variable.dims != ("chain", "draw", "variant"):
        raise ValueError(f"posterior {name!r} must have exactly chain/draw/variant axes")
    if variable.dtype != np.dtype(np.float64):
        raise ValueError(f"posterior {name!r} must have dtype float64")
    if variable.sizes != {
        "chain": config.chains,
        "draw": config.draws,
        "variant": len(variant_ids),
    }:
        raise ValueError(f"posterior {name!r} has unexpected axis sizes")
    _require_canonical_positions(variable, config)
    labels = _variant_labels(variable, name)
    if set(labels) != set(variant_ids):
        raise ValueError(f"posterior {name!r} variant labels do not match fitted variants")
    array = variable.sel(variant=list(variant_ids)).to_numpy()
    if not np.all(np.isfinite(array)):
        raise ArithmeticError(f"posterior {name!r} must be finite")
    if np.any((array <= 0.0) | (array >= 1.0)):
        raise ArithmeticError(f"posterior {name!r} must be strictly between 0 and 1")
    return array


def _require_canonical_positions(
    variable: xr.DataArray | xr.Dataset, config: PopulationHeterogeneityConfig
) -> None:
    for name, size in (("chain", config.chains), ("draw", config.draws)):
        if name not in variable.coords:
            raise ValueError(f"{name} coordinates must be canonical integer positions")
        coordinate = variable.coords[name].to_numpy()
        if not np.issubdtype(coordinate.dtype, np.integer) or not np.array_equal(
            coordinate, np.arange(size)
        ):
            raise ValueError(f"{name} coordinates must be canonical integer positions")


def _variant_labels(variable: xr.DataArray, name: str) -> tuple[str, ...]:
    if "variant" not in variable.coords:
        raise ValueError(f"posterior {name!r} is missing variant coordinates")
    labels = tuple(variable.coords["variant"].values.tolist())
    if any(not isinstance(label, str) or not label.strip() for label in labels):
        raise ValueError(f"posterior {name!r} variant labels must be literal strings")
    if len(set(labels)) != len(labels):
        raise ValueError(f"posterior {name!r} variant labels must be unique")
    return labels


def _divergence_count(
    sample_stats: xr.Dataset, config: PopulationHeterogeneityConfig
) -> int:
    if "diverging" not in sample_stats:
        raise ValueError("sample_stats is missing 'diverging'")
    flags = sample_stats["diverging"]
    if flags.dims != ("chain", "draw") or flags.sizes != {
        "chain": config.chains,
        "draw": config.draws,
    }:
        raise ValueError("sample_stats.diverging must have exactly the configured chain/draw axes")
    _require_canonical_positions(flags, config)
    if flags.dtype != np.dtype(bool):
        raise ValueError("sample_stats.diverging must be Boolean")
    return int(np.count_nonzero(flags.to_numpy()))


def _diagnostic_values(
    dataset: xr.Dataset, name: str, variant_ids: tuple[str, ...]
) -> np.ndarray:
    if name not in dataset:
        raise ValueError(f"diagnostic is missing {name!r}")
    variable = dataset[name]
    if variable.dims != ("variant",):
        raise ValueError(f"diagnostic {name!r} must have exactly a variant axis")
    labels = _variant_labels(variable, name)
    if set(labels) != set(variant_ids):
        raise ValueError(f"diagnostic {name!r} variant labels do not match fitted variants")
    return variable.sel(variant=list(variant_ids)).to_numpy()


def _diagnostics(
    idata: xr.DataTree, variant_ids: tuple[str, ...]
) -> tuple[VariantHeterogeneityDiagnostics, ...]:
    rhat = az.rhat(idata, var_names=["mean", "rho"], method="rank")
    bulk = az.ess(idata, var_names=["mean", "rho"], method="bulk")
    tail = az.ess(idata, var_names=["mean", "rho"], method="tail")
    rhat_values = np.vstack(
        [_diagnostic_values(rhat, name, variant_ids) for name in ("mean", "rho")]
    )
    bulk_values = np.vstack(
        [_diagnostic_values(bulk, name, variant_ids) for name in ("mean", "rho")]
    )
    tail_values = np.vstack(
        [_diagnostic_values(tail, name, variant_ids) for name in ("mean", "rho")]
    )
    diagnostics = []
    nonfinite = False
    for index, variant_id in enumerate(variant_ids):
        cells = np.concatenate(
            (rhat_values[:, index], bulk_values[:, index], tail_values[:, index])
        )
        if not np.all(np.isfinite(cells)):
            nonfinite = True
            continue
        diagnostics.append(
            VariantHeterogeneityDiagnostics(
                variant_id,
                float(np.max(rhat_values[:, index])),
                float(np.min(bulk_values[:, index])),
                float(np.min(tail_values[:, index])),
            )
        )
    available = tuple(diagnostics)
    if nonfinite:
        raise HeterogeneityConvergenceError(
            "sampler produced nonfinite convergence diagnostics", diagnostics=available
        )
    return available


def _validate_diagnostics(
    idata: xr.DataTree,
    variant_ids: tuple[str, ...],
    divergence_count: int,
) -> tuple[VariantHeterogeneityDiagnostics, ...]:
    try:
        diagnostics = _diagnostics(idata, variant_ids)
    except HeterogeneityConvergenceError as error:
        raise HeterogeneityConvergenceError(
            error.reason, diagnostics=error.diagnostics, divergence_count=divergence_count
        ) from error
    if divergence_count:
        raise HeterogeneityConvergenceError(
            "sampler produced divergent transitions",
            diagnostics=diagnostics,
            divergence_count=divergence_count,
        )
    if any(
        item.max_rhat > MAX_RHAT
        or item.min_bulk_ess < MIN_ESS
        or item.min_tail_ess < MIN_ESS
        for item in diagnostics
    ):
        raise HeterogeneityConvergenceError(
            "sampler failed fixed convergence gates",
            diagnostics=diagnostics,
            divergence_count=divergence_count,
        )
    return diagnostics


def fit_reference_population_heterogeneity(
    training: Sequence[ReferenceCount], *, config: PopulationHeterogeneityConfig
) -> PopulationHeterogeneityFit:
    """Fit the declared independent per-variant B0H graph to training rows only."""
    if not isinstance(config, PopulationHeterogeneityConfig):
        raise ValueError("config must be PopulationHeterogeneityConfig")
    rows = validate_reference_counts(training)
    available = tuple(item for item in rows if item.an > 0)
    if not available:
        raise ReferenceInfeasibleError("training data have no available rows")
    oversized = tuple(item.record_id for item in available if item.an > MAX_BETA_SCORING_COUNT)
    if oversized:
        raise ValueError(
            f"training AN exceeds MAX_BETA_SCORING_COUNT={MAX_BETA_SCORING_COUNT}: {list(oversized)}"
        )
    variant_ids = tuple(sorted({item.variant_id for item in available}))
    by_variant = {variant_id: index for index, variant_id in enumerate(variant_ids)}
    index = np.asarray([by_variant[item.variant_id] for item in available], dtype=np.int64)
    ac = np.asarray([item.ac for item in available], dtype=np.int64)
    an = np.asarray([item.an for item in available], dtype=np.int64)

    with pm.Model(coords={"variant": variant_ids}):
        mean = pm.Beta(
            "mean", config.mean_prior_alpha, config.mean_prior_beta, dims="variant"
        )
        rho = pm.Beta("rho", config.rho_prior_alpha, config.rho_prior_beta, dims="variant")
        pm.CustomDist(
            "obs",
            an,
            mean[index],
            rho[index],
            logp=beta_binomial_logp,
            observed=ac,
            dtype="int64",
        )
        idata = pm.sample(
            draws=config.draws,
            tune=config.tune,
            chains=config.chains,
            random_seed=config.seed,
            nuts_sampler="numpyro",
            target_accept=config.target_accept,
            nuts={"chain_method": "vectorized"},
            progressbar=False,
        )

    if not isinstance(idata, xr.DataTree) or not hasattr(idata, "posterior"):
        raise ValueError("sampler must return posterior InferenceData")
    if not hasattr(idata, "sample_stats"):
        raise ValueError("sampler output is missing sample_stats")
    mean_draws = _posterior_array(idata.posterior, "mean", config=config, variant_ids=variant_ids)
    rho_draws = _posterior_array(idata.posterior, "rho", config=config, variant_ids=variant_ids)
    divergence_count = _divergence_count(idata.sample_stats, config)
    diagnostics = _validate_diagnostics(idata, variant_ids, divergence_count)

    training_counts = tuple(
        VariantTrainingCounts(
            variant_id,
            sum(item.variant_id == variant_id for item in available),
            sum(item.ac for item in available if item.variant_id == variant_id),
            sum(item.an for item in available if item.variant_id == variant_id),
        )
        for variant_id in variant_ids
    )
    return PopulationHeterogeneityFit(
        config=config,
        variant_ids=variant_ids,
        mean_draws=mean_draws,
        rho_draws=rho_draws,
        training_record_ids=tuple(sorted(item.record_id for item in rows)),
        training_group_ids=tuple(sorted({item.group_id for item in rows})),
        unavailable_training_ids=tuple(sorted(item.record_id for item in rows if item.an == 0)),
        training_counts=training_counts,
        diagnostics=diagnostics,
        divergence_count=divergence_count,
    )


def predict_reference_population_heterogeneity(
    fitted: PopulationHeterogeneityFit,
    testing: Sequence[ReferenceCount],
    *,
    cdf_backend: Literal["scipy", "cupy"] = "scipy",
) -> ReferenceHeterogeneityPrediction:
    """Construct marginal predictions for disjoint withheld reference rows."""
    if not isinstance(fitted, PopulationHeterogeneityFit):
        raise ValueError("fitted must be PopulationHeterogeneityFit")
    rows = validate_reference_counts(testing)
    if set(fitted.training_record_ids) & {item.record_id for item in rows}:
        raise ValueError("training and testing record IDs must be disjoint")
    if set(fitted.training_group_ids) & {item.group_id for item in rows}:
        raise ValueError("training and testing group IDs must be disjoint")
    scoreable = tuple(item for item in rows if item.an > 0)
    if not scoreable:
        raise ReferenceInfeasibleError("test fold has no scoreable rows")
    absent = tuple(sorted({item.variant_id for item in scoreable} - set(fitted.variant_ids)))
    if absent:
        raise B0InfeasibleError(absent)

    by_variant = {variant_id: index for index, variant_id in enumerate(fitted.variant_ids)}
    indices = [by_variant[item.variant_id] for item in scoreable]
    mean = fitted.mean_draws.reshape(-1, len(fitted.variant_ids))[:, indices]
    rho = fitted.rho_draws.reshape(-1, len(fitted.variant_ids))[:, indices]
    marginal = CountPredictive(mean, concentration=(1.0 - rho) / rho, cdf_backend=cdf_backend)
    return ReferenceHeterogeneityPrediction(
        marginal_predictive=marginal,
        observation_ids=tuple(item.record_id for item in scoreable),
        unavailable_ids=tuple(item.record_id for item in rows if item.an == 0),
    )
