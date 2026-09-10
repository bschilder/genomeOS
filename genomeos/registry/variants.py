"""Reviewed variant-normalization registry (design 2026-09-10 §5).

A second, canonical way to name a variant this project already maps: a GRCh38 `chr-pos-ref-alt`
identity with a resolved rsID and strand. It sits *beside* the internal `variant_id` and never
replaces it, so no published identity moves (§3A).

Every row is hand-authored and reviewed. Nothing here resolves a variant automatically, and a
`variant_id` with no row is a refusal at every consumer, never a fallback (§7).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd
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

_COMPLEMENT = str.maketrans({"A": "T", "T": "A", "C": "G", "G": "C"})
_PALINDROMES: tuple[frozenset[str], ...] = (frozenset({"A", "T"}), frozenset({"C", "G"}))


def complement(alleles: str) -> str:
    """`"A/G"` -> `"T/C"`. Each allele independently; the slash is preserved."""
    return alleles.translate(_COMPLEMENT)


def is_palindromic(printed_alleles: str) -> bool:
    """True when complementing returns the same pair, so the letters cannot reveal strand.

    `A/T` and `C/G` are their own complements. For those the round-trip check in `validate_rows`
    passes under *either* strand and therefore proves nothing, which is why such rows are required
    to carry `strand_evidence` instead (design §5).
    """
    return frozenset(printed_alleles.split("/")) in _PALINDROMES


def validate_rows(frame: pd.DataFrame) -> pd.DataFrame:
    """Schema validation plus the cross-field invariants pandera cannot express."""
    validated = VARIANT_NORMALIZATION_SCHEMA.validate(frame)
    for row in validated.itertuples():
        where = f"variant_normalization[{row.variant_id}]"
        if row.status == "unresolved":
            if not row.refusal_reason.strip():
                raise ValueError(f"{where}: an unresolved row requires a refusal_reason")
            if row.rsid or row.normalized_variant_id or row.strand:
                raise ValueError(
                    f"{where}: an unresolved row must not carry an rsid, coordinate, or strand"
                )
            continue

        for field in ("rsid", "normalized_variant_id", "strand", "reference_resource"):
            if not str(getattr(row, field)).strip():
                raise ValueError(f"{where}: a resolved row requires {field}")
        if not row.naming_citation.strip():
            raise ValueError(
                f"{where}: a resolved row requires a naming_citation — the source establishing "
                "that the legacy name denotes this rsID. Without one the row is unresolved (§6)."
            )
        if row.refusal_reason.strip():
            raise ValueError(f"{where}: a resolved row must not carry a refusal_reason")

        _, _, ref, alt = row.normalized_variant_id.rsplit("-", 3)
        printed = row.printed_alleles if row.strand == "plus" else complement(row.printed_alleles)
        if frozenset(printed.split("/")) != frozenset({ref, alt}):
            raise ValueError(
                f"{where}: printed_alleles {row.printed_alleles!r} on the {row.strand} strand "
                f"does not round-trip to {{{ref}, {alt}}}"
            )
        if is_palindromic(row.printed_alleles) and not row.strand_evidence.strip():
            raise ValueError(
                f"{where}: {row.printed_alleles!r} is palindromic, so the round-trip cannot "
                "detect a strand error; strand_evidence is required"
            )
    return validated


@dataclass(frozen=True)
class NormalizedIdentity:
    """A reviewed second name for a variant. Only ever constructed from a `resolved` row."""

    variant_id: str
    rsid: str
    normalized_variant_id: str
    strand: str


def load(path: Path) -> pd.DataFrame:
    """Read and fully validate the registry. Raises rather than returning a partial table."""
    frame = pd.read_csv(path, sep="\t", dtype=str, keep_default_na=False)
    return validate_rows(frame)


def normalized_identity(variant_id: str, registry: pd.DataFrame) -> NormalizedIdentity | None:
    """The reviewed identity for `variant_id`, or `None` if there is not one.

    `None` covers both "no row" and "recorded as unresolvable". Callers must treat it as a
    refusal — there is no fallback, and in particular no inferring a coordinate from the shape of
    the identifier (§7).
    """
    matches = registry[(registry["variant_id"] == variant_id) & (registry["status"] == "resolved")]
    if matches.empty:
        return None
    row = matches.iloc[0]
    return NormalizedIdentity(
        variant_id=variant_id,
        rsid=row["rsid"],
        normalized_variant_id=row["normalized_variant_id"],
        strand=row["strand"],
    )
