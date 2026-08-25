#!/usr/bin/env python3
"""Run the mandatory fast checks for the API and Atlas contracts."""

from __future__ import annotations

import compileall
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SMOKE_TESTS = (
    "tests/test_api.py",
    "tests/test_registry_schema.py",
    "tests/test_observations_schema.py",
    "tests/test_h3util.py",
    "tests/test_artifact_catalog.py",
    "tests/test_atlas_api.py",
    "tests/test_observability.py",
)


def main() -> int:
    if not compileall.compile_dir(ROOT / "genomeos", quiet=1):
        print("Python compilation smoke check failed", file=sys.stderr)
        return 1
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT)
    subprocess.run(
        [sys.executable, "scripts/freeze_contract.py", "--check"],
        cwd=ROOT,
        check=True,
        env=environment,
    )
    subprocess.run(
        [sys.executable, "-m", "pytest", "-q", *SMOKE_TESTS],
        cwd=ROOT,
        check=True,
        env=environment,
    )
    print("smoke checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
