"""Verifiable immutable CuGen pilot artifacts (CuGen pilot design §7; Atlas §§4-5).

Completed bundles are checked from their snapshotted bytes without importing CuGen or CuPy.
Hashes establish bundle consistency, not source authenticity, residency, or data permissions.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from genomeos.validation.cugen_format import decode_cugen_bytes, estimate_ld_workspace
from genomeos.validation.ld_comparison import LD_OUTPUT_COLUMNS, reconcile_ld_output
from genomeos.validation.ld_contract import LDVariant, validate_training_selection
from genomeos.validation.ld_reference import (
    LDPair,
    VariantMoments,
    reference_ld,
    validate_ld_evidence,
    variant_moments,
)

DATA_FILES = (
    "source.cugen", "training.cugen", "reference.json", "cpu.tsv", "gpu.tsv",
    "validation.json", "runtime.json",
)
COMPLETE_MEMBERS = frozenset((*DATA_FILES, "manifest.json"))
_INTEGER_COLUMNS = frozenset({"CHR_A", "POS_A", "CHR_B", "POS_B", "N_OBS", "gidx_a", "gidx_b"})
_FLOAT_COLUMNS = frozenset({"MAF_A", "MAF_B", "R", "R2"})
_INTEGER_TOKEN = re.compile(r"(?:0|[1-9][0-9]*)")
_REVISION = re.compile(r"[0-9a-f]{40}")
_GENOMEOS_SOURCE_PATHS = frozenset(
    {
        "genomeos/validation/cugen_pilot.py",
        "genomeos/validation/cugen_artifact.py", "genomeos/validation/cugen_backend.py",
        "genomeos/validation/cugen_format.py", "genomeos/validation/cugen_source.json",
        "genomeos/validation/ld_comparison.py", "genomeos/validation/ld_contract.py",
        "genomeos/validation/ld_reference.py",
    }
)


def _canonical_json(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_exclusive(path: Path, content: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(content)


def _json_file(path: Path) -> Any:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        document: dict[str, Any] = {}
        for key, value in pairs:
            if key in document:
                raise ValueError(f"duplicate JSON field {key!r} in {path.name}")
            document[key] = value
        return document

    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream, object_pairs_hook=reject_duplicates)


def _bounded_cugen_member(path: Path) -> bytes:
    size = path.stat().st_size
    if size > 67_072:
        raise ValueError("CuGen artifact member exceeds the 67072-byte pilot maximum")
    with path.open("rb") as stream:
        content = stream.read(67_073)
    if len(content) != size or len(content) > 67_072:
        raise ValueError("CuGen artifact member changed or exceeded its bounded read")
    return content


def _scientific_identity(manifest: dict[str, Any]) -> str:
    identity = dict(manifest)
    identity.pop("scientific_identity_sha256", None)
    identity["files"] = {name: digest for name, digest in identity["files"].items() if name != "runtime.json"}
    return _sha256_bytes(_canonical_json(identity))


def _write_ld_tsv(path: Path, output: pd.DataFrame) -> None:
    if tuple(output.columns) != LD_OUTPUT_COLUMNS:
        raise ValueError("CuGen pair output columns do not match the admitted schema")
    with path.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
        writer.writerow(LD_OUTPUT_COLUMNS)
        for row in output.itertuples(index=False, name=None):
            writer.writerow(row)


def _parse_integer_token(token: str, column: str) -> int:
    if _INTEGER_TOKEN.fullmatch(token) is None:
        raise ValueError(f"{column} must use canonical base10 integer tokens")
    return int(token)


def _parse_float_token(token: str, column: str) -> float:
    if token != token.strip() or not token:
        raise ValueError(f"{column} must use a nonempty unpadded float token")
    try:
        value = float(token)
    except ValueError as error:
        raise ValueError(f"{column} must use a finite numeric token") from error
    limits = (-1.0, 1.0) if column == "R" else (0.0, 1.0)
    if column.startswith("MAF"):
        limits = (0.0, 0.5)
    if not math.isfinite(value) or not limits[0] <= value <= limits[1]:
        raise ValueError(f"{column} must be finite and in range")
    return value


def _read_ld_tsv(path: Path) -> pd.DataFrame:
    rows: list[list[object]] = []
    with path.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.reader(stream, delimiter="\t")
        try:
            header = tuple(next(reader))
        except StopIteration as error:
            raise ValueError("LD TSV is empty") from error
        if header != LD_OUTPUT_COLUMNS:
            raise ValueError("LD TSV header does not match the admitted schema")
        for line_number, raw in enumerate(reader, start=2):
            if len(raw) != len(LD_OUTPUT_COLUMNS):
                raise ValueError(f"LD TSV row {line_number} has the wrong field count")
            parsed: list[object] = []
            for column, token in zip(LD_OUTPUT_COLUMNS, raw, strict=True):
                if column in _INTEGER_COLUMNS:
                    parsed.append(_parse_integer_token(token, column))
                elif column in _FLOAT_COLUMNS:
                    parsed.append(_parse_float_token(token, column))
                else:
                    parsed.append(token)
            rows.append(parsed)
    return pd.DataFrame(rows, columns=LD_OUTPUT_COLUMNS)


def _pair_record(pair: LDPair) -> dict[str, Any]:
    record = asdict(pair)
    record["counts"] = list(pair.counts)
    return record


def _moment_record(moment: VariantMoments) -> dict[str, Any]:
    return asdict(moment)


def _variant_record(variant: LDVariant) -> dict[str, Any]:
    return asdict(variant)


def _partition_record(selection: object) -> dict[str, Any]:
    return asdict(selection)  # type: ignore[arg-type]


def write_completed_cugen_artifact(
    out: Path,
    *,
    variants: tuple[LDVariant, ...],
    selection: object,
    genome_build: str,
    ploidy: str,
    data_version: str,
    window_variants: int | None,
    window_bp: int | None,
    chunk_size: int,
    tile_size: int,
    workspace: object,
    moments: tuple[VariantMoments, ...],
    reference: tuple[LDPair, ...],
    cpu: pd.DataFrame,
    gpu: pd.DataFrame,
    cpu_validation: dict[str, Any],
    gpu_validation: dict[str, Any],
    sources: dict[str, Any],
    execution: dict[str, Any],
    runtime: dict[str, Any],
) -> Path:
    """Write the seven completed members and create the completion manifest last."""
    _require_data_version(data_version)
    _verify_runtime(runtime)
    reference_document = {
        "schema_version": 1, "genome_build": genome_build, "ploidy": ploidy,
        "data_version": data_version, "window_variants": window_variants,
        "window_bp": window_bp, "chunk_size": chunk_size, "tile_size": tile_size,
        "variants": [_variant_record(item) for item in variants],
        "partition": _partition_record(selection),
        "workspace": asdict(workspace),  # type: ignore[arg-type]
        "moments": [_moment_record(item) for item in moments],
        "pairs": [_pair_record(item) for item in reference],
    }
    _write_exclusive(out / "reference.json", _canonical_json(reference_document))
    _write_ld_tsv(out / "cpu.tsv", cpu)
    _write_ld_tsv(out / "gpu.tsv", gpu)
    validation = {
        "schema_version": 1, "subset_calls_exact": True,
        "cpu": cpu_validation, "gpu": gpu_validation,
        "workspace": asdict(workspace),  # type: ignore[arg-type]
    }
    _write_exclusive(out / "validation.json", _canonical_json(validation))
    _write_exclusive(out / "runtime.json", _canonical_json(runtime))
    files = {name: _sha256_file(out / name) for name in DATA_FILES}
    manifest: dict[str, Any] = {
        "schema_version": 1, "status": "completed", "evidence_kind": "synthetic_fixture",
        "publication_eligible": False, "joint_covariance_admitted": False,
        "genome_build": genome_build, "ploidy": ploidy, "data_version": data_version,
        "variants": reference_document["variants"], "partition": reference_document["partition"],
        "windows": {"window_variants": window_variants, "window_bp": window_bp},
        "chunk_size": chunk_size, "tile_size": tile_size,
        "input": {"sha256": files["source.cugen"]}, "sources": sources, "execution": execution,
        "validation": {"cpu": cpu_validation, "gpu": gpu_validation},
        "files": files,
    }
    manifest["scientific_identity_sha256"] = _scientific_identity(manifest)
    manifest_path = out / "manifest.json"
    _write_exclusive(manifest_path, _canonical_json(manifest))
    return manifest_path


def _require_keys(value: object, expected: set[str], name: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError(f"{name} does not have the exact admitted fields")
    return value


def _require_schema_version(document: dict[str, Any], name: str) -> None:
    if type(document.get("schema_version")) is not int or document["schema_version"] != 1:
        raise ValueError(f"{name} schema_version must be the integer 1")


def _require_data_version(value: object) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError("data_version must be a nonempty whitespace-trimmed string")


def _verify_runtime(runtime: object) -> None:
    document = _require_keys(
        runtime,
        {
            "schema_version", "subset_seconds", "cpu_ld_seconds",
            "gpu_ld_seconds", "pre_artifact_wall_seconds",
            "ld_timing_scope", "pre_artifact_timing_scope",
        },
        "runtime.json",
    )
    _require_schema_version(document, "runtime.json")
    if (
        document["ld_timing_scope"] != "unsynchronized_public_call_wall_intervals"
        or document["pre_artifact_timing_scope"]
        != "ends_before_artifact_serialization_and_completed_reader_verification"
    ):
        raise ValueError("runtime timing scopes do not match the admitted measurement contract")
    for name in ("subset_seconds", "cpu_ld_seconds", "gpu_ld_seconds", "pre_artifact_wall_seconds"):
        value = document[name]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(f"runtime {name} must be numeric")
        if not math.isfinite(float(value)) or float(value) < 0:
            raise ValueError(f"runtime {name} must be finite and nonnegative")


def _records_equal(actual: object, expected: object, name: str) -> None:
    if type(actual) is not type(expected):
        raise ValueError(f"stored {name} has a substituted JSON value type")
    if isinstance(actual, dict):
        if actual.keys() != expected.keys():  # type: ignore[union-attr]
            raise ValueError(f"stored {name} disagrees with independently recomputed evidence")
        for key in actual:
            _records_equal(actual[key], expected[key], f"{name}.{key}")  # type: ignore[index]
    elif isinstance(actual, list):
        if len(actual) != len(expected):  # type: ignore[arg-type]
            raise ValueError(f"stored {name} disagrees with independently recomputed evidence")
        for index, (actual_item, expected_item) in enumerate(zip(actual, expected, strict=True)):  # type: ignore[arg-type]
            _records_equal(actual_item, expected_item, f"{name}[{index}]")
    elif actual != expected:
        raise ValueError(f"stored {name} disagrees with independently recomputed evidence")


def verify_cugen_pilot(out: Path) -> dict[str, Any]:
    """Verify hashes, identities, bytes and numeric results without importing CuGen/CuPy."""
    root = Path(out)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("artifact root must be a real directory")
    entries = {entry.name: entry for entry in os.scandir(root)}
    if set(entries) != COMPLETE_MEMBERS:
        raise ValueError("artifact directory does not contain the exact admitted member set")
    if any(entry.is_symlink() or not entry.is_file(follow_symlinks=False) for entry in entries.values()):
        raise ValueError("artifact members must be regular files, never symlinks")

    manifest = _require_keys(
        _json_file(root / "manifest.json"),
        {
            "schema_version", "status", "evidence_kind", "publication_eligible",
            "joint_covariance_admitted", "genome_build", "ploidy", "data_version", "variants",
            "partition", "windows", "chunk_size", "tile_size", "input", "sources", "execution",
            "validation", "files", "scientific_identity_sha256",
        },
        "manifest",
    )
    _require_schema_version(manifest, "manifest")
    _require_data_version(manifest["data_version"])
    if (
        manifest["status"] != "completed"
        or manifest["evidence_kind"] != "synthetic_fixture"
        or manifest["publication_eligible"] is not False
        or manifest["joint_covariance_admitted"] is not False
    ):
        raise ValueError("manifest completion or evidence declarations are invalid")
    files = _require_keys(manifest["files"], set(DATA_FILES), "manifest files")
    for name in ("source.cugen", "training.cugen"):
        if (root / name).stat().st_size > 67_072:
            raise ValueError(f"{name} exceeds the 67072-byte pilot maximum")
    for name, digest in files.items():
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise ValueError("manifest file hashes must be lowercase SHA256 values")
        if _sha256_file(root / name) != digest:
            raise ValueError(f"artifact hash mismatch for {name}")
    if _scientific_identity(manifest) != manifest["scientific_identity_sha256"]:
        raise ValueError("scientific identity hash mismatch")
    if manifest["input"] != {"sha256": files["source.cugen"]}:
        raise ValueError("manifest input hash disagrees with the source snapshot")

    reference_document = _require_keys(
        _json_file(root / "reference.json"),
        {
            "schema_version", "genome_build", "ploidy", "data_version", "window_variants",
            "window_bp", "chunk_size", "tile_size", "variants", "partition", "workspace",
            "moments", "pairs",
        },
        "reference.json",
    )
    _require_schema_version(reference_document, "reference.json")
    _require_data_version(reference_document["data_version"])
    variants = tuple(LDVariant(**item) for item in reference_document["variants"])
    stored_moments = tuple(VariantMoments(**item) for item in reference_document["moments"])
    stored_pairs = tuple(
        LDPair(**{**item, "counts": tuple(item["counts"])})
        for item in reference_document["pairs"]
    )
    try:
        validate_ld_evidence(
            stored_pairs, variants, stored_moments,
            genome_build=reference_document["genome_build"],
            ploidy=reference_document["ploidy"],
        )
    except (TypeError, ValueError) as error:
        raise ValueError(f"stored LD reference disagrees with recomputed evidence: {error}") from error
    partition = _require_keys(
        reference_document["partition"],
        {"sample_ids", "training_indices", "training_ids", "held_out_ids", "excluded_ids"},
        "reference partition",
    )
    selection = validate_training_selection(
        partition["sample_ids"],
        partition["training_indices"],
        held_out_ids=partition["held_out_ids"],
        excluded_ids=partition["excluded_ids"],
    )
    if list(selection.training_ids) != partition["training_ids"]:
        raise ValueError("stored training_ids disagree with training_indices")
    identity_checks = {
        "genome_build": reference_document["genome_build"],
        "ploidy": reference_document["ploidy"],
        "data_version": reference_document["data_version"],
        "variants": reference_document["variants"],
        "partition": reference_document["partition"],
        "windows": {
            "window_variants": reference_document["window_variants"],
            "window_bp": reference_document["window_bp"],
        },
        "chunk_size": reference_document["chunk_size"],
        "tile_size": reference_document["tile_size"],
    }
    for name, value in identity_checks.items():
        _records_equal(manifest[name], value, f"manifest {name}")

    source = decode_cugen_bytes(
        _bounded_cugen_member(root / "source.cugen"),
        variants,
        expected_samples=len(selection.sample_ids),
    )
    training = decode_cugen_bytes(
        _bounded_cugen_member(root / "training.cugen"),
        variants,
        expected_samples=len(selection.training_ids),
    )
    expected_calls = source.calls[np.asarray(selection.training_indices, dtype=np.int64)]
    if not np.array_equal(training.calls, expected_calls):
        raise ValueError("training snapshot does not exactly match selected source calls")
    moments = variant_moments(training.calls)
    pairs = reference_ld(
        training.calls,
        variants,
        genome_build=manifest["genome_build"],
        ploidy=manifest["ploidy"],
        window_variants=reference_document["window_variants"],
        window_bp=reference_document["window_bp"],
    )
    if not pairs:
        raise ValueError("no_requested_pairs")
    window_bp = reference_document["window_bp"]
    window_kb = None if window_bp is None else window_bp / 1000.0
    if window_bp is not None and round(window_kb * 1000) != window_bp:
        raise ValueError("window_bp cannot round-trip exactly through CuGen window_kb")
    _records_equal(reference_document["moments"], [_moment_record(x) for x in moments], "moments")
    _records_equal(reference_document["pairs"], [_pair_record(x) for x in pairs], "LD reference")
    workspace = estimate_ld_workspace(
        source_variants=len(variants),
        source_samples=len(selection.sample_ids),
        training_samples=len(selection.training_ids),
        requested_pair_count=len(pairs),
        chunk_size=manifest["chunk_size"],
        tile_size=manifest["tile_size"],
    )
    _records_equal(reference_document["workspace"], asdict(workspace), "workspace estimate")
    cpu_summary = reconcile_ld_output(pairs, variants, moments, _read_ld_tsv(root / "cpu.tsv"))
    gpu_summary = reconcile_ld_output(pairs, variants, moments, _read_ld_tsv(root / "gpu.tsv"))
    validation = _require_keys(
        _json_file(root / "validation.json"),
        {"schema_version", "subset_calls_exact", "cpu", "gpu", "workspace"},
        "validation.json",
    )
    _require_schema_version(validation, "validation.json")
    expected_validation = {
        "schema_version": 1,
        "subset_calls_exact": True,
        "cpu": cpu_summary,
        "gpu": gpu_summary,
        "workspace": asdict(workspace),
    }
    _records_equal(validation, expected_validation, "validation summary")
    _records_equal(manifest["validation"], {"cpu": cpu_summary, "gpu": gpu_summary}, "manifest validation")
    _verify_runtime(_json_file(root / "runtime.json"))
    _verify_source_provenance(manifest["sources"])
    _verify_execution(manifest)
    return manifest


def _verify_hash_mapping(value: object, name: str) -> None:
    if not isinstance(value, dict) or not value:
        raise ValueError(f"{name} must be a nonempty source hash mapping")
    for path, digest in value.items():
        if (
            not isinstance(path, str)
            or not path
            or Path(path).is_absolute()
            or ".." in Path(path).parts
            or not isinstance(digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
        ):
            raise ValueError(f"{name} contains an invalid path or SHA256")


def _verify_source_provenance(value: object) -> None:
    sources = _require_keys(value, {"cugen", "genomeos"}, "manifest sources")
    cugen = _require_keys(
        sources["cugen"], {"repository", "revision", "allowlist_files", "imported_files"}, "CuGen source"
    )
    genomeos = _require_keys(
        sources["genomeos"], {"revision", "provenance", "imported_files"}, "genomeOS source"
    )
    if cugen["repository"] != "https://github.com/bschilder/cugen":
        raise ValueError("CuGen repository identity is invalid")
    if not isinstance(cugen["revision"], str) or _REVISION.fullmatch(cugen["revision"]) is None:
        raise ValueError("CuGen revision must be a full lowercase commit")
    if not isinstance(genomeos["revision"], str) or _REVISION.fullmatch(genomeos["revision"]) is None:
        raise ValueError("genomeOS revision must be a full lowercase commit")
    if genomeos["provenance"] not in ("supplied", "git_observed"):
        raise ValueError("genomeOS revision provenance is invalid")
    _verify_hash_mapping(cugen["allowlist_files"], "CuGen allowlist")
    _verify_hash_mapping(cugen["imported_files"], "CuGen imported files")
    _verify_hash_mapping(genomeos["imported_files"], "genomeOS imported files")
    allowlist = _json_file(Path(__file__).with_name("cugen_source.json"))
    expected_files = {item["path"]: item["sha256"] for item in allowlist["files"]}
    if (
        cugen["repository"] != allowlist["repository"]
        or cugen["revision"] != allowlist["revision"]
        or cugen["allowlist_files"] != expected_files
    ):
        raise ValueError("CuGen source provenance does not match the pinned allowlist")
    imported_paths = {"cugen/__init__.py", "cugen/write.py", "cugen/subset.py", "cugen/ld.py"}
    if set(cugen["imported_files"]) != imported_paths or any(
        cugen["imported_files"][path] != expected_files[path] for path in imported_paths
    ):
        raise ValueError("CuGen imported-source hashes do not match the pinned public paths")
    if set(genomeos["imported_files"]) != _GENOMEOS_SOURCE_PATHS:
        raise ValueError("genomeOS imported-source hash paths are incomplete")


def _verify_execution(manifest: dict[str, Any]) -> None:
    windows = manifest["windows"]
    if not isinstance(windows, dict) or set(windows) != {"window_variants", "window_bp"}:
        raise ValueError("manifest windows are invalid")
    window_bp = windows["window_bp"]
    window_kb = None if window_bp is None else window_bp / 1000.0
    common = {
        "stats": ["r", "r2"],
        "precision": "fp32",
        "sign_reference": "alt",
        "missing": "pairwise",
        "min_obs": 2,
        "maf_min": 0,
        "min_r2": 0,
        "output": None,
        "output_format": "pairs",
        "tile_size": manifest["tile_size"],
        "max_pairs": 2016,
        "verbose": False,
        "window": windows["window_variants"],
        "window_kb": window_kb,
        "annotation": "supplied_variant_identity",
    }
    expected = [
        {
            "path": "cugen.subset_cugen_file",
            "arguments": {
                "use_pinned": False,
                "chunk_size": manifest["chunk_size"],
                "verbose": False,
            },
        },
        {"path": "cugen.ld_matrix", "arguments": {**common, "backend": "numpy"}},
        {"path": "cugen.ld_matrix", "arguments": {**common, "backend": "gpu"}},
    ]
    _records_equal(manifest["execution"], {"requested": expected, "executed": expected}, "execution")
