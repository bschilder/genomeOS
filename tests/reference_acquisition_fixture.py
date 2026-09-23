"""Synthetic acquisition fixtures for the frozen reference-window plan (#255)."""

from __future__ import annotations

import base64
import gzip
import hashlib
import platform
import shutil
import struct
from pathlib import Path

import numpy as np

from genomeos.validation.reference_acquisition_types import (
    ArtifactRef,
    RangeReceipt,
    RetainedIndex,
    ReviewReceipt,
    VerifiedSource,
)
from genomeos.validation.reference_byte_plan import (
    IndexReceipt,
    SourceBytePlan,
    assemble_preflight,
    crc32c,
    encode_preflight,
    fixed_vcf_ranges,
    merge_byte_ranges,
    plan_window,
)
from genomeos.validation.reference_tbi import parse_tbi
from genomeos.validation.reference_vcf_tokens import HeaderEvidence, parse_header
from genomeos.validation.reference_window_manifest import (
    encode_manifest,
    encode_window_config,
    windows_tsv,
)
from genomeos.validation.reference_window_types import (
    AUTOSOMES,
    BIT_GENERATOR,
    CONFIG_SCHEMA_VERSION,
    CONTIG_EVIDENCE,
    COUNT_CONTRACT,
    DRAW_METHOD,
    EOF_BYTES,
    EXCLUSION_CHROM,
    EXCLUSION_END0,
    EXCLUSION_START0,
    HEADER_PREFIX_BYTES,
    MANIFEST_SCHEMA_VERSION,
    MAX_TRANSFER_BYTES,
    SEED,
    SOURCE_BUCKET,
    SOURCE_EVIDENCE_STATUS,
    SOURCE_PREFIX,
    STRATA,
    WIDTH,
    GenomicInterval,
    Provenance,
    PublicObject,
    ReferenceWindow,
    SourcePair,
    StartRun,
    WindowConfig,
    WindowManifest,
)
from genomeos.validation.reference_windows import select_reference_windows
from tests.reference_tbi_fixture import synthetic_bgzf

NATIVE_FIXTURES = Path(__file__).parent / "fixtures" / "reference_acquisition" / "native"


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _tbi(chrom: str) -> bytes:
    name = f"{chrom}\0".encode("ascii")
    payload = (
        b"TBI\x01" + struct.pack("<8i", 1, 2, 1, 2, 0, 35, 0, len(name)) + name + struct.pack("<2i", 0, 0)
    )
    return synthetic_bgzf(payload)


def _object(chrom: str, suffix: str, generation: str, raw: bytes | None) -> PublicObject:
    uri = f"gs://{SOURCE_BUCKET}/{SOURCE_PREFIX}{chrom}.vcf.bgz{suffix}"
    if raw is None:
        return PublicObject(uri, generation, 2_097_152, _b64(bytes(16)), _b64(bytes(4)))
    return PublicObject(
        uri,
        generation,
        len(raw),
        _b64(hashlib.md5(raw).digest()),
        _b64(crc32c(raw).to_bytes(4, "big")),
    )


def synthetic_preflight_case(*, source_size_bytes: int = 2_097_152) -> tuple[
    WindowManifest, bytes, bytes, tuple[RetainedIndex, ...], ReviewReceipt
]:
    """Build a strict 22-source, 66-window preflight without network or native tools."""
    lengths = tuple((chrom, 100_000) for chrom in AUTOSOMES)
    config = WindowConfig(
        CONFIG_SCHEMA_VERSION,
        WIDTH,
        STRATA,
        SEED,
        np.__version__,
        BIT_GENERATOR,
        DRAW_METHOD,
        GenomicInterval(EXCLUSION_CHROM, EXCLUSION_START0, EXCLUSION_END0),
        MAX_TRANSFER_BYTES,
        HEADER_PREFIX_BYTES,
        EOF_BYTES,
    )
    windows = select_reference_windows(lengths, config)
    window_raw = windows_tsv(windows)
    config_sha = hashlib.sha256(encode_window_config(config)).hexdigest()
    manifest_provenance = Provenance(
        data_version="synthetic-reference-acquisition-v1",
        evidence_kind="synthetic_fixture",
        input_sha256=tuple(
            sorted(
                (
                    key,
                    config_sha if key == "selection_config" else hashlib.sha256(key.encode()).hexdigest(),
                )
                for key in ("contigs", "selection_config", "source_audit", "source_metadata")
            )
        ),
        source_revision="1" * 40,
        imported_source_sha256=tuple(
            (path, hashlib.sha256(path.encode()).hexdigest())
            for path in sorted(
                (
                    "genomeos/validation/reference_window_manifest.py",
                    "genomeos/validation/reference_window_types.py",
                    "genomeos/validation/reference_windows.py",
                    "scripts/freeze_reference_windows.py",
                )
            )
        ),
        python_version=platform.python_version(),
        source_audit_locator="synthetic-audit.md",
    )
    raw_indexes = tuple(_tbi(chrom) for chrom in AUTOSOMES)
    if source_size_bytes < 1:
        raise ValueError("source_size_bytes must be positive")
    source_payloads = tuple(
        None
        if source_size_bytes == 2_097_152
        else (f"synthetic-{chrom}\n".encode().ljust(source_size_bytes, b"x"))
        for chrom in AUTOSOMES
    )
    sources = tuple(
        SourcePair(
            chrom,
            _object(chrom, "", str(10_000 + index), source_payloads[index]),
            _object(chrom, ".tbi", str(20_000 + index), raw_indexes[index]),
        )
        for index, chrom in enumerate(AUTOSOMES)
    )
    manifest = WindowManifest(
        MANIFEST_SCHEMA_VERSION,
        config,
        lengths,
        sources,
        windows,
        manifest_provenance,
        hashlib.sha256(window_raw).hexdigest(),
        ("chrX", "chrY"),
        CONTIG_EVIDENCE,
        SOURCE_EVIDENCE_STATUS,
        COUNT_CONTRACT,
        False,
        False,
    )
    manifest_raw = encode_manifest(manifest)
    manifest_sha = hashlib.sha256(manifest_raw).hexdigest()
    imported = tuple(
        (path, hashlib.sha256(path.encode()).hexdigest())
        for path in sorted(
            (
                "genomeos/validation/reference_byte_plan.py",
                "genomeos/validation/reference_tbi.py",
                "genomeos/validation/reference_window_manifest.py",
                "genomeos/validation/reference_window_types.py",
                "genomeos/validation/reference_windows.py",
                "scripts/gcloud_repo.py",
                "scripts/preflight_reference_windows.py",
            )
        )
    )
    preflight_provenance = Provenance(
        data_version=manifest.provenance.data_version,
        evidence_kind=manifest.provenance.evidence_kind,
        input_sha256=(("manifest", manifest_sha), ("windows", manifest.windows_sha256)),
        source_revision="2" * 40,
        imported_source_sha256=imported,
        python_version=platform.python_version(),
        source_audit_locator=manifest.provenance.source_audit_locator,
    )
    plans = []
    for source, raw in zip(sources, raw_indexes, strict=True):
        parsed = parse_tbi(raw, expected_chrom=source.chrom, vcf_size_bytes=source.vcf.size_bytes)
        planned_windows = tuple(
            plan_window(parsed, window, source_size_bytes=source.vcf.size_bytes)
            for window in windows
            if window.chrom == source.chrom
        )
        required = fixed_vcf_ranges(
            source.vcf.size_bytes,
            header_prefix_bytes=config.header_prefix_bytes,
            eof_bytes=config.eof_bytes,
        ) + tuple(byte_range for window in planned_windows for byte_range in window.ranges)
        plans.append(
            SourceBytePlan(
                source,
                IndexReceipt(
                    source.chrom,
                    "verified",
                    None,
                    1,
                    1,
                    1,
                    len(raw),
                    hashlib.sha256(raw).hexdigest(),
                ),
                planned_windows,
                merge_byte_ranges(required, source_size_bytes=source.vcf.size_bytes),
            )
        )
    preflight = assemble_preflight(
        manifest,
        tuple(plans),
        manifest_sha256=manifest_sha,
        provenance=preflight_provenance,
    )
    preflight_raw = encode_preflight(preflight)
    retained = tuple(RetainedIndex(chrom, raw) for chrom, raw in zip(AUTOSOMES, raw_indexes, strict=True))
    review = ReviewReceipt(
        "reference_preflight_review_v1",
        manifest_sha,
        hashlib.sha256(preflight_raw).hexdigest(),
        preflight.provenance.source_revision,
        preflight.provenance.imported_source_sha256,
        "reviews/reference-preflight.md",
        "f" * 64,
        "accepted",
    )
    return manifest, manifest_raw, preflight_raw, retained, review


def synthetic_window(chrom: str, *, start0: int = 100, end0: int = 10_100) -> ReferenceWindow:
    """Construct the plan's fixed-width toy first-stratum window."""
    if end0 - start0 != WIDTH or not 0 <= start0 <= 23_333:
        raise ValueError("synthetic window must be a legal fixed-width first-stratum window")
    return ReferenceWindow(
        f"{chrom}-s1",
        chrom,
        1,
        0,
        33_333,
        start0,
        end0,
        (StartRun(0, 23_333),),
        23_334,
        start0,
    )


def _later_window(chrom: str, stratum: int, lower: int, upper: int) -> ReferenceWindow:
    start = lower
    return ReferenceWindow(
        f"{chrom}-s{stratum}",
        chrom,
        stratum,
        lower,
        upper,
        start,
        start + WIDTH,
        (StartRun(lower, upper - WIDTH),),
        upper - lower - WIDTH + 1,
        0,
    )


def _artifact(root: Path, path: str) -> ArtifactRef:
    raw = (root / path).read_bytes()
    return ArtifactRef(path, len(raw), hashlib.sha256(raw).hexdigest())


def synthetic_coverage_case(
    artifact_root: Path,
) -> tuple[SourceBytePlan, VerifiedSource, ReferenceWindow, HeaderEvidence]:
    """Stage the checked-in synthetic source using real range receipt evidence."""
    from scripts.reference_window_io import stage_sparse

    raw_vcf = (NATIVE_FIXTURES / "synthetic.vcf.bgz").read_bytes()
    raw_tbi = (NATIVE_FIXTURES / "synthetic.vcf.bgz.tbi").read_bytes()
    artifact_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    source = SourcePair(
        "chr1",
        _object("chr1", "", "100", raw_vcf),
        _object("chr1", ".tbi", "200", raw_tbi),
    )
    index = parse_tbi(raw_tbi, expected_chrom="chr1", vcf_size_bytes=len(raw_vcf))
    window = synthetic_window("chr1")
    windows = (
        plan_window(index, window, source_size_bytes=len(raw_vcf)),
        plan_window(
            index,
            _later_window("chr1", 2, 33_333, 66_666),
            source_size_bytes=len(raw_vcf),
        ),
        plan_window(
            index,
            _later_window("chr1", 3, 66_666, 1_000_000),
            source_size_bytes=len(raw_vcf),
        ),
    )
    required = fixed_vcf_ranges(
        len(raw_vcf),
        header_prefix_bytes=HEADER_PREFIX_BYTES,
        eof_bytes=EOF_BYTES,
    ) + tuple(value for planned in windows for value in planned.ranges)
    merged = merge_byte_ranges(required, source_size_bytes=len(raw_vcf))
    plan = SourceBytePlan(
        source,
        IndexReceipt("chr1", "verified", None, 1, 1, 1, len(raw_tbi), hashlib.sha256(raw_tbi).hexdigest()),
        windows,
        merged,
    )

    (artifact_root / "ranges").mkdir()
    (artifact_root / "sources" / "chr1").mkdir(parents=True)
    index_path = artifact_root / "sources" / "chr1" / "INCOMPLETE.original.vcf.bgz.tbi"
    shutil.copyfile(NATIVE_FIXTURES / "synthetic.vcf.bgz.tbi", index_path)
    index_ref = _artifact(artifact_root, "sources/chr1/INCOMPLETE.original.vcf.bgz.tbi")
    receipts = []
    for byte_range in merged:
        relative = f"ranges/chr1-{byte_range.first}-{byte_range.last}.bin"
        (artifact_root / relative).write_bytes(raw_vcf[byte_range.first : byte_range.last + 1])
        body = _artifact(artifact_root, relative)
        stderr_path = relative + ".stderr"
        (artifact_root / stderr_path).write_bytes(b"")
        stderr = _artifact(artifact_root, stderr_path)
        receipts.append(
            RangeReceipt(
                "chr1",
                source.vcf.generation,
                byte_range.first,
                byte_range.last,
                byte_range.last - byte_range.first + 1,
                body.size_bytes,
                1,
                "verified",
                None,
                body.sha256,
                body,
                stderr,
                0,
                False,
                False,
            )
        )
    verified = stage_sparse(
        plan,
        tuple(receipts),
        artifact_root=artifact_root,
        index=index_ref,
        sparse_path="sources/chr1/INCOMPLETE.original.vcf.bgz",
    )
    expanded = gzip.decompress(raw_vcf)
    header_end = expanded.index(b"#CHROM")
    header_end = expanded.index(b"\n", header_end) + 1
    header = parse_header(
        expanded[:header_end],
        expected_contigs=(("chr1", 1_000_000),),
        source_chrom="chr1",
        expected_samples=("s1", "s2"),
    )
    return plan, verified, window, header
