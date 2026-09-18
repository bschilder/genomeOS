"""Execute paired reference counts offline (reference acquisition design §§5–7)."""

from __future__ import annotations

import hashlib
import sqlite3
from collections import Counter
from collections.abc import Iterator
from pathlib import Path

from genomeos.validation.reference_acquisition_types import (
    AcquisitionWindowReceipt,
    ArtifactRef,
    NativeCountFiles,
    NativeTokenFiles,
)
from genomeos.validation.reference_cohorts import (
    PAPER_STAGE,
    TECHNICAL_STAGE,
    Cohort,
    cohort_columns,
)
from genomeos.validation.reference_genotypes import (
    MissingOriginCount,
    QcTally,
    VariantCounts,
    count_cohort_pair_with_native,
    plan_cohort_pair,
)
from genomeos.validation.reference_preparation import prepare_rows
from genomeos.validation.reference_preparation_types import (
    PreparationStageReceipt,
    StageWindowSummary,
)
from genomeos.validation.reference_vcf_tokens import (
    RECORD_LIMIT_BYTES,
    HeaderEvidence,
    SourceRecord,
    parse_record,
    site_disposition,
)
from genomeos.validation.reference_window_types import ReferenceWindow
from scripts.reference_io_common import fsync_artifact
from scripts.reference_native_stage import normalize_stage_reason, open_native_stage
from scripts.reference_preparation_outputs import encoded_count_row as _encoded_count_row
from scripts.reference_preparation_outputs import export_stage_part as _export_stage_part
from scripts.reference_window_io import (
    iter_native_tokens,
    iter_native_totals,
    native_called_totals,
    query_native_tokens,
)

STAGES = (TECHNICAL_STAGE, PAPER_STAGE)
KINDS = ("called", "quality")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


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


def scan_window(
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


def prepare_pair(
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
