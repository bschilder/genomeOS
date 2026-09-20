"""Frozen curated-variant candidates and fail-closed eligibility (design §7.1, §13).

ClinVar clinical significance, CPIC pharmacogenomic actionability, and penetrance are distinct
claims.  This module keeps them distinct while defining the stable entities that downstream
surface work may target.  An imported row is a candidate until a different, attributable project
reviewer verifies it; selection helpers therefore return no pending or unresolved row.

The CPIC adapter consumes frozen tables supplied by an I/O boundary.  It performs no network or
filesystem access and retains every active Level A/B pair, including pairs for which the snapshot
contains no admitted allele.  Such gaps are explicit coverage rows rather than silent omissions.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pandera.pandas as pa

from genomeos.schema_checks import REVIEWABLE_TEXT

ENTITY_TYPES: tuple[str, ...] = (
    "sequence_variant",
    "named_allele",
    "hla_allele",
    "copy_number_state",
)
IDENTITY_STATUSES: tuple[str, ...] = ("resolved", "unresolved")
CLINICAL_DOMAINS: tuple[str, ...] = ("mendelian", "pharmacogenomic")
INHERITANCE_MODES: tuple[str, ...] = (
    "autosomal_recessive",
    "autosomal_dominant",
    "x_linked_recessive",
    "x_linked_dominant",
    "mitochondrial",
    "not_applicable",
)
OBSERVATION_TYPES: tuple[str, ...] = (
    "biallelic_allele_count",
    "multiallelic_allele_count",
    "named_haplotype_count",
    "copy_number_carrier_count",
)
INCLUSION_ROUTES: tuple[str, ...] = (
    "clinvar_penetrance",
    "cpic_a_b",
    "founder_validation",
    "carrier_screening_validation",
)
PENETRANCE_EVIDENCE_STATUSES: tuple[str, ...] = (
    "not_applicable",
    "identified_pending_review",
    "verified",
    "not_identified",
    "ambiguous",
)
PROJECT_REVIEW_STATUSES: tuple[str, ...] = ("pending", "verified", "rejected")
PROPOSAL_METHODS: tuple[str, ...] = (
    "automated_proposal",
    "manual_curation",
    "deterministic_import",
)

_NONEMPTY = REVIEWABLE_TEXT
_HTTPS_OR_EMPTY = pa.Check.str_matches(r"^https://.+|^$")

CURATED_VARIANTS_SCHEMA = pa.DataFrameSchema(
    {
        "variant_id": pa.Column(str, _NONEMPTY, nullable=False, unique=True),
        "display_name": pa.Column(str, _NONEMPTY, nullable=False),
        "gene": pa.Column(str, pa.Check.str_matches(r"^[A-Z0-9-]+$"), nullable=False),
        "entity_type": pa.Column(str, pa.Check.isin(ENTITY_TYPES), nullable=False),
        "canonical_identifier": pa.Column(str, nullable=False),
        "identity_status": pa.Column(str, pa.Check.isin(IDENTITY_STATUSES), nullable=False),
        "clinical_domain": pa.Column(str, pa.Check.isin(CLINICAL_DOMAINS), nullable=False),
        "inheritance": pa.Column(str, pa.Check.isin(INHERITANCE_MODES), nullable=False),
        "clinical_context": pa.Column(str, _NONEMPTY, nullable=False),
        "observation_type": pa.Column(str, pa.Check.isin(OBSERVATION_TYPES), nullable=False),
        "inclusion_route": pa.Column(str, pa.Check.isin(INCLUSION_ROUTES), nullable=False),
        "source_name": pa.Column(str, _NONEMPTY, nullable=False),
        "source_release": pa.Column(str, _NONEMPTY, nullable=False),
        "source_record_id": pa.Column(str, _NONEMPTY, nullable=False),
        "source_url": pa.Column(str, _HTTPS_OR_EMPTY, nullable=False),
        "source_classification": pa.Column(str, _NONEMPTY, nullable=False),
        "penetrance_evidence_status": pa.Column(
            str, pa.Check.isin(PENETRANCE_EVIDENCE_STATUSES), nullable=False
        ),
        "penetrance_evidence_locator": pa.Column(str, _HTTPS_OR_EMPTY, nullable=False),
        "founder_context": pa.Column(str, nullable=False),
        "proposed_by": pa.Column(
            str,
            pa.Check.str_matches(r"^(?:human|agent|import):[^\s]+$"),
            nullable=False,
        ),
        "proposal_method": pa.Column(str, pa.Check.isin(PROPOSAL_METHODS), nullable=False),
        "project_review_status": pa.Column(
            str, pa.Check.isin(PROJECT_REVIEW_STATUSES), nullable=False
        ),
        "reviewed_by": pa.Column(str, nullable=False),
        "reviewed_at": pa.Column(str, nullable=False),
        "refusal_reason": pa.Column(str, nullable=False),
        "set_version": pa.Column(str, _NONEMPTY, nullable=False),
    },
    strict=True,
    coerce=True,
    unique=["source_name", "source_record_id"],
    name="curated_variants",
)

CPIC_PAIR_TARGETS_SCHEMA = pa.DataFrameSchema(
    {
        "pair_id": pa.Column(str, _NONEMPTY, nullable=False, unique=True),
        "gene": pa.Column(str, _NONEMPTY, nullable=False),
        "drug_id": pa.Column(str, _NONEMPTY, nullable=False),
        "drug_name": pa.Column(str, _NONEMPTY, nullable=False),
        "cpic_level": pa.Column(str, pa.Check.isin(("A", "B")), nullable=False),
        "guideline_id": pa.Column(str, nullable=False),
        "guideline_name": pa.Column(str, nullable=False),
        "guideline_url": pa.Column(str, _HTTPS_OR_EMPTY, nullable=False),
        "source_release": pa.Column(str, _NONEMPTY, nullable=False),
        "status": pa.Column(
            str,
            pa.Check.isin(
                ("candidate_gene_covered", "no_allele_table", "no_admitted_function")
            ),
            nullable=False,
        ),
    },
    strict=True,
    coerce=True,
    name="cpic_pair_targets",
)

CPIC_COVERAGE_SCHEMA = pa.DataFrameSchema(
    {
        "gene": pa.Column(str, _NONEMPTY, nullable=False, unique=True),
        # pandas' nullable "Int64" rather than numpy int. This schema coerces, and pandera coerces
        # before it checks, so a plain numpy integer turned a fractional count into a whole one and
        # then validated the result — the silent repair §12 forbids. "Int64" casting raises on a
        # non-integral value while still accepting an integral float like 3.0. Same change #323 made
        # to the P1 observation counts, applied to the last columns that still had the shape (#338).
        "pair_count": pa.Column("Int64", pa.Check.ge(1), nullable=False),
        "allele_row_count": pa.Column("Int64", pa.Check.ge(0), nullable=False),
        "candidate_count": pa.Column("Int64", pa.Check.ge(0), nullable=False),
        "status": pa.Column(
            str,
            pa.Check.isin(
                ("candidate_gene_covered", "no_allele_table", "no_admitted_function")
            ),
            nullable=False,
        ),
        "refusal_reason": pa.Column(str, nullable=False),
        "source_release": pa.Column(str, _NONEMPTY, nullable=False),
        "set_version": pa.Column(str, _NONEMPTY, nullable=False),
    },
    strict=True,
    coerce=True,
    name="cpic_coverage",
)

def _ids(frame: pd.DataFrame, mask: pd.Series) -> str:
    return ", ".join(frame.loc[mask, "variant_id"].astype(str).head(5))


def _refuse(frame: pd.DataFrame, mask: pd.Series, message: str) -> None:
    if bool(mask.any()):
        raise ValueError(f"{message}: {_ids(frame, mask)}")


def validate_rows(frame: pd.DataFrame) -> pd.DataFrame:
    """Validate the frozen table and all cross-field scientific invariants."""
    validated = CURATED_VARIANTS_SCHEMA.validate(frame)

    def blank(column: str) -> pd.Series:
        return validated[column].str.strip().eq("")

    mendelian = validated["clinical_domain"].eq("mendelian")
    pgx = validated["clinical_domain"].eq("pharmacogenomic")
    unresolved = validated["identity_status"].eq("unresolved")
    verified = validated["project_review_status"].eq("verified")
    decided = validated["project_review_status"].isin(("verified", "rejected"))
    pending = validated["project_review_status"].eq("pending")

    _refuse(
        validated,
        mendelian & validated["inheritance"].eq("not_applicable"),
        "Mendelian candidates require an inheritance mode",
    )
    _refuse(
        validated,
        pgx & ~validated["inheritance"].eq("not_applicable"),
        "pharmacogenomic candidates must use not_applicable inheritance",
    )
    _refuse(
        validated,
        pgx & ~validated["inclusion_route"].eq("cpic_a_b"),
        "pharmacogenomic candidates require the CPIC A/B inclusion route",
    )
    _refuse(
        validated,
        pgx
        & (
            ~validated["penetrance_evidence_status"].eq("not_applicable")
            | ~blank("penetrance_evidence_locator")
        ),
        "pharmacogenomic candidates cannot carry a penetrance claim",
    )
    _refuse(
        validated,
        mendelian & validated["penetrance_evidence_status"].eq("not_applicable"),
        "Mendelian candidates require an explicit penetrance-evidence state",
    )
    needs_locator = validated["penetrance_evidence_status"].isin(
        ("identified_pending_review", "verified", "ambiguous")
    )
    _refuse(
        validated,
        needs_locator & blank("penetrance_evidence_locator"),
        "identified or ambiguous penetrance evidence requires a locator",
    )
    _refuse(
        validated,
        unresolved & (~blank("canonical_identifier") | blank("refusal_reason")),
        "unresolved identities require a refusal_reason and no canonical identifier",
    )
    _refuse(
        validated,
        ~unresolved & (blank("canonical_identifier") | ~blank("refusal_reason")),
        "resolved identities require a canonical identifier and no refusal_reason",
    )
    _refuse(
        validated,
        unresolved & verified,
        "unresolved identities cannot be verified",
    )
    _refuse(
        validated,
        pending & (~blank("reviewed_by") | ~blank("reviewed_at")),
        "pending rows must not carry reviewed_by or reviewed_at",
    )
    _refuse(
        validated,
        decided & (blank("reviewed_by") | blank("reviewed_at")),
        "verified or rejected rows require reviewed_by and reviewed_at",
    )
    _refuse(
        validated,
        decided & validated["reviewed_by"].eq(validated["proposed_by"]),
        "a project reviewer must differ from the proposer",
    )
    if validated["set_version"].nunique() != 1:
        raise ValueError("a curated table must contain exactly one set_version")
    return validated


def load(path: Path) -> pd.DataFrame:
    """Load and fully validate one frozen curated-variant table."""
    return validate_rows(pd.read_csv(path, sep="\t", dtype=str, keep_default_na=False))


def select_for_frequency_surface(frame: pd.DataFrame) -> pd.DataFrame:
    """Return reviewed, resolved frequency targets; all other rows are explicit refusals."""
    validated = validate_rows(frame)
    mask = validated["project_review_status"].eq("verified") & validated[
        "identity_status"
    ].eq("resolved")
    return validated.loc[mask].reset_index(drop=True)


def select_for_affected_burden(frame: pd.DataFrame) -> pd.DataFrame:
    """Return targets whose Mendelian inclusion *and* penetrance evidence are verified."""
    selected = select_for_frequency_surface(frame)
    mask = selected["clinical_domain"].eq("mendelian") & selected[
        "penetrance_evidence_status"
    ].eq("verified")
    return selected.loc[mask].reset_index(drop=True)
