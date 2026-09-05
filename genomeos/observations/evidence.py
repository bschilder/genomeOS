"""Publication-evidence contracts and validation (literature design §§4–5.3).

The tables in this module are staging evidence, not P1 observations.  Nulls preserve unfinished
curation; explicit field-state rows explain every value or absence.  Status fields are recomputed
from that evidence so neither a caller nor an extraction agent can self-certify a record.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, date, datetime
from typing import Any
from urllib.parse import urlsplit

import pandas as pd
import pandera.pandas as pa
from pandas.api.types import is_bool

from genomeos.observations.schema import SAMPLING_DESIGNS, VARIANT_ID_PATTERN

LITERATURE_SEARCH_COLUMNS = (
    "search_id", "corpus_id", "database", "query", "executed_at", "candidate_id",
    "decision", "decision_reason", "manifest_version",
)
LITERATURE_EVIDENCE_COLUMNS = (
    "source_record_id", "corpus_id", "variant_id", "rsid", "counted_allele",
    "normalization_status", "population_label", "sample_id", "cohort_id", "assay",
    "sampling_design", "disease_ascertainment_excluded", "date_lower", "date_upper", "an",
    "ac_lower", "ac_upper", "reported_frequency", "count_basis", "denominator_basis",
    "citation_id", "citation_text", "record_source_id", "record_locator",
    "record_source_url", "verification_status", "extraction_method", "extracted_by",
    "extracted_at", "verified_by", "verified_at", "verification_reference", "reuse_status",
    "reuse_evidence", "reuse_checked_at", "notes", "ingest_version",
)
FIELD_EVIDENCE_COLUMNS = (
    "source_record_id", "field_name", "evidence_status", "raw_value", "evidence_source_id",
    "source_locator", "checked_scope", "derivation_method", "decision_reference", "notes",
)
TRACKED_FIELDS = (
    "variant_id", "rsid", "counted_allele", "population_label", "sample_id", "cohort_id", "an",
    "ac_lower", "ac_upper", "reported_frequency", "count_basis", "denominator_basis",
    "citation_id", "citation_text", "assay", "sampling_design",
    "disease_ascertainment_excluded", "date_lower", "date_upper",
)
PROMOTION_REQUIRED_FIELDS = (
    "variant_id", "counted_allele", "population_label", "cohort_id", "an", "ac_lower",
    "ac_upper", "count_basis", "denominator_basis", "citation_id", "citation_text", "assay",
    "sampling_design", "disease_ascertainment_excluded", "date_lower", "date_upper",
)
VERIFICATION_SCIENTIFIC_FIELDS = (
    "variant_id", "counted_allele", "population_label", "cohort_id", "an", "ac_lower",
    "ac_upper", "count_basis", "denominator_basis", "assay", "sampling_design",
    "disease_ascertainment_excluded", "date_lower", "date_upper",
)
EVIDENCE_STATUSES = ("reported", "derived", "not_reported", "ambiguous", "not_reviewed")
DERIVATION_METHODS = (
    "variant_normalization", "persistent_citation_resolution",
    "alternate_count_from_reference_count", "allele_count_from_genotypes",
    "allele_denominator_from_complete_diploid_sample",
    "allele_denominator_from_hemizygous_males", "counts_from_explicit_integer_fraction",
    "controlled_vocabulary_mapping", "modern_sample_to_zero_bp",
)
_DERIVATION_OUTPUTS = {
    "variant_normalization": {"variant_id", "rsid", "counted_allele"},
    "persistent_citation_resolution": {"citation_id", "citation_text"},
    "alternate_count_from_reference_count": {"ac_lower", "ac_upper"},
    "allele_count_from_genotypes": {"ac_lower", "ac_upper"},
    "allele_denominator_from_complete_diploid_sample": {"an"},
    "allele_denominator_from_hemizygous_males": {"an"},
    "counts_from_explicit_integer_fraction": {"an", "ac_lower", "ac_upper"},
    "controlled_vocabulary_mapping": {
        "cohort_id", "count_basis", "denominator_basis", "assay", "sampling_design",
        "disease_ascertainment_excluded",
    },
    "modern_sample_to_zero_bp": {"date_lower", "date_upper"},
}

_CORPUS = r"[a-z0-9]+(?:-[a-z0-9]+)*"
_SOURCE_RECORD = rf"^literature:{_CORPUS}:[0-9a-f]{{64}}$"
_RSID = r"^rs[1-9][0-9]*$"
_COHORT = r"^cohort:[a-z0-9][a-z0-9.-]*:[a-z0-9][a-z0-9.-]*$"
_VERSION = rf"^{_CORPUS}@[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}\.[1-9][0-9]*$"
_CITATION = (
    r"^(?:pmid:[1-9][0-9]*|doi:10\.[0-9]{4,9}/\S+|"
    r"thesis:[a-z0-9][a-z0-9.-]*:[A-Za-z0-9][A-Za-z0-9._/-]*)$"
)
_REPOSITORY = (
    r"^repo:github\.com/[a-z0-9_.-]+/[a-z0-9_.-]+@[0-9a-f]{40}:[^\t\r\n]+$"
)
_SOURCE = rf"(?:{_CITATION[1:-1]}|{_REPOSITORY[1:-1]})"
_LOCATOR = r"^(?:table|figure|page|supplement|dataset-record):[^\t\r\n]+$"
_IDENTITY = (
    r"^(?:human:[a-z0-9](?:[a-z0-9-]{0,37}[a-z0-9])?|"
    r"agent:[a-z0-9][a-z0-9.-]*:[a-z0-9][a-z0-9._-]*|"
    r"import:[a-z0-9][a-z0-9._/-]*@[0-9a-f]{40})$"
)
_UTC_TIMESTAMP = r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$"
_DATE = r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
_FAKE_MISSING = frozenset({"na", "n/a", "unknown", "none", "null", "-", "tbd", "not reported"})
_PLACEHOLDER_LOCATORS = frozenset(
    {"table:unknown", "page:the-paper", "supplement:supplement", "table:the-paper"}
)


def _string(nullable: bool = False, checks: Any = None, *, unique: bool = False) -> pa.Column:
    return pa.Column(str, checks=checks, nullable=nullable, required=True, unique=unique)


LITERATURE_SEARCHES_SCHEMA = pa.DataFrameSchema(
    {
        "search_id": _string(checks=pa.Check.str_length(min_value=1)),
        "corpus_id": _string(checks=pa.Check.str_matches(rf"^{_CORPUS}$")),
        "database": _string(checks=pa.Check.isin(["pubmed"])),
        "query": _string(checks=pa.Check.str_length(min_value=1)),
        "executed_at": _string(checks=pa.Check.str_matches(_UTC_TIMESTAMP)),
        "candidate_id": _string(checks=pa.Check.str_matches(r"^pmid:[1-9][0-9]*$")),
        "decision": _string(checks=pa.Check.isin(["included", "excluded", "pending"])),
        "decision_reason": _string(nullable=True),
        "manifest_version": _string(checks=pa.Check.str_matches(_VERSION)),
    },
    strict=True,
    ordered=True,
    coerce=True,
    unique=["search_id", "candidate_id"],
    name="literature_searches",
)

LITERATURE_EVIDENCE_SCHEMA = pa.DataFrameSchema(
    {
        "source_record_id": _string(checks=pa.Check.str_matches(_SOURCE_RECORD), unique=True),
        "corpus_id": _string(checks=pa.Check.str_matches(rf"^{_CORPUS}$")),
        "variant_id": _string(nullable=True, checks=pa.Check.str_matches(VARIANT_ID_PATTERN)),
        "rsid": _string(nullable=True, checks=pa.Check.str_matches(_RSID)),
        "counted_allele": _string(nullable=True, checks=pa.Check.str_matches(r"^[ACGT]+$")),
        "normalization_status": _string(
            checks=pa.Check.isin(["verified", "ambiguous", "unresolved"])
        ),
        "population_label": _string(checks=pa.Check.str_length(min_value=1)),
        "sample_id": _string(nullable=True, checks=pa.Check.str_length(min_value=1)),
        "cohort_id": _string(nullable=True, checks=pa.Check.str_matches(_COHORT)),
        "assay": _string(nullable=True, checks=pa.Check.str_length(min_value=1)),
        "sampling_design": _string(nullable=True, checks=pa.Check.isin(SAMPLING_DESIGNS)),
        "disease_ascertainment_excluded": pa.Column("boolean", nullable=True, required=True),
        "date_lower": pa.Column("Int64", pa.Check.ge(0), nullable=True, required=True),
        "date_upper": pa.Column("Int64", pa.Check.ge(0), nullable=True, required=True),
        "an": pa.Column("Int64", pa.Check.gt(0), nullable=True, required=True),
        "ac_lower": pa.Column("Int64", pa.Check.ge(0), nullable=True, required=True),
        "ac_upper": pa.Column("Int64", pa.Check.ge(0), nullable=True, required=True),
        "reported_frequency": _string(nullable=True, checks=pa.Check.str_length(min_value=1)),
        "count_basis": _string(
            nullable=True,
            checks=pa.Check.isin(["reported", "genotype_derived", "frequency_reconstructed"]),
        ),
        "denominator_basis": _string(
            nullable=True,
            checks=pa.Check.isin(
                ["reported_alleles", "diploid_individuals", "hemizygous_males"]
            ),
        ),
        "citation_id": _string(nullable=True, checks=pa.Check.str_matches(_CITATION)),
        "citation_text": _string(nullable=True, checks=pa.Check.str_length(min_value=1)),
        "record_source_id": _string(checks=pa.Check.str_matches(_SOURCE)),
        "record_locator": _string(checks=pa.Check.str_matches(_LOCATOR)),
        "record_source_url": _string(nullable=True, checks=pa.Check.str_matches(r"^https://")),
        "verification_status": _string(
            checks=pa.Check.isin(
                ["original_source_verified", "compilation_verified", "pending"]
            )
        ),
        "extraction_method": _string(
            checks=pa.Check.isin(
                ["manual_transcription", "structured_table", "ocr_reviewed", "automated_proposal"]
            )
        ),
        "extracted_by": _string(checks=pa.Check.str_matches(_IDENTITY)),
        "extracted_at": _string(checks=pa.Check.str_matches(_UTC_TIMESTAMP)),
        "verified_by": _string(nullable=True, checks=pa.Check.str_matches(_IDENTITY)),
        "verified_at": _string(nullable=True, checks=pa.Check.str_matches(_UTC_TIMESTAMP)),
        "verification_reference": _string(nullable=True, checks=pa.Check.str_length(min_value=1)),
        "reuse_status": _string(
            checks=pa.Check.isin(
                [
                    "explicitly_open", "permission_granted", "no_restriction_found",
                    "restricted", "not_checked",
                ]
            )
        ),
        "reuse_evidence": _string(nullable=True, checks=pa.Check.str_length(min_value=1)),
        "reuse_checked_at": _string(nullable=True, checks=pa.Check.str_matches(_DATE)),
        "notes": _string(nullable=True, checks=pa.Check.str_length(min_value=1)),
        "ingest_version": _string(checks=pa.Check.str_matches(_VERSION)),
    },
    strict=True,
    ordered=True,
    coerce=True,
    name="literature_evidence",
)

LITERATURE_FIELD_EVIDENCE_SCHEMA = pa.DataFrameSchema(
    {
        "source_record_id": _string(checks=pa.Check.str_matches(_SOURCE_RECORD)),
        "field_name": _string(checks=pa.Check.isin(TRACKED_FIELDS)),
        "evidence_status": _string(checks=pa.Check.isin(EVIDENCE_STATUSES)),
        "raw_value": _string(nullable=True, checks=pa.Check.str_length(min_value=1)),
        "evidence_source_id": _string(nullable=True, checks=pa.Check.str_matches(_SOURCE)),
        "source_locator": _string(nullable=True, checks=pa.Check.str_matches(_LOCATOR)),
        "checked_scope": _string(nullable=True, checks=pa.Check.str_length(min_value=1)),
        "derivation_method": _string(nullable=True, checks=pa.Check.isin(DERIVATION_METHODS)),
        "decision_reference": _string(nullable=True, checks=pa.Check.str_matches(r"^https://github\.com/")),
        "notes": _string(nullable=True, checks=pa.Check.str_length(min_value=1)),
    },
    strict=True,
    ordered=True,
    coerce=True,
    unique=["source_record_id", "field_name"],
    name="literature_field_evidence",
)


def make_source_record_id(corpus_id: str, record_source_id: str, record_locator: str) -> str:
    """Return the immutable literature record identity defined by design §5.2.1."""
    digest = hashlib.sha256(f"{record_source_id}\n{record_locator}".encode()).hexdigest()
    return f"literature:{corpus_id}:{digest}"


def _is_null(value: object) -> bool:
    return bool(pd.isna(value))


def _canonical_json(value: str, expected_type: type) -> Any:
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("structured evidence must be valid JSON") from exc
    if not isinstance(parsed, expected_type):
        raise ValueError(f"structured evidence must be a JSON {expected_type.__name__}")
    if json.dumps(parsed, sort_keys=True, separators=(",", ":")) != value:
        raise ValueError("structured evidence must use canonical JSON")
    return parsed


def _validate_timestamp(value: str) -> None:
    parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    if parsed > datetime.now(UTC):
        raise ValueError("timestamps may not be in the future")


def _validate_date(value: str) -> None:
    parsed = date.fromisoformat(value)
    if parsed > datetime.now(UTC).date():
        raise ValueError("dates may not be in the future")


def _require_https_url(value: object, field: str) -> None:
    parsed = urlsplit(str(value))
    if parsed.scheme != "https" or not parsed.netloc or parsed.hostname in {
        "localhost", "127.0.0.1",
    }:
        raise ValueError(f"{field} must be an absolute non-local HTTPS URL")


def _validate_text_and_anchors(evidence: pd.DataFrame, fields: pd.DataFrame) -> None:
    for frame in (evidence, fields):
        for column in frame.select_dtypes(include=["object", "string"]).columns:
            for value in frame[column].dropna():
                text = str(value)
                if text != text.strip() or any(char in text for char in "\t\r\n"):
                    raise ValueError(f"{column} contains surrounding or control whitespace")
                if text.casefold() in _FAKE_MISSING:
                    raise ValueError(f"{column} contains fake missingness: {text!r}")
    for locator in pd.concat([evidence["record_locator"], fields["source_locator"]]).dropna():
        if str(locator).casefold() in _PLACEHOLDER_LOCATORS:
            raise ValueError(f"placeholder source locator: {locator}")
    for value in evidence["citation_id"].dropna():
        if str(value).startswith("doi:") and str(value) != str(value).lower():
            raise ValueError("DOI citation_id must be lowercase")
    for value in evidence["record_source_url"].dropna():
        parsed = urlsplit(str(value))
        if parsed.scheme != "https" or not parsed.netloc or parsed.query or parsed.fragment:
            raise ValueError("record_source_url must be a stable absolute HTTPS URL")
        if parsed.hostname in {"localhost", "127.0.0.1"}:
            raise ValueError("record_source_url may not be local")


def _typed_literal(value: object) -> str:
    if is_bool(value):
        return str(value).lower()
    if isinstance(value, int):
        return str(value)
    return str(value)


def _validate_derived_value(main: pd.Series, item: object) -> None:
    field = item.field_name
    method = item.derivation_method
    if field not in _DERIVATION_OUTPUTS[method]:
        raise ValueError(f"{field}: derivation method {method} cannot produce this field")
    raw = item.raw_value
    expected: object
    if method == "variant_normalization":
        payload = _canonical_json(raw, dict)
        required = {"printed_alleles", "printed_build", "reference_resource", "strand"}
        if not required.issubset(payload):
            raise ValueError(f"{field}: derivation lacks normalization inputs")
        expected = payload.get(f"resolved_{field}")
    elif method == "persistent_citation_resolution":
        payload = _canonical_json(raw, dict)
        required = {"literal_reference", "matched_record", "retrieval_version"}
        if not required.issubset(payload):
            raise ValueError(f"{field}: derivation lacks citation-resolution inputs")
        expected = payload.get(f"resolved_{field}")
        if field == "citation_id" and payload.get("matched_record") != expected:
            raise ValueError(f"{field}: derivation did not resolve one exact record")
    elif method == "alternate_count_from_reference_count":
        payload = _canonical_json(raw, dict)
        if set(payload) != {"an", "reference_ac"} or not all(
            isinstance(payload[key], int) and not isinstance(payload[key], bool) for key in payload
        ):
            raise ValueError(f"{field}: derivation requires integer an and reference_ac")
        expected = payload["an"] - payload["reference_ac"]
    elif method == "allele_count_from_genotypes":
        payload = _canonical_json(raw, dict)
        allele = main["counted_allele"]
        if not payload or not isinstance(allele, str) or len(allele) != 1:
            raise ValueError(f"{field}: derivation requires one counted base and genotype counts")
        if not all(
            isinstance(genotype, str)
            and len(genotype) == 2
            and set(genotype) <= {"A", "C", "G", "T"}
            and isinstance(count, int)
            and not isinstance(count, bool)
            and count >= 0
            for genotype, count in payload.items()
        ):
            raise ValueError(f"{field}: derivation requires exact diploid genotype counts")
        expected = sum(genotype.count(allele) * count for genotype, count in payload.items())
    elif method == "allele_denominator_from_complete_diploid_sample":
        payload = _canonical_json(raw, dict)
        if set(payload) != {"autosomal", "called_individuals", "complete_calls"}:
            raise ValueError(f"{field}: derivation requires complete diploid-call evidence")
        if payload["autosomal"] is not True or payload["complete_calls"] is not True:
            raise ValueError(f"{field}: derivation cannot assume autosomal complete calls")
        if str(main["variant_id"]).startswith("chrX-"):
            raise ValueError(f"{field}: diploid autosomal derivation cannot be used on chrX")
        if not isinstance(payload["called_individuals"], int) or isinstance(
            payload["called_individuals"], bool
        ):
            raise ValueError(f"{field}: called_individuals must be an integer")
        expected = 2 * payload["called_individuals"]
    elif method == "allele_denominator_from_hemizygous_males":
        payload = _canonical_json(raw, dict)
        if set(payload) != {"called_males", "hemizygous_x_linked"}:
            raise ValueError(f"{field}: derivation requires X-linked male-call evidence")
        if payload["hemizygous_x_linked"] is not True or not isinstance(
            payload["called_males"], int
        ) or isinstance(payload["called_males"], bool):
            raise ValueError(f"{field}: derivation cannot assume hemizygosity")
        if not str(main["variant_id"]).startswith("chrX-"):
            raise ValueError(f"{field}: hemizygous-male derivation requires a chrX variant")
        expected = payload["called_males"]
    elif method == "counts_from_explicit_integer_fraction":
        match = re.fullmatch(r"(0|[1-9][0-9]*)/([1-9][0-9]*)", raw)
        if match is None:
            raise ValueError(f"{field}: derivation requires a literal integer fraction")
        numerator, denominator = (int(part) for part in match.groups())
        expected = denominator if field == "an" else numerator
    elif method == "controlled_vocabulary_mapping":
        payload = _canonical_json(raw, dict)
        if set(payload) != {"mapping_key", "source_value", "value"}:
            raise ValueError(f"{field}: derivation requires one versioned exact mapping")
        if not all(
            isinstance(payload[key], str) and payload[key]
            for key in ("mapping_key", "source_value")
        ) or payload["value"] is None:
            raise ValueError(f"{field}: derivation requires one versioned exact mapping")
        expected = payload["value"]
    else:
        if raw.casefold() in _FAKE_MISSING:
            raise ValueError(f"{field}: derivation requires located evidence of a modern sample")
        expected = 0
    if _typed_literal(main[field]) != _typed_literal(expected):
        raise ValueError(f"{field}: derived cell is not exactly recomputable from raw_value")


def _validate_field_rows(evidence: pd.DataFrame, fields: pd.DataFrame) -> None:
    source_ids = set(evidence["source_record_id"])
    if not set(fields["source_record_id"]).issubset(source_ids):
        raise ValueError("field evidence contains orphan source_record_id")
    for source_id in source_ids:
        group = fields.loc[fields["source_record_id"] == source_id]
        if len(group) != len(TRACKED_FIELDS) or set(group["field_name"]) != set(TRACKED_FIELDS):
            raise ValueError(f"{source_id} must have exactly 19 field-evidence rows")
        main = evidence.loc[evidence["source_record_id"] == source_id].iloc[0]
        for item in group.itertuples(index=False):
            status = item.evidence_status
            cell = main[item.field_name]
            if status in {"reported", "derived"}:
                if _is_null(cell) or _is_null(item.raw_value) or _is_null(item.evidence_source_id):
                    raise ValueError(f"{item.field_name}: resolved evidence requires a value and source")
                if _is_null(item.source_locator) or not _is_null(item.checked_scope):
                    raise ValueError(f"{item.field_name}: resolved evidence requires only a locator")
                if status == "reported":
                    if not _is_null(item.derivation_method):
                        raise ValueError(f"{item.field_name}: reported evidence cannot name a derivation")
                    if _typed_literal(cell) != item.raw_value:
                        raise ValueError(f"{item.field_name}: reported raw_value does not equal the cell")
                elif _is_null(item.derivation_method) or _is_null(item.decision_reference):
                    raise ValueError(f"{item.field_name}: derived evidence needs method and decision")
                else:
                    _validate_derived_value(main, item)
            elif status == "not_reported":
                if not _is_null(cell) or not _is_null(item.raw_value) or _is_null(item.evidence_source_id):
                    raise ValueError(f"{item.field_name}: not_reported must preserve a blank cell")
                if not _is_null(item.source_locator) or _is_null(item.checked_scope):
                    raise ValueError(f"{item.field_name}: not_reported needs checked_scope, not a locator")
                scope = _canonical_json(item.checked_scope, list)
                if not scope or scope != sorted(set(scope)) or not all(
                    isinstance(locator, str) and re.fullmatch(_LOCATOR, locator) for locator in scope
                ):
                    raise ValueError(f"{item.field_name}: checked_scope must be sorted exact locators")
                if not _is_null(item.derivation_method) or not _is_null(item.decision_reference):
                    raise ValueError(f"{item.field_name}: not_reported cannot name a derivation")
            elif status == "ambiguous":
                if not _is_null(cell) or _is_null(item.raw_value) or _is_null(item.evidence_source_id):
                    raise ValueError(f"{item.field_name}: ambiguous evidence needs raw located text")
                if _is_null(item.source_locator) or not _is_null(item.checked_scope):
                    raise ValueError(f"{item.field_name}: ambiguous evidence needs one value locator")
                if not _is_null(item.derivation_method):
                    raise ValueError(f"{item.field_name}: ambiguous evidence cannot name a derivation")
            else:
                absent = (
                    cell, item.raw_value, item.evidence_source_id, item.source_locator,
                    item.checked_scope, item.derivation_method, item.decision_reference,
                )
                if not all(_is_null(value) for value in absent):
                    raise ValueError(f"{item.field_name}: not_reviewed must contain no claimed evidence")
            if status in {"not_reported", "ambiguous", "not_reviewed"} and _is_null(item.notes):
                raise ValueError(f"{item.field_name}: unresolved evidence requires explanatory notes")


def _computed_normalization(main: pd.Series, field_rows: pd.DataFrame) -> str:
    states = field_rows.set_index("field_name")["evidence_status"]
    if "ambiguous" in {states["variant_id"], states["counted_allele"]}:
        return "ambiguous"
    resolved = {"reported", "derived"}
    if states["variant_id"] not in resolved or states["counted_allele"] not in resolved:
        return "unresolved"
    if _is_null(main["variant_id"]) or _is_null(main["counted_allele"]):
        return "unresolved"
    return "verified" if str(main["variant_id"]).rsplit("-", 1)[-1] == main["counted_allele"] else "ambiguous"


def _sample_required(evidence: pd.DataFrame, index: int) -> bool:
    row = evidence.loc[index]
    keys = ["citation_id", "population_label", "cohort_id", "variant_id"]
    matches = pd.Series(True, index=evidence.index)
    for key in keys:
        matches &= evidence[key].eq(row[key])
    return int(matches.sum()) > 1


def _validate_conditional_samples(evidence: pd.DataFrame) -> None:
    keys = ["citation_id", "population_label", "cohort_id", "variant_id"]
    for _, group in evidence.groupby(keys, dropna=False):
        if len(group) <= 1:
            continue
        if group["sample_id"].isna().any() or not group["sample_id"].is_unique:
            raise ValueError(
                "sample_id is required and must be distinct for separately reported "
                "measurements of one citation/population/cohort/variant"
            )


def _computed_verification(main: pd.Series, field_rows: pd.DataFrame, sample_required: bool) -> str:
    states = field_rows.set_index("field_name")["evidence_status"]
    required = [*PROMOTION_REQUIRED_FIELDS, *(["sample_id"] if sample_required else [])]
    resolved = all(
        states[field] in {"reported", "derived"} and not _is_null(main[field])
        for field in required
    )
    verifier = not _is_null(main["verified_by"]) and not _is_null(main["verified_at"])
    verifier = verifier and not _is_null(main["verification_reference"])
    if not resolved or not verifier:
        return "pending"
    scientific = [*VERIFICATION_SCIENTIFIC_FIELDS, *(["sample_id"] if sample_required else [])]
    sources = field_rows.set_index("field_name")["evidence_source_id"]
    return (
        "original_source_verified"
        if all(sources[field] == main["citation_id"] for field in scientific)
        else "compilation_verified"
    )


def _validate_reuse(main: pd.Series, field_rows: pd.DataFrame) -> tuple[str, object]:
    contributing = {main["record_source_id"], *field_rows["evidence_source_id"].dropna()}
    if _is_null(main["reuse_evidence"]):
        return "not_checked", pd.NA
    payload = _canonical_json(main["reuse_evidence"], dict)
    if set(payload) != {"checks"} or not isinstance(payload["checks"], list):
        raise ValueError("reuse_evidence must contain only a checks array")
    checks = payload["checks"]
    if not checks:
        raise ValueError("reuse_evidence checks may not be empty")
    source_order = [check.get("source_id") for check in checks if isinstance(check, dict)]
    if source_order != sorted(set(source_order)):
        raise ValueError("reuse checks must be unique and sorted by source_id")
    if not set(source_order).issubset(contributing):
        raise ValueError("reuse checks include a non-contributing source")
    findings: list[str] = []
    dates: list[str] = []
    required_keys = {
        "explicitly_open": {"checked_at", "finding", "licence", "source_id", "terms_url"},
        "permission_granted": {
            "checked_at", "finding", "permission_reference", "scope", "source_id",
        },
        "no_restriction_found": {
            "checked_at", "finding", "source_id", "surfaces",
        },
        "restricted": {
            "checked_at", "finding", "restriction", "source_id", "terms_url",
        },
    }
    for check in checks:
        if not isinstance(check, dict) or check.get("finding") not in required_keys:
            raise ValueError("reuse check has an unsupported finding")
        finding = check["finding"]
        if set(check) != required_keys[finding]:
            raise ValueError(f"reuse {finding} check has missing or extra keys")
        _validate_date(check["checked_at"])
        dates.append(check["checked_at"])
        findings.append(finding)
        if finding == "no_restriction_found":
            surfaces = check["surfaces"]
            if not surfaces or surfaces != sorted(set(surfaces)) or not all(
                isinstance(url, str) for url in surfaces
            ):
                raise ValueError("no-restriction checks require sorted HTTPS surfaces")
            for url in surfaces:
                _require_https_url(url, "surfaces")
        if finding in {"explicitly_open", "restricted"}:
            _require_https_url(check["terms_url"], "terms_url")
        if finding == "permission_granted":
            _require_https_url(check["permission_reference"], "permission_reference")
        if finding == "permission_granted" and check["scope"] != (
            "public redistribution and downstream reuse"
        ):
            raise ValueError("permission scope must cover public redistribution and downstream reuse")
    if "restricted" in findings:
        status = "restricted"
    elif set(source_order) != contributing:
        status = "not_checked"
    elif "permission_granted" in findings:
        status = "permission_granted"
    elif set(findings) == {"explicitly_open"}:
        status = "explicitly_open"
    else:
        status = "no_restriction_found"
    return status, max(dates)


def validate_literature_tables(
    evidence: pd.DataFrame, field_evidence: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Validate both ledgers and prove that every stored status is evidence-derived."""
    validated = LITERATURE_EVIDENCE_SCHEMA.validate(evidence).reset_index(drop=True)
    fields = LITERATURE_FIELD_EVIDENCE_SCHEMA.validate(field_evidence).reset_index(drop=True)
    _validate_text_and_anchors(validated, fields)
    _validate_field_rows(validated, fields)
    _validate_conditional_samples(validated)
    for index, main in validated.iterrows():
        expected_id = make_source_record_id(
            main["corpus_id"], main["record_source_id"], main["record_locator"]
        )
        if main["source_record_id"] != expected_id:
            raise ValueError("source_record_id does not match its immutable record anchor")
        if not main["source_record_id"].startswith(f"literature:{main['corpus_id']}:"):
            raise ValueError("source_record_id corpus does not match corpus_id")
        if not main["ingest_version"].startswith(f"{main['corpus_id']}@"):
            raise ValueError("ingest_version corpus does not match corpus_id")
        if main[["an", "ac_lower", "ac_upper"]].notna().any():
            if main[["an", "ac_lower", "ac_upper"]].isna().any():
                raise ValueError("count bounds and denominator must be supplied together")
            if not 0 <= main["ac_lower"] <= main["ac_upper"] <= main["an"]:
                raise ValueError("count interval must satisfy 0 <= lower <= upper <= an")
        if main[["date_lower", "date_upper"]].notna().any():
            if main[["date_lower", "date_upper"]].isna().any():
                raise ValueError("date bounds must be supplied together")
            if main["date_lower"] > main["date_upper"]:
                raise ValueError("date_lower must not exceed date_upper")
        _validate_timestamp(main["extracted_at"])
        if not _is_null(main["verified_at"]):
            _validate_timestamp(main["verified_at"])
        rows = fields.loc[fields["source_record_id"] == main["source_record_id"]]
        normalization = _computed_normalization(main, rows)
        if main["normalization_status"] != normalization:
            raise ValueError("normalization_status disagrees with field evidence")
        verification = _computed_verification(main, rows, _sample_required(validated, index))
        if main["verification_status"] != verification:
            raise ValueError("verification_status disagrees with field evidence")
        verifier_values = main[["verified_by", "verified_at", "verification_reference"]]
        if verification == "pending" and verifier_values.notna().any():
            raise ValueError("pending rows may not claim verifier metadata")
        if verification != "pending" and main["verified_by"] == main["extracted_by"]:
            raise ValueError("verified_by must be independent from extracted_by")
        reuse_status, reuse_date = _validate_reuse(main, rows)
        if main["reuse_status"] != reuse_status:
            raise ValueError("reuse_status disagrees with source-specific checks")
        if (_is_null(main["reuse_checked_at"]) and not _is_null(reuse_date)) or (
            not _is_null(main["reuse_checked_at"]) and main["reuse_checked_at"] != reuse_date
        ):
            raise ValueError("reuse_checked_at must equal the latest reuse check")
    return validated, fields


def validate_search_manifest(frame: pd.DataFrame) -> pd.DataFrame:
    """Validate a reproducible discovery manifest without making screening decisions."""
    validated = LITERATURE_SEARCHES_SCHEMA.validate(frame).reset_index(drop=True)
    for row in validated.itertuples(index=False):
        _validate_timestamp(row.executed_at)
        if not row.manifest_version.startswith(f"{row.corpus_id}@"):
            raise ValueError("manifest_version corpus does not match corpus_id")
        if row.decision == "excluded" and _is_null(row.decision_reason):
            raise ValueError("excluded candidates require decision_reason")
        if row.decision == "pending" and not _is_null(row.decision_reason):
            raise ValueError("pending candidates may not have decision_reason")
    return validated
