"""Earth Engine candidate-registry tests (design §7; global plan WP3; issue #290)."""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError

import pytest
from pydantic import ValidationError

from genomeos.covariates.registry import (
    ASSET_REGISTRY_SCHEMA_VERSION,
    CovariateAsset,
    CovariateAssetRegistry,
    decode_registry,
    default_registry_bytes,
    encode_registry,
    load_default_registry,
    lookup_asset,
)

SATELLITE_KEY = "google_satellite_embedding_v1_annual"


def _record() -> dict[str, object]:
    return json.loads(default_registry_bytes())["assets"][0]


def test_satellite_embedding_identity_and_joint_vector_are_frozen():
    registry = load_default_registry()
    asset = lookup_asset(registry, SATELLITE_KEY)

    assert registry.schema_version == ASSET_REGISTRY_SCHEMA_VERSION
    assert asset.platform == "google_earth_engine"
    assert asset.asset_id == "GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL"
    assert asset.publishers == ("Google Earth Engine", "Google DeepMind")
    assert asset.dataset_version == "1.1"
    assert asset.model_version == "2.1"
    assert asset.available_years == tuple(range(2017, 2025))
    assert asset.valid_time_start.isoformat() == "2017-01-01"
    assert asset.valid_time_end_exclusive.isoformat() == "2025-01-01"
    assert asset.temporal_resolution == "annual"
    assert asset.nominal_scale_m == 10.0
    assert asset.collection_layout == "tiled_images"
    assert asset.approximate_image_edge_m == 163_840.0
    assert asset.crs_semantics == "per_image_local_utm"
    assert asset.vector_dimension == 64
    assert asset.band_names == tuple(f"A{index:02d}" for index in range(64))
    assert asset.band_units == "dimensionless"
    assert asset.vector_semantics == "joint_unit_length_vector"
    assert asset.required_image_properties == (
        "DATASET_VERSION",
        "MODEL_VERSION",
        "PROCESSING_SOFTWARE_VERSION",
        "UTM_ZONE",
        "system:time_start",
        "system:time_end",
    )


def test_candidate_state_separates_catalog_facts_from_unrun_extraction_and_admission():
    asset = lookup_asset(load_default_registry(), SATELLITE_KEY)

    assert asset.admission_status == "candidate_only"
    assert asset.extraction_status == "not_run"
    assert asset.empirically_observed_scale_m is None
    assert asset.extraction_receipt_sha256 is None
    assert asset.commercial_compatibility == "compatible"
    assert asset.commercial_use.finding == "explicitly_open"
    assert asset.commercial_use.restricted_fields == ()
    assert asset.license_spdx == "CC-BY-4.0"
    assert asset.attribution == (
        "The AlphaEarth Foundations Satellite Embedding dataset is produced by Google and "
        "Google DeepMind."
    )
    assert any("not historical ancestry" in limit for limit in asset.interpretation_limits)
    assert any("all 64 bands jointly" in limit for limit in asset.interpretation_limits)


def test_default_registry_is_canonical_and_round_trips_exactly():
    raw = default_registry_bytes()
    decoded = decode_registry(raw)

    assert encode_registry(decoded) == raw
    assert decode_registry(encode_registry(decoded)) == decoded


def test_registry_and_records_are_immutable():
    registry = load_default_registry()
    with pytest.raises((AttributeError, FrozenInstanceError, ValidationError)):
        registry.assets = ()  # type: ignore[misc]
    with pytest.raises((AttributeError, FrozenInstanceError, ValidationError)):
        registry.assets[0].dataset_version = "invented"  # type: ignore[misc]


def test_lookup_refuses_an_unknown_asset_key():
    with pytest.raises(KeyError, match="unknown covariate asset"):
        lookup_asset(load_default_registry(), "missing")


@pytest.mark.parametrize(
    ("mutation", "match"),
    [
        ({"band_names": [f"A{index:02d}" for index in range(63)]}, "vector_dimension"),
        ({"available_years": [2017, 2019]}, "continuous annual interval"),
        ({"valid_time_end_exclusive": "2024-01-01"}, "available_years"),
        ({"required_image_properties": ["DATASET_VERSION"]}, "required_image_properties"),
        ({"commercial_compatibility": "incompatible"}, "commercial_compatibility"),
        (
            {
                "extraction_status": "not_run",
                "empirically_observed_scale_m": 10.0,
            },
            "not_run",
        ),
        (
            {
                "extraction_status": "fixture_extracted",
                "empirically_observed_scale_m": 10.0,
                "extraction_receipt_sha256": None,
            },
            "receipt",
        ),
    ],
)
def test_asset_contract_refuses_inconsistent_scientific_metadata(mutation, match):
    values = _record()
    values.update(mutation)
    with pytest.raises(ValueError, match=match):
        CovariateAsset.model_validate(values)


def test_asset_contract_refuses_unknown_fields():
    values = _record()
    values["plausible_default"] = "silently accepted"
    with pytest.raises(ValueError, match="Extra inputs"):
        CovariateAsset.model_validate(values)


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        ("nominal_scale_m", True, "valid number"),
        ("nominal_scale_m", "10.0", "valid number"),
        ("approximate_image_edge_m", "163840.0", "valid number"),
        ("vector_dimension", True, "valid integer"),
        ("vector_dimension", "64", "valid integer"),
        ("dataset_version", 1.1, "valid string"),
    ],
)
def test_asset_contract_refuses_scalar_coercion(field, value, match):
    values = _record()
    values[field] = value
    with pytest.raises(ValueError, match=match):
        CovariateAsset.model_validate(values)


def test_registry_refuses_duplicate_keys_and_platform_asset_ids():
    record = _record()
    duplicate_key = dict(record)
    duplicate_key["asset_id"] = "GOOGLE/OTHER/ASSET"
    with pytest.raises(ValueError, match="asset_key"):
        CovariateAssetRegistry.model_validate(
            {"schema_version": ASSET_REGISTRY_SCHEMA_VERSION, "assets": [record, duplicate_key]}
        )

    duplicate_id = dict(record)
    duplicate_id["asset_key"] = "different_key"
    with pytest.raises(ValueError, match="platform asset identity"):
        CovariateAssetRegistry.model_validate(
            {"schema_version": ASSET_REGISTRY_SCHEMA_VERSION, "assets": [record, duplicate_id]}
        )


def test_decode_refuses_noncanonical_or_malformed_registry_bytes():
    payload = json.loads(default_registry_bytes())
    noncanonical = json.dumps(payload).encode()
    with pytest.raises(ValueError, match="canonical"):
        decode_registry(noncanonical)
    with pytest.raises(ValueError, match="JSON"):
        decode_registry(b"not-json")
