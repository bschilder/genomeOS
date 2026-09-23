"""Bounded process and artifact primitives (reference acquisition design §4.1)."""

from __future__ import annotations

import base64
import hashlib
import os
import signal
import subprocess
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import BinaryIO

from genomeos.validation.reference_acquisition_types import ArtifactRef, VerifiedSource
from genomeos.validation.reference_byte_plan import SourceBytePlan, crc32c_chunks

TRANSFER_PIECE_BYTES = 1_048_576
SPARSE_ALLOCATION_SLACK_BYTES = 16_777_216
_BGZF_EOF = bytes.fromhex("1f8b08040000000000ff0600424302001b0003000000000000000000")


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


def _partial_process_paths(
    root: Path,
    stdout_path: Path | str,
    stderr_path: Path | str,
) -> tuple[str, str]:
    """Reserve final names conceptually and return fresh partial output names."""
    stdout_final, stdout_relative = _destination(root, stdout_path)
    stderr_final, stderr_relative = _destination(root, stderr_path)
    _require(stdout_final != stderr_final, "process output paths must differ")
    stdout_partial, stdout_partial_relative = _destination(root, f"{stdout_relative}.partial")
    stderr_partial, stderr_partial_relative = _destination(root, f"{stderr_relative}.partial")
    _require(stdout_partial != stderr_partial, "partial process output paths must differ")
    return stdout_partial_relative, stderr_partial_relative


def _promote_process_outputs(
    root: Path,
    stdout: ArtifactRef,
    stderr: ArtifactRef,
) -> tuple[ArtifactRef, ArtifactRef]:
    """Promote validated partial outputs, publishing scientific stdout last."""
    _require(
        stdout.path.endswith(".partial") and stderr.path.endswith(".partial"),
        "process outputs are not partial",
    )
    stdout_partial = _existing(root, stdout)
    stderr_partial = _existing(root, stderr)
    _require(
        stdout_partial.stat().st_size == stdout.size_bytes
        and stderr_partial.stat().st_size == stderr.size_bytes,
        "partial process output size changed before promotion",
    )
    stdout_relative = stdout.path.removesuffix(".partial")
    stderr_relative = stderr.path.removesuffix(".partial")
    stdout_final, _ = _destination(root, stdout_relative)
    stderr_final, _ = _destination(root, stderr_relative)
    stderr_partial.rename(stderr_final)
    try:
        stdout_partial.rename(stdout_final)
    except BaseException:
        stderr_final.rename(stderr_partial)
        raise
    return (
        ArtifactRef(stdout_relative, stdout.size_bytes, stdout.sha256),
        ArtifactRef(stderr_relative, stderr.size_bytes, stderr.sha256),
    )


def fsync_artifact(handle: BinaryIO) -> None:
    """Flush one open artifact before its identity can enter a manifest."""
    handle.flush()
    os.fsync(handle.fileno())


def write_artifact_bytes(root: Path, value: Path | str, raw: bytes) -> ArtifactRef:
    """Write one exclusive 0600 artifact and fsync its content."""
    _require(type(raw) is bytes, "artifact content must be bytes")
    path, relative = _destination(root, value)
    with path.open("xb") as handle:
        os.chmod(path, 0o600)
        handle.write(raw)
        fsync_artifact(handle)
    return _artifact(root, path, relative)


def fsync_artifact_tree(root: Path) -> None:
    """Persist all artifact-directory entries before publishing the final manifest."""
    resolved = _root(root)
    directories = sorted(
        (path for path in resolved.rglob("*") if path.is_dir()),
        key=lambda path: len(path.parts),
        reverse=True,
    )
    for path in (*directories, resolved):
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def _validate_artifact(root: Path, reference: ArtifactRef) -> Path:
    path = _existing(root, reference)
    _require(_digest_file(path) == (reference.size_bytes, reference.sha256), "artifact identity mismatch")
    return path


def _environment(overrides: dict[str, str] | None = None) -> dict[str, str]:
    result = {
        key: os.environ[key]
        for key in ("PATH", "TMPDIR", "TEMP", "TMP", "LANG", "LC_ALL", "SYSTEMROOT", "BCFTOOLS_PLUGINS")
        if key in os.environ
    }
    result.update(
        {
            "CLOUDSDK_AUTH_DISABLE_CREDENTIALS": "true",
            "CLOUDSDK_COMPONENT_MANAGER_DISABLE_UPDATE_CHECK": "true",
            "CLOUDSDK_CORE_DISABLE_FILE_LOGGING": "true",
            "CLOUDSDK_CORE_DISABLE_PROMPTS": "true",
            "CLOUDSDK_STORAGE_MAX_RETRIES": "0",
        }
    )
    if overrides:
        _require(
            set(overrides) == {"GENOMEOS_GCLOUD_EXECUTABLE"}
            and Path(overrides["GENOMEOS_GCLOUD_EXECUTABLE"]).is_absolute(),
            "invalid process environment override",
        )
        result.update(overrides)
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


def _write_chunk(output: BinaryIO, raw: bytes) -> None:
    written = output.write(raw)
    if written != len(raw):
        raise OSError("short artifact write")


def _run_process(
    argv: list[str],
    *,
    artifact_root: Path,
    stdout_path: Path | str,
    stderr_path: Path | str,
    stdout_limit: int,
    stderr_limit: int,
    timeout: float,
    environment: dict[str, str] | None = None,
) -> _ProcessResult:
    stdout_file, stdout_relative = _destination(artifact_root, stdout_path)
    stderr_file, stderr_relative = _destination(artifact_root, stderr_path)
    _require(stdout_file != stderr_file, "process output paths must differ")
    counts = {"stdout": 0, "stderr": 0}
    digests = {"stdout": hashlib.sha256(), "stderr": hashlib.sha256()}
    exceeded = {"stdout": False, "stderr": False}
    errors: list[BaseException] = []
    storage_errors: list[OSError] = []
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
                env=_environment(environment),
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
                        try:
                            _write_chunk(output, retained)
                        except OSError as error:
                            storage_errors.append(error)
                            if process is not None:
                                _terminate(process)
                            break
                        digests[name].update(retained)
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
        fsync_artifact(stdout_handle)
        fsync_artifact(stderr_handle)
    if storage_errors:
        raise storage_errors[0]
    if errors and process is not None and exit_code == 0:
        exit_code = None
    return _ProcessResult(
        exit_code,
        timed_out,
        exceeded["stdout"],
        exceeded["stderr"],
        ArtifactRef(stdout_relative, counts["stdout"], digests["stdout"].hexdigest()),
        ArtifactRef(stderr_relative, counts["stderr"], digests["stderr"].hexdigest()),
    )


def _md5_b64(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        while chunk := handle.read(TRANSFER_PIECE_BYTES):
            digest.update(chunk)
    return base64.b64encode(digest.digest()).decode("ascii")


def _crc32c_b64(path: Path) -> str:
    def chunks() -> Iterator[bytes]:
        with path.open("rb") as handle:
            while chunk := handle.read(TRANSFER_PIECE_BYTES):
                yield chunk

    checksum = crc32c_chunks(chunks())
    return base64.b64encode(checksum.to_bytes(4, "big")).decode("ascii")


def _allocated(path: Path) -> int:
    status = path.stat()
    return status.st_blocks * 512 if hasattr(status, "st_blocks") else status.st_size


@dataclass
class _StableArtifact:
    path: Path
    handle: BinaryIO
    identity: tuple[int, int, int, int]


def _stat_identity(path: Path) -> tuple[int, int, int, int]:
    status = path.stat()
    return status.st_dev, status.st_ino, status.st_size, status.st_mtime_ns


def _descriptor_identity(handle: BinaryIO) -> tuple[int, int, int, int]:
    status = os.fstat(handle.fileno())
    return status.st_dev, status.st_ino, status.st_size, status.st_mtime_ns


def _open_stable_artifact(root: Path, reference: ArtifactRef) -> _StableArtifact:
    path = _existing(root, reference)
    identity = _stat_identity(path)
    handle = path.open("rb")
    _require(_descriptor_identity(handle) == identity, "artifact changed while opening")
    _require(identity[2] == reference.size_bytes, "artifact size changed while opening")
    return _StableArtifact(path, handle, identity)


def _stable_sha256(value: _StableArtifact) -> str:
    digest = hashlib.sha256()
    value.handle.seek(0)
    while chunk := value.handle.read(TRANSFER_PIECE_BYTES):
        digest.update(chunk)
    value.handle.seek(0)
    return digest.hexdigest()


def _stable_hashes(value: _StableArtifact) -> tuple[str, str, str]:
    sha = hashlib.sha256()
    md5 = hashlib.md5()

    def chunks() -> Iterator[bytes]:
        value.handle.seek(0)
        while chunk := value.handle.read(TRANSFER_PIECE_BYTES):
            sha.update(chunk)
            md5.update(chunk)
            yield chunk

    crc32c = crc32c_chunks(chunks())
    value.handle.seek(0)
    return (
        sha.hexdigest(),
        base64.b64encode(md5.digest()).decode("ascii"),
        base64.b64encode(crc32c.to_bytes(4, "big")).decode("ascii"),
    )


def _close_stable_artifact(value: _StableArtifact) -> None:
    identity = _descriptor_identity(value.handle)
    value.handle.close()
    _require(
        identity == value.identity and _stat_identity(value.path) == value.identity,
        "artifact changed during verified use",
    )


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
    _require(verified.index.path == f"{verified.sparse_path}.tbi", "verified index is not sparse sibling")
    _require(verified.index.size_bytes == plan.source.tbi.size_bytes, "verified index size mismatch")
    _require(verified.index.sha256 == plan.receipt.sha256, "verified index SHA mismatch")
    opened: list[_StableArtifact] = []
    try:
        index = _open_stable_artifact(artifact_root, verified.index)
        opened.append(index)
        index_sha, index_md5, index_crc32c = _stable_hashes(index)
        _require(index_sha == verified.index.sha256, "verified index content mismatch")
        _require(index_md5 == plan.source.tbi.md5_b64, "verified index MD5 mismatch")
        _require(index_crc32c == plan.source.tbi.crc32c_b64, "verified index CRC32C mismatch")
        sparse_ref = ArtifactRef(verified.sparse_path, verified.logical_size_bytes, "0" * 64)
        sparse = _open_stable_artifact(artifact_root, sparse_ref)
        opened.append(sparse)
        payload_bytes = sum(value.range_file.size_bytes for value in verified.ranges)
        observed_allocation = _allocated(sparse.path)
        _require(
            observed_allocation == verified.allocated_size_bytes
            and observed_allocation <= payload_bytes + SPARSE_ALLOCATION_SLACK_BYTES,
            "sparse allocation limit exceeded",
        )
        _require(
            verified.logical_size_bytes >= len(_BGZF_EOF),
            "verified source is smaller than the canonical BGZF EOF marker",
        )
        sparse.handle.seek(verified.logical_size_bytes - len(_BGZF_EOF))
        _require(
            sparse.handle.read(len(_BGZF_EOF)) == _BGZF_EOF,
            "canonical BGZF EOF marker is missing",
        )
        ranges = []
        for value in verified.ranges:
            retained = _open_stable_artifact(artifact_root, value.range_file)
            opened.append(retained)
            range_sha = _stable_sha256(retained)
            _require(range_sha == value.range_file.sha256, "retained range identity mismatch")
            ranges.append((value, retained))
        for value, retained in ranges:
            sparse.handle.seek(value.first)
            retained.handle.seek(0)
            remaining = value.range_file.size_bytes
            while remaining:
                expected_raw = retained.handle.read(min(TRANSFER_PIECE_BYTES, remaining))
                actual = sparse.handle.read(len(expected_raw))
                _require(actual == expected_raw and bool(actual), "sparse populated extent mismatch")
                remaining -= len(actual)
    finally:
        for value in reversed(opened):
            _close_stable_artifact(value)
