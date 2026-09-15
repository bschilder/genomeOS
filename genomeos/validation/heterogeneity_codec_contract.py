"""Closed B0H v1 records (design §§5,7–8,12; codec §§2,4,6).

Explicit field checks and public constructors; no inference, I/O or RNG draws.
The tuple helpers check this fixed record set, not a general type language.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass, fields
from typing import TypeAlias

import numpy as np

from genomeos.surfaces.heterogeneity_types import (
    PopulationHeterogeneityConfig,
    PopulationHeterogeneityFit,
    ReferenceHeterogeneityPrediction,
    VariantHeterogeneityDiagnostics,
    VariantTrainingCounts,
)
from genomeos.validation.heterogeneity_attempts import (
    AttemptError,
    FitAttemptResult,
    FitAttemptSpec,
    StructuralCheckResult,
)
from genomeos.validation.heterogeneity_codec_wire import ArrayReference, B0HCodecError
from genomeos.validation.heterogeneity_dependence import (
    DependenceComparisons,
    DependencePointReference,
    HeterogeneityDependenceReference,
)
from genomeos.validation.heterogeneity_diagnostic_seeds import DiagnosticSeedIdentity
from genomeos.validation.heterogeneity_sbc_controls import (
    DiagnosticCallError,
    PriorControlFailure,
    PriorControlResult,
)
from genomeos.validation.heterogeneity_sbc_quantity_types import (
    QuantityRankEvidence,
    ScalarQuantityEvidence,
    SelectedSbcQuantities,
)
from genomeos.validation.heterogeneity_simulation_types import (
    AllUnavailableDataset,
    GeneratedDataset,
    GenerationFailure,
    GenerationId,
    GenerationProvenance,
    HeldoutTarget,
    ParameterTruth,
    SbcCaseId,
    SeedIdentity,
    SharedHistory,
)
from genomeos.validation.heterogeneity_summary_types import (
    HeldoutPredictiveSummary,
    HeterogeneityFitSummary,
    ParameterPosteriorSummary,
    PredictiveSummaryEvidence,
)
from genomeos.validation.predictive import CountPredictive
from genomeos.validation.reference_counts import ReferenceCount

B0HEvidence: TypeAlias = (
    GeneratedDataset
    | AllUnavailableDataset
    | GenerationFailure
    | FitAttemptResult
    | StructuralCheckResult
    | SelectedSbcQuantities
    | HeterogeneityFitSummary
)
ROOT_TYPES = (
    GeneratedDataset,
    AllUnavailableDataset,
    GenerationFailure,
    FitAttemptResult,
    StructuralCheckResult,
    SelectedSbcQuantities,
    HeterogeneityFitSummary,
)

# Literal frozen constructor fields. No runtime field discovery populates this map.
_RECORDS = (
    (SbcCaseId, "track_id study_id case_id replicate_id"),
    (GenerationId, "track_id study_id case_id replicate_id"),
    (SeedIdentity, "entropy"),
    (ParameterTruth, "mean rho"),
    (GenerationProvenance, "generation_id seeds"),
    (SharedHistory, "cluster_frequencies candidate_frequencies uses_cluster"),
    (
        HeldoutTarget,
        "kind row latent_frequency cluster_id cluster_frequency candidate_frequency uses_cluster",
    ),
    (
        GeneratedDataset,
        "case_id provenance truth training latent_frequencies "
        "shared_history heldouts beta_zero_draws beta_one_draws",
    ),
    (AllUnavailableDataset, "case_id provenance training"),
    (
        GenerationFailure,
        "case_id provenance stage index reason truth sampled_mean "
        "sampled_rho offending_value exception_type exception_message",
    ),
    (ReferenceCount, "record_id variant_id group_id region_id variant_group ac an"),
    (FitAttemptSpec, "case attempt_id seed config"),
    (AttemptError, "category exception_class message reason diagnostics divergence_count"),
    (FitAttemptResult, "spec status fit error identity_mismatches returned_type"),
    (StructuralCheckResult, "case status error fit returned_type"),
    (
        PopulationHeterogeneityConfig,
        "mean_prior_alpha mean_prior_beta rho_prior_alpha "
        "rho_prior_beta draws tune chains target_accept seed",
    ),
    (VariantTrainingCounts, "variant_id training_observation_count training_ac training_an"),
    (VariantHeterogeneityDiagnostics, "variant_id max_rhat min_bulk_ess min_tail_ess"),
    (
        PopulationHeterogeneityFit,
        "config variant_ids mean_draws rho_draws training_record_ids "
        "training_group_ids unavailable_training_ids training_counts diagnostics divergence_count",
    ),
    (ReferenceHeterogeneityPrediction, "marginal_predictive observation_ids unavailable_ids"),
    (CountPredictive, "mean_draws concentration cdf_backend"),
    (DiagnosticSeedIdentity, "case attempt_id purpose_id spawn_key"),
    (DiagnosticCallError, "exception_class message"),
    (PriorControlFailure, "chain parameter reason sampled_mean sampled_rho returned_type error"),
    (PriorControlResult, "seed pairs failure"),
    (DependencePointReference, "mean rho components raw_values value error_bound resolved"),
    (HeterogeneityDependenceReference, "orders analytic_separability points"),
    (DependenceComparisons, "status comparisons_by_order comparisons"),
    (ScalarQuantityEvidence, "quantity_id values error failed_training_row"),
    (QuantityRankEvidence, "mode_id quantity_id seed status rank comparisons error"),
    (
        SelectedSbcQuantities,
        "spec selected_indices selection_seeds control point_slots "
        "points scalar_quantities reference reference_error ranks",
    ),
    (ParameterPosteriorSummary, "parameter truth estimate quantiles draw_count"),
    (
        HeldoutPredictiveSummary,
        "target log_score absolute_error squared_error coverage interval_width randomized_pit",
    ),
    (
        PredictiveSummaryEvidence,
        "seed seed_words seed_uint128 cdf_backend draw_count targets status prediction rows error",
    ),
    (HeterogeneityFitSummary, "spec variant_id parameters predictive"),
)


@dataclass(frozen=True)
class RecordNode:
    tag: str
    fields: dict[str, object]


def _definition(tag: str) -> tuple[type, tuple[str, ...]]:
    if type(tag) is str:
        for cls, names in _RECORDS:
            if tag == cls.__name__:
                return cls, tuple(names.split())
    raise B0HCodecError("unknown record tag")


def check_contract_drift() -> None:
    for cls, names in _RECORDS:
        expected = set(names.split())
        actual = {field.name for field in fields(cls) if field.init}
        signature = inspect.signature(cls)
        if actual != expected or set(signature.parameters) != expected:
            raise B0HCodecError(f"{cls.__name__}: constructor field drift")


def _integer(value: object) -> int:
    if type(value) is int or type(value) in (
        np.int8,
        np.int16,
        np.int32,
        np.int64,
        np.uint8,
        np.uint16,
        np.uint32,
        np.uint64,
        np.longlong,
        np.ulonglong,
    ):
        return int(value)
    raise B0HCodecError("expected a non-Boolean integer")


def _float(value: object) -> float:
    if type(value) not in (float, np.float16, np.float32, np.float64):
        raise B0HCodecError("expected a binary64-or-narrower floating scalar")
    return float(value)


def _numeric(value: object) -> float | int:
    return _float(value) if type(value) in (float, np.float16, np.float32, np.float64) else _integer(value)


def _string(value: object) -> str:
    if type(value) is not str:
        raise B0HCodecError("expected a literal string")
    return value


def _boolean(value: object) -> bool:
    if type(value) is not bool:
        raise B0HCodecError("expected a literal Boolean")
    return value


def _coverage(value: object) -> bool:
    if type(value) not in (bool, np.bool_):
        raise B0HCodecError("expected a Boolean coverage scalar")
    return bool(value)


def _tuple(value: object, check: Callable[[object], object], length: int | None = None) -> tuple:
    if type(value) is not tuple or length is not None and len(value) != length:
        raise B0HCodecError("expected an immutable tuple with the declared arity")
    return tuple(check(item) for item in value)


def _optional(value: object, check: Callable[[object], object]) -> object:
    return None if value is None else check(value)


def _record(value: object, cls: type) -> object:
    if type(value) is cls or type(value) is RecordNode and value.tag == cls.__name__:
        return value
    raise B0HCodecError(f"expected exact {cls.__name__} record")


def _array(value: object) -> object:
    if type(value) is ArrayReference:
        return value
    if (
        type(value) is np.ndarray
        and value.dtype == np.dtype(np.float64)
        and not value.flags.writeable
        and value.ndim
        and 0 not in value.shape
    ):
        return value
    raise B0HCodecError("expected immutable native float64 array")


def _field(record: object, name: str) -> object:
    return record.fields[name] if type(record) is RecordNode else getattr(record, name)


def _shapes(tag: str, values: dict[str, object]) -> None:
    if tag == "PopulationHeterogeneityFit":
        config = values["config"]
        shape = (_field(config, "chains"), _field(config, "draws"), len(values["variant_ids"]))
        if any(values[name].shape != shape for name in ("mean_draws", "rho_draws")):
            raise B0HCodecError("fit shape differs from its retained config")
    elif tag == "CountPredictive":
        shape = values["mean_draws"].shape
        concentration = values["concentration"]
        if len(shape) != 2 or concentration is not None and concentration.shape != shape:
            raise B0HCodecError("predictive arrays require aligned two-dimensional shape")
    elif tag == "PredictiveSummaryEvidence" and values["prediction"] is not None:
        marginal = _field(values["prediction"], "marginal_predictive")
        shape = (values["draw_count"], len(values["targets"]))
        for name in ("mean_draws", "concentration"):
            array = _field(marginal, name)
            if array is None or array.shape != shape:
                raise B0HCodecError("summary prediction shape differs from draw/target axes")


def check_record_fields(tag: str, fields: dict[str, object]) -> dict[str, object]:
    _, names = _definition(tag)
    if type(fields) is not dict or any(type(key) is not str for key in fields) or set(fields) != set(names):
        raise B0HCodecError("record has missing or extra fields")

    # These accessors name a concrete field; failures retain only the known field path.
    def apply(name, check):
        try:
            return check(fields[name])
        except B0HCodecError as error:
            raise B0HCodecError(f"{tag}.{name}: invalid field representation") from error

    def i(name):
        return apply(name, _integer)

    def f(name):
        return apply(name, _float)

    def s(name):
        return apply(name, _string)

    def b(name):
        return apply(name, _boolean)

    def r(name, cls):
        return apply(name, lambda value: _record(value, cls))

    def t(name, check, length=None):
        return apply(name, lambda value: _tuple(value, check, length))

    def o(name, check):
        return apply(name, lambda value: _optional(value, check))

    def rr(cls):
        return lambda value: _record(value, cls)

    def pair(value):
        return _tuple(value, _float, 2)

    match tag:
        case "SbcCaseId" | "GenerationId":
            checked = tuple(i(name) for name in names)
        case "SeedIdentity":
            checked = (t("entropy", _integer, 9),)
        case "ParameterTruth":
            checked = (f("mean"), f("rho"))
        case "GenerationProvenance":
            checked = (r("generation_id", GenerationId), t("seeds", rr(SeedIdentity), 4))
        case "SharedHistory":
            checked = (
                t("cluster_frequencies", _float, 2),
                t("candidate_frequencies", _float, 16),
                t("uses_cluster", _boolean, 16),
            )
        case "HeldoutTarget":
            checked = (
                s("kind"),
                r("row", ReferenceCount),
                f("latent_frequency"),
                o("cluster_id", _integer),
                o("cluster_frequency", _float),
                o("candidate_frequency", _float),
                o("uses_cluster", _boolean),
            )
        case "GeneratedDataset":
            checked = (
                r("case_id", SbcCaseId),
                r("provenance", GenerationProvenance),
                r("truth", ParameterTruth),
                t("training", rr(ReferenceCount), 16),
                t("latent_frequencies", _float, 16),
                o("shared_history", rr(SharedHistory)),
                t("heldouts", rr(HeldoutTarget)),
                i("beta_zero_draws"),
                i("beta_one_draws"),
            )
        case "AllUnavailableDataset":
            checked = (
                r("case_id", SbcCaseId),
                r("provenance", GenerationProvenance),
                t("training", rr(ReferenceCount), 16),
            )
        case "GenerationFailure":
            checked = (
                r("case_id", SbcCaseId),
                r("provenance", GenerationProvenance),
                s("stage"),
                o("index", _integer),
                s("reason"),
                o("truth", rr(ParameterTruth)),
                o("sampled_mean", _numeric),
                o("sampled_rho", _numeric),
                o("offending_value", _numeric),
                o("exception_type", _string),
                o("exception_message", _string),
            )
        case "ReferenceCount":
            checked = tuple(s(name) for name in names[:5]) + (i("ac"), i("an"))
        case "FitAttemptSpec":
            checked = (
                r("case", SbcCaseId),
                i("attempt_id"),
                r("seed", SeedIdentity),
                r("config", PopulationHeterogeneityConfig),
            )
        case "AttemptError":
            checked = (
                s("category"),
                s("exception_class"),
                s("message"),
                o("reason", _string),
                o("diagnostics", lambda value: _tuple(value, rr(VariantHeterogeneityDiagnostics))),
                o("divergence_count", _integer),
            )
        case "FitAttemptResult":
            checked = (
                r("spec", FitAttemptSpec),
                s("status"),
                o("fit", rr(PopulationHeterogeneityFit)),
                o("error", rr(AttemptError)),
                t("identity_mismatches", _string),
                o("returned_type", _string),
            )
        case "StructuralCheckResult":
            checked = (
                r("case", SbcCaseId),
                s("status"),
                o("error", rr(AttemptError)),
                o("fit", rr(PopulationHeterogeneityFit)),
                o("returned_type", _string),
            )
        case "PopulationHeterogeneityConfig":
            checked = tuple(f(name) for name in names[:4]) + (
                i("draws"),
                i("tune"),
                i("chains"),
                f("target_accept"),
                i("seed"),
            )
        case "VariantTrainingCounts":
            checked = (s("variant_id"), i("training_observation_count"), i("training_ac"), i("training_an"))
        case "VariantHeterogeneityDiagnostics":
            checked = (s("variant_id"), f("max_rhat"), f("min_bulk_ess"), f("min_tail_ess"))
        case "PopulationHeterogeneityFit":
            checked = (
                r("config", PopulationHeterogeneityConfig),
                t("variant_ids", _string),
                apply("mean_draws", _array),
                apply("rho_draws", _array),
                t("training_record_ids", _string),
                t("training_group_ids", _string),
                t("unavailable_training_ids", _string),
                t("training_counts", rr(VariantTrainingCounts)),
                t("diagnostics", rr(VariantHeterogeneityDiagnostics)),
                i("divergence_count"),
            )
        case "ReferenceHeterogeneityPrediction":
            checked = (
                r("marginal_predictive", CountPredictive),
                t("observation_ids", _string),
                t("unavailable_ids", _string),
            )
        case "CountPredictive":
            checked = (apply("mean_draws", _array), o("concentration", _array), s("cdf_backend"))
        case "DiagnosticSeedIdentity":
            checked = (r("case", SbcCaseId), i("attempt_id"), i("purpose_id"), t("spawn_key", _integer))
        case "DiagnosticCallError":
            checked = (s("exception_class"), s("message"))
        case "PriorControlFailure":
            checked = (
                i("chain"),
                s("parameter"),
                s("reason"),
                o("sampled_mean", _numeric),
                o("sampled_rho", _numeric),
                o("returned_type", _string),
                o("error", rr(DiagnosticCallError)),
            )
        case "PriorControlResult":
            checked = (
                r("seed", DiagnosticSeedIdentity),
                t("pairs", pair),
                o("failure", rr(PriorControlFailure)),
            )
        case "DependencePointReference":
            checked = (
                f("mean"),
                f("rho"),
                t("components", lambda value: _tuple(value, _float, 4), 3),
                t("raw_values", _float, 3),
                f("value"),
                f("error_bound"),
                b("resolved"),
            )
        case "HeterogeneityDependenceReference":
            checked = (
                t("orders", _integer, 3),
                b("analytic_separability"),
                t("points", rr(DependencePointReference)),
            )
        case "DependenceComparisons":
            checked = (
                s("status"),
                t("comparisons_by_order", lambda value: _tuple(value, _integer, 4), 3),
                o("comparisons", lambda value: _tuple(value, _integer, 4)),
            )
        case "ScalarQuantityEvidence":
            checked = (
                i("quantity_id"),
                o("values", lambda value: _tuple(value, _float)),
                o("error", rr(DiagnosticCallError)),
                o("failed_training_row", _integer),
            )
        case "QuantityRankEvidence":
            checked = (
                i("mode_id"),
                i("quantity_id"),
                r("seed", DiagnosticSeedIdentity),
                s("status"),
                o("rank", _integer),
                o("comparisons", rr(DependenceComparisons)),
                o("error", rr(DiagnosticCallError)),
            )
        case "SelectedSbcQuantities":
            checked = (
                r("spec", FitAttemptSpec),
                t("selected_indices", lambda value: _tuple(value, _integer, 2), 4),
                t("selection_seeds", rr(DiagnosticSeedIdentity), 4),
                r("control", PriorControlResult),
                t("point_slots", _integer),
                t("points", pair),
                t("scalar_quantities", rr(ScalarQuantityEvidence), 5),
                o("reference", rr(HeterogeneityDependenceReference)),
                o("reference_error", rr(DiagnosticCallError)),
                t("ranks", rr(QuantityRankEvidence), 18),
            )
        case "ParameterPosteriorSummary":
            checked = (s("parameter"), f("truth"), f("estimate"), t("quantiles", _float, 7), i("draw_count"))
        case "HeldoutPredictiveSummary":
            checked = (
                r("target", HeldoutTarget),
                f("log_score"),
                f("absolute_error"),
                f("squared_error"),
                t("coverage", _coverage, 3),
                t("interval_width", _float, 3),
                f("randomized_pit"),
            )
        case "PredictiveSummaryEvidence":
            checked = (
                r("seed", DiagnosticSeedIdentity),
                t("seed_words", _integer, 4),
                i("seed_uint128"),
                s("cdf_backend"),
                i("draw_count"),
                t("targets", rr(HeldoutTarget)),
                s("status"),
                o("prediction", rr(ReferenceHeterogeneityPrediction)),
                t("rows", rr(HeldoutPredictiveSummary)),
                o("error", rr(DiagnosticCallError)),
            )
        case "HeterogeneityFitSummary":
            checked = (
                r("spec", FitAttemptSpec),
                s("variant_id"),
                t("parameters", rr(ParameterPosteriorSummary), 2),
                r("predictive", PredictiveSummaryEvidence),
            )
        case _:
            raise B0HCodecError("unknown record tag")
    result = dict(zip(names, checked, strict=True))
    _shapes(tag, result)
    return result


def record_fields(value: object) -> tuple[str, dict[str, object]]:
    for cls, names in _RECORDS:
        if type(value) is cls:
            tag = cls.__name__
            return tag, check_record_fields(tag, {name: getattr(value, name) for name in names.split()})
    raise B0HCodecError("unsupported record class")


def construct_record(tag: str, fields: dict[str, object]) -> object:
    values = check_record_fields(tag, fields)
    try:
        match tag:
            case "SbcCaseId":
                return SbcCaseId(**values)
            case "GenerationId":
                return GenerationId(**values)
            case "SeedIdentity":
                return SeedIdentity(**values)
            case "ParameterTruth":
                return ParameterTruth(**values)
            case "GenerationProvenance":
                return GenerationProvenance(**values)
            case "SharedHistory":
                return SharedHistory(**values)
            case "HeldoutTarget":
                return HeldoutTarget(**values)
            case "GeneratedDataset":
                return GeneratedDataset(**values)
            case "AllUnavailableDataset":
                return AllUnavailableDataset(**values)
            case "GenerationFailure":
                return GenerationFailure(**values)
            case "ReferenceCount":
                return ReferenceCount(**values)
            case "FitAttemptSpec":
                return FitAttemptSpec(**values)
            case "AttemptError":
                return AttemptError(**values)
            case "FitAttemptResult":
                return FitAttemptResult(**values)
            case "StructuralCheckResult":
                return StructuralCheckResult(**values)
            case "PopulationHeterogeneityConfig":
                return PopulationHeterogeneityConfig(**values)
            case "VariantTrainingCounts":
                return VariantTrainingCounts(**values)
            case "VariantHeterogeneityDiagnostics":
                return VariantHeterogeneityDiagnostics(**values)
            case "PopulationHeterogeneityFit":
                return PopulationHeterogeneityFit(**values)
            case "ReferenceHeterogeneityPrediction":
                return ReferenceHeterogeneityPrediction(**values)
            case "CountPredictive":
                return CountPredictive(**values)
            case "DiagnosticSeedIdentity":
                return DiagnosticSeedIdentity(**values)
            case "DiagnosticCallError":
                return DiagnosticCallError(**values)
            case "PriorControlFailure":
                return PriorControlFailure(**values)
            case "PriorControlResult":
                return PriorControlResult(**values)
            case "DependencePointReference":
                return DependencePointReference(**values)
            case "HeterogeneityDependenceReference":
                return HeterogeneityDependenceReference(**values)
            case "DependenceComparisons":
                return DependenceComparisons(**values)
            case "ScalarQuantityEvidence":
                return ScalarQuantityEvidence(**values)
            case "QuantityRankEvidence":
                return QuantityRankEvidence(**values)
            case "SelectedSbcQuantities":
                return SelectedSbcQuantities(**values)
            case "ParameterPosteriorSummary":
                return ParameterPosteriorSummary(**values)
            case "HeldoutPredictiveSummary":
                return HeldoutPredictiveSummary(**values)
            case "PredictiveSummaryEvidence":
                return PredictiveSummaryEvidence(**values)
            case "HeterogeneityFitSummary":
                return HeterogeneityFitSummary(**values)
    except (TypeError, ValueError, OverflowError) as error:
        raise B0HCodecError(f"{tag}: public constructor rejected evidence") from error
    raise B0HCodecError("unknown record tag")
