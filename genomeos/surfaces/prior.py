"""Bounded pointwise latent-prior prediction (design §7.1b, §12; issue #266).

The support denominator is the prior uncertainty of the same ``freq_pred`` node at the same
coordinates as the posterior prediction. Sampling the retained model preserves its fitted graph,
including approximation geometry and hyperpriors, while keeping memory bounded by query batches.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pymc as pm

SEED = 42
PRIOR_NORMALIZATION = "pointwise_approximate_latent_v1"
PRIOR_DRAWS = 500
PRIOR_BATCH_SIZE = 2048


def latent_prior_frequency_sd(
    model: Any, coordinates: np.ndarray, *, seed: int
) -> np.ndarray:
    """Return one population SD of prior ``freq_pred`` draws per unit-sphere coordinate.

    The same seed is replayed for every batch so batching remains an engineering memory bound
    rather than part of the scientific result. The model's original ``x_pred`` data is restored
    after success or failure.
    """
    points = np.asarray(coordinates, dtype=float)
    if points.ndim != 2 or points.shape[1:] != (3,):
        raise ValueError("coordinates must have shape (n, 3)")
    if len(points) == 0:
        raise ValueError("coordinates must be nonempty")
    if not np.isfinite(points).all():
        raise ValueError("coordinates must be finite")
    if not np.allclose(np.linalg.norm(points, axis=1), 1.0, rtol=0, atol=1e-7):
        raise ValueError("coordinates must lie on the unit sphere")
    if isinstance(seed, (bool, np.bool_)) or not isinstance(seed, (int, np.integer)) or seed < 0:
        raise ValueError("seed must be a nonnegative integer")
    named_vars = getattr(model, "named_vars", {})
    if "x_pred" not in named_vars or "freq_pred" not in named_vars:
        raise ValueError("model must expose predictive nodes x_pred and freq_pred")

    original = np.array(model["x_pred"].get_value(), copy=True)
    sd = np.empty(len(points), dtype=np.float64)
    try:
        for start in range(0, len(points), PRIOR_BATCH_SIZE):
            stop = min(start + PRIOR_BATCH_SIZE, len(points))
            with model:
                pm.set_data({"x_pred": points[start:stop]})
                prior = pm.sample_prior_predictive(
                    draws=PRIOR_DRAWS,
                    var_names=["freq_pred"],
                    random_seed=int(seed),
                )
            samples = np.asarray(prior.prior["freq_pred"].to_numpy(), dtype=np.float64)
            batch_size = stop - start
            expected = PRIOR_DRAWS * batch_size
            if (
                samples.ndim < 2
                or samples.shape[-1] != batch_size
                or int(np.prod(samples.shape[:-1])) != PRIOR_DRAWS
                or samples.size != expected
            ):
                raise ValueError(
                    "prior freq_pred draws have the wrong shape: "
                    f"expected {PRIOR_DRAWS} x {batch_size}, got {samples.shape}"
                )
            samples = samples.reshape(PRIOR_DRAWS, batch_size)
            if not np.isfinite(samples).all():
                raise ValueError("prior freq_pred draws must be finite")
            sd[start:stop] = samples.std(axis=0, ddof=0)
    finally:
        with model:
            pm.set_data({"x_pred": original})

    if not np.isfinite(sd).all() or (sd <= 0).any():
        raise ValueError("prior frequency SD must be finite and positive at every coordinate")
    return sd
