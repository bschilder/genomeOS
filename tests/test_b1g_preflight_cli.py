"""Offline B1G basis-preflight adapter tests (design §§4–8, 12; #331)."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pandas as pd


def _load_script():
    script = Path(__file__).parents[1] / "scripts" / "preflight_b1g_basis.py"
    specification = importlib.util.spec_from_file_location("b1g_preflight_cli", script)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_runner_verifies_bytes_and_writes_complete_preflight(tmp_path: Path):
    rows = []
    assignments = []
    for block_id, prefix, longitude in (
        ("west", "w", 0.0),
        ("east", "e", 3.2),
    ):
        for index in range(9):
            record_id = f"{prefix}-{index}"
            rows.append(
                {
                    "variant_id": "chr11-5227002-T-A",
                    "rsid": "rs334",
                    "population_id": f"population-{record_id}",
                    "lat": 0.0,
                    "lon": longitude + index * 0.001,
                    "radius_km": 1.0,
                    "ac": 0 if index == 8 else 1,
                    "an": 20,
                    "source_record_id": record_id,
                    "source": "fixture",
                    "assay": "fixture-assay",
                    "date_lower": 0,
                    "date_upper": 0,
                    "sampling_design": "population_random",
                    "disease_ascertainment_excluded": True,
                    "cohort_id": f"cohort-{record_id}",
                    "ingest_version": "fixture-v1",
                }
            )
            assignments.append(
                {
                    "source_record_id": record_id,
                    "block_id": block_id,
                    "region_id": f"region-{block_id}",
                    "variant_group": "hbs",
                }
            )

    observations_path = tmp_path / "observations.tsv"
    assignments_path = tmp_path / "assignments.tsv"
    dependencies_path = tmp_path / "dependencies.tsv"
    pd.DataFrame.from_records(rows).to_csv(observations_path, sep="\t", index=False)
    pd.DataFrame.from_records(assignments).to_csv(assignments_path, sep="\t", index=False)
    pd.DataFrame(columns=["source_record_id_a", "source_record_id_b"]).to_csv(
        dependencies_path,
        sep="\t",
        index=False,
    )
    output = tmp_path / "output"
    expected = {
        "observations": _sha256(observations_path),
        "assignments": _sha256(assignments_path),
        "dependencies": _sha256(dependencies_path),
    }

    module = _load_script()
    module.run_preflight(
        observations_path=observations_path,
        assignments_path=assignments_path,
        dependencies_path=dependencies_path,
        out=output,
        data_version="fixture-v1",
        buffer_km=300.0,
        query_chunk_size=3,
        expected_sha256=expected,
    )

    assert {path.name for path in output.iterdir()} == {
        "basis_preflight.tsv",
        "provenance.json",
        "report.json",
    }
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    provenance = json.loads((output / "provenance.json").read_text(encoding="utf-8"))
    assert report["schema_version"] == "b1g_basis_preflight_v1"
    assert len(report["cells"]) == 18
    assert len(report["grid_summary"]) == 9
    assert provenance["input_sha256"] == expected
    assert provenance["elapsed_ns"] > 0
