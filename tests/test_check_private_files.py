"""The tracked-file privacy gate (#235).

The gate's original job was secret-shaped strings and forbidden paths. It missed a personal home
directory written as a string literal *inside* a tracked file, because it inspected which files
were tracked rather than what they said about someone's machine. That gap had two costs: a
contributor's username and machine layout committed to a public repo, and a portability bug the
same check would have caught for free — `Path("C:/Users/...")` is not absolute on POSIX, so it
silently creates a junk `./C:/Users/...` tree instead of failing.

These tests exercise the pure scanning function directly, so a case can be added without a
throwaway git repository.
"""

from __future__ import annotations

import runpy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE = runpy.run_path(str(ROOT / "scripts" / "check_private_files.py"))
personal_paths = MODULE["personal_paths"]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('PAYLOAD_DIR = Path("C:/Users/Bola/.hermes/payloads")', "C:/Users/Bola"),
        # Reported verbatim, doubled separators included: that is the string a reviewer greps for.
        (r'PAYLOAD_DIR = Path("C:\\Users\\Bola\\payloads")', r"C:\\Users\\Bola"),
        ("cache = /Users/someperson/Library/Caches/genomeos", "/Users/someperson"),
        ("export DATA=/home/someperson/data/raw", "/home/someperson"),
        ('D:/Users/Bola/scratch', "D:/Users/Bola"),
    ],
)
def test_a_personal_home_directory_is_reported(text, expected):
    """The exact shapes seen in review, plus the Windows and env-var variants."""
    findings = personal_paths(text)
    assert findings, f"no finding for {text!r}"
    assert any(expected in match for _, match in findings)


def test_the_reported_line_number_is_the_offending_one():
    """A filename alone is not actionable when the file is 300 lines long."""
    text = "clean\nalso clean\nPAYLOAD_DIR = Path('C:/Users/Bola/x')\nclean again\n"
    assert [line for line, _ in personal_paths(text)] == [3]


@pytest.mark.parametrize(
    "text",
    [
        "python -m pip install -e '.[dev]'",
        ".venv/bin/python scripts/smoke.py",
        "OUT=$HOME/data",
        "set OUT=%USERPROFILE%\\genomeos",
        "OUT=~/data",
        "cp /Users/<user>/thing .",
        "cp /Users/youruser/thing .",
        "cp /home/your-user/thing .",
        "cp /Users/username/thing .",
        "runs in /home/runner/work/genomeOS on GitHub Actions",
        "the devcontainer mounts /home/vscode/src",
        "the image writes to /home/ubuntu/out",
    ],
)
def test_placeholders_and_ci_paths_are_not_reported(text):
    """A gate that fires on documentation or on a CI runner's own path gets disabled.

    `/home/runner` is GitHub Actions, `/home/vscode` and `/home/ubuntu` are devcontainer and image
    conventions. None of them identify a person, and all three appear legitimately in config.
    """
    assert personal_paths(text) == []


def test_the_repository_itself_is_clean():
    """The gate has to pass on `main`, or it will be removed rather than satisfied.

    This is the check that made the fix a two-part change: adding the pattern meant also fixing the
    one pre-existing plan document that recorded its verification commands as absolute paths on one
    contributor's machine.
    """
    main = MODULE["main"]
    assert main() == 0
