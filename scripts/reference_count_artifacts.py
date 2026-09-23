"""Recompute and validate reference count artifacts (reference acquisition design §6.2)."""

from __future__ import annotations

import hashlib
import re
import sqlite3
import tempfile
from collections.abc import Iterator
from itertools import zip_longest
from pathlib import Path

from genomeos.validation.reference_acquisition_types import (
    AcquisitionManifest,
)
from genomeos.validation.reference_cohorts import (
    PAPER_STAGE,
    TECHNICAL_STAGE,
    Cohort,
)
from genomeos.validation.reference_genotypes import QcTally
from genomeos.validation.reference_preparation_codec import decode_dependency
from genomeos.validation.reference_preparation_types import PreparationManifest
from genomeos.validation.reference_window_types import WindowManifest
from scripts.reference_artifact_io import (
    artifact_path as _path,
)
from scripts.reference_artifact_io import (
    checked_ref as _check_ref,
)
from scripts.reference_artifact_io import (
    iter_tsv as _iter_tsv,
)
from scripts.reference_artifact_io import (
    natural as _natural,
)
from scripts.reference_artifact_io import (
    nullable as _nullable,
)
from scripts.reference_artifact_io import (
    read_bounded_ref as _bounded_ref,
)
from scripts.reference_artifact_io import (
    require as _require,
)
from scripts.reference_count_replay import load_expected_counts
from scripts.reference_count_rows import (
    count_rows as _count_rows,
)
from scripts.reference_count_rows import (
    partial_count_rows as _partial_count_rows,
)

_VARIANT_WINDOW_COLUMNS = (
    "variant_id", "window_id", "chrom", "start0", "end0", "source_uri", "source_generation",
)
_COUNT_VARIANT = re.compile(
    r"GRCh38:(chr(?:[1-9]|1[0-9]|2[0-2])):([1-9][0-9]*):[^:]+:[^:]+\Z"
)
_TSV_LINE_LIMIT = 16_777_216
_DEPENDENCY_LIMIT = 16_777_216



def expected_qc_rows(manifest: PreparationManifest) -> tuple[tuple[str, ...], ...]:
    rows = []
    for window in manifest.windows:
        for stage in window.stages:
            if stage.summary is None:
                continue
            rows.extend(
                (window.window_id, stage.stage, "disposition", key, "NA", str(count))
                for key, count in stage.summary.qc.dispositions
            )
            rows.extend(
                (window.window_id, stage.stage, "inspection", key, "NA", str(count))
                for key, count in stage.summary.qc.inspection_totals
            )
            rows.extend(
                (window.window_id, stage.stage, "missing_origin", value.field, value.origin, str(value.count))
                for value in stage.summary.qc.missing_origins
            )
    return tuple(rows)


def expected_native_rows(manifest: PreparationManifest) -> tuple[tuple[str, ...], ...]:
    rows = []
    for window in manifest.windows:
        for stage in window.stages:
            summary = stage.summary
            rows.append(
                (
                    window.window_id,
                    stage.stage,
                    stage.state,
                    _nullable(None if summary is None else summary.variants),
                    _nullable(None if summary is None else summary.native_ac_an_matches),
                    _nullable(None if summary is None else summary.native_interpreted_calls),
                )
            )
    return tuple(rows)


def _variant_window(
    variant_id: str,
    frozen_by_chrom: dict[str, tuple[object, ...]],
) -> object:
    match = _COUNT_VARIANT.fullmatch(variant_id)
    _require(match is not None, "invalid count variant identity")
    chrom, pos1 = match.group(1), int(match.group(2))
    matches = tuple(
        window
        for window in frozen_by_chrom.get(chrom, ())
        if window.start0 < pos1 <= window.end0
    )
    _require(len(matches) == 1, "variant does not identify exactly one frozen window")
    return matches[0]


def _load_variant_windows(
    root: Path,
    connection: sqlite3.Connection,
    frozen_by_id: dict[str, object],
    sources: dict[str, object],
    manifest: PreparationManifest,
) -> dict[str, int]:
    connection.execute(
        "CREATE TABLE assignments "
        "(variant_id TEXT PRIMARY KEY, window_id TEXT NOT NULL, seen INT NOT NULL, admitted INT NOT NULL)"
    )
    counts: dict[str, int] = {}
    preparation_by_id = {value.window_id: value for value in manifest.windows}
    batch = []
    try:
        if manifest.complete:
            rows = _iter_tsv(_path(root, "variant-windows.tsv"), _VARIANT_WINDOW_COLUMNS)
        else:
            directory = root / "work" / "variant-windows"
            expected = tuple(
                directory / f"{index:03d}-{window.window_id}.part"
                for index, window in enumerate(manifest.windows)
                if window.raw_records is not None
            )
            _require(all(path.is_file() and not path.is_symlink() for path in expected),
                     "successful window assignment fragment is unavailable")
            expected_names = {path.name for path in expected}
            _require(
                directory.is_dir()
                and not directory.is_symlink()
                and all(path.is_file() for path in directory.iterdir())
                and {path.name for path in directory.iterdir()} == expected_names,
                "assignment fragment layout mismatch",
            )

            def partial_rows() -> Iterator[tuple[str, ...]]:
                for path in expected:
                    with path.open("rb") as stream:
                        while raw := stream.readline(_TSV_LINE_LIMIT + 1):
                            _require(
                                len(raw) <= _TSV_LINE_LIMIT
                                and raw.endswith(b"\n")
                                and b"\r" not in raw
                                and b"\0" not in raw,
                                "assignment fragment must use bounded LF rows",
                            )
                            try:
                                row = tuple(raw[:-1].decode("utf-8").split("\t"))
                            except UnicodeDecodeError as error:
                                raise ValueError("assignment fragment must be UTF-8") from error
                            _require(len(row) == len(_VARIANT_WINDOW_COLUMNS),
                                     "assignment fragment row width mismatch")
                            yield row

            rows = partial_rows()
        for value in rows:
            variant_id, window_id, chrom, start0, end0, uri, generation = value
            start, end = _natural(start0, "window start0"), _natural(end0, "window end0")
            window = frozen_by_id.get(window_id)
            source = sources.get(chrom)
            match = _COUNT_VARIANT.fullmatch(variant_id)
            _require(
                window is not None
                and source is not None
                and (chrom, start, end) == (window.chrom, window.start0, window.end0)
                and (uri, generation) == (source.vcf.uri, source.vcf.generation)
                and match is not None
                and match.group(1) == chrom
                and start < int(match.group(2)) <= end,
                "variant-window assignment differs from frozen acquisition",
            )
            counts[window_id] = counts.get(window_id, 0) + 1
            preparation_window = preparation_by_id[window_id]
            batch.append(
                (variant_id, window_id, 0, int(preparation_window.state != "refused"))
            )
            if len(batch) == 10_000:
                connection.executemany("INSERT INTO assignments VALUES (?, ?, ?, ?)", batch)
                batch.clear()
        if batch:
            connection.executemany("INSERT INTO assignments VALUES (?, ?, ?, ?)", batch)
        connection.commit()
    except sqlite3.IntegrityError as error:
        raise ValueError("duplicate variant-window assignment") from error
    return counts




def _validate_count_tables(
    root: Path,
    manifest: PreparationManifest,
    acquisition_root: Path,
    acquisition: AcquisitionManifest,
    frozen: WindowManifest,
    cohorts: tuple[Cohort, Cohort],
    source_samples: tuple[str, ...],
) -> None:
    cohort_populations = {
        stage: tuple(sorted({sample.population for sample in cohort.samples}))
        for stage, cohort in zip(
            (TECHNICAL_STAGE, PAPER_STAGE), cohorts, strict=True
        )
    }
    frozen_windows = {value.window_id: value for value in frozen.windows}
    sources = {value.source.chrom: value.source for value in acquisition.sources}
    frozen_by_chrom: dict[str, tuple[object, ...]] = {}
    for window in frozen_windows.values():
        frozen_by_chrom.setdefault(window.chrom, ())
        frozen_by_chrom[window.chrom] = (*frozen_by_chrom[window.chrom], window)

    with tempfile.TemporaryDirectory(prefix="genomeos-count-validation-") as directory:
        connection = sqlite3.connect(Path(directory) / "assignments.sqlite3")
        try:
            assigned_counts = _load_variant_windows(
                root, connection, frozen_windows, sources, manifest
            )
            _require(
                all(
                    assigned_counts.get(window.window_id, 0) == window.retained_variants
                    for window in manifest.windows
                    if window.state != "refused"
                ),
                "variant-window counts differ from preparation ledger",
            )
            expected_counts, expected_qc, expected_dispositions = load_expected_counts(
                connection,
                acquisition_root,
                acquisition,
                root,
                manifest,
                frozen,
                cohorts,
                source_samples,
            )
            _require(
                all(
                    expected_counts.get(window.window_id, 0) == window.retained_variants
                    for window in manifest.windows
                    if window.state != "refused"
                ),
                "retained count rows differ from parent evidence",
            )
            _require(
                all(
                    assigned_counts.get(window.window_id, 0)
                    == expected_counts.get(window.window_id, 0)
                    for window in manifest.windows
                    if window.raw_records is not None
                ),
                "variant-window fragments differ from parent evidence",
            )
            _require(
                all(
                    window.site_dispositions
                    == expected_dispositions.get(window.window_id, ())
                    for window in manifest.windows
                    if window.state != "refused"
                ),
                "site dispositions differ from parent genotype evidence",
            )

            track_axes = tuple(
                (stage, kind)
                for stage in (TECHNICAL_STAGE, PAPER_STAGE)
                for kind in ("called", "quality")
            )
            if manifest.complete:
                iterators = tuple(
                    _count_rows(_check_ref(root, track.table)) for track in manifest.tracks
                )
            else:
                iterators = tuple(
                    _partial_count_rows(root, manifest, stage, kind)
                    for stage, kind in track_axes
                )
            sentinel = object()
            groups: set[str] = set()
            group_regions: dict[str, str] = {}
            current_group: str | None = None
            group_digest = hashlib.sha256()
            group_variants = 0
            baseline_digest: str | None = None
            baseline_variants = 0
            totals = [[0, 0, 0] for _ in track_axes]
            window_totals: dict[tuple[str, str, str], list[int]] = {}
            seen_batch: list[tuple[str]] = []

            def finish_group() -> None:
                nonlocal baseline_digest, baseline_variants
                if current_group is None:
                    return
                digest = group_digest.hexdigest()
                if baseline_digest is None:
                    baseline_digest, baseline_variants = digest, group_variants
                else:
                    _require(
                        (digest, group_variants) == (baseline_digest, baseline_variants),
                        "population variant sets differ",
                    )

            def mark_seen() -> None:
                if seen_batch:
                    connection.executemany(
                        "UPDATE assignments SET seen = 1 WHERE variant_id = ?",
                        seen_batch,
                    )
                    seen_batch.clear()

            for values in zip_longest(*iterators, fillvalue=sentinel):
                _require(all(value is not sentinel for value in values), "four track keys differ")
                rows = tuple(values)
                first = rows[0]
                _require(
                    all(
                        (
                            row.record_id,
                            row.variant_id,
                            row.group_id,
                            row.region_id,
                            row.variant_group,
                        )
                        == (
                            first.record_id,
                            first.variant_id,
                            first.group_id,
                            first.region_id,
                            first.variant_group,
                        )
                        for row in rows[1:]
                    ),
                    "four track keys differ",
                )
                expected = connection.execute(
                    """SELECT variant_id, group_id, region_id, variant_group,
                              technical_called_ac, technical_called_an,
                              technical_quality_ac, technical_quality_an,
                              paper_called_ac, paper_called_an,
                              paper_quality_ac, paper_quality_an, seen
                       FROM expected WHERE record_id = ?""",
                    (first.record_id,),
                ).fetchone()
                actual = (
                    first.variant_id,
                    first.group_id,
                    first.region_id,
                    first.variant_group,
                    rows[0].ac,
                    rows[0].an,
                    rows[1].ac,
                    rows[1].an,
                    rows[2].ac,
                    rows[2].an,
                    rows[3].ac,
                    rows[3].an,
                    0,
                )
                _require(expected == actual, "count row differs from parent genotype evidence")
                connection.execute(
                    "UPDATE expected SET seen = 1 WHERE record_id = ?",
                    (first.record_id,),
                )
                if first.group_id != current_group:
                    finish_group()
                    current_group = first.group_id
                    groups.add(first.group_id)
                    group_digest = hashlib.sha256()
                    group_variants = 0
                encoded_variant = first.variant_id.encode()
                group_digest.update(len(encoded_variant).to_bytes(8, "big"))
                group_digest.update(encoded_variant)
                group_variants += 1
                previous_region = group_regions.setdefault(first.group_id, first.region_id)
                _require(previous_region == first.region_id, "population region differs across rows")

                frozen_window = _variant_window(first.variant_id, frozen_by_chrom)
                _require(
                    first.variant_group
                    == f"GRCh38:{frozen_window.chrom}:{frozen_window.start0 + 1}-{frozen_window.end0}",
                    "variant group differs from frozen window",
                )
                if baseline_digest is None:
                    assignment = connection.execute(
                        "SELECT window_id, admitted FROM assignments WHERE variant_id = ?",
                        (first.variant_id,),
                    ).fetchone()
                    _require(
                        assignment == (frozen_window.window_id, 1),
                        "count variant lacks its exact sidecar assignment",
                    )
                    seen_batch.append((first.variant_id,))
                    if len(seen_batch) == 10_000:
                        mark_seen()

                for index, ((stage, kind), row) in enumerate(
                    zip(track_axes, rows, strict=True)
                ):
                    totals[index][0] += row.an == 0
                    totals[index][1] += row.ac
                    totals[index][2] += row.an
                    key = (stage, kind, frozen_window.window_id)
                    values_for_window = window_totals.setdefault(key, [0, 0, 0, 0])
                    values_for_window[0] += 1
                    values_for_window[1] += row.an == 0
                    values_for_window[2] += row.ac
                    values_for_window[3] += row.an
            finish_group()
            mark_seen()
            connection.commit()
            _require(
                connection.execute(
                    "SELECT COUNT(*) FROM assignments WHERE admitted = 1 AND seen = 0"
                ).fetchone()[0]
                == 0,
                "variant-window key mismatch",
            )
            _require(
                connection.execute("SELECT COUNT(*) FROM expected WHERE seen = 0").fetchone()[0] == 0,
                "count table omits parent genotype evidence",
            )

            for window in manifest.windows:
                if window.state == "refused":
                    continue
                for stage in window.stages:
                    summary = stage.summary
                    _require(summary is not None, "complete stage lacks a summary")
                    _require(
                        summary.qc
                        == expected_qc.get((window.window_id, stage.stage), QcTally((), (), ())),
                        "QC summary differs from parent genotype evidence",
                    )
                    for kind in ("called", "quality"):
                        actual = window_totals.get((stage.stage, kind, window.window_id), [0, 0, 0, 0])
                        _require(
                            tuple(actual)
                            == (
                                summary.rows,
                                getattr(summary, f"{kind}_unavailable"),
                                getattr(summary, f"{kind}_ac_sum"),
                                getattr(summary, f"{kind}_an_sum"),
                            ),
                            "count rows differ from stage-window summary",
                        )

            for index, track in enumerate(manifest.tracks):
                unavailable, ac_sum, an_sum = totals[index]
                rows = baseline_variants * len(groups)
                _require(
                    (
                        track.rows,
                        track.variants,
                        track.represented_groups,
                        track.unavailable_rows,
                        track.ac_sum,
                        track.an_sum,
                    )
                    == (rows, baseline_variants, len(groups), unavailable, ac_sum, an_sum),
                    "track summary mismatch",
                )
                dependency = decode_dependency(
                    _bounded_ref(root, track.dependencies, _DEPENDENCY_LIMIT, "dependency sidecar")
                )
                _require(
                    dependency.stage == track.stage
                    and dependency.populations == cohort_populations[track.stage]
                    and dependency.audit_sha256 == manifest.inputs.dependency_audit.sha256,
                    "dependency identity differs from qualified cohort inputs",
                )
                if manifest.status == "complete_nonempty":
                    _require(set(cohort_populations[track.stage]) == groups,
                             "dependency populations differ from count track")
            if not manifest.complete:
                files = {value.path: value for value in manifest.files}
                for stage in (TECHNICAL_STAGE, PAPER_STAGE):
                    path = f"{stage}.dependencies.json"
                    _require(path in files, "refused preparation lacks dependency evidence")
                    dependency = decode_dependency(
                        _bounded_ref(
                            root, files[path], _DEPENDENCY_LIMIT, "dependency sidecar"
                        )
                    )
                    _require(
                        dependency.stage == stage
                        and dependency.populations == cohort_populations[stage]
                        and dependency.audit_sha256
                        == manifest.inputs.dependency_audit.sha256,
                        "dependency identity differs from qualified cohort inputs",
                    )
                    if baseline_variants:
                        _require(set(cohort_populations[stage]) == groups,
                                 "dependency populations differ from count fragments")
        finally:
            connection.close()


def validate_count_tables(
    root: Path,
    manifest: PreparationManifest,
    acquisition_root: Path,
    acquisition: AcquisitionManifest,
    frozen: WindowManifest,
    cohorts: tuple[Cohort, Cohort],
    source_samples: tuple[str, ...],
) -> None:
    """Validate count evidence while hiding the bounded disk index implementation."""
    try:
        _validate_count_tables(
            root,
            manifest,
            acquisition_root,
            acquisition,
            frozen,
            cohorts,
            source_samples,
        )
    except sqlite3.Error as error:
        raise ValueError("count validation storage failure") from error
