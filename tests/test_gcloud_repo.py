from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "gcloud_repo", ROOT / "scripts" / "gcloud_repo.py"
)
assert SPEC and SPEC.loader
GCLOUD_REPO = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GCLOUD_REPO)


def test_gcloud_environment_is_repo_local():
    environment = GCLOUD_REPO.gcloud_environment()
    assert environment["CLOUDSDK_CONFIG"] == str(
        ROOT / ".local" / "gcloud" / "genomeos"
    )


def test_login_defaults_to_personal_account():
    with patch.object(GCLOUD_REPO, "run_gcloud", return_value=0) as run:
        with patch("sys.argv", ["gcloud_repo.py", "auth", "login"]):
            assert GCLOUD_REPO.main() == 0
    run.assert_called_once_with(["auth", "login", "dawei.lin100@gmail.com"])


def test_init_does_not_guess_a_project():
    with patch.dict("os.environ", {}, clear=True), patch.object(
        GCLOUD_REPO, "run_gcloud", return_value=0
    ) as run:
        assert GCLOUD_REPO.command_init(None) == 0
    commands = [call.args[0] for call in run.call_args_list]
    assert commands == [
        ["config", "set", "account", "dawei.lin100@gmail.com"],
        ["config", "set", "run/region", "us-east1"],
    ]


def test_init_sets_only_explicit_project():
    with patch.object(GCLOUD_REPO, "run_gcloud", return_value=0) as run:
        assert GCLOUD_REPO.command_init("genomeos-project") == 0
    commands = [call.args[0] for call in run.call_args_list]
    assert ["config", "set", "project", "genomeos-project"] in commands
