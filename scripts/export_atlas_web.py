#!/usr/bin/env python3
"""Export allowlisted Atlas artifacts for the static globe client (design §11).

This is a publication boundary, not another ingestion path. It reuses the validated MAP source
adapters, refuses incomplete scientific metadata, and emits only artifact identities named in the
repository-owned allowlist. The browser receives no fit objects, credentials, or unapproved data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import pandas as pd

from genomeos.observations.sources import (
    afnd_carriers,
    afnd_cytokines,
    afnd_frequencies,
    map_g6pd,
    map_surveys,
)
from genomeos.publication.atlas_discovery import validate_artifact_discovery, validate_discovery_groups
from genomeos.registry.sources import afnd as afnd_registry

SCHEMA_VERSION = 1
SUPPORT_STATES = {"observed", "interpolated", "prior_dominated", "unknown"}
SURFACE_COLUMNS = {
    "h3_index",
    "variant_id",
    "post_mean",
    "post_sd",
    "q025",
    "q975",
    "support",
    "posterior_contraction",
    "dist_nearest_obs_km",
    "model_version",
    "data_version",
}
MANIFEST_FIELDS = {
    "artifact_format",
    "correlation_range_km",
    "data_version",
    "likelihood",
    "model_version",
    "n_cells",
    "n_observations",
    "resolution",
    "support_counts",
    "variant_id",
}
FORMAT_2_MANIFEST_FIELDS = {"target_grid_source", "target_grid_version"}
OBSERVATION_FIELDS = {
    "source_record_id",
    "lat",
    "lon",
    "radius_km",
    "ac",
    "an",
    "assay",
    "sampling_design",
    "disease_ascertainment_excluded",
    "cohort_id",
    "ingest_version",
}
NATURAL_EARTH_REVISION = "ca96624a56bd078437bca8184e78163e5039ad19"
NATURAL_EARTH_SOURCE = (
    "https://github.com/nvkelso/natural-earth-vector/blob/"
    f"{NATURAL_EARTH_REVISION}/geojson/ne_50m_admin_0_countries.geojson"
)
NATURAL_EARTH_PLACES_SOURCE = (
    "https://github.com/nvkelso/natural-earth-vector/blob/"
    f"{NATURAL_EARTH_REVISION}/geojson/ne_50m_populated_places.geojson"
)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"{path}: invalid JSON: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return value


def _require_fields(value: Mapping[str, Any], fields: set[str], context: str) -> None:
    missing = fields - set(value)
    if missing:
        raise ValueError(f"{context}: missing required fields {sorted(missing)}")


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n").encode()


def _write_json(path: Path, value: Any, *, refuse_conflict: bool = False) -> str:
    content = _canonical_bytes(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    if refuse_conflict and path.exists() and path.read_bytes() != content:
        raise ValueError(f"{path}: two exports produced different content for one cache path")
    path.write_bytes(content)
    return hashlib.sha256(content).hexdigest()


def _json_value(value: Any) -> Any:
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


def _validated_surface(
    artifact_dir: Path,
    expected_variant_id: str,
) -> tuple[dict[str, Any], pd.DataFrame]:
    manifest = _read_json(artifact_dir / "manifest.json")
    _require_fields(manifest, MANIFEST_FIELDS, str(artifact_dir / "manifest.json"))
    if int(manifest["artifact_format"]) == 2:
        _require_fields(
            manifest,
            FORMAT_2_MANIFEST_FIELDS,
            str(artifact_dir / "manifest.json"),
        )
    if manifest["variant_id"] != expected_variant_id:
        raise ValueError(
            f"{artifact_dir}: manifest variant_id {manifest['variant_id']!r} does not match "
            f"allowlist {expected_variant_id!r}"
        )

    cells = pd.read_parquet(artifact_dir / "cells.parquet")
    missing = SURFACE_COLUMNS - set(cells.columns)
    if missing:
        raise ValueError(f"{artifact_dir}: missing surface columns {sorted(missing)}")
    if len(cells) != int(manifest["n_cells"]):
        raise ValueError(f"{artifact_dir}: n_cells={manifest['n_cells']} but parquet has {len(cells)} rows")
    if cells["h3_index"].duplicated().any():
        raise ValueError(f"{artifact_dir}: h3_index must be unique")

    for field, expected in (
        ("variant_id", manifest["variant_id"]),
        ("model_version", manifest["model_version"]),
        ("data_version", manifest["data_version"]),
    ):
        actual = set(cells[field].astype(str))
        if actual != {str(expected)}:
            raise ValueError(f"{artifact_dir}: {field} values {sorted(actual)} != {expected!r}")

    support = set(cells["support"].astype(str))
    invalid_support = support - SUPPORT_STATES
    if invalid_support:
        raise ValueError(f"{artifact_dir}: invalid support states {sorted(invalid_support)}")
    actual_support = cells["support"].value_counts().to_dict()
    declared_support = {str(key): int(value) for key, value in manifest["support_counts"].items()}
    if actual_support != declared_support:
        raise ValueError(f"{artifact_dir}: support_counts {declared_support} != parquet {actual_support}")

    for field in (
        "post_mean",
        "post_sd",
        "q025",
        "q975",
        "posterior_contraction",
        "dist_nearest_obs_km",
    ):
        numeric = pd.to_numeric(cells[field], errors="coerce")
        if numeric.isna().any() or not numeric.map(math.isfinite).all():
            raise ValueError(f"{artifact_dir}: every {field} must be finite")
    if not cells["post_mean"].between(0, 1).all():
        raise ValueError(f"{artifact_dir}: post_mean must be in [0, 1]")
    if not cells["q025"].between(0, 1).all() or not cells["q975"].between(0, 1).all():
        raise ValueError(f"{artifact_dir}: credible interval bounds must be in [0, 1]")
    if (cells["post_sd"] < 0).any():
        raise ValueError(f"{artifact_dir}: post_sd must be non-negative")
    if (cells["posterior_contraction"] < 0).any():
        raise ValueError(f"{artifact_dir}: posterior_contraction must be non-negative")
    if (cells["dist_nearest_obs_km"] < 0).any():
        raise ValueError(f"{artifact_dir}: dist_nearest_obs_km must be non-negative")
    if ((cells["q025"] > cells["post_mean"]) | (cells["post_mean"] > cells["q975"])).any():
        raise ValueError(f"{artifact_dir}: q025 <= post_mean <= q975 is required")
    return manifest, cells


def _metric_domains(cells: pd.DataFrame) -> dict[str, list[float]]:
    supported = cells[cells["support"].isin({"observed", "interpolated"})]
    if supported.empty:
        raise ValueError("surface has no observed or interpolated cells")
    return {
        field: [float(supported[field].min()), float(supported[field].max())]
        for field in ("post_mean", "post_sd")
    }


def _load_observations(
    observation_source: str,
    hbs_csv: Path,
    g6pd_csv: Path,
    afnd_frequencies_tsv: Path | None,
    afnd_populations_tsv: Path | None,
    ingest_version: str,
) -> tuple[pd.DataFrame, pd.DataFrame, str, str]:
    if observation_source == "map_hbs_surveys.csv":
        raw = pd.read_csv(hbs_csv)
        observations, _ = map_surveys.load(hbs_csv, ingest_version)
        prefix = "map-surveys:"
        source_url = "raw/map_hbs_surveys.csv"
        study_label_field = "source"
    elif observation_source == "map_g6pd_surveys.csv":
        raw = pd.read_csv(g6pd_csv)
        observations, _ = map_g6pd.load(g6pd_csv, ingest_version)
        prefix = "map-g6pd:"
        source_url = "raw/map_g6pd_surveys.csv"
        study_label_field = "citation"
    elif observation_source in {
        "afnd_frequencies",
        "afnd_cytokines",
        "afnd_carriers",
    }:
        if afnd_frequencies_tsv is None or afnd_populations_tsv is None:
            raise ValueError(f"{observation_source}: AFND frequency and population paths required")
        if observation_source == "afnd_frequencies":
            observations, _ = afnd_frequencies.load(
                afnd_frequencies_tsv,
                afnd_populations_tsv,
                ingest_version,
            )
        elif observation_source == "afnd_cytokines":
            observations, _ = afnd_cytokines.load(
                afnd_frequencies_tsv,
                afnd_populations_tsv,
                ingest_version,
            )
        else:
            carriers, _ = afnd_carriers.load(
                afnd_frequencies_tsv,
                afnd_populations_tsv,
                ingest_version,
            )
            observations = afnd_carriers.as_binomial(carriers)
        raw = pd.read_csv(
            afnd_populations_tsv,
            sep="\t",
            dtype=str,
            keep_default_na=False,
        )
        _require_fields(raw.iloc[0].to_dict(), {"pop_id", "population"}, str(afnd_populations_tsv))
        raw["population_id"] = raw["pop_id"].map(afnd_registry.population_id)
        raw["country"] = raw["population"]
        raw["citation"] = raw["population"].map(
            lambda value: f"Allele Frequency Net Database (AFND): {value}"
        )
        raw["study_label"] = raw["population"]
        raw = raw.set_index("population_id")
        evidence_rows: list[dict[str, Any]] = []
        for record in observations.to_dict(orient="records"):
            population_id = str(record["population_id"])
            if population_id not in raw.index:
                raise ValueError(f"{observation_source}: {population_id} has no AFND population evidence")
            population = raw.loc[population_id]
            evidence_rows.append(
                {
                    "citation": population["citation"],
                    "country": population["country"],
                    "source_locator": (
                        f"AFND {record['variant_id']} measurement for {population['population']}"
                    ),
                    "source_record_id": record["source_record_id"],
                    "source_url": population.get("source_url", ""),
                    "study_label": population["study_label"],
                }
            )
        evidence = pd.DataFrame(evidence_rows).set_index("source_record_id")
        return observations, evidence, "raw/afnd_frequencies.tsv", "afnd:"
    else:
        raise ValueError(f"unsupported observation source {observation_source!r}")

    missing = OBSERVATION_FIELDS - set(observations.columns)
    if missing:
        raise ValueError(f"{observation_source}: missing observation fields {sorted(missing)}")
    raw_missing = {"id", "country", "citation", study_label_field} - set(raw.columns)
    if raw_missing:
        raise ValueError(f"{observation_source}: missing source fields {sorted(raw_missing)}")
    if raw["id"].duplicated().any():
        raise ValueError(f"{observation_source}: source-native id must be unique")
    raw = raw.copy()
    raw["source_record_id"] = raw["id"].map(lambda value: f"{prefix}{int(value)}")
    raw["study_label"] = raw[study_label_field]
    evidence = raw.set_index("source_record_id")
    return observations, evidence, source_url, prefix


def _serialize_observations(
    observations: pd.DataFrame,
    evidence: pd.DataFrame,
    *,
    source_url: str,
    dataset: str,
    revision: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in observations.to_dict(orient="records"):
        source_record_id = str(record["source_record_id"])
        if source_record_id not in evidence.index:
            raise ValueError(f"observation {source_record_id}: missing source evidence")
        source = evidence.loc[source_record_id]
        population_label = source["country"]
        citation = source["citation"]
        study_id = record["cohort_id"]
        study_label = source["study_label"]
        if not isinstance(population_label, str) or not population_label.strip():
            raise ValueError(f"observation {source_record_id}: population_label is required")
        if not isinstance(citation, str) or not citation.strip():
            raise ValueError(f"observation {source_record_id}: citation_text is required")
        if not isinstance(study_id, str) or not study_id.strip():
            raise ValueError(f"observation {source_record_id}: study_id is required")
        if not isinstance(study_label, str) or not study_label.strip():
            raise ValueError(f"observation {source_record_id}: study_label is required")
        radius = _json_value(record["radius_km"])
        if not isinstance(radius, (int, float)) or not math.isfinite(radius) or radius <= 0:
            raise ValueError(f"observation {source_record_id}: radius_km must be positive and finite")
        lat = float(record["lat"])
        lon = float(record["lon"])
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError(f"observation {source_record_id}: invalid coordinates")
        evidence_url = source.get("source_url", "")
        record_url = (
            str(evidence_url).strip()
            if isinstance(evidence_url, str) and evidence_url.strip()
            else f"https://huggingface.co/datasets/{dataset}/blob/{revision}/{source_url}"
        )
        source_locator = source.get("source_locator", f"MAP survey {source_record_id.split(':', 1)[1]}")
        rows.append(
            {
                "ac": int(record["ac"]),
                "an": int(record["an"]),
                "assay": str(record["assay"]),
                "citation_text": citation.strip(),
                "cohort_id": str(record["cohort_id"]),
                "disease_ascertainment_excluded": bool(record["disease_ascertainment_excluded"]),
                "ingest_version": str(record["ingest_version"]),
                "lat": lat,
                "lon": lon,
                "population_label": population_label.strip(),
                "radius_km": float(radius),
                "sampling_design": str(record["sampling_design"]),
                "source_locator": str(source_locator),
                "source_record_id": source_record_id,
                "source_url": record_url,
                "study_id": study_id.strip(),
                "study_label": study_label.strip(),
            }
        )
    return rows


def _surface_payload(
    artifact_id: str,
    variant_metadata: Mapping[str, Any],
    manifest: Mapping[str, Any],
    cells: pd.DataFrame,
    *,
    registry_version: str,
    hf_dataset: str,
    hf_revision: str,
) -> dict[str, Any]:
    domains = _metric_domains(cells)
    selected = cells[
        [
            "h3_index",
            "post_mean",
            "post_sd",
            "q025",
            "q975",
            "support",
            "posterior_contraction",
            "dist_nearest_obs_km",
        ]
    ]
    cell_rows = [
        {key: _json_value(value) for key, value in record.items()}
        for record in selected.to_dict(orient="records")
    ]
    identity = {
        "artifact_format": int(manifest["artifact_format"]),
        "data_version": str(manifest["data_version"]),
        "entity_type": str(variant_metadata["entity_type"]),
        "hf_dataset": hf_dataset,
        "hf_revision": hf_revision,
        "id": artifact_id,
        "label": str(variant_metadata["label"]),
        "measurement": str(variant_metadata["measurement"]),
        "metric_domains": domains,
        "model_version": str(manifest["model_version"]),
        "registry_version": registry_version,
        "resolution": int(manifest["resolution"]),
        "variant_id": str(manifest["variant_id"]),
    }
    if int(manifest["artifact_format"]) == 2:
        identity.update(
            {
                "target_grid_source": str(manifest["target_grid_source"]),
                "target_grid_version": str(manifest["target_grid_version"]),
            }
        )
    return {
        "artifact": identity,
        "cells": cell_rows,
        "schema_version": SCHEMA_VERSION,
    }


def _external_resources(
    entry: Mapping[str, Any],
    *,
    artifact_id: str,
    variant_id: str,
    entity_type: str,
    source_root: Path,
    out_dir: Path,
) -> tuple[list[dict[str, Any]], list[Path]]:
    """Validate declared capabilities and publish their normalized cache payloads."""
    declared = entry.get("external_resources", [])
    if not isinstance(declared, list):
        raise ValueError(f"allowlist artifact {artifact_id}: external_resources must be a list")
    if declared and entity_type != "variant":
        raise ValueError(f"allowlist artifact {artifact_id}: external lookup requires entity_type=variant")
    resources: list[dict[str, Any]] = []
    written: list[Path] = []
    seen: set[str] = set()
    for resource in declared:
        if not isinstance(resource, Mapping):
            raise ValueError(f"allowlist artifact {artifact_id}: invalid external resource")
        _require_fields(
            resource,
            {"source", "normalized_variant_id", "cache_file"},
            f"allowlist artifact {artifact_id} external resource",
        )
        source = str(resource["source"])
        if source not in {"gnomad", "dbsnp"} or source in seen:
            raise ValueError(f"allowlist artifact {artifact_id}: external source must be unique gnomad/dbsnp")
        seen.add(source)
        normalized = str(resource["normalized_variant_id"])
        if normalized != variant_id:
            raise ValueError(
                f"allowlist artifact {artifact_id}: external normalized variant does not match the artifact"
            )
        cache_file = Path(str(resource["cache_file"]))
        if cache_file.is_absolute() or ".." in cache_file.parts:
            raise ValueError(f"allowlist artifact {artifact_id}: cache_file must be a safe relative path")
        cache_payload = _read_json(source_root / cache_file)
        _require_fields(
            cache_payload,
            {"schema_version", "source", "source_release", "retrieved_at", "query", "record"},
            str(source_root / cache_file),
        )
        expected_schema_version = {"dbsnp": 1, "gnomad": 2}[source]
        if (
            cache_payload["source"] != source
            or cache_payload["schema_version"] != expected_schema_version
        ):
            raise ValueError(f"{source_root / cache_file}: cache source/schema mismatch")
        query = cache_payload["query"]
        if not isinstance(query, Mapping) or query.get("normalized_variant_id") != normalized:
            raise ValueError(f"{source_root / cache_file}: cache query identity mismatch")
        published_path = out_dir / cache_file
        cache_hash = _write_json(published_path, cache_payload, refuse_conflict=True)
        published: dict[str, Any] = {
            "cache_sha256": cache_hash,
            "cache_url": cache_file.as_posix(),
            "normalized_variant_id": normalized,
            "source": source,
        }
        if source == "gnomad":
            _require_fields(resource, {"dataset"}, f"{artifact_id} gnomad resource")
            dataset = str(resource["dataset"])
            if query.get("dataset") != dataset:
                raise ValueError(f"{source_root / cache_file}: gnomAD dataset mismatch")
            published["dataset"] = dataset
        else:
            _require_fields(resource, {"rsid"}, f"{artifact_id} dbsnp resource")
            rsid = str(resource["rsid"])
            if query.get("rsid") != rsid:
                raise ValueError(f"{source_root / cache_file}: dbSNP rsID mismatch")
            published["rsid"] = rsid
        resources.append(published)
        written.append(published_path)
    return resources, written


def export_catalog(
    source_root: Path,
    hbs_csv: Path,
    g6pd_csv: Path,
    allowlist_path: Path,
    out_dir: Path,
    hf_revision: str,
    requested_ids: Iterable[str] | None = None,
    afnd_frequencies_tsv: Path | None = None,
    afnd_populations_tsv: Path | None = None,
) -> list[Path]:
    """Export the requested allowlisted artifacts and return every written JSON path."""
    source_root = Path(source_root)
    out_dir = Path(out_dir)
    allowlist = _read_json(Path(allowlist_path))
    _require_fields(
        allowlist,
        {"schema_version", "hf_dataset", "hf_revision", "artifacts"},
        str(allowlist_path),
    )
    if allowlist["schema_version"] != SCHEMA_VERSION:
        raise ValueError(f"{allowlist_path}: unsupported schema_version")
    if allowlist["hf_revision"] != hf_revision:
        raise ValueError("requested Hugging Face revision does not match the allowlist")
    if not isinstance(allowlist["artifacts"], list):
        raise ValueError(f"{allowlist_path}: artifacts must be a list")

    by_id = {entry.get("id"): entry for entry in allowlist["artifacts"]}
    if None in by_id or len(by_id) != len(allowlist["artifacts"]):
        raise ValueError(f"{allowlist_path}: artifact ids must be present and unique")
    selected_ids = list(requested_ids) if requested_ids is not None else list(by_id)
    refused = set(selected_ids) - set(by_id)
    if refused:
        raise ValueError(f"requested artifacts are not allowlisted: {sorted(refused)}")

    catalog_metadata = _read_json(source_root / "catalog-metadata.json")
    _require_fields(
        catalog_metadata,
        {
            "artifact_version",
            "registry_version",
            "created_at",
            "discovery",
            "assumptions",
            "discovery_groups",
            "variants",
        },
        str(source_root / "catalog-metadata.json"),
    )
    discovery_groups = validate_discovery_groups(catalog_metadata["discovery_groups"])
    discovery_group_ids = {str(group["id"]) for group in discovery_groups}
    discovery_by_variant = catalog_metadata["discovery"]
    if not isinstance(discovery_by_variant, Mapping):
        raise ValueError("catalog discovery must be an object keyed by variant_id")
    out_dir.mkdir(parents=True, exist_ok=True)
    artifacts: list[dict[str, Any]] = []
    registry_versions: set[str] = set()
    written: list[Path] = []
    hf_dataset = str(allowlist["hf_dataset"])
    observation_cache: dict[str, tuple[pd.DataFrame, pd.DataFrame, str, str]] = {}

    for artifact_id in selected_ids:
        entry = by_id[artifact_id]
        _require_fields(
            entry,
            {"id", "variant_id", "artifact_dir", "observation_source"},
            f"allowlist artifact {artifact_id}",
        )
        artifact_name = str(entry["artifact_dir"])
        if Path(artifact_name).name != artifact_name:
            raise ValueError(f"allowlist artifact {artifact_id}: artifact_dir must be a basename")
        variant_id = str(entry["variant_id"])
        variants = catalog_metadata["variants"]
        if variant_id not in variants:
            raise ValueError(f"{variant_id}: missing catalog metadata")
        variant_metadata = variants[variant_id]
        _require_fields(
            variant_metadata,
            {"label", "entity_type", "measurement", "assumptions"},
            f"catalog variant {variant_id}",
        )
        if variant_id not in discovery_by_variant:
            raise ValueError(f"catalog variant {variant_id}: missing discovery metadata")
        discovery = validate_artifact_discovery(
            discovery_by_variant[variant_id],
            context=f"catalog variant {variant_id}",
            group_ids=discovery_group_ids,
        )
        registry_version = str(variant_metadata.get("registry_version", catalog_metadata["registry_version"]))
        if not registry_version:
            raise ValueError(f"catalog variant {variant_id}: registry_version must be non-empty")
        registry_versions.add(registry_version)

        manifest, cells = _validated_surface(
            source_root / "artifacts" / artifact_name,
            variant_id,
        )
        observation_source = entry["observation_source"]
        observation_rows: list[dict[str, Any]] | None = None
        if observation_source is not None:
            source_key = str(observation_source)
            if source_key not in observation_cache:
                observation_cache[source_key] = _load_observations(
                    source_key,
                    Path(hbs_csv),
                    Path(g6pd_csv),
                    afnd_frequencies_tsv,
                    afnd_populations_tsv,
                    str(manifest["data_version"]),
                )
            loaded, evidence, raw_source_url, _ = observation_cache[source_key]
            observations = loaded[loaded["variant_id"] == variant_id].reset_index(drop=True)
            if len(observations) != int(manifest["n_observations"]):
                raise ValueError(
                    f"{artifact_id}: manifest n_observations={manifest['n_observations']} but "
                    f"adapter retained {len(observations)}"
                )

        surface = _surface_payload(
            artifact_id,
            variant_metadata,
            manifest,
            cells,
            registry_version=registry_version,
            hf_dataset=hf_dataset,
            hf_revision=hf_revision,
        )
        if observation_source is not None:
            observation_rows = _serialize_observations(
                observations,
                evidence,
                source_url=raw_source_url,
                dataset=hf_dataset,
                revision=hf_revision,
            )

        surface_path = out_dir / f"{artifact_id}.surface.json"
        surface_hash = _write_json(surface_path, surface)
        manifest_path = out_dir / f"{artifact_id}.manifest.json"
        manifest_hash = _write_json(manifest_path, manifest)
        observations_path: Path | None = None
        observation_hash: str | None = None
        if observation_rows is not None:
            observations_path = out_dir / f"{artifact_id}.observations.json"
            observation_hash = _write_json(
                observations_path,
                {
                    "artifact": surface["artifact"],
                    "observations": observation_rows,
                    "schema_version": SCHEMA_VERSION,
                },
            )
        external_resources, external_paths = _external_resources(
            entry,
            artifact_id=artifact_id,
            variant_id=variant_id,
            entity_type=str(variant_metadata["entity_type"]),
            source_root=source_root,
            out_dir=out_dir,
        )
        written.extend(path for path in (surface_path, observations_path, manifest_path) if path is not None)
        written.extend(external_paths)
        artifacts.append(
            {
                **surface["artifact"],
                "assumptions": list(variant_metadata["assumptions"]),
                "correlation_range_km": float(manifest["correlation_range_km"]),
                "discovery": discovery,
                "downloads": {
                    "manifest": {
                        "label": "Artifact manifest",
                        "media_type": "application/json",
                        "sha256": manifest_hash,
                        "url": manifest_path.name,
                    },
                    "observations": (
                        {
                            "label": "Measured observations",
                            "media_type": "application/json",
                            "sha256": observation_hash,
                            "url": observations_path.name,
                        }
                        if observations_path is not None
                        else None
                    ),
                    "surface": {
                        "label": "Inferred surface",
                        "media_type": "application/json",
                        "sha256": surface_hash,
                        "url": surface_path.name,
                    },
                },
                "external_resources": external_resources,
                "likelihood": str(manifest["likelihood"]),
                "n_cells": int(manifest["n_cells"]),
                "n_observations": int(manifest["n_observations"]),
                "observations_available": observation_rows is not None,
                "observations_sha256": observation_hash,
                "observations_url": (observations_path.name if observations_path is not None else None),
                "support_counts": {str(key): int(value) for key, value in manifest["support_counts"].items()},
                "surface_sha256": surface_hash,
                "surface_url": surface_path.name,
            }
        )

    catalog = {
        "artifact_version": str(catalog_metadata["artifact_version"]),
        "artifacts": artifacts,
        "assumptions": list(catalog_metadata["assumptions"]),
        "context_sources": [
            {
                "id": "natural-earth-admin-0",
                "label": "Natural Earth country boundaries",
                "license": "public_domain",
                "revision": NATURAL_EARTH_REVISION,
                "source_url": NATURAL_EARTH_SOURCE,
                "url": "ne-50m-admin-0.geojson",
            },
            {
                "id": "natural-earth-populated-places",
                "label": "Natural Earth populated places",
                "license": "public_domain",
                "revision": NATURAL_EARTH_REVISION,
                "source_url": NATURAL_EARTH_PLACES_SOURCE,
                "url": "ne-50m-populated-places.json",
            },
        ],
        "created_at": str(catalog_metadata["created_at"]),
        "discovery_groups": discovery_groups,
        "hf_dataset": hf_dataset,
        "hf_revision": hf_revision,
        "registry_versions": sorted(registry_versions),
        "schema_version": SCHEMA_VERSION,
    }
    catalog_path = out_dir / "catalog.json"
    _write_json(catalog_path, catalog)
    written.append(catalog_path)
    return sorted(set(written))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument("--hbs-csv", type=Path, required=True)
    parser.add_argument("--g6pd-csv", type=Path, required=True)
    parser.add_argument("--afnd-frequencies", type=Path)
    parser.add_argument("--afnd-populations", type=Path)
    parser.add_argument("--allowlist", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    allowlist = _read_json(args.allowlist)
    paths = export_catalog(
        source_root=args.store,
        hbs_csv=args.hbs_csv,
        g6pd_csv=args.g6pd_csv,
        allowlist_path=args.allowlist,
        out_dir=args.out,
        hf_revision=str(allowlist.get("hf_revision", "")),
        afnd_frequencies_tsv=args.afnd_frequencies,
        afnd_populations_tsv=args.afnd_populations,
    )
    print(f"exported {len(paths) - 1} artifact payloads and catalog.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
