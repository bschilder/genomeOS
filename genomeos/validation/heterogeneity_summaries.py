"""Guarded B0H post-fit descriptive summaries (design §§5,7–8,12; #211)."""

from __future__ import annotations

from dataclasses import replace
from typing import Literal

import numpy as np

from genomeos.surfaces.heterogeneity_types import PopulationHeterogeneityFit
from genomeos.surfaces.reference_heterogeneity import (
    predict_reference_population_heterogeneity,
)
from genomeos.validation.heterogeneity_attempts import FitAttemptResult, require_fit_identity
from genomeos.validation.heterogeneity_diagnostic_seeds import DiagnosticSeedIdentity
from genomeos.validation.heterogeneity_sbc_controls import DiagnosticCallError
from genomeos.validation.heterogeneity_simulation_types import GeneratedDataset
from genomeos.validation.heterogeneity_summary_types import (
    HeterogeneityFitSummary,
    ParameterPosteriorSummary,
    PredictiveSummaryEvidence,
    predictive_summary_rows,
    require_summary_prediction,
)
from genomeos.validation.predictive import predictive_diagnostics

SEED = 42
_LEVELS = (0.025, 0.1, 0.25, 0.5, 0.75, 0.9, 0.975)


def _error(error: Exception) -> DiagnosticCallError:
    return DiagnosticCallError(type(error).__module__ + "." + type(error).__qualname__, str(error))


def _parameter_summary(
    name: Literal["mean", "rho"],
    truth: float,
    array: np.ndarray,
    count: int,
) -> ParameterPosteriorSummary:
    estimate = np.mean(array[:, :, 0])
    if type(estimate) not in (float, np.float64) or not np.isfinite(estimate):
        raise ValueError("posterior mean must return a finite binary64 scalar")
    quantiles = np.quantile(array[:, :, 0], _LEVELS, method="linear")
    if (
        not isinstance(quantiles, np.ndarray)
        or quantiles.dtype != np.dtype("float64")
        or quantiles.shape != (7,)
        or not np.all(np.isfinite(quantiles))
    ):
        raise ValueError("posterior quantiles must return a finite float64 vector of length seven")
    return ParameterPosteriorSummary(
        name, truth, float(estimate), tuple(float(value) for value in quantiles), count
    )


def summarize_heterogeneity_fit(
    dataset: GeneratedDataset,
    *,
    attempt: FitAttemptResult,
    cdf_backend: Literal["scipy", "cupy"],
) -> HeterogeneityFitSummary:
    """Summarize every accepted draw and the original-order marginal count targets."""
    if not isinstance(dataset, GeneratedDataset) or not isinstance(attempt, FitAttemptResult):
        raise ValueError("summary requires GeneratedDataset and FitAttemptResult")
    if attempt.status != "accepted" or not isinstance(attempt.fit, PopulationHeterogeneityFit):
        raise ValueError("summary requires an accepted typed fit")
    if type(cdf_backend) is not str or cdf_backend not in ("scipy", "cupy"):
        raise ValueError("cdf_backend must be explicitly scipy or cupy")
    require_fit_identity(dataset, spec=attempt.spec, fit=attempt.fit)
    dataset = replace(dataset)
    attempt = replace(attempt)
    fitted = attempt.fit
    count = attempt.spec.config.chains * attempt.spec.config.draws
    parameters = tuple(
        _parameter_summary(name, truth, array, count)
        for name, truth, array in (
            ("mean", dataset.truth.mean, fitted.mean_draws),
            ("rho", dataset.truth.rho, fitted.rho_draws),
        )
    )
    seed = DiagnosticSeedIdentity(attempt.spec.case, attempt.spec.attempt_id, 7, ())
    words, scalar = seed.scalar_words, seed.scalar_uint128
    if words is None or scalar is None:
        raise ValueError("purpose7 must expose its exact scalar seed")
    targets = dataset.heldouts
    testing = tuple(target.row for target in targets)
    prediction = None
    error = None
    rows = ()
    try:
        prediction = predict_reference_population_heterogeneity(fitted, testing, cdf_backend=cdf_backend)
    except Exception as caught:
        status = "prediction_failed"
        error = _error(caught)
    else:
        require_summary_prediction(prediction, targets=targets, cdf_backend=cdf_backend, draw_count=count)
        ac = np.asarray([target.row.ac for target in targets], dtype=np.int64)
        an = np.asarray([target.row.an for target in targets], dtype=np.int64)
        try:
            frame = predictive_diagnostics(prediction.marginal_predictive, ac, an, seed=scalar)
        except Exception as caught:
            status = "diagnostics_failed"
            error = _error(caught)
        else:
            rows = predictive_summary_rows(frame, targets=targets)
            status = "complete"
    evidence = PredictiveSummaryEvidence(
        seed, words, scalar, cdf_backend, count, targets, status, prediction, rows, error
    )
    return HeterogeneityFitSummary(attempt.spec, fitted.variant_ids[0], parameters, evidence)
