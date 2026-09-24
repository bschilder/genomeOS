"""Retained sampler diagnostics and convergence refusal (design §§7, 12; #333).

This pure boundary reduces an ArviZ posterior to the extrema needed to audit a spatial fit. It
does not fit, retry, serialize, or publish a model. Callers retain the returned record even when
one of the declared gates refuses the fit.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from numbers import Integral, Real

import arviz as az
import numpy as np


def _finite_number(value: object, field: str, *, minimum: float) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise ValueError(f"{field} must be finite and at least {minimum}")
    normalized = float(value)
    if not isfinite(normalized) or normalized < minimum:
        raise ValueError(f"{field} must be finite and at least {minimum}")
    return normalized


def _label(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a nonempty string")
    return value


@dataclass(frozen=True)
class SamplerDiagnostics:
    """Worst retained rank-Rhat, bulk/tail ESS, and divergence count for one fit."""

    max_rhat: float
    max_rhat_parameter: str
    min_bulk_ess: float
    min_bulk_ess_parameter: str
    min_tail_ess: float
    min_tail_ess_parameter: str
    divergence_count: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "max_rhat", _finite_number(self.max_rhat, "max_rhat", minimum=0.0))
        object.__setattr__(
            self,
            "min_bulk_ess",
            _finite_number(self.min_bulk_ess, "min_bulk_ess", minimum=0.0),
        )
        object.__setattr__(
            self,
            "min_tail_ess",
            _finite_number(self.min_tail_ess, "min_tail_ess", minimum=0.0),
        )
        for field in (
            "max_rhat_parameter",
            "min_bulk_ess_parameter",
            "min_tail_ess_parameter",
        ):
            object.__setattr__(self, field, _label(getattr(self, field), field))
        count = self.divergence_count
        if isinstance(count, (bool, np.bool_)) or not isinstance(count, Integral) or count < 0:
            raise ValueError("divergence_count must be a nonnegative integer")
        object.__setattr__(self, "divergence_count", int(count))


def _extreme(dataset: object, *, maximum: bool, field: str) -> tuple[float, str]:
    data_vars = getattr(dataset, "data_vars", None)
    if data_vars is None or not data_vars:
        raise ValueError(f"{field} diagnostics must contain at least one parameter")
    selected_value = -np.inf if maximum else np.inf
    selected_name = ""
    for name in sorted(data_vars):
        values = np.asarray(data_vars[name].to_numpy(), dtype=np.float64)
        if values.size == 0 or not np.all(np.isfinite(values)):
            raise ValueError(f"{field} diagnostics for {name!r} must be nonempty and finite")
        candidate = float(np.max(values) if maximum else np.min(values))
        if (maximum and candidate > selected_value) or (
            not maximum and candidate < selected_value
        ):
            selected_value = candidate
            selected_name = str(name)
    return selected_value, selected_name


def _diagnostic_variable_names(
    idata: object, var_names: tuple[str, ...] | None
) -> tuple[str, ...] | None:
    if var_names is None:
        return None
    if not isinstance(var_names, tuple) or not var_names:
        raise ValueError("var_names must be a nonempty tuple of unique posterior variable names")
    if any(not isinstance(name, str) or not name.strip() for name in var_names):
        raise ValueError("var_names must be a nonempty tuple of unique posterior variable names")
    if len(set(var_names)) != len(var_names):
        raise ValueError("var_names must be a nonempty tuple of unique posterior variable names")
    posterior = getattr(idata, "posterior", None)
    data_vars = getattr(posterior, "data_vars", None)
    if data_vars is None:
        raise ValueError("posterior variables are unavailable")
    missing = tuple(name for name in var_names if name not in data_vars)
    if missing:
        raise ValueError(f"posterior is missing diagnostic variables: {missing}")
    return var_names


def summarize_sampler_diagnostics(
    idata: object,
    *,
    chains: int,
    draws: int,
    var_names: tuple[str, ...] | None = None,
) -> SamplerDiagnostics:
    """Return finite extrema for the requested sampled variables and all divergences."""
    if isinstance(chains, bool) or not isinstance(chains, Integral) or chains < 2:
        raise ValueError("chains must be an integer of at least two")
    if isinstance(draws, bool) or not isinstance(draws, Integral) or draws < 1:
        raise ValueError("draws must be a positive integer")
    try:
        flags = idata.sample_stats["diverging"]
    except (AttributeError, KeyError, TypeError) as error:
        raise ValueError("sample_stats must contain diverging") from error
    if flags.dims != ("chain", "draw") or flags.sizes != {
        "chain": int(chains),
        "draw": int(draws),
    }:
        raise ValueError("sample_stats.diverging must match configured chain and draw axes")
    if flags.dtype != np.dtype(bool):
        raise ValueError("sample_stats.diverging must be Boolean")
    selected_names = _diagnostic_variable_names(idata, var_names)
    diagnostic_kwargs = {} if selected_names is None else {"var_names": list(selected_names)}

    max_rhat, max_rhat_parameter = _extreme(
        az.rhat(idata, method="rank", **diagnostic_kwargs), maximum=True, field="r_hat"
    )
    min_bulk_ess, min_bulk_ess_parameter = _extreme(
        az.ess(idata, method="bulk", **diagnostic_kwargs), maximum=False, field="bulk ESS"
    )
    min_tail_ess, min_tail_ess_parameter = _extreme(
        az.ess(idata, method="tail", **diagnostic_kwargs), maximum=False, field="tail ESS"
    )
    return SamplerDiagnostics(
        max_rhat=max_rhat,
        max_rhat_parameter=max_rhat_parameter,
        min_bulk_ess=min_bulk_ess,
        min_bulk_ess_parameter=min_bulk_ess_parameter,
        min_tail_ess=min_tail_ess,
        min_tail_ess_parameter=min_tail_ess_parameter,
        divergence_count=int(np.count_nonzero(flags.to_numpy())),
    )


def convergence_failure(
    diagnostics: SamplerDiagnostics, *, max_rhat: float, min_ess: float
) -> str | None:
    """Return a complete refusal reason, or ``None`` when every declared gate passes."""
    if not isinstance(diagnostics, SamplerDiagnostics):
        raise TypeError("diagnostics must be SamplerDiagnostics")
    rhat_limit = _finite_number(max_rhat, "max_rhat", minimum=1.0)
    ess_limit = _finite_number(min_ess, "min_ess", minimum=0.0)
    problems = []
    if diagnostics.max_rhat > rhat_limit:
        problems.append(
            f"r_hat {diagnostics.max_rhat:.3f} > {rhat_limit:g} "
            f"(worst: {diagnostics.max_rhat_parameter})"
        )
    if diagnostics.min_bulk_ess < ess_limit:
        problems.append(
            f"bulk ESS {diagnostics.min_bulk_ess:.0f} < {ess_limit:g} "
            f"(worst: {diagnostics.min_bulk_ess_parameter})"
        )
    if diagnostics.min_tail_ess < ess_limit:
        problems.append(
            f"tail ESS {diagnostics.min_tail_ess:.0f} < {ess_limit:g} "
            f"(worst: {diagnostics.min_tail_ess_parameter})"
        )
    if diagnostics.divergence_count:
        noun = "transition" if diagnostics.divergence_count == 1 else "transitions"
        problems.append(f"{diagnostics.divergence_count} divergent {noun}")
    if not problems:
        return None
    return "sampler did not converge (" + "; ".join(problems) + ")"
