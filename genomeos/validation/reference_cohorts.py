"""Preserve exact reference cohort identities (reference acquisition design §2)."""

from __future__ import annotations

import csv
import hashlib
import io
import json
from dataclasses import dataclass
from typing import Any, Literal

TECHNICAL_STAGE = "technical_qc_4117"
PAPER_STAGE = "paper_ancestry_exclusion_4094"
METADATA_SHA256 = "e18e7a29d0567b8063edc1a714bd31e57dc422823ba51af2c63fecef0dbc3cf1"
OUTLIERS_SHA256 = "592772fff79086a6b55ce07693f2871c9e4fbe9bdeff1ff926d87fcba884994f"
EXCLUSIONS_SHA256 = "a2d7138d85ba0931d3de7edb20e714fd840bdc75d82e29ed7cd1c9392b544488"
TECHNICAL_SAMPLES_SHA256 = "4a4cb8594e78e8d584dd61357d10b9c35b2e50c870a9a7bad0f42b326544d4e2"
PAPER_SAMPLES_SHA256 = "7e2a7260d7d9b138b535c1cc2c48496e534bad9b72b8f7d72da6107193e55aec"

_REQUIRED_COLUMNS = (
    "s",
    "population",
    "hgdp_tgp_meta.Genetic.region",
    "sample_filters.hard_filtered",
)
_KNOWN_COLLISION_IDENTITIES = frozenset(
    {"Han", "NorthernHan", "PapuanHighlands", "PapuanSepik"}
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _text(value: object, field: str, *, reject_na: bool = False) -> str:
    valid = (
        isinstance(value, str)
        and bool(value.strip())
        and value == value.strip()
        and "\t" not in value
        and "\n" not in value
        and "\r" not in value
        and "\0" not in value
    )
    _require(valid and (not reject_na or value != "NA"), f"invalid {field}")
    return value


@dataclass(frozen=True)
class Sample:
    sample_id: str
    population: str
    region: str
    hard_filtered: bool

    def __post_init__(self) -> None:
        _text(self.sample_id, "sample_id")
        _text(self.population, "population", reject_na=True)
        _text(self.region, "region", reject_na=True)
        _require(type(self.hard_filtered) is bool, "hard_filtered must be bool")


@dataclass(frozen=True)
class CohortExclusions:
    control_id: str
    contamination_ids: tuple[str, str]

    def __post_init__(self) -> None:
        _text(self.control_id, "control_id")
        _require(type(self.contamination_ids) is tuple and len(self.contamination_ids) == 2,
                 "contamination_ids must contain two IDs")
        for value in self.contamination_ids:
            _text(value, "contamination_id")
        _require(self.contamination_ids == tuple(sorted(self.contamination_ids)),
                 "contamination_ids must be sorted")
        _require(len(set(self.contamination_ids)) == 2, "contamination_ids must be distinct")
        _require(self.control_id not in self.contamination_ids, "control and contamination IDs overlap")


@dataclass(frozen=True)
class Cohort:
    stage: Literal["technical_qc_4117", "paper_ancestry_exclusion_4094"]
    samples: tuple[Sample, ...]

    def __post_init__(self) -> None:
        _require(self.stage in (TECHNICAL_STAGE, PAPER_STAGE), "invalid cohort stage")
        _require(type(self.samples) is tuple and all(type(sample) is Sample for sample in self.samples),
                 "cohort samples must be a tuple of Sample values")
        ids = tuple(sample.sample_id for sample in self.samples)
        _require(ids == tuple(sorted(ids)), "cohort samples must be sorted by sample_id")
        _require(len(ids) == len(set(ids)), "cohort sample IDs must be unique")


@dataclass(frozen=True)
class CohortColumn:
    sample_id: str
    sample_index: int
    population: str
    region: str

    def __post_init__(self) -> None:
        _text(self.sample_id, "sample_id")
        _require(type(self.sample_index) is int and self.sample_index >= 0,
                 "sample_index must be an integer >= 0")
        _text(self.population, "population", reject_na=True)
        _text(self.region, "region", reject_na=True)


def _validate_population_regions(samples: tuple[Sample, ...]) -> None:
    regions: dict[str, str] = {}
    for sample in samples:
        previous = regions.setdefault(sample.population, sample.region)
        _require(previous == sample.region, "one population has inconsistent operational region labels")


def select_cohorts(
    samples: tuple[Sample, ...],
    exclusions: CohortExclusions,
    outliers: tuple[str, ...],
) -> tuple[Cohort, Cohort]:
    """Apply the preserved technical and paper exclusions by exact sample identity."""
    _require(type(samples) is tuple and all(type(sample) is Sample for sample in samples),
             "metadata must be a tuple of Sample values")
    _require(type(exclusions) is CohortExclusions, "exclusions must be CohortExclusions")
    _require(type(outliers) is tuple, "outliers must be a tuple")
    for value in outliers:
        _text(value, "outlier ID")
    sample_ids = tuple(sample.sample_id for sample in samples)
    _require(len(sample_ids) == len(set(sample_ids)), "metadata sample IDs must be unique")
    _validate_population_regions(samples)
    known_ids = set(sample_ids)
    contamination = set(exclusions.contamination_ids)
    _require(exclusions.control_id not in known_ids, "synthetic control must remain outside metadata")
    _require(contamination <= known_ids, "contamination exclusions are absent from metadata")
    hard_ids = {sample.sample_id for sample in samples if sample.hard_filtered}
    _require(not contamination & hard_ids, "contamination exclusions overlap hard filters")
    _require(len(outliers) == len(set(outliers)), "release outlier IDs must be unique")

    technical_ids = known_ids - hard_ids - contamination
    _require(set(outliers) <= technical_ids, "invalid release outlier membership")
    paper_ids = technical_ids - set(outliers)
    by_id = {sample.sample_id: sample for sample in samples}
    technical = Cohort(TECHNICAL_STAGE, tuple(by_id[key] for key in sorted(technical_ids)))
    paper = Cohort(PAPER_STAGE, tuple(by_id[key] for key in sorted(paper_ids)))
    return technical, paper


def cohort_columns(header_samples: tuple[str, ...], cohort: Cohort) -> tuple[CohortColumn, ...]:
    """Join a qualified cohort to one source's actual sample-column order."""
    _require(type(header_samples) is tuple, "header samples must be a tuple")
    for value in header_samples:
        _text(value, "header sample ID")
    _require(len(header_samples) == len(set(header_samples)), "source header sample IDs must be unique")
    _require(type(cohort) is Cohort, "cohort must be Cohort")
    members = {sample.sample_id: sample for sample in cohort.samples}
    _require(set(members) <= set(header_samples), "source header is missing a cohort member")
    return tuple(
        CohortColumn(value, index, members[value].population, members[value].region)
        for index, value in enumerate(header_samples)
        if value in members
    )


def _digest(value: object) -> str | None:
    return hashlib.sha256(value).hexdigest() if type(value) is bytes else None


def _verify_real_hashes(inputs: tuple[object, ...]) -> None:
    expected = (
        METADATA_SHA256,
        OUTLIERS_SHA256,
        EXCLUSIONS_SHA256,
        TECHNICAL_SAMPLES_SHA256,
        PAPER_SAMPLES_SHA256,
    )
    actual = tuple(_digest(value) for value in inputs)
    _require(actual == expected, "real cohort input hash mismatch")


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        _require(key not in result, "duplicate cohort exclusion key")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"nonfinite cohort exclusion value: {value}")


def _parse_exclusions(raw: bytes) -> CohortExclusions:
    try:
        payload = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_pairs,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("invalid cohort exclusions") from error
    _require(
        type(payload) is dict
        and set(payload) == {"schema_version", "control_id", "contamination_ids"},
        "invalid cohort exclusion fields",
    )
    _require(payload["schema_version"] == "reference_cohort_exclusions_v1",
             "unsupported cohort exclusion schema")
    values = payload["contamination_ids"]
    _require(type(values) is list, "contamination_ids must be an array")
    exclusions = CohortExclusions(payload["control_id"], tuple(values))
    canonical = (json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()
    _require(raw == canonical, "cohort exclusions are not canonical")
    return exclusions


def _parse_metadata(raw: bytes) -> tuple[Sample, ...]:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("cohort metadata must be UTF-8") from error
    rows = csv.reader(io.StringIO(text, newline=""), delimiter="\t")
    try:
        header = tuple(next(rows))
    except StopIteration as error:
        raise ValueError("cohort metadata is empty") from error
    _require(len(header) == len(set(header)) and all(header), "cohort metadata columns are invalid")
    _require(set(_REQUIRED_COLUMNS) <= set(header), "cohort metadata lacks required columns")
    positions = {field: header.index(field) for field in _REQUIRED_COLUMNS}
    result = []
    for row in rows:
        _require(len(row) == len(header), "cohort metadata row width mismatch")
        hard = row[positions["sample_filters.hard_filtered"]]
        _require(hard in ("true", "false"), "invalid literal hard_filtered value")
        result.append(
            Sample(
                row[positions["s"]],
                row[positions["population"]],
                row[positions["hgdp_tgp_meta.Genetic.region"]],
                hard == "true",
            )
        )
    return tuple(result)


def _parse_ids(raw: bytes, field: str, *, sorted_lf: bool) -> tuple[str, ...]:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"{field} must be UTF-8") from error
    _require(not sorted_lf or (raw.endswith(b"\n") and b"\r" not in raw), f"{field} must use sorted LF")
    values = tuple(text.splitlines())
    for value in values:
        _text(value, field)
    _require(len(values) == len(set(values)), f"{field} IDs must be unique")
    if sorted_lf:
        _require(values == tuple(sorted(values)), f"{field} IDs must be sorted")
        _require(raw == "".join(f"{value}\n" for value in values).encode(), f"noncanonical {field}")
    return values


def _encoded_cohort(cohort: Cohort) -> bytes:
    return "".join(f"{sample.sample_id}\n" for sample in cohort.samples).encode()


def qualify_real_cohorts(
    metadata: bytes,
    outliers: bytes,
    exclusions: bytes,
    technical_samples: bytes,
    paper_samples: bytes,
) -> tuple[Cohort, Cohort]:
    """Reconstruct the two exact retained real cohorts after checking all frozen bytes."""
    _verify_real_hashes((metadata, outliers, exclusions, technical_samples, paper_samples))
    parsed_samples = _parse_metadata(metadata)
    parsed_outliers = _parse_ids(outliers, "release outlier", sorted_lf=False)
    parsed_exclusions = _parse_exclusions(exclusions)
    _parse_ids(technical_samples, "technical sample list", sorted_lf=True)
    _parse_ids(paper_samples, "paper sample list", sorted_lf=True)

    _require(len(parsed_samples) == 4_150, "real metadata must contain 4,150 samples")
    _require(sum(sample.hard_filtered for sample in parsed_samples) == 31,
             "real metadata must contain 31 hard filters")
    _require(len(parsed_outliers) == 23, "real outlier list must contain 23 samples")
    technical, paper = select_cohorts(parsed_samples, parsed_exclusions, parsed_outliers)
    _require(len(technical.samples) == 4_117 and len(paper.samples) == 4_094,
             "real cohort cardinalities do not match the frozen stages")
    technical_populations = {sample.population for sample in technical.samples}
    paper_populations = {sample.population for sample in paper.samples}
    _require(len(technical_populations) == len(paper_populations) == 80,
             "real cohorts must each retain 80 literal populations")
    _require(_KNOWN_COLLISION_IDENTITIES <= technical_populations,
             "known literal population identities were collapsed")
    _require(_encoded_cohort(technical) == technical_samples,
             "technical sample list does not match reconstructed cohort")
    _require(_encoded_cohort(paper) == paper_samples,
             "paper sample list does not match reconstructed cohort")
    return technical, paper
