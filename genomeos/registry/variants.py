"""Reviewed variant-normalization registry (design 2026-09-10 §5).

A second, canonical way to name a variant this project already maps: a GRCh38 `chr-pos-ref-alt`
identity with a resolved rsID and strand. It sits *beside* the internal `variant_id` and never
replaces it, so no published identity moves (§3A).

Every row is hand-authored and reviewed. Nothing here resolves a variant automatically, and a
`variant_id` with no row is a refusal at every consumer, never a fallback (§7).
"""

from __future__ import annotations

import pandera.pandas as pa

#: A locus is either resolved to a coordinate, or recorded as unresolvable with a reason. An
#: absent row means "not attempted" — a third state, distinguishable from both (§6).
RESOLUTION_STATUSES: tuple[str, ...] = ("resolved", "unresolved")
STRANDS: tuple[str, ...] = ("plus", "minus")
VERIFICATION_STATUSES: tuple[str, ...] = ("verified", "pending")

_RSID = r"^rs[1-9][0-9]*$"
_NORMALIZED_VARIANT = r"^chr(?:[1-9]|1[0-9]|2[0-2]|X|Y|MT)-[1-9][0-9]*-[ACGT]+-[ACGT]+$"
_PRINTED_ALLELES = r"^[ACGT]+/[ACGT]+$"
# Built from STRANDS rather than hardcoded: the column must also admit "" on an unresolved row,
# which a bare pa.Check.isin(STRANDS) cannot express.
_STRAND = rf"^(?:{'|'.join(STRANDS)})$|^$"

VARIANT_NORMALIZATION_SCHEMA = pa.DataFrameSchema(
    {
        "variant_id": pa.Column(str, pa.Check.str_length(min_value=1), nullable=False, unique=True),
        "status": pa.Column(str, pa.Check.isin(RESOLUTION_STATUSES), nullable=False),
        # Blank on an unresolved row; the loader enforces that pairing, which pandera cannot.
        "rsid": pa.Column(str, pa.Check.str_matches(rf"{_RSID}|^$"), nullable=False),
        "normalized_variant_id": pa.Column(
            str, pa.Check.str_matches(rf"{_NORMALIZED_VARIANT}|^$"), nullable=False
        ),
        # Always required: it is the input to the round-trip check, so it is kept even on a
        # refused row, where it is often the evidence of *why* the row could not resolve.
        "printed_alleles": pa.Column(str, pa.Check.str_matches(_PRINTED_ALLELES), nullable=False),
        "printed_convention": pa.Column(str, pa.Check.str_length(min_value=1), nullable=False),
        "strand": pa.Column(str, pa.Check.str_matches(_STRAND), nullable=False),
        "strand_evidence": pa.Column(str, nullable=False),
        "reference_resource": pa.Column(str, nullable=False),
        "naming_citation": pa.Column(str, nullable=False),
        "resolved_at": pa.Column(str, pa.Check.str_length(min_value=1), nullable=False),
        "reviewed_by": pa.Column(str, pa.Check.str_length(min_value=1), nullable=False),
        "verification_status": pa.Column(
            str, pa.Check.isin(VERIFICATION_STATUSES), nullable=False
        ),
        "refusal_reason": pa.Column(str, nullable=False),
        "notes": pa.Column(str, nullable=False),
    },
    strict=True,
    coerce=True,
    name="variant_normalization",
)
