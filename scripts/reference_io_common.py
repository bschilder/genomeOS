"""Bounded process and artifact primitives (reference acquisition design §4.1)."""

from __future__ import annotations

import base64
import hashlib
import os
import signal
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import BinaryIO

from genomeos.validation.reference_acquisition_types import ArtifactRef, VerifiedSource
from genomeos.validation.reference_byte_plan import SourceBytePlan

TRANSFER_PIECE_BYTES = 1_048_576
SPARSE_ALLOCATION_SLACK_BYTES = 16_777_216


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _root(path: Path) -> Path:
    _require(isinstance(path, Path) and path.is_dir() and not path.is_symlink(), "invalid artifact root")
    return path.resolve(strict=True)


def _relative_path(value: str) -> PurePosixPath:
    _require(isinstance(value, str) and bool(value), "invalid relative artifact path")
    path = PurePosixPath(value)
    _require(not path.is_absolute() and "\\" not in value, "artifact path must be relative")
    _require(all(part not in ("", ".", "..") for part in path.parts), "invalid artifact path")
    _require(str(path) == value, "artifact path is not canonical")
    return path


def _destination(root: Path, value: Path | str) -> tuple[Path, str]:
    resolved_root = _root(root)
    if isinstance(value, Path):
        candidate = value if value.is_absolute() else resolved_root / value
        try:
            relative = candidate.relative_to(resolved_root).as_posix()
        except ValueError as error:
            raise ValueError("destination is outside artifact root") from error
    else:
        relative = str(_relative_path(value))
        candidate = resolved_root / relative
    _relative_path(relative)
    candidate.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    _require(
        candidate.parent.resolve(strict=True).is_relative_to(resolved_root), "destination parent escapes root"
    )
    if candidate.exists() or candidate.is_symlink():
        raise FileExistsError("destination already exists")
    return candidate, relative


def _existing(root: Path, reference: ArtifactRef) -> Path:
    resolved_root = _root(root)
    relative = _relative_path(reference.path)
    candidate = resolved_root / relative
    cursor = resolved_root
    for part in relative.parts:
        cursor /= part
        _require(not cursor.is_symlink(), "artifact path contains a symlink")
    _require(
        candidate.exists() and candidate.is_file() and not candidate.is_symlink(), "artifact is unavailable"
    )
    _require(candidate.resolve(strict=True).is_relative_to(resolved_root), "artifact escapes root")
    return candidate


def _digest_file(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while chunk := handle.read(TRANSFER_PIECE_BYTES):
            digest.update(chunk)
            size += len(chunk)
    return size, digest.hexdigest()


def _artifact(root: Path, path: Path, relative: str) -> ArtifactRef:
    _require(path.resolve(strict=True).is_relative_to(_root(root)), "artifact escapes root")
    size, digest = _digest_file(path)
    return ArtifactRef(relative, size, digest)


def _validate_artifact(root: Path, reference: ArtifactRef) -> Path:
    path = _existing(root, reference)
    _require(_digest_file(path) == (reference.size_bytes, reference.sha256), "artifact identity mismatch")
    return path


def _environment() -> dict[str, str]:
    result = {
        key: os.environ[key]
        for key in ("PATH", "TMPDIR", "TEMP", "TMP", "LANG", "LC_ALL", "SYSTEMROOT", "BCFTOOLS_PLUGINS")
        if key in os.environ
    }
    result.update(
        {
            "CLOUDSDK_AUTH_DISABLE_CREDENTIALS": "true",
            "CLOUDSDK_CORE_DISABLE_FILE_LOGGING": "true",
            "CLOUDSDK_CORE_DISABLE_PROMPTS": "true",
            "CLOUDSDK_STORAGE_MAX_RETRIES": "0",
        }
    )
    return result


@dataclass(frozen=True)
class _ProcessResult:
    exit_code: int | None
    timed_out: bool
    stdout_limit_exceeded: bool
    stderr_limit_exceeded: bool
    stdout: ArtifactRef
    stderr: ArtifactRef


def _terminate(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except OSError:
        process.kill()


def _run_process(
    argv: list[str],
    *,
    artifact_root: Path,
    stdout_path: Path | str,
    stderr_path: Path | str,
    stdout_limit: int,
    stderr_limit: int,
    timeout: float,
) -> _ProcessResult:
    stdout_file, stdout_relative = _destination(artifact_root, stdout_path)
    stderr_file, stderr_relative = _destination(artifact_root, stderr_path)
    _require(stdout_file != stderr_file, "process output paths must differ")
    counts = {"stdout": 0, "stderr": 0}
    exceeded = {"stdout": False, "stderr": False}
    errors: list[BaseException] = []
    process: subprocess.Popen[bytes] | None = None

    with (
        stdout_file.open("xb", buffering=0) as stdout_handle,
        stderr_file.open("xb", buffering=0) as stderr_handle,
    ):
        os.chmod(stdout_file, 0o600)
        os.chmod(stderr_file, 0o600)
        try:
            process = subprocess.Popen(
                argv,
                cwd=_root(artifact_root),
                env=_environment(),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
                start_new_session=True,
            )
        except OSError as error:
            errors.append(error)

        def drain(name: str, pipe: BinaryIO, output: BinaryIO, limit: int) -> None:
            try:
                while True:
                    chunk = pipe.read(TRANSFER_PIECE_BYTES)
                    if not chunk:
                        break
                    remaining = max(0, limit + 1 - counts[name])
                    retained = chunk[:remaining]
                    if retained:
                        output.write(retained)
                        counts[name] += len(retained)
                    if len(chunk) > remaining or counts[name] > limit:
                        exceeded[name] = True
                        if process is not None:
                            _terminate(process)
                        break
            except BaseException as error:  # pragma: no cover - platform pipe faults
                errors.append(error)
                if process is not None:
                    _terminate(process)

        threads: list[threading.Thread] = []
        if process is not None and process.stdout is not None and process.stderr is not None:
            threads = [
                threading.Thread(
                    target=drain, args=("stdout", process.stdout, stdout_handle, stdout_limit), daemon=True
                ),
                threading.Thread(
                    target=drain, args=("stderr", process.stderr, stderr_handle, stderr_limit), daemon=True
                ),
            ]
            for thread in threads:
                thread.start()
        timed_out = False
        exit_code: int | None = None
        if process is not None:
            try:
                exit_code = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                _terminate(process)
                exit_code = process.wait()
            for thread in threads:
                thread.join(2)
            if any(thread.is_alive() for thread in threads):
                _terminate(process)
                exit_code = process.wait()
                for thread in threads:
                    thread.join(2)
        stdout_handle.flush()
        stderr_handle.flush()
        os.fsync(stdout_handle.fileno())
        os.fsync(stderr_handle.fileno())
    if errors and process is not None and exit_code == 0:
        exit_code = None
    return _ProcessResult(
        exit_code,
        timed_out,
        exceeded["stdout"],
        exceeded["stderr"],
        _artifact(artifact_root, stdout_file, stdout_relative),
        _artifact(artifact_root, stderr_file, stderr_relative),
    )


def _md5_b64(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        while chunk := handle.read(TRANSFER_PIECE_BYTES):
            digest.update(chunk)
    return base64.b64encode(digest.digest()).decode("ascii")


def _crc32c_b64(path: Path) -> str:
    checksum = 0xFFFFFFFF
    with path.open("rb") as handle:
        while chunk := handle.read(TRANSFER_PIECE_BYTES):
            for byte in chunk:
                checksum ^= byte
                for _ in range(8):
                    checksum = (checksum >> 1) ^ (0x82F63B78 if checksum & 1 else 0)
    return base64.b64encode((checksum ^ 0xFFFFFFFF).to_bytes(4, "big")).decode("ascii")


def _allocated(path: Path) -> int:
    status = path.stat()
    return status.st_blocks * 512 if hasattr(status, "st_blocks") else status.st_size


def validate_verified_source(
    verified: VerifiedSource,
    plan: SourceBytePlan,
    *,
    artifact_root: Path,
) -> None:
    """Revalidate source identity, retained bytes, index, and populated sparse extents."""
    _require(type(verified) is VerifiedSource and type(plan) is SourceBytePlan, "invalid verified source")
    _require(verified.source == plan.source, "verified source identity mismatch")
    expected = tuple((value.first, value.last) for value in plan.merged_vcf_ranges)
    _require(
        tuple((value.first, value.last) for value in verified.ranges) == expected,
        "verified coverage mismatch",
    )
    index_path = _validate_artifact(artifact_root, verified.index)
    _require(verified.index.path == f"{verified.sparse_path}.tbi", "verified index is not sparse sibling")
    _require(verified.index.size_bytes == plan.source.tbi.size_bytes, "verified index size mismatch")
    _require(verified.index.sha256 == plan.receipt.sha256, "verified index SHA mismatch")
    _require(_md5_b64(index_path) == plan.source.tbi.md5_b64, "verified index MD5 mismatch")
    _require(_crc32c_b64(index_path) == plan.source.tbi.crc32c_b64, "verified index CRC32C mismatch")
    sparse = _existing(
        artifact_root, ArtifactRef(verified.sparse_path, verified.logical_size_bytes, "0" * 64)
    )
    _require(sparse.stat().st_size == verified.logical_size_bytes, "sparse logical size mismatch")
    payload_bytes = sum(value.range_file.size_bytes for value in verified.ranges)
    _require(
        _allocated(sparse) <= payload_bytes + SPARSE_ALLOCATION_SLACK_BYTES,
        "sparse allocation limit exceeded",
    )
    with sparse.open("rb") as staged:
        for value in verified.ranges:
            range_path = _validate_artifact(artifact_root, value.range_file)
            staged.seek(value.first)
            with range_path.open("rb") as handle:
                remaining = value.range_file.size_bytes
                while remaining:
                    expected_raw = handle.read(min(TRANSFER_PIECE_BYTES, remaining))
                    actual = staged.read(len(expected_raw))
                    _require(actual == expected_raw and bool(actual), "sparse populated extent mismatch")
                    remaining -= len(actual)
