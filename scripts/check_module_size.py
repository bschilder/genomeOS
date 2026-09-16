#!/usr/bin/env python3
"""Fail when a production Python module exceeds the agent-readable budget."""

from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# `scripts/` holds production code, not just entry points — the Atlas exporter alone is over 700
# logical lines and enforces publication policy. Leaving it out of the budget is how that file
# reached 870 lines, past the hard cap, with every gate green: nothing was looking at it.
DEFAULT_ROOTS = (ROOT / "genomeos", ROOT / "scripts")


def logical_lines(path: Path) -> int:
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-lines", type=int, default=800)
    parser.add_argument("--max-bytes", type=int, default=50 * 1024)
    args = parser.parse_args(argv)

    failures: list[str] = []
    checked = 0
    for root in DEFAULT_ROOTS:
        for path in sorted(root.rglob("*.py")):
            checked += 1
            lines = logical_lines(path)
            size = path.stat().st_size
            if lines > args.max_lines or size > args.max_bytes:
                failures.append(
                    f"{path.relative_to(ROOT)}: {lines} logical lines, {size} bytes "
                    f"(limits: {args.max_lines}, {args.max_bytes})"
                )

    if failures:
        print("Modules over the agent-readable budget:")
        print("\n".join(f"- {failure}" for failure in failures))
        return 1
    print(f"module-size check passed ({checked} modules)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
