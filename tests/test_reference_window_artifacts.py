"""Strict reference artifact codecs and writers (reference acquisition design §6)."""

from __future__ import annotations

import hashlib
import json
import os
import platform
from dataclasses import replace
from pathlib import Path

import pytest

from genomeos.validation.reference_acquisition_codec import decode_acquisition, encode_acquisition
from genomeos.validation.reference_acquisition_types import (
    ACQUISITION_POLICY,
    AcquisitionInputs,
    AcquisitionManifest,
    AcquisitionSourceReceipt,
    AcquisitionTotals,
    AcquisitionWindowReceipt,
    ArtifactRef,
    CohortInputHashes,
    HeaderReceipt,
    MetadataReceipt,
    NativeCountFiles,
    NativeRunReceipt,
    NativeTokenFiles,
    RangeReceipt,
    RunProvenance,
    VerifiedRange,
    VerifiedSource,
)
from genomeos.validation.reference_byte_plan import BytePreflight
from genomeos.validation.reference_genotypes import (
    MissingOriginCount,
    PopulationCount,
    QcTally,
    VariantCounts,
)
from genomeos.validation.reference_preflight_input import decode_reviewed_preflight
from genomeos.validation.reference_preparation import prepare_rows
from genomeos.validation.reference_preparation_codec import (
    decode_preparation,
    encode_dependency,
    encode_preparation,
    encode_preparation_inputs,
)
from genomeos.validation.reference_preparation_types import (
    DEPENDENCY_EDGES,
    PREPARATION_POLICY,
    DependencyEvidence,
    PreparationInputs,
    PreparationManifest,
    PreparationStageReceipt,
    PreparationWindowReceipt,
    StageWindowSummary,
    TrackSummary,
)
from genomeos.validation.reference_window_manifest import decode_manifest, windows_tsv
from genomeos.validation.reference_window_types import AUTOSOMES
from scripts.reference_window_artifacts import (
    validate_acquisition,
    validate_preparation,
    write_acquisition_manifest,
    write_preparation_manifest,
)
from tests.reference_acquisition_fixture import synthetic_preflight_case

_BGZF_EOF = bytes.fromhex("1f8b08040000000000ff0600424302001b0003000000000000000000")


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def _ref(path: str, raw: bytes = b"") -> ArtifactRef:
    return ArtifactRef(path, len(raw), hashlib.sha256(raw).hexdigest())


def _write(root: Path, path: str, raw: bytes) -> ArtifactRef:
    destination = root / path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(raw)
    return _ref(path, raw)


def _review_raw(review) -> bytes:
    value = {
        "schema_version": review.schema_version,
        "manifest_sha256": review.manifest_sha256,
        "preflight_sha256": review.preflight_sha256,
        "implementation_revision": review.implementation_revision,
        "implementation_sha256": dict(review.implementation_sha256),
        "review_locator": review.review_locator,
        "review_sha256": review.review_sha256,
        "status": review.status,
    }
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _rows_raw(columns: tuple[str, ...], rows: tuple[tuple[str, ...], ...]) -> bytes:
    return "".join("\t".join(row) + "\n" for row in (columns, *rows)).encode()


def _window_rows(windows, last: str) -> tuple[tuple[str, ...], ...]:
    return tuple(
        (
            value.window_id,
            value.chrom,
            value.state,
            "NA" if value.reason is None else value.reason,
            "NA" if value.raw_records is None else str(value.raw_records),
            "NA" if getattr(value, last) is None else str(getattr(value, last)),
        )
        for value in windows
    )


def _cohort() -> CohortInputHashes:
    return CohortInputHashes(*(_digest(field) for field in CohortInputHashes.__dataclass_fields__))


def _provenance() -> RunProvenance:
    source_path = Path(__file__).parents[1] / "genomeos/validation/reference_preparation.py"
    return RunProvenance(
        "a" * 40,
        platform.python_version(),
        (
            (
                "genomeos/validation/reference_preparation.py",
                hashlib.sha256(source_path.read_bytes()).hexdigest(),
            ),
        ),
        (("bcftools", "bcftools 1.23.1"),),
        (("bin/bcftools", _digest("bcftools")),),
        (),
    )


def refused_acquisition() -> AcquisitionManifest:
    """Return a complete 22/66 failure ledger with no admitted products."""
    window_manifest, _, _, retained, review = synthetic_preflight_case()
    sources = tuple(
        AcquisitionSourceReceipt(
            source,
            _ref(f"inputs/indexes/{source.chrom}.tbi", index.raw),
            MetadataReceipt("not_attempted", "invalid_input", 0, 0, None, None, None, False, False),
            (),
            "refused",
            "invalid_input",
            None,
            None,
        )
        for source, index in zip(window_manifest.sources, retained, strict=True)
    )
    windows = tuple(
        AcquisitionWindowReceipt(
            window.window_id,
            window.chrom,
            "refused",
            "invalid_input",
            None,
            None,
            None,
            None,
            None,
            None,
            (),
        )
        for window in window_manifest.windows
    )
    return AcquisitionManifest(
        "reference_window_acquisition_v1",
        AcquisitionInputs(
            _ref("inputs/window-manifest.json"),
            _ref("inputs/windows.tsv"),
            _ref("inputs/preflight.json"),
            _ref("inputs/review.json", review.review_sha256.encode()),
            _cohort(),
        ),
        _provenance(),
        ACQUISITION_POLICY,
        sources,
        windows,
        (),
        AcquisitionTotals(0, 0, 0, 0, 0, 0, 0, 0, None, None, None),
        False,
        False,
        False,
        False,
    )


def refused_preparation() -> PreparationManifest:
    """Return a complete 66-by-2 failure ledger with no admitted tracks."""
    stages = tuple(
        PreparationStageReceipt(stage, "not_attempted", "invalid_input", None, None, None)
        for stage in ("technical_qc_4117", "paper_ancestry_exclusion_4094")
    )
    windows = tuple(
        PreparationWindowReceipt(
            f"chr{chrom}-s{stratum}",
            f"chr{chrom}",
            "refused",
            "invalid_input",
            None,
            None,
            None,
            stages,
        )
        for chrom in range(1, 23)
        for stratum in range(1, 4)
    )
    return PreparationManifest(
        "reference_window_counts_v1",
        PreparationInputs(
            _ref("inputs/acquisition.json"),
            _cohort(),
            _ref("inputs/cohort/dependency-audit.json"),
        ),
        _provenance(),
        PREPARATION_POLICY,
        windows,
        (),
        (),
        "refused",
        False,
        False,
        False,
        False,
    )


def _complete_acquisition_tree(
    root: Path,
    *,
    one_record: bool = False,
) -> tuple[AcquisitionManifest, BytePreflight]:
    window_manifest, manifest_raw, preflight_raw, retained, review = synthetic_preflight_case(
        source_size_bytes=4_096
    )
    artifacts: dict[str, ArtifactRef] = {}

    def put(path: str, raw: bytes) -> ArtifactRef:
        reference = _write(root, path, raw)
        artifacts[path] = reference
        return reference

    upstream_windows = put("inputs/windows.tsv", windows_tsv(window_manifest.windows))
    upstream_manifest = put("inputs/window-manifest.json", manifest_raw)
    upstream_preflight = put("inputs/preflight.json", preflight_raw)
    upstream_review = put("inputs/review.json", _review_raw(review))
    cohort_refs = {
        "metadata": put("inputs/cohort/metadata.tsv", b"synthetic metadata\n"),
        "outliers": put("inputs/cohort/outliers.txt", b""),
        "exclusions": put("inputs/cohort/exclusions.json", b"{}\n"),
        "technical_samples": put("inputs/cohort/technical.samples.txt", b""),
        "paper_samples": put("inputs/cohort/paper.samples.txt", b""),
        "dependency_audit": put("inputs/cohort/dependency-audit.json", b"{}\n"),
    }
    cohort = CohortInputHashes(
        *(cohort_refs[field].sha256 for field in CohortInputHashes.__dataclass_fields__)
    )
    decoded = decode_reviewed_preflight(
        preflight_raw,
        manifest=window_manifest,
        manifest_raw=manifest_raw,
        indexes=retained,
        review=review,
    )
    sources = []
    for plan, index in zip(decoded.sources, retained, strict=True):
        chrom = plan.source.chrom
        sparse_relative = f"sources/{chrom}/INCOMPLETE.original.vcf.bgz"
        prefix = f"synthetic-{chrom}\n".encode()
        source_raw = prefix + b"x" * (4_096 - len(prefix) - len(_BGZF_EOF)) + _BGZF_EOF
        sparse = root / sparse_relative
        sparse.parent.mkdir(parents=True, exist_ok=True)
        sparse.write_bytes(source_raw)
        index_ref = put(f"{sparse_relative}.tbi", index.raw)
        metadata_stdout = put(f"runtime/{chrom}.metadata.stdout", b"")
        metadata_stderr = put(f"runtime/{chrom}.metadata.stderr", b"")
        range_stderr = put(f"runtime/{chrom}.range.stderr", b"")
        receipts = []
        verified_ranges = []
        for byte_range in plan.merged_vcf_ranges:
            relative = f"ranges/{chrom}-{byte_range.first}-{byte_range.last}.bin"
            retained_range = put(relative, source_raw[byte_range.first : byte_range.last + 1])
            receipts.append(
                RangeReceipt(
                    chrom,
                    plan.source.vcf.generation,
                    byte_range.first,
                    byte_range.last,
                    retained_range.size_bytes,
                    retained_range.size_bytes,
                    1,
                    "verified",
                    None,
                    retained_range.sha256,
                    retained_range,
                    range_stderr,
                    0,
                    False,
                    False,
                )
            )
            verified_ranges.append(VerifiedRange(byte_range.first, byte_range.last, retained_range))
        header = put(f"sources/{chrom}/header.vcf", f"##contig=<ID={chrom}>\n".encode())
        verified = VerifiedSource(
            plan.source,
            tuple(verified_ranges),
            sparse_relative,
            index_ref,
            len(source_raw),
            sparse.stat().st_blocks * 512,
            False,
        )
        sources.append(
            AcquisitionSourceReceipt(
                plan.source,
                index_ref,
                MetadataReceipt(
                    "verified", None, 1, 0, metadata_stdout, metadata_stderr, 0, False, False
                ),
                tuple(receipts),
                "ready",
                None,
                verified,
                HeaderReceipt(
                    header,
                    hashlib.sha256(b"").hexdigest(),
                    0,
                    "exact_metadata_plus_control",
                    "frozen_manifest_assembly_and_lengths",
                    "verified",
                ),
            )
        )
    windows = []
    for window in window_manifest.windows:
        prefix = f"windows/{window.window_id}"
        retained = one_record and window.window_id == "chr1-s1"
        position = window.start0 + 1
        raw_bytes = (
            f"chr1\t{position}\t.\tA\tG\t.\tPASS\t.\n".encode()
            if retained
            else b""
        )
        raw = put(f"{prefix}.original-records.tsv", raw_bytes)
        offsets_bytes = b"ordinal\tsource_virtual_offset\traw_sha256\n"
        if retained:
            offsets_bytes += f"0\t0\t{hashlib.sha256(raw_bytes).hexdigest()}\n".encode()
        offsets = put(
            f"{prefix}.record-offsets.tsv",
            offsets_bytes,
        )
        native_bcf = put(f"{prefix}.native.bcf", b"BCF\x04\x02")
        native_keys = put(
            f"{prefix}.native.keys.tsv",
            f"chr1\t{position}\tA\tG\tPASS\n".encode() if retained else b"",
        )
        stderr = put(f"{prefix}.native.stderr", b"")
        runs = (
            NativeRunReceipt(
                "extract_bcf", ("bcftools", "view", native_bcf.path), "complete", None, 0,
                native_bcf, stderr, 2_147_483_648, 1_048_576, False, False,
            ),
            NativeRunReceipt(
                "query_keys", ("bcftools", "query", native_bcf.path), "complete", None, 0,
                native_keys, stderr, 2_147_483_648, 1_048_576, False, False,
            ),
        )
        windows.append(
            AcquisitionWindowReceipt(
                window.window_id,
                window.chrom,
                "records_acquired" if retained else "no_records",
                None,
                int(retained),
                int(retained),
                raw, offsets, native_bcf, native_keys, runs,
            )
        )
    ledger = _rows_raw(
        ("window_id", "chrom", "state", "reason", "raw_records", "native_records"),
        _window_rows(tuple(windows), "native_records"),
    )
    put("windows.tsv", ledger)
    ranges = tuple(value for source in sources for value in source.ranges)
    totals = AcquisitionTotals(
        decoded.total_planned_bytes,
        sum(value.retained_index.size_bytes for value in sources),
        sum(value.receipt.received_bytes for value in decoded.sources),
        sum(value.requested_bytes for value in ranges),
        sum(value.received_bytes for value in ranges),
        sum(value.adapter_invocations for value in ranges),
        sum(value.metadata.adapter_invocations for value in sources),
        sum(value.metadata.stdout_bytes for value in sources),
        None,
        None,
        None,
    )
    manifest = AcquisitionManifest(
        "reference_window_acquisition_v1",
        AcquisitionInputs(upstream_manifest, upstream_windows, upstream_preflight, upstream_review, cohort),
        _provenance(),
        ACQUISITION_POLICY,
        tuple(sources),
        tuple(windows),
        tuple(artifacts[path] for path in sorted(artifacts)),
        totals,
        True,
        False,
        False,
        False,
    )
    return manifest, decoded


def _complete_empty_preparation_tree(root: Path, acquisition_root: Path) -> PreparationManifest:
    artifacts: dict[str, ArtifactRef] = {}

    def put(path: str, raw: bytes) -> ArtifactRef:
        reference = _write(root, path, raw)
        artifacts[path] = reference
        return reference

    acquisition_raw = (acquisition_root / "acquisition.json").read_bytes()
    acquisition = put("inputs/acquisition.json", acquisition_raw)
    cohort_paths = {
        "metadata": "metadata.tsv",
        "outliers": "outliers.txt",
        "exclusions": "exclusions.json",
        "technical_samples": "technical.samples.txt",
        "paper_samples": "paper.samples.txt",
        "dependency_audit": "dependency-audit.json",
    }
    cohort_refs = {
        field: put(
            f"inputs/cohort/{name}",
            (acquisition_root / f"inputs/cohort/{name}").read_bytes(),
        )
        for field, name in cohort_paths.items()
    }
    cohort = CohortInputHashes(
        *(cohort_refs[field].sha256 for field in CohortInputHashes.__dataclass_fields__)
    )
    inputs = PreparationInputs(acquisition, cohort, cohort_refs["dependency_audit"])
    put("inputs.json", encode_preparation_inputs(inputs))

    populations = tuple(sorted((*{value for edge in DEPENDENCY_EDGES for value in edge},
                                *(f"population-{index:02d}" for index in range(74)))))
    edges = DEPENDENCY_EDGES
    dependency_refs = {}
    for stage in ("technical_qc_4117", "paper_ancestry_exclusion_4094"):
        dependency = DependencyEvidence(
            "reference_population_dependencies_v1",
            stage,
            populations,
            edges,
            1_302 if stage == "technical_qc_4117" else 1_294,
            77,
            cohort.dependency_audit,
            "reported_edges_only_shared_source_dependence_remains",
        )
        dependency_refs[stage] = put(f"{stage}.dependencies.json", encode_dependency(dependency))

    count_header = _rows_raw(
        ("record_id", "variant_id", "group_id", "region_id", "variant_group", "ac", "an"),
        (),
    )
    tracks = []
    for stage in ("technical_qc_4117", "paper_ancestry_exclusion_4094"):
        for kind in ("called", "quality"):
            table = put(f"{stage}.{kind}.tsv", count_header)
            tracks.append(TrackSummary(stage, kind, table, dependency_refs[stage], 0, 0, 0, 0, 0, 0))

    empty_qc = QcTally((), (), ())
    windows = []
    for chrom in range(1, 23):
        for stratum in range(1, 4):
            summaries = (
                StageWindowSummary(4_117, 80, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, empty_qc),
                StageWindowSummary(4_094, 80, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, empty_qc),
            )
            stages = tuple(
                PreparationStageReceipt(stage, "complete", None, summary, None, None)
                for stage, summary in zip(
                    ("technical_qc_4117", "paper_ancestry_exclusion_4094"), summaries, strict=True
                )
            )
            windows.append(
                PreparationWindowReceipt(
                    f"chr{chrom}-s{stratum}", f"chr{chrom}", "no_records", None, 0, 0, (), stages
                )
            )
    put(
        "windows.tsv",
        _rows_raw(
            ("window_id", "chrom", "state", "reason", "raw_records", "retained_variants"),
            _window_rows(tuple(windows), "retained_variants"),
        ),
    )
    put(
        "variant-windows.tsv",
        _rows_raw(
            (
                "variant_id", "window_id", "chrom", "start0", "end0", "source_uri",
                "source_generation",
            ),
            (),
        ),
    )
    put(
        "qc-dispositions.tsv",
        _rows_raw(("window_id", "stage", "category", "key", "origin", "count"), ()),
    )
    native_rows = tuple(
        (window.window_id, stage.stage, "complete", "0", "0", "0")
        for window in windows
        for stage in window.stages
    )
    put(
        "native-controls.tsv",
        _rows_raw(
            (
                "window_id", "stage", "state", "variants", "native_ac_an_matches",
                "native_interpreted_calls",
            ),
            native_rows,
        ),
    )
    return PreparationManifest(
        "reference_window_counts_v1",
        inputs,
        _provenance(),
        PREPARATION_POLICY,
        tuple(windows),
        tuple(tracks),
        tuple(artifacts[path] for path in sorted(artifacts)),
        "complete_empty",
        True,
        False,
        False,
        False,
    )


def _complete_unavailable_preparation_tree(root: Path, acquisition_root: Path) -> PreparationManifest:
    empty = _complete_empty_preparation_tree(root, acquisition_root)
    selected_window = decode_manifest(
        (acquisition_root / "inputs/window-manifest.json").read_bytes(),
        windows_bytes=(acquisition_root / "inputs/windows.tsv").read_bytes(),
    ).windows[0]
    population_names = tuple(sorted((*{value for edge in DEPENDENCY_EDGES for value in edge},
                                     *(f"population-{index:02d}" for index in range(74)))))
    parent_bcf = validate_acquisition(acquisition_root).windows[0].native_bcf
    assert parent_bcf is not None
    stage_receipts = []
    table_refs = {}
    for stage, sample_count in (
        ("technical_qc_4117", 4_117),
        ("paper_ancestry_exclusion_4094", 4_094),
    ):
        population_counts = tuple(
            PopulationCount(
                population,
                "synthetic-region",
                sample_count - 79 if index == 0 else 1,
                0,
                0,
                0,
                0,
            )
            for index, population in enumerate(population_names)
        )
        qc = QcTally(
            (("missing_gt", sample_count),),
            (("gt", sample_count),),
            (MissingOriginCount("gt", "literal_dot", sample_count),),
        )
        counts = (
            VariantCounts(
                f"GRCh38:chr1:{selected_window.start0 + 1}:A:G",
                population_counts,
                qc,
            ),
        )
        for kind in ("called", "quality"):
            rows = prepare_rows(selected_window, counts, kind=kind)
            raw = _rows_raw(
                ("record_id", "variant_id", "group_id", "region_id", "variant_group", "ac", "an"),
                tuple(
                    (
                        row.record_id, row.variant_id, row.group_id, row.region_id,
                        row.variant_group, str(row.ac), str(row.an),
                    )
                    for row in rows
                ),
            )
            table_refs[(stage, kind)] = _write(root, f"{stage}.{kind}.tsv", raw)

        prefix = f"native/{stage}.chr1-s1"
        requested = _write(root, f"{prefix}.requested.samples.txt", b"synthetic\n")
        selected = _write(root, f"{prefix}.selected.bcf", b"BCF\x04\x02")
        recomputed = _write(root, f"{prefix}.recomputed.bcf", b"BCF\x04\x02tags")
        selected_samples = _write(root, f"{prefix}.selected.samples.txt", b"synthetic\n")
        totals = _write(
            root,
            f"{prefix}.totals.tsv",
            f"GRCh38:chr1:{selected_window.start0 + 1}:A:G\t0\t0\n".encode(),
        )
        tokens = _write(
            root,
            f"{prefix}.tokens.tsv",
            f"chr1\t{selected_window.start0 + 1}\tA\tG\t.\n".encode(),
        )
        stderr = _write(root, f"{prefix}.stderr", b"")

        def run(
            operation: str,
            stdout: ArtifactRef,
            stderr: ArtifactRef = stderr,
        ) -> NativeRunReceipt:
            return NativeRunReceipt(
                operation,
                ("bcftools", operation, stdout.path),
                "complete",
                None,
                0,
                stdout,
                stderr,
                2_147_483_648,
                1_048_576,
                False,
                False,
            )

        external = ArtifactRef(
            f"@acquisition/{parent_bcf.path}", parent_bcf.size_bytes, parent_bcf.sha256
        )
        control = NativeCountFiles(
            external,
            requested,
            selected,
            recomputed,
            selected_samples,
            totals,
            (
                run("select_cohort", selected),
                run("fill_tags", recomputed),
                run("query_samples", selected_samples),
                run("query_totals", totals),
            ),
            "complete",
            None,
        )
        token_control = NativeTokenFiles(
            selected,
            selected_samples,
            tokens,
            run("query_samples", selected_samples),
            run("query_tokens", tokens),
            "complete",
            None,
        )
        summary = StageWindowSummary(
            sample_count, 80, 1, 80, 80, 80, 0, 0, 0, 0, 1, sample_count, qc
        )
        stage_receipts.append(
            PreparationStageReceipt(stage, "complete", None, summary, control, token_control)
        )

    windows = (
        PreparationWindowReceipt(
            "chr1-s1", "chr1", "counts_prepared", None, 1, 1,
            (("retained", 1),), tuple(stage_receipts),
        ),
        *empty.windows[1:],
    )
    tracks = tuple(
        TrackSummary(
            stage,
            kind,
            table_refs[(stage, kind)],
            next(track.dependencies for track in empty.tracks if track.stage == stage),
            80,
            1,
            80,
            80,
            0,
            0,
        )
        for stage in ("technical_qc_4117", "paper_ancestry_exclusion_4094")
        for kind in ("called", "quality")
    )
    (root / "windows.tsv").write_bytes(
        _rows_raw(
            ("window_id", "chrom", "state", "reason", "raw_records", "retained_variants"),
            _window_rows(windows, "retained_variants"),
        )
    )
    source = validate_acquisition(acquisition_root).sources[0].source
    variant_id = f"GRCh38:chr1:{selected_window.start0 + 1}:A:G"
    (root / "variant-windows.tsv").write_bytes(
        _rows_raw(
            (
                "variant_id", "window_id", "chrom", "start0", "end0", "source_uri",
                "source_generation",
            ),
            ((
                variant_id, "chr1-s1", "chr1", str(selected_window.start0),
                str(selected_window.end0), source.vcf.uri, source.vcf.generation,
            ),),
        )
    )
    qc_rows = tuple(
        row
        for stage, count in (("technical_qc_4117", 4_117), ("paper_ancestry_exclusion_4094", 4_094))
        for row in (
            ("chr1-s1", stage, "disposition", "missing_gt", "NA", str(count)),
            ("chr1-s1", stage, "inspection", "gt", "NA", str(count)),
            ("chr1-s1", stage, "missing_origin", "gt", "literal_dot", str(count)),
        )
    )
    (root / "qc-dispositions.tsv").write_bytes(_rows_raw(
        ("window_id", "stage", "category", "key", "origin", "count"), qc_rows
    ))
    native_rows = tuple(
        (
            window.window_id,
            stage.stage,
            stage.state,
            str(stage.summary.variants),
            str(stage.summary.native_ac_an_matches),
            str(stage.summary.native_interpreted_calls),
        )
        for window in windows
        for stage in window.stages
    )
    (root / "native-controls.tsv").write_bytes(_rows_raw(
        (
            "window_id", "stage", "state", "variants", "native_ac_an_matches",
            "native_interpreted_calls",
        ),
        native_rows,
    ))
    artifacts = tuple(sorted((
        _ref(path.relative_to(root).as_posix(), path.read_bytes())
        for path in root.rglob("*")
        if path.is_file()
    ), key=lambda value: value.path))
    return PreparationManifest(
        "reference_window_counts_v1",
        empty.inputs,
        empty.provenance,
        PREPARATION_POLICY,
        windows,
        tracks,
        artifacts,
        "complete_nonempty",
        True,
        False,
        False,
        False,
    )


@pytest.mark.parametrize(
    ("value", "encode", "decode"),
    [
        (refused_acquisition(), encode_acquisition, decode_acquisition),
        (refused_preparation(), encode_preparation, decode_preparation),
    ],
)
def test_phase_codec_round_trip(value, encode, decode):
    raw = encode(value)
    assert raw.endswith(b"\n")
    assert decode(raw) == value
    assert encode(decode(raw)) == raw


@pytest.mark.parametrize(
    ("raw", "decode"),
    [
        (encode_acquisition(refused_acquisition()), decode_acquisition),
        (encode_preparation(refused_preparation()), decode_preparation),
    ],
)
def test_phase_codec_rejects_noncanonical_extra_duplicate_and_bool(raw, decode):
    document = json.loads(raw)
    document["extra"] = None
    with pytest.raises(ValueError, match="fields"):
        decode((json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n").encode())

    duplicate = raw.replace(b'{"benchmark_admitted":', b'{"complete":false,"benchmark_admitted":', 1)
    with pytest.raises(ValueError, match="duplicate"):
        decode(duplicate)

    document = json.loads(raw)
    document["complete"] = 0
    with pytest.raises(ValueError, match="type"):
        decode((json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n").encode())

    document = json.loads(raw)
    document["windows"][0]["raw_records"] = True
    with pytest.raises(ValueError):
        decode((json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n").encode())


def test_phase_codecs_reject_other_phase_state_and_policy_drift():
    acquisition = json.loads(encode_acquisition(refused_acquisition()))
    acquisition["windows"][0]["state"] = "counts_prepared"
    with pytest.raises(ValueError):
        decode_acquisition((json.dumps(acquisition, sort_keys=True, separators=(",", ":")) + "\n").encode())

    preparation = json.loads(encode_preparation(refused_preparation()))
    preparation["windows"][0]["state"] = "records_acquired"
    with pytest.raises(ValueError):
        decode_preparation((json.dumps(preparation, sort_keys=True, separators=(",", ":")) + "\n").encode())
    preparation = json.loads(encode_preparation(refused_preparation()))
    preparation["policy"]["native_timeout_seconds"] = 1
    with pytest.raises(ValueError, match="policy"):
        decode_preparation((json.dumps(preparation, sort_keys=True, separators=(",", ":")) + "\n").encode())


def test_preparation_dependency_components_are_recomputed():
    populations = tuple(sorted((*{value for edge in DEPENDENCY_EDGES for value in edge},
                                *(f"p{index:02d}" for index in range(74)))))
    with pytest.raises(ValueError, match="component"):
        DependencyEvidence(
            "reference_population_dependencies_v1",
            "technical_qc_4117",
            populations,
            DEPENDENCY_EDGES,
            1_302,
            76,
            "f" * 64,
            "reported_edges_only_shared_source_dependence_remains",
        )


def test_refused_ledger_keeps_all_expected_window_and_stage_outcomes():
    acquisition = refused_acquisition()
    preparation = refused_preparation()
    assert tuple(source.source.chrom for source in acquisition.sources) == AUTOSOMES
    assert len(acquisition.windows) == len(preparation.windows) == 66
    assert all(len(window.stages) == 2 for window in preparation.windows)
    assert not acquisition.complete and not preparation.complete and preparation.tracks == ()


def test_manifest_dataclass_rejects_mutated_policy_before_encoding():
    with pytest.raises(ValueError, match="policy"):
        replace(refused_acquisition(), policy=((*ACQUISITION_POLICY[:-1], ("source_complete", "true"))))


def test_acquisition_writer_is_manifest_last_exact_and_read_back(tmp_path):
    manifest, preflight = _complete_acquisition_tree(tmp_path)
    assert not (tmp_path / "acquisition.json").exists()
    reference = write_acquisition_manifest(tmp_path, manifest, preflight=preflight)
    raw = (tmp_path / "acquisition.json").read_bytes()
    assert reference == _ref("acquisition.json", raw)
    assert validate_acquisition(tmp_path) == manifest

    before = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    with pytest.raises(ValueError, match="already exists"):
        write_acquisition_manifest(tmp_path, manifest, preflight=preflight)
    assert {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()} == before


def test_acquisition_writer_leaves_no_manifest_after_prewrite_failure(tmp_path):
    manifest, preflight = _complete_acquisition_tree(tmp_path)
    damaged = tmp_path / manifest.files[0].path
    damaged.write_bytes(damaged.read_bytes() + b"tamper")
    with pytest.raises(ValueError, match="hash|identity"):
        write_acquisition_manifest(tmp_path, manifest, preflight=preflight)
    assert not (tmp_path / "acquisition.json").exists()


def test_acquisition_validator_rejects_artifact_tamper_and_symlink(tmp_path):
    manifest, preflight = _complete_acquisition_tree(tmp_path)
    write_acquisition_manifest(tmp_path, manifest, preflight=preflight)
    target = tmp_path / "windows/chr1-s1.original-records.tsv"
    target.write_bytes(b"tamper\n")
    with pytest.raises(ValueError, match="identity"):
        validate_acquisition(tmp_path)

    target.write_bytes(b"")
    real = tmp_path / "replacement"
    real.write_bytes(b"")
    target.unlink()
    os.symlink(real, target)
    with pytest.raises(ValueError, match="symlink"):
        validate_acquisition(tmp_path)


@pytest.mark.parametrize("artifact_kind", ["range", "header", "original", "native"])
def test_acquisition_validator_rejects_each_scientific_artifact_tamper(tmp_path, artifact_kind):
    manifest, preflight = _complete_acquisition_tree(tmp_path, one_record=True)
    write_acquisition_manifest(tmp_path, manifest, preflight=preflight)
    source, window = manifest.sources[0], manifest.windows[0]
    references = {
        "range": source.ranges[0].retained,
        "header": source.header.header,
        "original": window.raw,
        "native": window.native_bcf,
    }
    reference = references[artifact_kind]
    assert reference is not None
    path = tmp_path / reference.path
    path.write_bytes(path.read_bytes() + b"tamper")
    with pytest.raises(ValueError, match="identity"):
        validate_acquisition(tmp_path)


def test_complete_empty_preparation_writes_four_real_header_only_tracks(tmp_path):
    acquisition_root = tmp_path / "acquisition"
    counts_root = tmp_path / "counts"
    acquisition_root.mkdir()
    counts_root.mkdir()
    acquisition, preflight = _complete_acquisition_tree(acquisition_root)
    write_acquisition_manifest(acquisition_root, acquisition, preflight=preflight)
    preparation = _complete_empty_preparation_tree(counts_root, acquisition_root)

    reference = write_preparation_manifest(
        counts_root, preparation, acquisition_root=acquisition_root
    )
    raw = (counts_root / "manifest.json").read_bytes()
    assert reference == _ref("manifest.json", raw)
    assert validate_preparation(counts_root, acquisition_root=acquisition_root) == preparation
    assert len(preparation.tracks) == 4
    assert all((counts_root / track.table.path).read_text().count("\n") == 1 for track in preparation.tracks)


def test_preparation_validator_rejects_parent_rebinding_and_table_tamper(tmp_path):
    acquisition_root = tmp_path / "acquisition"
    counts_root = tmp_path / "counts"
    acquisition_root.mkdir()
    counts_root.mkdir()
    acquisition, preflight = _complete_acquisition_tree(acquisition_root)
    write_acquisition_manifest(acquisition_root, acquisition, preflight=preflight)
    preparation = _complete_empty_preparation_tree(counts_root, acquisition_root)
    write_preparation_manifest(counts_root, preparation, acquisition_root=acquisition_root)

    table = counts_root / preparation.tracks[0].table.path
    table.write_bytes(table.read_bytes() + b"bad\trow\n")
    with pytest.raises(ValueError, match="identity"):
        validate_preparation(counts_root, acquisition_root=acquisition_root)

    table.write_bytes(_rows_raw(
        ("record_id", "variant_id", "group_id", "region_id", "variant_group", "ac", "an"), ()
    ))
    copied = counts_root / preparation.inputs.acquisition.path
    copied.write_bytes(copied.read_bytes() + b" ")
    with pytest.raises(ValueError, match="identity|differs"):
        validate_preparation(counts_root, acquisition_root=acquisition_root)


def test_preparation_writer_failure_does_not_publish_manifest(tmp_path):
    acquisition_root = tmp_path / "acquisition"
    counts_root = tmp_path / "counts"
    acquisition_root.mkdir()
    counts_root.mkdir()
    acquisition, preflight = _complete_acquisition_tree(acquisition_root)
    write_acquisition_manifest(acquisition_root, acquisition, preflight=preflight)
    preparation = _complete_empty_preparation_tree(counts_root, acquisition_root)
    (counts_root / "windows.tsv").write_bytes(b"broken\n")
    with pytest.raises(ValueError):
        write_preparation_manifest(counts_root, preparation, acquisition_root=acquisition_root)
    assert not (counts_root / "manifest.json").exists()


def test_nonempty_all_an_zero_is_retained_and_parent_bound(tmp_path):
    acquisition_root = tmp_path / "acquisition"
    counts_root = tmp_path / "counts"
    acquisition_root.mkdir()
    counts_root.mkdir()
    acquisition, preflight = _complete_acquisition_tree(acquisition_root, one_record=True)
    write_acquisition_manifest(acquisition_root, acquisition, preflight=preflight)
    preparation = _complete_unavailable_preparation_tree(counts_root, acquisition_root)
    write_preparation_manifest(counts_root, preparation, acquisition_root=acquisition_root)

    validated = validate_preparation(counts_root, acquisition_root=acquisition_root)
    assert validated.status == "complete_nonempty"
    assert all(track.rows == track.unavailable_rows == 80 for track in validated.tracks)
    assert all(track.an_sum == 0 for track in validated.tracks)


def test_nonempty_preparation_rejects_deleted_an_zero_row(tmp_path):
    acquisition_root = tmp_path / "acquisition"
    counts_root = tmp_path / "counts"
    acquisition_root.mkdir()
    counts_root.mkdir()
    acquisition, preflight = _complete_acquisition_tree(acquisition_root, one_record=True)
    write_acquisition_manifest(acquisition_root, acquisition, preflight=preflight)
    preparation = _complete_unavailable_preparation_tree(counts_root, acquisition_root)
    table = counts_root / preparation.tracks[0].table.path
    lines = table.read_bytes().splitlines(keepends=True)
    table.write_bytes(b"".join((*lines[:1], *lines[2:])))
    changed_ref = _ref(preparation.tracks[0].table.path, table.read_bytes())
    files = tuple(changed_ref if value.path == changed_ref.path else value for value in preparation.files)
    tracks = (
        replace(
            preparation.tracks[0],
            table=changed_ref,
            rows=79,
            represented_groups=79,
            unavailable_rows=79,
        ),
        *preparation.tracks[1:],
    )
    changed = replace(preparation, tracks=tracks, files=files)
    with pytest.raises(ValueError, match="four track keys differ|track totals"):
        write_preparation_manifest(counts_root, changed, acquisition_root=acquisition_root)


def test_writer_rejects_mutated_imported_source_hash(tmp_path):
    manifest, preflight = _complete_acquisition_tree(tmp_path)
    wrong = replace(
        manifest.provenance,
        imported_source_sha256=(("genomeos/validation/reference_preparation.py", "0" * 64),),
    )
    with pytest.raises(ValueError, match="source hash"):
        write_acquisition_manifest(tmp_path, replace(manifest, provenance=wrong), preflight=preflight)
    assert not (tmp_path / "acquisition.json").exists()


def test_preparation_validator_rejects_rehashed_dependency_edge_mutation(tmp_path):
    acquisition_root = tmp_path / "acquisition"
    counts_root = tmp_path / "counts"
    acquisition_root.mkdir()
    counts_root.mkdir()
    acquisition, preflight = _complete_acquisition_tree(acquisition_root, one_record=True)
    write_acquisition_manifest(acquisition_root, acquisition, preflight=preflight)
    preparation = _complete_unavailable_preparation_tree(counts_root, acquisition_root)
    write_preparation_manifest(counts_root, preparation, acquisition_root=acquisition_root)

    relative = "technical_qc_4117.dependencies.json"
    path = counts_root / relative
    document = json.loads(path.read_bytes())
    document["edges"][0] = ["CDX", "Japanese"]
    path.write_bytes((json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n").encode())
    reference = _ref(relative, path.read_bytes())
    tracks = tuple(
        replace(track, dependencies=reference) if track.stage == "technical_qc_4117" else track
        for track in preparation.tracks
    )
    files = tuple(reference if value.path == relative else value for value in preparation.files)
    changed = replace(preparation, tracks=tracks, files=files)
    (counts_root / "manifest.json").write_bytes(encode_preparation(changed))
    with pytest.raises(ValueError, match="dependency"):
        validate_preparation(counts_root, acquisition_root=acquisition_root)


@pytest.mark.parametrize("mutation", ["count_cell", "variant_window"])
def test_preparation_validator_rejects_rehashed_semantic_mutation(tmp_path, mutation):
    acquisition_root = tmp_path / "acquisition"
    counts_root = tmp_path / "counts"
    acquisition_root.mkdir()
    counts_root.mkdir()
    acquisition, preflight = _complete_acquisition_tree(acquisition_root, one_record=True)
    write_acquisition_manifest(acquisition_root, acquisition, preflight=preflight)
    preparation = _complete_unavailable_preparation_tree(counts_root, acquisition_root)
    write_preparation_manifest(counts_root, preparation, acquisition_root=acquisition_root)

    if mutation == "count_cell":
        relative = preparation.tracks[0].table.path
        path = counts_root / relative
        lines = path.read_text().splitlines()
        cells = lines[1].split("\t")
        cells[-1] = "2"
        lines[1] = "\t".join(cells)
        path.write_text("\n".join(lines) + "\n")
        reference = _ref(relative, path.read_bytes())
        tracks = (
            replace(preparation.tracks[0], table=reference),
            *preparation.tracks[1:],
        )
    else:
        relative = "variant-windows.tsv"
        path = counts_root / relative
        lines = path.read_text().splitlines()
        cells = lines[1].split("\t")
        cells[3] = str(int(cells[3]) + 1)
        lines[1] = "\t".join(cells)
        path.write_text("\n".join(lines) + "\n")
        reference = _ref(relative, path.read_bytes())
        tracks = preparation.tracks
    files = tuple(reference if value.path == relative else value for value in preparation.files)
    changed = replace(preparation, tracks=tracks, files=files)
    (counts_root / "manifest.json").write_bytes(encode_preparation(changed))
    with pytest.raises(ValueError, match="stage-window summary|frozen acquisition"):
        validate_preparation(counts_root, acquisition_root=acquisition_root)
