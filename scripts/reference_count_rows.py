"""Stream immutable count rows and partial fragments (reference acquisition design §6.2)."""

from __future__ import annotations

import heapq
import json
import re
from collections.abc import Iterator
from pathlib import Path

from genomeos.validation.reference_count_types import ReferenceCount
from genomeos.validation.reference_preparation_types import PreparationManifest
from scripts.reference_artifact_io import TSV_LINE_LIMIT, iter_tsv, natural, require

COUNT_COLUMNS = (
    "record_id", "variant_id", "group_id", "region_id", "variant_group", "ac", "an",
)
COUNT_VARIANT = re.compile(
    r"GRCh38:(chr(?:[1-9]|1[0-9]|2[0-2])):([1-9][0-9]*):[^:]+:[^:]+\Z"
)


def count_rows(path: Path) -> Iterator[ReferenceCount]:
    """Yield one strictly ordered admitted count table."""
    previous_id: str | None = None
    group_regions: dict[str, str] = {}
    for value in iter_tsv(path, COUNT_COLUMNS):
        row = ReferenceCount(*value[:5], natural(value[5], "AC"), natural(value[6], "AN"))
        expected_id = json.dumps([row.group_id, row.variant_id], separators=(",", ":"))
        require(row.record_id == expected_id, "count record_id is not canonical")
        require(COUNT_VARIANT.fullmatch(row.variant_id) is not None,
                "invalid count variant identity")
        require(previous_id is None or previous_id < row.record_id,
                "count rows must be strictly sorted")
        previous_id = row.record_id
        previous_region = group_regions.setdefault(row.group_id, row.region_id)
        require(previous_region == row.region_id, "count group has inconsistent region")
        yield row


def partial_count_rows(
    root: Path,
    manifest: PreparationManifest,
    stage: str,
    kind: str,
) -> Iterator[ReferenceCount]:
    """Merge the bounded successful-window fragments of one refused preparation."""
    directory = root / "work" / f"{stage}.{kind}"
    expected = tuple(
        directory / f"{window.window_id}.part"
        for window in manifest.windows
        if window.state != "refused" and window.retained_variants
    )
    require(all(path.is_file() and not path.is_symlink() for path in expected),
            "successful window count fragment is unavailable")
    expected_names = {path.name for path in expected}
    if directory.exists():
        require(
            directory.is_dir()
            and not directory.is_symlink()
            and all(path.is_file() for path in directory.iterdir())
            and {path.name for path in directory.iterdir()} == expected_names,
            "count fragment layout mismatch",
        )
    else:
        require(not expected, "successful window count fragment directory is unavailable")
    readers = [path.open("rb") for path in expected]
    try:
        def bounded_lines(stream) -> Iterator[bytes]:
            while raw := stream.readline(TSV_LINE_LIMIT + 1):
                yield raw

        previous_id: str | None = None
        group_regions: dict[str, str] = {}
        for raw in heapq.merge(*(bounded_lines(reader) for reader in readers)):
            require(
                len(raw) <= TSV_LINE_LIMIT
                and raw.endswith(b"\n")
                and b"\r" not in raw
                and b"\0" not in raw,
                "count fragment must use bounded LF rows",
            )
            try:
                fields = tuple(raw[:-1].decode("utf-8").split("\t"))
            except UnicodeDecodeError as error:
                raise ValueError("count fragment must be UTF-8") from error
            require(len(fields) == len(COUNT_COLUMNS), "count fragment row width mismatch")
            row = ReferenceCount(
                *fields[:5], natural(fields[5], "AC"), natural(fields[6], "AN")
            )
            expected_id = json.dumps([row.group_id, row.variant_id], separators=(",", ":"))
            require(row.record_id == expected_id, "count record_id is not canonical")
            require(COUNT_VARIANT.fullmatch(row.variant_id) is not None,
                    "invalid count variant identity")
            require(previous_id is None or previous_id < row.record_id,
                    "count rows must be strictly sorted")
            previous_id = row.record_id
            previous_region = group_regions.setdefault(row.group_id, row.region_id)
            require(previous_region == row.region_id, "count group has inconsistent region")
            yield row
    finally:
        for reader in readers:
            reader.close()
