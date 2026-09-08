"""Data-store inventory safeguards (design §5)."""

from __future__ import annotations

import json
import subprocess
import sys


def test_inventory_does_not_hash_the_file_it_is_about_to_replace(tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    source = root / "source.txt"
    source.write_text("source evidence\n")
    out = root / "INVENTORY.json"
    out.write_text("old inventory\n")

    completed = subprocess.run(
        [sys.executable, "scripts/store_inventory.py", "--root", str(root), "--out", str(out)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    paths = {entry["path"] for entry in json.loads(out.read_text())["files"]}
    assert str(source) in paths
    assert str(out) not in paths, "an overwritten inventory cannot truthfully hash itself"
