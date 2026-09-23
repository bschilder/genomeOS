"""Immutable acquisition outcome records (reference acquisition design §§4.1, 6.1)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from genomeos.validation.reference_acquisition_evidence import (
    ACQUISITION_POLICY,
    REASONS,
    AcquisitionInputs,
    AcquisitionReviewBundle,
    ArtifactRef,
    CohortInputHashes,
    HeaderReceipt,
    MetadataReceipt,
    NativeCountFiles,
    NativeRunReceipt,
    NativeTokenFiles,
    RangeReceipt,
    Reason,
    RetainedIndex,
    ReviewReceipt,
    RunProvenance,
    VerifiedRange,
    VerifiedSource,
    nonnegative_count,
    require,
    validate_reason,
    validated_text,
)
from genomeos.validation.reference_window_types import AUTOSOMES, SourcePair

__all__ = [
    "ACQUISITION_POLICY",
    "REASONS",
    "AcquisitionInputs",
    "AcquisitionManifest",
    "AcquisitionReviewBundle",
    "AcquisitionSourceReceipt",
    "AcquisitionTotals",
    "AcquisitionWindowReceipt",
    "ArtifactRef",
    "CohortInputHashes",
    "HeaderReceipt",
    "MetadataReceipt",
    "NativeCountFiles",
    "NativeRunReceipt",
    "NativeTokenFiles",
    "RangeReceipt",
    "RetainedIndex",
    "ReviewReceipt",
    "RunProvenance",
    "VerifiedRange",
    "VerifiedSource",
]


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
        require(
            type(self.source) is SourcePair and type(self.retained_index) is ArtifactRef,
            "invalid acquisition source",
        )
        require(type(self.metadata) is MetadataReceipt, "invalid source metadata receipt")
        require(
            type(self.ranges) is tuple and all(type(item) is RangeReceipt for item in self.ranges),
            "invalid source range receipts",
        )
        require(
            all(item.chrom == self.source.chrom for item in self.ranges), "source range chromosome mismatch"
        )
        require(
            all(item.generation == self.source.vcf.generation for item in self.ranges),
            "source range generation mismatch",
        )
        require(self.state in ("ready", "refused"), "invalid acquisition source state")
        validate_reason(self.reason, required=self.state == "refused")
        require(self.verified is None or type(self.verified) is VerifiedSource, "invalid verified source")
        require(self.header is None or type(self.header) is HeaderReceipt, "invalid source header")
        if self.metadata.state != "verified":
            require(
                all(
                    item.state == "not_attempted" and item.reason == self.metadata.reason
                    for item in self.ranges
                ),
                "metadata refusal must stop all range attempts",
            )
            require(
                self.state == "refused"
                and self.reason == self.metadata.reason
                and self.verified is None
                and self.header is None,
                "source outcome differs from metadata refusal",
            )
        else:
            range_failure: str | None = None
            for item in self.ranges:
                if range_failure is None and item.state == "verified":
                    continue
                if range_failure is None:
                    require(
                        item.state in ("partial", "refused"),
                        "first failed range must record its attempted result",
                    )
                    range_failure = item.reason
                else:
                    require(
                        item.state == "not_attempted" and item.reason == range_failure,
                        "range attempts continued after the first failure",
                    )
            if range_failure is not None:
                require(
                    self.state == "refused"
                    and self.reason == range_failure
                    and self.verified is None
                    and self.header is None,
                    "source outcome differs from range refusal",
                )
            elif self.state == "refused":
                require(
                    self.verified is not None
                    and self.header is None
                    and self.reason
                    in {
                        "header_invalid",
                        "sample_mismatch",
                        "limit_exceeded",
                        "artifact_mismatch",
                    },
                    "source outcome differs from header refusal",
                )
        if self.verified is not None:
            require(
                self.verified.source == self.source and self.verified.index == self.retained_index,
                "verified source identity mismatch",
            )
            require(
                all(item.state == "verified" and item.retained is not None for item in self.ranges)
                and self.verified.ranges
                == tuple(VerifiedRange(item.first, item.last, item.retained) for item in self.ranges),
                "verified source ranges differ from transport receipts",
            )
        if self.state == "ready":
            require(
                type(self.verified) is VerifiedSource and type(self.header) is HeaderReceipt,
                "ready source requires verified coverage and header",
            )
            require(
                self.metadata.state == "verified" and all(item.state == "verified" for item in self.ranges),
                "ready source requires verified transport",
            )


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
        validated_text(self.window_id, "window_id")
        require(
            self.chrom in AUTOSOMES and self.window_id.startswith(f"{self.chrom}-s"),
            "window chromosome mismatch",
        )
        require(self.state in ("records_acquired", "no_records", "refused"), "invalid window state")
        validate_reason(self.reason, required=self.state == "refused")
        for field in ("raw_records", "native_records"):
            value = getattr(self, field)
            require(value is None or type(value) is int, f"invalid {field}")
            if value is not None:
                nonnegative_count(value, field)
        for field in ("raw", "offsets", "native_bcf", "native_keys"):
            value = getattr(self, field)
            require(value is None or type(value) is ArtifactRef, f"invalid {field} artifact")
        require(
            type(self.native_runs) is tuple
            and all(type(item) is NativeRunReceipt for item in self.native_runs),
            "invalid native window runs",
        )
        require(
            len(self.native_runs) <= 2
            and tuple(run.operation for run in self.native_runs)
            == ("extract_bcf", "query_keys")[: len(self.native_runs)],
            "native window run order mismatch",
        )
        refused = tuple(index for index, run in enumerate(self.native_runs) if run.state == "refused")
        require(
            not refused or refused == (len(self.native_runs) - 1,),
            "native window runs continued after a refused process",
        )
        require(
            self.native_bcf == (self.native_runs[0].stdout if len(self.native_runs) >= 1 else None)
            and self.native_keys == (self.native_runs[1].stdout if len(self.native_runs) >= 2 else None),
            "native window products lack process lineage",
        )
        if refused:
            require(
                self.state == "refused" and self.reason == self.native_runs[-1].reason,
                "native window outcome differs from its failed process",
            )
        elif self.state == "refused" and self.native_runs:
            valid_postprocess_refusal = (
                len(self.native_runs) == 1 and self.reason == "artifact_mismatch"
            ) or (
                len(self.native_runs) == 2
                and self.reason in {"artifact_mismatch", "native_mismatch"}
            )
            require(
                valid_postprocess_refusal,
                "successful native window controls have an invalid refusal",
            )
        if self.state != "refused":
            require(
                self.raw_records is not None and self.native_records is not None,
                "successful window requires known counts",
            )
            require(
                all(
                    type(item) is ArtifactRef
                    for item in (self.raw, self.offsets, self.native_bcf, self.native_keys)
                ),
                "successful window requires all artifacts",
            )
            require(self.raw_records == self.native_records, "raw/native record counts differ")
            require(
                len(self.native_runs) == 2
                and all(run.state == "complete" for run in self.native_runs),
                "successful window requires complete native runs",
            )
        else:
            require(
                self.native_records is None,
                "refused window cannot claim a native record count",
            )
            require(
                (self.raw_records is None) == (self.raw is None and self.offsets is None),
                "refused raw count and evidence disagree",
            )
            require(
                (self.raw is None) == (self.offsets is None),
                "refused original evidence is incomplete",
            )
            require(
                bool(self.native_runs) is (self.raw is not None),
                "refused native execution disagrees with original evidence",
            )
        if self.state == "records_acquired":
            require(
                self.raw_records is not None and self.raw_records > 0,
                "records_acquired window must be nonempty",
            )
        if self.state == "no_records":
            require(self.raw_records == self.native_records == 0, "no_records window must be empty")


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
            "planned_bytes_including_indexes",
            "retained_index_bytes",
            "inherited_index_received_bytes",
            "vcf_requested_bytes",
            "vcf_received_bytes",
            "range_adapter_invocations",
            "metadata_adapter_invocations",
            "metadata_stdout_bytes",
        ):
            nonnegative_count(getattr(self, field), field)
        require(
            self.metadata_http_attempts is self.body_http_attempts is self.wire_bytes is None,
            "unobserved transport totals must be null",
        )


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
        require(self.schema_version == "reference_window_acquisition_v1", "unsupported acquisition schema")
        require(
            type(self.inputs) is AcquisitionInputs and type(self.provenance) is RunProvenance,
            "invalid acquisition inputs or provenance",
        )
        require(self.policy == ACQUISITION_POLICY, "unsupported acquisition policy")
        require(
            type(self.sources) is tuple
            and all(type(item) is AcquisitionSourceReceipt for item in self.sources),
            "invalid acquisition sources",
        )
        require(
            tuple(item.source.chrom for item in self.sources) == AUTOSOMES,
            "acquisition sources must be natural autosomes",
        )
        expected_ids = tuple(f"chr{chrom}-s{stratum}" for chrom in range(1, 23) for stratum in range(1, 4))
        require(
            type(self.windows) is tuple
            and all(type(item) is AcquisitionWindowReceipt for item in self.windows),
            "invalid acquisition windows",
        )
        require(
            tuple(item.window_id for item in self.windows) == expected_ids,
            "acquisition windows must contain the frozen 66 IDs",
        )
        require(
            type(self.files) is tuple and all(type(item) is ArtifactRef for item in self.files),
            "invalid acquisition files",
        )
        require(
            tuple(item.path for item in self.files) == tuple(sorted(item.path for item in self.files)),
            "acquisition files must be path-sorted",
        )
        require(len({item.path for item in self.files}) == len(self.files), "duplicate acquisition file")
        require(
            type(self.totals) is AcquisitionTotals and type(self.complete) is bool,
            "invalid acquisition totals or completeness",
        )
        expected_complete = all(source.state == "ready" for source in self.sources) and all(
            window.state != "refused" for window in self.windows
        )
        require(self.complete is expected_complete, "acquisition completeness disagrees with receipts")
        require(
            self.publication_eligible is False
            and self.p1_eligible is False
            and self.benchmark_admitted is False,
            "acquisition eligibility must remain false",
        )
