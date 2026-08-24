from pathlib import Path

import pandas as pd
import pandera.errors
import pytest

from genomeos.observations.ingest import read_observations, write_observations
from genomeos.observations.sources import map_surveys

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def obs() -> pd.DataFrame:
    observations, _report = map_surveys.load(FIXTURES / "map_hbs_surveys.csv", "0.1.0")
    return observations


def test_write_partitions_by_chromosome(tmp_path, obs):
    out = write_observations(obs, tmp_path)
    assert (out / "chrom=chr11").is_dir()


def test_round_trip_preserves_row_count_and_counts(tmp_path, obs):
    write_observations(obs, tmp_path)
    back = read_observations(tmp_path)
    assert len(back) == len(obs)
    assert back["ac"].sum() == obs["ac"].sum()


def test_read_can_filter_to_one_variant(tmp_path, obs):
    write_observations(obs, tmp_path)
    back = read_observations(tmp_path, variant_id=map_surveys.HBS_VARIANT_ID)
    assert len(back) == len(obs)
    assert read_observations(tmp_path, variant_id="chr1-1-A-T").empty


def test_write_rejects_a_frame_that_violates_the_schema(tmp_path, obs):
    broken = obs.copy()
    broken.loc[0, "sampling_design"] = "unknown"
    with pytest.raises(pandera.errors.SchemaError):
        write_observations(broken, tmp_path)
