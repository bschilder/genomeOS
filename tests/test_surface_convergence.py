"""Sampler-diagnostic extraction and refusal gates (design §§7, 12; #333)."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest
import xarray as xr

import genomeos.surfaces.convergence as subject
from genomeos.surfaces.convergence import (
    SamplerDiagnostics,
    convergence_failure,
    summarize_sampler_diagnostics,
)


def _dataset(name: str, values: list[float]) -> xr.Dataset:
    return xr.Dataset({name: (("coefficient",), np.asarray(values, dtype=np.float64))})


def test_sampler_diagnostics_retain_worst_parameter_and_divergences(monkeypatch):
    sample_stats = xr.Dataset(
        {
            "diverging": (
                ("chain", "draw"),
                np.asarray(
                    [
                        [False, False, False],
                        [False, True, False],
                        [False, False, False],
                        [False, False, False],
                    ],
                    dtype=bool,
                ),
            )
        }
    )
    idata = SimpleNamespace(sample_stats=sample_stats)
    monkeypatch.setattr(subject.az, "rhat", lambda *_args, **_kwargs: _dataset("z", [1.01, 1.04]))

    def ess(*_args, method, **_kwargs):
        return _dataset("z", [250.0, 220.0] if method == "bulk" else [205.0, 240.0])

    monkeypatch.setattr(subject.az, "ess", ess)

    observed = summarize_sampler_diagnostics(idata, chains=4, draws=3)

    assert observed == SamplerDiagnostics(
        max_rhat=1.04,
        max_rhat_parameter="z",
        min_bulk_ess=220.0,
        min_bulk_ess_parameter="z",
        min_tail_ess=205.0,
        min_tail_ess_parameter="z",
        divergence_count=1,
    )


@pytest.mark.parametrize(
    ("diagnostics", "message"),
    [
        (SamplerDiagnostics(1.051, "z", 250.0, "a", 250.0, "a", 0), "r_hat"),
        (SamplerDiagnostics(1.01, "z", 199.0, "a", 250.0, "a", 0), "bulk ESS"),
        (SamplerDiagnostics(1.01, "z", 250.0, "a", 199.0, "a", 0), "tail ESS"),
        (SamplerDiagnostics(1.01, "z", 250.0, "a", 250.0, "a", 1), "divergent"),
    ],
)
def test_each_declared_gate_refuses_the_sampler(diagnostics, message):
    reason = convergence_failure(diagnostics, max_rhat=1.05, min_ess=200.0)

    assert reason is not None
    assert message in reason


def test_values_on_declared_boundaries_are_admissible():
    diagnostics = SamplerDiagnostics(1.05, "z", 200.0, "a", 200.0, "a", 0)

    assert convergence_failure(diagnostics, max_rhat=1.05, min_ess=200.0) is None
