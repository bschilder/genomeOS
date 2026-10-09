"""Validate and persist observations as chromosome-partitioned parquet (design §6, P1).

Partitioned by `chrom` because every downstream read is either per-variant (Plan 3's API) or
per-chromosome (Plan 2's batch fits); partitioning turns both into a directory prune instead of
a scan. Validation happens on write, so an invalid frame can never reach storage (§12).
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

import duckdb
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from genomeos.observations.schema import OBSERVATIONS_SCHEMA


def _chrom(variant_id: pd.Series) -> pd.Series:
    return variant_id.str.split("-").str[0]


def write_observations(obs: pd.DataFrame, out_dir: Path) -> Path:
    validated = OBSERVATIONS_SCHEMA.validate(obs)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    # One synchronous write per partition, on this thread -- not `to_parquet(partition_cols=...)`.
    # That routes through Arrow's async dataset writer, whose worker thread drops the last
    # reference to the zero-copy NumPy column buffers *after* to_parquet has returned. In a script
    # that exits right after writing, that release can land in interpreter shutdown, where
    # CPython 3.12 answers the worker's GIL request with pthread_exit; glibc unwinds it through
    # pyarrow's noexcept buffer destructor and the process aborts with "terminate called without
    # an active exception" (SIGABRT) after doing all of its work.
    # The schema is inferred once, from the whole frame, as the single table used to be: inferred
    # per partition, a column that is null throughout one chrom (an object column under pandas 2)
    # would be typed `null` in that file alone.
    schema = pa.Schema.from_pandas(validated, preserve_index=False)
    for chrom, rows in validated.groupby(_chrom(validated["variant_id"]), sort=True, dropna=False):
        # Same hive layout Arrow writes (`chrom=phenotype%3Ag6pd`); duckdb decodes it on read.
        partition = out_dir / f"chrom={quote(str(chrom), safe='')}"
        partition.mkdir(exist_ok=True)
        table = pa.Table.from_pandas(rows, schema=schema, preserve_index=False)
        pq.write_table(table, partition / "part-0.parquet")
    return out_dir


def read_observations(out_dir: Path, variant_id: str | None = None) -> pd.DataFrame:
    # Scan only the P1 hive partitions. Audit ledgers intentionally live beside them at the
    # store root and have a different schema; a recursive glob would conflate evidence with
    # observations, violating design §4 before validation even has a chance to run.
    glob = str(Path(out_dir) / "chrom=*" / "*.parquet")
    sql = f"SELECT * EXCLUDE (chrom) FROM read_parquet('{glob}', hive_partitioning = true)"
    if variant_id is None:
        return duckdb.sql(sql).df()
    # Prune the partition as well as filter, so a per-variant read never scans other chroms.
    sql += " WHERE chrom = ? AND variant_id = ?"
    return duckdb.execute(sql, [variant_id.split("-")[0], variant_id]).df()
