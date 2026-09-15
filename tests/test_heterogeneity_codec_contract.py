"""Closed field contracts are independent of numerical execution."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pytest

from genomeos.validation.heterogeneity_codec_contract import (
    ROOT_TYPES,
    RecordNode,
    check_contract_drift,
    check_record_fields,
    construct_record,
    record_fields,
)
from genomeos.validation.heterogeneity_codec_wire import ArrayReference, B0HCodecError
from genomeos.validation.heterogeneity_dependence import DependencePointReference
from genomeos.validation.heterogeneity_simulation_types import SbcCaseId


def test_case_contract_and_exact_fields():
    check_contract_drift()
    tag, fields = record_fields(SbcCaseId(0, 0, 0, 0))
    assert tag == "SbcCaseId"
    assert fields == dict(track_id=0, study_id=0, case_id=0, replicate_id=0)
    assert construct_record(tag, fields) == SbcCaseId(0, 0, 0, 0)
    assert len(ROOT_TYPES) == 7
    for field in fields:
        with pytest.raises(B0HCodecError):
            check_record_fields(tag, {key: value for key, value in fields.items() if key != field})
    with pytest.raises(B0HCodecError):
        check_record_fields(tag, {**fields, "new_defaulted_field": None})


@pytest.mark.parametrize("bad", [True, 0.0, "0", np.bool_(False)])
def test_bool_and_coercible_integer_fields_refused(bad):
    with pytest.raises(B0HCodecError):
        check_record_fields("SbcCaseId", dict(track_id=bad, study_id=0, case_id=0, replicate_id=0))


def test_known_numpy_values_normalize_at_declared_fields():
    fields = dict(track_id=np.int64(0), study_id=0, case_id=0, replicate_id=0)
    result = check_record_fields("SbcCaseId", fields)
    assert type(result["track_id"]) is int
    reference = DependencePointReference(
        np.float32(0.5),
        np.float16(0.25),
        ((0.0,) * 4,) * 3,
        (0.0,) * 3,
        np.float64(-0.0),
        0.0,
        False,
    )
    _, normalized = record_fields(reference)
    assert type(normalized["mean"]) is float
    assert type(normalized["rho"]) is float
    for bad in (np.longdouble(0.5), complex(0.5), True, 1):
        with pytest.raises(B0HCodecError):
            check_record_fields("DependencePointReference", {**normalized, "mean": bad})


def test_exact_class_only_and_field_drift(monkeypatch):
    @dataclass(frozen=True)
    class Child(SbcCaseId):
        pass

    with pytest.raises(B0HCodecError):
        record_fields(Child(0, 0, 0, 0))
    import genomeos.validation.heterogeneity_codec_contract as contract

    original = contract.fields

    def drifted(cls):
        actual = original(cls)
        return actual[:-1] if cls is SbcCaseId else actual

    monkeypatch.setattr(contract, "fields", drifted)
    with pytest.raises(B0HCodecError, match="drift"):
        check_contract_drift()


def test_shape_context_uses_retained_fit_config():
    config = RecordNode(
        "PopulationHeterogeneityConfig",
        dict(
            mean_prior_alpha=1.0,
            mean_prior_beta=1.0,
            rho_prior_alpha=1.0,
            rho_prior_beta=9.0,
            draws=2,
            tune=1,
            chains=4,
            target_accept=0.9,
            seed=42,
        ),
    )
    reference = ArrayReference((4, 2, 1), 64, "0" * 64)
    fields = dict(
        config=config,
        variant_ids=("v",),
        mean_draws=reference,
        rho_draws=reference,
        training_record_ids=("r",),
        training_group_ids=("g",),
        unavailable_training_ids=(),
        training_counts=(),
        diagnostics=(),
        divergence_count=0,
    )
    assert check_record_fields("PopulationHeterogeneityFit", fields)["mean_draws"] == reference
    with pytest.raises(B0HCodecError, match="shape"):
        check_record_fields(
            "PopulationHeterogeneityFit",
            {
                **fields,
                "rho_draws": ArrayReference((8, 1, 1), 64, "0" * 64),
            },
        )


def test_validation_wraps_only_known_constructor_defects(monkeypatch):
    fields = dict(track_id=0, study_id=0, case_id=0, replicate_id=0)

    def known(self):
        raise ValueError("invalid test fixture")

    monkeypatch.setattr(SbcCaseId, "__post_init__", known)
    with pytest.raises(B0HCodecError) as caught:
        construct_record("SbcCaseId", fields)
    assert isinstance(caught.value.__cause__, ValueError)

    def unexpected(self):
        raise RuntimeError("implementation defect")

    monkeypatch.setattr(SbcCaseId, "__post_init__", unexpected)
    with pytest.raises(RuntimeError, match="implementation defect"):
        construct_record("SbcCaseId", fields)
