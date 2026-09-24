"""Marginalized spatial-activity count likelihood (design §§7–8; issue #384).

The expression is intended for an observed PyMC ``CustomDist``. It integrates the latent
activity state analytically so gradient-based samplers never receive a discrete indicator. An
observed zero retains both inactive and beta-binomial sampling-zero paths. Direct random
generation remains in ``ActivityCountPredictive`` and the simulation preflight.
"""

from __future__ import annotations

import pytensor.tensor as pt
from pymc.distributions.dist_math import check_parameters
from pytensor.tensor.variable import TensorVariable

from genomeos.surfaces.heterogeneity_likelihood import beta_binomial_logp


def activity_beta_binomial_logp(
    value: TensorVariable,
    n: TensorVariable,
    mean: TensorVariable,
    activity_probability: TensorVariable,
    concentration: TensorVariable,
) -> TensorVariable:
    """Return per-observation log mass after integrating the activity state."""
    value = pt.as_tensor_variable(value)
    n = pt.as_tensor_variable(n)
    mean = pt.as_tensor_variable(mean)
    activity_probability = pt.as_tensor_variable(activity_probability)
    concentration = pt.as_tensor_variable(concentration)

    activity_valid = (
        pt.ge(activity_probability, 0.0)
        & pt.le(activity_probability, 1.0)
        & ~pt.isnan(activity_probability)
        & ~pt.isinf(activity_probability)
    )
    concentration_valid = (
        pt.gt(concentration, 0.0)
        & ~pt.isnan(concentration)
        & ~pt.isinf(concentration)
    )
    safe_activity = pt.where(activity_valid, activity_probability, 0.5)
    safe_concentration = pt.where(concentration_valid, concentration, 1.0)
    rho = 1.0 / (1.0 + safe_concentration)
    beta_binomial = beta_binomial_logp(value, n, mean, rho)

    log_active = pt.log(safe_activity)
    log_inactive = pt.log1p(-safe_activity)
    logp = pt.where(
        pt.eq(value, 0),
        pt.logaddexp(log_inactive, log_active + beta_binomial),
        log_active + beta_binomial,
    )
    logp = check_parameters(
        logp,
        concentration_valid,
        msg="concentration must be positive and finite",
    )
    return check_parameters(
        logp,
        activity_valid,
        msg="activity_probability must be between zero and one",
    )
