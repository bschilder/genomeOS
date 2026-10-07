"""Review-figure arithmetic for the GOSA web rendition (fast-load spec §B.1, §B.5)."""

from __future__ import annotations

import json
from pathlib import Path

from genomeos.publication import surface_codec as codec
from scripts.plot_surface_codec_parity import bin_colors, bin_flips, color_at, max_detail_error, quantize

EXPORT = Path(__file__).resolve().parent / "fixtures" / "atlas-web" / "export"


def test_quantize_mirrors_quantize_metric() -> None:
    assert quantize(0.5, (0.0, 1.0)) == 16
    assert quantize(1.0, (0.0, 1.0)) == 31  # the top edge stays in the last bin
    assert quantize(-3.0, (0.0, 1.0)) == 0 and quantize(7.0, (0.0, 1.0)) == 31  # clamped
    assert quantize(0.2, (0.2, 0.2)) == 0


def test_color_at_mirrors_color_at_stops() -> None:
    assert color_at("rainbow", 0.0) == (0x6E, 0x40, 0xAA)
    assert color_at("rainbow", 1.0) == (0xFF, 0x5E, 0x63)
    assert color_at("plasma", 0.5) == (0xCC, 0x47, 0x78)  # tests/atlas-scene.test.ts pins #cc4778
    assert color_at("plasma", 2.0) == color_at("plasma", 1.0)


def test_bin_colour_comes_from_the_first_unmasked_cell_in_grid_order() -> None:
    support = (2, 0, 1)  # prior_dominated, observed, interpolated
    colors = bin_colors(support, (0.0, 0.01, 0.02), (0.0, 1.0), "plasma")
    assert colors == {0: color_at("plasma", 0.01)}


def test_golden_fixture_pins_two_float32_bin_flips_and_an_exact_detail_tier() -> None:
    # hbs-rs334 post_sd sits on bin edges: row 5 (observed, 0.0153) and row 8 (prior-dominated,
    # 0.0201) change bin under float32. The render tier's bins are the ones the globe draws.
    expected = {("hbs-rs334", "post_sd"): [(5, 10, 11), (8, 19, 18)]}
    catalog = json.loads((EXPORT / "catalog.json").read_text())
    for ref in catalog["artifacts"]:
        render = codec.decode((EXPORT / ref["web"]["render"]["url"]).read_bytes(), tier="render")
        detail = codec.decode((EXPORT / ref["web"]["detail"]["url"]).read_bytes(), tier="detail")
        for metric in ("post_mean", "post_sd"):
            flips = bin_flips(
                render.columns["support"],
                detail.columns[metric],
                render.columns[metric],
                ref["metric_domains"][metric],
            )
            assert flips == expected.get((ref["id"], metric), [])
        cells = json.loads((EXPORT / ref["surface_url"]).read_text())["cells"]
        assert set(max_detail_error(detail.columns, cells).values()) == {0.0}


def test_bin_flips_report_binned_cells_only() -> None:
    # Row 0 is interpolated and crosses 0.5; row 1 is unknown and is never binned.
    assert bin_flips((1, 3), (0.49, 0.49), (0.51, 0.51), (0.0, 1.0)) == [(0, 15, 16)]
