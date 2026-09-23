"""Contracts for the first-party coverage badge generator."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_generator_writes_svg_without_a_readme_or_pages_checkout(tmp_path: Path) -> None:
    report = tmp_path / "coverage.json"
    badge = tmp_path / "coverage.svg"
    report.write_text(
        json.dumps({"totals": {"percent_covered": 84.6}}),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).parents[1] / "scripts" / "render_coverage_badge.py"),
            "--coverage-json",
            str(report),
            "--out",
            str(badge),
        ],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert 'aria-label="coverage: 85%"' in badge.read_text(encoding="utf-8")
