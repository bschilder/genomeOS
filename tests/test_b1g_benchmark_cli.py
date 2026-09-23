"""B1G parallel campaign file adapter tests (design §§4–8, 12; #331)."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from dataclasses import asdict, replace
from pathlib import Path

import pandas as pd
import pytest

from genomeos.surfaces.config import FitConfig
from genomeos.surfaces.convergence import SamplerDiagnostics
from genomeos.validation.b1g_attempt import B1GFitAttempt
from genomeos.validation.b1g_benchmark import (
    PREDICTION_COLUMNS,
    B1GCandidateScore,
    B1GFoldResult,
    B1GFoldStatus,
    B1GInnerFoldRecord,
    derive_b1g_seed,
)
from genomeos.validation.nested_folds import (
    THREE_INNER_FOLD_ALGORITHM,
    plan_three_inner_folds,
)

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "benchmark_b1g.py"
GOOD = SamplerDiagnostics(1.01, "intercept", 300.0, "intercept", 260.0, "intercept", 0)


def _load_runner(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    assert spec is not None and spec.loader is not None
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    return runner


def _write_inputs(root: Path) -> dict[str, Path]:
    observations = pd.DataFrame(
        {
            "variant_id": "chr11-5227002-T-A",
            "rsid": "rs334",
            "population_id": ["pop-a", "pop-b", "pop-c", "pop-d"],
            "lat": [-60.0, -20.0, 20.0, 60.0],
            "lon": [-150.0, -50.0, 50.0, 150.0],
            "radius_km": 1.0,
            "ac": [1, 2, 3, 4],
            "an": 100,
            "source_record_id": ["obs-a", "obs-b", "obs-c", "obs-d"],
            "source": "synthetic",
            "assay": "genotype",
            "date_lower": 0,
            "date_upper": 0,
            "sampling_design": "population_random",
            "disease_ascertainment_excluded": False,
            "cohort_id": ["cohort-a", "cohort-b", "cohort-c", "cohort-d"],
            "ingest_version": "test",
        }
    )
    assignments = pd.DataFrame(
        {
            "source_record_id": observations["source_record_id"],
            "block_id": ["a", "b", "c", "d"],
            "region_id": ["region-a", "region-b", "region-c", "region-d"],
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
        json.dumps(asdict(FitConfig(draws=3, tune=4, chains=2)), indent=2, sort_keys=True) + "\n"
    )
    return paths


def _arguments(paths: dict[str, Path], checkpoint: Path) -> list[str]:
    return [
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
        "1",
        "--checkpoint-dir",
        str(checkpoint),
        "--evidence-kind",
        "synthetic_fixture",
        "--assignment-review-status",
        "reviewed",
        "--dependency-review-status",
        "not_checked",
    ]


def _fake_fold(plan, split):
    ordinal = plan.splits.index(split)
    selection_seed = derive_b1g_seed(plan.seed, split.split_id, "selection")
    outer_initial_seed = derive_b1g_seed(plan.seed, split.split_id, 500.0, 8, "fit")
    outer_retry_seed = derive_b1g_seed(
        plan.seed, split.split_id, 500.0, 8, "fit", "retry"
    )
    record_id = split.test_ids[0]
    observation = plan.observations.set_index("source_record_id").loc[record_id]
    assignment = plan.assignments.set_index("source_record_id").loc[record_id]
    row = {
        "split_id": split.split_id,
        "block_id": split.block_id,
        "source_record_id": record_id,
        "variant_id": observation["variant_id"],
        "region_id": assignment["region_id"],
        "variant_group": assignment["variant_group"],
        "cohort_id": observation["cohort_id"],
        "observed_ac": int(observation["ac"]),
        "observed_an": int(observation["an"]),
        "basis_radius_km": 500.0,
        "basis_count": 8,
        "fit_seed": outer_initial_seed,
        "predictive_seed": ordinal + 20,
        "log_score": -1.0,
        "absolute_error": 0.01,
        "squared_error": 0.0001,
        "coverage_50": True,
        "interval_width_50": 0.02,
        "coverage_80": True,
        "interval_width_80": 0.04,
        "coverage_95": True,
        "interval_width_95": 0.06,
        "randomized_pit": 0.5,
    }
    candidates = []
    grouping = plan_three_inner_folds(
        plan.assignments[
            plan.assignments["source_record_id"].isin(split.train_ids)
        ].loc[:, ["source_record_id", "block_id"]]
    )
    for config in plan.config.candidate_configs:
        inner_folds = tuple(
            B1GInnerFoldRecord(
                f"inner-{inner_index}",
                "completed",
                tuple(
                    f"obs-{block}" for block in grouping.groups[inner_index].source_block_ids
                ),
                derive_b1g_seed(
                    selection_seed,
                    f"inner-{inner_index}",
                    config.radius_km,
                    config.basis_count,
                    "fit",
                ),
                derive_b1g_seed(
                    selection_seed,
                    f"inner-{inner_index}",
                    config.radius_km,
                    config.basis_count,
                    "predictive",
                ),
                GOOD,
                None,
                f"inner-{inner_index}",
                grouping.groups[inner_index].source_block_ids,
                THREE_INNER_FOLD_ALGORITHM,
                grouping.grouping_sha256,
                (
                    B1GFitAttempt(
                        "initial",
                        replace(
                            plan.config.fit_config,
                            seed=derive_b1g_seed(
                                selection_seed,
                                f"inner-{inner_index}",
                                config.radius_km,
                                config.basis_count,
                                "fit",
                            ),
                        ),
                        "accepted",
                        None,
                        GOOD,
                    ),
                    B1GFitAttempt(
                        "retry",
                        replace(
                            plan.config.fit_config,
                            draws=2 * plan.config.fit_config.draws,
                            tune=2 * plan.config.fit_config.tune,
                            seed=derive_b1g_seed(
                                selection_seed,
                                f"inner-{inner_index}",
                                config.radius_km,
                                config.basis_count,
                                "fit",
                                "retry",
                            ),
                        ),
                        "not_attempted",
                        "initial_accepted",
                        None,
                    ),
                ),
            )
            for inner_index in range(3)
        )
        candidates.append(
            B1GCandidateScore(
                config.radius_km,
                config.basis_count,
                3,
                3,
                -1.0,
                3,
                0,
                (),
                True,
                inner_folds,
            )
        )
    return B1GFoldResult(
        B1GFoldStatus(split.split_id, "completed", split.test_ids, 500.0, 8, None),
        pd.DataFrame.from_records([row], columns=PREDICTION_COLUMNS),
        tuple(candidates),
        GOOD,
        (
            B1GFitAttempt(
                "initial",
                replace(plan.config.fit_config, seed=outer_initial_seed),
                "accepted",
                None,
                GOOD,
            ),
            B1GFitAttempt(
                "retry",
                replace(
                    plan.config.fit_config,
                    draws=2 * plan.config.fit_config.draws,
                    tune=2 * plan.config.fit_config.tune,
                    seed=outer_retry_seed,
                ),
                "not_attempted",
                "initial_accepted",
                None,
            ),
        ),
    )


def test_runner_initializes_parallel_folds_and_atomic_final_publication(tmp_path, monkeypatch):
    paths = _write_inputs(tmp_path)
    checkpoint = tmp_path / "checkpoint"
    output = tmp_path / "output"
    runner = _load_runner("b1g_runner_complete")
    monkeypatch.setattr(runner, "evaluate_b1g_fold", _fake_fold)
    monkeypatch.setattr(runner, "_device_name", lambda: "synthetic-device")
    monkeypatch.setattr(runner, "_peak_rss_bytes", lambda: 123_456)
    base = _arguments(paths, checkpoint)

    assert runner.run(runner._parser().parse_args([*base, "--initialize"])) == 0
    for ordinal in (3, 1, 0, 2):
        assert runner.run(
            runner._parser().parse_args([*base, "--fold-index", str(ordinal)])
        ) == 0
    assert runner.run(
        runner._parser().parse_args([*base, "--finalize", "--out", str(output)])
    ) == 0

    assert sorted(path.name for path in output.iterdir()) == [
        "candidate_scores.tsv",
        "fold_status.tsv",
        "inner_folds.tsv",
        "inventory.json",
        "manifest.json",
        "predictions.tsv",
        "summary.json",
    ]
    assert len(pd.read_csv(output / "predictions.tsv", sep="\t")) == 4
    candidates = pd.read_csv(output / "candidate_scores.tsv", sep="\t")
    inner = pd.read_csv(output / "inner_folds.tsv", sep="\t")
    assert len(candidates) == 36
    assert len(inner) == 108
    assert json.loads(candidates.iloc[0]["failure_reasons"]) == []
    assert len(json.loads(inner.iloc[0]["expected_test_ids"])) == 1
    assert len(json.loads(inner.iloc[0]["source_block_ids"])) == 1
    assert [
        attempt["status"] for attempt in json.loads(inner.iloc[0]["fit_attempts"])
    ] == ["accepted", "not_attempted"]
    folds = pd.read_csv(output / "fold_status.tsv", sep="\t")
    assert [
        attempt["status"] for attempt in json.loads(folds.iloc[0]["fit_attempts"])
    ] == ["accepted", "not_attempted"]
    assert set(inner["grouping_algorithm"]) == {THREE_INNER_FOLD_ALGORITHM}
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["model"]["model_id"] == "B1G"
    assert manifest["publication_eligible"] is False
    assert manifest["configuration"]["candidate_grid"] == {
        "basis_counts": [8, 16, 32],
        "radii_km": [500.0, 1000.0, 2000.0],
    }
    assert manifest["configuration"]["inner_fold_protocol"] == {
        "algorithm": THREE_INNER_FOLD_ALGORITHM,
        "fold_count": 3,
    }
    assert manifest["configuration"]["fit_retry_protocol"] == {
        "admission_error": "B1GConvergenceError",
        "draws_multiplier": 2,
        "maximum_retries": 1,
        "tune_multiplier": 2,
    }
    assert "genomeos/validation/b1g_attempt.py" in manifest["science_source_sha256"]
    assert "genomeos/validation/nested_folds.py" in manifest["science_source_sha256"]
    assert len(manifest["folds"]) == 4
    assert {fold["runtime"]["device"] for fold in manifest["folds"]} == {
        "synthetic-device"
    }
    for name, record in manifest["output_files"].items():
        content = (output / name).read_bytes()
        assert record == {
            "sha256": hashlib.sha256(content).hexdigest(),
            "size_bytes": len(content),
        }


def test_worker_refuses_input_drift_from_initialized_campaign(tmp_path, monkeypatch):
    paths = _write_inputs(tmp_path)
    checkpoint = tmp_path / "checkpoint"
    runner = _load_runner("b1g_runner_drift")
    calls = []
    monkeypatch.setattr(runner, "evaluate_b1g_fold", lambda *args: calls.append(args))
    base = _arguments(paths, checkpoint)
    assert runner.run(runner._parser().parse_args([*base, "--initialize"])) == 0
    observations = pd.read_csv(paths["observations"], sep="\t")
    observations.loc[0, "ac"] = 9
    observations.to_csv(paths["observations"], sep="\t", index=False, lineterminator="\n")

    with pytest.raises(ValueError, match="header mismatch"):
        runner.run(runner._parser().parse_args([*base, "--fold-index", "0"]))

    assert calls == []
