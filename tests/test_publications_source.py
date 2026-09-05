"""Publication-to-P1 promotion tests (literature design §§4, 5.4, 8)."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from genomeos.observations.evidence import make_source_record_id
from genomeos.observations.schema import OBSERVATIONS_SCHEMA
from genomeos.observations.sources import publications

FIXTURES = Path(__file__).parent / "fixtures" / "literature"
PROMOTABLE = FIXTURES / "promotable"
PENDING = FIXTURES / "non_promotable"


def _registry() -> tuple[pd.DataFrame, pd.DataFrame]:
    populations = pd.read_csv(PROMOTABLE / "populations.tsv", sep="\t")
    aliases = pd.read_csv(PROMOTABLE / "aliases.tsv", sep="\t")
    return populations, aliases


def _load(directory: Path = PROMOTABLE):
    populations, aliases = _registry()
    return publications.load(
        directory / "evidence.tsv",
        directory / "field_evidence.tsv",
        populations,
        aliases,
        "observations@2026-09-05.1",
    )


def _read(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, sep="\t", keep_default_na=False).replace("", pd.NA)


def _write_tables(tmp_path: Path, evidence: pd.DataFrame, fields: pd.DataFrame) -> tuple[Path, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    evidence_path = tmp_path / "evidence.tsv"
    fields_path = tmp_path / "field_evidence.tsv"
    evidence = evidence.copy()
    evidence["disease_ascertainment_excluded"] = evidence[
        "disease_ascertainment_excluded"
    ].map({True: "true", False: "false", "true": "true", "false": "false"})
    evidence.to_csv(evidence_path, sep="\t", index=False, na_rep="")
    fields.to_csv(fields_path, sep="\t", index=False, na_rep="")
    return evidence_path, fields_path


def test_promotable_record_produces_one_schema_valid_p1_observation():
    """Catches a reviewed exact record being dropped or evidence columns leaking into P1."""
    observations, retained, report = _load()
    OBSERVATIONS_SCHEMA.validate(observations)
    assert len(observations) == len(retained) == report.retained == 1
    assert report.refusals == {}
    row = observations.iloc[0]
    assert row["source_record_id"] == retained.iloc[0]["source_record_id"]
    assert (row["ac"], row["an"]) == (17, 58)
    assert row["source"] == "literature:lct-rs4988235"


def test_geography_is_copied_exactly_from_the_resolved_p0_row():
    """Catches invented country centroids or a default uncertainty radius in the adapter."""
    observations, _, _ = _load()
    populations, _ = _registry()
    expected = populations.set_index("population_id").loc["literature-sami"]
    row = observations.iloc[0]
    assert row["population_id"] == "literature-sami"
    assert row["lat"] == expected["lat"]
    assert row["lon"] == expected["lon"]
    assert row["radius_km"] == expected["uncertainty_radius_km"]


def test_pending_record_is_retained_as_evidence_but_not_promoted():
    """Catches a staging row becoming P1 merely because it contains a plausible frequency."""
    observations, retained, report = _load(PENDING)
    assert observations.empty
    assert retained.empty
    assert report.total == 1
    assert report.refusals == {"required_field_unresolved": 1}


@pytest.mark.parametrize(
    ("updates", "reason"),
    [
        ({"ac_upper": 18}, "count_not_exact"),
        ({"count_basis": "frequency_reconstructed"}, "count_not_exact"),
        ({"verification_status": "pending"}, "source_not_verified"),
        ({"normalization_status": "ambiguous"}, "variant_ambiguous"),
    ],
)
def test_scientific_refusals_are_reported_not_silently_dropped(tmp_path, updates, reason):
    """Catches promotion selecting an interval, reconstructed count, or caller status."""
    evidence = _read(PROMOTABLE / "evidence.tsv")
    fields = _read(PROMOTABLE / "field_evidence.tsv")
    for column, value in updates.items():
        evidence.loc[0, column] = value
        if column in set(fields["field_name"]):
            fields.loc[fields["field_name"] == column, "raw_value"] = str(value).lower()
    if "verification_status" in updates:
        evidence.loc[0, ["verified_by", "verified_at", "verification_reference"]] = pd.NA
    if "normalization_status" in updates:
        fields.loc[fields["field_name"] == "variant_id", [
            "evidence_status", "raw_value", "notes",
        ]] = ["ambiguous", "GRCh37 or GRCh38", "The printed build is ambiguous."]
        evidence.loc[0, "variant_id"] = pd.NA
        evidence.loc[0, "verification_status"] = "pending"
        evidence.loc[0, ["verified_by", "verified_at", "verification_reference"]] = pd.NA
    paths = _write_tables(tmp_path, evidence, fields)
    populations, aliases = _registry()
    observations, _, report = publications.load(
        *paths, populations, aliases, "observations@2026-09-05.1"
    )
    assert observations.empty
    assert report.refusals == {reason: 1}


def test_explicit_reuse_restriction_refuses_promotion(tmp_path):
    """Catches the permissive missing-licence policy overriding explicit source terms."""
    evidence = _read(PROMOTABLE / "evidence.tsv")
    fields = _read(PROMOTABLE / "field_evidence.tsv")
    reuse = {
        "checks": [
            {
                "checked_at": "2026-09-04",
                "finding": "restricted",
                "restriction": "non-commercial reuse only",
                "source_id": "pmid:29063188",
                "terms_url": "https://example.org/terms",
            }
        ]
    }
    evidence.loc[0, "reuse_status"] = "restricted"
    evidence.loc[0, "reuse_evidence"] = json.dumps(
        reuse, sort_keys=True, separators=(",", ":")
    )
    paths = _write_tables(tmp_path, evidence, fields)
    populations, aliases = _registry()
    observations, _, report = publications.load(
        *paths, populations, aliases, "observations@2026-09-05.1"
    )
    assert observations.empty
    assert report.refusals == {"reuse_restricted": 1}


def test_unmapped_ordinary_population_is_a_hard_error():
    """Catches fuzzy matching or country fallback when the exact P0 alias is absent."""
    populations, aliases = _registry()
    with pytest.raises(publications.UnmappedPopulationError, match="Sami"):
        publications.load(
            PROMOTABLE / "evidence.tsv",
            PROMOTABLE / "field_evidence.tsv",
            populations,
            aliases.iloc[0:0],
            "observations@2026-09-05.1",
        )


def test_duplicate_cohort_measurement_is_a_hard_error(tmp_path):
    """Catches duplicate publication rows receiving twice the statistical weight."""
    evidence = _read(PROMOTABLE / "evidence.tsv")
    fields = _read(PROMOTABLE / "field_evidence.tsv")
    duplicate = evidence.copy()
    duplicate.loc[0, "record_locator"] = "table:3,row:sami-duplicate"
    duplicate.loc[0, "source_record_id"] = (
        "literature:lct-rs4988235:"
        "46254d2ef02333c836b6636b83f7be3eab5bf6905223441fc370b6b9f51dae2c"
    )
    duplicate_fields = fields.copy()
    duplicate_fields["source_record_id"] = duplicate.loc[0, "source_record_id"]
    paths = _write_tables(
        tmp_path,
        pd.concat([evidence, duplicate], ignore_index=True),
        pd.concat([fields, duplicate_fields], ignore_index=True),
    )
    populations, aliases = _registry()
    with pytest.raises(ValueError, match="sample_id|duplicate"):
        publications.load(*paths, populations, aliases, "observations@2026-09-05.1")


def test_no_force_or_eligibility_override_exists():
    """Catches a bypass argument being added for agents to self-promote incomplete data."""
    populations, aliases = _registry()
    with pytest.raises(TypeError):
        publications.load(
            PROMOTABLE / "evidence.tsv",
            PROMOTABLE / "field_evidence.tsv",
            populations,
            aliases,
            "observations@2026-09-05.1",
            force=True,
        )


def test_ingest_report_refusal_counts_are_immutable():
    """Catches a caller rewriting acceptance evidence after the adapter returns it."""
    _, _, report = _load(PENDING)
    with pytest.raises(TypeError):
        report.refusals["required_field_unresolved"] = 0


def test_promoted_outputs_are_independent_of_input_row_order(tmp_path):
    """Catches the retained ledger preserving a scientifically meaningless TSV order."""
    evidence = _read(PROMOTABLE / "evidence.tsv")
    fields = _read(PROMOTABLE / "field_evidence.tsv")
    evidence.loc[0, "sample_id"] = "sami-original"
    original_sample = fields["field_name"] == "sample_id"
    fields.loc[
        original_sample, ["evidence_status", "raw_value", "source_locator", "checked_scope"]
    ] = ["reported", "sami-original", evidence.loc[0, "record_locator"], pd.NA]
    second = evidence.iloc[0].copy()
    second["record_locator"] = "table:3,row:sami-replicate"
    second["sample_id"] = "sami-replicate"
    second["source_record_id"] = make_source_record_id(
        second["corpus_id"], second["record_source_id"], second["record_locator"]
    )
    evidence = pd.concat([evidence, second.to_frame().T], ignore_index=True)
    second_fields = fields.copy()
    second_fields["source_record_id"] = second["source_record_id"]
    sample = second_fields["field_name"] == "sample_id"
    second_fields.loc[
        sample, ["evidence_status", "raw_value", "source_locator", "checked_scope"]
    ] = [
        "reported", "sami-replicate", second["record_locator"], pd.NA,
    ]
    fields = pd.concat([fields, second_fields], ignore_index=True)

    forward_paths = _write_tables(tmp_path / "forward", evidence, fields)
    reverse_paths = _write_tables(
        tmp_path / "reverse",
        evidence.iloc[::-1].reset_index(drop=True),
        fields.iloc[::-1].reset_index(drop=True),
    )
    populations, aliases = _registry()
    forward = publications.load(
        *forward_paths, populations, aliases, "observations@2026-09-05.1"
    )
    reverse = publications.load(
        *reverse_paths, populations, aliases, "observations@2026-09-05.1"
    )
    pd.testing.assert_frame_equal(forward[0], reverse[0])
    pd.testing.assert_frame_equal(forward[1], reverse[1])
