#!/usr/bin/env python3
"""Regenerate the GOSA golden fixtures (Atlas design §11; fast-load spec §B.3, §B.5, §B.8).

    python tests/fixtures/atlas-web/regenerate.py

Writes, from the two hand-written ten-cell surfaces below:

- ``tests/fixtures/atlas-web/export/``: a real ``export_atlas_web.py`` export of a resolution-3
  store, then encoded in place by ``encode_atlas_web.py`` (golden ``.gosa`` objects plus the
  encoded ``catalog.json``);
- ``tests/fixtures/atlas-web/mutations/``: the shared mutation corpus, one hard error per file,
  with ``manifest.json`` naming each file's base object, requested tier and expected error code;
- ``website/tests/fixtures/atlas/golden/``: byte-identical copies of both trees for vitest.

The cells are SYNTHETIC contract fixtures, not scientific results. They sit around Madrid (the
browser fixture's inspector target), sorted by u64 index, and between them cover all four support
states, a prior-dominated cell outside ``metric_domains`` in both metrics, ``q025 == post_mean``,
``post_mean == q975``, and one format-1 and one format-2 artifact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import struct
import sys
import tempfile
from pathlib import Path
from typing import Any

import h3
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from genomeos.publication import surface_codec as codec  # noqa: E402
from scripts import encode_atlas_web, export_atlas_web  # noqa: E402

HF_REVISION = "fc17bc1c1d96a0d0766746dcf26277ccdc669717"
CURATED_HBS = ROOT / "tests" / "fixtures" / "map_hbs_curated_synthetic.csv"

#: Resolution-3 cells, ascending u64: rows 0-2 lie three rings from latLngToCell(Madrid, 3) =
#: 83390cfffffffff; rows 3-9 are gridDisk(83390cfffffffff, 1).
CELLS = (
    "83184bfffffffff",
    "833824fffffffff",
    "833825fffffffff",
    "833901fffffffff",
    "833908fffffffff",
    "83390cfffffffff",
    "83390dfffffffff",
    "83390efffffffff",
    "83392afffffffff",
    "83392bfffffffff",
)
COLUMNS = ("support", "post_mean", "post_sd", "q025", "q975", "posterior_contraction", "dist_nearest_obs_km")

# fmt: off
#: hbs-rs334 fixture (format 1). Row 1 is prior-dominated above both domains; row 4 has
#: q025 == post_mean; row 7 has post_mean == q975.
HBS_ROWS = (
    ("unknown",         0.0402, 0.0708, 0.0011, 0.2347, 0.97, 1450.5),
    ("prior_dominated", 0.2513, 0.0917, 0.0982, 0.4489, 0.94,  655.0),
    ("unknown",         0.0557, 0.0655, 0.0018, 0.2296, 0.99, 1388.25),
    ("interpolated",    0.0731, 0.0214, 0.0371, 0.1196, 0.41,  180.25),
    ("interpolated",    0.0119, 0.0087, 0.0119, 0.0402, 0.62,   96.75),
    ("observed",        0.1342, 0.0153, 0.1057, 0.1655, 0.12,    0.0),
    ("observed",        0.1804, 0.0198, 0.1431, 0.2207, 0.18,   12.5),
    ("interpolated",    0.0985, 0.0236, 0.0611, 0.0985, 0.55,  240.5),
    ("prior_dominated", 0.0877, 0.0201, 0.0532, 0.1309, 0.91,  410.75),
    ("interpolated",    0.0466, 0.0279, 0.0101, 0.1123, 0.47,  310.0),
)
#: g6pd-deficiency fixture (format 2, observations unavailable). Row 2 is prior-dominated below
#: the post_mean domain and above the post_sd domain; row 5 has q025 == post_mean; row 9 has
#: post_mean == q975.
G6PD_ROWS = (
    ("interpolated",    0.0652, 0.0144, 0.0401, 0.0947, 0.52,  205.5),
    ("unknown",         0.0315, 0.0611, 0.0007, 0.1984, 0.98, 1302.0),
    ("prior_dominated", 0.0021, 0.0733, 0.0001, 0.2105, 0.95,  702.25),
    ("observed",        0.0904, 0.0121, 0.0681, 0.1155, 0.15,    3.5),
    ("interpolated",    0.0478, 0.0163, 0.0203, 0.0839, 0.44,   88.0),
    ("observed",        0.0233, 0.0059, 0.0233, 0.0362, 0.21,    0.0),
    ("unknown",         0.0388, 0.0587, 0.0012, 0.1876, 0.99, 1501.75),
    ("interpolated",    0.1127, 0.0189, 0.0786, 0.1522, 0.37,  140.5),
    ("prior_dominated", 0.0599, 0.0251, 0.0218, 0.1103, 0.92,  455.0),
    ("interpolated",    0.0716, 0.0207, 0.0365, 0.0716, 0.58,  260.25),
)
# fmt: on

ARTIFACTS = (
    {
        "id": "hbs-rs334",
        "variant_id": "chr11-5227002-T-A",
        "artifact_dir": "chr11-5227002-T-A__v1__map-test",
        "observation_source": "map_hbs_surveys.csv",
        "rows": HBS_ROWS,
        "manifest": {
            "artifact_format": 1,
            "correlation_range_km": 500.0,
            "data_version": "map-test",
            "likelihood": "beta_binomial",
            "model_version": "v1",
            "n_observations": 1,
            "resolution": 3,
        },
        "metadata": {
            "label": "HbS (rs334) fixture",
            "entity_type": "variant",
            "measurement": "allele_frequency",
            "assumptions": ["SYNTHETIC fixture surface"],
        },
    },
    {
        "id": "g6pd-deficiency",
        "variant_id": "phenotype:g6pd-deficiency",
        "artifact_dir": "phenotype__g6pd-deficiency__v2__map-test",
        "observation_source": None,
        "rows": G6PD_ROWS,
        "manifest": {
            "artifact_format": 2,
            "correlation_range_km": 420.0,
            "data_version": "map-test",
            "likelihood": "beta_binomial",
            "model_version": "v2",
            "n_observations": 3,
            "resolution": 3,
            "target_grid_source": "worldpop-1km-unconstrained",
            "target_grid_version": "fixture-2020",
        },
        "metadata": {
            "label": "G6PD deficiency fixture",
            "entity_type": "phenotype",
            "measurement": "phenotype_frequency",
            "assumptions": ["SYNTHETIC fixture surface"],
        },
    },
)

DISCOVERY_GROUP = {
    "id": "red-blood-cell-disorders",
    "label": "Red blood cell disorders",
    "summary": "Hemoglobin and red-cell enzyme traits.",
    "biology": "These maps describe variation affecting red blood cells.",
    "references": [{"label": "NIH overview", "url": "https://www.nhlbi.nih.gov/health/anemia"}],
}


def _discovery(symbol: str) -> dict[str, Any]:
    return {
        "group_id": DISCOVERY_GROUP["id"],
        "map_measures": f"SYNTHETIC fixture map for {symbol}.",
        "symbol_expansion": symbol,
        "relevance": "Contract fixture for the GOSA web codec; not a scientific result.",
        "aliases": [symbol.lower()],
        "references": [{"label": "NIH overview", "url": "https://www.nhlbi.nih.gov/health/anemia"}],
    }


def _write_store(store: Path) -> None:
    for spec in ARTIFACTS:
        artifact = store / "artifacts" / spec["artifact_dir"]
        artifact.mkdir(parents=True)
        frame = pd.DataFrame(spec["rows"], columns=list(COLUMNS))
        frame.insert(0, "h3_index", list(CELLS))
        frame["variant_id"] = spec["variant_id"]
        frame["model_version"] = spec["manifest"]["model_version"]
        frame["data_version"] = spec["manifest"]["data_version"]
        frame.to_parquet(artifact / "cells.parquet", index=False)
        counts = frame["support"].value_counts().to_dict()
        manifest = {
            **spec["manifest"],
            "n_cells": len(CELLS),
            "variant_id": spec["variant_id"],
            "support_counts": {str(state): int(count) for state, count in sorted(counts.items())},
        }
        (artifact / "manifest.json").write_text(json.dumps(manifest, sort_keys=True))
    metadata = {
        "artifact_version": "atlas-fixture-v1",
        "registry_version": "map-test-registry",
        "created_at": "2026-10-07T00:00:00Z",
        "assumptions": ["SYNTHETIC fixture catalog"],
        "discovery_groups": [DISCOVERY_GROUP],
        "discovery": {spec["variant_id"]: _discovery(spec["metadata"]["label"]) for spec in ARTIFACTS},
        "variants": {spec["variant_id"]: spec["metadata"] for spec in ARTIFACTS},
    }
    (store / "catalog-metadata.json").write_text(json.dumps(metadata, sort_keys=True))


def export_tree(out: Path) -> None:
    """Export the fixture store with ``export_atlas_web`` and encode it in place."""
    with tempfile.TemporaryDirectory() as temporary:
        work = Path(temporary)
        _write_store(work / "store")
        hbs_csv = work / "map_hbs_surveys.csv"
        pd.read_csv(CURATED_HBS).iloc[[0]].to_csv(hbs_csv, index=False)
        g6pd_csv = work / "map_g6pd_surveys.csv"
        g6pd_csv.write_text("id,latitude,longitude\n")
        allowlist = work / "allowlist.json"
        allowlist.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "hf_dataset": "bschilder/genomeos-data",
                    "hf_revision": HF_REVISION,
                    "artifacts": [
                        {key: spec[key] for key in ("id", "variant_id", "artifact_dir", "observation_source")}
                        for spec in ARTIFACTS
                    ],
                }
            )
        )
        export_atlas_web.export_catalog(
            source_root=work / "store",
            hbs_csv=hbs_csv,
            g6pd_csv=g6pd_csv,
            allowlist_path=allowlist,
            out_dir=out,
            hf_revision=HF_REVISION,
        )
    encode_atlas_web.encode_export(out, out)


# --- mutation corpus: an independent minimal framer, so the corpus shares no codec code -------


def _align8(value: int) -> int:
    return (value + 7) & ~7


def _split(data: bytes) -> tuple[dict[str, Any], bytes]:
    """The parsed header and the column-area bytes of a valid container."""
    (length,) = struct.unpack_from("<I", data, 8)
    return json.loads(data[12 : 12 + length]), data[_align8(12 + length) :]


def _frame(header: dict[str, Any], area: bytes) -> bytes:
    text = json.dumps(header, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    head = b"GOSA" + struct.pack("<HHI", 1, 0, len(text)) + text
    return head + bytes(_align8(len(head)) - len(head)) + area


def _shuffle(raw: bytes, width: int, planes: range) -> bytes:
    return b"".join(raw[plane::width] for plane in planes)


def _unshuffle(payload: bytes, width: int) -> bytes:
    count = len(payload) // width
    return bytes(payload[plane * count + row] for row in range(count) for plane in range(width))


def _grid(grid: bytes, cells: list[int], planes: range = range(8)) -> bytes:
    """The golden grid with new cell values (and their digest), delta-shuffled in ``planes`` order."""
    header, _ = _split(grid)
    header["grid_sha256"] = hashlib.sha256(struct.pack(f"<{len(cells)}Q", *cells)).hexdigest()
    deltas = [cells[0], *(after - before for before, after in zip(cells, cells[1:], strict=False))]
    return _frame(header, _shuffle(struct.pack(f"<{len(deltas)}Q", *deltas), 8, planes))


def _column(data: bytes, name: str, row: int, value: float) -> bytes:
    """Set one value of one column; every other byte of the container is unchanged."""
    header, area = _split(data)
    column = next(column for column in header["columns"] if column["name"] == name)
    fmt = {"u8": "B", "f32": "f", "f64": "d"}[column["dtype"]]
    width = struct.calcsize(fmt)
    start, end = column["offset"], column["offset"] + column["length"]
    values = list(struct.unpack(f"<{column['length'] // width}{fmt}", _unshuffle(area[start:end], width)))
    values[row] = value
    payload = _shuffle(struct.pack(f"<{len(values)}{fmt}", *values), width, range(width))
    return _frame(header, area[:start] + payload + area[end:])


DELETE = object()


def _header(data: bytes, path: tuple[Any, ...], value: Any) -> bytes:
    """Set (or, with ``value=DELETE``, remove) one header field; the column area is unchanged."""
    header, area = _split(data)
    target = header
    for key in path[:-1]:
        target = target[key]
    if value is DELETE:
        del target[path[-1]]
    else:
        target[path[-1]] = value
    return _frame(header, area)


def mutation_corpus(grid: bytes, render: bytes, detail: bytes) -> dict[str, tuple[str, str, bytes]]:
    """``name -> (requested tier, expected GosaError code, bytes)``; one hard error per file."""
    cells = [int(cell, 16) for cell in CELLS]
    head, last = cells[:-1], cells[-1]
    header_end = 12 + struct.unpack_from("<I", render, 8)[0]
    render_header, _ = _split(render)
    pad = _align8(header_end) + render_header["columns"][0]["length"]  # first byte after support
    second_offset = render_header["columns"][1]["offset"]
    utf8 = render.index(b'"tier":"render"') + len(b'"tier":"r')
    child = int(h3.cell_to_center_child(CELLS[-1], 4), 16)
    return {
        "grid-truncated-preamble": ("grid", "truncated", grid[:8]),
        "grid-bad-magic": ("grid", "magic", b"GOSB" + grid[4:]),
        "grid-format-version-2": ("grid", "format_version", grid[:4] + b"\x02\x00" + grid[6:]),
        "grid-reserved-1": ("grid", "reserved", grid[:6] + b"\x01\x00" + grid[8:]),
        "render-header-invalid-utf8": (
            "render",
            "header_encoding",
            render[:utf8] + b"\xff" + render[utf8 + 1 :],
        ),
        "render-header-not-json": (
            "render",
            "header_json",
            render[: header_end - 1] + b" " + render[header_end:],
        ),
        "render-header-extra-key": ("render", "header_schema", _header(render, ("extra",), 1)),
        "grid-header-boolean-n-cells": ("grid", "header_schema", _header(grid, ("n_cells",), True)),
        "render-requested-as-detail": ("detail", "tier", render),
        "render-identity-missing-label": (
            "render",
            "identity",
            _header(render, ("artifact", "label"), DELETE),
        ),
        "render-columns-reordered": (
            "render",
            "columns",
            _header(_header(render, ("columns", 1, "name"), "post_sd"), ("columns", 2, "name"), "post_mean"),
        ),
        "render-column-wrong-dtype": ("render", "columns", _header(render, ("columns", 1, "dtype"), "f64")),
        "render-column-length": (
            "render",
            "column_length",
            _header(render, ("columns", 0, "length"), len(CELLS) - 1),
        ),
        "render-offset-plus-8": (
            "render",
            "offset",
            _header(render, ("columns", 1, "offset"), second_offset + 8),
        ),
        "grid-trailing-byte": ("grid", "trailing_bytes", grid + b"\x00"),
        "detail-truncated-column": ("detail", "truncated", detail[:-1]),
        "render-pad-byte": ("render", "padding", render[:pad] + b"\x01" + render[pad + 1 :]),
        "grid-msb-first-planes": ("grid", "grid_order", _grid(grid, cells, range(7, -1, -1))),
        "grid-zero-delta": ("grid", "grid_order", _grid(grid, [cells[0], *head])),
        "grid-reserved-h3-bit": ("grid", "h3_cell", _grid(grid, [*head, last | 1 << 63])),
        "grid-mode-2": ("grid", "h3_cell", _grid(grid, [*head, (last & ~(0xF << 59)) | 2 << 59])),
        "grid-digit-7": ("grid", "h3_cell", _grid(grid, [*head, last | 7 << 36])),
        "grid-base-cell-122": ("grid", "h3_cell", _grid(grid, [*head, (last & ~(0x7F << 45)) | 122 << 45])),
        "grid-wrong-resolution": ("grid", "h3_cell", _grid(grid, [*head, child])),
        "grid-header-sha-mismatch": ("grid", "grid_sha256", _header(grid, ("grid_sha256",), "0" * 64)),
        "render-support-code-4": ("render", "support_code", _column(render, "support", 0, 4)),
        "render-post-mean-nan": ("render", "non_finite", _column(render, "post_mean", 0, float("nan"))),
        "detail-post-sd-negative": ("detail", "value_range", _column(detail, "post_sd", 0, -0.01)),
        "detail-post-mean-above-one": ("detail", "value_range", _column(detail, "post_mean", 3, 1.5)),
        "detail-q025-above-mean": ("detail", "interval_order", _column(detail, "q025", 3, 0.0741)),
    }


def write_mutations(export: Path, out: Path) -> None:
    """Write the corpus derived from the first artifact's golden objects, plus its manifest."""
    catalog = json.loads((export / "catalog.json").read_text(encoding="utf-8"))
    ((grid_sha, grid_entry),) = catalog["grids"].items()
    ref = catalog["artifacts"][0]
    bases = {
        "grid": (grid_entry["url"], None),
        "render": (ref["web"]["render"]["url"], ref["id"]),
        "detail": (ref["web"]["detail"]["url"], ref["id"]),
    }
    grid, render, detail = ((export / bases[tier][0]).read_bytes() for tier in ("grid", "render", "detail"))
    out.mkdir(parents=True)
    entries = []
    for name, (tier, code, data) in mutation_corpus(grid, render, detail).items():
        (out / f"{name}.gosa").write_bytes(data)
        base_tier = name.split("-", 1)[0]
        base, artifact = bases[base_tier]
        entries.append(
            {
                "artifact": artifact,
                "base": base,
                "bytes": len(data),
                "code": code,
                "file": f"{name}.gosa",
                "grid_sha256": grid_sha,
                "sha256": hashlib.sha256(data).hexdigest(),
                "tier": tier,
            }
        )
    manifest = {"codes": list(codec.GOSA_ERROR_CODES), "mutations": entries}
    (out / "manifest.json").write_bytes(encode_atlas_web.canonical_bytes(manifest))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--root", type=Path, default=ROOT, help="repository root to write under")
    args = parser.parse_args(argv)
    fixtures = args.root / "tests" / "fixtures" / "atlas-web"
    golden = args.root / "website" / "tests" / "fixtures" / "atlas" / "golden"
    for owned in (fixtures / "export", fixtures / "mutations", golden):
        shutil.rmtree(owned, ignore_errors=True)
    export_tree(fixtures / "export")
    write_mutations(fixtures / "export", fixtures / "mutations")
    shutil.copytree(fixtures / "export", golden)
    shutil.copytree(fixtures / "mutations", golden / "mutations")
    print(f"wrote {fixtures} and {golden}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
