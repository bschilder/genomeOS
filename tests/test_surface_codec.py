"""GOSA v1 container codec (Atlas design §11; fast-load spec §B.3)."""

from __future__ import annotations

import hashlib
import json
import struct
from typing import Any

import pytest

from genomeos.publication import surface_codec as codec
from genomeos.surfaces.mask import SUPPORT_STATES

#: Three ascending resolution-3 cells around Madrid.
CELLS = (0x833901FFFFFFFFF, 0x833908FFFFFFFFF, 0x83390CFFFFFFFFF)
ARTIFACT = {
    "artifact_format": 2,
    "data_version": "map-test",
    "entity_type": "variant",
    "hf_dataset": "bschilder/genomeos-data",
    "hf_revision": "fc17bc1c1d96a0d0766746dcf26277ccdc669717",
    "id": "hbs-rs334",
    "label": "HbS (rs334) fixture",
    "measurement": "allele_frequency",
    "metric_domains": {"post_mean": [0.0119, 0.1804], "post_sd": [0.0087, 0.0279]},
    "model_version": "v1",
    "registry_version": "map-test-registry",
    "resolution": 3,
    "target_grid_source": "worldpop-1km-unconstrained",
    "target_grid_version": "fixture-2020",
    "variant_id": "chr11-5227002-T-A",
}
SOURCE_SHA = "a" * 64
VALUES = {
    "support": ["observed", "prior_dominated", "unknown"],
    # Row 1 is prior-dominated above both metric domains: valid, never clamped.
    "post_mean": [0.1342, 0.2513, 0.0119],
    "post_sd": [0.0153, 0.0917, 0.0087],
    "q025": [0.1057, 0.0982, 0.0119],
    "q975": [0.1655, 0.4489, 0.0402],
    "posterior_contraction": [0.12, 0.94, 1.37],
    "dist_nearest_obs_km": [0.0, 655.0, 1450.5],
}


def _grid() -> bytes:
    return codec.encode_grid(CELLS, 3)


def _render(**overrides: Any) -> bytes:
    fields = {key: VALUES[key] for key in ("support", "post_mean", "post_sd")} | overrides
    return codec.encode_render(
        artifact=ARTIFACT, source_surface_sha256=SOURCE_SHA, grid_sha256=codec.grid_sha256(CELLS), **fields
    )


def _detail(**overrides: Any) -> bytes:
    fields = {key: VALUES[key] for key in codec.DETAIL_FIELDS} | overrides
    return codec.encode_detail(
        artifact=ARTIFACT, source_surface_sha256=SOURCE_SHA, grid_sha256=codec.grid_sha256(CELLS), **fields
    )


def _split(data: bytes) -> tuple[dict, bytes]:
    (length,) = struct.unpack_from("<I", data, 8)
    return json.loads(data[12 : 12 + length]), data[(12 + length + 7) & ~7 :]


def _frame(header: object, area: bytes, *, version: int = 1, reserved: int = 0) -> bytes:
    text = json.dumps(header, sort_keys=True, separators=(",", ":")).encode()
    head = b"GOSA" + struct.pack("<HHI", version, reserved, len(text)) + text
    return head + bytes(((len(head) + 7) & ~7) - len(head)) + area


def _frame_text(text: str, area: bytes) -> bytes:
    """Frame header text that ``json.dumps`` cannot write (too deep, too many digits)."""
    raw = text.encode()
    head = b"GOSA" + struct.pack("<HHI", 1, 0, len(raw)) + raw
    return head + bytes(((len(head) + 7) & ~7) - len(head)) + area


def _edit_header(data: bytes, edit) -> bytes:
    header, area = _split(data)
    edit(header)
    return _frame(header, area)


def _code(data: bytes, tier: str) -> str:
    with pytest.raises(codec.GosaError) as error:
        codec.decode(data, tier=tier)
    return error.value.code


def test_support_codes_match_the_mask_and_the_detail_columns_match_the_spec() -> None:
    assert codec.SUPPORT_CODES == SUPPORT_STATES
    assert codec.FORMAT_VERSION == 1
    assert codec.TIER_COLUMNS["render"] == (
        ("support", "u8", "raw"),
        ("post_mean", "f32", "shuffle"),
        ("post_sd", "f32", "shuffle"),
    )
    assert [name for name, _, _ in codec.TIER_COLUMNS["detail"]] == [
        "post_mean",
        "post_sd",
        "q025",
        "q975",
        "posterior_contraction",
        "dist_nearest_obs_km",
    ]


def test_grid_round_trips_and_its_digest_covers_the_decoded_column() -> None:
    data = _grid()
    decoded = codec.decode(data, tier="grid")
    assert decoded.columns == {"h3": CELLS}
    assert decoded.header["artifact"] is None and decoded.header["source_surface_sha256"] is None
    assert decoded.header["grid_sha256"] == codec.grid_sha256(CELLS)
    assert codec.grid_sha256(CELLS) == hashlib.sha256(struct.pack("<3Q", *CELLS)).hexdigest()
    (length,) = struct.unpack_from("<I", data, 8)
    assert data[:8] == b"GOSA" + struct.pack("<HH", 1, 0)
    assert len(data) == ((12 + length + 7) & ~7) + 3 * 8  # header, zero pad, one u64 column


def test_grid_layout_is_delta_then_byte_shuffled_least_significant_plane_first() -> None:
    header, area = _split(_grid())
    deltas = [CELLS[0], CELLS[1] - CELLS[0], CELLS[2] - CELLS[1]]
    raw = struct.pack("<3Q", *deltas)
    assert area == b"".join(raw[plane::8] for plane in range(8))
    assert header["columns"] == [
        {"dtype": "u64", "encoding": "delta_shuffle", "length": 24, "name": "h3", "offset": 0}
    ]


def test_render_round_trips_float32_values_and_support_codes() -> None:
    decoded = codec.decode(_render(), tier="render")
    assert decoded.columns["support"] == (0, 2, 3)
    expected = struct.unpack("<3f", struct.pack("<3f", *VALUES["post_mean"]))
    assert decoded.columns["post_mean"] == expected
    assert decoded.header["artifact"] == ARTIFACT
    assert decoded.header["resolution"] == 3
    header, area = _split(_render())
    assert [(c["name"], c["offset"], c["length"]) for c in header["columns"]] == [
        ("support", 0, 3),
        ("post_mean", 8, 12),
        ("post_sd", 24, 12),
    ]
    assert area[3:8] == bytes(5)  # zero padding between columns


def test_detail_round_trips_float64_bit_for_bit_including_out_of_domain_values() -> None:
    decoded = codec.decode(_detail(), tier="detail")
    for field in codec.DETAIL_FIELDS:
        assert struct.pack("<3d", *decoded.columns[field]) == struct.pack("<3d", *VALUES[field])
    assert decoded.columns["post_mean"][1] > ARTIFACT["metric_domains"]["post_mean"][1]


def test_encoding_is_byte_deterministic() -> None:
    assert _grid() == _grid()
    assert _render() == _render()
    assert _detail() == _detail()


def test_header_is_canonical_sorted_compact_utf8_json() -> None:
    data = _render(**{})
    (length,) = struct.unpack_from("<I", data, 8)
    text = data[12 : 12 + length]
    header = json.loads(text)
    assert text == json.dumps(header, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    assert set(header) == set(codec.HEADER_KEYS)


@pytest.mark.parametrize(
    ("mutate", "tier", "code"),
    [
        (lambda d: d[:8], "grid", "truncated"),
        (lambda d: b"GOSB" + d[4:], "grid", "magic"),
        (lambda d: d[:4] + b"\x02\x00" + d[6:], "grid", "format_version"),
        (lambda d: d[:6] + b"\x01\x00" + d[8:], "grid", "reserved"),
        (lambda d: d[:8] + struct.pack("<I", 10_000) + d[12:], "grid", "truncated"),
        (lambda d: d + b"\x00", "grid", "trailing_bytes"),
        (lambda d: d[:-1], "grid", "truncated"),
        (lambda d: d, "render", "tier"),
    ],
)
def test_preamble_framing_and_tier_refusals(mutate, tier: str, code: str) -> None:
    assert _code(mutate(_grid()), tier) == code


def test_header_encoding_json_and_schema_refusals() -> None:
    render = _render()
    (length,) = struct.unpack_from("<I", render, 8)
    end = 12 + length
    at = render.index(b'"tier":"render"') + 9
    assert _code(render[:at] + b"\xff" + render[at + 1 :], "render") == "header_encoding"
    assert _code(render[: end - 1] + b" " + render[end:], "render") == "header_json"
    header, area = _split(render)
    assert _code(_frame([header], area), "render") == "header_schema"
    nan_header = json.dumps(header, sort_keys=True, separators=(",", ":")).replace(
        '"n_cells":3', '"n_cells":NaN'
    )
    text = nan_header.encode()
    raw = b"GOSA" + struct.pack("<HHI", 1, 0, len(text)) + text
    assert _code(raw + bytes(((len(raw) + 7) & ~7) - len(raw)) + area, "render") == "header_json"
    for edit in (
        lambda h: h.update(extra=1),
        lambda h: h.pop("tier"),
        lambda h: h.update(n_cells=True),
        lambda h: h.update(n_cells=-1),
        lambda h: h.update(n_cells=2**53),
        lambda h: h.update(schema_version=2),
        lambda h: h.update(resolution=16),
        lambda h: h.update(tier="preview"),
        lambda h: h.update(grid_sha256="A" * 64),
        lambda h: h.update(grid_sha256="a" * 64 + "\n"),  # Python's `$` also matches before a final "\n"
        lambda h: h.update(source_surface_sha256=None),
        lambda h: h.update(source_surface_sha256=SOURCE_SHA + "\n"),
        lambda h: h["columns"][0].update(extra=1),
        lambda h: h["columns"][0].update(length="3"),
    ):
        assert _code(_edit_header(render, edit), "render") == "header_schema"
    assert _code(_edit_header(_grid(), lambda h: h.update(artifact=ARTIFACT)), "grid") == "header_schema"


def test_integral_float_header_numbers_are_read_as_javascript_reads_them() -> None:
    render = _render()
    header, area = _split(render)
    header["n_cells"] = 3.0
    assert codec.decode(_frame(header, area), tier="render").header["n_cells"] == 3


def test_integers_past_float64_precision_are_read_as_javascript_reads_them() -> None:
    header, area = _split(_render())
    text = json.dumps(header, sort_keys=True, separators=(",", ":"))
    # CPython refuses int literals over 4,300 digits; JSON.parse reads Infinity, no safe integer.
    huge = "1" + "0" * 5000
    n_cells = _frame_text(text.replace('"n_cells":3', f'"n_cells":{huge}'), area)
    assert _code(n_cells, "render") == "header_schema"
    assert _code(_frame_text(text.replace("[0.0119,0.1804]", f"[0,{huge}]"), area), "render") == "identity"
    # 2**53 + 1 and 2**53 are one double, so to JavaScript this domain is ordered.
    header["artifact"]["metric_domains"]["post_mean"] = [2**53 + 1, 2**53]
    assert codec.decode(_frame(header, area), tier="render")


def test_deep_headers_reach_the_schema_checks_as_json_parse_lets_them() -> None:
    # V8's JSON.parse has no nesting limit; CPython's C parser raises RecursionError.
    header, area = _split(_render())
    text = json.dumps(header, sort_keys=True, separators=(",", ":"))
    deep = "[" * 100_000 + "]" * 100_000
    assert _code(_frame_text(deep, area), "render") == "header_schema"
    n_cells = _frame_text(text.replace('"n_cells":3', f'"n_cells":{deep}'), area)
    assert _code(n_cells, "render") == "header_schema"
    label = _frame_text(text.replace('"label":"HbS (rs334) fixture"', f'"label":{deep}'), area)
    assert _code(label, "render") == "identity"
    assert _code(label, "detail") == "tier"
    unclosed = text.replace('"n_cells":3', f'"n_cells":{deep[:-1]}')
    assert _code(_frame_text(unclosed, area), "render") == "header_json"


def test_identity_refusals_mirror_the_zod_artifact_identity_schema() -> None:
    render = _render()
    for edit in (
        lambda h: h["artifact"].pop("label"),
        lambda h: h["artifact"].update(label="   "),
        lambda h: h["artifact"].update(label="\ufeff"),  # trim() strips U+FEFF; str.strip() keeps it
        lambda h: h["artifact"].update(label="\u3000\u2028"),
        lambda h: h["artifact"].update(colour="red"),
        lambda h: h["artifact"].update(artifact_format=4),
        lambda h: h["artifact"].update(artifact_format=True),
        lambda h: h["artifact"].pop("target_grid_version"),
        lambda h: h["artifact"].update(entity_type="cell"),
        lambda h: h["artifact"].update(measurement="frequency"),
        lambda h: h["artifact"].update(entity_type=["variant"]),  # unhashable: no TypeError
        lambda h: h["artifact"].update(measurement={"allele_frequency": 1}),
        lambda h: h["artifact"]["metric_domains"].update(post_mean=[0.2, 0.1]),
        lambda h: h["artifact"]["metric_domains"].update(post_sd=[0.1]),
        lambda h: h["artifact"]["metric_domains"].update(post_mean=[0, 10**400]),  # JSON.parse: Infinity
        lambda h: h["artifact"].update(resolution=4),
    ):
        assert _code(_edit_header(render, edit), "render") == "identity"
    for label in ("\x1c", "\x85"):  # str.isspace() is true for these; ECMAScript trim() keeps them
        assert codec.decode(
            _edit_header(render, lambda h, label=label: h["artifact"].update(label=label)), tier="render"
        )
    format_one = {key: value for key, value in ARTIFACT.items() if not key.startswith("target_grid")}
    assert codec.decode(
        _edit_header(render, lambda h: h.update(artifact=format_one | {"artifact_format": 1})), tier="render"
    )


def test_column_list_length_offset_and_padding_refusals() -> None:
    render = _render()
    swap = lambda h: (h["columns"][1].update(name="post_sd"), h["columns"][2].update(name="post_mean"))  # noqa: E731
    assert _code(_edit_header(render, swap), "render") == "columns"
    assert _code(_edit_header(render, lambda h: h["columns"][1].update(dtype="f64")), "render") == "columns"
    assert (
        _code(_edit_header(render, lambda h: h["columns"][1].update(encoding="raw")), "render") == "columns"
    )
    assert _code(_edit_header(render, lambda h: h["columns"].pop()), "render") == "columns"
    assert (
        _code(_edit_header(render, lambda h: h["columns"].append(dict(h["columns"][2]))), "render")
        == "columns"
    )
    assert (
        _code(_edit_header(render, lambda h: h["columns"][0].update(length=2)), "render") == "column_length"
    )
    assert _code(_edit_header(render, lambda h: h["columns"][1].update(offset=16)), "render") == "offset"
    header, area = _split(render)
    assert _code(_frame(header, area[:3] + b"\x01" + area[4:]), "render") == "padding"
    (length,) = struct.unpack_from("<I", render, 8)
    if (12 + length) % 8:
        assert _code(render[: 12 + length] + b"\x01" + render[13 + length :], "render") == "padding"


def _grid_bytes(cells: list[int], planes: range = range(8)) -> bytes:
    header, _ = _split(_grid())
    header["grid_sha256"] = hashlib.sha256(struct.pack(f"<{len(cells)}Q", *cells)).hexdigest()
    deltas = [cells[0], *(b - a for a, b in zip(cells, cells[1:], strict=False))]
    raw = struct.pack(f"<{len(deltas)}Q", *deltas)
    return _frame(header, b"".join(raw[plane::8] for plane in planes))


def test_grid_order_and_h3_validity_refusals() -> None:
    first, second, last = CELLS
    assert _code(_grid_bytes([first, first, last]), "grid") == "grid_order"
    # Most-significant plane first: byte-swapped deltas overflow or name invalid cells.
    assert _code(_grid_bytes(list(CELLS), range(7, -1, -1)), "grid") in {"grid_order", "h3_cell"}
    for bad in (
        last | 1 << 63,  # reserved bit
        (last & ~(0xF << 59)) | 2 << 59,  # mode 2 (directed edge)
        last | 7 << 36,  # digit 7 inside the resolution
        (last & ~(0x7F << 45)) | 122 << 45,  # base cell 122
        0x84390CFFFFFFFFF | 0x1FFFFFFFF,  # a valid resolution-4 cell
    ):
        assert _code(_grid_bytes([first, second, bad]), "grid") == "h3_cell"
    assert _code(_edit_header(_grid(), lambda h: h.update(grid_sha256="0" * 64)), "grid") == "grid_sha256"


def _with_value(data: bytes, name: str, row: int, value: float) -> bytes:
    header, area = _split(data)
    column = next(c for c in header["columns"] if c["name"] == name)
    fmt, width = {"u8": ("B", 1), "f32": ("f", 4), "f64": ("d", 8)}[column["dtype"]]
    payload = area[column["offset"] : column["offset"] + column["length"]]
    count = len(payload) // width
    raw = bytes(payload[plane * count + i] for i in range(count) for plane in range(width))
    values = list(struct.unpack(f"<{count}{fmt}", raw))
    values[row] = value
    raw = struct.pack(f"<{count}{fmt}", *values)
    shuffled = b"".join(raw[plane::width] for plane in range(width))
    start = column["offset"]
    return _frame(header, area[:start] + shuffled + area[start + len(shuffled) :])


def test_value_refusals_in_column_then_row_order() -> None:
    assert _code(_with_value(_render(), "support", 0, 4), "render") == "support_code"
    assert _code(_with_value(_render(), "post_mean", 0, float("nan")), "render") == "non_finite"
    assert _code(_with_value(_render(), "post_sd", 0, float("inf")), "render") == "non_finite"
    assert _code(_with_value(_render(), "post_mean", 2, 1.5), "render") == "value_range"
    assert _code(_with_value(_detail(), "post_sd", 0, -0.01), "detail") == "value_range"
    assert _code(_with_value(_detail(), "q975", 0, 1.01), "detail") == "value_range"
    assert _code(_with_value(_detail(), "posterior_contraction", 0, -1e-9), "detail") == "value_range"
    assert _code(_with_value(_detail(), "dist_nearest_obs_km", 0, -0.5), "detail") == "value_range"
    assert _code(_with_value(_detail(), "q025", 0, 0.2), "detail") == "interval_order"
    assert _code(_with_value(_detail(), "q975", 0, 0.1), "detail") == "interval_order"
    # The first failing column wins: post_mean NaN is reported before a negative post_sd.
    both = _with_value(_with_value(_detail(), "post_sd", 0, -1.0), "post_mean", 2, float("nan"))
    assert _code(both, "detail") == "non_finite"


def test_encoders_refuse_what_the_decoder_would_refuse() -> None:
    with pytest.raises(codec.GosaError, match="grid not strictly increasing"):
        codec.encode_grid([CELLS[1], CELLS[0]], 3)
    with pytest.raises(codec.GosaError) as error:
        codec.encode_grid([*CELLS[:2], 0x84390CFFFFFFFFF | 0x1FFFFFFFF], 3)
    assert error.value.code == "h3_cell"
    with pytest.raises(codec.GosaError) as error:
        _render(support=["observed", "nearby", "unknown"])
    assert error.value.code == "support_code"
    with pytest.raises(codec.GosaError) as error:
        _render(post_sd=[0.0153, 1e300, 0.0087])
    assert error.value.code == "non_finite"
    with pytest.raises(codec.GosaError) as error:
        _detail(q025=[0.2, 0.0982, 0.0119])
    assert error.value.code == "interval_order"
    with pytest.raises(codec.GosaError) as error:
        _detail(post_sd=[0.0153, 0.0917])
    assert error.value.code == "column_length"
    with pytest.raises(codec.GosaError) as error:
        codec.encode_render(
            artifact={**ARTIFACT, "label": ""},
            source_surface_sha256=SOURCE_SHA,
            grid_sha256=codec.grid_sha256(CELLS),
            support=VALUES["support"],
            post_mean=VALUES["post_mean"],
            post_sd=VALUES["post_sd"],
        )
    assert error.value.code == "identity"


def _render_with(artifact: dict[str, Any], source_surface_sha256: str = SOURCE_SHA) -> bytes:
    return codec.encode_render(
        artifact=artifact,
        source_surface_sha256=source_surface_sha256,
        grid_sha256=codec.grid_sha256(CELLS),
        support=VALUES["support"],
        post_mean=VALUES["post_mean"],
        post_sd=VALUES["post_sd"],
    )


def test_encoders_write_one_encoding_per_javascript_number() -> None:
    integral_float: Any = 3.0
    assert codec.encode_grid(CELLS, integral_float) == _grid()
    assert _render_with({**ARTIFACT, "artifact_format": 2.0, "resolution": 3.0}) == _render()
    ints = {**ARTIFACT, "metric_domains": {"post_mean": [0, 1], "post_sd": [0.0, 1.0]}}
    floats = {**ARTIFACT, "metric_domains": {"post_mean": [0.0, 1.0], "post_sd": [0, 1]}}
    assert _render_with(ints) == _render_with(floats)


def test_untyped_values_fail_with_gosa_codes() -> None:
    domain = [0.0087, 0.0279]
    for change, code in (
        ({"label": "HbS \ud800"}, "header_encoding"),  # a lone surrogate has no UTF-8 form
        ({"entity_type": ["variant"]}, "identity"),
        ({"metric_domains": {"post_mean": [0, 10**400], "post_sd": domain}}, "identity"),
        ({"metric_domains": {"post_mean": [0, 10**5000], "post_sd": domain}}, "identity"),
    ):
        with pytest.raises(codec.GosaError) as error:
            _render_with({**ARTIFACT, **change})
        assert error.value.code == code
    with pytest.raises(codec.GosaError) as error:
        _render_with(ARTIFACT, source_surface_sha256=SOURCE_SHA + "\n")
    assert error.value.code == "header_schema"
    with pytest.raises(codec.GosaError) as error:  # its message must not repr a 5,001-digit int
        _render(support=["observed", 10**5000, "unknown"])
    assert error.value.code == "support_code"
    # JSON.parse reads an escaped lone surrogate and zod accepts it, so the decoder does too.
    header, area = _split(_render())
    header["artifact"]["label"] = "HbS \ud800"
    assert codec.decode(_frame(header, area), tier="render").header["artifact"]["label"] == "HbS \ud800"


def test_error_codes_are_a_closed_vocabulary() -> None:
    with pytest.raises(ValueError, match="unknown GOSA error code"):
        codec.GosaError("nearly", "not a code")
    assert len(set(codec.GOSA_ERROR_CODES)) == len(codec.GOSA_ERROR_CODES)
