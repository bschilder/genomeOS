"""The reviewed variant-normalization registry (design 2026-09-10 §5)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pandera.errors
import pytest

from genomeos.registry.variants import (
    VARIANT_NORMALIZATION_SCHEMA,
    NormalizedIdentity,
    complement,
    is_palindromic,
    load,
    normalized_identity,
    validate_rows,
)


def _row(**overrides) -> dict[str, object]:
    """One valid resolved row. Overrides replace individual fields."""
    row = {
        "variant_id": "cyt:example-1-a",
        "status": "resolved",
        "rsid": "rs1",
        "normalized_variant_id": "chr1-100-A-G",
        "printed_alleles": "A/G",
        "printed_convention": "promoter offset -1 from the TSS used by the source",
        "strand": "plus",
        "strand_evidence": "",
        "reference_resource": "dbSNP build 156; Ensembl release 112",
        "naming_citation": "pmid:12345678",
        "resolved_at": "2026-09-10T00:00:00Z",
        "reviewed_by": "human:reviewer",
        "verification_status": "pending",
        "refusal_reason": "",
        "notes": "",
    }
    row.update(overrides)
    return row


def test_a_valid_resolved_row_passes():
    frame = pd.DataFrame([_row()])
    assert len(VARIANT_NORMALIZATION_SCHEMA.validate(frame)) == 1


def test_an_unknown_status_is_refused():
    frame = pd.DataFrame([_row(status="probably")])
    with pytest.raises(pandera.errors.SchemaError):
        VARIANT_NORMALIZATION_SCHEMA.validate(frame)


def test_a_malformed_normalized_identifier_is_refused():
    frame = pd.DataFrame([_row(normalized_variant_id="chr1:100:A:G")])
    with pytest.raises(pandera.errors.SchemaError):
        VARIANT_NORMALIZATION_SCHEMA.validate(frame)


def test_a_duplicate_variant_id_is_refused():
    frame = pd.DataFrame([_row(), _row()])
    with pytest.raises(pandera.errors.SchemaError):
        VARIANT_NORMALIZATION_SCHEMA.validate(frame)


@pytest.mark.parametrize(
    ("alleles", "expected"),
    [("A/T", True), ("T/A", True), ("C/G", True), ("G/C", True), ("A/G", False), ("C/T", False)],
)
def test_palindromic_pairs_are_recognised(alleles, expected):
    """A/T and C/G complement to themselves, so strand cannot be inferred from the letters."""
    assert is_palindromic(alleles) is expected


def test_complement_flips_each_allele():
    assert complement("A/G") == "T/C"


def test_printed_alleles_must_round_trip_under_the_recorded_strand():
    """The central check: a minus-strand row whose letters are already plus-strand is a defect."""
    bad = pd.DataFrame([_row(printed_alleles="A/G", strand="minus", normalized_variant_id="chr1-100-A-G")])
    with pytest.raises(ValueError, match="does not round-trip"):
        validate_rows(bad)


def test_a_minus_strand_row_that_does_round_trip_is_accepted():
    good = pd.DataFrame([_row(printed_alleles="T/C", strand="minus", normalized_variant_id="chr1-100-A-G")])
    assert len(validate_rows(good)) == 1


def test_a_palindromic_resolved_row_requires_strand_evidence():
    """The round-trip has no power here, so something else must establish strand (spec §5)."""
    bad = pd.DataFrame(
        [_row(printed_alleles="G/C", normalized_variant_id="chr1-100-G-C", strand_evidence="")]
    )
    with pytest.raises(ValueError, match="palindromic"):
        validate_rows(bad)


def test_a_palindromic_row_with_strand_evidence_is_accepted():
    good = pd.DataFrame(
        [
            _row(
                printed_alleles="G/C",
                normalized_variant_id="chr1-100-G-C",
                strand_evidence="pmid:12345678 states the minus strand explicitly",
            )
        ]
    )
    assert len(validate_rows(good)) == 1


def test_a_resolved_row_without_a_naming_citation_is_refused():
    bad = pd.DataFrame([_row(naming_citation="")])
    with pytest.raises(ValueError, match="naming_citation"):
        validate_rows(bad)


def test_an_unresolved_row_needs_a_reason_and_no_coordinate():
    missing_reason = pd.DataFrame(
        [_row(status="unresolved", rsid="", normalized_variant_id="", strand="", refusal_reason="")]
    )
    with pytest.raises(ValueError, match="refusal_reason"):
        validate_rows(missing_reason)

    keeps_coordinate = pd.DataFrame(
        [_row(status="unresolved", rsid="", refusal_reason="no candidate rsID found")]
    )
    with pytest.raises(ValueError, match="unresolved"):
        validate_rows(keeps_coordinate)


@pytest.mark.parametrize("field", ["rsid", "normalized_variant_id", "strand", "reference_resource"])
def test_a_resolved_row_missing_a_required_field_is_refused(field):
    """The `raise` in validate_rows is the sole enforcement here — the schema itself admits ""
    for rsid, normalized_variant_id, and strand (design §6, §7.1)."""
    bad = pd.DataFrame([_row(**{field: ""})])
    with pytest.raises(ValueError, match=field):
        validate_rows(bad)


def _write(tmp_path: Path, rows: list[dict[str, object]]) -> Path:
    path = tmp_path / "variant_normalization.tsv"
    pd.DataFrame(rows).to_csv(path, sep="\t", index=False)
    return path


def test_load_reads_and_validates(tmp_path):
    registry = load(_write(tmp_path, [_row()]))
    assert list(registry["variant_id"]) == ["cyt:example-1-a"]


def test_load_refuses_an_invalid_file(tmp_path):
    path = _write(tmp_path, [_row(status="resolved", naming_citation="")])
    with pytest.raises(ValueError, match="naming_citation"):
        load(path)


def test_a_resolved_variant_returns_its_identity(tmp_path):
    registry = load(_write(tmp_path, [_row()]))
    assert normalized_identity("cyt:example-1-a", registry) == NormalizedIdentity(
        variant_id="cyt:example-1-a",
        rsid="rs1",
        normalized_variant_id="chr1-100-A-G",
        strand="plus",
    )


def test_an_absent_variant_returns_none(tmp_path):
    """Absence is a refusal for the caller, not a blank to fill (§7)."""
    registry = load(_write(tmp_path, [_row()]))
    assert normalized_identity("cyt:not-in-the-registry", registry) is None


def test_an_unresolved_variant_returns_none(tmp_path):
    """A recorded refusal is consumed exactly like an absent row; the difference is visibility."""
    registry = load(
        _write(
            tmp_path,
            [
                _row(
                    status="unresolved",
                    rsid="",
                    normalized_variant_id="",
                    strand="",
                    naming_citation="",
                    refusal_reason="no candidate rsID in LitVar2 or dbSNP",
                )
            ],
        )
    )
    assert normalized_identity("cyt:example-1-a", registry) is None


REGISTRY_PATH = Path(__file__).resolve().parents[1] / "data" / "registry" / "variant_normalization.tsv"


def test_the_committed_registry_validates():
    """The checked-in file is the artifact; `load` runs every invariant over it."""
    registry = load(REGISTRY_PATH)
    assert len(registry) >= 1


def test_every_resolved_row_cites_its_naming_source():
    registry = load(REGISTRY_PATH)
    resolved = registry[registry["status"] == "resolved"]
    assert (resolved["naming_citation"].str.strip() != "").all()


def test_every_unresolved_row_states_what_was_attempted():
    registry = load(REGISTRY_PATH)
    unresolved = registry[registry["status"] == "unresolved"]
    assert (unresolved["refusal_reason"].str.strip() != "").all()
