"""Focused scalar and runtime checks for CuGen pilot artifacts (design §§7-8)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import test_cugen_pilot as pilot_tests


def _write_json(path: Path, document: object) -> None:
    path.write_text(
        json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def _rewrite_manifest_identity(output: Path) -> None:
    manifest_path = output / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    identity = json.loads(json.dumps(manifest))
    identity.pop("scientific_identity_sha256", None)
    identity["files"].pop("runtime.json")
    payload = (json.dumps(identity, sort_keys=True, separators=(",", ":")) + "\n").encode()
    manifest["scientific_identity_sha256"] = hashlib.sha256(payload).hexdigest()
    _write_json(manifest_path, manifest)


@pytest.mark.parametrize("name", ["manifest.json", "reference.json", "runtime.json", "validation.json"])
def test_verifier_refuses_boolean_schema_versions_after_self_consistent_rehash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    """Catch JSON true passing an integer schema-version equality check."""
    manifest_path, artifact = pilot_tests._run_pilot(tmp_path, monkeypatch)
    output = manifest_path.parent
    target = output / name
    document = json.loads(target.read_text(encoding="utf-8"))
    document["schema_version"] = True
    _write_json(target, document)
    if name == "manifest.json":
        _rewrite_manifest_identity(output)
    else:
        pilot_tests._rewrite_manifest_hash(output, name)

    with pytest.raises((TypeError, ValueError), match="schema_version"):
        artifact.verify_cugen_pilot(output)


@pytest.mark.parametrize("data_version", ["", " padded", True])
def test_verifier_reapplies_data_version_rule_after_self_consistent_rehash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, data_version: object
) -> None:
    """Catch a completed reader accepting an identity the run boundary refuses."""
    manifest_path, artifact = pilot_tests._run_pilot(tmp_path, monkeypatch)
    output = manifest_path.parent
    reference_path = output / "reference.json"
    reference = json.loads(reference_path.read_text(encoding="utf-8"))
    reference["data_version"] = data_version
    _write_json(reference_path, reference)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["data_version"] = data_version
    _write_json(manifest_path, manifest)
    pilot_tests._rewrite_manifest_hash(output, "reference.json")

    with pytest.raises((TypeError, ValueError), match="data_version"):
        artifact.verify_cugen_pilot(output)


def test_writer_labels_pre_artifact_and_unsynchronized_public_call_intervals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Catch preliminary host-wall measurements being named as full-workflow or device timing."""
    manifest_path, _artifact = pilot_tests._run_pilot(tmp_path, monkeypatch)
    runtime = json.loads((manifest_path.parent / "runtime.json").read_text(encoding="utf-8"))

    assert set(runtime) == {
        "schema_version",
        "subset_seconds",
        "cpu_ld_seconds",
        "gpu_ld_seconds",
        "pre_artifact_wall_seconds",
        "ld_timing_scope",
        "pre_artifact_timing_scope",
    }
    assert runtime["ld_timing_scope"] == "unsynchronized_public_call_wall_intervals"
    assert runtime["pre_artifact_timing_scope"] == (
        "ends_before_artifact_serialization_and_completed_reader_verification"
    )
