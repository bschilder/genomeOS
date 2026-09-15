"""Synthetic immutable B0H wire tests (design §§5, 7–8, 12)."""

from __future__ import annotations

import io
import json
import zipfile
from dataclasses import replace

import numpy as np
import pytest
from reference_b0h_synthetic import synthetic_fit, synthetic_rows

import genomeos.validation.reference_b0h_artifacts as subject
from genomeos.surfaces.heterogeneity_types import PopulationHeterogeneityConfig
from genomeos.validation.reference_b0h_fold import B0HAttempt, B0HFoldResult


def synthetic_results():
    config = PopulationHeterogeneityConfig(1, 1, 1, 9, draws=2, tune=3, seed=17)
    fit = synthetic_fit(synthetic_rows(), config=config)
    accepted = B0HAttempt("initial", config, "accepted", None, 0, fit.diagnostics)
    retry = B0HAttempt(
        "retry", replace(config, draws=4, tune=6, seed=19), "not_attempted", "initial_accepted"
    )
    return tuple(
        (
            f"split:{i}/é",
            B0HFoldResult(
                "failed",
                "scoring",
                "ValueError: synthetic scoring refusal",
                (accepted, retry),
                fit,
                None,
                None,
                (),
            ),
        )
        for i in range(5)
    )


def synthetic_publication(results=None):
    results = synthetic_results() if results is None else results
    diagnostics, draws, posteriors = subject.encode_b0h(results)
    configuration = {
        "source_release": "synthetic",
        "cohort_stage": "synthetic",
        "count_kind": "quality",
        "evidence_role": "synthetic",
        "prior_alpha": 1.0,
        "prior_beta": 1.0,
        "folds": 5,
        "seed": 42,
        "model": subject.MODEL,
        "rho_prior_alpha": 1.0,
        "rho_prior_beta": 9.0,
        "draws": 2,
        "tune": 3,
        "chains": 4,
        "target_accept": 0.9,
        "cdf_backend": "scipy",
    }
    files = {name: b"synthetic supporting file\n" for name in subject.B0H_OUTPUT_FILENAMES}
    files.update(
        {
            "fit_diagnostics.json": diagnostics,
            "posterior_draws.npz": draws,
            "posteriors.tsv": posteriors.to_csv(sep="\t", index=False, lineterminator="\n").encode(),
            "splits.json": subject.json_bytes(
                {"folds": [{"split_id": split_id, "status": result.status} for split_id, result in results]}
            ),
            "summary.json": subject.json_bytes({"comparison_complete": False}),
        }
    )
    unavailable = {"status": "unavailable", "value": None, "reason": "synthetic unobserved"}
    manifest = {
        "schema_version": 2,
        "model": subject.MODEL,
        "target": "reference_panel_within_resource",
        "joint_prediction_supported": False,
        "limitations": ["synthetic only"],
        "configuration": configuration,
        "dependency_qualification": "synthetic",
        "input_files": {name: subject.fingerprint(b"synthetic input") for name in ("counts", "dependencies")},
        "git": {"head": "0" * 40, "dirty": False},
        "science_source_sha256": {"synthetic/source.py": "0" * 64},
        "package_versions": {
            name: "synthetic-version"
            for name in (
                "numpy",
                "scipy",
                "pandas",
                "pymc",
                "pytensor",
                "arviz",
                "xarray",
                "numpyro",
                "jax",
                "jaxlib",
            )
        },
        "runtime": {key: unavailable for key in ("python_version", "jax_backend", "cdf_backend")},
        "seeds": {
            "root": 42,
            "split": 1,
            "pit_by_fold": {key: 23 for key, result in results},
            "fit_by_fold": {key: {"initial": 17, "retry": 19} for key, result in results},
        },
        "output_files": {key: subject.fingerprint(value) for key, value in files.items()},
    }
    files["manifest.json"] = subject.json_bytes(manifest)
    return files


def refresh(files, name, data):
    files[name] = data
    manifest = json.loads(files["manifest.json"])
    manifest["output_files"][name] = subject.fingerprint(data)
    files["manifest.json"] = subject.json_bytes(manifest)


def test_exact_repeatable_bytes_unicode_and_retained_failed_folds():
    first = synthetic_publication()
    assert first == synthetic_publication()
    arrays = subject.validate_b0h_publication(first)
    assert len(arrays) == 15
    ids = arrays["fold_0000__variant_ids"]
    assert ids.dtype.str == "<U4" and ids.tolist() == ["001", "NA", "é:/v"]
    assert arrays["fold_0000__mean_draws"].shape == (4, 2, 3)
    assert arrays["fold_0000__mean_draws"].dtype.str == "<f8"
    diagnostics = json.loads(first["fit_diagnostics.json"])
    assert [fold["split_id"] for fold in diagnostics["folds"]] == [key for key, result in synthetic_results()]
    assert all(
        fold["status"] == "failed" and fold["posterior_status"] == "retained" for fold in diagnostics["folds"]
    )
    with zipfile.ZipFile(io.BytesIO(first["posterior_draws.npz"])) as archive:
        assert archive.namelist() == sorted(archive.namelist())
        for item in archive.infolist():
            assert item.date_time == (1980, 1, 1, 0, 0, 0)
            assert item.compress_type == zipfile.ZIP_STORED
            assert item.create_system == 3 and item.external_attr == 0o600 << 16
            assert item.internal_attr == item.flag_bits == 0
            assert item.create_version == item.extract_version == 20
            assert item.extra == item.comment == b""
            assert archive.read(item)[:8] == b"\x93NUMPY\x01\x00"
    _, _, frame = subject.encode_b0h(synthetic_results())
    assert tuple(frame.columns) == subject.B0H_POSTERIOR_COLUMNS
    assert set(frame.training_ac) == {6} and set(frame.training_an) == {24}
    assert set(frame.training_observation_count) == {6}
    assert np.allclose(frame.posterior_mean_mean, 0.25)
    assert np.allclose(frame.posterior_rho_mean, 0.1)


def test_empty_accepted_set_is_valid_empty_archive():
    records = []
    for split, result in synthetic_results():
        initial = replace(
            result.attempts[0],
            status="failed",
            reason="ValueError: synthetic",
            diagnostics=(),
            divergence_count=None,
        )
        retry = replace(result.attempts[1], reason="initial_not_retryable")
        records.append((split, replace(result, failure_phase="fit", fit=None, attempts=(initial, retry))))
    files = synthetic_publication(tuple(records))
    assert subject.validate_b0h_publication(files) == {}
    assert files["posteriors.tsv"].decode().splitlines() == ["\t".join(subject.B0H_POSTERIOR_COLUMNS)]


def test_accepted_retry_uses_its_own_dimensions_and_keeps_failed_initial():
    records = []
    for split, result in synthetic_results():
        initial = replace(
            result.attempts[0],
            status="convergence_failed",
            reason="synthetic initial divergence",
            divergence_count=1,
        )
        fit = synthetic_fit(synthetic_rows(), config=result.attempts[1].config)
        retry = replace(
            result.attempts[1],
            status="accepted",
            reason=None,
            divergence_count=0,
            diagnostics=fit.diagnostics,
        )
        records.append((split, replace(result, fit=fit, attempts=(initial, retry))))
    files = synthetic_publication(tuple(records))
    arrays = subject.validate_b0h_publication(files)
    assert arrays["fold_0000__mean_draws"].shape == (4, 4, 3)
    initial = json.loads(files["fit_diagnostics.json"])["folds"][0]["attempts"][0]
    assert initial["status"] == "convergence_failed" and initial["divergence_count"] == 1


@pytest.mark.parametrize("mode", ["missing", "extra", "hash", "schema", "mapping", "diagnostic"])
def test_publication_corruption_is_refused(mode):
    files = synthetic_publication()
    if mode == "missing":
        del files["manifest.json"]
    elif mode == "extra":
        files["extra"] = b"synthetic"
    elif mode == "hash":
        files["posterior_draws.npz"] += b"synthetic corruption"
    elif mode == "schema":
        manifest = json.loads(files["manifest.json"])
        manifest["schema_version"] = 1
        files["manifest.json"] = subject.json_bytes(manifest)
    else:
        document = json.loads(files["fit_diagnostics.json"])
        if mode == "mapping":
            document["folds"][0]["posterior_prefix"] = "fold_0001"
        else:
            document["folds"][0]["attempts"][0]["diagnostics"][0]["max_rhat"] = 1.2
        refresh(files, "fit_diagnostics.json", subject.json_bytes(document))
    with pytest.raises((ValueError, KeyError)):
        subject.validate_b0h_publication(files)


@pytest.mark.parametrize("mode", ["object", "extra", "missing", "duplicate", "float32", "shape", "ids"])
def test_npz_corruption_even_with_updated_fingerprint_is_refused(mode):
    files = synthetic_publication()
    with np.load(io.BytesIO(files["posterior_draws.npz"]), allow_pickle=False) as loaded:
        arrays = {key: loaded[key] for key in loaded.files}
    key = "fold_0000__mean_draws"
    if mode == "object":
        arrays[key] = np.array(["synthetic"], dtype=object)
    elif mode == "extra":
        arrays["extra"] = np.zeros(1)
    elif mode == "missing":
        del arrays[key]
    elif mode == "float32":
        arrays[key] = arrays[key].astype(np.float32)
    elif mode == "shape":
        arrays[key] = arrays[key].reshape(8, 3)
    elif mode == "ids":
        arrays["fold_0000__variant_ids"] = np.array(["NA", "001", "é:/v"])
    buffer = io.BytesIO()
    np.savez(buffer, **arrays)
    if mode == "duplicate":
        with zipfile.ZipFile(buffer, "a") as archive:
            with pytest.warns(UserWarning, match="Duplicate name"):
                archive.writestr(key + ".npy", archive.read(key + ".npy"))
    refresh(files, "posterior_draws.npz", buffer.getvalue())
    with pytest.raises(ValueError):
        subject.validate_b0h_publication(files)
