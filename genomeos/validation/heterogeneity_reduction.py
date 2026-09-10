"""Pure full-study B0H reduction (design §§5,7–8,12; runner §6)."""
from __future__ import annotations

import json
import math
import struct
from collections import Counter, defaultdict

from genomeos.validation.heterogeneity_attempts import FitAttemptResult
from genomeos.validation.heterogeneity_reduction_records import (
    CaseAccounting,
    DescriptiveAggregate,
    DescriptiveRow,
    RankReduction,
    StudyReduction,
)
from genomeos.validation.heterogeneity_runner_binding import (
    next_stage_key,
    require_paired_generations,
    validate_case_evidence,
)
from genomeos.validation.heterogeneity_runner_records import (
    CampaignManifest,
    CaseEvidence,
    StoredStage,
    prepared_null,
)
from genomeos.validation.heterogeneity_runner_wire import record_digest, sha256
from genomeos.validation.heterogeneity_sbc_quantity_types import SelectedSbcQuantities
from genomeos.validation.heterogeneity_summary_types import HeterogeneityFitSummary
from genomeos.validation.sbc_ranks import RankNullReference, test_rank_uniformity


def _bits(value: float) -> str:
    return struct.pack(">d", value).hex()


def _float(bits: str) -> float:
    return struct.unpack(">d", bytes.fromhex(bits))[0]


def _json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=True,
                      allow_nan=False, separators=(",", ":")).encode("ascii")


def rank_reduction(track_id: int, mode_id: int, quantity_id: int,
                   ranks: tuple[int, ...], failures: tuple[str, ...],
                   reference: RankNullReference) -> RankReduction:
    prepared_null(reference)
    if type(ranks) is not tuple or type(failures) is not tuple or len(ranks) + len(failures) != 512:
        raise ValueError("rank reduction requires 512 explicit outcomes")
    if any(type(rank) is not int or rank not in range(5) for rank in ranks):
        raise ValueError("ranks must be exact integers0..4")
    test = test_rank_uniformity(ranks, reference=reference) if len(ranks) == 512 else None
    role = ("correct_family" if mode_id == 0 else "required_control"
            if (mode_id, quantity_id) in ((1, 3), (2, 5)) else "other_control")
    return RankReduction(
        track_id=track_id, mode_id=mode_id, quantity_id=quantity_id,
        counts=tuple(ranks.count(rank) for rank in range(5)), actual_n=len(ranks),
        missing_n=len(failures), failure_status_counts=tuple(sorted(Counter(failures).items())),
        test=test, role=role, decision="uncomputable" if test is None else
        "reject" if test.p_value <= .05 / 12 else "not_reject",
    )


def _status(stage: StoredStage | None) -> str:
    if stage is None:
        return "not_admitted"
    if stage.loss is not None:
        return "owner_lost"
    if stage.completion is None:
        return "started_unresolved"
    if stage.failure is not None:
        return "execution_failed"
    if type(stage.value) is SelectedSbcQuantities:
        return "complete" if stage.value.complete else "incomplete"
    if type(stage.value) is HeterogeneityFitSummary:
        return stage.value.predictive.status
    return stage.value.status


def _account(manifest: CampaignManifest, evidence: CaseEvidence) -> CaseAccounting:
    found = {(s.start.key.stage, s.start.key.attempt_id): s for s in evidence.stages}
    accepted = next((s.value.spec.attempt_id for s in evidence.stages
                     if type(s.value) is FitAttemptResult and s.value.status == "accepted"), None)
    fields = {"generation": _status(found.get(("generation", None))),
              "structural": _status(found.get(("structural", None))),
              "attempt0": _status(found.get(("fit", 0))),
              "attempt1": _status(found.get(("fit", 1))),
              "quantities": _status(found.get(("quantities", accepted))),
              "summary": _status(found.get(("summary", accepted)))}
    upcoming = next_stage_key(manifest, evidence)
    missing = () if upcoming is None else (upcoming.stage,)
    if upcoming is not None:
        name = "attempt" + str(upcoming.attempt_id) if upcoming.stage == "fit" else upcoming.stage
        fields[name] = "unstarted"
    reasons = []
    for name, status in fields.items():
        if status in ("not_admitted", "available", "all_unavailable", "accepted",
                      "expected_refusal", "complete"):
            continue
        if name == "attempt0" and status == "convergence_failed" and accepted == 1:
            continue
        reasons.append(name + ":" + status)
    return CaseAccounting(
        case=evidence.case, **fields, accepted_attempt=accepted,
        owner_loss_count=sum(s.loss is not None for s in evidence.stages),
        execution_failure_count=sum(s.failure is not None for s in evidence.stages),
        unstarted_required_stages=missing, unresolved_reasons=tuple(reasons),
    )


def missing_quantities_reason(account: CaseAccounting) -> str:
    """Name the first actual prerequisite that prevents an absent quantities slot."""
    if account.case.study_id != 0 or account.quantities not in ("not_admitted", "unstarted"):
        raise ValueError("absence attribution requires a prior case with absent quantities")
    if account.generation != "available":
        return "generation:" + account.generation
    if account.accepted_attempt is not None:
        return "quantities:unstarted"
    if account.attempt0 == "convergence_failed":
        return "attempt1:" + account.attempt1
    return "attempt0:" + account.attempt0


def _label(study: int) -> str:
    return {0: "independent_dataset", 1: "paired_tracks",
            2: "shared_history_paired_tracks", 4: "boundary_degenerate_paired_tracks"}[study]


def _metric_keys(case) -> tuple[tuple[str, str], ...]:
    if case.study_id == 3:
        return ()
    shared = ("shared_cluster0", "fresh_cluster") if case.study_id == 2 else ("fresh_population",)
    intervals = ("coverage_50", "coverage_80", "coverage_95", "width_50", "width_80", "width_95")
    parameter = ("estimate", "truth", "absolute_error", "squared_error") + intervals
    predictive = ("log_score", "absolute_error", "squared_error", "randomized_pit") + intervals
    return (
        tuple((target, metric) for target in ("parameter_mean", "parameter_rho") for metric in parameter)
        + tuple((target, metric) for target in shared for metric in predictive)
    )


def _rows(evidence: CaseEvidence) -> tuple[DescriptiveRow, ...]:
    summary = next((s.value for s in evidence.stages if type(s.value) is HeterogeneityFitSummary), None)
    if summary is None:
        return ()
    result = []
    for target, value in tuple(("parameter_" + p.parameter, p) for p in summary.parameters) + tuple(
            (r.target.kind, r) for r in summary.predictive.rows):
        metrics = [("absolute_error", value.absolute_error), ("squared_error", value.squared_error)]
        if target.startswith("parameter_"):
            metrics.extend((("estimate", value.estimate), ("truth", value.truth)))
        else:
            metrics.extend((("log_score", value.log_score), ("randomized_pit", value.randomized_pit)))
        metrics.extend(("coverage_" + str(level), float(flag)) for level, flag in
                       zip((50, 80, 95), value.coverage, strict=True))
        metrics.extend(("width_" + str(level), width) for level, width in
                       zip((50, 80, 95), value.interval_width, strict=True))
        result.extend(DescriptiveRow(
            case=evidence.case, target_kind=target, metric=metric,
            value_bits=_bits(float(number)), dependence_label=_label(evidence.case.study_id))
                      for metric, number in metrics)
    return tuple(result)


def _aggregates(manifest, rows) -> tuple[DescriptiveAggregate, ...]:
    planned, values = Counter(), defaultdict(list)
    for case in manifest.cases:
        for target, metric in _metric_keys(case):
            planned[(case.study_id, case.case_id, case.track_id, target, metric)] += 1
    for row in rows:
        key = (row.case.study_id, row.case.case_id, row.case.track_id, row.target_kind, row.metric)
        values[key].append(_float(row.value_bits))
    result = []
    for (study, case, track, target, metric), count in sorted(planned.items()):
        observed = values[(study, case, track, target, metric)]
        mean = None
        if observed:
            mean = -math.inf if any(x == -math.inf for x in observed) else math.fsum(
                x / len(observed) for x in observed)
        result.append(DescriptiveAggregate(
            study_id=study, case_id=case, track_id=track, target_kind=target, metric=metric,
            planned_n=count, actual_n=len(observed), failed_n=count - len(observed),
            mean_bits=None if mean is None else _bits(mean)))
    return tuple(result)


def reduce_b0h_study(manifest: CampaignManifest, cases: tuple[CaseEvidence, ...],
                     null_reference: RankNullReference) -> StudyReduction:
    null = prepared_null(null_reference)
    if record_digest(null) != manifest.null_sha256:
        raise ValueError("reduction null differs from prepared campaign null")
    if type(cases) is not tuple or tuple(c.case for c in cases) != manifest.cases:
        raise ValueError("reduction requires exact ordered complete manifest membership")
    for evidence in cases:
        validate_case_evidence(manifest, evidence)
    for index in range(0, len(cases), 2):
        left, right = cases[index:index + 2]
        if left.case.study_id != 0 and left.stages and right.stages:
            require_paired_generations(left.stages[0], right.stages[0])
    inventory = tuple((e.case.canonical_id, tuple(d for s in e.stages for d in (
        record_digest(s.start), None if s.completion is None else record_digest(s.completion),
        None if s.loss is None else record_digest(s.loss)) if d is not None)) for e in cases)
    accounting = tuple(_account(manifest, evidence) for evidence in cases)
    by_case = {account.case: account for account in accounting}
    ranks = []
    for track in (0, 1):
        prior = tuple(e for e in cases if e.case.study_id == 0 and e.case.track_id == track)
        for mode in range(3):
            for quantity in range(6):
                valid, failures = [], []
                for evidence in prior:
                    stage = next((s for s in evidence.stages if s.start.key.stage == "quantities"), None)
                    if stage is None or type(stage.value) is not SelectedSbcQuantities:
                        failures.append(
                            missing_quantities_reason(by_case[evidence.case])
                            if stage is None else _status(stage)
                        )
                    else:
                        entry = stage.value.ranks[mode * 6 + quantity]
                        if entry.status == "ranked":
                            valid.append(entry.rank)
                        else:
                            failures.append(entry.status)
                ranks.append(
                    rank_reduction(track, mode, quantity, tuple(valid), tuple(failures), null_reference)
                )
    rows = tuple(row for evidence in cases for row in _rows(evidence))
    rejected = any(row.decision == "reject" for row in ranks if row.role == "correct_family")
    limited = any(row.decision != "reject" for row in ranks if row.role == "required_control")
    reasons = study_claim_reasons(accounting, tuple(ranks))
    all_stages = tuple(s for e in cases for s in e.stages)
    completed = Counter(s.start.key.stage for s in all_stages if s.completion is not None)
    return StudyReduction(
        format="b0h_reduction", version="1", campaign_sha256=record_digest(manifest),
        inventory_sha256=sha256(_json(inventory)), null_sha256=manifest.null_sha256,
        cases=accounting, planned_initial_fits=1936, planned_retry_slots=1936,
        completed_fit_calls=completed["fit"],
        ambiguous_fit_calls=sum(s.start.key.stage == "fit" and s.completion is None for s in all_stages),
        completed_generation_calls=completed["generation"],
        completed_structural_calls=completed["structural"],
        completed_quantity_calls=completed["quantities"], completed_summary_calls=completed["summary"],
        ranks=tuple(ranks), rows=rows, aggregates=_aggregates(manifest, rows),
        correct_family_rejected=rejected, sensitivity_limited=limited,
        unconditional_claim_eligible=not reasons, claim_reasons=reasons,
        permitted_claim=None if reasons else "no discrepancy detected at this design's resolution",
    )


def reduction_bytes(value: StudyReduction) -> bytes:
    if type(value) is not StudyReduction:
        raise ValueError("reduction output requires exact StudyReduction root")
    value = StudyReduction.model_validate(value, strict=True)
    if value.claim_reasons != study_claim_reasons(value.cases, value.ranks):
        raise ValueError("reduction claim reasons contradict retained accounting")
    document = value.model_dump(mode="json")
    for target, source in zip(document["ranks"], value.ranks, strict=True):
        if source.test is not None:
            target["test"] = {"counts": list(source.test.counts), "statistic": source.test.statistic,
                              "p_value_bits": _bits(source.test.p_value),
                              "bonferroni_p_value_bits": _bits(source.test.bonferroni_p_value)}
    return _json(document)


def study_claim_reasons(accounting: tuple[CaseAccounting, ...],
                        ranks: tuple[RankReduction, ...]) -> tuple[str, ...]:
    from genomeos.validation.heterogeneity_simulation import enumerate_sbc_cases
    if tuple(row.case for row in accounting) != enumerate_sbc_cases():
        raise ValueError("claim accounting must match all1938 planned identities")
    expected = tuple((track, mode, quantity) for track in (0, 1)
                     for mode in range(3) for quantity in range(6))
    if tuple((r.track_id, r.mode_id, r.quantity_id) for r in ranks) != expected:
        raise ValueError("claim requires all36 ordered rank rows")
    reasons = []
    if any(row.unresolved_reasons or row.owner_loss_count or row.execution_failure_count
           or (row.case.study_id == 3 and row.structural != "expected_refusal")
           or (row.case.study_id != 3 and (row.accepted_attempt is None or row.summary != "complete"))
           or (row.case.study_id == 0 and row.quantities != "complete") for row in accounting):
        reasons.append("unresolved_case_or_required_diagnostic_outcomes")
    if any(row.decision == "uncomputable" for row in ranks):
        reasons.append("incomplete_rank_outcomes")
    if any(row.decision == "reject" for row in ranks if row.role == "correct_family"):
        reasons.append("correct_family_discrepancy_detected")
    if any(row.decision != "reject" for row in ranks if row.role == "required_control"):
        reasons.append("predeclared_control_sensitivity_limited")
    return tuple(reasons)
