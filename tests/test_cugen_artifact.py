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


def _empty_pair_summary() -> dict[str, object]:
    return {
        "requested_pairs": 0,
        "observed_pairs": 0,
        "invalid_pairs": 0,
        "maximum_absolute_r_error": 0.0,
        "maximum_absolute_r2_error": 0.0,
        "maximum_absolute_maf_error": 0.0,
        "passed": True,
    }


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


@pytest.mark.parametrize(
    "mutation",
    ["reference_count", "manifest_training_index", "validation_bool", "workspace", "execution_bool"],
)
def test_verifier_refuses_self_rehashed_nested_type_substitutions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    """Catch Python numeric equality admitting JSON values with substituted scalar types."""
    manifest_path, artifact = pilot_tests._run_pilot(tmp_path, monkeypatch)
    output = manifest_path.parent
    if mutation == "reference_count":
        path = output / "reference.json"
        document = json.loads(path.read_text(encoding="utf-8"))
        document["pairs"][0]["counts"][0] = True
        _write_json(path, document)
        pilot_tests._rewrite_manifest_hash(output, path.name)
    elif mutation == "manifest_training_index":
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["partition"]["training_indices"][0] = 4.0
        _write_json(manifest_path, manifest)
        _rewrite_manifest_identity(output)
    elif mutation == "validation_bool":
        path = output / "validation.json"
        document = json.loads(path.read_text(encoding="utf-8"))
        document["subset_calls_exact"] = 1
        _write_json(path, document)
        pilot_tests._rewrite_manifest_hash(output, path.name)
    elif mutation == "workspace":
        for name in ("reference.json", "validation.json"):
            path = output / name
            document = json.loads(path.read_text(encoding="utf-8"))
            document["workspace"]["host_bytes"] = float(document["workspace"]["host_bytes"])
            _write_json(path, document)
            pilot_tests._rewrite_manifest_hash(output, path.name)
    else:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["execution"]["requested"][0]["arguments"]["use_pinned"] = 0
        manifest["execution"]["executed"][0]["arguments"]["use_pinned"] = 0
        _write_json(manifest_path, manifest)
        _rewrite_manifest_identity(output)

    with pytest.raises((TypeError, ValueError), match="type|integer|boolean"):
        artifact.verify_cugen_pilot(output)


def test_verifier_refuses_self_rehashed_zero_requested_pair_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Catch completed-reader admission of a plan the execution adapter refuses as empty."""
    manifest_path, artifact = pilot_tests._run_pilot(tmp_path, monkeypatch)
    output = manifest_path.parent
    workspace_updates = {
        "host_pair_contingency_bytes": 0,
        "host_pair_metadata_output_bytes": 0,
        "host_bytes": 67_109_100,
        "device_pair_output_bytes": 0,
        "device_bytes": 134_218_988,
    }
    reference_path = output / "reference.json"
    reference = json.loads(reference_path.read_text(encoding="utf-8"))
    reference["window_bp"] = 0
    reference["pairs"] = []
    reference["workspace"].update(workspace_updates)
    _write_json(reference_path, reference)
    for name in ("cpu.tsv", "gpu.tsv"):
        path = output / name
        path.write_text(path.read_text(encoding="utf-8").splitlines()[0] + "\n", encoding="utf-8")
    validation_path = output / "validation.json"
    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    validation["cpu"] = _empty_pair_summary()
    validation["gpu"] = _empty_pair_summary()
    validation["workspace"].update(workspace_updates)
    _write_json(validation_path, validation)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["windows"]["window_bp"] = 0
    manifest["validation"] = {"cpu": _empty_pair_summary(), "gpu": _empty_pair_summary()}
    for call_set in ("requested", "executed"):
        for call in manifest["execution"][call_set][1:]:
            call["arguments"]["window_kb"] = 0.0
    _write_json(manifest_path, manifest)
    for name in ("reference.json", "cpu.tsv", "gpu.tsv", "validation.json"):
        pilot_tests._rewrite_manifest_hash(output, name)

    with pytest.raises(ValueError, match="no_requested_pairs"):
        artifact.verify_cugen_pilot(output)


def test_verifier_refuses_window_bp_that_cannot_round_trip_through_cugen_kb(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Catch completed-reader admission of a window the execution adapter cannot represent."""
    manifest_path, artifact = pilot_tests._run_pilot(tmp_path, monkeypatch)
    output = manifest_path.parent
    window_bp = 2**53 + 1
    reference_path = output / "reference.json"
    reference = json.loads(reference_path.read_text(encoding="utf-8"))
    reference["window_bp"] = window_bp
    _write_json(reference_path, reference)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["windows"]["window_bp"] = window_bp
    for call_set in ("requested", "executed"):
        for call in manifest["execution"][call_set][1:]:
            call["arguments"]["window_kb"] = window_bp / 1000.0
    _write_json(manifest_path, manifest)
    pilot_tests._rewrite_manifest_hash(output, "reference.json")

    with pytest.raises(ValueError, match="round-trip exactly"):
        artifact.verify_cugen_pilot(output)
