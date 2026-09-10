"""Validated B0H generation contracts (design §§5, 7–8, 12; #211).

These immutable identities and results are shared by the independent synthetic
sampler and its constructor validation. Keeping their joint checks cohesive is
a documented exception to the preferred 500-line target; the module remains
below the repository's hard 800-line/50-KiB gate. It performs no I/O or fitting.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Integral
from typing import Literal, TypeAlias

import numpy as np

from genomeos.validation.reference_counts import ReferenceCount

SEED = 42
Entropy: TypeAlias = tuple[int, int, int, int, int, int, int, int, int]

_PROTOCOL = "b0h_sbc_v1"
_ALGORITHM = "b0h_generation_v1"
_MIXED_AN = (0, 1, 2, 5, 10, 20, 40, 64) * 2
_MEANS = (0.001, 0.05, 0.5)
_RHOS = (0.0, 0.0001, 0.1, 0.5)
_SHARED_MEANS = (0.01, 0.5)
_SHARED_RHOS = (0.1, 0.5)
_FLOAT_TYPES = (float, np.float16, np.float32, np.float64)
_STAGES = {
    "truth_mean",
    "truth_rho",
    "truth_validation",
    "beta_shapes",
    "training_cluster",
    "training_population",
    "training_switch",
    "training_count",
    "heldout_cluster",
    "heldout_population",
    "heldout_switch",
    "heldout_count",
}
_RNG_STAGES = _STAGES - {"truth_validation", "beta_shapes"}
_SERIALIZED_EXCEPTIONS = {"ValueError", "FloatingPointError", "OverflowError"}


def simulation_integer(value: object, name: str) -> int:
    """Normalize a non-Boolean Python or NumPy integer."""
    if not isinstance(name, str) or not name:
        raise ValueError("integer field name must be a nonempty string")
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Integral):
        raise ValueError(f"{name} must be an integer")
    return int(value)


def simulation_probability(value: object, name: str) -> float:
    """Normalize an exact endpoint integer or binary64-or-narrower float."""
    if not isinstance(name, str) or not name:
        raise ValueError("probability field name must be a nonempty string")
    if isinstance(value, (bool, np.bool_)):
        raise ValueError(f"{name} must be a binary64-or-narrower probability scalar")
    if isinstance(value, Integral):
        if int(value) not in (0, 1):
            raise ValueError(f"{name} must be in [0, 1]")
        return float(value)
    if type(value) not in _FLOAT_TYPES:
        raise ValueError(f"{name} must be a binary64-or-narrower probability scalar")
    normalized = float(value)
    if not math.isfinite(normalized) or not 0.0 <= normalized <= 1.0:
        raise ValueError(f"{name} must be finite and in [0, 1]")
    return normalized


def simulation_failure_scalar(value: object, name: str) -> float | int:
    """Retain supported numeric failure evidence, including nonfinite floats."""
    if not isinstance(name, str) or not name:
        raise ValueError("failure field name must be a nonempty string")
    if isinstance(value, (bool, np.bool_)):
        raise ValueError(f"{name} must be a non-Boolean numeric scalar")
    if isinstance(value, Integral):
        return int(value)
    if type(value) in _FLOAT_TYPES:
        return float(value)
    raise ValueError(f"{name} must be a binary64-or-narrower numeric scalar")


def _sequence(value: object, name: str) -> tuple[object, ...]:
    try:
        return tuple(value)  # type: ignore[arg-type]
    except TypeError as error:
        raise ValueError(f"{name} must be a sequence") from error


def _case_domain(study: int, case: int, replicate: int) -> None:
    bounds = {0: (1, 512), 1: (24, 16), 2: (4, 16), 3: (1, 1), 4: (2, 4)}
    if study not in bounds:
        raise ValueError("study_id must be between 0 and 4")
    cases, replicates = bounds[study]
    if not 0 <= case < cases or not 0 <= replicate < replicates:
        raise ValueError("case_id or replicate_id is outside the study domain")


def _set_fields(instance: object, values: tuple[tuple[str, object], ...]) -> None:
    for name, value in values:
        object.__setattr__(instance, name, value)


@dataclass(frozen=True)
class SbcCaseId:
    """One planned fit-track case in the frozen B0H generation manifest."""

    track_id: int
    study_id: int
    case_id: int
    replicate_id: int

    def __post_init__(self) -> None:
        values = tuple(
            simulation_integer(value, name)
            for name, value in (
                ("track_id", self.track_id),
                ("study_id", self.study_id),
                ("case_id", self.case_id),
                ("replicate_id", self.replicate_id),
            )
        )
        track, study, case, replicate = values
        if track not in (0, 1):
            raise ValueError("track_id must be 0 or 1")
        _case_domain(study, case, replicate)
        _set_fields(
            self, tuple(zip(("track_id", "study_id", "case_id", "replicate_id"), values, strict=True))
        )

    @property
    def canonical_id(self) -> str:
        return f"{_PROTOCOL}:s{self.study_id}:c{self.case_id}:r{self.replicate_id}:t{self.track_id}"


@dataclass(frozen=True)
class GenerationId:
    """Scientific-generation identity shared by paired stress-fit tracks."""

    track_id: int
    study_id: int
    case_id: int
    replicate_id: int

    def __post_init__(self) -> None:
        values = tuple(
            simulation_integer(value, name)
            for name, value in (
                ("track_id", self.track_id),
                ("study_id", self.study_id),
                ("case_id", self.case_id),
                ("replicate_id", self.replicate_id),
            )
        )
        track, study, case, replicate = values
        if track not in ((0, 1) if study == 0 else (99,)):
            raise ValueError("generation track does not match study")
        _case_domain(study, case, replicate)
        _set_fields(
            self, tuple(zip(("track_id", "study_id", "case_id", "replicate_id"), values, strict=True))
        )

    @property
    def canonical_id(self) -> str:
        return f"{_PROTOCOL}:s{self.study_id}:c{self.case_id}:r{self.replicate_id}:g{self.track_id}"


@dataclass(frozen=True)
class SeedIdentity:
    """One exact generation or fitting seed namespace."""

    entropy: Entropy

    def __post_init__(self) -> None:
        values = _sequence(self.entropy, "entropy")
        if len(values) != 9:
            raise ValueError("entropy must contain exactly nine integers")
        entropy = tuple(simulation_integer(value, "entropy component") for value in values)
        seed, issue, version, track, study, case, replicate, purpose, attempt = entropy
        if (seed, issue, version) != (42, 211, 1):
            raise ValueError("entropy prefix must be (42, 211, 1)")
        _case_domain(study, case, replicate)
        if purpose in range(4):
            valid_track = track in (0, 1) if study == 0 else track == 99
            if attempt != 0 or not valid_track:
                raise ValueError("generation entropy has an invalid track or attempt")
        elif purpose == 4:
            if track not in (0, 1) or attempt not in (0, 1) or study == 3:
                raise ValueError("fitting entropy has an invalid track, attempt, or study")
        else:
            raise ValueError("purpose_id is not exposed by the generation component")
        object.__setattr__(self, "entropy", entropy)

    @property
    def fit_uint32(self) -> int | None:
        if self.entropy[7] != 4:
            return None
        return int(np.random.SeedSequence(self.entropy).generate_state(1, dtype=np.uint32)[0])


@dataclass(frozen=True)
class ParameterTruth:
    """Known mean and intra-population correlation for one generated dataset."""

    mean: float
    rho: float

    def __post_init__(self) -> None:
        mean = simulation_probability(self.mean, "mean")
        rho = simulation_probability(self.rho, "rho")
        if rho >= 1.0 or (mean in (0.0, 1.0) and rho != 0.0):
            raise ValueError("rho must be in [0, 1), with endpoint means only at rho zero")
        _set_fields(self, (("mean", mean), ("rho", rho)))


def generation_id(case: SbcCaseId) -> GenerationId:
    """Map a fit case to its track-specific or shared scientific generation."""
    if not isinstance(case, SbcCaseId):
        raise ValueError("case must be an SbcCaseId")
    normalized = SbcCaseId(**vars(case))
    track = normalized.track_id if normalized.study_id == 0 else 99
    return GenerationId(track, normalized.study_id, normalized.case_id, normalized.replicate_id)


def sbc_seed_identity(case: SbcCaseId, *, purpose_id: int, attempt_id: int) -> SeedIdentity:
    """Return one validated generation or fit namespace for a planned case."""
    if not isinstance(case, SbcCaseId):
        raise ValueError("case must be an SbcCaseId")
    normalized = SbcCaseId(**vars(case))
    purpose = simulation_integer(purpose_id, "purpose_id")
    attempt = simulation_integer(attempt_id, "attempt_id")
    track = normalized.track_id if purpose == 4 else generation_id(normalized).track_id
    return SeedIdentity(
        (
            SEED,
            211,
            1,
            track,
            normalized.study_id,
            normalized.case_id,
            normalized.replicate_id,
            purpose,
            attempt,
        )
    )


@dataclass(frozen=True)
class GenerationProvenance:
    """Fixed algorithm labels and all four planned generation namespaces."""

    generation_id: GenerationId
    seeds: tuple[SeedIdentity, SeedIdentity, SeedIdentity, SeedIdentity]

    def __post_init__(self) -> None:
        if not isinstance(self.generation_id, GenerationId):
            raise ValueError("generation_id must be a GenerationId")
        generation = GenerationId(**vars(self.generation_id))
        seeds = _sequence(self.seeds, "seeds")
        if len(seeds) != 4 or any(not isinstance(seed, SeedIdentity) for seed in seeds):
            raise ValueError("seeds must contain four SeedIdentity values")
        expected = tuple(
            SeedIdentity(
                (
                    SEED,
                    211,
                    1,
                    generation.track_id,
                    generation.study_id,
                    generation.case_id,
                    generation.replicate_id,
                    purpose,
                    0,
                )
            )
            for purpose in range(4)
        )
        normalized = tuple(SeedIdentity(seed.entropy) for seed in seeds)  # type: ignore[union-attr]
        if normalized != expected:
            raise ValueError("planned seeds do not match generation_id")
        _set_fields(self, (("generation_id", generation), ("seeds", normalized)))

    protocol_id = property(lambda self: _PROTOCOL)
    algorithm_id = property(lambda self: _ALGORITHM)
    bit_generator = property(lambda self: "PCG64")
    floating_dtype = property(lambda self: "float64")


def _normalized_case(case: object) -> SbcCaseId:
    if not isinstance(case, SbcCaseId):
        raise ValueError("case must be an SbcCaseId")
    return SbcCaseId(**vars(case))


def fixed_simulation_truth(case: SbcCaseId) -> ParameterTruth | None:
    """Decode literal truth for fixed studies; prior and unavailable return None."""
    case = _normalized_case(case)
    if case.study_id == 1:
        mean_index, rest = divmod(case.case_id, 8)
        rho_index, _ = divmod(rest, 2)
        return ParameterTruth(_MEANS[mean_index], _RHOS[rho_index])
    if case.study_id == 2:
        mean_index, rho_index = divmod(case.case_id, 2)
        return ParameterTruth(_SHARED_MEANS[mean_index], _SHARED_RHOS[rho_index])
    if case.study_id == 4:
        return ParameterTruth(float(case.case_id), 0.0)
    return None


def simulation_training_an(case: SbcCaseId) -> tuple[int, ...]:
    """Return the literal sixteen-row denominator design for a planned case."""
    case = _normalized_case(case)
    if case.study_id in (0, 2):
        return _MIXED_AN
    if case.study_id == 1:
        return _MIXED_AN if case.case_id % 2 == 0 else (20,) * 16
    if case.study_id == 3:
        return (0,) * 16
    return (20,) * 16


def simulation_reference_count(
    generation: GenerationId, where: str, key: str, ac: int, an: int
) -> ReferenceCount:
    """Build one exact synthetic nonspatial count label after domain validation."""
    if not isinstance(generation, GenerationId):
        raise ValueError("generation must be a GenerationId")
    generation = GenerationId(**vars(generation))
    case = SbcCaseId(
        generation.track_id if generation.study_id == 0 else 0,
        generation.study_id,
        generation.case_id,
        generation.replicate_id,
    )
    if type(where) is not str or type(key) is not str:
        raise ValueError("where and key must be literal strings")
    if where == "train":
        if not isinstance(key, str) or key not in tuple(str(i) for i in range(16)):
            raise ValueError("training key must be a decimal row index from 0 through 15")
        expected_an = simulation_training_an(case)[int(key)]
    elif where == "heldout":
        kinds = (
            ()
            if case.study_id == 3
            else ("shared_cluster0", "fresh_cluster")
            if case.study_id == 2
            else ("fresh_population",)
        )
        if key not in kinds:
            raise ValueError("heldout key is invalid")
        expected_an = 20
    else:
        raise ValueError("where must be train or heldout")
    normalized_an = simulation_integer(an, "an")
    if normalized_an != expected_an:
        raise ValueError("an does not match the declared synthetic row")
    canonical = generation.canonical_id
    return ReferenceCount(
        f"synthetic:{canonical}:{where}:row:{key}",
        f"synthetic:{canonical}:variant:0",
        f"synthetic:{canonical}:{where}:group:{key}",
        "synthetic_nonspatial",
        "synthetic_single_variant",
        ac,
        normalized_an,
    )


@dataclass(frozen=True)
class SharedHistory:
    """Raw cluster and candidate draws for the shared-history misspecification."""

    cluster_frequencies: tuple[float, float]
    candidate_frequencies: tuple[float, ...]
    uses_cluster: tuple[bool, ...]

    def __post_init__(self) -> None:
        clusters = tuple(
            simulation_probability(value, "cluster_frequency")
            for value in _sequence(self.cluster_frequencies, "cluster_frequencies")
        )
        candidates = tuple(
            simulation_probability(value, "candidate_frequency")
            for value in _sequence(self.candidate_frequencies, "candidate_frequencies")
        )
        switches = _sequence(self.uses_cluster, "uses_cluster")
        if len(clusters) != 2 or len(candidates) != 16 or len(switches) != 16:
            raise ValueError("shared history shapes must be 2, 16, and 16")
        if any(type(value) is not bool for value in switches):
            raise ValueError("uses_cluster must contain Boolean values")
        _set_fields(
            self,
            (
                ("cluster_frequencies", clusters),
                ("candidate_frequencies", candidates),
                ("uses_cluster", switches),
            ),
        )


@dataclass(frozen=True)
class HeldoutTarget:
    """One disjoint ordinary or shared-history heldout count."""

    kind: Literal["fresh_population", "shared_cluster0", "fresh_cluster"]
    row: ReferenceCount
    latent_frequency: float
    cluster_id: int | None
    cluster_frequency: float | None
    candidate_frequency: float | None
    uses_cluster: bool | None

    def __post_init__(self) -> None:
        if self.kind not in ("fresh_population", "shared_cluster0", "fresh_cluster"):
            raise ValueError("heldout kind is invalid")
        if not isinstance(self.row, ReferenceCount):
            raise ValueError("heldout row must be a ReferenceCount")
        q = simulation_probability(self.latent_frequency, "latent_frequency")
        metadata = (self.cluster_id, self.cluster_frequency, self.candidate_frequency, self.uses_cluster)
        if self.kind == "fresh_population":
            if any(value is not None for value in metadata):
                raise ValueError("ordinary heldout cannot carry cluster metadata")
        else:
            cluster_id = simulation_integer(self.cluster_id, "cluster_id")
            expected_id = 0 if self.kind == "shared_cluster0" else 2
            if cluster_id != expected_id or type(self.uses_cluster) is not bool:
                raise ValueError("heldout cluster metadata is invalid")
            cluster = simulation_probability(self.cluster_frequency, "cluster_frequency")
            candidate = simulation_probability(self.candidate_frequency, "candidate_frequency")
            if q != (cluster if self.uses_cluster else candidate):
                raise ValueError("heldout latent frequency does not match its selected source")
            _set_fields(
                self,
                (
                    ("cluster_id", cluster_id),
                    ("cluster_frequency", cluster),
                    ("candidate_frequency", candidate),
                ),
            )
        object.__setattr__(self, "latent_frequency", q)


def _case_provenance(case: object, provenance: object) -> tuple[SbcCaseId, GenerationProvenance]:
    case = _normalized_case(case)
    if not isinstance(provenance, GenerationProvenance):
        raise ValueError("provenance must be a GenerationProvenance")
    provenance = GenerationProvenance(provenance.generation_id, provenance.seeds)
    if provenance.generation_id != generation_id(case):
        raise ValueError("provenance does not match case_id")
    return case, provenance


def _training_rows(
    case: SbcCaseId, provenance: GenerationProvenance, rows: object
) -> tuple[ReferenceCount, ...]:
    rows = _sequence(rows, "training")
    ans = simulation_training_an(case)
    if len(rows) != 16 or any(not isinstance(row, ReferenceCount) for row in rows):
        raise ValueError("training must contain sixteen ReferenceCount rows")
    for index, (row, an) in enumerate(zip(rows, ans, strict=True)):
        expected = simulation_reference_count(
            provenance.generation_id,
            "train",
            str(index),
            row.ac,
            an,  # type: ignore[union-attr]
        )
        if row != expected:
            raise ValueError("training row labels or denominators do not match the case")
    return rows  # type: ignore[return-value]


@dataclass(frozen=True)
class GeneratedDataset:
    """One complete available synthetic training and heldout realization."""

    case_id: SbcCaseId
    provenance: GenerationProvenance
    truth: ParameterTruth
    training: tuple[ReferenceCount, ...]
    latent_frequencies: tuple[float, ...]
    shared_history: SharedHistory | None
    heldouts: tuple[HeldoutTarget, ...]
    beta_zero_draws: int
    beta_one_draws: int

    def __post_init__(self) -> None:
        case, provenance = _case_provenance(self.case_id, self.provenance)
        if case.study_id == 3 or not isinstance(self.truth, ParameterTruth):
            raise ValueError("available dataset requires valid truth and an eligible study")
        truth = ParameterTruth(self.truth.mean, self.truth.rho)
        expected_truth = fixed_simulation_truth(case)
        if expected_truth is not None and truth != expected_truth:
            raise ValueError("truth does not match the fixed case")
        if case.study_id == 0 and not (0.0 < truth.mean < 1.0 and 0.0 < truth.rho < 1.0):
            raise ValueError("prior truth must be strictly interior")
        training = _training_rows(case, provenance, self.training)
        latents = tuple(
            simulation_probability(value, "latent_frequency")
            for value in _sequence(self.latent_frequencies, "latent_frequencies")
        )
        if len(latents) != 16:
            raise ValueError("latent_frequencies must contain sixteen values")
        heldouts_raw = _sequence(self.heldouts, "heldouts")
        if any(not isinstance(target, HeldoutTarget) for target in heldouts_raw):
            raise ValueError("heldouts must contain HeldoutTarget values")
        heldouts = tuple(HeldoutTarget(**vars(target)) for target in heldouts_raw)  # type: ignore[arg-type]
        kinds = ("shared_cluster0", "fresh_cluster") if case.study_id == 2 else ("fresh_population",)
        if tuple(target.kind for target in heldouts) != kinds:
            raise ValueError("heldout kinds do not match the study")
        for target in heldouts:
            expected = simulation_reference_count(
                provenance.generation_id, "heldout", target.kind, target.row.ac, 20
            )
            if target.row != expected:
                raise ValueError("heldout labels or denominator do not match the case")
        if case.study_id == 2:
            if not isinstance(self.shared_history, SharedHistory):
                raise ValueError("shared study requires shared history")
            history = SharedHistory(**vars(self.shared_history))
            selected = tuple(
                history.cluster_frequencies[index // 8] if use else candidate
                for index, (candidate, use) in enumerate(
                    zip(history.candidate_frequencies, history.uses_cluster, strict=True)
                )
            )
            if latents != selected or heldouts[0].cluster_frequency != history.cluster_frequencies[0]:
                raise ValueError("shared latent frequencies or B0 reuse are inconsistent")
            raw_beta = (
                *history.cluster_frequencies,
                *history.candidate_frequencies,
                heldouts[0].candidate_frequency,
                heldouts[1].cluster_frequency,
                heldouts[1].candidate_frequency,
            )
        else:
            if self.shared_history is not None:
                raise ValueError("ordinary study cannot carry shared history")
            history = None
            raw_beta = (*latents, heldouts[0].latent_frequency) if truth.rho > 0.0 else ()
            if truth.rho == 0.0 and (
                latents != (truth.mean,) * 16 or heldouts[0].latent_frequency != truth.mean
            ):
                raise ValueError("rho-zero latent frequencies must equal the fixed mean")
        zero = simulation_integer(self.beta_zero_draws, "beta_zero_draws")
        one = simulation_integer(self.beta_one_draws, "beta_one_draws")
        if zero < 0 or one < 0 or (zero, one) != (raw_beta.count(0.0), raw_beta.count(1.0)):
            raise ValueError("Beta endpoint counters do not match retained raw draws")
        if truth.mean in (0.0, 1.0):
            expected_counts = tuple(0 if truth.mean == 0.0 else row.an for row in training)
            if tuple(row.ac for row in training) != expected_counts or heldouts[0].row.ac != int(
                20 * truth.mean
            ):
                raise ValueError("boundary counts must equal their deterministic outcomes")
        _set_fields(
            self,
            (
                ("case_id", case),
                ("provenance", provenance),
                ("truth", truth),
                ("training", training),
                ("latent_frequencies", latents),
                ("shared_history", history),
                ("heldouts", heldouts),
                ("beta_zero_draws", zero),
                ("beta_one_draws", one),
            ),
        )

    status = property(lambda self: "available")


@dataclass(frozen=True)
class AllUnavailableDataset:
    """Structural fixture retaining sixteen explicit AN=0 rows and no truth."""

    case_id: SbcCaseId
    provenance: GenerationProvenance
    training: tuple[ReferenceCount, ...]

    def __post_init__(self) -> None:
        case, provenance = _case_provenance(self.case_id, self.provenance)
        if case.study_id != 3:
            raise ValueError("all-unavailable result is restricted to study 3")
        rows = _training_rows(case, provenance, self.training)
        if any(row.ac != 0 or row.an != 0 for row in rows):
            raise ValueError("all-unavailable rows must have AC=AN=0")
        _set_fields(self, (("case_id", case), ("provenance", provenance), ("training", rows)))

    status = property(lambda self: "all_unavailable")
    truth = property(lambda self: None)
    latent_frequencies = property(lambda self: None)
    shared_history = property(lambda self: None)
    heldouts = property(lambda self: ())
    expected_sampler_calls = property(lambda self: 0)
    refusal_reason = property(lambda self: "no_available_training_counts")


@dataclass(frozen=True)
class GenerationFailure:
    """Typed refusal for one failed scalar generation step, with no partial rows."""

    case_id: SbcCaseId
    provenance: GenerationProvenance
    stage: str
    index: int | None
    reason: str
    truth: ParameterTruth | None
    sampled_mean: float | int | None
    sampled_rho: float | int | None
    offending_value: float | int | None
    exception_type: str | None
    exception_message: str | None

    def __post_init__(self) -> None:
        case, provenance = _case_provenance(self.case_id, self.provenance)
        if type(self.stage) is not str or self.stage not in _STAGES or case.study_id == 3:
            raise ValueError("generation failure stage or study is invalid")
        if type(self.reason) is not str:
            raise ValueError("generation failure reason must be a literal string")
        allowed_reason = (
            {"rounded_prior_boundary"}
            if self.stage == "truth_validation"
            else {"invalid_beta_shapes"}
            if self.stage == "beta_shapes"
            else {"rng_exception", "invalid_rng_scalar"}
        )
        if self.reason not in allowed_reason:
            raise ValueError("generation failure reason does not match its stage")
        if self.truth is not None and not isinstance(self.truth, ParameterTruth):
            raise ValueError("failure truth must be a ParameterTruth or None")
        truth = None if self.truth is None else ParameterTruth(self.truth.mean, self.truth.rho)
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
        truth_stage = self.stage in {"truth_mean", "truth_rho", "truth_validation"}
        if truth_stage:
            if case.study_id != 0 or truth is not None:
                raise ValueError("truth-draw failures require unvalidated prior truth")
        elif truth is None:
            raise ValueError("post-validation failures require validated truth")
        if case.study_id == 0 and truth is not None:
            if not 0.0 < truth.mean < 1.0 or not 0.0 < truth.rho < 1.0:
                raise ValueError("validated prior failure truth must be strictly interior")
            if mean is None or rho is None:
                raise ValueError("validated prior failure must retain both candidates")
            valid_mean = simulation_probability(mean, "sampled_mean")
            valid_rho = simulation_probability(rho, "sampled_rho")
            if (valid_mean, valid_rho) != (truth.mean, truth.rho):
                raise ValueError("validated prior truth must match sampled candidates")
        elif case.study_id != 0 and (
            mean is not None or rho is not None or truth != fixed_simulation_truth(case)
        ):
            raise ValueError("fixed failure must carry its known truth and no prior candidates")
        self._validate_prior_candidates(mean, rho)
        index = self._validate_operation(case, truth)
        offending = (
            None
            if self.offending_value is None
            else simulation_failure_scalar(self.offending_value, "offending_value")
        )
        paired_exception = (self.exception_type is None) == (self.exception_message is None)
        if (
            not paired_exception
            or self.exception_type is not None
            and (
                type(self.exception_type) is not str
                or type(self.exception_message) is not str
                or self.exception_type not in _SERIALIZED_EXCEPTIONS
            )
        ):
            raise ValueError("exception metadata must be paired permitted strings")
        if self.reason == "rng_exception":
            if self.exception_type is None or offending is not None:
                raise ValueError("rng_exception requires only exception evidence")
            if self.stage == "truth_mean" and mean is not None:
                raise ValueError("throwing truth_mean calls return no candidate")
            if self.stage == "truth_rho" and rho is not None:
                raise ValueError("throwing truth_rho calls return no candidate")
        elif self.reason == "invalid_beta_shapes":
            if (self.exception_type is None) == (offending is None):
                raise ValueError("shape failure requires exactly one evidence form")
            if offending is not None and (
                offending > 0 and (not isinstance(offending, float) or math.isfinite(offending))
            ):
                raise ValueError("shape scalar evidence must be nonpositive or nonfinite")
        elif self.exception_type is not None:
            raise ValueError("scalar and boundary failures cannot carry exception metadata")
        if self.reason == "invalid_rng_scalar":
            candidate = mean if self.stage == "truth_mean" else rho if self.stage == "truth_rho" else None
            if self.stage in {"truth_mean", "truth_rho"} and (
                (candidate is None) != (offending is None)
                or candidate is not None
                and not self._same_scalar(candidate, offending)
            ):
                raise ValueError("invalid prior candidate must match offending evidence")
        if self.reason == "rounded_prior_boundary":
            expected = mean if mean in (0.0, 1.0) else rho
            if offending is None or not self._same_scalar(expected, offending):
                raise ValueError("boundary evidence must identify the first endpoint candidate")
        _set_fields(
            self,
            (
                ("case_id", case),
                ("provenance", provenance),
                ("index", index),
                ("truth", truth),
                ("sampled_mean", mean),
                ("sampled_rho", rho),
                ("offending_value", offending),
            ),
        )

    def _validate_prior_candidates(
        self, mean: float | int | None, rho: float | int | None
    ) -> None:
        if self.stage == "truth_mean":
            if rho is not None:
                raise ValueError("truth_mean failure cannot retain rho")
            if self.reason == "invalid_rng_scalar" and mean is not None:
                try:
                    simulation_probability(mean, "sampled_mean")
                except ValueError:
                    pass
                else:
                    raise ValueError("invalid truth_mean candidate must be outside its domain")
        elif self.stage == "truth_rho":
            if mean is None:
                raise ValueError("truth_rho failure must retain mean")
            simulation_probability(mean, "sampled_mean")
            if self.reason == "invalid_rng_scalar" and rho is not None:
                try:
                    simulation_probability(rho, "sampled_rho")
                except ValueError:
                    pass
                else:
                    raise ValueError("invalid truth_rho candidate must be outside its domain")
        elif self.stage == "truth_validation":
            if mean is None or rho is None:
                raise ValueError("truth_validation failure must retain both candidates")
            valid_mean = simulation_probability(mean, "sampled_mean")
            valid_rho = simulation_probability(rho, "sampled_rho")
            if valid_mean not in (0.0, 1.0) and valid_rho not in (0.0, 1.0):
                raise ValueError("rounded prior boundary requires an endpoint candidate")

    def _validate_operation(self, case: SbcCaseId, truth: ParameterTruth | None) -> int | None:
        if self.stage in {"truth_mean", "truth_rho", "truth_validation"}:
            allowed: tuple[int, ...] | None = None
        elif self.stage == "beta_shapes":
            allowed = None if truth is not None and truth.rho > 0.0 else ()
        elif self.stage == "training_cluster":
            allowed = (0, 1) if case.study_id == 2 else ()
        elif self.stage == "training_population":
            allowed = tuple(range(16)) if truth is not None and truth.rho > 0.0 else ()
        elif self.stage == "training_switch":
            allowed = tuple(range(16)) if case.study_id == 2 else ()
        elif self.stage == "training_count":
            allowed = tuple(range(16))
        elif self.stage == "heldout_cluster":
            allowed = (1,) if case.study_id == 2 else ()
        elif self.stage == "heldout_population":
            allowed = (
                ((0, 1) if case.study_id == 2 else (0,))
                if truth is not None and truth.rho > 0.0
                else ()
            )
        elif self.stage == "heldout_switch":
            allowed = (0, 1) if case.study_id == 2 else ()
        else:
            allowed = (0, 1) if case.study_id == 2 else (0,)
        if allowed is None:
            if self.index is not None:
                raise ValueError("truth and shape failure indices must be None")
            return None
        index = simulation_integer(self.index, "index")
        if index not in allowed:
            raise ValueError("failure index is outside its case and stage domain")
        return index

    @staticmethod
    def _same_scalar(left: float | int | None, right: float | int | None) -> bool:
        if type(left) is not type(right):
            return False
        return bool(left == right or isinstance(left, float) and math.isnan(left) and math.isnan(right))

    status = property(lambda self: "generation_failed")


GenerationResult: TypeAlias = GeneratedDataset | AllUnavailableDataset | GenerationFailure


def enumerate_sbc_cases() -> tuple[SbcCaseId, ...]:
    """Return the exact sorted 1,938-record calibration manifest."""
    bounds = ((1, 512), (24, 16), (4, 16), (1, 1), (2, 4))
    return tuple(
        SbcCaseId(track, study, case, replicate)
        for study, (cases, replicates) in enumerate(bounds)
        for case in range(cases)
        for replicate in range(replicates)
        for track in range(2)
    )
