"""Read qualified records from reviewed reference ranges (design §4.1)."""

from __future__ import annotations

import hashlib
import os
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from genomeos.validation.reference_acquisition_types import (
    ArtifactRef,
    HeaderReceipt,
    VerifiedRange,
    VerifiedSource,
)
from genomeos.validation.reference_byte_plan import SourceBytePlan
from genomeos.validation.reference_tbi import VirtualChunk
from genomeos.validation.reference_vcf_tokens import (
    BGZF_BLOCK_LIMIT_BYTES,
    HEADER_LIMIT_BYTES,
    RECORD_LIMIT_BYTES,
    HeaderEvidence,
    SourceRecord,
    decode_bgzf_member,
    parse_header,
    parse_record,
    site_disposition,
)
from genomeos.validation.reference_window_types import ReferenceWindow
from scripts.reference_io_common import (
    TRANSFER_PIECE_BYTES,
    _artifact,
    _destination,
    _existing,
    _require,
    _validate_artifact,
    fsync_artifact,
    validate_verified_source,
)

DECODED_WINDOW_LIMIT_BYTES = 2_147_483_648
RECORDS_PER_WINDOW_LIMIT = 1_000_000

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
        _require(len(raw) + len(payload) <= HEADER_LIMIT_BYTES, "limit_exceeded")
        raw.extend(payload)
        marker = 0 if raw.startswith(b"#CHROM") else raw.find(b"\n#CHROM") + 1
        if marker >= 0 and raw[marker:].startswith(b"#CHROM"):
            end = raw.find(b"\n", marker)
            if end >= 0:
                return bytes(raw[: end + 1])
        _require(payload, "header is absent before BGZF EOF")
        physical += compressed_size


def read_source_header(
    verified: VerifiedSource,
    plan: SourceBytePlan,
    *,
    artifact_root: Path,
    expected_contigs: tuple[tuple[str, int], ...],
    expected_samples: tuple[str, ...],
    destination: Path,
) -> tuple[HeaderEvidence, HeaderReceipt]:
    """Read, qualify, and persist one exact source header from verified ranges."""
    raw, evidence = load_source_header(
        verified,
        plan,
        artifact_root=artifact_root,
        expected_contigs=expected_contigs,
        expected_samples=expected_samples,
    )
    path, relative = _destination(artifact_root, destination)
    with path.open("xb") as output:
        os.chmod(path, 0o600)
        output.write(raw)
        fsync_artifact(output)
    artifact = _artifact(artifact_root, path, relative)
    sample_bytes = "".join(f"{sample}\n" for sample in evidence.samples).encode()
    receipt = HeaderReceipt(
        artifact,
        hashlib.sha256(sample_bytes).hexdigest(),
        len(evidence.samples),
        "exact_metadata_plus_control",
        "frozen_manifest_assembly_and_lengths",
        "verified",
    )
    return evidence, receipt


def load_source_header(
    verified: VerifiedSource,
    plan: SourceBytePlan,
    *,
    artifact_root: Path,
    expected_contigs: tuple[tuple[str, int], ...],
    expected_samples: tuple[str, ...],
) -> tuple[bytes, HeaderEvidence]:
    """Read and qualify a retained source header without creating an artifact."""
    validate_verified_source(verified, plan, artifact_root=artifact_root)
    handles = [_open_verified_range(artifact_root, value) for value in verified.ranges]
    try:
        raw = _source_header(handles)
    finally:
        for value in handles:
            path = Path(value.handle.name)
            identity = _handle_identity(value.handle)
            value.handle.close()
            _require(
                identity == value.identity and _file_identity(path) == value.identity,
                "retained range changed during header read",
            )
    return raw, parse_header(
        raw,
        expected_contigs=expected_contigs,
        source_chrom=plan.source.chrom,
        expected_samples=expected_samples,
    )


def _merge_virtual(chunks: tuple[VirtualChunk, ...]) -> tuple[tuple[int, int], ...]:
    intervals = sorted((chunk.begin, chunk.end) for chunk in chunks)
    merged: list[tuple[int, int]] = []
    for begin, end in intervals:
        if merged and begin <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((begin, end))
    return tuple(merged)


def _predecessor_byte(handles: list[_RangeHandle], physical: int) -> int | None:
    """Return a covered predecessor byte, or None when the reviewed plan omitted its block."""
    if physical == 0:
        return None
    lower = max(0, physical - BGZF_BLOCK_LIMIT_BYTES)
    if not any(
        value.evidence.first <= lower and physical - 1 <= value.evidence.last
        for value in handles
    ):
        return None
    compressed = _read_covered(handles, lower, physical - lower)
    marker = b"\x1f\x8b\x08"
    candidates: list[int] = []
    cursor = compressed.find(marker)
    while cursor >= 0:
        candidates.append(lower + cursor)
        cursor = compressed.find(marker, cursor + 1)
    for candidate in reversed(candidates):
        try:
            payload, size = _bgzf_at(handles, candidate)
        except ValueError:
            continue
        if candidate + size == physical:
            _require(bool(payload), "virtual chunk follows empty BGZF member")
            return payload[-1]
    raise ValueError("virtual chunk predecessor is not a complete BGZF member")


def _virtual_pieces(
    handles: list[_RangeHandle], begin: int, end: int
) -> Iterator[tuple[bytes, int, int, int]]:
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
        if first:
            predecessor = payload[lower - 1] if lower else None
            if lower == 0 and physical != 0:
                predecessor = _predecessor_byte(handles, physical)
                _require(
                    predecessor is not None,
                    "virtual chunk predecessor is outside reviewed ranges",
                )
            _require(
                physical == 0 or predecessor == 0x0A,
                "virtual chunk starts inside a record",
            )
        if lower < upper:
            yield payload[lower:upper], physical, lower, len(payload)
        first = False
        if physical == end_physical:
            break
        physical += compressed_size
        _require(physical <= end_physical, "virtual chunk ends inside an unplanned block")


def _qualified_record_lines(
    verified: VerifiedSource,
    plan: SourceBytePlan,
    window: ReferenceWindow,
    header: HeaderEvidence,
    *,
    artifact_root: Path,
) -> Iterator[tuple[SourceRecord, bytes]]:
    validate_verified_source(verified, plan, artifact_root=artifact_root)
    _require(type(window) is ReferenceWindow and type(header) is HeaderEvidence, "invalid raw reader inputs")
    matching = tuple(value for value in plan.windows if value.window_id == window.window_id)
    _require(len(matching) == 1 and window.chrom == plan.source.chrom, "window plan identity mismatch")
    window_plan = matching[0]
    handles: list[_RangeHandle] = []
    try:
        for value in verified.ranges:
            handles.append(_open_verified_range(artifact_root, value))
        _require(
            hashlib.sha256(_source_header(handles)).hexdigest() == header.raw_sha256,
            "header evidence does not match source bytes",
        )
        decoded = 0
        candidates = 0
        ordinal = 0
        previous_position = 0
        seen_offsets: set[int] = set()
        seen_keys: set[tuple[str, int, str, str]] = set()
        for begin, end in _merge_virtual(window_plan.chunks):
            record_bytes = bytearray()
            record_offset: int | None = None
            for piece, physical, low, decoded_bytes in _virtual_pieces(handles, begin, end):
                decoded += decoded_bytes
                _require(decoded <= DECODED_WINDOW_LIMIT_BYTES, "limit_exceeded")
                piece_offset = 0
                while piece_offset < len(piece):
                    if record_offset is None:
                        record_offset = (physical << 16) | (low + piece_offset)
                    newline = piece.find(b"\n", piece_offset)
                    upper = len(piece) if newline < 0 else newline + 1
                    _require(
                        len(record_bytes) + upper - piece_offset <= RECORD_LIMIT_BYTES,
                        "limit_exceeded",
                    )
                    record_bytes.extend(piece[piece_offset:upper])
                    piece_offset = upper
                    if newline < 0:
                        continue
                    line = bytes(record_bytes)
                    virtual_offset = record_offset
                    record_bytes.clear()
                    record_offset = None
                    candidates += 1
                    _require(candidates <= RECORDS_PER_WINDOW_LIMIT, "limit_exceeded")
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
                    yield record, line
            _require(not record_bytes and record_offset is None, "virtual chunk ends inside a record")
    finally:
        for value in handles:
            path = Path(value.handle.name)
            descriptor_identity = _handle_identity(value.handle)
            value.handle.close()
            _require(
                descriptor_identity == value.identity and _file_identity(path) == value.identity,
                "retained range changed during read",
            )


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
    """Yield and retain exact POS-selected records from reviewed source coverage."""
    raw_final, raw_relative = _destination(artifact_root, raw_destination)
    offsets_final, offsets_relative = _destination(artifact_root, offsets_destination)
    raw_path, _ = _destination(artifact_root, f"{raw_relative}.partial")
    offset_path, _ = _destination(artifact_root, f"{offsets_relative}.partial")
    try:
        with raw_path.open("xb") as raw_output, offset_path.open("xb") as offset_output:
            os.chmod(raw_path, 0o600)
            os.chmod(offset_path, 0o600)
            offset_output.write(b"ordinal\tsource_virtual_offset\traw_sha256\n")
            for ordinal, (record, line) in enumerate(
                _qualified_record_lines(verified, plan, window, header, artifact_root=artifact_root)
            ):
                raw_output.write(line)
                offset_output.write(
                    f"{ordinal}\t{record.source_virtual_offset}\t{record.raw_sha256}\n".encode()
                )
                yield record
            fsync_artifact(raw_output)
            fsync_artifact(offset_output)
    except BaseException:
        raw_path.unlink(missing_ok=True)
        offset_path.unlink(missing_ok=True)
        raise
    offset_path.rename(offsets_final)
    try:
        raw_path.rename(raw_final)
    except BaseException:
        offsets_final.rename(offset_path)
        raw_path.unlink(missing_ok=True)
        offset_path.unlink(missing_ok=True)
        raise


def iter_source_records(
    verified: VerifiedSource,
    plan: SourceBytePlan,
    window: ReferenceWindow,
    header: HeaderEvidence,
    *,
    artifact_root: Path,
) -> Iterator[SourceRecord]:
    """Yield qualified source records without retaining a second copy."""
    for record, _ in _qualified_record_lines(
        verified, plan, window, header, artifact_root=artifact_root
    ):
        yield record


def _validated_original_evidence(
    verified: VerifiedSource,
    plan: SourceBytePlan,
    window: ReferenceWindow,
    header: HeaderEvidence,
    *,
    artifact_root: Path,
    raw: ArtifactRef,
    offsets: ArtifactRef,
) -> Iterator[SourceRecord]:
    raw_path = _validate_artifact(artifact_root, raw)
    offsets_path = _validate_artifact(artifact_root, offsets)
    with raw_path.open("rb") as raw_input, offsets_path.open("rb") as offset_input:
        _require(
            offset_input.readline(256) == b"ordinal\tsource_virtual_offset\traw_sha256\n",
            "record offset columns mismatch",
        )
        for ordinal, (record, source_line) in enumerate(
            _qualified_record_lines(verified, plan, window, header, artifact_root=artifact_root)
        ):
            retained_line = raw_input.readline(RECORD_LIMIT_BYTES + 1)
            _require(retained_line == source_line, "original record differs from source bytes")
            offset_line = offset_input.readline(256)
            _require(offset_line.endswith(b"\n") and b"\r" not in offset_line, "invalid record offset row")
            try:
                fields = offset_line[:-1].decode("ascii").split("\t")
            except UnicodeDecodeError as error:
                raise ValueError("record offset row must be ASCII") from error
            _require(
                fields
                == [str(ordinal), str(record.source_virtual_offset), record.raw_sha256],
                "record offset evidence differs from source",
            )
            yield record
        _require(raw_input.read(1) == b"", "original record evidence has extra rows")
        _require(offset_input.read(1) == b"", "record offset evidence has extra rows")


def validate_original_evidence(
    verified: VerifiedSource,
    plan: SourceBytePlan,
    window: ReferenceWindow,
    header: HeaderEvidence,
    *,
    artifact_root: Path,
    raw: ArtifactRef,
    offsets: ArtifactRef,
) -> int:
    """Recompute retained original rows and offsets from reviewed source ranges."""
    return sum(
        1
        for _ in _validated_original_evidence(
            verified,
            plan,
            window,
            header,
            artifact_root=artifact_root,
            raw=raw,
            offsets=offsets,
        )
    )


def validate_original_records(
    verified: VerifiedSource,
    plan: SourceBytePlan,
    window: ReferenceWindow,
    header: HeaderEvidence,
    *,
    artifact_root: Path,
    raw: ArtifactRef,
    offsets: ArtifactRef,
    native_keys: ArtifactRef,
) -> int:
    """Stream-compare retained original evidence with exact native keys."""
    native_path = _validate_artifact(artifact_root, native_keys)
    with native_path.open("rb") as native_input:
        count = 0
        for record in _validated_original_evidence(
            verified,
            plan,
            window,
            header,
            artifact_root=artifact_root,
            raw=raw,
            offsets=offsets,
        ):
            expected_key = (
                f"{record.chrom}\t{record.pos1}\t{record.ref}\t{record.alt}\t{record.filter}\n"
            ).encode()
            _require(
                native_input.readline(RECORD_LIMIT_BYTES + 1) == expected_key,
                "native_mismatch",
            )
            count += 1
        _require(native_input.read(1) == b"", "native_mismatch")
    return count
