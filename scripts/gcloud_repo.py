#!/usr/bin/env python3
"""Run gcloud with credentials and configuration isolated to this repository."""

from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO_GCLOUD_CONFIG = ROOT / ".local" / "gcloud" / "genomeos"
DEFAULT_REGION = "us-east1"


def gcloud_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment["CLOUDSDK_CONFIG"] = str(REPO_GCLOUD_CONFIG)
    return environment


def run_gcloud(arguments: list[str]) -> int:
    REPO_GCLOUD_CONFIG.mkdir(parents=True, exist_ok=True)
    return subprocess.call(
        ["gcloud", *arguments], cwd=ROOT, env=gcloud_environment()
    )


def configured_project(explicit: str | None) -> str | None:
    return explicit or os.getenv("GENOMEOS_GCP_PROJECT")


def configured_account(explicit: str | None) -> str | None:
    return explicit or os.getenv("GENOMEOS_GCP_ACCOUNT")


def command_info() -> int:
    project = configured_project(None) or "<not selected>"
    account = configured_account(None) or "<not selected>"
    print(
        "\n".join(
            [
                f"CLOUDSDK_CONFIG={REPO_GCLOUD_CONFIG}",
                f"account={account}",
                f"project={project}",
                f"default_region={DEFAULT_REGION}",
                "",
                "Use this wrapper instead of plain gcloud inside GenomeOS:",
                "  python scripts/gcloud_repo.py auth login",
                "  python scripts/gcloud_repo.py init --project PROJECT_ID",
                "  python scripts/gcloud_repo.py run auth list",
            ]
        )
    )
    return 0


def command_init(project: str | None, account: str | None) -> int:
    selected_account = configured_account(account)
    if not selected_account:
        raise SystemExit(
            "init requires --account or GENOMEOS_GCP_ACCOUNT; account identity is not stored in Git"
        )
    status = run_gcloud(["config", "set", "account", selected_account])
    if status:
        return status
    selected_project = configured_project(project)
    if selected_project:
        status = run_gcloud(["config", "set", "project", selected_project])
        if status:
            return status
    return run_gcloud(["config", "set", "run/region", DEFAULT_REGION])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Repository-isolated gcloud wrapper for GenomeOS"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("info")

    auth = subparsers.add_parser("auth")
    auth.add_argument("auth_arguments", nargs=argparse.REMAINDER)

    init = subparsers.add_parser("init")
    init.add_argument("--project")
    init.add_argument("--account")

    run = subparsers.add_parser("run")
    run.add_argument("gcloud_arguments", nargs=argparse.REMAINDER)
    return parser


def main() -> int:
    arguments = build_parser().parse_args()
    if arguments.command == "info":
        return command_info()
    if arguments.command == "init":
        return command_init(arguments.project, arguments.account)
    if arguments.command == "auth":
        auth_arguments = arguments.auth_arguments or ["login"]
        return run_gcloud(["auth", *auth_arguments])
    if not arguments.gcloud_arguments:
        raise SystemExit("run requires gcloud arguments")
    return run_gcloud(arguments.gcloud_arguments)


if __name__ == "__main__":
    raise SystemExit(main())
