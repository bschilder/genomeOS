#!/usr/bin/env python3
"""Preflight generation-pinned public indexes only (preflight design §§4–7; Atlas §§4–8, 12)."""

from __future__ import annotations

import argparse
import base64
import hashlib
import inspect
import json
import os
import platform
import signal
import subprocess
import sys
import threading
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) in sys.path:
    sys.path.remove(str(ROOT))
sys.path.insert(0, str(ROOT))

import genomeos.validation.reference_byte_plan as byte_plan_module  # noqa: E402
import genomeos.validation.reference_tbi as tbi_module  # noqa: E402
import genomeos.validation.reference_window_manifest as manifest_module  # noqa: E402
import genomeos.validation.reference_window_types as types_module  # noqa: E402
from genomeos.validation.reference_byte_plan import (  # noqa: E402
    METADATA_LIMIT_BYTES,
    REQUEST_TIMEOUT_SECONDS,
    STORAGE_BODY_MAX_RETRIES,
    IndexReceipt,
    SourceBytePlan,
    WindowBytePlan,
    assemble_preflight,
    crc32c,
    encode_preflight,
    fixed_vcf_ranges,
    merge_byte_ranges,
    plan_window,
)
from genomeos.validation.reference_tbi import MAX_COMPRESSED_BYTES, parse_tbi  # noqa: E402
from genomeos.validation.reference_window_manifest import decode_manifest  # noqa: E402
from genomeos.validation.reference_window_types import Provenance, PublicObject, SourcePair  # noqa: E402

MANIFEST_LIMIT_BYTES = 4 * 1024 * 1024
WINDOWS_LIMIT_BYTES = 64 * 1024
WRAPPER = ROOT / "scripts" / "gcloud_repo.py"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Preflight bounded generation-pinned reference indexes.")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--windows", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    return parser


def _read_bounded(path: Path, limit: int, name: str) -> bytes:
    with path.open("rb") as handle:
        raw = handle.read(limit + 1)
    if len(raw) > limit:
        raise ValueError(f"{name} exceeds bounded input limit")
    if not raw:
        raise ValueError(f"{name} must not be empty")
    return raw


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate metadata key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"nonfinite metadata value: {value}")


def _environment() -> dict[str, str]:
    environment = {
        key: os.environ[key]
        for key in ("PATH", "TMPDIR", "TEMP", "TMP", "LANG", "LC_ALL", "SYSTEMROOT")
        if key in os.environ
    }
    environment["CLOUDSDK_AUTH_DISABLE_CREDENTIALS"] = "true"
    environment["CLOUDSDK_CORE_DISABLE_FILE_LOGGING"] = "true"
    environment["CLOUDSDK_CORE_DISABLE_PROMPTS"] = "true"
    environment["CLOUDSDK_STORAGE_MAX_RETRIES"] = str(STORAGE_BODY_MAX_RETRIES)
    return environment


def _run_bounded(argv: list[str], *, limit: int) -> tuple[bytes, int, bool, bool]:
    process = subprocess.Popen(
        argv,
        cwd=ROOT,
        env=_environment(),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        shell=False,
        start_new_session=True,
    )
    if process.stdout is None:
        _terminate(process)
        process.wait()
        return b"", process.returncode, False, False
    result = bytearray()
    errors: list[BaseException] = []

    def read() -> None:
        try:
            while len(result) <= limit:
                chunk = process.stdout.read(min(65_536, limit + 1 - len(result)))
                if not chunk:
                    break
                result.extend(chunk)
        except BaseException as error:  # pragma: no cover - OS stream failures are platform-specific
            errors.append(error)

    started = time.monotonic()
    thread = threading.Thread(target=read, daemon=True)
    thread.start()
    thread.join(REQUEST_TIMEOUT_SECONDS)
    if thread.is_alive():
        _terminate(process)
        process.wait()
        thread.join(1)
        return bytes(result), process.returncode, True, len(result) > limit
    if errors:
        _terminate(process)
        process.wait()
        return bytes(result), process.returncode, False, len(result) > limit
    if len(result) > limit:
        _terminate(process)
        returncode = process.wait()
        return bytes(result), returncode, False, True
    remaining = max(0.001, REQUEST_TIMEOUT_SECONDS - (time.monotonic() - started))
    try:
        returncode = process.wait(timeout=remaining)
    except subprocess.TimeoutExpired:
        _terminate(process)
        process.wait()
        thread.join(1)
        return bytes(result), process.returncode, True, len(result) > limit
    raw = bytes(result)
    return raw, returncode, False, len(raw) > limit


def _terminate(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (AttributeError, OSError):
        process.kill()


def _argv(wrapper: Path, arguments: list[str]) -> list[str]:
    return [sys.executable, str(wrapper), "run", *arguments]


def _metadata(object_: PublicObject, *, wrapper: Path) -> tuple[str | None, str | None]:
    try:
        raw, returncode, timed_out, oversized = _run_bounded(
            _argv(
                wrapper,
                [
                    "storage",
                    "objects",
                    "describe",
                    f"{object_.uri}#{object_.generation}",
                    "--raw",
                    "--format=json",
                ],
            ),
            limit=METADATA_LIMIT_BYTES,
        )
    except OSError:
        return "generation_unavailable", None
    if oversized:
        return "limit_exceeded", None
    if timed_out or returncode != 0:
        return "generation_unavailable", None
    try:
        value = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_unique_pairs, parse_constant=_reject_constant
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return "metadata_mismatch", None
    expected = {
        "generation": object_.generation,
        "size": str(object_.size_bytes),
        "md5Hash": object_.md5_b64,
        "crc32c": object_.crc32c_b64,
    }
    if type(value) is not dict or any(value.get(key) != item for key, item in expected.items()):
        return "metadata_mismatch", None
    return None, hashlib.sha256(raw).hexdigest()


def _refusal(
    source: SourcePair,
    reason: str,
    *,
    vcf_attempts: int,
    tbi_attempts: int,
    body_attempts: int,
    received_bytes: int = 0,
    sha256: str | None = None,
) -> tuple[None, IndexReceipt]:
    return None, IndexReceipt(
        source.chrom,
        "refused",
        reason,
        vcf_attempts,
        tbi_attempts,
        body_attempts,
        received_bytes,
        sha256,
    )


def fetch_public_index(source: SourcePair, *, wrapper: Path) -> tuple[bytes | None, IndexReceipt]:
    """Verify both pinned identities and fetch at most one bounded TBI body."""
    if type(source) is not SourcePair:
        raise ValueError("source must be a SourcePair")
    if not wrapper.is_file():
        return _refusal(source, "transfer_failed", vcf_attempts=0, tbi_attempts=0, body_attempts=0)
    reason, _ = _metadata(source.vcf, wrapper=wrapper)
    if reason is not None:
        return _refusal(source, reason, vcf_attempts=1, tbi_attempts=0, body_attempts=0)
    reason, _ = _metadata(source.tbi, wrapper=wrapper)
    if reason is not None:
        return _refusal(source, reason, vcf_attempts=1, tbi_attempts=1, body_attempts=0)
    if source.tbi.size_bytes > MAX_COMPRESSED_BYTES:
        return _refusal(source, "limit_exceeded", vcf_attempts=1, tbi_attempts=1, body_attempts=0)
    try:
        body, returncode, timed_out, oversized = _run_bounded(
            _argv(wrapper, ["storage", "cat", f"{source.tbi.uri}#{source.tbi.generation}"]),
            limit=source.tbi.size_bytes,
        )
    except OSError:
        return _refusal(source, "transfer_failed", vcf_attempts=1, tbi_attempts=1, body_attempts=1)
    if oversized:
        return _refusal(
            source,
            "size_mismatch",
            vcf_attempts=1,
            tbi_attempts=1,
            body_attempts=1,
            received_bytes=len(body),
        )
    if timed_out or returncode != 0:
        return _refusal(
            source,
            "transfer_failed",
            vcf_attempts=1,
            tbi_attempts=1,
            body_attempts=1,
            received_bytes=len(body),
        )
    if len(body) != source.tbi.size_bytes:
        return _refusal(
            source,
            "size_mismatch",
            vcf_attempts=1,
            tbi_attempts=1,
            body_attempts=1,
            received_bytes=len(body),
        )
    md5 = base64.b64encode(hashlib.md5(body, usedforsecurity=False).digest()).decode("ascii")
    crc = base64.b64encode(crc32c(body).to_bytes(4, "big")).decode("ascii")
    if (md5, crc) != (source.tbi.md5_b64, source.tbi.crc32c_b64):
        return _refusal(
            source,
            "checksum_mismatch",
            vcf_attempts=1,
            tbi_attempts=1,
            body_attempts=1,
            received_bytes=len(body),
        )
    sha256 = hashlib.sha256(body).hexdigest()
    return body, IndexReceipt(source.chrom, "verified", None, 1, 1, 1, len(body), sha256)


def _failed_windows(manifest, source: SourcePair, reason: str) -> tuple[WindowBytePlan, ...]:
    return tuple(
        WindowBytePlan(window.window_id, "refused", reason, "not_inspected", (), ())
        for window in manifest.windows
        if window.chrom == source.chrom
    )


def _source_plan(manifest, source: SourcePair) -> tuple[SourceBytePlan, bytes | None]:
    fixed = fixed_vcf_ranges(
        source.vcf.size_bytes,
        header_prefix_bytes=manifest.config.header_prefix_bytes,
        eof_bytes=manifest.config.eof_bytes,
    )
    body, receipt = fetch_public_index(source, wrapper=WRAPPER)
    if body is None:
        return SourceBytePlan(source, receipt, _failed_windows(manifest, source, receipt.reason), fixed), None
    try:
        index = parse_tbi(body, expected_chrom=source.chrom, vcf_size_bytes=source.vcf.size_bytes)
        windows = tuple(
            plan_window(index, window, source_size_bytes=source.vcf.size_bytes)
            for window in manifest.windows
            if window.chrom == source.chrom
        )
    except ValueError:
        refused = replace(receipt, state="refused", reason="index_invalid")
        return (
            SourceBytePlan(source, refused, _failed_windows(manifest, source, "index_invalid"), fixed),
            None,
        )
    merged = merge_byte_ranges(
        fixed + tuple(byte_range for window in windows for byte_range in window.ranges),
        source_size_bytes=source.vcf.size_bytes,
    )
    return SourceBytePlan(source, receipt, windows, merged), body


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_revision() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, check=False, capture_output=True, text=True
    )
    revision = completed.stdout.strip()
    if (
        completed.returncode
        or len(revision) != 40
        or any(char not in "0123456789abcdef" for char in revision)
    ):
        raise ValueError("unable to record Git source revision")
    return revision


def _imported_source_hashes() -> tuple[tuple[str, str], ...]:
    geometry_module = inspect.getmodule(manifest_module.select_reference_windows)
    geometry_file = getattr(geometry_module, "__file__", None)
    if geometry_file is None:
        raise ValueError("unable to resolve executed geometry module")
    geometry_path = Path(geometry_file).resolve()
    geometry_relative = "genomeos/validation/reference_windows.py"
    if geometry_path != (ROOT / geometry_relative).resolve():
        raise ValueError("executed geometry module is not the expected checkout file")
    paths = {
        "genomeos/validation/reference_byte_plan.py": Path(byte_plan_module.__file__).resolve(),
        "genomeos/validation/reference_tbi.py": Path(tbi_module.__file__).resolve(),
        "genomeos/validation/reference_window_manifest.py": Path(manifest_module.__file__).resolve(),
        "genomeos/validation/reference_window_types.py": Path(types_module.__file__).resolve(),
        geometry_relative: geometry_path,
        "scripts/gcloud_repo.py": WRAPPER.resolve(),
        "scripts/preflight_reference_windows.py": Path(__file__).resolve(),
    }
    records = []
    for relative, actual in paths.items():
        if actual != (ROOT / relative).resolve():
            raise ValueError(f"imported source is outside this checkout: {actual.name}")
        records.append((relative, _sha256(actual)))
    return tuple(sorted(records))


def _build(manifest_raw: bytes, windows_raw: bytes):
    manifest = decode_manifest(manifest_raw, windows_bytes=windows_raw)
    for source in manifest.sources:
        fixed_vcf_ranges(
            source.vcf.size_bytes,
            header_prefix_bytes=manifest.config.header_prefix_bytes,
            eof_bytes=manifest.config.eof_bytes,
        )
    planned = tuple(_source_plan(manifest, source) for source in manifest.sources)
    source_plans = tuple(plan for plan, _ in planned)
    verified_indexes = tuple((plan.source.chrom, body) for plan, body in planned if body is not None)
    provenance = Provenance(
        data_version=manifest.provenance.data_version,
        evidence_kind=manifest.provenance.evidence_kind,
        input_sha256=(
            ("manifest", hashlib.sha256(manifest_raw).hexdigest()),
            ("windows", hashlib.sha256(windows_raw).hexdigest()),
        ),
        source_revision=_source_revision(),
        imported_source_sha256=_imported_source_hashes(),
        python_version=platform.python_version(),
        source_audit_locator=manifest.provenance.source_audit_locator,
    )
    return (
        assemble_preflight(
            manifest,
            source_plans,
            manifest_sha256=hashlib.sha256(manifest_raw).hexdigest(),
            provenance=provenance,
        ),
        verified_indexes,
    )


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        manifest_raw = _read_bounded(args.manifest, MANIFEST_LIMIT_BYTES, "manifest")
        windows_raw = _read_bounded(args.windows, WINDOWS_LIMIT_BYTES, "windows")
        manifest_module.decode_manifest(manifest_raw, windows_bytes=windows_raw)
        if args.out.exists():
            raise ValueError(f"output directory already exists: {args.out}")
        preflight, verified_indexes = _build(manifest_raw, windows_raw)
        artifact = encode_preflight(preflight)
        args.out.mkdir(parents=True, exist_ok=False)
        indexes = args.out / "indexes"
        indexes.mkdir()
        for chrom, body in verified_indexes:
            receipt = next(plan.receipt for plan in preflight.sources if plan.source.chrom == chrom)
            if hashlib.sha256(body).hexdigest() != receipt.sha256:
                raise ValueError(f"verified index hash changed before persistence: {chrom}")
            with (indexes / f"{chrom}.tbi").open("xb") as handle:
                handle.write(body)
        with (args.out / "preflight.json").open("xb") as handle:
            handle.write(artifact)
    except (OSError, ValueError) as error:
        parser.exit(2, f"error: {error}\n")
    return 0 if preflight.complete and preflight.budget_status == "within_cap" else 1


if __name__ == "__main__":
    raise SystemExit(main())
