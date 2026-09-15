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

import scripts.reference_io_common as io_common
import scripts.reference_native_io as native_io
import scripts.reference_window_io as window_io
from genomeos.validation.reference_acquisition_types import (
    ArtifactRef,
    MetadataReceipt,
    NativeRunReceipt,
    NativeTokenFiles,
)
from genomeos.validation.reference_byte_plan import ByteRange, chunk_byte_range
from genomeos.validation.reference_genotypes import assess_call
from genomeos.validation.reference_tbi import VirtualChunk
from genomeos.validation.reference_vcf_tokens import parse_header, parse_record, project_call
from genomeos.validation.reference_window_types import SOURCE_BUCKET, SOURCE_PREFIX, PublicObject
from scripts.reference_io_common import _run_process
from scripts.reference_window_io import (
    extract_native,
    fetch_metadata,
    fetch_range,
    iter_native_tokens,
    iter_original_records,
    native_called_totals,
    query_native_tokens,
    read_native_totals,
    validate_metadata_receipt,
    validate_original_records,
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
        "assert os.environ['CLOUDSDK_COMPONENT_MANAGER_DISABLE_UPDATE_CHECK'] == 'true'\n"
        "assert os.environ['CLOUDSDK_STORAGE_MAX_RETRIES'] == '0'\n"
        "assert sys.argv[1:4] == ['run','storage','cat']\n"
        "assert '#' in sys.argv[-1]\n"
        f"open({str(ledger)!r},'w').write(json.dumps(sys.argv[1:]))\n" + body + "\n",
        encoding="utf-8",
    )
    return path, ledger


def _metadata_wrapper(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "metadata-wrapper.py"
    path.write_text(
        "import os, sys, time\n"
        "assert os.environ['CLOUDSDK_COMPONENT_MANAGER_DISABLE_UPDATE_CHECK'] == 'true'\n"
        "assert os.environ['CLOUDSDK_STORAGE_MAX_RETRIES'] == '0'\n"
        "assert sys.argv[1:5] == ['run','storage','objects','describe']\n"
        "assert '#' in sys.argv[5]\n" + body + "\n",
        encoding="utf-8",
    )
    return path


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
    assert receipt.retained.path == "range.bin"
    assert receipt.stderr.path == "range.bin.stderr"
    assert not (tmp_path / "range.bin.partial").exists()
    assert not (tmp_path / "range.bin.stderr.partial").exists()
    assert json.loads(ledger.read_text())[-2:] == ["--range=10-12", f"{_public_object().uri}#123"]


def test_metadata_validator_rejects_rehashed_semantic_mutation(tmp_path):
    source = _public_object()
    retained = tmp_path / "metadata.json"
    stderr = tmp_path / "metadata.stderr"
    stderr.write_bytes(b"")
    raw = (
        json.dumps(
            {
                "generation": source.generation,
                "size": str(source.size_bytes),
                "md5Hash": source.md5_b64,
                "crc32c": source.crc32c_b64,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode()
    retained.write_bytes(raw)
    receipt = MetadataReceipt(
        "verified",
        None,
        1,
        len(raw),
        _artifact(tmp_path, "metadata.json"),
        _artifact(tmp_path, "metadata.stderr"),
        0,
        False,
        False,
    )
    validate_metadata_receipt(source, receipt, artifact_root=tmp_path)

    changed = raw.replace(b'"generation":"123"', b'"generation":"124"')
    retained.write_bytes(changed)
    changed_receipt = replace(
        receipt,
        stdout_bytes=len(changed),
        retained=_artifact(tmp_path, "metadata.json"),
    )
    with pytest.raises(ValueError, match="metadata_mismatch"):
        validate_metadata_receipt(source, changed_receipt, artifact_root=tmp_path)


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
    assert receipt.retained.path.endswith(".partial")
    assert receipt.stderr.path.endswith(".partial")
    assert (tmp_path / receipt.retained.path).read_bytes() == expected
    assert not (tmp_path / "range.bin").exists()
    assert not (tmp_path / "range.bin.stderr").exists()


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
    assert receipt.retained.path.endswith(".partial")
    assert receipt.adapter_invocations == 1 and ledger.exists()


def test_fetch_metadata_timeout_is_distinct_from_generation_unavailable(tmp_path, monkeypatch):
    wrapper = _metadata_wrapper(
        tmp_path,
        "sys.stdout.buffer.write(b'{');sys.stdout.flush();time.sleep(10)",
    )
    monkeypatch.setattr(window_io, "METADATA_TIMEOUT_SECONDS", 0.05)
    receipt = fetch_metadata(
        _public_object(),
        wrapper=wrapper,
        artifact_root=tmp_path,
        destination=tmp_path / "metadata.json",
    )
    assert receipt.state == "refused"
    assert receipt.reason == "timeout"
    assert receipt.adapter_invocations == 1
    assert receipt.retained.path == "metadata.json.partial"
    assert receipt.stderr.path == "metadata.json.stderr.partial"
    assert not (tmp_path / "metadata.json").exists()
    assert not (tmp_path / "metadata.json.stderr").exists()


def test_process_promotion_failure_restores_partial_only_outputs(tmp_path, monkeypatch):
    wrapper, _ = _wrapper(tmp_path, "sys.stdout.buffer.write(b'abc')")
    original_rename = Path.rename

    def fail_stdout_promotion(path, target):
        if path.name == "range.bin.partial":
            raise OSError("synthetic promotion fault")
        return original_rename(path, target)

    monkeypatch.setattr(Path, "rename", fail_stdout_promotion)
    with pytest.raises(OSError, match="synthetic promotion fault"):
        fetch_range(
            _public_object(),
            ByteRange(10, 12),
            wrapper=wrapper,
            artifact_root=tmp_path,
            destination=tmp_path / "range.bin",
        )
    assert (tmp_path / "range.bin.partial").read_bytes() == b"abc"
    assert (tmp_path / "range.bin.stderr.partial").read_bytes() == b""
    assert not (tmp_path / "range.bin").exists()
    assert not (tmp_path / "range.bin.stderr").exists()


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


def test_bounded_process_storage_fault_retains_only_partial_prefix(tmp_path, monkeypatch):
    child = tmp_path / "child.py"
    child.write_text(
        "import sys\n"
        "chunk=b'x'*(1024*1024)\n"
        "sys.stdout.buffer.write(chunk)\n"
        "sys.stdout.buffer.flush()\n"
        "sys.stdout.buffer.write(chunk)\n",
        encoding="utf-8",
    )
    original_write = io_common._write_chunk
    retained_bytes = 0

    def fail_second_stdout_write(output, raw):
        nonlocal retained_bytes
        if raw and retained_bytes >= 1_048_576:
            raise OSError("synthetic storage fault")
        original_write(output, raw)
        retained_bytes += len(raw)

    monkeypatch.setattr(io_common, "_write_chunk", fail_second_stdout_write)
    with pytest.raises(OSError, match="synthetic storage fault"):
        _run_process(
            [sys.executable, str(child)],
            artifact_root=tmp_path,
            stdout_path="stdout.partial",
            stderr_path="stderr.partial",
            stdout_limit=3 * 1024 * 1024,
            stderr_limit=1_024,
            timeout=10,
        )
    assert 1_048_576 <= (tmp_path / "stdout.partial").stat().st_size < 2_097_152
    assert (tmp_path / "stderr.partial").is_file()
    assert not (tmp_path / "stdout").exists()
    assert not (tmp_path / "stderr").exists()


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


def test_verified_source_rejects_rehashed_noncanonical_eof(tmp_path):
    plan, verified, _, _ = synthetic_coverage_case(tmp_path)
    tail = verified.ranges[-1]
    tail_path = tmp_path / tail.range_file.path
    sparse_path = tmp_path / verified.sparse_path
    tail_path.chmod(0o600)
    sparse_path.chmod(0o600)
    changed = bytearray(tail_path.read_bytes())
    changed[-1] = 1
    tail_path.write_bytes(changed)
    with sparse_path.open("r+b") as stream:
        stream.seek(tail.last)
        stream.write(b"\x01")
    changed_ref = _artifact(tmp_path, tail.range_file.path)
    changed_verified = replace(
        verified,
        ranges=(*verified.ranges[:-1], replace(tail, range_file=changed_ref)),
    )
    with pytest.raises(ValueError, match="canonical BGZF EOF marker"):
        validate_verified_source(changed_verified, plan, artifact_root=tmp_path)


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


def test_original_reader_proves_virtual_chunk_start_is_a_record_boundary(tmp_path):
    plan, verified, window, header = synthetic_coverage_case(tmp_path)
    original = plan.windows[0]
    chunk = original.chunks[0]
    inside_record = VirtualChunk(chunk.begin + 1, chunk.end)
    changed_window = replace(
        original,
        chunks=(inside_record,),
        ranges=(chunk_byte_range(inside_record, source_size_bytes=plan.source.vcf.size_bytes),),
    )
    changed = replace(plan, windows=(changed_window, *plan.windows[1:]))
    with pytest.raises(ValueError, match="starts inside a record"):
        tuple(
            iter_original_records(
                verified,
                changed,
                window,
                header,
                artifact_root=tmp_path,
                raw_destination=tmp_path / "windows/bad-boundary.raw.tsv",
                offsets_destination=tmp_path / "windows/bad-boundary.offsets.tsv",
            )
        )


def test_original_reader_refuses_when_chunk_predecessor_is_not_retained(tmp_path, monkeypatch):
    plan, verified, window, header = synthetic_coverage_case(tmp_path)
    monkeypatch.setattr(window_io, "_predecessor_byte", lambda handles, physical: None)
    with pytest.raises(ValueError, match="predecessor is outside reviewed ranges"):
        tuple(
            iter_original_records(
                verified,
                plan,
                window,
                header,
                artifact_root=tmp_path,
                raw_destination=tmp_path / "windows/unproved-boundary.raw.tsv",
                offsets_destination=tmp_path / "windows/unproved-boundary.offsets.tsv",
            )
        )


def test_decoded_window_limit_charges_full_bgzf_member_for_a_tiny_slice(tmp_path, monkeypatch):
    plan, verified, window, header = synthetic_coverage_case(tmp_path)
    original = plan.windows[0]
    tiny = VirtualChunk(original.chunks[0].begin, original.chunks[0].begin + 1)
    changed_window = replace(
        original,
        chunks=(tiny,),
        ranges=(chunk_byte_range(tiny, source_size_bytes=plan.source.vcf.size_bytes),),
    )
    changed = replace(plan, windows=(changed_window, *plan.windows[1:]))
    monkeypatch.setattr(window_io, "DECODED_WINDOW_LIMIT_BYTES", 1)
    with pytest.raises(ValueError, match="limit_exceeded"):
        tuple(
            iter_original_records(
                verified,
                changed,
                window,
                header,
                artifact_root=tmp_path,
                raw_destination=tmp_path / "windows/tiny.raw.tsv",
                offsets_destination=tmp_path / "windows/tiny.offsets.tsv",
            )
        )


def test_candidate_record_limit_counts_rows_rejected_by_position(tmp_path, monkeypatch):
    plan, verified, window, header = synthetic_coverage_case(tmp_path)
    monkeypatch.setattr(window_io, "RECORDS_PER_WINDOW_LIMIT", 1)
    monkeypatch.setattr(window_io, "site_disposition", lambda record, target: "outside_pos")
    with pytest.raises(ValueError, match="limit_exceeded"):
        tuple(
            iter_original_records(
                verified,
                plan,
                window,
                header,
                artifact_root=tmp_path,
                raw_destination=tmp_path / "windows/candidates.raw.tsv",
                offsets_destination=tmp_path / "windows/candidates.offsets.tsv",
            )
        )


def test_original_validator_rederives_source_rows_offsets_and_native_keys(tmp_path):
    plan, verified, window, header = synthetic_coverage_case(tmp_path)
    records = tuple(
        iter_original_records(
            verified,
            plan,
            window,
            header,
            artifact_root=tmp_path,
            raw_destination=tmp_path / "windows/chr1-s1.raw.tsv",
            offsets_destination=tmp_path / "windows/chr1-s1.offsets.tsv",
        )
    )
    native_path = tmp_path / "windows/chr1-s1.native-keys.tsv"
    native_path.write_bytes(
        b"".join(
            f"{row.chrom}\t{row.pos1}\t{row.ref}\t{row.alt}\t{row.filter}\n".encode()
            for row in records
        )
    )
    assert validate_original_records(
        verified,
        plan,
        window,
        header,
        artifact_root=tmp_path,
        raw=_artifact(tmp_path, "windows/chr1-s1.raw.tsv"),
        offsets=_artifact(tmp_path, "windows/chr1-s1.offsets.tsv"),
        native_keys=_artifact(tmp_path, "windows/chr1-s1.native-keys.tsv"),
    ) == len(records)

    native_path.write_bytes(native_path.read_bytes() + b"chr1\t999999\tA\tG\tPASS\n")
    with pytest.raises(ValueError, match="native_mismatch"):
        validate_original_records(
            verified,
            plan,
            window,
            header,
            artifact_root=tmp_path,
            raw=_artifact(tmp_path, "windows/chr1-s1.raw.tsv"),
            offsets=_artifact(tmp_path, "windows/chr1-s1.offsets.tsv"),
            native_keys=_artifact(tmp_path, "windows/chr1-s1.native-keys.tsv"),
        )


def test_native_token_reader_enforces_per_line_bound(tmp_path, monkeypatch):
    bcf = tmp_path / "window.bcf"
    samples = tmp_path / "samples.txt"
    tokens = tmp_path / "tokens.tsv"
    stderr = tmp_path / "stderr"
    bcf.write_bytes(b"BCF\x04\x02")
    samples.write_bytes(b"s1\n")
    tokens.write_bytes(b"chr1\t1\tA\tG\t0/1:30:20:10,10\n")
    stderr.write_bytes(b"")
    bcf_ref = _artifact(tmp_path, "window.bcf")
    samples_ref = _artifact(tmp_path, "samples.txt")
    tokens_ref = _artifact(tmp_path, "tokens.tsv")
    stderr_ref = _artifact(tmp_path, "stderr")
    sample_run = NativeRunReceipt(
        "query_samples", ("bcftools", "query", "-l", "window.bcf"),
        "complete", None, 0, samples_ref, stderr_ref,
        1_048_576, 1_048_576, False, False,
    )
    token_run = NativeRunReceipt(
        "query_tokens", ("bcftools", "query", "-f", "format", "window.bcf"),
        "complete", None, 0, tokens_ref, stderr_ref,
        2_147_483_648, 1_048_576, False, False,
    )
    query = NativeTokenFiles(
        bcf_ref, samples_ref, tokens_ref, sample_run, token_run, "complete", None,
    )
    monkeypatch.setattr(native_io, "RECORD_LIMIT_BYTES", 8)
    with pytest.raises(ValueError, match="native_encoding_refused"):
        tuple(iter_native_tokens(query, artifact_root=tmp_path))


def test_native_decimal_parser_normalizes_interpreter_digit_limit():
    with pytest.raises(ValueError, match="^native_encoding_refused$"):
        native_io._native_natural("9" * 5_000)


def test_native_count_producer_refuses_duplicate_selected_sample_ids(tmp_path, monkeypatch):
    (tmp_path / "window.bcf").write_bytes(b"BCF\x04\x02")
    (tmp_path / "cohort.samples.txt").write_bytes(b"s1\n")

    def native_receipt(
        operation,
        argv,
        argv_template,
        *,
        artifact_root,
        stdout_path,
        stderr_path,
        stdout_limit,
    ):
        del argv
        if operation in ("select_cohort", "fill_tags"):
            raw = b"BCF\x04\x02"
        elif operation == "query_samples":
            raw = b"s1\ns1\n"
        else:
            raise AssertionError("duplicate sample IDs must refuse before totals")
        output = artifact_root / stdout_path
        error = artifact_root / stderr_path
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(raw)
        error.write_bytes(b"")
        return NativeRunReceipt(
            operation,
            argv_template,
            "complete",
            None,
            0,
            _artifact(artifact_root, stdout_path),
            _artifact(artifact_root, stderr_path),
            stdout_limit,
            1_048_576,
            False,
            False,
        )

    monkeypatch.setattr(native_io, "_native_receipt", native_receipt)
    control = native_called_totals(
        _artifact(tmp_path, "window.bcf"),
        _artifact(tmp_path, "cohort.samples.txt"),
        acquisition_root=tmp_path,
        artifact_root=tmp_path,
        bcftools=tmp_path / "unused-bcftools",
        output_prefix="native/test",
    )
    assert control.state == "refused"
    assert control.reason == "native_mismatch"
    assert len(control.runs) == 3


def test_native_count_producer_retains_run_lineage_on_invalid_selected_samples(
    tmp_path, monkeypatch,
):
    (tmp_path / "window.bcf").write_bytes(b"BCF\x04\x02")
    (tmp_path / "cohort.samples.txt").write_bytes(b"s1\n")

    def native_receipt(
        operation,
        argv,
        argv_template,
        *,
        artifact_root,
        stdout_path,
        stderr_path,
        stdout_limit,
    ):
        del argv
        raw = b"BCF\x04\x02" if operation in ("select_cohort", "fill_tags") else b"\xff\n"
        output = artifact_root / stdout_path
        error = artifact_root / stderr_path
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(raw)
        error.write_bytes(b"")
        return NativeRunReceipt(
            operation,
            argv_template,
            "complete",
            None,
            0,
            _artifact(artifact_root, stdout_path),
            _artifact(artifact_root, stderr_path),
            stdout_limit,
            1_048_576,
            False,
            False,
        )

    monkeypatch.setattr(native_io, "_native_receipt", native_receipt)
    control = native_called_totals(
        _artifact(tmp_path, "window.bcf"),
        _artifact(tmp_path, "cohort.samples.txt"),
        acquisition_root=tmp_path,
        artifact_root=tmp_path,
        bcftools=tmp_path / "unused-bcftools",
        output_prefix="native/test",
    )
    assert (control.state, control.reason) == ("refused", "native_encoding_refused")
    assert [run.operation for run in control.runs] == [
        "select_cohort",
        "fill_tags",
        "query_samples",
    ]
    assert control.selected_bcf is not None
    assert control.recomputed_bcf is not None
    assert control.selected_samples is not None


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
