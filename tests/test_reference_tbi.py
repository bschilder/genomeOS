"""Bounded TBI parsing and native coverage controls (preflight design §§5, 7; #254)."""

from __future__ import annotations

import hashlib
import json
import struct
import zlib
from pathlib import Path

import pytest

from genomeos.validation.reference_tbi import (
    candidate_chunks,
    parse_tbi,
)
from tests.reference_tbi_fixture import (
    QUERIES,
    RECORDS,
    bgzf_record_blocks,
    canonical_json,
    create_native_fixture,
    expanded_tbi_payload,
    native_tools,
    synthetic_bgzf,
)

FIXTURE = Path(__file__).parent / "fixtures" / "reference_windows" / "native"


def _fixture_index():
    vcf = FIXTURE / "synthetic.vcf.gz"
    return parse_tbi(
        (FIXTURE / "synthetic.vcf.gz.tbi").read_bytes(),
        expected_chrom="chr1",
        vcf_size_bytes=vcf.stat().st_size,
    )


def _fields(payload: bytes) -> tuple[int, int, int]:
    name_length = struct.unpack_from("<i", payload, 32)[0]
    bins_offset = 36 + name_length
    first_bin = bins_offset + 4
    return bins_offset, first_bin, name_length


def _layout(payload: bytes):
    bins_offset, offset, _ = _fields(payload)
    entries = []
    for _ in range(struct.unpack_from("<i", payload, bins_offset)[0]):
        bin_id, chunks = struct.unpack_from("<Ii", payload, offset)
        end = offset + 8 + chunks * 16
        entries.append((offset, end, bin_id, chunks))
        offset = end
    linear_count = struct.unpack_from("<i", payload, offset)[0]
    return bins_offset, entries, offset, linear_count


def _assert_native_query_blocks_are_covered(raw: bytes, index) -> None:
    from genomeos.validation.reference_byte_plan import chunk_byte_range

    intervals = ((0, 1), (16_383, 16_384), (32_768, 32_769))
    for record, interval in zip(RECORDS[:3], intervals, strict=True):
        touched = bgzf_record_blocks(raw, record.encode())
        ranges = tuple(
            chunk_byte_range(chunk, source_size_bytes=len(raw))
            for chunk in candidate_chunks(index, *interval)
        )
        assert all(
            any(byte_range.first <= lo and byte_range.last >= hi for byte_range in ranges)
            for lo, hi in touched
        )
    assert len(bgzf_record_blocks(raw, RECORDS[1].encode())) >= 3
    assert isinstance(candidate_chunks(index, 100_000, 100_001), tuple)


def test_checked_in_native_evidence_hashes_and_queries_are_exact():
    evidence_raw = (FIXTURE / "expected-queries.json").read_bytes()
    evidence = json.loads(evidence_raw)
    assert evidence_raw == canonical_json(evidence)
    assert evidence["schema_version"] == "synthetic_reference_tbi_evidence_v1"
    assert tuple((row["argv"][5], row["stdout"]) for row in evidence["queries"]) == QUERIES
    for name, digest in evidence["fixture_sha256"].items():
        assert hashlib.sha256((FIXTURE / name).read_bytes()).hexdigest() == digest
    assert all("1.23.1" in value for value in evidence["native_versions"].values())


def test_saved_native_fixture_candidate_ranges_cover_complete_long_record_blocks():
    raw = (FIXTURE / "synthetic.vcf.gz").read_bytes()
    _assert_native_query_blocks_are_covered(raw, _fixture_index())


def test_candidate_chunks_cover_boundary_queries_and_keep_beyond_record_unknown():
    index = _fixture_index()
    for start0, end0 in ((0, 1), (16_383, 16_384), (32_768, 32_769), (100_000, 100_001)):
        assert isinstance(candidate_chunks(index, start0, end0), tuple)


def test_native_reference_tbi_oracle(tmp_path):
    if native_tools() is None:
        pytest.skip("bgzip, tabix and bcftools are not all installed")
    vcf, tbi, evidence = create_native_fixture(tmp_path)
    saved = json.loads((FIXTURE / "expected-queries.json").read_bytes())
    assert evidence["fixture_sha256"] == saved["fixture_sha256"]
    assert evidence["native_versions"] == saved["native_versions"]
    raw = vcf.read_bytes()
    index = parse_tbi(tbi.read_bytes(), expected_chrom="chr1", vcf_size_bytes=len(raw))
    _assert_native_query_blocks_are_covered(raw, index)
    assert tuple((row["argv"][5], row["stdout"]) for row in evidence["queries"]) == QUERIES


@pytest.mark.parametrize("cut", [0, 1, 17, 18, 25, 26])
def test_bgzf_truncation_refuses(cut):
    raw = (FIXTURE / "synthetic.vcf.gz.tbi").read_bytes()
    with pytest.raises(ValueError, match="BGZF|compressed"):
        parse_tbi(raw[:cut], expected_chrom="chr1", vcf_size_bytes=10_000)


def test_crc_corruption_and_bgzf_size_lie_refuse():
    raw = bytearray((FIXTURE / "synthetic.vcf.gz.tbi").read_bytes())
    corrupt_crc = raw.copy()
    corrupt_crc[-5] ^= 1
    with pytest.raises(ValueError, match="CRC"):
        parse_tbi(bytes(corrupt_crc), expected_chrom="chr1", vcf_size_bytes=10_000)
    corrupt_size = raw.copy()
    corrupt_size[16:18] = (65_535).to_bytes(2, "little")
    with pytest.raises(ValueError, match="BGZF"):
        parse_tbi(bytes(corrupt_size), expected_chrom="chr1", vcf_size_bytes=10_000)


def test_single_bgzf_member_expansion_limit_refuses():
    part = b"x" * 65_537
    compressor = zlib.compressobj(wbits=-15)
    body = compressor.compress(part) + compressor.flush()
    size = 18 + len(body) + 8
    header = bytes.fromhex("1f8b08040000000000ff060042430200") + struct.pack("<H", size - 1)
    raw = header + body + struct.pack("<II", zlib.crc32(part), len(part))
    with pytest.raises(ValueError, match="block expansion"):
        parse_tbi(raw, expected_chrom="chr1", vcf_size_bytes=10_000)


@pytest.mark.parametrize(
    "field,value,match", [(4, 0, "n_ref"), (4, 2, "n_ref"), (8, 1, "preset"), (32, -1, "name")]
)
def test_tbi_header_mutations_refuse(field, value, match):
    payload = bytearray(expanded_tbi_payload((FIXTURE / "synthetic.vcf.gz.tbi").read_bytes()))
    struct.pack_into("<i", payload, field, value)
    with pytest.raises(ValueError, match=match):
        parse_tbi(synthetic_bgzf(bytes(payload)), expected_chrom="chr1", vcf_size_bytes=10_000)


def test_wrong_name_and_extraneous_or_partial_no_coordinate_bytes_refuse():
    payload = bytearray(expanded_tbi_payload((FIXTURE / "synthetic.vcf.gz.tbi").read_bytes()))
    payload[36:41] = b"chr2\0"
    with pytest.raises(ValueError, match="chromosome"):
        parse_tbi(synthetic_bgzf(bytes(payload)), expected_chrom="chr1", vcf_size_bytes=10_000)
    original = expanded_tbi_payload((FIXTURE / "synthetic.vcf.gz.tbi").read_bytes())
    assert original[-8:] == b"\0" * 8
    assert (
        parse_tbi(synthetic_bgzf(original[:-8]), expected_chrom="chr1", vcf_size_bytes=10_000).n_no_coor
        is None
    )
    assert parse_tbi(synthetic_bgzf(original), expected_chrom="chr1", vcf_size_bytes=10_000).n_no_coor == 0
    with pytest.raises(ValueError, match="trailing"):
        parse_tbi(synthetic_bgzf(original + b"x"), expected_chrom="chr1", vcf_size_bytes=10_000)
    with pytest.raises(ValueError, match="n_no_coor"):
        parse_tbi(synthetic_bgzf(original[:-8] + b"\0" * 4), expected_chrom="chr1", vcf_size_bytes=10_000)
    nonzero = bytearray(original)
    nonzero[-8:] = (1).to_bytes(8, "little")
    with pytest.raises(ValueError, match="n_no_coor"):
        parse_tbi(synthetic_bgzf(bytes(nonzero)), expected_chrom="chr1", vcf_size_bytes=10_000)


def test_duplicate_invalid_and_malformed_pseudo_bins_refuse():
    payload = bytearray(expanded_tbi_payload((FIXTURE / "synthetic.vcf.gz.tbi").read_bytes()))
    bins_offset, first_bin, _ = _fields(payload)
    n_bin = struct.unpack_from("<i", payload, bins_offset)[0]
    first_id = struct.unpack_from("<I", payload, first_bin)[0]
    second = first_bin + 8 + struct.unpack_from("<i", payload, first_bin + 4)[0] * 16
    duplicate = payload.copy()
    struct.pack_into("<I", duplicate, second, first_id)
    with pytest.raises(ValueError, match="duplicate"):
        parse_tbi(synthetic_bgzf(bytes(duplicate)), expected_chrom="chr1", vcf_size_bytes=10_000)
    invalid = payload.copy()
    struct.pack_into("<I", invalid, first_bin, 37_449)
    with pytest.raises(ValueError, match="bin"):
        parse_tbi(synthetic_bgzf(bytes(invalid)), expected_chrom="chr1", vcf_size_bytes=10_000)
    pseudo_offset = first_bin
    for _ in range(n_bin):
        bin_id, chunks = struct.unpack_from("<Ii", payload, pseudo_offset)
        if bin_id == 37_450:
            break
        pseudo_offset += 8 + chunks * 16
    malformed = payload.copy()
    struct.pack_into("<i", malformed, pseudo_offset + 4, 1)
    with pytest.raises(ValueError, match="pseudo"):
        parse_tbi(synthetic_bgzf(bytes(malformed)), expected_chrom="chr1", vcf_size_bytes=10_000)


def test_valid_pseudo_count_is_not_interpreted_as_file_offset():
    payload = bytearray(expanded_tbi_payload((FIXTURE / "synthetic.vcf.gz.tbi").read_bytes()))
    bins_offset, offset, _ = _fields(payload)
    for _ in range(struct.unpack_from("<i", payload, bins_offset)[0]):
        bin_id, chunks = struct.unpack_from("<Ii", payload, offset)
        if bin_id == 37_450:
            struct.pack_into("<Q", payload, offset + 8 + 16, 1_000_000)
            break
        offset += 8 + chunks * 16
    parsed = parse_tbi(synthetic_bgzf(bytes(payload)), expected_chrom="chr1", vcf_size_bytes=10_000)
    assert parsed.mapped_count == 1_000_000


def test_signed_caps_and_expansion_caps_trigger_before_iteration():
    payload = bytearray(expanded_tbi_payload((FIXTURE / "synthetic.vcf.gz.tbi").read_bytes()))
    bins_offset, _, _ = _fields(payload)
    for value in (-1, 2**31 - 1):
        mutated = payload.copy()
        struct.pack_into("<i", mutated, bins_offset, value)
        with pytest.raises(ValueError, match="bin count"):
            parse_tbi(synthetic_bgzf(bytes(mutated)), expected_chrom="chr1", vcf_size_bytes=10_000)
    with pytest.raises(ValueError, match="compressed"):
        parse_tbi(b"x" * (16 * 1024 * 1024 + 1), expected_chrom="chr1", vcf_size_bytes=10_000)
    huge = synthetic_bgzf(b"x" * (64 * 1024 * 1024 + 1))
    with pytest.raises(ValueError, match="decompressed"):
        parse_tbi(huge, expected_chrom="chr1", vcf_size_bytes=10_000)


def test_truncation_at_binary_field_boundaries_refuses():
    payload = expanded_tbi_payload((FIXTURE / "synthetic.vcf.gz.tbi").read_bytes())
    bins_offset, entries, linear_offset, linear_count = _layout(payload)
    cuts = {4, 8, 12, 32, 36, bins_offset, bins_offset + 4, linear_offset, linear_offset + 4}
    for begin, end, _, chunks in entries:
        cuts.update((begin + 4, begin + 8))
        cuts.update(begin + 8 + 16 * index for index in range(1, chunks + 1))
        cuts.discard(end)
    cuts.update(linear_offset + 4 + 8 * index for index in range(1, linear_count + 1))
    cuts.discard(len(payload) - 8)  # n_no_coor is explicitly optional.
    for cut in sorted(cuts):
        with pytest.raises(ValueError):
            parse_tbi(synthetic_bgzf(payload[:cut]), expected_chrom="chr1", vcf_size_bytes=10_000)


def test_chunk_counts_reversed_chunks_and_out_of_source_offsets_refuse():
    original = expanded_tbi_payload((FIXTURE / "synthetic.vcf.gz.tbi").read_bytes())
    _, entries, _, _ = _layout(original)
    ordinary = next(entry for entry in entries if entry[2] != 37_450)
    for count in (-1, 2**31 - 1):
        payload = bytearray(original)
        struct.pack_into("<i", payload, ordinary[0] + 4, count)
        with pytest.raises(ValueError, match="chunk count|chunk table"):
            parse_tbi(synthetic_bgzf(bytes(payload)), expected_chrom="chr1", vcf_size_bytes=10_000)
    payload = bytearray(original)
    begin = struct.unpack_from("<Q", payload, ordinary[0] + 8)[0]
    struct.pack_into("<Q", payload, ordinary[0] + 16, begin)
    with pytest.raises(ValueError, match="reversed or empty"):
        parse_tbi(synthetic_bgzf(bytes(payload)), expected_chrom="chr1", vcf_size_bytes=10_000)
    outside_start = bytearray(original)
    struct.pack_into("<QQ", outside_start, ordinary[0] + 8, 10_000 << 16, 10_001 << 16)
    with pytest.raises(ValueError, match="outside source"):
        parse_tbi(synthetic_bgzf(bytes(outside_start)), expected_chrom="chr1", vcf_size_bytes=10_000)
    outside_end = bytearray(original)
    struct.pack_into("<Q", outside_end, ordinary[0] + 16, (10_000 << 16) | 1)
    with pytest.raises(ValueError, match="outside source"):
        parse_tbi(synthetic_bgzf(bytes(outside_end)), expected_chrom="chr1", vcf_size_bytes=10_000)
    terminal = bytearray(original)
    struct.pack_into("<Q", terminal, ordinary[0] + 16, 10_000 << 16)
    assert parse_tbi(synthetic_bgzf(bytes(terminal)), expected_chrom="chr1", vcf_size_bytes=10_000)


def test_pseudo_counts_and_reference_offsets_have_separate_validation():
    original = expanded_tbi_payload((FIXTURE / "synthetic.vcf.gz.tbi").read_bytes())
    _, entries, _, _ = _layout(original)
    pseudo = next(entry for entry in entries if entry[2] == 37_450)
    for field, value, match in (
        (pseudo[0] + 24, 2**63, "mapped count"),
        (pseudo[0] + 32, 1, "unmapped count"),
        (pseudo[0] + 8, 10_000 << 16, "reference begin"),
        (pseudo[0] + 16, (10_000 << 16) | 1, "reference end"),
    ):
        payload = bytearray(original)
        struct.pack_into("<Q", payload, field, value)
        with pytest.raises(ValueError, match=match):
            parse_tbi(synthetic_bgzf(bytes(payload)), expected_chrom="chr1", vcf_size_bytes=10_000)


def test_absent_pseudo_and_linear_entries_remain_unknown_not_failure():
    original = expanded_tbi_payload((FIXTURE / "synthetic.vcf.gz.tbi").read_bytes())
    bins_offset, entries, _, _ = _layout(original)
    pseudo = next(entry for entry in entries if entry[2] == 37_450)
    without_pseudo = bytearray(original[: pseudo[0]] + original[pseudo[1] :])
    struct.pack_into("<i", without_pseudo, bins_offset, len(entries) - 1)
    parsed = parse_tbi(synthetic_bgzf(bytes(without_pseudo)), expected_chrom="chr1", vcf_size_bytes=10_000)
    assert parsed.reference_bounds is parsed.mapped_count is parsed.unmapped_count is None

    _, _, linear_offset, linear_count = _layout(original)
    tail = original[linear_offset + 4 + linear_count * 8 :]
    without_linear = original[:linear_offset] + struct.pack("<i", 0) + tail
    parsed = parse_tbi(synthetic_bgzf(without_linear), expected_chrom="chr1", vcf_size_bytes=10_000)
    assert parsed.linear_offsets == ()


def test_zero_linear_sentinels_are_retained_and_bad_linear_fields_refuse():
    original = expanded_tbi_payload((FIXTURE / "synthetic.vcf.gz.tbi").read_bytes())
    _, _, linear_offset, linear_count = _layout(original)
    zero = bytearray(original)
    zero[linear_offset + 4 : linear_offset + 4 + linear_count * 8] = b"\0" * (linear_count * 8)
    parsed = parse_tbi(synthetic_bgzf(bytes(zero)), expected_chrom="chr1", vcf_size_bytes=10_000)
    assert parsed.linear_offsets == (0,) * linear_count
    for count in (-1, 2**31 - 1):
        payload = bytearray(original)
        struct.pack_into("<i", payload, linear_offset, count)
        with pytest.raises(ValueError, match="linear count"):
            parse_tbi(synthetic_bgzf(bytes(payload)), expected_chrom="chr1", vcf_size_bytes=10_000)
    outside = bytearray(original)
    struct.pack_into("<Q", outside, linear_offset + 4, 10_000 << 16)
    with pytest.raises(ValueError, match="linear.*outside source"):
        parse_tbi(synthetic_bgzf(bytes(outside)), expected_chrom="chr1", vcf_size_bytes=10_000)


def test_nonzero_and_partial_no_coordinate_values_refuse():
    original = expanded_tbi_payload((FIXTURE / "synthetic.vcf.gz.tbi").read_bytes())
    nonzero = bytearray(original)
    struct.pack_into("<Q", nonzero, len(nonzero) - 8, 1)
    with pytest.raises(ValueError, match="n_no_coor"):
        parse_tbi(synthetic_bgzf(bytes(nonzero)), expected_chrom="chr1", vcf_size_bytes=10_000)
    with pytest.raises(ValueError, match="partial.*n_no_coor"):
        parse_tbi(
            synthetic_bgzf(original[:-8] + b"\0" * 4),
            expected_chrom="chr1",
            vcf_size_bytes=10_000,
        )


def test_candidate_chunks_uses_root_once_and_rejects_invalid_region():
    index = _fixture_index()
    chunks = candidate_chunks(index, 0, 1)
    assert len(chunks) == len(set(chunks))
    with pytest.raises(ValueError, match="region"):
        candidate_chunks(index, 1, 1)
    with pytest.raises(ValueError, match="region"):
        candidate_chunks(index, 0, 2**29 + 1)
