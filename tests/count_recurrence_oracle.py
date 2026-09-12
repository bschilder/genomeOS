"""Shared independent absolute Decimal oracle for scoring checks (design §7, §8)."""

from __future__ import annotations

from scripts.count_recurrence_oracle import Oracle, absolute_law, verified_law

__all__ = ["Oracle", "absolute_law", "verified_law"]
