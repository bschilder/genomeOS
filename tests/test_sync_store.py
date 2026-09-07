"""Public data-store release boundaries (design §5, §11)."""

from __future__ import annotations

import json

from scripts.sync_store import ATLAS_RELEASE_SUPPORT, atlas_release_targets


def test_atlas_release_contains_exactly_the_allowlist_and_reviewed_support(tmp_path):
    artifact_names = [f"artifact-{index}" for index in range(30)]
    allowlist = tmp_path / "public-artifacts.json"
    allowlist.write_text(
        json.dumps({"artifacts": [{"artifact_dir": name} for name in artifact_names]})
    )

    targets = atlas_release_targets(allowlist)

    artifact_targets = targets[:30]
    assert {local.rsplit("/", 1)[-1] for local, _ in artifact_targets} == set(artifact_names)
    assert targets[30:] == ATLAS_RELEASE_SUPPORT
    local_paths = {local for local, _ in targets}
    assert not any(
        forbidden in path
        for path in local_paths
        for forbidden in ("data/raw/", "store/fits", "store/screen", "store/surfaces")
    )


def test_atlas_release_refuses_path_traversal(tmp_path):
    entries = [{"artifact_dir": f"artifact-{index}"} for index in range(29)]
    entries.append({"artifact_dir": "../private"})
    allowlist = tmp_path / "public-artifacts.json"
    allowlist.write_text(json.dumps({"artifacts": entries}))

    try:
        atlas_release_targets(allowlist)
    except ValueError as error:
        assert "safe basename" in str(error)
    else:
        raise AssertionError("path traversal must be refused")
