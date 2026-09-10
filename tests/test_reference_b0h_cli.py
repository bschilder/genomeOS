"""Synthetic B0H CLI integration; no calibration or real-fit evidence (design §§5, 7–8, 12)."""

from __future__ import annotations

import csv
import importlib.util
import json
import subprocess
import sys
from dataclasses import asdict, replace

import pandas as pd
import pytest
from reference_b0h_synthetic import synthetic_fit, synthetic_rows
from test_reference_counts_cli import SCRIPT, _command, _run

import genomeos.validation.reference_b0h_fold as fold_module
from genomeos.surfaces.heterogeneity_types import HeterogeneityConvergenceError
from genomeos.validation.reference_b0h_artifacts import validate_b0h_publication


def load_runner():
    specification = importlib.util.spec_from_file_location("synthetic_reference_b0h_runner", SCRIPT)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def synthetic_args(tmp_path, runner, *, out_name="out", extra=()):
    counts = tmp_path / "synthetic-counts.tsv"
    rows = list(synthetic_rows())
    rows[0] = replace(rows[0], ac=0, an=0)
    with counts.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=runner.COUNT_COLUMNS, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(asdict(row) for row in rows)
    dependencies = tmp_path / "synthetic-dependencies.json"
    dependencies.write_text('{"edges": [], "qualification": "synthetic only"}\n', encoding="utf-8")
    command = _command(tmp_path / out_name, counts=counts, dependencies=dependencies, folds=5)
    return runner._parser().parse_args(
        command[2:]
        + [
            "--model",
            "B0H_population_heterogeneity",
            "--rho-prior-alpha",
            "1",
            "--rho-prior-beta",
            "9",
            "--draws",
            "2",
            "--tune",
            "3",
            *extra,
        ]
    )


def read_files(out):
    return {path.name: path.read_bytes() for path in out.iterdir()}


def test_legacy_default_and_explicit_model_scipy_are_byte_equal(tmp_path):
    first, second = tmp_path / "legacy", tmp_path / "explicit"
    assert _run(_command(first)).returncode == 0
    explicit = _command(second) + ["--model", "pooled_beta_counts", "--cdf-backend", "scipy"]
    assert _run(explicit).returncode == 0
    assert read_files(first) == read_files(second)
    manifest = json.loads((first / "manifest.json").read_bytes())
    assert manifest["schema_version"] == 1
    assert "model" not in manifest and "runtime" not in manifest
    assert len(read_files(first)) == 6


@pytest.mark.parametrize(
    "option, value",
    [
        ("--rho-prior-alpha", "1"),
        ("--rho-prior-beta", "9"),
        ("--draws", "500"),
        ("--tune", "1000"),
        ("--chains", "4"),
        ("--target-accept", "0.9"),
        ("--cdf-backend", "cupy"),
    ],
)
def test_b0_rejects_every_explicit_b0h_setting(tmp_path, option, value):
    out = tmp_path / "out"
    assert _run(_command(out) + [option, value]).returncode != 0
    assert not out.exists()


def test_b0_startup_help_validation_and_execution_need_no_surfaces_extra(tmp_path):
    bootstrap = (
        "import importlib.abc, runpy, sys\n"
        "class Block(importlib.abc.MetaPathFinder):\n"
        " def find_spec(self, fullname, path=None, target=None):\n"
        "  if fullname.split('.')[0] in {'pymc','pytensor','arviz','numpyro','jax','jaxlib','xarray'}"
        " or fullname.startswith('genomeos.surfaces'):\n"
        "   raise ModuleNotFoundError('synthetic blocked surfaces extra: ' + fullname)\n"
        "sys.meta_path.insert(0, Block())\n"
        "script = sys.argv.pop(1)\n"
        "runpy.run_path(script, run_name='__main__')\n"
    )
    base = [sys.executable, "-c", bootstrap, str(SCRIPT)]
    assert subprocess.run(base + ["--help"], capture_output=True).returncode == 0
    result = subprocess.run(base + _command(tmp_path / "out")[2:], capture_output=True)
    assert result.returncode == 0, result.stderr
    invalid = subprocess.run(
        base + _command(tmp_path / "invalid")[2:] + ["--draws", "500"], capture_output=True
    )
    assert invalid.returncode != 0
    assert b"synthetic blocked" not in invalid.stderr


@pytest.mark.parametrize(
    "field, value",
    [
        ("rho_prior_alpha", None),
        ("rho_prior_beta", None),
        ("folds", 4),
        ("chains", 3),
        ("draws", 0),
        ("tune", 0),
        ("target_accept", 1.0),
    ],
)
def test_b0h_invalid_configuration_refuses_before_fit(tmp_path, monkeypatch, field, value):
    runner = load_runner()
    args = synthetic_args(tmp_path, runner)
    setattr(args, field, value)

    def forbidden(*args, **kwargs):
        pytest.fail("invalid configuration reached fitter")

    monkeypatch.setattr(fold_module, "fit_reference_population_heterogeneity", forbidden)
    with pytest.raises(ValueError):
        runner.run(args)
    assert not args.out.exists()


def test_b0h_absent_sampler_options_use_public_config_defaults(tmp_path):
    runner = load_runner()
    args = synthetic_args(tmp_path, runner)
    for field in ("draws", "tune", "chains", "target_accept"):
        setattr(args, field, None)
    config = runner._model_config(args)
    assert (config.draws, config.tune, config.chains, config.target_accept) == (500, 1000, 4, 0.9)
    assert (config.mean_prior_alpha, config.mean_prior_beta) == (1.0, 1.0)
    assert not args.out.exists()


def test_mocked_fivefold_publication_is_repeatable_and_training_only(tmp_path, monkeypatch):
    runner = load_runner()
    calls = []

    def capture(training, *, config):
        calls.append((tuple(training), config))
        return synthetic_fit(training, config=config)

    monkeypatch.setattr(fold_module, "fit_reference_population_heterogeneity", capture)
    first = synthetic_args(tmp_path, runner, out_name="first")
    second = synthetic_args(tmp_path, runner, out_name="second")
    assert runner.run(first) == runner.run(second) == 0
    assert read_files(first.out) == read_files(second.out)
    files = read_files(first.out)
    arrays = validate_b0h_publication(files)
    assert len(arrays) == 15 and len(calls) == 10
    manifest = json.loads(files["manifest.json"])
    splits = json.loads(files["splits.json"])["folds"]
    for index, split in enumerate(splits):
        training, config = calls[index]
        assert {row.record_id for row in training} == set(split["train_ids"])
        assert not {row.record_id for row in training} & set(split["test_ids"])
        assert config.seed == manifest["seeds"]["fit_by_fold"][split["split_id"]]["initial"]
    legacy_split, legacy_pit = runner._seeds(42, 5)
    assert manifest["seeds"]["split"] == legacy_split
    assert list(manifest["seeds"]["pit_by_fold"].values()) == list(legacy_pit)
    rows = pd.read_csv(first.out / "row_status.tsv", sep="\t", keep_default_na=False)
    assert len(rows) == 18 and (rows.status == "unavailable_denominator").sum() == 1
    assert manifest["runtime"]["jax_backend"]["status"] == "unavailable"
    assert manifest["runtime"]["cdf_backend"]["status"] == "unavailable"


@pytest.mark.parametrize("failure", ["convergence", "numeric", "prediction", "scoring"])
def test_failed_fold_ledger_and_accepted_fit_retention(tmp_path, monkeypatch, failure):
    runner = load_runner()
    args = synthetic_args(tmp_path, runner)
    calls = []
    fail_training = None

    def fit(training, *, config):
        nonlocal fail_training
        identity = tuple(row.record_id for row in training)
        if fail_training is None:
            fail_training = identity
        calls.append(config)
        if identity == fail_training and failure == "convergence":
            raise HeterogeneityConvergenceError("synthetic terminal convergence failure")
        if identity == fail_training and failure == "numeric":
            raise ArithmeticError("synthetic numeric failure")
        return synthetic_fit(training, config=config)

    monkeypatch.setattr(fold_module, "fit_reference_population_heterogeneity", fit)
    if failure in {"prediction", "scoring"}:
        name = (
            "predict_reference_population_heterogeneity"
            if failure == "prediction"
            else "predictive_diagnostics"
        )
        original = getattr(fold_module, name)
        invoked = False

        def fail_once(*args, **kwargs):
            nonlocal invoked
            if not invoked:
                invoked = True
                raise ValueError("synthetic later failure")
            return original(*args, **kwargs)

        monkeypatch.setattr(fold_module, name, fail_once)
    assert runner.run(args) == 2
    files = read_files(args.out)
    arrays = validate_b0h_publication(files)
    document = json.loads(files["fit_diagnostics.json"])
    first = document["folds"][0]
    assert first["status"] == "failed"
    assert all(fold["status"] == "completed" for fold in document["folds"][1:])
    assert len(calls) == (6 if failure == "convergence" else 5)
    if failure in {"prediction", "scoring"}:
        assert first["posterior_status"] == "retained"
        assert len(arrays) == 15 and first["attempts"][0]["status"] == "accepted"
    else:
        assert first["posterior_status"] == "not_available" and len(arrays) == 12
    if failure == "convergence":
        assert [item["status"] for item in first["attempts"]] == ["convergence_failed"] * 2
        assert calls[1].draws == 4 and calls[1].tune == 6
    predictions = pd.read_csv(args.out / "predictions.tsv", sep="\t", keep_default_na=False)
    assert first["split_id"] not in set(predictions.split_id)
    rows = pd.read_csv(args.out / "row_status.tsv", sep="\t", keep_default_na=False)
    assert len(rows) == 18 and (rows.status == "unavailable_denominator").sum() == 1


def test_missing_only_test_fold_never_fits_and_is_accounted(tmp_path, monkeypatch):
    runner = load_runner()
    args = synthetic_args(tmp_path, runner)
    rows = runner._read_counts(args.counts.read_bytes())
    split_seed, _pit = runner._seeds(args.seed, 5)
    folds = runner.reference_group_folds(rows, dependency_edges=(), n_folds=5, seed=split_seed)
    missing_ids = set(folds[0].test_ids)
    with args.counts.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=runner.COUNT_COLUMNS, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(
            asdict(replace(row, ac=0, an=0) if row.record_id in missing_ids else row) for row in rows
        )
    calls = []

    def fit(training, *, config):
        calls.append(config)
        return synthetic_fit(training, config=config)

    monkeypatch.setattr(fold_module, "fit_reference_population_heterogeneity", fit)
    assert runner.run(args) == 2 and len(calls) == 4
    validate_b0h_publication(read_files(args.out))
    status = pd.read_csv(args.out / "row_status.tsv", sep="\t", keep_default_na=False)
    assert set(status.loc[status.record_id.isin(missing_ids), "status"]) == {"unavailable_denominator"}


@pytest.mark.parametrize("phase", ["fit", "backend", "publication"])
def test_interruptions_never_publish_valid_completion(tmp_path, monkeypatch, phase):
    runner = load_runner()
    args = synthetic_args(tmp_path, runner)
    monkeypatch.setattr(fold_module, "fit_reference_population_heterogeneity", synthetic_fit)
    if phase == "publication":
        original = runner._json_write

        def interrupted(path, value):
            if path.name == "manifest.json":
                raise OSError("synthetic interrupted publication")
            return original(path, value)

        monkeypatch.setattr(runner, "_json_write", interrupted)
        error_type = OSError
    else:

        def interrupted(*args, **kwargs):
            raise RuntimeError("synthetic unavailable backend/interruption")

        name = "fit_reference_population_heterogeneity" if phase == "fit" else "predictive_diagnostics"
        monkeypatch.setattr(fold_module, name, interrupted)
        error_type = RuntimeError
    with pytest.raises(error_type):
        runner.run(args)
    assert not (args.out / "manifest.json").exists()
    if args.out.exists():
        with pytest.raises(ValueError):
            validate_b0h_publication(read_files(args.out))


def test_b0h_output_reuse_and_provenance_failure_refuse_before_fit(tmp_path, monkeypatch):
    from scripts import reference_b0h_provenance as provenance

    runner = load_runner()
    args = synthetic_args(tmp_path, runner)
    monkeypatch.setattr(fold_module, "fit_reference_population_heterogeneity", synthetic_fit)
    assert runner.run(args) == 0
    before = read_files(args.out)
    with pytest.raises(ValueError, match="already exists"):
        runner.run(args)
    assert before == read_files(args.out)
    other = synthetic_args(tmp_path, runner, out_name="refused")

    def fail(*args, **kwargs):
        raise ValueError("synthetic provenance failure")

    monkeypatch.setattr(provenance, "b0h_source_hashes", fail)
    with pytest.raises(ValueError, match="synthetic provenance failure"):
        runner.run(other)
    assert not other.out.exists()
