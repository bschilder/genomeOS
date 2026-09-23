"""Immutable parallel B1G outer-fold checkpoints (design §§4–8, 12; #331)."""

from __future__ import annotations

import json
from dataclasses import asdict, replace

import pandas as pd
import pytest

from genomeos.surfaces.config import FitConfig
from genomeos.surfaces.convergence import SamplerDiagnostics
from genomeos.validation.b1g_benchmark import (
    PREDICTION_COLUMNS,
    B1GBenchmarkConfig,
    B1GBenchmarkPlan,
    B1GCandidateScore,
    B1GFoldResult,
    B1GFoldStatus,
    B1GInnerFoldRecord,
)
from genomeos.validation.b1g_checkpoint import (
    B1GFoldRuntime,
    finalize_b1g_checkpoint,
    load_b1g_fold_shards,
    write_b1g_fold_shard,
)
from genomeos.validation.spatial_gp_checkpoint import (
    build_checkpoint_header,
    initialize_checkpoint,
)
from genomeos.validation.splits import build_buffered_splits

GOOD = SamplerDiagnostics(1.01, "intercept", 300.0, "intercept", 260.0, "intercept", 0)
BAD = SamplerDiagnostics(1.08, "amplitude", 100.0, "amplitude", 90.0, "amplitude", 1)


def _plan() -> B1GBenchmarkPlan:
    observations = pd.DataFrame(
        {
            "variant_id": "chr11-5227002-T-A",
            "rsid": "rs334",
            "population_id": ["pop-a", "pop-b"],
            "lat": [-40.0, 40.0],
            "lon": [-100.0, 100.0],
            "radius_km": 1.0,
            "ac": [1, 2],
            "an": [100, 100],
            "source_record_id": ["obs-a", "obs-b"],
            "source": "synthetic",
            "assay": "genotype",
            "date_lower": 0,
            "date_upper": 0,
            "sampling_design": "population_random",
            "disease_ascertainment_excluded": False,
            "cohort_id": ["cohort-a", "cohort-b"],
            "ingest_version": "test",
        }
    )
    assignments = pd.DataFrame(
        {
            "source_record_id": ["obs-a", "obs-b"],
            "block_id": ["a", "b"],
            "region_id": ["region-a", "region-b"],
            "variant_group": "hbs",
        }
    )
    splits = build_buffered_splits(
        observations,
        assignments.loc[:, ["source_record_id", "block_id"]],
        (),
        buffer_km=1.0,
        data_version="fixture-v1",
    )
    return B1GBenchmarkPlan(
        observations=observations,
        assignments=assignments,
        dependencies=(),
        splits=splits,
        buffer_km=1.0,
        data_version="fixture-v1",
        config=B1GBenchmarkConfig(FitConfig(draws=3, tune=4, chains=2)),
        seed=42,
    )


def _header(plan: B1GBenchmarkPlan) -> dict[str, object]:
    fit_config = asdict(plan.config.fit_config)
    configuration = {
        "buffer_km": plan.buffer_km,
        "cdf_backend": plan.config.cdf_backend,
        "data_version": plan.data_version,
        "fit_config": fit_config,
        "query_chunk_size": plan.config.query_chunk_size,
        "sampler_convergence_gate": {
            "maximum_divergences": 0,
            "maximum_rhat": plan.config.fit_config.max_rhat,
            "minimum_bulk_ess": plan.config.fit_config.min_ess,
            "minimum_tail_ess": plan.config.fit_config.min_ess,
        },
        "seed": plan.seed,
    }
    return build_checkpoint_header(
        model_id="B1G",
        evidence_kind="synthetic_fixture",
        qualification={"scientific_promotion_decision": "not_made"},
        configuration=configuration,
        input_files={"observations": {"sha256": "a" * 64, "size_bytes": 1}},
        planned_splits=[asdict(split) for split in plan.splits],
        seed_schedule=[{"split_id": split.split_id} for split in plan.splits],
        code_revision="b" * 40,
        science_source_sha256={"b1g.py": "c" * 64},
        package_versions={"python": "3.12.0"},
    )


def _candidate(
    inner_id: str,
    *,
    radius_km: float,
    basis_count: int,
    diagnostics: SamplerDiagnostics = GOOD,
) -> B1GCandidateScore:
    inner = B1GInnerFoldRecord(
        split_id=inner_id,
        status="completed",
        expected_test_ids=(f"{inner_id}-test",),
        fit_seed=1,
        predictive_seed=2,
        sampler_diagnostics=diagnostics,
        failure_reason=None,
    )
    return B1GCandidateScore(
        radius_km,
        basis_count,
        1,
        1,
        -1.0,
        1,
        0,
        (),
        True,
        (inner,),
    )


def _fold(plan: B1GBenchmarkPlan, ordinal: int) -> B1GFoldResult:
    split = plan.splits[ordinal]
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
        "fit_seed": 3,
        "predictive_seed": 4,
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
    return B1GFoldResult(
        status=B1GFoldStatus(split.split_id, "completed", split.test_ids, 500.0, 8, None),
        predictions=pd.DataFrame.from_records([row], columns=PREDICTION_COLUMNS),
        candidate_scores=tuple(
            _candidate(
                f"inner-{index}",
                radius_km=config.radius_km,
                basis_count=config.basis_count,
            )
            for index, config in enumerate(plan.config.candidate_configs)
        ),
        sampler_diagnostics=GOOD,
    )


def _runtime() -> B1GFoldRuntime:
    return B1GFoldRuntime(
        elapsed_seconds=12.5,
        peak_rss_bytes=123_456,
        device="synthetic-device",
        query_chunk_size=1024,
    )


def _infeasible_fold(plan: B1GBenchmarkPlan, ordinal: int) -> B1GFoldResult:
    split = plan.splits[ordinal]
    reason = "outer split has no training observations after leakage exclusions"
    return B1GFoldResult(
        status=B1GFoldStatus(
            split.split_id,
            "infeasible",
            split.test_ids,
            None,
            None,
            reason,
        ),
        predictions=pd.DataFrame(columns=PREDICTION_COLUMNS),
        candidate_scores=(),
        sampler_diagnostics=None,
    )


def test_parallel_shards_round_trip_and_finalize_in_any_write_order(tmp_path):
    plan = _plan()
    header = _header(plan)
    checkpoint = tmp_path / "checkpoint"
    initialize_checkpoint(checkpoint, header)

    write_b1g_fold_shard(checkpoint, header, plan, 1, _fold(plan, 1), _runtime())
    write_b1g_fold_shard(checkpoint, header, plan, 0, _fold(plan, 0), _runtime())

    shards = load_b1g_fold_shards(checkpoint, header, plan)
    assert tuple(shard.ordinal for shard in shards) == (0, 1)
    assert all(shard.runtime == _runtime() for shard in shards)
    result = finalize_b1g_checkpoint(checkpoint, header, plan)
    assert result.summary["comparison_complete"] is True
    assert len(result.predictions) == 2


def test_infeasible_fold_before_inner_planning_is_preserved(tmp_path):
    plan = _plan()
    header = _header(plan)
    checkpoint = tmp_path / "checkpoint"
    initialize_checkpoint(checkpoint, header)

    write_b1g_fold_shard(
        checkpoint,
        header,
        plan,
        0,
        _infeasible_fold(plan, 0),
        _runtime(),
    )

    (shard,) = load_b1g_fold_shards(checkpoint, header, plan)
    assert shard.result.status.status == "infeasible"
    assert shard.result.candidate_scores == ()
    assert shard.result.predictions.empty


def test_checkpoint_root_refuses_unknown_visible_artifacts(tmp_path):
    plan = _plan()
    header = _header(plan)
    checkpoint = tmp_path / "checkpoint"
    initialize_checkpoint(checkpoint, header)
    (checkpoint / "unexpected.txt").write_text("not part of the campaign\n")

    with pytest.raises(ValueError, match="unknown or missing artifacts"):
        load_b1g_fold_shards(checkpoint, header, plan)


def test_shard_is_immutable_and_integrity_checked(tmp_path):
    plan = _plan()
    header = _header(plan)
    checkpoint = tmp_path / "checkpoint"
    initialize_checkpoint(checkpoint, header)
    fold = _fold(plan, 0)
    write_b1g_fold_shard(checkpoint, header, plan, 0, fold, _runtime())

    with pytest.raises(FileExistsError, match="immutable"):
        write_b1g_fold_shard(checkpoint, header, plan, 0, fold, _runtime())

    artifact = checkpoint / "folds" / "0000.json"
    document = json.loads(artifact.read_text())
    document["runtime"]["elapsed_seconds"] = 99.0
    artifact.write_text(json.dumps(document))
    with pytest.raises(ValueError, match="integrity"):
        load_b1g_fold_shards(checkpoint, header, plan)


def test_eligible_candidate_cannot_hide_bad_inner_diagnostics(tmp_path):
    plan = _plan()
    header = _header(plan)
    checkpoint = tmp_path / "checkpoint"
    initialize_checkpoint(checkpoint, header)
    fold = _fold(plan, 0)
    candidates = list(fold.candidate_scores)
    bad_inner = replace(candidates[0].inner_folds[0], sampler_diagnostics=BAD)
    candidates[0] = replace(candidates[0], inner_folds=(bad_inner,))
    contradictory = replace(fold, candidate_scores=tuple(candidates))

    with pytest.raises(ValueError, match="eligible candidate.*convergence"):
        write_b1g_fold_shard(
            checkpoint,
            header,
            plan,
            0,
            contradictory,
            _runtime(),
        )


def test_finalization_refuses_missing_parallel_shards(tmp_path):
    plan = _plan()
    header = _header(plan)
    checkpoint = tmp_path / "checkpoint"
    initialize_checkpoint(checkpoint, header)
    write_b1g_fold_shard(checkpoint, header, plan, 1, _fold(plan, 1), _runtime())

    with pytest.raises(ValueError, match="exactly one result"):
        finalize_b1g_checkpoint(checkpoint, header, plan)
