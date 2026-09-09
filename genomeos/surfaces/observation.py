"""Pure unseen-cohort observation parameter composition (design §§4–5, 7.1, 8, 12).

The contracts in this module reproduce fitted observation effects for offline posterior-
predictive scoring. They do not fit a model, sample replicated counts, or qualify a survey as
representative of present-day residents. Missing fitted effects and metadata are hard errors.
"""

from __future__ import annotations

from dataclasses import dataclass
from numbers import Integral, Real

import numpy as np
from scipy.special import expit

SEED = 42


def _validate_label_tuple(value: object, name: str, *, nonempty: bool = True) -> None:
    if not isinstance(value, tuple):
        raise ValueError(f"{name} must be a tuple")
    if nonempty and not value:
        raise ValueError(f"{name} must be nonempty")
    if any(not isinstance(label, str) or not label.strip() for label in value):
        raise ValueError(f"{name} must contain nonempty strings")


def _coordinate_tuple(value: object, name: str, lower: float, upper: float) -> tuple[float, ...]:
    if not isinstance(value, tuple):
        raise ValueError(f"{name} must be a tuple")
    if any(isinstance(item, (bool, np.bool_)) or not isinstance(item, Real) for item in value):
        raise ValueError(f"{name} must contain numeric values, not booleans")
    coordinates = tuple(float(item) for item in value)
    if any(not np.isfinite(item) for item in coordinates):
        raise ValueError(f"{name} must be finite")
    if any(item < lower or item > upper for item in coordinates):
        raise ValueError(f"{name} must be between {lower:g} and {upper:g}")
    return coordinates


def _float_array(value: object, name: str) -> np.ndarray:
    try:
        array = np.asarray(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be numeric") from error
    if not np.issubdtype(array.dtype, np.number) or np.issubdtype(
        array.dtype, np.complexfloating
    ):
        raise ValueError(f"{name} must be numeric")
    return array.astype(np.float64)


def _immutable_float64(array: np.ndarray) -> np.ndarray:
    """Copy onto a bytes-backed float64 buffer whose write flag cannot be re-enabled."""
    contiguous = np.ascontiguousarray(array, dtype=np.float64)
    return np.frombuffer(contiguous.tobytes(), dtype=np.float64).reshape(contiguous.shape)


def _validate_draw_ids(value: object, expected: int) -> tuple[tuple[int, int], ...]:
    if not isinstance(value, tuple):
        raise ValueError("draw_ids must be a tuple")
    if len(value) != expected:
        raise ValueError(f"draw_ids length must equal the {expected} posterior draws")
    normalized: list[tuple[int, int]] = []
    for pair in value:
        if not isinstance(pair, tuple) or len(pair) != 2:
            raise ValueError("draw_ids must contain (chain, draw) coordinate pairs")
        if any(
            isinstance(label, (bool, np.bool_)) or not isinstance(label, Integral)
            for label in pair
        ):
            raise ValueError("draw_ids must contain integer coordinates, not booleans")
        normalized.append((int(pair[0]), int(pair[1])))
    result = tuple(normalized)
    if len(set(result)) != len(result):
        raise ValueError("draw_ids must be unique")
    return result


@dataclass(frozen=True)
class SurveyQueries:
    """Explicit identities, designs, and WGS84 coordinates for unseen survey observations."""

    observation_ids: tuple[str, ...]
    cohort_ids: tuple[str, ...]
    sampling_designs: tuple[str, ...]
    lat: tuple[float, ...]
    lon: tuple[float, ...]

    def __post_init__(self) -> None:
        _validate_label_tuple(self.observation_ids, "observation_ids")
        _validate_label_tuple(self.cohort_ids, "cohort_ids")
        _validate_label_tuple(self.sampling_designs, "sampling_designs")
        lengths = {
            len(self.observation_ids),
            len(self.cohort_ids),
            len(self.sampling_designs),
            len(self.lat),
            len(self.lon),
        }
        if len(lengths) != 1:
            raise ValueError("SurveyQueries fields must have the same length")
        if len(set(self.observation_ids)) != len(self.observation_ids):
            raise ValueError("observation_ids must be unique")
        object.__setattr__(self, "lat", _coordinate_tuple(self.lat, "lat", -90.0, 90.0))
        object.__setattr__(self, "lon", _coordinate_tuple(self.lon, "lon", -180.0, 180.0))


@dataclass(frozen=True)
class ObservationModelMetadata:
    """Recorded fitted observation-model choices needed for fail-closed prediction."""

    convention: str
    fitted_designs: tuple[str, ...]
    training_cohort_ids: tuple[str, ...]
    cohort_effect_applied: bool
    nugget_applied: bool
    likelihood: str

    def __post_init__(self) -> None:
        if self.convention != "new_cohort_count_v1":
            raise ValueError("convention must be 'new_cohort_count_v1'")
        _validate_label_tuple(self.fitted_designs, "fitted_designs")
        if len(set(self.fitted_designs)) != len(self.fitted_designs):
            raise ValueError("fitted_designs must be unique")
        _validate_label_tuple(self.training_cohort_ids, "training_cohort_ids")
        if len(set(self.training_cohort_ids)) != len(self.training_cohort_ids):
            raise ValueError("training_cohort_ids must be unique")
        if self.training_cohort_ids != tuple(sorted(self.training_cohort_ids)):
            raise ValueError("training_cohort_ids must be sorted")
        if not isinstance(self.cohort_effect_applied, bool):
            raise ValueError("cohort_effect_applied must be a boolean")
        if not isinstance(self.nugget_applied, bool):
            raise ValueError("nugget_applied must be a boolean")
        if self.likelihood not in {"binomial", "beta_binomial"}:
            raise ValueError("likelihood must be 'binomial' or 'beta_binomial'")


@dataclass(frozen=True, eq=False)
class ObservationParameters:
    """Immutable draw-aligned conditional parameters for exact count scoring."""

    queries: SurveyQueries
    metadata: ObservationModelMetadata
    draw_ids: tuple[tuple[int, int], ...]
    mean_draws: np.ndarray
    concentration: np.ndarray | None

    def __post_init__(self) -> None:
        if not isinstance(self.queries, SurveyQueries):
            raise ValueError("queries must be SurveyQueries")
        if not isinstance(self.metadata, ObservationModelMetadata):
            raise ValueError("metadata must be ObservationModelMetadata")
        mean = _float_array(self.mean_draws, "mean_draws")
        if mean.ndim != 2:
            raise ValueError("mean_draws must be a two-dimensional (draws, observations) array")
        if mean.shape[0] == 0:
            raise ValueError("mean_draws must contain at least one draw")
        expected_shape = (mean.shape[0], len(self.queries.observation_ids))
        if mean.shape != expected_shape:
            raise ValueError(f"mean_draws must have shape {expected_shape}")
        if not np.all(np.isfinite(mean)):
            raise ValueError("mean_draws must be finite")
        if np.any((mean < 0.0) | (mean > 1.0)):
            raise ValueError("mean_draws must be between 0 and 1")
        object.__setattr__(self, "draw_ids", _validate_draw_ids(self.draw_ids, mean.shape[0]))
        object.__setattr__(self, "mean_draws", _immutable_float64(mean))

        if self.metadata.likelihood == "binomial":
            if self.concentration is not None:
                raise ValueError("concentration must be None for a binomial model")
            return
        if self.concentration is None:
            raise ValueError("concentration is required for a beta_binomial model")
        concentration = _float_array(self.concentration, "concentration")
        if concentration.shape != expected_shape:
            raise ValueError(f"concentration must have shape {expected_shape}")
        if not np.all(np.isfinite(concentration)):
            raise ValueError("concentration must be finite")
        if np.any(concentration <= 0.0):
            raise ValueError("concentration must be positive")
        object.__setattr__(self, "concentration", _immutable_float64(concentration))


def _scale_draws(
    value: np.ndarray | None, name: str, applied: bool, draws: int
) -> np.ndarray | None:
    if not applied:
        if value is not None:
            raise ValueError(f"{name} must be None when its fitted effect was omitted")
        return None
    if value is None:
        raise ValueError(f"{name} is required when its fitted effect was applied")
    array = _float_array(value, name)
    if array.shape != (draws,):
        raise ValueError(f"{name} must have shape ({draws},)")
    if not np.all(np.isfinite(array)):
        raise ValueError(f"{name} must be finite")
    if np.any(array < 0.0):
        raise ValueError(f"{name} must be nonnegative")
    return array


def compose_unseen_observations(
    latent_logit_draws: np.ndarray,
    *,
    draw_ids: tuple[tuple[int, int], ...],
    queries: SurveyQueries,
    metadata: ObservationModelMetadata,
    design_effect_draws: np.ndarray,
    cohort_sd_draws: np.ndarray | None,
    nugget_sd_draws: np.ndarray | None,
    concentration_draws: np.ndarray | None,
    seed: int = SEED,
) -> ObservationParameters:
    """Compose fitted design and new random effects onto draw-aligned latent logits."""
    if not isinstance(queries, SurveyQueries):
        raise ValueError("queries must be SurveyQueries")
    if not isinstance(metadata, ObservationModelMetadata):
        raise ValueError("metadata must be ObservationModelMetadata")
    if isinstance(seed, (bool, np.bool_)) or not isinstance(seed, Integral) or seed < 0:
        raise ValueError("seed must be a nonnegative integer, not a boolean")

    latent = _float_array(latent_logit_draws, "latent_logit_draws")
    observations = len(queries.observation_ids)
    if latent.ndim != 2 or latent.shape[1] != observations or latent.shape[0] == 0:
        raise ValueError(
            "latent_logit_draws must have shape (D, N) with positive D and query length N"
        )
    if not np.all(np.isfinite(latent)):
        raise ValueError("latent_logit_draws must be finite")
    draws = latent.shape[0]
    validated_draw_ids = _validate_draw_ids(draw_ids, draws)

    fitted_design_index = {label: index for index, label in enumerate(metadata.fitted_designs)}
    unknown_designs = sorted(set(queries.sampling_designs) - fitted_design_index.keys())
    if unknown_designs:
        raise ValueError(f"query sampling design was not fitted: {unknown_designs}")
    seen_cohorts = sorted(set(queries.cohort_ids) & set(metadata.training_cohort_ids))
    if seen_cohorts:
        raise ValueError(f"seen cohort IDs are not valid unseen-cohort queries: {seen_cohorts}")

    contrasts = _float_array(design_effect_draws, "design_effect_draws")
    expected_design_shape = (draws, len(metadata.fitted_designs) - 1)
    if contrasts.shape != expected_design_shape:
        raise ValueError(f"design_effect_draws must have shape {expected_design_shape}")
    if not np.all(np.isfinite(contrasts)):
        raise ValueError("design_effect_draws must be finite")
    cohort_sd = _scale_draws(
        cohort_sd_draws, "cohort_sd_draws", metadata.cohort_effect_applied, draws
    )
    nugget_sd = _scale_draws(
        nugget_sd_draws, "nugget_sd_draws", metadata.nugget_applied, draws
    )

    if metadata.likelihood == "binomial":
        if concentration_draws is not None:
            raise ValueError("concentration_draws must be None for a binomial model")
        concentration = None
    else:
        if concentration_draws is None:
            raise ValueError("concentration_draws is required for a beta_binomial model")
        scalar_concentration = _float_array(concentration_draws, "concentration_draws")
        if scalar_concentration.shape != (draws,):
            raise ValueError(f"concentration_draws must have shape ({draws},)")
        if not np.all(np.isfinite(scalar_concentration)):
            raise ValueError("concentration_draws must be finite")
        if np.any(scalar_concentration <= 0.0):
            raise ValueError("concentration_draws must be positive")
        concentration = np.broadcast_to(scalar_concentration[:, None], (draws, observations))

    full_design_effects = np.zeros((draws, len(metadata.fitted_designs)), dtype=np.float64)
    full_design_effects[:, 1:] = contrasts
    design_index = np.array(
        [fitted_design_index[label] for label in queries.sampling_designs], dtype=np.intp
    )
    logits = latent + full_design_effects[:, design_index]

    cohorts = tuple(sorted(set(queries.cohort_ids)))
    cohort_lookup = {value: index for index, value in enumerate(cohorts)}
    cohort_index = np.array([cohort_lookup[value] for value in queries.cohort_ids], dtype=np.intp)
    sorted_observations = tuple(sorted(queries.observation_ids))
    observation_lookup = {value: index for index, value in enumerate(sorted_observations)}
    observation_index = np.array(
        [observation_lookup[value] for value in queries.observation_ids], dtype=np.intp
    )
    cohort_seed, nugget_seed = np.random.SeedSequence(int(seed)).spawn(2)
    if cohort_sd is not None:
        cohort_z = np.random.default_rng(cohort_seed).normal(size=(draws, len(cohorts)))
        logits += cohort_sd[:, None] * cohort_z[:, cohort_index]
    if nugget_sd is not None:
        nugget_z = np.random.default_rng(nugget_seed).normal(size=(draws, observations))
        logits += nugget_sd[:, None] * nugget_z[:, observation_index]

    return ObservationParameters(
        queries=queries,
        metadata=metadata,
        draw_ids=validated_draw_ids,
        mean_draws=expit(logits),
        concentration=concentration,
    )
