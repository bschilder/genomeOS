"""Lossless B0H prior-control outcomes (design §§5, 7–8, 12; #211)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np

from genomeos.validation.heterogeneity_diagnostic_seeds import DiagnosticSeedIdentity
from genomeos.validation.heterogeneity_simulation_types import (
    simulation_failure_scalar,
    simulation_integer,
    simulation_probability,
)

SEED = 42


def _qualified_name(value: object, name: str) -> str:
    if type(value) is not str or "." not in value or any(not part for part in value.split(".")):
        raise ValueError(f"{name} must be a nonempty qualified string")
    return value


def _interior_probability(value: object, name: str) -> float:
    probability = simulation_probability(value, name)
    if probability in (0.0, 1.0):
        raise ValueError(f"{name} must be strictly interior")
    return probability


@dataclass(frozen=True)
class DiagnosticCallError:
    """Lossless class and message from one actual diagnostic call exception."""

    exception_class: str
    message: str

    def __post_init__(self) -> None:
        exception_class = _qualified_name(self.exception_class, "exception_class")
        if type(self.message) is not str:
            raise ValueError("message must be a literal string")
        object.__setattr__(self, "exception_class", exception_class)


@dataclass(frozen=True)
class PriorControlFailure:
    """The first failed scalar draw after an immutable complete-pair prefix."""

    chain: int
    parameter: Literal["mean", "rho"]
    reason: Literal["rng_exception", "invalid_scalar", "rounded_boundary"]
    sampled_mean: float | int | None
    sampled_rho: float | int | None
    returned_type: str | None
    error: DiagnosticCallError | None

    def __post_init__(self) -> None:
        chain = simulation_integer(self.chain, "chain")
        if chain not in range(4):
            raise ValueError("chain must be between 0 and 3")
        if type(self.parameter) is not str or self.parameter not in ("mean", "rho"):
            raise ValueError("parameter must be mean or rho")
        if type(self.reason) is not str or self.reason not in (
            "rng_exception",
            "invalid_scalar",
            "rounded_boundary",
        ):
            raise ValueError("reason is not a declared prior-control failure")
        mean = (
            None
            if self.sampled_mean is None
            else simulation_failure_scalar(self.sampled_mean, "sampled_mean")
        )
        rho = (
            None
            if self.sampled_rho is None
            else simulation_failure_scalar(self.sampled_rho, "sampled_rho")
        )
        returned_type = (
            None
            if self.returned_type is None
            else _qualified_name(self.returned_type, "returned_type")
        )
        if self.error is not None and not isinstance(self.error, DiagnosticCallError):
            raise ValueError("error must be a DiagnosticCallError or None")
        error = (
            None
            if self.error is None
            else DiagnosticCallError(self.error.exception_class, self.error.message)
        )
        if self.parameter == "mean":
            if rho is not None:
                raise ValueError("mean failure cannot retain rho evidence")
            current = mean
        else:
            if mean is None:
                raise ValueError("rho failure must retain its accepted mean")
            mean = _interior_probability(mean, "sampled_mean")
            current = rho
        if self.reason == "rng_exception":
            if current is not None or returned_type is not None or error is None:
                raise ValueError("rng_exception requires only actual exception evidence")
        elif self.reason == "invalid_scalar":
            if error is not None or (current is None) == (returned_type is None):
                raise ValueError("invalid_scalar requires exactly one return evidence form")
            if current is not None:
                try:
                    simulation_probability(current, f"sampled_{self.parameter}")
                except ValueError:
                    pass
                else:
                    raise ValueError("invalid scalar evidence must fail the probability domain")
        else:
            if current is None or returned_type is not None or error is not None:
                raise ValueError("rounded_boundary requires only endpoint evidence")
            if simulation_probability(current, f"sampled_{self.parameter}") not in (0.0, 1.0):
                raise ValueError("rounded boundary evidence must be an endpoint")
        object.__setattr__(self, "chain", chain)
        object.__setattr__(self, "sampled_mean", mean)
        object.__setattr__(self, "sampled_rho", rho)
        object.__setattr__(self, "returned_type", returned_type)
        object.__setattr__(self, "error", error)


@dataclass(frozen=True)
class PriorControlResult:
    """Four prior-only point pairs or the exact retained failure prefix."""

    seed: DiagnosticSeedIdentity
    pairs: tuple[tuple[float, float], ...]
    failure: PriorControlFailure | None

    def __post_init__(self) -> None:
        if not isinstance(self.seed, DiagnosticSeedIdentity):
            raise ValueError("seed must be a DiagnosticSeedIdentity")
        seed = DiagnosticSeedIdentity(
            self.seed.case,
            self.seed.attempt_id,
            self.seed.purpose_id,
            self.seed.spawn_key,
        )
        if seed.purpose_id != 8:
            raise ValueError("control seed must have purpose 8")
        if not isinstance(self.pairs, tuple):
            raise ValueError("pairs must be an immutable tuple")
        pairs: list[tuple[float, float]] = []
        for index, pair in enumerate(self.pairs):
            if not isinstance(pair, tuple) or len(pair) != 2:
                raise ValueError("each control pair must be an immutable mean/rho tuple")
            pairs.append(
                (
                    _interior_probability(pair[0], f"pairs[{index}].mean"),
                    _interior_probability(pair[1], f"pairs[{index}].rho"),
                )
            )
        normalized_pairs = tuple(pairs)
        if self.failure is not None and not isinstance(self.failure, PriorControlFailure):
            raise ValueError("failure must be a PriorControlFailure or None")
        failure = (
            None
            if self.failure is None
            else PriorControlFailure(
                self.failure.chain,
                self.failure.parameter,
                self.failure.reason,
                self.failure.sampled_mean,
                self.failure.sampled_rho,
                self.failure.returned_type,
                self.failure.error,
            )
        )
        complete = len(normalized_pairs) == 4 and failure is None
        failed = (
            len(normalized_pairs) < 4
            and failure is not None
            and failure.chain == len(normalized_pairs)
        )
        if complete == failed:
            raise ValueError("control result must be exactly complete or prefix-failed")
        object.__setattr__(self, "seed", seed)
        object.__setattr__(self, "pairs", normalized_pairs)
        object.__setattr__(self, "failure", failure)

    @property
    def status(self) -> Literal["complete", "failed"]:
        """Return the exact structural outcome label."""
        return "complete" if self.failure is None else "failed"


def draw_prior_control(*, seed: DiagnosticSeedIdentity) -> PriorControlResult:
    """Draw four fixed-order prior-only pairs while retaining the exact failure prefix."""
    if not isinstance(seed, DiagnosticSeedIdentity):
        raise ValueError("seed must be a DiagnosticSeedIdentity")
    seed = DiagnosticSeedIdentity(seed.case, seed.attempt_id, seed.purpose_id, seed.spawn_key)
    if seed.purpose_id != 8:
        raise ValueError("control seed must have purpose8")
    rng = np.random.Generator(
        np.random.PCG64(np.random.SeedSequence(seed.entropy, spawn_key=seed.spawn_key))
    )
    pairs: list[tuple[float, float]] = []
    rho_beta = 9.0 if seed.case.track_id == 0 else 4.0
    for chain in range(4):
        mean = None
        for parameter, beta in (("mean", 1.0), ("rho", rho_beta)):
            try:
                raw = rng.beta(1.0, beta)
            except Exception as error:
                qualified = type(error).__module__ + "." + type(error).__qualname__
                failure = PriorControlFailure(
                    chain,
                    parameter,
                    "rng_exception",
                    mean,
                    None,
                    None,
                    DiagnosticCallError(qualified, str(error)),
                )
                return PriorControlResult(seed, tuple(pairs), failure)
            try:
                evidence = simulation_failure_scalar(raw, parameter)
            except ValueError:
                returned_type = type(raw).__module__ + "." + type(raw).__qualname__
                failure = PriorControlFailure(
                    chain,
                    parameter,
                    "invalid_scalar",
                    mean,
                    None,
                    returned_type,
                    None,
                )
                return PriorControlResult(seed, tuple(pairs), failure)
            candidate_mean = evidence if parameter == "mean" else mean
            candidate_rho = evidence if parameter == "rho" else None
            try:
                probability = simulation_probability(evidence, parameter)
            except ValueError:
                failure = PriorControlFailure(
                    chain,
                    parameter,
                    "invalid_scalar",
                    candidate_mean,
                    candidate_rho,
                    None,
                    None,
                )
                return PriorControlResult(seed, tuple(pairs), failure)
            if probability in (0.0, 1.0):
                failure = PriorControlFailure(
                    chain,
                    parameter,
                    "rounded_boundary",
                    candidate_mean,
                    candidate_rho,
                    None,
                    None,
                )
                return PriorControlResult(seed, tuple(pairs), failure)
            if parameter == "mean":
                mean = probability
            else:
                pairs.append((mean, probability))
    return PriorControlResult(seed, tuple(pairs), None)
