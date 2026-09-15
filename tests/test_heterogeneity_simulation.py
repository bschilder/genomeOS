"""Independent fixtures for B0H synthetic generation (design §§5, 7–8, 12)."""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import FrozenInstanceError, replace
from fractions import Fraction

import numpy as np
import pytest

from genomeos.validation import heterogeneity_simulation as sim
from genomeos.validation import heterogeneity_simulation_types as sim_types
from genomeos.validation.reference_counts import ReferenceCount


class RecordingRng:
    """Strict scalar queue fake; assertions concern production outputs and call order."""

    def __init__(self, events: list[tuple[str, object]]) -> None:
        self.events = iter(events)
        self.calls: list[tuple[object, ...]] = []

    def _next(self, method: str, *args: object) -> object:
        expected_method, value = next(self.events)
        assert expected_method == method
        self.calls.append((method, *args))
        if isinstance(value, BaseException):
            raise value
        return value

    def beta(self, a: float, b: float) -> object:
        return self._next("beta", a, b)

    def random(self) -> object:
        return self._next("random")

    def binomial(self, n: int, p: float) -> object:
        return self._next("binomial", n, p)

    def assert_exhausted(self) -> None:
        with pytest.raises(StopIteration):
            next(self.events)


class GeneratorFactory:
    def __init__(self, rngs: list[RecordingRng]) -> None:
        self.rngs = iter(rngs)
        self.entropies: list[tuple[int, ...]] = []

    def __call__(self, bit_generator: object) -> RecordingRng:
        self.entropies.append(tuple(bit_generator))  # type: ignore[arg-type]
        return next(self.rngs)


def _patch_rngs(monkeypatch: pytest.MonkeyPatch, rngs: list[RecordingRng]) -> GeneratorFactory:
    factory = GeneratorFactory(rngs)
    monkeypatch.setattr(np.random, "PCG64", lambda seed: seed.entropy)
    monkeypatch.setattr(np.random, "Generator", factory)
    return factory


def test_manifest_and_literal_seed_anchors() -> None:
    cases = sim.enumerate_sbc_cases()
    assert len(cases) == 1938
    assert Counter(c.study_id for c in cases) == {0: 1024, 1: 768, 2: 128, 3: 2, 4: 16}
    assert cases[0].canonical_id == "b0h_sbc_v1:s0:c0:r0:t0"
    assert cases[1].canonical_id == "b0h_sbc_v1:s0:c0:r0:t1"
    assert cases[-1].canonical_id == "b0h_sbc_v1:s4:c1:r3:t1"
    assert [(c.study_id, c.case_id, c.replicate_id, c.track_id) for c in cases] == sorted(
        (c.study_id, c.case_id, c.replicate_id, c.track_id) for c in cases
    )
    anchors = (
        (cases[0], 0, 279725986),
        (cases[0], 1, 2209982770),
        (cases[1], 0, 848552836),
        (cases[1], 1, 1074711532),
        (cases[-2], 0, 1211901720),
        (cases[-2], 1, 3856046949),
        (cases[-1], 0, 1619381632),
        (cases[-1], 1, 522047641),
    )
    for case, attempt, expected in anchors:
        identity = sim.sbc_seed_identity(case, purpose_id=4, attempt_id=attempt)
        assert identity.fit_uint32 == expected
    assert sim.sbc_seed_identity(cases[0], purpose_id=4, attempt_id=0).entropy == (
        42,
        211,
        1,
        0,
        0,
        0,
        0,
        4,
        0,
    )


def test_facade_reexports_only_the_frozen_original_api() -> None:
    assert sim.SbcCaseId is sim_types.SbcCaseId
    assert sim.GeneratedDataset is sim_types.GeneratedDataset
    assert sim.GenerationResult is sim_types.GenerationResult
    assert "simulation_probability" not in sim.__all__
    assert not hasattr(sim, "simulation_probability")


def test_supporting_helpers_validate_domains_and_declared_rows() -> None:
    assert sim_types.simulation_integer(np.int16(2), "value") == 2
    assert sim_types.simulation_probability(np.float32(0.25), "value") == 0.25
    assert math.isnan(sim_types.simulation_failure_scalar(math.nan, "value"))
    case = sim.SbcCaseId(0, 1, 0, 0)
    generation = sim.generation_id(case)
    assert sim_types.fixed_simulation_truth(case) == sim.ParameterTruth(0.001, 0.0)
    assert sim_types.simulation_training_an(case) == (0, 1, 2, 5, 10, 20, 40, 64) * 2
    row = sim_types.simulation_reference_count(generation, "train", "0", 0, 0)
    assert (row.record_id, row.an) == (f"synthetic:{generation.canonical_id}:train:row:0", 0)
    for helper, args in (
        (sim_types.simulation_integer, (True, "value")),
        (sim_types.simulation_probability, (np.longdouble(0.2), "value")),
        (sim_types.simulation_failure_scalar, (np.array(0.2), "value")),
        (sim_types.fixed_simulation_truth, (object(),)),
        (sim_types.simulation_training_an, (object(),)),
        (sim_types.simulation_reference_count, (generation, "train", "00", 0, 0)),
        (sim_types.simulation_reference_count, (generation, "train", "0", 0, 20)),
        (sim_types.simulation_reference_count, (generation, "heldout", "fresh_cluster", 0, 20)),
    ):
        with pytest.raises(ValueError):
            helper(*args)


@pytest.mark.parametrize(
    ("case", "truth", "ans"),
    (
        (sim.SbcCaseId(0, 1, 0, 0), sim.ParameterTruth(0.001, 0.0), (0, 1, 2, 5, 10, 20, 40, 64) * 2),
        (sim.SbcCaseId(0, 1, 1, 0), sim.ParameterTruth(0.001, 0.0), (20,) * 16),
        (sim.SbcCaseId(0, 1, 23, 0), sim.ParameterTruth(0.5, 0.5), (20,) * 16),
        (sim.SbcCaseId(0, 2, 3, 0), sim.ParameterTruth(0.5, 0.5), (0, 1, 2, 5, 10, 20, 40, 64) * 2),
    ),
)
def test_literal_case_decoding(case: sim.SbcCaseId, truth: sim.ParameterTruth, ans: tuple[int, ...]) -> None:
    result = sim.generate_sbc_case(case)
    assert isinstance(result, sim.GeneratedDataset)
    assert result.truth == truth
    assert tuple(row.an for row in result.training) == ans


def test_fixed_interior_matches_independent_scalar_numpy_construction() -> None:
    case = sim.SbcCaseId(track_id=0, study_id=1, case_id=13, replicate_id=0)
    result = sim.generate_sbc_case(case)
    kappa = (1.0 - 0.1) / 0.1
    rng_q = np.random.Generator(np.random.PCG64(np.random.SeedSequence((42, 211, 1, 99, 1, 13, 0, 1, 0))))
    q = tuple(float(rng_q.beta(0.05 * kappa, 0.95 * kappa)) for _ in range(16))
    rng_ac = np.random.Generator(np.random.PCG64(np.random.SeedSequence((42, 211, 1, 99, 1, 13, 0, 2, 0))))
    ac = tuple(int(rng_ac.binomial(20, p)) for p in q)
    rng_test = np.random.Generator(np.random.PCG64(np.random.SeedSequence((42, 211, 1, 99, 1, 13, 0, 3, 0))))
    q_test = float(rng_test.beta(0.05 * kappa, 0.95 * kappa))
    ac_test = int(rng_test.binomial(20, q_test))
    assert isinstance(result, sim.GeneratedDataset)
    assert result.truth == sim.ParameterTruth(0.05, 0.1)
    assert result.latent_frequencies == q
    assert tuple(row.ac for row in result.training) == ac
    assert tuple(row.an for row in result.training) == (20,) * 16
    assert result.heldouts[0].latent_frequency == q_test
    assert result.heldouts[0].row.ac == ac_test


def test_prior_track_one_matches_literal_independent_streams() -> None:
    case = sim.SbcCaseId(1, 0, 0, 0)
    truth_rng = np.random.Generator(np.random.PCG64(np.random.SeedSequence((42, 211, 1, 1, 0, 0, 0, 0, 0))))
    mean = float(truth_rng.beta(1, 1))
    rho = float(truth_rng.beta(1, 4))
    kappa = (1.0 - rho) / rho
    population_rng = np.random.Generator(
        np.random.PCG64(np.random.SeedSequence((42, 211, 1, 1, 0, 0, 0, 1, 0)))
    )
    frequencies = tuple(float(population_rng.beta(mean * kappa, (1.0 - mean) * kappa)) for _ in range(16))
    ans = (0, 1, 2, 5, 10, 20, 40, 64) * 2
    count_rng = np.random.Generator(np.random.PCG64(np.random.SeedSequence((42, 211, 1, 1, 0, 0, 0, 2, 0))))
    counts = tuple(int(count_rng.binomial(an, q)) for an, q in zip(ans, frequencies, strict=True))
    heldout_rng = np.random.Generator(np.random.PCG64(np.random.SeedSequence((42, 211, 1, 1, 0, 0, 0, 3, 0))))
    heldout_q = float(heldout_rng.beta(mean * kappa, (1.0 - mean) * kappa))
    heldout_ac = int(heldout_rng.binomial(20, heldout_q))

    result = sim.generate_sbc_case(case)
    assert isinstance(result, sim.GeneratedDataset)
    assert result.truth == sim.ParameterTruth(mean, rho)
    assert result.latent_frequencies == frequencies
    assert tuple(row.ac for row in result.training) == counts
    assert tuple(row.an for row in result.training) == ans
    assert tuple((result.training[i].ac, result.latent_frequencies[i]) for i in (0, 8)) == (
        (0, frequencies[0]),
        (0, frequencies[8]),
    )
    assert result.heldouts[0].latent_frequency == heldout_q
    assert result.heldouts[0].row.ac == heldout_ac


def test_unavailable_has_no_invented_truth_or_rng(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden_rng(*args: object, **kwargs: object) -> object:
        raise AssertionError("structural fixture must make no RNG")

    monkeypatch.setattr(np.random, "Generator", forbidden_rng)
    result = sim.generate_sbc_case(sim.SbcCaseId(0, 3, 0, 0))
    assert isinstance(result, sim.AllUnavailableDataset)
    assert result.status == "all_unavailable"
    assert len(result.training) == 16
    assert {(row.ac, row.an) for row in result.training} == {(0, 0)}
    assert result.truth is None and result.latent_frequencies is None
    assert result.heldouts == () and result.expected_sampler_calls == 0


@pytest.mark.parametrize(("study", "case", "replicate"), ((1, 13, 0), (2, 3, 2)))
def test_paired_tracks_share_generation_but_not_fit_seeds(study: int, case: int, replicate: int) -> None:
    left_case = sim.SbcCaseId(0, study, case, replicate)
    right_case = sim.SbcCaseId(1, study, case, replicate)
    left = sim.generate_sbc_case(left_case)
    right = sim.generate_sbc_case(right_case)
    assert isinstance(left, sim.GeneratedDataset) and isinstance(right, sim.GeneratedDataset)
    assert replace(left, case_id=right.case_id) == right
    assert sim.sbc_seed_identity(left_case, purpose_id=4, attempt_id=0) != sim.sbc_seed_identity(
        right_case, purpose_id=4, attempt_id=0
    )
    assert sim.generate_sbc_case(left_case) == left
    sim.generate_sbc_case(sim.SbcCaseId(0, 1, 13, 4))
    assert sim.generate_sbc_case(left_case) == left


def test_boundary_generation_and_immutability() -> None:
    zero = sim.generate_sbc_case(sim.SbcCaseId(0, 4, 0, 0))
    one = sim.generate_sbc_case(sim.SbcCaseId(1, 4, 1, 3))
    assert isinstance(zero, sim.GeneratedDataset) and isinstance(one, sim.GeneratedDataset)
    assert (tuple(row.ac for row in zero.training), zero.heldouts[0].row.ac) == ((0,) * 16, 0)
    assert (tuple(row.ac for row in one.training), one.heldouts[0].row.ac) == ((20,) * 16, 20)
    assert zero.beta_zero_draws == zero.beta_one_draws == 0
    assert one.beta_zero_draws == one.beta_one_draws == 0
    with pytest.raises(FrozenInstanceError):
        zero.truth.mean = 0.2  # type: ignore[misc]
    with pytest.raises(TypeError):
        zero.training[0] = zero.training[0]  # type: ignore[index]


def test_shared_history_uses_exact_scalar_order_and_separate_streams(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    population_events: list[tuple[str, object]] = [("beta", 0.2)]
    for index in range(8):
        population_events.extend((("beta", 0.6), ("random", 0.0 if index % 2 == 0 else 0.9)))
    population_events.append(("beta", 0.8))
    for index in range(8):
        population_events.extend((("beta", 0.6), ("random", 0.0 if index % 2 == 0 else 0.9)))
    population = RecordingRng(population_events)
    counts = RecordingRng([("binomial", 0)] * 16)
    heldout = RecordingRng(
        [
            ("beta", 0.7),
            ("random", 0.0),
            ("binomial", 0),
            ("beta", 0.3),
            ("beta", 0.9),
            ("random", 0.9),
            ("binomial", 0),
        ]
    )
    factory = _patch_rngs(monkeypatch, [population, counts, heldout])

    result = sim.generate_sbc_case(sim.SbcCaseId(0, 2, 3, 0))
    assert isinstance(result, sim.GeneratedDataset)
    assert factory.entropies == [(42, 211, 1, 99, 2, 3, 0, purpose, 0) for purpose in (1, 2, 3)]
    assert result.latent_frequencies == (0.2, 0.6) * 4 + (0.8, 0.6) * 4
    assert result.shared_history == sim.SharedHistory((0.2, 0.8), (0.6,) * 16, (True, False) * 8)
    assert tuple((target.kind, target.latent_frequency, target.cluster_id) for target in result.heldouts) == (
        ("shared_cluster0", 0.2, 0),
        ("fresh_cluster", 0.9, 2),
    )
    expected_population_calls: list[tuple[object, ...]] = [("beta", 0.5, 0.5)]
    for _ in range(8):
        expected_population_calls.extend((("beta", 0.5, 0.5), ("random",)))
    expected_population_calls.append(("beta", 0.5, 0.5))
    for _ in range(8):
        expected_population_calls.extend((("beta", 0.5, 0.5), ("random",)))
    assert population.calls == expected_population_calls
    assert counts.calls == [
        ("binomial", an, q)
        for an, q in zip((0, 1, 2, 5, 10, 20, 40, 64) * 2, result.latent_frequencies, strict=True)
    ]
    assert heldout.calls == [
        ("beta", 0.5, 0.5),
        ("random",),
        ("binomial", 20, 0.2),
        ("beta", 0.5, 0.5),
        ("beta", 0.5, 0.5),
        ("random",),
        ("binomial", 20, 0.9),
    ]
    training_ids = {(row.record_id, row.group_id) for row in result.training}
    heldout_ids = {(target.row.record_id, target.row.group_id) for target in result.heldouts}
    assert training_ids.isdisjoint(heldout_ids)


@pytest.mark.parametrize(
    ("first_u", "fresh_u", "expected"),
    (
        (0.9, 0.0, (0.7, 0.3)),
        (math.sqrt(0.5), math.sqrt(0.5), (0.7, 0.9)),
    ),
)
def test_shared_heldout_selection_boundary(
    monkeypatch: pytest.MonkeyPatch,
    first_u: float,
    fresh_u: float,
    expected: tuple[float, float],
) -> None:
    population = RecordingRng(
        [("beta", 0.2)]
        + [(item, value) for _ in range(8) for item, value in (("beta", 0.6), ("random", 0.9))]
        + [("beta", 0.8)]
        + [(item, value) for _ in range(8) for item, value in (("beta", 0.6), ("random", 0.9))]
    )
    counts = RecordingRng([("binomial", 0)] * 16)
    heldout = RecordingRng(
        [
            ("beta", 0.7),
            ("random", first_u),
            ("binomial", 0),
            ("beta", 0.3),
            ("beta", 0.9),
            ("random", fresh_u),
            ("binomial", 0),
        ]
    )
    _patch_rngs(monkeypatch, [population, counts, heldout])
    result = sim.generate_sbc_case(sim.SbcCaseId(0, 2, 3, 0))
    assert isinstance(result, sim.GeneratedDataset)
    assert tuple(target.latent_frequency for target in result.heldouts) == expected


def test_boundary_and_rho_zero_make_no_beta_or_uniform_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for case, q, expected_ac in (
        (sim.SbcCaseId(0, 4, 0, 0), 0.0, 0),
        (sim.SbcCaseId(0, 4, 1, 0), 1.0, 20),
        (sim.SbcCaseId(0, 1, 1, 0), 0.001, 0),
    ):
        count = RecordingRng([("binomial", expected_ac)] * 16)
        heldout = RecordingRng([("binomial", expected_ac)])
        factory = _patch_rngs(monkeypatch, [count, heldout])
        result = sim.generate_sbc_case(case)
        assert isinstance(result, sim.GeneratedDataset)
        assert factory.entropies == [
            (42, 211, 1, 99, case.study_id, case.case_id, case.replicate_id, purpose, 0) for purpose in (2, 3)
        ]
        assert all(call[0] == "binomial" for call in count.calls + heldout.calls)
        assert count.calls == [("binomial", 20, q)] * 16
        assert heldout.calls == [("binomial", 20, q)]
        count.assert_exhausted()
        heldout.assert_exhausted()


def test_latent_beta_endpoints_are_retained_forwarded_and_counted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    latents = (0.0, 1.0) + (0.5,) * 14
    population = RecordingRng([("beta", value) for value in latents])
    counts = RecordingRng([("binomial", 0)] * 16)
    heldout = RecordingRng([("beta", 1.0), ("binomial", 0)])
    _patch_rngs(monkeypatch, [population, counts, heldout])
    result = sim.generate_sbc_case(sim.SbcCaseId(0, 1, 12, 0))
    assert isinstance(result, sim.GeneratedDataset)
    assert result.latent_frequencies == latents
    assert (result.beta_zero_draws, result.beta_one_draws) == (1, 2)
    assert counts.calls[0] == ("binomial", 0, 0.0)
    assert counts.calls[1] == ("binomial", 1, 1.0)


def test_shared_unselected_endpoint_candidates_are_counted_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    population_events: list[tuple[str, object]] = [("beta", 0.0)]
    population_events.extend(
        (method, value) for _ in range(8) for method, value in (("beta", 0.6), ("random", 0.0))
    )
    population_events.append(("beta", 0.8))
    population_events.extend(
        (method, value) for _ in range(8) for method, value in (("beta", 0.6), ("random", 0.0))
    )
    heldout_events = [
        ("beta", 1.0),
        ("random", 0.0),
        ("binomial", 0),
        ("beta", 0.3),
        ("beta", 0.9),
        ("random", 0.9),
        ("binomial", 0),
    ]
    _patch_rngs(
        monkeypatch,
        [
            RecordingRng(population_events),
            RecordingRng([("binomial", 0)] * 16),
            RecordingRng(heldout_events),
        ],
    )
    result = sim.generate_sbc_case(sim.SbcCaseId(0, 2, 3, 0))
    assert isinstance(result, sim.GeneratedDataset)
    assert result.latent_frequencies[:8] == (0.0,) * 8
    assert result.heldouts[0].latent_frequency == 0.0
    assert (result.beta_zero_draws, result.beta_one_draws) == (1, 1)


def test_prior_boundary_and_shape_underflow_are_explicit_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    truth = RecordingRng([("beta", 0.0), ("beta", 0.1)])
    _patch_rngs(monkeypatch, [truth])
    boundary = sim.generate_sbc_case(sim.SbcCaseId(0, 0, 0, 0))
    assert isinstance(boundary, sim.GenerationFailure)
    assert (boundary.stage, boundary.reason, boundary.sampled_mean, boundary.sampled_rho) == (
        "truth_validation",
        "rounded_prior_boundary",
        0.0,
        0.1,
    )
    assert truth.calls == [("beta", 1.0, 1.0), ("beta", 1.0, 9.0)]

    tiny = float(np.nextafter(0.0, 1.0))
    truth = RecordingRng([("beta", tiny), ("beta", 0.9)])
    _patch_rngs(monkeypatch, [truth])
    underflow = sim.generate_sbc_case(sim.SbcCaseId(0, 0, 0, 0))
    assert isinstance(underflow, sim.GenerationFailure)
    assert (underflow.stage, underflow.reason, underflow.truth) == (
        "beta_shapes",
        "invalid_beta_shapes",
        sim.ParameterTruth(tiny, 0.9),
    )


@pytest.mark.parametrize("value", (math.nan, math.inf, -0.1, 1.1, True, np.array([0.2])))
def test_invalid_training_beta_scalar_returns_no_partial_dataset(
    monkeypatch: pytest.MonkeyPatch, value: object
) -> None:
    population = RecordingRng([("beta", 0.2), ("beta", value)])
    _patch_rngs(monkeypatch, [population])
    failure = sim.generate_sbc_case(sim.SbcCaseId(0, 1, 13, 0))
    assert isinstance(failure, sim.GenerationFailure)
    assert (failure.stage, failure.index, failure.reason, failure.truth) == (
        "training_population",
        1,
        "invalid_rng_scalar",
        sim.ParameterTruth(0.05, 0.1),
    )
    assert not hasattr(failure, "training") and not hasattr(failure, "heldouts")


@pytest.mark.parametrize("error", (ValueError("bad"), FloatingPointError("fp"), OverflowError("wide")))
def test_expected_rng_exceptions_are_typed(monkeypatch: pytest.MonkeyPatch, error: BaseException) -> None:
    population = RecordingRng([("beta", 0.2), ("beta", error)])
    _patch_rngs(monkeypatch, [population])
    failure = sim.generate_sbc_case(sim.SbcCaseId(0, 1, 13, 0))
    assert isinstance(failure, sim.GenerationFailure)
    assert (failure.stage, failure.index, failure.reason) == (
        "training_population",
        1,
        "rng_exception",
    )
    assert (failure.exception_type, failure.exception_message) == (type(error).__name__, str(error))


class CustomValueError(ValueError):
    pass


@pytest.mark.parametrize(
    "error",
    (RuntimeError("runner"), MemoryError("memory"), CustomValueError("custom")),
)
def test_unexpected_rng_exceptions_propagate(monkeypatch: pytest.MonkeyPatch, error: BaseException) -> None:
    population = RecordingRng([("beta", error)])
    _patch_rngs(monkeypatch, [population])
    with pytest.raises(type(error), match=str(error)):
        sim.generate_sbc_case(sim.SbcCaseId(0, 1, 13, 0))


def _valid_shared_rngs() -> list[RecordingRng]:
    population: list[tuple[str, object]] = []
    for _ in range(2):
        population.append(("beta", 0.4))
        population.extend(
            (method, value) for _ in range(8) for method, value in (("beta", 0.6), ("random", 0.9))
        )
    return [
        RecordingRng(population),
        RecordingRng([("binomial", 0)] * 16),
        RecordingRng(
            [
                ("beta", 0.7),
                ("random", 0.9),
                ("binomial", 0),
                ("beta", 0.3),
                ("beta", 0.8),
                ("random", 0.9),
                ("binomial", 0),
            ]
        ),
    ]


@pytest.mark.parametrize(
    ("stream", "position", "replacement", "stage", "index"),
    (
        (0, 17, ("beta", math.nan), "training_cluster", 1),
        (0, 3, ("beta", -0.1), "training_population", 1),
        (0, 4, ("random", 1.0), "training_switch", 1),
        (1, 1, ("binomial", 0.5), "training_count", 1),
        (2, 0, ("beta", np.array([0.2])), "heldout_population", 0),
        (2, 1, ("random", True), "heldout_switch", 0),
        (2, 2, ("binomial", 21), "heldout_count", 0),
        (2, 3, ("beta", math.inf), "heldout_cluster", 1),
        (2, 4, ("beta", 2.0), "heldout_population", 1),
        (2, 5, ("random", 1.0), "heldout_switch", 1),
        (2, 6, ("binomial", -1), "heldout_count", 1),
    ),
)
def test_every_shared_failure_stage_returns_typed_refusal(
    monkeypatch: pytest.MonkeyPatch,
    stream: int,
    position: int,
    replacement: tuple[str, object],
    stage: str,
    index: int,
) -> None:
    rngs = _valid_shared_rngs()
    events = list(rngs[stream].events)
    events[position] = replacement
    rngs[stream] = RecordingRng(events)
    _patch_rngs(monkeypatch, rngs)
    failure = sim.generate_sbc_case(sim.SbcCaseId(0, 2, 3, 0))
    assert isinstance(failure, sim.GenerationFailure)
    assert (failure.stage, failure.index, failure.reason) == (
        stage,
        index,
        "invalid_rng_scalar",
    )


@pytest.mark.parametrize(
    ("events", "stage", "sampled_mean"),
    (
        ([("beta", math.nan)], "truth_mean", math.nan),
        ([("beta", 0.4), ("beta", np.array([0.1]))], "truth_rho", 0.4),
        ([("beta", ValueError("truth failed"))], "truth_mean", None),
        ([("beta", 0.4), ("beta", FloatingPointError("rho failed"))], "truth_rho", 0.4),
    ),
)
def test_truth_draw_failures_retain_only_returned_scalar_candidates(
    monkeypatch: pytest.MonkeyPatch,
    events: list[tuple[str, object]],
    stage: str,
    sampled_mean: float | None,
) -> None:
    _patch_rngs(monkeypatch, [RecordingRng(events)])
    failure = sim.generate_sbc_case(sim.SbcCaseId(0, 0, 0, 0))
    assert isinstance(failure, sim.GenerationFailure)
    assert (failure.stage, failure.sampled_rho) == (stage, None)
    if sampled_mean is not None and math.isnan(sampled_mean):
        assert math.isnan(failure.sampled_mean)
    else:
        assert failure.sampled_mean == sampled_mean


@pytest.mark.parametrize(
    ("events", "expected_mean", "expected_rho"),
    (
        ([("beta", 10**10000)], 10**10000, None),
        ([("beta", 2**53 + 1)], 2**53 + 1, None),
        ([("beta", 0.4), ("beta", 10**10000)], 0.4, 10**10000),
        ([("beta", 0.4), ("beta", 2**53 + 1)], 0.4, 2**53 + 1),
    ),
    ids=("huge_mean", "wide_mean", "huge_rho", "wide_rho"),
)
def test_invalid_prior_integer_candidates_remain_exact_failure_evidence(
    monkeypatch: pytest.MonkeyPatch,
    events: list[tuple[str, object]],
    expected_mean: float | int,
    expected_rho: int | None,
) -> None:
    _patch_rngs(monkeypatch, [RecordingRng(events)])
    failure = sim.generate_sbc_case(sim.SbcCaseId(0, 0, 0, 0))
    assert isinstance(failure, sim.GenerationFailure)
    expected_stage = "truth_mean" if expected_rho is None else "truth_rho"
    expected_offending = expected_mean if expected_rho is None else expected_rho
    assert (failure.stage, failure.reason) == (expected_stage, "invalid_rng_scalar")
    assert failure.sampled_mean == expected_mean
    assert failure.sampled_rho == expected_rho
    assert failure.offending_value == expected_offending
    if isinstance(expected_mean, int):
        assert type(failure.sampled_mean) is int
    if expected_rho is not None:
        assert type(failure.sampled_rho) is int


def test_failure_constructor_rejects_impossible_operation_and_exception_states() -> None:
    rho_zero = sim.generate_sbc_case(sim.SbcCaseId(0, 1, 1, 0))
    ordinary = sim.generate_sbc_case(sim.SbcCaseId(0, 1, 13, 0))
    shared = sim.generate_sbc_case(sim.SbcCaseId(0, 2, 3, 0))
    assert isinstance(rho_zero, sim.GeneratedDataset)
    assert isinstance(ordinary, sim.GeneratedDataset)
    assert isinstance(shared, sim.GeneratedDataset)

    def failure(
        source: sim.GeneratedDataset,
        stage: str,
        index: int | None,
        *,
        reason: str = "rng_exception",
        offending: float | int | None = None,
        exception_type: str | None = "ValueError",
        exception_message: str | None = "failed",
    ) -> sim.GenerationFailure:
        return sim.GenerationFailure(
            source.case_id,
            source.provenance,
            stage,
            index,
            reason,
            source.truth,
            None,
            None,
            offending,
            exception_type,
            exception_message,
        )

    invalid = (
        lambda: failure(ordinary, "heldout_count", 1),
        lambda: failure(ordinary, "heldout_population", 1),
        lambda: failure(shared, "heldout_cluster", 0),
        lambda: failure(rho_zero, "beta_shapes", None, reason="invalid_beta_shapes"),
        lambda: failure(rho_zero, "training_population", 0),
        lambda: failure(ordinary, "training_cluster", 0),
        lambda: failure(ordinary, "training_switch", 0),
        lambda: failure(
            ordinary,
            "training_count",
            0,
            exception_type="MemoryError",
        ),
        lambda: failure(
            ordinary,
            "training_count",
            0,
            exception_type="CustomValueError",
        ),
        lambda: failure(ordinary, "training_count", 0, offending=1),
        lambda: failure(
            ordinary,
            "training_count",
            0,
            reason="invalid_rng_scalar",
            exception_type="ValueError",
            exception_message="failed",
        ),
        lambda: failure(
            ordinary,
            "beta_shapes",
            None,
            reason="invalid_beta_shapes",
            offending=0.0,
        ),
        lambda: failure(
            ordinary,
            "beta_shapes",
            None,
            reason="invalid_beta_shapes",
            offending=1.0,
            exception_type=None,
            exception_message=None,
        ),
        lambda: sim.GenerationFailure(
            ordinary.case_id,
            ordinary.provenance,
            [],  # type: ignore[arg-type]
            0,
            "rng_exception",
            ordinary.truth,
            None,
            None,
            None,
            "ValueError",
            "failed",
        ),
        lambda: sim.GenerationFailure(
            ordinary.case_id,
            ordinary.provenance,
            "training_count",
            0,
            [],  # type: ignore[arg-type]
            ordinary.truth,
            None,
            None,
            None,
            "ValueError",
            "failed",
        ),
        lambda: sim.GenerationFailure(
            ordinary.case_id,
            ordinary.provenance,
            "training_count",
            0,
            "rng_exception",
            object(),  # type: ignore[arg-type]
            None,
            None,
            None,
            "ValueError",
            "failed",
        ),
    )
    for construct in invalid:
        with pytest.raises(ValueError):
            construct()

    prior = sim.generate_sbc_case(sim.SbcCaseId(0, 0, 0, 0))
    assert isinstance(prior, sim.GeneratedDataset)
    for malformed in (True, Fraction(1, 2), np.longdouble("0.2"), np.array([0.2])):
        with pytest.raises(ValueError):
            sim.GenerationFailure(
                prior.case_id,
                prior.provenance,
                "truth_mean",
                None,
                "invalid_rng_scalar",
                None,
                malformed,  # type: ignore[arg-type]
                None,
                None,
                None,
                None,
            )
    with pytest.raises(ValueError):
        sim.GenerationFailure(
            prior.case_id,
            prior.provenance,
            "training_count",
            0,
            "rng_exception",
            sim.ParameterTruth(prior.truth.mean, 0.0),
            prior.truth.mean,
            prior.truth.rho,
            None,
            "ValueError",
            "failed",
        )


def test_failure_constructor_rejects_scalars_accepted_by_downstream_operation() -> None:
    mixed = sim.generate_sbc_case(sim.SbcCaseId(0, 1, 0, 0))
    ordinary = sim.generate_sbc_case(sim.SbcCaseId(0, 1, 13, 0))
    shared = sim.generate_sbc_case(sim.SbcCaseId(0, 2, 3, 0))
    assert isinstance(mixed, sim.GeneratedDataset)
    assert isinstance(ordinary, sim.GeneratedDataset)
    assert isinstance(shared, sim.GeneratedDataset)

    accepted_returns = (
        (ordinary, "training_population", 0, 0),
        (ordinary, "heldout_population", 0, 0.5),
        (shared, "training_cluster", 0, 1),
        (shared, "heldout_cluster", 1, 1.0),
        (shared, "training_switch", 0, 0.5),
        (shared, "heldout_switch", 0, 0),
        (ordinary, "training_count", 0, 10),
        (ordinary, "heldout_count", 0, 20),
        (mixed, "training_count", 0, 0),
    )
    for source, stage, index, offending in accepted_returns:
        with pytest.raises(ValueError):
            sim.GenerationFailure(
                source.case_id,
                source.provenance,
                stage,
                index,
                "invalid_rng_scalar",
                source.truth,
                None,
                None,
                offending,
                None,
                None,
            )


def test_failure_constructor_preserves_scalars_refused_by_downstream_operation() -> None:
    mixed = sim.generate_sbc_case(sim.SbcCaseId(0, 1, 0, 0))
    ordinary = sim.generate_sbc_case(sim.SbcCaseId(0, 1, 13, 0))
    shared = sim.generate_sbc_case(sim.SbcCaseId(0, 2, 3, 0))
    assert isinstance(mixed, sim.GeneratedDataset)
    assert isinstance(ordinary, sim.GeneratedDataset)
    assert isinstance(shared, sim.GeneratedDataset)
    huge = 10**10000

    refused_returns = (
        (ordinary, "training_population", 0, math.nan),
        (ordinary, "heldout_population", 0, math.inf),
        (shared, "training_cluster", 0, -0.1),
        (shared, "heldout_cluster", 1, huge),
        (shared, "training_switch", 0, 1.0),
        (shared, "heldout_switch", 0, -0.1),
        (ordinary, "training_count", 0, 10.0),
        (ordinary, "heldout_count", 0, 21),
        (mixed, "training_count", 0, 1),
        (ordinary, "training_count", 0, huge),
    )
    for source, stage, index, offending in refused_returns:
        failure = sim.GenerationFailure(
            source.case_id,
            source.provenance,
            stage,
            index,
            "invalid_rng_scalar",
            source.truth,
            None,
            None,
            offending,
            None,
            None,
        )
        if isinstance(offending, float) and math.isnan(offending):
            assert math.isnan(failure.offending_value)  # type: ignore[arg-type]
        else:
            assert failure.offending_value == offending
        if offending is huge:
            assert type(failure.offending_value) is int


@pytest.mark.parametrize(
    "args",
    (
        (99, 0, 0, 0),
        (2, 0, 0, 0),
        (0, 5, 0, 0),
        (0, 0, 1, 0),
        (0, 1, 24, 0),
        (0, 2, 4, 0),
        (0, 3, 0, 1),
        (0, 4, 0, 4),
        (-1, 0, 0, 0),
        (False, 0, 0, 0),
        (0.0, 0, 0, 0),
    ),
)
def test_case_id_rejects_unsupported_domains(args: tuple[object, ...]) -> None:
    with pytest.raises(ValueError):
        sim.SbcCaseId(*args)  # type: ignore[arg-type]


def test_seed_identity_rejects_unsupported_domains() -> None:
    case = sim.SbcCaseId(0, 1, 0, 0)
    for purpose, attempt in ((9, 0), (0, 1), (4, 2), (False, 0), (0.0, 0)):
        with pytest.raises(ValueError):
            sim.sbc_seed_identity(case, purpose_id=purpose, attempt_id=attempt)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        sim.sbc_seed_identity(sim.SbcCaseId(0, 3, 0, 0), purpose_id=4, attempt_id=0)
    valid = sim.SeedIdentity((42, 211, 1, 99, 1, 0, 0, 0, 0))
    for entropy in (
        (1,) * 9,
        valid.entropy[:-1],
        (*valid.entropy[:-1], True),
        (42, 211, 1, 0, 1, 0, 0, 0, 0),
    ):
        with pytest.raises(ValueError):
            sim.SeedIdentity(entropy)  # type: ignore[arg-type]


def test_parameter_truth_rejects_unsupported_and_nonfinite_values() -> None:
    assert sim.ParameterTruth(np.float32(0.5), np.float16(0.25)) == sim.ParameterTruth(0.5, 0.25)
    for mean, rho in (
        (True, 0.0),
        (0.5, False),
        (Fraction(1, 2), 0.1),
        (0.5, Fraction(1, 10)),
        (math.nan, 0.1),
        (0.5, math.inf),
        (-0.1, 0.0),
        (1.1, 0.0),
        (0.5, 1.0),
        (0.0, 0.1),
        (1.0, 0.1),
    ):
        with pytest.raises(ValueError):
            sim.ParameterTruth(mean, rho)  # type: ignore[arg-type]


def test_literal_shared_marginal_and_covariance_anchor() -> None:
    mean, rho = Fraction(1, 2), Fraction(1, 2)
    latent_variance = mean * (1 - mean) * rho
    latent_covariance = latent_variance / 2
    assert (latent_variance, latent_covariance) == (Fraction(1, 8), Fraction(1, 16))
    pmf = (Fraction(3, 8), Fraction(1, 4), Fraction(3, 8))
    expected = sum(index * probability for index, probability in enumerate(pmf))
    variance = sum((index - expected) ** 2 * probability for index, probability in enumerate(pmf))
    count_covariance = 2 * 2 * latent_covariance
    assert variance == Fraction(3, 4)
    assert count_covariance == Fraction(1, 4)
    assert count_covariance / variance == Fraction(1, 3)


def _row(generation: sim.GenerationId, *, where: str, key: str, ac: int, an: int) -> ReferenceCount:
    canonical = generation.canonical_id
    return ReferenceCount(
        record_id=f"synthetic:{canonical}:{where}:row:{key}",
        variant_id=f"synthetic:{canonical}:variant:0",
        group_id=f"synthetic:{canonical}:{where}:group:{key}",
        region_id="synthetic_nonspatial",
        variant_group="synthetic_single_variant",
        ac=ac,
        an=an,
    )


def test_public_result_constructors_reject_joint_mismatches() -> None:
    result = sim.generate_sbc_case(sim.SbcCaseId(0, 1, 13, 0))
    assert isinstance(result, sim.GeneratedDataset)
    with pytest.raises(ValueError):
        replace(result, training=result.training[:-1])
    with pytest.raises(ValueError):
        replace(result, latent_frequencies=(*result.latent_frequencies[:-1], math.nan))
    with pytest.raises(ValueError):
        replace(result, beta_zero_draws=result.beta_zero_draws + 1)
    with pytest.raises(ValueError):
        replace(result, training=(replace(result.training[0], an=21), *result.training[1:]))
    with pytest.raises(ValueError):
        replace(result, heldouts=(replace(result.heldouts[0], kind="shared_cluster0"),))
    with pytest.raises(ValueError):
        sim.AllUnavailableDataset(
            result.case_id,
            result.provenance,
            tuple(
                _row(result.provenance.generation_id, where="train", key=str(i), ac=0, an=0)
                for i in range(16)
            ),
        )

    rho_zero = sim.generate_sbc_case(sim.SbcCaseId(0, 1, 1, 0))
    boundary = sim.generate_sbc_case(sim.SbcCaseId(0, 4, 1, 0))
    shared = sim.generate_sbc_case(sim.SbcCaseId(0, 2, 3, 0))
    assert isinstance(rho_zero, sim.GeneratedDataset)
    assert isinstance(boundary, sim.GeneratedDataset)
    assert isinstance(shared, sim.GeneratedDataset)
    with pytest.raises(ValueError):
        replace(rho_zero, latent_frequencies=(0.2,) * 16)
    with pytest.raises(ValueError):
        replace(boundary, training=(replace(boundary.training[0], ac=19), *boundary.training[1:]))
    with pytest.raises(ValueError):
        replace(
            shared,
            shared_history=replace(
                shared.shared_history,
                cluster_frequencies=(0.123, shared.shared_history.cluster_frequencies[1]),
            ),
        )
    with pytest.raises(ValueError):
        replace(shared.heldouts[0], latent_frequency=0.123)
