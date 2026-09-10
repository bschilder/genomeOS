"""Pure reducer anchors; literal mock nulls are not calibration results."""
from __future__ import annotations

import importlib

import pytest
from heterogeneity_runner_fixtures import campaign

from genomeos.validation.heterogeneity_runner_records import CaseEvidence
from genomeos.validation.heterogeneity_runner_wire import record_digest
from genomeos.validation.sbc_ranks import RankNullReference, rank_ecdf_statistic


def test_literal_full_n_rank_decisions_and_inclusive_tail():
    reduction = importlib.import_module("genomeos.validation.heterogeneity_reduction")
    reference = RankNullReference(512, 1653499886, (100,) * 99999 + (2048,))
    balanced = (0,) * 103 + (1,) * 103 + (2,) * 102 + (3,) * 102 + (4,) * 102
    assert rank_ecdf_statistic((103, 103, 102, 102, 102)) == 6
    assert rank_ecdf_statistic((512, 0, 0, 0, 0)) == 2048
    correct = reduction.rank_reduction(0, 0, 0, balanced, (), reference)
    control = reduction.rank_reduction(0, 1, 3, (0,) * 512, (), reference)
    assert correct.test.statistic == 6
    assert correct.decision == "not_reject"
    assert control.test.p_value == 2 / 100001
    assert control.test.bonferroni_p_value == 24 / 100001
    assert control.decision == "reject"
    assert control.role == "required_control"


def test_511_or_zero_ranks_never_get_a_full_n_test():
    reduction = importlib.import_module("genomeos.validation.heterogeneity_reduction")
    reference = RankNullReference(512, 1653499886, (100,) * 100000)
    result = reduction.rank_reduction(
        1, 0, 5, (2,) * 511, ("dependence_rank_order_unresolved",), reference)
    assert result.actual_n == 511
    assert result.missing_n == 1
    assert result.test is None
    assert result.decision == "uncomputable"
    empty = reduction.rank_reduction(1, 0, 5, (), ("unstarted",) * 512, reference)
    assert empty.counts == (0, 0, 0, 0, 0)
    assert empty.test is None
    with pytest.raises(ValueError):
        reduction.rank_reduction(1, 0, 5, (2,) * 511, ("unstarted",),
                                 RankNullReference(511, 1653499886, (100,) * 100000))


def test_empty_campaign_accounts_all_records_without_science(tmp_path, monkeypatch):
    reduction = importlib.import_module("genomeos.validation.heterogeneity_reduction")
    manifest, _, null = campaign(tmp_path)
    cases = tuple(CaseEvidence(record_digest(manifest), case, ()) for case in manifest.cases)

    def forbidden(*args, **kwargs):
        raise AssertionError("pure empty reduction called a rank test or science")

    monkeypatch.setattr(reduction, "test_rank_uniformity", forbidden)
    reference = RankNullReference(null.sample_size, null.seed, null.statistics)
    output = reduction.reduce_b0h_study(manifest, cases, reference)
    assert len(output.cases) == 1938
    assert output.planned_initial_fits == 1936
    assert output.completed_fit_calls == output.ambiguous_fit_calls == 0
    assert len(output.ranks) == 36
    assert all(row.actual_n == 0 and row.missing_n == 512 for row in output.ranks)
    assert output.sensitivity_limited
    assert not output.correct_family_rejected
    assert not output.unconditional_claim_eligible
    assert output.permitted_claim is None
    with pytest.raises(ValueError, match="exact StudyReduction"):
        reduction.reduction_bytes(object())
    malformed = output.model_copy(update={"cases": list(output.cases)})
    with pytest.raises(ValueError):
        reduction.reduction_bytes(malformed)
    assert reduction.reduction_bytes(output) == reduction.reduction_bytes(
        reduction.reduce_b0h_study(manifest, cases, reference))
    for invalid in (cases[:-1], cases[::-1], cases[:-1] + (cases[0],)):
        with pytest.raises(ValueError):
            reduction.reduce_b0h_study(manifest, invalid, reference)


def test_absent_quantities_report_actual_failed_fit(tmp_path, monkeypatch):
    from test_heterogeneity_runner import mocked_runner

    from genomeos.validation.heterogeneity_runner_store import LocalB0HStore

    runner, _ = mocked_runner(monkeypatch, terminal=True)
    reduction = importlib.import_module("genomeos.validation.heterogeneity_reduction")
    from heterogeneity_runner_fixtures import dataset

    manifest, admission, null = campaign(tmp_path)
    with LocalB0HStore.create(tmp_path / "study.sqlite3", manifest=manifest, admission=admission,
                              null=null, owner_id="fixture-owner") as store:
        result = runner.execute_b0h_case(manifest, dataset().case_id, store)
    digest = record_digest(manifest)
    cases = tuple(result if case == result.case else CaseEvidence(digest, case, ())
                  for case in manifest.cases)
    output = reduction.reduce_b0h_study(manifest, cases, RankNullReference(512, null.seed, null.statistics))
    assert output.cases[0].attempt0 == "failed"
    assert output.cases[0].quantities == "not_admitted"
    assert output.ranks[0].failure_status_counts == (("attempt0:failed", 1), ("generation:unstarted", 511))
    assert output.ranks[0].test is None


def test_descriptive_targets_keep_separate_denominators_and_negative_infinity(tmp_path, monkeypatch):
    import struct

    from heterogeneity_codec_fixtures import summary
    from heterogeneity_runner_fixtures import dataset
    from test_heterogeneity_runner import mocked_runner

    from genomeos.validation.heterogeneity_runner_store import LocalB0HStore

    runner, _ = mocked_runner(monkeypatch)
    reduction = importlib.import_module("genomeos.validation.heterogeneity_reduction")

    def fixture_summary(data, *, attempt, cdf_backend):
        return summary(2, 0, data.case_id.track_id, attempt.spec.attempt_id, cdf_backend,
                       "complete" if data.case_id.track_id == 0 else "prediction_failed")

    monkeypatch.setattr(runner, "summarize_heterogeneity_fit", fixture_summary)
    manifest, admission, null = campaign(tmp_path)
    with LocalB0HStore.create(tmp_path / "study.sqlite3", manifest=manifest, admission=admission,
                              null=null, owner_id="fixture-owner") as store:
        left = runner.execute_b0h_case(manifest, dataset(2, 0, 0).case_id, store)
        right = runner.execute_b0h_case(manifest, dataset(2, 0, 1).case_id, store)

    def forbidden(*args, **kwargs):
        raise AssertionError("pure reduction called a scientific stage")

    for name in ("generate_sbc_case", "run_fit_attempt", "selected_sbc_quantities",
                 "summarize_heterogeneity_fit", "exercise_unavailable"):
        monkeypatch.setattr(runner, name, forbidden)
    monkeypatch.setattr(reduction, "test_rank_uniformity", forbidden)
    digest = record_digest(manifest)
    found = {left.case: left, right.case: right}
    cases = tuple(found.get(case, CaseEvidence(digest, case, ())) for case in manifest.cases)
    output = reduction.reduce_b0h_study(manifest, cases, RankNullReference(512, null.seed, null.statistics))
    aggregates = {(r.track_id, r.target_kind, r.metric): r for r in output.aggregates
                  if r.study_id == 2 and r.case_id == 0}
    shared = aggregates[(0, "shared_cluster0", "log_score")]
    fresh = aggregates[(0, "fresh_cluster", "log_score")]
    missing = aggregates[(1, "shared_cluster0", "log_score")]
    assert shared.actual_n == fresh.actual_n == 1
    assert shared.failed_n == shared.planned_n - 1
    assert shared.mean_bits == struct.pack(">d", -float("inf")).hex()
    assert fresh.mean_bits == struct.pack(">d", -2.0).hex()
    assert missing.actual_n == 0 and missing.failed_n == missing.planned_n and missing.mean_bits is None
    assert aggregates[(1, "parameter_mean", "estimate")].actual_n == 1
    assert not output.unconditional_claim_eligible


@pytest.mark.parametrize("metric,bits", [
    ("log_score", "7ff0000000000000"), ("log_score", "7ff8000000000000"),
    ("absolute_error", "fff0000000000000"), ("coverage_50", "3fe0000000000000"),
])
def test_descriptive_records_refuse_invalid_numeric_domains(metric, bits):
    from heterogeneity_runner_fixtures import dataset

    from genomeos.validation.heterogeneity_reduction_records import DescriptiveRow

    with pytest.raises(ValueError):
        DescriptiveRow(case=dataset().case_id, target_kind="fresh_population", metric=metric,
                       value_bits=bits, dependence_label="independent_dataset")


def test_missed_control_owner_loss_and_predictive_failure_have_distinct_meaning(tmp_path):
    reduction = importlib.import_module("genomeos.validation.heterogeneity_reduction")
    from genomeos.validation.heterogeneity_reduction_records import CaseAccounting

    manifest, _, null = campaign(tmp_path)
    reference = RankNullReference(512, 1653499886, null.statistics)
    balanced = (0,) * 103 + (1,) * 103 + (2,) * 102 + (3,) * 102 + (4,) * 102
    accounting = tuple(CaseAccounting(
        case=case, generation="all_unavailable" if case.study_id == 3 else "available",
        structural="expected_refusal" if case.study_id == 3 else "not_admitted",
        attempt0="not_admitted" if case.study_id == 3 else "accepted", attempt1="not_admitted",
        quantities="complete" if case.study_id == 0 else "not_admitted",
        summary="not_admitted" if case.study_id == 3 else "complete",
        accepted_attempt=None if case.study_id == 3 else 0, owner_loss_count=0,
        execution_failure_count=0, unstarted_required_stages=(), unresolved_reasons=(),
    ) for case in manifest.cases)
    ranks = tuple(reduction.rank_reduction(
        track, mode, quantity,
        (0,) * 512 if (mode, quantity) in ((1, 3), (2, 5)) else balanced,
        (), reference,
    ) for track in (0, 1) for mode in range(3) for quantity in range(6))
    assert reduction.study_claim_reasons(accounting, ranks) == ()
    missed = list(ranks)
    missed[9] = reduction.rank_reduction(0, 1, 3, balanced, (), reference)
    assert reduction.study_claim_reasons(accounting, tuple(missed)) == (
        "predeclared_control_sensitivity_limited",)
    for changes in (
        {"summary": "owner_lost", "owner_loss_count": 1},
        {"summary": "prediction_failed"},
        {"summary": "diagnostics_failed"},
    ):
        altered = accounting[0].model_copy(update=changes)
        reasons = reduction.study_claim_reasons((altered,) + accounting[1:], ranks)
        assert reasons == ("unresolved_case_or_required_diagnostic_outcomes",)
        assert "correct_family_discrepancy_detected" not in reasons
