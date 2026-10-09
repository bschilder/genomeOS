from pathlib import Path

import pandas as pd
import pandera.errors
import pyarrow.parquet as pq
import pytest

from genomeos.observations.ingest import read_observations, write_observations
from genomeos.observations.sources import map_surveys

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def obs() -> pd.DataFrame:
    observations, _report = map_surveys.load(
        FIXTURES / "map_hbs_curated_synthetic.csv", "0.1.0"
    )
    return observations


def test_write_partitions_by_chromosome(tmp_path, obs):
    out = write_observations(obs, tmp_path)
    assert (out / "chrom=chr11").is_dir()


def test_round_trip_preserves_row_count_and_counts(tmp_path, obs):
    write_observations(obs, tmp_path)
    back = read_observations(tmp_path)
    assert len(back) == len(obs)
    assert back["ac"].sum() == obs["ac"].sum()
    before = obs.set_index("source_record_id")
    after = back.set_index("source_record_id")
    assert after.loc["map-surveys:9001", "radius_km"] == 73.25
    assert after.loc["map-surveys:9001", "cohort_id"] == before.loc[
        "map-surveys:9001", "cohort_id"
    ]


def test_read_can_filter_to_one_variant(tmp_path, obs):
    write_observations(obs, tmp_path)
    back = read_observations(tmp_path, variant_id=map_surveys.HBS_VARIANT_ID)
    assert len(back) == len(obs)
    assert read_observations(tmp_path, variant_id="chr1-1-A-T").empty


def test_read_ignores_non_observation_parquet_at_store_root(tmp_path, obs):
    """Evidence ledgers beside chrom partitions must never enter the P1 scan."""
    write_observations(obs, tmp_path)
    pd.DataFrame({"source_record_id": ["evidence:1"], "citation": ["example"]}).to_parquet(
        tmp_path / "literature_evidence.parquet", index=False
    )
    assert len(read_observations(tmp_path)) == len(obs)


def test_write_rejects_a_frame_that_violates_the_schema(tmp_path, obs):
    broken = obs.copy()
    broken.loc[0, "sampling_design"] = "unknown"
    with pytest.raises(pandera.errors.SchemaError):
        write_observations(broken, tmp_path)


def test_write_never_hands_column_buffers_to_arrows_async_dataset_writer(tmp_path, obs, monkeypatch):
    """`to_parquet(partition_cols=...)` goes through `pyarrow.dataset.write_dataset`, whose worker
    thread releases the NumPy-backed buffers after the call returns. When that release lands in
    interpreter shutdown, the process aborts with SIGABRT after finishing its work (#413's CI run)."""
    import pyarrow.dataset

    def refuse(*_args, **_kwargs):
        raise AssertionError("write_observations must write each partition synchronously")

    monkeypatch.setattr(pyarrow.dataset, "write_dataset", refuse)
    write_observations(obs, tmp_path)
    assert len(read_observations(tmp_path)) == len(obs)


def test_a_namespaced_id_gets_an_encoded_partition_with_the_store_schema(tmp_path, obs):
    """Partitions are written one at a time, but keep Arrow's hive encoding and one schema.

    `phenotype:` ids land in `chrom=phenotype%3A...`, which DuckDB decodes for the pruned read, and
    a column null throughout one partition (no rsid for a phenotype) keeps the store's type there.
    """
    mixed = obs.copy()
    mixed.loc[0, "variant_id"] = "phenotype:sickle-cell-trait"
    mixed.loc[0, "rsid"] = None
    write_observations(mixed, tmp_path)

    files = sorted(tmp_path.glob("chrom=*/*.parquet"))
    assert [f.parent.name for f in files] == ["chrom=chr11", "chrom=phenotype%3Asickle"]
    schemas = [pq.read_schema(f).remove_metadata() for f in files]
    assert schemas[1].equals(schemas[0])
    assert len(read_observations(tmp_path, variant_id="phenotype:sickle-cell-trait")) == 1
    assert len(read_observations(tmp_path)) == len(obs)
