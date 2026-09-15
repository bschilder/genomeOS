"""Bounded reference acquisition adapter controls (reference acquisition design §4.1)."""

from __future__ import annotations

import base64
import gzip
import hashlib
import json
import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

import scripts.reference_window_io as window_io
from genomeos.validation.reference_acquisition_types import ArtifactRef
from genomeos.validation.reference_byte_plan import ByteRange
from genomeos.validation.reference_genotypes import assess_call
from genomeos.validation.reference_vcf_tokens import parse_header, parse_record, project_call
from genomeos.validation.reference_window_types import SOURCE_BUCKET, SOURCE_PREFIX, PublicObject
from scripts.reference_io_common import _run_process
from scripts.reference_window_io import (
    extract_native,
    fetch_range,
    iter_native_tokens,
    iter_original_records,
    native_called_totals,
    query_native_tokens,
    read_native_totals,
    validate_verified_source,
)
from tests.reference_acquisition_fixture import NATIVE_FIXTURES, synthetic_coverage_case
from tests.reference_tbi_fixture import native_tools


def _public_object(size: int = 100_000_000) -> PublicObject:
    return PublicObject(
        f"gs://{SOURCE_BUCKET}/{SOURCE_PREFIX}chr1.vcf.bgz",
        "123",
        size,
        base64.b64encode(bytes(16)).decode(),
        base64.b64encode(bytes(4)).decode(),
    )


def _wrapper(tmp_path: Path, body: str) -> tuple[Path, Path]:
    ledger = tmp_path / "argv.json"
    path = tmp_path / "wrapper.py"
    path.write_text(
        "import json, os, sys, time\n"
        "assert os.environ['CLOUDSDK_STORAGE_MAX_RETRIES'] == '0'\n"
        "assert sys.argv[1:4] == ['run','storage','cat']\n"
        "assert '#' in sys.argv[-1]\n"
        f"open({str(ledger)!r},'w').write(json.dumps(sys.argv[1:]))\n" + body + "\n",
        encoding="utf-8",
    )
    return path, ledger


def _artifact(root: Path, relative: str) -> ArtifactRef:
    raw = (root / relative).read_bytes()
    return ArtifactRef(relative, len(raw), hashlib.sha256(raw).hexdigest())


def test_fetch_range_records_one_generation_pinned_invocation(tmp_path):
    wrapper, ledger = _wrapper(tmp_path, "sys.stdout.buffer.write(b'abc')")
    receipt = fetch_range(
        _public_object(),
        ByteRange(10, 12),
        wrapper=wrapper,
        artifact_root=tmp_path,
        destination=tmp_path / "range.bin",
    )
    assert (receipt.state, receipt.requested_bytes, receipt.received_bytes) == ("verified", 3, 3)
    assert receipt.adapter_invocations == 1
    assert receipt.sha256 == hashlib.sha256(b"abc").hexdigest()
    assert json.loads(ledger.read_text())[-2:] == ["--range=10-12", f"{_public_object().uri}#123"]


@pytest.mark.parametrize(
    "last,body,state,reason,expected,exit_code",
    [
        (13, "sys.stdout.buffer.write(b'abc')", "partial", "size_mismatch", b"abc", 0),
        (11, "sys.stdout.buffer.write(b'abc')", "refused", "limit_exceeded", b"abc", 0),
        (12, "sys.stdout.buffer.write(b'ab');sys.exit(7)", "partial", "transfer_failed", b"ab", 7),
    ],
)
def test_fetch_range_retains_exact_failed_prefix(tmp_path, last, body, state, reason, expected, exit_code):
    wrapper, _ = _wrapper(tmp_path, body)
    receipt = fetch_range(
        _public_object(),
        ByteRange(10, last),
        wrapper=wrapper,
        artifact_root=tmp_path,
        destination=tmp_path / "range.bin",
    )
    assert (receipt.state, receipt.reason, receipt.received_bytes, receipt.exit_code) == (
        state,
        reason,
        len(expected),
        exit_code,
    )
    assert (tmp_path / receipt.retained.path).read_bytes() == expected


def test_fetch_range_timeout_retains_prefix_and_never_retries(tmp_path, monkeypatch):
    wrapper, ledger = _wrapper(tmp_path, "sys.stdout.buffer.write(b'a');sys.stdout.flush();time.sleep(10)")
    monkeypatch.setattr(window_io, "RANGE_TIMEOUT_SECONDS", 0.05)
    receipt = fetch_range(
        _public_object(),
        ByteRange(10, 12),
        wrapper=wrapper,
        artifact_root=tmp_path,
        destination=tmp_path / "range.bin",
    )
    assert (receipt.state, receipt.reason, receipt.received_bytes) == ("partial", "timeout", 1)
    assert receipt.adapter_invocations == 1 and ledger.exists()


def test_existing_range_destination_refuses_before_spawn(tmp_path):
    wrapper, ledger = _wrapper(tmp_path, "sys.stdout.buffer.write(b'abc')")
    destination = tmp_path / "range.bin"
    destination.write_bytes(b"existing")
    with pytest.raises(FileExistsError):
        fetch_range(
            _public_object(),
            ByteRange(10, 12),
            wrapper=wrapper,
            artifact_root=tmp_path,
            destination=destination,
        )
    assert not ledger.exists()


def test_fetch_range_streams_large_body_to_file(tmp_path):
    size = 64 * 1024 * 1024
    wrapper, _ = _wrapper(
        tmp_path,
        "chunk=b'x'*(1024*1024)\nfor _ in range(64): sys.stdout.buffer.write(chunk)",
    )
    receipt = fetch_range(
        _public_object(size),
        ByteRange(0, size - 1),
        wrapper=wrapper,
        artifact_root=tmp_path,
        destination=tmp_path / "large.bin",
    )
    assert receipt.state == "verified" and receipt.received_bytes == size
    assert receipt.sha256 == hashlib.sha256(b"x" * size).hexdigest()


def test_bounded_process_stops_on_stderr_first_and_retains_cap_plus_one(tmp_path):
    child = tmp_path / "child.py"
    child.write_text("import sys,time\nsys.stderr.buffer.write(b'abc')\nsys.stderr.flush()\ntime.sleep(10)\n")
    result = _run_process(
        [sys.executable, str(child)],
        artifact_root=tmp_path,
        stdout_path="stdout.partial",
        stderr_path="stderr.partial",
        stdout_limit=10,
        stderr_limit=2,
        timeout=2,
    )
    assert result.stderr_limit_exceeded and not result.stdout_limit_exceeded
    assert result.stderr.size_bytes == 3 and result.stdout.size_bytes == 0


def test_saved_coverage_requires_actual_range_bytes(tmp_path):
    plan, verified, window, header = synthetic_coverage_case(tmp_path)
    first = verified.ranges[0].range_file
    path = tmp_path / first.path
    original = path.read_bytes()
    path.chmod(0o600)
    path.write_bytes(bytes([original[0] ^ 1]) + original[1:])
    with pytest.raises(ValueError):
        validate_verified_source(verified, plan, artifact_root=tmp_path)
    with pytest.raises(ValueError):
        tuple(
            iter_original_records(
                verified,
                plan,
                window,
                header,
                artifact_root=tmp_path,
                raw_destination=tmp_path / "new.raw.tsv",
                offsets_destination=tmp_path / "new.offsets.tsv",
            )
        )


def test_planned_ranges_cannot_replace_missing_acquired_coverage(tmp_path):
    plan, verified, _, _ = synthetic_coverage_case(tmp_path)
    with pytest.raises(ValueError):
        validate_verified_source(replace(verified, ranges=()), plan, artifact_root=tmp_path)


def test_sparse_extent_index_and_generation_are_revalidated(tmp_path):
    plan, verified, _, _ = synthetic_coverage_case(tmp_path)
    sparse = tmp_path / verified.sparse_path
    sparse.chmod(0o600)
    with sparse.open("r+b") as handle:
        handle.write(b"bad")
    with pytest.raises(ValueError):
        validate_verified_source(verified, plan, artifact_root=tmp_path)

    plan2, verified2, _, _ = synthetic_coverage_case(tmp_path / "index")
    index = tmp_path / "index" / verified2.index.path
    index.chmod(0o600)
    index.write_bytes(b"bad")
    with pytest.raises(ValueError):
        validate_verified_source(verified2, plan2, artifact_root=tmp_path / "index")
    with pytest.raises(ValueError):
        validate_verified_source(
            replace(
                verified2,
                source=replace(verified2.source, vcf=replace(verified2.source.vcf, generation="999")),
            ),
            plan2,
            artifact_root=tmp_path / "index",
        )


def test_verified_source_is_relocatable_by_relative_content_identity(tmp_path):
    original = tmp_path / "original"
    relocated = tmp_path / "relocated"
    plan, verified, _, _ = synthetic_coverage_case(original)
    assert len(verified.ranges) == 2
    assert verified.ranges[0].last + 1 < verified.ranges[1].first
    assert sum(value.range_file.size_bytes for value in verified.ranges) < verified.logical_size_bytes
    shutil.copytree(original, relocated)
    validate_verified_source(verified, plan, artifact_root=relocated)


def test_original_reader_emits_exact_pos_selected_lines_and_offsets(tmp_path):
    plan, verified, window, header = synthetic_coverage_case(tmp_path)
    raw_path = tmp_path / "windows" / "chr1-s1.raw.tsv"
    offsets_path = tmp_path / "windows" / "chr1-s1.offsets.tsv"
    records = tuple(
        iter_original_records(
            verified,
            plan,
            window,
            header,
            artifact_root=tmp_path,
            raw_destination=raw_path,
            offsets_destination=offsets_path,
        )
    )
    assert [(value.pos1, value.ref, value.alt) for value in records] == [
        (101, "A", "G"),
        (102, "C", "T"),
        (103, "A", "G,T"),
        (104, "G", "A"),
        (105, "A", "C"),
        (105, "A", "T"),
        (10_100, "T", "C"),
    ]
    raw_lines = raw_path.read_bytes().splitlines(keepends=True)
    assert [hashlib.sha256(line).hexdigest() for line in raw_lines] == [value.raw_sha256 for value in records]
    offsets = offsets_path.read_text().splitlines()
    assert offsets[0] == "ordinal\tsource_virtual_offset\traw_sha256"
    assert len(offsets) == len(records) + 1
    assert len({value.source_virtual_offset for value in records}) == len(records)


def test_original_reader_binds_header_evidence_to_acquired_source(tmp_path):
    plan, verified, window, header = synthetic_coverage_case(tmp_path)
    with pytest.raises(ValueError, match="header evidence"):
        tuple(
            iter_original_records(
                verified,
                plan,
                window,
                replace(header, raw_sha256="f" * 64),
                artifact_root=tmp_path,
                raw_destination=tmp_path / "wrong.raw.tsv",
                offsets_destination=tmp_path / "wrong.offsets.tsv",
            )
        )


def test_checked_in_native_fixture_has_frozen_identity():
    evidence = json.loads((NATIVE_FIXTURES / "evidence.json").read_text())
    for name, expected in evidence["fixture_sha256"].items():
        assert hashlib.sha256((NATIVE_FIXTURES / name).read_bytes()).hexdigest() == expected


def test_original_overflow_integer_remains_valid_before_native_normalization():
    expanded = gzip.decompress((NATIVE_FIXTURES / "malformed.vcf.bgz").read_bytes())
    marker = expanded.index(b"#CHROM")
    header_end = expanded.index(b"\n", marker) + 1
    header = parse_header(
        expanded[:header_end],
        expected_contigs=(("chr1", 1_000_000),),
        source_chrom="chr1",
        expected_samples=("s1",),
    )
    record = parse_record(expanded[header_end:], source_virtual_offset=0, header=header)
    call = project_call(record.format_keys, record.sample_tokens[0])
    assert call.gq == "2147483648"
    assert assess_call(call.gt, call.gq, call.dp, call.ad).disposition == "accepted"


@pytest.mark.skipif(native_tools() is None, reason="bcftools/bgzip/tabix are unavailable")
def test_live_native_full_and_sparse_controls(tmp_path):
    tools = native_tools()
    assert tools is not None
    _, _, bcftools = (Path(value) for value in tools)
    version = subprocess.run([bcftools, "--version"], check=True, capture_output=True, text=True).stdout
    assert version.startswith("bcftools 1.23.1\nUsing htslib 1.23.1")

    plan, verified, window, _ = synthetic_coverage_case(tmp_path)
    run = extract_native(
        verified,
        plan,
        window,
        artifact_root=tmp_path,
        bcftools=bcftools,
        stdout_path="windows/chr1-s1.window.bcf",
        stderr_path="windows/chr1-s1.window.stderr",
    )
    assert run.state == "complete" and "-o" not in run.argv_template
    assert (run.stdout_limit_bytes, run.stderr_limit_bytes) == (2_147_483_648, 1_048_576)
    query = query_native_tokens(
        run.stdout,
        artifact_root=tmp_path,
        bcftools=bcftools,
        output_prefix="windows/chr1-s1.native",
    )
    native = tuple(iter_native_tokens(query, artifact_root=tmp_path))
    assert query.sample_query.stdout_limit_bytes == 1_048_576
    assert query.token_query is not None and query.token_query.stdout_limit_bytes == 2_147_483_648
    assert [(row.variant_id, row.sample_ids) for row in native] == [
        (f"GRCh38:chr1:{pos}:{ref}:{alt}", ("s1", "s2"))
        for pos, ref, alt in [
            (101, "A", "G"),
            (102, "C", "T"),
            (103, "A", "G,T"),
            (104, "G", "A"),
            (105, "A", "C"),
            (105, "A", "T"),
            (10_100, "T", "C"),
        ]
    ]
    evidence = json.loads((NATIVE_FIXTURES / "evidence.json").read_text())
    full_keys = subprocess.run(
        [
            bcftools,
            "query",
            "--regions-overlap",
            "0",
            "-r",
            "chr1:101-10100",
            "-f",
            r"%CHROM\t%POS\t%REF\t%ALT\t%FILTER\n",
            NATIVE_FIXTURES / "synthetic.vcf.bgz",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    sparse_keys = subprocess.run(
        [
            bcftools,
            "query",
            "-f",
            r"%CHROM\t%POS\t%REF\t%ALT\t%FILTER\n",
            tmp_path / run.stdout.path,
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert full_keys == sparse_keys == evidence["native_keys"]

    normalized = subprocess.run(
        [bcftools, "query", "-f", r"[%GT:%GQ:%DP:%AD\n]", NATIVE_FIXTURES / "malformed.vcf.bgz"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert normalized == evidence["malformed_native_token"]

    (tmp_path / "cohort.samples.txt").write_text("s1\ns2\n")
    cohort = _artifact(tmp_path, "cohort.samples.txt")
    control = native_called_totals(
        run.stdout,
        cohort,
        acquisition_root=tmp_path,
        artifact_root=tmp_path,
        bcftools=bcftools,
        output_prefix="windows/chr1-s1.counts",
    )
    assert control.state == "complete"
    assert [value.stdout_limit_bytes for value in control.runs] == [
        2_147_483_648,
        2_147_483_648,
        1_048_576,
        2_147_483_648,
    ]
    with pytest.raises(ValueError, match="native_count_unavailable"):
        read_native_totals(control, artifact_root=tmp_path)
