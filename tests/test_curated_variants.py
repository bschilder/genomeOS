"""Curated v1 variant-set contract (Atlas design §7.1 and §13)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pandera.errors
import pytest

from genomeos.registry.cpic import build_cpic_candidates
from genomeos.registry.curated import (
    CURATED_VARIANTS_SCHEMA,
    load,
    select_for_affected_burden,
    select_for_frequency_surface,
    validate_rows,
)


def _row(**overrides: str) -> dict[str, str]:
    row = {
        "variant_id": "clinvar:VCV000015333",
        "display_name": "HBB c.20A>T (HbS)",
        "gene": "HBB",
        "entity_type": "sequence_variant",
        "canonical_identifier": "VCV000015333",
        "identity_status": "resolved",
        "clinical_domain": "mendelian",
        "inheritance": "autosomal_recessive",
        "clinical_context": "sickle cell disease",
        "observation_type": "biallelic_allele_count",
        "inclusion_route": "clinvar_penetrance",
        "source_name": "ClinVar",
        "source_release": "2026-09-13",
        "source_record_id": "VCV000015333",
        "source_url": "https://www.ncbi.nlm.nih.gov/clinvar/variation/15333/",
        "source_classification": "Pathogenic",
        "penetrance_evidence_status": "identified_pending_review",
        "penetrance_evidence_locator": "https://www.ncbi.nlm.nih.gov/books/NBK1377/",
        "founder_context": "",
        "proposed_by": "agent:openai:codex",
        "proposal_method": "automated_proposal",
        "project_review_status": "pending",
        "reviewed_by": "",
        "reviewed_at": "",
        "refusal_reason": "",
        "set_version": "v1-candidate.1",
    }
    row.update(overrides)
    return row


def test_valid_candidate_row_passes_schema_and_cross_field_checks():
    frame = pd.DataFrame([_row()])
    assert len(validate_rows(frame)) == 1


def test_duplicate_variant_identity_is_refused():
    with pytest.raises(pandera.errors.SchemaError):
        CURATED_VARIANTS_SCHEMA.validate(pd.DataFrame([_row(), _row()]))


@pytest.mark.parametrize("clinical_context", ["height", "cognitive ability", "risk tolerance"])
def test_ineligible_trait_domains_cannot_enter_the_contract(clinical_context):
    bad = pd.DataFrame([_row(clinical_domain="anthropometric", clinical_context=clinical_context)])
    with pytest.raises(pandera.errors.SchemaError):
        CURATED_VARIANTS_SCHEMA.validate(bad)


def test_mendelian_candidate_requires_inheritance():
    missing_inheritance = pd.DataFrame([_row(inheritance="not_applicable")])
    with pytest.raises(ValueError, match="Mendelian.*inheritance"):
        validate_rows(missing_inheritance)


def test_cpic_candidate_requires_cpic_route_and_no_penetrance_claim():
    base = _row(
        variant_id="cpic:allele:110057",
        display_name="HLA-B*58:01",
        gene="HLA-B",
        entity_type="hla_allele",
        canonical_identifier="CPIC allele 110057",
        clinical_domain="pharmacogenomic",
        inheritance="not_applicable",
        clinical_context="allopurinol response",
        observation_type="multiallelic_allele_count",
        inclusion_route="cpic_a_b",
        source_name="CPIC",
        source_release="v1.60.0",
        source_record_id="CPIC:allele:110057",
        source_url="https://api.cpicpgx.org/v1/allele?id=eq.110057",
        source_classification="allele-status trigger",
        penetrance_evidence_status="not_applicable",
        penetrance_evidence_locator="",
    )
    assert len(validate_rows(pd.DataFrame([base]))) == 1

    with pytest.raises(ValueError, match="CPIC A/B inclusion route"):
        validate_rows(pd.DataFrame([{**base, "inclusion_route": "founder_validation"}]))
    with pytest.raises(ValueError, match="pharmacogenomic.*penetrance"):
        validate_rows(
            pd.DataFrame(
                [
                    {
                        **base,
                        "penetrance_evidence_status": "identified_pending_review",
                        "penetrance_evidence_locator": "https://example.org/not-applicable",
                    }
                ]
            )
        )


def test_review_identity_and_timestamp_must_match_review_state():
    with pytest.raises(ValueError, match="pending.*reviewed_by"):
        validate_rows(pd.DataFrame([_row(reviewed_by="human:expert")]))
    with pytest.raises(ValueError, match="verified.*reviewed_by"):
        validate_rows(pd.DataFrame([_row(project_review_status="verified")]))
    with pytest.raises(ValueError, match="reviewer must differ"):
        validate_rows(
            pd.DataFrame(
                [
                    _row(
                        project_review_status="verified",
                        reviewed_by="agent:openai:codex",
                        reviewed_at="2026-09-14",
                    )
                ]
            )
        )


def test_unresolved_identity_requires_a_reason_and_cannot_be_reviewed():
    unresolved = _row(
        variant_id="curated:smn1-zero-copy",
        display_name="SMN1 zero-functional-copy state",
        gene="SMN1",
        entity_type="copy_number_state",
        canonical_identifier="",
        identity_status="unresolved",
        observation_type="copy_number_carrier_count",
        inclusion_route="carrier_screening_validation",
        source_name="GeneReviews",
        source_record_id="NBK1352",
        source_url="https://www.ncbi.nlm.nih.gov/books/NBK1352/",
        source_classification="carrier-screening target",
        penetrance_evidence_status="ambiguous",
        penetrance_evidence_locator="https://www.ncbi.nlm.nih.gov/books/NBK1352/",
        refusal_reason="No single sequence variant represents SMN1 dosage or silent carriers.",
    )
    assert len(validate_rows(pd.DataFrame([unresolved]))) == 1
    with pytest.raises(ValueError, match="unresolved.*refusal_reason"):
        validate_rows(pd.DataFrame([{**unresolved, "refusal_reason": ""}]))
    with pytest.raises(ValueError, match="unresolved.*verified"):
        validate_rows(
            pd.DataFrame(
                [
                    {
                        **unresolved,
                        "project_review_status": "verified",
                        "reviewed_by": "human:expert",
                        "reviewed_at": "2026-09-14",
                    }
                ]
            )
        )


def test_frequency_and_affected_selection_fail_closed():
    reviewed = _row(
        project_review_status="verified",
        reviewed_by="human:clinical-geneticist",
        reviewed_at="2026-09-14",
        penetrance_evidence_status="verified",
    )
    cpic = _row(
        variant_id="cpic:allele:110057",
        display_name="HLA-B*58:01",
        gene="HLA-B",
        entity_type="hla_allele",
        canonical_identifier="CPIC allele 110057",
        clinical_domain="pharmacogenomic",
        inheritance="not_applicable",
        clinical_context="allopurinol response",
        observation_type="multiallelic_allele_count",
        inclusion_route="cpic_a_b",
        source_name="CPIC",
        source_release="v1.60.0",
        source_record_id="CPIC:allele:110057",
        source_url="https://api.cpicpgx.org/v1/allele?id=eq.110057",
        source_classification="allele-status trigger",
        penetrance_evidence_status="not_applicable",
        penetrance_evidence_locator="",
        project_review_status="verified",
        reviewed_by="human:clinical-geneticist",
        reviewed_at="2026-09-14",
    )
    pending = _row(
        variant_id="clinvar:VCV000007105",
        canonical_identifier="VCV000007105",
        source_record_id="VCV000007105",
    )
    frame = validate_rows(pd.DataFrame([reviewed, cpic, pending]))

    assert set(select_for_frequency_surface(frame)["variant_id"]) == {
        "clinvar:VCV000015333",
        "cpic:allele:110057",
    }
    assert list(select_for_affected_burden(frame)["variant_id"]) == [
        "clinvar:VCV000015333"
    ]


def _cpic_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    pairs = pd.DataFrame(
        [
            {
                "genesymbol": "HLA-B",
                "drugid": "RxNorm:519",
                "guidelineid": "100422",
                "cpiclevel": "A",
                "removed": "false",
            },
            {
                "genesymbol": "CYP2C19",
                "drugid": "RxNorm:704",
                "guidelineid": "100414",
                "cpiclevel": "A",
                "removed": "false",
            },
            {
                "genesymbol": "SCN1A",
                "drugid": "RxNorm:2002",
                "guidelineid": "",
                "cpiclevel": "B",
                "removed": "false",
            },
            {
                "genesymbol": "CYP2C19",
                "drugid": "RxNorm:999",
                "guidelineid": "",
                "cpiclevel": "C",
                "removed": "false",
            },
        ]
    )
    alleles = pd.DataFrame(
        [
            {
                "id": "110057",
                "genesymbol": "HLA-B",
                "name": "*58:01",
                "clinicalfunctionalstatus": "",
                "version": "147",
            },
            {
                "id": "2",
                "genesymbol": "CYP2C19",
                "name": "*2",
                "clinicalfunctionalstatus": "No function",
                "version": "10",
            },
            {
                "id": "1",
                "genesymbol": "CYP2C19",
                "name": "*1",
                "clinicalfunctionalstatus": "Normal function",
                "version": "10",
            },
        ]
    )
    drugs = pd.DataFrame(
        [
            {"drugid": "RxNorm:519", "name": "allopurinol", "guidelineid": "100422"},
            {"drugid": "RxNorm:704", "name": "clopidogrel", "guidelineid": "100414"},
            {"drugid": "RxNorm:2002", "name": "carbamazepine", "guidelineid": ""},
        ]
    )
    guidelines = pd.DataFrame(
        [
            {
                "id": "100422",
                "name": "HLA-B and allopurinol",
                "url": "https://www.clinpgx.org/guideline/PA166105003",
            },
            {
                "id": "100414",
                "name": "CYP2C19 and clopidogrel",
                "url": "https://www.clinpgx.org/guideline/PA166104956",
            },
        ]
    )
    return alleles, pairs, drugs, guidelines


def test_cpic_builder_is_vectorized_deterministic_and_keeps_explicit_gaps():
    alleles, pairs, drugs, guidelines = _cpic_inputs()
    variants, pair_targets, coverage = build_cpic_candidates(
        alleles,
        pairs,
        drugs,
        guidelines,
        source_release="v1.60.0",
        set_version="v1-candidate.1",
    )

    assert list(variants["variant_id"]) == ["cpic:allele:2", "cpic:allele:110057"]
    assert "cpic_level" not in variants.columns
    assert "cpic_level" in pair_targets.columns
    assert set(pair_targets["cpic_level"]) == {"A", "B"}
    assert set(pair_targets["gene"]) == {"CYP2C19", "HLA-B", "SCN1A"}
    assert coverage.set_index("gene").loc["SCN1A", "status"] == "no_allele_table"
    assert coverage.set_index("gene").loc["SCN1A", "candidate_count"] == 0

    reversed_outputs = build_cpic_candidates(
        alleles.iloc[::-1],
        pairs.iloc[::-1],
        drugs.iloc[::-1],
        guidelines.iloc[::-1],
        source_release="v1.60.0",
        set_version="v1-candidate.1",
    )
    for actual, expected in zip(reversed_outputs, (variants, pair_targets, coverage), strict=True):
        pd.testing.assert_frame_equal(actual, expected)


def test_load_validates_the_frozen_table(tmp_path: Path):
    path = tmp_path / "curated_variants.tsv"
    pd.DataFrame([_row()]).to_csv(path, sep="\t", index=False)
    assert list(load(path)["variant_id"]) == ["clinvar:VCV000015333"]


REPO = Path(__file__).resolve().parents[1]


def test_repository_sources_build_a_complete_reproducible_candidate_release(tmp_path: Path):
    outputs = []
    for name in ("first", "second"):
        out = tmp_path / name
        result = subprocess.run(
            [sys.executable, "scripts/build_curated_variant_set.py", "--out", str(out)],
            cwd=REPO,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        outputs.append(out)

    first, second = outputs
    for filename in (
        "curated_variants.tsv",
        "cpic_pair_targets.tsv",
        "cpic_coverage.tsv",
        "MANIFEST.json",
    ):
        assert (first / filename).read_bytes() == (second / filename).read_bytes()

    manifest = json.loads((first / "MANIFEST.json").read_text())
    assert manifest["counts"] == {
        "cpic_genes": 29,
        "cpic_genes_without_admitted_alleles": 9,
        "cpic_genes_without_admitted_function": 1,
        "cpic_genes_without_allele_table": 8,
        "cpic_pair_targets": 128,
        "pending_project_review": 698,
        "resolved_identities": 697,
        "unresolved_identities": 1,
        "variants": 698,
        "verified_for_affected_burden": 0,
        "verified_for_frequency_surface": 0,
    }

    variants = load(first / "curated_variants.tsv")
    assert {
        "clinvar:VCV000007105",
        "clinvar:VCV000003889",
        "curated:smn1-zero-functional-copy",
        "cpic:allele:110057",
    }.issubset(set(variants["variant_id"]))
    assert select_for_frequency_surface(variants).empty

    committed = REPO / "data" / "registry" / "curated-v1-candidate.1"
    for filename in (
        "curated_variants.tsv",
        "cpic_pair_targets.tsv",
        "cpic_coverage.tsv",
        "MANIFEST.json",
    ):
        assert (first / filename).read_bytes() == (committed / filename).read_bytes()


def test_release_builder_refuses_to_replace_an_existing_directory(tmp_path: Path):
    out = tmp_path / "already-there"
    out.mkdir()
    result = subprocess.run(
        [sys.executable, "scripts/build_curated_variant_set.py", "--out", str(out)],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "refusing to replace immutable output directory" in result.stderr
