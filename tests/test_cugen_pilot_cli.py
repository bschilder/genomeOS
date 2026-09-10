"""Subprocess checks for the synthetic-only CuGen LD pilot CLI (design §8)."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "pilot_cugen_ld.py"
PINNED_CUGEN = Path("/private/tmp/genomeos-cugen-precision.jfAGjg/source")
REVISION = "0123456789abcdef0123456789abcdef01234567"


def _command(out: Path, *, case: str = "hand", repeats: int = 3) -> list[str]:
    return [
        sys.executable,
        str(SCRIPT),
        "--cugen-root",
        str(PINNED_CUGEN),
        "--out",
        str(out),
        "--data-version",
        "fixture-v1",
        "--case",
        case,
        "--repeats",
        str(repeats),
        "--seed",
        "42",
        "--source-revision",
        REVISION,
    ]


def _environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return environment


def _experiment_module() -> object:
    spec = importlib.util.find_spec("genomeos.validation.cugen_experiment")
    assert spec is not None, "synthetic CuGen experiment module must exist"
    return importlib.import_module("genomeos.validation.cugen_experiment")


def _measurement_module() -> object:
    spec = importlib.util.find_spec("genomeos.validation.cugen_measurement")
    assert spec is not None, "CuGen runtime measurement module must exist"
    return importlib.import_module("genomeos.validation.cugen_measurement")


def test_cli_refuses_fewer_than_three_repeats_before_source_or_gpu_access(tmp_path: Path) -> None:
    """Catch an under-repeated experiment reaching source loading or device execution."""
    environment = _environment()
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--cugen-root",
            str(tmp_path / "unavailable-source"),
            "--out",
            str(tmp_path / "out"),
            "--data-version",
            "fixture-v1",
            "--case",
            "hand",
            "--repeats",
            "2",
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 2
    assert "--repeats must be at least 3" in completed.stderr
    assert not (tmp_path / "out").exists()


def test_synthetic_cases_are_reproducible_and_preserve_hand_fixture_literals() -> None:
    """Catch nondeterministic fixtures or drift from the independently hand-checked case."""
    experiment = _experiment_module()
    first = experiment.build_synthetic_case("hand", seed=42)
    second = experiment.build_synthetic_case("hand", seed=42)

    np.testing.assert_array_equal(
        first.calls,
        np.array(
            [
                [0, 0, 2, 3, 1, 0, 3],
                [1, 1, 1, 3, 1, 3, 3],
                [2, 2, 0, 3, 1, 2, 3],
                [0, 2, 0, 3, 1, 3, 0],
                [2, 0, 2, 3, 1, 1, 1],
                [1, 2, 0, 3, 1, 2, 3],
                [0, 1, 1, 3, 1, 0, 0],
                [2, 0, 2, 3, 1, 2, 3],
            ],
            dtype=np.uint8,
        ),
    )
    np.testing.assert_array_equal(first.calls, second.calls)
    assert first.selection == second.selection
    assert first.variants == second.variants
    assert tuple(item.gidx for item in first.variants) == (30, 10, 70, 20, 60, 40, 50)
    assert first.selection.training_indices == (4, 0, 2, 1)
    assert first.calls.flags.writeable is False


def test_scale_case_hits_caps_and_held_out_mutation_never_changes_training() -> None:
    """Catch scale drift or a leakage control that mutates any selected training genotype."""
    experiment = _experiment_module()
    original = experiment.build_synthetic_case("scale", seed=42)
    mutated = experiment.mutate_held_out(original)
    held_rows = [original.selection.sample_ids.index(item) for item in original.selection.held_out_ids]

    assert original.calls.shape == (4096, 64)
    assert len(original.selection.training_ids) == 3072
    assert len(original.selection.held_out_ids) == 512
    assert len(original.selection.excluded_ids) == 512
    np.testing.assert_array_equal(
        original.calls[np.asarray(original.selection.training_indices)],
        mutated.calls[np.asarray(mutated.selection.training_indices)],
    )
    assert np.all(original.calls[np.asarray(held_rows)] != mutated.calls[np.asarray(held_rows)])


def test_precision_case_contains_all_independent_near_fixed_controls() -> None:
    """Catch dropping a sample-size, overlap, or allele-flip precision regression control."""
    experiment = _experiment_module()
    case = experiment.build_synthetic_case("precision", seed=42)

    assert case.calls.shape == (4096, 16)
    assert case.precision_controls == (
        (3072, False, False, 0, 1),
        (3072, False, True, 2, 3),
        (3072, True, False, 4, 5),
        (3072, True, True, 6, 7),
        (4096, False, False, 8, 9),
        (4096, False, True, 10, 11),
        (4096, True, False, 12, 13),
        (4096, True, True, 14, 15),
    )
    for n, overlap, flipped, left, right in case.precision_controls:
        called = case.calls[:n, (left, right)]
        assert called[0, 0] == 1
        assert called[3, 0] == (0 if flipped else 2)
        rare_right = {0, 1} if overlap else {1, 2}
        assert {int(i) for i in np.flatnonzero(called[:, 1] == 1)} == rare_right
        if n == 3072:
            assert np.all(case.calls[n:, (left, right)] == 3)


def test_stage_measurement_synchronizes_device_boundaries_and_labels_pool_snapshots() -> None:
    """Catch asynchronous device clocks or stage snapshots being mislabeled as memory peaks."""
    measurement = _measurement_module()
    synchronized: list[str] = []
    ticks = iter((1.0, 3.0, 5.0, 11.0))
    observer = measurement.PilotMeasurementObserver(
        synchronize=lambda: synchronized.append("sync"),
        clock=lambda: next(ticks),
        rss_high_water=lambda: 123,
        pool_snapshot=lambda: {"device_used_bytes": 7, "device_retained_bytes": 9},
    )

    for stage in ("subset", "gpu_ld"):
        observer(stage, "start")
        observer(stage, "end")

    assert synchronized == ["sync", "sync", "sync", "sync"]
    assert [(item.stage, item.seconds) for item in observer.records] == [
        ("subset", 2.0),
        ("gpu_ld", 6.0),
    ]
    assert all(item.memory_semantics == "stage_boundary_snapshots_not_peaks" for item in observer.records)


def test_outer_measurement_includes_serialization_and_completed_reader_verification() -> None:
    """Catch stopping the full-workflow clock before artifact writing or verification returns."""
    measurement = _measurement_module()
    ticks = iter((0.0, 1.0, 3.0, 4.0, 9.0, 10.0))
    observer = measurement.PilotMeasurementObserver(
        synchronize=lambda: None,
        clock=lambda: next(ticks),
        rss_high_water=lambda: 1,
        pool_snapshot=lambda: {},
    )

    def run(active_observer: object) -> str:
        active_observer("artifact_write", "start")
        active_observer("artifact_write", "end")
        active_observer("artifact_verification", "start")
        active_observer("artifact_verification", "end")
        return "manifest"

    result, seconds = measurement.measure_full_workflow(run, observer=observer, clock=lambda: next(ticks))

    assert result == "manifest"
    assert seconds == 10.0
    assert [(item.stage, item.seconds) for item in observer.records] == [
        ("artifact_write", 2.0),
        ("artifact_verification", 5.0),
    ]


def test_cli_refuses_existing_output_without_mutation(tmp_path: Path) -> None:
    """Catch reruns overwriting or mingling a prior experiment summary."""
    output = tmp_path / "existing"
    output.mkdir()
    sentinel = output / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")

    completed = subprocess.run(
        _command(output), cwd=ROOT, env=_environment(), capture_output=True, text=True, check=False
    )

    assert completed.returncode == 2
    assert "output path already exists" in completed.stderr
    assert sentinel.read_text(encoding="utf-8") == "keep"


def test_unavailable_gpu_is_nonzero_with_complete_planned_run_accounting(tmp_path: Path) -> None:
    """Catch an unavailable requested GPU becoming a skip or silently dropped planned runs."""
    assert PINNED_CUGEN.is_dir(), "controller-qualified pinned CuGen source is required"
    environment = _environment()
    environment["CUDA_VISIBLE_DEVICES"] = ""
    output = tmp_path / "failed"

    completed = subprocess.run(
        _command(output), cwd=ROOT, env=environment, capture_output=True, text=True, check=False
    )

    assert completed.returncode == 2
    assert "CUDA" in completed.stderr
    summary = json.loads((output / "experiment.json").read_text(encoding="utf-8"))
    assert summary["status"] == "failed"
    assert summary["planned_count"] == 6
    assert summary["completed_count"] == 0
    assert summary["failed_count"] == 6
    assert len(summary["planned_runs"]) == 6
    assert all(item["status"] == "failed" for item in summary["planned_runs"])
    assert all(item["failure"]["stage"] == "cuda_preflight" for item in summary["planned_runs"])


def test_cli_source_generation_is_reproducible_across_fresh_failed_processes(tmp_path: Path) -> None:
    """Catch process-dependent synthetic bytes before hardware execution begins."""
    assert PINNED_CUGEN.is_dir(), "controller-qualified pinned CuGen source is required"
    environment = _environment()
    environment["CUDA_VISIBLE_DEVICES"] = ""
    outputs = (tmp_path / "first", tmp_path / "second")
    summaries: list[dict[str, object]] = []
    for output in outputs:
        completed = subprocess.run(
            _command(output), cwd=ROOT, env=environment, capture_output=True, text=True, check=False
        )
        assert completed.returncode == 2
        summaries.append(json.loads((output / "experiment.json").read_text(encoding="utf-8")))

    assert [item["run_id"] for item in summaries[0]["planned_runs"]] == [
        item["run_id"] for item in summaries[1]["planned_runs"]
    ]
    assert [item["source_sha256"] for item in summaries[0]["planned_runs"]] == [
        item["source_sha256"] for item in summaries[1]["planned_runs"]
    ]
