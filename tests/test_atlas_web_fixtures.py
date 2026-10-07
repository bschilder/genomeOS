"""Committed GOSA golden fixtures and the shared mutation corpus (fast-load spec §B.3, §B.5, §B.8)."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
from collections import Counter
from pathlib import Path

import h3
import pytest

from genomeos.publication import surface_codec as codec
from scripts import encode_atlas_web

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "atlas-web"
EXPORT = FIXTURES / "export"
MUTATIONS = FIXTURES / "mutations"
GOLDEN = ROOT / "website" / "tests" / "fixtures" / "atlas" / "golden"
#: The spec §B.3 list every decoder must refuse with the same error class.
SPEC_MUTATIONS = {
    "grid-reserved-1": "reserved",
    "render-pad-byte": "padding",
    "grid-trailing-byte": "trailing_bytes",
    "render-offset-plus-8": "offset",
    "grid-msb-first-planes": "grid_order",
    "grid-zero-delta": "grid_order",
    "grid-reserved-h3-bit": "h3_cell",
    "grid-mode-2": "h3_cell",
    "grid-digit-7": "h3_cell",
    "grid-base-cell-122": "h3_cell",
    "grid-wrong-resolution": "h3_cell",
}


def _catalog() -> dict:
    return json.loads((EXPORT / "catalog.json").read_text())


def _surface(ref: dict) -> dict:
    return json.loads((EXPORT / ref["surface_url"]).read_text())


def _tree(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_regenerating_reproduces_every_committed_fixture_byte(tmp_path: Path) -> None:
    spec = importlib.util.spec_from_file_location("atlas_web_regenerate", FIXTURES / "regenerate.py")
    assert spec is not None and spec.loader is not None
    regenerate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(regenerate)
    assert regenerate.main(["--root", str(tmp_path)]) == 0
    assert _tree(tmp_path / "tests/fixtures/atlas-web/export") == _tree(EXPORT)
    assert _tree(tmp_path / "tests/fixtures/atlas-web/mutations") == _tree(MUTATIONS)
    assert _tree(tmp_path / "website/tests/fixtures/atlas/golden") == _tree(GOLDEN)


def test_fixture_tree_holds_every_property_the_decoders_must_exercise() -> None:
    catalog = _catalog()
    assert [ref["artifact_format"] for ref in catalog["artifacts"]] == [1, 2]
    assert [ref["observations_available"] for ref in catalog["artifacts"]] == [True, False]
    for ref in catalog["artifacts"]:
        surface = _surface(ref)
        cells = surface["cells"]
        indices = [int(cell["h3_index"], 16) for cell in cells]
        assert indices == sorted(indices) and len(set(indices)) == len(indices)
        assert 8 <= len(cells) <= 12
        assert {h3.get_resolution(cell["h3_index"]) for cell in cells} == {3}
        assert set(Counter(cell["support"] for cell in cells)) == set(codec.SUPPORT_CODES)
        domains = surface["artifact"]["metric_domains"]
        for metric in ("post_mean", "post_sd"):
            low, high = domains[metric]
            assert any(
                cell["support"] == "prior_dominated" and not low <= cell[metric] <= high for cell in cells
            ), f"{ref['id']}: no prior-dominated cell outside the {metric} domain"
        assert any(cell["q025"] == cell["post_mean"] for cell in cells)
        assert any(cell["post_mean"] == cell["q975"] for cell in cells)
    format_one = _surface(catalog["artifacts"][0])["artifact"]
    assert "target_grid_source" not in format_one and "target_grid_version" not in format_one


def test_golden_objects_re_encode_byte_for_byte_from_the_json() -> None:
    catalog = _catalog()
    ((grid_sha, grid_entry),) = catalog["grids"].items()
    first = _surface(catalog["artifacts"][0])
    grid = codec.encode_grid([int(cell["h3_index"], 16) for cell in first["cells"]], 3)
    assert grid == (EXPORT / grid_entry["url"]).read_bytes()
    assert (len(grid), codec.container_sha256(grid)) == (grid_entry["bytes"], grid_entry["sha256"])
    for ref in catalog["artifacts"]:
        surface = _surface(ref)
        cells = surface["cells"]
        common = {
            "artifact": surface["artifact"],
            "source_surface_sha256": ref["surface_sha256"],
            "grid_sha256": grid_sha,
        }
        render = codec.encode_render(
            **common,
            support=[cell["support"] for cell in cells],
            post_mean=[cell["post_mean"] for cell in cells],
            post_sd=[cell["post_sd"] for cell in cells],
        )
        detail = codec.encode_detail(
            **common, **{field: [cell[field] for cell in cells] for field in codec.DETAIL_FIELDS}
        )
        for tier, data in (("render", render), ("detail", detail)):
            declared = ref["web"][tier]
            assert data == (EXPORT / declared["url"]).read_bytes(), f"{ref['id']} {tier}"
            assert (len(data), hashlib.sha256(data).hexdigest()) == (declared["bytes"], declared["sha256"])


def test_every_golden_object_re_encodes_byte_for_byte_from_its_decoded_container() -> None:
    """Spec §B.3 shared test: encode(decode(f)) == f for every golden grid, render and detail object.

    Unlike the test above, the encoder's inputs come from the decoder (header and columns), so a
    decode that returns values the encoder would serialise differently fails here.
    """
    catalog = _catalog()
    ((_, grid_entry),) = catalog["grids"].items()
    grid_bytes = (EXPORT / grid_entry["url"]).read_bytes()
    grid = codec.decode(grid_bytes, tier="grid")
    assert codec.encode_grid(list(grid.columns["h3"]), grid.header["resolution"]) == grid_bytes
    for ref in catalog["artifacts"]:
        for tier in ("render", "detail"):
            data = (EXPORT / ref["web"][tier]["url"]).read_bytes()
            decoded = codec.decode(data, tier=tier)
            common = {
                "artifact": decoded.header["artifact"],
                "source_surface_sha256": decoded.header["source_surface_sha256"],
                "grid_sha256": decoded.header["grid_sha256"],
            }
            if tier == "render":
                again = codec.encode_render(
                    **common,
                    support=[codec.SUPPORT_CODES[code] for code in decoded.columns["support"]],
                    post_mean=list(decoded.columns["post_mean"]),
                    post_sd=list(decoded.columns["post_sd"]),
                )
            else:
                again = codec.encode_detail(
                    **common, **{field: list(decoded.columns[field]) for field in codec.DETAIL_FIELDS}
                )
            assert again == data, f"{ref['id']} {tier}"


def test_golden_support_bytes_are_the_documented_codes() -> None:
    expected = {
        "hbs-rs334": bytes([3, 2, 3, 1, 1, 0, 0, 1, 2, 1]),
        "g6pd-deficiency": bytes([1, 3, 2, 0, 1, 0, 3, 1, 2, 1]),
    }
    for ref in _catalog()["artifacts"]:
        data = (EXPORT / ref["web"]["render"]["url"]).read_bytes()
        header = codec.decode(data, tier="render").header
        column_area = (12 + int.from_bytes(data[8:12], "little") + 7) & ~7
        support = header["columns"][0]
        assert support["name"] == "support"
        assert data[column_area : column_area + support["length"]] == expected[ref["id"]]


def test_encoder_cli_reproduces_the_committed_catalog_from_the_bare_export(tmp_path: Path) -> None:
    work = tmp_path / "export"
    shutil.copytree(EXPORT, work, ignore=shutil.ignore_patterns("grids", "surfaces"))
    bare = _catalog()
    bare.pop("grids")
    for ref in bare["artifacts"]:
        ref.pop("web")
        ref.pop("observations_bytes")
    (work / "catalog.json").write_bytes(encode_atlas_web.canonical_bytes(bare))
    assert encode_atlas_web.main(["--in", str(work)]) == 0
    assert _tree(work) == _tree(EXPORT)


def test_every_tier_verifies_against_its_catalog_ref() -> None:
    catalog = _catalog()
    ((grid_sha, grid_entry),) = catalog["grids"].items()
    grid = codec.verify_container(
        (EXPORT / grid_entry["url"]).read_bytes(),
        tier="grid",
        sha256=grid_entry["sha256"],
        size=grid_entry["bytes"],
    )
    for ref in catalog["artifacts"]:
        tiers = {
            tier: codec.verify_container(
                (EXPORT / ref["web"][tier]["url"]).read_bytes(),
                tier=tier,
                sha256=ref["web"][tier]["sha256"],
                size=ref["web"][tier]["bytes"],
            )
            for tier in ("render", "detail")
        }
        codec.verify_artifact_tiers(grid=grid, ref=ref, grid_sha256=grid_sha, **tiers)
    with pytest.raises(codec.GosaError) as error:
        codec.verify_container(b"GOSA", tier="grid", sha256=grid_entry["sha256"], size=grid_entry["bytes"])
    assert error.value.code == "container_sha256"


def test_mutation_corpus_is_refused_with_the_manifest_error_code() -> None:
    manifest = json.loads((MUTATIONS / "manifest.json").read_text())
    assert manifest["codes"] == list(codec.GOSA_ERROR_CODES)
    names = {entry["file"].removesuffix(".gosa"): entry["code"] for entry in manifest["mutations"]}
    assert {name: names.get(name) for name in SPEC_MUTATIONS} == SPEC_MUTATIONS
    assert sorted(path.name for path in MUTATIONS.glob("*.gosa")) == sorted(
        e["file"] for e in manifest["mutations"]
    )
    for entry in manifest["mutations"]:
        data = (MUTATIONS / entry["file"]).read_bytes()
        assert (len(data), hashlib.sha256(data).hexdigest()) == (entry["bytes"], entry["sha256"])
        assert (EXPORT / entry["base"]).is_file()
        with pytest.raises(codec.GosaError) as error:
            codec.decode(data, tier=entry["tier"])
        assert error.value.code == entry["code"], entry["file"]


def test_website_golden_copies_are_byte_identical() -> None:
    assert _tree(GOLDEN / "mutations") == _tree(MUTATIONS)
    golden = {key: value for key, value in _tree(GOLDEN).items() if not key.startswith("mutations/")}
    assert golden == _tree(EXPORT)
