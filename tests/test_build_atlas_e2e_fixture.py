"""Compact e2e fixture tree for the browser tests (fast-load spec §B.5, §B.8)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import h3
import pytest

from genomeos.publication import surface_codec as codec
from scripts import build_atlas_e2e_fixture as e2e

ROOT = Path(__file__).resolve().parents[1]
GOLDEN_EXPORT = ROOT / "tests" / "fixtures" / "atlas-web" / "export"
COMMITTED = ROOT / "website" / "tests" / "fixtures" / "atlas" / "e2e"


def _tree(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _golden_cells() -> list[str]:
    catalog = json.loads((GOLDEN_EXPORT / "catalog.json").read_text())
    surface = json.loads((GOLDEN_EXPORT / catalog["artifacts"][0]["surface_url"]).read_text())
    return [cell["h3_index"] for cell in surface["cells"]]


def test_cell_selection_pins_the_inspector_disk_then_samples_evenly_then_sorts() -> None:
    cells = _golden_cells()
    # Rows 3-9 lie within gridDisk(latLngToCell(INSPECTOR_TARGET, 3), 2); rows 0-2 do not.
    disk = set(h3.grid_disk(h3.latlng_to_cell(*e2e.INSPECTOR_TARGET, 3), 2))
    assert [cell in disk for cell in cells] == [False] * 3 + [True] * 7
    # Two slots over three remaining rows: floor(0 * 3 / 2) = 0 and floor(1 * 3 / 2) = 1.
    assert e2e.select_rows(cells, 3, budget=9) == [0, 1, 3, 4, 5, 6, 7, 8, 9]
    assert e2e.select_rows(cells, 3, budget=5) == [3, 4, 5, 6, 7]
    assert e2e.select_rows(cells, 3, budget=10) == list(range(10))


def test_observation_selection_keeps_the_nearest_eight_then_samples_the_rest() -> None:
    lat, lon = e2e.INSPECTOR_TARGET
    rows = [{"id": index, "lat": lat + index * 0.5, "lon": lon} for index in range(70)][::-1]
    kept = [row["id"] for row in e2e.select_observations(rows, budget=10)]
    # Nearest eight in distance order, then floor(i * 62 / 2) of the remaining 62 for i = 0, 1.
    assert kept == [0, 1, 2, 3, 4, 5, 6, 7, 8, 39]
    assert e2e.select_observations(rows[:5], budget=10) == rows[:5]


def test_build_is_deterministic_and_every_object_matches_its_catalog(tmp_path: Path) -> None:
    first = e2e.build_fixture(GOLDEN_EXPORT, tmp_path / "a", cell_budget=9, observation_budget=1)
    e2e.build_fixture(GOLDEN_EXPORT, tmp_path / "b", cell_budget=9, observation_budget=1)
    assert _tree(tmp_path / "a") == _tree(tmp_path / "b")
    source = json.loads((GOLDEN_EXPORT / "catalog.json").read_text())
    hbs, g6pd = first["artifacts"]
    assert (hbs["n_cells"], hbs["n_observations"]) == (9, 1)
    assert hbs["support_counts"] == {"interpolated": 4, "observed": 2, "prior_dominated": 2, "unknown": 1}
    assert hbs["surface_sha256"] == source["artifacts"][0]["surface_sha256"]
    assert hbs["downloads"]["observations"]["sha256"] == hbs["observations_sha256"]
    observations = (tmp_path / "a" / hbs["observations_url"]).read_bytes()
    assert hashlib.sha256(observations).hexdigest() == hbs["observations_sha256"]
    assert len(observations) == hbs["observations_bytes"]
    assert (g6pd["observations_available"], g6pd["observations_bytes"]) == (False, None)
    assert json.loads((tmp_path / "a" / "catalog.json").read_text()) == first


def test_refuses_to_replace_a_directory_that_is_not_a_fixture_tree(tmp_path: Path) -> None:
    (tmp_path / "out").mkdir()
    (tmp_path / "out" / "notes.txt").write_text("keep me")
    with pytest.raises(ValueError, match="not a fixture tree"):
        e2e.build_fixture(GOLDEN_EXPORT, tmp_path / "out", cell_budget=9, observation_budget=1)
    assert (tmp_path / "out" / "notes.txt").read_text() == "keep me"


def test_committed_e2e_tree_is_complete_and_self_consistent() -> None:
    catalog = json.loads((COMMITTED / "catalog.json").read_text())
    assert len(catalog["artifacts"]) == 30
    ((grid_sha, entry),) = catalog["grids"].items()
    assert (entry["n_cells"], entry["resolution"]) == (e2e.CELL_BUDGET, 4)
    grid = codec.verify_container(
        (COMMITTED / entry["url"]).read_bytes(), tier="grid", sha256=entry["sha256"], size=entry["bytes"]
    )
    cells = {f"{cell:x}" for cell in grid.columns["h3"]}
    assert set(h3.grid_disk(h3.latlng_to_cell(*e2e.INSPECTOR_TARGET, 4), 2)) <= cells
    for ref in catalog["artifacts"]:
        assert (ref["n_cells"], ref["n_observations"]) == (e2e.CELL_BUDGET, e2e.OBSERVATION_BUDGET)
        tiers = {
            tier: codec.verify_container(
                (COMMITTED / ref["web"][tier]["url"]).read_bytes(),
                tier=tier,
                sha256=ref["web"][tier]["sha256"],
                size=ref["web"][tier]["bytes"],
            )
            for tier in ("render", "detail")
        }
        codec.verify_artifact_tiers(grid=grid, ref=ref, grid_sha256=grid_sha, **tiers)
        observations = (COMMITTED / ref["observations_url"]).read_bytes()
        assert hashlib.sha256(observations).hexdigest() == ref["observations_sha256"]
        assert len(observations) == ref["observations_bytes"]
        assert len(json.loads(observations)["observations"]) == e2e.OBSERVATION_BUDGET
    assert {path.name for path in COMMITTED.iterdir()} == {
        "catalog.json",
        "grids",
        "surfaces",
        *(f"{ref['id']}.observations.json" for ref in catalog["artifacts"]),
    }
