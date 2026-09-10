"""Build the HBB rs334 Salih 2010 literature corpus fixture (issue #151).

Replays the committed PubMed ESearch payload fixtures and writes the corpus under
the frozen literature-evidence contracts (design §§5.1-5.3; refusal rules §8):

    python scripts/build_hbb_salih_fixture.py
    python scripts/build_hbb_salih_fixture.py --refresh
    python scripts/build_hbb_salih_fixture.py --payloads DIR --out DIR [--email ADDR]

Replay mode is deterministic. Every timestamp is read from the payload fixture's
own `captured_at`, never from the wall clock, so the three corpus TSVs reproduce
byte for byte and a rerun cannot silently mint new search identities. `--refresh`
is the only path that touches the network and the only path that rewrites the
payload fixtures; it sends NCBI the tool identifier, and an email address when one
is supplied. PubMed is a live corpus, so a refresh can return candidates that the
screening table leaves `pending`; that is the designed outcome, not a defect.

The payload fixtures hold the verbatim ESearch responses and are the auditable
provenance for every manifest row. The corpus test runs this builder in replay mode
and diffs its output against the committed fixtures.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from genomeos.observations.evidence import (
    FIELD_EVIDENCE_COLUMNS,
    LITERATURE_EVIDENCE_COLUMNS,
    LITERATURE_SEARCH_COLUMNS,
    TRACKED_FIELDS,
    make_search_id,
    make_source_record_id,
    validate_literature_tables,
    validate_search_manifest,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

CORPUS = "hbb-rs334-salih-2010"
PMID = "pmid:20128890"
SOURCE_URL = "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC2829010/"
DECISION_REF = "https://github.com/bschilder/genomeOS/issues/149"
MANIFEST_VERSION = f"{CORPUS}@2026-09-09.1"
INGEST_VERSION = MANIFEST_VERSION
EXTRACTED_BY = "agent:hermes-sentinel:4.0"
CITATION = (
    "Salih NA, Hussain AA, Almugtaba IA, et al. Loss of balancing selection in the "
    "betaS globin locus. BMC Med Genet. 2010;11:21."
)

DEFAULT_OUT_DIR = REPO_ROOT / "tests" / "fixtures" / "literature" / CORPUS
DEFAULT_PAYLOAD_DIR = DEFAULT_OUT_DIR / "payloads"

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
    assert len(rows) == len(TRACKED_FIELDS)
    by_name = {row["field_name"]: row for row in rows}
    if set(by_name) != set(TRACKED_FIELDS):
        raise ValueError("field rows must cover exactly the tracked fields")
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
            row = {
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
            }
            fields.append(row)
    return evidence, fields


ESEARCH_ENDPOINT = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
NCBI_TOOL = "genomeos-corpus-builder"
QUERIES = {
    "Q1": "rs334[All Fields] AND (population[Title/Abstract] OR frequency[Title/Abstract])",
    "Q2": (
        '("sickle cell"[Title] OR "haemoglobin S"[Title] OR "hemoglobin S"[Title]) '
        'AND ("gene frequency"[Title/Abstract] OR "allele frequency"[Title/Abstract]) '
        "AND (population[Title/Abstract] OR survey[Title/Abstract] "
        "OR community[Title/Abstract])"
    ),
    "Q3": "rs334[All Fields] AND genotype[Title/Abstract]",
}


def payload_path(payload_dir: Path, qname: str) -> Path:
    return payload_dir / f"{qname}.json"


def load_payloads(payload_dir: Path) -> dict[str, dict]:
    """Read the committed ESearch payload fixtures. Never touches the network."""
    payloads: dict[str, dict] = {}
    for qname, term in QUERIES.items():
        path = payload_path(payload_dir, qname)
        if not path.exists():
            raise FileNotFoundError(
                f"missing committed payload fixture {path}; run with --refresh to capture it"
            )
        envelope = json.loads(path.read_text(encoding="utf-8"))
        if envelope.get("query") != term:
            raise ValueError(f"payload fixture {qname} does not hold its declared query")
        payloads[qname] = envelope
    return payloads


def refresh_payloads(payload_dir: Path, email: str | None = None) -> dict[str, dict]:
    """Query PubMed ESearch now and rewrite the payload fixtures with capture metadata."""
    payload_dir.mkdir(parents=True, exist_ok=True)
    captured_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    payloads: dict[str, dict] = {}
    for qname, term in QUERIES.items():
        params = {"db": "pubmed", "term": term, "retmax": "200", "retmode": "json",
                  "tool": NCBI_TOOL}
        if email is not None:
            params["email"] = email
        url = f"{ESEARCH_ENDPOINT}?{urllib.parse.urlencode(params)}"
        request = urllib.request.Request(url, headers={"User-Agent": NCBI_TOOL})
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = json.load(response)
        envelope = {
            "database": "pubmed",
            "query": term,
            "endpoint": ESEARCH_ENDPOINT,
            "retmode": "json",
            "retmax": "200",
            "captured_at": captured_at,
            "response": payload,
        }
        payload_path(payload_dir, qname).write_text(
            json.dumps(envelope, indent=1) + "\n", encoding="utf-8", newline="\n"
        )
        payloads[qname] = envelope
    return payloads


def build_search_rows(payloads: dict[str, dict]) -> list[dict]:
    """Expand the payload id lists into manifest rows, in payload order."""
    rows = []
    for qname, term in QUERIES.items():
        executed_at = payloads[qname]["captured_at"]
        sid = make_search_id("pubmed", term, executed_at)
        for pid in payloads[qname]["response"]["esearchresult"]["idlist"]:
            rows.append({"candidate_id": f"pmid:{pid}", "query_term": term,
                         "search_id": sid, "qname": qname, "executed_at": executed_at})
    return rows


def decision_for(qname: str, pmid: str) -> tuple[str, str | None]:
    """Screening decisions from the 2026-09-09 discovery pass (00_DISCOVERY.md)."""
    incl = {"20128890"}  # Salih 2010 - staged in this fixture
    excl = {
        "35811813": (
            "case-control malaria clinical groups (SM/UM/CTR); "
            "not a representative population sample"
        ),
        "29526279": (
            "1000 Genomes cohort already inside the atlas P1 adapter path; "
            "reconciliation duplicate, not an independent measurement for this slice"
        ),
        "35193898": (
            "newborn screening table prints percentages only; "
            "exact counts not recoverable (frequency-reconstructed)"
        ),
        "41290096": "patients with uncomplicated Plasmodium falciparum malaria; clinical cohort",
        "42355421": "ancient DNA osteological sample; not a contemporary population survey",
        "38378484": "molecular characterisation in sickle cell disease patients; affected cohort",
        "35785794": "secondary analysis of a transfusion trial; affected cohort",
        "35759254": "COVID-19 outcomes association study; no population frequency measurement",
        "33399855": "coronary heart disease association cohort; no population frequency measurement",
        "35934714": "malaria risk-score SNP model (association); no population frequency measurement",
        "39444160": "pneumonia association study in affected children; no population frequency measurement",
        "24934404": "candidate-gene malaria association study; no population frequency measurement",
    }
    if pmid in incl:
        return "included", None
    if pmid in excl:
        return "excluded", excl[pmid]
    return "pending", None


def write_tsv(path: Path, columns: tuple, rows: list[dict]) -> None:
    """Write ordered TSV rows; None becomes an empty cell. Always LF endings."""
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, delimiter="\t", lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
        w.writerow(columns)
        for row in rows:
            w.writerow(["" if row.get(c) is None else str(row.get(c)) for c in columns])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--payloads", type=Path, default=DEFAULT_PAYLOAD_DIR,
                    help="committed ESearch payload fixtures; the replay source")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT_DIR,
                    help="corpus fixture directory to write")
    ap.add_argument("--refresh", action="store_true",
                    help="query PubMed ESearch and rewrite the payload fixtures first")
    ap.add_argument("--email", default=None,
                    help="contact email sent to NCBI with --refresh (they ask for one)")
    args = ap.parse_args()

    if args.refresh:
        payloads = refresh_payloads(args.payloads, args.email)
    else:
        payloads = load_payloads(args.payloads)

    # Pinned, never the wall clock: the capture metadata is the single source of time.
    extracted_at = min(p["captured_at"] for p in payloads.values())

    evidence, fields = build_rows(extracted_at)
    searches = []
    for sr in build_search_rows(payloads):
        decision, reason = decision_for(sr["qname"], sr["candidate_id"].split(":")[1])
        searches.append({
            "search_id": sr["search_id"],
            "corpus_id": CORPUS,
            "database": "pubmed",
            "query": sr["query_term"],
            "executed_at": sr["executed_at"],
            "candidate_id": sr["candidate_id"],
            "decision": decision,
            "decision_reason": reason,
            "manifest_version": MANIFEST_VERSION,
        })

    args.out.mkdir(parents=True, exist_ok=True)
    write_tsv(args.out / "evidence.tsv", LITERATURE_EVIDENCE_COLUMNS, evidence)
    write_tsv(args.out / "field_evidence.tsv", FIELD_EVIDENCE_COLUMNS, fields)
    write_tsv(args.out / "searches.tsv", LITERATURE_SEARCH_COLUMNS, searches)

    # validate everything
    import pandas as pd
    ev = pd.read_csv(args.out / "evidence.tsv", sep="\t", dtype=str,
                     keep_default_na=False).replace("", pd.NA)
    fi = pd.read_csv(args.out / "field_evidence.tsv", sep="\t", dtype=str,
                     keep_default_na=False).replace("", pd.NA)
    se = pd.read_csv(args.out / "searches.tsv", sep="\t", dtype=str,
                     keep_default_na=False).replace("", pd.NA)
    ve, vf = validate_literature_tables(ev, fi)
    vs = validate_search_manifest(se)
    print(f"VALIDATION PASS: evidence={len(ve)} field={len(vf)} searches={len(vs)}")
    print("ac/an per population:")
    for _, row in ve.iterrows():
        print(
            f"  {row['population_label']}: ac={row['ac_lower']}/{row['ac_upper']} "
            f"an={row['an']} norm={row['normalization_status']} "
            f"reuse={row['reuse_status']} verif={row['verification_status']}"
        )


if __name__ == "__main__":
    main()
