"""Strict reference artifact codecs and writers (reference acquisition design §6)."""

from __future__ import annotations

import hashlib
import json
import os
import platform
from dataclasses import replace
from pathlib import Path

import pytest

from genomeos.validation.reference_acquisition_codec import (
    decode_acquisition,
    encode_acquisition,
    encode_acquisition_review,
)
from genomeos.validation.reference_acquisition_types import (
    ACQUISITION_POLICY,
    AcquisitionInputs,
    AcquisitionManifest,
    AcquisitionReviewBundle,
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
from genomeos.validation.reference_cohorts import (
    PAPER_STAGE,
    TECHNICAL_STAGE,
    Cohort,
    Sample,
)
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
from genomeos.validation.reference_vcf_tokens import HeaderEvidence
from genomeos.validation.reference_window_manifest import decode_manifest, windows_tsv
from genomeos.validation.reference_window_types import AUTOSOMES
from scripts import reference_acquisition_artifacts as acquisition_artifacts
from scripts import reference_count_replay as count_replay
from scripts import reference_preparation_artifacts as preparation_artifacts
from scripts.reference_runtime import campaign_source_hashes
from scripts.reference_window_artifacts import (
    validate_acquisition,
    validate_preparation,
    write_acquisition_manifest,
    write_preparation_manifest,
)
from tests.reference_acquisition_fixture import synthetic_preflight_case

_POPULATIONS = tuple(
    sorted(
        {
            "CDX",
            "Dai",
            "Cambodian",
            "Japanese",
            "ITU",
            "STU",
            *(f"population-{index:02d}" for index in range(74)),
        }
    )
)
_BGZF_EOF = bytes.fromhex("1f8b08040000000000ff0600424302001b0003000000000000000000")


def _artifact_cohort(stage: str, size: int) -> Cohort:
    samples = tuple(
        Sample(
            f"sample-{index:04d}",
            _POPULATIONS[index] if index < len(_POPULATIONS) else _POPULATIONS[0],
            "synthetic-region",
            False,
        )
        for index in range(size)
    )
    return Cohort(stage, samples)


@pytest.fixture(autouse=True)
def _synthetic_artifact_adapters(monkeypatch):
    technical = _artifact_cohort(TECHNICAL_STAGE, 4_117)
    paper = _artifact_cohort(PAPER_STAGE, 4_094)
    source_samples = tuple(value.sample_id for value in technical.samples)
    def qualify_synthetic(root, hashes, expected=None):
        for field, relative in acquisition_artifacts._COHORT_PATHS.items():
            raw = (root / relative).read_bytes()
            if hashlib.sha256(raw).hexdigest() != getattr(hashes, field):
                raise ValueError(f"cohort {field} hash mismatch")
        if expected is not None:
            assert expected.technical == technical
            assert expected.paper == paper
            assert expected.source_samples == source_samples
        return technical, paper, source_samples

    monkeypatch.setattr(acquisition_artifacts, "_qualify_cohort_files", qualify_synthetic)
    monkeypatch.setattr(preparation_artifacts, "_qualify_cohort_files", qualify_synthetic)
    monkeypatch.setattr(
        acquisition_artifacts,
        "parse_header",
        lambda raw, *, expected_contigs, source_chrom, expected_samples: HeaderEvidence(
            expected_samples,
            tuple(
                [(source_chrom, dict(expected_contigs)[source_chrom], "gnomAD_GRCh38")]
                + [
                    (chrom, length, "gnomAD_GRCh38")
                    for chrom, length in expected_contigs
                    if chrom != source_chrom
                ]
            ),
            (
                ("GT", "1", "String"),
                ("GQ", "1", "Integer"),
                ("DP", "1", "Integer"),
                ("AD", "R", "Integer"),
            ),
            hashlib.sha256(raw).hexdigest(),
        ),
    )

    def load_source_header(
        verified, plan, *, artifact_root, expected_contigs, expected_samples
    ):
        raw = (artifact_root / verified.sparse_path).read_bytes().splitlines(keepends=True)[0]
        return raw, acquisition_artifacts.parse_header(
            raw,
            expected_contigs=expected_contigs,
            source_chrom=plan.source.chrom,
            expected_samples=expected_samples,
        )

    monkeypatch.setattr(acquisition_artifacts, "load_source_header", load_source_header)

    def validate_original(*args, artifact_root, raw, offsets, native_keys, **kwargs):
        del args, offsets, kwargs
        retained = (artifact_root / raw.path).read_bytes().splitlines()
        native = (artifact_root / native_keys.path).read_bytes().splitlines()
        expected = []
        for line in retained:
            fields = line.split(b"\t")
            expected.append(b"\t".join((fields[0], fields[1], fields[3], fields[4], fields[6])))
        if expected != native:
            raise ValueError("native_mismatch")
        return len(retained)

    def validate_original_evidence(*args, artifact_root, raw, offsets, **kwargs):
        del args, kwargs
        retained = (artifact_root / raw.path).read_bytes().splitlines(keepends=True)
        evidence = (artifact_root / offsets.path).read_bytes().splitlines()
        expected = [b"ordinal\tsource_virtual_offset\traw_sha256"]
        expected.extend(
            f"{index}\t{index}\t{hashlib.sha256(line).hexdigest()}".encode()
            for index, line in enumerate(retained)
        )
        if expected != evidence:
            raise ValueError("artifact_mismatch")
        return len(retained)

    monkeypatch.setattr(acquisition_artifacts, "validate_original_records", validate_original)
    monkeypatch.setattr(acquisition_artifacts, "validate_original_evidence", validate_original_evidence)
    monkeypatch.setattr(count_replay, "parse_header", acquisition_artifacts.parse_header)


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def _ref(path: str, raw: bytes = b"") -> ArtifactRef:
    return ArtifactRef(path, len(raw), hashlib.sha256(raw).hexdigest())


def _write(root: Path, path: str, raw: bytes) -> ArtifactRef:
    destination = root / path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(raw)
    return _ref(path, raw)


def _replace_file(files: tuple[ArtifactRef, ...], reference: ArtifactRef) -> tuple[ArtifactRef, ...]:
    return tuple(reference if value.path == reference.path else value for value in files)


def _review_raw(review) -> bytes:
    return encode_acquisition_review(
        AcquisitionReviewBundle(
            "reference_acquisition_review_bundle_v1",
            review,
            "a" * 40,
            campaign_source_hashes(),
            "reviews/reference-acquisition.md",
            "e" * 64,
            "accepted",
        )
    )


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


def _provenance(phase: str = "acquisition") -> RunProvenance:
    core_versions = {
        "bcftools": "bcftools 1.23.1",
        "bcftools_fill_tags": (
            "bcftools  1.23.1 using htslib 1.23.1\n"
            "plugin at 1.23.1 using htslib 1.23.1"
        ),
        "bcftools_htslib": "Using htslib 1.23.1",
    }
    if phase == "acquisition":
        core_versions.update(
            {
                "tabix": "tabix (htslib) 1.23.1",
                "bgzip": "bgzip (htslib) 1.23.1",
                "gcloud": '{"Google Cloud SDK":"574.0.0"}',
            }
        )
    sdk = (
        tuple(
            (name, _digest(name))
            for name in (
                "lib/googlecloudsdk/api_lib/storage/api_factory.py",
                "lib/googlecloudsdk/api_lib/storage/gcs_download.py",
                "lib/googlecloudsdk/api_lib/storage/gcs_json/download.py",
                "lib/googlecloudsdk/api_lib/storage/retry_util.py",
                "lib/surface/storage/cat.py",
                "lib/surface/storage/objects/describe.py",
            )
        )
        if phase == "acquisition"
        else ()
    )
    return RunProvenance(
        "a" * 40,
        platform.python_version(),
        campaign_source_hashes(),
        tuple(sorted(core_versions.items())),
        tuple((name, _digest(name)) for name in sorted(core_versions)),
        sdk,
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
        _provenance("preparation"),
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
        "technical_samples": put(
            "inputs/cohort/technical.samples.txt",
            "".join(
                f"{value.sample_id}\n"
                for value in _artifact_cohort(TECHNICAL_STAGE, 4_117).samples
            ).encode(),
        ),
        "paper_samples": put(
            "inputs/cohort/paper.samples.txt",
            "".join(
                f"{value.sample_id}\n"
                for value in _artifact_cohort(PAPER_STAGE, 4_094).samples
            ).encode(),
        ),
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
        header_raw = f"##contig=<ID={chrom}>\n".encode()
        source_raw = header_raw + b"x" * (4_096 - len(header_raw) - len(_BGZF_EOF)) + _BGZF_EOF
        sparse = root / sparse_relative
        sparse.parent.mkdir(parents=True, exist_ok=True)
        sparse.write_bytes(source_raw)
        index_ref = put(f"{sparse_relative}.tbi", index.raw)
        metadata_raw = (
            json.dumps(
                {
                    "generation": plan.source.vcf.generation,
                    "size": str(plan.source.vcf.size_bytes),
                    "md5Hash": plan.source.vcf.md5_b64,
                    "crc32c": plan.source.vcf.crc32c_b64,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode()
        metadata_stdout = put(f"runtime/{chrom}.metadata.stdout", metadata_raw)
        metadata_stderr = put(f"runtime/{chrom}.metadata.stdout.stderr", b"")
        receipts = []
        verified_ranges = []
        for byte_range in plan.merged_vcf_ranges:
            relative = (
                f"sources/{chrom}/ranges/{byte_range.first}-{byte_range.last}.bin"
            )
            retained_range = put(relative, source_raw[byte_range.first : byte_range.last + 1])
            range_stderr = put(f"{relative}.stderr", b"")
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
        header = put(f"sources/{chrom}/header.vcf", header_raw)
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
                    "verified",
                    None,
                    1,
                    len(metadata_raw),
                    metadata_stdout,
                    metadata_stderr,
                    0,
                    False,
                    False,
                ),
                tuple(receipts),
                "ready",
                None,
                verified,
                HeaderReceipt(
                    header,
                    hashlib.sha256(
                        "".join(
                            f"{value.sample_id}\n"
                            for value in _artifact_cohort(TECHNICAL_STAGE, 4_117).samples
                        ).encode()
                    ).hexdigest(),
                    4_117,
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
        raw_bytes = b""
        if retained:
            raw_bytes = (
                "\t".join(
                    (
                        "chr1",
                        str(position),
                        ".",
                        "A",
                        "G",
                        ".",
                        "PASS",
                        ".",
                        "GT:GQ:DP:AD",
                        *("." for _ in range(4_117)),
                    )
                )
                + "\n"
            ).encode()
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
        extract_stderr = put(f"{prefix}.extract.stderr", b"")
        keys_stderr = put(f"{prefix}.keys.stderr", b"")
        runs = (
            NativeRunReceipt(
                "extract_bcf",
                (
                    "bcftools", "view", "--no-version", "-r",
                    f"{window.chrom}:{window.start0 + 1}-{window.end0}",
                    "--regions-overlap", "0", "-Ob",
                    f"sources/{window.chrom}/INCOMPLETE.original.vcf.bgz",
                ),
                "complete", None, 0,
                native_bcf, extract_stderr, 2_147_483_648, 1_048_576, False, False,
            ),
            NativeRunReceipt(
                "query_keys",
                (
                    "bcftools", "query", "-f",
                    r"%CHROM\t%POS\t%REF\t%ALT\t%FILTER\n", native_bcf.path,
                ),
                "complete", None, 0,
                native_keys, keys_stderr, 2_147_483_648, 1_048_576, False, False,
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
        _provenance("preparation"),
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
    population_names = _POPULATIONS
    parent_bcf = validate_acquisition(acquisition_root).windows[0].native_bcf
    assert parent_bcf is not None
    stage_receipts = []
    table_refs = {}
    for stage, sample_count in (
        (TECHNICAL_STAGE, 4_117),
        (PAPER_STAGE, 4_094),
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

        prefix = f"native/chr1-s1.{stage}"
        requested_name = (
            "technical.samples.txt" if stage == TECHNICAL_STAGE else "paper.samples.txt"
        )
        requested_path = root / "inputs/cohort" / requested_name
        requested = _ref(f"inputs/cohort/{requested_name}", requested_path.read_bytes())
        selected = _write(root, f"{prefix}.selected.bcf", b"BCF\x04\x02")
        recomputed = _write(root, f"{prefix}.recomputed.bcf", b"BCF\x04\x02tags")
        cohort = _artifact_cohort(stage, sample_count)
        selected_samples = _write(
            root,
            f"{prefix}.samples.txt",
            "".join(f"{value.sample_id}\n" for value in cohort.samples).encode(),
        )
        token_samples = _write(
            root,
            f"{prefix}.tokens.samples.txt",
            "".join(f"{value.sample_id}\n" for value in cohort.samples).encode(),
        )
        totals = _write(
            root,
            f"{prefix}.totals.tsv",
            f"chr1\t{selected_window.start0 + 1}\tA\tG\t0\t0\n".encode(),
        )
        tokens = _write(
            root,
            f"{prefix}.tokens.tokens.tsv",
            (
                f"chr1\t{selected_window.start0 + 1}\tA\tG\t"
                + "\t".join("." for _ in cohort.samples)
                + "\n"
            ).encode(),
        )
        stderrs = {
            "select_cohort": _write(root, f"{prefix}.selected.bcf.stderr", b""),
            "fill_tags": _write(root, f"{prefix}.recomputed.bcf.stderr", b""),
            "query_samples": _write(root, f"{prefix}.samples.txt.stderr", b""),
            "query_totals": _write(root, f"{prefix}.totals.tsv.stderr", b""),
            "token_samples": _write(root, f"{prefix}.tokens.samples.stderr", b""),
            "query_tokens": _write(root, f"{prefix}.tokens.tokens.stderr", b""),
        }

        def run(
            operation: str,
            stdout: ArtifactRef,
            template: tuple[str, ...],
            stderr: ArtifactRef,
        ) -> NativeRunReceipt:
            return NativeRunReceipt(
                operation,
                template,
                "complete",
                None,
                0,
                stdout,
                stderr,
                1_048_576 if operation == "query_samples" else 2_147_483_648,
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
                run(
                    "select_cohort",
                    selected,
                    (
                        "bcftools", "view", "--no-version", "-S", requested.path,
                        "-m2", "-M2", "-v", "snps", "-f", "PASS", "-Ob",
                        external.path,
                    ),
                    stderrs["select_cohort"],
                ),
                run(
                    "fill_tags",
                    recomputed,
                    (
                        "bcftools", "+fill-tags", selected.path, "--no-version",
                        "-Ob", "--", "-t", "AC,AN",
                    ),
                    stderrs["fill_tags"],
                ),
                run(
                    "query_samples",
                    selected_samples,
                    ("bcftools", "query", "-l", recomputed.path),
                    stderrs["query_samples"],
                ),
                run(
                    "query_totals",
                    totals,
                    (
                        "bcftools", "query", "-f",
                        r"%CHROM\t%POS\t%REF\t%ALT\t%INFO/AC\t%INFO/AN\n",
                        recomputed.path,
                    ),
                    stderrs["query_totals"],
                ),
            ),
            "complete",
            None,
        )
        token_control = NativeTokenFiles(
            selected,
            token_samples,
            tokens,
            run(
                "query_samples",
                token_samples,
                ("bcftools", "query", "-l", selected.path),
                stderrs["token_samples"],
            ),
            run(
                "query_tokens",
                tokens,
                (
                    "bcftools", "query", "-f",
                    r"%CHROM\t%POS\t%REF\t%ALT[\t%GT:%GQ:%DP:%AD]\n",
                    selected.path,
                ),
                stderrs["query_tokens"],
            ),
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
        for stage in (TECHNICAL_STAGE, PAPER_STAGE)
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


def test_preparation_window_receipt_binds_stage_states_to_failure_point():
    before_scan = refused_preparation().windows[0]
    with pytest.raises(ValueError, match="failure point"):
        replace(
            before_scan,
            stages=tuple(replace(stage, state="refused") for stage in before_scan.stages),
        )

    after_scan_stages = tuple(
        PreparationStageReceipt(stage, "refused", "native_mismatch", None, None, None)
        for stage in (TECHNICAL_STAGE, PAPER_STAGE)
    )
    after_scan = replace(
        before_scan,
        reason="native_mismatch",
        raw_records=1,
        stages=after_scan_stages,
    )
    with pytest.raises(ValueError, match="first stage outcome"):
        replace(
            after_scan,
            stages=(
                replace(after_scan.stages[0], reason="record_invalid"),
                after_scan.stages[1],
            ),
        )


def test_manifest_dataclass_rejects_mutated_policy_before_encoding():
    with pytest.raises(ValueError, match="policy"):
        replace(refused_acquisition(), policy=((*ACQUISITION_POLICY[:-1], ("source_complete", "true"))))


@pytest.mark.parametrize("receipt_kind", ["metadata", "range", "native"])
def test_process_receipts_reject_size_and_overflow_flag_disagreement(receipt_kind):
    digest = "a" * 64
    stderr = ArtifactRef("stderr.partial", 0, digest)
    with pytest.raises(ValueError, match="size disagrees"):
        if receipt_kind == "metadata":
            MetadataReceipt(
                "refused", "generation_unavailable", 1, 1_048_577,
                ArtifactRef("metadata.partial", 1_048_577, digest), stderr,
                1, False, False,
            )
        elif receipt_kind == "range":
            RangeReceipt(
                "chr1", "123", 0, 9, 10, 11, 1, "refused", "transfer_failed",
                digest, ArtifactRef("range.partial", 11, digest), stderr,
                1, False, False,
            )
        else:
            NativeRunReceipt(
                "query_keys", ("bcftools", "query"), "refused", "native_encoding_refused", 1,
                ArtifactRef("stdout.partial", 11, digest), stderr,
                10, 10, False, False,
            )


@pytest.mark.parametrize(
    "factory,pattern",
    [
        (
            lambda output, error: RangeReceipt(
                "chr1", "123", 0, 9, 10, 10, 1, "partial", "transfer_failed",
                output.sha256, output, error, 0, False, False,
            ),
            "zero-exit range refusal",
        ),
        (
            lambda output, error: MetadataReceipt(
                "refused", "generation_unavailable", 1, output.size_bytes,
                output, error, 0, False, False,
            ),
            "zero-exit metadata refusal",
        ),
        (
            lambda output, error: MetadataReceipt(
                "refused", "metadata_mismatch", 1, output.size_bytes,
                output, error, 1, False, False,
            ),
            "failed metadata process",
        ),
        (
            lambda output, error: NativeRunReceipt(
                "query_keys", ("bcftools", "query"), "refused", "native_mismatch", 1,
                output, error, 10, 10, False, False,
            ),
            "failed native process",
        ),
    ],
)
def test_process_receipts_reject_reasons_contradicted_by_process_evidence(factory, pattern):
    digest = hashlib.sha256(b"").hexdigest()
    output = ArtifactRef("stdout.partial", 10, digest)
    error = ArtifactRef("stderr.partial", 0, digest)
    with pytest.raises(ValueError, match=pattern):
        factory(output, error)


def test_source_receipt_rejects_ranges_attempted_after_metadata_refusal(tmp_path):
    manifest, _ = _complete_acquisition_tree(tmp_path)
    source = manifest.sources[0]
    refused_metadata = replace(
        source.metadata,
        state="refused",
        reason="metadata_mismatch",
        retained=replace(source.metadata.retained, path=f"{source.metadata.retained.path}.partial"),
        stderr=replace(source.metadata.stderr, path=f"{source.metadata.stderr.path}.partial"),
    )
    with pytest.raises(ValueError, match="metadata refusal"):
        replace(
            source,
            metadata=refused_metadata,
            state="refused",
            reason="metadata_mismatch",
            verified=None,
            header=None,
        )


def test_source_receipt_binds_its_reason_to_metadata_refusal(tmp_path):
    manifest, _ = _complete_acquisition_tree(tmp_path)
    source = manifest.sources[0]
    refused_metadata = replace(
        source.metadata,
        state="refused",
        reason="metadata_mismatch",
        retained=replace(source.metadata.retained, path=f"{source.metadata.retained.path}.partial"),
        stderr=replace(source.metadata.stderr, path=f"{source.metadata.stderr.path}.partial"),
    )
    not_attempted = tuple(
        replace(
            item,
            requested_bytes=0,
            received_bytes=0,
            adapter_invocations=0,
            state="not_attempted",
            reason="metadata_mismatch",
            sha256=None,
            retained=None,
            stderr=None,
            exit_code=None,
        )
        for item in source.ranges
    )
    with pytest.raises(ValueError, match="source outcome"):
        replace(
            source,
            metadata=refused_metadata,
            ranges=not_attempted,
            state="refused",
            reason="generation_unavailable",
            verified=None,
            header=None,
        )


def test_acquisition_window_receipt_enforces_raw_then_native_state_machine(tmp_path):
    manifest, _ = _complete_acquisition_tree(tmp_path, one_record=True)
    window = manifest.windows[0]

    with pytest.raises(ValueError, match="native execution disagrees"):
        replace(
            window,
            state="refused",
            reason="native_mismatch",
            raw_records=None,
            native_records=None,
            raw=None,
            offsets=None,
        )

    with pytest.raises(ValueError, match="native execution disagrees"):
        replace(
            window,
            state="refused",
            reason="record_invalid",
            native_records=None,
            native_bcf=None,
            native_keys=None,
            native_runs=(),
        )

    with pytest.raises(ValueError, match="invalid refusal"):
        replace(
            window,
            state="refused",
            reason="native_mismatch",
            native_records=None,
            native_keys=None,
            native_runs=window.native_runs[:1],
        )


def test_source_receipt_rejects_range_attempt_after_first_failure(tmp_path):
    manifest, _ = _complete_acquisition_tree(tmp_path)
    source = manifest.sources[0]
    first = source.ranges[0]
    partial_ref = replace(first.retained, path=f"{first.retained.path}.partial")
    partial_stderr = replace(first.stderr, path=f"{first.stderr.path}.partial")
    partial = replace(
        first,
        state="partial",
        reason="transfer_failed",
        retained=partial_ref,
        stderr=partial_stderr,
        exit_code=1,
    )
    with pytest.raises(ValueError, match="continued after"):
        replace(
            source,
            ranges=(partial, first),
            state="refused",
            reason="transfer_failed",
            verified=None,
            header=None,
        )


def test_verified_source_ranges_must_be_the_transport_receipts(tmp_path):
    manifest, _ = _complete_acquisition_tree(tmp_path)
    source = manifest.sources[0]
    first = source.verified.ranges[0]
    alternate = _write(tmp_path, "alternate-range.bin", b"z" * first.range_file.size_bytes)
    changed_verified = replace(
        source.verified,
        ranges=(replace(first, range_file=alternate), *source.verified.ranges[1:]),
    )
    with pytest.raises(ValueError, match="transport receipts"):
        replace(source, verified=changed_verified)


def test_refused_preparation_window_cannot_retain_complete_stage_summaries(tmp_path):
    acquisition_root = tmp_path / "acquisition"
    counts_root = tmp_path / "counts"
    acquisition_root.mkdir()
    counts_root.mkdir()
    acquisition, preflight = _complete_acquisition_tree(acquisition_root)
    write_acquisition_manifest(acquisition_root, acquisition, preflight=preflight)
    preparation = _complete_empty_preparation_tree(counts_root, acquisition_root)
    window = preparation.windows[0]
    with pytest.raises(ValueError, match="stage summaries"):
        replace(
            window,
            state="refused",
            reason="invalid_input",
            retained_variants=None,
            site_dispositions=None,
        )


def test_refused_preparation_manifest_requires_a_refused_window(tmp_path):
    acquisition_root = tmp_path / "acquisition"
    counts_root = tmp_path / "counts"
    acquisition_root.mkdir()
    counts_root.mkdir()
    acquisition, preflight = _complete_acquisition_tree(acquisition_root)
    write_acquisition_manifest(acquisition_root, acquisition, preflight=preflight)
    preparation = _complete_empty_preparation_tree(counts_root, acquisition_root)
    with pytest.raises(ValueError, match="requires a refused window"):
        replace(preparation, tracks=(), status="refused", complete=False)


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


def test_acquisition_writer_rejects_rehashed_unrelated_inventory_file(tmp_path):
    manifest, preflight = _complete_acquisition_tree(tmp_path)
    unrelated = _write(tmp_path, "unrelated.bin", b"not a campaign artifact\n")
    changed = replace(
        manifest,
        files=tuple(sorted((*manifest.files, unrelated), key=lambda value: value.path)),
    )

    with pytest.raises(ValueError, match="noncanonical path"):
        write_acquisition_manifest(tmp_path, changed, preflight=preflight)
    assert not (tmp_path / "acquisition.json").exists()


@pytest.mark.parametrize(
    "role",
    (
        "retained_index",
        "metadata_stdout",
        "metadata_stderr",
        "range_stdout",
        "range_stderr",
        "sparse_source",
        "header",
        "original_records",
        "record_offsets",
    ),
)
def test_acquisition_validator_rejects_relocated_role_artifacts(tmp_path, role):
    manifest, preflight = _complete_acquisition_tree(tmp_path)
    write_acquisition_manifest(tmp_path, manifest, preflight=preflight)
    source = manifest.sources[0]
    window = manifest.windows[0]
    paths = {
        "retained_index": source.retained_index.path,
        "metadata_stdout": source.metadata.retained.path,
        "metadata_stderr": source.metadata.stderr.path,
        "range_stdout": source.ranges[0].retained.path,
        "range_stderr": source.ranges[0].stderr.path,
        "sparse_source": source.verified.sparse_path,
        "header": source.header.header.path,
        "original_records": window.raw.path,
        "record_offsets": window.offsets.path,
    }
    old = paths[role]
    new = f"{old}.moved"
    (tmp_path / old).rename(tmp_path / new)
    payload = json.loads((tmp_path / "acquisition.json").read_bytes())

    def relocate(value):
        if type(value) is dict:
            return {key: relocate(item) for key, item in value.items()}
        if type(value) is list:
            return [relocate(item) for item in value]
        return new if value == old else value

    payload = relocate(payload)
    payload["files"].sort(key=lambda value: value["path"])
    (tmp_path / "acquisition.json").write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
    )
    with pytest.raises(ValueError, match="fixed layout"):
        validate_acquisition(tmp_path)


def test_acquisition_writer_removes_its_manifest_after_postwrite_source_change(
    tmp_path, monkeypatch
):
    manifest, preflight = _complete_acquisition_tree(tmp_path)
    original = acquisition_artifacts._check_provenance
    calls = 0

    def changed(provenance, *, phase):
        nonlocal calls
        calls += 1
        if calls == 3:
            raise ValueError("imported source hash map is incomplete or changed")
        return original(provenance, phase=phase)

    monkeypatch.setattr(acquisition_artifacts, "_check_provenance", changed)
    with pytest.raises(ValueError, match="source hash"):
        write_acquisition_manifest(tmp_path, manifest, preflight=preflight)
    assert calls == 3
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


@pytest.mark.parametrize("mutation", ["tool_version", "executable_set", "sdk_set"])
def test_acquisition_validator_rejects_runtime_provenance_mutation(tmp_path, mutation):
    manifest, preflight = _complete_acquisition_tree(tmp_path)
    write_acquisition_manifest(tmp_path, manifest, preflight=preflight)
    provenance = manifest.provenance
    if mutation == "tool_version":
        versions = tuple(
            (name, "bcftools 1.22" if name == "bcftools" else value)
            for name, value in provenance.tool_versions
        )
        provenance = replace(provenance, tool_versions=versions)
    elif mutation == "executable_set":
        provenance = replace(
            provenance,
            executable_sha256=provenance.executable_sha256[:-1],
        )
    else:
        provenance = replace(
            provenance,
            sdk_source_sha256=provenance.sdk_source_sha256[:-1],
        )
    (tmp_path / "acquisition.json").write_bytes(
        encode_acquisition(replace(manifest, provenance=provenance))
    )
    with pytest.raises(ValueError, match="runtime|toolchain|SDK"):
        validate_acquisition(tmp_path)


def test_acquisition_validator_rejects_header_receipt_self_assertion(tmp_path):
    manifest, preflight = _complete_acquisition_tree(tmp_path)
    write_acquisition_manifest(tmp_path, manifest, preflight=preflight)
    source = manifest.sources[0]
    changed_source = replace(source, header=replace(source.header, sample_count=4_116))
    changed = replace(manifest, sources=(changed_source, *manifest.sources[1:]))
    (tmp_path / "acquisition.json").write_bytes(encode_acquisition(changed))
    with pytest.raises(ValueError, match="header receipt"):
        validate_acquisition(tmp_path)


def test_acquisition_validator_rejects_sparse_allocation_mutation(tmp_path):
    manifest, preflight = _complete_acquisition_tree(tmp_path)
    write_acquisition_manifest(tmp_path, manifest, preflight=preflight)
    source = manifest.sources[0]
    changed_source = replace(
        source,
        verified=replace(
            source.verified,
            allocated_size_bytes=source.verified.allocated_size_bytes + 1,
        ),
    )
    changed = replace(manifest, sources=(changed_source, *manifest.sources[1:]))
    (tmp_path / "acquisition.json").write_bytes(encode_acquisition(changed))
    with pytest.raises(ValueError, match="allocated|allocation"):
        validate_acquisition(tmp_path)


def test_acquisition_validator_binds_refused_source_child_windows(tmp_path):
    manifest, preflight = _complete_acquisition_tree(tmp_path)
    write_acquisition_manifest(tmp_path, manifest, preflight=preflight)
    source = manifest.sources[0]
    refused_source = replace(
        source,
        state="refused",
        reason="header_invalid",
        header=None,
    )
    changed = replace(
        manifest,
        sources=(refused_source, *manifest.sources[1:]),
        complete=False,
    )
    (tmp_path / "acquisition.json").write_bytes(encode_acquisition(changed))
    with pytest.raises(
        ValueError,
        match="noncanonical path|header failure is not reproduced|contradictory child",
    ):
        validate_acquisition(tmp_path)


def test_acquisition_validator_rejects_dependency_audit_byte_mutation(tmp_path):
    manifest, preflight = _complete_acquisition_tree(tmp_path)
    write_acquisition_manifest(tmp_path, manifest, preflight=preflight)
    _write(tmp_path, "inputs/cohort/dependency-audit.json", b'{"tampered":true}\n')
    with pytest.raises(ValueError, match="cohort dependency_audit hash mismatch"):
        validate_acquisition(tmp_path)


@pytest.mark.parametrize("mutation", ["argv", "output_path"])
def test_acquisition_validator_rejects_native_command_lineage_mutation(tmp_path, mutation):
    manifest, preflight = _complete_acquisition_tree(tmp_path)
    write_acquisition_manifest(tmp_path, manifest, preflight=preflight)
    window = manifest.windows[0]
    extract, query = window.native_runs
    files = manifest.files
    if mutation == "argv":
        extract = replace(
            extract,
            argv_template=tuple(
                token for token in extract.argv_template if token != "--regions-overlap"
            ),
        )
        changed_window = replace(window, native_runs=(extract, query))
    else:
        old = tmp_path / extract.stdout.path
        moved_path = f"windows/{window.window_id}.moved.bcf"
        old.rename(tmp_path / moved_path)
        moved = _ref(moved_path, (tmp_path / moved_path).read_bytes())
        extract = replace(extract, stdout=moved)
        changed_window = replace(window, native_bcf=moved, native_runs=(extract, query))
        files = tuple(moved if value.path == window.native_bcf.path else value for value in files)
    changed = replace(manifest, windows=(changed_window, *manifest.windows[1:]), files=files)
    (tmp_path / "acquisition.json").write_bytes(encode_acquisition(changed))
    with pytest.raises(ValueError, match="argv|fixed layout"):
        validate_acquisition(tmp_path)


@pytest.mark.parametrize("mutation", ["false_reason", "false_artifact_reason", "raw_count"])
def test_refused_acquisition_revalidates_known_window_evidence(tmp_path, mutation):
    manifest, preflight = _complete_acquisition_tree(tmp_path, one_record=True)
    write_acquisition_manifest(tmp_path, manifest, preflight=preflight)
    window = manifest.windows[0]
    refused = replace(
        window,
        state="refused",
        reason="artifact_mismatch" if mutation == "false_artifact_reason" else "native_mismatch",
        raw_records=2 if mutation == "raw_count" else window.raw_records,
        native_records=None,
    )
    windows = (refused, *manifest.windows[1:])
    ledger = _rows_raw(
        ("window_id", "chrom", "state", "reason", "raw_records", "native_records"),
        _window_rows(windows, "native_records"),
    )
    ledger_ref = _write(tmp_path, "windows.tsv", ledger)
    changed = replace(
        manifest,
        windows=windows,
        files=_replace_file(manifest.files, ledger_ref),
        complete=False,
    )
    (tmp_path / "acquisition.json").write_bytes(encode_acquisition(changed))
    with pytest.raises(ValueError, match="refused native (evidence|failure)|record count"):
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


def test_preparation_writer_rejects_rehashed_unrelated_inventory_file(tmp_path):
    acquisition_root = tmp_path / "acquisition"
    counts_root = tmp_path / "counts"
    acquisition_root.mkdir()
    counts_root.mkdir()
    acquisition, preflight = _complete_acquisition_tree(acquisition_root)
    write_acquisition_manifest(acquisition_root, acquisition, preflight=preflight)
    preparation = _complete_empty_preparation_tree(counts_root, acquisition_root)
    unrelated = _write(counts_root, "work/unrelated.part", b"not a role artifact\n")
    changed = replace(
        preparation,
        files=tuple(sorted((*preparation.files, unrelated), key=lambda value: value.path)),
    )

    with pytest.raises(ValueError, match="noncanonical path"):
        write_preparation_manifest(counts_root, changed, acquisition_root=acquisition_root)
    assert not (counts_root / "manifest.json").exists()


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


def test_preparation_writer_removes_its_manifest_after_failed_readback(
    tmp_path, monkeypatch
):
    acquisition_root = tmp_path / "acquisition"
    counts_root = tmp_path / "counts"
    acquisition_root.mkdir()
    counts_root.mkdir()
    acquisition, preflight = _complete_acquisition_tree(acquisition_root)
    write_acquisition_manifest(acquisition_root, acquisition, preflight=preflight)
    preparation = _complete_empty_preparation_tree(counts_root, acquisition_root)
    original = preparation_artifacts._write_exclusive

    def changed(path, raw):
        original(path, raw)
        path.write_bytes(b"{}\n")

    monkeypatch.setattr(preparation_artifacts, "_write_exclusive", changed)
    with pytest.raises(ValueError, match="readback"):
        write_preparation_manifest(
            counts_root, preparation, acquisition_root=acquisition_root
        )
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


@pytest.mark.parametrize("mutation", ["edge", "population", "audit"])
def test_preparation_validator_rejects_rehashed_dependency_mutation(tmp_path, mutation):
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
    if mutation == "edge":
        document["edges"][0] = ["CDX", "Japanese"]
    elif mutation == "population":
        document["populations"] = sorted(
            "population-renamed" if value == "population-73" else value
            for value in document["populations"]
        )
    else:
        document["audit_sha256"] = "0" * 64
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


@pytest.mark.parametrize("mutation", ["count_cell", "region_label", "variant_window"])
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
    elif mutation == "region_label":
        replacements = {}
        changed_tracks = []
        for track in preparation.tracks:
            relative = track.table.path
            path = counts_root / relative
            lines = path.read_text().splitlines()
            changed_lines = [lines[0]]
            for line in lines[1:]:
                cells = line.split("\t")
                cells[3] = "forged-region"
                changed_lines.append("\t".join(cells))
            path.write_text("\n".join(changed_lines) + "\n")
            reference = _ref(relative, path.read_bytes())
            replacements[relative] = reference
            changed_tracks.append(replace(track, table=reference))
        tracks = tuple(changed_tracks)
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
    if mutation == "region_label":
        files = tuple(replacements.get(value.path, value) for value in preparation.files)
    else:
        files = tuple(reference if value.path == relative else value for value in preparation.files)
    changed = replace(preparation, tracks=tracks, files=files)
    (counts_root / "manifest.json").write_bytes(encode_preparation(changed))
    with pytest.raises(
        ValueError,
        match="parent genotype evidence|stage-window summary|frozen acquisition",
    ):
        validate_preparation(counts_root, acquisition_root=acquisition_root)
