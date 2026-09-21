"""Frozen numerical process settings for B0H execution (design §§5,7–8,12; #337)."""

from __future__ import annotations

import os

NUMERICAL_THREAD_CAPS = (
    ("OMP_NUM_THREADS", "1"),
    ("MKL_NUM_THREADS", "1"),
    ("OPENBLAS_NUM_THREADS", "1"),
    ("NUMEXPR_NUM_THREADS", "1"),
)


def apply_numerical_thread_caps() -> None:
    """Set caps before importing numerical libraries in a science process."""
    os.environ.update(NUMERICAL_THREAD_CAPS)


def require_numerical_thread_caps() -> None:
    """Refuse admission when the process did not bootstrap under the frozen caps."""
    mismatched = [name for name, value in NUMERICAL_THREAD_CAPS if os.environ.get(name) != value]
    if mismatched:
        raise ValueError("numerical thread caps are not established: " + ", ".join(mismatched))
