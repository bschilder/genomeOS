import json
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


def test_literature_contracts_and_observation_source_key_are_frozen():
    expected = {
        "literature_evidence.schema.json",
        "literature_field_evidence.schema.json",
        "literature_searches.schema.json",
    }
    assert expected.issubset({path.name for path in (REPO / "contract").glob("*.json")})
    observations = json.loads((REPO / "contract" / "observations.schema.json").read_text())
    assert "source_record_id" in observations["columns"]
