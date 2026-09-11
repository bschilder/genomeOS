"""Pure reference-window range accounting (preflight design §§4–6; Atlas §§4–8, 12)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Literal

from genomeos.validation.reference_tbi import (
    MAX_BGZF_BLOCK_BYTES,
    MAX_CHUNKS,
    MAX_COMPRESSED_BYTES,
    MAX_DECOMPRESSED_BYTES,
    MAX_DISTINCT_BINS,
    MAX_LINEAR_OFFSETS,
    MAX_REFERENCE_NAME_BYTES,
    TbiIndex,
    VirtualChunk,
    candidate_chunks,
)
from genomeos.validation.reference_window_types import (
    AUTOSOMES,
    EOF_BYTES,
    HEADER_PREFIX_BYTES,
    MAX_TRANSFER_BYTES,
    Provenance,
    ReferenceWindow,
    SourcePair,
    WindowManifest,
)

WindowState = Literal["index_chunks_planned", "no_index_chunks", "refused"]
ReceiptState = Literal["verified", "refused"]
BudgetStatus = Literal["within_cap", "over_cap", "incomplete"]
RefusalCode = Literal[
    "metadata_mismatch",
    "generation_unavailable",
    "transfer_failed",
    "size_mismatch",
    "checksum_mismatch",
    "index_invalid",
    "limit_exceeded",
]
PolicyEntries = tuple[tuple[str, str | int], ...]

PREFLIGHT_SCHEMA_VERSION = "reference_index_preflight_v1"
METADATA_LIMIT_BYTES = 1_048_576
REQUEST_ATTEMPTS_PER_OBJECT = 1
REQUEST_ATTEMPT_ACCOUNTING = "wrapper_invocations"
REQUEST_TIMEOUT_SECONDS = 120
STORAGE_BODY_MAX_RETRIES = 0
METADATA_HTTP_ATTEMPTS = "unobserved"
REFUSAL_CODES = frozenset(
    {
        "metadata_mismatch",
        "generation_unavailable",
        "transfer_failed",
        "size_mismatch",
        "checksum_mismatch",
        "index_invalid",
        "limit_exceeded",
    }
)
POLICY: PolicyEntries = (
    ("bgzf_block_limit_bytes", MAX_BGZF_BLOCK_BYTES),
    ("chunk_limit", MAX_CHUNKS),
    ("compressed_tbi_limit_bytes", MAX_COMPRESSED_BYTES),
    ("decompressed_tbi_limit_bytes", MAX_DECOMPRESSED_BYTES),
    ("distinct_bin_limit", MAX_DISTINCT_BINS),
    ("linear_offset_limit", MAX_LINEAR_OFFSETS),
    ("metadata_http_attempts", METADATA_HTTP_ATTEMPTS),
    ("metadata_limit_bytes", METADATA_LIMIT_BYTES),
    ("range_policy", "conservative_reg2bins_v1"),
    ("reference_count", 1),
    ("reference_name_limit_bytes", MAX_REFERENCE_NAME_BYTES),
    ("request_attempt_accounting", REQUEST_ATTEMPT_ACCOUNTING),
    ("request_attempts_per_object", REQUEST_ATTEMPTS_PER_OBJECT),
    ("request_timeout_seconds", REQUEST_TIMEOUT_SECONDS),
    ("storage_body_max_retries", STORAGE_BODY_MAX_RETRIES),
)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _integer(value: object, field: str, *, minimum: int = 0) -> int:
    _require(type(value) is int and value >= minimum, f"{field} must be an integer >= {minimum}")
    return value


def _sha(value: object, field: str) -> str:
    _require(isinstance(value, str) and _SHA256.fullmatch(value) is not None, f"invalid {field} sha256")
    return value


@dataclass(frozen=True, order=True)
class ByteRange:
    first: int
    last: int

    def __post_init__(self) -> None:
        _integer(self.first, "byte range first")
        _integer(self.last, "byte range last")
        _require(self.first <= self.last, "byte range is reversed")


@dataclass(frozen=True)
class WindowBytePlan:
    window_id: str
    state: WindowState
    reason: RefusalCode | None
    variant_content: Literal["not_inspected"]
    chunks: tuple[VirtualChunk, ...]
    ranges: tuple[ByteRange, ...]

    def __post_init__(self) -> None:
        _require(isinstance(self.window_id, str) and bool(self.window_id), "invalid window_id")
        _require(
            isinstance(self.state, str)
            and self.state in ("index_chunks_planned", "no_index_chunks", "refused"),
            "invalid window state",
        )
        _require(self.variant_content == "not_inspected", "variant_content must be not_inspected")
        _require(type(self.chunks) is tuple, "chunks must be a tuple")
        _require(type(self.ranges) is tuple, "ranges must be a tuple")
        _require(all(type(value) is VirtualChunk for value in self.chunks), "invalid chunks")
        _require(all(type(value) is ByteRange for value in self.ranges), "invalid ranges")
        if self.state == "refused":
            _require(
                isinstance(self.reason, str) and self.reason in REFUSAL_CODES,
                "refused window requires a fixed reason",
            )
            _require(not self.chunks and not self.ranges, "refused window cannot contain planned bytes")
        else:
            _require(self.reason is None, "non-refused window cannot have a reason")
            _require(
                bool(self.chunks) == (self.state == "index_chunks_planned"),
                "window state disagrees with chunks",
            )
            _require(bool(self.ranges) == bool(self.chunks), "window ranges disagree with chunks")


@dataclass(frozen=True)
class IndexReceipt:
    """Index result whose ``*_attempts`` fields count adapter wrapper invocations."""

    chrom: str
    state: ReceiptState
    reason: RefusalCode | None
    vcf_metadata_attempts: int
    tbi_metadata_attempts: int
    tbi_body_attempts: int
    received_bytes: int
    sha256: str | None

    def __post_init__(self) -> None:
        _require(self.chrom in AUTOSOMES, "invalid receipt chromosome")
        _require(
            isinstance(self.state, str) and self.state in ("verified", "refused"),
            "invalid receipt state",
        )
        for field in ("vcf_metadata_attempts", "tbi_metadata_attempts", "tbi_body_attempts"):
            value = _integer(getattr(self, field), field)
            _require(value <= 1, f"{field} exceeds one-attempt policy")
        _require(
            self.tbi_metadata_attempts <= self.vcf_metadata_attempts
            and self.tbi_body_attempts <= self.tbi_metadata_attempts,
            "receipt attempts are out of order",
        )
        _integer(self.received_bytes, "received_bytes")
        _require(
            self.tbi_body_attempts == 1 or self.received_bytes == 0,
            "received bytes require a body attempt",
        )
        _require(
            self.sha256 is None
            or (isinstance(self.sha256, str) and _SHA256.fullmatch(self.sha256) is not None),
            "invalid receipt sha256",
        )
        if self.state == "verified":
            _require(self.reason is None, "verified receipt cannot have a reason")
            _require(
                (self.vcf_metadata_attempts, self.tbi_metadata_attempts, self.tbi_body_attempts) == (1, 1, 1),
                "verified receipt requires all attempts",
            )
            _require(self.sha256 is not None, "verified receipt requires sha256")
        else:
            _require(
                isinstance(self.reason, str) and self.reason in REFUSAL_CODES,
                "refused receipt requires a fixed reason",
            )


@dataclass(frozen=True)
class SourceBytePlan:
    source: SourcePair
    receipt: IndexReceipt
    windows: tuple[WindowBytePlan, ...]
    merged_vcf_ranges: tuple[ByteRange, ...]

    def __post_init__(self) -> None:
        _require(type(self.source) is SourcePair, "invalid source")
        _require(
            type(self.receipt) is IndexReceipt and self.receipt.chrom == self.source.chrom,
            "receipt source mismatch",
        )
        _require(type(self.windows) is tuple, "windows must be a tuple")
        _require(
            len(self.windows) == 3 and all(type(item) is WindowBytePlan for item in self.windows),
            "source requires three window plans",
        )
        _require(type(self.merged_vcf_ranges) is tuple, "merged_vcf_ranges must be a tuple")
        _require(all(type(item) is ByteRange for item in self.merged_vcf_ranges), "invalid merged ranges")
        for item in self.windows:
            if item.state == "index_chunks_planned":
                expected_ranges = merge_byte_ranges(
                    tuple(
                        chunk_byte_range(chunk, source_size_bytes=self.source.vcf.size_bytes)
                        for chunk in item.chunks
                    ),
                    source_size_bytes=self.source.vcf.size_bytes,
                )
                _require(item.ranges == expected_ranges, "window ranges do not match virtual chunks")
        if self.receipt.state == "refused":
            _require(
                all(item.state == "refused" and item.reason == self.receipt.reason for item in self.windows),
                "refused receipt must refuse every source window",
            )
        else:
            _require(
                all(item.state != "refused" for item in self.windows),
                "verified receipt cannot contain refused windows",
            )
            _require(
                self.receipt.received_bytes == self.source.tbi.size_bytes,
                "verified receipt byte count must match the TBI object",
            )


@dataclass(frozen=True)
class BytePreflight:
    schema_version: str
    manifest_sha256: str
    windows_sha256: str
    sources: tuple[SourceBytePlan, ...]
    complete: bool
    budget_status: BudgetStatus
    known_planned_bytes: int
    total_planned_bytes: int | None
    max_transfer_bytes: int
    provenance: Provenance
    policy: PolicyEntries
    publication_eligible: Literal[False]
    p1_eligible: Literal[False]

    def __post_init__(self) -> None:
        _validate_preflight(self)


def _validate_policy(value: object) -> None:
    _require(type(value) is tuple and len(value) == len(POLICY), "unsupported preflight policy")
    for actual, expected in zip(value, POLICY, strict=True):
        _require(type(actual) is tuple and len(actual) == 2, "invalid preflight policy entry")
        _require(actual[0] == expected[0], "unsupported preflight policy")
        _require(type(actual[1]) is type(expected[1]), "invalid preflight policy value type")
        _require(actual[1] == expected[1], "unsupported preflight policy")


def _known_planned_bytes(sources: tuple[SourceBytePlan, ...]) -> int:
    return sum(
        plan.source.tbi.size_bytes + sum(item.last - item.first + 1 for item in plan.merged_vcf_ranges)
        for plan in sources
    )


def _receipts_complete(sources: tuple[SourceBytePlan, ...]) -> bool:
    return all(plan.receipt.state == "verified" for plan in sources)


def _expected_budget_status(complete: bool, known: int) -> BudgetStatus:
    if not complete:
        return "incomplete"
    return "within_cap" if known <= MAX_TRANSFER_BYTES else "over_cap"


def _validate_preflight(value: BytePreflight) -> None:
    _require(type(value) is BytePreflight, "preflight must be BytePreflight")
    _require(value.schema_version == PREFLIGHT_SCHEMA_VERSION, "unsupported preflight schema_version")
    _sha(value.manifest_sha256, "manifest")
    _sha(value.windows_sha256, "windows")
    _require(
        type(value.sources) is tuple and all(type(item) is SourceBytePlan for item in value.sources),
        "preflight sources must be SourceBytePlan records",
    )
    _require(
        tuple(item.source.chrom for item in value.sources) == AUTOSOMES,
        "preflight sources must be natural autosomes",
    )
    for plan in value.sources:
        _require(
            tuple(window.window_id for window in plan.windows)
            == tuple(f"{plan.source.chrom}-s{stratum}" for stratum in range(1, 4)),
            "source window plans are incomplete",
        )
        required = fixed_vcf_ranges(
            plan.source.vcf.size_bytes,
            header_prefix_bytes=HEADER_PREFIX_BYTES,
            eof_bytes=EOF_BYTES,
        ) + tuple(byte_range for window in plan.windows for byte_range in window.ranges)
        _require(
            plan.merged_vcf_ranges
            == merge_byte_ranges(required, source_size_bytes=plan.source.vcf.size_bytes),
            "source ranges do not match planned bytes",
        )
    _require(type(value.complete) is bool, "complete must be bool")
    _require(
        isinstance(value.budget_status, str)
        and value.budget_status in ("within_cap", "over_cap", "incomplete"),
        "invalid budget status",
    )
    known = _known_planned_bytes(value.sources)
    _integer(value.known_planned_bytes, "known_planned_bytes")
    _require(value.known_planned_bytes == known, "known planned bytes disagree with sources")
    _require(
        value.total_planned_bytes is None or type(value.total_planned_bytes) is int,
        "invalid total_planned_bytes",
    )
    _integer(value.max_transfer_bytes, "max_transfer_bytes", minimum=1)
    _require(value.max_transfer_bytes == MAX_TRANSFER_BYTES, "preflight must use the fixed transfer cap")
    complete = _receipts_complete(value.sources)
    _require(value.complete is complete, "preflight receipt completeness disagrees with complete")
    expected_total = known if complete else None
    _require(value.total_planned_bytes == expected_total, "total planned bytes disagree with completeness")
    _require(
        value.budget_status == _expected_budget_status(complete, known),
        "budget status disagrees with total",
    )
    _require(type(value.provenance) is Provenance, "invalid provenance")
    _validate_policy(value.policy)
    _require(value.publication_eligible is False, "publication_eligible must be false")
    _require(value.p1_eligible is False, "p1_eligible must be false")


def chunk_byte_range(chunk: VirtualChunk, *, source_size_bytes: int) -> ByteRange:
    """Conservatively map a virtual chunk to an inclusive physical byte range."""
    _require(type(chunk) is VirtualChunk and chunk.begin < chunk.end, "chunk must be nonempty")
    size = _integer(source_size_bytes, "source_size_bytes", minimum=1)
    first = chunk.begin >> 16
    _require(first < size, "chunk start is outside source")
    end_block, end_offset = chunk.end >> 16, chunk.end & 0xFFFF
    if end_offset == 0:
        _require(0 < end_block <= size, "chunk terminal end is outside source")
        last = end_block - 1
    else:
        _require(end_block < size, "chunk end is outside source")
        last = min(size - 1, end_block + MAX_BGZF_BLOCK_BYTES - 1)
    _require(first <= last, "chunk physical range is empty")
    return ByteRange(first, last)


def merge_byte_ranges(ranges: tuple[ByteRange, ...], *, source_size_bytes: int) -> tuple[ByteRange, ...]:
    """Union touching inclusive ranges for one immutable source generation."""
    _require(type(ranges) is tuple, "ranges must be a tuple")
    size = _integer(source_size_bytes, "source_size_bytes", minimum=1)
    _require(
        all(type(item) is ByteRange and item.last < size for item in ranges), "byte range is outside source"
    )
    merged: list[ByteRange] = []
    for item in sorted(ranges):
        if merged and item.first <= merged[-1].last + 1:
            previous = merged[-1]
            merged[-1] = ByteRange(previous.first, max(previous.last, item.last))
        else:
            merged.append(item)
    return tuple(merged)


def plan_window(index: TbiIndex, window: ReferenceWindow, *, source_size_bytes: int) -> WindowBytePlan:
    """Build one conservative index-derived window plan without inspecting variants."""
    _require(type(index) is TbiIndex and type(window) is ReferenceWindow, "invalid plan inputs")
    _require(index.chrom == window.chrom, "window and index chromosome mismatch")
    chunks = candidate_chunks(index, window.start0, window.end0)
    ranges = merge_byte_ranges(
        tuple(chunk_byte_range(chunk, source_size_bytes=source_size_bytes) for chunk in chunks),
        source_size_bytes=source_size_bytes,
    )
    state: WindowState = "index_chunks_planned" if chunks else "no_index_chunks"
    return WindowBytePlan(window.window_id, state, None, "not_inspected", chunks, ranges)


def fixed_vcf_ranges(
    source_size_bytes: int, *, header_prefix_bytes: int, eof_bytes: int
) -> tuple[ByteRange, ...]:
    """Return the fixed planned header-prefix and EOF reads for one VCF."""
    size = _integer(source_size_bytes, "source_size_bytes", minimum=1)
    prefix = _integer(header_prefix_bytes, "header_prefix_bytes", minimum=1)
    eof = _integer(eof_bytes, "eof_bytes", minimum=1)
    _require(size >= eof, "source is smaller than fixed EOF read")
    return merge_byte_ranges(
        (ByteRange(0, min(size, prefix) - 1), ByteRange(size - eof, size - 1)),
        source_size_bytes=size,
    )


def assemble_preflight(
    manifest: WindowManifest,
    source_plans: tuple[SourceBytePlan, ...],
    *,
    manifest_sha256: str,
    provenance: Provenance,
) -> BytePreflight:
    """Validate complete ledger identity and compute conservative total accounting."""
    _require(type(manifest) is WindowManifest, "manifest must be WindowManifest")
    _require(type(source_plans) is tuple, "source_plans must be a tuple")
    _sha(manifest_sha256, "manifest")
    _require(type(provenance) is Provenance, "provenance must be Provenance")
    _require(
        (provenance.data_version, provenance.evidence_kind)
        == (manifest.provenance.data_version, manifest.provenance.evidence_kind),
        "preflight provenance does not match manifest",
    )
    input_hashes = dict(provenance.input_sha256)
    _require(set(input_hashes) == {"manifest", "windows"}, "invalid preflight input hashes")
    _require(
        input_hashes == {"manifest": manifest_sha256, "windows": manifest.windows_sha256},
        "preflight input hashes do not match artifacts",
    )
    _require(len(source_plans) == len(manifest.sources), "missing source plans")
    _require(
        tuple(plan.source for plan in source_plans) == manifest.sources,
        "source plans do not match manifest sources",
    )
    expected_by_chrom = {
        chrom: tuple(window.window_id for window in manifest.windows if window.chrom == chrom)
        for chrom in AUTOSOMES
    }
    for plan in source_plans:
        _require(
            tuple(window.window_id for window in plan.windows) == expected_by_chrom[plan.source.chrom],
            "window plans do not match manifest windows",
        )
    known = _known_planned_bytes(source_plans)
    complete = _receipts_complete(source_plans)
    total = known if complete else None
    status = _expected_budget_status(complete, known)
    return BytePreflight(
        schema_version=PREFLIGHT_SCHEMA_VERSION,
        manifest_sha256=manifest_sha256,
        windows_sha256=manifest.windows_sha256,
        sources=source_plans,
        complete=complete,
        budget_status=status,
        known_planned_bytes=known,
        total_planned_bytes=total,
        max_transfer_bytes=manifest.config.max_transfer_bytes,
        provenance=provenance,
        policy=POLICY,
        publication_eligible=False,
        p1_eligible=False,
    )


def _object_payload(value: object) -> object:
    if isinstance(value, VirtualChunk):
        return {"begin": value.begin, "end": value.end}
    if isinstance(value, ByteRange):
        return {"first": value.first, "last": value.last}
    if isinstance(value, WindowBytePlan):
        return {
            "window_id": value.window_id,
            "state": value.state,
            "reason": value.reason,
            "variant_content": value.variant_content,
            "chunks": [_object_payload(item) for item in value.chunks],
            "ranges": [_object_payload(item) for item in value.ranges],
        }
    if isinstance(value, IndexReceipt):
        return {
            "chrom": value.chrom,
            "state": value.state,
            "reason": value.reason,
            "vcf_metadata_attempts": value.vcf_metadata_attempts,
            "tbi_metadata_attempts": value.tbi_metadata_attempts,
            "tbi_body_attempts": value.tbi_body_attempts,
            "received_bytes": value.received_bytes,
            "sha256": value.sha256,
        }
    if isinstance(value, SourcePair):

        def public(item):
            return {
                "uri": item.uri,
                "generation": item.generation,
                "size_bytes": item.size_bytes,
                "md5_b64": item.md5_b64,
                "crc32c_b64": item.crc32c_b64,
            }

        return {"chrom": value.chrom, "vcf": public(value.vcf), "tbi": public(value.tbi)}
    if isinstance(value, SourceBytePlan):
        return {
            "source": _object_payload(value.source),
            "receipt": _object_payload(value.receipt),
            "windows": [_object_payload(item) for item in value.windows],
            "merged_vcf_ranges": [_object_payload(item) for item in value.merged_vcf_ranges],
        }
    raise TypeError(f"unsupported preflight value: {type(value).__name__}")


def encode_preflight(preflight: BytePreflight) -> bytes:
    """Encode validated preflight evidence as canonical timestamp-free JSON."""
    _validate_preflight(preflight)
    provenance = preflight.provenance
    payload = {
        "schema_version": preflight.schema_version,
        "manifest_sha256": preflight.manifest_sha256,
        "windows_sha256": preflight.windows_sha256,
        "sources": [_object_payload(item) for item in preflight.sources],
        "complete": preflight.complete,
        "budget_status": preflight.budget_status,
        "known_planned_bytes": preflight.known_planned_bytes,
        "total_planned_bytes": preflight.total_planned_bytes,
        "max_transfer_bytes": preflight.max_transfer_bytes,
        "provenance": {
            "data_version": provenance.data_version,
            "evidence_kind": provenance.evidence_kind,
            "input_sha256": dict(provenance.input_sha256),
            "source_revision": provenance.source_revision,
            "imported_source_sha256": dict(provenance.imported_source_sha256),
            "python_version": provenance.python_version,
            "source_audit_locator": provenance.source_audit_locator,
        },
        "policy": dict(preflight.policy),
        "publication_eligible": preflight.publication_eligible,
        "p1_eligible": preflight.p1_eligible,
    }
    return (
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False) + "\n"
    ).encode()


def crc32c(data: bytes) -> int:
    """Return the RFC 3720 CRC32C value using the reflected Castagnoli polynomial."""
    _require(type(data) is bytes, "CRC32C input must be bytes")
    value = 0xFFFFFFFF
    for byte in data:
        value ^= byte
        for _ in range(8):
            value = (value >> 1) ^ (0x82F63B78 if value & 1 else 0)
    return value ^ 0xFFFFFFFF
