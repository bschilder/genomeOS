"""Browser-export contracts for the Cesium explorer (design §11)."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from genomeos.registry.variants import load as load_variant_registry
from genomeos.registry.variants import normalized_identity
from scripts import export_atlas_web

HF_REVISION = "fc17bc1c1d96a0d0766746dcf26277ccdc669717"
VARIANT_ID = "chr11-5227002-T-A"
PUBLIC_ALLOWLIST = Path("website/src/atlas/public-artifacts.json")


def _write_source_tree(root: Path) -> Path:
    artifact = root / "artifacts" / "hbs-test__v1__map-test"
    artifact.mkdir(parents=True)
    cells = pd.DataFrame(
        {
            "h3_index": ["831f8dfffffffff", "831f8cfffffffff"],
            "variant_id": [VARIANT_ID, VARIANT_ID],
            "post_median": [0.1, 0.2],
            "post_mean": [0.11, 0.21],
            "post_sd": [0.01, 0.03],
            "q025": [0.08, 0.15],
            "q975": [0.14, 0.27],
            "q25": [0.1, 0.19],
            "q75": [0.12, 0.23],
            "support": ["observed", "unknown"],
            "posterior_contraction": [0.2, 0.9],
            "dist_nearest_obs_km": [0.0, 1200.0],
            "model_version": ["v1", "v1"],
            "data_version": ["map-test", "map-test"],
        }
    )
    cells.to_parquet(artifact / "cells.parquet", index=False)
    (artifact / "manifest.json").write_text(
        json.dumps(
            {
                "artifact_format": 1,
                "correlation_range_km": 500.0,
                "data_version": "map-test",
                "lengthscale_sigma": 0.5,
                "likelihood": "beta_binomial",
                "model_version": "v1",
                "n_cells": 2,
                "n_observations": 1,
                "prior_frequency_sd": 0.1,
                "resolution": 3,
                "support_counts": {"observed": 1, "unknown": 1},
                "variant_id": VARIANT_ID,
            }
        )
    )
    (root / "catalog-metadata.json").write_text(
        json.dumps(
            {
                "artifact_version": "atlas-test-v1",
                "registry_version": "map-test-registry",
                "created_at": "2026-09-06T00:00:00Z",
                "assumptions": ["test catalog"],
                "discovery_groups": [
                    {
                        "id": "red-blood-cell-disorders",
                        "label": "Red blood cell disorders",
                        "summary": "Hemoglobin and red-cell enzyme traits.",
                        "biology": "These maps describe variation affecting red blood cells.",
                        "references": [
                            {
                                "label": "NIH overview",
                                "url": "https://www.nhlbi.nih.gov/health/anemia",
                            }
                        ],
                    }
                ],
                "discovery": {
                    VARIANT_ID: {
                        "group_id": "red-blood-cell-disorders",
                        "map_measures": "Frequency of the HbS allele in sampled populations.",
                        "symbol_expansion": "Hemoglobin S, HBB rs334",
                        "relevance": "HbS is the causal hemoglobin variant in sickle cell disease.",
                        "aliases": ["sickle hemoglobin", "HBB"],
                        "references": [
                            {
                                "label": "MedlinePlus Genetics: sickle cell disease",
                                "url": "https://medlineplus.gov/genetics/condition/sickle-cell-disease/",
                            }
                        ],
                    }
                },
                "variants": {
                    VARIANT_ID: {
                        "label": "HbS (rs334)",
                        "entity_type": "variant",
                        "measurement": "allele_frequency",
                        "surface_eligible": True,
                        "assumptions": ["test surface"],
                    }
                },
            }
        )
    )
    cache = root / "external" / "gnomad" / "chr11-5227002-t-a.json"
    cache.parent.mkdir(parents=True)
    cache.write_text(
        json.dumps(
            {
                "query": {
                    "dataset": "gnomad_r4",
                    "normalized_variant_id": VARIANT_ID,
                },
                "record": {"fixture": True},
                "retrieved_at": "2026-09-07T00:00:00Z",
                "schema_version": 2,
                "source": "gnomad",
                "source_release": "gnomad_r4",
            }
        )
    )
    return artifact


def test_public_catalog_inventory_has_two_map_and_twenty_eight_afnd_entries() -> None:
    allowlist = json.loads(PUBLIC_ALLOWLIST.read_text())
    entries = allowlist["artifacts"]
    assert len(entries) == 30
    assert len({entry["id"] for entry in entries}) == 30
    assert len({entry["artifact_dir"] for entry in entries}) == 30
    assert sum(entry["observation_source"] is not None for entry in entries) == 30
    families = {entry["variant_id"].split(":", 1)[0] for entry in entries}
    assert families == {"chr11-5227002-T-A", "phenotype", "cyt", "hla", "kir"}
    assert sum(entry["variant_id"].startswith("cyt:") for entry in entries) == 4
    assert sum(entry["variant_id"].startswith("hla:") for entry in entries) == 20
    assert sum(entry["variant_id"].startswith("kir:") for entry in entries) == 4


def test_every_declared_external_resource_resolves_against_the_real_registry() -> None:
    """The real allowlist joined to the real registry — the only test that reads both.

    Exporting was previously the sole place these two files met, so a row becoming unresolvable
    (pending verification, refused, or removed) broke a published artifact with nothing failing
    first. It also catches the opposite mistake: declaring an external resource for a locus whose
    row is still pending.
    """
    allowlist = json.loads(PUBLIC_ALLOWLIST.read_text())
    registry = load_variant_registry(export_atlas_web.VARIANT_REGISTRY_PATH)
    declaring = [entry for entry in allowlist["artifacts"] if entry.get("external_resources")]
    assert declaring, "expected at least one allowlisted artifact to declare an external resource"
    assert [
        entry["id"]
        for entry in declaring
        if normalized_identity(entry["variant_id"], registry) is None
    ] == []


def _write_hbs_csv(path: Path) -> None:
    pd.DataFrame(
        [
            {
                "id": 1,
                "latitude": 5.56,
                "longitude": -0.2,
                "country": "Ghana",
                "sample_size": 10,
                "hbaa": 8,
                "hbas": 2,
                "hbss": 0,
                "malaria_hypothesis": "YES",
                "population_estimates": "YES",
                "area_type": "Point (≤ 10 km2)",
                "source": "IBDTEST",
                "citation": "Example citation.",
            }
        ]
    ).to_csv(path, index=False)


def _write_allowlist(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "hf_dataset": "bschilder/genomeos-data",
                "hf_revision": HF_REVISION,
                "artifacts": [
                    {
                        "id": "hbs-rs334",
                        "variant_id": VARIANT_ID,
                        "artifact_dir": "hbs-test__v1__map-test",
                        "observation_source": "map_hbs_surveys.csv",
                        "external_resources": [
                            {
                                "source": "gnomad",
                                "normalized_variant_id": VARIANT_ID,
                                "dataset": "gnomad_r4",
                                "cache_file": "external/gnomad/chr11-5227002-t-a.json",
                            }
                        ],
                    }
                ],
            }
        )
    )


@pytest.fixture
def export_inputs(tmp_path: Path) -> dict[str, Path]:
    store = tmp_path / "store"
    _write_source_tree(store)
    hbs = tmp_path / "map_hbs_surveys.csv"
    g6pd = tmp_path / "map_g6pd_surveys.csv"
    allowlist = tmp_path / "allowlist.json"
    _write_hbs_csv(hbs)
    g6pd.write_text("id,latitude,longitude\n")
    _write_allowlist(allowlist)
    return {
        "store": store,
        "hbs": hbs,
        "g6pd": g6pd,
        "allowlist": allowlist,
        "out": tmp_path / "web",
    }


def _export(inputs: dict[str, Path], **kwargs: object) -> list[Path]:
    return export_atlas_web.export_catalog(
        source_root=inputs["store"],
        hbs_csv=inputs["hbs"],
        g6pd_csv=inputs["g6pd"],
        allowlist_path=inputs["allowlist"],
        out_dir=inputs["out"],
        hf_revision=HF_REVISION,
        **kwargs,
    )


def test_export_preserves_support_versions_and_observation_evidence(
    export_inputs: dict[str, Path],
) -> None:
    paths = _export(export_inputs)
    assert {path.relative_to(export_inputs["out"]).as_posix() for path in paths} == {
        "catalog.json",
        "external/gnomad/chr11-5227002-t-a.json",
        "hbs-rs334.manifest.json",
        "hbs-rs334.observations.json",
        "hbs-rs334.surface.json",
    }

    surface = json.loads((export_inputs["out"] / "hbs-rs334.surface.json").read_text())
    observations = json.loads((export_inputs["out"] / "hbs-rs334.observations.json").read_text())
    catalog = json.loads((export_inputs["out"] / "catalog.json").read_text())

    assert {cell["support"] for cell in surface["cells"]} == {"observed", "unknown"}
    assert surface["artifact"]["hf_revision"] == HF_REVISION
    assert surface["artifact"]["model_version"] == "v1"
    assert all(row["radius_km"] > 0 for row in observations["observations"])
    assert observations["observations"][0]["citation_text"] == "Example citation."
    assert observations["observations"][0]["population_label"] == "Ghana"
    assert observations["observations"][0]["study_id"] == "map-study-IBDTEST"
    assert observations["observations"][0]["study_label"] == "IBDTEST"
    assert catalog["artifacts"][0]["surface_sha256"]
    assert catalog["artifacts"][0]["observations_sha256"]
    assert catalog["artifacts"][0]["downloads"]["manifest"]["sha256"]
    assert catalog["discovery_groups"][0]["label"] == "Red blood cell disorders"
    assert catalog["artifacts"][0]["discovery"] == {
        "group_id": "red-blood-cell-disorders",
        "map_measures": "Frequency of the HbS allele in sampled populations.",
        "symbol_expansion": "Hemoglobin S, HBB rs334",
        "relevance": "HbS is the causal hemoglobin variant in sickle cell disease.",
        "aliases": ["sickle hemoglobin", "HBB"],
        "references": [
            {
                "label": "MedlinePlus Genetics: sickle cell disease",
                "url": "https://medlineplus.gov/genetics/condition/sickle-cell-disease/",
            }
        ],
    }
    assert catalog["artifacts"][0]["external_resources"] == [
        {
            "cache_sha256": catalog["artifacts"][0]["external_resources"][0]["cache_sha256"],
            "cache_url": "external/gnomad/chr11-5227002-t-a.json",
            "dataset": "gnomad_r4",
            "normalized_variant_id": VARIANT_ID,
            "source": "gnomad",
        }
    ]


def test_export_is_byte_deterministic(export_inputs: dict[str, Path]) -> None:
    _export(export_inputs)
    before = {
        path.relative_to(export_inputs["out"]).as_posix(): path.read_bytes()
        for path in sorted(export_inputs["out"].rglob("*"))
        if path.is_file()
    }
    _export(export_inputs)
    after = {
        path.relative_to(export_inputs["out"]).as_posix(): path.read_bytes()
        for path in sorted(export_inputs["out"].rglob("*"))
        if path.is_file()
    }
    assert after == before


def test_export_refuses_an_artifact_outside_the_allowlist(
    export_inputs: dict[str, Path],
) -> None:
    with pytest.raises(ValueError, match="not allowlisted"):
        _export(export_inputs, requested_ids=["hla:a-02-01"])


def test_export_refuses_missing_observation_radius(
    export_inputs: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    real_load = export_atlas_web.map_surveys.load

    def load_without_radius(*args: object, **kwargs: object):
        frame, report = real_load(*args, **kwargs)
        return frame.drop(columns="radius_km"), report

    monkeypatch.setattr(export_atlas_web.map_surveys, "load", load_without_radius)
    with pytest.raises(ValueError, match="radius_km"):
        _export(export_inputs)


def test_export_refuses_missing_discovery_metadata(export_inputs: dict[str, Path]) -> None:
    metadata_path = export_inputs["store"] / "catalog-metadata.json"
    metadata = json.loads(metadata_path.read_text())
    del metadata["discovery"][VARIANT_ID]
    metadata_path.write_text(json.dumps(metadata))

    with pytest.raises(ValueError, match="discovery"):
        _export(export_inputs)


def test_export_refuses_missing_source_native_study_label(
    export_inputs: dict[str, Path],
) -> None:
    source = pd.read_csv(export_inputs["hbs"])
    source.loc[0, "source"] = ""
    source.to_csv(export_inputs["hbs"], index=False)
    with pytest.raises(ValueError, match="study_label"):
        _export(export_inputs)


def test_export_refuses_non_finite_surface_values(export_inputs: dict[str, Path]) -> None:
    artifact = export_inputs["store"] / "artifacts" / "hbs-test__v1__map-test"
    cells = pd.read_parquet(artifact / "cells.parquet")
    cells.loc[0, "post_mean"] = float("nan")
    cells.to_parquet(artifact / "cells.parquet", index=False)
    with pytest.raises(ValueError, match="post_mean must be finite"):
        _export(export_inputs)


def test_export_accepts_contraction_ratio_above_one_and_refuses_negative(
    export_inputs: dict[str, Path],
) -> None:
    artifact = export_inputs["store"] / "artifacts" / "hbs-test__v1__map-test"
    cells_path = artifact / "cells.parquet"
    cells = pd.read_parquet(cells_path)
    cells.loc[0, "posterior_contraction"] = 1.37
    cells.to_parquet(cells_path, index=False)

    _export(export_inputs)

    cells.loc[0, "posterior_contraction"] = -0.01
    cells.to_parquet(cells_path, index=False)
    with pytest.raises(ValueError, match="posterior_contraction must be non-negative"):
        _export(export_inputs)


def test_export_refuses_missing_manifest_version(export_inputs: dict[str, Path]) -> None:
    manifest_path = export_inputs["store"] / "artifacts" / "hbs-test__v1__map-test" / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    del manifest["model_version"]
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="model_version"):
        _export(export_inputs)


def test_export_refuses_variant_mismatch(export_inputs: dict[str, Path]) -> None:
    artifact = export_inputs["store"] / "artifacts" / "hbs-test__v1__map-test"
    cells = pd.read_parquet(artifact / "cells.parquet")
    cells.loc[0, "variant_id"] = "chr1-1-A-C"
    cells.to_parquet(artifact / "cells.parquet", index=False)
    with pytest.raises(ValueError, match="variant_id"):
        _export(export_inputs)


def test_export_keeps_reviewed_surface_when_observations_are_unavailable(
    export_inputs: dict[str, Path],
) -> None:
    allowlist = json.loads(export_inputs["allowlist"].read_text())
    allowlist["artifacts"][0]["observation_source"] = None
    export_inputs["allowlist"].write_text(json.dumps(allowlist))
    metadata_path = export_inputs["store"] / "catalog-metadata.json"
    metadata = json.loads(metadata_path.read_text())
    metadata["variants"][VARIANT_ID]["registry_version"] = "afnd-test-registry"
    metadata_path.write_text(json.dumps(metadata))

    paths = _export(export_inputs)

    assert {path.relative_to(export_inputs["out"]).as_posix() for path in paths} == {
        "catalog.json",
        "external/gnomad/chr11-5227002-t-a.json",
        "hbs-rs334.manifest.json",
        "hbs-rs334.surface.json",
    }
    catalog = json.loads((export_inputs["out"] / "catalog.json").read_text())
    artifact = catalog["artifacts"][0]
    assert artifact["registry_version"] == "afnd-test-registry"
    assert artifact["n_observations"] == 1
    assert artifact["observations_available"] is False
    assert artifact["observations_sha256"] is None
    assert artifact["observations_url"] is None
    assert catalog["registry_versions"] == ["afnd-test-registry"]


def test_a_coordinate_keyed_resource_needs_a_reviewed_normalization(tmp_path):
    """A cytokine locus is entity_type=variant but has a composite id, so it must refuse until
    the registry says otherwise. Previously this passed the exporter and failed in the browser."""
    from genomeos.registry.variants import VARIANT_NORMALIZATION_SCHEMA

    empty = VARIANT_NORMALIZATION_SCHEMA.validate(
        pd.DataFrame(columns=list(VARIANT_NORMALIZATION_SCHEMA.columns))
    )
    entry = {
        "external_resources": [
            {
                "source": "gnomad",
                "normalized_variant_id": "cyt:il-6-174-c",
                "dataset": "gnomad_r4",
                "cache_file": "external/gnomad/cyt.json",
            }
        ]
    }
    with pytest.raises(ValueError, match="no reviewed normalization"):
        export_atlas_web._external_resources(
            entry,
            artifact_id="cyt-il-6-174-c",
            variant_id="cyt:il-6-174-c",
            entity_type="variant",
            source_root=tmp_path,
            out_dir=tmp_path / "out",
            variant_registry=empty,
        )
