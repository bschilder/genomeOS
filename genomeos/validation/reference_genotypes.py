"""Apply preserved genotype count semantics (reference acquisition design §§4–5)."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Literal

from genomeos.validation.reference_cohorts import CohortColumn
from genomeos.validation.reference_vcf_tokens import CallTokens, SourceRecord, project_call

Disposition = Literal[
    "accepted",
    "missing_gt",
    "missing_gq",
    "low_gq",
    "missing_dp",
    "low_dp",
    "missing_het_ad",
    "low_het_balance",
]
Inspection = Literal["gt", "gq", "dp", "ad_missing", "ad_arity", "ad_ref", "ad_alt"]
MissingField = Literal["gt", "gq", "dp", "ad"]
MissingOrigin = Literal["literal_dot", "omitted_trailing", "absent_record_format"]

DISPOSITIONS = (
    "accepted",
    "low_dp",
    "low_gq",
    "low_het_balance",
    "missing_dp",
    "missing_gq",
    "missing_gt",
    "missing_het_ad",
)
INSPECTIONS = ("ad_alt", "ad_arity", "ad_missing", "ad_ref", "dp", "gq", "gt")
MISSING_FIELDS = ("ad", "dp", "gq", "gt")
MISSING_ORIGINS = ("absent_record_format", "literal_dot", "omitted_trailing")

_NATURAL = re.compile(r"[0-9]+\Z")
_GENOTYPE = re.compile(r"([01])[/|]([01])\Z")
_VARIANT_ID = re.compile(r"GRCh38:(chr(?:[1-9]|1[0-9]|2[0-2])):([1-9][0-9]*):([^:]+):([^:]+)\Z")
_MISSING_DISPOSITION = {
    "gt": "missing_gt",
    "gq": "missing_gq",
    "dp": "missing_dp",
    "ad": "missing_het_ad",
}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _text(value: object, field: str) -> str:
    valid = (
        isinstance(value, str)
        and bool(value)
        and value == value.strip()
        and not any(character in value for character in "\t\n\r\0")
    )
    _require(valid, f"invalid {field}")
    return value


def _count(value: object, field: str) -> int:
    _require(type(value) is int and value >= 0, f"{field} must be an integer >= 0")
    return value


def _natural(token: str, field: str) -> int:
    _require(isinstance(token, str) and _NATURAL.fullmatch(token) is not None, f"invalid {field}")
    return int(token)


def _genotype(token: str) -> int | None:
    _require(isinstance(token, str), "invalid GT")
    if token in (".", "./.", ".|."):
        return None
    match = _GENOTYPE.fullmatch(token)
    _require(match is not None, "invalid GT")
    return int(match.group(1)) + int(match.group(2))


def _positive_pairs(
    value: object,
    *,
    field: str,
    allowed: tuple[str, ...],
) -> dict[str, int]:
    _require(type(value) is tuple, f"{field} must be a tuple")
    pairs: list[tuple[str, int]] = []
    for entry in value:
        _require(type(entry) is tuple and len(entry) == 2, f"invalid {field} entry")
        key = _text(entry[0], f"{field} key")
        count = _count(entry[1], f"{field} count")
        _require(key in allowed and count > 0, f"invalid {field} counter")
        pairs.append((key, count))
    _require(tuple(pairs) == tuple(sorted(pairs)), f"{field} must be key-sorted")
    _require(len({key for key, _ in pairs}) == len(pairs), f"{field} keys must be unique")
    return dict(pairs)


@dataclass(frozen=True)
class NativeVariantTokens:
    variant_id: str
    sample_ids: tuple[str, ...]
    tokens: tuple[str, ...]

    def __post_init__(self) -> None:
        _require(isinstance(self.variant_id, str) and _VARIANT_ID.fullmatch(self.variant_id) is not None,
                 "invalid native variant ID")
        _require(type(self.sample_ids) is tuple and type(self.tokens) is tuple,
                 "native IDs and tokens must be tuples")
        for sample_id in self.sample_ids:
            _text(sample_id, "native sample ID")
        for token in self.tokens:
            _text(token, "native sample token")
        _require(len(self.sample_ids) == len(self.tokens), "native sample ID/token length mismatch")
        _require(len(self.sample_ids) == len(set(self.sample_ids)), "native sample IDs must be unique")


@dataclass(frozen=True)
class MissingOriginCount:
    field: MissingField
    origin: MissingOrigin
    count: int

    def __post_init__(self) -> None:
        _require(self.field in MISSING_FIELDS, "invalid missing-origin field")
        _require(self.origin in MISSING_ORIGINS, "invalid missing-origin state")
        _require(_count(self.count, "missing-origin count") > 0, "missing-origin count must be positive")


@dataclass(frozen=True)
class CallAssessment:
    dosage: int | None
    disposition: Disposition
    inspected_fields: tuple[Inspection, ...]

    def __post_init__(self) -> None:
        _require(self.disposition in DISPOSITIONS, "invalid call disposition")
        _require(
            self.dosage is None or (type(self.dosage) is int and 0 <= self.dosage <= 2),
            "invalid call dosage",
        )
        _require((self.dosage is None) == (self.disposition == "missing_gt"), "dosage/disposition mismatch")
        _require(type(self.inspected_fields) is tuple, "inspected fields must be a tuple")
        _require(all(field in INSPECTIONS for field in self.inspected_fields), "invalid inspected field")
        _require(self.inspected_fields and self.inspected_fields[0] == "gt", "GT must be inspected first")


@dataclass(frozen=True)
class PopulationCount:
    population: str
    region: str
    sample_count: int
    called_ac: int
    called_an: int
    quality_ac: int
    quality_an: int

    def __post_init__(self) -> None:
        _text(self.population, "population")
        _text(self.region, "region")
        sample_count = _count(self.sample_count, "sample_count")
        called_ac = _count(self.called_ac, "called_ac")
        called_an = _count(self.called_an, "called_an")
        quality_ac = _count(self.quality_ac, "quality_ac")
        quality_an = _count(self.quality_an, "quality_an")
        _require(called_an % 2 == 0 and quality_an % 2 == 0, "allele numbers must be even")
        _require(quality_ac <= called_ac <= called_an <= 2 * sample_count, "invalid called allele counts")
        _require(quality_ac <= quality_an <= called_an, "invalid quality allele counts")


@dataclass
class _PopulationAccumulator:
    region: str
    sample_count: int = 0
    called_ac: int = 0
    called_an: int = 0
    quality_ac: int = 0
    quality_an: int = 0


@dataclass(frozen=True)
class QcTally:
    dispositions: tuple[tuple[str, int], ...]
    inspection_totals: tuple[tuple[str, int], ...]
    missing_origins: tuple[MissingOriginCount, ...]

    def __post_init__(self) -> None:
        dispositions = _positive_pairs(self.dispositions, field="dispositions", allowed=DISPOSITIONS)
        inspections = _positive_pairs(self.inspection_totals, field="inspection totals", allowed=INSPECTIONS)
        _require(type(self.missing_origins) is tuple, "missing origins must be a tuple")
        _require(
            all(type(value) is MissingOriginCount for value in self.missing_origins),
            "invalid missing-origin entry",
        )
        missing_keys = tuple((value.field, value.origin) for value in self.missing_origins)
        _require(missing_keys == tuple(sorted(missing_keys)), "missing origins must be sorted")
        _require(len(missing_keys) == len(set(missing_keys)), "missing origins must be unique")

        disposition_total = sum(dispositions.values())
        _require(inspections.get("gt", 0) == disposition_total, "GT inspection coverage mismatch")
        gq_expected = disposition_total - dispositions.get("missing_gt", 0)
        _require(inspections.get("gq", 0) == gq_expected, "GQ inspection coverage mismatch")
        dp_expected = gq_expected - dispositions.get("missing_gq", 0) - dispositions.get("low_gq", 0)
        _require(inspections.get("dp", 0) == dp_expected, "DP inspection coverage mismatch")
        ad_missing = inspections.get("ad_missing", 0)
        ad_arity = inspections.get("ad_arity", 0)
        ad_ref = inspections.get("ad_ref", 0)
        ad_alt = inspections.get("ad_alt", 0)
        _require(
            ad_arity == ad_missing - dispositions.get("missing_het_ad", 0),
            "AD missing/arity coverage mismatch",
        )
        _require(ad_ref == ad_arity, "AD reference coverage mismatch")
        _require(0 <= ad_alt <= ad_ref, "AD alternate coverage mismatch")
        low_balance = dispositions.get("low_het_balance", 0)
        _require(ad_ref - ad_alt <= low_balance, "AD short-circuit coverage mismatch")
        _require(0 <= ad_ref - low_balance <= dispositions.get("accepted", 0),
                 "AD acceptance coverage mismatch")

        missing_totals: Counter[str] = Counter()
        for value in self.missing_origins:
            missing_totals[value.field] += value.count
        for field, disposition in _MISSING_DISPOSITION.items():
            _require(
                missing_totals[field] == dispositions.get(disposition, 0),
                f"{field} missing-origin coverage mismatch",
            )


@dataclass(frozen=True)
class VariantCounts:
    variant_id: str
    populations: tuple[PopulationCount, ...]
    qc: QcTally

    def __post_init__(self) -> None:
        _require(isinstance(self.variant_id, str) and _VARIANT_ID.fullmatch(self.variant_id) is not None,
                 "invalid variant ID")
        _require(type(self.populations) is tuple, "populations must be a tuple")
        _require(
            all(type(value) is PopulationCount for value in self.populations),
            "invalid population count",
        )
        keys = tuple((value.population, value.region) for value in self.populations)
        _require(keys == tuple(sorted(keys)), "population counts must be sorted")
        _require(len({value.population for value in self.populations}) == len(self.populations),
                 "population counts must have unique population IDs")
        _require(type(self.qc) is QcTally, "qc must be QcTally")
        dispositions = dict(self.qc.dispositions)
        samples = sum(value.sample_count for value in self.populations)
        called_an = sum(value.called_an for value in self.populations)
        quality_an = sum(value.quality_an for value in self.populations)
        _require(sum(dispositions.values()) == samples, "dispositions do not cover the cohort")
        _require(called_an == 2 * (samples - dispositions.get("missing_gt", 0)), "called AN mismatch")
        _require(quality_an == 2 * dispositions.get("accepted", 0), "quality AN mismatch")


def assess_call(gt: str, gq: str, dp: str, ad: str) -> CallAssessment:
    """Apply the frozen sequential QC tree to unnormalized original lexemes."""
    inspected: list[Inspection] = ["gt"]
    dosage = _genotype(gt)
    if dosage is None:
        return CallAssessment(None, "missing_gt", tuple(inspected))

    inspected.append("gq")
    if gq == ".":
        return CallAssessment(dosage, "missing_gq", tuple(inspected))
    if _natural(gq, "GQ") < 20:
        return CallAssessment(dosage, "low_gq", tuple(inspected))

    inspected.append("dp")
    if dp == ".":
        return CallAssessment(dosage, "missing_dp", tuple(inspected))
    depth = _natural(dp, "DP")
    if depth < 10:
        return CallAssessment(dosage, "low_dp", tuple(inspected))
    if dosage != 1:
        return CallAssessment(dosage, "accepted", tuple(inspected))

    inspected.append("ad_missing")
    alleles = ad.split(",")
    if "." in alleles:
        return CallAssessment(dosage, "missing_het_ad", tuple(inspected))
    inspected.append("ad_arity")
    _require(len(alleles) == 2, "invalid AD arity")
    for field, token in zip(("ad_ref", "ad_alt"), alleles, strict=True):
        inspected.append(field)
        if _natural(token, field) * 5 < depth:
            return CallAssessment(dosage, "low_het_balance", tuple(inspected))
    return CallAssessment(dosage, "accepted", tuple(inspected))


def _validate_columns(record: SourceRecord, columns: tuple[CohortColumn, ...]) -> None:
    _require(type(columns) is tuple, "cohort columns must be a tuple")
    _require(all(type(column) is CohortColumn for column in columns), "invalid cohort column")
    ids: set[str] = set()
    indices: set[int] = set()
    regions: dict[str, str] = {}
    for column in columns:
        _require(column.sample_id not in ids and column.sample_index not in indices,
                 "duplicate cohort column identity")
        _require(column.sample_index < len(record.sample_ids), "cohort source index is out of bounds")
        _require(
            record.sample_ids[column.sample_index] == column.sample_id,
            "cohort/source identity mismatch",
        )
        previous = regions.setdefault(column.population, column.region)
        _require(previous == column.region, "population has inconsistent region labels")
        ids.add(column.sample_id)
        indices.add(column.sample_index)


def _variant_id(record: SourceRecord) -> str:
    return f"GRCh38:{record.chrom}:{record.pos1}:{record.ref}:{record.alt}"


def count_variant(record: SourceRecord, columns: tuple[CohortColumn, ...]) -> VariantCounts:
    """Count called and quality alleles by exact source identity in one pass."""
    _require(type(record) is SourceRecord, "record must be SourceRecord")
    _require(
        record.filter == "PASS"
        and len(record.ref) == len(record.alt) == 1
        and record.ref != record.alt
        and record.ref in "ACGT"
        and record.alt in "ACGT",
        "record is not a retained A/C/G/T SNP",
    )
    _validate_columns(record, columns)
    aggregates: dict[str, _PopulationAccumulator] = {}
    dispositions: Counter[str] = Counter()
    inspections: Counter[str] = Counter()
    missing: Counter[tuple[str, str]] = Counter()
    for column in columns:
        values = aggregates.setdefault(column.population, _PopulationAccumulator(column.region))
        values.sample_count += 1
        call = project_call(record.format_keys, record.sample_tokens[column.sample_index])
        assessment = assess_call(call.gt, call.gq, call.dp, call.ad)
        dispositions[assessment.disposition] += 1
        inspections.update(assessment.inspected_fields)
        if assessment.dosage is not None:
            values.called_ac += assessment.dosage
            values.called_an += 2
        if assessment.disposition == "accepted":
            _require(assessment.dosage is not None, "accepted call lacks dosage")
            values.quality_ac += assessment.dosage
            values.quality_an += 2
        missing_field = next(
            (
                field
                for field, disposition in _MISSING_DISPOSITION.items()
                if disposition == assessment.disposition
            ),
            None,
        )
        if missing_field is not None:
            origin = dict(call.presence)[missing_field]
            _require(origin != "present", "missing disposition lacks explicit origin")
            missing[(missing_field, origin)] += 1

    populations = tuple(
        PopulationCount(
            population,
            values.region,
            values.sample_count,
            values.called_ac,
            values.called_an,
            values.quality_ac,
            values.quality_an,
        )
        for population, values in sorted(aggregates.items())
    )
    qc = QcTally(
        tuple(sorted((key, value) for key, value in dispositions.items() if value)),
        tuple(sorted((key, value) for key, value in inspections.items() if value)),
        tuple(MissingOriginCount(field, origin, count) for (field, origin), count in sorted(missing.items())),
    )
    return VariantCounts(_variant_id(record), populations, qc)


def _native_value(field: str, call: CallTokens) -> object:
    if field == "gt":
        return _genotype(call.gt)
    if field in ("gq", "dp"):
        token = getattr(call, field)
        return None if token == "." else _natural(token, field.upper())
    alleles = call.ad.split(",")
    if field == "ad_missing":
        return "." in alleles
    if field == "ad_arity":
        return len(alleles)
    index = 0 if field == "ad_ref" else 1
    _require(index < len(alleles), "native AD arity mismatch")
    return _natural(alleles[index], field)


def check_native_interpretation(
    record: SourceRecord,
    columns: tuple[CohortColumn, ...],
    native: NativeVariantTokens,
) -> None:
    """Compare native query values by sample ID at only original-visited nodes."""
    _require(
        type(record) is SourceRecord and type(native) is NativeVariantTokens,
        "invalid native comparison",
    )
    _validate_columns(record, columns)
    _require(native.variant_id == _variant_id(record), "native variant identity mismatch")
    expected_ids = {column.sample_id for column in columns}
    _require(set(native.sample_ids) == expected_ids, "native sample identity mismatch")
    native_by_id = dict(zip(native.sample_ids, native.tokens, strict=True))
    for column in columns:
        original = project_call(record.format_keys, record.sample_tokens[column.sample_index])
        assessment = assess_call(original.gt, original.gq, original.dp, original.ad)
        normalized = project_call(("GT", "GQ", "DP", "AD"), native_by_id[column.sample_id])
        for field in assessment.inspected_fields:
            _require(
                _native_value(field, original) == _native_value(field, normalized),
                "native token interpretation mismatch",
            )
