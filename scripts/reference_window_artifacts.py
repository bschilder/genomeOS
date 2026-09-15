"""Write and validate immutable reference artifacts (reference acquisition design §6.2)."""

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
from genomeos.validation.reference_cohorts import (
    PAPER_STAGE,
    TECHNICAL_STAGE,
    QualifiedCohortInputs,
)
from genomeos.validation.reference_preflight_input import decode_reviewed_preflight
from genomeos.validation.reference_preparation_codec import (
    decode_preparation,
    decode_preparation_inputs,
    encode_preparation,
)
from genomeos.validation.reference_preparation_types import PreparationManifest
from genomeos.validation.reference_tbi import MAX_COMPRESSED_BYTES
from genomeos.validation.reference_vcf_tokens import (
    HEADER_LIMIT_BYTES,
    parse_header,
)
from genomeos.validation.reference_window_manifest import decode_manifest
from genomeos.validation.reference_window_types import WindowManifest
from scripts.reference_artifact_inventory import (
    acquisition_inventory_paths,
    preparation_inventory_paths,
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
    artifact_identity as _identity,
)
from scripts.reference_artifact_io import (
    artifact_path as _path,
)
from scripts.reference_artifact_io import (
    artifact_root as _root,
)
from scripts.reference_artifact_io import (
    checked_ref as _check_ref,
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
from scripts.reference_cohort_artifacts import (
    COHORT_PATHS as _COHORT_PATHS,
)
from scripts.reference_cohort_artifacts import (
    qualify_cohort_files as _qualify_cohort_files,
)
from scripts.reference_count_artifacts import (
    expected_native_rows,
    expected_qc_rows,
    validate_count_tables,
)
from scripts.reference_io_common import fsync_artifact_tree, validate_verified_source
from scripts.reference_runtime import campaign_source_hashes, validate_runtime_provenance
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
_PREPARATION_COLUMNS = (
    "window_id", "chrom", "state", "reason", "raw_records", "retained_variants",
)
_QC_COLUMNS = ("window_id", "stage", "category", "key", "origin", "count")
_NATIVE_COLUMNS = (
    "window_id", "stage", "state", "variants", "native_ac_an_matches", "native_interpreted_calls",
)
_MANIFEST_LIMIT = 16_777_216
_SIDECAR_LIMIT = 16_777_216
_NATIVE_STDOUT_LIMITS = {
    "extract_bcf": 2_147_483_648,
    "query_keys": 2_147_483_648,
    "select_cohort": 2_147_483_648,
    "fill_tags": 2_147_483_648,
    "query_samples": 1_048_576,
    "query_tokens": 2_147_483_648,
    "query_totals": 2_147_483_648,
}


def _check_provenance(provenance: object, *, phase: str) -> None:
    checkout = Path(__file__).resolve().parents[1]
    expected = campaign_source_hashes(checkout)
    _require(
        provenance.imported_source_sha256 == expected,
        "imported source hash map is incomplete or changed",
    )
    validate_runtime_provenance(provenance, phase=phase)


def _check_native_run_limits(run: object) -> None:
    _require(
        run.stdout_limit_bytes == _NATIVE_STDOUT_LIMITS[run.operation]
        and run.stderr_limit_bytes == 1_048_576,
        "native process receipt uses noncanonical bounds",
    )


def _check_run_template(
    run: object,
    expected: tuple[str, ...],
    *,
    stdout_path: str,
    stderr_path: str,
) -> None:
    _check_native_run_limits(run)
    _require(run.argv_template == expected, "native process argv differs from frozen command")
    suffix = ".partial" if run.state == "refused" else ""
    _require(
        run.stdout.path == f"{stdout_path}{suffix}"
        and run.stderr.path == f"{stderr_path}{suffix}",
        "native process outputs differ from the fixed layout",
    )


def _check_acquisition_runs(window: object, source: object, frozen_window: object) -> None:
    if not window.native_runs:
        return
    _require(source.verified is not None, "native window lacks verified source")
    region = f"{window.chrom}:{frozen_window.start0 + 1}-{frozen_window.end0}"
    templates = (
        (
            "bcftools", "view", "--no-version", "-r", region,
            "--regions-overlap", "0", "-Ob", source.verified.sparse_path,
        ),
        (
            "bcftools", "query", "-f",
            r"%CHROM\t%POS\t%REF\t%ALT\t%FILTER\n",
            f"windows/{window.window_id}.native.bcf",
        ),
    )
    paths = (
        (f"windows/{window.window_id}.native.bcf", f"windows/{window.window_id}.extract.stderr"),
        (f"windows/{window.window_id}.native.keys.tsv", f"windows/{window.window_id}.keys.stderr"),
    )
    for run, expected, (stdout_path, stderr_path) in zip(
        window.native_runs, templates, paths, strict=False
    ):
        _check_run_template(
            run,
            expected,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
        )


def _check_stage_runs(window: object, stage: object) -> None:
    control = stage.native_control
    tokens = stage.native_tokens
    prefix = f"native/{window.window_id}.{stage.stage}"
    if control is not None:
        sample_path = _COHORT_PATHS[
            "technical_samples" if stage.stage == TECHNICAL_STAGE else "paper_samples"
        ]
        templates = (
            (
                "bcftools", "view", "--no-version", "-S", sample_path,
                "-m2", "-M2", "-v", "snps", "-f", "PASS", "-Ob",
                control.input_bcf.path,
            ),
            (
                "bcftools", "+fill-tags", f"{prefix}.selected.bcf",
                "--no-version", "-Ob", "--", "-t", "AC,AN",
            ),
            ("bcftools", "query", "-l", f"{prefix}.recomputed.bcf"),
            (
                "bcftools", "query", "-f",
                r"%CHROM\t%POS\t%REF\t%ALT\t%INFO/AC\t%INFO/AN\n",
                f"{prefix}.recomputed.bcf",
            ),
        )
        paths = (
            (f"{prefix}.selected.bcf", f"{prefix}.selected.bcf.stderr"),
            (f"{prefix}.recomputed.bcf", f"{prefix}.recomputed.bcf.stderr"),
            (f"{prefix}.samples.txt", f"{prefix}.samples.txt.stderr"),
            (f"{prefix}.totals.tsv", f"{prefix}.totals.tsv.stderr"),
        )
        for run, expected, (stdout_path, stderr_path) in zip(
            control.runs, templates, paths, strict=False
        ):
            _check_run_template(
                run,
                expected,
                stdout_path=stdout_path,
                stderr_path=stderr_path,
            )
    if tokens is not None:
        token_templates = (
            ("bcftools", "query", "-l", tokens.input_bcf.path),
            (
                "bcftools", "query", "-f",
                r"%CHROM\t%POS\t%REF\t%ALT[\t%GT:%GQ:%DP:%AD]\n",
                tokens.input_bcf.path,
            ),
        )
        _check_run_template(
            tokens.sample_query,
            token_templates[0],
            stdout_path=f"{prefix}.tokens.samples.txt",
            stderr_path=f"{prefix}.tokens.samples.stderr",
        )
        if tokens.token_query is not None:
            _check_run_template(
                tokens.token_query,
                token_templates[1],
                stdout_path=f"{prefix}.tokens.tokens.tsv",
                stderr_path=f"{prefix}.tokens.tokens.stderr",
            )


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
        if source.metadata.state == "verified":
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


def _validate_preparation_content(
    root: Path,
    manifest: PreparationManifest,
    acquisition_root: Path,
    *,
    deep: bool = True,
    cohort_inputs: QualifiedCohortInputs | None = None,
) -> None:
    _require(type(deep) is bool, "invalid preparation validation mode")
    _check_provenance(manifest.provenance, phase="preparation")
    parent_root = _root(acquisition_root)
    if deep:
        acquisition = validate_acquisition(parent_root, cohort_inputs=cohort_inputs)
    else:
        acquisition = decode_acquisition(
            _bounded_bytes(
                _path(parent_root, "acquisition.json"),
                _MANIFEST_LIMIT,
                "acquisition manifest",
            )
        )
    _require(
        (
            manifest.provenance.code_revision,
            manifest.provenance.imported_source_sha256,
        )
        == (
            acquisition.provenance.code_revision,
            acquisition.provenance.imported_source_sha256,
        ),
        "preparation implementation differs from reviewed acquisition",
    )
    parent_raw = _bounded_bytes(
        _path(parent_root, "acquisition.json"), _MANIFEST_LIMIT, "acquisition manifest"
    )
    copied = _bounded_ref(
        root, manifest.inputs.acquisition, _MANIFEST_LIMIT, "copied acquisition manifest"
    )
    _require(copied == parent_raw, "copied acquisition manifest differs from acquisition root")
    _require(manifest.inputs.acquisition.sha256 == hashlib.sha256(parent_raw).hexdigest(),
             "preparation acquisition hash mismatch")
    _require(
        manifest.inputs.acquisition.path == "inputs/acquisition.json"
        and manifest.inputs.dependency_audit.path == _COHORT_PATHS["dependency_audit"],
        "preparation input paths differ from the fixed layout",
    )
    _require(
        manifest.inputs.cohort == acquisition.inputs.cohort,
        "preparation cohort inputs differ from acquisition",
    )
    technical, paper, source_samples = _qualify_cohort_files(
        root, manifest.inputs.cohort, cohort_inputs
    )
    _require(manifest.inputs.dependency_audit.sha256 == manifest.inputs.cohort.dependency_audit,
             "preparation dependency-audit identity mismatch")
    preparation_caps = {
        "windows.tsv": _SIDECAR_LIMIT,
        "qc-dispositions.tsv": _SIDECAR_LIMIT,
        "native-controls.tsv": _SIDECAR_LIMIT,
        "inputs.json": _SIDECAR_LIMIT,
        manifest.inputs.acquisition.path: _MANIFEST_LIMIT,
        **{value: _SIDECAR_LIMIT for value in _COHORT_PATHS.values()},
        f"{TECHNICAL_STAGE}.dependencies.json": _SIDECAR_LIMIT,
        f"{PAPER_STAGE}.dependencies.json": _SIDECAR_LIMIT,
        **{track.dependencies.path: _SIDECAR_LIMIT for track in manifest.tracks},
    }
    _inventory(
        root,
        manifest,
        "manifest.json",
        allowed_paths=preparation_inventory_paths(manifest),
        caps=preparation_caps,
    )
    for window in manifest.windows:
        for stage in window.stages:
            _check_stage_runs(window, stage)
    _require(decode_preparation_inputs(
        _bounded_bytes(_path(root, "inputs.json"), _SIDECAR_LIMIT, "preparation inputs")
    ) == manifest.inputs,
             "preparation inputs sidecar mismatch")
    _check_tsv(
        _path(root, "windows.tsv"),
        _PREPARATION_COLUMNS,
        _windows_rows(manifest.windows, preparation=True),
    )
    _check_tsv(
        _path(root, "qc-dispositions.tsv"), _QC_COLUMNS, expected_qc_rows(manifest)
    )
    _check_tsv(
        _path(root, "native-controls.tsv"), _NATIVE_COLUMNS, expected_native_rows(manifest)
    )
    acquisition_windows = {value.window_id: value for value in acquisition.windows}
    frozen = decode_manifest(
        _bounded_bytes(
            _path(_root(acquisition_root), "inputs/window-manifest.json"),
            _MANIFEST_LIMIT,
            "window manifest",
        ),
        windows_bytes=_bounded_bytes(
            _path(_root(acquisition_root), "inputs/windows.tsv"),
            _SIDECAR_LIMIT,
            "windows sidecar",
        ),
    )
    admitted_bcf = {
        value.native_bcf.path: value.native_bcf
        for value in acquisition.windows
        if value.native_bcf is not None
    }
    acquisition_root = parent_root
    for window in manifest.windows:
        parent_window = acquisition_windows[window.window_id]
        if window.raw_records is not None:
            _require(
                window.raw_records == parent_window.raw_records,
                "preparation raw count differs from acquisition",
            )
        if window.state == "refused":
            _require(
                window.retained_variants is None,
                "refused preparation cannot claim a retained variant count",
            )
        for stage in window.stages:
            _require(
                stage.native_tokens is None or stage.native_control is not None,
                "native token evidence lacks its count control",
            )
            if stage.native_control is None:
                continue
            sample_relative = _COHORT_PATHS[
                "technical_samples" if stage.stage == TECHNICAL_STAGE else "paper_samples"
            ]
            sample_size, sample_sha = _identity(_path(root, sample_relative))
            _require(
                stage.native_control.requested_samples
                == ArtifactRef(sample_relative, sample_size, sample_sha),
                "native requested samples differ from the qualified cohort",
            )
            if stage.native_tokens is not None:
                _require(
                    stage.native_control.selected_bcf is not None
                    and stage.native_tokens.input_bcf == stage.native_control.selected_bcf,
                    "native token input differs from selected cohort BCF",
                )
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
    _require(acquisition.complete, "preparation requires complete acquisition")
    if deep:
        validate_count_tables(
            root,
            manifest,
            acquisition_root,
            acquisition,
            frozen,
            (technical, paper),
            source_samples,
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


def write_preparation_manifest(
    directory: Path,
    manifest: PreparationManifest,
    *,
    acquisition_root: Path,
    cohort_inputs: QualifiedCohortInputs | None = None,
) -> ArtifactRef:
    """Validate a count tree and exclusively write manifest.json last."""
    root = _root(directory)
    _require(type(manifest) is PreparationManifest, "invalid preparation manifest")
    _require(not (root / "manifest.json").exists(), "preparation manifest already exists")
    _validate_preparation_content(
        root,
        manifest,
        acquisition_root,
        deep=True,
        cohort_inputs=cohort_inputs,
    )
    fsync_artifact_tree(root)
    raw = encode_preparation(manifest)
    final = root / "manifest.json"
    published = False
    try:
        _check_provenance(manifest.provenance, phase="preparation")
        _write_exclusive(final, raw)
        published = True
        retained = _bounded_bytes(
            final,
            _MANIFEST_LIMIT,
            "written preparation manifest",
        )
        _require(
            retained == raw and decode_preparation(retained) == manifest,
            "written preparation manifest failed readback",
        )
        _require(
            validate_preparation(
                root,
                acquisition_root=acquisition_root,
                cohort_inputs=cohort_inputs,
            )
            == manifest,
            "written preparation manifest failed deep readback",
        )
    except BaseException:
        if published:
            final.unlink(missing_ok=True)
        raise
    return ArtifactRef("manifest.json", len(raw), hashlib.sha256(raw).hexdigest())


def validate_preparation(
    directory: Path,
    *,
    acquisition_root: Path,
    cohort_inputs: QualifiedCohortInputs | None = None,
) -> PreparationManifest:
    """Deeply validate one preparation root and its external acquisition binding."""
    root = _root(directory)
    manifest = decode_preparation(
        _bounded_bytes(_path(root, "manifest.json"), _MANIFEST_LIMIT, "preparation manifest")
    )
    _validate_preparation_content(
        root, manifest, acquisition_root, cohort_inputs=cohort_inputs
    )
    return manifest
