"""Offline spatial-activity campaign adapter tests (#384)."""

from __future__ import annotations

import importlib.util
import json
from dataclasses import asdict
from pathlib import Path

import pandas as pd
import pytest

from genomeos.surfaces.config import FitConfig
from genomeos.surfaces.spatial_activity_fit import SpatialActivitySamplerConfig
from genomeos.surfaces.spatial_activity_model import SpatialActivityModelConfig
from genomeos.validation.benchmark import BenchmarkFoldStatus
from genomeos.validation.spatial_activity_campaign import (
    SpatialActivityCampaignDecision,
    SpatialActivityCampaignResult,
    SpatialActivityConditionComparison,
)
from genomeos.validation.spatial_activity_runner import SpatialActivityFoldResult
from genomeos.validation.spatial_activity_tasks import SpatialActivityTaskResult

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "preflight_spatial_activity.py"


def _module():
    spec = importlib.util.spec_from_file_location("preflight_spatial_activity", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _inputs(tmp_path: Path) -> dict[str, Path]:
    rows = []
    for block in range(5):
        for replicate in range(2):
            index = block * 2 + replicate
            rows.append(
                {
                    "variant_id": "chr11-5227002-T-A",
                    "rsid": "rs334",
                    "population_id": f"population-{index}",
                    "lat": float(-50 + block * 25 + replicate),
                    "lon": float(-150 + block * 65 + replicate),
                    "radius_km": 1.0,
                    "ac": index % 3,
                    "an": 100 + index,
                    "source_record_id": f"record-{index:02d}",
                    "source": "synthetic_fixture",
                    "assay": "genotype",
                    "date_lower": 0,
                    "date_upper": 0,
                    "sampling_design": "population_random",
                    "disease_ascertainment_excluded": True,
                    "cohort_id": f"cohort-{block:02d}",
                    "ingest_version": "test",
                }
            )
    observations = pd.DataFrame.from_records(rows)
    assignments = pd.DataFrame(
        {
            "source_record_id": observations["source_record_id"],
            "block_id": observations["cohort_id"].str.replace("cohort", "block"),
            "region_id": observations["cohort_id"].str.replace("cohort", "region"),
            "variant_group": "hbs",
        }
    )
    dependencies = pd.DataFrame(
        columns=("source_record_id_a", "source_record_id_b")
    )
    paths = {
        "observations": tmp_path / "observations.tsv",
        "assignments": tmp_path / "assignments.tsv",
        "dependencies": tmp_path / "dependencies.tsv",
        "baseline_fit_config": tmp_path / "baseline-fit-config.json",
        "model_config": tmp_path / "model-config.json",
        "sampler_config": tmp_path / "sampler-config.json",
    }
    observations.to_csv(paths["observations"], sep="\t", index=False)
    assignments.to_csv(paths["assignments"], sep="\t", index=False)
    dependencies.to_csv(paths["dependencies"], sep="\t", index=False)
    baseline = FitConfig(draws=3, tune=4, chains=4, nuts_sampler="pymc")
    model = SpatialActivityModelConfig(
        hsgp_m=(2, 2, 2),
        hsgp_c=1.5,
        lengthscale_mu=-2.0,
        lengthscale_sigma=0.4,
        conditional_intercept_mu=-3.5,
        conditional_intercept_sigma=1.5,
        conditional_amplitude_sigma=1.0,
        activity_intercept_mu=2.5,
        activity_intercept_sigma=1.0,
        activity_amplitude_sigma=1.0,
        concentration_sigma=100.0,
        cohort_sd_sigma=0.5,
    )
    sampler = SpatialActivitySamplerConfig(
        draws=3,
        tune=4,
        chains=4,
        nuts_sampler="pymc",
    )
    for name, value in (
        ("baseline_fit_config", baseline),
        ("model_config", model),
        ("sampler_config", sampler),
    ):
        paths[name].write_text(json.dumps(asdict(value), sort_keys=True) + "\n")
    return paths


def _common(paths: dict[str, Path]) -> list[str]:
    return [
        "--observations",
        str(paths["observations"]),
        "--assignments",
        str(paths["assignments"]),
        "--dependencies",
        str(paths["dependencies"]),
        "--baseline-fit-config",
        str(paths["baseline_fit_config"]),
        "--model-config",
        str(paths["model_config"]),
        "--sampler-config",
        str(paths["sampler_config"]),
        "--data-version",
        "activity-cli-test-v1",
        "--buffer-km",
        "300",
    ]


def test_manifest_is_canonical_complete_and_refuses_overwrite(tmp_path) -> None:
    module = _module()
    paths = _inputs(tmp_path)
    first = tmp_path / "manifest.json"
    second = tmp_path / "manifest-copy.json"

    assert module.run(module._parser().parse_args(["manifest", *_common(paths), "--out", str(first)])) == 0
    assert module.run(module._parser().parse_args(["manifest", *_common(paths), "--out", str(second)])) == 0

    assert first.read_bytes() == second.read_bytes()
    document = json.loads(first.read_bytes())
    assert document["format"] == "spatial_activity_campaign_manifest"
    assert document["version"] == 1
    assert document["evidence_kind"] == "synthetic_preflight"
    assert document["publication_eligible"] is False
    assert document["real_hbs_fit_permitted"] is False
    assert document["task_count"] == 720
    assert len(document["tasks"]) == 720
    assert sum(task["split_role"] == "outer" for task in document["tasks"]) == 180
    assert sum(task["split_role"] == "inner" for task in document["tasks"]) == 540
    assert set(document["input_files"]) == set(paths)
    assert all(len(item["sha256"]) == 64 for item in document["input_files"].values())
    assert "genomeos/validation/spatial_activity_campaign.py" in document["science_files"]
    with pytest.raises(FileExistsError, match="overwrite"):
        module.run(module._parser().parse_args(["manifest", *_common(paths), "--out", str(first)]))


def test_run_rebuilds_manifest_and_writes_one_terminal_task(monkeypatch, tmp_path) -> None:
    module = _module()
    paths = _inputs(tmp_path)
    manifest = tmp_path / "manifest.json"
    module.run(module._parser().parse_args(["manifest", *_common(paths), "--out", str(manifest)]))
    task_id = json.loads(manifest.read_bytes())["tasks"][0]["task_id"]
    calls = []

    def evaluate(plan, task):
        calls.append((plan, task))
        return SpatialActivityTaskResult(
            task=task,
            result=SpatialActivityFoldResult(
                scenario_id=task.scenario_id,
                mode=task.mode,
                split_role=task.split_role,
                status=BenchmarkFoldStatus(
                    split_id=task.split_id,
                    status="failed",
                    expected_test_ids=("heldout",),
                    failure_reason="deliberate adapter test refusal",
                ),
                fit_seed=1,
                predictive_seed=2,
                model_config=plan.model_config,
                attempts=(),
                assessment=None,
                fitted=None,
            ),
        )

    monkeypatch.setattr(module, "evaluate_spatial_activity_task", evaluate)
    results = tmp_path / "results"
    status = module.run(
        module._parser().parse_args(
            [
                "run",
                *_common(paths),
                "--manifest",
                str(manifest),
                "--task-id",
                task_id,
                "--results-dir",
                str(results),
            ]
        )
    )

    assert status == 2
    assert len(calls) == 1
    assert calls[0][1].task_id == task_id
    assert (results / f"{task_id}.json").is_file()


def test_run_refuses_changed_input_or_unknown_task_before_fit(monkeypatch, tmp_path) -> None:
    module = _module()
    paths = _inputs(tmp_path)
    manifest = tmp_path / "manifest.json"
    module.run(module._parser().parse_args(["manifest", *_common(paths), "--out", str(manifest)]))
    paths["dependencies"].write_text(
        "source_record_id_a\tsource_record_id_b\nrecord-00\trecord-01\n"
    )
    monkeypatch.setattr(
        module,
        "evaluate_spatial_activity_task",
        lambda *_: pytest.fail("fit must not start"),
    )
    with pytest.raises(ValueError, match="manifest"):
        module.run(
            module._parser().parse_args(
                [
                    "run",
                    *_common(paths),
                    "--manifest",
                    str(manifest),
                    "--task-id",
                    "0" * 64,
                    "--results-dir",
                    str(tmp_path / "results"),
                ]
            )
        )


def test_run_shard_reuses_process_and_resumes_valid_artifacts(monkeypatch, tmp_path) -> None:
    module = _module()
    paths = _inputs(tmp_path)
    manifest = tmp_path / "manifest.json"
    module.run(module._parser().parse_args(["manifest", *_common(paths), "--out", str(manifest)]))
    task_ids = [item["task_id"] for item in json.loads(manifest.read_bytes())["tasks"][:2]]
    task_file = tmp_path / "tasks.txt"
    task_file.write_text("\n".join(task_ids) + "\n")
    calls = []

    def evaluate(plan, task):
        calls.append(task.task_id)
        return SpatialActivityTaskResult(
            task=task,
            result=SpatialActivityFoldResult(
                scenario_id=task.scenario_id,
                mode=task.mode,
                split_role=task.split_role,
                status=BenchmarkFoldStatus(
                    split_id=task.split_id,
                    status="failed",
                    expected_test_ids=("heldout",),
                    failure_reason="deliberate shard test refusal",
                ),
                fit_seed=1,
                predictive_seed=2,
                model_config=plan.model_config,
                attempts=(),
                assessment=None,
                fitted=None,
            ),
        )

    monkeypatch.setattr(module, "evaluate_spatial_activity_task", evaluate)
    results = tmp_path / "results"
    arguments = module._parser().parse_args(
        [
            "run-shard",
            *_common(paths),
            "--manifest",
            str(manifest),
            "--tasks",
            str(task_file),
            "--results-dir",
            str(results),
        ]
    )

    assert module.run(arguments) == 2
    assert calls == task_ids
    assert {path.stem for path in results.glob("*.json")} == set(task_ids)
    assert module.run(arguments) == 2
    assert calls == task_ids


def test_run_shard_refuses_duplicate_or_empty_task_ledgers(tmp_path) -> None:
    module = _module()
    paths = _inputs(tmp_path)
    manifest = tmp_path / "manifest.json"
    module.run(module._parser().parse_args(["manifest", *_common(paths), "--out", str(manifest)]))
    task_id = json.loads(manifest.read_bytes())["tasks"][0]["task_id"]
    task_file = tmp_path / "tasks.txt"
    base = [
        "run-shard",
        *_common(paths),
        "--manifest",
        str(manifest),
        "--tasks",
        str(task_file),
        "--results-dir",
        str(tmp_path / "results"),
    ]
    task_file.write_text("")
    with pytest.raises(ValueError, match="empty"):
        module.run(module._parser().parse_args(base))
    task_file.write_text(f"{task_id}\n{task_id}\n")
    with pytest.raises(ValueError, match="duplicate"):
        module.run(module._parser().parse_args(base))


def test_finalize_hashes_artifacts_and_preserves_negative_decision(monkeypatch, tmp_path) -> None:
    module = _module()
    paths = _inputs(tmp_path)
    manifest = tmp_path / "manifest.json"
    module.run(module._parser().parse_args(["manifest", *_common(paths), "--out", str(manifest)]))
    results = tmp_path / "results"
    results.mkdir()
    (results / ("a" * 64 + ".json")).write_bytes(b"terminal-evidence\n")
    sentinel = (object(),)
    comparison = SpatialActivityConditionComparison(
        condition_id="localized_weak|denominator=1|cohort_sd=0",
        truth="localized_weak",
        denominator_multiplier=1.0,
        cohort_sd=0.0,
        paired_outer_fold_count=15,
        paired_zero_stratum_count=15,
        paired_positive_stratum_count=15,
        complete=True,
        mean_log_score_delta=-0.1,
        log_score_delta_ci95_low=-0.2,
        log_score_delta_ci95_high=0.0,
        relative_mae_improvement=-0.1,
        relative_marginal_recovery_improvement=-0.1,
        mean_zero_log_score_delta=-0.1,
        mean_positive_log_score_delta=-0.1,
        candidate_coverage_50=0.5,
        candidate_coverage_80=0.8,
        candidate_coverage_95=0.95,
        candidate_mean_absolute_component_correlation=0.9,
        candidate_component_correlation_fold_count=15,
        candidate_component_correlation_observation_count=150,
        candidate_mean_inactive_probability=None,
        candidate_fraction_draws_below_activity_threshold=None,
    )
    campaign = SpatialActivityCampaignResult(
        task_count=720,
        completed_task_count=720,
        retried_task_count=4,
        comparisons=(comparison,),
        decision=SpatialActivityCampaignDecision(
            eligible_for_real_fit=False,
            refusal_reasons=("localized synthetic prediction did not improve",),
        ),
        results=(),
    )
    monkeypatch.setattr(module, "load_spatial_activity_task_results", lambda path: sentinel)
    calls = []

    def finalize(plan, loaded):
        calls.append((plan, loaded))
        return campaign

    monkeypatch.setattr(module, "finalize_spatial_activity_campaign", finalize)
    output = tmp_path / "campaign.json"
    status = module.run(
        module._parser().parse_args(
            [
                "finalize",
                *_common(paths),
                "--manifest",
                str(manifest),
                "--results-dir",
                str(results),
                "--out",
                str(output),
            ]
        )
    )

    assert status == 2
    assert len(calls) == 1 and calls[0][1] is sentinel
    document = json.loads(output.read_bytes())
    assert document["format"] == "spatial_activity_campaign_result"
    assert document["evidence_kind"] == "synthetic_preflight"
    assert document["publication_eligible"] is False
    assert document["decision"]["eligible_for_real_fit"] is False
    assert document["decision"]["refusal_reasons"] == [
        "localized synthetic prediction did not improve"
    ]
    assert document["campaign_manifest_sha256"] == __import__("hashlib").sha256(
        manifest.read_bytes()
    ).hexdigest()
    assert document["task_artifacts"]["a" * 64 + ".json"]["sha256"] == (
        __import__("hashlib").sha256(b"terminal-evidence\n").hexdigest()
    )
    with pytest.raises(FileExistsError, match="overwrite"):
        module.run(
            module._parser().parse_args(
                [
                    "finalize",
                    *_common(paths),
                    "--manifest",
                    str(manifest),
                    "--results-dir",
                    str(results),
                    "--out",
                    str(output),
                ]
            )
        )


def test_parser_requires_explicit_campaign_inputs() -> None:
    module = _module()
    with pytest.raises(SystemExit):
        module._parser().parse_args(["manifest", "--out", "manifest.json"])
