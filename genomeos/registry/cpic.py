"""CPIC Level A/B candidate derivation (Atlas design §13).

This pure adapter consumes frozen CPIC tables supplied by an I/O boundary. It preserves every
active A/B gene-drug pair and separately derives named-allele candidates from source-authored
clinical-functional states. A candidate allele is never asserted to apply to every drug paired
with its gene; reviewers join through the separately emitted pair table.
"""

from __future__ import annotations

import pandas as pd

from genomeos.registry.curated import (
    CPIC_COVERAGE_SCHEMA,
    CPIC_PAIR_TARGETS_SCHEMA,
    validate_rows,
)

# These are clinical-functional states printed by CPIC, not interpretations invented here. Normal,
# uncertain, unknown, and blank states stay outside the candidate table. The complete pair table
# and per-gene coverage report make every resulting omission visible.
ADMITTED_FUNCTIONS = frozenset(
    {
        "Decreased function",
        "I/Deficient with CNSHA",
        "II/Deficient",
        "III/Deficient",
        "Increased function",
        "Malignant Hyperthermia associated",
        "No function",
        "increased risk of aminoglycoside-induced hearing loss",
        "ivacaftor responsive",
    }
)

# HLA recommendations and the VKORC1 warfarin rule use allele/genotype presence rather than CPIC's
# clinicalfunctionalstatus field. This allowlist is deliberately exact and reviewable.
ALLELE_STATUS_TRIGGERS = frozenset(
    {
        ("HLA-A", "*31:01"),
        ("HLA-B", "*15:02"),
        ("HLA-B", "*57:01"),
        ("HLA-B", "*58:01"),
        ("VKORC1", "rs9923231 variant (T)"),
    }
)


def _require_columns(frame: pd.DataFrame, name: str, columns: set[str]) -> None:
    missing = sorted(columns - set(frame.columns))
    if missing:
        raise ValueError(f"{name} is missing columns: {missing}")


def build_cpic_candidates(
    alleles: pd.DataFrame,
    pairs: pd.DataFrame,
    drugs: pd.DataFrame,
    guidelines: pd.DataFrame,
    *,
    source_release: str,
    set_version: str,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Derive candidates and complete A/B coverage from one frozen CPIC snapshot.

    Pandas joins and grouped reductions operate over whole tables. The implementation does not
    perform pair-by-allele nested iteration, which would obscure omissions and scale quadratically.
    """
    _require_columns(
        alleles,
        "alleles",
        {"id", "genesymbol", "name", "clinicalfunctionalstatus", "version"},
    )
    _require_columns(
        pairs,
        "pairs",
        {"genesymbol", "drugid", "guidelineid", "cpiclevel", "removed"},
    )
    _require_columns(drugs, "drugs", {"drugid", "name", "guidelineid"})
    _require_columns(guidelines, "guidelines", {"id", "name", "url"})
    if not source_release.strip() or not set_version.strip():
        raise ValueError("source_release and set_version must be nonempty")

    removed = pairs["removed"].astype(str).str.lower()
    if (~removed.isin(("true", "false", "t", "f", "1", "0"))).any():
        raise ValueError("CPIC removed must contain explicit boolean values")
    active = pairs.loc[
        pairs["cpiclevel"].isin(("A", "B")) & removed.isin(("false", "f", "0"))
    ].copy()
    if active.empty:
        raise ValueError("the CPIC snapshot contains no active Level A/B pairs")
    if active.duplicated(["genesymbol", "drugid"]).any():
        raise ValueError("active CPIC gene-drug pairs must be unique")

    drug_names = drugs[["drugid", "name"]].drop_duplicates("drugid").rename(
        columns={"name": "drug_name"}
    )
    guideline_names = guidelines[["id", "name", "url"]].drop_duplicates("id").rename(
        columns={"id": "guidelineid", "name": "guideline_name", "url": "guideline_url"}
    )
    active = active.merge(drug_names, on="drugid", how="left", validate="many_to_one")
    active = active.merge(guideline_names, on="guidelineid", how="left", validate="many_to_one")
    if active["drug_name"].isna().any():
        raise ValueError("every active CPIC pair must resolve to a drug name")
    active[["guideline_name", "guideline_url"]] = active[
        ["guideline_name", "guideline_url"]
    ].fillna("")

    eligible_genes = set(active["genesymbol"])
    allele_keys = pd.MultiIndex.from_frame(alleles[["genesymbol", "name"]])
    explicit_trigger = allele_keys.isin(pd.MultiIndex.from_tuples(ALLELE_STATUS_TRIGGERS))
    admitted = alleles.loc[
        alleles["genesymbol"].isin(eligible_genes)
        & (alleles["clinicalfunctionalstatus"].isin(ADMITTED_FUNCTIONS) | explicit_trigger)
    ].copy()
    if admitted["id"].duplicated().any():
        raise ValueError("CPIC allele ids must be unique")

    admitted["_id_order"] = pd.to_numeric(admitted["id"], errors="raise")
    admitted = admitted.sort_values("_id_order", kind="stable")
    variants = pd.DataFrame(
        {
            "variant_id": "cpic:allele:" + admitted["id"].astype(str),
            "display_name": admitted["genesymbol"] + admitted["name"],
            "gene": admitted["genesymbol"],
            "entity_type": admitted["genesymbol"].str.startswith("HLA-").map(
                {True: "hla_allele", False: "named_allele"}
            ),
            "canonical_identifier": "CPIC allele " + admitted["id"].astype(str),
            "identity_status": "resolved",
            "clinical_domain": "pharmacogenomic",
            "inheritance": "not_applicable",
            "clinical_context": (
                "CPIC pharmacogenomic allele; exact gene-drug pairs are in cpic_pair_targets.tsv"
            ),
            "observation_type": admitted["genesymbol"].str.startswith("HLA-").map(
                {True: "multiallelic_allele_count", False: "named_haplotype_count"}
            ),
            "inclusion_route": "cpic_a_b",
            "source_name": "CPIC",
            "source_release": source_release,
            "source_record_id": "CPIC:allele:" + admitted["id"].astype(str),
            "source_url": "https://api.cpicpgx.org/v1/allele?id=eq."
            + admitted["id"].astype(str),
            "source_classification": admitted["clinicalfunctionalstatus"].mask(
                admitted["clinicalfunctionalstatus"].eq(""), "allele-status trigger"
            ),
            "penetrance_evidence_status": "not_applicable",
            "penetrance_evidence_locator": "",
            "founder_context": "",
            "proposed_by": f"import:cpic-{source_release}",
            "proposal_method": "deterministic_import",
            "project_review_status": "pending",
            "reviewed_by": "",
            "reviewed_at": "",
            "refusal_reason": "",
            "set_version": set_version,
        }
    )
    variants = validate_rows(variants.reset_index(drop=True))

    candidate_counts = variants.groupby("gene").size().rename("candidate_count")
    allele_counts = (
        alleles.loc[alleles["genesymbol"].isin(eligible_genes)]
        .groupby("genesymbol")
        .size()
        .rename("allele_row_count")
    )
    gene_status = pd.Series("candidate_gene_covered", index=sorted(eligible_genes), dtype=str)
    gene_status.loc[~gene_status.index.isin(allele_counts.index)] = "no_allele_table"
    gene_status.loc[
        gene_status.index.isin(allele_counts.index)
        & ~gene_status.index.isin(candidate_counts.index)
    ] = "no_admitted_function"

    pair_targets = active.rename(
        columns={
            "genesymbol": "gene",
            "drugid": "drug_id",
            "guidelineid": "guideline_id",
            "cpiclevel": "cpic_level",
        }
    )
    pair_targets["pair_id"] = (
        "CPIC:pair:" + pair_targets["gene"] + ":" + pair_targets["drug_id"]
    )
    pair_targets["source_release"] = source_release
    pair_targets["status"] = pair_targets["gene"].map(gene_status)
    pair_targets = pair_targets[
        [
            "pair_id",
            "gene",
            "drug_id",
            "drug_name",
            "cpic_level",
            "guideline_id",
            "guideline_name",
            "guideline_url",
            "source_release",
            "status",
        ]
    ].sort_values(["gene", "drug_id"], kind="stable", ignore_index=True)
    pair_targets = CPIC_PAIR_TARGETS_SCHEMA.validate(pair_targets)

    pair_counts = active.groupby("genesymbol").size().rename("pair_count")
    coverage = pd.DataFrame(index=sorted(eligible_genes)).rename_axis("gene")
    coverage = coverage.join(pair_counts).join(allele_counts).join(candidate_counts).fillna(0)
    coverage[["pair_count", "allele_row_count", "candidate_count"]] = coverage[
        ["pair_count", "allele_row_count", "candidate_count"]
    ].astype(int)
    coverage["status"] = coverage.index.map(gene_status)
    coverage["refusal_reason"] = coverage["status"].map(
        {
            "candidate_gene_covered": "",
            "no_allele_table": "The frozen CPIC snapshot publishes no allele rows for this A/B pair gene.",
            "no_admitted_function": (
                "The frozen CPIC allele table has no row carrying an admitted functional state "
                "or exact allele-status trigger for this A/B pair gene."
            ),
        }
    )
    coverage["source_release"] = source_release
    coverage["set_version"] = set_version
    coverage = CPIC_COVERAGE_SCHEMA.validate(coverage.reset_index())
    return variants, pair_targets, coverage
