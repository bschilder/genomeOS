"""Literal B0H diagnostic namespaces (design §§5,7–8,12)."""
from __future__ import annotations

from dataclasses import FrozenInstanceError

import numpy as np
import pytest

from genomeos.validation import heterogeneity_diagnostic_seeds as seeds
from genomeos.validation.heterogeneity_diagnostic_seeds import DiagnosticSeedIdentity
from genomeos.validation.heterogeneity_simulation_types import SbcCaseId


@pytest.mark.parametrize("track", (0, 1))
@pytest.mark.parametrize("attempt", (0, 1))
def test_entropy_and_direct_children(track, attempt):
    case = SbcCaseId(track, 0, 0, 7)
    for chain in range(4):
        identity = DiagnosticSeedIdentity(case, attempt, 5, (chain,))
        entropy = (42, 211, 1, track, 0, 0, 7, 5, attempt)
        assert identity.entropy == entropy
        assert identity.scalar_words is None
        assert identity.scalar_uint128 is None
        direct = np.random.SeedSequence(entropy, spawn_key=(chain,))
        nested = np.random.SeedSequence(entropy).spawn(4)[chain]
        np.testing.assert_array_equal(direct.generate_state(4), nested.generate_state(4))
    for mode in range(3):
        for quantity in range(6):
            identity = DiagnosticSeedIdentity(case, attempt, 6, (mode, quantity))
            entropy = (42, 211, 1, track, 0, 0, 7, 6, attempt)
            nested = np.random.SeedSequence(entropy).spawn(3)[mode].spawn(6)[quantity]
            words = tuple(int(x) for x in nested.generate_state(4, dtype=np.uint32))
            assert identity.entropy == entropy
            assert identity.scalar_words == words
            assert identity.scalar_uint128 == sum(w << (32*i) for i, w in enumerate(words))


def test_literal_word_order(monkeypatch):
    calls = []

    class LiteralSequence:
        def __init__(self, entropy, *, spawn_key):
            calls.append((entropy, spawn_key))

        def generate_state(self, size, dtype):
            assert size == 4 and dtype is np.uint32
            return np.array([1, 2, 3, 4], dtype=np.uint32)

    monkeypatch.setattr(seeds.np.random, "SeedSequence", LiteralSequence)
    identity = DiagnosticSeedIdentity(SbcCaseId(1, 0, 0, 8), 1, 6, (2, 5))
    assert identity.scalar_words == (1, 2, 3, 4)
    assert identity.scalar_uint128 == 1 + (2 << 32) + (3 << 64) + (4 << 96)
    assert all(call == ((42, 211, 1, 1, 0, 0, 8, 6, 1), (2, 5)) for call in calls)


@pytest.mark.parametrize("study", (0, 1, 2, 4))
def test_pit_namespace_is_available_without_predictive_execution(study):
    identity = DiagnosticSeedIdentity(SbcCaseId(1, study, 0, 0), 1, 7, ())
    assert identity.entropy == (42, 211, 1, 1, study, 0, 0, 7, 1)
    assert len(identity.scalar_words) == 4
    assert isinstance(identity.scalar_uint128, int)


@pytest.mark.parametrize("attempt,purpose,key", (
    (True, 5, (0,)), (-1, 5, (0,)), (2, 5, (0,)),
    (0, True, (0,)), (0, 4, ()), (0, 9, ()),
    (0, 5, ()), (0, 5, (True,)), (0, 5, (4,)), (0, 5, [0]),
    (0, 6, (0,)), (0, 6, (3, 0)), (0, 6, (0, 6)),
    (0, 6, (0, False)), (0, 7, (0,)), (0, 8, (2,)),
))
def test_closed_domains(attempt, purpose, key):
    with pytest.raises(ValueError):
        DiagnosticSeedIdentity(SbcCaseId(0, 0, 0, 0), attempt, purpose, key)


@pytest.mark.parametrize("purpose,key", ((5, (0,)), (6, (0, 0)), (8, (1,))))
def test_prior_only_namespaces_refuse_stress(purpose, key):
    with pytest.raises(ValueError):
        DiagnosticSeedIdentity(SbcCaseId(0, 1, 0, 0), 0, purpose, key)


def test_structural_and_mutation_refusal():
    with pytest.raises(ValueError):
        DiagnosticSeedIdentity(SbcCaseId(0, 3, 0, 0), 0, 7, ())
    identity = DiagnosticSeedIdentity(SbcCaseId(0, 0, 0, 0), 0, 8, (1,))
    assert identity.scalar_words is identity.scalar_uint128 is None
    with pytest.raises(FrozenInstanceError):
        identity.attempt_id = 1
