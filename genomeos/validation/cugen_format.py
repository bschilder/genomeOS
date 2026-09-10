"""Canonical CuGen binary and allocation admission (pilot design §§5-6; Atlas §§4-5).

This pure boundary decodes only the bounded training-pilot format and estimates the named
workspace terms used to admit later GPU execution. It does not import CuGen, allocate device
memory, measure process peaks, or admit LD as a joint covariance model.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from numbers import Integral

import numpy as np

from genomeos.validation.ld_contract import (
    MAX_LD_PAIRS,
    MAX_LD_SAMPLES,
    MAX_LD_VARIANTS,
    validate_hard_calls,
    validate_ld_variants,
)
from genomeos.validation.ld_reference import variant_moments

_HEADER_SIZE = 256
_HEADER = struct.Struct("<8sIIQQQQQQI")
_MAGIC = b"CUPGEN01"
_FORMAT_VERSION = 1
_ENCODING = 0
_HAS_MISSING = 1
_HAS_GIDX_MAP = 2
_HOST_BUDGET_BYTES = 256 * 2**20
_DEVICE_BUDGET_BYTES = 256 * 2**20


@dataclass(frozen=True)
class DecodedCuGen:
    """Immutable canonical source evidence decoded into read-only NumPy arrays."""

    calls: np.ndarray
    gidx: np.ndarray
    mean: np.ndarray
    sxx: np.ndarray
    maf: np.ndarray
    has_missing: bool


@dataclass(frozen=True)
class LDWorkspaceEstimate:
    """Conservative named workspace estimates, not measured process or CUDA peaks."""

    host_bytes: int
    device_bytes: int
    host_reserve_bytes: int
    host_source_decode_bytes: int
    host_pair_contingency_bytes: int
    host_pair_metadata_output_bytes: int
    host_variant_metadata_bytes: int
    host_chunk_workspace_bytes: int
    host_packed_copies_bytes: int
    device_reserve_bytes: int
    device_selection_bytes: int
    device_packed_copies_bytes: int
    device_chunk_workspace_bytes: int
    device_tile_workspace_bytes: int
    device_tile_pair_workspace_bytes: int
    device_pair_output_bytes: int


def _exact_integer(value: object, name: str, *, minimum: int, maximum: int) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Integral):
        raise TypeError(f"{name} must be an exact integer")
    normalized = int(value)
    if not minimum <= normalized <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return normalized


def _validate_header(
    content: bytes, *, expected_samples: int
) -> tuple[int, int, int, int, int, int]:
    if len(content) < _HEADER_SIZE:
        raise ValueError("CuGen content is shorter than the 256-byte header")
    (
        magic,
        version,
        encoding,
        sample_count,
        variant_count,
        bytes_per_variant,
        stats_offset,
        data_offset,
        gidx_offset,
        flags,
    ) = _HEADER.unpack_from(content)
    if magic != _MAGIC:
        raise ValueError("CuGen magic must be CUPGEN01")
    if version != _FORMAT_VERSION:
        raise ValueError("only canonical CuGen format version 1 is supported")
    if encoding != _ENCODING:
        raise ValueError("only canonical CuGen encoding 0 is supported")
    if not 1 <= sample_count <= MAX_LD_SAMPLES:
        raise ValueError(f"CuGen sample count must be between 1 and {MAX_LD_SAMPLES}")
    if not 1 <= variant_count <= MAX_LD_VARIANTS:
        raise ValueError(f"CuGen variant count must be between 1 and {MAX_LD_VARIANTS}")
    if sample_count != expected_samples:
        raise ValueError("CuGen sample count must exactly match expected_samples")

    canonical_bpv = (sample_count + 3) // 4
    canonical_gidx_offset = _HEADER_SIZE + 12 * variant_count
    canonical_data_offset = _HEADER_SIZE + 20 * variant_count
    canonical_length = canonical_data_offset + variant_count * canonical_bpv
    if bytes_per_variant != canonical_bpv:
        raise ValueError("CuGen bytes_per_variant is not canonical for the sample count")
    if stats_offset != _HEADER_SIZE:
        raise ValueError("CuGen stats_offset must be 256")
    if gidx_offset != canonical_gidx_offset:
        raise ValueError("CuGen gidx_offset is not canonical for the variant count")
    if data_offset != canonical_data_offset:
        raise ValueError("CuGen data_offset is not canonical for the variant count")
    if flags not in (_HAS_GIDX_MAP, _HAS_GIDX_MAP | _HAS_MISSING):
        raise ValueError("CuGen flags must require gidx and may only additionally mark missing")
    if any(content[_HEADER.size : _HEADER_SIZE]):
        raise ValueError("CuGen reserved header bytes must all be zero")
    if len(content) != canonical_length:
        raise ValueError("CuGen content length does not exactly match the canonical layout")
    return (
        int(sample_count),
        int(variant_count),
        int(canonical_bpv),
        int(stats_offset),
        int(gidx_offset),
        int(data_offset),
    )


def _validate_statistics(
    mean: np.ndarray, sxx: np.ndarray, maf: np.ndarray, calls: np.ndarray
) -> None:
    if not (
        np.all(np.isfinite(mean))
        and np.all(np.isfinite(sxx))
        and np.all(np.isfinite(maf))
    ):
        raise ValueError("CuGen stored statistics must all be finite")
    for row, moments in enumerate(variant_moments(calls)):
        stored_mean = float(mean[row])
        stored_sxx = float(sxx[row])
        stored_maf = float(maf[row])
        if moments.mean is None:
            if stored_mean != 0.0 or stored_sxx != 0.0 or stored_maf != 0.0:
                raise ValueError("all-missing variants must use CuGen's zero-stat convention")
            continue
        if abs(stored_mean - moments.mean) > 2e-7:
            raise ValueError("CuGen stored mean disagrees with decoded calls")
        sxx_tolerance = 1e-5 * max(1.0, moments.sxx)
        if abs(stored_sxx - moments.sxx) > sxx_tolerance:
            raise ValueError("CuGen stored sxx disagrees with decoded calls")
        if abs(stored_maf - moments.maf) > 1e-7:
            raise ValueError("CuGen stored MAF disagrees with decoded calls")


def decode_cugen_bytes(
    content: bytes, variants: object, *, expected_samples: int
) -> DecodedCuGen:
    """Validate and decode one canonical bounded CuGen format-1/encoding-0 byte string."""
    if not isinstance(content, bytes):
        raise TypeError("content must be immutable bytes")
    expected = _exact_integer(
        expected_samples,
        "expected_samples",
        minimum=1,
        maximum=MAX_LD_SAMPLES,
    )
    (
        sample_count,
        variant_count,
        bytes_per_variant,
        stats_offset,
        gidx_offset,
        data_offset,
    ) = _validate_header(content, expected_samples=expected)
    block = validate_ld_variants(
        variants, genome_build="GRCh38", ploidy="autosomal_diploid"
    )
    if len(block) != variant_count:
        raise ValueError("CuGen variant count must exactly match supplied variants")

    statistics = np.frombuffer(
        content,
        dtype="<f4",
        count=3 * variant_count,
        offset=stats_offset,
    ).reshape(3, variant_count)
    mean, sxx, maf = statistics
    gidx = np.frombuffer(
        content,
        dtype="<i8",
        count=variant_count,
        offset=gidx_offset,
    )
    if tuple(int(value) for value in gidx) != tuple(variant.gidx for variant in block):
        raise ValueError("CuGen gidx map must exactly match supplied file-row order")
    packed = np.frombuffer(
        content,
        dtype=np.uint8,
        count=variant_count * bytes_per_variant,
        offset=data_offset,
    ).reshape(variant_count, bytes_per_variant)

    unused_calls = (-sample_count) % 4
    if unused_calls and np.any(packed[:, -1] & ((1 << (2 * unused_calls)) - 1)):
        raise ValueError("CuGen packed-call padding must be zero")
    sample = np.arange(sample_count)
    decoded = (
        (packed[:, sample // 4] >> (6 - 2 * (sample % 4))) & np.uint8(3)
    ).T
    calls = validate_hard_calls(decoded)
    has_missing = bool(np.any(calls == 3))
    if bool(_HAS_MISSING & _HEADER.unpack_from(content)[-1]) != has_missing:
        raise ValueError("CuGen HAS_MISSING flag must match decoded real-sample calls")
    _validate_statistics(mean, sxx, maf, calls)
    return DecodedCuGen(calls, gidx, mean, sxx, maf, has_missing)


def estimate_ld_workspace(
    *,
    source_variants: int,
    source_samples: int,
    training_samples: int,
    requested_pair_count: int,
    chunk_size: int,
    tile_size: int,
) -> LDWorkspaceEstimate:
    """Return named conservative workspace estimates, refusing invalid or overbudget work."""
    variant_count = _exact_integer(
        source_variants,
        "source_variants",
        minimum=1,
        maximum=MAX_LD_VARIANTS,
    )
    sample_count = _exact_integer(
        source_samples,
        "source_samples",
        minimum=1,
        maximum=MAX_LD_SAMPLES,
    )
    training_count = _exact_integer(
        training_samples,
        "training_samples",
        minimum=1,
        maximum=sample_count,
    )
    max_pairs = min(MAX_LD_PAIRS, variant_count * (variant_count - 1) // 2)
    pair_count = _exact_integer(
        requested_pair_count,
        "requested_pair_count",
        minimum=0,
        maximum=max_pairs,
    )
    chunk = _exact_integer(chunk_size, "chunk_size", minimum=1, maximum=64)
    tile = _exact_integer(tile_size, "tile_size", minimum=1, maximum=64)
    chunk_variants = min(chunk, variant_count)
    tile_variants = min(tile, variant_count)
    source_quads = (sample_count + 3) // 4
    training_quads = (training_count + 3) // 4

    host_terms = (
        64 * 2**20,
        4 * variant_count * sample_count,
        8 * pair_count * training_count,
        128 * pair_count,
        64 * variant_count,
        4 * chunk_variants * (training_count + source_quads + training_quads),
        2 * variant_count * (source_quads + training_quads),
    )
    device_terms = (
        128 * 2**20,
        9 * training_count,
        4 * variant_count * training_quads,
        64 * chunk_variants * training_count,
        24 * tile_variants * training_count,
        128 * tile_variants * tile_variants,
        64 * pair_count,
    )
    host_bytes = sum(host_terms)
    device_bytes = sum(device_terms)
    if host_bytes > _HOST_BUDGET_BYTES:
        raise ValueError("estimated host workspace exceeds the 256 MiB pilot budget")
    if device_bytes > _DEVICE_BUDGET_BYTES:
        raise ValueError("estimated device workspace exceeds the 256 MiB pilot budget")
    return LDWorkspaceEstimate(host_bytes, device_bytes, *host_terms, *device_terms)
