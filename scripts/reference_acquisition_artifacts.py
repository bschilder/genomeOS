"""Write and validate immutable acquisition artifacts (design §6.2)."""
from __future__ import annotations

import hashlib
from pathlib import Path

from genomeos.validation.reference_acquisition_codec import (
    decode_acquisition,
    decode_acquisition_review,
    encode_acquisition,
)
from genomeos.validation.reference_acquisition_types import (
    AcquisitionManifest,
    ArtifactRef,
    RetainedIndex,
)
from genomeos.validation.reference_byte_plan import BytePreflight, encode_preflight
from genomeos.validation.reference_cohorts import QualifiedCohortInputs
from genomeos.validation.reference_preflight_input import decode_reviewed_preflight
from genomeos.validation.reference_tbi import MAX_COMPRESSED_BYTES
from genomeos.validation.reference_vcf_tokens import HEADER_LIMIT_BYTES, parse_header
from genomeos.validation.reference_window_manifest import decode_manifest
from genomeos.validation.reference_window_types import WindowManifest
from scripts.reference_artifact_inventory import (
    acquisition_inventory_paths,
)
from scripts.reference_artifact_inventory import (
    check_tsv as _check_tsv,
)
from scripts.reference_artifact_inventory import (
    header_failure_reason as _header_failure_reason,
)
from scripts.reference_artifact_inventory import (
    record_failure_reason as _record_failure_reason,
)
from scripts.reference_artifact_inventory import (
    validate_inventory as _inventory,
)
from scripts.reference_artifact_inventory import (
    windows_rows as _windows_rows,
)
from scripts.reference_artifact_io import (
    artifact_path as _path,
)
from scripts.reference_artifact_io import (
    artifact_root as _root,
)
from scripts.reference_artifact_io import (
    read_bounded as _bounded_bytes,
)
from scripts.reference_artifact_io import (
    read_bounded_ref as _bounded_ref,
)
from scripts.reference_artifact_io import (
    require as _require,
)
from scripts.reference_artifact_io import (
    write_exclusive as _write_exclusive,
)
from scripts.reference_artifact_run_validation import (
    _check_acquisition_runs,
    _check_provenance,
)
from scripts.reference_cohort_artifacts import (
    COHORT_PATHS as _COHORT_PATHS,
)
from scripts.reference_cohort_artifacts import (
    qualify_cohort_files as _qualify_cohort_files,
)
from scripts.reference_io_common import fsync_artifact_tree, validate_verified_source
from scripts.reference_window_io import (
    iter_source_records,
    load_source_header,
    validate_metadata_receipt,
    validate_original_evidence,
    validate_original_records,
)

_ACQUISITION_COLUMNS = (
    "window_id", "chrom", "state", "reason", "raw_records", "native_records",
)
_MANIFEST_LIMIT = 16_777_216
_SIDECAR_LIMIT = 16_777_216

def _validate_acquisition_inputs(
    root: Path,
    manifest: AcquisitionManifest,
    expected_preflight: BytePreflight | None,
    cohort_inputs: QualifiedCohortInputs | None,
) -> tuple[BytePreflight, tuple[str, ...], WindowManifest]:
    _check_provenance(manifest.provenance, phase="acquisition")
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
    _, _, source_samples = _qualify_cohort_files(
        root, manifest.inputs.cohort, cohort_inputs
    )
    windows_raw = _bounded_ref(root, manifest.inputs.windows, _SIDECAR_LIMIT, "windows sidecar")
    window_manifest_raw = _bounded_ref(
        root, manifest.inputs.window_manifest, _MANIFEST_LIMIT, "window manifest"
    )
    window_manifest = decode_manifest(window_manifest_raw, windows_bytes=windows_raw)
    preflight_raw = _bounded_ref(root, manifest.inputs.preflight, _MANIFEST_LIMIT, "preflight")
    review = decode_acquisition_review(
        _bounded_ref(root, manifest.inputs.review, _MANIFEST_LIMIT, "acquisition review")
    )
    _require(
        review.implementation_revision == manifest.provenance.code_revision
        and review.implementation_sha256 == manifest.provenance.imported_source_sha256,
        "acquisition review differs from implementation provenance",
    )
    retained = tuple(
        RetainedIndex(
            source.source.chrom,
            _bounded_ref(
                root, source.retained_index, MAX_COMPRESSED_BYTES, "retained index"
            ),
        )
        for source in manifest.sources
    )
    preflight = decode_reviewed_preflight(
        preflight_raw,
        manifest=window_manifest,
        manifest_raw=window_manifest_raw,
        indexes=retained,
        review=review.preflight,
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
    return preflight, source_samples, window_manifest


def _validate_acquisition_content(
    root: Path,
    manifest: AcquisitionManifest,
    expected_preflight: BytePreflight | None = None,
    cohort_inputs: QualifiedCohortInputs | None = None,
) -> None:
    preflight, source_samples, window_manifest = _validate_acquisition_inputs(
        root, manifest, expected_preflight, cohort_inputs
    )
    plans = {value.source.chrom: value for value in preflight.sources}
    sparse = {
        source.verified.sparse_path
        for source in manifest.sources
        if source.verified is not None
    }
    acquisition_caps = {
        "windows.tsv": _SIDECAR_LIMIT,
        **{value: _SIDECAR_LIMIT for value in _COHORT_PATHS.values()},
        manifest.inputs.window_manifest.path: _MANIFEST_LIMIT,
        manifest.inputs.windows.path: _SIDECAR_LIMIT,
        manifest.inputs.preflight.path: _MANIFEST_LIMIT,
        manifest.inputs.review.path: _MANIFEST_LIMIT,
        **{
            source.header.header.path: HEADER_LIMIT_BYTES
            for source in manifest.sources
            if source.header is not None
        },
    }
    _inventory(
        root,
        manifest,
        "acquisition.json",
        allowed_paths=acquisition_inventory_paths(manifest),
        sparse=sparse,
        caps=acquisition_caps,
    )
    _check_tsv(
        _path(root, "windows.tsv"),
        _ACQUISITION_COLUMNS,
        _windows_rows(manifest.windows, preparation=False),
    )
    for source in manifest.sources:
        plan = plans[source.source.chrom]
        planned = tuple((value.first, value.last) for value in plan.merged_vcf_ranges)
        _require(tuple((value.first, value.last) for value in source.ranges) == planned,
                 "range receipt accounting mismatch")
        if source.verified is not None:
            validate_verified_source(source.verified, plan, artifact_root=root)
        if source.metadata.state != "not_attempted":
            validate_metadata_receipt(source.source.vcf, source.metadata, artifact_root=root)
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
    source_receipts = {value.source.chrom: value for value in manifest.sources}
    frozen_windows = {value.window_id: value for value in window_manifest.windows}
    headers = {}
    for source in manifest.sources:
        if source.verified is None:
            continue
        try:
            source_header_raw, header = load_source_header(
                source.verified,
                plans[source.source.chrom],
                artifact_root=root,
                expected_contigs=window_manifest.contig_lengths,
                expected_samples=source_samples,
            )
        except ValueError as error:
            _require(
                source.state == "refused"
                and source.header is None
                and source.reason == _header_failure_reason(error),
                "refused source header evidence differs from its reason",
            )
            continue
        _require(
            source.state == "ready" and source.header is not None,
            "refused source header failure is not reproduced",
        )
        retained_header_raw = _bounded_ref(
            root, source.header.header, HEADER_LIMIT_BYTES, "source header"
        )
        _require(source_header_raw == retained_header_raw, "retained header differs from source bytes")
        retained_header = parse_header(
            retained_header_raw,
            expected_contigs=window_manifest.contig_lengths,
            source_chrom=source.source.chrom,
            expected_samples=source_samples,
        )
        _require(retained_header == header, "retained header differs from source bytes")
        ordered_samples = "".join(f"{sample}\n" for sample in header.samples).encode()
        _require(
            source.header.sample_count == len(header.samples)
            and source.header.ordered_samples_sha256 == hashlib.sha256(ordered_samples).hexdigest(),
            "header receipt differs from retained header",
        )
        headers[source.source.chrom] = header
    for source in manifest.sources:
        if source.state != "refused":
            continue
        for window in (value for value in manifest.windows if value.chrom == source.source.chrom):
            _require(
                window.state == "refused"
                and window.reason == source.reason
                and window.raw_records is None
                and window.native_records is None
                and window.raw is None
                and window.offsets is None
                and window.native_bcf is None
                and window.native_keys is None
                and window.native_runs == (),
                "refused source has contradictory child window evidence",
            )
    for window in manifest.windows:
        source = source_receipts[window.chrom]
        _check_acquisition_runs(window, source, frozen_windows[window.window_id])
        if window.state == "refused":
            _require(
                (window.raw is None) == (window.offsets is None),
                "refused original evidence is incomplete",
            )
            if window.raw is not None and window.offsets is not None:
                _require(
                    source.verified is not None
                    and source.header is not None
                    and window.raw_records is not None,
                    "refused original evidence lacks source lineage",
                )
                count = validate_original_evidence(
                    source.verified,
                    plans[window.chrom],
                    frozen_windows[window.window_id],
                    headers[window.chrom],
                    artifact_root=root,
                    raw=window.raw,
                    offsets=window.offsets,
                )
                _require(count == window.raw_records, "refused original record count mismatch")
                complete_keys = (
                    len(window.native_runs) == 2
                    and all(run.state == "complete" for run in window.native_runs)
                    and window.native_keys is not None
                )
                if complete_keys:
                    try:
                        native_count = validate_original_records(
                            source.verified,
                            plans[window.chrom],
                            frozen_windows[window.window_id],
                            headers[window.chrom],
                            artifact_root=root,
                            raw=window.raw,
                            offsets=window.offsets,
                            native_keys=window.native_keys,
                        )
                    except ValueError as error:
                        _require(
                            str(error) == "native_mismatch" and window.reason == "native_mismatch",
                            "refused native evidence differs from its reason",
                        )
                    else:
                        _require(
                            native_count == count,
                            "refused native evidence differs from its reason",
                        )
                        raise ValueError("refused native failure is not reproduced")
                elif window.native_runs and all(
                    run.state == "complete" for run in window.native_runs
                ):
                    raise ValueError("refused native failure is not reproduced")
            elif source.state == "ready":
                try:
                    for _ in iter_source_records(
                        source.verified,
                        plans[window.chrom],
                        frozen_windows[window.window_id],
                        headers[window.chrom],
                        artifact_root=root,
                    ):
                        pass
                except ValueError as error:
                    _require(
                        window.reason == _record_failure_reason(error),
                        "refused original evidence differs from its reason",
                    )
                else:
                    raise ValueError("refused original failure is not reproduced")
            continue
        _require(source.verified is not None and window.native_keys is not None, "missing source evidence")
        count = validate_original_records(
            source.verified,
            plans[window.chrom],
            frozen_windows[window.window_id],
            headers[window.chrom],
            artifact_root=root,
            raw=window.raw,
            offsets=window.offsets,
            native_keys=window.native_keys,
        )
        _require(count == window.raw_records == window.native_records, "original record count mismatch")
        _require(
            tuple(run.operation for run in window.native_runs) == ("extract_bcf", "query_keys"),
            "successful window lacks exact native controls",
        )


def write_acquisition_manifest(
    directory: Path,
    manifest: AcquisitionManifest,
    *,
    preflight: BytePreflight,
    cohort_inputs: QualifiedCohortInputs | None = None,
) -> ArtifactRef:
    """Validate a complete phase tree and exclusively write acquisition.json last."""
    root = _root(directory)
    _require(type(manifest) is AcquisitionManifest and type(preflight) is BytePreflight,
             "invalid acquisition writer inputs")
    _require(not (root / "acquisition.json").exists(), "acquisition manifest already exists")
    _validate_acquisition_content(root, manifest, preflight, cohort_inputs)
    fsync_artifact_tree(root)
    raw = encode_acquisition(manifest)
    final = root / "acquisition.json"
    published = False
    try:
        _check_provenance(manifest.provenance, phase="acquisition")
        _write_exclusive(final, raw)
        published = True
        _require(validate_acquisition(root, cohort_inputs=cohort_inputs) == manifest,
                 "written acquisition manifest failed readback")
    except BaseException:
        if published:
            final.unlink(missing_ok=True)
        raise
    return ArtifactRef("acquisition.json", len(raw), hashlib.sha256(raw).hexdigest())


def validate_acquisition(
    directory: Path,
    *,
    cohort_inputs: QualifiedCohortInputs | None = None,
) -> AcquisitionManifest:
    """Deeply validate one acquisition root and return its typed final ledger."""
    root = _root(directory)
    manifest = decode_acquisition(
        _bounded_bytes(_path(root, "acquisition.json"), _MANIFEST_LIMIT, "acquisition manifest")
    )
    _validate_acquisition_content(root, manifest, cohort_inputs=cohort_inputs)
    return manifest
