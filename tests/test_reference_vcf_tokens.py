"""Bounded original VCF token controls (reference acquisition design §4)."""

from __future__ import annotations

import hashlib
import struct
import zlib
from dataclasses import replace

import pytest

from genomeos.validation.reference_genotypes import assess_call
from genomeos.validation.reference_vcf_tokens import (
    HEADER_LIMIT_BYTES,
    RECORD_LIMIT_BYTES,
    decode_bgzf_member,
    parse_header,
    parse_record,
    project_call,
    site_disposition,
)
from genomeos.validation.reference_window_types import ReferenceWindow, StartRun


def _header(
    *,
    chrom: str = "chr1",
    length: int = 1_000_000,
    assembly: str = "gnomAD_GRCh38",
    samples: tuple[str, ...] = ("s1", "s2"),
    formats: tuple[str, ...] = (
        '##FORMAT=<ID=GT,Number=1,Type=String,Description="Genotype">',
        '##FORMAT=<ID=GQ,Number=1,Type=Integer,Description="Genotype quality">',
        '##FORMAT=<ID=DP,Number=1,Type=Integer,Description="Depth">',
        '##FORMAT=<ID=AD,Number=R,Type=Integer,Description="Allele depths">',
    ),
) -> bytes:
    fixed = "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT"
    return (
        "##fileformat=VCFv4.2\n"
        f"##contig=<ID={chrom},length={length},assembly={assembly}>\n"
        + "\n".join(formats)
        + "\n"
        + fixed
        + "\t"
        + "\t".join(samples)
        + "\n"
    ).encode()


def _evidence(**changes):
    raw = _header(**changes)
    samples = changes.get("samples", ("s1", "s2"))
    chrom = changes.get("chrom", "chr1")
    length = changes.get("length", 1_000_000)
    return parse_header(
        raw,
        expected_contigs=((chrom, length),),
        source_chrom=chrom,
        expected_samples=samples,
    )


def _record(
    *,
    pos: int = 101,
    ref: str = "A",
    alt: str = "G",
    filter_: str = "PASS",
    format_: str = "GT:GQ:DP:AD",
    tokens: tuple[str, ...] = ("0/1:20:10:2,8", "0/0:20:10:."),
) -> bytes:
    return (
        f"chr1\t{pos}\t.\t{ref}\t{alt}\t.\t{filter_}\t.\t{format_}\t" + "\t".join(tokens) + "\n"
    ).encode()


def _window() -> ReferenceWindow:
    return ReferenceWindow("chr1-s1", "chr1", 1, 0, 20_000, 100, 10_100, (StartRun(100, 100),), 1, 0)


def _bgzf_member(payload: bytes, *, extra: bytes = b"BC\x02\x00\x00\x00") -> bytes:
    compressor = zlib.compressobj(wbits=-15)
    body = compressor.compress(payload) + compressor.flush()
    header = bytes.fromhex("1f8b08040000000000ff") + struct.pack("<H", len(extra)) + extra
    raw = header + body + struct.pack("<II", zlib.crc32(payload), len(payload) & 0xFFFFFFFF)
    size = len(raw)
    return raw[:16] + struct.pack("<H", size - 1) + raw[18:]


def test_header_and_record_preserve_exact_tokens_and_hashes():
    raw_header = _header(samples=("s2", "s1"))
    header = parse_header(
        raw_header,
        expected_contigs=(("chr1", 1_000_000),),
        source_chrom="chr1",
        expected_samples=("s1", "s2"),
    )
    assert header.samples == ("s2", "s1")
    assert header.contigs == (("chr1", 1_000_000, "gnomAD_GRCh38"),)
    assert set((key, (number, type_)) for key, number, type_ in header.formats) >= {
        "GT": ("1", "String"),
        "GQ": ("1", "Integer"),
        "DP": ("1", "Integer"),
        "AD": ("R", "Integer"),
    }.items()
    assert header.raw_sha256 == hashlib.sha256(raw_header).hexdigest()

    raw_record = _record(format_="GT:DP:AD:GQ", tokens=("0/1:10:2,8:020", "0/0:10:.:20"))
    record = parse_record(raw_record, source_virtual_offset=1 << 16, header=header)
    assert record.format_keys == ("GT", "DP", "AD", "GQ")
    assert record.sample_ids is header.samples
    assert record.sample_tokens == ("0/1:10:2,8:020", "0/0:10:.:20")
    assert record.raw_sha256 == hashlib.sha256(raw_record).hexdigest()


def test_trailing_omission_is_explicit_missing_evidence():
    trailing = project_call(("GT", "GQ", "DP", "AD"), "0/1:20:10")
    assert (trailing.gt, trailing.gq, trailing.dp, trailing.ad) == ("0/1", "20", "10", ".")
    assert dict(trailing.presence)["ad"] == "omitted_trailing"
    absent = project_call(("GT", "DP", "AD"), "0/1:10:2,8")
    assert absent.gq == "." and dict(absent.presence)["gq"] == "absent_record_format"
    assert assess_call(trailing.gt, trailing.gq, trailing.dp, trailing.ad).disposition == "missing_het_ad"
    assert assess_call(absent.gt, absent.gq, absent.dp, absent.ad).disposition == "missing_gq"


def test_absent_record_gt_is_valid_missingness_without_dosage():
    call = project_call(("GQ", "DP", "AD"), "20:10:2,8")
    assert call.gt == "." and dict(call.presence)["gt"] == "absent_record_format"
    assert assess_call(call.gt, call.gq, call.dp, call.ad).disposition == "missing_gt"
    record = parse_record(
        _record(format_="GQ:DP:AD", tokens=("20:10:2,8", "30:12:6,6")),
        source_virtual_offset=0,
        header=_evidence(),
    )
    assert record.format_keys == ("GQ", "DP", "AD")


@pytest.mark.parametrize(
    "format_keys,sample_token",
    [
        (("GT", "GQ", "DP", "AD"), "0/1::10:2,8"),
        (("GT", "GQ", "DP", "AD"), "0/1:20:10:2,8:extra"),
        (("GQ", "GT", "DP", "AD"), "20:0/1:10:2,8"),
        (("GT", "GT"), "0/1:0/1"),
        ((), "."),
    ],
)
def test_malformed_sample_projection_refuses(format_keys, sample_token):
    with pytest.raises(ValueError):
        project_call(format_keys, sample_token)


def test_parse_record_refuses_structural_damage_and_truncation():
    header = _evidence()
    bad_records = (
        _record(tokens=("0/1:20:10:2,8",)),
        _record(tokens=("0/1:20:10:2,8", "")),
        _record(tokens=("0/1:20:10:2,8:extra", "0/0:20:10:.")),
        _record(format_="GQ:GT:DP:AD", tokens=("20:0/1:10:2,8", "20:0/0:10:.")),
        _record(format_="GT:GT", tokens=("0/1:0/1", "0/0:0/0")),
        _record()[:-1],
        _record().replace(b"chr1\t101", b"chr2\t101"),
        _record().replace(b"\t101\t", b"\t0\t"),
        _record().replace(b"\t101\t", b"\t1.0\t"),
    )
    for raw in bad_records:
        with pytest.raises(ValueError):
            parse_record(raw, source_virtual_offset=0, header=header)


@pytest.mark.parametrize(
    "pos,expected",
    [(100, "outside_pos"), (101, "retained"), (10_100, "retained"), (10_101, "outside_pos")],
)
def test_site_position_boundaries(pos, expected):
    record = parse_record(_record(pos=pos), source_virtual_offset=0, header=_evidence())
    assert site_disposition(record, _window()) == expected


@pytest.mark.parametrize(
    "changes,expected",
    [
        ({"filter_": "."}, "not_pass"),
        ({"alt": "G,T"}, "not_biallelic"),
        ({"ref": "N"}, "not_acgt_snp"),
        ({"ref": "A", "alt": "A"}, "not_acgt_snp"),
    ],
)
def test_site_dispositions_are_sequential(changes, expected):
    record = parse_record(_record(**changes), source_virtual_offset=0, header=_evidence())
    assert site_disposition(record, _window()) == expected


@pytest.mark.parametrize(
    "raw,match",
    [
        (_header(assembly="GRCh37"), "contig"),
        (_header(length=999), "contig"),
        (_header(samples=("s1", "s1")), "sample"),
        (_header().replace(b"VCFv4.2", b"VCFv4.3"), "VCFv4.2"),
        (_header().replace(b"ID=GQ,Number=1", b"ID=GQ,Number=2"), "FORMAT"),
        (_header().replace(b"ID=AD,Number=R", b"ID=AD,Number=1"), "FORMAT"),
        (_header() + b"extra\n", "#CHROM"),
    ],
)
def test_header_identity_and_required_declarations_refuse(raw, match):
    with pytest.raises(ValueError, match=match):
        parse_header(
            raw,
            expected_contigs=(("chr1", 1_000_000),),
            source_chrom="chr1",
            expected_samples=("s1", "s2"),
        )


def test_duplicate_contig_and_format_declarations_refuse():
    contig = b"##contig=<ID=chr1,length=1000000,assembly=gnomAD_GRCh38>\n"
    with pytest.raises(ValueError, match="duplicate"):
        parse_header(
            _header().replace(contig, contig + contig),
            expected_contigs=(("chr1", 1_000_000),),
            source_chrom="chr1",
            expected_samples=("s1", "s2"),
        )
    format_line = b'##FORMAT=<ID=GT,Number=1,Type=String,Description="Genotype">\n'
    with pytest.raises(ValueError, match="duplicate"):
        parse_header(
            _header().replace(format_line, format_line + format_line),
            expected_contigs=(("chr1", 1_000_000),),
            source_chrom="chr1",
            expected_samples=("s1", "s2"),
        )


def test_bgzf_member_is_bounded_and_integrity_checked():
    raw = _bgzf_member(b"hello")
    assert decode_bgzf_member(raw) == b"hello"
    assert decode_bgzf_member(raw[:4] + b"\x01\x02\x03\x04\x00\x03" + raw[10:]) == b"hello"
    mutations = (
        raw[:-1],
        raw[:-8] + struct.pack("<I", 0) + raw[-4:],
        raw[:-4] + struct.pack("<I", 4),
        _bgzf_member(b"hello", extra=b"BC\x02\x00\x00\x00BC\x02\x00\x00\x00"),
        _bgzf_member(b"x" * 65_537),
    )
    for changed in mutations:
        with pytest.raises(ValueError):
            decode_bgzf_member(changed)


def test_record_can_cross_bgzf_blocks_but_limits_are_hard():
    header = _evidence(samples=("s1",))
    raw = _record(format_="GT:X", tokens=("0/1:" + "x" * 70_000,))
    assert len(raw) > 65_536
    assert parse_record(raw, source_virtual_offset=0, header=header).sample_tokens[0].endswith("x" * 100)
    with pytest.raises(ValueError, match="limit"):
        parse_record(b"x" * (RECORD_LIMIT_BYTES + 1), source_virtual_offset=0, header=header)
    with pytest.raises(ValueError, match="limit"):
        parse_header(
            b"x" * (HEADER_LIMIT_BYTES + 1),
            expected_contigs=(("chr1", 1_000_000),),
            source_chrom="chr1",
            expected_samples=("s1",),
        )


def test_header_evidence_is_bound_to_raw_bytes():
    header = _evidence()
    with pytest.raises(ValueError, match="sha256"):
        replace(header, raw_sha256="x" * 64)
