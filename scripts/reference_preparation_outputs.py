"""Write preparation fragments and ledgers (reference acquisition design §6.2)."""

from __future__ import annotations

import heapq
import shutil
import sqlite3
from pathlib import Path

from genomeos.validation.reference_acquisition_types import ArtifactRef
from genomeos.validation.reference_count_types import ReferenceCount
from scripts.reference_artifact_io import artifact_identity
from scripts.reference_io_common import fsync_artifact

COUNT_HEADER = "record_id\tvariant_id\tgroup_id\tregion_id\tvariant_group\tac\tan\n"


def _artifact(root: Path, relative: str) -> ArtifactRef:
    size, digest = artifact_identity(root / relative)
    return ArtifactRef(relative, size, digest)


def encoded_count_row(row: ReferenceCount) -> bytes:
    return (
        "\t".join(
            (
                row.record_id,
                row.variant_id,
                row.group_id,
                row.region_id,
                row.variant_group,
                str(row.ac),
                str(row.an),
            )
        ).encode()
        + b"\n"
    )


def export_stage_part(
    connection: sqlite3.Connection,
    root: Path,
    stage: str,
    kind: str,
    window_id: str,
    *,
    table: str,
) -> None:
    path = root / "work" / f"{stage}.{kind}" / f"{window_id}.part"
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with path.open("xb") as output:
        path.chmod(0o600)
        cursor = connection.execute(f"SELECT line FROM {table} ORDER BY record_id")
        while rows := cursor.fetchmany(10_000):
            for (line,) in rows:
                output.write(line)
        fsync_artifact(output)


def merge_count_parts(root: Path, stage: str, kind: str) -> ArtifactRef:
    relative = f"{stage}.{kind}.tsv"
    work = root / "work" / f"{stage}.{kind}"
    work.mkdir(mode=0o700, parents=True, exist_ok=True)
    paths = sorted(work.glob("*.part"))
    readers = [path.open("rb") for path in paths]
    try:
        with (root / relative).open("xb") as output:
            (root / relative).chmod(0o600)
            output.write(COUNT_HEADER.encode())
            for line in heapq.merge(*readers):
                output.write(line)
            fsync_artifact(output)
    finally:
        for reader in readers:
            reader.close()
    for path in paths:
        path.unlink()
    work.rmdir()
    return _artifact(root, relative)


def merge_variant_parts(root: Path, *, admit: bool) -> ArtifactRef:
    relative = "variant-windows.tsv"
    work = root / "work" / "variant-windows"
    work.mkdir(mode=0o700, parents=True, exist_ok=True)
    paths = sorted(work.glob("*.part"))
    with (root / relative).open("xb") as output:
        (root / relative).chmod(0o600)
        output.write(
            b"variant_id\twindow_id\tchrom\tstart0\tend0\tsource_uri\tsource_generation\n"
        )
        if admit:
            for path in paths:
                with path.open("rb") as source:
                    shutil.copyfileobj(source, output, 1_048_576)
        fsync_artifact(output)
    if admit:
        for path in paths:
            path.unlink()
        work.rmdir()
    return _artifact(root, relative)


def window_ledger(windows) -> bytes:
    rows = ["window_id\tchrom\tstate\treason\traw_records\tretained_variants\n"]
    for value in windows:
        fields = (
            value.window_id,
            value.chrom,
            value.state,
            value.reason,
            value.raw_records,
            value.retained_variants,
        )
        rows.append("\t".join("NA" if item is None else str(item) for item in fields) + "\n")
    return "".join(rows).encode()


def qc_ledger(windows) -> bytes:
    rows = ["window_id\tstage\tcategory\tkey\torigin\tcount\n"]
    for window in windows:
        for stage in window.stages:
            if stage.summary is None:
                continue
            rows.extend(
                f"{window.window_id}\t{stage.stage}\tdisposition\t{key}\tNA\t{count}\n"
                for key, count in stage.summary.qc.dispositions
            )
            rows.extend(
                f"{window.window_id}\t{stage.stage}\tinspection\t{key}\tNA\t{count}\n"
                for key, count in stage.summary.qc.inspection_totals
            )
            rows.extend(
                f"{window.window_id}\t{stage.stage}\tmissing_origin\t"
                f"{value.field}\t{value.origin}\t{value.count}\n"
                for value in stage.summary.qc.missing_origins
            )
    return "".join(rows).encode()


def native_ledger(windows) -> bytes:
    rows = [
        "window_id\tstage\tstate\tvariants\tnative_ac_an_matches\tnative_interpreted_calls\n"
    ]
    for window in windows:
        for stage in window.stages:
            summary = stage.summary
            fields = (
                window.window_id,
                stage.stage,
                stage.state,
                None if summary is None else summary.variants,
                None if summary is None else summary.native_ac_an_matches,
                None if summary is None else summary.native_interpreted_calls,
            )
            rows.append("\t".join("NA" if item is None else str(item) for item in fields) + "\n")
    return "".join(rows).encode()


def preparation_files(root: Path) -> tuple[ArtifactRef, ...]:
    return tuple(
        _artifact(root, relative)
        for relative in sorted(
            path.relative_to(root).as_posix()
            for path in root.rglob("*")
            if path.is_file() and path.name != "manifest.json"
        )
    )
