"""Deterministic B0H diagnostic seed identities (design §§5, 7–8, 12; #211)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np

from genomeos.validation.heterogeneity_simulation_types import (
    SbcCaseId,
    simulation_integer,
)

SEED = 42


@dataclass(frozen=True)
class DiagnosticSeedIdentity:
    """One declared selection, rank, PIT, or prior-control RNG namespace."""

    case: SbcCaseId
    attempt_id: int
    purpose_id: Literal[5, 6, 7, 8]
    spawn_key: tuple[int, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.case, SbcCaseId):
            raise ValueError("case must be an SbcCaseId")
        case = SbcCaseId(
            self.case.track_id,
            self.case.study_id,
            self.case.case_id,
            self.case.replicate_id,
        )
        if case.study_id == 3:
            raise ValueError("diagnostic seeds require a nonstructural study")
        attempt = simulation_integer(self.attempt_id, "attempt_id")
        if attempt not in (0, 1):
            raise ValueError("attempt_id must be 0 or 1")
        purpose = simulation_integer(self.purpose_id, "purpose_id")
        if purpose not in (5, 6, 7, 8):
            raise ValueError("purpose_id must be between 5 and 8")
        if not isinstance(self.spawn_key, tuple):
            raise ValueError("spawn_key must be an immutable integer tuple")
        spawn_key = tuple(
            simulation_integer(value, f"spawn_key[{index}]")
            for index, value in enumerate(self.spawn_key)
        )
        valid_key = (
            len(spawn_key) == 1 and 0 <= spawn_key[0] < 4
            if purpose == 5
            else len(spawn_key) == 2
            and 0 <= spawn_key[0] < 3
            and 0 <= spawn_key[1] < 6
            if purpose == 6
            else spawn_key == ()
            if purpose == 7
            else spawn_key == (1,)
        )
        if not valid_key:
            raise ValueError("spawn_key does not match its diagnostic purpose")
        if purpose in (5, 6, 8) and case.study_id != 0:
            raise ValueError("this diagnostic purpose is restricted to study 0")
        object.__setattr__(self, "case", case)
        object.__setattr__(self, "attempt_id", attempt)
        object.__setattr__(self, "purpose_id", purpose)
        object.__setattr__(self, "spawn_key", spawn_key)

    @property
    def entropy(self) -> tuple[int, int, int, int, int, int, int, int, int]:
        """Return the full literal diagnostic namespace entropy."""
        case = self.case
        return (
            SEED,
            211,
            1,
            case.track_id,
            case.study_id,
            case.case_id,
            case.replicate_id,
            self.purpose_id,
            self.attempt_id,
        )

    @property
    def scalar_words(self) -> tuple[int, int, int, int] | None:
        """Return the full four-word scalar identity for purposes 6 and 7."""
        if self.purpose_id not in (6, 7):
            return None
        sequence = np.random.SeedSequence(self.entropy, spawn_key=self.spawn_key)
        return tuple(int(word) for word in sequence.generate_state(4, dtype=np.uint32))

    @property
    def scalar_uint128(self) -> int | None:
        """Assemble scalar words little-endian without narrowing to uint32."""
        words = self.scalar_words
        if words is None:
            return None
        return sum(word << (32 * index) for index, word in enumerate(words))
