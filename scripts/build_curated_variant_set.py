#!/usr/bin/env python3
"""Build the immutable v1 candidate set from reviewed-source snapshots (design §7.1, §13).

This is the filesystem boundary around :func:`genomeos.registry.cpic.build_cpic_candidates`.
It verifies the frozen CPIC input bytes before deriving rows, combines them with the explicitly
authored Mendelian/founder proposals, and publishes into a new directory atomically.  It does not
download data or promote any candidate to reviewed status.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
from pathlib import Path

import pandas as pd

from genomeos.registry.cpic import build_cpic_candidates
from genomeos.registry.curated import validate_rows

REPO = Path(__file__).resolve().parents[1]
DEFAULT_CPIC = REPO / "data" / "sources" / "cpic" / "v1.60.0"
DEFAULT_MANUAL = REPO / "data" / "sources" / "curated" / "manual_candidates.tsv"
OUTPUT_FILES = (
    "curated_variants.tsv",
    "cpic_pair_targets.tsv",
    "cpic_coverage.tsv",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def _verify_cpic_snapshot(cpic_dir: Path) -> dict:
    source_path = cpic_dir / "SOURCE.json"
    source = json.loads(source_path.read_text())
    for filename, record in source["tables"].items():
        path = cpic_dir / filename
        if not path.is_file():
            raise ValueError(f"CPIC snapshot file is missing: {path}")
        actual = _sha256(path)
        if actual != record["sha256"]:
            raise ValueError(
                f"CPIC snapshot hash mismatch for {filename}: expected {record['sha256']}, "
                f"observed {actual}"
            )
    license_path = cpic_dir / "LICENSE.md"
    if not license_path.is_file() or _sha256(license_path) != source["license_file_sha256"]:
        raise ValueError("CPIC snapshot license file is missing or does not match SOURCE.json")
    if source["terms_status"] != "no_restriction_found":
        raise ValueError("CPIC snapshot terms must be checked before derived rows are built")
    return source


def _verify_manual_sources(manual_path: Path) -> Path:
    source_path = manual_path.parent / "SOURCE.json"
    source = json.loads(source_path.read_text())
    statuses = {record["reuse_status"] for record in source["sources"].values()}
    if "not_checked" in statuses or not statuses:
        raise ValueError("every manual-candidate source must have a completed terms check")
    return source_path


def build(
    *,
    cpic_dir: Path,
    manual_path: Path,
    output_dir: Path,
    source_release: str,
    set_version: str,
) -> Path:
    """Build into a new directory and return its manifest path."""
    if output_dir.exists():
        raise FileExistsError(f"refusing to replace immutable output directory: {output_dir}")
    source = _verify_cpic_snapshot(cpic_dir)
    manual_source_path = _verify_manual_sources(manual_path)
    if source_release != source["data_release"]:
        raise ValueError(
            f"requested source release {source_release!r} does not match snapshot "
            f"{source['data_release']!r}"
        )

    variants, pair_targets, coverage = build_cpic_candidates(
        _read_csv(cpic_dir / "alleles.csv"),
        _read_csv(cpic_dir / "pairs_a_b.csv"),
        _read_csv(cpic_dir / "drugs.csv"),
        _read_csv(cpic_dir / "guidelines.csv"),
        source_release=source_release,
        set_version=set_version,
    )
    manual = validate_rows(
        pd.read_csv(manual_path, sep="\t", dtype=str, keep_default_na=False)
    )
    if set(manual["set_version"]) != {set_version}:
        raise ValueError("manual candidate set_version does not match the requested set version")
    combined = validate_rows(
        pd.concat([variants, manual], ignore_index=True).sort_values(
            "variant_id", kind="stable", ignore_index=True
        )
    )

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}-", dir=output_dir.parent))
    try:
        frames = {
            "curated_variants.tsv": combined,
            "cpic_pair_targets.tsv": pair_targets,
            "cpic_coverage.tsv": coverage,
        }
        for filename, frame in frames.items():
            frame.to_csv(temporary / filename, sep="\t", index=False, lineterminator="\n")

        manifest = {
            "evidence_kind": "curated_candidate_set",
            "publication_eligible": False,
            "publication_refusal": (
                "Every candidate remains pending independent project review; unresolved entities "
                "also require an admitted canonical representation."
            ),
            "set_version": set_version,
            "sources": {
                "cpic": {
                    "release": source_release,
                    "accessed_at": source["accessed_at"],
                    "source_data_date": source["source_data_date"],
                    "source_manifest_sha256": _sha256(cpic_dir / "SOURCE.json"),
                },
                "manual_candidates": {
                    "sha256": _sha256(manual_path),
                    "source_manifest_sha256": _sha256(manual_source_path),
                },
            },
            "counts": {
                "variants": len(combined),
                "cpic_pair_targets": len(pair_targets),
                "cpic_genes": int(coverage["gene"].nunique()),
                "cpic_genes_without_admitted_alleles": int(
                    coverage["status"].ne("candidate_gene_covered").sum()
                ),
                "cpic_genes_without_allele_table": int(
                    coverage["status"].eq("no_allele_table").sum()
                ),
                "cpic_genes_without_admitted_function": int(
                    coverage["status"].eq("no_admitted_function").sum()
                ),
                "resolved_identities": int(combined["identity_status"].eq("resolved").sum()),
                "unresolved_identities": int(combined["identity_status"].eq("unresolved").sum()),
                "pending_project_review": int(
                    combined["project_review_status"].eq("pending").sum()
                ),
                "verified_for_frequency_surface": 0,
                "verified_for_affected_burden": 0,
            },
            "outputs": {filename: _sha256(temporary / filename) for filename in OUTPUT_FILES},
            "builder": {
                "path": "scripts/build_curated_variant_set.py",
                "sha256": _sha256(Path(__file__)),
                "domain_path": "genomeos/registry/curated.py",
                "domain_sha256": _sha256(REPO / "genomeos" / "registry" / "curated.py"),
                "cpic_adapter_path": "genomeos/registry/cpic.py",
                "cpic_adapter_sha256": _sha256(REPO / "genomeos" / "registry" / "cpic.py"),
            },
        }
        manifest_path = temporary / "MANIFEST.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        temporary.rename(output_dir)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return output_dir / "MANIFEST.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cpic-dir", type=Path, default=DEFAULT_CPIC)
    parser.add_argument("--manual", type=Path, default=DEFAULT_MANUAL)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--source-release", default="v1.60.0")
    parser.add_argument("--set-version", default="v1-candidate.1")
    args = parser.parse_args()
    manifest = build(
        cpic_dir=args.cpic_dir,
        manual_path=args.manual,
        output_dir=args.out,
        source_release=args.source_release,
        set_version=args.set_version,
    )
    print(manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
