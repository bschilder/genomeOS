#!/usr/bin/env python3
"""Reject tracked private files and high-confidence credential material."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_PARTS = {".codex", ".agents", ".local", ".nvim-chatgpt"}
FORBIDDEN_NAMES = {".env", "auth.json", "history.jsonl", "credentials.json"}
FORBIDDEN_SUFFIXES = {".pem", ".key", ".p12", ".pfx"}
NAME_PATTERNS = (
    re.compile(r"credentials.*\.json$", re.IGNORECASE),
    re.compile(r"service[-_]?account.*\.json$", re.IGNORECASE),
)
SECRET_PATTERNS = {
    "private key": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "GitHub token": re.compile(rb"(?:gh[pousr]_|github_pat_)[A-Za-z0-9_]{20,}"),
    "AWS access key": re.compile(rb"AKIA[0-9A-Z]{16}"),
    "Google API key": re.compile(rb"AIza[0-9A-Za-z_-]{30,}"),
    "Slack token": re.compile(rb"xox[baprs]-[0-9A-Za-z-]{20,}"),
    "OpenAI-style key": re.compile(rb"sk-(?:proj-)?[A-Za-z0-9_-]{20,}"),
    "personal email address": re.compile(
        rb"[A-Za-z0-9._%+-]+@(?:gmail|outlook|yahoo|icloud|protonmail)\.[A-Za-z]{2,}",
        re.IGNORECASE,
    ),
}


def tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return [item.decode() for item in result.stdout.split(b"\0") if item]


def forbidden_path(name: str) -> bool:
    path = PurePosixPath(name)
    if any(part in FORBIDDEN_PARTS for part in path.parts):
        return True
    if path.name in FORBIDDEN_NAMES or path.suffix.lower() in FORBIDDEN_SUFFIXES:
        return True
    return any(pattern.search(path.name) for pattern in NAME_PATTERNS)


def main() -> int:
    failures: list[str] = []
    files = tracked_files()
    for name in files:
        if forbidden_path(name):
            failures.append(f"forbidden tracked path: {name}")
            continue
        path = ROOT / name
        if not path.is_file() or path.stat().st_size > 5 * 1024 * 1024:
            continue
        content = path.read_bytes()
        for kind, pattern in SECRET_PATTERNS.items():
            if pattern.search(content):
                failures.append(f"possible {kind}: {name}")

    if failures:
        print("Private-file check failed. Do not commit or push:")
        print("\n".join(f"- {failure}" for failure in failures))
        return 1
    print(f"private-file check passed ({len(files)} tracked files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
