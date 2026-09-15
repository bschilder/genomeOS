"""Preserve bounded original VCF lexemes (reference acquisition design §4)."""

from __future__ import annotations

import hashlib
import re
import struct
import zlib
from dataclasses import dataclass
from typing import Literal

from genomeos.validation.reference_window_types import ReferenceWindow

HEADER_LIMIT_BYTES = 8_388_608
RECORD_LIMIT_BYTES = 16_777_216
BGZF_BLOCK_LIMIT_BYTES = 65_536
MAX_SOURCE_SAMPLES = 4_151

Presence = Literal["present", "literal_dot", "omitted_trailing", "absent_record_format"]
SiteDisposition = Literal["outside_pos", "not_pass", "not_biallelic", "not_acgt_snp", "retained"]

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_POS = re.compile(r"[1-9][0-9]*\Z")
_META_VALUE = re.compile(r"(?:^|,)(ID|Number|Type|length|assembly)=([^,>]+)")
_FIXED_HEADER = ("#CHROM", "POS", "ID", "REF", "ALT", "QUAL", "FILTER", "INFO", "FORMAT")
_CALL_FIELDS = ("gt", "gq", "dp", "ad")
_PRESENCE = frozenset({"present", "literal_dot", "omitted_trailing", "absent_record_format"})


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _text(value: object, field: str) -> str:
    valid = (
        isinstance(value, str)
        and bool(value)
        and value == value.strip()
        and not any(character in value for character in "\t\n\r\0")
    )
    _require(valid, f"invalid {field}")
    return value


def _tuple_of_text(value: object, field: str) -> tuple[str, ...]:
    _require(type(value) is tuple, f"{field} must be a tuple")
    result = tuple(_text(item, field) for item in value)
    return result


def _sha(value: object, field: str) -> str:
    _require(isinstance(value, str) and _SHA256.fullmatch(value) is not None, f"invalid {field} sha256")
    return value


def _missing_lexeme(field: str, token: str) -> bool:
    if token == ".":
        return True
    if field == "gt":
        return token in ("./.", ".|.")
    if field == "ad":
        return "." in token.split(",")
    return False


def _validate_format_keys(format_keys: tuple[str, ...]) -> None:
    _require(bool(format_keys), "record FORMAT must contain at least one key")
    for key in format_keys:
        _text(key, "FORMAT key")
        _require(":" not in key and key != ".", "invalid FORMAT key")
    _require(len(format_keys) == len(set(format_keys)), "duplicate FORMAT key")
    _require("GT" not in format_keys or format_keys[0] == "GT", "GT must be the first FORMAT key")


@dataclass(frozen=True)
class HeaderEvidence:
    samples: tuple[str, ...]
    contigs: tuple[tuple[str, int, str], ...]
    formats: tuple[tuple[str, str, str], ...]
    raw_sha256: str

    def __post_init__(self) -> None:
        samples = _tuple_of_text(self.samples, "header sample ID")
        _require(len(samples) == len(set(samples)), "header sample IDs must be unique")
        _require(len(samples) <= MAX_SOURCE_SAMPLES, "header sample limit exceeded")
        _require(type(self.contigs) is tuple and bool(self.contigs), "header contigs must be a tuple")
        contig_ids: list[str] = []
        for entry in self.contigs:
            _require(type(entry) is tuple and len(entry) == 3, "invalid header contig evidence")
            contig_ids.append(_text(entry[0], "contig ID"))
            _require(type(entry[1]) is int and entry[1] > 0, "invalid contig length")
            _text(entry[2], "contig assembly")
        _require(len(contig_ids) == len(set(contig_ids)), "header contig IDs must be unique")
        _require(type(self.formats) is tuple, "header formats must be a tuple")
        format_ids: list[str] = []
        for entry in self.formats:
            _require(type(entry) is tuple and len(entry) == 3, "invalid header FORMAT evidence")
            format_ids.append(_text(entry[0], "FORMAT ID"))
            _text(entry[1], "FORMAT Number")
            _text(entry[2], "FORMAT Type")
        _require(len(format_ids) == len(set(format_ids)), "header FORMAT IDs must be unique")
        _sha(self.raw_sha256, "header")


@dataclass(frozen=True)
class SourceRecord:
    chrom: str
    pos1: int
    ref: str
    alt: str
    filter: str
    format_keys: tuple[str, ...]
    sample_ids: tuple[str, ...]
    sample_tokens: tuple[str, ...]
    source_virtual_offset: int
    raw_sha256: str

    def __post_init__(self) -> None:
        _text(self.chrom, "record chromosome")
        _require(type(self.pos1) is int and self.pos1 > 0, "record position must be positive")
        _text(self.ref, "REF")
        _text(self.alt, "ALT")
        _text(self.filter, "FILTER")
        _require(type(self.format_keys) is tuple, "FORMAT keys must be a tuple")
        _validate_format_keys(self.format_keys)
        sample_ids = _tuple_of_text(self.sample_ids, "record sample ID")
        _require(len(sample_ids) == len(set(sample_ids)), "record sample IDs must be unique")
        _require(
            type(self.sample_tokens) is tuple
            and all(
                isinstance(token, str)
                and not any(character in token for character in "\t\n\r\0")
                for token in self.sample_tokens
            ),
            "invalid sample token storage",
        )
        sample_tokens = self.sample_tokens
        _require(len(sample_ids) == len(sample_tokens), "sample ID/token length mismatch")
        _require(
            type(self.source_virtual_offset) is int and self.source_virtual_offset >= 0,
            "invalid source virtual offset",
        )
        _sha(self.raw_sha256, "record")


@dataclass(frozen=True)
class CallTokens:
    gt: str
    gq: str
    dp: str
    ad: str
    presence: tuple[tuple[str, Presence], ...]

    def __post_init__(self) -> None:
        for field in _CALL_FIELDS:
            _text(getattr(self, field), field)
        _require(type(self.presence) is tuple, "call presence must be a tuple")
        _require(
            tuple(field for field, _ in self.presence) == _CALL_FIELDS,
            "call presence fields are invalid",
        )
        _require(all(origin in _PRESENCE for _, origin in self.presence), "invalid call presence origin")


@dataclass(frozen=True)
class CallProjection:
    """Validated FORMAT-column positions reusable across every sample in one record."""

    format_keys: tuple[str, ...]
    positions: tuple[int | None, int | None, int | None, int | None]

    def __post_init__(self) -> None:
        _validate_format_keys(self.format_keys)
        _require(type(self.positions) is tuple and len(self.positions) == len(_CALL_FIELDS),
                 "invalid call projection")
        _require(
            all(value is None or (type(value) is int and 0 <= value < len(self.format_keys))
                for value in self.positions),
            "invalid call projection position",
        )


def compile_call_projection(format_keys: tuple[str, ...]) -> CallProjection:
    """Validate one FORMAT layout and compile its four QC-field positions."""
    _require(type(format_keys) is tuple, "FORMAT keys must be a tuple")
    _validate_format_keys(format_keys)
    positions = {key: index for index, key in enumerate(format_keys)}
    return CallProjection(format_keys, tuple(positions.get(field.upper()) for field in _CALL_FIELDS))


def project_compiled_call(projection: CallProjection, sample_token: str) -> CallTokens:
    """Project one sample token through an already validated record FORMAT layout."""
    _require(type(projection) is CallProjection, "projection must be CallProjection")
    token = _text(sample_token, "sample token")
    values = token.split(":")
    _require(all(values), "empty interior sample subfield")
    _require(len(values) <= len(projection.format_keys), "extra sample subfield")
    projected: list[str] = []
    evidence: list[tuple[str, Presence]] = []
    for field, index in zip(_CALL_FIELDS, projection.positions, strict=True):
        if index is None:
            value = "."
            origin: Presence = "absent_record_format"
        elif index >= len(values):
            value = "."
            origin = "omitted_trailing"
        else:
            value = values[index]
            origin = "literal_dot" if _missing_lexeme(field, value) else "present"
        projected.append(value)
        evidence.append((field, origin))
    return CallTokens(*projected, tuple(evidence))


def decode_bgzf_member(raw: bytes) -> bytes:
    """Decode exactly one integrity-checked BGZF member with a bounded output."""
    _require(type(raw) is bytes, "BGZF member must be bytes")
    _require(26 <= len(raw) <= BGZF_BLOCK_LIMIT_BYTES, "invalid BGZF member size")
    _require(raw[:3] == b"\x1f\x8b\x08" and raw[3] == 4, "invalid BGZF framing")
    extra_length = int.from_bytes(raw[10:12], "little")
    body_start = 12 + extra_length
    _require(body_start + 8 <= len(raw), "truncated BGZF member")

    offset = 12
    block_sizes: list[int] = []
    while offset < body_start:
        _require(offset + 4 <= body_start, "truncated BGZF extra subfield")
        subfield_id = raw[offset : offset + 2]
        subfield_length = int.from_bytes(raw[offset + 2 : offset + 4], "little")
        offset += 4
        _require(offset + subfield_length <= body_start, "truncated BGZF extra subfield")
        if subfield_id == b"BC":
            _require(subfield_length == 2, "invalid BGZF BC subfield")
            block_sizes.append(int.from_bytes(raw[offset : offset + 2], "little") + 1)
        offset += subfield_length
    _require(offset == body_start and len(block_sizes) == 1, "BGZF requires one BC subfield")
    _require(block_sizes[0] == len(raw), "BGZF block size mismatch")

    compressed = raw[body_start:-8]
    decoder = zlib.decompressobj(wbits=-15)
    try:
        payload = decoder.decompress(compressed, BGZF_BLOCK_LIMIT_BYTES + 1)
    except zlib.error as error:
        raise ValueError("invalid BGZF deflate stream") from error
    _require(len(payload) <= BGZF_BLOCK_LIMIT_BYTES, "BGZF output limit exceeded")
    _require(
        decoder.eof and not decoder.unused_data and not decoder.unconsumed_tail,
        "incomplete BGZF deflate stream",
    )
    expected_crc, expected_size = struct.unpack("<II", raw[-8:])
    _require(zlib.crc32(payload) == expected_crc, "BGZF CRC mismatch")
    _require(len(payload) == expected_size, "BGZF ISIZE mismatch")
    return payload


def _metadata_values(line: str, prefix: str) -> dict[str, str] | None:
    if not line.startswith(prefix) or not line.endswith(">"):
        return None
    inner = line[len(prefix) : -1]
    values: dict[str, str] = {}
    for match in _META_VALUE.finditer(inner):
        key, value = match.groups()
        _require(key not in values, "duplicate structured header field")
        values[key] = value
    return values


def parse_header(
    raw: bytes,
    *,
    expected_contigs: tuple[tuple[str, int], ...],
    source_chrom: str,
    expected_samples: tuple[str, ...],
) -> HeaderEvidence:
    """Validate one complete source header and retain its exact identity evidence."""
    _require(type(raw) is bytes, "header must be bytes")
    _require(len(raw) <= HEADER_LIMIT_BYTES, "header limit exceeded")
    _require(
        bool(raw) and raw.endswith(b"\n") and b"\r" not in raw and b"\0" not in raw,
        "invalid header lines",
    )
    try:
        lines = raw[:-1].decode("ascii").split("\n")
    except UnicodeDecodeError as error:
        raise ValueError("header must be ASCII") from error
    _require(lines[0] == "##fileformat=VCFv4.2", "header must declare VCFv4.2")
    _require(sum(line.startswith("#CHROM") for line in lines) == 1, "header requires one #CHROM line")
    _require(lines[-1].startswith("#CHROM"), "#CHROM must terminate the header")
    _require(all(line.startswith("##") for line in lines[1:-1]), "invalid header line")

    _require(type(expected_contigs) is tuple and bool(expected_contigs), "expected contigs must be a tuple")
    expected: dict[str, int] = {}
    for entry in expected_contigs:
        _require(type(entry) is tuple and len(entry) == 2, "expected contig entries must be pairs")
        chrom = _text(entry[0], "expected contig")
        length = entry[1]
        _require(type(length) is int and length > 0, "invalid expected contig length")
        _require(chrom not in expected, "duplicate expected contig")
        expected[chrom] = length
    _require(source_chrom in expected, "source chromosome is absent from expected contigs")

    declared_contigs: list[tuple[str, int, str]] = []
    declared_formats: list[tuple[str, str, str]] = []
    for line in lines[1:-1]:
        contig = _metadata_values(line, "##contig=<")
        if contig is not None:
            _require(set(contig) >= {"ID", "length", "assembly"}, "incomplete contig declaration")
            length_text = contig["length"]
            _require(_POS.fullmatch(length_text) is not None, "invalid contig length")
            declared_contigs.append((contig["ID"], int(length_text), contig["assembly"]))
            continue
        format_ = _metadata_values(line, "##FORMAT=<")
        if format_ is not None:
            _require(set(format_) >= {"ID", "Number", "Type"}, "incomplete FORMAT declaration")
            declared_formats.append((format_["ID"], format_["Number"], format_["Type"]))

    contig_ids = tuple(chrom for chrom, _, _ in declared_contigs)
    _require(len(contig_ids) == len(set(contig_ids)), "duplicate contig declaration")
    format_ids = tuple(key for key, _, _ in declared_formats)
    _require(len(format_ids) == len(set(format_ids)), "duplicate FORMAT declaration")
    by_contig = {chrom: (length, assembly) for chrom, length, assembly in declared_contigs}
    for chrom, length in expected.items():
        _require(by_contig.get(chrom) == (length, "gnomAD_GRCh38"), "contig identity mismatch")
    _require(source_chrom in by_contig, "source contig declaration is missing")
    by_format = {key: (number, type_) for key, number, type_ in declared_formats}
    required = {
        "GT": ("1", "String"),
        "GQ": ("1", "Integer"),
        "DP": ("1", "Integer"),
        "AD": ("R", "Integer"),
    }
    _require(all(by_format.get(key) == value for key, value in required.items()), "required FORMAT mismatch")

    columns = tuple(lines[-1].split("\t"))
    _require(columns[:9] == _FIXED_HEADER and len(columns) >= 10, "invalid #CHROM columns")
    samples = columns[9:]
    _tuple_of_text(samples, "header sample ID")
    _require(len(samples) == len(set(samples)), "header sample IDs must be unique")
    expected_sample_ids = _tuple_of_text(expected_samples, "expected sample ID")
    _require(len(expected_sample_ids) == len(set(expected_sample_ids)), "expected sample IDs must be unique")
    _require(len(samples) <= MAX_SOURCE_SAMPLES, "header sample limit exceeded")
    _require(set(samples) == set(expected_sample_ids), "source sample identity mismatch")

    ordered_contigs = tuple(
        [next(item for item in declared_contigs if item[0] == source_chrom)]
        + [item for item in declared_contigs if item[0] != source_chrom]
    )
    return HeaderEvidence(samples, ordered_contigs, tuple(declared_formats), hashlib.sha256(raw).hexdigest())


def project_call(format_keys: tuple[str, ...], sample_token: str) -> CallTokens:
    """Project named QC fields while retaining VCF-defined missingness provenance."""
    return project_compiled_call(compile_call_projection(format_keys), sample_token)


def parse_record(raw: bytes, *, source_virtual_offset: int, header: HeaderEvidence) -> SourceRecord:
    """Parse one complete LF-terminated record without normalizing any sample token."""
    _require(type(header) is HeaderEvidence, "header must be HeaderEvidence")
    _require(type(raw) is bytes, "record must be bytes")
    _require(len(raw) <= RECORD_LIMIT_BYTES, "record limit exceeded")
    _require(
        bool(raw) and raw.endswith(b"\n") and raw.count(b"\n") == 1 and b"\r" not in raw and b"\0" not in raw,
        "record must be one complete LF-terminated line",
    )
    try:
        fields = raw[:-1].decode("ascii").split("\t")
    except UnicodeDecodeError as error:
        raise ValueError("record must be ASCII") from error
    _require(len(fields) == 9 + len(header.samples), "record column count mismatch")
    chrom, pos_text, _, ref, alt, _, filter_, _, format_text = fields[:9]
    _require(chrom == header.contigs[0][0], "record source contig mismatch")
    _require(_POS.fullmatch(pos_text) is not None, "invalid record position")
    _text(ref, "REF")
    _text(alt, "ALT")
    _text(filter_, "FILTER")
    format_keys = tuple(format_text.split(":"))
    _validate_format_keys(format_keys)
    sample_tokens = tuple(fields[9:])
    return SourceRecord(
        chrom,
        int(pos_text),
        ref,
        alt,
        filter_,
        format_keys,
        header.samples,
        sample_tokens,
        source_virtual_offset,
        hashlib.sha256(raw).hexdigest(),
    )


def site_disposition(record: SourceRecord, window: ReferenceWindow) -> SiteDisposition:
    """Apply the frozen sequential site selection without inspecting genotype fields."""
    _require(type(record) is SourceRecord and type(window) is ReferenceWindow, "invalid site inputs")
    _require(record.chrom == window.chrom, "record/window chromosome mismatch")
    if not window.start0 < record.pos1 <= window.end0:
        return "outside_pos"
    if record.filter != "PASS":
        return "not_pass"
    if record.alt == "." or "," in record.alt:
        return "not_biallelic"
    if record.ref == record.alt or record.ref not in "ACGT" or record.alt not in "ACGT":
        return "not_acgt_snp"
    if len(record.ref) != 1 or len(record.alt) != 1:
        return "not_acgt_snp"
    return "retained"
