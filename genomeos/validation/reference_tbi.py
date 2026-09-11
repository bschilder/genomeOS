"""Bounded conservative TBI interpretation (preflight design §5; Atlas §§4–8, 12)."""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass

MAX_COMPRESSED_BYTES = 16 * 1024 * 1024
MAX_DECOMPRESSED_BYTES = 64 * 1024 * 1024
MAX_BGZF_BLOCK_BYTES = 65_536
MAX_REFERENCE_NAME_BYTES = 64
MAX_DISTINCT_BINS = 37_450
MAX_CHUNKS = 1_000_000
MAX_LINEAR_OFFSETS = 32_768
MAX_POSITION = 2**29
PSEUDO_BIN = 37_450
INVALID_BIN = 37_449
REG2BINS_LEVELS = ((0, 0), (1, 26), (9, 23), (73, 20), (585, 17), (4681, 14))
AUTOSOMES = tuple(f"chr{number}" for number in range(1, 23))


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _integer(value: object, field: str, *, minimum: int = 0) -> int:
    _require(type(value) is int and value >= minimum, f"{field} must be an integer >= {minimum}")
    return value


@dataclass(frozen=True, order=True)
class VirtualChunk:
    begin: int
    end: int

    def __post_init__(self) -> None:
        _integer(self.begin, "virtual chunk begin")
        _integer(self.end, "virtual chunk end")
        _require(self.begin <= self.end, "virtual chunk is reversed")


@dataclass(frozen=True)
class TbiIndex:
    chrom: str
    bins: tuple[tuple[int, tuple[VirtualChunk, ...]], ...]
    linear_offsets: tuple[int, ...]
    reference_bounds: VirtualChunk | None
    mapped_count: int | None
    unmapped_count: int | None
    n_no_coor: int | None

    def __post_init__(self) -> None:
        _require(self.chrom in AUTOSOMES, "chromosome must be chr1 through chr22")
        _require(type(self.bins) is tuple, "bins must be a tuple")
        _require(len(self.bins) <= MAX_DISTINCT_BINS, "bin count exceeds limit")
        seen: set[int] = set()
        for entry in self.bins:
            _require(type(entry) is tuple and len(entry) == 2, "bin entries must be pairs")
            bin_id, chunks = entry
            _integer(bin_id, "bin id")
            _require(0 <= bin_id < INVALID_BIN and bin_id not in seen, "invalid or duplicate ordinary bin")
            _require(type(chunks) is tuple and bool(chunks), "ordinary bin chunks must be a nonempty tuple")
            _require(
                all(type(chunk) is VirtualChunk and chunk.begin < chunk.end for chunk in chunks),
                "invalid chunk",
            )
            seen.add(bin_id)
        _require(tuple(bin_id for bin_id, _ in self.bins) == tuple(sorted(seen)), "bins must be sorted")
        _require(type(self.linear_offsets) is tuple, "linear_offsets must be a tuple")
        _require(len(self.linear_offsets) <= MAX_LINEAR_OFFSETS, "linear offset count exceeds limit")
        _require(
            all(type(offset) is int and offset >= 0 for offset in self.linear_offsets),
            "invalid linear offset",
        )
        _require(
            self.reference_bounds is None or type(self.reference_bounds) is VirtualChunk,
            "invalid reference bounds",
        )
        for field, value in (
            ("mapped_count", self.mapped_count),
            ("unmapped_count", self.unmapped_count),
            ("n_no_coor", self.n_no_coor),
        ):
            _require(value is None or (type(value) is int and value >= 0), f"invalid {field}")
        _require(
            (self.reference_bounds is None) == (self.mapped_count is None) == (self.unmapped_count is None),
            "pseudo-bin fields must be jointly present or absent",
        )
        _require(sum(len(chunks) for _, chunks in self.bins) <= MAX_CHUNKS, "chunk count exceeds limit")
        _require(self.mapped_count is None or self.mapped_count <= 2**63 - 1, "mapped count exceeds range")
        _require(self.unmapped_count in (None, 0), "unmapped count must be zero or absent")
        _require(self.n_no_coor in (None, 0), "n_no_coor must be zero or absent")


def _expand_bgzf(compressed: bytes) -> bytes:
    _require(type(compressed) is bytes and bool(compressed), "compressed TBI must be nonempty bytes")
    _require(len(compressed) <= MAX_COMPRESSED_BYTES, "compressed TBI exceeds 16 MiB limit")
    output = bytearray()
    offset = 0
    while offset < len(compressed):
        _require(len(compressed) - offset >= 18, "truncated BGZF header")
        _require(compressed[offset : offset + 3] == b"\x1f\x8b\x08", "invalid BGZF magic")
        _require(compressed[offset + 3] == 4, "unsupported BGZF flags")
        extra_length = int.from_bytes(compressed[offset + 10 : offset + 12], "little")
        header_end = offset + 12 + extra_length
        _require(extra_length >= 6 and header_end + 8 <= len(compressed), "truncated BGZF extra data")
        cursor = offset + 12
        block_size: int | None = None
        while cursor < header_end:
            _require(cursor + 4 <= header_end, "invalid BGZF extra field")
            subfield_length = int.from_bytes(compressed[cursor + 2 : cursor + 4], "little")
            subfield_end = cursor + 4 + subfield_length
            _require(subfield_end <= header_end, "invalid BGZF extra field length")
            if compressed[cursor : cursor + 2] == b"BC":
                _require(subfield_length == 2 and block_size is None, "invalid BGZF BC field")
                block_size = int.from_bytes(compressed[cursor + 4 : subfield_end], "little") + 1
            cursor = subfield_end
        _require(block_size is not None, "missing BGZF BC field")
        _require(26 <= block_size <= MAX_BGZF_BLOCK_BYTES, "invalid BGZF block size")
        block_end = offset + block_size
        _require(block_end <= len(compressed), "truncated BGZF block")
        _require(header_end <= block_end - 8, "invalid BGZF payload bounds")
        deflate = compressed[header_end : block_end - 8]
        inflater = zlib.decompressobj(wbits=-15)
        try:
            payload = inflater.decompress(deflate, MAX_BGZF_BLOCK_BYTES + 1)
        except zlib.error as error:
            raise ValueError("invalid BGZF deflate payload") from error
        _require(len(payload) <= MAX_BGZF_BLOCK_BYTES, "BGZF block expansion exceeds 65536 bytes")
        _require(
            inflater.eof and not inflater.unused_data and not inflater.unconsumed_tail, "invalid BGZF stream"
        )
        expected_crc, expected_size = struct.unpack_from("<II", compressed, block_end - 8)
        _require((zlib.crc32(payload) & 0xFFFFFFFF) == expected_crc, "BGZF CRC mismatch")
        _require((len(payload) & 0xFFFFFFFF) == expected_size, "BGZF ISIZE mismatch")
        _require(
            len(output) + len(payload) <= MAX_DECOMPRESSED_BYTES, "decompressed TBI exceeds 64 MiB limit"
        )
        output.extend(payload)
        offset = block_end
    _require(offset == len(compressed), "trailing BGZF bytes")
    return bytes(output)


class _Reader:
    def __init__(self, payload: bytes):
        self.payload = payload
        self.offset = 0

    @property
    def remaining(self) -> int:
        return len(self.payload) - self.offset

    def take(self, size: int, field: str) -> bytes:
        _require(size >= 0 and self.remaining >= size, f"truncated TBI {field}")
        result = self.payload[self.offset : self.offset + size]
        self.offset += size
        return result

    def i32(self, field: str) -> int:
        return struct.unpack("<i", self.take(4, field))[0]

    def u32(self, field: str) -> int:
        return struct.unpack("<I", self.take(4, field))[0]

    def u64(self, field: str) -> int:
        return struct.unpack("<Q", self.take(8, field))[0]


def _validate_virtual_offset(value: int, size: int, field: str, *, terminal: bool = False) -> None:
    physical = value >> 16
    within = physical < size or (terminal and value & 0xFFFF == 0 and physical == size)
    _require(within, f"{field} virtual offset is outside source")


def parse_tbi(compressed: bytes, *, expected_chrom: str, vcf_size_bytes: int) -> TbiIndex:
    """Parse one bounded, single-reference VCF TBI without linear pruning."""
    _require(isinstance(expected_chrom, str) and bool(expected_chrom), "invalid expected chromosome")
    size = _integer(vcf_size_bytes, "vcf_size_bytes", minimum=1)
    reader = _Reader(_expand_bgzf(compressed))
    _require(reader.take(4, "magic") == b"TBI\x01", "invalid TBI magic")
    _require(reader.i32("n_ref") == 1, "TBI n_ref must equal one")
    fields = tuple(reader.i32(name) for name in ("preset", "col_seq", "col_beg", "col_end", "meta", "skip"))
    _require(fields == (2, 1, 2, 0, 35, 0), "unsupported TBI VCF preset fields")
    name_length = reader.i32("name length")
    _require(1 <= name_length <= MAX_REFERENCE_NAME_BYTES, "invalid TBI name length")
    name = reader.take(name_length, "reference name")
    _require(name.endswith(b"\0") and name.count(b"\0") == 1, "TBI name must be one NUL-terminated value")
    try:
        chrom = name[:-1].decode("ascii")
    except UnicodeDecodeError as error:
        raise ValueError("TBI chromosome name must be ASCII") from error
    _require(chrom == expected_chrom, "TBI chromosome does not match expected chromosome")

    bin_count = reader.i32("bin count")
    _require(0 <= bin_count <= MAX_DISTINCT_BINS, "invalid TBI bin count")
    _require(reader.remaining >= bin_count * 8 + 4, "truncated TBI bin table")
    ordinary: list[tuple[int, tuple[VirtualChunk, ...]]] = []
    seen: set[int] = set()
    reference_bounds = None
    mapped_count = None
    unmapped_count = None
    total_chunks = 0
    for _ in range(bin_count):
        bin_id = reader.u32("bin id")
        _require(
            bin_id != INVALID_BIN and (bin_id < INVALID_BIN or bin_id == PSEUDO_BIN), "invalid TBI bin id"
        )
        _require(bin_id not in seen, "duplicate TBI bin")
        seen.add(bin_id)
        chunk_count = reader.i32("chunk count")
        _require(chunk_count >= 0, "invalid signed TBI chunk count")
        _require(total_chunks + chunk_count <= MAX_CHUNKS, "TBI chunk count exceeds limit")
        _require(reader.remaining >= chunk_count * 16 + 4, "truncated TBI chunk table")
        if bin_id == PSEUDO_BIN:
            _require(chunk_count == 2, "TBI pseudo-bin must contain exactly two pairs")
            begin, end = reader.u64("reference begin"), reader.u64("reference end")
            _validate_virtual_offset(begin, size, "reference begin")
            _validate_virtual_offset(end, size, "reference end", terminal=True)
            _require(begin <= end, "TBI reference bounds are reversed")
            reference_bounds = VirtualChunk(begin, end)
            mapped_count, unmapped_count = reader.u64("mapped count"), reader.u64("unmapped count")
            _require(mapped_count <= 2**63 - 1, "TBI mapped count exceeds signed range")
            _require(unmapped_count == 0, "TBI unmapped count must be zero")
        else:
            chunks = []
            for _ in range(chunk_count):
                begin, end = reader.u64("chunk begin"), reader.u64("chunk end")
                _require(begin < end, "ordinary TBI chunk is reversed or empty")
                _validate_virtual_offset(begin, size, "chunk begin")
                _validate_virtual_offset(end, size, "chunk end", terminal=True)
                chunks.append(VirtualChunk(begin, end))
            if chunks:
                ordinary.append((bin_id, tuple(chunks)))
        total_chunks += chunk_count

    linear_count = reader.i32("linear count")
    _require(0 <= linear_count <= MAX_LINEAR_OFFSETS, "invalid TBI linear count")
    _require(reader.remaining >= linear_count * 8, "truncated TBI linear offsets")
    linear = []
    for _ in range(linear_count):
        value = reader.u64("linear offset")
        if value:
            _validate_virtual_offset(value, size, "linear")
        linear.append(value)
    if reader.remaining == 0:
        n_no_coor = None
    elif reader.remaining == 8:
        n_no_coor = reader.u64("n_no_coor")
        _require(n_no_coor == 0, "TBI n_no_coor must be zero")
    elif reader.remaining < 8:
        raise ValueError("partial TBI n_no_coor")
    else:
        raise ValueError("extraneous trailing TBI bytes")
    return TbiIndex(
        chrom=chrom,
        bins=tuple(sorted(ordinary)),
        linear_offsets=tuple(linear),
        reference_bounds=reference_bounds,
        mapped_count=mapped_count,
        unmapped_count=unmapped_count,
        n_no_coor=n_no_coor,
    )


def candidate_chunks(index: TbiIndex, start0: int, end0: int) -> tuple[VirtualChunk, ...]:
    """Return every ordinary chunk in overlapping reg2bins, without linear pruning."""
    _require(type(index) is TbiIndex, "index must be a TbiIndex")
    _integer(start0, "region start0")
    _integer(end0, "region end0", minimum=1)
    _require(start0 < end0 <= MAX_POSITION, "invalid half-open region")
    selected_bins = {0}
    for offset, shift in REG2BINS_LEVELS[1:]:
        selected_bins.update(range(offset + (start0 >> shift), offset + ((end0 - 1) >> shift) + 1))
    chunks = {chunk for bin_id, values in index.bins if bin_id in selected_bins for chunk in values}
    return tuple(sorted(chunks))
