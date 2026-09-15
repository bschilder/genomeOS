"""Offline build-script integration tests (design §6; literature design §5.4)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from genomeos.observations.ingest import read_observations
from genomeos.registry.build import build_registry
from genomeos.registry.sources import hgdp
from scripts import build_registry as build_registry_script

FIXTURES = Path(__file__).parent / "fixtures"
LITERATURE = FIXTURES / "literature" / "promotable"
ROOT = Path(__file__).parents[1]


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    return subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True)


def _registry_command(
    hgdp_input: Path, out: Path, release_version: str = "0.1.0"
) -> list[str]:
    return [
        sys.executable,
        str(ROOT / "scripts" / "build_registry.py"),
        "--hgdp",
        str(hgdp_input),
        "--release-version",
        release_version,
        "--out",
        str(out),
    ]


def _write_registry(path: Path) -> None:
    from genomeos.registry.publication import publish_registry
    from genomeos.registry.release_contract import identify_input

    literature_populations = pd.read_csv(LITERATURE / "populations.tsv", sep="\t").replace(
        {float("nan"): pd.NA}
    )
    literature_populations["registry_version"] = "0.1.0"
    literature_aliases = pd.read_csv(LITERATURE / "aliases.tsv", sep="\t")
    populations, aliases = build_registry(
        [
            hgdp.load(FIXTURES / "hgdp_populations.tsv", "0.1.0"),
            (literature_populations, literature_aliases),
        ]
    )
    publish_registry(
        populations,
        aliases,
        inputs=(
            identify_input("source", "hgdp", (FIXTURES / "hgdp_populations.tsv").read_bytes()),
            identify_input(
                "source", "literature-populations", (LITERATURE / "populations.tsv").read_bytes()
            ),
            identify_input(
                "source", "literature-aliases", (LITERATURE / "aliases.tsv").read_bytes()
            ),
        ),
        release_version="0.1.0",
        out=path,
    )


def _read_registry(path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    from genomeos.registry.publication import read_registry

    return read_registry(path)


def _command(registry: Path, out: Path) -> list[str]:
    return [
        sys.executable,
        str(ROOT / "scripts" / "build_observations.py"),
        "--registry",
        str(registry),
        "--gnomad",
        str(FIXTURES / "gnomad_hgdp_1kg_freqs.tsv"),
        "--map-surveys",
        str(FIXTURES / "map_hbs_surveys.csv"),
        "--literature-evidence",
        str(LITERATURE / "evidence.tsv"),
        "--literature-field-evidence",
        str(LITERATURE / "field_evidence.tsv"),
        "--out",
        str(out),
    ]


def test_build_observations_promotes_and_retains_literature(tmp_path):
    registry = tmp_path / "registry"
    out = tmp_path / "observations"
    _write_registry(registry)

    completed = _run(_command(registry, out))
    assert completed.returncode == 0, completed.stderr

    observations = read_observations(out)
    literature = observations.loc[observations["variant_id"] == "chr2-135851076-G-A"]
    registry_populations, _ = _read_registry(registry)
    expected_geo = registry_populations.set_index("population_id").loc["literature-sami"]
    assert len(literature) == 1
    assert literature.iloc[0]["population_id"] == "literature-sami"
    assert literature.iloc[0]["lat"] == expected_geo["lat"]
    assert literature.iloc[0]["lon"] == expected_geo["lon"]
    assert literature.iloc[0]["radius_km"] == expected_geo["uncertainty_radius_km"]
    retained = pd.read_parquet(out / "literature_evidence.parquet")
    assert retained["source_record_id"].tolist() == literature["source_record_id"].tolist()
    assert "1/1 literature records promoted" in completed.stdout


def test_literature_build_options_are_all_or_neither(tmp_path):
    registry = tmp_path / "registry"
    _write_registry(registry)
    command = _command(registry, tmp_path / "observations")
    field_flag = command.index("--literature-field-evidence")
    del command[field_flag : field_flag + 2]

    completed = _run(command)

    assert completed.returncode != 0
    assert "must be supplied together" in completed.stderr


def test_registry_build_refuses_legacy_hgdp_input_without_creating_output(tmp_path):
    legacy = tmp_path / "legacy-hgdp.tsv"
    legacy.write_text(
        "population\tlatitude\tlongitude\tregion\nExample\t1\t2\tSynthetic\n",
        encoding="utf-8",
    )
    out = tmp_path / "registry"

    completed = _run(_registry_command(legacy, out))

    assert completed.returncode != 0
    assert "provenance" in completed.stderr
    assert "uncertainty_radius_km" in completed.stderr
    assert not out.exists()


def test_registry_build_preserves_explicit_hgdp_support_in_parquet(tmp_path):
    out = tmp_path / "registry"

    completed = _run(_registry_command(FIXTURES / "hgdp_populations.tsv", out))

    assert completed.returncode == 0, completed.stderr
    populations = pd.read_parquet(out / "populations.parquet")
    aliases = pd.read_parquet(out / "population_aliases.parquet")
    assert len(populations) == 6
    assert populations["uncertainty_radius_km"].tolist() == [
        2.5,
        5.0,
        25.0,
        75.0,
        125.0,
        250.0,
    ]
    assert populations["provenance"].tolist() == [
        "synthetic:hgdp-fixture-v1#row-1",
        "synthetic:hgdp-fixture-v1#row-2",
        "synthetic:hgdp-fixture-v1#row-3",
        "synthetic:hgdp-fixture-v1#row-4",
        "synthetic:hgdp-fixture-v1#row-5",
        "synthetic:hgdp-fixture-v1#row-6",
    ]
    assert aliases["label"].tolist() == [
        "Yoruba",
        "Biaka",
        "Han",
        "Sardinian",
        "Karitiana",
        "Papuan",
    ]


def test_registry_repeat_build_preserves_every_existing_byte(tmp_path):
    out = tmp_path / "registry"
    first = _run(_registry_command(FIXTURES / "hgdp_populations.tsv", out))
    assert first.returncode == 0, first.stderr
    before = {p.name: p.read_bytes() for p in out.iterdir() if p.is_file()}

    second = _run(_registry_command(FIXTURES / "hgdp_populations.tsv", out))

    assert second.returncode != 0
    assert {p.name: p.read_bytes() for p in out.iterdir() if p.is_file()} == before


def _write_synthetic_hgdp(
    path: Path,
    *,
    latitude: str = "1",
    radius: str = "2.5",
    provenance: str = "synthetic:registry-publication#one",
    population: str = "Fictional One",
) -> None:
    path.write_text(
        "population\tlatitude\tlongitude\tuncertainty_radius_km\tprovenance\n"
        f"{population}\t{latitude}\t2\t{radius}\t{provenance}\n",
        encoding="utf-8",
    )


def test_registry_build_requires_release_version(tmp_path):
    command = _registry_command(FIXTURES / "hgdp_populations.tsv", tmp_path / "registry")
    release_flag = command.index("--release-version")
    del command[release_flag : release_flag + 2]

    completed = _run(command)

    assert completed.returncode != 0
    assert "--release-version" in completed.stderr


def test_registry_build_validates_release_before_reading_source(tmp_path):
    out = tmp_path / "registry"

    completed = _run(_registry_command(tmp_path / "missing.tsv", out, "01.2.3"))

    assert completed.returncode != 0
    assert "normal semver" in completed.stderr
    assert not out.exists()


def test_registry_build_refuses_existing_output_before_reading_source(tmp_path):
    out = tmp_path / "registry"
    out.mkdir()
    sentinel = out / "sentinel"
    sentinel.write_bytes(b"preserve me")

    completed = _run(_registry_command(tmp_path / "missing.tsv", out))

    assert completed.returncode != 0
    assert "destination already exists" in completed.stderr
    assert sentinel.read_bytes() == b"preserve me"


def test_registry_build_is_reproducible_across_input_locations(tmp_path):
    first_source = tmp_path / "first.tsv"
    second_source = tmp_path / "relocated.tsv"
    _write_synthetic_hgdp(first_source)
    second_source.write_bytes(first_source.read_bytes())
    first_out = tmp_path / "registry-one"
    second_out = tmp_path / "registry-two"

    first = _run(_registry_command(first_source, first_out))
    second = _run(_registry_command(second_source, second_out))

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    first_populations, first_aliases = _read_registry(first_out)
    second_populations, second_aliases = _read_registry(second_out)
    assert first_populations["registry_version"].tolist() == second_populations[
        "registry_version"
    ].tolist()
    assert first_aliases.equals(second_aliases)
    assert (first_out / "manifest.json").read_bytes() == (
        second_out / "manifest.json"
    ).read_bytes()
    assert (first_out / "populations.parquet").read_bytes() == (
        second_out / "populations.parquet"
    ).read_bytes()
    assert (first_out / "population_aliases.parquet").read_bytes() == (
        second_out / "population_aliases.parquet"
    ).read_bytes()


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("latitude", "1.5"),
        ("radius", "3.5"),
        ("provenance", "synthetic:registry-publication#two"),
        ("population", "Fictional Two"),
    ],
)
def test_changed_hgdp_content_changes_identity_and_preserves_old_release(
    tmp_path, field, replacement
):
    source = tmp_path / "source.tsv"
    _write_synthetic_hgdp(source)
    old_out = tmp_path / "old"
    first = _run(_registry_command(source, old_out))
    assert first.returncode == 0, first.stderr
    before = {p.name: p.read_bytes() for p in old_out.iterdir() if p.is_file()}
    old_populations, _ = _read_registry(old_out)

    values = {field: replacement}
    _write_synthetic_hgdp(source, **values)
    new_out = tmp_path / "new"
    second = _run(_registry_command(source, new_out))

    assert second.returncode == 0, second.stderr
    new_populations, _ = _read_registry(new_out)
    assert old_populations.loc[0, "registry_version"] != new_populations.loc[0, "registry_version"]
    assert {p.name: p.read_bytes() for p in old_out.iterdir() if p.is_file()} == before
    _read_registry(old_out)


def test_changed_release_label_changes_identity_and_preserves_old_release(tmp_path):
    source = tmp_path / "source.tsv"
    _write_synthetic_hgdp(source)
    old_out = tmp_path / "old"
    first = _run(_registry_command(source, old_out, "1.0.0"))
    assert first.returncode == 0, first.stderr
    before = {p.name: p.read_bytes() for p in old_out.iterdir() if p.is_file()}
    old_populations, _ = _read_registry(old_out)

    new_out = tmp_path / "new"
    second = _run(_registry_command(source, new_out, "1.0.1"))

    assert second.returncode == 0, second.stderr
    new_populations, _ = _read_registry(new_out)
    assert old_populations.loc[0, "registry_version"] != new_populations.loc[0, "registry_version"]
    assert {p.name: p.read_bytes() for p in old_out.iterdir() if p.is_file()} == before
    _read_registry(old_out)


def test_registry_cli_snapshot_binds_bytes_consumed_by_adapter(tmp_path, monkeypatch):
    from genomeos.registry.release_contract import identify_input

    source = tmp_path / "source.tsv"
    _write_synthetic_hgdp(source)
    original_bytes = source.read_bytes()
    out = tmp_path / "registry"
    real_load = build_registry_script.hgdp.load

    def mutate_original_then_load(snapshot: Path, registry_version: str):
        _write_synthetic_hgdp(source, latitude="9")
        return real_load(snapshot, registry_version)

    monkeypatch.setattr(build_registry_script.hgdp, "load", mutate_original_then_load)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_registry.py",
            "--hgdp",
            str(source),
            "--release-version",
            "0.1.0",
            "--out",
            str(out),
        ],
    )

    build_registry_script.main()

    populations, _ = _read_registry(out)
    assert populations["lat"].tolist() == [1.0]
    manifest = (out / "manifest.json").read_text(encoding="utf-8")
    assert identify_input("source", "hgdp", original_bytes).sha256 in manifest


def test_registry_build_with_afnd_preserves_report_and_records_selected_input(tmp_path):
    from genomeos.registry.release_contract import RegistryManifest, identify_input

    out = tmp_path / "registry"
    command = _registry_command(FIXTURES / "hgdp_populations.tsv", out)
    command.extend(["--afnd", str(FIXTURES / "afnd_populations.tsv")])

    completed = _run(command)

    assert completed.returncode == 0, completed.stderr
    assert "7/9 populations retained" in completed.stdout
    manifest = RegistryManifest.model_validate_json((out / "manifest.json").read_bytes())
    records = {(item.kind, item.role): item for item in manifest.inputs}
    assert records[("source", "afnd")].sha256 == identify_input(
        "source", "afnd", (FIXTURES / "afnd_populations.tsv").read_bytes()
    ).sha256
    assert ("implementation", "genomeos/registry/sources/afnd.py") in records


def test_build_observations_refuses_legacy_registry_before_output(tmp_path):
    legacy = tmp_path / "legacy"
    populations, aliases = hgdp.load(FIXTURES / "hgdp_populations.tsv", "0.1.0")
    legacy.mkdir()
    populations.to_parquet(legacy / "populations.parquet", index=False)
    aliases.to_parquet(legacy / "population_aliases.parquet", index=False)
    out = tmp_path / "observations"

    completed = _run(_command(legacy, out))

    assert completed.returncode != 0
    assert "manifest" in completed.stderr
    assert not out.exists()


def test_build_observations_refuses_incomplete_registry_before_output(tmp_path):
    incomplete = tmp_path / "incomplete"
    incomplete.mkdir()
    (incomplete / "populations.parquet").write_bytes(b"incomplete")
    out = tmp_path / "observations"

    completed = _run(_command(incomplete, out))

    assert completed.returncode != 0
    assert "manifest" in completed.stderr
    assert not out.exists()
