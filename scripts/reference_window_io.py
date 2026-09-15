#!/usr/bin/env python3
"""Acquire and read bounded reference bytes (reference acquisition design §4.1)."""

from __future__ import annotations

import hashlib
import os
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from genomeos.validation.reference_acquisition_types import (
    ArtifactRef,
    RangeReceipt,
    VerifiedRange,
    VerifiedSource,
)
from genomeos.validation.reference_byte_plan import ByteRange, SourceBytePlan
from genomeos.validation.reference_tbi import VirtualChunk
from genomeos.validation.reference_vcf_tokens import (
    BGZF_BLOCK_LIMIT_BYTES,
    HEADER_LIMIT_BYTES,
    RECORD_LIMIT_BYTES,
    HeaderEvidence,
    SourceRecord,
    decode_bgzf_member,
    parse_record,
    site_disposition,
)
from genomeos.validation.reference_window_types import PublicObject, ReferenceWindow
from scripts.reference_io_common import (
    SPARSE_ALLOCATION_SLACK_BYTES,
    TRANSFER_PIECE_BYTES,
    _allocated,
    _crc32c_b64,
    _destination,
    _existing,
    _md5_b64,
    _require,
    _run_process,
    _validate_artifact,
    validate_verified_source,
)
from scripts.reference_native_io import (
    extract_native,
    iter_native_tokens,
    native_called_totals,
    query_native_tokens,
    read_native_totals,
)

RANGE_TIMEOUT_SECONDS = 1_800
STDERR_LIMIT_BYTES = 1_048_576
DECODED_WINDOW_LIMIT_BYTES = 2_147_483_648
RECORDS_PER_WINDOW_LIMIT = 1_000_000
_EOF = bytes.fromhex("1f8b08040000000000ff0600424302001b0003000000000000000000")

__all__ = [
    "extract_native",
    "fetch_range",
    "iter_native_tokens",
    "iter_original_records",
    "native_called_totals",
    "query_native_tokens",
    "read_native_totals",
    "stage_sparse",
    "validate_verified_source",
]


def fetch_range(
    source: PublicObject,
    byte_range: ByteRange,
    *,
    wrapper: Path,
    artifact_root: Path,
    destination: Path,
) -> RangeReceipt:
    """Fetch one generation-pinned byte range through one bounded wrapper invocation."""
    _require(type(source) is PublicObject and type(byte_range) is ByteRange, "invalid range input")
    _require(byte_range.last < source.size_bytes, "byte range is outside source")
    _require(isinstance(wrapper, Path) and wrapper.is_file() and not wrapper.is_symlink(), "invalid wrapper")
    requested = byte_range.last - byte_range.first + 1
    stderr = Path(f"{destination}.stderr")
    result = _run_process(
        [
            sys.executable,
            str(wrapper),
            "run",
            "storage",
            "cat",
            f"--range={byte_range.first}-{byte_range.last}",
            f"{source.uri}#{source.generation}",
        ],
        artifact_root=artifact_root,
        stdout_path=destination,
        stderr_path=stderr,
        stdout_limit=requested,
        stderr_limit=STDERR_LIMIT_BYTES,
        timeout=RANGE_TIMEOUT_SECONDS,
    )
    if result.stdout_limit_exceeded or result.stderr_limit_exceeded:
        state, reason = "refused", "limit_exceeded"
    elif result.timed_out:
        state, reason = "partial", "timeout"
    elif result.exit_code != 0:
        state, reason = "partial", "transfer_failed"
    elif result.stdout.size_bytes != requested:
        state, reason = "partial", "size_mismatch"
    else:
        state, reason = "verified", None
    return RangeReceipt(
        "chr" + source.uri.rsplit(".chr", 1)[1].split(".", 1)[0],
        source.generation,
        byte_range.first,
        byte_range.last,
        requested,
        result.stdout.size_bytes,
        1,
        state,
        reason,
        result.stdout.sha256,
        result.stdout,
        result.stderr,
        result.exit_code,
        result.stdout_limit_exceeded,
        result.stderr_limit_exceeded,
    )


def stage_sparse(
    source: SourceBytePlan,
    receipts: tuple[RangeReceipt, ...],
    *,
    artifact_root: Path,
    index: ArtifactRef,
    sparse_path: str,
) -> VerifiedSource:
    """Stage a sparse source only from exact verified range and index evidence."""
    _require(type(source) is SourceBytePlan and source.receipt.state == "verified", "invalid source plan")
    _require(type(receipts) is tuple, "range receipts must be a tuple")
    expected = tuple((value.first, value.last) for value in source.merged_vcf_ranges)
    actual = tuple((value.first, value.last) for value in receipts)
    _require(actual == expected, "range receipts do not match reviewed plan")
    _require(
        all(
            type(value) is RangeReceipt
            and value.state == "verified"
            and value.chrom == source.source.chrom
            and value.generation == source.source.vcf.generation
            and value.retained is not None
            for value in receipts
        ),
        "range receipts are not verified",
    )
    index_path = _validate_artifact(artifact_root, index)
    _require(index.path == f"{sparse_path}.tbi", "retained index is not the sparse-file sibling")
    _require(index.size_bytes == source.source.tbi.size_bytes, "retained index size mismatch")
    _require(index.sha256 == source.receipt.sha256, "retained index SHA mismatch")
    _require(_md5_b64(index_path) == source.source.tbi.md5_b64, "retained index MD5 mismatch")
    _require(_crc32c_b64(index_path) == source.source.tbi.crc32c_b64, "retained index CRC32C mismatch")

    retained: list[tuple[RangeReceipt, Path]] = []
    for receipt in receipts:
        assert receipt.retained is not None
        path = _validate_artifact(artifact_root, receipt.retained)
        retained.append((receipt, path))
    sparse, sparse_relative = _destination(artifact_root, sparse_path)
    with sparse.open("xb") as output:
        os.chmod(sparse, 0o600)
        output.truncate(source.source.vcf.size_bytes)
        for receipt, path in retained:
            output.seek(receipt.first)
            with path.open("rb") as handle:
                while chunk := handle.read(TRANSFER_PIECE_BYTES):
                    output.write(chunk)
        output.flush()
        os.fsync(output.fileno())
    allocated = _allocated(sparse)
    payload_bytes = sum(value.received_bytes for value in receipts)
    _require(allocated <= payload_bytes + SPARSE_ALLOCATION_SLACK_BYTES, "sparse allocation limit exceeded")
    with sparse.open("rb") as staged:
        for receipt, path in retained:
            staged.seek(receipt.first)
            with path.open("rb") as handle:
                remaining = receipt.received_bytes
                while remaining:
                    expected_raw = handle.read(min(TRANSFER_PIECE_BYTES, remaining))
                    actual = staged.read(len(expected_raw))
                    _require(actual == expected_raw and bool(actual), "sparse extent mismatch")
                    remaining -= len(actual)
        staged.seek(source.source.vcf.size_bytes - len(_EOF))
        _require(staged.read(len(_EOF)) == _EOF, "canonical BGZF EOF marker is missing")
    for _, path in retained:
        os.chmod(path, 0o400)
    os.chmod(index_path, 0o400)
    os.chmod(sparse, 0o400)
    verified_ranges = tuple(
        VerifiedRange(receipt.first, receipt.last, receipt.retained)
        for receipt in receipts
        if receipt.retained is not None
    )
    return VerifiedSource(
        source.source,
        verified_ranges,
        sparse_relative,
        index,
        source.source.vcf.size_bytes,
        allocated,
        False,
    )


@dataclass
class _RangeHandle:
    evidence: VerifiedRange
    handle: BinaryIO
    identity: tuple[int, int, int, int]


def _file_identity(path: Path) -> tuple[int, int, int, int]:
    status = path.stat()
    return status.st_dev, status.st_ino, status.st_size, status.st_mtime_ns


def _handle_identity(handle: BinaryIO) -> tuple[int, int, int, int]:
    status = os.fstat(handle.fileno())
    return status.st_dev, status.st_ino, status.st_size, status.st_mtime_ns


def _open_verified_range(artifact_root: Path, evidence: VerifiedRange) -> _RangeHandle:
    path = _existing(artifact_root, evidence.range_file)
    identity = _file_identity(path)
    handle = path.open("rb")
    _require(_handle_identity(handle) == identity, "retained range changed while opening")
    digest = hashlib.sha256()
    size = 0
    while chunk := handle.read(TRANSFER_PIECE_BYTES):
        digest.update(chunk)
        size += len(chunk)
    _require(
        (size, digest.hexdigest()) == (evidence.range_file.size_bytes, evidence.range_file.sha256),
        "retained range identity mismatch",
    )
    _require(_file_identity(path) == identity, "retained range changed during verification")
    handle.seek(0)
    return _RangeHandle(evidence, handle, identity)


def _read_covered(handles: list[_RangeHandle], first: int, size: int) -> bytes:
    _require(size >= 0, "invalid source read size")
    last = first + size - 1
    match = next(
        (value for value in handles if value.evidence.first <= first and last <= value.evidence.last),
        None,
    )
    _require(match is not None, "coverage_gap")
    match.handle.seek(first - match.evidence.first)
    raw = match.handle.read(size)
    _require(len(raw) == size, "covered source read was truncated")
    return raw


def _bgzf_at(handles: list[_RangeHandle], physical: int) -> tuple[bytes, int]:
    fixed = _read_covered(handles, physical, 12)
    _require(fixed[:3] == b"\x1f\x8b\x08" and fixed[3] == 4, "invalid BGZF framing")
    extra_length = int.from_bytes(fixed[10:12], "little")
    extra = _read_covered(handles, physical + 12, extra_length)
    offsets = 0
    block_sizes: list[int] = []
    while offsets < len(extra):
        _require(offsets + 4 <= len(extra), "invalid BGZF extra framing")
        length = int.from_bytes(extra[offsets + 2 : offsets + 4], "little")
        _require(offsets + 4 + length <= len(extra), "invalid BGZF extra framing")
        if extra[offsets : offsets + 2] == b"BC":
            _require(length == 2, "invalid BGZF BC subfield")
            block_sizes.append(int.from_bytes(extra[offsets + 4 : offsets + 6], "little") + 1)
        offsets += 4 + length
    _require(len(block_sizes) == 1 and block_sizes[0] <= BGZF_BLOCK_LIMIT_BYTES, "invalid BGZF block size")
    raw = _read_covered(handles, physical, block_sizes[0])
    return decode_bgzf_member(raw), len(raw)


def _source_header(handles: list[_RangeHandle]) -> bytes:
    physical = 0
    raw = bytearray()
    while True:
        payload, compressed_size = _bgzf_at(handles, physical)
        _require(len(raw) + len(payload) <= HEADER_LIMIT_BYTES, "header limit exceeded")
        raw.extend(payload)
        marker = 0 if raw.startswith(b"#CHROM") else raw.find(b"\n#CHROM") + 1
        if marker >= 0 and raw[marker:].startswith(b"#CHROM"):
            end = raw.find(b"\n", marker)
            if end >= 0:
                return bytes(raw[: end + 1])
        _require(payload, "header is absent before BGZF EOF")
        physical += compressed_size


def _merge_virtual(chunks: tuple[VirtualChunk, ...]) -> tuple[tuple[int, int], ...]:
    intervals = sorted((chunk.begin, chunk.end) for chunk in chunks)
    merged: list[tuple[int, int]] = []
    for begin, end in intervals:
        if merged and begin <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((begin, end))
    return tuple(merged)


def _virtual_pieces(handles: list[_RangeHandle], begin: int, end: int) -> Iterator[tuple[bytes, int, int]]:
    _require(begin < end, "empty virtual chunk")
    end_physical, end_low = end >> 16, end & 0xFFFF
    physical = begin >> 16
    first_low = begin & 0xFFFF
    first = True
    while physical < end_physical or (physical == end_physical and end_low > 0):
        payload, compressed_size = _bgzf_at(handles, physical)
        lower = first_low if first else 0
        upper = end_low if physical == end_physical else len(payload)
        _require(lower <= upper <= len(payload), "invalid virtual offset")
        if lower < upper:
            yield payload[lower:upper], physical, lower
        first = False
        if physical == end_physical:
            break
        physical += compressed_size
        _require(physical <= end_physical, "virtual chunk ends inside an unplanned block")


def iter_original_records(
    verified: VerifiedSource,
    plan: SourceBytePlan,
    window: ReferenceWindow,
    header: HeaderEvidence,
    *,
    artifact_root: Path,
    raw_destination: Path,
    offsets_destination: Path,
) -> Iterator[SourceRecord]:
    """Yield exact POS-selected original records using only retained range files."""
    validate_verified_source(verified, plan, artifact_root=artifact_root)
    _require(type(window) is ReferenceWindow and type(header) is HeaderEvidence, "invalid raw reader inputs")
    matching = tuple(value for value in plan.windows if value.window_id == window.window_id)
    _require(len(matching) == 1 and window.chrom == plan.source.chrom, "window plan identity mismatch")
    window_plan = matching[0]
    raw_path, _ = _destination(artifact_root, raw_destination)
    offset_path, _ = _destination(artifact_root, offsets_destination)
    handles: list[_RangeHandle] = []
    try:
        for value in verified.ranges:
            handles.append(_open_verified_range(artifact_root, value))
        _require(
            hashlib.sha256(_source_header(handles)).hexdigest() == header.raw_sha256,
            "header evidence does not match source bytes",
        )
        decoded = 0
        ordinal = 0
        previous_position = 0
        seen_offsets: set[int] = set()
        seen_keys: set[tuple[str, int, str, str]] = set()
        with raw_path.open("xb") as raw_output, offset_path.open("xb") as offset_output:
            os.chmod(raw_path, 0o600)
            os.chmod(offset_path, 0o600)
            offset_output.write(b"ordinal\tsource_virtual_offset\traw_sha256\n")
            for begin, end in _merge_virtual(window_plan.chunks):
                record_bytes = bytearray()
                record_offset: int | None = None
                for piece, physical, low in _virtual_pieces(handles, begin, end):
                    decoded += len(piece)
                    _require(decoded <= DECODED_WINDOW_LIMIT_BYTES, "decoded window limit exceeded")
                    piece_offset = 0
                    while piece_offset < len(piece):
                        if record_offset is None:
                            record_offset = (physical << 16) | (low + piece_offset)
                        newline = piece.find(b"\n", piece_offset)
                        upper = len(piece) if newline < 0 else newline + 1
                        _require(
                            len(record_bytes) + upper - piece_offset <= RECORD_LIMIT_BYTES,
                            "record limit exceeded",
                        )
                        record_bytes.extend(piece[piece_offset:upper])
                        piece_offset = upper
                        if newline < 0:
                            continue
                        line = bytes(record_bytes)
                        virtual_offset = record_offset
                        record_bytes.clear()
                        record_offset = None
                        _require(virtual_offset not in seen_offsets, "duplicate source virtual offset")
                        seen_offsets.add(virtual_offset)
                        record = parse_record(line, source_virtual_offset=virtual_offset, header=header)
                        disposition = site_disposition(record, window)
                        if disposition == "outside_pos":
                            continue
                        _require(record.pos1 >= previous_position, "records are not position-sorted")
                        previous_position = record.pos1
                        key = (record.chrom, record.pos1, record.ref, record.alt)
                        _require(key not in seen_keys, "duplicate source variant key")
                        seen_keys.add(key)
                        ordinal += 1
                        _require(ordinal <= RECORDS_PER_WINDOW_LIMIT, "window record limit exceeded")
                        raw_output.write(line)
                        offset_output.write(
                            f"{ordinal - 1}\t{virtual_offset}\t{record.raw_sha256}\n".encode()
                        )
                        yield record
                _require(not record_bytes and record_offset is None, "virtual chunk ends inside a record")
            raw_output.flush()
            offset_output.flush()
            os.fsync(raw_output.fileno())
            os.fsync(offset_output.fileno())
    finally:
        for value in handles:
            path = Path(value.handle.name)
            descriptor_identity = _handle_identity(value.handle)
            value.handle.close()
            _require(
                descriptor_identity == value.identity and _file_identity(path) == value.identity,
                "retained range changed during read",
            )
