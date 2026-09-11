#!/usr/bin/env python3
"""Freeze a local source-bound reference-window manifest (design §§4–8, 12; #254)."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) in sys.path:
    sys.path.remove(str(ROOT))
sys.path.insert(0, str(ROOT))

import genomeos.validation.reference_window_manifest as manifest_module  # noqa: E402
import genomeos.validation.reference_window_types as types_module  # noqa: E402
import genomeos.validation.reference_windows as windows_module  # noqa: E402
from genomeos.validation.reference_window_manifest import (  # noqa: E402
    encode_manifest,
    parse_contig_declarations,
    parse_source_listing,
    windows_tsv,
)
from genomeos.validation.reference_window_types import (  # noqa: E402
    BIT_GENERATOR,
    CONFIG_SCHEMA_VERSION,
    CONTIG_EVIDENCE,
    COUNT_CONTRACT,
    DRAW_METHOD,
    EOF_BYTES,
    EXCLUSION_CHROM,
    EXCLUSION_END0,
    EXCLUSION_START0,
    HEADER_PREFIX_BYTES,
    MANIFEST_SCHEMA_VERSION,
    MAX_TRANSFER_BYTES,
    SEED,
    SOURCE_EVIDENCE_STATUS,
    STRATA,
    WIDTH,
    GenomicInterval,
    Provenance,
    WindowConfig,
    WindowManifest,
)
from genomeos.validation.reference_windows import select_reference_windows  # noqa: E402

_FOUR_MIB = 4 * 1024 * 1024
_CONTIG_LIMIT = 64 * 1024


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Freeze deterministic source-bound reference windows.")
    parser.add_argument("--source-metadata", required=True, type=Path)
    parser.add_argument("--contigs", required=True, type=Path)
    parser.add_argument("--source-audit", required=True, type=Path)
    parser.add_argument("--data-version", required=True)
    parser.add_argument(
        "--evidence-kind",
        required=True,
        choices=("synthetic_fixture", "public_reference_development"),
    )
    parser.add_argument("--out", required=True, type=Path)
    return parser


def _read_bounded(path: Path, limit: int, description: str) -> bytes:
    with path.open("rb") as handle:
        raw = handle.read(limit + 1)
    if len(raw) > limit:
        label = "4 MiB" if limit == _FOUR_MIB else "64 KiB"
        raise ValueError(f"{description} exceeds {label}")
    if not raw:
        raise ValueError(f"{description} must not be empty")
    return raw


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False) + "\n"
    ).encode("utf-8")


def _source_revision() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    revision = completed.stdout.strip()
    if (
        completed.returncode != 0
        or len(revision) != 40
        or any(char not in "0123456789abcdef" for char in revision)
    ):
        raise ValueError("unable to record a Git source revision")
    return revision


def _imported_source_hashes() -> tuple[tuple[str, str], ...]:
    paths = {
        "genomeos/validation/reference_window_manifest.py": Path(manifest_module.__file__).resolve(),
        "genomeos/validation/reference_window_types.py": Path(types_module.__file__).resolve(),
        "genomeos/validation/reference_windows.py": Path(windows_module.__file__).resolve(),
        "scripts/freeze_reference_windows.py": Path(__file__).resolve(),
    }
    root = ROOT.resolve()
    records = []
    for relative, actual in paths.items():
        try:
            actual.relative_to(root)
        except ValueError as error:
            raise ValueError(f"imported source is outside this checkout: {actual.name}") from error
        if actual != (root / relative).resolve():
            raise ValueError(f"imported source is outside this checkout: {actual.name}")
        records.append((relative, _sha256(actual.read_bytes())))
    return tuple(sorted(records))


def _build(args: argparse.Namespace) -> tuple[bytes, bytes]:
    source_raw = _read_bounded(args.source_metadata, _FOUR_MIB, "source metadata")
    contig_raw = _read_bounded(args.contigs, _CONTIG_LIMIT, "contig declarations")
    audit_raw = _read_bounded(args.source_audit, _FOUR_MIB, "source audit")
    try:
        audit_text = audit_raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("source audit must be UTF-8") from error
    if not audit_text.strip():
        raise ValueError("source audit must contain explanatory text")
    if (
        not isinstance(args.data_version, str)
        or not args.data_version.strip()
        or args.data_version != args.data_version.strip()
    ):
        raise ValueError("data version must be nonempty text without surrounding whitespace")

    sources = parse_source_listing(source_raw)
    lengths = parse_contig_declarations(contig_raw)
    config = WindowConfig(
        schema_version=CONFIG_SCHEMA_VERSION,
        width=WIDTH,
        strata=STRATA,
        seed=SEED,
        numpy_version=np.__version__,
        bit_generator=BIT_GENERATOR,
        draw_method=DRAW_METHOD,
        exclusion=GenomicInterval(EXCLUSION_CHROM, EXCLUSION_START0, EXCLUSION_END0),
        max_transfer_bytes=MAX_TRANSFER_BYTES,
        header_prefix_bytes=HEADER_PREFIX_BYTES,
        eof_bytes=EOF_BYTES,
    )
    windows = select_reference_windows(lengths, config)
    window_bytes = windows_tsv(windows)
    input_hashes = tuple(
        sorted(
            {
                "source_metadata": _sha256(source_raw),
                "contigs": _sha256(contig_raw),
                "source_audit": _sha256(audit_raw),
                "selection_config": _sha256(_canonical(asdict(config))),
            }.items()
        )
    )
    manifest = WindowManifest(
        schema_version=MANIFEST_SCHEMA_VERSION,
        config=config,
        contig_lengths=lengths,
        sources=sources,
        windows=windows,
        provenance=Provenance(
            data_version=args.data_version,
            evidence_kind=args.evidence_kind,
            input_sha256=input_hashes,
            imported_source_sha256=_imported_source_hashes(),
            source_revision=_source_revision(),
            python_version=platform.python_version(),
            source_audit_locator=args.source_audit.name,
        ),
        windows_sha256=_sha256(window_bytes),
        omitted_source_chromosomes=("chrX", "chrY"),
        contig_evidence=CONTIG_EVIDENCE,
        source_evidence_status=SOURCE_EVIDENCE_STATUS,
        count_contract=COUNT_CONTRACT,
        publication_eligible=False,
        p1_eligible=False,
    )
    manifest_bytes = encode_manifest(manifest)
    manifest_module.decode_manifest(manifest_bytes, windows_bytes=window_bytes)
    return window_bytes, manifest_bytes


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        if args.out.exists():
            raise ValueError(f"output directory already exists: {args.out}")
        window_bytes, manifest_bytes = _build(args)
        args.out.mkdir(parents=True, exist_ok=False)
        with (args.out / "windows.tsv").open("xb") as handle:
            handle.write(window_bytes)
        with (args.out / "manifest.json").open("xb") as handle:
            handle.write(manifest_bytes)
    except (OSError, ValueError) as error:
        parser.exit(2, f"error: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
