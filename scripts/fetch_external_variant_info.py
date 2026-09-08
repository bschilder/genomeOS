#!/usr/bin/env python3
"""Build small, versioned gnomAD/dbSNP caches for eligible Atlas variants (design §11).

The cache is a publication aid, not an identifier resolver. Callers must provide a reviewed
GRCh38 `chr-pos-ref-alt` identity and, for dbSNP, a reviewed rsID. The normalizers verify the
returned alleles instead of guessing or broadening those identifiers.
"""

from __future__ import annotations

import argparse
import json
import re
import urllib.request
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
GNOMAD_API = "https://gnomad.broadinstitute.org/api"
DBSNP_API = "https://api.ncbi.nlm.nih.gov/variation/v0/refsnp/{numeric_rsid}"
VARIANT_PATTERN = re.compile(
    r"^chr(?P<chrom>(?:[1-9]|1[0-9]|2[0-2]|X|Y|MT))-(?P<pos>[1-9][0-9]*)-"
    r"(?P<ref>[ACGT]+)-(?P<alt>[ACGT]+)$"
)
RSID_PATTERN = re.compile(r"^rs(?P<number>[1-9][0-9]*)$")

GNOMAD_QUERY = """
query Variant($variantId: String!, $datasetId: DatasetId!) {
  variant(variantId: $variantId, dataset: $datasetId) {
    variant_id chrom pos ref alt rsids
    exome { ac an ac_hom ac_hemi }
    genome { ac an ac_hom ac_hemi }
    joint { ac an }
    transcript_consequences {
      gene_id gene_symbol transcript_id major_consequence hgvsc hgvsp
      is_canonical is_mane_select
    }
  }
}
""".strip()


def _variant_parts(variant_id: str) -> dict[str, str | int]:
    match = VARIANT_PATTERN.fullmatch(variant_id)
    if match is None:
        raise ValueError("variant_id must be normalized GRCh38 chr-pos-ref-alt")
    return {
        "alt": match.group("alt"),
        "chrom": match.group("chrom"),
        "pos": int(match.group("pos")),
        "ref": match.group("ref"),
    }


def _frequency_section(value: Any) -> dict[str, int | float] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("gnomAD frequency section must be an object or null")
    ac, an = value.get("ac"), value.get("an")
    if not isinstance(ac, int) or not isinstance(an, int) or ac < 0 or an <= 0 or ac > an:
        raise ValueError("gnomAD frequency section requires integer 0 <= ac <= an")
    result: dict[str, int | float] = {"ac": ac, "an": an, "af": ac / an}
    for field in ("ac_hom", "ac_hemi"):
        field_value = value.get(field)
        if field_value is not None:
            if not isinstance(field_value, int) or field_value < 0:
                raise ValueError(f"gnomAD {field} must be a non-negative integer")
            result[field] = field_value
    return result


def normalize_gnomad(
    payload: dict[str, Any],
    variant_id: str,
    dataset: str,
    retrieved_at: str,
) -> dict[str, Any]:
    """Normalize a gnomAD GraphQL result after exact variant verification."""
    expected = _variant_parts(variant_id)
    errors = payload.get("errors")
    if errors:
        raise ValueError(f"gnomAD returned errors: {errors}")
    record = payload.get("data", {}).get("variant")
    if not isinstance(record, dict):
        raise ValueError("gnomAD returned no variant record")
    returned = {
        "alt": record.get("alt"),
        "chrom": str(record.get("chrom")),
        "pos": record.get("pos"),
        "ref": record.get("ref"),
    }
    if returned != expected:
        raise ValueError(f"gnomAD identity {returned!r} != reviewed query {expected!r}")
    consequences = record.get("transcript_consequences") or []
    if not isinstance(consequences, list):
        raise ValueError("gnomAD transcript_consequences must be a list")
    preferred = next(
        (row for row in consequences if row.get("is_mane_select")),
        next((row for row in consequences if row.get("is_canonical")), None),
    )
    consequence = None
    if preferred is not None:
        consequence = {
            field: preferred.get(field)
            for field in (
                "gene_id",
                "gene_symbol",
                "transcript_id",
                "major_consequence",
                "hgvsc",
                "hgvsp",
                "is_canonical",
                "is_mane_select",
            )
        }
    return {
        "query": {"dataset": dataset, "normalized_variant_id": variant_id},
        "record": {
            **expected,
            "canonical_consequence": consequence,
            "exome": _frequency_section(record.get("exome")),
            "genome": _frequency_section(record.get("genome")),
            "joint": _frequency_section(record.get("joint")),
            "rsids": [str(value) for value in (record.get("rsids") or [])],
            "source_url": f"https://gnomad.broadinstitute.org/variant/{record['variant_id']}?dataset={dataset}",
        },
        "retrieved_at": retrieved_at,
        "schema_version": SCHEMA_VERSION,
        "source": "gnomad",
        "source_release": dataset,
    }


def _grch38_placement(payload: dict[str, Any]) -> list[dict[str, Any]]:
    placements = payload.get("primary_snapshot_data", {}).get("placements_with_allele", [])
    if not isinstance(placements, list):
        raise ValueError("dbSNP placements_with_allele must be a list")
    return [
        placement
        for placement in placements
        if placement.get("is_ptlp")
        and any(
            str(assembly.get("assembly_name", "")).startswith("GRCh38")
            and assembly.get("is_top_level") is True
            for assembly in placement.get("placement_annot", {}).get(
                "seq_id_traits_by_assembly", []
            )
        )
    ]


def normalize_dbsnp(
    payload: dict[str, Any],
    rsid: str,
    variant_id: str,
    retrieved_at: str,
) -> dict[str, Any]:
    """Select the exact reviewed GRCh38 allele from a multi-allelic RefSNP record."""
    rs_match = RSID_PATTERN.fullmatch(rsid)
    if rs_match is None:
        raise ValueError("rsid must match rs followed by a positive integer")
    expected = _variant_parts(variant_id)
    if str(payload.get("refsnp_id")) != rs_match.group("number"):
        raise ValueError("dbSNP refsnp_id does not match the reviewed rsID")
    match: dict[str, Any] | None = None
    for placement in _grch38_placement(payload):
        for allele in placement.get("alleles", []):
            spdi = allele.get("allele", {}).get("spdi", {})
            if (
                spdi.get("position") == expected["pos"] - 1
                and spdi.get("deleted_sequence") == expected["ref"]
                and spdi.get("inserted_sequence") == expected["alt"]
            ):
                match = {"hgvs": allele.get("hgvs"), "spdi": spdi}
                break
        if match is not None:
            break
    if match is None:
        raise ValueError("dbSNP returned no exact GRCh38 allele for the reviewed variant")
    citations = payload.get("citations") or []
    if not isinstance(citations, list):
        raise ValueError("dbSNP citations must be a list")
    build = str(payload.get("last_update_build_id", "unknown"))
    return {
        "query": {"normalized_variant_id": variant_id, "rsid": rsid},
        "record": {
            "citation_count": len(citations),
            "hgvs": match["hgvs"],
            "last_update_date": payload.get("last_update_date"),
            "rsid": rsid,
            "source_url": f"https://www.ncbi.nlm.nih.gov/snp/{rsid}",
            "spdi": match["spdi"],
        },
        "retrieved_at": retrieved_at,
        "schema_version": SCHEMA_VERSION,
        "source": "dbsnp",
        "source_release": f"dbSNP build {build}",
    }


def _request_json(url: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": "genomeOS-atlas/1"},
        method="GET" if body is None else "POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
        value = json.load(response)
    if not isinstance(value, dict):
        raise ValueError(f"{url}: expected a JSON object")
    return value


def _write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(f"{path} already exists; caches are immutable")
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant-id", required=True)
    parser.add_argument("--rsid", required=True)
    parser.add_argument("--dataset", default="gnomad_r4")
    parser.add_argument("--retrieved-at", required=True)
    parser.add_argument("--out-root", type=Path, required=True)
    args = parser.parse_args()
    parts = _variant_parts(args.variant_id)
    gnomad_id = f"{parts['chrom']}-{parts['pos']}-{parts['ref']}-{parts['alt']}"
    rs_match = RSID_PATTERN.fullmatch(args.rsid)
    if rs_match is None:
        raise ValueError("rsid must match rs followed by a positive integer")

    gnomad = normalize_gnomad(
        _request_json(
            GNOMAD_API,
            {
                "query": GNOMAD_QUERY,
                "variables": {"datasetId": args.dataset, "variantId": gnomad_id},
            },
        ),
        args.variant_id,
        args.dataset,
        args.retrieved_at,
    )
    dbsnp = normalize_dbsnp(
        _request_json(DBSNP_API.format(numeric_rsid=rs_match.group("number"))),
        args.rsid,
        args.variant_id,
        args.retrieved_at,
    )
    stem = args.variant_id.lower()
    _write(args.out_root / "gnomad" / f"{stem}.json", gnomad)
    _write(args.out_root / "dbsnp" / f"{args.rsid.lower()}.json", dbsnp)
    print(f"wrote reviewed gnomAD and dbSNP caches under {args.out_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
