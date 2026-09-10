"""Actual synthetic GPU admission checks for CuGen training-only LD (design §§4, 8)."""

from __future__ import annotations

import importlib.util
import json
import os
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from genomeos.validation.cugen_backend import load_verified_cugen_api
from genomeos.validation.cugen_experiment import build_synthetic_case, mutate_held_out
from genomeos.validation.cugen_pilot import run_cugen_pilot
from genomeos.validation.ld_contract import LDVariant, validate_training_selection

for _name in ("CUPY_TF32", "NVIDIA_TF32_OVERRIDE", "USE_PINNED_READER"):
    os.environ[_name] = "0"


def _gpu_available() -> bool:
    if importlib.util.find_spec("cupy") is None:
        return False
    import cupy as cp

    try:
        return cp.cuda.runtime.getDeviceCount() > 0
    except cp.cuda.runtime.CUDARuntimeError:
        return False


requires_gpu = pytest.mark.skipif(not _gpu_available(), reason="requires a working CUDA device")


def _runtime_inputs() -> tuple[Path, str]:
    root_value = os.environ.get("CUGEN_ROOT")
    revision = os.environ.get("GENOMEOS_SOURCE_REVISION", "")
    assert root_value is not None, "CUGEN_ROOT must name the audited pinned source tree"
    root = Path(root_value)
    assert root.is_dir(), "CUGEN_ROOT must name the audited pinned source tree"
    assert re.fullmatch(r"[0-9a-f]{40}", revision), (
        "GENOMEOS_SOURCE_REVISION must be the executing source-only bundle commit"
    )
    return root, revision


def _write_and_run(tmp_path: Path, case: object, name: str, chunk: int, tile: int) -> Path:
    root, revision = _runtime_inputs()
    api = load_verified_cugen_api(root)
    source = tmp_path / f"{name}.cugen"
    api.write_cugen(
        source,
        case.calls,
        gidx=np.asarray([item.gidx for item in case.variants], dtype=np.int64),
        encoding=0,
    )
    return run_cugen_pilot(
        source,
        variants=case.variants,
        selection=case.selection,
        genome_build="GRCh38",
        ploidy="autosomal_diploid",
        evidence_kind="synthetic_fixture",
        data_version="gpu-synthetic-v1",
        cugen_root=root,
        window_variants=case.window_variants,
        window_bp=case.window_bp,
        chunk_size=chunk,
        tile_size=tile,
        out=tmp_path / f"{name}-artifact",
        source_revision=revision,
    )


@requires_gpu
@pytest.mark.parametrize(
    ("samples", "variants", "chunk", "tile"),
    [(1, 2, 1, 1), (3, 2, 1, 1), (4, 3, 2, 2), (5, 4, 3, 3)],
)
def test_actual_gpu_covers_small_subset_chunk_and_tile_boundaries(
    tmp_path: Path, samples: int, variants: int, chunk: int, tile: int
) -> None:
    """Catch GPU disagreement across subset sizes 1/3/4/5 and chunk/tile sizes 1/2/3."""
    base = build_synthetic_case("hand", seed=42)
    calls = np.asarray(base.calls[:samples, :variants])
    ids = tuple(f"boundary-{row}" for row in range(samples))
    selection = validate_training_selection(ids, tuple(range(samples)), held_out_ids=(), excluded_ids=())
    case = type(base)(
        name="boundary",
        calls=calls,
        variants=base.variants[:variants],
        selection=selection,
        window_variants=None,
        window_bp=None,
        chunk_size=chunk,
        tile_size=tile,
    )

    manifest = json.loads(_write_and_run(tmp_path, case, f"boundary-{chunk}", chunk, tile).read_text())

    assert manifest["validation"]["gpu"]["passed"] is True
    assert manifest["chunk_size"] == chunk
    assert manifest["tile_size"] == tile


@requires_gpu
def test_actual_gpu_preserves_zero_all_missing_and_monomorphic_refusals(tmp_path: Path) -> None:
    """Catch missing or constant calls being recoded into reported zero correlations."""
    base = build_synthetic_case("hand", seed=42)
    calls = np.array(
        [[0, 3, 1, 0, 0], [0, 3, 1, 1, 2], [0, 3, 1, 2, 1], [0, 3, 1, 0, 2]],
        dtype=np.uint8,
    )
    variants = tuple(
        LDVariant(row, f"1-{100 + row}-A-C", "1", 100 + row, "A", "C")
        for row in range(5)
    )
    ids = tuple(f"edge-{row}" for row in range(4))
    case = type(base)(
        name="invalid-states",
        calls=calls,
        variants=variants,
        selection=validate_training_selection(ids, (0, 1, 2, 3), held_out_ids=(), excluded_ids=()),
        window_variants=None,
        window_bp=None,
        chunk_size=2,
        tile_size=2,
    )

    manifest_path = _write_and_run(tmp_path, case, "invalid-states", 2, 2)
    reference = json.loads((manifest_path.parent / "reference.json").read_text())
    statuses = [item["status"] for item in reference["pairs"]]

    assert "insufficient_observations" in statuses
    assert "zero_variance" in statuses
    assert "observed" in statuses
    assert json.loads(manifest_path.read_text())["validation"]["gpu"]["passed"] is True


@requires_gpu
def test_actual_gpu_meets_all_near_fixed_precision_controls(tmp_path: Path) -> None:
    """Catch regression of either sample size, overlap state, or double-flip invariance."""
    case = build_synthetic_case("precision", seed=42)
    manifest_path = _write_and_run(tmp_path, case, "precision", 3, 3)
    gpu = pd.read_csv(manifest_path.parent / "gpu.tsv", sep="\t", keep_default_na=False)
    expected = {
        (3072, False): -0.0004605808764446619,
        (3072, True): 0.706991645342556,
        (4096, False): -0.0003453934724429183,
        (4096, True): 0.7070204380906536,
    }

    for n, overlap, _flipped, left, right in case.precision_controls:
        gidx_left = case.variants[left].gidx
        gidx_right = case.variants[right].gidx
        row = gpu[(gpu["gidx_a"] == gidx_left) & (gpu["gidx_b"] == gidx_right)].iloc[0]
        assert int(row["N_OBS"]) == n
        assert float(row["R"]) == pytest.approx(expected[(n, overlap)], abs=1e-5)
        assert float(row["R2"]) == pytest.approx(expected[(n, overlap)] ** 2, abs=2e-5)


@requires_gpu
def test_actual_gpu_held_out_mutation_changes_only_full_source_identity(tmp_path: Path) -> None:
    """Catch held-out calls leaking into selected bytes, counts, moments, or CuGen outputs."""
    baseline = build_synthetic_case("hand", seed=42)
    mutated = mutate_held_out(baseline)
    baseline_manifest = json.loads(
        _write_and_run(tmp_path, baseline, "baseline", 3, 3).read_text(encoding="utf-8")
    )
    mutated_manifest = json.loads(
        _write_and_run(tmp_path, mutated, "mutated", 3, 3).read_text(encoding="utf-8")
    )

    assert baseline_manifest["files"]["source.cugen"] != mutated_manifest["files"]["source.cugen"]
    for name in ("training.cugen", "reference.json", "cpu.tsv", "gpu.tsv", "validation.json"):
        assert baseline_manifest["files"][name] == mutated_manifest["files"][name]
