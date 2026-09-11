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
    ("normalized_variant_id", "printed_alleles"),
    [
        ("chr1-100-AT-GC", "AT/GC"),
        ("chr1-100-A-G", "AT/GC"),
        ("chr1-100-AT-GC", "A/G"),
    ],
)
def test_a_multi_base_allele_is_refused(normalized_variant_id, printed_alleles):
    """`complement()` complements per base but does not reverse, so a multi-base allele pair on
    the minus strand round-trips against the wrong (un-reversed) complement — it would wrongly
    accept a transposed pair and wrongly refuse the correct one (I4). Rather than implement
    reverse-complement for a case no consumer needs yet, the schema refuses any multi-base allele
    loudly at the door instead of silently mishandling strand for it."""
    frame = pd.DataFrame(
        [_row(normalized_variant_id=normalized_variant_id, printed_alleles=printed_alleles)]
    )
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


def test_a_resolved_row_with_a_refusal_reason_is_refused():
    """A resolved row must not carry a refusal_reason — that field means something only when
    status is unresolved, and carrying one alongside a resolution is a contradiction (m2)."""
    bad = pd.DataFrame([_row(refusal_reason="no candidate rsID found")])
    with pytest.raises(ValueError, match="must not carry a refusal_reason"):
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
    for rsid, normalized_variant_id, and strand (design §5, contract table)."""
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


def test_a_verified_mapping_row_returns_its_identity(tmp_path):
    """A row asserting a legacy-name-to-coordinate mapping resolves once it is verified."""
    registry = load(_write(tmp_path, [_row(verification_status="verified")]))
    assert normalized_identity("cyt:example-1-a", registry) == NormalizedIdentity(
        variant_id="cyt:example-1-a",
        rsid="rs1",
        normalized_variant_id="chr1-100-A-G",
        strand="plus",
    )


def test_a_pending_mapping_row_returns_none(tmp_path):
    """Resolution is a proposal; a mapping claim waits on verification (design §9, #242).

    This row differs from the one above only in `verification_status`, so the pair pins the gate
    to that field and to nothing else about the row.
    """
    registry = load(_write(tmp_path, [_row(verification_status="pending")]))
    assert normalized_identity("cyt:example-1-a", registry) is None


def test_a_pending_identity_row_still_resolves(tmp_path):
    """An identity row asserts no mapping, so there is nothing for verification to check.

    Its `variant_id` already *is* the normalized coordinate: no legacy name was translated and no
    strand was chosen, so an external annotation keyed by that coordinate cannot contradict it.
    Requiring verification here would block already-published artifacts for no scientific gain.
    """
    identity = _row(
        variant_id="chr1-100-A-G",
        normalized_variant_id="chr1-100-A-G",
        verification_status="pending",
    )
    registry = load(_write(tmp_path, [identity]))
    assert normalized_identity("chr1-100-A-G", registry) == NormalizedIdentity(
        variant_id="chr1-100-A-G",
        rsid="rs1",
        normalized_variant_id="chr1-100-A-G",
        strand="plus",
    )


def test_an_absent_variant_returns_none(tmp_path):
    """Absence is a refusal for the caller, not a blank to fill (§7)."""
    registry = load(_write(tmp_path, [_row(verification_status="verified")]))
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
    """The checked-in file is the artifact; `load` runs every invariant over it.

    (m1) There used to be two further assertions here — that every resolved row's
    `naming_citation` is non-empty, and every unresolved row's `refusal_reason` is non-empty —
    checked against the already-`load`ed committed registry. Both were vacuous: `validate_rows`
    (called by `load`) already raises `ValueError` for exactly those conditions, so if `load`
    above returns at all, both assertions are already guaranteed true and can never fail. That
    behavior is covered on crafted rows by `test_a_resolved_row_without_a_naming_citation_is_refused`
    and `test_an_unresolved_row_needs_a_reason_and_no_coordinate`, so the two were deleted rather
    than kept as tests named for an acceptance criterion that could not fail.
    """
    registry = load(REGISTRY_PATH)
    assert len(registry) >= 1
