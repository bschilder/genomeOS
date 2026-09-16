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

from genomeos.observations.schema import OBSERVATIONS_SCHEMA
from genomeos.surfaces.config import FitConfig
from genomeos.surfaces.observation import (
    ObservationModelMetadata,
    ObservationParameters,
    SurveyQueries,
)

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "benchmark_spatial_gp.py"
VARIANT = "chr11-5227002-T-A"


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
        json.dumps(asdict(FitConfig(likelihood="beta_binomial")), indent=2, sort_keys=True)
        + "\n"
    )
    return paths


def _command(paths: dict[str, Path], out: Path) -> list[str]:
    return [
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
        "--out",
        str(out),
    ]


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

    def predict_new_cohort_parameters(
        self, queries: SurveyQueries, *, seed: int
    ) -> ObservationParameters:
        assert not set(queries.cohort_ids) & set(self.training_cohorts)
        draws = 8
        mean = np.broadcast_to(
            np.linspace(0.01, 0.08, len(queries.observation_ids)),
            (draws, len(queries.observation_ids)),
        )
        concentration = (
            np.full(mean.shape, 30.0) if self.likelihood == "beta_binomial" else None
        )
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


def _install_fake_fit(runner, monkeypatch) -> None:
    real_evaluate = runner.evaluate_single_variant_gp

    def evaluate(*args, **kwargs):
        def fit(observations: pd.DataFrame, config: FitConfig) -> _FakeFit:
            return _FakeFit(tuple(sorted(observations["cohort_id"].unique())), config.likelihood)

        return real_evaluate(*args, **kwargs, fit_function=fit)

    monkeypatch.setattr(runner, "evaluate_single_variant_gp", evaluate)


def test_runner_writes_reproducible_current_gp_evidence(tmp_path, monkeypatch):
    paths = _write_inputs(tmp_path)
    runner = _load_runner("spatial_gp_runner_success")
    _install_fake_fit(runner, monkeypatch)
    args = runner._parser().parse_args(_command(paths, tmp_path / "first")[2:])

    assert runner.run(args) == 0
    args.out = tmp_path / "second"
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
    assert len(manifest["configuration_sha256"]) == 64
    assert len(manifest["inputs_sha256"]) == 64
    assert len(manifest["split_manifest_sha256"]) == 64
    assert set(manifest["science_source_sha256"]) >= {
        "genomeos/surfaces/fit.py",
        "genomeos/validation/spatial_gp_benchmark.py",
        "scripts/benchmark_spatial_gp.py",
    }
    predictions = pd.read_csv(first / "predictions.tsv", sep="\t")
    assert len(predictions) == 4
    assert set(predictions["variant_id"]) == {VARIANT}
    assert json.loads((first / "summary.json").read_text())["benchmark"][
        "comparison_complete"
    ] is True
    for name, record in manifest["output_files"].items():
        content = (first / name).read_bytes()
        assert record == {
            "sha256": hashlib.sha256(content).hexdigest(),
            "size_bytes": len(content),
        }


def test_real_cli_preserves_global_scoring_refusal_without_fitting(tmp_path):
    paths = _write_inputs(tmp_path, large_denominator=True)
    output = tmp_path / "refused"

    completed = _run(_command(paths, output))

    assert completed.returncode == 1, completed.stderr
    statuses = pd.read_csv(output / "fold_status.tsv", sep="\t", keep_default_na=False)
    assert set(statuses["status"]) == {"failed"}
    assert all("65,536" in reason for reason in statuses["failure_reason"])
    assert pd.read_csv(output / "predictions.tsv", sep="\t").empty
    summary = json.loads((output / "summary.json").read_text())
    assert summary["benchmark"]["comparison_complete"] is False
    assert summary["benchmark"]["split_counts"]["failed"] == 4


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


def test_runner_bootstraps_the_checked_out_science_sources(tmp_path):
    paths = _write_inputs(tmp_path, large_denominator=True)
    conflicting = tmp_path / "conflicting"
    package = conflicting / "genomeos"
    package.mkdir(parents=True)
    package.joinpath("__init__.py").write_text(
        'raise RuntimeError("synthetic wrong-checkout genomeos imported")\n'
    )

    completed = _run(_command(paths, tmp_path / "run"), pythonpath=conflicting)

    assert completed.returncode == 1, completed.stderr
    assert "synthetic wrong-checkout" not in completed.stderr
    manifest = json.loads((tmp_path / "run" / "manifest.json").read_text())
    expected = hashlib.sha256(
        (ROOT / "genomeos/validation/spatial_gp_benchmark.py").read_bytes()
    ).hexdigest()
    assert (
        manifest["science_source_sha256"][
            "genomeos/validation/spatial_gp_benchmark.py"
        ]
        == expected
    )
