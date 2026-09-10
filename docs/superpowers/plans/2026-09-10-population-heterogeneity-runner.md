# Minimum B0H Runner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run and reduce the frozen 1,938-record B0H campaign while preserving every returned outcome and refusing ambiguous scientific redelivery.

**Architecture:** One offline worker owns one SQLite database through a campaign-wide process lock. It commits each START before one existing public scientific call, then commits exact codec evidence, its receipt and completion together. A separate pure reducer uses retained, dataset-bound evidence and the one prepared N512 null.

**Tech Stack:** Python 3.12, standard-library SQLite/hashlib/fcntl/json, existing NumPy, Pydantic v2 and B0H scientific public interfaces. CuPy is the fixed CDF backend; this plan installs no dependency.

**Spec:** `docs/superpowers/specs/2026-09-10-population-heterogeneity-runner-design.md`, adopted at `c75e0b68c9a7ee4b79ed7280b8434e70cc13e921` in `/private/tmp/genomeos-b0h-runner.1CHMA3`, personally read completely by this planner after adoption.

## Global Constraints

- Protocol `b0h_sbc_v1`; preserve all 1,938 cases in `enumerate_sbc_cases()` order.
- One worker, one GPU, one operational delivery per stage/attempt; no queue, leases, timeout takeover, cloud launcher, optional backend, online backup or operational redelivery.
- SQLite `journal_mode=DELETE`, `synchronous=EXTRA`, explicit transactions and foreign keys; immutable INSERT-only logical records with exact scientific BLOBs.
- The only campaign database filename is `study.sqlite3` in the exact admitted canonical parent directory. This binds one store and one stable lock path per campaign; alternate aliases/names cannot create duplicate deliveries.
- Commit START before calling science; result/payload/receipt/COMPLETE share one later transaction. A receipt without COMPLETE is corruption.
- Known live evidence can retry publication of identical bytes; START-only process loss never retries science.
- Only a complete actual attempt0 `convergence_failed` result admits attempt1; preserve both attempts and use only accepted-attempt arrays.
- CuPy is fixed before study results; no alternate-backend rescue.
- Prepare `simulate_rank_null(sample_size=512, replicates=100000, seed=1653499886)` before manifest creation. Bind the full exact null record digest, including entropy `(42,211,1,100,0,0,0,0,0)`.
- Reuse existing public codec and scientific constructors/functions. No new likelihood, integration, seed selection, ranks, prior, fitting, convergence or predictive algorithm.
- Pure validation modules have no filesystem, network, HTTP, environment or UI dependency.
- Stochastic modules declare `SEED = 42`; inputs and configuration determine draws on a pinned runtime.
- No new package dependency, P1/production schema, serving change, inferred coordinate or radius.
- Keep existing clinical gates and global promotion defaults unchanged.
- AN=0 is retained as unavailable, never converted to frequency zero.
- No cross-variant pooling or independence claim for linked loci.
- All sampler/prior/scorer/convergence contracts in the parent B0H spec stand.
- Existing analytical, quadrature and numerical regression thresholds stay unchanged.
- Production modules target at most500 logical lines; retain the hard800/50KiB gate.
- No NUTS, complete calibration study, cloud operation, Git mutation or production-source edit occurs while drafting this document.
- Runtime/storage measurements are future admission evidence, not facts established by the eight-case timing pilot or these fixture tests.
- Advance #211/#189; close neither. Root owns branch adoption, stable full suite, broad review, push and PR.
- Executors may read/write only their explicitly authorized plan-owned SDD briefs/reports. Unrelated SDD/private state remains off limits. Never stage or upload SDD, `.superpowers/`, `.agents/`, `.codex/`, private material or generated study outputs. This neutral planner inspects no SDD directory.

## Scientific contract and ownership

The claim under examination is posterior/marginal predictive calibration under the already frozen simulated law, with sensitivity to ignored counts and lost parameter pairing. Acceptance accounts for 1,938 cases, 1,936 initial-fit slots and at most 1,936 convergence-only retry slots; twelve full-N512 correct-mode tests and four predeclared control assertions retain their existing threshold. The runner and pure reducer produce evidence for the research report and later unchanged B0 comparison. Missing diagnostics, owner loss, unsupported records, wrong identities or storage uncertainty cannot become successful calibration. Non-rejection permits only “no discrepancy detected at this design's resolution.”

Read `AGENTS.md`, `docs/overview.md`, `docs/scientific-engineering-objectives.md`, Atlas design §§5,7–8,12, and all seven 2026-09-10 B0H specifications (parent, SBC, generation, attempts, quantities, summaries, codec) before execution. Root's issue search already found existing open #211 and no duplicate runner. The timing note at result `8fb80bd` supports one-worker feasibility only. This draft was prepared against public codec source `b2f7700`; root must relay any final codec review corrections before adopting code blocks.

Owned files and responsibilities:

| File | Responsibility |
| --- | --- |
| `genomeos/validation/heterogeneity_runner_records.py` | Closed operational records, manifest and exact null envelope; no I/O/science calls |
| `genomeos/validation/heterogeneity_runner_wire.py` | Canonical operation bytes, receipt hashing and exact codec root checks; no I/O/science calls |
| `genomeos/validation/heterogeneity_runner_reader.py` | Concrete read-only SQL decoding, exact inventory and collected-snapshot consumption; no execution authority |
| `genomeos/validation/heterogeneity_runner_store.py` | One SQLite store, process exclusion, explicit publication transactions, immutable reads and loss records |
| `genomeos/validation/heterogeneity_runner.py` | Dataset-bound restoration and stage orchestration through existing public functions |
| `genomeos/validation/heterogeneity_runner_binding.py` | Pure receipt-chain validation and deterministic next-stage eligibility, shared by execution and reduction |
| `genomeos/validation/heterogeneity_reduction.py` | Pure complete-case accounting, rank decisions and descriptive rows |
| `genomeos/validation/heterogeneity_reduction_records.py` | Closed reduction records and exact binary64 output fields |
| `genomeos/validation/heterogeneity_runner_admission.py` | Actual runtime/source/storage observation at the offline composition boundary |
| `scripts/run_b0h_calibration.py` | Minimal admit/prepare/run/reduce/collect command composition |
| `tests/heterogeneity_runner_fixtures.py` | Clearly labeled constructor-valid synthetic fixtures; no RNG/NUTS |
| `tests/test_heterogeneity_runner_records.py` | Closed fields/null/manifest identity tests |
| `tests/test_heterogeneity_runner_store.py` | Transaction, exclusion, uncertainty, loss and corruption tests |
| `tests/test_heterogeneity_runner.py` | Counted public-call lifecycle and restored binding tests |
| `tests/test_heterogeneity_reduction.py` | Full-N gates, conditional accounting and pure deterministic reduction |
| `tests/test_heterogeneity_runner_cli.py` | Offline command composition and admission refusal tests |
| `docs/research/population-heterogeneity-runner-2026-09-10.md` | Literal engineering scope and refusal note; actual observed verification goes in root's PR report |

No existing production/scientific source needs modification. Schema freeze applies to operational runner versioning, not a change to P1/serving `contract/` schemas.

## Field and wire contracts to freeze before implementation

All operational records use exact closed field sets. `None` is serialized explicitly in nullable positions. No arbitrary extension maps, strings naming imported classes, dynamic scientific deserialization, permissive casts or default evidence fields. Booleans never satisfy integer fields. Digests are lowercase 64-character SHA256 strings. Operational JSON is ASCII, sorted keys, separators `,` and `:`, no whitespace/newline, duplicate keys refused, exact canonical re-encoding required. Literal Python exception messages are UTF-8 with surrogatepass encoded as lowercase hexadecimal, preserving arbitrary code points without normalization. No operational JSON float is admitted: descriptive binary64 values use exactly 16 hexadecimal IEEE-754 digits. The scientific codec remains the sole representation of its seven public roots.

`SbcCaseId` fields are always named `(track_id, study_id, case_id, replicate_id)`; enumeration order is separately `(study_id, case_id, replicate_id, track_id)`. The manifest contains the complete ordered tuple, not an accepted subset. Worker assignment is a single nonempty worker ID attached to all cases; multiple workers are rejected in v1.

| Record | Exact fields and domains |
| --- | --- |
| `SourceIdentity` | `revision` (40 lowercase hex), `content_sha256` (digest), `lock_sha256` (digest) |
| `RuntimeIdentity` | `python_version`, `platform`, `machine`, `environment_sha256`, `jax_version`, `cupy_version`, `jax_device`, `cupy_device`, `driver_version`, `jax_float64`, `cupy_float64`; nonempty strings, digest, and literal true for each measured precision flag |
| `StorageAdmission` | `database_parent`, `device_id`, `mount_type`, `mount_options`, `free_bytes`, `probe_sha256`, `exclusive_lock_observed`, `rollback_observed`, `commit_readback_observed`, `directory_fsync_observed`; actual absolute parent, exact integer device/free bytes, nonempty mount strings and digest, literal true measurement results |
| `AdmissionReceipt` | `format="b0h_admission"`, `version="1"`, `source`, `runtime`, `storage`, `observed_unix_ns`, `startup_elapsed_ns`, `preflight_elapsed_ns`, `device_total_bytes`, `device_free_bytes`, `process_peak_rss_bytes`, `memory_observation_label`; nonnegative exact integers and explicit label |
| `PreparedNull` | `format="b0h_rank_null"`, `version="1"`, `entropy=(42,211,1,100,0,0,0,0,0)`, `sample_size=512`, `replicates=100000`, `seed=1653499886`, `statistics` (exactly100000 non-Boolean integers in0..2048, original order); reconstructed through public `RankNullReference` |
| `CampaignManifest` | `format="b0h_campaign"`, `version="1"`, `protocol="b0h_sbc_v1"`, `runner_version="1"`, `codec_version="1"`, `cdf_backend="cupy"`, `source`, `runtime`, `admission_sha256`, `null_sha256`, `max_metadata_bytes`, `max_total_payload_bytes`, `worker_id`, `cases`; exact full enumeration, positive metadata/nonnegative payload budget |
| `StageKey` | `campaign_sha256`, `case`, `stage`, `attempt_id`; stage in generation/structural/fit/quantities/summary; attempt None for generation/structural, exact0/1 for the other three; structural only study3, quantities only study0, other fit-bearing stages exclude study3 |
| `StageStart` | `format="b0h_start"`, `version="1"`, `key`, `worker_id`, `owner_id`, `source`, `runtime`, `cdf_backend="cupy"`, `prerequisites` (ordered receipt-or-failure completion digests), `started_unix_ns`, `started_monotonic_ns`; owner is a nonempty actual process-incarnation label, no timeout/lease |
| `PayloadIdentity` | `sha256`, `length`; exact nonnegative byte length |
| `EvidenceReceipt` | `format="b0h_receipt"`, `version="1"`, `start_sha256`, `root_type` (one of seven exact public root names), `metadata_sha256`, `metadata_length`, `payloads` (sorted unique `PayloadIdentity` tuple) |
| `StageExecutionFailure` | `format="b0h_execution_failure"`, `version="1"`, `start_sha256`, `phase` (public_call, returned_evidence_validation, codec_encoding), `exception_class`, `message_utf8hex`; actual qualified class and literal message only |
| `StageCompletion` | `format="b0h_completion"`, `version="1"`, `start_sha256`, `receipt_sha256`, `failure_sha256`, `whole_call_elapsed_ns`, `process_peak_rss_bytes`, `resource_unavailable_reason`; exactly one receipt/failure, RSS or explicit nonempty unavailable reason, whole-call duration actually measured |
| `OwnerLoss` | `format="b0h_owner_loss"`, `version="1"`, `start_sha256`, `previous_owner_id`, `observing_owner_id`, `observed_unix_ns`, `evidence="prior_process_exclusion_released"`, `surviving_receipts=()`; released lock confirms exclusion loss, not call outcome; atomic store admits no receipt-only recovery |
| `StoredStage` | Frozen in-memory `start`, `completion`, `receipt`, `failure`, `loss`, `encoded`, `value`; each nullable field follows missing/START/loss/completed state rules; `value` is one actual decoded public root |
| `CollectedB0HSnapshot` | Frozen in-memory `manifest`, `null`, `cases`, `database_sha256`, `inventory_sha256`; original admitted provenance only, no execution authority |
| `CaseEvidence` | Frozen in-memory `campaign_sha256`, `case`, `stages` in generation, structural or fit0, fit1, quantities, summary order; retains explicit unstarted slots through case accounting |
| `CaseAccounting` | `case`, generation/structural/attempt0/attempt1/quantities/summary status strings from closed per-stage domains, `accepted_attempt`, `owner_loss_count`, `execution_failure_count`, `unstarted_required_stages`, `unresolved_reasons`; no failure erasure after accepted retry |
| `RankReduction` | `track_id`, `mode_id`, `quantity_id`, `counts` (five nonnegative integers), `actual_n`, `missing_n`, `failure_status_counts`, `test` (existing `RankTestResult` or None), `role` (correct_family/required_control/other_control), `decision` (reject/not_reject/uncomputable) |
| `DescriptiveRow` | `case`, `target_kind` (parameter_mean/parameter_rho/fresh_population/shared_cluster0/fresh_cluster), `metric` (estimate/truth/absolute_error/squared_error/log_score/randomized_pit/coverage_50/coverage_80/coverage_95/width_50/width_80/width_95), `value_bits` (binary64 bits), `dependence_label` (independent_dataset/shared_history_paired_tracks/boundary_degenerate_paired_tracks/paired_tracks) |
| `DescriptiveAggregate` | `study_id`, `case_id`, `track_id`, `target_kind`, `metric`, `planned_n`, `actual_n`, `failed_n`, `mean_bits` or None; only actual rows count in denominator, preserve negative-infinite log score |
| `StudyReduction` | `format="b0h_reduction"`, `version="1"`, `campaign_sha256`, `inventory_sha256`, `null_sha256`, `cases`, `planned_initial_fits=1936`, `planned_retry_slots=1936`, `completed_fit_calls`, `ambiguous_fit_calls`, `completed_generation_calls`, `completed_structural_calls`, `completed_quantity_calls`, `completed_summary_calls`, `ranks`, `rows`, `aggregates`, `correct_family_rejected`, `sensitivity_limited`, `unconditional_claim_eligible`, `claim_reasons`, `permitted_claim`; claim None unless eligible |

Completed calls and ambiguous START slots are separate counts. Internal graph/sampler entries are not inferred from wrapper calls or `expected_sampler_calls`; they require separately observed test instrumentation. `StageStart.prerequisites` binds completed evidence with exact completion digests, whose receipts bind exact root bytes. For summary after a quantities execution failure, the quantities completion still appears in ordering prerequisites; summary's scientific data prerequisite remains the accepted fit.

Storage/codec defects retain their adapter classification. The executor catches ordinary exceptions only around the public scientific call; encoding/constructor defects propagate and leave unresolved START evidence. The command records the actual defect without inventing a scientific result. Publication failures after encoding retain the exact known packet in PendingPublication.

### Exact public signatures and composition

```python
def runner_record_bytes(record: RunnerRecord) -> bytes: ...
def read_runner_record(data: bytes) -> RunnerRecord: ...
def record_digest(record: RunnerRecord) -> str: ...
def prepared_null(reference: RankNullReference) -> PreparedNull: ...
def restore_null(record: PreparedNull) -> RankNullReference: ...
def build_manifest(admission: AdmissionReceipt, null: PreparedNull, *,
                   worker_id: str, limits: B0HCodecLimits) -> CampaignManifest: ...
def evidence_receipt(start: StageStart, encoded: EncodedB0HEvidence, *,
                     limits: B0HCodecLimits) -> EvidenceReceipt: ...

class LocalB0HStore:
    def __init__(self, database: Path, *, manifest: CampaignManifest,
                 admission: AdmissionReceipt, null: PreparedNull,
                 owner_id: str) -> None: ...
    @classmethod
    def create(cls, database: Path, *, manifest: CampaignManifest, admission: AdmissionReceipt,
               null: PreparedNull, owner_id: str) -> LocalB0HStore: ...
    def __enter__(self) -> LocalB0HStore: ...
    def __exit__(self, exc_type: object, exc: object, tb: object) -> None: ...
    def stages(self, case: SbcCaseId) -> tuple[StoredStage, ...]: ...
    def start(self, record: StageStart) -> None: ...
    def complete(self, start: StageStart, completion: StageCompletion, *,
                 receipt: EvidenceReceipt | None,
                 encoded: EncodedB0HEvidence | None,
                 failure: StageExecutionFailure | None) -> None: ...
    def publish_pending(self, packet: PublicationPacket) -> None: ...
    def collect(self, destination: Path) -> tuple[str, str]: ...
    def record_owner_loss(self, start: StageStart) -> OwnerLoss: ...
    def inventory(self) -> tuple[tuple[str, tuple[str, ...]], ...]: ...

def load_b0h_case(manifest: CampaignManifest, case: SbcCaseId,
                  store: LocalB0HStore) -> CaseEvidence: ...
def execute_b0h_case(manifest: CampaignManifest, case: SbcCaseId,
                     store: LocalB0HStore) -> CaseEvidence: ...
def reduce_b0h_study(manifest: CampaignManifest,
                     cases: tuple[CaseEvidence, ...],
                     null_reference: RankNullReference) -> StudyReduction: ...
def read_collected_b0h_snapshot(directory: Path, *, expected_database_sha256: str,
                               expected_inventory_sha256: str) -> CollectedB0HSnapshot: ...
def observe_b0h_admission(source_root: Path, database_parent: Path) -> AdmissionReceipt: ...
def main(argv: Sequence[str] | None = None) -> int: ...
```

These declarations freeze the intended interface but are not implementation steps. Complete executable bodies and literal TDD steps follow below; these signature-only declarations are not replacement implementation stubs.

## Task 1: Closed campaign records and wire contract

**Files:** Create `genomeos/validation/heterogeneity_runner_records.py`, `genomeos/validation/heterogeneity_runner_wire.py`, and `tests/test_heterogeneity_runner_records.py`. The scientific objective is exact campaign and returned-evidence identity; acceptance is closed fields, exact bytes and malformed-null refusal. Consumers are the store, executor and reducer. No scientific computation belongs here.

**Interfaces:** Consume the public seven-root codec and generation identity constructors; produce the exact operational records and wire signatures above.

- [ ] Step 1: Add the following importable failing-test scaffold in `tests/test_heterogeneity_runner_records.py`. Import inside the test so RED is a test failure, not a collection error. Run the exact command below before creating the production module.

```python
"""Runner wire contract fixtures; no realized scientific evidence."""
from __future__ import annotations

import importlib

import pytest


def test_null_requires_complete_frozen_identity():
    records = importlib.import_module(
        "genomeos.validation.heterogeneity_runner_records"
    )
    from genomeos.validation.sbc_ranks import RankNullReference

    with pytest.raises(ValueError, match="512"):
        records.prepared_null(RankNullReference(511, 1653499886, (2,) * 100000))
    with pytest.raises(ValueError, match="100000"):
        records.prepared_null(RankNullReference(512, 1653499886, (2,)))
    with pytest.raises(ValueError, match="1653499886"):
        records.prepared_null(RankNullReference(512, 1, (2,) * 100000))
```

- [ ] Step 2: Run behavioral RED before the records module exists.

```bash
env PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib /private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python -m pytest tests/test_heterogeneity_runner_records.py::test_null_requires_complete_frozen_identity -o addopts='' -q
```

Expected: the named test fails on the absent module. Once production code exists, retain the three malformed-null assertions as substantive behavior checks.

- [ ] Step 3: Create `genomeos/validation/heterogeneity_runner_records.py` with this complete code. Pydantic is already installed; its role is a closed operational envelope, never scientific root dispatch. Every evidence field is required.

```python
"""Closed offline B0H runner records (design §§5,7–8,12; runner §§2–5)."""
from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from genomeos.validation.heterogeneity_codec import B0HCodecLimits
from genomeos.validation.heterogeneity_simulation import enumerate_sbc_cases
from genomeos.validation.heterogeneity_simulation_types import SbcCaseId
from genomeos.validation.sbc_ranks import RankNullReference

Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Text = Annotated[str, Field(min_length=1)]
Natural = Annotated[int, Field(ge=0)]
Positive = Annotated[int, Field(gt=0)]
StageName = Literal["generation", "structural", "fit", "quantities", "summary"]
RootName = Literal[
    "GeneratedDataset", "AllUnavailableDataset", "GenerationFailure",
    "FitAttemptResult", "StructuralCheckResult", "SelectedSbcQuantities",
    "HeterogeneityFitSummary",
]


class ClosedRecord(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid",
                              revalidate_instances="always")

    @model_validator(mode="before")
    @classmethod
    def literal_scalar_types(cls, value):
        if type(value) is dict:
            bool_fields = {"jax_float64", "cupy_float64", "exclusive_lock_observed",
                           "rollback_observed", "commit_readback_observed", "directory_fsync_observed"}
            int_fields = {"sample_size", "replicates", "seed", "attempt_id", "accepted_attempt",
                          "track_id", "study_id", "mode_id", "quantity_id",
                          "planned_initial_fits", "planned_retry_slots"}
            for name, item in value.items():
                if name in bool_fields and type(item) is not bool:
                    raise ValueError("Boolean observation must be literal bool")
                if name in int_fields and item is not None and type(item) is not int:
                    raise ValueError("integer identity must be literal int")
        return value


class SourceIdentity(ClosedRecord):
    revision: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
    content_sha256: Digest
    lock_sha256: Digest


class RuntimeIdentity(ClosedRecord):
    python_version: Text
    platform: Text
    machine: Text
    environment_sha256: Digest
    jax_version: Text
    cupy_version: Text
    jax_device: Text
    cupy_device: Text
    driver_version: Text
    jax_float64: Literal[True]
    cupy_float64: Literal[True]


class StorageAdmission(ClosedRecord):
    database_parent: Annotated[str, Field(pattern=r"^/")]
    device_id: Natural
    mount_type: Text
    mount_options: Text
    free_bytes: Natural
    probe_sha256: Digest
    exclusive_lock_observed: Literal[True]
    rollback_observed: Literal[True]
    commit_readback_observed: Literal[True]
    directory_fsync_observed: Literal[True]


class AdmissionReceipt(ClosedRecord):
    format: Literal["b0h_admission"]
    version: Literal["1"]
    source: SourceIdentity
    runtime: RuntimeIdentity
    storage: StorageAdmission
    observed_unix_ns: Natural
    startup_elapsed_ns: Natural
    preflight_elapsed_ns: Natural
    device_total_bytes: Positive
    device_free_bytes: Natural
    process_peak_rss_bytes: Positive
    memory_observation_label: Text

    @model_validator(mode="after")
    def memory_bounds(self) -> Self:
        if self.device_free_bytes > self.device_total_bytes:
            raise ValueError("free memory exceeds device memory")
        return self


class PreparedNull(ClosedRecord):
    format: Literal["b0h_rank_null"]
    version: Literal["1"]
    entropy: tuple[int, int, int, int, int, int, int, int, int]
    sample_size: Literal[512]
    replicates: Literal[100000]
    seed: Literal[1653499886]
    statistics: Annotated[
        tuple[Annotated[int, Field(ge=0, le=2048)], ...],
        Field(min_length=100000, max_length=100000),
    ]

    @model_validator(mode="after")
    def identity(self) -> Self:
        if self.entropy != (42, 211, 1, 100, 0, 0, 0, 0, 0):
            raise ValueError("wrong null entropy")
        return self


class CampaignManifest(ClosedRecord):
    format: Literal["b0h_campaign"]
    version: Literal["1"]
    protocol: Literal["b0h_sbc_v1"]
    runner_version: Literal["1"]
    codec_version: Literal["1"]
    cdf_backend: Literal["cupy"]
    source: SourceIdentity
    runtime: RuntimeIdentity
    admission_sha256: Digest
    null_sha256: Digest
    max_metadata_bytes: Positive
    max_total_payload_bytes: Natural
    worker_id: Text
    cases: tuple[SbcCaseId, ...]

    @model_validator(mode="after")
    def planned_cases(self) -> Self:
        if self.cases != enumerate_sbc_cases():
            raise ValueError("campaign requires exact ordered 1938 cases")
        return self

    @property
    def limits(self) -> B0HCodecLimits:
        return B0HCodecLimits(self.max_metadata_bytes, self.max_total_payload_bytes)


class StageKey(ClosedRecord):
    campaign_sha256: Digest
    case: SbcCaseId
    stage: StageName
    attempt_id: Literal[0, 1] | None

    @model_validator(mode="after")
    def allowed_stage(self) -> Self:
        if self.stage in ("generation", "structural"):
            if self.attempt_id is not None:
                raise ValueError("generation/structural has no fit attempt")
        elif type(self.attempt_id) is not int:
            raise ValueError("fit-bearing stage requires attempt0/1")
        if self.stage == "structural" and self.case.study_id != 3:
            raise ValueError("structural requires study3")
        if self.stage not in ("generation", "structural") and self.case.study_id == 3:
            raise ValueError("study3 has no fit-bearing stage")
        if self.stage == "quantities" and self.case.study_id != 0:
            raise ValueError("quantities requires study0")
        return self


class StageStart(ClosedRecord):
    format: Literal["b0h_start"]
    version: Literal["1"]
    key: StageKey
    worker_id: Text
    owner_id: Text
    source: SourceIdentity
    runtime: RuntimeIdentity
    cdf_backend: Literal["cupy"]
    prerequisites: tuple[Digest, ...]
    started_unix_ns: Natural
    started_monotonic_ns: Natural

    @model_validator(mode="after")
    def unique_dependencies(self) -> Self:
        if len(set(self.prerequisites)) != len(self.prerequisites):
            raise ValueError("duplicate prerequisite")
        return self


class PayloadIdentity(ClosedRecord):
    sha256: Digest
    length: Natural


class EvidenceReceipt(ClosedRecord):
    format: Literal["b0h_receipt"]
    version: Literal["1"]
    start_sha256: Digest
    root_type: RootName
    metadata_sha256: Digest
    metadata_length: Positive
    payloads: tuple[PayloadIdentity, ...]

    @model_validator(mode="after")
    def payload_order(self) -> Self:
        identities = tuple(p.sha256 for p in self.payloads)
        if identities != tuple(sorted(set(identities))):
            raise ValueError("payload identities must be sorted and unique")
        return self


class StageExecutionFailure(ClosedRecord):
    format: Literal["b0h_execution_failure"]
    version: Literal["1"]
    start_sha256: Digest
    phase: Literal["public_call", "returned_evidence_validation", "codec_encoding"]
    exception_class: Annotated[str, Field(pattern=r"^[^.]+(?:\.[^.]+)+$")]
    message_utf8hex: Annotated[str, Field(pattern=r"^(?:[0-9a-f]{2})*$")]

    @model_validator(mode="after")
    def message_encoding(self) -> Self:
        raw = bytes.fromhex(self.message_utf8hex)
        if raw.decode("utf-8", "surrogatepass").encode("utf-8", "surrogatepass") != raw:
            raise ValueError("noncanonical exception message")
        return self


class StageCompletion(ClosedRecord):
    format: Literal["b0h_completion"]
    version: Literal["1"]
    start_sha256: Digest
    receipt_sha256: Digest | None
    failure_sha256: Digest | None
    whole_call_elapsed_ns: Natural
    process_peak_rss_bytes: Positive | None
    resource_unavailable_reason: Text | None

    @model_validator(mode="after")
    def exclusive_fields(self) -> Self:
        if (self.receipt_sha256 is None) == (self.failure_sha256 is None):
            raise ValueError("completion requires exactly one receipt or failure")
        if (self.process_peak_rss_bytes is None) == (self.resource_unavailable_reason is None):
            raise ValueError("resource value requires observation or unavailable reason")
        return self


class OwnerLoss(ClosedRecord):
    format: Literal["b0h_owner_loss"]
    version: Literal["1"]
    start_sha256: Digest
    previous_owner_id: Text
    observing_owner_id: Text
    observed_unix_ns: Natural
    evidence: Literal["prior_process_exclusion_released"]
    surviving_receipts: tuple[()]

    @model_validator(mode="after")
    def distinct_owner(self) -> Self:
        if self.previous_owner_id == self.observing_owner_id:
            raise ValueError("live owner cannot declare its own process loss")
        return self


RunnerRecord = (
    AdmissionReceipt | PreparedNull | CampaignManifest | StageStart
    | EvidenceReceipt | StageExecutionFailure | StageCompletion | OwnerLoss
)


def prepared_null(reference: RankNullReference) -> PreparedNull:
    if type(reference) is not RankNullReference:
        raise ValueError("null requires RankNullReference")
    if reference.sample_size != 512:
        raise ValueError("null sample_size must be 512")
    if len(reference.statistics) != 100000:
        raise ValueError("null requires 100000 statistics")
    if reference.seed != 1653499886:
        raise ValueError("null seed must be 1653499886")
    return PreparedNull(
        format="b0h_rank_null", version="1", entropy=(42, 211, 1, 100, 0, 0, 0, 0, 0),
        sample_size=512, replicates=100000, seed=1653499886,
        statistics=reference.statistics,
    )


def restore_null(record: PreparedNull) -> RankNullReference:
    checked = PreparedNull.model_validate(record)
    return RankNullReference(checked.sample_size, checked.seed, checked.statistics)
```

- [ ] Step 4: Before implementing wire behavior, append the following tests and run them. The literal envelope expectation is independent of the encoder.

```python
def test_canonical_null_bytes_and_rejected_json():
    wire = importlib.import_module("genomeos.validation.heterogeneity_runner_wire")
    records = importlib.import_module("genomeos.validation.heterogeneity_runner_records")
    from genomeos.validation.sbc_ranks import RankNullReference

    null = records.prepared_null(RankNullReference(512, 1653499886, (2,) * 100000))
    expected = (
        b'{"entropy":[42,211,1,100,0,0,0,0,0],"format":"b0h_rank_null",'
        b'"replicates":100000,"sample_size":512,"seed":1653499886,"statistics":['
        + b",".join([b"2"] * 100000) + b'],"version":"1"}'
    )
    assert wire.runner_record_bytes(null) == expected
    assert wire.read_runner_record(expected) == null
    for invalid in (
        expected + b"\n",
        expected.replace(b'"version":"1"', b'"version":"2"'),
        expected.replace(b'"version":"1"', b'"version":"1","version":"1"'),
        expected.replace(b'"replicates":100000', b'"replicates":true'),
        expected.replace(b'"sample_size":512', b'"sample_size":512,"extra":0'),
    ):
        with pytest.raises(ValueError):
            wire.read_runner_record(invalid)


def test_operational_root_admission_precedes_caller_methods():
    wire = importlib.import_module("genomeos.validation.heterogeneity_runner_wire")
    records = importlib.import_module("genomeos.validation.heterogeneity_runner_records")
    from genomeos.validation.sbc_ranks import RankNullReference
    class Malicious:
        def model_dump(self, **kwargs):
            pytest.fail("unsupported caller method invoked")
    with pytest.raises(ValueError, match="unsupported operational root"):
        wire.runner_record_bytes(Malicious())
    class Subclass(records.PreparedNull):
        def model_dump(self, **kwargs):
            pytest.fail("subclass caller method invoked")
    null = records.prepared_null(RankNullReference(512, 1653499886, (2,) * 100000))
    subclass = Subclass(**null.model_dump())
    with pytest.raises(ValueError, match="unsupported operational root"):
        wire.runner_record_bytes(subclass)
    # Deliberately invalid operational objects are hostile-input fixtures,
    # never scientific records or claimed admission observations.
    for changes in ({"statistics": [2] * 100000}, {"sample_size": 512.0},
                    {"entropy": (True, 211, 1, 100, 0, 0, 0, 0, 0)}):
        invalid = null.model_copy(update=changes)
        with pytest.raises(ValueError):
            wire.runner_record_bytes(invalid)
```

```bash
env PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib /private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python -m pytest tests/test_heterogeneity_runner_records.py::test_canonical_null_bytes_and_rejected_json -o addopts='' -q
```

Expected: the test fails on the absent wire module, after the records test is green.

- [ ] Step 5: Create `genomeos/validation/heterogeneity_runner_wire.py` with this complete code.

```python
"""Canonical operational B0H bytes (design §§5,7–8,12; runner §§3,5)."""
from __future__ import annotations

import hashlib
import json
from typing import Annotated

from pydantic import Field, TypeAdapter

from genomeos.validation.heterogeneity_codec import (
    B0HCodecLimits, EncodedB0HEvidence, decode_b0h_evidence,
)
from genomeos.validation.heterogeneity_runner_records import (
    AdmissionReceipt, CampaignManifest, EvidenceReceipt, PayloadIdentity,
    PreparedNull, RunnerRecord, StageStart, StageCompletion, StageExecutionFailure, OwnerLoss,
)
from genomeos.validation.heterogeneity_simulation import enumerate_sbc_cases

MAX_OPERATION_BYTES = 8 * 1024 * 1024
_RECORDS = TypeAdapter(Annotated[RunnerRecord, Field(discriminator="format")])
_ROOT_TYPES = (AdmissionReceipt, PreparedNull, CampaignManifest, StageStart,
               EvidenceReceipt, StageExecutionFailure, StageCompletion, OwnerLoss)


def sha256(data: bytes) -> str:
    if type(data) is not bytes:
        raise ValueError("digest input must be exact bytes")
    return hashlib.sha256(data).hexdigest()


def _pairs(items: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _reject_number(value: str) -> None:
    raise ValueError("operational JSON admits no floating numeric literal")


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=True, allow_nan=False,
                      sort_keys=True, separators=(",", ":")).encode("ascii")


def runner_record_bytes(record: RunnerRecord) -> bytes:
    if type(record) not in _ROOT_TYPES:
        raise ValueError("unsupported operational root")
    # Revalidate raw Python fields before JSON can normalize tuple/scalar types.
    # Every closed model uses strict=True and revalidate_instances='always'.
    validated = _RECORDS.validate_python(record, strict=True)
    raw = _canonical(validated.model_dump(mode="json"))
    if len(raw) > MAX_OPERATION_BYTES:
        raise ValueError("operational record exceeds byte budget")
    checked = _RECORDS.validate_json(raw, strict=True)
    if type(checked) is not type(record) or _canonical(checked.model_dump(mode="json")) != raw:
        raise ValueError("operational constructor changed evidence")
    return raw


def read_runner_record(data: bytes) -> RunnerRecord:
    if type(data) is not bytes or len(data) > MAX_OPERATION_BYTES:
        raise ValueError("operational bytes type or budget")
    # Bound parser recursion before json.loads; strings are skipped exactly.
    depth, quoted, escaped = 0, False, False
    for byte in data:
        if quoted:
            if escaped:
                escaped = False
            elif byte == 92:
                escaped = True
            elif byte == 34:
                quoted = False
        elif byte == 34:
            quoted = True
        elif byte in (91, 123):
            depth += 1
            if depth > 32:
                raise ValueError("operational nesting exceeds 32")
        elif byte in (93, 125):
            depth -= 1
    document = json.loads(data.decode("ascii"), object_pairs_hook=_pairs,
                          parse_float=_reject_number, parse_constant=_reject_number)
    if _canonical(document) != data:
        raise ValueError("noncanonical operational JSON")
    checked = _RECORDS.validate_json(data, strict=True)
    if runner_record_bytes(checked) != data:
        raise ValueError("operational normalization changed bytes")
    return checked


def record_digest(record: RunnerRecord) -> str:
    return sha256(runner_record_bytes(record))


def build_manifest(admission: AdmissionReceipt, null: PreparedNull, *,
                   worker_id: str, limits: B0HCodecLimits) -> CampaignManifest:
    admission = read_runner_record(runner_record_bytes(admission))
    null = read_runner_record(runner_record_bytes(null))
    if type(admission) is not AdmissionReceipt or type(null) is not PreparedNull:
        raise ValueError("manifest requires admission and prepared null")
    return CampaignManifest(
        format="b0h_campaign", version="1", protocol="b0h_sbc_v1",
        runner_version="1", codec_version="1", cdf_backend="cupy",
        source=admission.source, runtime=admission.runtime,
        admission_sha256=record_digest(admission), null_sha256=record_digest(null),
        max_metadata_bytes=limits.max_metadata_bytes,
        max_total_payload_bytes=limits.max_total_payload_bytes,
        worker_id=worker_id, cases=enumerate_sbc_cases(),
    )


def evidence_receipt(start: StageStart, encoded: EncodedB0HEvidence, *,
                     limits: B0HCodecLimits) -> EvidenceReceipt:
    value = decode_b0h_evidence(encoded, limits=limits)
    return EvidenceReceipt(
        format="b0h_receipt", version="1", start_sha256=record_digest(start),
        root_type=type(value).__name__, metadata_sha256=sha256(encoded.metadata),
        metadata_length=len(encoded.metadata),
        payloads=tuple(PayloadIdentity(sha256=digest, length=len(raw))
                       for digest, raw in encoded.payloads),
    )
```


- [ ] Verification gate: run the task's focused GREEN, mandatory smoke and static/privacy checks. Record the actual command, exit status and counts in the authorized task report. A failed fixture or adapter check is not permission to alter scientific policy.

```bash
env PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib /private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python -m pytest tests/test_heterogeneity_runner_records.py -o addopts='' -q
env PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib /private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python scripts/smoke.py
/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/ruff check .
env PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib /private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python scripts/freeze_contract.py --check
env PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib /private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python scripts/check_module_size.py
git diff --check
git add genomeos/validation/heterogeneity_runner_records.py genomeos/validation/heterogeneity_runner_wire.py tests/test_heterogeneity_runner_records.py
git diff --cached --name-only
env PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib /private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python scripts/check_private_files.py
```

- [ ] Inspect the staged-path output. It must contain only this task's explicitly owned files above and no SDD/private/generated evidence. Preserve unrelated work. If every check passed and the staged scope is exact, make the task commit; advance #211/#189 without closing either.

```bash
git commit -m "feat: add closed B0H campaign records and wire contract" -m "Advances #211 and #189; neither calibration nor benchmark completion is claimed."
```

## Task 2: Transactional store and single-process ownership

**Files:** Create `genomeos/validation/heterogeneity_runner_store.py`, `genomeos/validation/heterogeneity_runner_reader.py`, `tests/heterogeneity_runner_fixtures.py`, `tests/test_heterogeneity_runner_store.py`; add the shown in-memory packet/stage records to `heterogeneity_runner_records.py`. Scientific claim: immutable invocation evidence survives acknowledged publication and cannot authorize repeated science after ambiguous loss. Acceptance covers exact transactions, ownership, corruption and retained known-live bytes. Consume Task1 closed records/codec envelopes; produce `LocalB0HStore`, `PublicationPacket`, `StoredStage`, `CaseEvidence` and `PendingPublication`. The executor is the consumer; this task has no science calls.

### Transaction-store implementation contract

The following schema is fixed. Every foreign-key target must exist in the same
transaction or earlier. `objects` contains closed operational record bytes;
scientific metadata has a separate BLOB table and ordered payload references.
Read paths verify that the exact referenced set equals all retained rows; orphan
receipts, completions, metadata and payloads refuse rather than becoming repair
work. An empty database is created exclusively only after its matching admission
and null have been validated. It is not an absent-campaign fallback for a missing
database during run/reduce.

```sql
CREATE TABLE objects (
    digest TEXT PRIMARY KEY NOT NULL,
    kind TEXT NOT NULL,
    body BLOB NOT NULL CHECK(typeof(body) = 'blob')
);
CREATE TABLE campaign (
    singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
    manifest TEXT NOT NULL REFERENCES objects(digest),
    admission TEXT NOT NULL REFERENCES objects(digest),
    null_reference TEXT NOT NULL REFERENCES objects(digest)
);
CREATE TABLE starts (
    case_id TEXT NOT NULL,
    stage TEXT NOT NULL,
    attempt INTEGER NOT NULL CHECK(attempt IN (-1, 0, 1)),
    digest TEXT UNIQUE NOT NULL REFERENCES objects(digest),
    PRIMARY KEY(case_id, stage, attempt)
);
CREATE TABLE completions (
    start_digest TEXT PRIMARY KEY REFERENCES starts(digest),
    digest TEXT UNIQUE NOT NULL REFERENCES objects(digest),
    receipt TEXT UNIQUE REFERENCES objects(digest),
    failure TEXT UNIQUE REFERENCES objects(digest),
    CHECK((receipt IS NULL) != (failure IS NULL))
);
CREATE TABLE metadata (
    receipt TEXT PRIMARY KEY REFERENCES objects(digest),
    body BLOB NOT NULL CHECK(typeof(body) = 'blob')
);
CREATE TABLE payloads (
    digest TEXT PRIMARY KEY NOT NULL,
    body BLOB NOT NULL CHECK(typeof(body) = 'blob')
);
CREATE TABLE payload_links (
    receipt TEXT NOT NULL REFERENCES metadata(receipt),
    ordinal INTEGER NOT NULL CHECK(ordinal >= 0),
    payload TEXT NOT NULL REFERENCES payloads(digest),
    PRIMARY KEY(receipt, ordinal),
    UNIQUE(receipt, payload)
);
CREATE TABLE losses (
    start_digest TEXT PRIMARY KEY REFERENCES starts(digest),
    digest TEXT UNIQUE NOT NULL REFERENCES objects(digest)
);
```

The SQL sentinel `-1` means only “not a fit-bearing stage”; wire `attempt_id`
remains null. Never expose `-1` as a scientific attempt or create `FitAttemptSpec`
for generation/structural cases. Before every new START, read all existing stage
records under the process lock and perform the complete case-bound validation.
The lock file is stable at `database.name + '.lock'`, opened with `O_CREAT` and
mode0600, never unlinked during campaign lifetime. Its inode remains stable;
use nonblocking `flock(LOCK_EX | LOCK_NB)` and retain the descriptor until store
close. A new process-incarnation owner ID is generated once at command start,
not once per case. Reject a symlink database or lock path and verify the opened
lock's inode matches its path.

Use `sqlite3.connect(..., isolation_level=None)` and explicit `BEGIN IMMEDIATE`,
`COMMIT`, `ROLLBACK`. Confirm `PRAGMA journal_mode` returns delete,
`PRAGMA synchronous` returns3, and `PRAGMA foreign_keys` returns1; do not assume
that issuing the setters worked. No transaction spans a scientific function.
Each insert first reads its unique key: identical fully validated bytes are
reuse; differing bytes are conflict. Do not use `INSERT OR IGNORE`, UPSERT,
UPDATE, DELETE or REPLACE. Existing database schemas must exactly match the
closed declared schema and supported version; unrecognized tables/triggers
are refusals. SQLite's internal tables are not evidence records.

After a commit exception, inspect `connection.in_transaction`, roll back an
uncommitted transaction when possible, then verify the exact expected committed
state using the database. Only exact START readback admits a public call.
Only exact result/receipt/completion readback admits the next stage. Proven
absence after a live result permits retrying the same retained publication bytes.
Unknown readback remains an adapter refusal with live evidence retained; a
SQLite exception is never proof of absence. No additional scientific invocation
is allowed on this path.

Root resolved pending live publication during drafting: retain one exact immutable
packet in a `PendingPublication` exception. The CLI retries publication-only
reconciliation every60seconds for at most1800seconds monotonic elapsed. Science
and next-case work pause throughout. Retry only SQLite I/O/locking failures after
transaction inspection; integrity, mismatch and programming errors do not retry.
Expiry/interruption reports unresolved publication, exits nonzero and leaves the
START ineligible for redelivery or retry1. This preserves bytes in memory for a
bounded interval, not durably through process death. API callers may keep the
exception and store alive. No recovery file, extra stage delivery or queue.

- [ ] Step 1: Add these in-memory record declarations at the end of the records module before executor/store consumers are introduced. Add the shown imports to that module's import block.

```python
from dataclasses import dataclass
from genomeos.validation.heterogeneity_codec import B0HEvidence, EncodedB0HEvidence


@dataclass(frozen=True)
class PublicationPacket:
    start: StageStart
    completion: StageCompletion
    receipt: EvidenceReceipt | None
    encoded: EncodedB0HEvidence | None
    failure: StageExecutionFailure | None

    def __post_init__(self) -> None:
        from genomeos.validation.heterogeneity_runner_wire import record_digest
        if type(self.start) is not StageStart or type(self.completion) is not StageCompletion:
            raise ValueError("publication requires exact START and COMPLETE roots")
        digest = record_digest(self.start)
        record_digest(self.completion)
        if self.completion.start_sha256 != digest:
            raise ValueError("publication completion START mismatch")
        if self.receipt is not None:
            if (type(self.receipt) is not EvidenceReceipt or type(self.encoded) is not EncodedB0HEvidence
                    or self.failure is not None or self.receipt.start_sha256 != digest
                    or self.completion.receipt_sha256 != record_digest(self.receipt)
                    or self.completion.failure_sha256 is not None):
                raise ValueError("publication scientific fields mismatch")
        elif (type(self.failure) is not StageExecutionFailure or self.encoded is not None
              or self.failure.start_sha256 != digest
              or self.completion.failure_sha256 != record_digest(self.failure)
              or self.completion.receipt_sha256 is not None):
            raise ValueError("publication failure fields mismatch")


@dataclass(frozen=True)
class StoredStage:
    start: StageStart
    completion: StageCompletion | None
    receipt: EvidenceReceipt | None
    failure: StageExecutionFailure | None
    loss: OwnerLoss | None
    encoded: EncodedB0HEvidence | None
    value: B0HEvidence | None


@dataclass(frozen=True)
class CaseEvidence:
    campaign_sha256: str
    case: SbcCaseId
    stages: tuple[StoredStage, ...]
```

- [ ] Step 2: Create the literal fixture module with the following complete contents. This construction produces synthetic tests, never actual run evidence. It deliberately uses existing public constructors and deterministic identity expansion without a generator, predictor, rank RNG or NUTS call.

```python
"""Constructor-valid runner fixtures; no realized science or admission claim."""
from __future__ import annotations

from dataclasses import replace

import numpy as np

from heterogeneity_codec_fixtures import dataset, fitted, selected, summary
from genomeos.validation.heterogeneity_attempts import (
    AttemptError, FitAttemptResult, plan_fit_attempt,
)
from genomeos.validation.heterogeneity_codec import B0HCodecLimits
from genomeos.validation.heterogeneity_runner_records import (
    AdmissionReceipt, RuntimeIdentity, SourceIdentity, StorageAdmission, prepared_null,
)
from genomeos.validation.heterogeneity_runner_wire import build_manifest
from genomeos.validation.sbc_ranks import RankNullReference


def campaign(parent):
    source = SourceIdentity(revision="a" * 40, content_sha256="b" * 64,
                            lock_sha256="c" * 64)
    runtime = RuntimeIdentity(
        python_version="fixture3.12", platform="fixture-linux", machine="fixture-x86_64",
        environment_sha256="d" * 64, jax_version="fixture", cupy_version="fixture",
        jax_device="fixture-gpu0", cupy_device="fixture-gpu0", driver_version="fixture",
        jax_float64=True, cupy_float64=True,
    )
    storage = StorageAdmission(
        database_parent=str(parent.resolve()), device_id=parent.stat().st_dev,
        mount_type="fixture-local", mount_options="fixture-rw", free_bytes=10**9,
        probe_sha256="e" * 64, exclusive_lock_observed=True, rollback_observed=True,
        commit_readback_observed=True, directory_fsync_observed=True,
    )
    admission = AdmissionReceipt(
        format="b0h_admission", version="1", source=source, runtime=runtime,
        storage=storage, observed_unix_ns=1, startup_elapsed_ns=1, preflight_elapsed_ns=1,
        device_total_bytes=10**9, device_free_bytes=10**8, process_peak_rss_bytes=10**6,
        memory_observation_label="synthetic_fixture_not_measured",
    )
    null = prepared_null(RankNullReference(512, 1653499886, (100,) * 99999 + (2048,)))
    manifest = build_manifest(admission, null, worker_id="worker0",
                              limits=B0HCodecLimits(2**20, 2**24))
    return manifest, admission, null


def accepted(data, attempt_id=0):
    spec = plan_fit_attempt(data, attempt_id=attempt_id)
    fit = fitted(data, spec)
    # Selected fixture has these literal correct posterior points at four indices.
    if data.case_id.study_id == 0:
        mean = np.array(fit.mean_draws, copy=True)
        rho = np.array(fit.rho_draws, copy=True)
        for (chain, draw), (m, r) in zip(
            ((0, 0), (1, 3), (2, 6), (3, 9)),
            ((.125, .25), (.25, .375), (.375, .5), (.5, .625)), strict=True,
        ):
            mean[chain, draw, 0], rho[chain, draw, 0] = m, r
        fit = replace(fit, mean_draws=mean, rho_draws=rho)
    if data.case_id.study_id == 4 and data.case_id.case_id == 1:
        counts = fit.training_counts[0]
        fit = replace(fit, training_counts=(replace(counts, training_ac=counts.training_an),))
    return FitAttemptResult(spec, "accepted", fit, None, (), None)


def failed(data, status="convergence_failed"):
    error = AttemptError(
        "convergence" if status == "convergence_failed" else "runtime",
        "builtins.RuntimeError", "literal synthetic failure",
        "fixture_convergence" if status == "convergence_failed" else None,
        () if status == "convergence_failed" else None,
        1 if status == "convergence_failed" else None,
    )
    return FitAttemptResult(plan_fit_attempt(data, attempt_id=0), status, None, error, (), None)


def quantities(data, attempt):
    return selected(attempt=attempt.spec.attempt_id, track=data.case_id.track_id)


def fit_summary(data, attempt, cdf_backend):
    return summary(data.case_id.study_id, data.case_id.case_id, data.case_id.track_id,
                   attempt.spec.attempt_id, cdf_backend)


__all__ = ["accepted", "campaign", "dataset", "failed", "fit_summary", "quantities"]
```

- [ ] Step 3: Add `tests/test_heterogeneity_runner_store.py` before the store module, then run its first test as RED.

```python
"""SQLite publication fixtures; no filesystem durability or science claim."""
from __future__ import annotations

import importlib
from dataclasses import replace

import pytest

from heterogeneity_runner_fixtures import campaign, dataset
from genomeos.validation.heterogeneity_codec import encode_b0h_evidence
from genomeos.validation.heterogeneity_runner_records import StageCompletion, StageKey, StageStart
from genomeos.validation.heterogeneity_runner_wire import evidence_receipt, record_digest


def start_record(manifest, data, owner="fixture-owner"):
    return StageStart(
        format="b0h_start", version="1",
        key=StageKey(campaign_sha256=record_digest(manifest), case=data.case_id,
                     stage="generation", attempt_id=None),
        worker_id=manifest.worker_id, owner_id=owner, source=manifest.source,
        runtime=manifest.runtime, cdf_backend="cupy", prerequisites=(),
        started_unix_ns=2, started_monotonic_ns=3,
    )


def packet(manifest, start, data):
    from genomeos.validation.heterogeneity_runner_records import PublicationPacket

    encoded = encode_b0h_evidence(data, limits=manifest.limits)
    receipt = evidence_receipt(start, encoded, limits=manifest.limits)
    completion = StageCompletion(
        format="b0h_completion", version="1", start_sha256=record_digest(start),
        receipt_sha256=record_digest(receipt), failure_sha256=None,
        whole_call_elapsed_ns=7, process_peak_rss_bytes=None,
        resource_unavailable_reason="fixture_not_measured",
    )
    return PublicationPacket(start, completion, receipt, encoded, None)


def publish(store, retained):
    store.complete(retained.start, retained.completion, receipt=retained.receipt,
                   encoded=retained.encoded, failure=retained.failure)


def test_atomic_completion_reuse_and_exclusion(tmp_path):
    storage = importlib.import_module("genomeos.validation.heterogeneity_runner_store")
    manifest, admission, null = campaign(tmp_path)
    data = dataset()
    start = start_record(manifest, data)
    retained = packet(manifest, start, data)
    path = tmp_path / "study.sqlite3"
    with storage.LocalB0HStore.create(path, manifest=manifest, admission=admission,
                               null=null, owner_id="fixture-owner") as store:
        store.start(start)
        publish(store, retained)
        before = store.inventory()
        publish(store, retained)
        assert store.inventory() == before
        stage, = store.stages(data.case_id)
        assert stage.encoded == retained.encoded
        assert stage.receipt == retained.receipt
        assert stage.completion.whole_call_elapsed_ns == 7
        with pytest.raises(storage.StoreIntegrityError):
            publish(store, replace(retained, completion=retained.completion.model_copy(
                update={"whole_call_elapsed_ns": 8})))
        with pytest.raises(storage.StoreUnavailable):
            with storage.LocalB0HStore(path, manifest=manifest, admission=admission,
                                       null=null, owner_id="other-owner"):
                pytest.fail("second owner acquired the lock")


def test_start_only_owner_loss_is_not_absence(tmp_path):
    storage = importlib.import_module("genomeos.validation.heterogeneity_runner_store")
    manifest, admission, null = campaign(tmp_path)
    data = dataset()
    start = start_record(manifest, data)
    path = tmp_path / "study.sqlite3"
    with storage.LocalB0HStore.create(path, manifest=manifest, admission=admission,
                               null=null, owner_id="fixture-owner") as store:
        store.start(start)
    with storage.LocalB0HStore(path, manifest=manifest, admission=admission,
                               null=null, owner_id="new-owner") as store:
        loss = store.record_owner_loss(start)
        assert loss.previous_owner_id == "fixture-owner"
        stage, = store.stages(data.case_id)
        assert stage.completion is None
        assert stage.loss == loss
        with pytest.raises(storage.StoreIntegrityError):
            store.start(start.model_copy(update={"owner_id": "new-owner"}))
@pytest.mark.parametrize("existing", [False, True])
def test_open_never_creates_missing_or_initializes_empty(tmp_path, existing):
    import sqlite3
    from genomeos.validation.heterogeneity_runner_store import LocalB0HStore, StoreIntegrityError
    manifest, admission, null = campaign(tmp_path)
    path = tmp_path / "study.sqlite3"
    if existing:
        path.write_bytes(b"")
    with pytest.raises(StoreIntegrityError):
        with LocalB0HStore(path, manifest=manifest, admission=admission,
                           null=null, owner_id="fixture-owner"):
            pytest.fail("open admitted a missing/empty campaign")
    assert path.exists() is existing
    if existing:
        with sqlite3.connect(path) as check:
            assert check.execute("SELECT name FROM sqlite_master").fetchall() == []


def test_create_refuses_existing_file_and_symlink(tmp_path):
    from genomeos.validation.heterogeneity_runner_store import LocalB0HStore, StoreIntegrityError
    manifest, admission, null = campaign(tmp_path)
    path = tmp_path / "study.sqlite3"
    path.write_bytes(b"")
    with pytest.raises(FileExistsError):
        with LocalB0HStore.create(path, manifest=manifest, admission=admission,
                                  null=null, owner_id="fixture-owner"):
            pytest.fail("exclusive create replaced an existing file")
    path.unlink()
    target = tmp_path / "unrelated.sqlite3"
    target.write_bytes(b"literal unrelated bytes")
    path.symlink_to(target)
    with pytest.raises(StoreIntegrityError, match="symlink"):
        with LocalB0HStore.create(path, manifest=manifest, admission=admission,
                                  null=null, owner_id="fixture-owner"):
            pytest.fail("symlink campaign admitted")
    assert target.read_bytes() == b"literal unrelated bytes"


def test_uninspectable_commit_keeps_same_live_packet(tmp_path, monkeypatch):
    import sqlite3
    from genomeos.validation.heterogeneity_runner_store import LocalB0HStore, PendingPublication
    manifest, admission, null = campaign(tmp_path)
    data = dataset()
    start = start_record(manifest, data)
    retained = packet(manifest, start, data)
    with LocalB0HStore.create(tmp_path / "study.sqlite3", manifest=manifest,
                              admission=admission, null=null, owner_id="fixture-owner") as store:
        store.start(start)
        original_commit = store._commit
        connection = store._db
        fail_inspection = [False]
        def io_failure():
            error = sqlite3.OperationalError("literal unavailable fixture")
            error.sqlite_errorcode = sqlite3.SQLITE_IOERR
            return error
        class Uninspectable:
            @property
            def in_transaction(self):
                return connection.in_transaction
            def execute(self, sql, parameters=()):
                if fail_inspection[0] and sql.startswith("SELECT"):
                    raise io_failure()
                return connection.execute(sql, parameters)
        def failed_commit():
            fail_inspection[0] = True
            raise io_failure()
        monkeypatch.setattr(store, "_db", Uninspectable())
        monkeypatch.setattr(store, "_commit", failed_commit)
        with pytest.raises(PendingPublication) as pending:
            publish(store, retained)
        assert pending.value.packet == retained
        assert pending.value.packet.completion.whole_call_elapsed_ns == 7
        monkeypatch.setattr(store, "_db", connection)
        monkeypatch.setattr(store, "_commit", original_commit)
        store.publish_pending(pending.value.packet)
        stage, = store.stages(data.case_id)
        assert stage.completion == retained.completion
        assert stage.encoded == retained.encoded


def test_inventory_performs_one_global_audit(tmp_path, monkeypatch):
    from genomeos.validation.heterogeneity_runner_store import LocalB0HStore
    manifest, admission, null = campaign(tmp_path)
    with LocalB0HStore.create(tmp_path / "study.sqlite3", manifest=manifest, admission=admission,
                              null=null, owner_id="fixture-owner") as store:
        calls = []
        original = store._reader.audit
        def audited():
            calls.append("whole-store")
            original()
        monkeypatch.setattr(store._reader, "audit", audited)
        assert len(store.inventory()) == 1938
        assert calls == ["whole-store"]


```

```bash
env PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib /private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python -m pytest tests/test_heterogeneity_runner_store.py::test_atomic_completion_reuse_and_exclusion -o addopts='' -q
```

Expected: named test failure at absent store module, not collection failure. Fix
any fixture construction error before proceeding; a fixture error is not the
store's behavioral RED.

Append the following to `tests/test_heterogeneity_runner_store.py` during Task2,
before implementing the store. SQL mutation below is solely deliberate corruption
of fresh `tmp_path` test databases; production writes remain INSERT-only.

```python
def test_commit_ack_loss_and_live_publication_retry(tmp_path, monkeypatch):
    import sqlite3
    storage = importlib.import_module("genomeos.validation.heterogeneity_runner_store")
    manifest, admission, null = campaign(tmp_path)
    data = dataset()
    start = start_record(manifest, data)
    retained = packet(manifest, start, data)
    with storage.LocalB0HStore.create(tmp_path / "study.sqlite3", manifest=manifest, admission=admission,
                               null=null, owner_id="fixture-owner") as store:
        commit = store._commit
        def ack_lost():
            commit()
            error = sqlite3.OperationalError("literal acknowledgement loss")
            error.sqlite_errorcode = sqlite3.SQLITE_IOERR
            raise error
        monkeypatch.setattr(store, "_commit", ack_lost)
        store.start(start)
        assert store.stages(data.case_id)[0].completion is None
        def before_commit():
            error = sqlite3.OperationalError("literal precommit I/O failure")
            error.sqlite_errorcode = sqlite3.SQLITE_IOERR
            raise error
        monkeypatch.setattr(store, "_commit", before_commit)
        with pytest.raises(storage.PendingPublication) as pending:
            publish(store, retained)
        assert pending.value.packet == retained
        assert store.stages(data.case_id)[0].completion is None
        monkeypatch.setattr(store, "_commit", ack_lost)
        store.publish_pending(pending.value.packet)
        assert store.stages(data.case_id)[0].encoded == retained.encoded
        monkeypatch.setattr(store, "_commit", commit)
        assert store.stages(data.case_id)[0].completion.whole_call_elapsed_ns == 7


def test_receipt_without_complete_is_refused(tmp_path):
    storage = importlib.import_module("genomeos.validation.heterogeneity_runner_store")
    manifest, admission, null = campaign(tmp_path)
    data = dataset()
    start = start_record(manifest, data)
    retained = packet(manifest, start, data)
    with storage.LocalB0HStore.create(tmp_path / "study.sqlite3", manifest=manifest, admission=admission,
                               null=null, owner_id="fixture-owner") as store:
        store.start(start)
        store._put_object(retained.receipt)
        with pytest.raises(storage.StoreIntegrityError, match="orphan"):
            store.inventory()


@pytest.mark.parametrize("mutation", ("flip", "remove", "metadata"))
def test_corrupt_exact_evidence_is_never_absence(tmp_path, mutation):
    from heterogeneity_runner_fixtures import accepted
    from genomeos.validation.heterogeneity_runner_records import StageKey
    storage = importlib.import_module("genomeos.validation.heterogeneity_runner_store")
    manifest, admission, null = campaign(tmp_path)
    data = dataset()
    generation = start_record(manifest, data)
    path = tmp_path / "study.sqlite3"
    with storage.LocalB0HStore.create(path, manifest=manifest, admission=admission,
                               null=null, owner_id="fixture-owner") as store:
        store.start(generation)
        generation_packet = packet(manifest, generation, data)
        publish(store, generation_packet)
        fit_start = generation.model_copy(update={
            "key": StageKey(campaign_sha256=record_digest(manifest), case=data.case_id,
                             stage="fit", attempt_id=0),
            "prerequisites": (record_digest(generation_packet.completion),),
        })
        store.start(fit_start)
        fit_packet = packet(manifest, fit_start, accepted(data))
        publish(store, fit_packet)
        digest, raw = fit_packet.encoded.payloads[0]
        if mutation == "flip":
            altered = bytes([raw[0] ^ 1]) + raw[1:]
            store._db.execute("UPDATE payloads SET body=? WHERE digest=?", (altered, digest))
        elif mutation == "remove":
            store._db.execute("PRAGMA foreign_keys=OFF")
            store._db.execute("DELETE FROM payloads WHERE digest=?", (digest,))
            store._db.execute("PRAGMA foreign_keys=ON")
        else:
            # Equal-length scientific metadata change; receipt is independently unchanged.
            altered = fit_packet.encoded.metadata.replace(
                b"3ff028f5c28f5c29", b"3ff051eb851eb852", 1)
            assert altered != fit_packet.encoded.metadata
            store._db.execute("UPDATE metadata SET body=? WHERE receipt=?",
                              (altered, record_digest(fit_packet.receipt)))
        with pytest.raises(ValueError):
            store.stages(data.case_id)
```


- [ ] Step 4: Create `genomeos/validation/heterogeneity_runner_reader.py` with this complete read-only decoding component. It accepts an already-open concrete SQLite connection; it cannot open/create a database, acquire execution ownership, or mutate evidence. The execution store and later collected-snapshot reader share only these exact reads.

```python
"""Concrete read-only SQLite decoding (design §§5,7–8,12; runner §§4–5)."""
from __future__ import annotations

import sqlite3

from genomeos.validation.heterogeneity_codec import EncodedB0HEvidence, decode_b0h_evidence
from genomeos.validation.heterogeneity_runner_records import (
    AdmissionReceipt, CampaignManifest, EvidenceReceipt, OwnerLoss, PreparedNull,
    StageCompletion, StageExecutionFailure, StageStart, StoredStage,
)
from genomeos.validation.heterogeneity_runner_wire import (
    evidence_receipt, read_runner_record, record_digest, sha256,
)
from genomeos.validation.heterogeneity_simulation_types import SbcCaseId

B0H_SQL_SCHEMA = (
    "CREATE TABLE objects(digest TEXT PRIMARY KEY NOT NULL,kind TEXT NOT NULL,"
    "body BLOB NOT NULL CHECK(typeof(body)='blob'))",
    "CREATE TABLE campaign(singleton INTEGER PRIMARY KEY CHECK(singleton=1),"
    "manifest TEXT NOT NULL REFERENCES objects(digest),"
    "admission TEXT NOT NULL REFERENCES objects(digest),"
    "null_reference TEXT NOT NULL REFERENCES objects(digest))",
    "CREATE TABLE starts(case_id TEXT NOT NULL,stage TEXT NOT NULL,"
    "attempt INTEGER NOT NULL CHECK(attempt IN(-1,0,1)),"
    "digest TEXT UNIQUE NOT NULL REFERENCES objects(digest),"
    "PRIMARY KEY(case_id,stage,attempt))",
    "CREATE TABLE completions(start_digest TEXT PRIMARY KEY REFERENCES starts(digest),"
    "digest TEXT UNIQUE NOT NULL REFERENCES objects(digest),"
    "receipt TEXT UNIQUE REFERENCES objects(digest),failure TEXT UNIQUE REFERENCES objects(digest),"
    "CHECK((receipt IS NULL)!=(failure IS NULL)))",
    "CREATE TABLE metadata(receipt TEXT PRIMARY KEY REFERENCES objects(digest),"
    "body BLOB NOT NULL CHECK(typeof(body)='blob'))",
    "CREATE TABLE payloads(digest TEXT PRIMARY KEY NOT NULL,"
    "body BLOB NOT NULL CHECK(typeof(body)='blob'))",
    "CREATE TABLE payload_links(receipt TEXT NOT NULL REFERENCES metadata(receipt),"
    "ordinal INTEGER NOT NULL CHECK(ordinal>=0),payload TEXT NOT NULL REFERENCES payloads(digest),"
    "PRIMARY KEY(receipt,ordinal),UNIQUE(receipt,payload))",
    "CREATE TABLE losses(start_digest TEXT PRIMARY KEY REFERENCES starts(digest),"
    "digest TEXT UNIQUE NOT NULL REFERENCES objects(digest))",
)
B0H_SQL_TABLES = ("campaign", "completions", "losses", "metadata", "objects", "payload_links",
           "payloads", "starts")


class StoreIntegrityError(ValueError):
    """Unsupported, corrupt or conflicting evidence; never retry automatically."""


class B0HSqlReader:
    """Borrow one connection; expose only exact record reads and whole-store audit."""

    def __init__(self, connection: sqlite3.Connection, *, manifest: CampaignManifest,
                 admission: AdmissionReceipt, null: PreparedNull) -> None:
        self._db = connection
        self.manifest, self.admission, self.null = manifest, admission, null
        self.campaign_sha256 = record_digest(manifest)

    def record(self, digest, cls):
        row = self._db.execute("SELECT kind,body FROM objects WHERE digest=?", (digest,)).fetchone()
        if row is None or type(row[1]) is not bytes or sha256(row[1]) != digest:
            raise StoreIntegrityError("missing or corrupt operational record")
        value = read_runner_record(row[1])
        if type(value) is not cls or row[0] != value.format:
            raise StoreIntegrityError("wrong operational record type")
        return value


    def stage(self, digest: str) -> StoredStage:
        start = self.record(digest, StageStart)
        completed = self._db.execute("SELECT digest,receipt,failure FROM completions WHERE start_digest=?",
                                     (digest,)).fetchone()
        lost = self._db.execute("SELECT digest FROM losses WHERE start_digest=?", (digest,)).fetchone()
        loss = None if lost is None else self.record(lost[0], OwnerLoss)
        if completed is None:
            return StoredStage(start, None, None, None, loss, None, None)
        if loss is not None:
            raise StoreIntegrityError("completed stage also declares owner loss")
        completion = self.record(completed[0], StageCompletion)
        if (completion.start_sha256 != digest or completion.receipt_sha256 != completed[1]
                or completion.failure_sha256 != completed[2]):
            raise StoreIntegrityError("completion foreign identity mismatch")
        if completed[2] is not None:
            failure = self.record(completed[2], StageExecutionFailure)
            if failure.start_sha256 != digest:
                raise StoreIntegrityError("execution failure START mismatch")
            return StoredStage(start, completion, None, failure, None, None, None)
        receipt = self.record(completed[1], EvidenceReceipt)
        metadata = self._db.execute("SELECT body FROM metadata WHERE receipt=?", (completed[1],)).fetchone()
        if metadata is None:
            raise StoreIntegrityError("missing scientific metadata")
        ordinals = tuple(row[0] for row in self._db.execute(
            "SELECT ordinal FROM payload_links WHERE receipt=? ORDER BY ordinal", (completed[1],)))
        if ordinals != tuple(range(len(ordinals))):
            raise StoreIntegrityError("payload ordinal gap")
        payloads = tuple(self._db.execute(
            "SELECT p.digest,p.body FROM payload_links l JOIN payloads p ON p.digest=l.payload "
            "WHERE l.receipt=? ORDER BY l.ordinal", (completed[1],)))
        encoded = EncodedB0HEvidence(metadata[0], payloads)
        if evidence_receipt(start, encoded, limits=self.manifest.limits) != receipt:
            raise StoreIntegrityError("scientific receipt differs from exact bytes")
        value = decode_b0h_evidence(encoded, limits=self.manifest.limits)
        return StoredStage(start, completion, receipt, None, None, encoded, value)

    def stages(self, case: SbcCaseId) -> tuple[StoredStage, ...]:
        rows = self._db.execute("SELECT digest FROM starts WHERE case_id=?", (case.canonical_id,))
        values = tuple(self.stage(row[0]) for row in rows)
        order = {"generation": 0, "structural": 1, "fit": 2, "quantities": 3, "summary": 4}
        return tuple(sorted(values, key=lambda s: (order[s.start.key.stage],
                            -1 if s.start.key.attempt_id is None else s.start.key.attempt_id)))

    def audit(self) -> None:
        actual_schema = dict(self._db.execute(
            "SELECT name,sql FROM sqlite_master WHERE type='table'"))
        expected_schema = {sql.split("TABLE ")[1].split("(")[0]: sql for sql in B0H_SQL_SCHEMA}
        if actual_schema != expected_schema:
            raise StoreIntegrityError("database table definition drift")
        if self._db.execute("SELECT count(*) FROM sqlite_master WHERE type='trigger'").fetchone()[0]:
            raise StoreIntegrityError("unexpected database trigger")
        expected = (1, self.campaign_sha256, record_digest(self.admission),
                    record_digest(self.null))
        if self._db.execute("SELECT * FROM campaign").fetchall() != [expected]:
            raise StoreIntegrityError("stored campaign differs")

        if self._db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise StoreIntegrityError("SQLite integrity check failed")
        if self._db.execute("PRAGMA foreign_key_check").fetchall():
            raise StoreIntegrityError("SQLite foreign key check failed")
        used = {self.campaign_sha256, record_digest(self.admission), record_digest(self.null)}
        for case_id, stage_name, attempt, digest in self._db.execute("SELECT * FROM starts"):
            used.add(digest)
            start = self.record(digest, StageStart)
            expected = (start.key.case.canonical_id, start.key.stage,
                        -1 if start.key.attempt_id is None else start.key.attempt_id)
            if (expected != (case_id, stage_name, attempt) or start.key.case not in self.manifest.cases
                    or start.key.campaign_sha256 != self.campaign_sha256):
                raise StoreIntegrityError("stored START index/campaign mismatch")
        for row in self._db.execute("SELECT digest,receipt,failure FROM completions"):
            used.update(value for value in row if value is not None)
        used.update(row[0] for row in self._db.execute("SELECT digest FROM losses"))
        if used != {row[0] for row in self._db.execute("SELECT digest FROM objects")}:
            raise StoreIntegrityError("orphan operational evidence; no receipt-only repair")
        receipts = {row[0] for row in self._db.execute("SELECT receipt FROM completions WHERE receipt IS NOT NULL")}
        if receipts != {row[0] for row in self._db.execute("SELECT receipt FROM metadata")}:
            raise StoreIntegrityError("orphan or missing metadata")
        linked = {row[0] for row in self._db.execute("SELECT payload FROM payload_links")}
        if linked != {row[0] for row in self._db.execute("SELECT digest FROM payloads")}:
            raise StoreIntegrityError("orphan payload")
        for value in (self.manifest, self.admission, self.null):
            if self.record(record_digest(value), type(value)) != value:
                raise StoreIntegrityError("campaign root differs")

    def inventory(self) -> tuple[tuple[str, tuple[str, ...]], ...]:
        self.audit()
        return tuple((case.canonical_id, tuple(
            digest for stage in self.stages(case) for digest in (
                record_digest(stage.start),
                None if stage.completion is None else record_digest(stage.completion),
                None if stage.loss is None else record_digest(stage.loss),
            ) if digest is not None)) for case in self.manifest.cases)
```

- [ ] Step 5: Create `genomeos/validation/heterogeneity_runner_store.py` with the following complete code. The imported `B0H_SQL_SCHEMA` is the executable form of the table contract above.

```python
"""Single-owner SQLite B0H evidence (design §§5,7–8,12; runner §§4–5)."""
from __future__ import annotations

import fcntl
import os
import sqlite3
from urllib.parse import quote
import time
from pathlib import Path

from genomeos.validation.heterogeneity_codec import EncodedB0HEvidence
from genomeos.validation.heterogeneity_runner_reader import (
    B0H_SQL_SCHEMA, B0H_SQL_TABLES, B0HSqlReader, StoreIntegrityError,
)
from genomeos.validation.heterogeneity_runner_records import (
    AdmissionReceipt, CampaignManifest, EvidenceReceipt, OwnerLoss, PreparedNull,
    PublicationPacket, StageCompletion, StageExecutionFailure, StageStart, StoredStage,
)
from genomeos.validation.heterogeneity_runner_wire import (
    evidence_receipt, read_runner_record, record_digest, runner_record_bytes, sha256,
)
from genomeos.validation.heterogeneity_simulation_types import SbcCaseId

_RETRYABLE = {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED, sqlite3.SQLITE_IOERR,
              sqlite3.SQLITE_FULL, sqlite3.SQLITE_CANTOPEN}


class StoreUnavailable(RuntimeError):
    """A storage I/O or lock failure prevented establishing the exact state."""


class PendingPublication(StoreUnavailable):
    """Exact known live bytes remain available; this is no second science delivery."""

    def __init__(self, packet: PublicationPacket, cause: BaseException) -> None:
        if type(packet) is not PublicationPacket:
            raise StoreIntegrityError("pending publication requires exact immutable packet")
        super().__init__("publication pending; science paused")
        self.packet = packet
        self.__cause__ = cause


class LocalB0HStore:
    def __init__(self, database: Path, *, manifest: CampaignManifest,
                 admission: AdmissionReceipt, null: PreparedNull, owner_id: str) -> None:
        self.database = database
        self.manifest = read_runner_record(runner_record_bytes(manifest))
        self.admission = read_runner_record(runner_record_bytes(admission))
        self.null = read_runner_record(runner_record_bytes(null))
        if type(self.manifest) is not CampaignManifest or type(self.admission) is not AdmissionReceipt:
            raise StoreIntegrityError("wrong campaign or admission root")
        if type(self.null) is not PreparedNull or type(owner_id) is not str or not owner_id:
            raise StoreIntegrityError("wrong null or owner identity")
        if (record_digest(admission) != manifest.admission_sha256
                or record_digest(null) != manifest.null_sha256
                or admission.source != manifest.source or admission.runtime != manifest.runtime):
            raise StoreIntegrityError("campaign admission/null identity mismatch")
        if (database.name != "study.sqlite3"
                or database.parent.resolve() != Path(admission.storage.database_parent)
                or database.parent.stat().st_dev != admission.storage.device_id):
            raise StoreIntegrityError("database filesystem differs from admission")
        self.owner_id = owner_id
        self.campaign_sha256 = record_digest(self.manifest)
        self._create = False
        self._lock = None
        self._db = None

    @classmethod
    def create(cls, database: Path, *, manifest: CampaignManifest,
               admission: AdmissionReceipt, null: PreparedNull,
               owner_id: str) -> LocalB0HStore:
        result = cls(database, manifest=manifest, admission=admission, null=null, owner_id=owner_id)
        result._create = True
        return result

    def __enter__(self) -> LocalB0HStore:
        lockpath = self.database.with_name(self.database.name + ".lock")
        if self.database.is_symlink() or lockpath.is_symlink():
            raise StoreIntegrityError("database/lock symlink refused")
        if not self._create and not self.database.is_file():
            raise StoreIntegrityError("existing campaign database is missing")
        self._lock = os.open(lockpath, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(self._lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if os.fstat(self._lock).st_ino != lockpath.stat().st_ino:
                raise StoreIntegrityError("lock inode changed")
            if self._create:
                descriptor = os.open(self.database, os.O_CREAT | os.O_EXCL | os.O_RDWR | os.O_NOFOLLOW, 0o600)
                os.close(descriptor)
            self._db = sqlite3.connect("file:" + quote(str(self.database.resolve())) + "?mode=rw",
                                       uri=True, isolation_level=None)
            self._reader = B0HSqlReader(self._db, manifest=self.manifest,
                                       admission=self.admission, null=self.null)
            if not self._create and not self._db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'").fetchall():
                raise StoreIntegrityError("existing empty database is not a prepared campaign")
            self._db.execute("PRAGMA journal_mode=DELETE")
            self._db.execute("PRAGMA synchronous=EXTRA")
            self._db.execute("PRAGMA foreign_keys=ON")
            for pragma, expected in (("journal_mode", "delete"), ("synchronous", 3),
                                     ("foreign_keys", 1)):
                if self._db.execute("PRAGMA " + pragma).fetchone()[0] != expected:
                    raise StoreIntegrityError("SQLite setting not established: " + pragma)
            tables = tuple(row[0] for row in self._db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"))
            if not tables:
                if not self._create:
                    raise StoreIntegrityError("existing empty database is not a prepared campaign")
                self._db.execute("BEGIN IMMEDIATE")
                try:
                    for statement in B0H_SQL_SCHEMA:
                        self._db.execute(statement)
                    for value in (self.manifest, self.admission, self.null):
                        self._put_object(value)
                    self._db.execute("INSERT INTO campaign VALUES(1,?,?,?)", (
                        self.campaign_sha256, record_digest(self.admission),
                        record_digest(self.null)))
                    self._commit()
                except BaseException:
                    if self._db.in_transaction:
                        self._db.execute("ROLLBACK")
                    raise
            elif tables != B0H_SQL_TABLES:
                raise StoreIntegrityError("unsupported database schema")
            self._integrity()
            for case in self.manifest.cases:
                self.stages(case)
            return self
        except BlockingIOError as error:
            self.__exit__(None, None, None)
            raise StoreUnavailable("campaign already owned") from error
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        try:
            if self._db is not None:
                self._db.close()
                self._db = None
        finally:
            if self._lock is not None:
                os.close(self._lock)
                self._lock = None

    def _require_open(self) -> None:
        if self._db is None or self._lock is None:
            raise StoreIntegrityError("store requires live campaign exclusion")

    def _commit(self) -> None:
        self._db.execute("COMMIT")

    def _object(self, digest, cls):
        return self._reader.record(digest, cls)

    def _put_object(self, value):
        raw = runner_record_bytes(value)
        digest = sha256(raw)
        prior = self._db.execute("SELECT kind,body FROM objects WHERE digest=?", (digest,)).fetchone()
        if prior is None:
            self._db.execute("INSERT INTO objects VALUES(?,?,?)", (digest, value.format, raw))
        elif prior != (value.format, raw):
            raise StoreIntegrityError("operational object conflict")
        return digest

    def _transaction(self, write, matches) -> None:
        self._require_open()
        try:
            self._db.execute("BEGIN IMMEDIATE")
            write()
            self._commit()
        except sqlite3.Error as error:
            retryable = getattr(error, "sqlite_errorcode", -1) & 255 in _RETRYABLE
            try:
                if self._db.in_transaction:
                    self._db.execute("ROLLBACK")
                if matches():
                    return
            except sqlite3.Error as inspection_error:
                if retryable:
                    raise StoreUnavailable("transaction cannot be inspected") from inspection_error
                raise
            if retryable:
                raise StoreUnavailable("publication absent after storage failure") from error
            raise
        except BaseException:
            if self._db.in_transaction:
                self._db.execute("ROLLBACK")
            raise
        if not matches():
            raise StoreIntegrityError("committed transaction readback differs")

    def start(self, record: StageStart) -> None:
        self._require_open()
        if (record.key.case not in self.manifest.cases
                or record.key.campaign_sha256 != self.campaign_sha256
                or record.worker_id != self.manifest.worker_id or record.owner_id != self.owner_id
                or record.source != self.manifest.source or record.runtime != self.manifest.runtime):
            raise StoreIntegrityError("START admission mismatch")
        key = record.key
        slot = (key.case.canonical_id, key.stage, -1 if key.attempt_id is None else key.attempt_id)
        prior = self._db.execute("SELECT digest FROM starts WHERE case_id=? AND stage=? AND attempt=?",
                                 slot).fetchone()
        if prior is not None:
            raise StoreIntegrityError("stage already has one START")
        digest = record_digest(record)
        def write():
            self._put_object(record)
            self._db.execute("INSERT INTO starts VALUES(?,?,?,?)", (*slot, digest))
        def matches():
            row = self._db.execute("SELECT digest FROM starts WHERE case_id=? AND stage=? AND attempt=?",
                                    slot).fetchone()
            return row == (digest,) and self._object(digest, StageStart) == record
        self._transaction(write, matches)

    def complete(self, start: StageStart, completion: StageCompletion, *,
                 receipt: EvidenceReceipt | None, encoded: EncodedB0HEvidence | None,
                 failure: StageExecutionFailure | None) -> None:
        packet = PublicationPacket(start, completion, receipt, encoded, failure)
        try:
            self._complete(start, completion, receipt=receipt, encoded=encoded, failure=failure)
        except sqlite3.Error as error:
            if getattr(error, "sqlite_errorcode", -1) & 255 in _RETRYABLE:
                raise PendingPublication(packet, error) from error
            raise

    def _complete(self, start: StageStart, completion: StageCompletion, *,
                  receipt: EvidenceReceipt | None, encoded: EncodedB0HEvidence | None,
                  failure: StageExecutionFailure | None) -> None:
        self._require_open()
        if self._db.in_transaction:
            # A previous failed rollback/commit inspection may have left an
            # uncommitted transaction. Never mistake its own reads for durability.
            self._db.execute("ROLLBACK")
        packet = PublicationPacket(start, completion, receipt, encoded, failure)
        digest = record_digest(start)
        if self._object(digest, StageStart) != start or completion.start_sha256 != digest:
            raise StoreIntegrityError("completion START mismatch")
        if self._db.execute("SELECT 1 FROM losses WHERE start_digest=?", (digest,)).fetchone():
            raise StoreIntegrityError("lost stage cannot complete")
        if receipt is not None:
            if (encoded is None or failure is not None
                    or evidence_receipt(start, encoded, limits=self.manifest.limits) != receipt
                    or completion.receipt_sha256 != record_digest(receipt)
                    or completion.failure_sha256 is not None):
                raise StoreIntegrityError("scientific publication packet mismatch")
        elif (failure is None or encoded is not None or failure.start_sha256 != digest
              or completion.failure_sha256 != record_digest(failure)
              or completion.receipt_sha256 is not None):
            raise StoreIntegrityError("failure publication packet mismatch")
        wanted = (record_digest(completion), completion.receipt_sha256, completion.failure_sha256)
        def matches():
            row = self._db.execute("SELECT digest,receipt,failure FROM completions WHERE start_digest=?",
                                    (digest,)).fetchone()
            if row is None:
                return False
            if row != wanted:
                raise StoreIntegrityError("immutable completion conflict")
            stage = self._stage(digest)
            if (stage.completion != completion or stage.receipt != receipt
                    or stage.failure != failure or stage.encoded != encoded):
                raise StoreIntegrityError("immutable result bytes conflict")
            return True
        if matches():
            return
        if start.owner_id != self.owner_id:
            raise StoreIntegrityError("only live START owner publishes new evidence")
        def write():
            result_digest = self._put_object(receipt if receipt is not None else failure)
            if encoded is not None:
                self._db.execute("INSERT INTO metadata VALUES(?,?)", (result_digest, encoded.metadata))
                for ordinal, (payload_digest, raw) in enumerate(encoded.payloads):
                    prior = self._db.execute("SELECT body FROM payloads WHERE digest=?",
                                             (payload_digest,)).fetchone()
                    if prior is None:
                        self._db.execute("INSERT INTO payloads VALUES(?,?)", (payload_digest, raw))
                    elif prior != (raw,):
                        raise StoreIntegrityError("payload digest collision")
                    self._db.execute("INSERT INTO payload_links VALUES(?,?,?)",
                                     (result_digest, ordinal, payload_digest))
            self._put_object(completion)
            self._db.execute("INSERT INTO completions VALUES(?,?,?,?)", (digest, *wanted))
        try:
            self._transaction(write, matches)
        except StoreUnavailable as error:
            raise PendingPublication(packet, error) from error

    def publish_pending(self, packet: PublicationPacket) -> None:
        self.complete(packet.start, packet.completion, receipt=packet.receipt,
                      encoded=packet.encoded, failure=packet.failure)

    def record_owner_loss(self, start: StageStart) -> OwnerLoss:
        self._require_open()
        digest = record_digest(start)
        prior = self._db.execute("SELECT digest FROM losses WHERE start_digest=?", (digest,)).fetchone()
        if prior is not None:
            return self._object(prior[0], OwnerLoss)
        if start.owner_id == self.owner_id or self._db.execute(
            "SELECT 1 FROM completions WHERE start_digest=?", (digest,)).fetchone():
            raise StoreIntegrityError("live/completed stage has no owner loss")
        loss = OwnerLoss(format="b0h_owner_loss", version="1", start_sha256=digest,
                         previous_owner_id=start.owner_id, observing_owner_id=self.owner_id,
                         observed_unix_ns=time.time_ns(), evidence="prior_process_exclusion_released",
                         surviving_receipts=())
        def write():
            self._db.execute("INSERT INTO losses VALUES(?,?)", (digest, self._put_object(loss)))
        def matches():
            row = self._db.execute("SELECT digest FROM losses WHERE start_digest=?", (digest,)).fetchone()
            return row == (record_digest(loss),)
        self._transaction(write, matches)
        return loss

    def _stage(self, digest: str) -> StoredStage:
        return self._reader.stage(digest)

    def stages(self, case: SbcCaseId) -> tuple[StoredStage, ...]:
        self._require_open()
        return self._reader.stages(case)

    def _integrity(self) -> None:
        self._require_open()
        self._reader.audit()

    def inventory(self) -> tuple[tuple[str, tuple[str, ...]], ...]:
        self._require_open()
        return self._reader.inventory()

```


- [ ] Verification gate: run the task's focused GREEN, mandatory smoke and static/privacy checks. Record the actual command, exit status and counts in the authorized task report. A failed fixture or adapter check is not permission to alter scientific policy.

```bash
env PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib /private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python -m pytest tests/test_heterogeneity_runner_records.py tests/test_heterogeneity_runner_store.py -o addopts='' -q
env PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib /private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python scripts/smoke.py
/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/ruff check .
env PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib /private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python scripts/freeze_contract.py --check
env PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib /private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python scripts/check_module_size.py
git diff --check
git add genomeos/validation/heterogeneity_runner_records.py genomeos/validation/heterogeneity_runner_reader.py genomeos/validation/heterogeneity_runner_store.py tests/heterogeneity_runner_fixtures.py tests/test_heterogeneity_runner_store.py
git diff --cached --name-only
env PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib /private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python scripts/check_private_files.py
```

- [ ] Inspect the staged-path output. It must contain only this task's explicitly owned files above and no SDD/private/generated evidence. Preserve unrelated work. If every check passed and the staged scope is exact, make the task commit; advance #211/#189 without closing either.

```bash
git commit -m "feat: add transactional single-owner B0H evidence store" -m "Advances #211 and #189; neither calibration nor benchmark completion is claimed."
```

## Task 3: Bound restoration and exactly-once public-stage execution

**Files:** Create `genomeos/validation/heterogeneity_runner_binding.py`, `genomeos/validation/heterogeneity_runner.py`
and `tests/test_heterogeneity_runner.py`. Scientific claim: each case consumes
exactly its retained inputs and declared accepted attempt. Acceptance: literal
wrapper-call counts and immutable reuse, convergence-only retry, identity and
process-loss refusal. The reducer consumes the pure binding interface; the
command consumes execution. No independent h, prediction or summary algorithm.

**Interfaces:** Consume Task1 records, Task2 store and the original public science
functions. Produce `validate_case_evidence(manifest, evidence) -> None`,
`next_stage_key(manifest, evidence) -> StageKey | None`, plus the exact load/execute
signatures frozen above.

- [ ] Step 1: Write these literal tests before either production module exists.

```python
"""Counted runner orchestration fixtures; no actual scientific computation."""
from __future__ import annotations

import importlib
from dataclasses import replace

import pytest

from heterogeneity_runner_fixtures import (
    accepted, campaign, dataset, failed, fit_summary, quantities,
)
from genomeos.validation.heterogeneity_attempts import FitAttemptResult
from genomeos.validation.heterogeneity_runner_store import LocalB0HStore, StoreIntegrityError


def mocked_runner(monkeypatch, *, retry=False, terminal=False):
    runner = importlib.import_module("genomeos.validation.heterogeneity_runner")
    counts = {"generation": 0, "fit": 0, "quantities": 0, "summary": 0}
    def generation(case):
        counts["generation"] += 1
        return dataset(case.study_id, case.case_id, case.track_id)
    def fit(data, *, spec):
        counts["fit"] += 1
        if spec.attempt_id == 0 and (retry or terminal):
            return failed(data, "failed" if terminal else "convergence_failed")
        return accepted(data, spec.attempt_id)
    def selected(data, *, attempt):
        counts["quantities"] += 1
        assert attempt.spec.attempt_id == (1 if retry else 0)
        assert attempt.fit.mean_draws.shape == (4, 1000 if retry else 500, 1)
        return quantities(data, attempt)
    def summary(data, *, attempt, cdf_backend):
        counts["summary"] += 1
        assert cdf_backend == "cupy"
        return fit_summary(data, attempt, cdf_backend)
    monkeypatch.setattr(runner, "generate_sbc_case", generation)
    monkeypatch.setattr(runner, "run_fit_attempt", fit)
    monkeypatch.setattr(runner, "selected_sbc_quantities", selected)
    monkeypatch.setattr(runner, "summarize_heterogeneity_fit", summary)
    return runner, counts


@pytest.mark.parametrize("study,expected", [
    (0, {"generation": 1, "fit": 1, "quantities": 1, "summary": 1}),
    (1, {"generation": 1, "fit": 1, "quantities": 0, "summary": 1}),
])
def test_fresh_case_and_reuse_have_exact_counts(tmp_path, monkeypatch, study, expected):
    runner, counts = mocked_runner(monkeypatch)
    manifest, admission, null = campaign(tmp_path)
    case = dataset(study).case_id
    with LocalB0HStore.create(tmp_path / "study.sqlite3", manifest=manifest, admission=admission,
                      null=null, owner_id="fixture-owner") as store:
        result = runner.execute_b0h_case(manifest, case, store)
        before = store.inventory()
        assert counts == expected
        loaded = runner.execute_b0h_case(manifest, case, store)
        assert counts == expected
        assert store.inventory() == before
        assert tuple(s.encoded for s in loaded.stages) == tuple(s.encoded for s in result.stages)


def test_only_completed_convergence_failure_admits_retry(tmp_path, monkeypatch):
    runner, counts = mocked_runner(monkeypatch, retry=True)
    manifest, admission, null = campaign(tmp_path)
    with LocalB0HStore.create(tmp_path / "study.sqlite3", manifest=manifest, admission=admission,
                      null=null, owner_id="fixture-owner") as store:
        result = runner.execute_b0h_case(manifest, dataset().case_id, store)
    assert counts == {"generation": 1, "fit": 2, "quantities": 1, "summary": 1}
    attempts = tuple(s for s in result.stages if s.start.key.stage == "fit")
    assert tuple(s.value.status for s in attempts) == ("convergence_failed", "accepted")
    from genomeos.validation.heterogeneity_runner_wire import record_digest
    assert record_digest(attempts[0].completion) in attempts[1].start.prerequisites


def test_runtime_failure_has_no_retry_or_diagnostics(tmp_path, monkeypatch):
    runner, counts = mocked_runner(monkeypatch, terminal=True)
    manifest, admission, null = campaign(tmp_path)
    with LocalB0HStore.create(tmp_path / "study.sqlite3", manifest=manifest, admission=admission,
                      null=null, owner_id="fixture-owner") as store:
        runner.execute_b0h_case(manifest, dataset().case_id, store)
    assert counts == {"generation": 1, "fit": 1, "quantities": 0, "summary": 0}


def test_wrong_returned_fit_is_retained_without_retry(tmp_path, monkeypatch):
    runner, counts = mocked_runner(monkeypatch)
    def rejected(data, *, spec):
        counts["fit"] += 1
        return FitAttemptResult(spec, "identity_rejected", None, None,
                                ("return_type",), "builtins.dict")
    monkeypatch.setattr(runner, "run_fit_attempt", rejected)
    manifest, admission, null = campaign(tmp_path)
    with LocalB0HStore.create(tmp_path / "study.sqlite3", manifest=manifest, admission=admission,
                      null=null, owner_id="fixture-owner") as store:
        result = runner.execute_b0h_case(manifest, dataset().case_id, store)
    assert result.stages[-1].value.returned_type == "builtins.dict"
    assert counts == {"generation": 1, "fit": 1, "quantities": 0, "summary": 0}


def test_quantities_execution_failure_keeps_independent_summary(tmp_path, monkeypatch):
    runner, counts = mocked_runner(monkeypatch)
    def broken(data, *, attempt):
        counts["quantities"] += 1
        raise KeyError("literal adapter defect")
    monkeypatch.setattr(runner, "selected_sbc_quantities", broken)
    manifest, admission, null = campaign(tmp_path)
    with LocalB0HStore.create(tmp_path / "study.sqlite3", manifest=manifest, admission=admission,
                      null=null, owner_id="fixture-owner") as store:
        result = runner.execute_b0h_case(manifest, dataset().case_id, store)
    assert counts == {"generation": 1, "fit": 1, "quantities": 1, "summary": 1}
    assert result.stages[2].failure.exception_class == "builtins.KeyError"
    assert result.stages[3].value.predictive.status == "complete"


def test_restoration_rejects_changed_selected_pairing(tmp_path, monkeypatch):
    runner, _ = mocked_runner(monkeypatch)
    manifest, admission, null = campaign(tmp_path)
    with LocalB0HStore.create(tmp_path / "study.sqlite3", manifest=manifest, admission=admission,
                      null=null, owner_id="fixture-owner") as store:
        result = runner.execute_b0h_case(manifest, dataset().case_id, store)
    binding = importlib.import_module("genomeos.validation.heterogeneity_runner_binding")
    original = result.stages[2]
    altered = replace(original.value, selected_indices=((0, 1), (1, 3), (2, 6), (3, 9)))
    # Even a locally constructor-valid root cannot contradict its receipt or fit.
    with pytest.raises(ValueError):
        binding.validate_case_evidence(manifest, replace(result, stages=(
            result.stages[0], result.stages[1], replace(original, value=altered), result.stages[3])))
def rebound_stage(manifest, stage, value):
    from genomeos.validation.heterogeneity_codec import encode_b0h_evidence
    from genomeos.validation.heterogeneity_runner_wire import evidence_receipt, record_digest
    encoded = encode_b0h_evidence(value, limits=manifest.limits)
    receipt = evidence_receipt(stage.start, encoded, limits=manifest.limits)
    completion = stage.completion.model_copy(update={"receipt_sha256": record_digest(receipt)})
    return replace(stage, completion=completion, receipt=receipt, encoded=encoded, value=value)


def test_equal_total_dataset_swap_breaks_retained_fit_prerequisite(tmp_path, monkeypatch):
    runner, _ = mocked_runner(monkeypatch)
    original = dataset()
    rows = list(original.training)
    rows[2] = replace(rows[2], ac=1)
    original = replace(original, training=tuple(rows))
    changed = list(original.training)
    changed[2], changed[3] = replace(changed[2], ac=0), replace(changed[3], ac=1)
    altered = replace(original, training=tuple(changed))
    assert sum(r.ac for r in original.training) == sum(r.ac for r in altered.training) == 1
    monkeypatch.setattr(runner, "generate_sbc_case", lambda case: original)
    manifest, admission, null = campaign(tmp_path)
    with LocalB0HStore.create(tmp_path / "study.sqlite3", manifest=manifest, admission=admission,
                              null=null, owner_id="fixture-owner") as store:
        result = runner.execute_b0h_case(manifest, original.case_id, store)
    binding = importlib.import_module("genomeos.validation.heterogeneity_runner_binding")
    replaced = rebound_stage(manifest, result.stages[0], altered)
    with pytest.raises(ValueError, match="dependency"):
        binding.validate_case_evidence(manifest, replace(result, stages=(replaced,) + result.stages[1:]))


def test_wrong_track_and_orphan_retry_are_rejected(tmp_path, monkeypatch):
    runner, _ = mocked_runner(monkeypatch, retry=True)
    manifest, admission, null = campaign(tmp_path)
    with LocalB0HStore.create(tmp_path / "study.sqlite3", manifest=manifest, admission=admission,
                              null=null, owner_id="fixture-owner") as store:
        result = runner.execute_b0h_case(manifest, dataset().case_id, store)
    binding = importlib.import_module("genomeos.validation.heterogeneity_runner_binding")
    other_track = rebound_stage(manifest, result.stages[2], accepted(dataset(track=1), 1))
    with pytest.raises(ValueError):
        binding.validate_case_evidence(manifest, replace(result,
            stages=result.stages[:2] + (other_track,) + result.stages[3:]))
    with pytest.raises(ValueError, match="orphan"):
        binding.validate_case_evidence(manifest, replace(result,
            stages=(result.stages[0],) + result.stages[2:]))


def test_changed_shared_heldout_retained_order_is_rejected(tmp_path, monkeypatch):
    runner, _ = mocked_runner(monkeypatch)
    manifest, admission, null = campaign(tmp_path)
    with LocalB0HStore.create(tmp_path / "study.sqlite3", manifest=manifest, admission=admission,
                              null=null, owner_id="fixture-owner") as store:
        result = runner.execute_b0h_case(manifest, dataset(2).case_id, store)
    binding = importlib.import_module("genomeos.validation.heterogeneity_runner_binding")
    # A bypassed wrong order must fail before metadata normalization can rescue it.
    original = result.stages[-1].value
    altered_predictive = object.__new__(type(original.predictive))
    for name in original.predictive.__dataclass_fields__:
        object.__setattr__(altered_predictive, name, getattr(original.predictive, name))
    object.__setattr__(altered_predictive, "targets", original.predictive.targets[::-1])
    altered = object.__new__(type(original))
    for name in original.__dataclass_fields__:
        object.__setattr__(altered, name, getattr(original, name))
    object.__setattr__(altered, "predictive", altered_predictive)
    with pytest.raises(ValueError):
        binding.validate_case_evidence(manifest, replace(result,
            stages=result.stages[:-1] + (replace(result.stages[-1], value=altered),)))


def test_unexpected_structural_return_is_retained_and_terminal(tmp_path, monkeypatch):
    from genomeos.validation.heterogeneity_attempts import StructuralCheckResult
    runner, counts = mocked_runner(monkeypatch)
    calls = []
    def structural(data):
        calls.append(data.case_id)
        return StructuralCheckResult(data.case_id, "unexpected_return", None, None, "builtins.dict")
    monkeypatch.setattr(runner, "exercise_unavailable", structural)
    manifest, admission, null = campaign(tmp_path)
    with LocalB0HStore.create(tmp_path / "study.sqlite3", manifest=manifest, admission=admission,
                              null=null, owner_id="fixture-owner") as store:
        result = runner.execute_b0h_case(manifest, dataset(3).case_id, store)
        runner.execute_b0h_case(manifest, dataset(3).case_id, store)
    assert calls == [dataset(3).case_id]
    assert result.stages[-1].value.status == "unexpected_return"
    assert counts == {"generation": 1, "fit": 0, "quantities": 0, "summary": 0}


def test_competing_process_cannot_deliver_a_scientific_stage(tmp_path, monkeypatch):
    import os
    import subprocess
    import sys
    from pathlib import Path
    runner, counts = mocked_runner(monkeypatch)
    manifest, admission, null = campaign(tmp_path)
    child_code = """
import sys
from pathlib import Path
from heterogeneity_runner_fixtures import campaign
from genomeos.validation.heterogeneity_runner_store import LocalB0HStore, StoreUnavailable
from genomeos.validation.heterogeneity_runner import execute_b0h_case
parent = Path(sys.argv[1])
manifest, admission, null = campaign(parent)
try:
    with LocalB0HStore(parent / "study.sqlite3", manifest=manifest,
                       admission=admission, null=null, owner_id="competing-process") as store:
        raise AssertionError("competing process acquired scientific admission")
except StoreUnavailable:
    print("blocked before any stage call")
"""
    with LocalB0HStore.create(tmp_path / "study.sqlite3", manifest=manifest, admission=admission,
                              null=null, owner_id="fixture-owner") as store:
        process = subprocess.run([sys.executable, "-c", child_code, str(tmp_path)], check=True,
            capture_output=True, text=True, env={**os.environ,
                "PYTHONPATH": str(Path(__file__).parent) + os.pathsep + os.environ.get("PYTHONPATH", "")})
        assert process.stdout.strip() == "blocked before any stage call"
        runner.execute_b0h_case(manifest, dataset().case_id, store)
    assert counts == {"generation": 1, "fit": 1, "quantities": 1, "summary": 1}


```

Append these to `tests/test_heterogeneity_runner.py` during Task3, before its
production implementation. All interruption points are deliberate fixture
faults; no real process is killed and no NUTS call occurs.

```python
@pytest.mark.parametrize("where", ("before_call", "during_call", "after_return"))
def test_process_loss_never_redelivers(tmp_path, monkeypatch, where):
    runner, counts = mocked_runner(monkeypatch)
    manifest, admission, null = campaign(tmp_path)
    path = tmp_path / "study.sqlite3"
    with LocalB0HStore.create(path, manifest=manifest, admission=admission,
                      null=null, owner_id="fixture-owner") as store:
        if where == "before_call":
            original = store.start
            def interrupted(record):
                original(record)
                raise KeyboardInterrupt
            monkeypatch.setattr(store, "start", interrupted)
        elif where == "during_call":
            def interrupted(case):
                counts["generation"] += 1
                raise KeyboardInterrupt
            monkeypatch.setattr(runner, "generate_sbc_case", interrupted)
        else:
            def interrupted(*args, **kwargs):
                raise KeyboardInterrupt
            monkeypatch.setattr(runner, "encode_b0h_evidence", interrupted)
        with pytest.raises(KeyboardInterrupt):
            runner.execute_b0h_case(manifest, dataset().case_id, store)
    before = dict(counts)
    with LocalB0HStore(path, manifest=manifest, admission=admission,
                      null=null, owner_id="replacement-process") as store:
        result = runner.execute_b0h_case(manifest, dataset().case_id, store)
    assert counts == before
    assert counts["fit"] == counts["quantities"] == counts["summary"] == 0
    assert result.stages[0].loss is not None
    assert result.stages[0].completion is None


def test_generation_failure_has_no_fit_or_diagnostic_calls(tmp_path, monkeypatch):
    from genomeos.validation.heterogeneity_simulation_types import GenerationFailure
    runner, counts = mocked_runner(monkeypatch)
    def generation(case):
        counts["generation"] += 1
        data = dataset()
        return GenerationFailure(case, data.provenance, "truth_mean", None,
                                 "rng_exception", None, None, None, None,
                                 "ValueError", "literal synthetic generation failure")
    monkeypatch.setattr(runner, "generate_sbc_case", generation)
    manifest, admission, null = campaign(tmp_path)
    with LocalB0HStore.create(tmp_path / "study.sqlite3", manifest=manifest, admission=admission,
                      null=null, owner_id="fixture-owner") as store:
        runner.execute_b0h_case(manifest, dataset().case_id, store)
    assert counts == {"generation": 1, "fit": 0, "quantities": 0, "summary": 0}


def test_actual_structural_wrapper_refuses_before_graph_or_sampler(tmp_path, monkeypatch):
    import genomeos.validation.heterogeneity_attempts as attempts
    import genomeos.surfaces.reference_heterogeneity as scientific
    runner, counts = mocked_runner(monkeypatch)
    calls = {"structural": 0, "fitter": 0, "graph": 0, "sampler": 0}
    actual_wrapper = attempts.exercise_unavailable
    actual_fitter = attempts.fit_reference_population_heterogeneity
    def fitter(*args, **kwargs):
        calls["fitter"] += 1
        return actual_fitter(*args, **kwargs)
    def structural(data):
        calls["structural"] += 1
        return actual_wrapper(data)
    def graph(*args, **kwargs):
        calls["graph"] += 1
        raise AssertionError("structural case entered graph")
    def sampler(*args, **kwargs):
        calls["sampler"] += 1
        raise AssertionError("structural case entered sampler")
    monkeypatch.setattr(attempts, "fit_reference_population_heterogeneity", fitter)
    monkeypatch.setattr(runner, "exercise_unavailable", structural)
    monkeypatch.setattr(scientific.pm, "Model", graph)
    monkeypatch.setattr(scientific.pm, "sample", sampler)
    manifest, admission, null = campaign(tmp_path)
    with LocalB0HStore.create(tmp_path / "study.sqlite3", manifest=manifest, admission=admission,
                      null=null, owner_id="fixture-owner") as store:
        result = runner.execute_b0h_case(manifest, dataset(3).case_id, store)
    assert calls == {"structural": 1, "fitter": 1, "graph": 0, "sampler": 0}
    assert counts == {"generation": 1, "fit": 0, "quantities": 0, "summary": 0}
    assert result.stages[-1].value.status == "expected_refusal"
```


- [ ] Step 2: Run RED before creating the binding/executor modules.

```bash
env PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib /private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python -m pytest tests/test_heterogeneity_runner.py::test_fresh_case_and_reuse_have_exact_counts -o addopts='' -q
```

Expected: both named test cases fail because the executor module does not exist;
all Task1/Task2 tests must already pass. No after-the-fact collection error counts as RED.

- [ ] Step 3: Create `genomeos/validation/heterogeneity_runner_binding.py` with this code.

```python
"""Pure B0H receipt and dataset binding (design §§5,7–8,12; runner §§3–6)."""
from __future__ import annotations

import struct
import json

from genomeos.validation.heterogeneity_attempts import (
    FitAttemptResult, StructuralCheckResult, plan_fit_attempt, require_fit_identity,
)
from genomeos.validation.heterogeneity_codec import encode_b0h_evidence
from genomeos.validation.heterogeneity_runner_records import (
    CampaignManifest, CaseEvidence, StageKey, StoredStage,
)
from genomeos.validation.heterogeneity_runner_wire import evidence_receipt, record_digest
from genomeos.validation.heterogeneity_sbc_quantity_types import SelectedSbcQuantities
from genomeos.validation.heterogeneity_simulation_types import (
    AllUnavailableDataset, GeneratedDataset, GenerationFailure,
)
from genomeos.validation.heterogeneity_summary_types import HeterogeneityFitSummary


def _equal_float(left: float, right: float) -> bool:
    return struct.pack(">d", left) == struct.pack(">d", right)


def _next(manifest: CampaignManifest, evidence: CaseEvidence) -> StageKey | None:
    stages = evidence.stages
    stage, attempt = "generation", None
    if stages:
        latest = stages[-1]
        if latest.completion is None:
            return None
        name = latest.start.key.stage
        value = latest.value
        if name == "generation":
            if type(value) is GeneratedDataset:
                stage, attempt = "fit", 0
            elif type(value) is AllUnavailableDataset:
                stage, attempt = "structural", None
            else:
                return None
        elif name == "fit":
            if type(value) is not FitAttemptResult:
                return None
            if value.status == "convergence_failed" and value.spec.attempt_id == 0:
                stage, attempt = "fit", 1
            elif value.status == "accepted":
                stage = "quantities" if evidence.case.study_id == 0 else "summary"
                attempt = value.spec.attempt_id
            else:
                return None
        elif name == "quantities":
            stage, attempt = "summary", latest.start.key.attempt_id
        else:
            return None
    return StageKey(campaign_sha256=evidence.campaign_sha256, case=evidence.case,
                    stage=stage, attempt_id=attempt)


def _bind_root(manifest: CampaignManifest, stage: StoredStage,
               dataset: object, accepted: FitAttemptResult | None) -> None:
    value, key = stage.value, stage.start.key
    if value is None:
        return
    if key.stage == "generation":
        if type(value) not in (GeneratedDataset, AllUnavailableDataset, GenerationFailure):
            raise ValueError("generation has wrong root")
        if value.case_id != key.case:
            raise ValueError("generation case mismatch")
    elif key.stage == "structural":
        if type(dataset) is not AllUnavailableDataset or type(value) is not StructuralCheckResult:
            raise ValueError("structural root or dataset mismatch")
        if value.case != key.case:
            raise ValueError("structural case mismatch")
    elif key.stage == "fit":
        if type(dataset) is not GeneratedDataset or type(value) is not FitAttemptResult:
            raise ValueError("fit root or dataset mismatch")
        if value.spec != plan_fit_attempt(dataset, attempt_id=key.attempt_id):
            raise ValueError("fit spec differs from stage")
        if value.status == "accepted":
            require_fit_identity(dataset, spec=value.spec, fit=value.fit)
    else:
        if type(dataset) is not GeneratedDataset or accepted is None:
            raise ValueError("diagnostics require accepted dataset-bound fit")
        expected_type = SelectedSbcQuantities if key.stage == "quantities" else HeterogeneityFitSummary
        if type(value) is not expected_type:
            raise ValueError("diagnostic root mismatch")
        require_fit_identity(dataset, spec=accepted.spec, fit=accepted.fit)
        if value.spec != accepted.spec or key.attempt_id != accepted.spec.attempt_id:
            raise ValueError("diagnostic attempt mismatch")
        if key.stage == "quantities":
            if type(value) is not SelectedSbcQuantities:
                raise ValueError("quantities root mismatch")
            expected = ((dataset.truth.mean, dataset.truth.rho),) + tuple(
                (float(accepted.fit.mean_draws[c, d, 0]), float(accepted.fit.rho_draws[c, d, 0]))
                for c, d in value.selected_indices)
            if value.points[:5] != expected:
                raise ValueError("selected points differ from retained truth/paired draws")
        else:
            if type(value) is not HeterogeneityFitSummary:
                raise ValueError("summary root mismatch")
            if (value.variant_id != dataset.training[0].variant_id
                    or value.predictive.targets != dataset.heldouts
                    or value.predictive.cdf_backend != manifest.cdf_backend
                    or not _equal_float(value.parameters[0].truth, dataset.truth.mean)
                    or not _equal_float(value.parameters[1].truth, dataset.truth.rho)):
                raise ValueError("summary truth/targets/backend binding mismatch")


def validate_case_evidence(manifest: CampaignManifest, evidence: CaseEvidence) -> None:
    if type(evidence) is not CaseEvidence or evidence.campaign_sha256 != record_digest(manifest):
        raise ValueError("case campaign identity mismatch")
    if evidence.case not in manifest.cases or type(evidence.stages) is not tuple:
        raise ValueError("case membership or stage sequence mismatch")
    prior = CaseEvidence(evidence.campaign_sha256, evidence.case, ())
    dataset, accepted = None, None
    for stage in evidence.stages:
        if type(stage) is not StoredStage or stage.start.key != _next(manifest, prior):
            raise ValueError("unexplained stage or orphan scientific retry")
        start = stage.start
        dependencies = tuple(record_digest(s.completion) for s in prior.stages)
        if (start.prerequisites != dependencies or start.worker_id != manifest.worker_id
                or start.source != manifest.source or start.runtime != manifest.runtime
                or start.cdf_backend != manifest.cdf_backend):
            raise ValueError("START dependency/runtime/assignment mismatch")
        start_digest = record_digest(start)
        if stage.completion is None:
            if any(x is not None for x in (stage.receipt, stage.failure, stage.encoded, stage.value)):
                raise ValueError("receipt/result without COMPLETE")
            if stage.loss is not None and (stage.loss.start_sha256 != start_digest
                    or stage.loss.previous_owner_id != start.owner_id):
                raise ValueError("owner loss identity mismatch")
        else:
            if stage.loss is not None or stage.completion.start_sha256 != start_digest:
                raise ValueError("completion/loss START mismatch")
            record_digest(stage.completion)
            if stage.receipt is not None:
                if (stage.failure is not None or stage.encoded is None or stage.value is None
                        or stage.completion.receipt_sha256 != record_digest(stage.receipt)
                        or stage.completion.failure_sha256 is not None
                        or evidence_receipt(start, stage.encoded, limits=manifest.limits) != stage.receipt
                        or encode_b0h_evidence(stage.value, limits=manifest.limits) != stage.encoded):
                    raise ValueError("receipt/scientific bytes mismatch")
                _bind_root(manifest, stage, dataset, accepted)
            elif (stage.failure is None or stage.encoded is not None or stage.value is not None
                  or stage.completion.receipt_sha256 is not None
                  or stage.completion.failure_sha256 != record_digest(stage.failure)
                  or stage.failure.start_sha256 != start_digest):
                raise ValueError("execution failure envelope mismatch")
        if start.key.stage == "generation":
            dataset = stage.value
        if type(stage.value) is FitAttemptResult and stage.value.status == "accepted":
            accepted = stage.value
        prior = CaseEvidence(prior.campaign_sha256, prior.case, prior.stages + (stage,))


def next_stage_key(manifest: CampaignManifest, evidence: CaseEvidence) -> StageKey | None:
    validate_case_evidence(manifest, evidence)
    return _next(manifest, evidence)


def require_paired_generations(left: StoredStage, right: StoredStage) -> None:
    a, b = left.start.key.case, right.start.key.case
    if (a.study_id == 0 or (a.study_id, a.case_id, a.replicate_id) !=
            (b.study_id, b.case_id, b.replicate_id) or {a.track_id, b.track_id} != {0, 1}):
        raise ValueError("paired generation identity mismatch")
    if left.encoded is None or right.encoded is None:
        return
    # Read only validated canonical scientific metadata, preserving all field bits.
    # Excluding case_id is a comparison view, never a rewritten stored result.
    def content(encoded):
        document = json.loads(encoded.metadata)
        root = document["root"]
        return (root[1], {key: value for key, value in root[2].items() if key != "case_id"},
                encoded.payloads)
    if content(left.encoded) != content(right.encoded):
        raise ValueError("paired stress generation content differs")
```

- [ ] Step 4: Create `genomeos/validation/heterogeneity_runner.py` with this code.

```python
"""Offline one-call B0H case execution (design §§5,7–8,12; runner §4)."""
from __future__ import annotations

import resource
import sys
import time

from genomeos.validation.heterogeneity_attempts import (
    FitAttemptResult, exercise_unavailable, plan_fit_attempt, run_fit_attempt,
)
from genomeos.validation.heterogeneity_codec import encode_b0h_evidence
from genomeos.validation.heterogeneity_runner_binding import (
    next_stage_key, validate_case_evidence, require_paired_generations,
)
from genomeos.validation.heterogeneity_runner_records import (
    CampaignManifest, CaseEvidence, StageCompletion, StageExecutionFailure, StageStart,
)
from genomeos.validation.heterogeneity_runner_store import LocalB0HStore, StoreIntegrityError
from genomeos.validation.heterogeneity_runner_wire import evidence_receipt, record_digest
from genomeos.validation.heterogeneity_sbc_quantities import selected_sbc_quantities
from genomeos.validation.heterogeneity_simulation import generate_sbc_case
from genomeos.validation.heterogeneity_simulation_types import SbcCaseId
from genomeos.validation.heterogeneity_summaries import summarize_heterogeneity_fit


def load_b0h_case(manifest: CampaignManifest, case: SbcCaseId,
                  store: LocalB0HStore) -> CaseEvidence:
    if record_digest(store.manifest) != record_digest(manifest) or case not in manifest.cases:
        raise StoreIntegrityError("requested campaign/case mismatch")
    evidence = CaseEvidence(record_digest(manifest), case, store.stages(case))
    validate_case_evidence(manifest, evidence)
    if case.study_id != 0 and evidence.stages:
        paired = SbcCaseId(1 - case.track_id, case.study_id, case.case_id, case.replicate_id)
        other = CaseEvidence(record_digest(manifest), paired, store.stages(paired))
        validate_case_evidence(manifest, other)
        if other.stages:
            require_paired_generations(evidence.stages[0], other.stages[0])
    return evidence


def _resource_observation() -> tuple[int | None, str | None]:
    if sys.platform not in ("linux", "darwin"):
        return None, "process_peak_rss_unit_unavailable_on_platform"
    try:
        raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    except OSError as error:
        return None, type(error).__module__ + "." + type(error).__qualname__
    return int(raw) * (1024 if sys.platform == "linux" else 1), None


def _execution_error(start: StageStart, phase: str, error: Exception) -> StageExecutionFailure:
    return StageExecutionFailure(
        format="b0h_execution_failure", version="1", start_sha256=record_digest(start),
        phase=phase, exception_class=type(error).__module__ + "." + type(error).__qualname__,
        message_utf8hex=str(error).encode("utf-8", "surrogatepass").hex(),
    )


def execute_b0h_case(manifest: CampaignManifest, case: SbcCaseId,
                     store: LocalB0HStore) -> CaseEvidence:
    while True:
        evidence = load_b0h_case(manifest, case, store)
        if evidence.stages and evidence.stages[-1].completion is None:
            pending = evidence.stages[-1]
            if pending.start.owner_id != store.owner_id and pending.loss is None:
                store.record_owner_loss(pending.start)
            return load_b0h_case(manifest, case, store)
        key = next_stage_key(manifest, evidence)
        if key is None:
            return evidence
        dataset = None if not evidence.stages else evidence.stages[0].value
        accepted = next((s.value for s in evidence.stages
                         if type(s.value) is FitAttemptResult and s.value.status == "accepted"), None)
        # Planning and guarded prerequisite validation occur before START/call.
        spec = plan_fit_attempt(dataset, attempt_id=key.attempt_id) if key.stage == "fit" else None
        if key.stage == "generation":
            call = lambda: generate_sbc_case(case)
        elif key.stage == "structural":
            call = lambda: exercise_unavailable(dataset)
        elif key.stage == "fit":
            call = lambda: run_fit_attempt(dataset, spec=spec)
        elif key.stage == "quantities":
            call = lambda: selected_sbc_quantities(dataset, attempt=accepted)
        else:
            call = lambda: summarize_heterogeneity_fit(dataset, attempt=accepted,
                                                      cdf_backend=manifest.cdf_backend)
        start = StageStart(
            format="b0h_start", version="1", key=key, worker_id=manifest.worker_id,
            owner_id=store.owner_id, source=manifest.source, runtime=manifest.runtime,
            cdf_backend=manifest.cdf_backend,
            prerequisites=tuple(record_digest(s.completion) for s in evidence.stages),
            started_unix_ns=time.time_ns(), started_monotonic_ns=time.monotonic_ns(),
        )
        store.start(start)
        call_started = time.monotonic_ns()
        failure, receipt, encoded = None, None, None
        try:
            value = call()
        except Exception as error:
            elapsed = time.monotonic_ns() - call_started
            failure = _execution_error(start, "public_call", error)
        else:
            elapsed = time.monotonic_ns() - call_started
            # Codec/storage errors propagate with their actual adapter classification.
            # In particular a codec constructor defect such as #232 is not a
            # synthetic scientific result or a convergence-retry condition.
            encoded = encode_b0h_evidence(value, limits=manifest.limits)
            receipt = evidence_receipt(start, encoded, limits=manifest.limits)
        rss, unavailable = _resource_observation()
        completion = StageCompletion(
            format="b0h_completion", version="1", start_sha256=record_digest(start),
            receipt_sha256=None if receipt is None else record_digest(receipt),
            failure_sha256=None if failure is None else record_digest(failure),
            whole_call_elapsed_ns=elapsed, process_peak_rss_bytes=rss,
            resource_unavailable_reason=unavailable,
        )
        store.complete(start, completion, receipt=receipt, encoded=encoded, failure=failure)
        # Fresh evidence passes exactly the same dataset-bound checks as restoration.
        # Wrong returned identity stops before any downstream scientific call.
        load_b0h_case(manifest, case, store)
```

- [ ] Step 5: Run focused GREEN, then mandatory smoke. If return validation or
fixture construction fails, correct the literal fixture/adapter defect and rerun
the touched focused test; never weaken the unchanged scientific constructors.

```bash
env PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib /private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python -m pytest tests/test_heterogeneity_runner_records.py tests/test_heterogeneity_runner_store.py tests/test_heterogeneity_runner.py -o addopts='' -q
env PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib /private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python scripts/smoke.py
```


- [ ] Verification gate: run the task's focused GREEN, mandatory smoke and static/privacy checks. Record the actual command, exit status and counts in the authorized task report. A failed fixture or adapter check is not permission to alter scientific policy.

```bash
env PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib /private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python -m pytest tests/test_heterogeneity_runner.py -o addopts='' -q
env PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib /private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python scripts/smoke.py
/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/ruff check .
env PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib /private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python scripts/freeze_contract.py --check
env PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib /private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python scripts/check_module_size.py
git diff --check
git add genomeos/validation/heterogeneity_runner_binding.py genomeos/validation/heterogeneity_runner.py tests/test_heterogeneity_runner.py
git diff --cached --name-only
env PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib /private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python scripts/check_private_files.py
```

- [ ] Inspect the staged-path output. It must contain only this task's explicitly owned files above and no SDD/private/generated evidence. Preserve unrelated work. If every check passed and the staged scope is exact, make the task commit; advance #211/#189 without closing either.

```bash
git commit -m "feat: execute bound B0H stages with single delivery" -m "Advances #211 and #189; neither calibration nor benchmark completion is claimed."
```

## Task 4: Pure full-study reduction with honest denominators

**Files:** Create the two reduction modules and `tests/test_heterogeneity_reduction.py`.
Scientific objective: determine the twelve correct-family and four fixed control
decisions without misrepresenting missing outcomes or dependent stress targets.
Acceptance: exact integer statistic/p-value anchors, complete membership, actual-N
conditional counts, distinct sensitivity and discrepancy decisions, descriptive
denominators and no scientific side effects. Consumers are offline reporting and
collection. Secondary metric values create no additional threshold.

**Interfaces:** Consume immutable `CampaignManifest`, complete ordered
`tuple[CaseEvidence,...]` and public `RankNullReference`; produce `StudyReduction`.
`rank_reduction(track_id, mode_id, quantity_id, ranks, failures, reference)` is a
pure narrow helper used by the reducer and directly tested against literal
counts. Its inputs require exactly512 total valid-rank/failure entries; only the
valid512 case calls the existing `test_rank_uniformity`.

- [ ] Step 1: Add the following tests before implementing the reduction modules.

```python
"""Pure reducer anchors; literal mock nulls are not calibration results."""
from __future__ import annotations

import importlib

import pytest

from heterogeneity_runner_fixtures import campaign
from genomeos.validation.heterogeneity_runner_records import CaseEvidence
from genomeos.validation.heterogeneity_runner_wire import record_digest
from genomeos.validation.sbc_ranks import RankNullReference, rank_ecdf_statistic


def test_literal_full_n_rank_decisions_and_inclusive_tail():
    reduction = importlib.import_module("genomeos.validation.heterogeneity_reduction")
    reference = RankNullReference(512, 1653499886, (100,) * 99999 + (2048,))
    balanced = (0,) * 103 + (1,) * 103 + (2,) * 102 + (3,) * 102 + (4,) * 102
    assert rank_ecdf_statistic((103, 103, 102, 102, 102)) == 6
    assert rank_ecdf_statistic((512, 0, 0, 0, 0)) == 2048
    correct = reduction.rank_reduction(0, 0, 0, balanced, (), reference)
    control = reduction.rank_reduction(0, 1, 3, (0,) * 512, (), reference)
    assert correct.test.statistic == 6
    assert correct.decision == "not_reject"
    assert control.test.p_value == 2 / 100001
    assert control.test.bonferroni_p_value == 24 / 100001
    assert control.decision == "reject"
    assert control.role == "required_control"


def test_511_or_zero_ranks_never_get_a_full_n_test():
    reduction = importlib.import_module("genomeos.validation.heterogeneity_reduction")
    reference = RankNullReference(512, 1653499886, (100,) * 100000)
    result = reduction.rank_reduction(
        1, 0, 5, (2,) * 511, ("dependence_rank_order_unresolved",), reference)
    assert result.actual_n == 511
    assert result.missing_n == 1
    assert result.test is None
    assert result.decision == "uncomputable"
    empty = reduction.rank_reduction(1, 0, 5, (), ("unstarted",) * 512, reference)
    assert empty.counts == (0, 0, 0, 0, 0)
    assert empty.test is None
    with pytest.raises(ValueError):
        reduction.rank_reduction(1, 0, 5, (2,) * 511, ("unstarted",),
                                 RankNullReference(511, 1653499886, (100,) * 100000))


def test_empty_campaign_accounts_all_records_without_science(tmp_path, monkeypatch):
    reduction = importlib.import_module("genomeos.validation.heterogeneity_reduction")
    manifest, _, null = campaign(tmp_path)
    cases = tuple(CaseEvidence(record_digest(manifest), case, ()) for case in manifest.cases)
    def forbidden(*args, **kwargs):
        raise AssertionError("pure empty reduction called a rank test or science")
    monkeypatch.setattr(reduction, "test_rank_uniformity", forbidden)
    reference = RankNullReference(null.sample_size, null.seed, null.statistics)
    output = reduction.reduce_b0h_study(manifest, cases, reference)
    assert len(output.cases) == 1938
    assert output.planned_initial_fits == 1936
    assert output.completed_fit_calls == output.ambiguous_fit_calls == 0
    assert len(output.ranks) == 36
    assert all(row.actual_n == 0 and row.missing_n == 512 for row in output.ranks)
    assert output.sensitivity_limited
    assert not output.correct_family_rejected
    assert not output.unconditional_claim_eligible
    assert output.permitted_claim is None
    with pytest.raises(ValueError, match="exact StudyReduction"):
        reduction.reduction_bytes(object())
    malformed = output.model_copy(update={"cases": list(output.cases)})
    with pytest.raises(ValueError):
        reduction.reduction_bytes(malformed)
    assert reduction.reduction_bytes(output) == reduction.reduction_bytes(
        reduction.reduce_b0h_study(manifest, cases, reference))
    for invalid in (cases[:-1], cases[::-1], cases[:-1] + (cases[0],)):
        with pytest.raises(ValueError):
            reduction.reduce_b0h_study(manifest, invalid, reference)
def test_absent_quantities_report_actual_failed_fit(tmp_path, monkeypatch):
    from test_heterogeneity_runner import mocked_runner
    from genomeos.validation.heterogeneity_runner_store import LocalB0HStore
    runner, _ = mocked_runner(monkeypatch, terminal=True)
    reduction = importlib.import_module("genomeos.validation.heterogeneity_reduction")
    from heterogeneity_runner_fixtures import dataset
    manifest, admission, null = campaign(tmp_path)
    with LocalB0HStore.create(tmp_path / "study.sqlite3", manifest=manifest, admission=admission,
                              null=null, owner_id="fixture-owner") as store:
        result = runner.execute_b0h_case(manifest, dataset().case_id, store)
    digest = record_digest(manifest)
    cases = tuple(result if case == result.case else CaseEvidence(digest, case, ()) for case in manifest.cases)
    output = reduction.reduce_b0h_study(manifest, cases, RankNullReference(512, null.seed, null.statistics))
    assert output.cases[0].attempt0 == "failed"
    assert output.cases[0].quantities == "not_admitted"
    assert output.ranks[0].failure_status_counts == (("attempt0:failed", 1), ("generation:unstarted", 511))
    assert output.ranks[0].test is None


def test_descriptive_targets_keep_separate_denominators_and_negative_infinity(tmp_path, monkeypatch):
    import struct
    from test_heterogeneity_runner import mocked_runner
    from heterogeneity_runner_fixtures import dataset
    from heterogeneity_codec_fixtures import summary
    from genomeos.validation.heterogeneity_runner_store import LocalB0HStore
    runner, _ = mocked_runner(monkeypatch)
    reduction = importlib.import_module("genomeos.validation.heterogeneity_reduction")
    def fixture_summary(data, *, attempt, cdf_backend):
        return summary(2, 0, data.case_id.track_id, attempt.spec.attempt_id, cdf_backend,
                       "complete" if data.case_id.track_id == 0 else "prediction_failed")
    monkeypatch.setattr(runner, "summarize_heterogeneity_fit", fixture_summary)
    manifest, admission, null = campaign(tmp_path)
    with LocalB0HStore.create(tmp_path / "study.sqlite3", manifest=manifest, admission=admission,
                              null=null, owner_id="fixture-owner") as store:
        left = runner.execute_b0h_case(manifest, dataset(2, 0, 0).case_id, store)
        right = runner.execute_b0h_case(manifest, dataset(2, 0, 1).case_id, store)
    def forbidden(*args, **kwargs):
        raise AssertionError("pure reduction called a scientific stage")
    for name in ("generate_sbc_case", "run_fit_attempt", "selected_sbc_quantities",
                 "summarize_heterogeneity_fit", "exercise_unavailable"):
        monkeypatch.setattr(runner, name, forbidden)
    monkeypatch.setattr(reduction, "test_rank_uniformity", forbidden)
    digest = record_digest(manifest)
    found = {left.case: left, right.case: right}
    cases = tuple(found.get(case, CaseEvidence(digest, case, ())) for case in manifest.cases)
    output = reduction.reduce_b0h_study(manifest, cases, RankNullReference(512, null.seed, null.statistics))
    aggregates = {(r.track_id, r.target_kind, r.metric): r for r in output.aggregates
                  if r.study_id == 2 and r.case_id == 0}
    shared = aggregates[(0, "shared_cluster0", "log_score")]
    fresh = aggregates[(0, "fresh_cluster", "log_score")]
    missing = aggregates[(1, "shared_cluster0", "log_score")]
    assert shared.actual_n == fresh.actual_n == 1
    assert shared.failed_n == shared.planned_n - 1
    assert shared.mean_bits == struct.pack(">d", -float("inf")).hex()
    assert fresh.mean_bits == struct.pack(">d", -2.0).hex()
    assert missing.actual_n == 0 and missing.failed_n == missing.planned_n and missing.mean_bits is None
    assert aggregates[(1, "parameter_mean", "estimate")].actual_n == 1
    assert not output.unconditional_claim_eligible


@pytest.mark.parametrize("metric,bits", [
    ("log_score", "7ff0000000000000"), ("log_score", "7ff8000000000000"),
    ("absolute_error", "fff0000000000000"), ("coverage_50", "3fe0000000000000"),
])
def test_descriptive_records_refuse_invalid_numeric_domains(metric, bits):
    from heterogeneity_runner_fixtures import dataset
    from genomeos.validation.heterogeneity_reduction_records import DescriptiveRow
    with pytest.raises(ValueError):
        DescriptiveRow(case=dataset().case_id, target_kind="fresh_population", metric=metric,
                       value_bits=bits, dependence_label="independent_dataset")


```

Append this literal test to `tests/test_heterogeneity_reduction.py` during Task4
before implementing `study_claim_reasons`. These are synthetic accounting fixtures,
not records asserted to have come from actual scientific calls.

```python
def test_missed_control_owner_loss_and_predictive_failure_have_distinct_meaning(tmp_path):
    reduction = importlib.import_module("genomeos.validation.heterogeneity_reduction")
    from genomeos.validation.heterogeneity_reduction_records import CaseAccounting
    manifest, _, null = campaign(tmp_path)
    reference = RankNullReference(512, 1653499886, null.statistics)
    balanced = (0,) * 103 + (1,) * 103 + (2,) * 102 + (3,) * 102 + (4,) * 102
    accounting = tuple(CaseAccounting(
        case=case, generation="all_unavailable" if case.study_id == 3 else "available",
        structural="expected_refusal" if case.study_id == 3 else "not_admitted",
        attempt0="not_admitted" if case.study_id == 3 else "accepted", attempt1="not_admitted",
        quantities="complete" if case.study_id == 0 else "not_admitted",
        summary="not_admitted" if case.study_id == 3 else "complete",
        accepted_attempt=None if case.study_id == 3 else 0, owner_loss_count=0,
        execution_failure_count=0, unstarted_required_stages=(), unresolved_reasons=(),
    ) for case in manifest.cases)
    ranks = tuple(reduction.rank_reduction(
        track, mode, quantity,
        (0,) * 512 if (mode, quantity) in ((1, 3), (2, 5)) else balanced,
        (), reference,
    ) for track in (0, 1) for mode in range(3) for quantity in range(6))
    assert reduction.study_claim_reasons(accounting, ranks) == ()
    missed = list(ranks)
    missed[9] = reduction.rank_reduction(0, 1, 3, balanced, (), reference)
    assert reduction.study_claim_reasons(accounting, tuple(missed)) == (
        "predeclared_control_sensitivity_limited",)
    for changes in (
        {"summary": "owner_lost", "owner_loss_count": 1},
        {"summary": "prediction_failed"},
        {"summary": "diagnostics_failed"},
    ):
        altered = accounting[0].model_copy(update=changes)
        reasons = reduction.study_claim_reasons((altered,) + accounting[1:], ranks)
        assert reasons == ("unresolved_case_or_required_diagnostic_outcomes",)
        assert "correct_family_discrepancy_detected" not in reasons
```


- [ ] Step 2: Run RED before either reduction production module exists.

```bash
env PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib /private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python -m pytest tests/test_heterogeneity_reduction.py::test_literal_full_n_rank_decisions_and_inclusive_tail -o addopts='' -q
```

Expected: named test fails at absent reduction module. No actual null simulation
is called by this test; the fixed100000-element tuple is a labeled mock null.

- [ ] Step 3: Create `genomeos/validation/heterogeneity_reduction_records.py`.

```python
"""Closed B0H descriptive/reduction outputs (design §§5,7–8,12; runner §6)."""
from __future__ import annotations

import math
import struct

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from genomeos.validation.heterogeneity_runner_records import ClosedRecord, Digest, Natural, Text
from genomeos.validation.heterogeneity_simulation_types import SbcCaseId
from genomeos.validation.sbc_ranks import RankTestResult

Bits = Annotated[str, Field(pattern=r"^[0-9a-f]{16}$")]
CommonStageStatus = Literal["unstarted", "not_admitted", "started_unresolved", "owner_lost", "execution_failed"]
GenerationStatus = CommonStageStatus | Literal["available", "all_unavailable", "generation_failed"]
StructuralStatus = CommonStageStatus | Literal["expected_refusal", "unexpected_exception", "unexpected_return"]
AttemptStatus = CommonStageStatus | Literal["accepted", "convergence_failed", "failed", "identity_rejected"]
QuantityStatus = CommonStageStatus | Literal["complete", "incomplete"]
SummaryStatus = CommonStageStatus | Literal["complete", "prediction_failed", "diagnostics_failed"]
RankFailure = Literal[
    "unstarted", "started_unresolved", "owner_lost", "execution_failed", "not_admitted",
    "generation:unstarted", "generation:started_unresolved", "generation:owner_lost",
    "generation:execution_failed", "generation:generation_failed",
    "attempt0:unstarted", "attempt0:started_unresolved", "attempt0:owner_lost",
    "attempt0:execution_failed", "attempt0:failed", "attempt0:identity_rejected",
    "attempt1:unstarted", "attempt1:started_unresolved", "attempt1:owner_lost",
    "attempt1:execution_failed", "attempt1:failed", "attempt1:identity_rejected",
    "attempt1:convergence_failed", "quantities:unstarted",
    "control_failed", "quantity_failed", "reference_failed", "dependence_reference_unresolved",
    "dependence_rank_order_unresolved", "comparison_failed", "rank_failed",
]
Metric = Literal[
    "estimate", "truth", "absolute_error", "squared_error", "log_score", "randomized_pit",
    "coverage_50", "coverage_80", "coverage_95", "width_50", "width_80", "width_95",
]
Target = Literal["parameter_mean", "parameter_rho", "fresh_population",
                 "shared_cluster0", "fresh_cluster"]


def _metric_value(metric: str, bits: str, *, aggregate: bool) -> None:
    value = struct.unpack(">d", bytes.fromhex(bits))[0]
    if math.isnan(value) or value == math.inf or (value == -math.inf and metric != "log_score"):
        raise ValueError("unsupported nonfinite descriptive value")
    if metric == "log_score":
        if value > 0:
            raise ValueError("log probability mass cannot be positive")
    elif metric in ("estimate", "truth", "randomized_pit") or metric.startswith("coverage_"):
        if not 0 <= value <= 1:
            raise ValueError("descriptive fraction outside [0,1]")
        if metric.startswith("coverage_") and not aggregate and value not in (0.0, 1.0):
            raise ValueError("per-case coverage must be an observed Boolean encoded as binary64")
    elif value < 0:
        raise ValueError("error/width cannot be negative")


class CaseAccounting(ClosedRecord):
    case: SbcCaseId
    generation: GenerationStatus
    structural: StructuralStatus
    attempt0: AttemptStatus
    attempt1: AttemptStatus
    quantities: QuantityStatus
    summary: SummaryStatus
    accepted_attempt: Literal[0, 1] | None
    owner_loss_count: Natural
    execution_failure_count: Natural
    unstarted_required_stages: tuple[Literal["generation", "structural", "fit", "quantities", "summary"], ...]
    unresolved_reasons: tuple[Text, ...]


class RankReduction(ClosedRecord):
    track_id: Literal[0, 1]
    mode_id: Literal[0, 1, 2]
    quantity_id: Literal[0, 1, 2, 3, 4, 5]
    counts: tuple[Natural, Natural, Natural, Natural, Natural]
    actual_n: Annotated[int, Field(ge=0, le=512)]
    missing_n: Annotated[int, Field(ge=0, le=512)]
    failure_status_counts: tuple[tuple[RankFailure, Natural], ...]
    test: RankTestResult | None
    role: Literal["correct_family", "required_control", "other_control"]
    decision: Literal["reject", "not_reject", "uncomputable"]

    @model_validator(mode="after")
    def denominator(self) -> Self:
        role = ("correct_family" if self.mode_id == 0 else "required_control"
                if (self.mode_id, self.quantity_id) in ((1, 3), (2, 5)) else "other_control")
        if self.role != role:
            raise ValueError("rank role differs from frozen declaration")
        names = tuple(name for name, _ in self.failure_status_counts)
        if names != tuple(sorted(set(names))) or any(count == 0 for _, count in self.failure_status_counts):
            raise ValueError("rank failures must be unique ordered nonzero counts")
        if sum(self.counts) != self.actual_n or self.actual_n + self.missing_n != 512:
            raise ValueError("rank denominator mismatch")
        if sum(count for _, count in self.failure_status_counts) != self.missing_n:
            raise ValueError("rank failure denominator mismatch")
        if (self.test is None) != (self.actual_n != 512):
            raise ValueError("only full N512 admits test")
        if self.test is not None and self.test.counts != self.counts:
            raise ValueError("rank test count mismatch")
        expected = "uncomputable" if self.test is None else (
            "reject" if self.test.p_value <= .05 / 12 else "not_reject")
        if self.decision != expected:
            raise ValueError("rank decision differs from fixed threshold")
        return self


class DescriptiveRow(ClosedRecord):
    case: SbcCaseId
    target_kind: Target
    metric: Metric
    value_bits: Bits
    dependence_label: Literal["independent_dataset", "shared_history_paired_tracks",
                              "boundary_degenerate_paired_tracks", "paired_tracks"]

    @model_validator(mode="after")
    def numeric_value(self) -> Self:
        _metric_value(self.metric, self.value_bits, aggregate=False)
        return self


class DescriptiveAggregate(ClosedRecord):
    study_id: Literal[0, 1, 2, 4]
    case_id: Natural
    track_id: Literal[0, 1]
    target_kind: Target
    metric: Metric
    planned_n: Natural
    actual_n: Natural
    failed_n: Natural
    mean_bits: Bits | None

    @model_validator(mode="after")
    def denominator(self) -> Self:
        if self.actual_n + self.failed_n != self.planned_n:
            raise ValueError("descriptive denominator mismatch")
        if (self.mean_bits is None) != (self.actual_n == 0):
            raise ValueError("descriptive mean requires actual observations")
        if self.mean_bits is not None:
            _metric_value(self.metric, self.mean_bits, aggregate=True)
        return self


class StudyReduction(ClosedRecord):
    format: Literal["b0h_reduction"]
    version: Literal["1"]
    campaign_sha256: Digest
    inventory_sha256: Digest
    null_sha256: Digest
    cases: tuple[CaseAccounting, ...]
    planned_initial_fits: Literal[1936]
    planned_retry_slots: Literal[1936]
    completed_fit_calls: Natural
    ambiguous_fit_calls: Natural
    completed_generation_calls: Natural
    completed_structural_calls: Natural
    completed_quantity_calls: Natural
    completed_summary_calls: Natural
    ranks: tuple[RankReduction, ...]
    rows: tuple[DescriptiveRow, ...]
    aggregates: tuple[DescriptiveAggregate, ...]
    correct_family_rejected: bool
    sensitivity_limited: bool
    unconditional_claim_eligible: bool
    claim_reasons: tuple[Text, ...]
    permitted_claim: Literal["no discrepancy detected at this design's resolution"] | None

    @model_validator(mode="after")
    def fixed_sizes(self) -> Self:
        from genomeos.validation.heterogeneity_simulation import enumerate_sbc_cases
        if tuple(case.case for case in self.cases) != enumerate_sbc_cases():
            raise ValueError("reduction requires exact ordered1938 cases")
        expected = tuple((track, mode, quantity) for track in (0, 1)
                         for mode in range(3) for quantity in range(6))
        if tuple((row.track_id, row.mode_id, row.quantity_id) for row in self.ranks) != expected:
            raise ValueError("reduction requires exact ordered36 rank rows")
        rejected = any(row.decision == "reject" for row in self.ranks if row.role == "correct_family")
        limited = any(row.decision != "reject" for row in self.ranks if row.role == "required_control")
        if self.correct_family_rejected != rejected or self.sensitivity_limited != limited:
            raise ValueError("reduction decisions contradict fixed rank roles")
        finished_fit = {"accepted", "convergence_failed", "failed", "identity_rejected", "execution_failed"}
        fit_states = tuple(state for case in self.cases for state in (case.attempt0, case.attempt1))
        if self.completed_fit_calls != sum(state in finished_fit for state in fit_states):
            raise ValueError("completed fit calls contradict case accounting")
        if self.ambiguous_fit_calls != sum(state in ("started_unresolved", "owner_lost") for state in fit_states):
            raise ValueError("ambiguous fit calls contradict case accounting")
        if self.unconditional_claim_eligible != (not self.claim_reasons):
            raise ValueError("claim eligibility contradicts reasons")
        if (self.permitted_claim is not None) != self.unconditional_claim_eligible:
            raise ValueError("claim wording contradicts eligibility")
        return self
```

- [ ] Step 4: Create `genomeos/validation/heterogeneity_reduction.py`.

```python
"""Pure full-study B0H reduction (design §§5,7–8,12; runner §6)."""
from __future__ import annotations

import json
import math
import struct
from collections import Counter, defaultdict

from genomeos.validation.heterogeneity_attempts import FitAttemptResult
from genomeos.validation.heterogeneity_reduction_records import (
    CaseAccounting, DescriptiveAggregate, DescriptiveRow, RankReduction, StudyReduction,
)
from genomeos.validation.heterogeneity_runner_binding import (
    next_stage_key, validate_case_evidence, require_paired_generations,
)
from genomeos.validation.heterogeneity_runner_records import (
    CampaignManifest, CaseEvidence, StoredStage, prepared_null,
)
from genomeos.validation.heterogeneity_runner_wire import record_digest, sha256
from genomeos.validation.heterogeneity_sbc_quantity_types import SelectedSbcQuantities
from genomeos.validation.heterogeneity_summary_types import HeterogeneityFitSummary
from genomeos.validation.sbc_ranks import RankNullReference, test_rank_uniformity


def _bits(value: float) -> str:
    return struct.pack(">d", value).hex()


def _float(bits: str) -> float:
    return struct.unpack(">d", bytes.fromhex(bits))[0]


def _json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=True,
                      allow_nan=False, separators=(",", ":")).encode("ascii")


def rank_reduction(track_id: int, mode_id: int, quantity_id: int,
                   ranks: tuple[int, ...], failures: tuple[str, ...],
                   reference: RankNullReference) -> RankReduction:
    prepared_null(reference)
    if type(ranks) is not tuple or type(failures) is not tuple or len(ranks) + len(failures) != 512:
        raise ValueError("rank reduction requires 512 explicit outcomes")
    if any(type(rank) is not int or rank not in range(5) for rank in ranks):
        raise ValueError("ranks must be exact integers0..4")
    test = test_rank_uniformity(ranks, reference=reference) if len(ranks) == 512 else None
    role = ("correct_family" if mode_id == 0 else "required_control"
            if (mode_id, quantity_id) in ((1, 3), (2, 5)) else "other_control")
    return RankReduction(
        track_id=track_id, mode_id=mode_id, quantity_id=quantity_id,
        counts=tuple(ranks.count(rank) for rank in range(5)), actual_n=len(ranks),
        missing_n=len(failures), failure_status_counts=tuple(sorted(Counter(failures).items())),
        test=test, role=role, decision="uncomputable" if test is None else
        "reject" if test.p_value <= .05 / 12 else "not_reject",
    )


def _status(stage: StoredStage | None) -> str:
    if stage is None:
        return "not_admitted"
    if stage.loss is not None:
        return "owner_lost"
    if stage.completion is None:
        return "started_unresolved"
    if stage.failure is not None:
        return "execution_failed"
    if type(stage.value) is SelectedSbcQuantities:
        return "complete" if stage.value.complete else "incomplete"
    if type(stage.value) is HeterogeneityFitSummary:
        return stage.value.predictive.status
    return stage.value.status


def _account(manifest: CampaignManifest, evidence: CaseEvidence) -> CaseAccounting:
    found = {(s.start.key.stage, s.start.key.attempt_id): s for s in evidence.stages}
    accepted = next((s.value.spec.attempt_id for s in evidence.stages
                     if type(s.value) is FitAttemptResult and s.value.status == "accepted"), None)
    fields = {"generation": _status(found.get(("generation", None))),
              "structural": _status(found.get(("structural", None))),
              "attempt0": _status(found.get(("fit", 0))),
              "attempt1": _status(found.get(("fit", 1))),
              "quantities": _status(found.get(("quantities", accepted))),
              "summary": _status(found.get(("summary", accepted)))}
    upcoming = next_stage_key(manifest, evidence)
    missing = () if upcoming is None else (upcoming.stage,)
    if upcoming is not None:
        name = "attempt" + str(upcoming.attempt_id) if upcoming.stage == "fit" else upcoming.stage
        fields[name] = "unstarted"
    reasons = []
    for name, status in fields.items():
        if status in ("not_admitted", "available", "all_unavailable", "accepted",
                      "expected_refusal", "complete"):
            continue
        if name == "attempt0" and status == "convergence_failed" and accepted == 1:
            continue
        reasons.append(name + ":" + status)
    return CaseAccounting(
        case=evidence.case, **fields, accepted_attempt=accepted,
        owner_loss_count=sum(s.loss is not None for s in evidence.stages),
        execution_failure_count=sum(s.failure is not None for s in evidence.stages),
        unstarted_required_stages=missing, unresolved_reasons=tuple(reasons),
    )


def missing_quantities_reason(account: CaseAccounting) -> str:
    """Name the first actual prerequisite that prevents an absent quantities slot."""
    if account.case.study_id != 0 or account.quantities not in ("not_admitted", "unstarted"):
        raise ValueError("absence attribution requires a prior case with absent quantities")
    if account.generation != "available":
        return "generation:" + account.generation
    if account.accepted_attempt is not None:
        return "quantities:unstarted"
    if account.attempt0 == "convergence_failed":
        return "attempt1:" + account.attempt1
    return "attempt0:" + account.attempt0


def _label(study: int) -> str:
    return {0: "independent_dataset", 1: "paired_tracks",
            2: "shared_history_paired_tracks", 4: "boundary_degenerate_paired_tracks"}[study]


def _metric_keys(case) -> tuple[tuple[str, str], ...]:
    if case.study_id == 3:
        return ()
    shared = ("shared_cluster0", "fresh_cluster") if case.study_id == 2 else ("fresh_population",)
    intervals = ("coverage_50", "coverage_80", "coverage_95", "width_50", "width_80", "width_95")
    parameter = ("estimate", "truth", "absolute_error", "squared_error") + intervals
    predictive = ("log_score", "absolute_error", "squared_error", "randomized_pit") + intervals
    return tuple((target, metric) for target in ("parameter_mean", "parameter_rho") for metric in parameter) + tuple(
        (target, metric) for target in shared for metric in predictive)


def _rows(evidence: CaseEvidence) -> tuple[DescriptiveRow, ...]:
    summary = next((s.value for s in evidence.stages if type(s.value) is HeterogeneityFitSummary), None)
    if summary is None:
        return ()
    result = []
    for target, value in tuple(("parameter_" + p.parameter, p) for p in summary.parameters) + tuple(
            (r.target.kind, r) for r in summary.predictive.rows):
        metrics = [("absolute_error", value.absolute_error), ("squared_error", value.squared_error)]
        if target.startswith("parameter_"):
            metrics.extend((("estimate", value.estimate), ("truth", value.truth)))
        else:
            metrics.extend((("log_score", value.log_score), ("randomized_pit", value.randomized_pit)))
        metrics.extend(("coverage_" + str(level), float(flag)) for level, flag in
                       zip((50, 80, 95), value.coverage, strict=True))
        metrics.extend(("width_" + str(level), width) for level, width in
                       zip((50, 80, 95), value.interval_width, strict=True))
        result.extend(DescriptiveRow(case=evidence.case, target_kind=target, metric=metric,
                                    value_bits=_bits(float(number)), dependence_label=_label(evidence.case.study_id))
                      for metric, number in metrics)
    return tuple(result)


def _aggregates(manifest, rows) -> tuple[DescriptiveAggregate, ...]:
    planned, values = Counter(), defaultdict(list)
    for case in manifest.cases:
        for target, metric in _metric_keys(case):
            planned[(case.study_id, case.case_id, case.track_id, target, metric)] += 1
    for row in rows:
        key = (row.case.study_id, row.case.case_id, row.case.track_id, row.target_kind, row.metric)
        values[key].append(_float(row.value_bits))
    result = []
    for (study, case, track, target, metric), count in sorted(planned.items()):
        observed = values[(study, case, track, target, metric)]
        mean = None
        if observed:
            mean = -math.inf if any(x == -math.inf for x in observed) else math.fsum(
                x / len(observed) for x in observed)
        result.append(DescriptiveAggregate(
            study_id=study, case_id=case, track_id=track, target_kind=target, metric=metric,
            planned_n=count, actual_n=len(observed), failed_n=count - len(observed),
            mean_bits=None if mean is None else _bits(mean)))
    return tuple(result)


def reduce_b0h_study(manifest: CampaignManifest, cases: tuple[CaseEvidence, ...],
                     null_reference: RankNullReference) -> StudyReduction:
    null = prepared_null(null_reference)
    if record_digest(null) != manifest.null_sha256:
        raise ValueError("reduction null differs from prepared campaign null")
    if type(cases) is not tuple or tuple(c.case for c in cases) != manifest.cases:
        raise ValueError("reduction requires exact ordered complete manifest membership")
    for evidence in cases:
        validate_case_evidence(manifest, evidence)
    for index in range(0, len(cases), 2):
        left, right = cases[index:index + 2]
        if left.case.study_id != 0 and left.stages and right.stages:
            require_paired_generations(left.stages[0], right.stages[0])
    inventory = tuple((e.case.canonical_id, tuple(d for s in e.stages for d in (
        record_digest(s.start), None if s.completion is None else record_digest(s.completion),
        None if s.loss is None else record_digest(s.loss)) if d is not None)) for e in cases)
    accounting = tuple(_account(manifest, evidence) for evidence in cases)
    by_case = {account.case: account for account in accounting}
    ranks = []
    for track in (0, 1):
        prior = tuple(e for e in cases if e.case.study_id == 0 and e.case.track_id == track)
        for mode in range(3):
            for quantity in range(6):
                valid, failures = [], []
                for evidence in prior:
                    stage = next((s for s in evidence.stages if s.start.key.stage == "quantities"), None)
                    if stage is None or type(stage.value) is not SelectedSbcQuantities:
                        failures.append(missing_quantities_reason(by_case[evidence.case]) if stage is None else _status(stage))
                    else:
                        entry = stage.value.ranks[mode * 6 + quantity]
                        if entry.status == "ranked":
                            valid.append(entry.rank)
                        else:
                            failures.append(entry.status)
                ranks.append(rank_reduction(track, mode, quantity, tuple(valid), tuple(failures), null_reference))
    rows = tuple(row for evidence in cases for row in _rows(evidence))
    rejected = any(row.decision == "reject" for row in ranks if row.role == "correct_family")
    limited = any(row.decision != "reject" for row in ranks if row.role == "required_control")
    reasons = study_claim_reasons(accounting, tuple(ranks))
    all_stages = tuple(s for e in cases for s in e.stages)
    completed = Counter(s.start.key.stage for s in all_stages if s.completion is not None)
    return StudyReduction(
        format="b0h_reduction", version="1", campaign_sha256=record_digest(manifest),
        inventory_sha256=sha256(_json(inventory)), null_sha256=manifest.null_sha256,
        cases=accounting, planned_initial_fits=1936, planned_retry_slots=1936,
        completed_fit_calls=completed["fit"],
        ambiguous_fit_calls=sum(s.start.key.stage == "fit" and s.completion is None for s in all_stages),
        completed_generation_calls=completed["generation"], completed_structural_calls=completed["structural"],
        completed_quantity_calls=completed["quantities"], completed_summary_calls=completed["summary"],
        ranks=tuple(ranks), rows=rows, aggregates=_aggregates(manifest, rows),
        correct_family_rejected=rejected, sensitivity_limited=limited,
        unconditional_claim_eligible=not reasons, claim_reasons=reasons,
        permitted_claim=None if reasons else "no discrepancy detected at this design's resolution",
    )


def reduction_bytes(value: StudyReduction) -> bytes:
    if type(value) is not StudyReduction:
        raise ValueError("reduction output requires exact StudyReduction root")
    value = StudyReduction.model_validate(value, strict=True)
    if value.claim_reasons != study_claim_reasons(value.cases, value.ranks):
        raise ValueError("reduction claim reasons contradict retained accounting")
    document = value.model_dump(mode="json")
    for target, source in zip(document["ranks"], value.ranks, strict=True):
        if source.test is not None:
            target["test"] = {"counts": list(source.test.counts), "statistic": source.test.statistic,
                              "p_value_bits": _bits(source.test.p_value),
                              "bonferroni_p_value_bits": _bits(source.test.bonferroni_p_value)}
    return _json(document)


def study_claim_reasons(accounting: tuple[CaseAccounting, ...],
                        ranks: tuple[RankReduction, ...]) -> tuple[str, ...]:
    from genomeos.validation.heterogeneity_simulation import enumerate_sbc_cases
    if tuple(row.case for row in accounting) != enumerate_sbc_cases():
        raise ValueError("claim accounting must match all1938 planned identities")
    expected = tuple((track, mode, quantity) for track in (0, 1)
                     for mode in range(3) for quantity in range(6))
    if tuple((r.track_id, r.mode_id, r.quantity_id) for r in ranks) != expected:
        raise ValueError("claim requires all36 ordered rank rows")
    reasons = []
    if any(row.unresolved_reasons or row.owner_loss_count or row.execution_failure_count
           or (row.case.study_id == 3 and row.structural != "expected_refusal")
           or (row.case.study_id != 3 and (row.accepted_attempt is None or row.summary != "complete"))
           or (row.case.study_id == 0 and row.quantities != "complete") for row in accounting):
        reasons.append("unresolved_case_or_required_diagnostic_outcomes")
    if any(row.decision == "uncomputable" for row in ranks):
        reasons.append("incomplete_rank_outcomes")
    if any(row.decision == "reject" for row in ranks if row.role == "correct_family"):
        reasons.append("correct_family_discrepancy_detected")
    if any(row.decision != "reject" for row in ranks if row.role == "required_control"):
        reasons.append("predeclared_control_sensitivity_limited")
    return tuple(reasons)
```

- [ ] Step 5: Run the reducer tests and mandatory smoke. Exact commands:

```bash
env PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib /private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python -m pytest tests/test_heterogeneity_reduction.py -o addopts='' -q
env PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib /private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python scripts/smoke.py
```


- [ ] Verification gate: run the task's focused GREEN, mandatory smoke and static/privacy checks. Record the actual command, exit status and counts in the authorized task report. A failed fixture or adapter check is not permission to alter scientific policy.

```bash
env PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib /private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python -m pytest tests/test_heterogeneity_reduction.py -o addopts='' -q
env PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib /private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python scripts/smoke.py
/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/ruff check .
env PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib /private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python scripts/freeze_contract.py --check
env PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib /private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python scripts/check_module_size.py
git diff --check
git add genomeos/validation/heterogeneity_reduction_records.py genomeos/validation/heterogeneity_reduction.py tests/test_heterogeneity_reduction.py
git diff --cached --name-only
env PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib /private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python scripts/check_private_files.py
```

- [ ] Inspect the staged-path output. It must contain only this task's explicitly owned files above and no SDD/private/generated evidence. Preserve unrelated work. If every check passed and the staged scope is exact, make the task commit; advance #211/#189 without closing either.

```bash
git commit -m "feat: reduce B0H evidence with honest full-study accounting" -m "Advances #211 and #189; neither calibration nor benchmark completion is claimed."
```

## Task 5: Offline admission, preparation, execution and collection

**Files:** Create `genomeos/validation/heterogeneity_runner_admission.py`,
`scripts/run_b0h_calibration.py`, `tests/test_heterogeneity_runner_cli.py`; extend
`genomeos/validation/heterogeneity_runner_store.py` with closed collection,
`genomeos/validation/heterogeneity_runner_reader.py` with read-only collection consumption,
and `genomeos/validation/heterogeneity_runner_records.py` with `CollectedB0HSnapshot`.
Create `docs/research/population-heterogeneity-runner-2026-09-10.md` with the literal scope note below. The product claim is
an operationally usable offline command that records actual runtime/storage
facts before case calls. Acceptance is no scientific call on failed admission,
fixed null preparation, bounded same-packet publication handling and checksummed
closed collection. Actual GPU/platform admission and campaign execution remain
later work, outside implementation tests. No cloud launcher or new scheduler.

**Interfaces:** Consume all preceding public records/functions. Produce the
`observe_b0h_admission(source_root, database_parent)` and `main(argv)` signatures
above, plus `LocalB0HStore.collect(destination: Path) -> tuple[str,str]` returning
database/inventory SHA256 and
`read_collected_b0h_snapshot(directory: Path, *, expected_database_sha256: str,
expected_inventory_sha256: str) -> CollectedB0HSnapshot`. `collect` closes the SQLite connection before copying
and retains its process lock through copying, fsync and checksum comparison.

### Command-only operational timing contract

The command emits JSON Lines to its caller's retained operational report stream.
`b0h_storage_interval` has exactly: `format="b0h_storage_interval"`,
`version="1"`, `operation_sequence` (positive per-process integer),
`owner_id` (actual process-incarnation label),
`phase` (store_open/start_publication/result_publication/closed_collection),
`start_sha256` (START digest for publications, otherwise None),
`interval="before_begin_report_to_store_method_return_or_raise"`,
`started_monotonic_ns` (actual nonnegative integer),
`event` (begin/end), `elapsed_ns` (None or actual nonnegative integer),
`outcome` (unresolved/returned/raised), `exception_class` (None or actual
qualified type), and `unavailable_reason` (None or end_not_observed).
The interval includes its begin-report transport plus the named store method,
excluding the end-report transport. A begin record has unresolved/None/end_not_observed; an end has measured elapsed,
returned or raised, and no unavailable reason. Each same-packet publication
attempt has its own sequence and interval. No interval is an isolated COMMIT,
kernel/I/O, JIT or durability measurement; no overlapping intervals are summed.

The collection hashes/receipt and immutable scientific packets remain unchanged.
Timing stream failure emits the separate closed `b0h_timing_report_unavailable`
record (`format`, `version="1"`, `reason="stdout_write_failed"`) to stderr
when possible; failure of both transports has no fabricated replacement.
Abrupt loss can leave only a begin record, explicitly end-unobserved. No stream
failure discards the live PendingPublication packet or enables science.
`startup_elapsed_ns` measures source checking and GPU-library setup inside
`observe_b0h_admission`, not earlier interpreter/CLI imports; preflight measures
the subsequent actual probes. The accepted cost is potentially unavailable
separate operational timing after abrupt process loss.

- [ ] Step 1: Add these literal tests before the admission or command files exist.

```python
"""Offline command fixtures; no GPU initialization, science or cloud launch."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from heterogeneity_runner_fixtures import campaign
from genomeos.validation.heterogeneity_runner_store import PendingPublication, StoreUnavailable


def command():
    path = Path(__file__).parents[1] / "scripts/run_b0h_calibration.py"
    spec = importlib.util.spec_from_file_location("b0h_cli_fixture", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_help_is_offline(capsys):
    cli = command()
    with pytest.raises(SystemExit) as exited:
        cli.main(["--help"])
    assert exited.value.code == 0
    assert "prepare" in capsys.readouterr().out


def test_pending_publication_retries_same_packet_only(tmp_path, monkeypatch):
    cli = command()
    from heterogeneity_runner_fixtures import dataset
    from test_heterogeneity_runner_store import packet as make_packet, start_record
    manifest, admission, null = campaign(tmp_path)
    data = dataset()
    packet = make_packet(manifest, start_record(manifest, data), data)
    pending = PendingPublication(packet, StoreUnavailable("synthetic unavailable store"))
    observed = []
    class Store:
        def publish_pending(self, received):
            observed.append(received)
            if len(observed) < 3:
                raise PendingPublication(received, StoreUnavailable("synthetic unavailable store"))
    elapsed = [0]
    monkeypatch.setattr(cli.time, "monotonic", lambda: elapsed[0])
    monkeypatch.setattr(cli.time, "sleep", lambda seconds: elapsed.__setitem__(0, elapsed[0] + seconds))
    cli.reconcile_publication(Store(), pending)
    assert observed == [packet, packet, packet]
    assert all(value is packet for value in observed)
    assert elapsed[0] == 180


def test_pending_expiry_keeps_packet_and_raises(tmp_path, monkeypatch):
    cli = command()
    from heterogeneity_runner_fixtures import dataset
    from test_heterogeneity_runner_store import packet as make_packet, start_record
    manifest, admission, null = campaign(tmp_path)
    data = dataset()
    packet = make_packet(manifest, start_record(manifest, data), data)
    pending = PendingPublication(packet, StoreUnavailable("synthetic unavailable store"))
    observed = []
    class Store:
        def publish_pending(self, received):
            observed.append(received)
            raise PendingPublication(received, StoreUnavailable("synthetic unavailable store"))
    elapsed = [0]
    monkeypatch.setattr(cli.time, "monotonic", lambda: elapsed[0])
    monkeypatch.setattr(cli.time, "sleep", lambda seconds: elapsed.__setitem__(0, elapsed[0] + seconds))
    with pytest.raises(PendingPublication) as failed:
        cli.reconcile_publication(Store(), pending)
    assert failed.value.packet is packet
    assert elapsed[0] == 1800
    assert len(observed) == 29


def test_failed_admission_makes_no_null_or_case_call(tmp_path, monkeypatch):
    cli = command()
    observed = []
    def refused(*args, **kwargs):
        observed.append("actual-admission-boundary")
        raise ValueError("literal runtime mismatch")
    def forbidden(*args, **kwargs):
        raise AssertionError("science invoked after admission refusal")
    monkeypatch.setattr(cli, "observe_b0h_admission", refused)
    monkeypatch.setattr(cli, "simulate_rank_null", forbidden)
    monkeypatch.setattr(cli, "execute_b0h_case", forbidden)
    source_root = Path(cli.__file__).resolve().parents[1]
    assert cli.main(["admit", "--source-root", str(source_root), "--database-parent", str(tmp_path),
                     "--out", str(tmp_path / "admission.json")]) == 2
    assert observed == ["actual-admission-boundary"]
    assert not (tmp_path / "admission.json").exists()
def test_imported_entrypoints_refuse_wrong_checkout(tmp_path):
    from genomeos.validation.heterogeneity_runner_admission import require_execution_source
    with pytest.raises(ValueError, match="differs from attested source_root"):
        require_execution_source(tmp_path)


def test_command_refuses_wrong_checkout_before_admission(tmp_path, monkeypatch, capsys):
    cli = command()
    def forbidden(*args, **kwargs):
        raise AssertionError("admission/science ran for wrong command root")
    monkeypatch.setattr(cli, "observe_b0h_admission", forbidden)
    monkeypatch.setattr(cli, "simulate_rank_null", forbidden)
    monkeypatch.setattr(cli, "execute_b0h_case", forbidden)
    assert cli.main(["admit", "--source-root", str(tmp_path), "--database-parent", str(tmp_path),
                     "--out", str(tmp_path / "admission.json")]) == 2
    assert "adapter_refusal" in capsys.readouterr().err


def collection_fixture(tmp_path):
    import json
    from genomeos.validation.heterogeneity_runner_store import LocalB0HStore
    execution = tmp_path / "execution"
    execution.mkdir()
    manifest, admission, null = campaign(execution)
    destination = tmp_path / "collection"
    with LocalB0HStore.create(execution / "study.sqlite3", manifest=manifest,
                              admission=admission, null=null, owner_id="fixture-owner") as store:
        database_digest, inventory_digest = store.collect(destination)
    receipt = {"format": "b0h_collection", "version": "1",
               "database_sha256": database_digest, "inventory_sha256": inventory_digest}
    command().frozen_file(destination / "collection.json", json.dumps(receipt, sort_keys=True,
                         separators=(",", ":")).encode("ascii"))
    return destination, database_digest, inventory_digest, manifest, null


def test_collected_snapshot_reads_elsewhere_without_execution_authority(tmp_path, monkeypatch):
    import shutil
    import genomeos.validation.heterogeneity_runner_reader as reader_module
    from genomeos.validation.heterogeneity_runner_store import LocalB0HStore, StoreIntegrityError
    from genomeos.validation.heterogeneity_reduction import reduce_b0h_study, reduction_bytes
    from genomeos.validation.heterogeneity_runner_records import restore_null
    destination, database_digest, inventory_digest, manifest, null = collection_fixture(tmp_path)
    copied = tmp_path / "copied_elsewhere"
    shutil.copytree(destination, copied)
    before = {path.name: path.read_bytes() for path in copied.iterdir()}
    connection_modes = []
    original_connect = reader_module.sqlite3.connect
    def observed_connect(uri, **kwargs):
        connection_modes.append((uri, kwargs))
        return original_connect(uri, **kwargs)
    def forbidden(*args, **kwargs):
        raise AssertionError("collected reader attempted execution authority")
    monkeypatch.setattr(reader_module.sqlite3, "connect", observed_connect)
    monkeypatch.setattr(LocalB0HStore, "__enter__", forbidden)
    cli = command()
    monkeypatch.setattr(cli, "simulate_rank_null", forbidden)
    monkeypatch.setattr(cli, "execute_b0h_case", forbidden)
    snapshot = reader_module.read_collected_b0h_snapshot(copied,
        expected_database_sha256=database_digest, expected_inventory_sha256=inventory_digest)
    assert snapshot.manifest == manifest and snapshot.null == null
    assert tuple(case.case for case in snapshot.cases) == manifest.cases
    assert len(snapshot.cases) == 1938 and all(case.stages == () for case in snapshot.cases)
    assert connection_modes[0][0].endswith("?mode=ro")
    assert connection_modes[0][1]["uri"] is True and "immutable" not in connection_modes[0][0]
    assert {path.name: path.read_bytes() for path in copied.iterdir()} == before
    first = reduce_b0h_study(snapshot.manifest, snapshot.cases, restore_null(snapshot.null))
    second = reduce_b0h_study(snapshot.manifest, snapshot.cases, restore_null(snapshot.null))
    assert reduction_bytes(first) == reduction_bytes(second)
    with pytest.raises(StoreIntegrityError, match="filesystem differs"):
        LocalB0HStore(copied / "study.sqlite3", manifest=manifest,
                      admission=campaign(tmp_path / "execution")[1], null=null, owner_id="new-owner")


@pytest.mark.parametrize("changed", ["expected_database", "expected_inventory", "receipt", "inventory",
                                      "database", "journal", "wal", "shm"])
def test_collected_snapshot_refuses_checksum_or_sidecar_drift(tmp_path, changed):
    from genomeos.validation.heterogeneity_runner_reader import read_collected_b0h_snapshot, StoreIntegrityError
    destination, database_digest, inventory_digest, manifest, null = collection_fixture(tmp_path)
    if changed == "expected_database":
        database_digest = "0" * 64
    elif changed == "expected_inventory":
        inventory_digest = "0" * 64
    elif changed in ("receipt", "inventory"):
        name = "collection.json" if changed == "receipt" else "inventory.json"
        path = destination / name
        path.write_bytes(path.read_bytes() + b" ")
    elif changed == "database":
        with (destination / "study.sqlite3").open("ab") as stream:
            stream.write(b"literal corrupt trailing bytes")
    else:
        suffix = {"journal": "-journal", "wal": "-wal", "shm": "-shm"}[changed]
        (destination / ("study.sqlite3" + suffix)).write_bytes(b"")
    with pytest.raises(StoreIntegrityError):
        read_collected_b0h_snapshot(destination, expected_database_sha256=database_digest,
                                    expected_inventory_sha256=inventory_digest)


def test_command_storage_timing_is_outside_immutable_packet(tmp_path, monkeypatch, capsys):
    import json
    from heterogeneity_runner_fixtures import dataset
    from test_heterogeneity_runner_store import packet, start_record, publish
    cli = command()
    manifest, admission, null = campaign(tmp_path)
    data = dataset()
    start = start_record(manifest, data)
    retained = packet(manifest, start, data)
    elapsed = [0]
    monkeypatch.setattr(cli.time, "monotonic_ns", lambda: elapsed[0])
    with cli._TimedStore.create(tmp_path / "study.sqlite3", manifest=manifest,
                                admission=admission, null=null, owner_id="fixture-owner") as store:
        original = store._commit
        def observed_commit():
            elapsed[0] += 11
            original()
        monkeypatch.setattr(store, "_commit", observed_commit)
        store.start(start)
        publish(store, retained)
        stage, = store.stages(data.case_id)
        assert stage.completion == retained.completion
        assert stage.completion.whole_call_elapsed_ns == 7
    reports = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    publication = [row for row in reports if row["phase"] == "result_publication"]
    assert publication[0]["elapsed_ns"] is None
    assert publication[0]["unavailable_reason"] == "end_not_observed"
    assert publication[1]["elapsed_ns"] == 11
    assert publication[1]["interval"] == "before_begin_report_to_store_method_return_or_raise"
    assert publication[1]["outcome"] == "returned"
    assert publication[1]["unavailable_reason"] is None


def test_failed_null_preparation_publishes_no_campaign_and_calls_no_case(tmp_path, monkeypatch):
    from genomeos.validation.heterogeneity_runner_wire import runner_record_bytes
    cli = command()
    manifest, admission, null = campaign(tmp_path)
    admission_path = tmp_path / "admission.json"
    admission_path.write_bytes(runner_record_bytes(admission))
    observed = []
    monkeypatch.setattr(cli, "observe_b0h_admission", lambda *args: admission)
    def failed_null(**kwargs):
        observed.append(kwargs)
        raise ValueError("literal null preparation failure")
    def forbidden(*args, **kwargs):
        raise AssertionError("case science ran after failed null preparation")
    monkeypatch.setattr(cli, "simulate_rank_null", failed_null)
    monkeypatch.setattr(cli, "execute_b0h_case", forbidden)
    source_root = Path(cli.__file__).resolve().parents[1]
    assert cli.main(["prepare", "--source-root", str(source_root),
        "--admission", str(admission_path), "--null", str(tmp_path / "null.json"),
        "--manifest", str(tmp_path / "manifest.json"), "--worker-id", "worker0",
        "--max-metadata-bytes", "1048576", "--max-payload-bytes", "16777216"]) == 2
    assert observed == [{"sample_size": 512, "replicates": 100000, "seed": 1653499886}]
    assert not (tmp_path / "null.json").exists()
    assert not (tmp_path / "manifest.json").exists()
    assert not (tmp_path / "study.sqlite3").exists()


```

- [ ] Step 2: Run RED before command/admission implementation.

```bash
env PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib /private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python -m pytest tests/test_heterogeneity_runner_cli.py::test_help_is_offline -o addopts='' -q
```

Expected: named test fails because command file is absent, not because a GPU or
package import is attempted. No actual admission test is run in this unit.

- [ ] Step 3: Create `genomeos/validation/heterogeneity_runner_admission.py`.

```python
"""Observed offline B0H platform admission (design §§5,7–8,12; runner §8)."""
from __future__ import annotations

import fcntl
import importlib.metadata
import inspect
import json
import os
import platform
import resource
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from genomeos.validation.heterogeneity_runner_records import (
    AdmissionReceipt, RuntimeIdentity, SourceIdentity, StorageAdmission,
)
from genomeos.validation.heterogeneity_runner_wire import sha256


def _json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=True,
                      separators=(",", ":")).encode("ascii")


def _git(root: Path, *arguments: str) -> bytes:
    return subprocess.run(["git", "-C", str(root), *arguments], check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout


def _source(root: Path) -> SourceIdentity:
    require_execution_source(root)
    paths = ("genomeos", "scripts", "pyproject.toml", "requirements.lock")
    if _git(root, "status", "--porcelain", "--untracked-files=all", "--", *paths):
        raise ValueError("source/runtime files must match reviewed committed revision")
    revision = _git(root, "rev-parse", "HEAD").decode("ascii").strip()
    names = _git(root, "ls-files", "-z", "--", *paths).split(b"\0")
    entries = []
    for name in sorted(name for name in names if name):
        path = root / name.decode("utf-8")
        if path.is_symlink() or not path.is_file():
            raise ValueError("source path is not a regular file")
        entries.append((name.hex(), sha256(path.read_bytes())))
    return SourceIdentity(revision=revision, content_sha256=sha256(_json(entries)),
                          lock_sha256=sha256((root / "requirements.lock").read_bytes()))


def require_execution_source(root: Path) -> None:
    from genomeos.validation import heterogeneity_simulation, heterogeneity_attempts
    from genomeos.validation import heterogeneity_sbc_quantities, heterogeneity_summaries
    from genomeos.validation import heterogeneity_codec, heterogeneity_runner, sbc_ranks
    from genomeos.surfaces import reference_heterogeneity
    functions = (
        (heterogeneity_simulation.generate_sbc_case, "genomeos/validation/heterogeneity_simulation.py"),
        (heterogeneity_attempts.run_fit_attempt, "genomeos/validation/heterogeneity_attempts.py"),
        (heterogeneity_attempts.exercise_unavailable, "genomeos/validation/heterogeneity_attempts.py"),
        (heterogeneity_sbc_quantities.selected_sbc_quantities, "genomeos/validation/heterogeneity_sbc_quantities.py"),
        (heterogeneity_summaries.summarize_heterogeneity_fit, "genomeos/validation/heterogeneity_summaries.py"),
        (heterogeneity_codec.encode_b0h_evidence, "genomeos/validation/heterogeneity_codec.py"),
        (heterogeneity_codec.decode_b0h_evidence, "genomeos/validation/heterogeneity_codec.py"),
        (heterogeneity_runner.execute_b0h_case, "genomeos/validation/heterogeneity_runner.py"),
        (sbc_ranks.simulate_rank_null, "genomeos/validation/sbc_ranks.py"),
        (reference_heterogeneity.fit_reference_population_heterogeneity, "genomeos/surfaces/reference_heterogeneity.py"),
        (reference_heterogeneity.predict_reference_population_heterogeneity, "genomeos/surfaces/reference_heterogeneity.py"),
    )
    for function, relative in functions:
        actual = inspect.getsourcefile(function)
        if actual is None or Path(actual).resolve() != (root / relative).resolve():
            raise ValueError("imported public entrypoint differs from attested source_root: " + relative)
    if Path(__file__).resolve() != (root / "genomeos/validation/heterogeneity_runner_admission.py").resolve():
        raise ValueError("admission adapter differs from attested source_root")


def _mount(parent: Path) -> tuple[str, str]:
    if sys.platform != "linux":
        raise ValueError("actual GPU campaign storage admission requires Linux mount evidence")
    found = []
    for line in Path("/proc/self/mountinfo").read_text().splitlines():
        parts = line.split()
        divider = parts.index("-")
        mount = parts[4]
        for encoded, literal in (("\\040", " "), ("\\011", "\t"), ("\\012", "\n"), ("\\134", "\\")):
            mount = mount.replace(encoded, literal)
        if parent == Path(mount) or Path(mount) in parent.parents:
            found.append((len(mount), parts[divider + 1], parts[5] + "," + parts[divider + 3]))
    if not found:
        raise ValueError("cannot establish actual filesystem mount")
    _, kind, options = max(found)
    if kind not in ("ext4", "xfs", "btrfs", "tmpfs"):
        raise ValueError("local filesystem backing not established for " + kind)
    return kind, options


def _storage(parent: Path) -> StorageAdmission:
    parent = parent.resolve(strict=True)
    kind, options = _mount(parent)
    with tempfile.TemporaryDirectory(prefix="b0h-admission-", dir=parent) as temporary:
        probe = Path(temporary)
        lockpath = probe / "exclusion.lock"
        with lockpath.open("xb") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            child = subprocess.run([
                sys.executable, "-c",
                "import fcntl,sys\nf=open(sys.argv[1],'rb')\n"
                "try:\n fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)\n"
                "except BlockingIOError:\n sys.exit(0)\nsys.exit(1)\n", str(lockpath),
            ], check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if child.returncode != 0:
                raise ValueError("cross-process exclusion probe failed")
        database = probe / "proof.sqlite3"
        connection = sqlite3.connect(database, isolation_level=None)
        try:
            connection.execute("PRAGMA journal_mode=DELETE")
            connection.execute("PRAGMA synchronous=EXTRA")
            connection.execute("PRAGMA foreign_keys=ON")
            settings = tuple(connection.execute("PRAGMA " + name).fetchone()[0]
                             for name in ("journal_mode", "synchronous", "foreign_keys"))
            if settings != ("delete", 3, 1):
                raise ValueError("SQLite admission setting mismatch")
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("CREATE TABLE proof(value BLOB NOT NULL)")
            connection.execute("INSERT INTO proof VALUES(?)", (b"committed",))
            connection.execute("COMMIT")
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("INSERT INTO proof VALUES(?)", (b"rolled_back",))
            connection.execute("ROLLBACK")
        finally:
            connection.close()
        with sqlite3.connect(database) as restored:
            if restored.execute("SELECT value FROM proof").fetchall() != [(b"committed",)]:
                raise ValueError("SQLite commit/rollback readback probe failed")
        descriptor = os.open(probe, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        digest = sha256(_json({"version": "1", "settings": settings,
                               "exclusive_lock": True, "commit_readback": True,
                               "rollback": True, "directory_fsync": True}))
    return StorageAdmission(
        database_parent=str(parent), device_id=parent.stat().st_dev,
        mount_type=kind, mount_options=options, free_bytes=shutil.disk_usage(parent).free,
        probe_sha256=digest, exclusive_lock_observed=True, rollback_observed=True,
        commit_readback_observed=True, directory_fsync_observed=True,
    )


def observe_b0h_admission(source_root: Path, database_parent: Path) -> AdmissionReceipt:
    start = time.monotonic_ns()
    source = _source(source_root.resolve(strict=True))
    import cupy as cp
    import jax
    import jax.numpy as jnp
    startup = time.monotonic_ns() - start
    preflight = time.monotonic_ns()
    devices = jax.devices()
    if len(devices) != 1 or devices[0].platform != "gpu" or cp.cuda.runtime.getDeviceCount() != 1:
        raise ValueError("admission requires exactly one visible GPU in JAX and CuPy")
    jax_probe = jnp.asarray([1.0], dtype=jnp.float64)
    jax_probe.block_until_ready()
    cupy_probe = cp.asarray([1.0], dtype=cp.float64)
    cp.cuda.get_current_stream().synchronize()
    if str(jax_probe.dtype) != "float64" or str(cupy_probe.dtype) != "float64":
        raise ValueError("actual JAX/CuPy float64 probes failed")
    versions = sorted((distribution.metadata["Name"], distribution.version)
                      for distribution in importlib.metadata.distributions())
    settings = tuple((name, os.environ.get(name)) for name in (
        "JAX_PLATFORMS", "JAX_ENABLE_X64", "XLA_PYTHON_CLIENT_PREALLOCATE",
        "CUDA_VISIBLE_DEVICES", "PYTENSOR_FLAGS"))
    driver = subprocess.run(["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
                            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.decode().strip()
    device_name = cp.cuda.runtime.getDeviceProperties(0)["name"]
    if type(device_name) is bytes:
        device_name = device_name.decode("utf-8")
    runtime = RuntimeIdentity(
        python_version=platform.python_version(), platform=platform.platform(), machine=platform.machine(),
        environment_sha256=sha256(_json((versions, settings))), jax_version=jax.__version__,
        cupy_version=cp.__version__, jax_device=str(devices[0]), cupy_device=device_name,
        driver_version=driver, jax_float64=True, cupy_float64=True,
    )
    storage = _storage(database_parent)
    free, total = cp.cuda.runtime.memGetInfo()
    return AdmissionReceipt(
        format="b0h_admission", version="1", source=source, runtime=runtime, storage=storage,
        observed_unix_ns=time.time_ns(), startup_elapsed_ns=startup,
        preflight_elapsed_ns=time.monotonic_ns() - preflight, device_total_bytes=int(total),
        device_free_bytes=int(free), process_peak_rss_bytes=int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) * 1024,
        memory_observation_label="post_preflight_device_free_and_process_high_water_not_campaign_peak",
    )
```

The probe demonstrates only the operations actually performed on the observed
mount. It is not a crash/power/Pod-loss certificate. The initial local-mount
allowlist is ext4/xfs/btrfs/tmpfs. Tmpfs is volatile. No filesystem name establishes
host/Pod/power-loss durability. Overlay/fuse/network mounts are refused because
local backing is unverified by this probe, not because GPU capacity is unavailable.
Root accepted the cost: an otherwise usable container mount may require a separate
backing-filesystem investigation and reviewed pre-case admission correction.
Actual platform inspection still precedes science; no automatic fallback is implied.

- [ ] Step 4: Add `collect` to `LocalB0HStore` and add the
shown standard-library imports. These are public methods, so the CLI never
reaches into store connections or lock descriptors.

```python
import hashlib
import json
import shutil

    def collect(self, destination: Path) -> tuple[str, str]:
        self._require_open()
        inventory = self.inventory()
        inventory_bytes = json.dumps(inventory, sort_keys=True, separators=(",", ":")).encode("ascii")
        self._db.close()
        self._db = None
        destination.mkdir(parents=False, exist_ok=False)
        target = destination / "study.sqlite3"
        shutil.copyfile(self.database, target)
        with target.open("rb") as copied:
            os.fsync(copied.fileno())
        def digest(path):
            with path.open("rb") as stream:
                return hashlib.file_digest(stream, "sha256").hexdigest()
        source_digest, copied_digest = digest(self.database), digest(target)
        if source_digest != copied_digest:
            raise StoreIntegrityError("closed database collection checksum mismatch")
        with (destination / "inventory.json").open("xb") as stream:
            stream.write(inventory_bytes)
            stream.flush()
            os.fsync(stream.fileno())
        descriptor = os.open(destination, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return source_digest, sha256(inventory_bytes)
```

- [ ] Step 4b: Add this immutable input snapshot to `heterogeneity_runner_records.py`. The constructor checks the raw in-memory root/tuple/digest domains; the reader performs all cross-record and scientific binding validation before return.

```python
@dataclass(frozen=True)
class CollectedB0HSnapshot:
    manifest: CampaignManifest
    null: PreparedNull
    cases: tuple[CaseEvidence, ...]
    database_sha256: str
    inventory_sha256: str

    def __post_init__(self) -> None:
        if type(self.manifest) is not CampaignManifest or type(self.null) is not PreparedNull:
            raise ValueError("snapshot root type mismatch")
        if type(self.cases) is not tuple or any(type(case) is not CaseEvidence for case in self.cases):
            raise ValueError("snapshot cases must be immutable exact records")
        for digest in (self.database_sha256, self.inventory_sha256):
            if type(digest) is not str or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                raise ValueError("snapshot digest must be lowercase SHA256")
```

- [ ] Step 4c: Append this complete function to `heterogeneity_runner_reader.py`, with the shown imports at its module top. The expected digests must be retained independently when collecting and explicitly supplied by the evidence consumer. No original parent/device check is relaxed on the execution adapter. The only SQL here is SELECT, PRAGMA read checks, BEGIN and COMMIT; there is no execution lock, START, loss, receipt write or scientific call. Use `mode=ro`, never `immutable=1`.

```python
import hashlib
import json
from pathlib import Path
from urllib.parse import quote

from genomeos.validation.heterogeneity_runner_records import CaseEvidence, CollectedB0HSnapshot


def read_collected_b0h_snapshot(directory: Path, *, expected_database_sha256: str,
                               expected_inventory_sha256: str) -> CollectedB0HSnapshot:
    from genomeos.validation.heterogeneity_runner_binding import (
        require_paired_generations, validate_case_evidence,
    )
    for digest in (expected_database_sha256, expected_inventory_sha256):
        if type(digest) is not str or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise StoreIntegrityError("explicit lowercase expected SHA256 required")
    database = directory / "study.sqlite3"
    inventory_path = directory / "inventory.json"
    receipt_path = directory / "collection.json"
    def require_closed_files():
        if directory.is_symlink() or not directory.is_dir():
            raise StoreIntegrityError("collection directory missing or symlink")
        for path in (database, inventory_path, receipt_path):
            if path.is_symlink() or not path.is_file():
                raise StoreIntegrityError("collection file missing or symlink")
        for suffix in ("-journal", "-wal", "-shm"):
            path = database.with_name(database.name + suffix)
            if path.exists() or path.is_symlink():
                raise StoreIntegrityError("collected database has unexpected journal/WAL sidecar")
    def database_digest():
        with database.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()
    def canonical(value):
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("ascii")
    require_closed_files()
    expected_receipt = canonical({
        "format": "b0h_collection", "version": "1",
        "database_sha256": expected_database_sha256,
        "inventory_sha256": expected_inventory_sha256,
    })
    inventory_bytes = inventory_path.read_bytes()
    if receipt_path.read_bytes() != expected_receipt or sha256(inventory_bytes) != expected_inventory_sha256:
        raise StoreIntegrityError("collection receipt/inventory differs from externally retained digests")
    if database_digest() != expected_database_sha256:
        raise StoreIntegrityError("collected database differs from externally retained digest")
    connection = sqlite3.connect("file:" + quote(str(database.resolve())) + "?mode=ro",
                                 uri=True, isolation_level=None)
    try:
        connection.execute("BEGIN")
        campaign = connection.execute("SELECT singleton,manifest,admission,null_reference FROM campaign").fetchall()
        if len(campaign) != 1 or campaign[0][0] != 1:
            raise StoreIntegrityError("collected campaign cardinality mismatch")
        roots = []
        for digest, cls in zip(campaign[0][1:], (CampaignManifest, AdmissionReceipt, PreparedNull), strict=True):
            row = connection.execute("SELECT kind,body FROM objects WHERE digest=?", (digest,)).fetchone()
            if row is None or type(row[1]) is not bytes or sha256(row[1]) != digest:
                raise StoreIntegrityError("collected campaign root missing/corrupt")
            value = read_runner_record(row[1])
            if type(value) is not cls or value.format != row[0]:
                raise StoreIntegrityError("collected campaign root type mismatch")
            roots.append(value)
        manifest, admission, null = roots
        if (record_digest(admission) != manifest.admission_sha256
                or record_digest(null) != manifest.null_sha256
                or admission.source != manifest.source or admission.runtime != manifest.runtime):
            raise StoreIntegrityError("collected admission/null binding mismatch")
        reader = B0HSqlReader(connection, manifest=manifest, admission=admission, null=null)
        inventory = reader.inventory()  # One whole-store audit in this stable snapshot.
        if canonical(inventory) != inventory_bytes:
            raise StoreIntegrityError("collected inventory differs from exact database records")
        cases = tuple(CaseEvidence(reader.campaign_sha256, case, reader.stages(case))
                      for case in manifest.cases)
        for case in cases:
            validate_case_evidence(manifest, case)
        indexed = {case.case: case for case in cases}
        for case in cases:
            if case.case.study_id != 0 and case.case.track_id == 0:
                paired = SbcCaseId(1, case.case.study_id, case.case.case_id, case.case.replicate_id)
                right = indexed[paired]
                if case.stages and right.stages:
                    require_paired_generations(case.stages[0], right.stages[0])
        require_closed_files()
        if (database_digest() != expected_database_sha256
                or inventory_path.read_bytes() != inventory_bytes
                or receipt_path.read_bytes() != expected_receipt):
            raise StoreIntegrityError("collection changed during read transaction")
        connection.execute("COMMIT")
        return CollectedB0HSnapshot(manifest, null, cases, expected_database_sha256,
                                    expected_inventory_sha256)
    finally:
        connection.close()
```

- [ ] Step 5: Create `scripts/run_b0h_calibration.py` with this complete code.

```python
"""Offline B0H admit/prepare/run/reduce/collect (design §§5,7–8,12; runner §§4–8)."""
from __future__ import annotations

import argparse
from collections.abc import Sequence
import json
import os
import sys
import time
import uuid
from pathlib import Path

from genomeos.validation.heterogeneity_codec import B0HCodecLimits, EncodedB0HEvidence
from genomeos.validation.heterogeneity_reduction import reduce_b0h_study, reduction_bytes
from genomeos.validation.heterogeneity_runner import execute_b0h_case, load_b0h_case
from genomeos.validation.heterogeneity_runner_admission import observe_b0h_admission
from genomeos.validation.heterogeneity_runner_reader import read_collected_b0h_snapshot
from genomeos.validation.heterogeneity_runner_records import (
    AdmissionReceipt, CampaignManifest, EvidenceReceipt, PreparedNull,
    StageCompletion, StageExecutionFailure, StageStart, prepared_null, restore_null,
)
from genomeos.validation.heterogeneity_runner_store import LocalB0HStore, PendingPublication
from genomeos.validation.heterogeneity_runner_wire import build_manifest, read_runner_record, record_digest, runner_record_bytes, sha256
from genomeos.validation.sbc_ranks import simulate_rank_null


def _emit_timing(record: dict) -> None:
    try:
        print(json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False), flush=True)
    except OSError:
        # Operational report transport can fail without discarding PendingPublication.
        # No synthetic duration or durable-report claim replaces the unavailable stream.
        try:
            print(json.dumps({"format": "b0h_timing_report_unavailable", "version": "1",
                              "reason": "stdout_write_failed"}, sort_keys=True,
                             separators=(",", ":")), file=sys.stderr, flush=True)
        except OSError:
            pass


class _TimedStore(LocalB0HStore):
    """CLI-only observed storage-method intervals, never part of scientific packets."""

    _operation_sequence = 0

    def _observe(self, phase, start_sha256, call):
        self._operation_sequence += 1
        sequence = self._operation_sequence
        started = time.monotonic_ns()
        def report(event, elapsed, outcome, exception_class, unavailable_reason):
            _emit_timing({
                "format": "b0h_storage_interval", "version": "1",
                "operation_sequence": sequence, "owner_id": self.owner_id, "phase": phase,
                "start_sha256": start_sha256,
                "interval": "before_begin_report_to_store_method_return_or_raise",
                "started_monotonic_ns": started, "event": event,
                "elapsed_ns": elapsed, "outcome": outcome,
                "exception_class": exception_class, "unavailable_reason": unavailable_reason,
            })
        report("begin", None, "unresolved", None, "end_not_observed")
        try:
            value = call()
        except BaseException as error:
            report("end", time.monotonic_ns() - started, "raised",
                   type(error).__module__ + "." + type(error).__qualname__, None)
            raise
        report("end", time.monotonic_ns() - started, "returned", None, None)
        return value

    def __enter__(self) -> _TimedStore:
        return self._observe("store_open", None, super().__enter__)

    def start(self, record: StageStart) -> None:
        method = super().start
        self._observe("start_publication", record_digest(record), lambda: method(record))

    def complete(self, start: StageStart, completion: StageCompletion, *,
                 receipt: EvidenceReceipt | None, encoded: EncodedB0HEvidence | None,
                 failure: StageExecutionFailure | None) -> None:
        method = super().complete
        self._observe("result_publication", record_digest(start), lambda: method(
            start, completion, receipt=receipt, encoded=encoded, failure=failure))

    def collect(self, destination: Path) -> tuple[str, str]:
        method = super().collect
        return self._observe("closed_collection", None, lambda: method(destination))


def frozen_file(path: Path, raw: bytes) -> None:
    if path.exists():
        if path.is_symlink() or path.read_bytes() != raw:
            raise ValueError("immutable output conflict: " + str(path))
        return
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def read_record(path: Path, cls):
    value = read_runner_record(path.read_bytes())
    if type(value) is not cls:
        raise ValueError("wrong input root: " + str(path))
    return value


def reconcile_publication(store: LocalB0HStore, pending: PendingPublication) -> None:
    packet = pending.packet
    origin = time.monotonic()
    while time.monotonic() - origin < 1800:
        remaining = 1800 - (time.monotonic() - origin)
        if remaining <= 0:
            break
        time.sleep(min(60, remaining))
        if time.monotonic() - origin >= 1800:
            break
        try:
            store.publish_pending(packet)
        except PendingPublication as still_pending:
            if still_pending.packet != packet:
                raise ValueError("publication retry changed retained packet") from still_pending
        else:
            return
    raise pending


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline frozen B0H campaign")
    commands = parser.add_subparsers(dest="command", required=True)
    admit = commands.add_parser("admit")
    admit.add_argument("--source-root", type=Path, required=True)
    admit.add_argument("--database-parent", type=Path, required=True)
    admit.add_argument("--out", type=Path, required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--admission", type=Path, required=True)
    prepare.add_argument("--source-root", type=Path, required=True)
    prepare.add_argument("--null", type=Path, required=True)
    prepare.add_argument("--manifest", type=Path, required=True)
    prepare.add_argument("--worker-id", required=True)
    prepare.add_argument("--max-metadata-bytes", type=int, required=True)
    prepare.add_argument("--max-payload-bytes", type=int, required=True)
    reduce = commands.add_parser("reduce")
    reduce.add_argument("--collection", type=Path, required=True)
    reduce.add_argument("--expected-database-sha256", required=True)
    reduce.add_argument("--expected-inventory-sha256", required=True)
    reduce.add_argument("--out", type=Path, required=True)
    for name in ("run", "collect"):
        child = commands.add_parser(name)
        child.add_argument("--admission", type=Path, required=True)
        child.add_argument("--manifest", type=Path, required=True)
        child.add_argument("--null", type=Path, required=True)
        child.add_argument("--database", type=Path, required=True)
        if name == "run":
            child.add_argument("--source-root", type=Path, required=True)
        else:
            child.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command in ("admit", "prepare", "run") and Path(__file__).resolve() != (
            args.source_root / "scripts/run_b0h_calibration.py").resolve():
            raise ValueError("executing command differs from attested source_root")
        if args.command == "admit":
            frozen_file(args.out, runner_record_bytes(observe_b0h_admission(args.source_root, args.database_parent)))
            return 0
        if args.command == "reduce":
            snapshot = read_collected_b0h_snapshot(args.collection,
                expected_database_sha256=args.expected_database_sha256,
                expected_inventory_sha256=args.expected_inventory_sha256)
            output = reduce_b0h_study(snapshot.manifest, snapshot.cases, restore_null(snapshot.null))
            raw = reduction_bytes(output)
            frozen_file(args.out, raw)
            print(json.dumps({"format": "b0h_reduction_receipt", "version": "1",
                              "sha256": sha256(raw), "inventory_sha256": output.inventory_sha256},
                             sort_keys=True, separators=(",", ":")))
            return 0 if output.unconditional_claim_eligible else 1
        admission = read_record(args.admission, AdmissionReceipt)
        if args.command in ("prepare", "run"):
            actual = observe_b0h_admission(args.source_root, Path(admission.storage.database_parent))
            if (actual.source != admission.source or actual.runtime != admission.runtime
                    or actual.storage.database_parent != admission.storage.database_parent
                    or actual.storage.device_id != admission.storage.device_id
                    or actual.storage.mount_type != admission.storage.mount_type
                    or actual.storage.mount_options != admission.storage.mount_options):
                raise ValueError("runtime/source/storage differs from frozen admission")
        if args.command == "prepare":
            reference = simulate_rank_null(sample_size=512, replicates=100000, seed=1653499886)
            null = prepared_null(reference)
            frozen_file(args.null, runner_record_bytes(null))
            manifest = build_manifest(admission, null, worker_id=args.worker_id,
                limits=B0HCodecLimits(args.max_metadata_bytes, args.max_payload_bytes))
            frozen_file(args.manifest, runner_record_bytes(manifest))
            database = Path(admission.storage.database_parent) / "study.sqlite3"
            open_store = _TimedStore if database.exists() else _TimedStore.create
            with open_store(database, manifest=manifest, admission=admission, null=null,
                              owner_id=str(uuid.uuid4())):
                pass
            return 0
        manifest = read_record(args.manifest, CampaignManifest)
        null = read_record(args.null, PreparedNull)
        if not args.database.is_file():
            raise ValueError("prepared campaign database is missing; no recreation on run/reduce")
        with _TimedStore(args.database, manifest=manifest, admission=admission,
                          null=null, owner_id=str(uuid.uuid4())) as store:
            if args.command == "run":
                for case in manifest.cases:
                    while True:
                        try:
                            execute_b0h_case(manifest, case, store)
                        except PendingPublication as pending:
                            reconcile_publication(store, pending)
                        else:
                            break
                return 0
            for case in manifest.cases:
                load_b0h_case(manifest, case, store)
            database_digest, inventory_digest = store.collect(args.out)
            receipt = {"format": "b0h_collection", "version": "1",
                       "database_sha256": database_digest, "inventory_sha256": inventory_digest}
            frozen_file(args.out / "collection.json", json.dumps(receipt, sort_keys=True,
                        separators=(",", ":")).encode("ascii"))
            print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
            return 0
    except PendingPublication as error:
        print(json.dumps({"status": "unresolved_publication", "message": str(error),
                          "redelivery_permitted": False}), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print(json.dumps({"status": "interrupted_unresolved", "redelivery_permitted": False}), file=sys.stderr)
        return 130
    except Exception as error:
        print(json.dumps({"status": "adapter_refusal", "exception_class":
                          type(error).__module__ + "." + type(error).__qualname__,
                          "message_utf8hex": str(error).encode("utf-8", "surrogatepass").hex()}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
```

Command errors produce explicit nonzero operational status; exit0 from `run`
means the loop completed, not that calibration passed. Only reduction reports
claim eligibility. The same immutable inputs permit repeated pure reduction;
use a different output path for a genuinely different snapshot, never overwrite.

- [ ] Step 5b: Create `docs/research/population-heterogeneity-runner-2026-09-10.md` with this exact engineering scope note. Do not add a plot or scientific success claim: this change creates no renderable scientific result.

```markdown
# B0H runner engineering boundary

This adapter implements the frozen B0H runner design, §§3–8. It advances #211
and #189 without completing the calibration study or baseline comparison.

One local worker owns one SQLite database. START is exclusive stage admission,
not proof that a graph or sampler ran. Exact scientific codec bytes, receipt and
completion publish atomically. An unresolved START is never redelivered.
Only a completed typed convergence failure admits the single scientific retry.

Known live publication bytes remain in one immutable packet. The command pauses
science and retries publication only every 60 seconds for at most 1,800 seconds.
Storage integrity and programming defects are not retryable. Expiry/interruption
reports loss risk and exits nonzero; this is not durable process-loss retention.

Actual source/import origins, JAX/CuPy float64 support, memory observations and
local storage probes precede case execution. Initial mount admission accepts
ext4, xfs, btrfs or tmpfs; tmpfs is volatile. A filesystem name proves no power,
host or Pod-loss durability. Unverified container backing requires investigation
and reviewed pre-case correction, not GPU-capacity fallback.

Closed collection copies the database while campaign exclusion is retained and
publishes database/inventory digests. Evidence consumers independently retain
those digests and supply both to the read-only collected-snapshot reader.
Collected provenance never authorizes execution on another machine. The reader
uses SQLite mode=ro, a stable read transaction, sidecar refusal and before/after
checksums; it does not assert immutable=1.

Reduction accounts for all 1,938 cases, twelve correct-family full-N tests, four
predeclared sensitivity assertions and all remaining control/diagnostic outcomes.
Missing ranks have explicit actual-N counts but no full-N p-value. Missing
predictive evidence blocks unconditional wording. Secondary values have no new
decision thresholds. Linked loci and paired tracks are not independent datasets.

The checked-in tests use synthetic constructor-valid fixtures and counted-call
sentinels. They are engineering evidence, not realized calibration or admission
measurements. Actual verification commands/results belong in the implementing
PR report; this note makes no unobserved test or full-study success claim.
```

- [ ] Step 6: Run the command tests and all runner-focused tests, then smoke.

```bash
env PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib /private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python -m pytest tests/test_heterogeneity_runner_records.py tests/test_heterogeneity_runner_store.py tests/test_heterogeneity_runner.py tests/test_heterogeneity_reduction.py tests/test_heterogeneity_runner_cli.py -o addopts='' -q
env PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib /private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python scripts/smoke.py
```

- [ ] Verification gate: run the task's focused GREEN, mandatory smoke and static/privacy checks. Record the actual command, exit status and counts in the authorized task report. A failed fixture or adapter check is not permission to alter scientific policy.

```bash
env PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib /private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python -m pytest tests/test_heterogeneity_runner_records.py tests/test_heterogeneity_runner_store.py tests/test_heterogeneity_runner.py tests/test_heterogeneity_reduction.py tests/test_heterogeneity_runner_cli.py -o addopts='' -q
env PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib /private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python scripts/smoke.py
/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/ruff check .
env PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib /private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python scripts/freeze_contract.py --check
env PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib /private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python scripts/check_module_size.py
git diff --check
git add genomeos/validation/heterogeneity_runner_records.py genomeos/validation/heterogeneity_runner_reader.py genomeos/validation/heterogeneity_runner_store.py genomeos/validation/heterogeneity_runner_admission.py scripts/run_b0h_calibration.py tests/test_heterogeneity_runner_cli.py docs/research/population-heterogeneity-runner-2026-09-10.md
git diff --cached --name-only
env PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib /private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python scripts/check_private_files.py
```

- [ ] Inspect the staged-path output. It must contain only this task's explicitly owned files above and no SDD/private/generated evidence. Preserve unrelated work. If every check passed and the staged scope is exact, make the task commit; advance #211/#189 without closing either.

```bash
git commit -m "feat: compose offline B0H admission and collected evidence consumption" -m "Advances #211 and #189; neither calibration nor benchmark completion is claimed."
```


## Root adoption and final verification

- [ ] Root personally reads this complete plan and adopted runner design at
`c75e0b68c9a7ee4b79ed7280b8434e70cc13e921`, resolves concrete discrepancies,
and adopts only the reviewed neutral artifacts. No implementation follows from
the planner's handoff alone.
- [ ] Execute the five independently rejectable tasks in order. Reuse each
preceding reviewed public contract; no task delegates specification reading.
- [ ] After task integration, root performs fresh broad review and the stable
full CI suite below. No prior codec-only result substitutes for runner integration.
Root reports actual commands/counts/warnings and any unexecuted acceptance item.

```bash
env PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib /private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python -m pytest -o addopts='' -q
/private/tmp/genomeos-af-locked.vIVN0z/venv/bin/ruff check .
env PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib /private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python scripts/freeze_contract.py --check
env PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib /private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python scripts/check_module_size.py
env PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib /private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python scripts/check_private_files.py
env PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTENSOR_FLAGS=base_compiledir=/private/tmp/genomeos-modeling-cache.VPqlMe/pytensor MPLCONFIGDIR=/private/tmp/genomeos-modeling-cache.VPqlMe/matplotlib /private/tmp/genomeos-af-locked.vIVN0z/venv/bin/python scripts/smoke.py
git diff --check
git diff --cached --name-only
```

- [ ] Root owns the branch push and PR after review/privacy verification. The PR
advances #211/#189 and closes neither. Actual GPU admission, full frozen null
preparation and case science remain separate subsequent work. No pod, launcher,
scheduler, storage fallback or optional recovery framework is introduced here.

## Planner self-review coverage

This table records static plan coverage, not executed results. The planner
personally checked code/signature/fixture correspondence and the final adopted
specification. No test, scientific call, runtime admission or implementation was
performed while drafting.

| Adopted requirement | Exact plan coverage | Evidence planned |
| --- | --- | --- |
| Frozen design, all 1,938 cases, one worker/CuPy | Global constraints; Task1 manifest/null; Task5 command | Closed identity/null tests; literal enumeration; admission refusal |
| Exact root admission and raw-field validation | Task1 records/wire | Unsupported object/subclass, bypassed tuple/scalar, duplicate-key/canonical-byte cases |
| Separate exclusive create and existing open | Task2 store | Missing/empty-existing/symlink refusal; create collision |
| Atomic exact result+receipt+COMPLETE | Task2 store and shared reader | Precommit failure, acknowledgment loss, exact reuse, bit/missing payload corruption |
| START is admission, not a sampler counter | Task3 execution; Task4 accounting | Counts for wrapper/fitter/graph/sampler separated; ambiguous fit slots explicit |
| One owner and no operational redelivery | Task2 flock; Task3 executor | Competing process; before/during/after-call interruption; owner-loss reuse |
| Same known packet retained through uncertainty | Task2 PendingPublication; Task5 reconciliation | Uninspectable I/O, same bytes/timing, bounded publication-only retry and expiry |
| Dataset/track/attempt/selected/heldout binding | Task3 pure binding | Equal-total dataset substitution, wrong track, orphan retry, selected index and heldout order refusal |
| Typed structural and convergence policy | Task3 executor | Actual all-unavailable early refusal; unexpected structural return; retry only convergence |
| Exact full-N tests and honest actual-N outcomes | Task4 reduction | Literal N512 inclusive-tail arithmetic; N511/N0 no test; actual prerequisite failure labels |
| Correct rejection versus control sensitivity | Task4 reduction | Twelve correct rows/four assertions; missed control distinct from rejection |
| Descriptive rows/failed denominators | Task4 reduction | Separate shared/fresh targets, negative-infinite score, missing prediction retains parameter rows |
| Separate actual storage/collection timing | Task5 command-only interval report | Measured store-method boundaries; same scientific packet/timing unchanged; missing end explicit |
| Actual import/source/storage binding | Task5 admission | Wrong-checkout import and command refusal; probes measured only at later actual admission |
| Portable evidence consumption, not recovery | Task5 collected reader | Copied directory, mode=ro, unchanged files, external hashes, journal/WAL refusal; original run path still rejected |
| Bounded scaling of whole-store audits | Task2 shared reader | One whole-store audit per inventory; cached immutable manifest digest in each SQL reader; focused per-case reads |
| Task-local TDD/review/commit gates | Every task | Import-in-test behavioral RED precedes production; exact focused/smoke/static/privacy and commit commands |
| No new science or operational framework | Owned-file map and scope note | No existing scientific module edits; no optional backend, recovery file, queue or cloud launcher |

Initial platform admission can refuse a usable container mount until its local
backing is reviewed. The 30-minute pending-publication window can consume idle
compute and still lose known bytes at expiry/interruption. Those explicit costs
were ruled on by root; neither is a scientific retry permission. The evidence
reader adds one concrete shared read component and full-file checksum work.

The draft is complete for root's personal review, not an execution-success
certificate. Literal fixture/code blocks remain intentionally unexecuted in
this planning-only role; actual RED/GREEN and integration results must be
observed during the authorized implementation tasks.
