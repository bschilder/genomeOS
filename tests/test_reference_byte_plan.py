"""Pure reference-window byte-plan controls (preflight design §5; #254)."""

from __future__ import annotations

import base64
import hashlib
from dataclasses import replace

import pytest

from genomeos.validation.reference_byte_plan import (
    ByteRange,
    IndexReceipt,
    SourceBytePlan,
    WindowBytePlan,
    assemble_preflight,
    chunk_byte_range,
    crc32c,
    encode_preflight,
    fixed_vcf_ranges,
    merge_byte_ranges,
    plan_window,
)
from genomeos.validation.reference_tbi import TbiIndex, VirtualChunk
from genomeos.validation.reference_window_manifest import decode_manifest
from genomeos.validation.reference_window_types import Provenance


def test_physical_end_boundary_and_final_block_clamp():
    assert chunk_byte_range(VirtualChunk(100 << 16, 200 << 16), source_size_bytes=1000) == ByteRange(100, 199)
    assert chunk_byte_range(VirtualChunk(100 << 16, (900 << 16) | 7), source_size_bytes=1000) == ByteRange(
        100, 999
    )
    assert merge_byte_ranges(
        (ByteRange(0, 9), ByteRange(8, 19), ByteRange(20, 29)), source_size_bytes=1000
    ) == (ByteRange(0, 29),)


def test_crc32c_published_check_value():
    assert crc32c(b"123456789") == 0xE3069283


def test_virtual_offsets_reject_out_of_source_and_accept_exclusive_terminal_end():
    assert chunk_byte_range(VirtualChunk(1 << 16, 10 << 16), source_size_bytes=10) == ByteRange(1, 9)
    for chunk in (VirtualChunk(10 << 16, 11 << 16), VirtualChunk(1 << 16, (10 << 16) | 1)):
        with pytest.raises(ValueError, match="source"):
            chunk_byte_range(chunk, source_size_bytes=10)


def test_byte_records_are_immutable_and_reject_mutable_or_inconsistent_states():
    with pytest.raises(ValueError, match="tuple"):
        WindowBytePlan("chr1-s1", "no_index_chunks", None, "not_inspected", [], ())
    with pytest.raises(ValueError, match="reason"):
        WindowBytePlan("chr1-s1", "refused", None, "not_inspected", (), ())
    with pytest.raises(ValueError, match="sha256"):
        IndexReceipt("chr1", "verified", None, 1, 1, 1, 10, None)


def _manifest(tmp_path):
    from tests.test_freeze_reference_windows_cli import _command, _run

    out = tmp_path / "manifest"
    completed = _run(_command(out))
    assert completed.returncode == 0, completed.stderr
    return decode_manifest(
        (out / "manifest.json").read_bytes(), windows_bytes=(out / "windows.tsv").read_bytes()
    )


def _provenance(manifest):
    return Provenance(
        data_version=manifest.provenance.data_version,
        evidence_kind="synthetic_fixture",
        input_sha256=(("manifest", "4" * 64), ("windows", manifest.windows_sha256)),
        source_revision="2" * 40,
        imported_source_sha256=(("genomeos/validation/reference_byte_plan.py", "3" * 64),),
        python_version=manifest.provenance.python_version,
        source_audit_locator="synthetic-audit.md",
    )


def _source_plan(manifest, source_index, *, receipt_state="verified", refused=False):
    source = manifest.sources[source_index]
    windows = tuple(window for window in manifest.windows if window.chrom == source.chrom)
    reason = "index_invalid" if refused else None
    plans = tuple(
        WindowBytePlan(
            window.window_id, "refused" if refused else "no_index_chunks", reason, "not_inspected", (), ()
        )
        for window in windows
    )
    receipt = IndexReceipt(
        source.chrom,
        receipt_state,
        reason,
        1,
        1,
        1,
        source.tbi.size_bytes,
        None if refused else hashlib.sha256(b"index").hexdigest(),
    )
    ranges = fixed_vcf_ranges(
        source.vcf.size_bytes,
        header_prefix_bytes=manifest.config.header_prefix_bytes,
        eof_bytes=manifest.config.eof_bytes,
    )
    return SourceBytePlan(source, receipt, plans, ranges)


def _source_total(plan):
    return plan.source.tbi.size_bytes + sum(item.last - item.first + 1 for item in plan.merged_vcf_ranges)


def test_complete_two_source_style_accounting_includes_all_index_fees_and_range_unions(tmp_path):
    manifest = _manifest(tmp_path)
    plans = tuple(_source_plan(manifest, index) for index in range(22))
    preflight = assemble_preflight(
        manifest, plans, manifest_sha256="4" * 64, provenance=_provenance(manifest)
    )
    expected = sum(_source_total(plan) for plan in plans)
    assert preflight.complete is True
    assert preflight.known_planned_bytes == expected
    assert preflight.total_planned_bytes == expected
    assert preflight.budget_status == "within_cap"
    assert encode_preflight(preflight).endswith(b"\n")


def test_unknown_source_ranges_make_total_null_and_preserve_known_partial_accounting(tmp_path):
    manifest = _manifest(tmp_path)
    plans = tuple(
        _source_plan(manifest, index, receipt_state="refused", refused=True)
        if index == 1
        else _source_plan(manifest, index)
        for index in range(22)
    )
    preflight = assemble_preflight(
        manifest, plans, manifest_sha256="4" * 64, provenance=_provenance(manifest)
    )
    assert preflight.complete is False
    assert preflight.total_planned_bytes is None
    assert preflight.budget_status == "incomplete"
    assert preflight.known_planned_bytes == sum(_source_total(plan) for plan in plans)


def test_cap_equality_passes_and_cap_plus_one_refuses(tmp_path):
    manifest = _manifest(tmp_path)
    base = tuple(_source_plan(manifest, index) for index in range(22))
    other_total = sum(_source_total(plan) for plan in base[1:])
    first_size = manifest.config.max_transfer_bytes - other_total - base[0].source.tbi.size_bytes
    equal_source = replace(base[0].source, vcf=replace(base[0].source.vcf, size_bytes=first_size))
    equal_manifest = replace(manifest, sources=(equal_source, *manifest.sources[1:]))
    equal_chunk = VirtualChunk(0, first_size << 16)
    equal_window = WindowBytePlan(
        base[0].windows[0].window_id,
        "index_chunks_planned",
        None,
        "not_inspected",
        (equal_chunk,),
        (ByteRange(0, first_size - 1),),
    )
    equal_first = SourceBytePlan(
        equal_source,
        base[0].receipt,
        (equal_window, *base[0].windows[1:]),
        (ByteRange(0, first_size - 1),),
    )
    equal = (equal_first, *base[1:])
    accepted = assemble_preflight(
        equal_manifest,
        equal,
        manifest_sha256="4" * 64,
        provenance=_provenance(equal_manifest),
    )
    assert accepted.total_planned_bytes == manifest.config.max_transfer_bytes
    assert accepted.budget_status == "within_cap"
    over_source = replace(equal_source, vcf=replace(equal_source.vcf, size_bytes=first_size + 1))
    over_manifest = replace(equal_manifest, sources=(over_source, *equal_manifest.sources[1:]))
    over_chunk = VirtualChunk(0, (first_size + 1) << 16)
    over_window = replace(
        equal_window,
        chunks=(over_chunk,),
        ranges=(ByteRange(0, first_size),),
    )
    over_first = replace(
        equal_first,
        source=over_source,
        windows=(over_window, *equal_first.windows[1:]),
        merged_vcf_ranges=(ByteRange(0, first_size),),
    )
    over = (over_first, *base[1:])
    refused = assemble_preflight(
        over_manifest,
        over,
        manifest_sha256="4" * 64,
        provenance=_provenance(over_manifest),
    )
    assert refused.total_planned_bytes == manifest.config.max_transfer_bytes + 1
    assert refused.budget_status == "over_cap"


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_source",
        "duplicate_source",
        "reordered_source",
        "foreign_window",
        "duplicate_window",
        "reordered_window",
    ],
)
def test_assemble_refuses_missing_duplicate_or_foreign_coverage(tmp_path, mutation):
    manifest = _manifest(tmp_path)
    plans = list(_source_plan(manifest, index) for index in range(22))
    if mutation == "missing_source":
        plans.pop()
    elif mutation == "duplicate_source":
        plans[-1] = plans[0]
    elif mutation == "reordered_source":
        plans[0], plans[1] = plans[1], plans[0]
    else:
        target = plans[0]
        windows = list(target.windows)
        if mutation == "reordered_window":
            windows[0], windows[1] = windows[1], windows[0]
        else:
            windows[-1] = windows[0] if mutation == "duplicate_window" else plans[1].windows[0]
        plans[0] = SourceBytePlan(target.source, target.receipt, tuple(windows), target.merged_vcf_ranges)
    with pytest.raises(ValueError, match="source|window"):
        assemble_preflight(manifest, tuple(plans), manifest_sha256="4" * 64, provenance=_provenance(manifest))


def test_crc32c_matches_manifest_style_big_endian_base64():
    raw = b"bounded bytes"
    encoded = base64.b64encode(crc32c(raw).to_bytes(4, "big")).decode()
    assert encoded == "cJ9wUg=="


def test_plan_window_distinguishes_index_coverage_without_claiming_variant_content(tmp_path):
    manifest = _manifest(tmp_path)
    window = manifest.windows[0]
    empty = TbiIndex(window.chrom, (), (), None, None, None, None)
    missing = plan_window(empty, window, source_size_bytes=10_000)
    assert missing.state == "no_index_chunks"
    assert missing.variant_content == "not_inspected"
    assert missing.chunks == missing.ranges == ()

    leaf_bin = 4681 + (window.start0 >> 14)
    chunk = VirtualChunk(100 << 16, 200 << 16)
    covered = TbiIndex(window.chrom, ((leaf_bin, (chunk,)),), (), None, None, None, None)
    planned = plan_window(covered, window, source_size_bytes=1_000)
    assert planned.state == "index_chunks_planned"
    assert planned.variant_content == "not_inspected"
    assert planned.chunks == (chunk,)
    assert planned.ranges == (ByteRange(100, 199),)


def test_index_ranges_overlapping_fixed_prefix_are_counted_once(tmp_path):
    manifest = _manifest(tmp_path)
    plans = list(_source_plan(manifest, index) for index in range(22))
    baseline = sum(_source_total(plan) for plan in plans)
    first = plans[0]
    window = first.windows[0]
    planned = WindowBytePlan(
        window.window_id,
        "index_chunks_planned",
        None,
        "not_inspected",
        (VirtualChunk(100 << 16, 200 << 16),),
        (ByteRange(100, 199),),
    )
    plans[0] = replace(first, windows=(planned, *first.windows[1:]))
    preflight = assemble_preflight(
        manifest,
        tuple(plans),
        manifest_sha256="4" * 64,
        provenance=_provenance(manifest),
    )
    assert preflight.total_planned_bytes == baseline
