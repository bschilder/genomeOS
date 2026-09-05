"""Contract tests for publication evidence (literature design §§5.1–5.3)."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pandera.errors
import pytest

from genomeos.observations.evidence import (
    FIELD_EVIDENCE_COLUMNS,
    LITERATURE_EVIDENCE_COLUMNS,
    LITERATURE_SEARCH_COLUMNS,
    TRACKED_FIELDS,
    make_source_record_id,
    validate_literature_tables,
    validate_search_manifest,
)

SOURCE_RECORD_ID = (
    "literature:lct-rs4988235:"
    "f5fd55995c17abf484c03ca85bb786b2710ab49556baad33ad8e1099caa53afe"
)
FIXTURES = Path(__file__).parent / "fixtures" / "literature"


def _read_tsv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, sep="\t", keep_default_na=False).replace("", pd.NA)


def _evidence_row(**overrides: object) -> pd.DataFrame:
    reuse = {
        "checks": [
            {
                "checked_at": "2026-09-04",
                "finding": "no_restriction_found",
                "source_id": "pmid:29063188",
                "surfaces": ["https://pubmed.ncbi.nlm.nih.gov/29063188/"],
            }
        ]
    }
    row: dict[str, object] = {
        "source_record_id": SOURCE_RECORD_ID,
        "corpus_id": "lct-rs4988235",
        "variant_id": "chr2-135851076-G-A",
        "rsid": "rs4988235",
        "counted_allele": "A",
        "normalization_status": "verified",
        "population_label": "Sami",
        "sample_id": pd.NA,
        "cohort_id": "cohort:liebert-2017:sami",
        "assay": "targeted genotyping",
        "sampling_design": "population_random",
        "disease_ascertainment_excluded": False,
        "date_lower": 0,
        "date_upper": 0,
        "an": 58,
        "ac_lower": 17,
        "ac_upper": 17,
        "reported_frequency": "17/58",
        "count_basis": "reported",
        "denominator_basis": "reported_alleles",
        "citation_id": "pmid:29063188",
        "citation_text": (
            "Liebert A et al. World-wide distributions of lactase persistence alleles "
            "and the complex effects of recombination and selection. Hum Genet. 2017."
        ),
        "record_source_id": "pmid:29063188",
        "record_locator": "table:3,row:sami",
        "record_source_url": "https://pubmed.ncbi.nlm.nih.gov/29063188/",
        "verification_status": "original_source_verified",
        "extraction_method": "manual_transcription",
        "extracted_by": "human:curator",
        "extracted_at": "2026-09-04T10:00:00Z",
        "verified_by": "human:reviewer",
        "verified_at": "2026-09-04T11:00:00Z",
        "verification_reference": "https://github.com/bschilder/genomeOS/issues/149",
        "reuse_status": "no_restriction_found",
        "reuse_evidence": json.dumps(reuse, sort_keys=True, separators=(",", ":")),
        "reuse_checked_at": "2026-09-04",
        "notes": pd.NA,
        "ingest_version": "lct-rs4988235@2026-09-05.1",
    }
    row.update(overrides)
    return pd.DataFrame([row], columns=LITERATURE_EVIDENCE_COLUMNS)


def _field_evidence() -> pd.DataFrame:
    values = _evidence_row().iloc[0]
    rows: list[dict[str, object]] = []
    for field in TRACKED_FIELDS:
        value = values[field]
        if field == "sample_id":
            rows.append(
                {
                    "source_record_id": SOURCE_RECORD_ID,
                    "field_name": field,
                    "evidence_status": "not_reported",
                    "raw_value": pd.NA,
                    "evidence_source_id": "pmid:29063188",
                    "source_locator": pd.NA,
                    "checked_scope": '["page:methods-2-4","table:3"]',
                    "derivation_method": pd.NA,
                    "decision_reference": pd.NA,
                    "notes": "No sample or stratum identifier appears in the checked sections.",
                }
            )
            continue
        rows.append(
            {
                "source_record_id": SOURCE_RECORD_ID,
                "field_name": field,
                "evidence_status": "reported",
                "raw_value": (
                    "false" if field == "disease_ascertainment_excluded" else str(value)
                ),
                "evidence_source_id": "pmid:29063188",
                "source_locator": f"table:3,row:sami,column:{field}",
                "checked_scope": pd.NA,
                "derivation_method": pd.NA,
                "decision_reference": pd.NA,
                "notes": pd.NA,
            }
        )
    return pd.DataFrame(rows, columns=FIELD_EVIDENCE_COLUMNS)


def test_contract_headers_are_exact_and_ordered():
    """Catches a reordered, omitted, or casually added public contract column."""
    assert LITERATURE_EVIDENCE_COLUMNS == (
        "source_record_id", "corpus_id", "variant_id", "rsid", "counted_allele",
        "normalization_status", "population_label", "sample_id", "cohort_id", "assay",
        "sampling_design", "disease_ascertainment_excluded", "date_lower", "date_upper",
        "an", "ac_lower", "ac_upper", "reported_frequency", "count_basis",
        "denominator_basis", "citation_id", "citation_text", "record_source_id",
        "record_locator", "record_source_url", "verification_status", "extraction_method",
        "extracted_by", "extracted_at", "verified_by", "verified_at",
        "verification_reference", "reuse_status", "reuse_evidence", "reuse_checked_at",
        "notes", "ingest_version",
    )
    assert FIELD_EVIDENCE_COLUMNS == (
        "source_record_id", "field_name", "evidence_status", "raw_value",
        "evidence_source_id", "source_locator", "checked_scope", "derivation_method",
        "decision_reference", "notes",
    )
    assert LITERATURE_SEARCH_COLUMNS == (
        "search_id", "corpus_id", "database", "query", "executed_at", "candidate_id",
        "decision", "decision_reason", "manifest_version",
    )


def test_source_record_id_uses_the_complete_immutable_anchor_hash():
    """Catches truncation or hashing mutable row content instead of the source anchor."""
    assert make_source_record_id(
        "lct-rs4988235",
        "repo:github.com/example/example@0000000000000000000000000000000000000000:data.tsv",
        "dataset-record:row-17",
    ) == (
        "literature:lct-rs4988235:"
        "7220defbe35cb5adbb8ee065f2d2460e03079f6d6cfacbc130477ca655543568"
    )


def test_complete_independently_verified_record_is_valid():
    evidence, fields = validate_literature_tables(_evidence_row(), _field_evidence())
    assert evidence.loc[0, "source_record_id"] == SOURCE_RECORD_ID
    assert len(fields) == 19


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("population_label", "unknown"),
        ("record_locator", "table:unknown"),
        ("citation_id", "doi:10.1000/UPPER"),
        ("source_record_id", "literature:lct-rs4988235:1234"),
        ("verified_by", "human:curator"),
        ("ac_upper", 59),
        ("date_lower", 1),
    ],
)
def test_dishonest_or_inconsistent_main_values_are_hard_errors(column, value):
    """Catches placeholder, identity, interval, and bound shortcuts at the staging boundary."""
    with pytest.raises((ValueError, pandera.errors.SchemaError)):
        validate_literature_tables(_evidence_row(**{column: value}), _field_evidence())


def test_missing_or_duplicate_field_evidence_is_a_hard_error():
    """Catches a ledger that creates apparent completeness by omitting field states."""
    fields = _field_evidence().iloc[:-1]
    with pytest.raises(ValueError, match="exactly 19"):
        validate_literature_tables(_evidence_row(), fields)

    duplicate = pd.concat([_field_evidence(), _field_evidence().iloc[[0]]], ignore_index=True)
    with pytest.raises((ValueError, pandera.errors.SchemaError)):
        validate_literature_tables(_evidence_row(), duplicate)


def test_stored_computed_statuses_must_agree_with_the_evidence():
    """Catches a caller self-certifying normalization, verification, or reuse."""
    for column, lie in (
        ("normalization_status", "ambiguous"),
        ("verification_status", "pending"),
        ("reuse_status", "explicitly_open"),
    ):
        with pytest.raises(ValueError, match=column):
            validate_literature_tables(_evidence_row(**{column: lie}), _field_evidence())


def test_absent_named_licence_is_admissible_when_checked_surfaces_show_no_restriction():
    """Catches the old policy of treating silence about a licence as a data block."""
    evidence, _ = validate_literature_tables(_evidence_row(), _field_evidence())
    assert evidence.loc[0, "reuse_status"] == "no_restriction_found"


def test_reuse_checks_must_cover_every_source_that_contributed_a_field():
    """Catches a compilation check being presented as coverage of an unchecked paper."""
    record_source = (
        "repo:github.com/example/example@0000000000000000000000000000000000000000:data.tsv"
    )
    evidence = _evidence_row(
        source_record_id=(
            "literature:lct-rs4988235:"
            "6a1c12a20521dfcf14de92310f5a9c36b647b84fa3e96e4c0f11c5510165bf22"
        ),
        record_source_id=record_source,
        reuse_status="not_checked",
    )
    fields = _field_evidence()
    fields["source_record_id"] = evidence.loc[0, "source_record_id"]
    validated, _ = validate_literature_tables(evidence, fields)
    assert validated.loc[0, "reuse_status"] == "not_checked"


def test_explicit_restriction_wins_even_when_another_source_was_not_checked():
    """Catches incomplete coverage accidentally overriding a known redistribution restriction."""
    record_source = (
        "repo:github.com/example/example@0000000000000000000000000000000000000000:data.tsv"
    )
    reuse = {
        "checks": [
            {
                "checked_at": "2026-09-04",
                "finding": "restricted",
                "restriction": "non-commercial reuse only",
                "source_id": record_source,
                "terms_url": "https://example.org/terms",
            }
        ]
    }
    evidence = _evidence_row(
        source_record_id=(
            "literature:lct-rs4988235:"
            "6a1c12a20521dfcf14de92310f5a9c36b647b84fa3e96e4c0f11c5510165bf22"
        ),
        record_source_id=record_source,
        reuse_status="restricted",
        reuse_evidence=json.dumps(reuse, sort_keys=True, separators=(",", ":")),
    )
    fields = _field_evidence()
    fields["source_record_id"] = evidence.loc[0, "source_record_id"]
    validated, _ = validate_literature_tables(evidence, fields)
    assert validated.loc[0, "reuse_status"] == "restricted"


def test_reuse_evidence_rejects_a_non_url_terms_reference():
    """Catches an agent replacing an inspected terms page with an unverifiable phrase."""
    reuse = {
        "checks": [
            {
                "checked_at": "2026-09-04",
                "finding": "explicitly_open",
                "licence": "CC0-1.0",
                "source_id": "pmid:29063188",
                "terms_url": "terms were checked",
            }
        ]
    }
    evidence = _evidence_row(
        reuse_status="explicitly_open",
        reuse_evidence=json.dumps(reuse, sort_keys=True, separators=(",", ":")),
    )
    with pytest.raises(ValueError, match="terms_url"):
        validate_literature_tables(evidence, _field_evidence())


def test_honestly_unresolved_record_remains_valid_staging_evidence():
    """Catches validators that erase the difference between incomplete and malformed data."""
    evidence = _evidence_row(
        assay=pd.NA,
        verification_status="pending",
        verified_by=pd.NA,
        verified_at=pd.NA,
        verification_reference=pd.NA,
    )
    fields = _field_evidence()
    fields.loc[fields["field_name"] == "assay", [
        "evidence_status", "raw_value", "evidence_source_id", "source_locator", "notes",
    ]] = ["not_reviewed", pd.NA, pd.NA, pd.NA, "The assay section has not yet been reviewed."]

    validated, _ = validate_literature_tables(evidence, fields)
    assert validated.loc[0, "verification_status"] == "pending"
    assert pd.isna(validated.loc[0, "assay"])


@pytest.mark.parametrize("case", ["promotable", "non_promotable", "derived"])
def test_canonical_fixture_is_schema_checked(case):
    """Catches documentation examples drifting away from the executable contracts."""
    directory = FIXTURES / case
    evidence, fields = validate_literature_tables(
        _read_tsv(directory / "evidence.tsv"),
        _read_tsv(directory / "field_evidence.tsv"),
    )
    expected_rows = 2 if case == "derived" else 1
    assert len(evidence) == expected_rows
    assert len(fields) == 19 * expected_rows


@pytest.mark.parametrize(
    "case",
    json.loads((FIXTURES / "invalid" / "cases.json").read_text()),
    ids=lambda item: item["case"],
)
def test_prohibited_shortcut_fixtures_are_rejected(case):
    """Catches each documented shortcut becoming structurally acceptable."""
    evidence = _evidence_row()
    fields = _field_evidence()
    if case["mutation"] == "extra_column":
        evidence[case["column"]] = case["value"]
    elif case["mutation"] == "drop_field":
        fields = fields.loc[fields["field_name"] != case["field"]]
    else:
        evidence.loc[0, case["column"]] = case["value"]
    with pytest.raises(
        (ValueError, pandera.errors.SchemaError, pandera.errors.SchemaErrors)
    ):
        validate_literature_tables(evidence, fields)


@pytest.mark.parametrize(
    ("field", "method", "raw_value", "bad_raw_value"),
    [
        (
            "variant_id",
            "variant_normalization",
            '{"printed_alleles":"G/A","printed_build":"GRCh37",'
            '"reference_resource":"GRCh38.p14","resolved_variant_id":'
            '"chr2-135851076-G-A","strand":"forward"}',
            '{"printed_alleles":"G/A","printed_build":"GRCh37",'
            '"reference_resource":"GRCh38.p14","resolved_variant_id":'
            '"chr2-135851077-G-A","strand":"forward"}',
        ),
        (
            "citation_id",
            "persistent_citation_resolution",
            '{"literal_reference":"Liebert 2017","matched_record":"pmid:29063188",'
            '"resolved_citation_id":"pmid:29063188","retrieval_version":"pubmed-2026-09-04"}',
            '{"literal_reference":"Liebert 2017","matched_record":"pmid:1",'
            '"resolved_citation_id":"pmid:1","retrieval_version":"pubmed-2026-09-04"}',
        ),
        (
            "ac_lower",
            "alternate_count_from_reference_count",
            '{"an":58,"reference_ac":41}',
            '{"an":58,"reference_ac":40}',
        ),
        (
            "ac_upper",
            "allele_count_from_genotypes",
            '{"AA":3,"AG":11,"GG":15}',
            '{"AA":4,"AG":11,"GG":14}',
        ),
        (
            "an",
            "allele_denominator_from_complete_diploid_sample",
            '{"autosomal":true,"called_individuals":29,"complete_calls":true}',
            '{"autosomal":true,"called_individuals":30,"complete_calls":true}',
        ),
        (
            "an",
            "allele_denominator_from_hemizygous_males",
            '{"called_males":58,"hemizygous_x_linked":true}',
            '{"called_males":59,"hemizygous_x_linked":true}',
        ),
        ("ac_lower", "counts_from_explicit_integer_fraction", "17/58", "18/58"),
        (
            "sampling_design",
            "controlled_vocabulary_mapping",
            '{"mapping_key":"sampling-design-v1:random-community-sample",'
            '"source_value":"random population sample","value":"population_random"}',
            '{"mapping_key":"sampling-design-v1:clinic",'
            '"source_value":"clinic sample","value":"convenience"}',
        ),
        (
            "date_lower", "modern_sample_to_zero_bp", "contemporary living participants",
            "contemporary living participants",
        ),
    ],
)
def test_each_allowlisted_derivation_is_recomputed(field, method, raw_value, bad_raw_value):
    """Catches a derivation label that accepts a value unrelated to its exact raw input."""
    fields = _field_evidence()
    mask = fields["field_name"] == field
    fields.loc[mask, ["evidence_status", "raw_value", "derivation_method", "decision_reference"]] = [
        "derived", raw_value, method, "https://github.com/bschilder/genomeOS/issues/149",
    ]
    evidence = _evidence_row()
    if method == "allele_denominator_from_hemizygous_males":
        evidence.loc[0, ["variant_id", "counted_allele"]] = ["chrX-154536002-C-T", "T"]
        fields.loc[fields["field_name"] == "variant_id", "raw_value"] = "chrX-154536002-C-T"
        fields.loc[fields["field_name"] == "counted_allele", "raw_value"] = "T"
    validate_literature_tables(evidence, fields)

    broken = evidence.copy()
    fields.loc[mask, "raw_value"] = bad_raw_value
    if method == "modern_sample_to_zero_bp":
        broken.loc[0, ["date_lower", "date_upper"]] = [1, 1]
        fields.loc[fields["field_name"] == "date_upper", "raw_value"] = "1"
    with pytest.raises(ValueError, match="deriv"):
        validate_literature_tables(broken, fields)


def test_search_manifest_keeps_every_candidate_pending_until_screened():
    """Catches missing queries and exclusions without an auditable reason."""
    manifest = pd.DataFrame(
        [
            {
                "search_id": "pubmed:lct-rs4988235:2026-09-03:4c825",
                "corpus_id": "lct-rs4988235",
                "database": "pubmed",
                "query": "rs4988235 AND population",
                "executed_at": "2026-09-03T12:00:00Z",
                "candidate_id": "pmid:29063188",
                "decision": "pending",
                "decision_reason": pd.NA,
                "manifest_version": "lct-rs4988235@2026-09-03.1",
            }
        ],
        columns=LITERATURE_SEARCH_COLUMNS,
    )
    validated = validate_search_manifest(manifest)
    assert validated.loc[0, "candidate_id"] == "pmid:29063188"

    invalid = manifest.copy()
    invalid.loc[0, ["decision", "decision_reason"]] = ["excluded", pd.NA]
    with pytest.raises(ValueError, match="decision_reason"):
        validate_search_manifest(invalid)
