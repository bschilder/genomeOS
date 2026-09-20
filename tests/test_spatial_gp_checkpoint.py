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

    assert tuple(result.status for result in observed) == tuple(result.status for result in expected)
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


@pytest.mark.parametrize(
    "filename,hash_field",
    [
        ("checkpoint.json", "header_sha256"),
        ("folds/0000.json", "artifact_sha256"),
    ],
)
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


SPLIT_CHANGES = [
    {"split_id": "different-split"},
    {"block_id": "different-held-out-block"},
    {"train_ids": ("different-training-row",)},
    {"test_ids": ("different-test-row",)},
    {"excluded_ids": ("different-excluded-row",)},
    {"exclusion_reasons": (("different-excluded-row", ("buffer",)),)},
    {"min_edge_separation_km": 999.0},
    {"input_fingerprint": "f" * 64},
    {"buffer_km": 999.0},
    {"data_version": "different-data-version"},
]


@pytest.mark.parametrize("change", SPLIT_CHANGES, ids=lambda value: next(iter(value)))
def test_write_binds_every_split_field_to_header_before_publication(tmp_path, change):
    split = _split(0)
    root = tmp_path / "checkpoint"
    initialize_checkpoint(root, _header((split,)))
    altered = replace(split, **change)
    before = (root / "checkpoint.json").read_bytes()
    with pytest.raises(ValueError, match="frozen split"):
        write_fold_checkpoint(root, 0, altered, _terminal(altered, "failed"))
    assert not list((root / "folds").iterdir())
    assert (root / "checkpoint.json").read_bytes() == before


@pytest.mark.parametrize("prefix_length", [0, 1])
@pytest.mark.parametrize("change", SPLIT_CHANGES, ids=lambda value: next(iter(value)))
def test_load_binds_every_split_field_even_before_an_empty_prefix(tmp_path, change, prefix_length):
    split = _split(0)
    root = tmp_path / "checkpoint"
    header = _header((split,))
    initialize_checkpoint(root, header)
    if prefix_length:
        write_fold_checkpoint(root, 0, split, _terminal(split, "failed"))
    before = {path.name: path.read_bytes() for path in (root / "folds").iterdir()}
    with pytest.raises(ValueError, match="frozen split"):
        load_fold_checkpoints(root, header, (replace(split, **change),))
    assert {path.name: path.read_bytes() for path in (root / "folds").iterdir()} == before


@pytest.mark.parametrize("change", ["reverse", "duplicate", "missing", "extra", "empty"])
def test_load_requires_exact_complete_ordered_caller_ledger(tmp_path, change):
    splits = (_split(0), _split(1))
    root = tmp_path / "checkpoint"
    header = _header(splits)
    initialize_checkpoint(root, header)
    supplied = {
        "reverse": splits[::-1],
        "duplicate": (splits[0], splits[0]),
        "missing": splits[:1],
        "extra": (*splits, _split(2)),
        "empty": (),
    }[change]
    with pytest.raises(ValueError, match="frozen split"):
        load_fold_checkpoints(root, header, supplied)
    from genomeos.validation.spatial_gp_checkpoint import finalize_checkpoint_benchmark

    with pytest.raises(ValueError, match="frozen split"):
        finalize_checkpoint_benchmark(root, header, _checkpoint_plan(supplied))


@pytest.mark.parametrize("ordinal", [-1, 1, True, 0.5])
def test_write_refuses_invalid_or_out_of_range_ordinal_before_publication(tmp_path, ordinal):
    split = _split(0)
    root = tmp_path / "checkpoint"
    initialize_checkpoint(root, _header((split,)))
    with pytest.raises(ValueError, match="ordinal"):
        write_fold_checkpoint(root, ordinal, split, _completed(split))
    assert not list((root / "folds").iterdir())


@pytest.mark.parametrize("change", ["digest", "missing_field", "extra_field", "duplicate", "empty"])
def test_header_refuses_invalid_rehashed_split_ledger_before_initialization(tmp_path, change):
    header = _header((_split(0),))
    if change == "digest":
        header["planned_splits_sha256"] = "f" * 64
    else:
        if change == "missing_field":
            del header["planned_splits"][0]["train_ids"]
        elif change == "extra_field":
            header["planned_splits"][0]["held_out_block_ids"] = ["unexpected"]
        elif change == "duplicate":
            header["planned_splits"] *= 2
        else:
            header["planned_splits"] = []
        header["planned_splits_sha256"] = hashlib.sha256(
            json.dumps(
                header["planned_splits"], sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode()
        ).hexdigest()
    _rehash_document(header, "header_sha256")
    with pytest.raises(ValueError, match="planned split"):
        initialize_checkpoint(tmp_path / "checkpoint", header)
    assert not (tmp_path / "checkpoint").exists()


def _checkpoint_plan(splits):
    from genomeos.surfaces.config import FitConfig
    from genomeos.validation.spatial_gp_benchmark import SpatialGPBenchmarkPlan

    # Finalization uses only the immutable split/configuration and retained fold evidence.
    return SpatialGPBenchmarkPlan(
        pd.DataFrame(), pd.DataFrame(), splits, FitConfig(likelihood="binomial"), 42, "scipy", None
    )


@pytest.mark.parametrize("change", SPLIT_CHANGES, ids=lambda value: next(iter(value)))
def test_finalization_reloads_only_header_bound_plan_splits(tmp_path, change):
    from genomeos.validation.spatial_gp_checkpoint import finalize_checkpoint_benchmark

    split = _split(0)
    root = tmp_path / "checkpoint"
    header = _header((split,))
    initialize_checkpoint(root, header)
    write_fold_checkpoint(root, 0, split, _terminal(split, "failed"))
    before = (root / "folds/0000.json").read_bytes()
    with pytest.raises(ValueError, match="frozen split"):
        finalize_checkpoint_benchmark(root, header, _checkpoint_plan((replace(split, **change),)))
    assert (root / "folds/0000.json").read_bytes() == before


def test_valid_partial_prefix_and_all_terminal_states_remain_reusable(tmp_path):
    from genomeos.validation.spatial_gp_checkpoint import finalize_checkpoint_benchmark

    splits = tuple(_split(index) for index in range(3))
    header = _header(splits)
    root = tmp_path / "checkpoint"
    initialize_checkpoint(root, header)
    results = (_completed(splits[0]), _terminal(splits[1], "failed"), _terminal(splits[2], "infeasible"))
    assert load_fold_checkpoints(root, header, splits) == ()
    for index, (split, result) in enumerate(zip(splits, results, strict=True)):
        write_fold_checkpoint(root, index, split, result)
        assert len(load_fold_checkpoints(root, header, splits)) == index + 1
        if index < 2:
            with pytest.raises(ValueError, match="cover exactly"):
                finalize_checkpoint_benchmark(root, header, _checkpoint_plan(splits))
    before = {p.name: p.read_bytes() for p in (root / "folds").iterdir()}
    final = finalize_checkpoint_benchmark(root, header, _checkpoint_plan(splits))
    assert [status.status for status in final.fold_status] == ["completed", "failed", "infeasible"]
    assert {p.name: p.read_bytes() for p in (root / "folds").iterdir()} == before


@pytest.mark.parametrize("field", ["train_ids", "test_ids", "excluded_ids", "exclusion_reasons"])
def test_member_order_is_part_of_frozen_identity(tmp_path, field):
    split = replace(
        _split(0),
        train_ids=("train-a", "train-b"),
        test_ids=("test-a", "test-b"),
        excluded_ids=("excluded-a", "excluded-b"),
        exclusion_reasons=(("excluded-a", ("buffer",)), ("excluded-b", ("dependency",))),
    )
    header = _header((split,))
    root = tmp_path / "checkpoint"
    initialize_checkpoint(root, header)
    changed = replace(split, **{field: getattr(split, field)[::-1]})
    with pytest.raises(ValueError, match="frozen split"):
        write_fold_checkpoint(root, 0, changed, _terminal(changed, "failed"))
    with pytest.raises(ValueError, match="frozen split"):
        load_fold_checkpoints(root, header, (changed,))
    assert not list((root / "folds").iterdir())


def test_atomic_write_failure_and_competing_publication_preserve_evidence(tmp_path, monkeypatch):
    import genomeos.validation.spatial_gp_checkpoint as checkpoints

    split = _split(0)
    root = tmp_path / "checkpoint"
    initialize_checkpoint(root, _header((split,)))
    target = root / "folds/0000.json"
    real_fsync = checkpoints.os.fsync

    def failing_fsync(_descriptor):
        raise OSError("simulated prepublication failure")

    monkeypatch.setattr(checkpoints.os, "fsync", failing_fsync)
    with pytest.raises(OSError, match="prepublication"):
        write_fold_checkpoint(root, 0, split, _completed(split))
    assert not list((root / "folds").iterdir())
    monkeypatch.setattr(checkpoints.os, "fsync", real_fsync)
    real_link = checkpoints.os.link

    def racing_link(source, destination):
        target.write_bytes(b"competing immutable evidence")
        real_link(source, destination)

    monkeypatch.setattr(checkpoints.os, "link", racing_link)
    with pytest.raises(FileExistsError, match="immutable"):
        write_fold_checkpoint(root, 0, split, _completed(split))
    assert target.read_bytes() == b"competing immutable evidence"
    assert list((root / "folds").iterdir()) == [target]


def test_writer_binds_the_supplied_split_to_the_requested_ordinal(tmp_path):
    splits = (_split(0), _split(1))
    root = tmp_path / "checkpoint"
    initialize_checkpoint(root, _header(splits))
    with pytest.raises(ValueError, match="frozen split"):
        write_fold_checkpoint(root, 1, splits[0], _terminal(splits[0], "failed"))
    assert not list((root / "folds").iterdir())
