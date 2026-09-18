"""Write and validate immutable reference artifacts (reference acquisition design §6.2)."""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Iterator
from dataclasses import fields, is_dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from genomeos.validation.reference_acquisition_codec import decode_acquisition, encode_acquisition
from genomeos.validation.reference_acquisition_types import (
    AcquisitionManifest,
    ArtifactRef,
    RetainedIndex,
    ReviewReceipt,
)
from genomeos.validation.reference_byte_plan import BytePreflight, encode_preflight
from genomeos.validation.reference_counts import ReferenceCount, validate_reference_counts
from genomeos.validation.reference_preflight_input import decode_reviewed_preflight
from genomeos.validation.reference_preparation_codec import (
    decode_dependency,
    decode_preparation,
    decode_preparation_inputs,
    encode_preparation,
)
from genomeos.validation.reference_preparation_types import PreparationManifest
from genomeos.validation.reference_window_manifest import decode_manifest
from scripts.reference_io_common import validate_verified_source

_ACQUISITION_COLUMNS = (
    "window_id", "chrom", "state", "reason", "raw_records", "native_records",
)
_PREPARATION_COLUMNS = (
    "window_id", "chrom", "state", "reason", "raw_records", "retained_variants",
)
_COUNT_COLUMNS = (
    "record_id", "variant_id", "group_id", "region_id", "variant_group", "ac", "an",
)
_VARIANT_WINDOW_COLUMNS = (
    "variant_id", "window_id", "chrom", "start0", "end0", "source_uri", "source_generation",
)
_QC_COLUMNS = ("window_id", "stage", "category", "key", "origin", "count")
_NATIVE_COLUMNS = (
    "window_id", "stage", "state", "variants", "native_ac_an_matches", "native_interpreted_calls",
)
_COHORT_PATHS = {
    "metadata": "inputs/cohort/metadata.tsv",
    "outliers": "inputs/cohort/outliers.txt",
    "exclusions": "inputs/cohort/exclusions.json",
    "technical_samples": "inputs/cohort/technical.samples.txt",
    "paper_samples": "inputs/cohort/paper.samples.txt",
    "dependency_audit": "inputs/cohort/dependency-audit.json",
}
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _root(directory: Path) -> Path:
    _require(isinstance(directory, Path) and directory.is_dir() and not directory.is_symlink(),
             "invalid artifact root")
    return directory.resolve(strict=True)


def _path(root: Path, relative: str) -> Path:
    path = PurePosixPath(relative)
    _require(
        isinstance(relative, str)
        and bool(relative)
        and not path.is_absolute()
        and "\\" not in relative
        and all(part not in ("", ".", "..") for part in path.parts)
        and str(path) == relative,
        "invalid artifact path",
    )
    candidate = root / relative
    cursor = root
    for part in path.parts:
        cursor /= part
        _require(not cursor.is_symlink(), "artifact path contains a symlink")
    _require(candidate.is_file() and candidate.resolve(strict=True).is_relative_to(root),
             "artifact is unavailable")
    return candidate


def _identity(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(1_048_576):
            size += len(chunk)
            digest.update(chunk)
    return size, digest.hexdigest()


def _check_ref(root: Path, reference: ArtifactRef) -> Path:
    path = _path(root, reference.path)
    _require(_identity(path) == (reference.size_bytes, reference.sha256), "artifact identity mismatch")
    return path


def _check_cohort_files(root: Path, hashes: object) -> None:
    for field, relative in _COHORT_PATHS.items():
        path = _path(root, relative)
        _require(_identity(path)[1] == getattr(hashes, field), f"cohort {field} hash mismatch")


def _check_source_hashes(provenance: object) -> None:
    checkout = Path(__file__).resolve().parents[1]
    _require(bool(provenance.imported_source_sha256), "source hash evidence is empty")
    for relative, expected in provenance.imported_source_sha256:
        _require(
            _identity(_path(checkout, relative))[1] == expected,
            f"imported source hash mismatch: {relative}",
        )


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


def _inventory(root: Path, manifest: object, final_name: str, *, sparse: set[str] | None = None) -> None:
    inventory = {reference.path: reference for reference in manifest.files}
    _require(len(inventory) == len(manifest.files), "duplicate artifact inventory path")
    nested: dict[str, ArtifactRef] = {}
    for trail, reference in _nested_refs(manifest):
        external = "native_control" in trail and trail[-1:] == ("input_bcf",) and reference.path.startswith(
            "@acquisition/"
        )
        if external:
            continue
        previous = nested.setdefault(reference.path, reference)
        _require(previous == reference, "one artifact path has conflicting identities")
    _require(set(nested) <= set(inventory), "nested artifact is absent from file inventory")
    for reference in manifest.files:
        _check_ref(root, reference)

    exempt = {final_name, "runtime-attempts.jsonl", *(sparse or set())}
    actual: set[str] = set()
    for candidate in root.rglob("*"):
        _require(not candidate.is_symlink(), "artifact tree contains a symlink")
        if candidate.is_file():
            actual.add(candidate.relative_to(root).as_posix())
    _require(actual - exempt == set(inventory), "artifact file inventory mismatch")


def _tsv(path: Path, columns: tuple[str, ...]) -> tuple[tuple[str, ...], ...]:
    raw = path.read_bytes()
    _require(raw.endswith(b"\n") and b"\r" not in raw and b"\0" not in raw, "TSV must use LF")
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeDecodeError as error:
        raise ValueError("TSV must be UTF-8") from error
    _require(bool(lines) and tuple(lines[0].split("\t")) == columns, "TSV columns mismatch")
    rows = tuple(tuple(line.split("\t")) for line in lines[1:])
    _require(all(len(row) == len(columns) for row in rows), "TSV row width mismatch")
    return rows


def _natural(token: str, field: str) -> int:
    _require(re.fullmatch(r"0|[1-9][0-9]*", token) is not None, f"invalid {field}")
    return int(token)


def _nullable(value: object) -> str:
    return "NA" if value is None else str(value)


def _windows_rows(windows: tuple[object, ...], *, preparation: bool) -> tuple[tuple[str, ...], ...]:
    result = []
    last = "retained_variants" if preparation else "native_records"
    for value in windows:
        result.append(
            (
                value.window_id,
                value.chrom,
                value.state,
                _nullable(value.reason),
                _nullable(value.raw_records),
                _nullable(getattr(value, last)),
            )
        )
    return tuple(result)


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        _require(key not in result, f"duplicate review key: {key}")
        result[key] = value
    return result


def _decode_review(raw: bytes) -> ReviewReceipt:
    try:
        value = json.loads(raw.decode(), object_pairs_hook=_unique_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("invalid review JSON") from error
    keys = {
        "schema_version", "manifest_sha256", "preflight_sha256", "implementation_revision",
        "implementation_sha256", "review_locator", "review_sha256", "status",
    }
    _require(type(value) is dict and set(value) == keys, "invalid review fields")
    hashes = value["implementation_sha256"]
    _require(type(hashes) is dict, "invalid review implementation hashes")
    review = ReviewReceipt(
        value["schema_version"], value["manifest_sha256"], value["preflight_sha256"],
        value["implementation_revision"], tuple(sorted(hashes.items())), value["review_locator"],
        value["review_sha256"], value["status"],
    )
    canonical = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
    _require(canonical == raw, "review JSON bytes are not canonical")
    return review


def _validate_acquisition_inputs(
    root: Path,
    manifest: AcquisitionManifest,
    expected_preflight: BytePreflight | None,
) -> BytePreflight:
    _check_source_hashes(manifest.provenance)
    _require(
        (
            manifest.inputs.window_manifest.path,
            manifest.inputs.windows.path,
            manifest.inputs.preflight.path,
            manifest.inputs.review.path,
        )
        == (
            "inputs/window-manifest.json",
            "inputs/windows.tsv",
            "inputs/preflight.json",
            "inputs/review.json",
        ),
        "acquisition input paths differ from the fixed layout",
    )
    _check_cohort_files(root, manifest.inputs.cohort)
    windows_raw = _check_ref(root, manifest.inputs.windows).read_bytes()
    window_manifest_raw = _check_ref(root, manifest.inputs.window_manifest).read_bytes()
    window_manifest = decode_manifest(window_manifest_raw, windows_bytes=windows_raw)
    preflight_raw = _check_ref(root, manifest.inputs.preflight).read_bytes()
    review = _decode_review(_check_ref(root, manifest.inputs.review).read_bytes())
    retained = tuple(
        RetainedIndex(source.source.chrom, _check_ref(root, source.retained_index).read_bytes())
        for source in manifest.sources
    )
    preflight = decode_reviewed_preflight(
        preflight_raw,
        manifest=window_manifest,
        manifest_raw=window_manifest_raw,
        indexes=retained,
        review=review,
    )
    if expected_preflight is not None:
        _require(encode_preflight(preflight) == encode_preflight(expected_preflight),
                 "preflight input differs from reviewed value")
    _require(tuple(value.source for value in manifest.sources)
             == tuple(value.source for value in preflight.sources), "acquisition source identity mismatch")
    _require(
        tuple(value.window_id for value in manifest.windows)
        == tuple(value.window_id for value in window_manifest.windows),
        "acquisition window identity mismatch",
    )
    return preflight


def _validate_acquisition_content(
    root: Path,
    manifest: AcquisitionManifest,
    expected_preflight: BytePreflight | None = None,
) -> None:
    preflight = _validate_acquisition_inputs(root, manifest, expected_preflight)
    plans = {value.source.chrom: value for value in preflight.sources}
    sparse = {
        source.verified.sparse_path
        for source in manifest.sources
        if source.verified is not None
    }
    _inventory(root, manifest, "acquisition.json", sparse=sparse)
    _require(
        _tsv(_path(root, "windows.tsv"), _ACQUISITION_COLUMNS)
        == _windows_rows(manifest.windows, preparation=False),
        "acquisition windows ledger mismatch",
    )
    for source in manifest.sources:
        plan = plans[source.source.chrom]
        planned = tuple((value.first, value.last) for value in plan.merged_vcf_ranges)
        _require(tuple((value.first, value.last) for value in source.ranges) == planned,
                 "range receipt accounting mismatch")
        if source.verified is not None:
            validate_verified_source(source.verified, plan, artifact_root=root)
    totals = manifest.totals
    _require(totals.planned_bytes_including_indexes == preflight.total_planned_bytes,
             "planned byte total mismatch")
    _require(
        totals.retained_index_bytes == sum(value.retained_index.size_bytes for value in manifest.sources),
        "retained index byte total mismatch",
    )
    _require(
        totals.inherited_index_received_bytes
        == sum(value.receipt.received_bytes for value in preflight.sources),
        "inherited index byte total mismatch",
    )
    ranges = tuple(value for source in manifest.sources for value in source.ranges)
    _require(totals.vcf_requested_bytes == sum(value.requested_bytes for value in ranges),
             "VCF requested byte total mismatch")
    _require(totals.vcf_received_bytes == sum(value.received_bytes for value in ranges),
             "VCF received byte total mismatch")
    _require(totals.range_adapter_invocations == sum(value.adapter_invocations for value in ranges),
             "range invocation total mismatch")
    _require(totals.metadata_adapter_invocations
             == sum(value.metadata.adapter_invocations for value in manifest.sources),
             "metadata invocation total mismatch")
    _require(totals.metadata_stdout_bytes == sum(value.metadata.stdout_bytes for value in manifest.sources),
             "metadata stdout total mismatch")
    for window in manifest.windows:
        if window.state == "refused":
            continue
        raw = _check_ref(root, window.raw).read_bytes()
        raw_lines = raw.splitlines(keepends=True)
        _require(all(line.endswith(b"\n") for line in raw_lines), "original records must use LF")
        offsets = _tsv(_check_ref(root, window.offsets), ("ordinal", "source_virtual_offset", "raw_sha256"))
        _require(len(raw_lines) == len(offsets) == window.raw_records, "original record count mismatch")
        for ordinal, (line, offset) in enumerate(zip(raw_lines, offsets, strict=True)):
            _require(_natural(offset[0], "record ordinal") == ordinal, "record ordinals are not contiguous")
            _natural(offset[1], "source virtual offset")
            _require(_DIGEST.fullmatch(offset[2]) is not None
                     and hashlib.sha256(line).hexdigest() == offset[2], "original record hash mismatch")
        native_keys = _check_ref(root, window.native_keys).read_bytes()
        _require(b"\r" not in native_keys and native_keys.count(b"\n") == window.native_records,
                 "native key count mismatch")
        original_keys = []
        for line in raw_lines:
            columns = line[:-1].split(b"\t")
            _require(len(columns) >= 7, "original VCF record is malformed")
            original_keys.append(b"\t".join((columns[0], columns[1], columns[3], columns[4], columns[6])))
        _require(native_keys.splitlines() == original_keys, "native/original variant keys differ")
        _require(
            tuple(run.operation for run in window.native_runs) == ("extract_bcf", "query_keys"),
            "successful window lacks exact native controls",
        )


def _count_rows(path: Path) -> tuple[ReferenceCount, ...]:
    rows = []
    for value in _tsv(path, _COUNT_COLUMNS):
        rows.append(ReferenceCount(*value[:5], _natural(value[5], "AC"), _natural(value[6], "AN")))
    result = tuple(rows)
    if result:
        validate_reference_counts(result)
        for row in result:
            expected_id = json.dumps([row.group_id, row.variant_id], separators=(",", ":"))
            _require(row.record_id == expected_id, "count record_id is not canonical")
            _require(
                re.fullmatch(
                    r"GRCh38:chr(?:[1-9]|1[0-9]|2[0-2]):[1-9][0-9]*:[^:]+:[^:]+",
                    row.variant_id,
                )
                is not None,
                "invalid count variant identity",
            )
        _require(
            tuple(value.record_id for value in result)
            == tuple(sorted(value.record_id for value in result)),
            "count rows must be sorted by record_id",
        )
    return result


def _expected_qc_rows(manifest: PreparationManifest) -> tuple[tuple[str, ...], ...]:
    rows = []
    for window in manifest.windows:
        for stage in window.stages:
            if stage.summary is None:
                continue
            rows.extend(
                (window.window_id, stage.stage, "disposition", key, "NA", str(count))
                for key, count in stage.summary.qc.dispositions
            )
            rows.extend(
                (window.window_id, stage.stage, "inspection", key, "NA", str(count))
                for key, count in stage.summary.qc.inspection_totals
            )
            rows.extend(
                (window.window_id, stage.stage, "missing_origin", value.field, value.origin, str(value.count))
                for value in stage.summary.qc.missing_origins
            )
    return tuple(rows)


def _expected_native_rows(manifest: PreparationManifest) -> tuple[tuple[str, ...], ...]:
    rows = []
    for window in manifest.windows:
        for stage in window.stages:
            summary = stage.summary
            rows.append(
                (
                    window.window_id,
                    stage.stage,
                    stage.state,
                    _nullable(None if summary is None else summary.variants),
                    _nullable(None if summary is None else summary.native_ac_an_matches),
                    _nullable(None if summary is None else summary.native_interpreted_calls),
                )
            )
    return tuple(rows)


def _variant_windows(root: Path) -> dict[str, tuple[str, str, int, int, str, str]]:
    result = {}
    for value in _tsv(_path(root, "variant-windows.tsv"), _VARIANT_WINDOW_COLUMNS):
        variant_id, window_id, chrom, start0, end0, uri, generation = value
        _require(variant_id not in result, "duplicate variant-window assignment")
        start, end = _natural(start0, "window start0"), _natural(end0, "window end0")
        _require(start < end and variant_id.startswith(f"GRCh38:{chrom}:"), "invalid variant-window row")
        result[variant_id] = (window_id, chrom, start, end, uri, generation)
    return result


def _validate_preparation_content(
    root: Path,
    manifest: PreparationManifest,
    acquisition_root: Path,
) -> None:
    _check_source_hashes(manifest.provenance)
    acquisition = validate_acquisition(acquisition_root)
    parent_raw = _path(_root(acquisition_root), "acquisition.json").read_bytes()
    copied = _check_ref(root, manifest.inputs.acquisition).read_bytes()
    _require(copied == parent_raw, "copied acquisition manifest differs from acquisition root")
    _require(manifest.inputs.acquisition.sha256 == hashlib.sha256(parent_raw).hexdigest(),
             "preparation acquisition hash mismatch")
    _require(
        manifest.inputs.acquisition.path == "inputs/acquisition.json"
        and manifest.inputs.dependency_audit.path == _COHORT_PATHS["dependency_audit"],
        "preparation input paths differ from the fixed layout",
    )
    _check_cohort_files(root, manifest.inputs.cohort)
    _require(manifest.inputs.dependency_audit.sha256 == manifest.inputs.cohort.dependency_audit,
             "preparation dependency-audit identity mismatch")
    _inventory(root, manifest, "manifest.json")
    _require(decode_preparation_inputs(_path(root, "inputs.json").read_bytes()) == manifest.inputs,
             "preparation inputs sidecar mismatch")
    _require(
        _tsv(_path(root, "windows.tsv"), _PREPARATION_COLUMNS)
        == _windows_rows(manifest.windows, preparation=True),
        "preparation windows ledger mismatch",
    )
    _require(_tsv(_path(root, "qc-dispositions.tsv"), _QC_COLUMNS) == _expected_qc_rows(manifest),
             "QC dispositions ledger mismatch")
    _require(_tsv(_path(root, "native-controls.tsv"), _NATIVE_COLUMNS) == _expected_native_rows(manifest),
             "native controls ledger mismatch")
    if manifest.complete:
        _require(acquisition.complete, "complete preparation requires complete acquisition")
        acquisition_windows = {value.window_id: value for value in acquisition.windows}
        frozen = decode_manifest(
            _path(_root(acquisition_root), "inputs/window-manifest.json").read_bytes(),
            windows_bytes=_path(_root(acquisition_root), "inputs/windows.tsv").read_bytes(),
        )
        frozen_windows = {value.window_id: value for value in frozen.windows}
        sources = {value.source.chrom: value.source for value in acquisition.sources}
        for window in manifest.windows:
            parent = acquisition_windows[window.window_id]
            _require(
                window.raw_records == parent.raw_records,
                "preparation raw count differs from acquisition",
            )
        tables = tuple(_count_rows(_check_ref(root, track.table)) for track in manifest.tracks)
        keysets = tuple({row.record_id for row in table} for table in tables)
        _require(not keysets or all(keys == keysets[0] for keys in keysets), "four track keys differ")
        assignments = _variant_windows(root)
        _require(set(assignments) == {row.variant_id for row in tables[0]} if tables else not assignments,
                 "variant-window key mismatch")
        assigned_counts: dict[str, int] = {}
        for variant_id, assignment in assignments.items():
            window_id, chrom, start, end, uri, generation = assignment
            frozen_window = frozen_windows.get(window_id)
            source = sources.get(chrom)
            match = re.fullmatch(r"GRCh38:chr(?:[1-9]|1[0-9]|2[0-2]):([1-9][0-9]*):[^:]+:[^:]+", variant_id)
            _require(
                frozen_window is not None
                and source is not None
                and (chrom, start, end)
                == (frozen_window.chrom, frozen_window.start0, frozen_window.end0)
                and (uri, generation) == (source.vcf.uri, source.vcf.generation)
                and match is not None
                and start < int(match.group(1)) <= end,
                "variant-window assignment differs from frozen acquisition",
            )
            assigned_counts[window_id] = assigned_counts.get(window_id, 0) + 1
        _require(
            all(
                assigned_counts.get(window.window_id, 0) == window.retained_variants
                for window in manifest.windows
            ),
            "variant-window counts differ from preparation ledger",
        )
        table_by_track = {
            (track.stage, track.kind): table
            for track, table in zip(manifest.tracks, tables, strict=True)
        }
        for window in manifest.windows:
            variants = {
                variant_id
                for variant_id, assignment in assignments.items()
                if assignment[0] == window.window_id
            }
            for stage in window.stages:
                summary = stage.summary
                for kind in ("called", "quality"):
                    rows = tuple(
                        row for row in table_by_track[(stage.stage, kind)] if row.variant_id in variants
                    )
                    prefix = "called" if kind == "called" else "quality"
                    _require(
                        (
                            len(rows),
                            sum(row.an == 0 for row in rows),
                            sum(row.ac for row in rows),
                            sum(row.an for row in rows),
                        )
                        == (
                            summary.rows,
                            getattr(summary, f"{prefix}_unavailable"),
                            getattr(summary, f"{prefix}_ac_sum"),
                            getattr(summary, f"{prefix}_an_sum"),
                        ),
                        "count rows differ from stage-window summary",
                    )
        for track, table in zip(manifest.tracks, tables, strict=True):
            groups = {row.group_id for row in table}
            variants = {row.variant_id for row in table}
            _require(
                (track.rows, track.variants, track.represented_groups, track.unavailable_rows,
                 track.ac_sum, track.an_sum)
                == (len(table), len(variants), len(groups), sum(row.an == 0 for row in table),
                    sum(row.ac for row in table), sum(row.an for row in table)),
                "track summary mismatch",
            )
            dependency = decode_dependency(_check_ref(root, track.dependencies).read_bytes())
            _require(dependency.stage == track.stage, "dependency stage differs from count track")
            if manifest.status == "complete_nonempty":
                _require(set(dependency.populations) == groups,
                         "dependency populations differ from count track")
            else:
                _require(
                    len(dependency.populations) == 80
                    and dependency.reported_pairs in (1_302, 1_294)
                    and dependency.component_count == 77,
                    "empty preparation lacks the full dependency graph",
                )
            for row in table:
                window_id, chrom, start, end, _, _ = assignments[row.variant_id]
                _require(row.variant_group == f"GRCh38:{chrom}:{start + 1}-{end}",
                         "variant group differs from assigned window")
                _require(window_id.startswith(f"{chrom}-s"), "variant window identity mismatch")
        for track in manifest.tracks:
            summaries = tuple(
                stage.summary
                for window in manifest.windows
                for stage in window.stages
                if stage.stage == track.stage
            )
            unavailable_field = "called_unavailable" if track.kind == "called" else "quality_unavailable"
            ac_field = "called_ac_sum" if track.kind == "called" else "quality_ac_sum"
            an_field = "called_an_sum" if track.kind == "called" else "quality_an_sum"
            _require(
                (
                    track.rows,
                    track.variants,
                    track.unavailable_rows,
                    track.ac_sum,
                    track.an_sum,
                )
                == (
                    sum(value.rows for value in summaries),
                    sum(value.variants for value in summaries),
                    sum(getattr(value, unavailable_field) for value in summaries),
                    sum(getattr(value, ac_field) for value in summaries),
                    sum(getattr(value, an_field) for value in summaries),
                ),
                "track totals differ from stage-window summaries",
            )
        admitted_bcf = {
            value.native_bcf.path: value.native_bcf
            for value in acquisition.windows
            if value.native_bcf is not None
        }
        acquisition_root = _root(acquisition_root)
        for window in manifest.windows:
            for stage in window.stages:
                if stage.native_control is None:
                    continue
                parent = stage.native_control.input_bcf
                _require(parent.path.startswith("@acquisition/"), "native input lacks parent prefix")
                relative = parent.path.removeprefix("@acquisition/")
                expected = admitted_bcf.get(relative)
                _require(
                    expected is not None
                    and (parent.size_bytes, parent.sha256) == (expected.size_bytes, expected.sha256),
                    "native input differs from admitted acquisition BCF",
                )
                _check_ref(acquisition_root, expected)


def _write_exclusive(path: Path, raw: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(descriptor)
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def write_acquisition_manifest(
    directory: Path,
    manifest: AcquisitionManifest,
    *,
    preflight: BytePreflight,
) -> ArtifactRef:
    """Validate a complete phase tree and exclusively write acquisition.json last."""
    root = _root(directory)
    _require(type(manifest) is AcquisitionManifest and type(preflight) is BytePreflight,
             "invalid acquisition writer inputs")
    _require(not (root / "acquisition.json").exists(), "acquisition manifest already exists")
    _validate_acquisition_content(root, manifest, preflight)
    raw = encode_acquisition(manifest)
    _write_exclusive(root / "acquisition.json", raw)
    _require(validate_acquisition(root) == manifest, "written acquisition manifest failed readback")
    return ArtifactRef("acquisition.json", len(raw), hashlib.sha256(raw).hexdigest())


def validate_acquisition(directory: Path) -> AcquisitionManifest:
    """Deeply validate one acquisition root and return its typed final ledger."""
    root = _root(directory)
    manifest = decode_acquisition(_path(root, "acquisition.json").read_bytes())
    _validate_acquisition_content(root, manifest)
    return manifest


def write_preparation_manifest(
    directory: Path,
    manifest: PreparationManifest,
    *,
    acquisition_root: Path,
) -> ArtifactRef:
    """Validate a count tree and exclusively write manifest.json last."""
    root = _root(directory)
    _require(type(manifest) is PreparationManifest, "invalid preparation manifest")
    _require(not (root / "manifest.json").exists(), "preparation manifest already exists")
    _validate_preparation_content(root, manifest, acquisition_root)
    raw = encode_preparation(manifest)
    _write_exclusive(root / "manifest.json", raw)
    _require(validate_preparation(root, acquisition_root=acquisition_root) == manifest,
             "written preparation manifest failed readback")
    return ArtifactRef("manifest.json", len(raw), hashlib.sha256(raw).hexdigest())


def validate_preparation(directory: Path, *, acquisition_root: Path) -> PreparationManifest:
    """Deeply validate one preparation root and its external acquisition binding."""
    root = _root(directory)
    manifest = decode_preparation(_path(root, "manifest.json").read_bytes())
    _validate_preparation_content(root, manifest, acquisition_root)
    return manifest
