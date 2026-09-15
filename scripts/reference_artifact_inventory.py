"""Validate exact artifact layouts and ledgers (acquisition design §6.2)."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import fields, is_dataclass
from itertools import zip_longest
from pathlib import Path

from genomeos.validation.reference_acquisition_types import (
    AcquisitionManifest,
    ArtifactRef,
)
from genomeos.validation.reference_preparation_types import PreparationManifest
from scripts.reference_artifact_io import (
    artifact_path,
    checked_ref,
    iter_tsv,
    nullable,
    require,
)
from scripts.reference_cohort_artifacts import COHORT_PATHS


def header_failure_reason(error: ValueError) -> str:
    message = str(error)
    if "sample" in message:
        return "sample_mismatch"
    if message == "artifact identity mismatch":
        return "artifact_mismatch"
    return (
        message
        if message in {"header_invalid", "limit_exceeded", "artifact_mismatch"}
        else "header_invalid"
    )


def record_failure_reason(error: ValueError) -> str:
    message = str(error)
    allowed = {
        "record_invalid",
        "native_encoding_refused",
        "native_mismatch",
        "limit_exceeded",
        "timeout",
        "artifact_mismatch",
        "coverage_gap",
    }
    return message if message in allowed else "record_invalid"


def _nested_refs(
    value: object,
    *,
    trail: tuple[str, ...] = (),
) -> Iterator[tuple[tuple[str, ...], ArtifactRef]]:
    if type(value) is ArtifactRef:
        yield trail, value
    elif is_dataclass(value) and not isinstance(value, type):
        for field in fields(value):
            if field.name != "files":
                yield from _nested_refs(getattr(value, field.name), trail=(*trail, field.name))
    elif isinstance(value, tuple):
        for index, item in enumerate(value):
            yield from _nested_refs(item, trail=(*trail, str(index)))


def _nested_inventory(manifest: object) -> dict[str, ArtifactRef]:
    nested: dict[str, ArtifactRef] = {}
    for trail, reference in _nested_refs(manifest):
        external = (
            "native_control" in trail
            and trail[-1:] == ("input_bcf",)
            and reference.path.startswith("@acquisition/")
        )
        if external:
            continue
        previous = nested.setdefault(reference.path, reference)
        require(previous == reference, "one artifact path has conflicting identities")
    return nested


def acquisition_inventory_paths(manifest: AcquisitionManifest) -> set[str]:
    """Return every canonical local path allowed in one acquisition inventory."""
    return {
        *_nested_inventory(manifest),
        *COHORT_PATHS.values(),
        "windows.tsv",
    }


def preparation_inventory_paths(manifest: PreparationManifest) -> set[str]:
    """Return every canonical local path allowed in one preparation inventory."""
    paths = {
        *_nested_inventory(manifest),
        *COHORT_PATHS.values(),
        "inputs.json",
        "native-controls.tsv",
        "qc-dispositions.tsv",
        "variant-windows.tsv",
        "windows.tsv",
        "technical_qc_4117.dependencies.json",
        "paper_ancestry_exclusion_4094.dependencies.json",
    }
    if not manifest.complete:
        paths.update(
            f"work/variant-windows/{index:03d}-{window.window_id}.part"
            for index, window in enumerate(manifest.windows)
            if window.raw_records is not None
        )
        paths.update(
            f"work/{stage}.{kind}/{window.window_id}.part"
            for window in manifest.windows
            if window.state != "refused" and window.retained_variants
            for stage in ("technical_qc_4117", "paper_ancestry_exclusion_4094")
            for kind in ("called", "quality")
        )
    return paths


def validate_inventory(
    root: Path,
    manifest: AcquisitionManifest | PreparationManifest,
    final_name: str,
    *,
    allowed_paths: set[str],
    sparse: set[str] | None = None,
    caps: dict[str, int] | None = None,
) -> None:
    """Validate hashes, paths, role bounds, and the exact canonical tree."""
    inventory = {reference.path: reference for reference in manifest.files}
    require(len(inventory) == len(manifest.files), "duplicate artifact inventory path")
    nested = _nested_inventory(manifest)
    require(set(nested) <= set(inventory), "nested artifact is absent from file inventory")
    require(
        all(inventory[path] == reference for path, reference in nested.items()),
        "nested artifact identity differs from file inventory",
    )
    require(set(inventory) == allowed_paths, "artifact inventory contains a noncanonical path")
    limits = caps or {}
    for reference in manifest.files:
        if reference.path in limits:
            require(
                reference.size_bytes <= limits[reference.path]
                and artifact_path(root, reference.path).stat().st_size <= limits[reference.path],
                "artifact exceeds its role-specific bound",
            )
        checked_ref(root, reference)

    exempt = {final_name, *(sparse or set())}
    actual: set[str] = set()
    for candidate in root.rglob("*"):
        require(not candidate.is_symlink(), "artifact tree contains a symlink")
        if candidate.is_file():
            actual.add(candidate.relative_to(root).as_posix())
    require(actual - exempt == set(inventory), "artifact file inventory mismatch")


def check_tsv(
    path: Path,
    columns: tuple[str, ...],
    expected: tuple[tuple[str, ...], ...],
    *,
    limit: int = 16_777_216,
) -> None:
    require(path.stat().st_size <= limit, "ledger exceeds its bound")
    for actual, planned in zip_longest(iter_tsv(path, columns), expected):
        require(actual == planned, "ledger differs from manifest")


def windows_rows(
    windows: tuple[object, ...],
    *,
    preparation: bool,
) -> tuple[tuple[str, ...], ...]:
    result = []
    last = "retained_variants" if preparation else "native_records"
    for value in windows:
        result.append(
            (
                value.window_id,
                value.chrom,
                value.state,
                nullable(value.reason),
                nullable(value.raw_records),
                nullable(getattr(value, last)),
            )
        )
    return tuple(result)
