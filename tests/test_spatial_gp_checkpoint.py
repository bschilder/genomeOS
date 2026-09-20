"""Fold-checkpoint artifact contract (design §§5, 7–8, 12; #319)."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import replace

import pandas as pd
import pytest

from genomeos.surfaces.convergence import SamplerDiagnostics
from genomeos.validation.benchmark import BenchmarkFoldStatus
from genomeos.validation.spatial_gp_benchmark import (
    PREDICTION_COLUMNS,
    SpatialGPFoldResult,
)
from genomeos.validation.spatial_gp_checkpoint import (
    build_checkpoint_header,
    initialize_checkpoint,
    load_fold_checkpoints,
    write_fold_checkpoint,
)
from genomeos.validation.splits import BenchmarkSplit

GOOD_DIAGNOSTICS = SamplerDiagnostics(1.01, "z", 300.0, "z", 260.0, "z", 0)
BAD_DIAGNOSTICS = SamplerDiagnostics(1.08, "z", 150.0, "z", 180.0, "z", 1)


def _split(index: int) -> BenchmarkSplit:
    return BenchmarkSplit(
        split_id=f"split-{index}",
        block_id=f"block-{index}",
        train_ids=("train",),
        test_ids=(f"obs-{index}",),
        excluded_ids=(),
        exclusion_reasons=(),
        min_edge_separation_km=100.0,
        input_fingerprint="a" * 64,
        buffer_km=10.0,
        data_version="test-v1",
    )


def _header(splits: tuple[BenchmarkSplit, ...], *, change: str | None = None):
    configuration = {
        "buffer_km": 10.0,
        "cdf_backend": "scipy",
        "data_version": "test-v1",
        "fit_config": {"likelihood": "beta_binomial", "max_rhat": 1.05, "min_ess": 200.0},
        "sampler_convergence_gate": {
            "maximum_divergences": 0,
            "maximum_rhat": 1.05,
            "minimum_bulk_ess": 200.0,
            "minimum_tail_ess": 200.0,
        },
        "seed": 42,
    }
    input_files = {"observations": {"sha256": "b" * 64, "size_bytes": 10}}
    planned_splits = [split.__dict__ for split in splits]
    seed_schedule = [
        {"split_id": split.split_id, "fit_seed": index + 10, "predictive_seed": index + 20}
        for index, split in enumerate(splits)
    ]
    code_revision = "c" * 40
    science_sources = {"science.py": "d" * 64}
    package_versions = {"python": "3.12.0", "genomeos": "0.1.0"}
    if change == "configuration":
        configuration = deepcopy(configuration)
        configuration["fit_config"]["likelihood"] = "binomial"
    elif change == "backend":
        configuration = dict(configuration, cdf_backend="cupy")
    elif change == "inputs":
        input_files = {"observations": {"sha256": "e" * 64, "size_bytes": 10}}
    elif change == "splits":
        planned_splits = deepcopy(planned_splits)
        planned_splits[0]["buffer_km"] = 100.0
    elif change == "seeds":
        seed_schedule = deepcopy(seed_schedule)
        seed_schedule[0]["fit_seed"] += 1
    elif change == "code":
        code_revision = "e" * 40
    elif change == "science":
        science_sources = {"science.py": "f" * 64}
    elif change == "packages":
        package_versions = dict(package_versions, numpy="2.0.0")
    return build_checkpoint_header(
        model_id="B2-current",
        evidence_kind="synthetic_fixture",
        qualification={"scientific_promotion_decision": "not_made"},
        configuration=configuration,
        input_files=input_files,
        planned_splits=planned_splits,
        seed_schedule=seed_schedule,
        code_revision=code_revision,
        science_source_sha256=science_sources,
        package_versions=package_versions,
    )


def _completed(split: BenchmarkSplit, *, log_score: float = -1.0) -> SpatialGPFoldResult:
    row = {
        "split_id": split.split_id,
        "block_id": split.block_id,
        "source_record_id": split.test_ids[0],
        "variant_id": "chr11-5227002-T-A",
        "region_id": "region-1",
        "variant_group": "hbs",
        "cohort_id": "cohort-1",
        "observed_ac": 1,
        "observed_an": 100,
        "fit_seed": 10,
        "predictive_seed": 20,
        "log_score": log_score,
        "absolute_error": 0.1,
        "squared_error": 0.01,
        "coverage_50": True,
        "interval_width_50": 0.1,
        "coverage_80": True,
        "interval_width_80": 0.2,
        "coverage_95": True,
        "interval_width_95": 0.3,
        "randomized_pit": 0.5,
    }
    return SpatialGPFoldResult(
        status=BenchmarkFoldStatus(split.split_id, "completed", split.test_ids, None),
        predictions=pd.DataFrame([row], columns=PREDICTION_COLUMNS),
        sampler_diagnostics=GOOD_DIAGNOSTICS,
    )


def _terminal(
    split: BenchmarkSplit,
    state: str,
    diagnostics: SamplerDiagnostics | None = None,
) -> SpatialGPFoldResult:
    return SpatialGPFoldResult(
        status=BenchmarkFoldStatus(split.split_id, state, split.test_ids, f"{state} reason"),
        predictions=pd.DataFrame(columns=PREDICTION_COLUMNS),
        sampler_diagnostics=diagnostics,
    )


def test_fold_checkpoints_round_trip_all_terminal_states_and_negative_infinity(tmp_path):
    splits = tuple(_split(index) for index in range(3))
    root = tmp_path / "checkpoint"
    initialize_checkpoint(root, _header(splits))
    expected = (
        _completed(splits[0], log_score=float("-inf")),
        _terminal(splits[1], "failed", BAD_DIAGNOSTICS),
        _terminal(splits[2], "infeasible"),
    )
    for ordinal, (split, result) in enumerate(zip(splits, expected, strict=True)):
        write_fold_checkpoint(root, ordinal, split, result)

    observed = load_fold_checkpoints(root, _header(splits), splits)

    assert tuple(result.status for result in observed) == tuple(
        result.status for result in expected
    )
    for actual, wanted in zip(observed, expected, strict=True):
        pd.testing.assert_frame_equal(actual.predictions, wanted.predictions, check_dtype=False)
        assert actual.sampler_diagnostics == wanted.sampler_diagnostics
    with pytest.raises(FileExistsError, match="immutable"):
        write_fold_checkpoint(root, 0, splits[0], expected[0])


def test_completed_fold_cannot_exist_without_sampler_diagnostics():
    split = _split(0)
    with pytest.raises(ValueError, match="completed folds must retain"):
        SpatialGPFoldResult(
            status=BenchmarkFoldStatus(split.split_id, "completed", split.test_ids, None),
            predictions=_completed(split).predictions,
            sampler_diagnostics=None,
        )


@pytest.mark.parametrize(
    "change",
    ["configuration", "backend", "inputs", "splits", "seeds", "code", "science", "packages"],
)
def test_resume_refuses_every_scientific_and_provenance_identity_mismatch(tmp_path, change):
    splits = (_split(0), _split(1))
    root = tmp_path / "checkpoint"
    initialize_checkpoint(root, _header(splits))

    with pytest.raises(ValueError, match="checkpoint header mismatch"):
        load_fold_checkpoints(root, _header(splits, change=change), splits)


def test_resume_refuses_noncontiguous_or_corrupted_fold_artifacts(tmp_path):
    splits = (_split(0), _split(1))
    root = tmp_path / "checkpoint"
    initialize_checkpoint(root, _header(splits))
    write_fold_checkpoint(root, 1, splits[1], _completed(splits[1]))
    with pytest.raises(ValueError, match="contiguous prefix"):
        load_fold_checkpoints(root, _header(splits), splits)

    (root / "folds" / "0001.json").unlink()
    write_fold_checkpoint(root, 0, splits[0], _completed(splits[0]))
    path = root / "folds" / "0000.json"
    document = json.loads(path.read_text())
    document["prediction_rows"][0][PREDICTION_COLUMNS.index("observed_ac")] = 99
    path.write_text(json.dumps(document))
    with pytest.raises(ValueError, match="integrity"):
        load_fold_checkpoints(root, _header(splits), splits)


FAILING_GATES = [
    {"max_rhat": 1.051},
    {"min_bulk_ess": 199.0},
    {"min_tail_ess": 199.0},
    {"divergence_count": 1},
]


def _rehash_document(document, hash_field):
    body = {key: value for key, value in document.items() if key != hash_field}
    document[hash_field] = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


@pytest.mark.parametrize("change", FAILING_GATES)
def test_checkpoint_write_refuses_completed_fold_with_failed_gate(tmp_path, change):
    split = _split(0)
    root = tmp_path / "checkpoint"
    initialize_checkpoint(root, _header((split,)))
    result = replace(_completed(split), sampler_diagnostics=replace(GOOD_DIAGNOSTICS, **change))

    with pytest.raises(ValueError, match="completed fold.*convergence"):
        write_fold_checkpoint(root, 0, split, result)

    assert list((root / "folds").iterdir()) == []


@pytest.mark.parametrize("change", FAILING_GATES)
def test_checkpoint_load_refuses_rehashed_completed_fold_with_failed_gate(tmp_path, change):
    split = _split(0)
    root = tmp_path / "checkpoint"
    header = _header((split,))
    initialize_checkpoint(root, header)
    write_fold_checkpoint(root, 0, split, _completed(split))
    path = root / "folds" / "0000.json"
    document = json.loads(path.read_text())
    document["sampler_diagnostics"].update(change)
    _rehash_document(document, "artifact_sha256")
    path.write_text(json.dumps(document))
    original = path.read_bytes()

    with pytest.raises(ValueError, match="completed fold.*convergence"):
        load_fold_checkpoints(root, header, (split,))

    assert path.read_bytes() == original


@pytest.mark.parametrize("filename,hash_field", [
    ("checkpoint.json", "header_sha256"),
    ("folds/0000.json", "artifact_sha256"),
])
def test_resume_refuses_schema_v1_without_retrospective_upgrade(tmp_path, filename, hash_field):
    split = _split(0)
    root = tmp_path / "checkpoint"
    header = _header((split,))
    initialize_checkpoint(root, header)
    write_fold_checkpoint(root, 0, split, _completed(split))
    path = root / filename
    document = json.loads(path.read_text())
    document["schema_version"] = 1
    _rehash_document(document, hash_field)
    path.write_text(json.dumps(document))
    original = path.read_bytes()

    with pytest.raises(ValueError, match="schema version is unsupported"):
        load_fold_checkpoints(root, header, (split,))

    assert path.read_bytes() == original


@pytest.mark.parametrize("change", ["missing", "inconsistent"])
def test_checkpoint_refuses_unavailable_or_inconsistent_frozen_gate(tmp_path, change):
    header = _header((_split(0),))
    if change == "missing":
        del header["configuration"]["sampler_convergence_gate"]
    else:
        header["configuration"]["sampler_convergence_gate"]["maximum_rhat"] = 1.2
    _rehash_document(header, "header_sha256")

    with pytest.raises(ValueError, match="convergence gate"):
        initialize_checkpoint(tmp_path / "checkpoint", header)

    assert not (tmp_path / "checkpoint").exists()
