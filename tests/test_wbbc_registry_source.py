"""WBBC regional geography contract (Atlas design §§4, 6, 7.1; issue #325)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from genomeos.registry.sources import wbbc

FIXTURES = Path(__file__).parent / "fixtures"
ROOT = Path(__file__).parents[1]


def test_loads_the_four_reviewed_regions_with_province_covering_radii():
    populations, aliases = wbbc.load(FIXTURES / "wbbc_regions.tsv", "0.1.0")

    assert populations["population_id"].tolist() == [
        "wbbc-north",
        "wbbc-central",
        "wbbc-south",
        "wbbc-lingnan",
    ]
    assert populations["location_type"].eq("inferred").all()
    assert populations["uncertainty_radius_km"].tolist() == [2025.0, 350.0, 1300.0, 650.0]
    assert aliases.to_dict("records") == [
        {"population_id": "wbbc-north", "source": "wbbc", "label": "North"},
        {"population_id": "wbbc-central", "source": "wbbc", "label": "Central"},
        {"population_id": "wbbc-south", "source": "wbbc", "label": "South"},
        {"population_id": "wbbc-lingnan", "source": "wbbc", "label": "Lingnan"},
    ]


def test_reviewed_fixture_matches_the_regenerable_public_artifact():
    assert (FIXTURES / "wbbc_regions.tsv").read_bytes() == (
        ROOT / "docs" / "research" / "wbbc-regions-2026-09-17.tsv"
    ).read_bytes()


@pytest.mark.parametrize(
    ("column", "replacement", "message"),
    [
        ("member_divisions", "Anhui|Jiangsu|Shanghai", "member divisions"),
        ("uncertainty_radius_km", "1", "reviewed geography"),
    ],
)
def test_refuses_geography_that_differs_from_the_reviewed_contract(
    tmp_path: Path, column: str, replacement: str, message: str
):
    frame = pd.read_csv(FIXTURES / "wbbc_regions.tsv", sep="\t", dtype=str)
    frame.loc[frame["region"] == "Central", column] = replacement
    path = tmp_path / "regions.tsv"
    frame.to_csv(path, sep="\t", index=False)

    with pytest.raises(ValueError, match=message):
        wbbc.load(path, "0.1.0")


def test_refuses_a_missing_or_unknown_source_region(tmp_path: Path):
    frame = pd.read_csv(FIXTURES / "wbbc_regions.tsv", sep="\t", dtype=str)
    frame.loc[frame["region"] == "North", "region"] = "Northern China"
    path = tmp_path / "regions.tsv"
    frame.to_csv(path, sep="\t", index=False)

    with pytest.raises(ValueError, match="exactly.*Central.*Lingnan.*North.*South"):
        wbbc.load(path, "0.1.0")
