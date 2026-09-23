"""Replay source and native evidence into expected counts (design §6.2)."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections import Counter
from collections.abc import Iterator
from pathlib import Path

from genomeos.validation.reference_acquisition_types import (
    AcquisitionManifest,
    AcquisitionWindowReceipt,
    ArtifactRef,
)
from genomeos.validation.reference_cohorts import PAPER_STAGE, TECHNICAL_STAGE, Cohort, cohort_columns
from genomeos.validation.reference_genotypes import (
    MissingOriginCount,
    NativeVariantTokens,
    QcTally,
    SourceRecord,
    count_cohort_pair_with_native,
    plan_cohort_pair,
)
from genomeos.validation.reference_preparation_types import (
    PreparationManifest,
    PreparationStageReceipt,
)
from genomeos.validation.reference_vcf_tokens import (
    HEADER_LIMIT_BYTES,
    HeaderEvidence,
    parse_header,
    parse_record,
    site_disposition,
)
from genomeos.validation.reference_window_types import WindowManifest
from scripts.reference_artifact_io import (
    artifact_identity,
    artifact_path,
    checked_ref,
    natural,
    read_bounded_ref,
    require,
)
from scripts.reference_native_stage import normalize_stage_reason
from scripts.reference_window_io import iter_native_tokens, iter_native_totals

_COHORT_PATHS = {
    "technical_samples": "inputs/cohort/technical.samples.txt",
    "paper_samples": "inputs/cohort/paper.samples.txt",
}
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_TSV_LINE_LIMIT = 16_777_216

def _iter_parent_records(
    root: Path,
    receipt: AcquisitionWindowReceipt,
    header: HeaderEvidence,
) -> Iterator[SourceRecord]:
    raw_path = checked_ref(root, receipt.raw)
    offset_path = checked_ref(root, receipt.offsets)
    with raw_path.open("rb") as raw_input, offset_path.open("rb") as offset_input:
        require(
            offset_input.readline(256) == b"ordinal\tsource_virtual_offset\traw_sha256\n",
            "record offset columns mismatch",
        )
        ordinal = 0
        while line := raw_input.readline(_TSV_LINE_LIMIT + 1):
            require(
                len(line) <= _TSV_LINE_LIMIT and line.endswith(b"\n"),
                "original record row exceeds its bound",
            )
            offset_line = offset_input.readline(256)
            require(offset_line.endswith(b"\n"), "missing record offset row")
            try:
                fields = offset_line[:-1].decode("ascii").split("\t")
            except UnicodeDecodeError as error:
                raise ValueError("record offset row must be ASCII") from error
            require(
                len(fields) == 3
                and fields[0] == str(ordinal)
                and _DIGEST.fullmatch(fields[2]) is not None
                and hashlib.sha256(line).hexdigest() == fields[2],
                "record offset evidence differs from original row",
            )
            yield parse_record(
                line,
                source_virtual_offset=natural(fields[1], "virtual offset"),
                header=header,
            )
            ordinal += 1
        require(offset_input.read(1) == b"", "record offset evidence has extra rows")


def _native_sample_ids(root: Path, reference: ArtifactRef) -> tuple[str, ...]:
    path = checked_ref(root, reference)
    require(path.stat().st_size <= 1_048_576, "native sample artifact exceeds its bound")
    raw = path.read_bytes()
    require(bool(raw) and raw.endswith(b"\n") and b"\r" not in raw and b"\0" not in raw,
             "invalid native sample artifact")
    try:
        values = tuple(raw.decode("ascii").splitlines())
    except UnicodeDecodeError as error:
        raise ValueError("native sample artifact must be ASCII") from error
    require(len(values) == len(set(values)) and all(values), "invalid native sample IDs")
    return values


def _native_streams_and_failures(
    root: Path,
    stage_receipts: dict[str, PreparationStageReceipt],
    cohorts: dict[str, Cohort],
) -> tuple[
    dict[str, tuple[Iterator[tuple[str, int, int]], Iterator[NativeVariantTokens]]],
    tuple[str, ...],
]:
    """Validate native sample identity and expose complete streams or causal failures."""
    streams = {}
    failures = []
    for stage, receipt in stage_receipts.items():
        control = receipt.native_control
        tokens = receipt.native_tokens
        if control is None:
            continue
        cohort = cohorts[stage]
        sample_relative = _COHORT_PATHS[
            "technical_samples" if stage == TECHNICAL_STAGE else "paper_samples"
        ]
        sample_size, sample_sha = artifact_identity(artifact_path(root, sample_relative))
        require(
            control.requested_samples == ArtifactRef(sample_relative, sample_size, sample_sha),
            "native requested samples differ from the qualified cohort",
        )
        sample_failure = None
        if control.selected_samples is not None:
            try:
                selected = _native_sample_ids(root, control.selected_samples)
            except ValueError:
                sample_failure = "native_encoding_refused"
            else:
                if set(selected) != {value.sample_id for value in cohort.samples}:
                    sample_failure = "native_mismatch"
        refused_run = next((run for run in control.runs if run.state == "refused"), None)
        if control.state == "refused":
            reason = refused_run.reason if refused_run is not None else sample_failure
            require(reason == control.reason, "native count refusal is not reproduced")
            failures.append(control.reason)
            continue
        require(sample_failure is None, "complete native sample identity is invalid")
        if tokens is None:
            continue
        refused_token_run = next(
            (
                run
                for run in (tokens.sample_query, tokens.token_query)
                if run is not None and run.state == "refused"
            ),
            None,
        )
        if tokens.state == "refused":
            require(
                refused_token_run is not None and refused_token_run.reason == tokens.reason,
                "native token refusal is not reproduced",
            )
            failures.append(tokens.reason)
            continue
        streams[stage] = (
            iter_native_totals(control, artifact_root=root),
            iter_native_tokens(tokens, artifact_root=root),
        )
    return streams, tuple(failures)


def load_expected_counts(
    connection: sqlite3.Connection,
    acquisition_root: Path,
    acquisition: AcquisitionManifest,
    preparation_root: Path,
    preparation: PreparationManifest,
    frozen: WindowManifest,
    cohorts: tuple[Cohort, Cohort],
    source_samples: tuple[str, ...],
) -> tuple[dict[str, int], dict[tuple[str, str], QcTally], dict[str, tuple[tuple[str, int], ...]]]:
    connection.execute(
        """CREATE TABLE expected (
               record_id TEXT PRIMARY KEY,
               variant_id TEXT NOT NULL,
               group_id TEXT NOT NULL,
               region_id TEXT NOT NULL,
               variant_group TEXT NOT NULL,
               technical_called_ac INT NOT NULL,
               technical_called_an INT NOT NULL,
               technical_quality_ac INT NOT NULL,
               technical_quality_an INT NOT NULL,
               paper_called_ac INT NOT NULL,
               paper_called_an INT NOT NULL,
               paper_quality_ac INT NOT NULL,
               paper_quality_an INT NOT NULL,
               seen INT NOT NULL
           )"""
    )
    sources = {value.source.chrom: value for value in acquisition.sources}
    headers = {
        chrom: parse_header(
            read_bounded_ref(
                acquisition_root, source.header.header, HEADER_LIMIT_BYTES, "source header"
            ),
            expected_contigs=frozen.contig_lengths,
            source_chrom=chrom,
            expected_samples=source_samples,
        )
        for chrom, source in sources.items()
        if source.state == "ready"
    }
    cohort_by_stage = {TECHNICAL_STAGE: cohorts[0], PAPER_STAGE: cohorts[1]}
    pair_plans = {
        chrom: plan_cohort_pair(
            header.samples,
            cohort_columns(header.samples, cohorts[0]),
            cohort_columns(header.samples, cohorts[1]),
        )
        for chrom, header in headers.items()
    }
    frozen_windows = {value.window_id: value for value in frozen.windows}
    preparation_windows = {value.window_id: value for value in preparation.windows}
    retained_counts: dict[str, int] = {}
    qc_counts: dict[tuple[str, str], tuple[Counter, Counter, Counter]] = {}
    site_counts: dict[str, Counter] = {}
    batch = []
    try:
        for receipt in acquisition.windows:
            window = frozen_windows[receipt.window_id]
            header = headers[receipt.chrom]
            preparation_window = preparation_windows[receipt.window_id]
            admitted = preparation_window.state != "refused"
            stage_receipts = {
                value.stage: value
                for value in preparation_window.stages
            }
            native_streams, native_failures = _native_streams_and_failures(
                preparation_root,
                stage_receipts,
                cohort_by_stage,
            )
            replayed_failure = None
            retained = 0
            for record in _iter_parent_records(acquisition_root, receipt, header):
                disposition = site_disposition(record, window)
                site_counts.setdefault(receipt.window_id, Counter())[disposition] += 1
                if disposition != "retained":
                    continue
                retained += 1
                if native_failures or replayed_failure is not None:
                    continue
                if set(native_streams) != {TECHNICAL_STAGE, PAPER_STAGE}:
                    if admitted:
                        raise ValueError("nonempty stage lacks native controls")
                    continue
                native_totals = {}
                native_tokens = {}
                try:
                    for stage in (TECHNICAL_STAGE, PAPER_STAGE):
                        total_iterator, token_iterator = native_streams[stage]
                        native_totals[stage] = next(total_iterator, None)
                        native_tokens[stage] = next(token_iterator, None)
                        require(
                            native_tokens[stage] is not None,
                            "native tokens differ from parent variant order",
                        )
                except ValueError as error:
                    failure = normalize_stage_reason(error)
                else:
                    try:
                        technical, paper = count_cohort_pair_with_native(
                            record,
                            pair_plans[receipt.chrom],
                            native_tokens[TECHNICAL_STAGE],
                            native_tokens[PAPER_STAGE],
                        )
                    except ValueError as error:
                        failure = (
                            str(error)
                            if str(error) in {"native_encoding_refused", "native_mismatch"}
                            else "record_invalid"
                        )
                    else:
                        failure = next(
                            (
                                "native_mismatch"
                                for stage, counts in (
                                    (TECHNICAL_STAGE, technical),
                                    (PAPER_STAGE, paper),
                                )
                                if native_totals[stage]
                                != (
                                    counts.variant_id,
                                    sum(value.called_ac for value in counts.populations),
                                    sum(value.called_an for value in counts.populations),
                                )
                            ),
                            None,
                        )
                if failure is not None:
                    if admitted:
                        raise ValueError(failure)
                    replayed_failure = failure
                    require(
                        replayed_failure == preparation_window.reason
                        and all(
                            stage.reason == replayed_failure
                            for stage in preparation_window.stages
                        ),
                        "refused count failure differs from its reason",
                    )
                    continue
                if not admitted:
                    continue
                for stage, counts in ((TECHNICAL_STAGE, technical), (PAPER_STAGE, paper)):
                    dispositions, inspections, missing = qc_counts.setdefault(
                        (receipt.window_id, stage),
                        (Counter(), Counter(), Counter()),
                    )
                    dispositions.update(dict(counts.qc.dispositions))
                    inspections.update(dict(counts.qc.inspection_totals))
                    missing.update(
                        {
                            (value.field, value.origin): value.count
                            for value in counts.qc.missing_origins
                        }
                    )
                require(technical.variant_id == paper.variant_id, "stage variant identities differ")
                variant_group = f"GRCh38:{window.chrom}:{window.start0 + 1}-{window.end0}"
                require(
                    tuple((value.population, value.region) for value in technical.populations)
                    == tuple((value.population, value.region) for value in paper.populations),
                    "stage population identities differ",
                )
                for technical_population, paper_population in zip(
                    technical.populations, paper.populations, strict=True
                ):
                    record_id = json.dumps(
                        [technical_population.population, technical.variant_id],
                        separators=(",", ":"),
                    )
                    batch.append(
                        (
                            record_id,
                            technical.variant_id,
                            technical_population.population,
                            technical_population.region,
                            variant_group,
                            technical_population.called_ac,
                            technical_population.called_an,
                            technical_population.quality_ac,
                            technical_population.quality_an,
                            paper_population.called_ac,
                            paper_population.called_an,
                            paper_population.quality_ac,
                            paper_population.quality_an,
                            0,
                        )
                    )
                if len(batch) >= 10_000:
                    connection.executemany(
                        "INSERT INTO expected VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        batch,
                    )
                    batch.clear()
            retained_counts[receipt.window_id] = retained
            if admitted:
                require(
                    all(
                        next(iterator, None) is None
                        for streams in native_streams.values()
                        for iterator in streams
                    ),
                    "native controls contain extra variants",
                )
            else:
                observed_raw = sum(site_counts.get(receipt.window_id, Counter()).values())
                require(
                    preparation_window.raw_records == observed_raw and retained > 0,
                    "refused window reason is not reproduced by parent evidence",
                )
                if native_failures:
                    require(
                        preparation_window.reason in native_failures,
                        "refused native failure differs from its reason",
                    )
                else:
                    if replayed_failure is None and set(native_streams) == {
                        TECHNICAL_STAGE,
                        PAPER_STAGE,
                    }:
                        try:
                            extra = any(
                                next(iterator, None) is not None
                                for streams in native_streams.values()
                                for iterator in streams
                            )
                        except ValueError as error:
                            replayed_failure = normalize_stage_reason(error)
                        else:
                            if extra:
                                replayed_failure = "native_mismatch"
                    require(
                        replayed_failure == preparation_window.reason,
                        "refused count failure is not reproduced",
                    )
        if batch:
            connection.executemany(
                "INSERT INTO expected VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                batch,
            )
        connection.commit()
    except sqlite3.IntegrityError as error:
        raise ValueError("duplicate expected count record") from error
    qc = {
        key: QcTally(
            tuple(sorted(dispositions.items())),
            tuple(sorted(inspections.items())),
            tuple(
                MissingOriginCount(field, origin, count)
                for (field, origin), count in sorted(missing.items())
            ),
        )
        for key, (dispositions, inspections, missing) in qc_counts.items()
    }
    dispositions = {
        window_id: tuple(sorted(counts.items()))
        for window_id, counts in site_counts.items()
    }
    return retained_counts, qc, dispositions
