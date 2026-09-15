"""Fetch and stage bounded reference bytes (reference acquisition design §4.1)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from genomeos.validation.reference_acquisition_types import (
    ArtifactRef,
    MetadataReceipt,
    RangeReceipt,
    VerifiedRange,
    VerifiedSource,
)
from genomeos.validation.reference_byte_plan import ByteRange, SourceBytePlan
from genomeos.validation.reference_window_types import PublicObject
from scripts.reference_io_common import (
    SPARSE_ALLOCATION_SLACK_BYTES,
    TRANSFER_PIECE_BYTES,
    _allocated,
    _close_stable_artifact,
    _destination,
    _existing,
    _open_stable_artifact,
    _partial_process_paths,
    _promote_process_outputs,
    _require,
    _run_process,
    _stable_hashes,
    _validate_artifact,
)
from scripts.reference_window_read import (
    _file_identity,
    _handle_identity,
    _open_verified_range,
    _RangeHandle,
)

RANGE_TIMEOUT_SECONDS = 1_800
METADATA_TIMEOUT_SECONDS = 120
STDERR_LIMIT_BYTES = 1_048_576
_EOF = bytes.fromhex("1f8b08040000000000ff0600424302001b0003000000000000000000")

def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        _require(key not in result, "duplicate metadata key")
        result[key] = value
    return result


def validate_metadata_receipt(
    source: PublicObject,
    receipt: MetadataReceipt,
    *,
    artifact_root: Path,
) -> None:
    """Replay verified metadata or prove a zero-exit mismatch refusal is truthful."""
    _require(
        type(source) is PublicObject
        and type(receipt) is MetadataReceipt
        and receipt.state != "not_attempted"
        and receipt.retained is not None,
        "metadata receipt was not attempted",
    )
    matches = False
    raw = _validate_artifact(artifact_root, receipt.retained).read_bytes()
    try:
        value = json.loads(raw, object_pairs_hook=_unique_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        value = None
    else:
        expected = {
            "generation": source.generation,
            "size": str(source.size_bytes),
            "md5Hash": source.md5_b64,
            "crc32c": source.crc32c_b64,
        }
        matches = type(value) is dict and all(
            value.get(key) == item for key, item in expected.items()
        )
    if receipt.state == "verified":
        _require(matches, "metadata_mismatch")
    elif (
        receipt.exit_code == 0
        and not receipt.stdout_limit_exceeded
        and not receipt.stderr_limit_exceeded
    ):
        _require(not matches, "metadata refusal is not reproduced")


def fetch_metadata(
    source: PublicObject,
    *,
    wrapper: Path,
    artifact_root: Path,
    destination: Path,
    gcloud_executable: Path | None = None,
) -> MetadataReceipt:
    """Fetch and qualify one generation-pinned metadata document once."""
    _require(type(source) is PublicObject and wrapper.is_file() and not wrapper.is_symlink(),
             "invalid metadata input")
    stderr_destination = Path(f"{destination}.stderr")
    stdout_partial, stderr_partial = _partial_process_paths(
        artifact_root, destination, stderr_destination
    )
    result = _run_process(
        [
            sys.executable,
            str(wrapper),
            "run",
            "storage",
            "objects",
            "describe",
            f"{source.uri}#{source.generation}",
            "--raw",
            "--format=json",
        ],
        artifact_root=artifact_root,
        stdout_path=stdout_partial,
        stderr_path=stderr_partial,
        stdout_limit=1_048_576,
        stderr_limit=STDERR_LIMIT_BYTES,
        timeout=METADATA_TIMEOUT_SECONDS,
        environment=(
            None
            if gcloud_executable is None
            else {"GENOMEOS_GCLOUD_EXECUTABLE": str(gcloud_executable)}
        ),
    )
    reason = None
    if result.stdout_limit_exceeded or result.stderr_limit_exceeded:
        reason = "limit_exceeded"
    elif result.timed_out:
        reason = "timeout"
    elif result.exit_code != 0:
        reason = "generation_unavailable"
    else:
        try:
            raw = _existing(artifact_root, result.stdout).read_bytes()
            value = json.loads(raw, object_pairs_hook=_unique_pairs)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            reason = "metadata_mismatch"
        else:
            expected = {
                "generation": source.generation,
                "size": str(source.size_bytes),
                "md5Hash": source.md5_b64,
                "crc32c": source.crc32c_b64,
            }
            if type(value) is not dict or any(value.get(key) != item for key, item in expected.items()):
                reason = "metadata_mismatch"
    retained, retained_stderr = result.stdout, result.stderr
    if reason is None:
        retained, retained_stderr = _promote_process_outputs(
            artifact_root, result.stdout, result.stderr
        )
    return MetadataReceipt(
        "verified" if reason is None else "refused",
        reason,
        1,
        result.stdout.size_bytes,
        retained,
        retained_stderr,
        result.exit_code,
        result.stdout_limit_exceeded,
        result.stderr_limit_exceeded,
    )


def fetch_range(
    source: PublicObject,
    byte_range: ByteRange,
    *,
    wrapper: Path,
    artifact_root: Path,
    destination: Path,
    gcloud_executable: Path | None = None,
) -> RangeReceipt:
    """Fetch one generation-pinned byte range through one bounded wrapper invocation."""
    _require(type(source) is PublicObject and type(byte_range) is ByteRange, "invalid range input")
    _require(byte_range.last < source.size_bytes, "byte range is outside source")
    _require(isinstance(wrapper, Path) and wrapper.is_file() and not wrapper.is_symlink(), "invalid wrapper")
    requested = byte_range.last - byte_range.first + 1
    stderr = Path(f"{destination}.stderr")
    stdout_partial, stderr_partial = _partial_process_paths(
        artifact_root, destination, stderr
    )
    result = _run_process(
        [
            sys.executable,
            str(wrapper),
            "run",
            "storage",
            "cat",
            f"--range={byte_range.first}-{byte_range.last}",
            f"{source.uri}#{source.generation}",
        ],
        artifact_root=artifact_root,
        stdout_path=stdout_partial,
        stderr_path=stderr_partial,
        stdout_limit=requested,
        stderr_limit=STDERR_LIMIT_BYTES,
        timeout=RANGE_TIMEOUT_SECONDS,
        environment=(
            None
            if gcloud_executable is None
            else {"GENOMEOS_GCLOUD_EXECUTABLE": str(gcloud_executable)}
        ),
    )
    if result.stdout_limit_exceeded or result.stderr_limit_exceeded:
        state, reason = "refused", "limit_exceeded"
    elif result.timed_out:
        state, reason = "partial", "timeout"
    elif result.exit_code != 0:
        state, reason = "partial", "transfer_failed"
    elif result.stdout.size_bytes != requested:
        state, reason = "partial", "size_mismatch"
    else:
        state, reason = "verified", None
    retained, retained_stderr = result.stdout, result.stderr
    if state == "verified":
        retained, retained_stderr = _promote_process_outputs(
            artifact_root, result.stdout, result.stderr
        )
    return RangeReceipt(
        "chr" + source.uri.rsplit(".chr", 1)[1].split(".", 1)[0],
        source.generation,
        byte_range.first,
        byte_range.last,
        requested,
        result.stdout.size_bytes,
        1,
        state,
        reason,
        retained.sha256,
        retained,
        retained_stderr,
        result.exit_code,
        result.stdout_limit_exceeded,
        result.stderr_limit_exceeded,
    )


def stage_sparse(
    source: SourceBytePlan,
    receipts: tuple[RangeReceipt, ...],
    *,
    artifact_root: Path,
    index: ArtifactRef,
    sparse_path: str,
) -> VerifiedSource:
    """Stage a sparse source only from exact verified range and index evidence."""
    _require(type(source) is SourceBytePlan and source.receipt.state == "verified", "invalid source plan")
    _require(type(receipts) is tuple, "range receipts must be a tuple")
    expected = tuple((value.first, value.last) for value in source.merged_vcf_ranges)
    actual = tuple((value.first, value.last) for value in receipts)
    _require(actual == expected, "range receipts do not match reviewed plan")
    _require(
        all(
            type(value) is RangeReceipt
            and value.state == "verified"
            and value.chrom == source.source.chrom
            and value.generation == source.source.vcf.generation
            and value.retained is not None
            for value in receipts
        ),
        "range receipts are not verified",
    )
    _require(index.path == f"{sparse_path}.tbi", "retained index is not the sparse-file sibling")
    _require(index.size_bytes == source.source.tbi.size_bytes, "retained index size mismatch")
    _require(index.sha256 == source.receipt.sha256, "retained index SHA mismatch")
    stable_index = _open_stable_artifact(artifact_root, index)
    index_path = stable_index.path
    try:
        index_sha, index_md5, index_crc32c = _stable_hashes(stable_index)
        _require(index_sha == index.sha256, "retained index SHA mismatch")
        _require(index_md5 == source.source.tbi.md5_b64, "retained index MD5 mismatch")
        _require(index_crc32c == source.source.tbi.crc32c_b64, "retained index CRC32C mismatch")
    finally:
        _close_stable_artifact(stable_index)

    verified_ranges = tuple(
        VerifiedRange(receipt.first, receipt.last, receipt.retained)
        for receipt in receipts
        if receipt.retained is not None
    )
    retained: list[_RangeHandle] = []
    try:
        for value in verified_ranges:
            retained.append(_open_verified_range(artifact_root, value))
        sparse, sparse_relative = _destination(artifact_root, sparse_path)
        with sparse.open("xb") as output:
            os.chmod(sparse, 0o600)
            output.truncate(source.source.vcf.size_bytes)
            for value in retained:
                output.seek(value.evidence.first)
                value.handle.seek(0)
                while chunk := value.handle.read(TRANSFER_PIECE_BYTES):
                    output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
        allocated = _allocated(sparse)
        payload_bytes = sum(value.received_bytes for value in receipts)
        _require(
            allocated <= payload_bytes + SPARSE_ALLOCATION_SLACK_BYTES,
            "sparse allocation limit exceeded",
        )
        with sparse.open("rb") as staged:
            for value in retained:
                staged.seek(value.evidence.first)
                value.handle.seek(0)
                remaining = value.evidence.range_file.size_bytes
                while remaining:
                    expected_raw = value.handle.read(min(TRANSFER_PIECE_BYTES, remaining))
                    actual = staged.read(len(expected_raw))
                    _require(actual == expected_raw and bool(actual), "sparse extent mismatch")
                    remaining -= len(actual)
            staged.seek(source.source.vcf.size_bytes - len(_EOF))
            _require(staged.read(len(_EOF)) == _EOF, "canonical BGZF EOF marker is missing")
    finally:
        for value in retained:
            path = Path(value.handle.name)
            identity = _handle_identity(value.handle)
            value.handle.close()
            _require(
                identity == value.identity and _file_identity(path) == value.identity,
                "retained range changed during sparse staging",
            )
    for value in retained:
        os.chmod(Path(value.handle.name), 0o400)
    os.chmod(index_path, 0o400)
    os.chmod(sparse, 0o400)
    return VerifiedSource(
        source.source,
        verified_ranges,
        sparse_relative,
        index,
        source.source.vcf.size_bytes,
        allocated,
        False,
    )
