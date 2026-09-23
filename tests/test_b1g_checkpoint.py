"""Immutable parallel B1G outer-fold checkpoints (design §§4–8, 12; #331)."""

from __future__ import annotations

import json
from dataclasses import asdict, replace

import pandas as pd
import pytest

from genomeos.surfaces.config import FitConfig
from genomeos.surfaces.convergence import SamplerDiagnostics
from genomeos.validation.b1g_attempt import B1GFitAttempt
from genomeos.validation.b1g_benchmark import (
    PREDICTION_COLUMNS,
    B1GBenchmarkConfig,
    B1GBenchmarkPlan,
    B1GCandidateScore,
    B1GFoldResult,
    B1GFoldStatus,
    B1GInnerFoldRecord,
    derive_b1g_seed,
)
from genomeos.validation.b1g_checkpoint import (
    B1GFoldRuntime,
    finalize_b1g_checkpoint,
    load_b1g_fold_shards,
    write_b1g_fold_shard,
)
from genomeos.validation.nested_folds import (
    THREE_INNER_FOLD_ALGORITHM,
    InnerFoldGroup,
    plan_three_inner_folds,
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
            "population_id": ["pop-a", "pop-b", "pop-c", "pop-d"],
            "lat": [-40.0, -10.0, 10.0, 40.0],
            "lon": [-150.0, -50.0, 50.0, 150.0],
            "radius_km": 1.0,
            "ac": [1, 2, 3, 4],
            "an": [100, 100, 100, 100],
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
            "source_record_id": ["obs-a", "obs-b", "obs-c", "obs-d"],
            "block_id": ["a", "b", "c", "d"],
            "region_id": ["region-a", "region-b", "region-c", "region-d"],
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
    grouping_sha256: str,
    *,
    radius_km: float,
    basis_count: int,
    groups: tuple[InnerFoldGroup, ...],
    fit_config: FitConfig,
    selection_seed: int,
    diagnostics: SamplerDiagnostics = GOOD,
) -> B1GCandidateScore:
    inner_folds = tuple(
        B1GInnerFoldRecord(
            split_id=f"inner-{index}",
            status="completed",
            expected_test_ids=tuple(f"obs-{block}" for block in groups[index].source_block_ids),
            fit_seed=derive_b1g_seed(
                selection_seed,
                f"inner-{index}",
                radius_km,
                basis_count,
                "fit",
            ),
            predictive_seed=derive_b1g_seed(
                selection_seed,
                f"inner-{index}",
                radius_km,
                basis_count,
                "predictive",
            ),
            sampler_diagnostics=diagnostics,
            failure_reason=None,
            inner_block_id=f"inner-{index}",
            source_block_ids=groups[index].source_block_ids,
            grouping_algorithm=THREE_INNER_FOLD_ALGORITHM,
            grouping_sha256=grouping_sha256,
            fit_attempts=(
                B1GFitAttempt(
                    "initial",
                    replace(
                        fit_config,
                        seed=derive_b1g_seed(
                            selection_seed,
                            f"inner-{index}",
                            radius_km,
                            basis_count,
                            "fit",
                        ),
                    ),
                    "accepted",
                    None,
                    diagnostics,
                ),
                B1GFitAttempt(
                    "retry",
                    replace(
                        fit_config,
                        draws=2 * fit_config.draws,
                        tune=2 * fit_config.tune,
                        seed=derive_b1g_seed(
                            selection_seed,
                            f"inner-{index}",
                            radius_km,
                            basis_count,
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
        for index in range(3)
    )
    return B1GCandidateScore(
        radius_km,
        basis_count,
        3,
        3,
        -1.0,
        3,
        0,
        (),
        True,
        inner_folds,
    )


def _fold(plan: B1GBenchmarkPlan, ordinal: int) -> B1GFoldResult:
    split = plan.splits[ordinal]
    selection_seed = derive_b1g_seed(plan.seed, split.split_id, "selection")
    outer_initial_seed = derive_b1g_seed(plan.seed, split.split_id, 500.0, 8, "fit")
    outer_retry_seed = derive_b1g_seed(
        plan.seed, split.split_id, 500.0, 8, "fit", "retry"
    )
    grouping = plan_three_inner_folds(
        plan.assignments[
            plan.assignments["source_record_id"].isin(split.train_ids)
        ].loc[:, ["source_record_id", "block_id"]]
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
                grouping.grouping_sha256,
                radius_km=config.radius_km,
                basis_count=config.basis_count,
                groups=grouping.groups,
                fit_config=plan.config.fit_config,
                selection_seed=selection_seed,
            )
            for index, config in enumerate(plan.config.candidate_configs)
        ),
        sampler_diagnostics=GOOD,
        fit_attempts=(
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

    for ordinal in (3, 1, 0, 2):
        write_b1g_fold_shard(checkpoint, header, plan, ordinal, _fold(plan, ordinal), _runtime())

    shards = load_b1g_fold_shards(checkpoint, header, plan)
    assert tuple(shard.ordinal for shard in shards) == (0, 1, 2, 3)
    assert all(shard.runtime == _runtime() for shard in shards)
    result = finalize_b1g_checkpoint(checkpoint, header, plan)
    assert result.summary["comparison_complete"] is True
    assert len(result.predictions) == 4


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
    assert document["schema_version"] == 3
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
    original_inner = candidates[0].inner_folds[0]
    bad_initial = replace(original_inner.fit_attempts[0], diagnostics=BAD)
    bad_inner = replace(
        original_inner,
        sampler_diagnostics=BAD,
        fit_attempts=(bad_initial, original_inner.fit_attempts[1]),
    )
    candidates[0] = replace(
        candidates[0],
        inner_folds=(bad_inner, *candidates[0].inner_folds[1:]),
    )
    contradictory = replace(fold, candidate_scores=tuple(candidates))

    with pytest.raises(ValueError, match="attempt status contradicts convergence"):
        write_b1g_fold_shard(
            checkpoint,
            header,
            plan,
            0,
            contradictory,
            _runtime(),
        )


def test_checkpoint_refuses_candidate_with_four_inner_folds(tmp_path):
    plan = _plan()
    header = _header(plan)
    checkpoint = tmp_path / "checkpoint"
    initialize_checkpoint(checkpoint, header)
    fold = _fold(plan, 0)
    candidates = list(fold.candidate_scores)
    extra = replace(
        candidates[0].inner_folds[0],
        split_id="inner-3",
        inner_block_id="inner-3",
        source_block_ids=("source-3",),
    )
    candidates[0] = replace(
        candidates[0],
        requested_count=4,
        scored_count=4,
        completed_inner_fold_count=4,
        inner_folds=(*candidates[0].inner_folds, extra),
    )

    with pytest.raises(ValueError, match="exactly three inner folds"):
        write_b1g_fold_shard(
            checkpoint,
            header,
            plan,
            0,
            replace(fold, candidate_scores=tuple(candidates)),
            _runtime(),
        )


def test_checkpoint_refuses_candidates_with_different_grouping_evidence(tmp_path):
    plan = _plan()
    header = _header(plan)
    checkpoint = tmp_path / "checkpoint"
    initialize_checkpoint(checkpoint, header)
    fold = _fold(plan, 0)
    candidates = list(fold.candidate_scores)
    changed = replace(candidates[1].inner_folds[0], grouping_sha256="e" * 64)
    candidates[1] = replace(
        candidates[1],
        inner_folds=(changed, *candidates[1].inner_folds[1:]),
    )

    with pytest.raises(ValueError, match="disagrees with the frozen inner-fold grouping"):
        write_b1g_fold_shard(
            checkpoint,
            header,
            plan,
            0,
            replace(fold, candidate_scores=tuple(candidates)),
            _runtime(),
        )


def test_checkpoint_refuses_missing_inner_or_outer_fit_attempt_evidence(tmp_path):
    plan = _plan()
    header = _header(plan)
    checkpoint = tmp_path / "checkpoint"
    initialize_checkpoint(checkpoint, header)
    fold = _fold(plan, 0)
    candidates = list(fold.candidate_scores)
    missing_inner = replace(candidates[0].inner_folds[0], fit_attempts=())
    candidates[0] = replace(
        candidates[0],
        inner_folds=(missing_inner, *candidates[0].inner_folds[1:]),
    )

    with pytest.raises(ValueError, match="exactly two attempt slots"):
        write_b1g_fold_shard(
            checkpoint,
            header,
            plan,
            0,
            replace(fold, candidate_scores=tuple(candidates)),
            _runtime(),
        )
    with pytest.raises(ValueError, match="exactly two attempt slots"):
        write_b1g_fold_shard(
            checkpoint,
            header,
            plan,
            0,
            replace(fold, fit_attempts=()),
            _runtime(),
        )


def test_checkpoint_round_trip_preserves_failed_initial_and_accepted_retry(tmp_path):
    plan = _plan()
    header = _header(plan)
    checkpoint = tmp_path / "checkpoint"
    initialize_checkpoint(checkpoint, header)
    fold = _fold(plan, 0)
    candidates = list(fold.candidate_scores)
    inner = candidates[0].inner_folds[0]
    initial, retry = inner.fit_attempts
    retried = replace(
        inner,
        fit_seed=retry.config.seed,
        fit_attempts=(
            replace(
                initial,
                status="convergence_failed",
                reason="B1GConvergenceError: synthetic initial failure",
                diagnostics=BAD,
            ),
            replace(retry, status="accepted", reason=None, diagnostics=GOOD),
        ),
    )
    candidates[0] = replace(
        candidates[0],
        inner_folds=(retried, *candidates[0].inner_folds[1:]),
    )

    write_b1g_fold_shard(
        checkpoint,
        header,
        plan,
        0,
        replace(fold, candidate_scores=tuple(candidates)),
        _runtime(),
    )

    (loaded,) = load_b1g_fold_shards(checkpoint, header, plan)
    attempts = loaded.result.candidate_scores[0].inner_folds[0].fit_attempts
    assert tuple(attempt.status for attempt in attempts) == (
        "convergence_failed",
        "accepted",
    )
    assert attempts[0].diagnostics == BAD
    assert attempts[1].diagnostics == GOOD


def test_finalization_refuses_missing_parallel_shards(tmp_path):
    plan = _plan()
    header = _header(plan)
    checkpoint = tmp_path / "checkpoint"
    initialize_checkpoint(checkpoint, header)
    write_b1g_fold_shard(checkpoint, header, plan, 1, _fold(plan, 1), _runtime())

    with pytest.raises(ValueError, match="exactly one result"):
        finalize_b1g_checkpoint(checkpoint, header, plan)
