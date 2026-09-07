"""Browser-export contracts for the Cesium explorer (design §11)."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

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
    return artifact


def test_public_catalog_inventory_has_two_map_and_twenty_eight_afnd_entries() -> None:
    allowlist = json.loads(PUBLIC_ALLOWLIST.read_text())
    entries = allowlist["artifacts"]
    assert len(entries) == 30
    assert len({entry["id"] for entry in entries}) == 30
    assert len({entry["artifact_dir"] for entry in entries}) == 30
    assert sum(entry["observation_source"] is not None for entry in entries) == 2
    families = {entry["variant_id"].split(":", 1)[0] for entry in entries}
    assert families == {"chr11-5227002-T-A", "phenotype", "cyt", "hla", "kir"}
    assert sum(entry["variant_id"].startswith("cyt:") for entry in entries) == 4
    assert sum(entry["variant_id"].startswith("hla:") for entry in entries) == 20
    assert sum(entry["variant_id"].startswith("kir:") for entry in entries) == 4


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
    assert {path.name for path in paths} == {
        "catalog.json",
        "hbs-rs334.observations.json",
        "hbs-rs334.surface.json",
    }

    surface = json.loads((export_inputs["out"] / "hbs-rs334.surface.json").read_text())
    observations = json.loads(
        (export_inputs["out"] / "hbs-rs334.observations.json").read_text()
    )
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


def test_export_is_byte_deterministic(export_inputs: dict[str, Path]) -> None:
    _export(export_inputs)
    before = {
        path.name: path.read_bytes() for path in sorted(export_inputs["out"].iterdir())
    }
    _export(export_inputs)
    after = {
        path.name: path.read_bytes() for path in sorted(export_inputs["out"].iterdir())
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


def test_export_refuses_missing_manifest_version(export_inputs: dict[str, Path]) -> None:
    manifest_path = (
        export_inputs["store"] / "artifacts" / "hbs-test__v1__map-test" / "manifest.json"
    )
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

    assert {path.name for path in paths} == {
        "catalog.json",
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
