"""Independent checks for CuGen binary and allocation admission (pilot design §§5-6)."""

from __future__ import annotations

import dataclasses
import struct
from collections.abc import Callable

import numpy as np
import pytest

from genomeos.validation.cugen_format import (
    DecodedCuGen,
    LDWorkspaceEstimate,
    decode_cugen_bytes,
    estimate_ld_workspace,
)
from genomeos.validation.ld_contract import LDVariant
from genomeos.validation.ld_reference import variant_moments

_HEADER_SIZE = 256
_SAMPLE_COUNT = 5
_GIDX = (30, 10, 70, 20)
_PACKED = b"\x1b\x40\x92\x40\xff\xc0\x25\x00"
_MEAN = (1.0, 1.2, 0.0, 0.8)
_SXX = (2.0, 2.8, 0.0, 2.8)
_MAF = (0.5, 0.4, 0.0, 0.4)
_CALLS = np.array(
    [
        [0, 2, 3, 0],
        [1, 1, 3, 2],
        [2, 0, 3, 1],
        [3, 2, 3, 1],
        [1, 1, 3, 0],
    ],
    dtype=np.uint8,
)


def _variants() -> tuple[LDVariant, ...]:
    return tuple(
        LDVariant(gidx, f"1-{position}-A-C", "1", position, "A", "C")
        for gidx, position in zip(_GIDX, (101, 201, 301, 401), strict=True)
    )


def _canonical_bytes(
    *,
    packed: bytes = _PACKED,
    gidx: tuple[int, ...] = _GIDX,
    mean: tuple[float, ...] = _MEAN,
    sxx: tuple[float, ...] = _SXX,
    maf: tuple[float, ...] = _MAF,
    sample_count: int = _SAMPLE_COUNT,
    flags: int = 3,
) -> bytes:
    """Build format-1 bytes independently with struct and literal packed calls."""
    variant_count = len(gidx)
    bytes_per_variant = (sample_count + 3) // 4
    stats_offset = _HEADER_SIZE
    gidx_offset = stats_offset + 12 * variant_count
    data_offset = stats_offset + 20 * variant_count
    header = bytearray(_HEADER_SIZE)
    struct.pack_into(
        "<8sIIQQQQQQI",
        header,
        0,
        b"CUPGEN01",
        1,
        0,
        sample_count,
        variant_count,
        bytes_per_variant,
        stats_offset,
        data_offset,
        gidx_offset,
        flags,
    )
    stats = struct.pack(f"<{variant_count}f", *mean)
    stats += struct.pack(f"<{variant_count}f", *sxx)
    stats += struct.pack(f"<{variant_count}f", *maf)
    return bytes(header) + stats + struct.pack(f"<{variant_count}q", *gidx) + packed


def _mutate_header(content: bytes, offset: int, fmt: str, value: object) -> bytes:
    mutated = bytearray(content)
    struct.pack_into(fmt, mutated, offset, value)
    return bytes(mutated)


def _mutate_float(content: bytes, vector: int, row: int, value: float) -> bytes:
    mutated = bytearray(content)
    struct.pack_into("<f", mutated, _HEADER_SIZE + 16 * vector + 4 * row, value)
    return bytes(mutated)


def test_decode_cugen_bytes_hand_decodes_canonical_high_bit_layout() -> None:
    """Catch low-bit/sample-major decoding or padding entering biological statistics."""
    decoded = decode_cugen_bytes(
        _canonical_bytes(), _variants(), expected_samples=_SAMPLE_COUNT
    )

    assert isinstance(decoded, DecodedCuGen)
    np.testing.assert_array_equal(decoded.calls, _CALLS)
    np.testing.assert_array_equal(decoded.gidx, np.array(_GIDX, dtype=np.int64))
    np.testing.assert_allclose(decoded.mean, _MEAN, rtol=0, atol=2e-7)
    np.testing.assert_allclose(decoded.sxx, _SXX, rtol=0, atol=1e-5)
    np.testing.assert_allclose(decoded.maf, _MAF, rtol=0, atol=1e-7)
    assert decoded.has_missing is True
    assert variant_moments(decoded.calls)[2].mean is None


def test_decode_cugen_bytes_returns_frozen_record_with_read_only_arrays() -> None:
    """Catch caller mutation changing admitted source evidence after validation."""
    decoded = decode_cugen_bytes(
        _canonical_bytes(), _variants(), expected_samples=_SAMPLE_COUNT
    )

    for array in (decoded.calls, decoded.gidx, decoded.mean, decoded.sxx, decoded.maf):
        assert array.flags.writeable is False
        with pytest.raises(ValueError):
            array.flat[0] = 0
    with pytest.raises(dataclasses.FrozenInstanceError):
        decoded.has_missing = False  # type: ignore[misc]


@pytest.mark.parametrize(
    ("offset", "fmt", "value"),
    [
        (0, "<8s", b"NOTCUGEN"),
        (8, "<I", 2),
        (12, "<I", 4),
        (16, "<Q", 4),
        (24, "<Q", 3),
        (32, "<Q", 3),
        (40, "<Q", 257),
        (48, "<Q", 337),
        (56, "<Q", 305),
        (64, "<I", 4),
        (64, "<I", 6),
        (64, "<I", 10),
    ],
)
def test_decode_cugen_bytes_rejects_each_noncanonical_header_field(
    offset: int, fmt: str, value: object
) -> None:
    """Catch acceptance of a header whose version, layout, dimensions, or flags drift."""
    content = _mutate_header(_canonical_bytes(), offset, fmt, value)
    with pytest.raises((TypeError, ValueError)):
        decode_cugen_bytes(content, _variants(), expected_samples=_SAMPLE_COUNT)


@pytest.mark.parametrize(
    "content_change",
    [lambda value: value[:255], lambda value: value[:-1], lambda value: value + b"\0"],
)
def test_decode_cugen_bytes_rejects_truncated_or_appended_content(
    content_change: Callable[[bytes], bytes],
) -> None:
    """Catch prefix-only validation that admits a truncated or trailing payload."""
    with pytest.raises(ValueError):
        decode_cugen_bytes(
            content_change(_canonical_bytes()),
            _variants(),
            expected_samples=_SAMPLE_COUNT,
        )


@pytest.mark.parametrize(
    "gidx",
    [
        (10, 30, 70, 20),
        (30, 30, 70, 20),
    ],
)
def test_decode_cugen_bytes_rejects_wrong_or_duplicate_complete_gidx_map(
    gidx: tuple[int, ...],
) -> None:
    """Catch set-only gidx reconciliation that loses file-row identity or uniqueness."""
    with pytest.raises(ValueError):
        decode_cugen_bytes(
            _canonical_bytes(gidx=gidx), _variants(), expected_samples=_SAMPLE_COUNT
        )


@pytest.mark.parametrize(
    ("vector", "row", "value"),
    [
        (0, 0, float("nan")),
        (1, 1, float("inf")),
        (2, 3, float("-inf")),
        (0, 0, 1.01),
        (1, 1, 2.81),
        (2, 3, 0.41),
        (0, 2, 0.1),
        (1, 2, 0.1),
        (2, 2, 0.1),
    ],
)
def test_decode_cugen_bytes_rejects_nonfinite_or_wrong_stored_statistics(
    vector: int, row: int, value: float
) -> None:
    """Catch storage-stat trust, including coercion of all-missing zero into biological AF."""
    with pytest.raises(ValueError):
        decode_cugen_bytes(
            _mutate_float(_canonical_bytes(), vector, row, value),
            _variants(),
            expected_samples=_SAMPLE_COUNT,
        )


def test_decode_cugen_bytes_rejects_nonzero_reserved_header_bytes() -> None:
    """Catch interpreting an unsupported header extension as canonical format 1."""
    content = bytearray(_canonical_bytes())
    content[68] = 1
    with pytest.raises(ValueError):
        decode_cugen_bytes(bytes(content), _variants(), expected_samples=_SAMPLE_COUNT)


def test_decode_cugen_bytes_rejects_nonzero_padding_dosages() -> None:
    """Catch padded bit pairs being decoded as people or ignored despite noncanonical bytes."""
    content = bytearray(_canonical_bytes())
    content[-1] = 1
    with pytest.raises(ValueError):
        decode_cugen_bytes(bytes(content), _variants(), expected_samples=_SAMPLE_COUNT)


def test_decode_cugen_bytes_requires_missing_flag_to_match_real_samples() -> None:
    """Catch declared missingness disagreeing with decoded non-padding calls."""
    with pytest.raises(ValueError):
        decode_cugen_bytes(
            _canonical_bytes(flags=2), _variants(), expected_samples=_SAMPLE_COUNT
        )

    no_missing_packed = b"\x18\x40\x92\x40\x00\x00\x25\x00"
    decoded = decode_cugen_bytes(
        _canonical_bytes(
            packed=no_missing_packed,
            mean=(0.8, 1.2, 0.0, 0.8),
            sxx=(2.8, 2.8, 0.0, 2.8),
            maf=(0.4, 0.4, 0.0, 0.4),
            flags=2,
        ),
        _variants(),
        expected_samples=_SAMPLE_COUNT,
    )
    assert decoded.has_missing is False
    assert not np.any(decoded.calls == 3)
    with pytest.raises(ValueError):
        decode_cugen_bytes(
            _canonical_bytes(
                packed=no_missing_packed,
                mean=(0.8, 1.2, 0.0, 0.8),
                sxx=(2.8, 2.8, 0.0, 2.8),
                maf=(0.4, 0.4, 0.0, 0.4),
                flags=3,
            ),
            _variants(),
            expected_samples=_SAMPLE_COUNT,
        )


@pytest.mark.parametrize("expected_samples", [True, 5.0, 0, 4097, 4])
def test_decode_cugen_bytes_rejects_invalid_or_mismatched_expected_samples(
    expected_samples: object,
) -> None:
    """Catch inferred or permissively converted source-sample dimensions."""
    with pytest.raises((TypeError, ValueError)):
        decode_cugen_bytes(
            _canonical_bytes(), _variants(), expected_samples=expected_samples  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(("offset", "value"), [(16, 4097), (24, 65)])
def test_decode_cugen_bytes_refuses_dimension_bombs_before_buffer_decode(
    monkeypatch: pytest.MonkeyPatch, offset: int, value: int
) -> None:
    """Catch attacker-controlled dimensions reaching any call/stat/gidx buffer construction."""
    import genomeos.validation.cugen_format as cugen_format

    def forbidden_frombuffer(*args: object, **kwargs: object) -> np.ndarray:
        raise AssertionError("dimension bomb reached bounded array decoding")

    monkeypatch.setattr(cugen_format.np, "frombuffer", forbidden_frombuffer)
    content = _mutate_header(_canonical_bytes(), offset, "<Q", value)
    with pytest.raises(ValueError):
        decode_cugen_bytes(content, _variants(), expected_samples=_SAMPLE_COUNT)


@pytest.mark.parametrize("content", [bytearray(_canonical_bytes()), memoryview(_canonical_bytes())])
def test_decode_cugen_bytes_accepts_only_immutable_bytes(content: object) -> None:
    """Catch mutable source content changing while or after admission."""
    with pytest.raises(TypeError):
        decode_cugen_bytes(content, _variants(), expected_samples=_SAMPLE_COUNT)  # type: ignore[arg-type]


def test_decode_cugen_bytes_rejects_variant_metadata_count_mismatch() -> None:
    """Catch decoding calls whose supplied identity block omits a file row."""
    with pytest.raises(ValueError):
        decode_cugen_bytes(
            _canonical_bytes(), _variants()[:-1], expected_samples=_SAMPLE_COUNT
        )


def test_estimate_ld_workspace_returns_exact_named_conservative_terms() -> None:
    """Catch omitted, double-counted, or ambiguously labelled allocation components."""
    estimate = estimate_ld_workspace(
        source_variants=7,
        source_samples=8,
        training_samples=4,
        requested_pair_count=21,
        chunk_size=2,
        tile_size=3,
    )

    assert estimate == LDWorkspaceEstimate(
        host_bytes=67_112_994,
        device_bytes=134_221_088,
        host_reserve_bytes=67_108_864,
        host_source_decode_bytes=224,
        host_pair_contingency_bytes=672,
        host_pair_metadata_output_bytes=2_688,
        host_variant_metadata_bytes=448,
        host_chunk_workspace_bytes=56,
        host_packed_copies_bytes=42,
        device_reserve_bytes=134_217_728,
        device_selection_bytes=36,
        device_packed_copies_bytes=28,
        device_chunk_workspace_bytes=512,
        device_tile_workspace_bytes=288,
        device_tile_pair_workspace_bytes=1_152,
        device_pair_output_bytes=1_344,
    )
    values = dataclasses.asdict(estimate)
    assert values["host_bytes"] == sum(
        value for name, value in values.items() if name.startswith("host_") and name != "host_bytes"
    )
    assert values["device_bytes"] == sum(
        value
        for name, value in values.items()
        if name.startswith("device_") and name != "device_bytes"
    )


def test_estimate_ld_workspace_admits_exact_fixed_caps_with_minimized_tiles() -> None:
    """Catch accidental cap extension, overbudget arithmetic, or failure to apply min(tile,V)."""
    estimate = estimate_ld_workspace(
        source_variants=64,
        source_samples=4096,
        training_samples=4096,
        requested_pair_count=2016,
        chunk_size=64,
        tile_size=64,
    )

    assert estimate.host_bytes == 136_314_880
    assert estimate.device_bytes == 158_238_720
    assert estimate.host_bytes <= 256 * 2**20
    assert estimate.device_bytes <= 256 * 2**20

    one_variant = estimate_ld_workspace(
        source_variants=1,
        source_samples=1,
        training_samples=1,
        requested_pair_count=0,
        chunk_size=64,
        tile_size=64,
    )
    assert one_variant.host_chunk_workspace_bytes == 12
    assert one_variant.device_chunk_workspace_bytes == 64
    assert one_variant.device_tile_workspace_bytes == 24
    assert one_variant.device_tile_pair_workspace_bytes == 128


@pytest.mark.parametrize("budget_name", ["_HOST_BUDGET_BYTES", "_DEVICE_BUDGET_BYTES"])
def test_estimate_ld_workspace_refuses_a_workspace_over_its_fixed_budget(
    monkeypatch: pytest.MonkeyPatch, budget_name: str
) -> None:
    """Catch a computed workspace total bypassing admission before later allocation."""
    import genomeos.validation.cugen_format as cugen_format

    monkeypatch.setattr(cugen_format, budget_name, 1)
    with pytest.raises(ValueError):
        estimate_ld_workspace(
            source_variants=7,
            source_samples=8,
            training_samples=4,
            requested_pair_count=21,
            chunk_size=2,
            tile_size=3,
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"source_variants": True},
        {"source_variants": 1.0},
        {"source_variants": 0},
        {"source_variants": 65},
        {"source_samples": 0},
        {"source_samples": 4097},
        {"training_samples": 0},
        {"training_samples": 9},
        {"requested_pair_count": -1},
        {"requested_pair_count": 22},
        {"requested_pair_count": 1.0},
        {"chunk_size": 0},
        {"chunk_size": 65},
        {"tile_size": 0},
        {"tile_size": 65},
    ],
)
def test_estimate_ld_workspace_rejects_invalid_dimensions_before_admission(
    changes: dict[str, object],
) -> None:
    """Catch integer coercion, unsafe dimensions, or impossible unordered-pair counts."""
    arguments: dict[str, object] = {
        "source_variants": 7,
        "source_samples": 8,
        "training_samples": 4,
        "requested_pair_count": 21,
        "chunk_size": 2,
        "tile_size": 3,
    }
    arguments.update(changes)
    with pytest.raises((TypeError, ValueError)):
        estimate_ld_workspace(**arguments)  # type: ignore[arg-type]
