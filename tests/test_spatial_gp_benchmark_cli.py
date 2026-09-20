"""Reproducible current-GP benchmark adapter (design §§5, 7–8, 12; #189)."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from genomeos.observations.schema import OBSERVATIONS_SCHEMA
from genomeos.surfaces.config import FitConfig
from genomeos.surfaces.convergence import SamplerDiagnostics
from genomeos.surfaces.fit import ConvergenceError
from genomeos.surfaces.observation import (
    ObservationModelMetadata,
    ObservationParameters,
    SurveyQueries,
)

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "benchmark_spatial_gp.py"
VARIANT = "chr11-5227002-T-A"
GOOD_DIAGNOSTICS = SamplerDiagnostics(1.01, "z", 300.0, "z", 260.0, "z", 0)
BAD_DIAGNOSTICS = SamplerDiagnostics(1.08, "z", 150.0, "z", 180.0, "z", 1)


def _write_inputs(root: Path, *, large_denominator: bool = False) -> dict[str, Path]:
    denominator = [100, 120, 140, 160]
    if large_denominator:
        denominator[2] = 65_537
    observations = OBSERVATIONS_SCHEMA.validate(
        pd.DataFrame(
            {
                "variant_id": VARIANT,
                "rsid": "rs334",
                "population_id": ["pop-a", "pop-b", "pop-c", "pop-d"],
                "lat": [-45.0, -15.0, 15.0, 45.0],
                "lon": [-120.0, -40.0, 40.0, 120.0],
                "radius_km": 1.0,
                "ac": [1, 2, 3, 4],
                "an": denominator,
                "source_record_id": ["obs-a", "obs-b", "obs-c", "obs-d"],
                "source": "synthetic",
                "assay": "genotype",
                "date_lower": 0,
                "date_upper": 0,
                "sampling_design": "population_random",
                "disease_ascertainment_excluded": True,
                "cohort_id": ["cohort-a", "cohort-b", "cohort-c", "cohort-d"],
                "ingest_version": "test-v1",
            }
        )
    )
    assignments = pd.DataFrame(
        {
            "source_record_id": ["obs-a", "obs-b", "obs-c", "obs-d"],
            "block_id": ["block-a", "block-b", "block-c", "block-d"],
            "region_id": ["region-1", "region-1", "region-2", "region-2"],
            "variant_group": "hbs",
        }
    )
    paths = {
        "observations": root / "observations.tsv",
        "assignments": root / "assignments.tsv",
        "dependencies": root / "dependencies.tsv",
        "fit_config": root / "fit-config.json",
    }
    observations.to_csv(paths["observations"], sep="\t", index=False, lineterminator="\n")
    assignments.to_csv(paths["assignments"], sep="\t", index=False, lineterminator="\n")
    paths["dependencies"].write_text("source_record_id_a\tsource_record_id_b\n")
    paths["fit_config"].write_text(
        json.dumps(asdict(FitConfig(likelihood="beta_binomial")), indent=2, sort_keys=True) + "\n"
    )
    return paths


def _command(
    paths: dict[str, Path],
    out: Path,
    *,
    checkpoint: Path | None = None,
    resume_from: Path | None = None,
) -> list[str]:
    command = [
        sys.executable,
        str(SCRIPT),
        "--observations",
        str(paths["observations"]),
        "--assignments",
        str(paths["assignments"]),
        "--dependencies",
        str(paths["dependencies"]),
        "--fit-config",
        str(paths["fit_config"]),
        "--data-version",
        "fixture-v1",
        "--buffer-km",
        "10",
        "--seed",
        "42",
        "--cdf-backend",
        "scipy",
        "--evidence-kind",
        "synthetic_fixture",
        "--assignment-review-status",
        "reviewed",
        "--dependency-review-status",
        "not_checked",
    ]
    if resume_from is None:
        command.extend(("--checkpoint-dir", str(checkpoint or out.with_name(out.name + "-checkpoint"))))
    else:
        command.extend(("--resume-from", str(resume_from)))
    command.extend(("--out", str(out)))
    return command


def _run(command: list[str], *, pythonpath: Path = ROOT) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(pythonpath)
    return subprocess.run(command, capture_output=True, text=True, env=environment, check=False)


def _load_runner(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    assert spec is not None and spec.loader is not None
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    return runner


@dataclass
class _FakeFit:
    training_cohorts: tuple[str, ...]
    likelihood: str
    fail_prediction: bool = False
    idata: object = None

    def predict_new_cohort_parameters(self, queries: SurveyQueries, *, seed: int) -> ObservationParameters:
        if self.fail_prediction:
            raise RuntimeError("controlled terminal fold failure")
        assert not set(queries.cohort_ids) & set(self.training_cohorts)
        draws = 8
        mean = np.broadcast_to(
            np.linspace(0.01, 0.08, len(queries.observation_ids)),
            (draws, len(queries.observation_ids)),
        )
        concentration = np.full(mean.shape, 30.0) if self.likelihood == "beta_binomial" else None
        return ObservationParameters(
            queries=queries,
            metadata=ObservationModelMetadata(
                convention="new_cohort_count_v1",
                fitted_designs=("population_random",),
                training_cohort_ids=self.training_cohorts,
                cohort_effect_applied=True,
                nugget_applied=False,
                likelihood=self.likelihood,
            ),
            draw_ids=tuple((0, draw) for draw in range(draws)),
            mean_draws=mean,
            concentration=concentration,
        )


def _install_fake_fit(
    runner,
    monkeypatch,
    *,
    interrupt_once_after: int | None = None,
    fail_on_call: int | None = None,
    convergence_failure_on_call: int | None = None,
):
    real_evaluate = runner.evaluate_single_variant_gp_fold
    calls: list[str] = []
    interrupted = False
    monkeypatch.setattr(
        "genomeos.validation.spatial_gp_benchmark.summarize_sampler_diagnostics",
        lambda *_args, **_kwargs: GOOD_DIAGNOSTICS,
    )

    def evaluate(plan, split, **kwargs):
        nonlocal interrupted
        if interrupt_once_after == len(calls) and not interrupted:
            interrupted = True
            raise KeyboardInterrupt("controlled fold-boundary interruption")
        call_index = len(calls)
        calls.append(split.split_id)

        def fit(observations: pd.DataFrame, config: FitConfig) -> _FakeFit:
            if call_index == convergence_failure_on_call:
                raise ConvergenceError(
                    "sampler did not converge (synthetic gate failure)",
                    diagnostics=BAD_DIAGNOSTICS,
                )
            return _FakeFit(
                tuple(sorted(observations["cohort_id"].unique())),
                config.likelihood,
                fail_prediction=call_index == fail_on_call,
            )

        return real_evaluate(plan, split, fit_function=fit, **kwargs)

    monkeypatch.setattr(runner, "evaluate_single_variant_gp_fold", evaluate)
    return calls


def test_runner_writes_reproducible_current_gp_evidence(tmp_path, monkeypatch):
    paths = _write_inputs(tmp_path)
    runner = _load_runner("spatial_gp_runner_success")
    _install_fake_fit(runner, monkeypatch)
    args = runner._parser().parse_args(_command(paths, tmp_path / "first")[2:])

    assert runner.run(args) == 0
    args.out = tmp_path / "second"
    args.checkpoint_dir = tmp_path / "second-checkpoint"
    assert runner.run(args) == 0

    first = tmp_path / "first"
    second = tmp_path / "second"
    assert {path.name: path.read_bytes() for path in first.iterdir()} == {
        path.name: path.read_bytes() for path in second.iterdir()
    }
    assert sorted(path.name for path in first.iterdir()) == [
        "fold_status.tsv",
        "inventory.json",
        "manifest.json",
        "predictions.tsv",
        "summary.json",
    ]
    manifest = json.loads((first / "manifest.json").read_text())
    assert manifest["schema_version"] == 2
    assert manifest["model"] == {
        "model_id": "B2-current",
        "name": "current_single_variant_spatial_gp",
        "resident_calibrated": False,
        "survey_heterogeneity_model": True,
    }
    assert manifest["qualification"] == {
        "assignment_review_status": "reviewed",
        "dependency_review_status": "not_checked",
        "scientific_promotion_decision": "not_made",
    }
    assert manifest["publication_eligible"] is False
    assert manifest["configuration"]["fit_config"]["likelihood"] == "beta_binomial"
    assert manifest["configuration"]["sampler_convergence_gate"] == {
        "maximum_divergences": 0,
        "maximum_rhat": 1.05,
        "minimum_bulk_ess": 200.0,
        "minimum_tail_ess": 200.0,
    }
    assert len(manifest["configuration_sha256"]) == 64
    assert len(manifest["inputs_sha256"]) == 64
    assert len(manifest["split_manifest_sha256"]) == 64
    assert set(manifest["science_source_sha256"]) >= {
        "genomeos/surfaces/convergence.py",
        "genomeos/surfaces/fit.py",
        "genomeos/validation/spatial_gp_benchmark.py",
        "scripts/benchmark_spatial_gp.py",
    }
    predictions = pd.read_csv(first / "predictions.tsv", sep="\t")
    assert len(predictions) == 4
    assert set(predictions["variant_id"]) == {VARIANT}
    statuses = pd.read_csv(first / "fold_status.tsv", sep="\t")
    assert set(statuses["max_rhat"]) == {GOOD_DIAGNOSTICS.max_rhat}
    assert set(statuses["min_bulk_ess"]) == {GOOD_DIAGNOSTICS.min_bulk_ess}
    assert set(statuses["min_tail_ess"]) == {GOOD_DIAGNOSTICS.min_tail_ess}
    assert set(statuses["divergence_count"]) == {0}
    assert all(split["sampler_diagnostics"] for split in manifest["splits"])
    assert json.loads((first / "summary.json").read_text())["benchmark"]["comparison_complete"] is True
    for name, record in manifest["output_files"].items():
        content = (first / name).read_bytes()
        assert record == {
            "sha256": hashlib.sha256(content).hexdigest(),
            "size_bytes": len(content),
        }


def test_runner_scores_denominator_above_old_limit(tmp_path, monkeypatch):
    paths = _write_inputs(tmp_path, large_denominator=True)
    output = tmp_path / "large-denominator"
    runner = _load_runner("spatial_gp_runner_large_denominator")
    _install_fake_fit(runner, monkeypatch)
    args = runner._parser().parse_args(_command(paths, output)[2:])

    result = runner.run(args)

    assert result == 0
    statuses = pd.read_csv(output / "fold_status.tsv", sep="\t", keep_default_na=False)
    assert set(statuses["status"]) == {"completed"}
    predictions = pd.read_csv(output / "predictions.tsv", sep="\t")
    assert 65_537 in set(predictions["observed_an"])
    summary = json.loads((output / "summary.json").read_text())
    assert summary["benchmark"]["comparison_complete"] is True
    assert summary["benchmark"]["split_counts"]["completed"] == 4


def test_runner_refuses_implicit_config_defaults_and_existing_output(tmp_path):
    paths = _write_inputs(tmp_path)
    config = json.loads(paths["fit_config"].read_text())
    del config["likelihood"]
    paths["fit_config"].write_text(json.dumps(config))
    output = tmp_path / "output"

    missing = _run(_command(paths, output))

    assert missing.returncode == 2
    assert "exactly the FitConfig fields" in missing.stderr
    assert not output.exists()

    output.mkdir()
    marker = output / "keep.txt"
    marker.write_text("untouched")
    existing = _run(_command(paths, output))
    assert existing.returncode == 2
    assert "already exists" in existing.stderr
    assert marker.read_text() == "untouched"


def test_runner_refuses_overlapping_checkpoint_and_output_directories(tmp_path):
    paths = _write_inputs(tmp_path)
    runner = _load_runner("spatial_gp_runner_overlapping_paths")
    output = tmp_path / "same"
    args = runner._parser().parse_args(_command(paths, output, checkpoint=output)[2:])

    with pytest.raises(ValueError, match="must be disjoint"):
        runner.run(args)

    assert not output.exists()


def test_runner_bootstraps_the_checked_out_science_sources(tmp_path):
    paths = _write_inputs(tmp_path)
    conflicting = tmp_path / "conflicting"
    package = conflicting / "genomeos"
    package.mkdir(parents=True)
    package.joinpath("__init__.py").write_text(
        'raise RuntimeError("synthetic wrong-checkout genomeos imported")\n'
    )

    command = _command(paths, tmp_path / "run")
    command[command.index("--buffer-km") + 1] = "20000"
    completed = _run(command, pythonpath=conflicting)

    assert completed.returncode == 1, completed.stderr
    assert "synthetic wrong-checkout" not in completed.stderr
    manifest = json.loads((tmp_path / "run" / "manifest.json").read_text())
    expected = hashlib.sha256((ROOT / "genomeos/validation/spatial_gp_benchmark.py").read_bytes()).hexdigest()
    assert manifest["science_source_sha256"]["genomeos/validation/spatial_gp_benchmark.py"] == expected


def test_runner_resumes_a_terminal_fold_prefix_with_byte_identical_publication(tmp_path, monkeypatch):
    paths = _write_inputs(tmp_path)
    checkpoint = tmp_path / "interrupted-checkpoint"
    resumed_out = tmp_path / "resumed"
    runner = _load_runner("spatial_gp_runner_resume")
    calls = _install_fake_fit(runner, monkeypatch, interrupt_once_after=2)
    interrupted = runner._parser().parse_args(_command(paths, resumed_out, checkpoint=checkpoint)[2:])

    with pytest.raises(KeyboardInterrupt, match="controlled"):
        runner.run(interrupted)

    assert not resumed_out.exists()
    assert sorted(path.name for path in (checkpoint / "folds").iterdir()) == [
        "0000.json",
        "0001.json",
    ]
    resumed = runner._parser().parse_args(_command(paths, resumed_out, resume_from=checkpoint)[2:])
    assert runner.run(resumed) == 0
    assert len(calls) == 4

    uninterrupted_out = tmp_path / "uninterrupted"
    uninterrupted_runner = _load_runner("spatial_gp_runner_uninterrupted")
    uninterrupted_calls = _install_fake_fit(uninterrupted_runner, monkeypatch)
    uninterrupted = uninterrupted_runner._parser().parse_args(
        _command(paths, uninterrupted_out, checkpoint=tmp_path / "complete-checkpoint")[2:]
    )
    assert uninterrupted_runner.run(uninterrupted) == 0
    assert len(uninterrupted_calls) == 4
    assert {path.name: path.read_bytes() for path in resumed_out.iterdir()} == {
        path.name: path.read_bytes() for path in uninterrupted_out.iterdir()
    }


def test_final_publication_is_atomic_when_manifest_write_fails(tmp_path, monkeypatch):
    paths = _write_inputs(tmp_path)
    output = tmp_path / "publication"
    runner = _load_runner("spatial_gp_runner_atomic")
    _install_fake_fit(runner, monkeypatch)
    real_json_write = runner._json_write

    def fail_manifest(path, value):
        if path.name == "manifest.json":
            raise OSError("controlled manifest failure")
        real_json_write(path, value)

    monkeypatch.setattr(runner, "_json_write", fail_manifest)
    args = runner._parser().parse_args(_command(paths, output)[2:])

    with pytest.raises(OSError, match="controlled manifest failure"):
        runner.run(args)

    assert not output.exists()
    assert not list(tmp_path.glob(".publication.partial-*"))
    assert len(list((tmp_path / "publication-checkpoint" / "folds").glob("*.json"))) == 4


def test_resume_reuses_a_terminal_failed_fold_without_selective_retry(tmp_path, monkeypatch):
    paths = _write_inputs(tmp_path)
    checkpoint = tmp_path / "failed-checkpoint"
    first_out = tmp_path / "failed-first"
    runner = _load_runner("spatial_gp_runner_failed_resume")
    calls = _install_fake_fit(runner, monkeypatch, convergence_failure_on_call=1)
    first = runner._parser().parse_args(_command(paths, first_out, checkpoint=checkpoint)[2:])

    assert runner.run(first) == 1
    assert len(calls) == 4
    statuses = pd.read_csv(first_out / "fold_status.tsv", sep="\t")
    assert list(statuses["status"]).count("failed") == 1
    failed = statuses.loc[statuses["status"] == "failed"].iloc[0]
    assert failed["max_rhat"] == BAD_DIAGNOSTICS.max_rhat
    assert failed["divergence_count"] == BAD_DIAGNOSTICS.divergence_count

    resumed_out = tmp_path / "failed-resumed"
    resumed = runner._parser().parse_args(_command(paths, resumed_out, resume_from=checkpoint)[2:])
    assert runner.run(resumed) == 1
    assert len(calls) == 4
    assert {path.name: path.read_bytes() for path in first_out.iterdir()} == {
        path.name: path.read_bytes() for path in resumed_out.iterdir()
    }


@pytest.mark.parametrize(
    "change",
    [
        {"max_rhat": 1.051},
        {"min_bulk_ess": 199.0},
        {"min_tail_ess": 199.0},
        {"divergence_count": 1},
    ],
)
def test_resume_refuses_contradictory_fold_before_fitting_or_publication(tmp_path, monkeypatch, change):
    paths = _write_inputs(tmp_path)
    checkpoint = tmp_path / "checkpoint"
    output = tmp_path / "output"
    runner = _load_runner("spatial_gp_runner_contradictory_checkpoint")
    calls = _install_fake_fit(runner, monkeypatch, interrupt_once_after=1)
    args = runner._parser().parse_args(_command(paths, output, checkpoint=checkpoint)[2:])
    with pytest.raises(KeyboardInterrupt):
        runner.run(args)
    path = checkpoint / "folds" / "0000.json"
    document = json.loads(path.read_text())
    document["sampler_diagnostics"].update(change)
    body = {key: value for key, value in document.items() if key != "artifact_sha256"}
    document["artifact_sha256"] = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    path.write_text(json.dumps(document))
    original = path.read_bytes()
    resumed = runner._parser().parse_args(_command(paths, output, resume_from=checkpoint)[2:])

    with pytest.raises(ValueError, match="completed fold.*convergence"):
        runner.run(resumed)

    assert len(calls) == 1
    assert not output.exists()
    assert path.read_bytes() == original


def test_fresh_runner_refuses_unbound_split_header_before_fitting(tmp_path, monkeypatch):
    inputs = _write_inputs(tmp_path)
    runner = _load_runner("spatial_gp_runner_unbound_header")
    calls = _install_fake_fit(runner, monkeypatch)
    build_header = runner.build_checkpoint_header

    def altered_header(**kwargs):
        kwargs["planned_splits"][0]["input_fingerprint"] = "f" * 64
        return build_header(**kwargs)

    monkeypatch.setattr(runner, "build_checkpoint_header", altered_header)
    args = runner._parser().parse_args(_command(inputs, tmp_path / "publication")[2:])
    with pytest.raises(ValueError, match="frozen split"):
        runner.run(args)
    assert calls == []
    assert not (tmp_path / "publication").exists()
