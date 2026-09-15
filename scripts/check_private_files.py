#!/usr/bin/env python3
"""Reject tracked private files, high-confidence credential material, and personal paths."""

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
}

# A tracked file may not hard-code someone's home directory. There are two costs, and the second
# is the one that surprises people: it commits a contributor's username and machine layout to a
# public repo, *and* it is a portability bug this same check catches for free. `Path("C:/Users/x")`
# is not absolute on POSIX, where `pathlib` treats `C:` as an ordinary relative segment, so a
# `mkdir(parents=True)` on it silently builds a junk `./C:/Users/x` tree instead of failing (#235).
#
# Windows first, so a drive-qualified path is reported at full length rather than as the
# `/Users/x` nested inside it.
PERSONAL_PATH_PATTERNS = (
    re.compile(r"""[A-Za-z]:[\\/]+Users[\\/]+[^\\/\s"'`)\]]+"""),
    re.compile(r"""/(?:Users|home)/+[^/\s"'`)\]]+"""),
)

# Names that identify a role, a placeholder, or a CI runner rather than a person. `runner` is
# GitHub Actions; `vscode`, `ubuntu`, `node` and `app` are devcontainer and base-image
# conventions. All of these appear legitimately in config, and a gate that fails on them gets
# deleted rather than satisfied. Add to this set rather than removing the check.
PLACEHOLDER_USERS = frozenset(
    {
        "user", "users", "username", "youruser", "your-user", "your_user", "you", "yourname",
        "name", "me", "someone", "example", "placeholder", "foo", "bar", "test", "ci",
        "runner", "vscode", "ubuntu", "node", "app", "root", "home", "shared", "public",
    }
)

# A scanner and its own tests must contain the shapes they detect, so they cannot scan themselves.
SELF_EXEMPT = frozenset({"scripts/check_private_files.py", "tests/test_check_private_files.py"})


def personal_paths(text: str) -> list[tuple[int, str]]:
    """Home-directory-shaped paths in `text`, as `(line number, matched text)`.

    `$HOME`, `~`, and `%USERPROFILE%` are deliberately **not** reported. Those are the portable
    ways to name a home directory, so flagging them would penalise the correct spelling — the
    problem is a path pinned to one person's machine, not the concept of a home directory.
    """
    findings: list[tuple[int, str]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        accepted: list[tuple[int, int]] = []
        for pattern in PERSONAL_PATH_PATTERNS:
            for match in pattern.finditer(line):
                segment = [part for part in re.split(r"[\\/]+", match.group()) if part][-1]
                if segment.lower() in PLACEHOLDER_USERS or segment[:1] in {"<", "{", "$", "%", "["}:
                    continue
                if any(start <= match.start() and match.end() <= end for start, end in accepted):
                    continue
                accepted.append((match.start(), match.end()))
                findings.append((number, match.group()))
    return findings


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
        if name not in SELF_EXEMPT:
            for number, match in personal_paths(content.decode("utf-8", errors="ignore")):
                failures.append(f"personal path: {name}:{number}: {match}")

    if failures:
        print("Private-file check failed. Do not commit or push:")
        print("\n".join(f"- {failure}" for failure in failures))
        if any(failure.startswith("personal path:") for failure in failures):
            print(
                "\nA personal path is both a privacy leak and a portability bug. Take the path "
                "through argparse with a relative default, or write $HOME / ~ / %USERPROFILE%. "
                "If the name is a role or a CI runner rather than a person, add it to "
                "PLACEHOLDER_USERS."
            )
        return 1
    print(f"private-file check passed ({len(files)} tracked files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
