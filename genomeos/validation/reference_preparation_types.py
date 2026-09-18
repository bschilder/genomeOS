"""Preparation-phase evidence records (reference acquisition design §6)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from genomeos.validation.reference_acquisition_types import (
    REASONS,
    ArtifactRef,
    CohortInputHashes,
    NativeCountFiles,
    NativeTokenFiles,
    RunProvenance,
)
from genomeos.validation.reference_cohorts import PAPER_STAGE, TECHNICAL_STAGE
from genomeos.validation.reference_genotypes import QcTally
from genomeos.validation.reference_window_types import AUTOSOMES

Stage = Literal["technical_qc_4117", "paper_ancestry_exclusion_4094"]
Kind = Literal["called", "quality"]

PREPARATION_POLICY: tuple[tuple[str, str | int], ...] = tuple(
    sorted(
        {
            "count_contract": "pilot_stage_qc_semantics_unchanged_v1",
            "missingness": "vcf42_explicit_origin_lazy_qc",
            "native_counts": "exact_called_cohort_totals_missing_refuses",
            "native_sample_stdout_limit_bytes": 1_048_576,
            "native_stdout_limit_bytes": 2_147_483_648,
            "native_timeout_seconds": 1_800,
            "native_version_stdout_limit_bytes": 65_536,
            "pos_selection": "start0_lt_pos_le_end0",
            "record_limit_bytes": 16_777_216,
            "records_per_window_limit": 1_000_000,
            "schema_version": "reference_preparation_policy_v1",
            "site_selection": "PASS_distinct_biallelic_uppercase_ACGT",
            "stderr_limit_bytes": 1_048_576,
        }.items()
    )
)

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_STAGES = (TECHNICAL_STAGE, PAPER_STAGE)
_KINDS = ("called", "quality")
_SITE_KEYS = ("not_acgt_snp", "not_biallelic", "not_pass", "outside_pos", "retained")
DEPENDENCY_EDGES = (("CDX", "Dai"), ("Cambodian", "Japanese"), ("ITU", "STU"))


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _text(value: object, field: str) -> str:
    _require(isinstance(value, str) and bool(value.strip()) and value == value.strip(), f"invalid {field}")
    return value


def _count(value: object, field: str) -> int:
    _require(type(value) is int and value >= 0, f"{field} must be an integer >= 0")
    return value


def _reason(value: object, *, required: bool) -> None:
    _require((isinstance(value, str) and value in REASONS) if required else value is None,
             "invalid refusal reason")


def _positive_pairs(value: object, *, field: str, keys: tuple[str, ...]) -> dict[str, int]:
    _require(type(value) is tuple, f"{field} must be a tuple")
    pairs: list[tuple[str, int]] = []
    for entry in value:
        _require(type(entry) is tuple and len(entry) == 2, f"invalid {field} entry")
        key = _text(entry[0], f"{field} key")
        count = _count(entry[1], f"{field} count")
        _require(key in keys and count > 0, f"invalid {field} counter")
        pairs.append((key, count))
    _require(tuple(pairs) == tuple(sorted(pairs)), f"{field} must be sorted")
    _require(len(pairs) == len({key for key, _ in pairs}), f"{field} keys must be unique")
    return dict(pairs)


@dataclass(frozen=True)
class PreparationInputs:
    acquisition: ArtifactRef
    cohort: CohortInputHashes
    dependency_audit: ArtifactRef

    def __post_init__(self) -> None:
        _require(type(self.acquisition) is ArtifactRef, "invalid acquisition input")
        _require(type(self.cohort) is CohortInputHashes, "invalid cohort input")
        _require(type(self.dependency_audit) is ArtifactRef, "invalid dependency audit input")


@dataclass(frozen=True)
class StageWindowSummary:
    sample_count: int
    population_count: int
    variants: int
    rows: int
    called_unavailable: int
    quality_unavailable: int
    called_ac_sum: int
    called_an_sum: int
    quality_ac_sum: int
    quality_an_sum: int
    native_ac_an_matches: int
    native_interpreted_calls: int
    qc: QcTally

    def __post_init__(self) -> None:
        for field in self.__dataclass_fields__:
            if field != "qc":
                _count(getattr(self, field), field)
        _require(type(self.qc) is QcTally, "invalid stage QC tally")
        _require(self.rows == self.population_count * self.variants, "stage row count mismatch")
        _require(self.called_unavailable <= self.rows and self.quality_unavailable <= self.rows,
                 "stage unavailable count exceeds rows")
        _require(self.quality_ac_sum <= self.called_ac_sum <= self.called_an_sum,
                 "stage called sums are invalid")
        _require(self.quality_ac_sum <= self.quality_an_sum <= self.called_an_sum,
                 "stage quality sums are invalid")
        _require(self.native_ac_an_matches == self.variants, "native match count must cover variants")
        _require(self.native_interpreted_calls == self.sample_count * self.variants,
                 "native interpretation count mismatch")
        dispositions = sum(count for _, count in self.qc.dispositions)
        _require(dispositions == self.sample_count * self.variants, "stage QC coverage mismatch")
        disposition_map = dict(self.qc.dispositions)
        _require(
            self.called_an_sum == 2 * (dispositions - disposition_map.get("missing_gt", 0))
            and self.quality_an_sum == 2 * disposition_map.get("accepted", 0),
            "stage allele-number totals disagree with QC",
        )


@dataclass(frozen=True)
class PreparationStageReceipt:
    stage: Stage
    state: Literal["complete", "refused", "not_attempted"]
    reason: str | None
    summary: StageWindowSummary | None
    native_control: NativeCountFiles | None
    native_tokens: NativeTokenFiles | None

    def __post_init__(self) -> None:
        _require(self.stage in _STAGES, "invalid preparation stage")
        _require(self.state in ("complete", "refused", "not_attempted"), "invalid stage state")
        _reason(self.reason, required=self.state != "complete")
        _require(self.summary is None or type(self.summary) is StageWindowSummary, "invalid stage summary")
        _require(self.native_control is None or type(self.native_control) is NativeCountFiles,
                 "invalid native count control")
        _require(self.native_tokens is None or type(self.native_tokens) is NativeTokenFiles,
                 "invalid native token control")
        if self.state == "not_attempted":
            _require(self.summary is None and self.native_control is None and self.native_tokens is None,
                     "not-attempted stage cannot carry outputs")
        elif self.state == "refused":
            _require(self.summary is None, "refused stage cannot carry an admitted summary")
            nested_failure = (
                self.native_control
                if self.native_control is not None and self.native_control.state == "refused"
                else self.native_tokens
                if self.native_tokens is not None and self.native_tokens.state == "refused"
                else None
            )
            if nested_failure is not None:
                _require(
                    self.reason == nested_failure.reason,
                    "refused stage reason differs from its failed native evidence",
                )
        else:
            _require(type(self.summary) is StageWindowSummary, "complete stage requires summary")
            expected_samples = 4_117 if self.stage == TECHNICAL_STAGE else 4_094
            _require(
                self.summary.sample_count == expected_samples and self.summary.population_count == 80,
                "complete stage cohort cardinality mismatch",
            )
            if self.summary.variants == 0:
                _require(self.native_control is None and self.native_tokens is None,
                         "empty stage cannot claim native controls")
            else:
                _require(
                    type(self.native_control) is NativeCountFiles
                    and self.native_control.state == "complete"
                    and type(self.native_tokens) is NativeTokenFiles
                    and self.native_tokens.state == "complete",
                    "nonempty stage requires complete native controls",
                )
                _require(
                    self.native_control.input_bcf.path.startswith("@acquisition/")
                    and self.native_tokens.input_bcf == self.native_control.selected_bcf,
                    "native stage artifact lineage mismatch",
                )


@dataclass(frozen=True)
class PreparationWindowReceipt:
    window_id: str
    chrom: str
    state: Literal["counts_prepared", "no_records", "no_pass_snps", "refused"]
    reason: str | None
    raw_records: int | None
    retained_variants: int | None
    site_dispositions: tuple[tuple[str, int], ...] | None
    stages: tuple[PreparationStageReceipt, ...]

    def __post_init__(self) -> None:
        _text(self.window_id, "window_id")
        _require(self.chrom in AUTOSOMES and self.window_id.startswith(f"{self.chrom}-s"),
                 "window chromosome mismatch")
        _require(self.state in ("counts_prepared", "no_records", "no_pass_snps", "refused"),
                 "invalid preparation window state")
        _reason(self.reason, required=self.state == "refused")
        _require(
            type(self.stages) is tuple
            and all(type(value) is PreparationStageReceipt for value in self.stages)
            and tuple(value.stage for value in self.stages) == _STAGES,
            "preparation stage order mismatch",
        )
        for field in ("raw_records", "retained_variants"):
            value = getattr(self, field)
            _require(value is None or type(value) is int, f"invalid {field}")
            if value is not None:
                _count(value, field)
        if self.state == "refused":
            _require(
                self.retained_variants is None
                and self.site_dispositions is None
                and all(value.summary is None for value in self.stages),
                "refused window cannot admit retained counts or stage summaries",
            )
            expected_stage_state = "not_attempted" if self.raw_records is None else "refused"
            _require(
                all(
                    value.state == expected_stage_state
                    for value in self.stages
                ),
                "refused window stage outcomes disagree with its failure point",
            )
            _require(
                self.stages[0].reason == self.reason,
                "refused window reason differs from the first stage outcome",
            )
            if expected_stage_state == "not_attempted":
                _require(
                    all(value.reason == self.reason for value in self.stages),
                    "pre-scan refusal reason must propagate to both stages",
                )
            if self.raw_records is not None:
                _require(self.raw_records > 0, "post-scan refusal requires observed records")
            return
        _require(self.raw_records is not None and self.retained_variants is not None,
                 "complete window requires known counts")
        dispositions = _positive_pairs(self.site_dispositions, field="site dispositions", keys=_SITE_KEYS)
        _require(sum(dispositions.values()) == self.raw_records, "site dispositions do not cover raw records")
        _require(dispositions.get("retained", 0) == self.retained_variants,
                 "retained variant count mismatch")
        _require(all(value.state == "complete" for value in self.stages),
                 "complete window requires complete stages")
        _require(all(value.summary.variants == self.retained_variants for value in self.stages),
                 "stage variant count differs from window")
        if self.state == "no_records":
            _require(self.raw_records == self.retained_variants == 0, "no_records window must be empty")
        elif self.state == "no_pass_snps":
            _require(self.raw_records > 0 and self.retained_variants == 0,
                     "no_pass_snps window has invalid counts")
        else:
            _require(self.retained_variants > 0, "counts_prepared window must contain variants")


@dataclass(frozen=True)
class TrackSummary:
    stage: Stage
    kind: Kind
    table: ArtifactRef
    dependencies: ArtifactRef
    rows: int
    variants: int
    represented_groups: int
    unavailable_rows: int
    ac_sum: int
    an_sum: int

    def __post_init__(self) -> None:
        _require(self.stage in _STAGES and self.kind in _KINDS, "invalid track identity")
        _require(type(self.table) is ArtifactRef and type(self.dependencies) is ArtifactRef,
                 "invalid track artifacts")
        for field in ("rows", "variants", "represented_groups", "unavailable_rows", "ac_sum", "an_sum"):
            _count(getattr(self, field), field)
        _require(self.rows == self.variants * self.represented_groups, "track row count mismatch")
        _require(self.unavailable_rows <= self.rows and self.ac_sum <= self.an_sum,
                 "invalid track count summary")


@dataclass(frozen=True)
class DependencyEvidence:
    schema_version: Literal["reference_population_dependencies_v1"]
    stage: Stage
    populations: tuple[str, ...]
    edges: tuple[tuple[str, str], ...]
    reported_pairs: int
    component_count: int
    audit_sha256: str
    qualification: Literal["reported_edges_only_shared_source_dependence_remains"]

    def __post_init__(self) -> None:
        _require(self.schema_version == "reference_population_dependencies_v1", "invalid dependency schema")
        _require(self.stage in _STAGES, "invalid dependency stage")
        _require(type(self.populations) is tuple and self.populations == tuple(sorted(self.populations)),
                 "dependency populations must be sorted")
        _require(len(self.populations) == len(set(self.populations)), "dependency populations must be unique")
        for value in self.populations:
            _text(value, "dependency population")
        _require(type(self.edges) is tuple and self.edges == tuple(sorted(self.edges)),
                 "dependency edges must be sorted")
        _require(len(self.edges) == len(set(self.edges)), "dependency edges must be unique")
        for edge in self.edges:
            _require(type(edge) is tuple and len(edge) == 2 and edge[0] < edge[1], "invalid dependency edge")
            _require(set(edge) <= set(self.populations), "dependency edge has unknown population")
        expected_pairs = 1_302 if self.stage == TECHNICAL_STAGE else 1_294
        _require(
            len(self.populations) == 80
            and self.edges == DEPENDENCY_EDGES
            and _count(self.reported_pairs, "reported_pairs") == expected_pairs,
            "dependency scope or reported pair count mismatch",
        )
        neighbors = {population: set() for population in self.populations}
        for left, right in self.edges:
            neighbors[left].add(right)
            neighbors[right].add(left)
        remaining = set(self.populations)
        components = 0
        while remaining:
            components += 1
            frontier = [remaining.pop()]
            while frontier:
                discovered = neighbors[frontier.pop()] & remaining
                remaining.difference_update(discovered)
                frontier.extend(discovered)
        _require(_count(self.component_count, "component_count") == components,
                 "dependency component count mismatch")
        _require(isinstance(self.audit_sha256, str) and _SHA256.fullmatch(self.audit_sha256) is not None,
                 "invalid dependency audit hash")
        _require(self.qualification == "reported_edges_only_shared_source_dependence_remains",
                 "invalid dependency qualification")


@dataclass(frozen=True)
class PreparationManifest:
    schema_version: Literal["reference_window_counts_v1"]
    inputs: PreparationInputs
    provenance: RunProvenance
    policy: tuple[tuple[str, str | int], ...]
    windows: tuple[PreparationWindowReceipt, ...]
    tracks: tuple[TrackSummary, ...]
    files: tuple[ArtifactRef, ...]
    status: Literal["complete_nonempty", "complete_empty", "refused"]
    complete: bool
    publication_eligible: Literal[False]
    p1_eligible: Literal[False]
    benchmark_admitted: Literal[False]

    def __post_init__(self) -> None:
        _require(self.schema_version == "reference_window_counts_v1", "invalid preparation schema")
        _require(type(self.inputs) is PreparationInputs and type(self.provenance) is RunProvenance,
                 "invalid preparation inputs or provenance")
        _require(self.policy == PREPARATION_POLICY, "unsupported preparation policy")
        expected_ids = tuple(f"chr{chrom}-s{stratum}" for chrom in range(1, 23) for stratum in range(1, 4))
        _require(
            type(self.windows) is tuple
            and all(type(value) is PreparationWindowReceipt for value in self.windows)
            and tuple(value.window_id for value in self.windows) == expected_ids,
            "preparation windows must contain the frozen 66 IDs",
        )
        _require(type(self.files) is tuple and all(type(value) is ArtifactRef for value in self.files),
                 "invalid preparation files")
        _require(type(self.tracks) is tuple and all(type(value) is TrackSummary for value in self.tracks),
                 "invalid preparation tracks")
        paths = tuple(value.path for value in self.files)
        _require(paths == tuple(sorted(paths)) and len(paths) == len(set(paths)),
                 "preparation files must be path-sorted and unique")
        _require(self.status in ("complete_nonempty", "complete_empty", "refused"),
                 "invalid preparation status")
        _require(type(self.complete) is bool and self.complete is (self.status != "refused"),
                 "preparation completeness disagrees with status")
        if self.status == "refused":
            _require(not self.tracks, "refused preparation cannot admit tracks")
            _require(
                any(value.state == "refused" for value in self.windows),
                "refused preparation requires a refused window",
            )
        else:
            expected_tracks = tuple((stage, kind) for stage in _STAGES for kind in _KINDS)
            _require(tuple((value.stage, value.kind) for value in self.tracks) == expected_tracks,
                     "complete preparation requires four ordered tracks")
            _require(
                all(
                    track.table.path == f"{track.stage}.{track.kind}.tsv"
                    and track.dependencies.path == f"{track.stage}.dependencies.json"
                    for track in self.tracks
                ),
                "complete preparation track paths differ from the fixed layout",
            )
            _require(
                all(
                    value.state != "refused"
                    and all(stage.state == "complete" for stage in value.stages)
                    for value in self.windows
                ),
                "complete preparation has an incomplete window",
            )
            total_variants = sum(value.retained_variants or 0 for value in self.windows)
            _require((total_variants == 0) is (self.status == "complete_empty"),
                     "preparation empty status mismatch")
        _require(self.publication_eligible is False and self.p1_eligible is False
                 and self.benchmark_admitted is False, "preparation eligibility must remain false")
