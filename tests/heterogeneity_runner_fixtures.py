"""Constructor-valid runner fixtures; no realized science or admission claim."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
from heterogeneity_codec_fixtures import dataset, fitted, selected, summary

from genomeos.validation.heterogeneity_attempts import AttemptError, FitAttemptResult, plan_fit_attempt
from genomeos.validation.heterogeneity_codec import B0HCodecLimits
from genomeos.validation.heterogeneity_runner_records import (
    AdmissionReceipt,
    RuntimeIdentity,
    SourceIdentity,
    StorageAdmission,
    prepared_null,
)
from genomeos.validation.heterogeneity_runner_wire import build_manifest
from genomeos.validation.sbc_ranks import RankNullReference


def campaign(parent):
    source = SourceIdentity(revision="a" * 40, content_sha256="b" * 64, lock_sha256="c" * 64)
    runtime = RuntimeIdentity(
        python_version="fixture3.12",
        platform="fixture-linux",
        machine="fixture-x86_64",
        environment_sha256="d" * 64,
        jax_version="fixture",
        cupy_version="fixture",
        jax_device="fixture-gpu0",
        cupy_device="fixture-gpu0",
        driver_version="fixture",
        jax_float64=True,
        cupy_float64=True,
    )
    storage = StorageAdmission(
        database_parent=str(parent.resolve()),
        device_id=parent.stat().st_dev,
        mount_type="fixture-local",
        mount_options="fixture-rw",
        free_bytes=10**9,
        probe_sha256="e" * 64,
        exclusive_lock_observed=True,
        rollback_observed=True,
        commit_readback_observed=True,
        directory_fsync_observed=True,
    )
    admission = AdmissionReceipt(
        format="b0h_admission",
        version="1",
        source=source,
        runtime=runtime,
        storage=storage,
        observed_unix_ns=1,
        startup_elapsed_ns=1,
        preflight_elapsed_ns=1,
        device_total_bytes=10**9,
        device_free_bytes=10**8,
        process_peak_rss_bytes=10**6,
        memory_observation_label="synthetic_fixture_not_measured",
    )
    null = prepared_null(RankNullReference(512, 1653499886, (100,) * 99999 + (2048,)))
    manifest = build_manifest(admission, null, worker_id="worker0", limits=B0HCodecLimits(2**20, 2**24))
    return manifest, admission, null


def accepted(data, attempt_id=0):
    spec = plan_fit_attempt(data, attempt_id=attempt_id)
    fit = fitted(data, spec)
    if data.case_id.study_id == 0:
        mean = np.array(fit.mean_draws, copy=True)
        rho = np.array(fit.rho_draws, copy=True)
        for (chain, draw), (m, r) in zip(
            ((0, 0), (1, 3), (2, 6), (3, 9)),
            ((0.125, 0.25), (0.25, 0.375), (0.375, 0.5), (0.5, 0.625)),
            strict=True,
        ):
            mean[chain, draw, 0], rho[chain, draw, 0] = m, r
        fit = replace(fit, mean_draws=mean, rho_draws=rho)
    if data.case_id.study_id == 4 and data.case_id.case_id == 1:
        counts = fit.training_counts[0]
        fit = replace(fit, training_counts=(replace(counts, training_ac=counts.training_an),))
    return FitAttemptResult(spec, "accepted", fit, None, (), None)


def failed(data, status="convergence_failed"):
    error = AttemptError(
        "convergence" if status == "convergence_failed" else "runtime",
        "builtins.RuntimeError",
        "literal synthetic failure",
        "fixture_convergence" if status == "convergence_failed" else None,
        () if status == "convergence_failed" else None,
        1 if status == "convergence_failed" else None,
    )
    return FitAttemptResult(plan_fit_attempt(data, attempt_id=0), status, None, error, (), None)


def quantities(data, attempt):
    return selected(attempt=attempt.spec.attempt_id, track=data.case_id.track_id)


def fit_summary(data, attempt, cdf_backend):
    return summary(
        data.case_id.study_id,
        data.case_id.case_id,
        data.case_id.track_id,
        attempt.spec.attempt_id,
        cdf_backend,
    )


__all__ = ["accepted", "campaign", "dataset", "failed", "fit_summary", "quantities"]
