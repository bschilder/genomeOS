"""Offline build-script integration tests (design §6; literature design §5.4)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd

from genomeos.observations.ingest import read_observations
from genomeos.registry.build import build_registry
from genomeos.registry.sources import hgdp

FIXTURES = Path(__file__).parent / "fixtures"
LITERATURE = FIXTURES / "literature" / "promotable"
ROOT = Path(__file__).parents[1]


def _write_registry(path: Path) -> None:
    literature_populations = pd.read_csv(LITERATURE / "populations.tsv", sep="\t").replace(
        {float("nan"): pd.NA}
    )
    literature_aliases = pd.read_csv(LITERATURE / "aliases.tsv", sep="\t")
    populations, aliases = build_registry(
        [
            hgdp.load(FIXTURES / "hgdp_populations.tsv", "0.1.0"),
            (literature_populations, literature_aliases),
        ]
    )
    path.mkdir()
    populations.to_parquet(path / "populations.parquet", index=False)
    aliases.to_parquet(path / "population_aliases.parquet", index=False)


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

    completed = subprocess.run(
        _command(registry, out), cwd=ROOT, check=True, capture_output=True, text=True
    )

    observations = read_observations(out)
    literature = observations.loc[observations["variant_id"] == "chr2-135851076-G-A"]
    expected_geo = pd.read_parquet(registry / "populations.parquet").set_index(
        "population_id"
    ).loc["literature-sami"]
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

    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)

    assert completed.returncode != 0
    assert "must be supplied together" in completed.stderr
