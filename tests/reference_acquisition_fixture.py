"""Synthetic acquisition fixtures for the frozen reference-window plan (#255)."""

from __future__ import annotations

import base64
import hashlib
import platform
import struct

import numpy as np

from genomeos.validation.reference_acquisition_types import RetainedIndex, ReviewReceipt
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
    SourcePair,
    WindowConfig,
    WindowManifest,
)
from genomeos.validation.reference_windows import select_reference_windows
from tests.reference_tbi_fixture import synthetic_bgzf


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _tbi(chrom: str) -> bytes:
    name = f"{chrom}\0".encode("ascii")
    payload = (
        b"TBI\x01"
        + struct.pack("<8i", 1, 2, 1, 2, 0, 35, 0, len(name))
        + name
        + struct.pack("<2i", 0, 0)
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


def synthetic_preflight_case(
) -> tuple[WindowManifest, bytes, bytes, tuple[RetainedIndex, ...], ReviewReceipt]:
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
    sources = tuple(
        SourcePair(
            chrom,
            _object(chrom, "", str(10_000 + index), None),
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
