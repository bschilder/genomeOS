"""Compact e2e fixture tree for the browser tests (fast-load spec §B.5, §B.8)."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
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


def _copy_export(tmp_path: Path) -> Path:
    source = tmp_path / "src"
    shutil.copytree(GOLDEN_EXPORT, source)
    return source


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


def test_a_rerun_replaces_the_previous_fixture_tree(tmp_path: Path) -> None:
    out = tmp_path / "out"
    e2e.build_fixture(GOLDEN_EXPORT, out, cell_budget=9, observation_budget=1)
    e2e.build_fixture(GOLDEN_EXPORT, out)  # a different grid key: the 9-cell objects must go
    e2e.build_fixture(GOLDEN_EXPORT, tmp_path / "fresh")
    assert _tree(out) == _tree(tmp_path / "fresh")
    assert sorted(path.name for path in tmp_path.iterdir()) == ["fresh", "out"]  # no staging left


@pytest.mark.parametrize("out", ["", "e2e", ".."], ids=["same", "inside", "containing"])
def test_refuses_an_out_that_overlaps_the_source(tmp_path: Path, out: str) -> None:
    source = _copy_export(tmp_path)
    before = _tree(source)
    with pytest.raises(ValueError, match="overlaps its source"):
        e2e.build_fixture(source, source / out, cell_budget=9, observation_budget=1)
    assert _tree(source) == before
    assert not (source / "e2e").exists()
    assert sorted(path.name for path in tmp_path.iterdir()) == ["src"]


def test_a_failed_run_keeps_the_previous_tree_and_leaves_nothing_behind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _copy_export(tmp_path)
    out = tmp_path / "out"
    # The second artifact fails after the first one's observations were written.
    surface = source / json.loads((source / "catalog.json").read_text())["artifacts"][1]["surface_url"]
    good = surface.read_bytes()
    surface.write_bytes(good + b" ")
    with pytest.raises(ValueError, match="sha256 does not match"):
        e2e.build_fixture(source, out, cell_budget=9, observation_budget=1)
    assert sorted(path.name for path in tmp_path.iterdir()) == ["src"]
    surface.write_bytes(good)
    e2e.build_fixture(source, out, cell_budget=9, observation_budget=1)  # the re-run is not refused
    previous = _tree(out)

    def interrupt(*args: object, **kwargs: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(e2e.encode_atlas_web, "encode_catalog", interrupt)
    with pytest.raises(KeyboardInterrupt):
        e2e.build_fixture(source, out)
    assert _tree(out) == previous
    assert sorted(path.name for path in tmp_path.iterdir()) == ["out", "src"]


def test_prepare_out_empties_a_fixture_tree_and_refuses_its_source(tmp_path: Path) -> None:
    tree = tmp_path / "tree"
    (tree / "grids").mkdir(parents=True)
    (tree / "catalog.json").write_text("{}")
    (tree / "grids" / "old.gosa").write_bytes(b"old")
    with pytest.raises(ValueError, match="overlaps its source"):
        e2e.prepare_out(tree, source=tree / "grids")
    assert (tree / "grids" / "old.gosa").read_bytes() == b"old"
    e2e.prepare_out(tree)
    assert tree.is_dir() and not any(tree.iterdir())
    assert sorted(path.name for path in tmp_path.iterdir()) == ["tree"]
    e2e.prepare_out(tmp_path / "new" / "tree")
    assert (tmp_path / "new" / "tree").is_dir()


def test_cli_writes_the_tree_named_by_from_dir_and_out(tmp_path: Path) -> None:
    out = tmp_path / "cli"
    script = ROOT / "scripts" / "build_atlas_e2e_fixture.py"
    argv = [sys.executable, str(script), "--from-dir", str(GOLDEN_EXPORT), "--out", str(out)]
    result = subprocess.run(argv, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert result.stdout == f"wrote 2 compact artifacts to {out}\n"
    e2e.build_fixture(GOLDEN_EXPORT, tmp_path / "api")
    assert _tree(out) == _tree(tmp_path / "api")


def test_cli_defaults_read_the_published_export_and_write_the_committed_tree(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[Path, Path]] = []

    def build(from_dir: Path, out: Path) -> dict:
        calls.append((from_dir, out))
        return {"artifacts": []}

    monkeypatch.setattr(e2e, "build_fixture", build)
    assert e2e.main([]) == 0
    assert calls == [(ROOT / "website" / "public" / "data" / "atlas", COMMITTED)]


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
