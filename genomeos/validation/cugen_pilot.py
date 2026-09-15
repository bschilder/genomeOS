"""Pinned public CuGen pilot orchestration (CuGen pilot design §7; Atlas §§4-5).

This offline adapter snapshots a bounded synthetic source, calls explicit CuGen public paths,
and completes an immutable artifact only after independent subset and numeric reconciliation.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
import subprocess
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Literal, Protocol

import numpy as np
import pandas as pd

from genomeos.validation.cugen_artifact import verify_cugen_pilot, write_completed_cugen_artifact
from genomeos.validation.cugen_backend import load_verified_cugen_api
from genomeos.validation.cugen_format import decode_cugen_bytes, estimate_ld_workspace
from genomeos.validation.ld_comparison import reconcile_ld_output
from genomeos.validation.ld_contract import (
    TrainingSelection,
    validate_ld_variants,
    validate_training_selection,
)
from genomeos.validation.ld_reference import reference_ld, requested_pairs, variant_moments

_MAX_SOURCE_BYTES = 67_072
_REVISION = re.compile(r"[0-9a-fA-F]{40}")
_PACKAGE_ROOT = Path(__file__).resolve().parents[2]
_GENOMEOS_SOURCES = (
    "genomeos/validation/cugen_pilot.py",
    "genomeos/validation/cugen_artifact.py",
    "genomeos/validation/cugen_backend.py",
    "genomeos/validation/cugen_format.py",
    "genomeos/validation/cugen_source.json",
    "genomeos/validation/ld_comparison.py",
    "genomeos/validation/ld_contract.py",
    "genomeos/validation/ld_reference.py",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _bounded_source(path: Path) -> bytes:
    source = Path(path)
    metadata = source.lstat()
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise ValueError("source must be a regular non-symlink file")
    if metadata.st_size > _MAX_SOURCE_BYTES:
        raise ValueError(f"source exceeds the {_MAX_SOURCE_BYTES}-byte pilot maximum")
    with source.open("rb") as stream:
        content = stream.read(_MAX_SOURCE_BYTES + 1)
        observed = os.fstat(stream.fileno())
    if len(content) > _MAX_SOURCE_BYTES:
        raise ValueError(f"source exceeds the {_MAX_SOURCE_BYTES}-byte pilot maximum")
    if not content or len(content) != metadata.st_size or observed.st_size != metadata.st_size:
        raise ValueError("source was truncated or changed during bounded validation")
    return content


def _validate_selection(selection: object) -> TrainingSelection:
    if not isinstance(selection, TrainingSelection):
        raise TypeError("selection must be a TrainingSelection")
    validated = validate_training_selection(
        selection.sample_ids,
        selection.training_indices,
        held_out_ids=selection.held_out_ids,
        excluded_ids=selection.excluded_ids,
    )
    if validated != selection:
        raise ValueError("selection fields do not form one canonical complete partition")
    return validated


StageName = Literal[
    "input_validation",
    "source_snapshot",
    "cugen_import",
    "subset",
    "training_validation",
    "reference",
    "cpu_ld",
    "cpu_reconciliation",
    "gpu_ld",
    "gpu_reconciliation",
    "artifact_write",
    "artifact_verification",
]


class PilotStageObserver(Protocol):
    """Observe fixed pilot stage boundaries without controlling execution."""

    def __call__(self, stage: str, event: Literal["start", "end"]) -> None: ...


@contextmanager
def _observed_stage(observer: PilotStageObserver | None, stage: StageName) -> Iterator[None]:
    if observer is not None:
        observer(stage, "start")
    yield
    if observer is not None:
        observer(stage, "end")


def _genomeos_source_provenance(source_revision: str | None) -> dict[str, Any]:
    if source_revision is None:
        try:
            completed = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=_PACKAGE_ROOT,
                capture_output=True,
                text=True,
                check=True,
            )
        except (OSError, subprocess.CalledProcessError) as error:
            raise ValueError("Git-observed source revision is unavailable") from error
        revision = completed.stdout.strip()
        provenance = "git_observed"
    else:
        revision = source_revision
        provenance = "supplied"
    if not isinstance(revision, str) or _REVISION.fullmatch(revision) is None:
        label = "source_revision" if source_revision is not None else "Git-observed source revision"
        raise ValueError(f"{label} must be a 40-character hexadecimal commit")
    imported_files: dict[str, str] = {}
    for relative in _GENOMEOS_SOURCES:
        actual = (_PACKAGE_ROOT / relative).resolve()
        if actual != _PACKAGE_ROOT / relative or not actual.is_file() or actual.is_symlink():
            raise ValueError(f"genomeOS source {relative} resolved outside the package checkout")
        imported_files[relative] = _sha256(actual)
    return {
        "revision": revision.lower(),
        "provenance": provenance,
        "imported_files": imported_files,
    }


def _public_calls(
    *, window_variants: int | None, window_kb: float | None, chunk_size: int, tile_size: int
) -> list[dict[str, Any]]:
    common = {
        "stats": ["r", "r2"],
        "precision": "fp32",
        "sign_reference": "alt",
        "missing": "pairwise",
        "min_obs": 2,
        "maf_min": 0,
        "min_r2": 0,
        "output": None,
        "output_format": "pairs",
        "tile_size": tile_size,
        "max_pairs": 2016,
        "verbose": False,
        "window": window_variants,
        "window_kb": window_kb,
        "annotation": "supplied_variant_identity",
    }
    return [
        {
            "path": "cugen.subset_cugen_file",
            "arguments": {"use_pinned": False, "chunk_size": chunk_size, "verbose": False},
        },
        {"path": "cugen.ld_matrix", "arguments": {**common, "backend": "numpy"}},
        {"path": "cugen.ld_matrix", "arguments": {**common, "backend": "gpu"}},
    ]


def _failure(out: Path, stage: str, error: BaseException) -> None:
    path = out / "failure.json"
    if path.exists():
        return
    content = {
        "schema_version": 1,
        "status": "failed",
        "stage": stage,
        "error_type": type(error).__name__,
        "message": str(error),
    }
    with path.open("x", encoding="utf-8") as stream:
        json.dump(content, stream, sort_keys=True, separators=(",", ":"))
        stream.write("\n")


def run_cugen_pilot(
    source: Path,
    *,
    variants: object,
    selection: TrainingSelection,
    genome_build: object,
    ploidy: object,
    evidence_kind: str,
    data_version: str,
    cugen_root: Path,
    window_variants: object,
    window_bp: object,
    chunk_size: int,
    tile_size: int,
    out: Path,
    source_revision: str | None = None,
    observer: PilotStageObserver | None = None,
) -> Path:
    """Run the bounded public CuGen comparison and return a completed manifest path."""
    output = Path(out)
    if os.path.lexists(output):
        raise FileExistsError("output path already exists")
    source_path = Path(source)
    if output.resolve(strict=False) == source_path.resolve(strict=False):
        raise ValueError("source and output paths must not collide")
    output.mkdir()
    stage: StageName = "input_validation"
    started = time.perf_counter()
    try:
        with _observed_stage(observer, stage):
            if evidence_kind != "synthetic_fixture":
                raise ValueError("evidence_kind must be explicitly 'synthetic_fixture'")
            if (
                not isinstance(data_version, str)
                or not data_version
                or data_version != data_version.strip()
            ):
                raise ValueError("data_version must be a nonempty whitespace-trimmed string")
            block = validate_ld_variants(variants, genome_build=genome_build, ploidy=ploidy)
            chosen = _validate_selection(selection)
            content = _bounded_source(source_path)
            decoded_source = decode_cugen_bytes(
                content, block, expected_samples=len(chosen.sample_ids)
            )
            plan = requested_pairs(block, window_variants=window_variants, window_bp=window_bp)
            if not plan:
                raise ValueError("no_requested_pairs")
            normalized_window_variants = None if window_variants is None else int(window_variants)
            normalized_window_bp = None if window_bp is None else int(window_bp)
            workspace = estimate_ld_workspace(
                source_variants=len(block),
                source_samples=len(chosen.sample_ids),
                training_samples=len(chosen.training_ids),
                requested_pair_count=len(plan),
                chunk_size=chunk_size,
                tile_size=tile_size,
            )
            normalized_chunk_size = int(chunk_size)
            normalized_tile_size = int(tile_size)
            genomeos_source = _genomeos_source_provenance(source_revision)

        stage = "source_snapshot"
        with _observed_stage(observer, stage):
            with (output / "source.cugen").open("xb") as stream:
                stream.write(content)

        stage = "cugen_import"
        with _observed_stage(observer, stage):
            cugen_api = load_verified_cugen_api(Path(cugen_root))

        stage = "subset"
        with _observed_stage(observer, stage):
            subset_seconds = cugen_api.subset_cugen_file(
                output / "source.cugen",
                output / "training.cugen",
                np.asarray(chosen.training_indices, dtype=np.int64),
                chunk_size=normalized_chunk_size,
                verbose=False,
                use_pinned=False,
            )
            if (
                isinstance(subset_seconds, bool)
                or not isinstance(subset_seconds, (int, float))
                or not math.isfinite(float(subset_seconds))
                or float(subset_seconds) < 0
            ):
                raise ValueError("subset_cugen_file must return a finite nonnegative wall time")

        stage = "training_validation"
        with _observed_stage(observer, stage):
            training_content = _bounded_source(output / "training.cugen")
            decoded_training = decode_cugen_bytes(
                training_content, block, expected_samples=len(chosen.training_ids)
            )
            expected_training = decoded_source.calls[
                np.asarray(chosen.training_indices, dtype=np.int64)
            ]
            if not np.array_equal(decoded_training.calls, expected_training):
                raise ValueError("CuGen subset calls disagree with the exact selected source calls")

        stage = "reference"
        with _observed_stage(observer, stage):
            moments = variant_moments(decoded_training.calls)
            reference = reference_ld(
                decoded_training.calls,
                block,
                genome_build=genome_build,
                ploidy=ploidy,
                window_variants=normalized_window_variants,
                window_bp=normalized_window_bp,
            )
            window_kb = None if normalized_window_bp is None else normalized_window_bp / 1000.0
            if normalized_window_bp is not None and round(window_kb * 1000) != normalized_window_bp:
                raise ValueError("window_bp cannot round-trip exactly through CuGen window_kb")
            annotation = pd.DataFrame(
                {
                    "gidx": [item.gidx for item in block],
                    "CHR": [item.chrom for item in block],
                    "POS": [item.position for item in block],
                    "ID": [item.variant_id for item in block],
                }
            )
            common = {
                "annotation": annotation,
                "window": normalized_window_variants,
                "window_kb": window_kb,
                "stats": ("r", "r2"),
                "precision": "fp32",
                "sign_reference": "alt",
                "missing": "pairwise",
                "min_obs": 2,
                "maf_min": 0,
                "min_r2": 0,
                "output": None,
                "output_format": "pairs",
                "tile_size": normalized_tile_size,
                "max_pairs": 2016,
                "verbose": False,
            }

        stage = "cpu_ld"
        with _observed_stage(observer, stage):
            cpu_started = time.perf_counter()
            cpu = cugen_api.ld_matrix(output / "training.cugen", backend="numpy", **common)
            cpu_seconds = time.perf_counter() - cpu_started

        stage = "cpu_reconciliation"
        with _observed_stage(observer, stage):
            cpu_validation = reconcile_ld_output(reference, block, moments, cpu)

        stage = "gpu_ld"
        with _observed_stage(observer, stage):
            gpu_started = time.perf_counter()
            gpu = cugen_api.ld_matrix(output / "training.cugen", backend="gpu", **common)
            gpu_seconds = time.perf_counter() - gpu_started

        stage = "gpu_reconciliation"
        with _observed_stage(observer, stage):
            gpu_validation = reconcile_ld_output(reference, block, moments, gpu)

        stage = "artifact_write"
        with _observed_stage(observer, stage):
            calls = _public_calls(
                window_variants=normalized_window_variants,
                window_kb=window_kb,
                chunk_size=normalized_chunk_size,
                tile_size=normalized_tile_size,
            )
            sources = {
                "cugen": {
                    "repository": cugen_api.repository,
                    "revision": cugen_api.revision,
                    "allowlist_files": dict(cugen_api.allowlist_files),
                    "imported_files": dict(cugen_api.imported_files),
                },
                "genomeos": genomeos_source,
            }
            runtime = {
                "schema_version": 1,
                "subset_seconds": float(subset_seconds),
                "cpu_ld_seconds": cpu_seconds,
                "gpu_ld_seconds": gpu_seconds,
                "pre_artifact_wall_seconds": time.perf_counter() - started,
                "ld_timing_scope": "unsynchronized_public_call_wall_intervals",
                "pre_artifact_timing_scope": (
                    "ends_before_artifact_serialization_and_completed_reader_verification"
                ),
            }
            manifest_path = write_completed_cugen_artifact(
                output,
                variants=block,
                selection=chosen,
                genome_build=str(genome_build),
                ploidy=str(ploidy),
                data_version=data_version,
                window_variants=normalized_window_variants,
                window_bp=normalized_window_bp,
                chunk_size=normalized_chunk_size,
                tile_size=normalized_tile_size,
                workspace=workspace,
                moments=moments,
                reference=reference,
                cpu=cpu,
                gpu=gpu,
                cpu_validation=cpu_validation,
                gpu_validation=gpu_validation,
                sources=sources,
                execution={"requested": calls, "executed": calls},
                runtime=runtime,
            )

        stage = "artifact_verification"
        with _observed_stage(observer, stage):
            verify_cugen_pilot(output)
        return manifest_path
    except Exception as error:
        manifest_path = output / "manifest.json"
        if manifest_path.exists():
            manifest_path.unlink()
        _failure(output, stage, error)
        raise
