"""Fixed numerical acceptance comparisons for synthetic count laws (design §7, §8).

The reference is an absolute Decimal product, never candidate-normalized. Upper tails
come directly from the public partition interface, independently of rounded lower CDFs.
"""

from __future__ import annotations

import warnings
from dataclasses import asdict
from decimal import Decimal, localcontext
from typing import Any

import numpy as np

from genomeos.validation.count_recurrence import beta_binomial_log_partitions
from genomeos.validation.predictive import CountPredictive
from scripts.count_recurrence_oracle import absolute_law

SEED = 42


def decimal_record(value: Any) -> Any:
    """Preserve Decimal strings separately from candidate binary64 values."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {key: decimal_record(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [decimal_record(item) for item in value]
    return value


def reference_pair(n: int, p: float, c: float, counts: tuple[int, ...], *, swapped=False):
    """Return both independently evaluated precisions, with absolute checks retained."""
    first = absolute_law(n, p, c, counts, 400, swapped)
    second = absolute_law(n, p, c, counts, 480, swapped)
    checks = {
        "normalization_400": abs(first.normalization - 1) <= Decimal("1e-70"),
        "normalization_480": abs(second.normalization - 1) <= Decimal("1e-70"),
        "queried_log_precision": all(
            abs(x - y) <= Decimal("1e-70") for x, y in zip(first.log_mass, second.log_mass, strict=True)
        ),
    }
    return second, {
        "precision_400": decimal_record(asdict(first)),
        "precision_480": decimal_record(asdict(second)),
        "checks": checks,
    }


def probability_check(actual: float, exact: Decimal) -> dict:
    """Fixed long-path/tail rules, including normal tiny tails and float underflow."""
    rounded = float(exact)
    error = abs(Decimal.from_float(actual) - exact) if np.isfinite(actual) else Decimal("Infinity")
    underflow = exact > 0 and rounded == 0
    if rounded < np.finfo(float).tiny:
        passed = error <= Decimal.from_float(4 * np.nextafter(0.0, 1.0))
    else:
        passed = error <= Decimal("1e-11") and error <= Decimal("1e-9") * exact
    return {
        "passed": bool(passed),
        "absolute_error": str(error),
        "float_underflow": bool(underflow),
        "rounded_oracle": rounded,
    }


def evaluate_case(case: dict, group: str, backend: str, xp: Any, record=None) -> dict:
    """Evaluate one declared law; the receipt caller retains unexpected exceptions."""
    n = case["an"]
    p, c = float.fromhex(case["mean_hex"]), float.fromhex(case["concentration_hex"])
    counts = tuple(case["queried_ac"])
    try:
        law = CountPredictive(np.full((1, len(counts)), p), np.full((1, len(counts)), c), cdf_backend=backend)
    except ValueError as error:
        expected = (
            case["expected_operation"] == "refuse_numeric_domain"
            and str(error) == case["expected_refusal_reason"]
        )
        return {
            "status": "expected_domain_refusal" if expected else "unexpected_constructor_failure",
            "message": str(error),
            "points": [],
        }
    if case["expected_operation"] != "evaluate":
        return {"status": "unexpected_domain_acceptance", "points": []}
    with localcontext() as context:
        context.prec, context.Emin, context.Emax = 480, -999999999, 999999999
        try:
            reference, oracle = reference_pair(n, p, c, counts)
        except ArithmeticError as error:
            return {"status": "oracle_failure", "message": str(error), "points": []}
        if record is not None:
            record({"event": "oracle", "case_id": case["case_id"], "oracle": oracle})
        complement, reflected = (None, None)
        if group == "small":
            try:
                complement, reflected = reference_pair(n, p, c, tuple(n - k for k in counts), swapped=True)
            except ArithmeticError as error:
                return {"status": "oracle_failure", "message": str(error), "points": [], "oracle": oracle}
            if record is not None:
                record({"event": "reflected_oracle", "case_id": case["case_id"], "oracle": reflected})
        logs, public_lower = law.log_prob(counts, [n] * len(counts)), law.cdf(counts, [n] * len(counts))
        partitions = beta_binomial_log_partitions(
            xp.asarray(p),
            xp.asarray(c),
            xp.asarray(n),
            xp.asarray(counts),
            array_module=xp,
            max_count=n,
        )
        lower, upper = partitions.tails(array_module=xp)
        partition_logs = partitions.log_mass(array_module=xp)
        if backend == "cupy":
            lower, upper, partition_logs = map(xp.asnumpy, (lower, upper, partition_logs))
        points = []
        for i, k in enumerate(counts):
            exact = reference.log_mass[i]
            actual = float(logs[i])
            error = abs(Decimal.from_float(actual) - exact)
            tolerance = Decimal("5e-10")
            if group == "long":
                tolerance = max(tolerance, Decimal.from_float(4 * abs(np.spacing(float(exact)))))
            checks = {
                "log": error <= tolerance,
                "partition_log": abs(Decimal.from_float(float(partition_logs[i])) - exact) <= tolerance,
            }
            if n == 1:
                checks["bernoulli_log"] = error <= Decimal("5e-12")
            if abs(exact) < Decimal("1e-8"):
                near_tolerance = abs(exact) * Decimal("2e-12")
                if abs(float(exact)) < np.finfo(float).tiny:
                    near_tolerance = Decimal.from_float(4 * np.nextafter(0.0, 1.0))
                checks["near_certain_log"] = actual < 0 and error <= near_tolerance
            pmf = float(np.exp(actual))
            if group == "small":
                pmf_error = abs(Decimal.from_float(pmf) - exact.exp())
                checks["pmf_absolute"] = pmf_error <= Decimal("5e-13")
                if exact.exp() >= Decimal("1e-300"):
                    checks["pmf_relative"] = pmf_error <= Decimal("1e-10") * exact.exp()
                checks["complement_log"] = abs(
                    Decimal.from_float(actual) - complement.log_mass[i]
                ) <= Decimal("5e-8")
            tails = {
                "public_lower": probability_check(float(public_lower[i]), reference.lower[i]),
                "partition_lower": probability_check(float(lower[i]), reference.lower[i]),
                "direct_upper": probability_check(float(upper[i]), reference.upper[i]),
                "pmf": probability_check(pmf, exact.exp()),
            }
            if group == "small":
                # The fixed small-law PMF rule has no relative gate below 1e-300.
                tails["pmf"]["passed"] = bool(checks["pmf_absolute"] and checks.get("pmf_relative", True))
            checks.update({name: item["passed"] for name, item in tails.items()})
            points.append(
                {
                    "ac": k,
                    "candidate_log": actual,
                    "candidate_pmf": pmf,
                    "candidate_lower": float(public_lower[i]),
                    "candidate_partition_lower": float(lower[i]),
                    "candidate_upper": float(upper[i]),
                    "candidate_partition_log": float(partition_logs[i]),
                    "log_absolute_error": str(error),
                    "log_tolerance": str(tolerance),
                    "oracle_log": str(exact),
                    "checks": checks,
                    "tails": tails,
                }
            )
        checks = dict(oracle["checks"])
        if reflected is not None:
            checks.update({"reflected_" + key: value for key, value in reflected["checks"].items()})
        if group == "small":
            masses = np.exp(logs)
            checks.update(
                normalization=abs(masses.sum() - 1) <= 5e-12,
                mean=abs(np.dot(counts, masses) - float(reference.mean)) <= 5e-10,
                variance=abs(
                    np.dot((np.asarray(counts) - float(reference.mean)) ** 2, masses)
                    - float(reference.variance)
                )
                <= 5e-10,
            )
        if record is not None:
            record(
                {"event": "candidate_points", "case_id": case["case_id"], "points": points, "checks": checks}
            )
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            sample = law.sample_counts([n] * len(counts), seed=SEED)
        checks["sample_in_range_integer"] = bool(
            np.issubdtype(sample.dtype, np.integer) and np.all((sample >= 0) & (sample <= n))
        )
        checks["sample_seed_shape"] = bool(
            sample.shape == (1, len(counts))
            and np.array_equal(sample, law.sample_counts([n] * len(counts), seed=SEED))
        )
        passed = all(checks.values()) and all(all(point["checks"].values()) for point in points)
        oracle_pass = all(oracle["checks"].values()) and (
            reflected is None or all(reflected["checks"].values())
        )
        return {
            "status": "pass" if passed else "candidate_mismatch" if oracle_pass else "oracle_failure",
            "checks": {key: bool(value) for key, value in checks.items()},
            "oracle": oracle,
            "reflected_oracle": reflected,
            "points": points,
            "sample": sample.tolist(),
        }
