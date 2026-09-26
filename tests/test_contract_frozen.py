import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_frozen_contract_matches_the_live_schemas():
    # Running a script puts the script's directory on sys.path, not the cwd, so without this the
    # subprocess resolves `genomeos` through the editable install — which in a git worktree is a
    # different checkout. The test then failed with a ModuleNotFoundError that reads as contract
    # drift for any module that exists only on the branch under test (#258).
    result = subprocess.run(
        [sys.executable, "scripts/freeze_contract.py", "--check"],
        cwd=REPO,
        env={**os.environ, "PYTHONPATH": str(REPO)},
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


def test_curated_variant_contracts_are_frozen():
    expected = {
        "curated_variants.schema.json",
        "cpic_pair_targets.schema.json",
        "cpic_coverage.schema.json",
    }
    assert expected.issubset({path.name for path in (REPO / "contract").glob("*.json")})
