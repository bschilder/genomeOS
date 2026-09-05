"""Build immutable P4 serving catalogs from published P2 surfaces (design §5, §6, §10)."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from pathlib import Path

import h3
import pandas as pd

from genomeos.artifacts.manifest import ArtifactFile, ArtifactManifest, VariantEntry

SURFACE_SCHEMA_VERSION = "surface-serving-v1"


def build_catalog(source: Path, metadata_path: Path, out: Path) -> Path:
    """Build one immutable local serving catalog from per-entity surface artifacts."""
    source, out = Path(source), Path(out)
    metadata = json.loads(Path(metadata_path).read_text(encoding="utf-8"))
    configured = metadata["variants"]
    source_manifests = sorted(source.glob("*/manifest.json"))
    if not source_manifests:
        raise ValueError(f"no published surface manifests found under {source}")
    if out.exists():
        raise FileExistsError(f"refusing to replace catalog: {out}")

    out.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{out.name}.", dir=out.parent))
    entries: list[VariantEntry] = []
    data_versions: set[str] = set()
    model_versions: set[str] = set()
    seen: set[str] = set()
    try:
        for manifest_path in source_manifests:
            source_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            variant_id = source_manifest["variant_id"]
            if variant_id not in configured:
                raise ValueError(f"metadata is missing an explicit entry for {variant_id}")
            if variant_id in seen:
                raise ValueError(f"duplicate published surface for {variant_id}")
            seen.add(variant_id)
            data_versions.add(source_manifest["data_version"])
            model_versions.add(source_manifest["model_version"])

            source_cells = manifest_path.parent / "cells.parquet"
            frame = pd.read_parquet(source_cells)
            expected_rows = int(source_manifest["n_cells"])
            if len(frame) != expected_rows:
                raise ValueError(
                    f"{variant_id} manifest declares {expected_rows} cells but contains {len(frame)}"
                )
            if set(frame["variant_id"]) != {variant_id}:
                raise ValueError(f"surface rows do not all belong to {variant_id}")

            resolution = int(source_manifest["resolution"])
            actual_resolutions = {h3.get_resolution(index) for index in frame["h3_index"]}
            if actual_resolutions != {resolution}:
                raise ValueError(
                    f"{variant_id} declares H3 resolution {resolution}, found {actual_resolutions}"
                )
            coordinates = [h3.cell_to_latlng(index) for index in frame["h3_index"]]
            serving = frame.assign(
                h3_resolution=resolution,
                lat=[coordinate[0] for coordinate in coordinates],
                lon=[coordinate[1] for coordinate in coordinates],
            )

            relative = Path("variants") / _slug(variant_id) / "surfaces.parquet"
            destination = staging / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            serving.to_parquet(destination, index=False)
            decision = configured[variant_id]
            entries.append(
                VariantEntry(
                    variant_id=variant_id,
                    label=decision["label"],
                    entity_type=decision["entity_type"],
                    measurement=decision["measurement"],
                    surface_eligible=decision["surface_eligible"],
                    assumptions=tuple(decision.get("assumptions", ())),
                    resolutions=(resolution,),
                    surface=ArtifactFile(
                        path=relative.as_posix(),
                        sha256=_sha256(destination),
                        row_count=len(serving),
                        schema_version=SURFACE_SCHEMA_VERSION,
                    ),
                )
            )

        unused = set(configured) - seen
        if unused:
            raise ValueError(f"metadata contains entries with no published surface: {sorted(unused)}")
        if len(data_versions) != 1 or len(model_versions) != 1:
            raise ValueError(
                "one catalog must pin exactly one data and model version; "
                f"found data={sorted(data_versions)}, model={sorted(model_versions)}"
            )

        manifest = ArtifactManifest(
            artifact_version=metadata["artifact_version"],
            registry_version=metadata["registry_version"],
            data_version=data_versions.pop(),
            model_version=model_versions.pop(),
            created_at=metadata["created_at"],
            assumptions=tuple(metadata.get("assumptions", ())),
            variants=tuple(sorted(entries, key=lambda entry: entry.variant_id)),
        )
        (staging / "manifest.json").write_text(
            json.dumps(manifest.model_dump(mode="json"), indent=2) + "\n", encoding="utf-8"
        )
        staging.rename(out)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return out


def _slug(identifier: str) -> str:
    return identifier.replace(":", "__")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
