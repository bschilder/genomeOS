"""Build the HBB rs334 Salih 2010 literature corpus ledgers (issue #151).

Deterministic transcription and derivation of the 2 evidence records and 38
field-evidence rows from Salih et al. 2010 Table 1, under the frozen
literature-evidence contracts (design §§5.2, 5.3):

    python scripts/build_hbb_salih_fixture.py \
        --out tests/fixtures/literature/hbb-rs334-salih-2010 \
        --extracted-at 2026-09-09T04:23:22Z

Search discovery and screening are not this script's responsibility. Design §4
gives scripts/fetch_pubmed_manifest.py the PubMed ESearch I/O, and design §5.1
makes screening a later immutable manifest version over that tool's all-pending
snapshot. The two versions live beside this output as searches.pending.tsv and
searches.tsv, and PROVENANCE.json records the queries, payloads and timestamps
they were built from.

Every timestamp is an explicit argument rather than the wall clock, so a rebuild
is reproducible and cannot silently mint a new corpus version. The corpus test
rebuilds through this script and diffs its output against the committed ledgers.
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

CORPUS = "hbb-rs334-salih-2010"
PMID = "pmid:20128890"
SOURCE_URL = "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC2829010/"
DECISION_REF = "https://github.com/bschilder/genomeOS/issues/149"
INGEST_VERSION = f"{CORPUS}@2026-09-09.1"
EXTRACTED_BY = "agent:hermes-sentinel:4.0"
CITATION = (
    "Salih NA, Hussain AA, Almugtaba IA, et al. Loss of balancing selection in the "
    "betaS globin locus. BMC Med Genet. 2010;11:21."
)

VARIANT_JSON = json.dumps({
    "printed_alleles": "HbA/HbS allele-specific PCR calls",
    "printed_build": "not stated (protein-allele level calls, 1994-2006 sampling)",
    "reference_resource": "dbSNP rs334; genomeOS gnomAD v4 cache chr11-5227002-T-A",
    "resolved_variant_id": "chr11-5227002-T-A",
    "strand": (
        "GRCh38 chr11:5227002 T>A; ALT A=HbS per gnomAD normalized record "
        "(canonical HBB c.20A>T p.Glu7Val)"
    ),
}, sort_keys=True, separators=(",", ":"))
COUNTED_JSON = json.dumps({
    "printed_alleles": "HbA/HbS allele-specific PCR calls",
    "printed_build": "not stated (protein-allele level calls, 1994-2006 sampling)",
    "reference_resource": "dbSNP rs334; genomeOS gnomAD v4 cache chr11-5227002-T-A",
    "resolved_counted_allele": "A",
    "strand": (
        "GRCh38 chr11:5227002 T>A; ALT A=HbS per gnomAD normalized record "
        "(canonical HBB c.20A>T p.Glu7Val)"
    ),
}, sort_keys=True, separators=(",", ":"))

REUSE_JSON = json.dumps({
    "checks": [{
        "checked_at": "2026-09-09",
        "finding": "no_restriction_found",
        "source_id": PMID,
        "surfaces": sorted([
            SOURCE_URL,
            "https://bmcmedgenet.biomedcentral.com/articles/10.1186/1471-2350-11-21",
        ]),
    }]
}, sort_keys=True, separators=(",", ":"))

POPULATIONS = [
    {
        "label": "Hausa",
        "locator": "table:1,row:N,col:Hausa-AA|AS|SS",
        "header_locator": "table:1,row:hausa-header",
        "aa": 118, "as": 91, "ss": 15,
        "n": 224,
        "note": (
            "Koka village, ~40 km east of Um-Salala, eastern bank of the River Rahad, "
            "~400 km SE of Khartoum, Sudan; coordinates unresolved (audit material)."
        ),
    },
    {
        "label": "Massalit",
        "locator": "table:1,row:N,col:Massalit-AA|AS|SS",
        "header_locator": "table:1,row:massalit-header",
        "aa": 163, "as": 68, "ss": 15,
        "n": 246,
        "note": (
            "Um-Salala village, eastern bank of the River Rahad, ~400 km SE of Khartoum, "
            "Sudan; coordinates unresolved (audit material)."
        ),
    },
]


def field_rows_for(population: dict, genotypes: str, ac: int, an: int) -> list[dict]:
    """Return the 19 tracked field-evidence rows for one population measurement."""
    rows = [
        dict(field_name="variant_id", evidence_status="derived", raw_value=VARIANT_JSON,
             evidence_source_id=PMID, source_locator="page:1,row:abstract",
             derivation_method="variant_normalization"),
        dict(field_name="rsid", evidence_status="reported", raw_value="rs334",
             evidence_source_id=PMID, source_locator="page:1,row:abstract",
             derivation_method=None),
        dict(field_name="counted_allele", evidence_status="derived", raw_value=COUNTED_JSON,
             evidence_source_id=PMID, source_locator="page:1,row:abstract",
             derivation_method="variant_normalization"),
        dict(field_name="population_label", evidence_status="reported",
             raw_value=population["label"], evidence_source_id=PMID,
             source_locator=population["header_locator"], derivation_method=None),
        dict(field_name="sample_id", evidence_status="not_reviewed",
             evidence_source_id=None, derivation_method=None,
             note=(
                 "Family-based village sample; 470 independent genotypes after relatedness "
                 "exclusion. Pending full-text methods/registry pass."
             )),
        dict(field_name="cohort_id", evidence_status="not_reviewed",
             evidence_source_id=None, derivation_method=None,
             note=(
                 f"Family-based village cohort ({population['n']} independent genotypes); "
                 "cohort_id assignment pending registry review."
             )),
        dict(field_name="an", evidence_status="derived",
             raw_value=json.dumps(
                 {"autosomal": True, "called_individuals": population["n"],
                  "complete_calls": True},
                 sort_keys=True, separators=(",", ":")),
             evidence_source_id=PMID, source_locator=population["locator"],
             derivation_method="allele_denominator_from_complete_diploid_sample"),
        dict(field_name="ac_lower", evidence_status="derived", raw_value=genotypes,
             evidence_source_id=PMID, source_locator=population["locator"],
             derivation_method="allele_count_from_genotypes",
             note=(
                 "Genotype classes mapped paper AA/AS/SS -> ref T/alt A: SS=AA (alt/alt), "
                 "AS=TA (het), AA=TT (ref/ref)."
             )),
        dict(field_name="ac_upper", evidence_status="derived", raw_value=genotypes,
             evidence_source_id=PMID, source_locator=population["locator"],
             derivation_method="allele_count_from_genotypes"),
        dict(field_name="reported_frequency", evidence_status="not_reported",
             evidence_source_id=PMID, checked_scope='["table:1","table:2"]',
             derivation_method=None,
             note=(
                 "No whole-population allele frequency printed for the Table 1 totals; "
                 "Table 2 reports malaria-strata counts only."
             )),
        dict(field_name="count_basis", evidence_status="derived",
             raw_value=json.dumps(
                 {"mapping_key": "count-basis-v1:genotype-derived",
                  "source_value": "AA/AS/SS genotype counts printed in Table 1",
                  "value": "genotype_derived"},
                 sort_keys=True, separators=(",", ":")),
             evidence_source_id=PMID, source_locator=population["locator"],
             derivation_method="controlled_vocabulary_mapping"),
        dict(field_name="denominator_basis", evidence_status="derived",
             raw_value=json.dumps(
                 {"mapping_key": "denominator-v1:diploid-individuals",
                  "source_value": "complete diploid calls (AA+AS+SS=N total row)",
                  "value": "diploid_individuals"},
                 sort_keys=True, separators=(",", ":")),
             evidence_source_id=PMID, source_locator=population["locator"],
             derivation_method="controlled_vocabulary_mapping"),
        dict(field_name="citation_id", evidence_status="reported", raw_value=PMID,
             evidence_source_id=PMID, source_locator="page:1,article-header",
             derivation_method=None),
        dict(field_name="citation_text", evidence_status="reported", raw_value=CITATION,
             evidence_source_id=PMID, source_locator="page:1,article-header",
             derivation_method=None),
        dict(field_name="assay", evidence_status="not_reviewed",
             evidence_source_id=None, derivation_method=None,
             note=(
                 "AS-PCR for HbA/HbS on buccal DNA described in Methods (PMC HTML); "
                 "deferred to independent full-text review."
             )),
        dict(field_name="sampling_design", evidence_status="not_reviewed",
             evidence_source_id=None, derivation_method=None,
             note=(
                 "Family-based village surveys 1994-2006 (8 surveys); "
                 "controlled-vocabulary mapping deferred to review pass."
             )),
        dict(field_name="disease_ascertainment_excluded", evidence_status="not_reviewed",
             evidence_source_id=None, derivation_method=None,
             note=(
                 "Village population samples under malaria surveillance; "
                 "ascertainment review deferred."
             )),
        dict(field_name="date_lower", evidence_status="not_reviewed",
             evidence_source_id=None, derivation_method=None,
             note=(
                 "Survey span 1994-2006 printed; per-row survey attribution not itemized, "
                 "date bounds deferred to review."
             )),
        dict(field_name="date_upper", evidence_status="not_reviewed",
             evidence_source_id=None, derivation_method=None,
             note=(
                 "Survey span 1994-2006 printed; per-row survey attribution not itemized, "
                 "date bounds deferred to review."
             )),
    ]
    by_name = {row["field_name"]: row for row in rows}
    if len(by_name) != len(rows) or set(by_name) != set(TRACKED_FIELDS):
        raise ValueError("field rows must cover exactly the tracked fields, once each")
    return [by_name[name] for name in TRACKED_FIELDS]


def build_rows(extracted_at: str) -> tuple[list[dict], list[dict]]:
    """Build the evidence and field-evidence rows, in TRACKED_FIELDS order."""
    evidence, fields = [], []
    for p in POPULATIONS:
        ac = p["as"] + 2 * p["ss"]
        an = 2 * p["n"]
        rid = make_source_record_id(CORPUS, PMID, p["locator"])
        genotypes = json.dumps({"AA": p["ss"], "TA": p["as"], "TT": p["aa"]},
                               sort_keys=True, separators=(",", ":"))
        # genotype-class JSON key order: AA (alt/alt), TA (het), TT (ref/ref)
        evidence.append({
            "source_record_id": rid,
            "corpus_id": CORPUS,
            "variant_id": "chr11-5227002-T-A",
            "rsid": "rs334",
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
            "reported_frequency": None,
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
            "reuse_checked_at": "2026-09-09",
            "notes": (
                f"Table 1 N row totals. AA/AS/SS are allele-specific PCR HbA/HbS calls; "
                f"HbS = ALT A at chr11-5227002-T-A. S copies = AS+2SS = {ac}, AN = 2N = {an}. "
                f"{p['note']}"
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
            f"{value!r} is not a UTC timestamp like 2026-09-09T04:23:22Z"
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

    # validate everything
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
