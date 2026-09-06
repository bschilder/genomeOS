"""Validate and persist observations as chromosome-partitioned parquet (design §6, P1).

Partitioned by `chrom` because every downstream read is either per-variant (Plan 3's API) or
per-chromosome (Plan 2's batch fits); partitioning turns both into a directory prune instead of
a scan. Validation happens on write, so an invalid frame can never reach storage (§12).
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from genomeos.observations.schema import OBSERVATIONS_SCHEMA


def _chrom(variant_id: pd.Series) -> pd.Series:
    return variant_id.str.split("-").str[0]


def write_observations(obs: pd.DataFrame, out_dir: Path) -> Path:
    validated = OBSERVATIONS_SCHEMA.validate(obs).copy()
    validated["chrom"] = _chrom(validated["variant_id"])
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    validated.to_parquet(out_dir, partition_cols=["chrom"], index=False)
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
