"""Explicit subcase execution/accounting for offline validation (design §7, §8).

Failures do not stop independent subcases. A dependency failure or interruption produces
an explicit incomplete outcome. This module does no numerical work and sets no tolerance.
"""

from __future__ import annotations

import traceback
from collections.abc import Callable
from typing import Any


def execute_subcases(
    plan: list[dict],
    actions: dict[str, Callable[[], dict]],
    record: Callable[[dict], None],
) -> dict:
    identifiers = [item["subcase_id"] for item in plan]
    if len(set(identifiers)) != len(plan) or set(identifiers) != set(actions):
        raise ValueError("subcase action inventory differs from declared plan")
    earlier = set()
    for item in plan:
        if not set(item["depends_on"]) <= earlier:
            raise ValueError("subcase dependencies must refer to earlier declared subcases")
        earlier.add(item["subcase_id"])
    record({"event": "subcase_plan", "subcases": plan})
    outcomes = []
    statuses = {}

    def outcome(item: dict) -> None:
        statuses[item["subcase_id"]] = item["status"]
        outcomes.append(item)
        record({"event": "subcase_outcome", **item})

    try:
        for item in plan:
            identifier = item["subcase_id"]
            blocked = [name for name in item["depends_on"] if statuses[name] != "pass"]
            if blocked:
                outcome(
                    {
                        **item,
                        "status": "incomplete",
                        "reason": "dependency did not pass",
                        "blocked_by": blocked,
                    }
                )
                continue
            record({"event": "subcase_started", **item})
            try:
                evidence = actions[identifier]()
                outcome(
                    {
                        **item,
                        "status": "pass" if evidence.get("passed", True) else "fail",
                        "evidence": evidence,
                    }
                )
            except Exception as error:
                outcome(
                    {**item, "status": "fail", "message": str(error), "traceback": traceback.format_exc()}
                )
    finally:
        for item in plan:
            if item["subcase_id"] not in statuses:
                outcome({**item, "status": "incomplete", "reason": "execution interrupted"})
    return {
        "planned_subcases": plan,
        "subcases": outcomes,
        "passed": all(item["status"] == "pass" for item in outcomes),
    }


def subcase(identifier: str, *dependencies: str) -> dict[str, Any]:
    return {"subcase_id": identifier, "depends_on": list(dependencies)}
