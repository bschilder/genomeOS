"""Index-only wrapper adapter controls (preflight design §§4, 6; #254)."""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import io
import json
import time
from dataclasses import replace
from pathlib import Path

import pytest

from genomeos.validation.reference_byte_plan import IndexReceipt, crc32c
from genomeos.validation.reference_tbi import TbiIndex
from genomeos.validation.reference_window_manifest import decode_manifest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "preflight_reference_windows.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("preflight_reference_windows", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Process:
    def __init__(self, raw: bytes, returncode: int = 0):
        self.stdout = io.BytesIO(raw)
        self.returncode = returncode
        self.killed = False

    def wait(self, timeout=None):
        return self.returncode

    def kill(self):
        self.killed = True
        self.returncode = -9


class _Factory:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def __call__(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        raw, returncode = self.replies.pop(0)
        return _Process(raw, returncode)


def _source_and_body(tmp_path):
    from tests.test_freeze_reference_windows_cli import _command, _run

    out = tmp_path / "manifest"
    assert _run(_command(out)).returncode == 0
    manifest = decode_manifest(
        (out / "manifest.json").read_bytes(), windows_bytes=(out / "windows.tsv").read_bytes()
    )
    body = (
        ROOT / "tests" / "fixtures" / "reference_windows" / "native" / "synthetic.vcf.gz.tbi"
    ).read_bytes()
    tbi = replace(
        manifest.sources[0].tbi,
        size_bytes=len(body),
        md5_b64=base64.b64encode(hashlib.md5(body, usedforsecurity=False).digest()).decode(),
        crc32c_b64=base64.b64encode(crc32c(body).to_bytes(4, "big")).decode(),
    )
    return replace(manifest.sources[0], tbi=tbi), body


def _metadata(value):
    return json.dumps(
        {
            "generation": value.generation,
            "size": str(value.size_bytes),
            "md5Hash": value.md5_b64,
            "crc32c": value.crc32c_b64,
        }
    ).encode()


def test_fetch_uses_pinned_wrapper_raw_metadata_and_only_tbi_body(monkeypatch, tmp_path):
    script = _load_script()
    source, body = _source_and_body(tmp_path)
    factory = _Factory([(_metadata(source.vcf), 0), (_metadata(source.tbi), 0), (body, 0)])
    monkeypatch.setattr(script.subprocess, "Popen", factory)
    wrapper = ROOT / "scripts" / "gcloud_repo.py"

    received, receipt = script.fetch_public_index(source, wrapper=wrapper)

    assert received == body
    assert receipt == IndexReceipt(
        "chr1", "verified", None, 1, 1, 1, len(body), hashlib.sha256(body).hexdigest()
    )
    assert len(factory.calls) == 3
    for argv, options in factory.calls:
        assert argv[:3] == [script.sys.executable, str(wrapper), "run"]
        assert options["shell"] is False
        assert options["stdin"] == script.subprocess.DEVNULL
        assert options["env"]["CLOUDSDK_AUTH_DISABLE_CREDENTIALS"] == "true"
        assert options["env"]["CLOUDSDK_CORE_DISABLE_FILE_LOGGING"] == "true"
        assert options["env"]["CLOUDSDK_CORE_DISABLE_PROMPTS"] == "true"
        assert "ANTHROPIC_API_KEY" not in options["env"]
    assert factory.calls[0][0][3:] == [
        "storage",
        "objects",
        "describe",
        f"{source.vcf.uri}#{source.vcf.generation}",
        "--raw",
        "--format=json",
    ]
    assert factory.calls[1][0][3:] == [
        "storage",
        "objects",
        "describe",
        f"{source.tbi.uri}#{source.tbi.generation}",
        "--raw",
        "--format=json",
    ]
    assert factory.calls[2][0][3:] == ["storage", "cat", f"{source.tbi.uri}#{source.tbi.generation}"]
    assert all(
        not ("storage" in call[0] and "cat" in call[0] and source.vcf.uri in call[0])
        for call in factory.calls
    )


@pytest.mark.parametrize(
    ("replies", "reason", "attempts"),
    [
        ([(b"", 1)], "generation_unavailable", (1, 0, 0)),
        ([(b"{}", 0)], "metadata_mismatch", (1, 0, 0)),
        ([(b"x" * (1024 * 1024 + 1), 0)], "limit_exceeded", (1, 0, 0)),
    ],
)
def test_metadata_failures_are_fixed_and_stop_before_body(monkeypatch, tmp_path, replies, reason, attempts):
    script = _load_script()
    source, _ = _source_and_body(tmp_path)
    factory = _Factory(replies)
    monkeypatch.setattr(script.subprocess, "Popen", factory)
    body, receipt = script.fetch_public_index(source, wrapper=ROOT / "scripts" / "gcloud_repo.py")
    assert body is None
    assert receipt.reason == reason
    assert (
        receipt.vcf_metadata_attempts,
        receipt.tbi_metadata_attempts,
        receipt.tbi_body_attempts,
    ) == attempts


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("generation", "999"),
        ("size", "999"),
        ("size", 134),
        ("md5Hash", "AQEBAQEBAQEBAQEBAQEBAQ=="),
        ("crc32c", "AQEBAQ=="),
    ],
)
def test_each_raw_metadata_identity_mismatch_refuses(monkeypatch, tmp_path, field, value):
    script = _load_script()
    source, _ = _source_and_body(tmp_path)
    metadata = json.loads(_metadata(source.vcf))
    metadata[field] = value
    factory = _Factory([(json.dumps(metadata).encode(), 0)])
    monkeypatch.setattr(script.subprocess, "Popen", factory)
    received, receipt = script.fetch_public_index(source, wrapper=ROOT / "scripts" / "gcloud_repo.py")
    assert received is None
    assert receipt.reason == "metadata_mismatch"
    assert (receipt.vcf_metadata_attempts, receipt.tbi_metadata_attempts, receipt.tbi_body_attempts) == (
        1,
        0,
        0,
    )


def test_unavailable_tbi_generation_stops_before_body(monkeypatch, tmp_path):
    script = _load_script()
    source, _ = _source_and_body(tmp_path)
    factory = _Factory([(_metadata(source.vcf), 0), (b"", 1)])
    monkeypatch.setattr(script.subprocess, "Popen", factory)
    received, receipt = script.fetch_public_index(source, wrapper=ROOT / "scripts" / "gcloud_repo.py")
    assert received is None
    assert receipt.reason == "generation_unavailable"
    assert (receipt.vcf_metadata_attempts, receipt.tbi_metadata_attempts, receipt.tbi_body_attempts) == (
        1,
        1,
        0,
    )


@pytest.mark.parametrize(
    "raw",
    [b'{"generation":"1","generation":"1"}', b'{"generation":NaN}'],
)
def test_duplicate_and_nonfinite_metadata_refuse(monkeypatch, tmp_path, raw):
    script = _load_script()
    source, _ = _source_and_body(tmp_path)
    factory = _Factory([(raw, 0)])
    monkeypatch.setattr(script.subprocess, "Popen", factory)
    received, receipt = script.fetch_public_index(source, wrapper=ROOT / "scripts" / "gcloud_repo.py")
    assert received is None
    assert receipt.reason == "metadata_mismatch"


def test_body_timeout_is_bounded_and_refused(monkeypatch, tmp_path):
    script = _load_script()
    source, _ = _source_and_body(tmp_path)

    class SlowStream:
        def read(self, size):
            time.sleep(0.05)
            return b""

    class SlowProcess(_Process):
        def __init__(self):
            super().__init__(b"")
            self.stdout = SlowStream()

    class TimeoutFactory(_Factory):
        def __call__(self, argv, **kwargs):
            self.calls.append((argv, kwargs))
            if len(self.calls) == 3:
                return SlowProcess()
            raw, returncode = self.replies.pop(0)
            return _Process(raw, returncode)

    factory = TimeoutFactory([(_metadata(source.vcf), 0), (_metadata(source.tbi), 0)])
    monkeypatch.setattr(script.subprocess, "Popen", factory)
    monkeypatch.setattr(script, "REQUEST_TIMEOUT_SECONDS", 0.001)
    received, receipt = script.fetch_public_index(source, wrapper=ROOT / "scripts" / "gcloud_repo.py")
    assert received is None
    assert receipt.reason == "transfer_failed"
    assert receipt.tbi_body_attempts == 1


@pytest.mark.parametrize("case", ["partial", "oversized", "checksum", "transfer"])
def test_body_failures_do_not_return_cacheable_bytes(monkeypatch, tmp_path, case):
    script = _load_script()
    source, body = _source_and_body(tmp_path)
    supplied, status, reason = body, 0, None
    if case == "partial":
        supplied, reason = body[:-1], "size_mismatch"
    elif case == "oversized":
        source = replace(source, tbi=replace(source.tbi, size_bytes=16 * 1024 * 1024 + 1))
        reason = "limit_exceeded"
    elif case == "checksum":
        supplied, reason = body[:-1] + bytes([body[-1] ^ 1]), "checksum_mismatch"
    else:
        status, reason = 1, "transfer_failed"
    replies = [(_metadata(source.vcf), 0), (_metadata(source.tbi), 0)]
    if case != "oversized":
        replies.append((supplied, status))
    factory = _Factory(replies)
    monkeypatch.setattr(script.subprocess, "Popen", factory)
    received, receipt = script.fetch_public_index(source, wrapper=ROOT / "scripts" / "gcloud_repo.py")
    assert received is None
    assert receipt.reason == reason
    assert receipt.sha256 is None
    assert receipt.tbi_body_attempts == (0 if case == "oversized" else 1)


def test_cli_rejects_malformed_manifest_before_any_process(monkeypatch, tmp_path):
    script = _load_script()
    bad = tmp_path / "manifest.json"
    bad.write_bytes(b"{}\n")
    windows = tmp_path / "windows.tsv"
    windows.write_bytes(b"bad\n")
    out = tmp_path / "out"
    calls = []
    monkeypatch.setattr(script.subprocess, "Popen", lambda *args, **kwargs: calls.append(args))
    with pytest.raises(SystemExit) as exited:
        script.main(["--manifest", str(bad), "--windows", str(windows), "--out", str(out)])
    assert exited.value.code == 2
    assert calls == []
    assert not out.exists()


def test_cli_refuses_existing_output_before_any_process(monkeypatch, tmp_path):
    script = _load_script()
    from tests.test_freeze_reference_windows_cli import _command, _run

    frozen = tmp_path / "frozen"
    assert _run(_command(frozen)).returncode == 0
    out = tmp_path / "out"
    out.mkdir()
    marker = out / "keep"
    marker.write_bytes(b"unchanged")
    calls = []
    monkeypatch.setattr(script.subprocess, "Popen", lambda *args, **kwargs: calls.append(args))
    with pytest.raises(SystemExit) as exited:
        script.main(
            [
                "--manifest",
                str(frozen / "manifest.json"),
                "--windows",
                str(frozen / "windows.tsv"),
                "--out",
                str(out),
            ]
        )
    assert exited.value.code == 2
    assert calls == []
    assert marker.read_bytes() == b"unchanged"


def test_cli_retains_all_66_windows_after_one_index_failure(monkeypatch, tmp_path):
    script = _load_script()
    from tests.test_freeze_reference_windows_cli import _command, _run

    frozen = tmp_path / "frozen"
    assert _run(_command(frozen)).returncode == 0
    manifest = decode_manifest(
        (frozen / "manifest.json").read_bytes(), windows_bytes=(frozen / "windows.tsv").read_bytes()
    )

    def fetch(source, *, wrapper):
        if source.chrom == "chr2":
            return None, IndexReceipt("chr2", "refused", "transfer_failed", 1, 1, 1, 0, None)
        body = b"x" * source.tbi.size_bytes
        return body, IndexReceipt(
            source.chrom, "verified", None, 1, 1, 1, len(body), hashlib.sha256(body).hexdigest()
        )

    monkeypatch.setattr(script, "fetch_public_index", fetch)
    monkeypatch.setattr(
        script,
        "parse_tbi",
        lambda raw, *, expected_chrom, vcf_size_bytes: TbiIndex(
            expected_chrom, (), (), None, None, None, None
        ),
    )
    out = tmp_path / "preflight"
    result = script.main(
        [
            "--manifest",
            str(frozen / "manifest.json"),
            "--windows",
            str(frozen / "windows.tsv"),
            "--out",
            str(out),
        ]
    )
    assert result != 0
    payload = json.loads((out / "preflight.json").read_bytes())
    all_windows = [window for source in payload["sources"] for window in source["windows"]]
    assert len(all_windows) == 66
    assert [window["window_id"] for window in all_windows] == [
        window.window_id for window in manifest.windows
    ]
    assert [window["state"] for window in all_windows if window["window_id"].startswith("chr2-")] == [
        "refused"
    ] * 3
    assert all(
        window["state"] == "no_index_chunks"
        for window in all_windows
        if not window["window_id"].startswith("chr2-")
    )
    assert payload["complete"] is False
    assert payload["budget_status"] == "incomplete"
    assert payload["total_planned_bytes"] is None
    assert payload["known_planned_bytes"] > 0
    assert sorted(path.name for path in out.iterdir()) == ["indexes", "preflight.json"]
    cached = sorted((out / "indexes").iterdir(), key=lambda path: int(path.stem[3:]))
    assert [path.name for path in cached] == [f"chr{chrom}.tbi" for chrom in range(1, 23) if chrom != 2]
    assert not (out / "indexes" / "chr2.tbi").exists()
    receipts = {source["source"]["chrom"]: source["receipt"] for source in payload["sources"]}
    for path in cached:
        assert hashlib.sha256(path.read_bytes()).hexdigest() == receipts[path.stem]["sha256"]
    completion_mtime = (out / "preflight.json").stat().st_mtime_ns
    assert all(path.stat().st_mtime_ns <= completion_mtime for path in cached)


def test_cli_never_caches_any_refusal_or_parser_invalid_body(monkeypatch, tmp_path):
    script = _load_script()
    from tests.test_freeze_reference_windows_cli import _command, _run

    frozen = tmp_path / "frozen"
    assert _run(_command(frozen)).returncode == 0
    reasons = (
        "metadata_mismatch",
        "generation_unavailable",
        "transfer_failed",
        "size_mismatch",
        "checksum_mismatch",
        "limit_exceeded",
    )

    def fetch(source, *, wrapper):
        chrom_number = int(source.chrom[3:])
        if chrom_number <= len(reasons):
            return None, IndexReceipt(source.chrom, "refused", reasons[chrom_number - 1], 1, 0, 0, 0, None)
        body = source.chrom.encode() + b"x" * (source.tbi.size_bytes - len(source.chrom))
        return body, IndexReceipt(
            source.chrom, "verified", None, 1, 1, 1, len(body), hashlib.sha256(body).hexdigest()
        )

    def parse(raw, *, expected_chrom, vcf_size_bytes):
        if expected_chrom == "chr7":
            raise ValueError("synthetic parser refusal")
        return TbiIndex(expected_chrom, (), (), None, None, None, None)

    monkeypatch.setattr(script, "fetch_public_index", fetch)
    monkeypatch.setattr(script, "parse_tbi", parse)
    out = tmp_path / "preflight"
    assert (
        script.main(
            [
                "--manifest",
                str(frozen / "manifest.json"),
                "--windows",
                str(frozen / "windows.tsv"),
                "--out",
                str(out),
            ]
        )
        == 1
    )
    payload = json.loads((out / "preflight.json").read_bytes())
    receipt_by_chrom = {source["source"]["chrom"]: source["receipt"] for source in payload["sources"]}
    for chrom_number, reason in enumerate((*reasons, "index_invalid"), start=1):
        chrom = f"chr{chrom_number}"
        assert receipt_by_chrom[chrom]["reason"] == reason
        assert not (out / "indexes" / f"{chrom}.tbi").exists()
    for chrom_number in range(8, 23):
        path = out / "indexes" / f"chr{chrom_number}.tbi"
        body = path.read_bytes()
        assert body.startswith(f"chr{chrom_number}".encode())
        assert hashlib.sha256(body).hexdigest() == receipt_by_chrom[f"chr{chrom_number}"]["sha256"]
