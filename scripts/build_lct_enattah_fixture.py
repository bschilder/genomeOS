"""Build the LCT rs4988235 Enattah 2007 literature corpus ledgers (issue #237).

Deterministic transcription and derivation of the 12 evidence records and 228
field-evidence rows from Enattah et al. 2007 Table 3, under the frozen
literature-evidence contracts (design §§5.2, 5.3):

    python scripts/build_lct_enattah_fixture.py \
        --out tests/fixtures/literature/lct-enattah-2007 \
        --extracted-at 2026-09-06T06:55:57Z

Search discovery and screening are not this script's responsibility. Design §4
gives scripts/fetch_pubmed_manifest.py the PubMed ESearch I/O, and design §5.1
makes screening a later immutable manifest version over that tool's all-pending
snapshot. searches.pending.tsv beside this output is that all-pending snapshot.
The published searches.tsv is the merged manifest and is not rewritten here:
re-deriving it changes search_id by construction, which is a data revision.
PROVENANCE.json records the queries, payloads and timestamps involved.

Every timestamp is an explicit argument rather than the wall clock, so a rebuild
is reproducible and cannot silently mint a new corpus version. The corpus test
rebuilds through this script and diffs its output against the committed ledgers.

Discovery correction (issue #237): the slice was merged with a 37-row manifest
whose third search had been captured with an effective `retmax` of 25. That
query matches 58 records at PubMed, so the merged manifest recorded the 25 most
recent matches and said nothing about the cap. The committed payloads are a
re-capture: Q1 and Q2 reproduce the merged candidate sets exactly, and Q3
carries the full 58. Re-deriving a manifest over those payloads changes
search_id by construction, so the published searches.tsv is left as merged and
the corrected snapshot is committed beside it. See
docs/audits/lct-enattah-2007-corpus.md for the reproduction evidence.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from genomeos.observations.evidence import (
    FIELD_EVIDENCE_COLUMNS,
    LITERATURE_EVIDENCE_COLUMNS,
    TRACKED_FIELDS,
    make_source_record_id,
    validate_literature_tables,
)

CORPUS = "lct-rs4988235"
PMID = "pmid:17701907"
SOURCE_URL = "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC1950831/"
DECISION_REF = "https://github.com/bschilder/genomeOS/issues/149"
INGEST_VERSION = f"{CORPUS}@2026-09-06.1"
EXTRACTED_BY = "agent:hermes-sentinel:4.0"
VARIANT_LOCATOR = "table:1,row:4,col:dbSNP Accession Number"
CITATION_LOCATOR = "page:1,article-header"
NOT_REVIEWED_NOTE = "Not yet reviewed in full text; pending methods/registry pass."
CITATION = (
    "Enattah NS, Trudeau A, et al. Evidence of still-ongoing convergence evolution of the "
    "lactase persistence T-13910 alleles in humans. Am J Hum Genet. 2007;81(3):615-625."
)

VARIANT_JSON = json.dumps({
    "printed_alleles": "C/T",
    "printed_build": "paper build hg18-era chr2:136442378",
    "reference_resource": "dbSNP rs4988235 / Ensembl GRCh38 chr2:135851076",
    "resolved_variant_id": "chr2-135851076-G-A",
    "strand": "paper C/T-13910 gene/minus-strand notation -> GRCh38 plus-strand G>A",
}, sort_keys=True, separators=(",", ":"))

COUNTED_JSON = json.dumps({
    "printed_alleles": "C/T",
    "printed_build": "paper build hg18-era chr2:136442378",
    "reference_resource": "dbSNP rs4988235 / Ensembl GRCh38 chr2:135851076",
    "resolved_counted_allele": "A",
    "strand": "paper C/T-13910 gene/minus-strand notation -> GRCh38 plus-strand G>A",
}, sort_keys=True, separators=(",", ":"))

COUNT_BASIS_JSON = json.dumps({
    "mapping_key": "count-basis-v1:genotype-derived",
    "source_value": "CC/CT/TT genotype counts printed in Table 3",
    "value": "genotype_derived",
}, sort_keys=True, separators=(",", ":"))

DENOMINATOR_JSON = json.dumps({
    "mapping_key": "denominator-v1:diploid-individuals",
    "source_value": "genotype counts over complete diploid calls (CC+CT+TT=N)",
    "value": "diploid_individuals",
}, sort_keys=True, separators=(",", ":"))

REUSE_JSON = json.dumps({
    "checks": [{
        "checked_at": "2026-09-06",
        "finding": "no_restriction_found",
        "source_id": PMID,
        "surfaces": sorted([SOURCE_URL]),
    }]
}, sort_keys=True, separators=(",", ":"))

# Enattah 2007 Table 3, in table order. Genotypes are the paper's CC/CT/TT classes,
# mapped to GRCh38 plus-strand G/G, G/A, A/A. `printed` is the paper's own frequency
# string, kept verbatim because it is a reported value, not a derived one.
POPULATIONS = [
    {"label": "Komi", "locator": "table:3,row:komi",
     "ref_ref": 7, "het": 3, "alt_alt": 0, "printed": "15"},
    {"label": "Udmurts", "locator": "table:3,row:udmurts",
     "ref_ref": 12, "het": 16, "alt_alt": 2, "printed": "33.4"},
    {"label": "Mokshas", "locator": "table:3,row:mokshas",
     "ref_ref": 13, "het": 17, "alt_alt": 0, "printed": "28.4"},
    {"label": "Erzas", "locator": "table:3,row:erzas",
     "ref_ref": 17, "het": 10, "alt_alt": 3, "printed": "26.7"},
    {"label": "Saami", "locator": "table:3,row:saami",
     "ref_ref": 20, "het": 10, "alt_alt": 0, "printed": "16.7"},
    {"label": "Finns, eastern", "locator": "table:3,row:finns-eastern",
     "ref_ref": 18, "het": 35, "alt_alt": 24, "printed": "53.9"},
    {"label": "Finns, western", "locator": "table:3,row:finns-western",
     "ref_ref": 25, "het": 68, "alt_alt": 61, "printed": "61.7"},
    {"label": "Basques", "locator": "table:3,row:basques",
     "ref_ref": 7, "het": 44, "alt_alt": 34, "printed": "65.9"},
    {"label": "Pathan", "locator": "table:3,row:pathan",
     "ref_ref": 12, "het": 15, "alt_alt": 1, "printed": "30.4"},
    {"label": "Sindi", "locator": "table:3,row:sindi",
     "ref_ref": 10, "het": 13, "alt_alt": 5, "printed": "41.1"},
    {"label": "Brahui", "locator": "table:3,row:brahui",
     "ref_ref": 17, "het": 10, "alt_alt": 3, "printed": "26.7"},
    {"label": "Qashqai", "locator": "table:3,row:qashqai",
     "ref_ref": 9, "het": 1, "alt_alt": 0, "printed": "5"},
]


def _at_column(population: dict, column: str) -> str:
    """Return the Table 3 locator for one column of a population's row.

    Evidence rows carry the row locator; field rows carry the column the value
    was actually read from, so a reviewer can go straight to the cell.
    """
    return f"{population['locator']},col:{column}"


def field_rows_for(population: dict, genotypes: str, ac: int, an: int) -> list[dict]:
    """Return the 19 tracked field-evidence rows for one population measurement."""
    rows = [
        dict(field_name="variant_id", evidence_status="derived", raw_value=VARIANT_JSON,
             evidence_source_id=PMID, source_locator=VARIANT_LOCATOR,
             derivation_method="variant_normalization",
             note="GRCh38 G>A from rs4988235; paper SNP4 C/T-13910."),
        dict(field_name="rsid", evidence_status="reported", raw_value="rs4988235",
             evidence_source_id=PMID, source_locator=VARIANT_LOCATOR,
             derivation_method=None),
        dict(field_name="counted_allele", evidence_status="derived", raw_value=COUNTED_JSON,
             evidence_source_id=PMID, source_locator=VARIANT_LOCATOR,
             derivation_method="variant_normalization",
             note="ALT allele A = paper T-13910 plus-strand."),
        dict(field_name="population_label", evidence_status="reported",
             raw_value=population["label"], evidence_source_id=PMID,
             source_locator=_at_column(population, "Region or Population"),
             derivation_method=None),
        dict(field_name="sample_id", evidence_status="not_reviewed",
             evidence_source_id=None, derivation_method=None, note=NOT_REVIEWED_NOTE),
        dict(field_name="cohort_id", evidence_status="not_reviewed",
             evidence_source_id=None, derivation_method=None, note=NOT_REVIEWED_NOTE),
        dict(field_name="an", evidence_status="derived",
             raw_value=json.dumps(
                 {"autosomal": True, "called_individuals": an // 2, "complete_calls": True},
                 sort_keys=True, separators=(",", ":")),
             evidence_source_id=PMID, source_locator=_at_column(population, "N"),
             derivation_method="allele_denominator_from_complete_diploid_sample"),
        dict(field_name="ac_lower", evidence_status="derived", raw_value=genotypes,
             evidence_source_id=PMID, source_locator=_at_column(population, "CC|CT|TT"),
             derivation_method="allele_count_from_genotypes",
             note="Genotype classes mapped paper C/T -> plus-strand G/A."),
        dict(field_name="ac_upper", evidence_status="derived", raw_value=genotypes,
             evidence_source_id=PMID, source_locator=_at_column(population, "CC|CT|TT"),
             derivation_method="allele_count_from_genotypes"),
        dict(field_name="reported_frequency", evidence_status="reported",
             raw_value=population["printed"], evidence_source_id=PMID,
             source_locator=_at_column(population, "T"),
             derivation_method=None),
        dict(field_name="count_basis", evidence_status="derived", raw_value=COUNT_BASIS_JSON,
             evidence_source_id=PMID, source_locator=_at_column(population, "CC|CT|TT"),
             derivation_method="controlled_vocabulary_mapping"),
        dict(field_name="denominator_basis", evidence_status="derived",
             raw_value=DENOMINATOR_JSON, evidence_source_id=PMID,
             source_locator=_at_column(population, "N"),
             derivation_method="controlled_vocabulary_mapping"),
        dict(field_name="citation_id", evidence_status="reported", raw_value=PMID,
             evidence_source_id=PMID, source_locator=CITATION_LOCATOR,
             derivation_method=None),
        dict(field_name="citation_text", evidence_status="reported", raw_value=CITATION,
             evidence_source_id=PMID, source_locator=CITATION_LOCATOR,
             derivation_method=None),
        dict(field_name="assay", evidence_status="not_reviewed",
             evidence_source_id=None, derivation_method=None, note=NOT_REVIEWED_NOTE),
        dict(field_name="sampling_design", evidence_status="not_reviewed",
             evidence_source_id=None, derivation_method=None, note=NOT_REVIEWED_NOTE),
        dict(field_name="disease_ascertainment_excluded", evidence_status="not_reviewed",
             evidence_source_id=None, derivation_method=None, note=NOT_REVIEWED_NOTE),
        dict(field_name="date_lower", evidence_status="not_reviewed",
             evidence_source_id=None, derivation_method=None, note=NOT_REVIEWED_NOTE),
        dict(field_name="date_upper", evidence_status="not_reviewed",
             evidence_source_id=None, derivation_method=None, note=NOT_REVIEWED_NOTE),
    ]
    by_name = {row["field_name"]: row for row in rows}
    if len(by_name) != len(rows) or set(by_name) != set(TRACKED_FIELDS):
        raise ValueError("field rows must cover exactly the tracked fields, once each")
    return [by_name[name] for name in TRACKED_FIELDS]


def build_rows(extracted_at: str) -> tuple[list[dict], list[dict]]:
    """Build the evidence and field-evidence rows, in TRACKED_FIELDS order."""
    evidence, fields = [], []
    for p in POPULATIONS:
        n = p["ref_ref"] + p["het"] + p["alt_alt"]
        an = 2 * n
        ac = p["het"] + 2 * p["alt_alt"]
        rid = make_source_record_id(CORPUS, PMID, p["locator"])
        genotypes = json.dumps(
            {"AA": p["alt_alt"], "GA": p["het"], "GG": p["ref_ref"]},
            sort_keys=True, separators=(",", ":"))
        evidence.append({
            "source_record_id": rid,
            "corpus_id": CORPUS,
            "variant_id": "chr2-135851076-G-A",
            "rsid": "rs4988235",
            "counted_allele": "A",
            "normalization_status": "verified",
            "population_label": p["label"],
            "sample_id": None,
            "cohort_id": None,
            "assay": None,
            "sampling_design": None,
            "disease_ascertainment_excluded": None,
            "date_lower": None,
            "date_upper": None,
            "an": an,
            "ac_lower": ac,
            "ac_upper": ac,
            "reported_frequency": p["printed"],
            "count_basis": "genotype_derived",
            "denominator_basis": "diploid_individuals",
            "citation_id": PMID,
            "citation_text": CITATION,
            "record_source_id": PMID,
            "record_locator": p["locator"],
            "record_source_url": SOURCE_URL,
            "verification_status": "pending",
            "extraction_method": "automated_proposal",
            "extracted_by": EXTRACTED_BY,
            "extracted_at": extracted_at,
            "verified_by": None,
            "verified_at": None,
            "verification_reference": None,
            "reuse_status": "no_restriction_found",
            "reuse_evidence": REUSE_JSON,
            "reuse_checked_at": "2026-09-06",
            "notes": (
                f"Genotype counts CC/CT/TT (paper notation) from PMC table 3. "
                f"T-13910 copies=CT+2TT={ac}, AN=2N={an}. Printed T%={p['printed']}; "
                f"computed {ac / an * 100:.4f}%."
            ),
            "ingest_version": INGEST_VERSION,
        })
        for fr in field_rows_for(p, genotypes, ac, an):
            fields.append({
                "source_record_id": rid,
                "field_name": fr["field_name"],
                "evidence_status": fr["evidence_status"],
                "raw_value": fr.get("raw_value"),
                "evidence_source_id": fr.get("evidence_source_id"),
                "source_locator": fr.get("source_locator"),
                "checked_scope": fr.get("checked_scope"),
                "derivation_method": fr.get("derivation_method"),
                "decision_reference": DECISION_REF if fr["evidence_status"] == "derived" else None,
                "notes": fr.get("note"),
            })
    return evidence, fields


def write_tsv(path: Path, columns: tuple, rows: list[dict]) -> None:
    """Write ordered TSV rows; None becomes an empty cell. Always LF endings."""
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh, delimiter="\t", lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
        writer.writerow(columns)
        for row in rows:
            writer.writerow(["" if row.get(c) is None else str(row.get(c)) for c in columns])


def _timestamp(value: str) -> str:
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            f"{value!r} is not a UTC timestamp like 2026-09-06T06:55:57Z"
        ) from error
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True,
                        help="corpus fixture directory to write the ledgers into")
    parser.add_argument("--extracted-at", type=_timestamp, required=True,
                        help="UTC extraction timestamp, recorded on every evidence row")
    args = parser.parse_args()

    evidence, fields = build_rows(args.extracted_at)
    args.out.mkdir(parents=True, exist_ok=True)
    write_tsv(args.out / "evidence.tsv", LITERATURE_EVIDENCE_COLUMNS, evidence)
    write_tsv(args.out / "field_evidence.tsv", FIELD_EVIDENCE_COLUMNS, fields)

    import pandas as pd
    ev = pd.read_csv(args.out / "evidence.tsv", sep="\t", dtype=str,
                     keep_default_na=False).replace("", pd.NA)
    fi = pd.read_csv(args.out / "field_evidence.tsv", sep="\t", dtype=str,
                     keep_default_na=False).replace("", pd.NA)
    validated_evidence, validated_fields = validate_literature_tables(ev, fi)
    print(f"VALIDATION PASS: evidence={len(validated_evidence)} field={len(validated_fields)}")
    print(f"extracted_at: {args.extracted_at}")
    for _, row in validated_evidence.iterrows():
        print(
            f"  {row['population_label']}: ac={row['ac_lower']}/{row['ac_upper']} "
            f"an={row['an']} norm={row['normalization_status']} "
            f"reuse={row['reuse_status']} verif={row['verification_status']}"
        )


if __name__ == "__main__":
    main()
