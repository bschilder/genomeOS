"""The reviewed variant-normalization registry (design 2026-09-10 §5)."""

from __future__ import annotations

import pandas as pd
import pandera.errors
import pytest

from genomeos.registry.variants import VARIANT_NORMALIZATION_SCHEMA


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
