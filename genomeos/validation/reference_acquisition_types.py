"""Immutable acquisition evidence records (reference acquisition design §§4.1, 6.1)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Literal, get_args

from genomeos.validation.reference_window_types import AUTOSOMES, HashEntries, SourcePair

Reason = Literal[
    "invalid_input",
    "review_mismatch",
    "metadata_mismatch",
    "generation_unavailable",
    "transfer_failed",
    "size_mismatch",
    "timeout",
    "limit_exceeded",
    "index_invalid",
    "coverage_gap",
    "header_invalid",
    "sample_mismatch",
    "record_invalid",
    "native_encoding_refused",
    "native_count_unavailable",
    "native_mismatch",
    "artifact_mismatch",
]

REASONS = frozenset(get_args(Reason))
NATIVE_OPERATIONS = frozenset(
    {
        "extract_bcf",
        "query_keys",
        "select_cohort",
        "fill_tags",
        "query_samples",
        "query_tokens",
        "query_totals",
        "version",
    }
)
ACQUISITION_POLICY: tuple[tuple[str, str | int], ...] = tuple(
    sorted(
        {
            "bgzf_block_limit_bytes": 65_536,
            "decoded_window_limit_bytes": 2_147_483_648,
            "header_limit_bytes": 8_388_608,
            "max_transfer_bytes": 26_843_545_600,
            "metadata_http_attempts": "unobserved",
            "metadata_stdout_limit_bytes": 1_048_576,
            "metadata_timeout_seconds": 120,
            "native_sample_stdout_limit_bytes": 1_048_576,
            "native_stdout_limit_bytes": 2_147_483_648,
            "native_timeout_seconds": 1_800,
            "native_version_stdout_limit_bytes": 65_536,
            "range_timeout_seconds": 1_800,
            "record_limit_bytes": 16_777_216,
            "records_per_window_limit": 1_000_000,
            "request_attempt_accounting": "wrapper_invocations",
            "schema_version": "reference_acquisition_policy_v1",
            "source_complete": "false",
            "sparse_allocation_slack_bytes": 16_777_216,
            "stderr_limit_bytes": 1_048_576,
            "storage_body_max_retries": 0,
            "transfer_piece_limit_bytes": 1_048_576,
        }.items()
    )
)

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_REVISION = re.compile(r"[0-9a-f]{40}\Z")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _text(value: object, field: str) -> str:
    _require(isinstance(value, str) and bool(value.strip()) and value == value.strip(), f"invalid {field}")
    return value


def _count(value: object, field: str) -> int:
    _require(type(value) is int and value >= 0, f"{field} must be an integer >= 0")
    return value


def _sha(value: object, field: str) -> str:
    _require(isinstance(value, str) and _SHA256.fullmatch(value) is not None, f"invalid {field} sha256")
    return value


def _revision(value: object, field: str) -> str:
    _require(isinstance(value, str) and _REVISION.fullmatch(value) is not None, f"invalid {field}")
    return value


def _relpath(value: object, field: str) -> str:
    text = _text(value, field)
    path = PurePosixPath(text)
    _require("\\" not in text and not path.is_absolute(), f"invalid {field}")
    _require(all(part not in ("", ".", "..") for part in path.parts), f"invalid {field}")
    _require(str(path) == text, f"noncanonical {field}")
    return text


def _hash_entries(value: object, field: str) -> HashEntries:
    _require(type(value) is tuple, f"{field} must be a tuple")
    entries = []
    for item in value:
        _require(type(item) is tuple and len(item) == 2, f"invalid {field} entry")
        entries.append((_relpath(item[0], f"{field} key"), _sha(item[1], f"{field} value")))
    _require(tuple(entries) == tuple(sorted(entries)), f"{field} must be key-sorted")
    _require(len({key for key, _ in entries}) == len(entries), f"{field} keys must be unique")
    return tuple(entries)


def _text_entries(value: object, field: str) -> tuple[tuple[str, str], ...]:
    _require(type(value) is tuple, f"{field} must be a tuple")
    entries = []
    for item in value:
        _require(type(item) is tuple and len(item) == 2, f"invalid {field} entry")
        entries.append((_text(item[0], f"{field} key"), _text(item[1], f"{field} value")))
    _require(tuple(entries) == tuple(sorted(entries)), f"{field} must be key-sorted")
    _require(len({key for key, _ in entries}) == len(entries), f"{field} keys must be unique")
    return tuple(entries)


def _reason(value: object, *, required: bool) -> None:
    _require(
        (isinstance(value, str) and value in REASONS) if required else (value is None),
        "invalid refusal reason",
    )


@dataclass(frozen=True)
class ArtifactRef:
    path: str
    size_bytes: int
    sha256: str

    def __post_init__(self) -> None:
        _relpath(self.path, "artifact path")
        _count(self.size_bytes, "artifact size_bytes")
        _sha(self.sha256, "artifact")


@dataclass(frozen=True)
class ReviewReceipt:
    schema_version: Literal["reference_preflight_review_v1"]
    manifest_sha256: str
    preflight_sha256: str
    implementation_revision: str
    implementation_sha256: HashEntries
    review_locator: str
    review_sha256: str
    status: Literal["accepted"]

    def __post_init__(self) -> None:
        _require(self.schema_version == "reference_preflight_review_v1", "unsupported review schema_version")
        _sha(self.manifest_sha256, "review manifest")
        _sha(self.preflight_sha256, "review preflight")
        _revision(self.implementation_revision, "review implementation_revision")
        _hash_entries(self.implementation_sha256, "review implementation_sha256")
        _text(self.review_locator, "review_locator")
        _sha(self.review_sha256, "review")
        _require(self.status == "accepted", "review status must be accepted")


@dataclass(frozen=True)
class RetainedIndex:
    chrom: str
    raw: bytes

    def __post_init__(self) -> None:
        _require(self.chrom in AUTOSOMES, "invalid retained index chromosome")
        _require(type(self.raw) is bytes and bool(self.raw), "retained index must be nonempty bytes")


@dataclass(frozen=True)
class CohortInputHashes:
    metadata: str
    outliers: str
    exclusions: str
    technical_samples: str
    paper_samples: str
    dependency_audit: str

    def __post_init__(self) -> None:
        for field in self.__dataclass_fields__:
            _sha(getattr(self, field), f"cohort {field}")


@dataclass(frozen=True)
class RunProvenance:
    code_revision: str
    python_version: str
    imported_source_sha256: HashEntries
    tool_versions: tuple[tuple[str, str], ...]
    executable_sha256: HashEntries
    sdk_source_sha256: HashEntries

    def __post_init__(self) -> None:
        _revision(self.code_revision, "code_revision")
        _text(self.python_version, "python_version")
        _hash_entries(self.imported_source_sha256, "imported_source_sha256")
        _text_entries(self.tool_versions, "tool_versions")
        _hash_entries(self.executable_sha256, "executable_sha256")
        _hash_entries(self.sdk_source_sha256, "sdk_source_sha256")


@dataclass(frozen=True)
class AcquisitionInputs:
    window_manifest: ArtifactRef
    windows: ArtifactRef
    preflight: ArtifactRef
    review: ArtifactRef
    cohort: CohortInputHashes

    def __post_init__(self) -> None:
        for field in ("window_manifest", "windows", "preflight", "review"):
            _require(type(getattr(self, field)) is ArtifactRef, f"invalid {field}")
        _require(type(self.cohort) is CohortInputHashes, "invalid cohort")


@dataclass(frozen=True)
class RangeReceipt:
    chrom: str
    generation: str
    first: int
    last: int
    requested_bytes: int
    received_bytes: int
    adapter_invocations: int
    state: Literal["verified", "partial", "refused", "not_attempted"]
    reason: Reason | None
    sha256: str | None
    retained: ArtifactRef | None
    stderr: ArtifactRef | None
    exit_code: int | None
    stdout_limit_exceeded: bool
    stderr_limit_exceeded: bool

    def __post_init__(self) -> None:
        _require(self.chrom in AUTOSOMES, "invalid range chromosome")
        _require(
            isinstance(self.generation, str)
            and re.fullmatch(r"[1-9][0-9]*", self.generation) is not None,
            "invalid range generation",
        )
        first, last = _count(self.first, "range first"), _count(self.last, "range last")
        _require(first <= last, "range is reversed")
        requested = _count(self.requested_bytes, "requested_bytes")
        received = _count(self.received_bytes, "received_bytes")
        invocations = _count(self.adapter_invocations, "adapter_invocations")
        _require(invocations <= 1, "adapter_invocations exceeds one")
        _require(self.state in ("verified", "partial", "refused", "not_attempted"), "invalid range state")
        _require(type(self.stdout_limit_exceeded) is bool and type(self.stderr_limit_exceeded) is bool,
                 "range limit flags must be bool")
        attempted = self.state != "not_attempted"
        _require((invocations == 1) is attempted, "range invocation disagrees with state")
        _require(requested == (last - first + 1 if attempted else 0), "requested_bytes disagree with range")
        _require(received <= requested + (1 if attempted else 0), "received_bytes exceeds bounded request")
        _reason(self.reason, required=self.state != "verified")
        if attempted:
            _require(type(self.retained) is ArtifactRef and type(self.stderr) is ArtifactRef,
                     "attempted range requires retained stdout and stderr")
            _require(self.sha256 == self.retained.sha256 and received == self.retained.size_bytes,
                     "range retained identity mismatch")
            _require(self.exit_code is None or type(self.exit_code) is int, "invalid range exit_code")
        else:
            _require(received == 0 and self.sha256 is None and self.retained is None and self.stderr is None,
                     "not-attempted range cannot retain output")
            _require(
                self.exit_code is None
                and not self.stdout_limit_exceeded
                and not self.stderr_limit_exceeded,
                "not-attempted range has process state",
            )
        if self.state == "verified":
            _require(received == requested and self.exit_code == 0, "verified range is incomplete")
            _require(not self.stdout_limit_exceeded and not self.stderr_limit_exceeded,
                     "verified range exceeded a limit")
        if self.stdout_limit_exceeded or self.stderr_limit_exceeded:
            _require(self.reason == "limit_exceeded", "range overflow requires limit_exceeded")


@dataclass(frozen=True)
class MetadataReceipt:
    state: Literal["verified", "refused", "not_attempted"]
    reason: Reason | None
    adapter_invocations: int
    stdout_bytes: int
    retained: ArtifactRef | None
    stderr: ArtifactRef | None
    exit_code: int | None
    stdout_limit_exceeded: bool
    stderr_limit_exceeded: bool

    def __post_init__(self) -> None:
        _require(self.state in ("verified", "refused", "not_attempted"), "invalid metadata state")
        invocations = _count(self.adapter_invocations, "metadata adapter_invocations")
        size = _count(self.stdout_bytes, "metadata stdout_bytes")
        _require(invocations <= 1 and size <= 1_048_577, "metadata output exceeds limit")
        _require(type(self.stdout_limit_exceeded) is bool and type(self.stderr_limit_exceeded) is bool,
                 "metadata limit flags must be bool")
        attempted = self.state != "not_attempted"
        _require((invocations == 1) is attempted, "metadata invocation disagrees with state")
        _reason(self.reason, required=self.state != "verified")
        if attempted:
            _require(type(self.retained) is ArtifactRef and self.retained.size_bytes == size,
                     "attempted metadata requires retained stdout")
            _require(type(self.stderr) is ArtifactRef, "attempted metadata requires retained stderr")
            _require(self.exit_code is None or type(self.exit_code) is int, "invalid metadata exit_code")
        else:
            _require(size == 0 and self.retained is None and self.stderr is None and self.exit_code is None,
                     "not-attempted metadata has process output")
            _require(not self.stdout_limit_exceeded and not self.stderr_limit_exceeded,
                     "not-attempted metadata has limit state")
        if self.state == "verified":
            _require(
                self.exit_code == 0
                and not self.stdout_limit_exceeded
                and not self.stderr_limit_exceeded,
                "verified metadata has failed process state",
            )
        if self.stdout_limit_exceeded or self.stderr_limit_exceeded:
            _require(self.reason == "limit_exceeded", "metadata overflow requires limit_exceeded")


@dataclass(frozen=True)
class VerifiedRange:
    first: int
    last: int
    range_file: ArtifactRef

    def __post_init__(self) -> None:
        _require(_count(self.first, "verified range first") <= _count(self.last, "verified range last"),
                 "verified range is reversed")
        _require(type(self.range_file) is ArtifactRef, "invalid verified range file")
        _require(self.range_file.size_bytes == self.last - self.first + 1,
                 "verified range file size mismatch")


@dataclass(frozen=True)
class VerifiedSource:
    source: SourcePair
    ranges: tuple[VerifiedRange, ...]
    sparse_path: str
    index: ArtifactRef
    logical_size_bytes: int
    allocated_size_bytes: int
    full_object_verified: Literal[False]

    def __post_init__(self) -> None:
        _require(type(self.source) is SourcePair, "invalid verified source")
        _require(type(self.ranges) is tuple and all(type(item) is VerifiedRange for item in self.ranges),
                 "invalid verified ranges")
        _require(tuple((item.first, item.last) for item in self.ranges)
                 == tuple(sorted((item.first, item.last) for item in self.ranges)),
                 "verified ranges must be sorted")
        _require(
            all(left.last < right.first for left, right in zip(self.ranges, self.ranges[1:], strict=False)),
            "verified ranges must be disjoint",
        )
        _relpath(self.sparse_path, "sparse_path")
        _require(type(self.index) is ArtifactRef, "invalid verified index")
        _require(_count(self.logical_size_bytes, "logical_size_bytes") == self.source.vcf.size_bytes,
                 "logical source size mismatch")
        _count(self.allocated_size_bytes, "allocated_size_bytes")
        _require(self.full_object_verified is False, "full_object_verified must be false")


@dataclass(frozen=True)
class HeaderReceipt:
    header: ArtifactRef
    ordered_samples_sha256: str
    sample_count: int
    sample_identity: Literal["exact_metadata_plus_control"]
    contig_identity: Literal["frozen_manifest_assembly_and_lengths"]
    required_formats: Literal["verified"]

    def __post_init__(self) -> None:
        _require(type(self.header) is ArtifactRef, "invalid header artifact")
        _sha(self.ordered_samples_sha256, "ordered samples")
        _count(self.sample_count, "sample_count")
        _require(self.sample_identity == "exact_metadata_plus_control", "invalid sample identity")
        _require(self.contig_identity == "frozen_manifest_assembly_and_lengths", "invalid contig identity")
        _require(self.required_formats == "verified", "required formats are not verified")


@dataclass(frozen=True)
class NativeRunReceipt:
    operation: Literal[
        "extract_bcf", "query_keys", "select_cohort", "fill_tags",
        "query_samples", "query_tokens", "query_totals", "version",
    ]
    argv_template: tuple[str, ...]
    state: Literal["complete", "refused"]
    reason: Reason | None
    exit_code: int | None
    stdout: ArtifactRef
    stderr: ArtifactRef
    stdout_limit_bytes: int
    stderr_limit_bytes: int
    stdout_limit_exceeded: bool
    stderr_limit_exceeded: bool

    def __post_init__(self) -> None:
        _require(self.operation in NATIVE_OPERATIONS, "invalid native operation")
        _require(type(self.argv_template) is tuple and bool(self.argv_template), "invalid argv_template")
        for token in self.argv_template:
            _text(token, "argv_template token")
            _require(not token.startswith("/"), "argv_template contains an absolute path")
        _require(self.state in ("complete", "refused"), "invalid native state")
        _reason(self.reason, required=self.state == "refused")
        _require(self.exit_code is None or type(self.exit_code) is int, "invalid native exit_code")
        _require(type(self.stdout) is ArtifactRef and type(self.stderr) is ArtifactRef,
                 "native run requires output artifacts")
        _count(self.stdout_limit_bytes, "stdout_limit_bytes")
        _count(self.stderr_limit_bytes, "stderr_limit_bytes")
        _require(type(self.stdout_limit_exceeded) is bool and type(self.stderr_limit_exceeded) is bool,
                 "native limit flags must be bool")
        if self.state == "complete":
            _require(
                self.exit_code == 0
                and not self.stdout_limit_exceeded
                and not self.stderr_limit_exceeded,
                "complete native run has failed process state",
            )
        if self.stdout_limit_exceeded or self.stderr_limit_exceeded:
            _require(self.reason == "limit_exceeded", "native overflow requires limit_exceeded")


@dataclass(frozen=True)
class NativeTokenFiles:
    input_bcf: ArtifactRef
    samples: ArtifactRef | None
    tokens: ArtifactRef | None
    sample_query: NativeRunReceipt
    token_query: NativeRunReceipt | None
    state: Literal["complete", "refused"]
    reason: Reason | None

    def __post_init__(self) -> None:
        _require(type(self.input_bcf) is ArtifactRef and type(self.sample_query) is NativeRunReceipt,
                 "invalid native token inputs")
        _require(self.samples is None or type(self.samples) is ArtifactRef, "invalid native sample file")
        _require(self.tokens is None or type(self.tokens) is ArtifactRef, "invalid native token file")
        _require(self.token_query is None or type(self.token_query) is NativeRunReceipt,
                 "invalid native token query")
        _require(self.state in ("complete", "refused"), "invalid native token state")
        _reason(self.reason, required=self.state == "refused")
        if self.state == "complete":
            _require(type(self.samples) is ArtifactRef and type(self.tokens) is ArtifactRef,
                     "complete native tokens require files")
            _require(type(self.token_query) is NativeRunReceipt, "complete native tokens require token query")
            _require(self.sample_query.state == self.token_query.state == "complete",
                     "complete native token query has refused run")


@dataclass(frozen=True)
class NativeCountFiles:
    input_bcf: ArtifactRef
    requested_samples: ArtifactRef
    selected_bcf: ArtifactRef | None
    recomputed_bcf: ArtifactRef | None
    selected_samples: ArtifactRef | None
    totals: ArtifactRef | None
    runs: tuple[NativeRunReceipt, ...]
    state: Literal["complete", "refused"]
    reason: Reason | None

    def __post_init__(self) -> None:
        _require(type(self.input_bcf) is ArtifactRef and type(self.requested_samples) is ArtifactRef,
                 "invalid native count inputs")
        _require(type(self.runs) is tuple and all(type(item) is NativeRunReceipt for item in self.runs),
                 "invalid native count runs")
        _require(
            all(
                item is None or type(item) is ArtifactRef
                for item in (self.selected_bcf, self.recomputed_bcf, self.selected_samples, self.totals)
            ),
            "invalid native count file",
        )
        _require(self.state in ("complete", "refused"), "invalid native count state")
        _reason(self.reason, required=self.state == "refused")
        if self.state == "complete":
            _require(all(type(item) is ArtifactRef for item in (
                self.selected_bcf, self.recomputed_bcf, self.selected_samples, self.totals
            )), "complete native counts require all files")
            _require(bool(self.runs) and all(run.state == "complete" for run in self.runs),
                     "complete native counts require complete runs")


@dataclass(frozen=True)
class AcquisitionSourceReceipt:
    source: SourcePair
    retained_index: ArtifactRef
    metadata: MetadataReceipt
    ranges: tuple[RangeReceipt, ...]
    state: Literal["ready", "refused"]
    reason: Reason | None
    verified: VerifiedSource | None
    header: HeaderReceipt | None

    def __post_init__(self) -> None:
        _require(type(self.source) is SourcePair and type(self.retained_index) is ArtifactRef,
                 "invalid acquisition source")
        _require(type(self.metadata) is MetadataReceipt, "invalid source metadata receipt")
        _require(type(self.ranges) is tuple and all(type(item) is RangeReceipt for item in self.ranges),
                 "invalid source range receipts")
        _require(all(item.chrom == self.source.chrom for item in self.ranges),
                 "source range chromosome mismatch")
        _require(all(item.generation == self.source.vcf.generation for item in self.ranges),
                 "source range generation mismatch")
        _require(self.state in ("ready", "refused"), "invalid acquisition source state")
        _reason(self.reason, required=self.state == "refused")
        _require(self.verified is None or type(self.verified) is VerifiedSource, "invalid verified source")
        _require(self.header is None or type(self.header) is HeaderReceipt, "invalid source header")
        if self.state == "ready":
            _require(type(self.verified) is VerifiedSource and type(self.header) is HeaderReceipt,
                     "ready source requires verified coverage and header")
            _require(
                self.metadata.state == "verified"
                and all(item.state == "verified" for item in self.ranges),
                "ready source requires verified transport",
            )
            _require(self.verified.source == self.source and self.verified.index == self.retained_index,
                     "ready source identity mismatch")


@dataclass(frozen=True)
class AcquisitionWindowReceipt:
    window_id: str
    chrom: str
    state: Literal["records_acquired", "no_records", "refused"]
    reason: Reason | None
    raw_records: int | None
    native_records: int | None
    raw: ArtifactRef | None
    offsets: ArtifactRef | None
    native_bcf: ArtifactRef | None
    native_keys: ArtifactRef | None
    native_runs: tuple[NativeRunReceipt, ...]

    def __post_init__(self) -> None:
        _text(self.window_id, "window_id")
        _require(self.chrom in AUTOSOMES and self.window_id.startswith(f"{self.chrom}-s"),
                 "window chromosome mismatch")
        _require(self.state in ("records_acquired", "no_records", "refused"), "invalid window state")
        _reason(self.reason, required=self.state == "refused")
        for field in ("raw_records", "native_records"):
            value = getattr(self, field)
            _require(value is None or type(value) is int, f"invalid {field}")
            if value is not None:
                _count(value, field)
        for field in ("raw", "offsets", "native_bcf", "native_keys"):
            value = getattr(self, field)
            _require(value is None or type(value) is ArtifactRef, f"invalid {field} artifact")
        _require(
            type(self.native_runs) is tuple
            and all(type(item) is NativeRunReceipt for item in self.native_runs),
            "invalid native window runs",
        )
        if self.state != "refused":
            _require(self.raw_records is not None and self.native_records is not None,
                     "successful window requires known counts")
            _require(all(type(item) is ArtifactRef for item in (
                self.raw, self.offsets, self.native_bcf, self.native_keys
            )), "successful window requires all artifacts")
            _require(self.raw_records == self.native_records, "raw/native record counts differ")
            _require(all(run.state == "complete" for run in self.native_runs),
                     "successful window requires complete native runs")
        if self.state == "records_acquired":
            _require(self.raw_records is not None and self.raw_records > 0,
                     "records_acquired window must be nonempty")
        if self.state == "no_records":
            _require(self.raw_records == self.native_records == 0, "no_records window must be empty")


@dataclass(frozen=True)
class AcquisitionTotals:
    planned_bytes_including_indexes: int
    retained_index_bytes: int
    inherited_index_received_bytes: int
    vcf_requested_bytes: int
    vcf_received_bytes: int
    range_adapter_invocations: int
    metadata_adapter_invocations: int
    metadata_stdout_bytes: int
    metadata_http_attempts: None
    body_http_attempts: None
    wire_bytes: None

    def __post_init__(self) -> None:
        for field in (
            "planned_bytes_including_indexes", "retained_index_bytes",
            "inherited_index_received_bytes", "vcf_requested_bytes", "vcf_received_bytes",
            "range_adapter_invocations", "metadata_adapter_invocations", "metadata_stdout_bytes",
        ):
            _count(getattr(self, field), field)
        _require(self.metadata_http_attempts is self.body_http_attempts is self.wire_bytes is None,
                 "unobserved transport totals must be null")


@dataclass(frozen=True)
class AcquisitionManifest:
    schema_version: Literal["reference_window_acquisition_v1"]
    inputs: AcquisitionInputs
    provenance: RunProvenance
    policy: tuple[tuple[str, str | int], ...]
    sources: tuple[AcquisitionSourceReceipt, ...]
    windows: tuple[AcquisitionWindowReceipt, ...]
    files: tuple[ArtifactRef, ...]
    totals: AcquisitionTotals
    complete: bool
    publication_eligible: Literal[False]
    p1_eligible: Literal[False]
    benchmark_admitted: Literal[False]

    def __post_init__(self) -> None:
        _require(self.schema_version == "reference_window_acquisition_v1", "unsupported acquisition schema")
        _require(type(self.inputs) is AcquisitionInputs and type(self.provenance) is RunProvenance,
                 "invalid acquisition inputs or provenance")
        _require(self.policy == ACQUISITION_POLICY, "unsupported acquisition policy")
        _require(
            type(self.sources) is tuple
            and all(type(item) is AcquisitionSourceReceipt for item in self.sources),
            "invalid acquisition sources",
        )
        _require(tuple(item.source.chrom for item in self.sources) == AUTOSOMES,
                 "acquisition sources must be natural autosomes")
        expected_ids = tuple(f"chr{chrom}-s{stratum}" for chrom in range(1, 23) for stratum in range(1, 4))
        _require(
            type(self.windows) is tuple
            and all(type(item) is AcquisitionWindowReceipt for item in self.windows),
            "invalid acquisition windows",
        )
        _require(tuple(item.window_id for item in self.windows) == expected_ids,
                 "acquisition windows must contain the frozen 66 IDs")
        _require(type(self.files) is tuple and all(type(item) is ArtifactRef for item in self.files),
                 "invalid acquisition files")
        _require(tuple(item.path for item in self.files) == tuple(sorted(item.path for item in self.files)),
                 "acquisition files must be path-sorted")
        _require(len({item.path for item in self.files}) == len(self.files), "duplicate acquisition file")
        _require(type(self.totals) is AcquisitionTotals and type(self.complete) is bool,
                 "invalid acquisition totals or completeness")
        expected_complete = all(source.state == "ready" for source in self.sources) and all(
            window.state != "refused" for window in self.windows
        )
        _require(self.complete is expected_complete, "acquisition completeness disagrees with receipts")
        _require(self.publication_eligible is False and self.p1_eligible is False
                 and self.benchmark_admitted is False, "acquisition eligibility must remain false")
