"""The agent-readable module budget, and what it actually looks at.

A budget that does not cover a tree is not a budget for that tree. `scripts/` was outside the scan
while holding production code, so the Atlas exporter grew past the hard cap with every gate green.
"""

from __future__ import annotations

from pathlib import Path

from scripts.check_module_size import DEFAULT_ROOTS, logical_lines, main

ROOT = Path(__file__).resolve().parents[1]


def test_the_budget_covers_both_trees_that_hold_production_code():
    """`scripts/` is production code. Dropping it from the scan silently disables the gate there."""
    scanned = {path.name for path in DEFAULT_ROOTS}
    assert scanned == {"genomeos", "scripts"}


def test_logical_lines_ignores_blank_lines_but_counts_comments():
    """The budget is about how much there is to read, so a comment counts and a blank line does not."""
    sample = ROOT / "scripts" / "check_module_size.py"
    text = sample.read_text(encoding="utf-8")
    assert logical_lines(sample) == sum(1 for line in text.splitlines() if line.strip())
    assert logical_lines(sample) < len(text.splitlines())


def test_the_repository_is_within_budget():
    """This has to pass on main, or the gate gets removed rather than satisfied."""
    assert main([]) == 0
