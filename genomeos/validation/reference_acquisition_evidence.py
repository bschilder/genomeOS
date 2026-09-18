"""Transport and native-process evidence records (reference acquisition design §6.1)."""

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


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validated_text(value: object, field: str) -> str:
    require(isinstance(value, str) and bool(value.strip()) and value == value.strip(), f"invalid {field}")
    return value


def nonnegative_count(value: object, field: str) -> int:
    require(type(value) is int and value >= 0, f"{field} must be an integer >= 0")
    return value


def _sha(value: object, field: str) -> str:
    require(isinstance(value, str) and _SHA256.fullmatch(value) is not None, f"invalid {field} sha256")
    return value


def _revision(value: object, field: str) -> str:
    require(isinstance(value, str) and _REVISION.fullmatch(value) is not None, f"invalid {field}")
    return value


def _relpath(value: object, field: str) -> str:
    text = validated_text(value, field)
    path = PurePosixPath(text)
    require("\\" not in text and not path.is_absolute(), f"invalid {field}")
    require(all(part not in ("", ".", "..") for part in path.parts), f"invalid {field}")
    require(str(path) == text, f"noncanonical {field}")
    return text


def _hash_entries(value: object, field: str) -> HashEntries:
    require(type(value) is tuple, f"{field} must be a tuple")
    entries = []
    for item in value:
        require(type(item) is tuple and len(item) == 2, f"invalid {field} entry")
        entries.append((_relpath(item[0], f"{field} key"), _sha(item[1], f"{field} value")))
    require(tuple(entries) == tuple(sorted(entries)), f"{field} must be key-sorted")
    require(len({key for key, _ in entries}) == len(entries), f"{field} keys must be unique")
    return tuple(entries)


def validated_text_entries(value: object, field: str) -> tuple[tuple[str, str], ...]:
    require(type(value) is tuple, f"{field} must be a tuple")
    entries = []
    for item in value:
        require(type(item) is tuple and len(item) == 2, f"invalid {field} entry")
        entries.append((validated_text(item[0], f"{field} key"), validated_text(item[1], f"{field} value")))
    require(tuple(entries) == tuple(sorted(entries)), f"{field} must be key-sorted")
    require(len({key for key, _ in entries}) == len(entries), f"{field} keys must be unique")
    return tuple(entries)


def validate_reason(value: object, *, required: bool) -> None:
    require(
        (isinstance(value, str) and value in REASONS) if required else (value is None),
        "invalid refusal reason",
    )


def _bounded_output(size: int, limit: int, exceeded: bool, field: str) -> None:
    require(
        size == limit + 1 if exceeded else size <= limit,
        f"{field} size disagrees with its limit state",
    )


@dataclass(frozen=True)
class ArtifactRef:
    path: str
    size_bytes: int
    sha256: str

    def __post_init__(self) -> None:
        _relpath(self.path, "artifact path")
        nonnegative_count(self.size_bytes, "artifact size_bytes")
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
        require(self.schema_version == "reference_preflight_review_v1", "unsupported review schema_version")
        _sha(self.manifest_sha256, "review manifest")
        _sha(self.preflight_sha256, "review preflight")
        _revision(self.implementation_revision, "review implementation_revision")
        _hash_entries(self.implementation_sha256, "review implementation_sha256")
        validated_text(self.review_locator, "review_locator")
        _sha(self.review_sha256, "review")
        require(self.status == "accepted", "review status must be accepted")


@dataclass(frozen=True)
class AcquisitionReviewBundle:
    schema_version: Literal["reference_acquisition_review_bundle_v1"]
    preflight: ReviewReceipt
    implementation_revision: str
    implementation_sha256: HashEntries
    review_locator: str
    review_sha256: str
    status: Literal["accepted"]

    def __post_init__(self) -> None:
        require(
            self.schema_version == "reference_acquisition_review_bundle_v1",
            "unsupported acquisition review schema_version",
        )
        require(type(self.preflight) is ReviewReceipt, "invalid preflight review receipt")
        _revision(self.implementation_revision, "acquisition review implementation_revision")
        _hash_entries(self.implementation_sha256, "acquisition review implementation_sha256")
        validated_text(self.review_locator, "acquisition review_locator")
        _sha(self.review_sha256, "acquisition review")
        require(self.status == "accepted", "acquisition review status must be accepted")


@dataclass(frozen=True)
class RetainedIndex:
    chrom: str
    raw: bytes

    def __post_init__(self) -> None:
        require(self.chrom in AUTOSOMES, "invalid retained index chromosome")
        require(type(self.raw) is bytes and bool(self.raw), "retained index must be nonempty bytes")


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
        validated_text(self.python_version, "python_version")
        _hash_entries(self.imported_source_sha256, "imported_source_sha256")
        validated_text_entries(self.tool_versions, "tool_versions")
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
            require(type(getattr(self, field)) is ArtifactRef, f"invalid {field}")
        require(type(self.cohort) is CohortInputHashes, "invalid cohort")


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
        require(self.chrom in AUTOSOMES, "invalid range chromosome")
        require(
            isinstance(self.generation, str) and re.fullmatch(r"[1-9][0-9]*", self.generation) is not None,
            "invalid range generation",
        )
        first, last = nonnegative_count(self.first, "range first"), nonnegative_count(self.last, "range last")
        require(first <= last, "range is reversed")
        requested = nonnegative_count(self.requested_bytes, "requested_bytes")
        received = nonnegative_count(self.received_bytes, "received_bytes")
        invocations = nonnegative_count(self.adapter_invocations, "adapter_invocations")
        require(invocations <= 1, "adapter_invocations exceeds one")
        require(self.state in ("verified", "partial", "refused", "not_attempted"), "invalid range state")
        require(
            type(self.stdout_limit_exceeded) is bool and type(self.stderr_limit_exceeded) is bool,
            "range limit flags must be bool",
        )
        attempted = self.state != "not_attempted"
        require((invocations == 1) is attempted, "range invocation disagrees with state")
        require(requested == (last - first + 1 if attempted else 0), "requested_bytes disagree with range")
        require(received <= requested + (1 if attempted else 0), "received_bytes exceeds bounded request")
        validate_reason(self.reason, required=self.state != "verified")
        if attempted:
            require(
                type(self.retained) is ArtifactRef and type(self.stderr) is ArtifactRef,
                "attempted range requires retained stdout and stderr",
            )
            require(
                self.retained.path.endswith(".partial") is (self.state != "verified"),
                "failed range output must use the .partial suffix",
            )
            require(
                self.stderr.path.endswith(".partial") is (self.state != "verified"),
                "failed range stderr must use the .partial suffix",
            )
            require(
                self.sha256 == self.retained.sha256 and received == self.retained.size_bytes,
                "range retained identity mismatch",
            )
            require(self.exit_code is None or type(self.exit_code) is int, "invalid range exit_code")
            _bounded_output(received, requested, self.stdout_limit_exceeded, "range stdout")
            _bounded_output(self.stderr.size_bytes, 1_048_576, self.stderr_limit_exceeded, "range stderr")
        else:
            require(
                received == 0 and self.sha256 is None and self.retained is None and self.stderr is None,
                "not-attempted range cannot retain output",
            )
            require(
                self.exit_code is None and not self.stdout_limit_exceeded and not self.stderr_limit_exceeded,
                "not-attempted range has process state",
            )
        if self.state == "verified":
            require(received == requested and self.exit_code == 0, "verified range is incomplete")
            require(
                not self.stdout_limit_exceeded and not self.stderr_limit_exceeded,
                "verified range exceeded a limit",
            )
        if self.stdout_limit_exceeded or self.stderr_limit_exceeded:
            require(self.reason == "limit_exceeded", "range overflow requires limit_exceeded")
            require(self.state == "refused", "range overflow must be refused")
        elif attempted and self.state != "verified":
            require(self.state == "partial", "non-overflow range failure must be partial")
            if self.exit_code == 0:
                require(
                    self.reason == "size_mismatch" and received != requested,
                    "zero-exit range refusal must prove a size mismatch",
                )
            else:
                require(
                    self.reason in {"timeout", "transfer_failed"},
                    "failed range process has an invalid reason",
                )


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
        require(self.state in ("verified", "refused", "not_attempted"), "invalid metadata state")
        invocations = nonnegative_count(self.adapter_invocations, "metadata adapter_invocations")
        size = nonnegative_count(self.stdout_bytes, "metadata stdout_bytes")
        require(invocations <= 1 and size <= 1_048_577, "metadata output exceeds limit")
        require(
            type(self.stdout_limit_exceeded) is bool and type(self.stderr_limit_exceeded) is bool,
            "metadata limit flags must be bool",
        )
        attempted = self.state != "not_attempted"
        require((invocations == 1) is attempted, "metadata invocation disagrees with state")
        validate_reason(self.reason, required=self.state != "verified")
        if attempted:
            require(
                type(self.retained) is ArtifactRef and self.retained.size_bytes == size,
                "attempted metadata requires retained stdout",
            )
            require(type(self.stderr) is ArtifactRef, "attempted metadata requires retained stderr")
            require(
                self.retained.path.endswith(".partial") is (self.state == "refused")
                and self.stderr.path.endswith(".partial") is (self.state == "refused"),
                "refused metadata output must use the .partial suffix",
            )
            require(self.exit_code is None or type(self.exit_code) is int, "invalid metadata exit_code")
            _bounded_output(size, 1_048_576, self.stdout_limit_exceeded, "metadata stdout")
            _bounded_output(
                self.stderr.size_bytes,
                1_048_576,
                self.stderr_limit_exceeded,
                "metadata stderr",
            )
        else:
            require(
                size == 0 and self.retained is None and self.stderr is None and self.exit_code is None,
                "not-attempted metadata has process output",
            )
            require(
                not self.stdout_limit_exceeded and not self.stderr_limit_exceeded,
                "not-attempted metadata has limit state",
            )
        if self.state == "verified":
            require(
                self.exit_code == 0 and not self.stdout_limit_exceeded and not self.stderr_limit_exceeded,
                "verified metadata has failed process state",
            )
        if self.stdout_limit_exceeded or self.stderr_limit_exceeded:
            require(self.reason == "limit_exceeded", "metadata overflow requires limit_exceeded")
        elif attempted and self.state == "refused":
            if self.exit_code == 0:
                require(
                    self.reason == "metadata_mismatch",
                    "zero-exit metadata refusal must be metadata_mismatch",
                )
            else:
                require(
                    self.reason in {"timeout", "generation_unavailable"},
                    "failed metadata process has an invalid reason",
                )


@dataclass(frozen=True)
class VerifiedRange:
    first: int
    last: int
    range_file: ArtifactRef

    def __post_init__(self) -> None:
        require(
            nonnegative_count(self.first, "verified range first")
            <= nonnegative_count(self.last, "verified range last"),
            "verified range is reversed",
        )
        require(type(self.range_file) is ArtifactRef, "invalid verified range file")
        require(
            self.range_file.size_bytes == self.last - self.first + 1, "verified range file size mismatch"
        )


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
        require(type(self.source) is SourcePair, "invalid verified source")
        require(
            type(self.ranges) is tuple and all(type(item) is VerifiedRange for item in self.ranges),
            "invalid verified ranges",
        )
        require(
            tuple((item.first, item.last) for item in self.ranges)
            == tuple(sorted((item.first, item.last) for item in self.ranges)),
            "verified ranges must be sorted",
        )
        require(
            all(left.last < right.first for left, right in zip(self.ranges, self.ranges[1:], strict=False)),
            "verified ranges must be disjoint",
        )
        _relpath(self.sparse_path, "sparse_path")
        require(type(self.index) is ArtifactRef, "invalid verified index")
        require(
            nonnegative_count(self.logical_size_bytes, "logical_size_bytes") == self.source.vcf.size_bytes,
            "logical source size mismatch",
        )
        nonnegative_count(self.allocated_size_bytes, "allocated_size_bytes")
        require(self.full_object_verified is False, "full_object_verified must be false")


@dataclass(frozen=True)
class HeaderReceipt:
    header: ArtifactRef
    ordered_samples_sha256: str
    sample_count: int
    sample_identity: Literal["exact_metadata_plus_control"]
    contig_identity: Literal["frozen_manifest_assembly_and_lengths"]
    required_formats: Literal["verified"]

    def __post_init__(self) -> None:
        require(type(self.header) is ArtifactRef, "invalid header artifact")
        _sha(self.ordered_samples_sha256, "ordered samples")
        nonnegative_count(self.sample_count, "sample_count")
        require(self.sample_identity == "exact_metadata_plus_control", "invalid sample identity")
        require(self.contig_identity == "frozen_manifest_assembly_and_lengths", "invalid contig identity")
        require(self.required_formats == "verified", "required formats are not verified")


@dataclass(frozen=True)
class NativeRunReceipt:
    operation: Literal[
        "extract_bcf",
        "query_keys",
        "select_cohort",
        "fill_tags",
        "query_samples",
        "query_tokens",
        "query_totals",
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
        require(self.operation in NATIVE_OPERATIONS, "invalid native operation")
        require(type(self.argv_template) is tuple and bool(self.argv_template), "invalid argv_template")
        for token in self.argv_template:
            validated_text(token, "argv_template token")
            require(not token.startswith("/"), "argv_template contains an absolute path")
        require(self.state in ("complete", "refused"), "invalid native state")
        validate_reason(self.reason, required=self.state == "refused")
        require(self.exit_code is None or type(self.exit_code) is int, "invalid native exit_code")
        require(
            type(self.stdout) is ArtifactRef and type(self.stderr) is ArtifactRef,
            "native run requires output artifacts",
        )
        require(
            self.stdout.path.endswith(".partial") is (self.state == "refused")
            and self.stderr.path.endswith(".partial") is (self.state == "refused"),
            "refused native output must use the .partial suffix",
        )
        stdout_limit = nonnegative_count(self.stdout_limit_bytes, "stdout_limit_bytes")
        stderr_limit = nonnegative_count(self.stderr_limit_bytes, "stderr_limit_bytes")
        require(
            type(self.stdout_limit_exceeded) is bool and type(self.stderr_limit_exceeded) is bool,
            "native limit flags must be bool",
        )
        _bounded_output(
            self.stdout.size_bytes,
            stdout_limit,
            self.stdout_limit_exceeded,
            "native stdout",
        )
        _bounded_output(
            self.stderr.size_bytes,
            stderr_limit,
            self.stderr_limit_exceeded,
            "native stderr",
        )
        if self.state == "complete":
            require(
                self.exit_code == 0 and not self.stdout_limit_exceeded and not self.stderr_limit_exceeded,
                "complete native run has failed process state",
            )
        if self.stdout_limit_exceeded or self.stderr_limit_exceeded:
            require(self.reason == "limit_exceeded", "native overflow requires limit_exceeded")
        elif self.state == "refused":
            require(
                self.exit_code != 0
                and self.reason in {"timeout", "native_encoding_refused"},
                "failed native process has an invalid reason",
            )


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
        require(
            type(self.input_bcf) is ArtifactRef and type(self.sample_query) is NativeRunReceipt,
            "invalid native token inputs",
        )
        require(self.samples is None or type(self.samples) is ArtifactRef, "invalid native sample file")
        require(self.tokens is None or type(self.tokens) is ArtifactRef, "invalid native token file")
        require(
            self.token_query is None or type(self.token_query) is NativeRunReceipt,
            "invalid native token query",
        )
        require(self.state in ("complete", "refused"), "invalid native token state")
        validate_reason(self.reason, required=self.state == "refused")
        require(self.sample_query.operation == "query_samples", "invalid native sample query")
        if self.sample_query.state == "complete":
            require(self.samples == self.sample_query.stdout, "native samples lack process lineage")
        else:
            require(
                self.samples is None and self.token_query is None,
                "refused sample query cannot admit token outputs",
            )
        if self.token_query is not None:
            require(self.token_query.operation == "query_tokens", "invalid native token query")
            require(
                self.tokens == (self.token_query.stdout if self.token_query.state == "complete" else None),
                "native tokens lack process lineage",
            )
        refused_run = (
            self.sample_query
            if self.sample_query.state == "refused"
            else self.token_query
            if self.token_query is not None and self.token_query.state == "refused"
            else None
        )
        if refused_run is not None:
            require(
                self.state == "refused" and self.reason == refused_run.reason,
                "native token outcome differs from its failed process",
            )
        else:
            require(
                self.token_query is not None and self.state == "complete",
                "complete native token runs cannot be refused or omitted",
            )
        if self.state == "complete":
            require(
                type(self.samples) is ArtifactRef and type(self.tokens) is ArtifactRef,
                "complete native tokens require files",
            )
            require(type(self.token_query) is NativeRunReceipt, "complete native tokens require token query")
            require(
                self.sample_query.state == self.token_query.state == "complete",
                "complete native token query has refused run",
            )


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
        require(
            type(self.input_bcf) is ArtifactRef and type(self.requested_samples) is ArtifactRef,
            "invalid native count inputs",
        )
        require(
            type(self.runs) is tuple and all(type(item) is NativeRunReceipt for item in self.runs),
            "invalid native count runs",
        )
        require(
            all(
                item is None or type(item) is ArtifactRef
                for item in (self.selected_bcf, self.recomputed_bcf, self.selected_samples, self.totals)
            ),
            "invalid native count file",
        )
        require(self.state in ("complete", "refused"), "invalid native count state")
        validate_reason(self.reason, required=self.state == "refused")
        operations = ("select_cohort", "fill_tags", "query_samples", "query_totals")
        require(
            1 <= len(self.runs) <= len(operations)
            and tuple(run.operation for run in self.runs) == operations[: len(self.runs)],
            "native count run order mismatch",
        )
        refused = tuple(index for index, run in enumerate(self.runs) if run.state == "refused")
        require(
            not refused or refused == (len(self.runs) - 1,),
            "native count runs continued after a refused process",
        )
        products = (self.selected_bcf, self.recomputed_bcf, self.selected_samples, self.totals)
        for index, product in enumerate(products):
            expected = (
                self.runs[index].stdout
                if index < len(self.runs) and self.runs[index].state == "complete"
                else None
            )
            require(product == expected, "native count product lacks process lineage")
        if refused:
            require(
                self.state == "refused" and self.reason == self.runs[-1].reason,
                "native count outcome differs from its failed process",
            )
        elif self.state == "refused":
            valid_postprocess_refusal = (
                self.reason == "artifact_mismatch" and len(self.runs) in (1, 2)
            ) or (
                self.reason in {"native_encoding_refused", "native_mismatch"}
                and len(self.runs) == 3
            )
            require(valid_postprocess_refusal, "successful native count prefix has an invalid refusal")
        if self.state == "complete":
            require(
                all(
                    type(item) is ArtifactRef
                    for item in (self.selected_bcf, self.recomputed_bcf, self.selected_samples, self.totals)
                ),
                "complete native counts require all files",
            )
            require(
                bool(self.runs) and all(run.state == "complete" for run in self.runs),
                "complete native counts require complete runs",
            )
