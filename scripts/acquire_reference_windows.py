#!/usr/bin/env python3
"""Acquire the reviewed frozen reference windows offline (acquisition design §§4–7)."""

from __future__ import annotations

import argparse
import hashlib
import platform
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) in sys.path:
    sys.path.remove(str(ROOT))
sys.path.insert(0, str(ROOT))

from genomeos.validation.reference_acquisition_codec import decode_acquisition_review  # noqa: E402
from genomeos.validation.reference_acquisition_types import (  # noqa: E402
    ACQUISITION_POLICY,
    AcquisitionInputs,
    AcquisitionManifest,
    AcquisitionReviewBundle,
    AcquisitionSourceReceipt,
    AcquisitionTotals,
    AcquisitionWindowReceipt,
    ArtifactRef,
    CohortInputHashes,
    RangeReceipt,
    RetainedIndex,
    RunProvenance,
)
from genomeos.validation.reference_byte_plan import BytePreflight  # noqa: E402
from genomeos.validation.reference_cohorts import (  # noqa: E402
    QualifiedCohortInputs,
    qualify_real_cohort_inputs,
)
from genomeos.validation.reference_preflight_input import decode_reviewed_preflight  # noqa: E402
from genomeos.validation.reference_tbi import MAX_COMPRESSED_BYTES  # noqa: E402
from genomeos.validation.reference_window_manifest import decode_manifest  # noqa: E402
from genomeos.validation.reference_window_types import WindowManifest  # noqa: E402
from scripts.reference_io_common import write_artifact_bytes  # noqa: E402
from scripts.reference_runtime import (  # noqa: E402
    acquisition_runtime,
    campaign_source_hashes,
    resolve_executable,
    resolve_gcloud,
)
from scripts.reference_window_artifacts import write_acquisition_manifest  # noqa: E402
from scripts.reference_window_io import (  # noqa: E402
    extract_native,
    fetch_metadata,
    fetch_range,
    iter_original_records,
    query_native_keys,
    read_source_header,
    stage_sparse,
    validate_original_records,
)

COHORT_NAMES = {
    "metadata": "metadata.tsv",
    "outliers": "outliers.txt",
    "exclusions": "exclusions.json",
    "technical_samples": "technical.samples.txt",
    "paper_samples": "paper.samples.txt",
    "dependency_audit": "dependency-audit.json",
}


class _ClosedReasonParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        del message
        self.exit(2, "error:invalid_input\n")


def _parser() -> argparse.ArgumentParser:
    parser = _ClosedReasonParser(description=__doc__)
    parser.add_argument("--windows-dir", required=True, type=Path)
    parser.add_argument("--preflight-dir", required=True, type=Path)
    parser.add_argument("--review", required=True, type=Path)
    parser.add_argument("--metadata", required=True, type=Path)
    parser.add_argument("--outliers", required=True, type=Path)
    parser.add_argument("--cohort-exclusions", required=True, type=Path)
    parser.add_argument("--technical-samples", required=True, type=Path)
    parser.add_argument("--paper-samples", required=True, type=Path)
    parser.add_argument("--dependency-audit", required=True, type=Path)
    parser.add_argument("--bcftools", required=True, type=Path)
    parser.add_argument("--tabix", required=True, type=Path)
    parser.add_argument("--bgzip", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    return parser


def _read(path: Path, limit: int) -> bytes:
    if not path.is_file() or path.is_symlink():
        raise ValueError("invalid_input")
    with path.open("rb") as handle:
        raw = handle.read(limit + 1)
    if not raw or len(raw) > limit:
        raise ValueError("invalid_input")
    return raw


def _digest(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while chunk := handle.read(1_048_576):
            digest.update(chunk)
            size += len(chunk)
    return size, digest.hexdigest()


def _retain(root: Path, relative: str, raw: bytes) -> ArtifactRef:
    return write_artifact_bytes(root, relative, raw)


def _artifact(root: Path, relative: str) -> ArtifactRef:
    size, digest = _digest(root / relative)
    return ArtifactRef(relative, size, digest)


def _line_count(path: Path) -> int:
    count = 0
    with path.open("rb") as handle:
        while chunk := handle.read(1_048_576):
            count += chunk.count(b"\n")
    return count


def _revision() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, check=False,
            capture_output=True, text=True, timeout=10,
        )
    except subprocess.SubprocessError as error:
        raise ValueError("invalid_input") from error
    revision = result.stdout.strip()
    if result.returncode or len(revision) != 40 or any(value not in "0123456789abcdef" for value in revision):
        raise ValueError("invalid_input")
    return revision


def _not_attempted(plan, reason: str) -> tuple[RangeReceipt, ...]:
    return tuple(
        RangeReceipt(
            plan.source.chrom, plan.source.vcf.generation, value.first, value.last,
            0, 0, 0, "not_attempted", reason, None, None, None, None, False, False,
        )
        for value in plan.merged_vcf_ranges
    )


def _files(root: Path, sparse: set[str]) -> tuple[ArtifactRef, ...]:
    paths = tuple(
        sorted(
            path.relative_to(root).as_posix()
            for path in root.rglob("*")
            if path.is_file()
            and path.relative_to(root).as_posix() not in sparse
            and path.name != "acquisition.json"
        )
    )
    return tuple(_artifact(root, path) for path in paths)


def _windows_tsv(windows: tuple[AcquisitionWindowReceipt, ...]) -> bytes:
    rows = ["window_id\tchrom\tstate\treason\traw_records\tnative_records\n"]
    for value in windows:
        fields = (
            value.window_id, value.chrom, value.state, value.reason,
            value.raw_records, value.native_records,
        )
        rows.append("\t".join("NA" if field is None else str(field) for field in fields) + "\n")
    return "".join(rows).encode()


def _refused_windows(manifest, chrom: str, reason: str) -> tuple[AcquisitionWindowReceipt, ...]:
    return tuple(
        AcquisitionWindowReceipt(
            window.window_id, chrom, "refused", reason, None, None,
            None, None, None, None, (),
        )
        for window in manifest.windows
        if window.chrom == chrom
    )


@dataclass(frozen=True)
class AcquisitionCompositionInputs:
    """Validated immutable evidence consumed by acquisition composition."""

    out: Path
    manifest: WindowManifest
    manifest_raw: bytes
    windows_raw: bytes
    preflight: BytePreflight
    preflight_raw: bytes
    review: AcquisitionReviewBundle
    review_raw: bytes
    indexes: tuple[RetainedIndex, ...]
    cohort: QualifiedCohortInputs
    bcftools: Path
    tabix: Path
    bgzip: Path
    gcloud: Path
    provenance: RunProvenance

    def __post_init__(self) -> None:
        if (
            type(self.manifest) is not WindowManifest
            or decode_manifest(self.manifest_raw, windows_bytes=self.windows_raw) != self.manifest
            or type(self.review) is not AcquisitionReviewBundle
            or decode_acquisition_review(self.review_raw) != self.review
            or type(self.preflight) is not BytePreflight
            or decode_reviewed_preflight(
                self.preflight_raw,
                manifest=self.manifest,
                manifest_raw=self.manifest_raw,
                indexes=self.indexes,
                review=self.review.preflight,
            )
            != self.preflight
            or type(self.cohort) is not QualifiedCohortInputs
            or type(self.provenance) is not RunProvenance
            or self.review.implementation_revision != self.provenance.code_revision
            or self.review.implementation_sha256 != self.provenance.imported_source_sha256
        ):
            raise ValueError("invalid acquisition composition inputs")
        if not all(
            isinstance(path, Path) and path.is_file() and not path.is_symlink()
            for path in (self.bcftools, self.tabix, self.bgzip, self.gcloud)
        ):
            raise ValueError("invalid acquisition composition tools")


def _load_real_composition(args: argparse.Namespace) -> AcquisitionCompositionInputs:
    if args.out.exists() or args.out.is_symlink():
        raise ValueError("invalid_input")
    manifest_path = args.windows_dir / "manifest.json"
    windows_path = args.windows_dir / "windows.tsv"
    preflight_path = args.preflight_dir / "preflight.json"
    manifest_raw = _read(manifest_path, 4_194_304)
    windows_raw = _read(windows_path, 65_536)
    preflight_raw = _read(preflight_path, 16_777_216)
    review_raw = _read(args.review, 1_048_576)
    manifest = decode_manifest(manifest_raw, windows_bytes=windows_raw)
    review = decode_acquisition_review(review_raw)
    indexes = tuple(
        RetainedIndex(
            chrom,
            _read(args.preflight_dir / "indexes" / f"{chrom}.tbi", MAX_COMPRESSED_BYTES),
        )
        for chrom in (f"chr{value}" for value in range(1, 23))
    )
    preflight = decode_reviewed_preflight(
        preflight_raw,
        manifest=manifest,
        manifest_raw=manifest_raw,
        indexes=indexes,
        review=review.preflight,
    )
    revision = _revision()
    source_hashes = campaign_source_hashes(ROOT)
    if (
        review.implementation_revision != revision
        or review.implementation_sha256 != source_hashes
    ):
        raise ValueError("review_mismatch")
    cohort_sources = {
        "metadata": args.metadata,
        "outliers": args.outliers,
        "exclusions": args.cohort_exclusions,
        "technical_samples": args.technical_samples,
        "paper_samples": args.paper_samples,
        "dependency_audit": args.dependency_audit,
    }
    cohort_raw = {name: _read(path, 268_435_456) for name, path in cohort_sources.items()}
    cohort = qualify_real_cohort_inputs(*(cohort_raw[name] for name in COHORT_NAMES))
    bcftools = resolve_executable(args.bcftools)
    tabix = resolve_executable(args.tabix)
    bgzip = resolve_executable(args.bgzip)
    gcloud = resolve_gcloud()
    runtime_identity = acquisition_runtime(
        bcftools, tabix, bgzip, gcloud
    )
    provenance = RunProvenance(
        revision,
        platform.python_version(),
        source_hashes,
        *runtime_identity,
    )
    return AcquisitionCompositionInputs(
        args.out,
        manifest,
        manifest_raw,
        windows_raw,
        preflight,
        preflight_raw,
        review,
        review_raw,
        indexes,
        cohort,
        bcftools,
        tabix,
        bgzip,
        gcloud,
        provenance,
    )


def compose_acquisition(
    inputs: AcquisitionCompositionInputs,
    *,
    final_guard: Callable[[], None] | None = None,
) -> AcquisitionManifest:
    """Compose one acquisition from already-qualified typed evidence."""
    if type(inputs) is not AcquisitionCompositionInputs:
        raise ValueError("invalid_input")
    if inputs.out.exists() or inputs.out.is_symlink():
        raise ValueError("invalid_input")
    manifest, preflight = inputs.manifest, inputs.preflight
    cohort_raw = {
        name: getattr(inputs.cohort, name)
        for name in COHORT_NAMES
    }
    source_samples = inputs.cohort.source_samples
    bcftools, gcloud = inputs.bcftools, inputs.gcloud
    inputs.out.mkdir(mode=0o700, parents=True, exist_ok=False)
    root = inputs.out.resolve(strict=True)
    input_refs = {
        "window_manifest": _retain(root, "inputs/window-manifest.json", inputs.manifest_raw),
        "windows": _retain(root, "inputs/windows.tsv", inputs.windows_raw),
        "preflight": _retain(root, "inputs/preflight.json", inputs.preflight_raw),
        "review": _retain(root, "inputs/review.json", inputs.review_raw),
    }
    cohort_refs = {
        name: _retain(root, f"inputs/cohort/{COHORT_NAMES[name]}", cohort_raw[name])
        for name in COHORT_NAMES
    }
    retained_indexes = {}
    for index in inputs.indexes:
        retained_indexes[index.chrom] = _retain(
            root,
            f"sources/{index.chrom}/INCOMPLETE.original.vcf.bgz.tbi",
            index.raw,
        )

    source_receipts = []
    window_receipts: dict[str, AcquisitionWindowReceipt] = {}
    sparse_paths: set[str] = set()
    wrapper = ROOT / "scripts/gcloud_repo.py"
    for plan in preflight.sources:
        chrom = plan.source.chrom
        metadata = fetch_metadata(
            plan.source.vcf, wrapper=wrapper, artifact_root=root,
            destination=Path(f"runtime/{chrom}.metadata.stdout"),
            gcloud_executable=gcloud,
        )
        receipts = []
        if metadata.state == "verified":
            for index, byte_range in enumerate(plan.merged_vcf_ranges):
                receipt = fetch_range(
                    plan.source.vcf, byte_range, wrapper=wrapper, artifact_root=root,
                    destination=Path(
                        f"sources/{chrom}/ranges/{byte_range.first}-{byte_range.last}.bin"
                    ),
                    gcloud_executable=gcloud,
                )
                receipts.append(receipt)
                if receipt.state != "verified":
                    receipts.extend(_not_attempted(plan, receipt.reason or "transfer_failed")[index + 1 :])
                    break
        else:
            receipts.extend(_not_attempted(plan, metadata.reason or "metadata_mismatch"))
        if metadata.state != "verified" or any(value.state != "verified" for value in receipts):
            reason = metadata.reason or next(value.reason for value in receipts if value.state != "verified")
            source_receipts.append(
                AcquisitionSourceReceipt(
                    plan.source, retained_indexes[chrom], metadata, tuple(receipts),
                    "refused", reason, None, None,
                )
            )
            window_receipts.update(
                (value.window_id, value) for value in _refused_windows(manifest, chrom, reason)
            )
            continue
        sparse_path = f"sources/{chrom}/INCOMPLETE.original.vcf.bgz"
        verified = stage_sparse(
            plan, tuple(receipts), artifact_root=root,
            index=retained_indexes[chrom], sparse_path=sparse_path,
        )
        sparse_paths.add(sparse_path)
        try:
            header, header_receipt = read_source_header(
                verified, plan, artifact_root=root, expected_contigs=manifest.contig_lengths,
                expected_samples=source_samples, destination=Path(f"sources/{chrom}/header.vcf"),
            )
        except ValueError as error:
            message = str(error)
            if "sample" in message:
                reason = "sample_mismatch"
            elif message == "artifact identity mismatch":
                reason = "artifact_mismatch"
            else:
                reason = message if message in {
                    "header_invalid", "limit_exceeded", "artifact_mismatch",
                } else "header_invalid"
            source_receipts.append(
                AcquisitionSourceReceipt(
                    plan.source, retained_indexes[chrom], metadata, tuple(receipts),
                    "refused", reason, verified, None,
                )
            )
            window_receipts.update(
                (value.window_id, value) for value in _refused_windows(manifest, chrom, reason)
            )
            continue
        source_receipts.append(
            AcquisitionSourceReceipt(
                plan.source, retained_indexes[chrom], metadata, tuple(receipts),
                "ready", None, verified, header_receipt,
            )
        )
        for window in (value for value in manifest.windows if value.chrom == chrom):
            prefix = f"windows/{window.window_id}"
            runs = []
            record_count = None
            raw_ref = None
            offsets_ref = None
            try:
                record_count = sum(
                    1
                    for _ in iter_original_records(
                        verified, plan, window, header, artifact_root=root,
                        raw_destination=Path(f"{prefix}.original-records.tsv"),
                        offsets_destination=Path(f"{prefix}.record-offsets.tsv"),
                    )
                )
                raw_ref = _artifact(root, f"{prefix}.original-records.tsv")
                offsets_ref = _artifact(root, f"{prefix}.record-offsets.tsv")
                extracted = extract_native(
                    verified, plan, window, artifact_root=root,
                    bcftools=bcftools,
                    stdout_path=f"{prefix}.native.bcf", stderr_path=f"{prefix}.extract.stderr",
                )
                runs.append(extracted)
                if extracted.state != "complete":
                    raise ValueError(extracted.reason)
                keys = query_native_keys(
                    extracted.stdout, artifact_root=root, bcftools=bcftools,
                    stdout_path=f"{prefix}.native.keys.tsv", stderr_path=f"{prefix}.keys.stderr",
                )
                runs.append(keys)
                if keys.state != "complete":
                    raise ValueError(keys.reason)
                native_count = validate_original_records(
                    verified,
                    plan,
                    window,
                    header,
                    artifact_root=root,
                    raw=raw_ref,
                    offsets=offsets_ref,
                    native_keys=keys.stdout,
                )
                state = "records_acquired" if record_count else "no_records"
                window_receipts[window.window_id] = AcquisitionWindowReceipt(
                    window.window_id, chrom, state, None, record_count, native_count,
                    raw_ref, offsets_ref, extracted.stdout, keys.stdout, tuple(runs),
                )
            except ValueError as error:
                reason = str(error) if str(error) in {value for value in (
                    "record_invalid", "native_encoding_refused", "native_mismatch", "limit_exceeded",
                    "timeout", "artifact_mismatch", "coverage_gap",
                )} else "record_invalid"
                if raw_ref is None or offsets_ref is None:
                    record_count = None
                    raw_ref = None
                    offsets_ref = None
                window_receipts[window.window_id] = AcquisitionWindowReceipt(
                    window.window_id, chrom, "refused", reason,
                    record_count, None,
                    raw_ref, offsets_ref,
                    runs[0].stdout if runs else None, runs[1].stdout if len(runs) > 1 else None,
                    tuple(runs),
                )
    ordered_windows = tuple(window_receipts[value.window_id] for value in manifest.windows)
    write_artifact_bytes(root, "windows.tsv", _windows_tsv(ordered_windows))
    ranges = tuple(value for source in source_receipts for value in source.ranges)
    totals = AcquisitionTotals(
        preflight.total_planned_bytes,
        sum(value.size_bytes for value in retained_indexes.values()),
        sum(value.receipt.received_bytes for value in preflight.sources),
        sum(value.requested_bytes for value in ranges),
        sum(value.received_bytes for value in ranges),
        sum(value.adapter_invocations for value in ranges),
        sum(value.metadata.adapter_invocations for value in source_receipts),
        sum(value.metadata.stdout_bytes for value in source_receipts),
        None, None, None,
    )
    if final_guard is not None:
        final_guard()
    cohort_hashes = CohortInputHashes(*(cohort_refs[name].sha256 for name in COHORT_NAMES))
    complete = all(value.state == "ready" for value in source_receipts) and all(
        value.state != "refused" for value in ordered_windows
    )
    acquisition = AcquisitionManifest(
        "reference_window_acquisition_v1",
        AcquisitionInputs(cohort=cohort_hashes, **input_refs),
        inputs.provenance, ACQUISITION_POLICY, tuple(source_receipts), ordered_windows,
        _files(root, sparse_paths), totals, complete, False, False, False,
    )
    write_acquisition_manifest(
        root,
        acquisition,
        preflight=preflight,
        cohort_inputs=inputs.cohort,
    )
    return acquisition


def acquire(args: argparse.Namespace) -> AcquisitionManifest:
    """Apply real campaign gates, then compose the frozen acquisition."""
    inputs = _load_real_composition(args)
    expected_runtime = (
        inputs.provenance.tool_versions,
        inputs.provenance.executable_sha256,
        inputs.provenance.sdk_source_sha256,
    )

    def final_guard() -> None:
        if (
            _revision() != inputs.provenance.code_revision
            or campaign_source_hashes(ROOT) != inputs.provenance.imported_source_sha256
            or acquisition_runtime(
                inputs.bcftools,
                inputs.tabix,
                inputs.bgzip,
                inputs.gcloud,
            )
            != expected_runtime
        ):
            raise ValueError("invalid_input")

    return compose_acquisition(inputs, final_guard=final_guard)


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as error:
        return int(error.code)
    try:
        result = acquire(args)
    except (OSError, ValueError):
        print("error:invalid_input", file=sys.stderr)
        return 2
    return 0 if result.complete else 1


if __name__ == "__main__":
    raise SystemExit(main())
