from pathlib import Path

import pandera
import pytest

from genomeos.registry.schema import ALIASES_SCHEMA, POPULATIONS_SCHEMA
from genomeos.registry.sources import hgdp

FIXTURE = Path(__file__).parent / "fixtures" / "hgdp_populations.tsv"


def write_input(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "populations.tsv"
    path.write_text(text, encoding="utf-8")
    return path


def test_load_conforms_to_schemas():
    populations, aliases = hgdp.load(FIXTURE, registry_version="0.1.0")
    POPULATIONS_SCHEMA.validate(populations)
    ALIASES_SCHEMA.validate(aliases)


def test_load_slugs_ids_and_preserves_original_label_as_alias():
    populations, aliases = hgdp.load(FIXTURE, registry_version="0.1.0")
    assert set(populations["population_id"]) >= {"hgdp-yoruba", "hgdp-sardinian"}
    yoruba = aliases[aliases["population_id"] == "hgdp-yoruba"].iloc[0]
    assert yoruba["source"] == "hgdp"
    assert yoruba["label"] == "Yoruba"


def test_hgdp_coordinates_are_ancestral_with_a_stated_radius():
    populations, _ = hgdp.load(FIXTURE, registry_version="0.1.0")
    assert (populations["location_type"] == "ancestral").all()
    assert (populations["uncertainty_radius_km"] > 0).all()


def test_hgdp_entries_carry_a_biocultural_notice():
    populations, _ = hgdp.load(FIXTURE, registry_version="0.1.0")
    assert populations["biocultural_notice"].notna().all()


def test_explicit_support_and_literal_identity_are_preserved(tmp_path):
    path = write_input(
        tmp_path,
        "population\tlatitude\tlongitude\tuncertainty_radius_km\tprovenance\n"
        "001\t1\t2\t2.5\tsynthetic:coordinates-v1#row-1;support-v2\n"
        "NA\t3\t4\t275\t synthetic:coordinates-v3#row-2 \n",
    )

    populations, aliases = hgdp.load(path, "0.1.0")

    assert populations["uncertainty_radius_km"].tolist() == [2.5, 275.0]
    assert populations["provenance"].tolist() == [
        "synthetic:coordinates-v1#row-1;support-v2",
        " synthetic:coordinates-v3#row-2 ",
    ]
    assert populations["population_id"].tolist() == ["hgdp-001", "hgdp-na"]
    assert aliases["label"].tolist() == ["001", "NA"]


def test_population_label_whitespace_is_preserved(tmp_path):
    path = write_input(
        tmp_path,
        "population\tlatitude\tlongitude\tuncertainty_radius_km\tprovenance\n"
        " Example Population \t1\t2\t2.5\tsynthetic:row-1\n",
    )

    populations, aliases = hgdp.load(path, "0.1.0")

    assert populations["population_id"].tolist() == ["hgdp-example-population"]
    assert aliases["label"].tolist() == [" Example Population "]


@pytest.mark.parametrize("column", ["uncertainty_radius_km", "provenance"])
def test_missing_support_column_is_a_hard_error(tmp_path, column):
    row = {
        "population": "Example",
        "latitude": "1",
        "longitude": "2",
        "uncertainty_radius_km": "2.5",
        "provenance": "synthetic:row-1",
    }
    del row[column]
    path = write_input(tmp_path, "\t".join(row) + "\n" + "\t".join(row.values()) + "\n")

    with pytest.raises(ValueError, match=column):
        hgdp.load(path, "0.1.0")


@pytest.mark.parametrize("radius", ["", " ", "0", "-1", "NaN", "inf", "-inf", "1e999", "true"])
def test_invalid_radius_is_refused(tmp_path, radius):
    path = write_input(
        tmp_path,
        "population\tlatitude\tlongitude\tuncertainty_radius_km\tprovenance\n"
        f"Example\t1\t2\t{radius}\tsynthetic:row-1\n",
    )

    with pytest.raises(ValueError, match="uncertainty_radius_km"):
        hgdp.load(path, "0.1.0")


@pytest.mark.parametrize("column", ["population", "provenance"])
@pytest.mark.parametrize("value", ["", " "])
def test_blank_required_text_is_refused(tmp_path, column, value):
    row = {
        "population": "Example",
        "latitude": "1",
        "longitude": "2",
        "uncertainty_radius_km": "2.5",
        "provenance": "synthetic:row-1",
    }
    row[column] = value
    path = write_input(tmp_path, "\t".join(row) + "\n" + "\t".join(row.values()) + "\n")

    with pytest.raises(ValueError, match=column):
        hgdp.load(path, "0.1.0")


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("latitude", ""),
        ("longitude", " "),
        ("latitude", "NaN"),
        ("longitude", "inf"),
        ("latitude", "-inf"),
        ("longitude", "1e999"),
    ],
)
def test_blank_or_nonfinite_coordinate_is_refused(tmp_path, column, value):
    row = {
        "population": "Example",
        "latitude": "1",
        "longitude": "2",
        "uncertainty_radius_km": "2.5",
        "provenance": "synthetic:row-1",
    }
    row[column] = value
    path = write_input(tmp_path, "\t".join(row) + "\n" + "\t".join(row.values()) + "\n")

    with pytest.raises(ValueError, match=column):
        hgdp.load(path, "0.1.0")


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    [("90.1", "2"), ("-90.1", "2"), ("1", "180.1"), ("1", "-180.1")],
)
def test_out_of_range_coordinate_is_a_schema_error(tmp_path, latitude, longitude):
    path = write_input(
        tmp_path,
        "population\tlatitude\tlongitude\tuncertainty_radius_km\tprovenance\n"
        f"Example\t{latitude}\t{longitude}\t2.5\tsynthetic:row-1\n",
    )

    with pytest.raises(pandera.errors.SchemaError):
        hgdp.load(path, "0.1.0")


@pytest.mark.parametrize("populations", [["North A", "North-A"], ["---"]])
def test_duplicate_or_invalid_population_slug_is_a_schema_error(tmp_path, populations):
    rows = "".join(
        f"{population}\t1\t2\t2.5\tsynthetic:row-{index}\n"
        for index, population in enumerate(populations, start=1)
    )
    path = write_input(
        tmp_path,
        "population\tlatitude\tlongitude\tuncertainty_radius_km\tprovenance\n" + rows,
    )

    with pytest.raises(pandera.errors.SchemaError):
        hgdp.load(path, "0.1.0")


@pytest.mark.parametrize(
    "header",
    [
        "population\tlatitude\tlongitude\tuncertainty_radius_km\tprovenance\tprovenance",
        "population\tlatitude\tlongitude\tuncertainty_radius_km\tprovenance\t ",
    ],
)
def test_duplicate_or_blank_column_name_is_refused(tmp_path, header):
    path = write_input(tmp_path, f"{header}\nExample\t1\t2\t2.5\tsynthetic:row-1\textra\n")

    with pytest.raises(ValueError, match="duplicate or blank column names"):
        hgdp.load(path, "0.1.0")


@pytest.mark.parametrize(
    "row",
    ["Example\t1\t2\t2.5", "Example\t1\t2\t2.5\tsynthetic:row-1\textra"],
)
def test_wrong_field_count_is_refused(tmp_path, row):
    path = write_input(
        tmp_path,
        "population\tlatitude\tlongitude\tuncertainty_radius_km\tprovenance\n"
        f"{row}\n",
    )

    with pytest.raises(ValueError, match="wrong field count at line 2"):
        hgdp.load(path, "0.1.0")


def test_embedded_blank_record_is_refused(tmp_path):
    path = write_input(
        tmp_path,
        "population\tlatitude\tlongitude\tuncertainty_radius_km\tprovenance\n"
        "Example\t1\t2\t2.5\tsynthetic:row-1\n"
        "\n"
        "Second\t3\t4\t5\tsynthetic:row-2\n",
    )

    with pytest.raises(ValueError, match="wrong field count at line 3"):
        hgdp.load(path, "0.1.0")


def test_missing_header_is_refused(tmp_path):
    path = write_input(tmp_path, "")

    with pytest.raises(ValueError, match="missing TSV header"):
        hgdp.load(path, "0.1.0")


def test_malformed_tsv_is_refused(tmp_path):
    path = write_input(
        tmp_path,
        "population\tlatitude\tlongitude\tuncertainty_radius_km\tprovenance\n"
        '"Example\t1\t2\t2.5\tsynthetic:row-1\n',
    )

    with pytest.raises(ValueError, match="malformed TSV at line 2"):
        hgdp.load(path, "0.1.0")
