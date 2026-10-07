"""GOSA v1 binary containers for the Atlas web rendition (Atlas design §11; fast-load spec §B.3).

The static globe fetches immutable, content-addressed tiers instead of the 20 MB canonical surface
JSON: one shared ``grid`` (sorted u64 H3 indices), a ``render`` tier (u8 support codes plus float32
``post_mean``/``post_sd``, used only for colour, height and bins) and a ``detail`` tier (the six
float64 summaries, the only source of displayed numbers). The canonical JSON stays the citable
download; these containers are a derived rendition of it and never replace it.

Layout, little-endian throughout: ``b"GOSA"``, u16 ``format_version`` (1), u16 ``reserved`` (0), u32
``header_length``, the canonical UTF-8 JSON header, zero padding to an 8-byte boundary, then the
column payloads at minimal 8-aligned offsets with zero padding between them and no trailing bytes.
A container is defined and hashed uncompressed; transport compression belongs to the server.

Pure: standard library plus ``h3``, no I/O. Every refusal is a :class:`GosaError` whose ``code``
names the hard error (spec v1 §12: schema violations are hard errors). ``GOSA_ERROR_CODES`` lists
the codes in the order the checks run; the TypeScript decoder runs the same checks in the same
order, and the shared mutation corpus in ``tests/fixtures/atlas-web/mutations/`` pins both. Values
outside ``metric_domains`` are valid: colour and height clamp, displayed numbers do not.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import struct
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from h3.api import basic_int as h3int

from genomeos.publication.ecmascript import json_parse, trim

MAGIC = b"GOSA"
FORMAT_VERSION = 1
SCHEMA_VERSION = 1
PREAMBLE_BYTES = 12
TIERS: tuple[str, ...] = ("grid", "render", "detail")

#: u8 support codes, in ``genomeos.surfaces.mask.SUPPORT_STATES`` and zod ``supportSchema`` order.
SUPPORT_CODES: tuple[str, ...] = ("observed", "interpolated", "prior_dominated", "unknown")

DETAIL_FIELDS: tuple[str, ...] = (
    "post_mean", "post_sd", "q025", "q975", "posterior_contraction", "dist_nearest_obs_km",
)

#: The normative column list per tier: (name, dtype, encoding), in this order and no other.
TIER_COLUMNS: dict[str, tuple[tuple[str, str, str], ...]] = {
    "grid": (("h3", "u64", "delta_shuffle"),),
    "render": (("support", "u8", "raw"), ("post_mean", "f32", "shuffle"), ("post_sd", "f32", "shuffle")),
    "detail": tuple((field, "f64", "shuffle") for field in DETAIL_FIELDS),
}

#: Hard-error codes in the order the checks run; a container breaking several rules is refused
#: with the first. The last four are context checks (``verify_artifact_tiers``, ``verify_container``).
GOSA_ERROR_CODES: tuple[str, ...] = (
    "truncated", "magic", "format_version", "reserved", "header_encoding", "header_json",
    "header_schema", "tier", "identity", "columns", "column_length", "offset", "trailing_bytes",
    "padding", "grid_order", "h3_cell", "grid_sha256", "support_code", "non_finite", "value_range",
    "interval_order", "n_cells", "source_sha256", "cross_tier", "container_sha256",
)

HEADER_KEYS = frozenset(
    {"artifact", "columns", "grid_sha256", "n_cells", "resolution", "schema_version",
     "source_surface_sha256", "tier"}
)
COLUMN_KEYS = frozenset({"dtype", "encoding", "length", "name", "offset"})

_WIDTH = {"u8": 1, "f32": 4, "f64": 8, "u64": 8}
_STRUCT = {"u8": "B", "f32": "f", "f64": "d", "u64": "Q"}
_PROBABILITY_FIELDS = frozenset({"post_mean", "q025", "q975"})
_MAX_SAFE_INTEGER = 2**53 - 1
_U64_LIMIT = 2**64
_BOM = chr(0xFEFF)
_SHA256 = re.compile(r"[0-9a-f]{64}")  # used with fullmatch: `$` also matches before a final "\n"
_IDENTITY_OPTIONAL = frozenset({"target_grid_source", "target_grid_version"})
_IDENTITY_TEXT = (
    "data_version", "hf_dataset", "hf_revision", "id", "label", "model_version",
    "registry_version", "variant_id",
)
_IDENTITY_REQUIRED = frozenset(
    {*_IDENTITY_TEXT, "artifact_format", "entity_type", "measurement", "metric_domains", "resolution"}
)
_ENTITY_TYPES = frozenset({"variant", "allele", "gene", "phenotype"})
_MEASUREMENTS = frozenset({"allele_frequency", "carrier_frequency", "phenotype_frequency"})


class GosaError(ValueError):
    """A GOSA container, or the values offered to an encoder, violate the v1 contract."""

    def __init__(self, code: str, message: str) -> None:
        if code not in GOSA_ERROR_CODES:
            raise ValueError(f"unknown GOSA error code {code!r}")
        super().__init__(f"{code}: {message}")
        self.code = code


@dataclass(frozen=True)
class GosaContainer:
    """A decoded, fully validated container; ``columns`` maps each name to its values."""

    tier: str
    header: dict[str, Any]
    columns: dict[str, tuple]


def _align8(value: int) -> int:
    return (value + 7) & ~7


def _safe_int(value: Any) -> int | None:
    """A JSON integer as JavaScript reads it: non-negative, safe, never a boolean."""
    if isinstance(value, bool):
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return value if isinstance(value, int) and 0 <= value <= _MAX_SAFE_INTEGER else None


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and _SHA256.fullmatch(value) is not None


def _is_text(value: Any) -> bool:
    return isinstance(value, str) and bool(trim(value))  # zod nonEmpty trims as ECMAScript does


def _is_finite_number(value: Any) -> bool:
    """A finite JS number; an ``int`` past the float64 range is JavaScript's ``Infinity``."""
    if not isinstance(value, int | float) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def validate_identity(artifact: Any) -> None:
    """Refuse an ``artifact`` that the strict zod ``artifactIdentitySchema`` would refuse."""
    if not isinstance(artifact, dict):
        raise GosaError("identity", "artifact must be an object")
    missing = _IDENTITY_REQUIRED - set(artifact)
    unknown = set(artifact) - _IDENTITY_REQUIRED - _IDENTITY_OPTIONAL
    if missing or unknown:
        raise GosaError("identity", f"artifact keys: missing {sorted(missing)}, unknown {sorted(unknown)}")
    artifact_format = _safe_int(artifact["artifact_format"])
    if artifact_format not in {1, 2, 3}:
        raise GosaError("identity", "artifact_format must be 1, 2 or 3")
    for field in (*_IDENTITY_TEXT, *sorted(_IDENTITY_OPTIONAL & set(artifact))):
        if not _is_text(artifact[field]):
            raise GosaError("identity", f"artifact {field} must be non-empty text")
    for field, allowed in (("entity_type", _ENTITY_TYPES), ("measurement", _MEASUREMENTS)):
        if not isinstance(artifact[field], str) or artifact[field] not in allowed:
            raise GosaError("identity", f"artifact {field} must be one of {sorted(allowed)}")
    resolution = _safe_int(artifact["resolution"])
    if resolution is None or resolution > 15:
        raise GosaError("identity", "artifact resolution must be an integer in [0, 15]")
    domains = artifact["metric_domains"]
    if not isinstance(domains, dict) or set(domains) != {"post_mean", "post_sd"}:
        raise GosaError("identity", "metric_domains must hold exactly post_mean and post_sd")
    for metric, domain in domains.items():
        if (
            not isinstance(domain, list)
            or len(domain) != 2
            or not all(_is_finite_number(bound) for bound in domain)
            or float(domain[0]) > float(domain[1])  # as the doubles JavaScript compares
        ):
            raise GosaError("identity", f"metric_domains.{metric} must be an ordered finite pair")
    if artifact_format >= 2 and not _IDENTITY_OPTIONAL <= set(artifact):
        raise GosaError("identity", "artifact formats 2 and 3 require target-grid source and version")


def _pack_values(values: Sequence[Any], dtype: str, name: str) -> bytes:
    if dtype == "u64" and not all(type(value) is int for value in values):
        raise GosaError("h3_cell", f"{name} must hold only integers")
    if dtype in {"f32", "f64"} and not all(_is_number(value) for value in values):
        raise GosaError("non_finite", f"{name} must hold only numbers")
    try:
        return struct.pack(f"<{len(values)}{_STRUCT[dtype]}", *values)
    except OverflowError as error:  # a finite float64 beyond the float32 range
        raise GosaError("non_finite", f"{name} does not fit {dtype}: {error}") from error
    except struct.error as error:  # an integer outside [0, 2**64)
        raise GosaError("h3_cell", f"{name} does not fit {dtype}: {error}") from error


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def grid_sha256(h3: Sequence[int]) -> str:
    """SHA-256 of the grid's decoded little-endian u64 column (n x 8 bytes)."""
    return hashlib.sha256(_pack_values(h3, "u64", "h3")).hexdigest()


def container_sha256(data: bytes) -> str:
    """The digest a catalog declares for a container: SHA-256 of its uncompressed bytes."""
    return hashlib.sha256(data).hexdigest()


def _shuffle(raw: bytes, width: int) -> bytes:
    """``encoded[k*n + i] = raw[i*width + k]``: plane k holds byte k (LSB first) of every element."""
    count = len(raw) // width
    out = bytearray(len(raw))
    target, source = memoryview(out), memoryview(raw)
    for plane in range(width):
        target[plane * count : (plane + 1) * count] = source[plane::width]
    return bytes(out)


def _unshuffle(encoded: memoryview, width: int) -> bytes:
    count = len(encoded) // width
    out = bytearray(len(encoded))
    target = memoryview(out)
    for plane in range(width):
        target[plane::width] = encoded[plane * count : (plane + 1) * count]
    return bytes(out)


def _pack(header: Mapping[str, Any], payloads: Sequence[bytes]) -> bytes:
    columns: list[dict[str, Any]] = []
    offset = 0
    for (name, dtype, encoding), payload in zip(TIER_COLUMNS[header["tier"]], payloads, strict=True):
        columns.append(
            {"dtype": dtype, "encoding": encoding, "length": len(payload), "name": name, "offset": offset}
        )
        offset = _align8(offset + len(payload))
    try:
        text = json.dumps(
            {**header, "columns": columns},
            sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False,
        ).encode("utf-8")
    except UnicodeEncodeError as error:  # a lone surrogate in an artifact string
        raise GosaError("header_encoding", f"header text has no UTF-8 form: {error}") from error
    out = bytearray(MAGIC + struct.pack("<HHI", FORMAT_VERSION, 0, len(text)) + text)
    out += bytes(_align8(len(out)) - len(out))
    start = len(out)
    for column, payload in zip(columns, payloads, strict=True):
        out += bytes(start + column["offset"] - len(out))
        out += payload
    return bytes(out)


def _require_cells(columns: Mapping[str, Sequence[Any]]) -> int:
    lengths = {name: len(values) for name, values in columns.items()}
    if len(set(lengths.values())) != 1 or not next(iter(lengths.values())):
        raise GosaError("column_length", f"columns need one equal, non-zero length: {lengths}")
    return next(iter(lengths.values()))


def _artifact_header(
    tier: str, artifact: Mapping[str, Any], source_surface_sha256: str, grid_sha: str, count: int
) -> dict[str, Any]:
    validate_identity(dict(artifact))
    if not _is_sha256(source_surface_sha256) or not _is_sha256(grid_sha):
        raise GosaError("header_schema", "source_surface_sha256 and grid_sha256 must be sha256 hex")
    # One encoding per JavaScript value: integers are written 3 (never 3.0), domain bounds 1.0.
    canonical = {
        **artifact, "artifact_format": _safe_int(artifact["artifact_format"]),
        "metric_domains": {
            key: [float(bound) for bound in pair] for key, pair in artifact["metric_domains"].items()
        },
        "resolution": _safe_int(artifact["resolution"]),
    }
    return {
        "artifact": canonical, "grid_sha256": grid_sha, "n_cells": count,
        "resolution": canonical["resolution"], "schema_version": SCHEMA_VERSION,
        "source_surface_sha256": source_surface_sha256, "tier": tier,
    }


def encode_grid(h3: Sequence[int], resolution: int) -> bytes:
    """Encode the shared, strictly increasing H3 grid; refuse anything ``decode`` would refuse."""
    values = list(h3)
    count = _require_cells({"h3": values})
    level = _safe_int(resolution)  # written as an int, so 3.0 and 3 give one container
    if level is None or level > 15:
        raise GosaError("header_schema", "resolution must be an integer in [0, 15]")
    raw = _pack_values(values, "u64", "h3")
    for row in range(1, count):
        if values[row] <= values[row - 1]:
            raise GosaError("grid_order", f"grid not strictly increasing at row {row}")
    deltas = [values[0], *(values[row] - values[row - 1] for row in range(1, count))]
    header = {
        "artifact": None, "grid_sha256": hashlib.sha256(raw).hexdigest(), "n_cells": count,
        "resolution": level, "schema_version": SCHEMA_VERSION, "source_surface_sha256": None,
        "tier": "grid",
    }
    data = _pack(header, [_shuffle(_pack_values(deltas, "u64", "h3"), 8)])
    decode(data, tier="grid")
    return data


def encode_render(
    *,
    artifact: Mapping[str, Any],
    source_surface_sha256: str,
    grid_sha256: str,
    support: Sequence[str],
    post_mean: Sequence[float],
    post_sd: Sequence[float],
) -> bytes:
    """Encode the render tier: float32 values for colour, height and bins only (spec §B.2)."""
    count = _require_cells({"support": support, "post_mean": post_mean, "post_sd": post_sd})
    codes = []
    for row, state in enumerate(support):
        if not isinstance(state, str) or state not in SUPPORT_CODES:
            shown = repr(state) if isinstance(state, str) else type(state).__name__  # repr(10**5000) raises
            raise GosaError("support_code", f"row {row}: unknown support state {shown}")
        codes.append(SUPPORT_CODES.index(state))
    header = _artifact_header("render", artifact, source_surface_sha256, grid_sha256, count)
    payloads = [bytes(codes)]
    for name, values in (("post_mean", post_mean), ("post_sd", post_sd)):
        payloads.append(_shuffle(_pack_values(list(values), "f32", name), 4))
    data = _pack(header, payloads)
    decode(data, tier="render")
    return data


def encode_detail(
    *,
    artifact: Mapping[str, Any],
    source_surface_sha256: str,
    grid_sha256: str,
    post_mean: Sequence[float],
    post_sd: Sequence[float],
    q025: Sequence[float],
    q975: Sequence[float],
    posterior_contraction: Sequence[float],
    dist_nearest_obs_km: Sequence[float],
) -> bytes:
    """Encode the detail tier: the six float64 summaries, bit-identical to the canonical JSON."""
    columns = {
        "post_mean": list(post_mean), "post_sd": list(post_sd), "q025": list(q025),
        "q975": list(q975), "posterior_contraction": list(posterior_contraction),
        "dist_nearest_obs_km": list(dist_nearest_obs_km),
    }
    count = _require_cells(columns)
    header = _artifact_header("detail", artifact, source_surface_sha256, grid_sha256, count)
    data = _pack(header, [_shuffle(_pack_values(columns[name], "f64", name), 8) for name in DETAIL_FIELDS])
    decode(data, tier="detail")
    return data


def _parse_header(raw: memoryview) -> Any:
    try:
        text = bytes(raw).decode("utf-8")
    except UnicodeDecodeError as error:
        raise GosaError("header_encoding", f"header is not valid UTF-8: {error}") from error
    # TextDecoder('utf-8', {fatal: true}) consumes one leading BOM; mirror it exactly.
    try:
        return json_parse(text.removeprefix(_BOM))  # JSON.parse numbers and depth, not CPython's
    except ValueError as error:
        raise GosaError("header_json", f"header is not valid JSON: {error}") from error


def _normalized_header(header: Any) -> dict[str, Any]:
    """Check the strict header schema; return it with every integer field as a Python ``int``."""
    if not isinstance(header, dict) or set(header) != HEADER_KEYS:
        keys = sorted(header) if isinstance(header, dict) else type(header).__name__
        raise GosaError("header_schema", f"header keys must be exactly {sorted(HEADER_KEYS)}, got {keys}")
    ints = {key: _safe_int(header[key]) for key in ("schema_version", "n_cells", "resolution")}
    if ints["schema_version"] != SCHEMA_VERSION or ints["n_cells"] is None:
        raise GosaError("header_schema", "schema_version must be 1 and n_cells a safe integer")
    if ints["resolution"] is None or ints["resolution"] > 15:
        raise GosaError("header_schema", "resolution must be an integer in [0, 15]")
    if header["tier"] not in TIERS or not _is_sha256(header["grid_sha256"]):
        raise GosaError("header_schema", "tier must be grid, render or detail; grid_sha256 sha256 hex")
    if not isinstance(header["columns"], list):
        raise GosaError("header_schema", "columns must be a list")
    columns = []
    for column in header["columns"]:
        if not isinstance(column, dict) or set(column) != COLUMN_KEYS:
            raise GosaError("header_schema", f"each column must hold exactly {sorted(COLUMN_KEYS)}")
        if not all(isinstance(column[key], str) for key in ("dtype", "encoding", "name")):
            raise GosaError("header_schema", "column name, dtype and encoding must be strings")
        length, offset = _safe_int(column["length"]), _safe_int(column["offset"])
        if length is None or offset is None:
            raise GosaError("header_schema", "column length and offset must be safe integers")
        columns.append({**column, "length": length, "offset": offset})
    if header["tier"] == "grid":
        if header["artifact"] is not None or header["source_surface_sha256"] is not None:
            raise GosaError("header_schema", "a grid carries a null artifact and source_surface_sha256")
    elif not isinstance(header["artifact"], dict) or not _is_sha256(header["source_surface_sha256"]):
        raise GosaError("header_schema", "render and detail carry an artifact and source_surface_sha256")
    return {**header, **ints, "columns": columns}


def _check_layout(view: memoryview, header: dict[str, Any], header_end: int) -> int:
    """Check columns, lengths, offsets, file length and padding; return the column-area start."""
    columns = header["columns"]
    expected = [list(spec) for spec in TIER_COLUMNS[header["tier"]]]
    actual = [[column["name"], column["dtype"], column["encoding"]] for column in columns]
    if actual != expected:
        raise GosaError("columns", f"columns {actual} are not the normative {expected}")
    for column in columns:
        if column["length"] != header["n_cells"] * _WIDTH[column["dtype"]]:
            raise GosaError("column_length", f"{column['name']}: length is not n_cells x width")
    offset = 0
    for column in columns:
        if column["offset"] != offset:
            raise GosaError("offset", f"{column['name']}: offset {column['offset']} is not {offset}")
        offset = _align8(offset + column["length"])
    start = _align8(header_end)
    end = start + columns[-1]["offset"] + columns[-1]["length"]
    if len(view) < end:
        raise GosaError("truncated", f"container is {len(view)} bytes; columns end at {end}")
    if len(view) > end:
        raise GosaError("trailing_bytes", f"{len(view) - end} bytes follow the last column")
    gaps = [(header_end, start)] + [
        (start + previous["offset"] + previous["length"], start + column["offset"])
        for previous, column in zip(columns, columns[1:], strict=False)
    ]
    for low, high in gaps:
        if any(view[low:high]):
            raise GosaError("padding", f"non-zero padding byte in [{low}, {high})")
    return start


def _decode_grid(payload: memoryview, header: dict[str, Any]) -> tuple[int, ...]:
    deltas = struct.unpack(f"<{header['n_cells']}Q", _unshuffle(payload, 8))
    values = []
    total = 0
    for row, delta in enumerate(deltas):
        if row and delta == 0:
            raise GosaError("grid_order", f"grid not strictly increasing at row {row} (zero delta)")
        total += delta
        if total >= _U64_LIMIT:
            raise GosaError("grid_order", f"grid not strictly increasing at row {row} (overflow)")
        values.append(total)
    resolution = header["resolution"]
    for row, cell in enumerate(values):
        if not h3int.is_valid_cell(cell) or h3int.get_resolution(cell) != resolution:
            raise GosaError("h3_cell", f"row {row}: {cell:x} is not a valid resolution-{resolution} cell")
    if grid_sha256(values) != header["grid_sha256"]:
        raise GosaError("grid_sha256", "decoded grid does not match the header grid_sha256")
    return tuple(values)


def _decode_floats(payload: memoryview, dtype: str, name: str, count: int) -> tuple[float, ...]:
    values = struct.unpack(f"<{count}{_STRUCT[dtype]}", _unshuffle(payload, _WIDTH[dtype]))
    probability = name in _PROBABILITY_FIELDS
    for row, value in enumerate(values):
        if not math.isfinite(value):
            raise GosaError("non_finite", f"{name} row {row} is not finite")
        if value < 0 or (probability and value > 1):
            bounds = "in [0, 1]" if probability else "non-negative"
            raise GosaError("value_range", f"{name} row {row} = {value!r} must be {bounds}")
    return values


def decode(data: bytes, *, tier: str) -> GosaContainer:
    """Decode and fully validate a container of the requested ``tier`` (checks run in code order)."""
    if tier not in TIERS:
        raise ValueError(f"unknown tier {tier!r}")
    view = memoryview(data)
    if len(view) < PREAMBLE_BYTES:
        raise GosaError("truncated", "shorter than the 12-byte preamble")
    if bytes(view[:4]) != MAGIC:
        raise GosaError("magic", f"magic {bytes(view[:4])!r} is not b'GOSA'")
    version, reserved, header_length = struct.unpack_from("<HHI", view, 4)
    if version != FORMAT_VERSION:
        raise GosaError("format_version", f"format_version {version} is not {FORMAT_VERSION}")
    if reserved != 0:
        raise GosaError("reserved", f"reserved is {reserved}, not 0")
    header_end = PREAMBLE_BYTES + header_length
    if header_end > len(view):
        raise GosaError("truncated", "header extends past the end of the container")
    header = _normalized_header(_parse_header(view[PREAMBLE_BYTES:header_end]))
    if header["tier"] != tier:
        raise GosaError("tier", f"container tier {header['tier']!r} is not the requested {tier!r}")
    if tier != "grid":
        validate_identity(header["artifact"])
        if _safe_int(header["artifact"]["resolution"]) != header["resolution"]:
            raise GosaError("identity", "header resolution differs from artifact.resolution")
    start = _check_layout(view, header, header_end)
    payloads = {
        column["name"]: view[start + column["offset"] : start + column["offset"] + column["length"]]
        for column in header["columns"]
    }
    if tier == "grid":
        return GosaContainer(tier, header, {"h3": _decode_grid(payloads["h3"], header)})
    columns: dict[str, tuple] = {}
    if tier == "render":
        columns["support"] = tuple(payloads["support"])
        for row, code in enumerate(columns["support"]):
            if code >= len(SUPPORT_CODES):
                raise GosaError("support_code", f"support row {row} has code {code} > 3")
    for name, dtype, _ in TIER_COLUMNS[tier]:
        if dtype != "u8":
            columns[name] = _decode_floats(payloads[name], dtype, name, header["n_cells"])
    if tier == "detail":
        bounds = zip(columns["q025"], columns["post_mean"], columns["q975"], strict=True)
        for row, (low, mean, high) in enumerate(bounds):
            if low > mean or mean > high:
                raise GosaError("interval_order", f"row {row}: q025 <= post_mean <= q975 is required")
    return GosaContainer(tier, header, columns)


def verify_container(data: bytes, *, tier: str, sha256: str, size: int) -> GosaContainer:
    """Check a container against its catalog-declared digest and decoded size, then decode it."""
    if len(data) != size or container_sha256(data) != sha256:
        raise GosaError("container_sha256", f"{tier} container differs from its declared sha256/bytes")
    return decode(data, tier=tier)


def _f32_bits(values: Sequence[float]) -> bytes:
    return struct.pack(f"<{len(values)}f", *values)


#: The catalog-ref fields a payload must repeat (``static-provider.ts`` ``IDENTITY_FIELDS``).
IDENTITY_FIELDS: tuple[str, ...] = (
    "artifact_format", "data_version", "entity_type", "hf_dataset", "hf_revision", "id",
    "measurement", "model_version", "registry_version", "resolution", "target_grid_source",
    "target_grid_version", "variant_id",
)


def verify_artifact_tiers(
    *,
    grid: GosaContainer,
    render: GosaContainer,
    detail: GosaContainer,
    ref: Mapping[str, Any],
    grid_sha256: str,
) -> None:
    """Check decoded tiers against their catalog ``ref`` and each other (spec §B.2, §B.3).

    ``ref`` is the catalog artifact entry (identity fields, ``n_cells``, ``surface_sha256``,
    ``support_counts``); ``grid_sha256`` is the ``grids`` key it names. The TypeScript
    ``decodeRender``/``decodeDetail`` run the same checks with the same codes, in this order.
    """
    if (grid.tier, render.tier, detail.tier) != TIERS:
        raise ValueError("verify_artifact_tiers needs a grid, a render and a detail container")
    if grid.header["grid_sha256"] != grid_sha256:
        raise GosaError("grid_sha256", "grid header digest differs from the catalog grids key")
    for container in (grid, render, detail):
        if container.header["n_cells"] != ref["n_cells"]:
            raise GosaError("n_cells", f"{container.tier} n_cells != catalog n_cells {ref['n_cells']}")
    for container in (render, detail):
        if container.header["grid_sha256"] != grid_sha256:
            raise GosaError("grid_sha256", f"{container.tier} names a different grid")
        artifact = container.header["artifact"]
        for field in IDENTITY_FIELDS:
            if artifact.get(field) != ref.get(field):
                raise GosaError(
                    "identity",
                    f"Atlas artifact identity mismatch for {field}: requested {ref.get(field)}, "
                    f"received {artifact.get(field)}",
                )
        for field in ("label", "metric_domains"):
            if artifact[field] != ref[field]:
                raise GosaError("identity", f"Atlas artifact identity mismatch for {field}")
        if container.header["source_surface_sha256"] != ref["surface_sha256"]:
            raise GosaError("source_sha256", f"{container.tier} source_surface_sha256 != surface_sha256")
    for metric in ("post_mean", "post_sd"):
        try:
            same = _f32_bits(detail.columns[metric]) == _f32_bits(render.columns[metric])
        except OverflowError:  # Math.fround rounds it to Infinity, which no decoded render value is
            same = False
        if not same:
            raise GosaError("cross_tier", f"float32(detail.{metric}) differs from render.{metric}")
    declared = ref["support_counts"]
    for code, state in enumerate(SUPPORT_CODES):
        count = render.columns["support"].count(code)
        if count != declared.get(state, 0):
            raise GosaError("cross_tier", f"support {state}: {count} cells, catalog {declared.get(state, 0)}")
