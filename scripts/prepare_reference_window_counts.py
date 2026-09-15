#!/usr/bin/env python3
"""Prepare four frozen reference count tracks offline (reference acquisition design §§5–7)."""

from __future__ import annotations

import argparse
import hashlib
import platform
import sqlite3
import subprocess
import sys
from collections import Counter
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) in sys.path:
    sys.path.remove(str(ROOT))
sys.path.insert(0, str(ROOT))

from genomeos.validation.reference_acquisition_codec import encode_acquisition  # noqa: E402
from genomeos.validation.reference_acquisition_types import (  # noqa: E402
    REASONS,
    AcquisitionManifest,
    AcquisitionWindowReceipt,
    ArtifactRef,
    CohortInputHashes,
    NativeCountFiles,
    NativeTokenFiles,
    RunProvenance,
)
from genomeos.validation.reference_cohorts import (  # noqa: E402
    PAPER_STAGE,
    TECHNICAL_STAGE,
    Cohort,
    QualifiedCohortInputs,
    cohort_columns,
    qualify_real_cohort_inputs,
)
from genomeos.validation.reference_genotypes import (  # noqa: E402
    MissingOriginCount,
    QcTally,
    VariantCounts,
    count_cohort_pair_with_native,
    plan_cohort_pair,
)
from genomeos.validation.reference_preparation import prepare_rows  # noqa: E402
from genomeos.validation.reference_preparation_codec import (  # noqa: E402
    encode_dependency,
    encode_preparation_inputs,
)
from genomeos.validation.reference_preparation_types import (  # noqa: E402
    DEPENDENCY_EDGES,
    PREPARATION_POLICY,
    DependencyEvidence,
    PreparationInputs,
    PreparationManifest,
    PreparationStageReceipt,
    PreparationWindowReceipt,
    StageWindowSummary,
    TrackSummary,
)
from genomeos.validation.reference_vcf_tokens import (  # noqa: E402
    HEADER_LIMIT_BYTES,
    RECORD_LIMIT_BYTES,
    HeaderEvidence,
    SourceRecord,
    parse_header,
    parse_record,
    site_disposition,
)
from genomeos.validation.reference_window_manifest import decode_manifest  # noqa: E402
from genomeos.validation.reference_window_types import ReferenceWindow  # noqa: E402
from scripts.reference_artifact_io import (  # noqa: E402
    artifact_path,
    artifact_root,
    read_bounded,
    read_bounded_ref,
)
from scripts.reference_io_common import fsync_artifact, write_artifact_bytes  # noqa: E402
from scripts.reference_native_stage import (  # noqa: E402
    normalize_stage_reason,
    open_native_stage,
)
from scripts.reference_preparation_outputs import (  # noqa: E402
    encoded_count_row as _encoded_count_row,
)
from scripts.reference_preparation_outputs import (  # noqa: E402
    export_stage_part as _export_stage_part,
)
from scripts.reference_preparation_outputs import (  # noqa: E402
    merge_count_parts as _merge_parts,
)
from scripts.reference_preparation_outputs import (  # noqa: E402
    merge_variant_parts as _merge_variant_parts,
)
from scripts.reference_preparation_outputs import (  # noqa: E402
    native_ledger as _native_ledger,
)
from scripts.reference_preparation_outputs import (  # noqa: E402
    preparation_files as _files,
)
from scripts.reference_preparation_outputs import (  # noqa: E402
    qc_ledger as _qc_ledger,
)
from scripts.reference_preparation_outputs import (  # noqa: E402
    window_ledger as _window_ledger,
)
from scripts.reference_runtime import (  # noqa: E402
    campaign_source_hashes,
    preparation_runtime,
    resolve_executable,
)
from scripts.reference_window_artifacts import (  # noqa: E402
    validate_acquisition,
    write_preparation_manifest,
)
from scripts.reference_window_io import (  # noqa: E402
    iter_native_tokens,
    iter_native_totals,
    native_called_totals,
    query_native_tokens,
)

STAGES = (TECHNICAL_STAGE, PAPER_STAGE)
KINDS = ("called", "quality")
COHORT_FILES = {
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
    parser.add_argument("--acquisition", required=True, type=Path)
    parser.add_argument("--metadata", required=True, type=Path)
    parser.add_argument("--outliers", required=True, type=Path)
    parser.add_argument("--cohort-exclusions", required=True, type=Path)
    parser.add_argument("--technical-samples", required=True, type=Path)
    parser.add_argument("--paper-samples", required=True, type=Path)
    parser.add_argument("--dependency-audit", required=True, type=Path)
    parser.add_argument("--bcftools", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    return parser


def _read(path: Path, limit: int = 268_435_456) -> bytes:
    if not path.is_file() or path.is_symlink():
        raise ValueError("invalid_input")
    with path.open("rb") as handle:
        raw = handle.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("limit_exceeded")
    return raw


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _write(root: Path, relative: str, raw: bytes) -> ArtifactRef:
    return write_artifact_bytes(root, relative, raw)


def _revision() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, check=False,
            capture_output=True, text=True, timeout=10,
        )
    except subprocess.SubprocessError as error:
        raise ValueError("invalid_input") from error
    value = result.stdout.strip()
    if result.returncode or len(value) != 40 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError("invalid_input")
    return value


def _record_lines(
    acquisition_root: Path,
    receipt: AcquisitionWindowReceipt,
    header: HeaderEvidence,
) -> Iterator[SourceRecord]:
    if receipt.raw is None or receipt.offsets is None:
        raise ValueError("artifact_mismatch")
    raw_path = acquisition_root / receipt.raw.path
    offsets_path = acquisition_root / receipt.offsets.path
    raw_digest = hashlib.sha256()
    offsets_digest = hashlib.sha256()
    raw_size = 0
    offsets_size = 0
    with raw_path.open("rb") as raw_input, offsets_path.open("rb") as offsets_input:
        header_line = offsets_input.readline(256)
        offsets_digest.update(header_line)
        offsets_size += len(header_line)
        if header_line != b"ordinal\tsource_virtual_offset\traw_sha256\n":
            raise ValueError("artifact_mismatch")
        ordinal = 0
        while line := raw_input.readline(RECORD_LIMIT_BYTES + 1):
            raw_digest.update(line)
            raw_size += len(line)
            if len(line) > RECORD_LIMIT_BYTES or not line.endswith(b"\n"):
                raise ValueError("record_invalid")
            offset_line = offsets_input.readline(256)
            offsets_digest.update(offset_line)
            offsets_size += len(offset_line)
            try:
                fields = offset_line[:-1].decode("ascii").split("\t")
            except UnicodeDecodeError as error:
                raise ValueError("artifact_mismatch") from error
            if (
                not offset_line.endswith(b"\n")
                or len(fields) != 3
                or fields[0] != str(ordinal)
                or _sha(line) != fields[2]
            ):
                raise ValueError("artifact_mismatch")
            yield parse_record(line, source_virtual_offset=int(fields[1]), header=header)
            ordinal += 1
        if offsets_input.read(1):
            raise ValueError("artifact_mismatch")
    if (
        (raw_size, raw_digest.hexdigest()) != (receipt.raw.size_bytes, receipt.raw.sha256)
        or (offsets_size, offsets_digest.hexdigest())
        != (receipt.offsets.size_bytes, receipt.offsets.sha256)
    ):
        raise ValueError("artifact_mismatch")


def _add_qc(
    value: VariantCounts,
    dispositions: Counter[str],
    inspections: Counter[str],
    missing: Counter[tuple[str, str]],
) -> None:
    dispositions.update(dict(value.qc.dispositions))
    inspections.update(dict(value.qc.inspection_totals))
    missing.update({(item.field, item.origin): item.count for item in value.qc.missing_origins})


def _aggregate_qc(
    dispositions: Counter[str],
    inspections: Counter[str],
    missing: Counter[tuple[str, str]],
) -> QcTally:
    return QcTally(
        tuple(sorted((key, count) for key, count in dispositions.items() if count)),
        tuple(sorted((key, count) for key, count in inspections.items() if count)),
        tuple(MissingOriginCount(field, origin, count) for (field, origin), count in sorted(missing.items())),
    )


def _scan_window(
    root: Path,
    acquisition_root: Path,
    parent_window: AcquisitionWindowReceipt,
    window: ReferenceWindow,
    header: HeaderEvidence,
    ordinal: int,
    source_uri: str,
    source_generation: str,
) -> tuple[int, int, Counter[str], Path]:
    """Classify every record once while streaming its retained assignment fragment."""
    path = root / "work" / "variant-windows" / f"{ordinal:03d}-{window.window_id}.part"
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    records = retained = 0
    dispositions: Counter[str] = Counter()
    try:
        with path.open("xb") as output:
            path.chmod(0o600)
            for record in _record_lines(acquisition_root, parent_window, header):
                records += 1
                disposition = site_disposition(record, window)
                dispositions[disposition] += 1
                if disposition != "retained":
                    continue
                retained += 1
                row = (
                    f"GRCh38:{record.chrom}:{record.pos1}:{record.ref}:{record.alt}",
                    window.window_id,
                    window.chrom,
                    str(window.start0),
                    str(window.end0),
                    source_uri,
                    source_generation,
                )
                output.write(("\t".join(row) + "\n").encode())
            fsync_artifact(output)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return records, retained, dispositions, path


def _prepare_pair(
    *,
    root: Path,
    acquisition_root: Path,
    parent_window: AcquisitionWindowReceipt,
    window: ReferenceWindow,
    header: HeaderEvidence,
    cohorts: tuple[Cohort, Cohort],
    sample_refs: dict[str, ArtifactRef],
    bcftools: Path,
) -> tuple[PreparationStageReceipt, PreparationStageReceipt]:
    """Count the nested cohorts in one pass while retaining two native controls."""
    columns = {
        stage: cohort_columns(header.samples, cohort)
        for stage, cohort in zip(STAGES, cohorts, strict=True)
    }
    plan = plan_cohort_pair(
        header.samples,
        columns[TECHNICAL_STAGE],
        columns[PAPER_STAGE],
    )
    controls: dict[str, NativeCountFiles | None] = {}
    token_controls: dict[str, NativeTokenFiles | None] = {}
    failures: dict[str, str] = {}
    for stage in STAGES:
        control, tokens, reason = open_native_stage(
            root=root,
            acquisition_root=acquisition_root,
            parent_window=parent_window,
            stage=stage,
            sample_ref=sample_refs[stage],
            bcftools=bcftools,
            count_runner=native_called_totals,
            token_runner=query_native_tokens,
        )
        controls[stage] = control
        token_controls[stage] = tokens
        if reason is not None:
            failures[stage] = reason
    if failures:
        reason = next(failures[stage] for stage in STAGES if stage in failures)
        return tuple(
            PreparationStageReceipt(
                stage, "refused", failures.get(stage, reason), None,
                controls[stage], token_controls[stage],
            )
            for stage in STAGES
        )

    native_streams = {
        stage: (
            iter_native_totals(controls[stage], artifact_root=root),
            iter_native_tokens(token_controls[stage], artifact_root=root),
        )
        for stage in STAGES
    }
    qc = {
        stage: (Counter(), Counter(), Counter())
        for stage in STAGES
    }
    stats = {stage: Counter() for stage in STAGES}
    database_path = root / "work" / f"{window.window_id}.paired.sqlite3"
    database_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path)
    database_path.chmod(0o600)
    try:
        for stage in STAGES:
            for kind in KINDS:
                connection.execute(
                    f"CREATE TABLE {stage}_{kind} "
                    "(record_id TEXT PRIMARY KEY, line BLOB NOT NULL)"
                )
        pending = {(stage, kind): [] for stage in STAGES for kind in KINDS}
        for record in _record_lines(acquisition_root, parent_window, header):
            if site_disposition(record, window) != "retained":
                continue
            native_totals = {}
            native_tokens = {}
            for stage in STAGES:
                total_iterator, token_iterator = native_streams[stage]
                native_totals[stage] = next(total_iterator, None)
                native_tokens[stage] = next(token_iterator, None)
                if native_tokens[stage] is None:
                    raise ValueError("native_mismatch")
            try:
                paired = count_cohort_pair_with_native(
                    record,
                    plan,
                    native_tokens[TECHNICAL_STAGE],
                    native_tokens[PAPER_STAGE],
                )
            except ValueError as error:
                if str(error) in {"native_encoding_refused", "native_mismatch"}:
                    raise ValueError(str(error)) from error
                raise ValueError("record_invalid") from error
            for stage, counts in zip(STAGES, paired, strict=True):
                expected_total = (
                    counts.variant_id,
                    sum(value.called_ac for value in counts.populations),
                    sum(value.called_an for value in counts.populations),
                )
                if native_totals[stage] != expected_total:
                    raise ValueError("native_mismatch")
                dispositions, inspections, missing = qc[stage]
                _add_qc(counts, dispositions, inspections, missing)
                rows_by_kind = {
                    kind: prepare_rows(window, (counts,), kind=kind)
                    for kind in KINDS
                }
                for kind, rows in rows_by_kind.items():
                    key = (stage, kind)
                    pending[key].extend(
                        (row.record_id, _encoded_count_row(row)) for row in rows
                    )
                    if len(pending[key]) >= 10_000:
                        connection.executemany(
                            f"INSERT INTO {stage}_{kind} VALUES (?, ?)", pending[key]
                        )
                        pending[key].clear()
                    stats[stage][f"{kind}_rows"] += len(rows)
                    stats[stage][f"{kind}_unavailable"] += sum(row.an == 0 for row in rows)
                    stats[stage][f"{kind}_ac"] += sum(row.ac for row in rows)
                    stats[stage][f"{kind}_an"] += sum(row.an for row in rows)
                stats[stage]["variants"] += 1
        if any(
            next(iterator, None) is not None
            for streams in native_streams.values()
            for iterator in streams
        ):
            raise ValueError("native_mismatch")
        for (stage, kind), rows in pending.items():
            if rows:
                connection.executemany(f"INSERT INTO {stage}_{kind} VALUES (?, ?)", rows)
        connection.commit()
        for stage in STAGES:
            for kind in KINDS:
                _export_stage_part(
                    connection,
                    root,
                    stage,
                    kind,
                    window.window_id,
                    table=f"{stage}_{kind}",
                )
    except ValueError as error:
        reason = normalize_stage_reason(error)
        return tuple(
            PreparationStageReceipt(
                stage, "refused", reason, None, controls[stage], token_controls[stage]
            )
            for stage in STAGES
        )
    finally:
        connection.close()
        database_path.unlink(missing_ok=True)

    return tuple(
        PreparationStageReceipt(
            stage,
            "complete",
            None,
            StageWindowSummary(
                len(columns[stage]),
                len({value.population for value in columns[stage]}),
                stats[stage]["variants"],
                stats[stage]["called_rows"],
                stats[stage]["called_unavailable"],
                stats[stage]["quality_unavailable"],
                stats[stage]["called_ac"],
                stats[stage]["called_an"],
                stats[stage]["quality_ac"],
                stats[stage]["quality_an"],
                stats[stage]["variants"],
                len(columns[stage]) * stats[stage]["variants"],
                _aggregate_qc(*qc[stage]),
            ),
            controls[stage],
            token_controls[stage],
        )
        for stage in STAGES
    )


@dataclass(frozen=True)
class PreparationCompositionInputs:
    """Validated immutable evidence consumed by preparation composition."""

    out: Path
    acquisition_root: Path
    acquisition: AcquisitionManifest
    acquisition_raw: bytes
    cohort: QualifiedCohortInputs
    bcftools: Path
    provenance: RunProvenance

    def __post_init__(self) -> None:
        cohort_hashes = CohortInputHashes(
            *(
                hashlib.sha256(getattr(self.cohort, field)).hexdigest()
                for field in CohortInputHashes.__dataclass_fields__
            )
        ) if type(self.cohort) is QualifiedCohortInputs else None
        if (
            type(self.cohort) is not QualifiedCohortInputs
            or type(self.provenance) is not RunProvenance
            or type(self.acquisition) is not AcquisitionManifest
            or not getattr(self.acquisition, "complete", False)
            or encode_acquisition(self.acquisition) != self.acquisition_raw
            or cohort_hashes != self.acquisition.inputs.cohort
            or (
                self.provenance.code_revision,
                self.provenance.imported_source_sha256,
            )
            != (
                self.acquisition.provenance.code_revision,
                self.acquisition.provenance.imported_source_sha256,
            )
            or not self.bcftools.is_file()
            or self.bcftools.is_symlink()
        ):
            raise ValueError("invalid preparation composition inputs")


def _load_real_composition(args: argparse.Namespace) -> PreparationCompositionInputs:
    if args.out.exists() or args.out.is_symlink():
        raise ValueError("invalid_input")
    acquisition_root = artifact_root(args.acquisition)
    parent = validate_acquisition(acquisition_root)
    if not parent.complete:
        raise ValueError("invalid_input")
    cohort_paths = {
        "metadata": args.metadata,
        "outliers": args.outliers,
        "exclusions": args.cohort_exclusions,
        "technical_samples": args.technical_samples,
        "paper_samples": args.paper_samples,
        "dependency_audit": args.dependency_audit,
    }
    raw = {key: _read(path) for key, path in cohort_paths.items()}
    cohort = qualify_real_cohort_inputs(*(raw[key] for key in COHORT_FILES))
    bcftools = resolve_executable(args.bcftools)
    runtime_identity = preparation_runtime(bcftools)
    versions, executable_hashes, sdk_hashes = runtime_identity
    revision = _revision()
    source_hashes = campaign_source_hashes(ROOT)
    if (
        revision != parent.provenance.code_revision
        or source_hashes != parent.provenance.imported_source_sha256
    ):
        raise ValueError("review_mismatch")
    acquisition_raw = read_bounded(
        artifact_path(acquisition_root, "acquisition.json"),
        16_777_216,
        "acquisition manifest",
    )
    if acquisition_raw != encode_acquisition(parent):
        raise ValueError("artifact_mismatch")
    provenance = RunProvenance(
        revision,
        platform.python_version(),
        source_hashes,
        *runtime_identity,
    )
    return PreparationCompositionInputs(
        args.out,
        acquisition_root,
        parent,
        acquisition_raw,
        cohort,
        bcftools,
        provenance,
    )


def compose_preparation(
    inputs: PreparationCompositionInputs,
    *,
    final_guard: Callable[[], None] | None = None,
) -> PreparationManifest:
    """Compose four count tracks from already-qualified typed evidence."""
    if type(inputs) is not PreparationCompositionInputs:
        raise ValueError("invalid_input")
    if inputs.out.exists() or inputs.out.is_symlink():
        raise ValueError("invalid_input")
    acquisition_root, parent = inputs.acquisition_root, inputs.acquisition
    raw = {key: getattr(inputs.cohort, key) for key in COHORT_FILES}
    technical, paper = inputs.cohort.technical, inputs.cohort.paper
    source_samples = inputs.cohort.source_samples
    bcftools = inputs.bcftools
    inputs.out.mkdir(mode=0o700, parents=True, exist_ok=False)
    root = inputs.out.resolve(strict=True)
    acquisition_ref = _write(root, "inputs/acquisition.json", inputs.acquisition_raw)
    cohort_refs = {
        key: _write(root, f"inputs/cohort/{COHORT_FILES[key]}", raw[key])
        for key in COHORT_FILES
    }
    hashes = CohortInputHashes(*(cohort_refs[key].sha256 for key in COHORT_FILES))
    preparation_inputs = PreparationInputs(
        acquisition_ref, hashes, cohort_refs["dependency_audit"]
    )
    _write(root, "inputs.json", encode_preparation_inputs(preparation_inputs))
    frozen = decode_manifest(
        read_bounded_ref(
            acquisition_root,
            parent.inputs.window_manifest,
            16_777_216,
            "window manifest",
        ),
        windows_bytes=read_bounded_ref(
            acquisition_root,
            parent.inputs.windows,
            16_777_216,
            "windows sidecar",
        ),
    )
    windows_by_id = {value.window_id: value for value in frozen.windows}
    sources = {value.source.chrom: value for value in parent.sources}
    cohorts = {TECHNICAL_STAGE: technical, PAPER_STAGE: paper}
    sample_refs = {
        TECHNICAL_STAGE: cohort_refs["technical_samples"],
        PAPER_STAGE: cohort_refs["paper_samples"],
    }
    dependency_refs = {}
    for stage, pairs in ((TECHNICAL_STAGE, 1_302), (PAPER_STAGE, 1_294)):
        populations = tuple(sorted({sample.population for sample in cohorts[stage].samples}))
        evidence = DependencyEvidence(
            "reference_population_dependencies_v1", stage, populations,
            DEPENDENCY_EDGES, pairs, 77, hashes.dependency_audit,
            "reported_edges_only_shared_source_dependence_remains",
        )
        dependency_refs[stage] = _write(root, f"{stage}.dependencies.json", encode_dependency(evidence))

    receipts = []
    failed = False
    for window_ordinal, parent_window in enumerate(parent.windows):
        window = windows_by_id[parent_window.window_id]
        source = sources[window.chrom]
        try:
            header = parse_header(
                read_bounded_ref(
                    acquisition_root,
                    source.header.header,
                    HEADER_LIMIT_BYTES,
                    "source header",
                ),
                expected_contigs=frozen.contig_lengths, source_chrom=window.chrom,
                expected_samples=source_samples,
            )
            record_count, retained_count, dispositions, variant_path = _scan_window(
                root,
                acquisition_root,
                parent_window,
                window,
                header,
                window_ordinal,
                source.source.vcf.uri,
                source.source.vcf.generation,
            )
        except ValueError as error:
            reason = str(error) if str(error) in REASONS else "record_invalid"
            stages = tuple(
                PreparationStageReceipt(stage, "not_attempted", reason, None, None, None)
                for stage in STAGES
            )
            receipts.append(
                PreparationWindowReceipt(
                    window.window_id, window.chrom, "refused", reason,
                    None, None, None, stages,
                )
            )
            failed = True
            continue
        if not retained_count:
            stages = tuple(
                PreparationStageReceipt(
                    stage,
                    "complete",
                    None,
                    StageWindowSummary(
                        len(cohorts[stage].samples), 80, 0, 0, 0, 0,
                        0, 0, 0, 0, 0, 0, QcTally((), (), ()),
                    ),
                    None,
                    None,
                )
                for stage in STAGES
            )
        else:
            stages = _prepare_pair(
                root=root,
                acquisition_root=acquisition_root,
                parent_window=parent_window,
                window=window,
                header=header,
                cohorts=(technical, paper),
                sample_refs=sample_refs,
                bcftools=bcftools,
            )
        if any(value.state == "refused" for value in stages):
            reason = next(value.reason for value in stages if value.state == "refused")
            failed = True
            receipts.append(
                PreparationWindowReceipt(
                    window.window_id, window.chrom, "refused", reason,
                    record_count, None, None, tuple(stages),
                )
            )
        else:
            state = (
                "counts_prepared"
                if retained_count
                else ("no_records" if not record_count else "no_pass_snps")
            )
            site_counts = tuple(sorted((key, value) for key, value in dispositions.items() if value))
            receipts.append(
                PreparationWindowReceipt(
                    window.window_id, window.chrom, state, None,
                    record_count, retained_count, site_counts, tuple(stages),
                )
            )
    receipt_tuple = tuple(receipts)
    _write(root, "windows.tsv", _window_ledger(receipt_tuple))
    _write(root, "qc-dispositions.tsv", _qc_ledger(receipt_tuple))
    _write(root, "native-controls.tsv", _native_ledger(receipt_tuple))
    _merge_variant_parts(root, admit=not failed)
    variant_count = sum(value.retained_variants or 0 for value in receipt_tuple)
    tracks = []
    if not failed:
        for stage in STAGES:
            for kind in KINDS:
                table = _merge_parts(root, stage, kind)
                summaries = tuple(
                    item.summary for window in receipts for item in window.stages if item.stage == stage
                )
                tracks.append(
                    TrackSummary(
                        stage, kind, table, dependency_refs[stage],
                        sum(value.rows for value in summaries),
                        sum(value.variants for value in summaries),
                        80 if variant_count else 0,
                        sum(getattr(value, f"{kind}_unavailable") for value in summaries),
                        sum(getattr(value, f"{kind}_ac_sum") for value in summaries),
                        sum(getattr(value, f"{kind}_an_sum") for value in summaries),
                    )
                )
    if final_guard is not None:
        final_guard()
    status = "refused" if failed else ("complete_nonempty" if variant_count else "complete_empty")
    result = PreparationManifest(
        "reference_window_counts_v1", preparation_inputs, inputs.provenance, PREPARATION_POLICY,
        receipt_tuple, tuple(tracks), _files(root), status, not failed, False, False, False,
    )
    write_preparation_manifest(
        root,
        result,
        acquisition_root=acquisition_root,
        cohort_inputs=inputs.cohort,
    )
    return result


def prepare(args: argparse.Namespace) -> PreparationManifest:
    """Apply real campaign gates, then compose the four frozen count tracks."""
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
            or preparation_runtime(inputs.bcftools) != expected_runtime
        ):
            raise ValueError("invalid_input")

    return compose_preparation(inputs, final_guard=final_guard)


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as error:
        return int(error.code)
    try:
        result = prepare(args)
    except (OSError, sqlite3.Error, ValueError):
        print("error:invalid_input", file=sys.stderr)
        return 2
    return 0 if result.complete else 1


if __name__ == "__main__":
    raise SystemExit(main())
