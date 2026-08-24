import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_frozen_contract_matches_the_live_schemas():
    result = subprocess.run(
        [sys.executable, "scripts/freeze_contract.py", "--check"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
