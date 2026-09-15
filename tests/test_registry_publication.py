"""Immutable registry publication tests (publication design §§identity, storage, reader)."""

from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path

import pandas as pd
import pytest
from pandera.errors import SchemaError
from pydantic import ValidationError

from genomeos.registry.publication import publish_registry, read_registry
from genomeos.registry.release_contract import (
    RegistryFile,
    RegistryInput,
    RegistryManifest,
    RegistryRelease,
    encode_registry_manifest,
    identify_input,
    parse_registry_manifest,
    prepare_registry_release,
    registry_identity,
    validate_release_version,
    verify_registry_manifest,
)


def _tables(
    *,
    release_version: str = "1.2.3",
    latitude: float = 1.0,
    radius: float = 2.5,
    provenance: str = "synthetic:registry-publication#one",
    label: str = "Fictional One",
    notice: object = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    populations = pd.DataFrame(
        {
            "population_id": ["fictional-one"],
            "lat": [latitude],
            "lon": [2.0],
            "uncertainty_radius_km": [radius],
            "location_type": ["ancestral"],
            "provenance": [provenance],
            "biocultural_notice": [notice],
            "registry_version": [release_version],
        },
        index=[91],
    )
    aliases = pd.DataFrame(
        {
            "population_id": ["fictional-one"],
            "source": ["hgdp"],
            "label": [label],
        },
        index=[47],
    )
    return populations, aliases


def _source_input(payload: bytes = b"source bytes", role: str = "fixture") -> RegistryInput:
    return identify_input("source", role, payload)


def _publish(path: Path, **table_changes: object) -> RegistryManifest:
    populations, aliases = _tables(**table_changes)
    return publish_registry(
        populations,
        aliases,
        inputs=(_source_input(),),
        release_version="1.2.3",
        out=path,
    )


def _rewrite_manifest(path: Path, mutate) -> None:
    manifest_path = path / "manifest.json"
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    mutate(raw)
    manifest_path.write_text(json.dumps(raw), encoding="utf-8")


def test_identify_input_hashes_exact_bytes_and_returns_frozen_record():
    record = identify_input("source", "fixture", b"source bytes")

    assert record == RegistryInput(
        kind="source",
        role="fixture",
        sha256="4d4823794cbed3c4ee0bbc684c8f66e1dfd5afa6f078d494ce254ec5a4671753",
        size_bytes=12,
    )
    with pytest.raises(ValidationError):
        record.role = "changed"


@pytest.mark.parametrize(
    "values",
    [
        {"kind": "other", "role": "fixture", "sha256": "0" * 64, "size_bytes": 1},
        {"kind": "source", "role": " ", "sha256": "0" * 64, "size_bytes": 1},
        {"kind": "source", "role": "fixture", "sha256": "A" * 64, "size_bytes": 1},
        {"kind": "source", "role": "fixture", "sha256": "0" * 63, "size_bytes": 1},
        {"kind": "source", "role": "fixture", "sha256": "0" * 64, "size_bytes": True},
        {"kind": "source", "role": "fixture", "sha256": "0" * 64, "size_bytes": -1},
    ],
)
def test_registry_input_rejects_malformed_or_nonstrict_fields(values):
    with pytest.raises(ValidationError):
        RegistryInput.model_validate(values)


@pytest.mark.parametrize(
    "release_version",
    ["1.2", "01.2.3", "1.02.3", "1.2.03", " 1.2.3", "1.2.3-alpha", 123],
)
def test_registry_identity_rejects_invalid_release_versions(release_version):
    populations, aliases = _tables()

    with pytest.raises((TypeError, ValueError, ValidationError)):
        registry_identity(populations, aliases, (_source_input(),), release_version)


def test_registry_identity_has_exact_canonical_value_and_ignores_indexes():
    populations, aliases = _tables()

    identity = registry_identity(populations, aliases, (_source_input(),), "1.2.3")
    populations.index = [999]
    aliases.index = [888]

    assert identity == (
        "1.2.3+sha256.43fea5c5d79e6cb28eb81eca5de5d06dc0d58badced8e5bc1867a458795e944e"
    )
    assert registry_identity(populations, aliases, (_source_input(),), "1.2.3") == identity

    populations["registry_version"] = "an-ignored-noncircular-value"
    assert registry_identity(populations, aliases, (_source_input(),), "1.2.3") == identity


@pytest.mark.parametrize(
    "change",
    [
        {"latitude": 1.5},
        {"radius": 3.5},
        {"provenance": "synthetic:registry-publication#two"},
        {"label": "Fictional Two"},
    ],
)
def test_registry_identity_changes_with_each_logical_claim(change):
    populations, aliases = _tables()
    changed_populations, changed_aliases = _tables(**change)

    original = registry_identity(populations, aliases, (_source_input(),), "1.2.3")
    changed = registry_identity(
        changed_populations, changed_aliases, (_source_input(),), "1.2.3"
    )

    assert changed != original


def test_registry_identity_preserves_row_order_and_binds_inputs():
    first_populations, first_aliases = _tables()
    second_populations, second_aliases = _tables(
        provenance="synthetic:registry-publication#two",
        label="Fictional Two",
    )
    second_populations["population_id"] = "fictional-two"
    second_aliases["population_id"] = "fictional-two"
    populations = pd.concat([first_populations, second_populations], ignore_index=True)
    aliases = pd.concat([first_aliases, second_aliases], ignore_index=True)

    original = registry_identity(populations, aliases, (_source_input(),), "1.2.3")

    assert registry_identity(
        populations.iloc[::-1], aliases.iloc[::-1], (_source_input(),), "1.2.3"
    ) != original
    assert registry_identity(
        populations,
        aliases,
        (_source_input(b"changed source bytes"),),
        "1.2.3",
    ) != original
    assert registry_identity(populations, aliases, (_source_input(),), "1.2.4") != original


def test_registry_identity_rejects_duplicate_inputs_and_requires_a_source():
    populations, aliases = _tables()
    source = _source_input()
    implementation = identify_input("implementation", "example.py", b"code")

    with pytest.raises(ValueError, match="duplicate"):
        registry_identity(populations, aliases, (source, source), "1.2.3")
    with pytest.raises(ValueError, match="source"):
        registry_identity(populations, aliases, (implementation,), "1.2.3")


def test_prepare_registry_release_returns_checked_identity_without_mutating_callers():
    populations, aliases = _tables()
    populations_before = populations.copy(deep=True)
    aliases_before = aliases.copy(deep=True)

    release = prepare_registry_release(
        populations,
        aliases,
        (_source_input(),),
        "1.2.3",
    )

    assert isinstance(release, RegistryRelease)
    assert release.registry_version == registry_identity(
        populations, aliases, (_source_input(),), "1.2.3"
    )
    assert release.populations["registry_version"].tolist() == [release.registry_version]
    assert release.aliases.to_dict("records") == aliases.to_dict("records")
    assert populations.equals(populations_before)
    assert aliases.equals(aliases_before)


def test_prepare_registry_release_refuses_wrong_incoming_version_without_mutation():
    populations, aliases = _tables(release_version="9.9.9")
    populations_before = populations.copy(deep=True)

    with pytest.raises(ValueError, match="incoming population registry_version"):
        prepare_registry_release(populations, aliases, (_source_input(),), "1.2.3")

    assert populations.equals(populations_before)


def test_verify_registry_manifest_checks_public_release_content_boundary():
    populations, aliases = _tables()
    release = prepare_registry_release(populations, aliases, (_source_input(),), "1.2.3")
    manifest = RegistryManifest(
        schema_version="registry-publication-v1",
        release_version=release.release_version,
        registry_version=release.registry_version,
        inputs=release.inputs,
        files=(
            RegistryFile(
                path="populations.parquet",
                sha256="0" * 64,
                size_bytes=1,
                row_count=1,
                logical_sha256=release.populations_logical_sha256,
            ),
            RegistryFile(
                path="population_aliases.parquet",
                sha256="1" * 64,
                size_bytes=1,
                row_count=1,
                logical_sha256=release.aliases_logical_sha256,
            ),
        ),
        software_versions={
            "python": "3.12",
            "pandas": "2.3",
            "pyarrow": "21",
            "pandera": "0.26",
        },
    )

    verified = verify_registry_manifest(release.populations, release.aliases, manifest)
    changed = release.populations.copy()
    changed.loc[0, "lat"] = 1.5

    assert verified.registry_version == release.registry_version
    with pytest.raises(ValueError, match="logical hash"):
        verify_registry_manifest(changed, release.aliases, manifest)


def test_manifest_encoding_and_parsing_are_strict_public_operations():
    populations, aliases = _tables()
    release = prepare_registry_release(populations, aliases, (_source_input(),), "1.2.3")
    files = (
        RegistryFile(
            path="populations.parquet",
            sha256="0" * 64,
            size_bytes=1,
            row_count=1,
            logical_sha256=release.populations_logical_sha256,
        ),
        RegistryFile(
            path="population_aliases.parquet",
            sha256="1" * 64,
            size_bytes=1,
            row_count=1,
            logical_sha256=release.aliases_logical_sha256,
        ),
    )
    manifest = RegistryManifest(
        schema_version="registry-publication-v1",
        release_version=release.release_version,
        registry_version=release.registry_version,
        inputs=release.inputs,
        files=files,
        software_versions={
            "python": "3.12",
            "pandas": "2.3",
            "pyarrow": "21",
            "pandera": "0.26",
        },
    )

    assert parse_registry_manifest(encode_registry_manifest(manifest)) == manifest
    with pytest.raises(ValueError, match="duplicate JSON key"):
        parse_registry_manifest(
            b'{"schema_version":"registry-publication-v1","schema_version":"other"}'
        )


def test_validate_release_version_is_the_strict_public_cli_boundary():
    assert validate_release_version("1.2.3") == "1.2.3"
    with pytest.raises(ValueError, match="normal semver"):
        validate_release_version("01.2.3")


def test_manifest_rejects_invalid_file_set_versions_and_software():
    file_record = RegistryFile(
        path="populations.parquet",
        sha256="0" * 64,
        size_bytes=1,
        row_count=1,
        logical_sha256="1" * 64,
    )
    values = {
        "schema_version": "registry-publication-v1",
        "release_version": "1.2.3",
        "registry_version": "1.2.3+sha256." + "2" * 64,
        "inputs": (_source_input(),),
        "files": (file_record, file_record),
        "software_versions": {
            "python": "3.12",
            "pandas": "2.3",
            "pyarrow": "21",
            "pandera": "0.26",
        },
    }

    with pytest.raises(ValidationError, match="file"):
        RegistryManifest.model_validate(values)
    values["files"] = (
        file_record,
        file_record.model_copy(update={"path": "population_aliases.parquet"}),
    )
    values["registry_version"] = "1.2.4+sha256." + "2" * 64
    with pytest.raises(ValidationError, match="registry_version"):
        RegistryManifest.model_validate(values)
    values["registry_version"] = "1.2.3+sha256." + "2" * 64
    values["software_versions"] = {"python": "3.12"}
    with pytest.raises(ValidationError, match="software"):
        RegistryManifest.model_validate(values)


def test_manifest_accepts_each_fixed_file_exactly_once_in_either_order():
    populations = RegistryFile(
        path="populations.parquet",
        sha256="0" * 64,
        size_bytes=1,
        row_count=1,
        logical_sha256="1" * 64,
    )
    aliases = populations.model_copy(update={"path": "population_aliases.parquet"})

    manifest = RegistryManifest(
        schema_version="registry-publication-v1",
        release_version="1.2.3",
        registry_version="1.2.3+sha256." + "2" * 64,
        inputs=(_source_input(),),
        files=(aliases, populations),
        software_versions={
            "python": "3.12",
            "pandas": "2.3",
            "pyarrow": "21",
            "pandera": "0.26",
        },
    )

    assert {record.path for record in manifest.files} == {
        "populations.parquet",
        "population_aliases.parquet",
    }


@pytest.mark.parametrize("field", ["size_bytes", "row_count"])
@pytest.mark.parametrize("value", [True, -1, "1"])
def test_registry_file_rejects_nonstrict_or_negative_counts(field, value):
    values = {
        "path": "populations.parquet",
        "sha256": "0" * 64,
        "size_bytes": 1,
        "row_count": 1,
        "logical_sha256": "1" * 64,
    }
    values[field] = value

    with pytest.raises(ValidationError):
        RegistryFile.model_validate(values)


def test_publication_round_trips_exact_tables_and_records_runtime(tmp_path):
    populations, aliases = _tables(notice=None)
    populations_before = populations.copy(deep=True)
    aliases_before = aliases.copy(deep=True)

    manifest = publish_registry(
        populations,
        aliases,
        inputs=(_source_input(),),
        release_version="1.2.3",
        out=tmp_path / "registry",
    )
    restored_populations, restored_aliases = read_registry(tmp_path / "registry")

    assert populations.equals(populations_before)
    assert aliases.equals(aliases_before)
    restored = restored_populations.drop(columns="registry_version").iloc[0]
    assert restored.drop(labels="biocultural_notice").to_dict() == {
        "population_id": "fictional-one",
        "lat": 1.0,
        "lon": 2.0,
        "uncertainty_radius_km": 2.5,
        "location_type": "ancestral",
        "provenance": "synthetic:registry-publication#one",
    }
    assert pd.isna(restored["biocultural_notice"])
    assert restored_aliases.to_dict("records") == [
        {"population_id": "fictional-one", "source": "hgdp", "label": "Fictional One"}
    ]
    assert restored_populations["registry_version"].tolist() == [manifest.registry_version]
    assert set(manifest.software_versions) == {"python", "pandas", "pyarrow", "pandera"}
    assert {(item.kind, item.role) for item in manifest.inputs} >= {
        ("source", "fixture"),
        ("implementation", "genomeos/registry/release_contract.py"),
        ("implementation", "genomeos/registry/publication.py"),
        ("implementation", "genomeos/registry/build.py"),
        ("implementation", "genomeos/registry/schema.py"),
    }
    assert {item.path for item in manifest.files} == {
        "populations.parquet",
        "population_aliases.parquet",
    }
    for record in manifest.files:
        payload = (tmp_path / "registry" / record.path).read_bytes()
        assert record.sha256 == hashlib.sha256(payload).hexdigest()
        assert record.size_bytes == len(payload)
        assert record.row_count == 1
    assert not (tmp_path / "registry" / ".manifest.pending").exists()


@pytest.mark.parametrize("target_kind", ["directory", "file", "symlink", "dangling-symlink"])
def test_publication_refuses_every_preexisting_destination_without_modifying_it(
    tmp_path, target_kind
):
    out = tmp_path / "registry"
    target = tmp_path / "target"
    if target_kind == "directory":
        out.mkdir()
    elif target_kind == "file":
        out.write_bytes(b"existing file")
    elif target_kind == "symlink":
        target.mkdir()
        out.symlink_to(target, target_is_directory=True)
    else:
        out.symlink_to(target, target_is_directory=True)
    before = out.lstat()

    with pytest.raises(FileExistsError):
        _publish(out)

    assert out.lstat() == before
    if target_kind == "file":
        assert out.read_bytes() == b"existing file"


@pytest.mark.parametrize(
    "change",
    [
        {"release_version": "9.9.9"},
        {"latitude": float("inf")},
        {"radius": float("nan")},
    ],
)
def test_publication_validates_before_claiming_output(tmp_path, change):
    populations, aliases = _tables(**change)
    out = tmp_path / "registry"

    with pytest.raises((ValueError, SchemaError)):
        publish_registry(
            populations,
            aliases,
            inputs=(_source_input(),),
            release_version="1.2.3",
            out=out,
        )

    assert not out.exists()


def test_second_parquet_failure_leaves_incomplete_directory(monkeypatch, tmp_path):
    from genomeos.registry import publication

    real_write = publication._write_parquet_file

    def fail_second(frame: pd.DataFrame, path: Path) -> bytes:
        if path.name == "population_aliases.parquet":
            raise OSError("injected second parquet failure")
        return real_write(frame, path)

    monkeypatch.setattr(publication, "_write_parquet_file", fail_second)
    out = tmp_path / "registry"

    with pytest.raises(OSError, match="second parquet"):
        _publish(out)

    assert out.is_dir()
    assert (out / "populations.parquet").is_file()
    assert not (out / "manifest.json").exists()
    with pytest.raises(ValueError, match="manifest"):
        read_registry(out)


def test_pre_manifest_failure_leaves_both_data_files_incomplete(monkeypatch, tmp_path):
    from genomeos.registry import publication

    def fail_manifest(path: Path, payload: bytes) -> None:
        raise OSError("injected pending manifest failure")

    monkeypatch.setattr(publication, "_write_pending_manifest", fail_manifest)
    out = tmp_path / "registry"

    with pytest.raises(OSError, match="pending manifest"):
        _publish(out)

    assert (out / "populations.parquet").is_file()
    assert (out / "population_aliases.parquet").is_file()
    assert not (out / "manifest.json").exists()
    with pytest.raises(ValueError, match="manifest"):
        read_registry(out)


def test_manifest_commit_failure_leaves_pending_bytes_but_no_completion_marker(
    monkeypatch, tmp_path
):
    from genomeos.registry import publication

    def fail_link(source: Path, destination: Path) -> None:
        raise OSError("injected manifest commit failure")

    monkeypatch.setattr(publication.os, "link", fail_link)
    out = tmp_path / "registry"

    with pytest.raises(OSError, match="manifest commit"):
        _publish(out)

    assert (out / ".manifest.pending").is_file()
    assert not (out / "manifest.json").exists()
    with pytest.raises(ValueError, match="manifest"):
        read_registry(out)


def test_post_commit_cleanup_failure_preserves_readable_release(monkeypatch, tmp_path):
    from genomeos.registry import publication

    def fail_cleanup(path: Path) -> None:
        raise OSError("injected cleanup failure")

    monkeypatch.setattr(publication, "_remove_pending_manifest", fail_cleanup)
    out = tmp_path / "registry"

    with pytest.raises(RuntimeError, match="may already be committed"):
        _publish(out)

    assert (out / "manifest.json").is_file()
    populations, _ = read_registry(out)
    assert len(populations) == 1


def test_two_publishers_race_for_one_exclusive_directory(monkeypatch, tmp_path):
    from genomeos.registry import publication

    barrier = threading.Barrier(2)
    real_claim = publication._claim_output_directory

    def coordinated_claim(path: Path) -> None:
        barrier.wait(timeout=5)
        real_claim(path)

    monkeypatch.setattr(publication, "_claim_output_directory", coordinated_claim)
    out = tmp_path / "registry"
    results: list[object] = []

    def run() -> None:
        try:
            results.append(_publish(out))
        except BaseException as exc:
            results.append(exc)

    workers = [threading.Thread(target=run), threading.Thread(target=run)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=10)

    assert sum(isinstance(result, RegistryManifest) for result in results) == 1
    assert sum(isinstance(result, FileExistsError) for result in results) == 1
    populations, aliases = read_registry(out)
    assert len(populations) == len(aliases) == 1


def test_reader_refuses_missing_completion_manifest(tmp_path):
    incomplete = tmp_path / "incomplete"
    incomplete.mkdir()
    (incomplete / "populations.parquet").write_bytes(b"incomplete")

    with pytest.raises(ValueError, match="manifest"):
        read_registry(incomplete)


@pytest.mark.parametrize("filename", ["populations.parquet", "population_aliases.parquet"])
def test_reader_refuses_tampered_or_truncated_parquet(tmp_path, filename):
    out = tmp_path / "registry"
    _publish(out)
    path = out / filename
    path.write_bytes(path.read_bytes()[:-1])

    with pytest.raises(ValueError, match="hash|size"):
        read_registry(out)


def test_reader_refuses_changed_logical_data_even_with_updated_outer_hash(tmp_path):
    out = tmp_path / "registry"
    _publish(out)
    path = out / "populations.parquet"
    populations = pd.read_parquet(path)
    populations.loc[0, "lat"] = 1.5
    populations.to_parquet(path, index=False)
    payload = path.read_bytes()

    def update_outer_hash(manifest: dict[str, object]) -> None:
        record = next(item for item in manifest["files"] if item["path"] == path.name)
        record["sha256"] = hashlib.sha256(payload).hexdigest()
        record["size_bytes"] = len(payload)

    _rewrite_manifest(out, update_outer_hash)

    with pytest.raises(ValueError, match="logical|identity"):
        read_registry(out)


def test_reader_refuses_wrong_embedded_registry_version_with_updated_outer_hash(tmp_path):
    out = tmp_path / "registry"
    _publish(out)
    path = out / "populations.parquet"
    populations = pd.read_parquet(path)
    populations.loc[0, "registry_version"] = "1.2.3+sha256." + "f" * 64
    populations.to_parquet(path, index=False)
    payload = path.read_bytes()

    def update_outer_hash(manifest: dict[str, object]) -> None:
        record = next(item for item in manifest["files"] if item["path"] == path.name)
        record["sha256"] = hashlib.sha256(payload).hexdigest()
        record["size_bytes"] = len(payload)

    _rewrite_manifest(out, update_outer_hash)

    with pytest.raises(ValueError, match="embedded registry_version"):
        read_registry(out)


def test_reader_refuses_nonfinite_table_value_with_updated_outer_hash(tmp_path):
    out = tmp_path / "registry"
    _publish(out)
    path = out / "populations.parquet"
    populations = pd.read_parquet(path)
    populations.loc[0, "lat"] = float("inf")
    populations.to_parquet(path, index=False)
    payload = path.read_bytes()

    def update_outer_hash(manifest: dict[str, object]) -> None:
        record = next(item for item in manifest["files"] if item["path"] == path.name)
        record["sha256"] = hashlib.sha256(payload).hexdigest()
        record["size_bytes"] = len(payload)

    _rewrite_manifest(out, update_outer_hash)

    with pytest.raises(ValueError, match="table contract"):
        read_registry(out)


@pytest.mark.parametrize(
    ("manifest_bytes", "message"),
    [
        (b'{"schema_version":"registry-publication-v1","schema_version":"other"}', "duplicate"),
        (b'{"schema_version":NaN}', "nonfinite"),
        (b"not-json", "manifest"),
    ],
)
def test_reader_refuses_malformed_manifest_json(tmp_path, manifest_bytes, message):
    out = tmp_path / "registry"
    _publish(out)
    (out / "manifest.json").write_bytes(manifest_bytes)

    with pytest.raises(ValueError, match=message):
        read_registry(out)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda raw: raw.update({"unknown": "field"}),
        lambda raw: raw.update({"schema_version": "registry-publication-v2"}),
        lambda raw: raw["files"].append(raw["files"][0]),
        lambda raw: raw["inputs"].append(raw["inputs"][0]),
        lambda raw: raw["files"][0].update({"path": "../outside.parquet"}),
        lambda raw: raw.update({"registry_version": "1.2.3+sha256." + "A" * 64}),
        lambda raw: raw["files"][0].update({"size_bytes": True}),
    ],
)
def test_reader_refuses_invalid_manifest_contract(tmp_path, mutate):
    out = tmp_path / "registry"
    _publish(out)
    _rewrite_manifest(out, mutate)

    with pytest.raises(ValueError, match="manifest"):
        read_registry(out)


@pytest.mark.parametrize(
    "filename", ["manifest.json", "populations.parquet", "population_aliases.parquet"]
)
def test_reader_refuses_symlinked_publication_files(tmp_path, filename):
    out = tmp_path / "registry"
    _publish(out)
    path = out / filename
    target = tmp_path / f"real-{filename}"
    path.rename(target)
    path.symlink_to(target)

    with pytest.raises(ValueError, match="regular non-symlink"):
        read_registry(out)


def test_reader_refuses_row_count_mismatch(tmp_path):
    out = tmp_path / "registry"
    _publish(out)

    def change_count(raw: dict[str, object]) -> None:
        raw["files"][0]["row_count"] = 2

    _rewrite_manifest(out, change_count)

    with pytest.raises(ValueError, match="row count"):
        read_registry(out)


def test_reader_uses_recorded_inputs_instead_of_current_implementation(monkeypatch, tmp_path):
    from genomeos.registry import publication

    out = tmp_path / "registry"
    manifest = _publish(out)
    monkeypatch.setattr(
        publication,
        "_core_implementation_inputs",
        lambda: (identify_input("implementation", "changed.py", b"changed"),),
    )

    populations, _ = read_registry(out)

    assert populations["registry_version"].tolist() == [manifest.registry_version]


def test_empty_schema_valid_tables_publish_and_round_trip(tmp_path):
    populations, aliases = _tables()
    populations = populations.iloc[0:0]
    aliases = aliases.iloc[0:0]

    manifest = publish_registry(
        populations,
        aliases,
        inputs=(_source_input(),),
        release_version="1.2.3",
        out=tmp_path / "empty",
    )
    restored_populations, restored_aliases = read_registry(tmp_path / "empty")

    assert manifest.registry_version.startswith("1.2.3+sha256.")
    assert restored_populations.empty
    assert restored_aliases.empty
