"""Synthetic full-interface controls for offline count validation (design §7, §8).

These fixed controls complement pointwise oracle checks. All stochastic checks use seed42;
sampling cannot distinguish finite concentration from its limit below floating resolution.
"""

from __future__ import annotations

import subprocess
import sys
import warnings
from typing import Any

import numpy as np
import pandas as pd

from genomeos.validation import count_recurrence as recurrence
from genomeos.validation.predictive import CountPredictive, predictive_diagnostics
from scripts.count_recurrence_control_plan import execute_subcases, subcase
from scripts.count_recurrence_oracle import verified_law

SEED = 42


TIES = [(1, 1e300), (4097, 1e300), (4097, 2.0)]
SAMPLERS = [(0.05, 134217728.0), (0.5, 1e300), (0.95, 134217728.0)]
SEAMS = (67108864.0, np.nextafter(67108864.0, np.inf), 1e300)
INVALID_PARAMETERS = [
    (0.5, np.nextafter(1e300, np.inf)),
    (-0.1, 2),
    (np.nan, 2),
    (0.5, 0),
    (0.5, np.inf),
    (np.nextafter(0.0, 1.0), 1e-10),
]
INVALID_COUNTS = [(-1, 20), (21, 20), (0.5, 20), (0, 0), (0, 2**31)]


def mixture(backend: str, xp: Any, record=lambda evidence: None) -> dict:
    state = {}

    def setup():
        means = np.broadcast_to(np.tile([0.05, 0.5, 0.95], 43)[:, None], (129, 5)).copy()
        means[0, 0], means[1, 1] = 0, 1
        concentrations = np.broadcast_to(np.tile([2.0, 1e12, 134217728.0], 43)[:, None], means.shape)
        an = np.array([2, 3, 20, 64, 1025])
        ac = an // 2
        state.update(
            means=means,
            concentrations=concentrations,
            an=an,
            ac=ac,
            law=CountPredictive(means, concentrations, cdf_backend=backend),
        )
        return {"mean": means, "concentration": concentrations, "an": an, "ac": ac}

    def cdf():
        expected = []
        for j, (n, k) in enumerate(zip(state["an"], state["ac"], strict=True)):
            values = [
                1.0
                if p == 0
                else 0.0
                if p == 1
                else float(verified_law(int(n), float(p), float(c), (int(k),)).lower[0])
                for p, c in zip(state["means"][:, j], state["concentrations"][:, j], strict=True)
            ]
            expected.append(np.mean(values))
        actual = state["law"].cdf(state["ac"], state["an"])
        evidence = {"cdf": actual, "oracle_cdf": expected}
        record({"stage": "mixture_cdf", **evidence})
        np.testing.assert_allclose(actual, expected, rtol=1e-9, atol=1e-11)
        return evidence

    def chunks(size):
        means = state["means"].T
        interior = np.where((means > 0) & (means < 1), means, 0.5)
        arguments = [
            xp.asarray(item)
            for item in (interior, state["concentrations"].T, state["an"][:, None], state["ac"][:, None])
        ]
        original = recurrence.SUPPORT_CHUNK_SIZE
        try:
            recurrence.SUPPORT_CHUNK_SIZE = size
            state[size] = recurrence.beta_binomial_log_partitions(*arguments, array_module=xp, max_count=1025)
        finally:
            recurrence.SUPPORT_CHUNK_SIZE = original
        return {"chunk_size": size}

    def compare(index):
        values = []
        for size in (1024, 257):
            parts = state[size]
            value = parts.log_mass(array_module=xp) if index == 0 else parts.tails(array_module=xp)[index - 1]
            values.append(xp.asnumpy(value) if backend == "cupy" else value)
        evidence = {"partition": index, "first": values[0], "second": values[1]}
        record({"stage": "chunks", **evidence})
        np.testing.assert_allclose(
            *values, rtol=0 if index == 0 else 1e-9, atol=5e-10 if index == 0 else 1e-11
        )
        return evidence

    def sample():
        state["sample"] = state["law"].sample_counts(state["an"], seed=SEED)
        return {"sample": state["sample"]}

    def endpoints():
        assert state["sample"][0, 0] == 0 and state["sample"][1, 1] == state["an"][1]
        return {"degenerate_endpoints": True}

    def sample_repeat():
        np.testing.assert_array_equal(state["sample"], state["law"].sample_counts(state["an"], seed=SEED))
        return {"deterministic_seed": SEED}

    def diagnostics():
        state["frame"] = predictive_diagnostics(state["law"], state["ac"], state["an"], seed=SEED)
        return {"frame": state["frame"].to_dict(orient="list")}

    def frame_repeat():
        pd.testing.assert_frame_equal(
            state["frame"], predictive_diagnostics(state["law"], state["ac"], state["an"], seed=SEED)
        )
        return {"deterministic_seed": SEED}

    actions = {
        "setup": setup,
        "mixture_cdf": cdf,
        "chunk_default": lambda: chunks(1024),
        "chunk_257": lambda: chunks(257),
        "chunk_log_mass": lambda: compare(0),
        "chunk_lower": lambda: compare(1),
        "chunk_upper": lambda: compare(2),
        "sample_counts": sample,
        "sample_endpoints": endpoints,
        "sample_determinism": sample_repeat,
        "diagnostics": diagnostics,
        "diagnostic_determinism": frame_repeat,
    }
    return execute_subcases(CONTROL_SUBCASES["mixture_chunk_boundaries"], actions, record)


def quantiles_and_diagnostics(backend: str, xp: Any, record=lambda evidence: None) -> dict:
    del xp
    state = {}

    def tie(n, c, operation):
        law = CountPredictive(np.array([[0.5]]), np.array([[c]]), cdf_backend=backend)
        actual = (
            law.cdf([n // 2], [n])[0]
            if operation == "cdf"
            else law.quantiles([n], [0.5 if operation == "median" else 1])[0, 0]
        )
        expected = 0.5 if operation == "cdf" else n // 2 if operation == "median" else n
        record(
            {
                "stage": "analytical_tie",
                "an": n,
                "concentration": c,
                "operation": operation,
                "actual": actual,
                "expected": expected,
            }
        )
        assert actual == expected
        return {"actual": actual, "expected": expected}

    def uniform(draws):
        law = CountPredictive(np.full((draws, 1), 0.5), np.full((draws, 1), 2.0), cdf_backend=backend)
        levels = np.array([1, 4, 7, 13, 21]) / 21
        actual = law.quantiles([20], levels)[:, 0]
        record({"stage": "uniform_mixture", "draws": draws, "levels": levels, "quantiles": actual})
        np.testing.assert_array_equal(actual, [0, 3, 6, 12, 20])
        return {"levels": levels, "quantiles": actual}

    def reference():
        n, p, c, k = 20, 0.05, 134217728.0, 1
        oracle = verified_law(n, p, c, tuple(range(n + 1)))
        lower = np.array([float(value) for value in oracle.lower])
        levels = np.array([0.025, 0.1, 0.25, 0.5, 0.75, 0.9, 0.975])
        state.update(
            n=n,
            p=p,
            k=k,
            oracle=oracle,
            lower=lower,
            levels=levels,
            quantiles=np.searchsorted(lower, levels),
            law=CountPredictive(np.array([[p]]), np.array([[c]]), cdf_backend=backend),
        )
        return {"lower": lower, "levels": levels, "quantiles": state["quantiles"]}

    def brackets():
        lower, levels, quantiles = (state[key] for key in ("lower", "levels", "quantiles"))
        assert np.all(lower[quantiles] > levels)
        assert all(q == 0 or lower[q - 1] < level for q, level in zip(quantiles, levels, strict=True))
        return {"strict_brackets": True}

    def quantiles():
        actual = state["law"].quantiles([state["n"]], state["levels"])[:, 0]
        record({"stage": "strict_quantiles", "actual": actual, "expected": state["quantiles"]})
        np.testing.assert_array_equal(actual, state["quantiles"])
        return {"quantiles": actual}

    def frame():
        state["frame"] = predictive_diagnostics(state["law"], [state["k"]], [state["n"]], seed=SEED)
        return {"frame": state["frame"].to_dict(orient="list")}

    def frame_values():
        n, p, k, oracle, qs, lower = (state[key] for key in ("n", "p", "k", "oracle", "quantiles", "lower"))
        expected = {
            "log_score": float(oracle.log_mass[k]),
            "absolute_error": abs(qs[3] / n - k / n),
            "squared_error": (p - k / n) ** 2,
        }
        for level, lo, hi in [(50, 2, 4), (80, 1, 5), (95, 0, 6)]:
            expected[f"coverage_{level}"] = bool(qs[lo] <= k <= qs[hi])
            expected[f"interval_width_{level}"] = (qs[hi] - qs[lo]) / n
        expected["randomized_pit"] = lower[k - 1] + np.random.default_rng(SEED).uniform() * float(
            oracle.log_mass[k].exp()
        )
        record({"stage": "diagnostics_expected", "expected": expected})
        assert list(state["frame"]) == list(expected)
        np.testing.assert_allclose(
            state["frame"].iloc[0].to_numpy(dtype=float), list(expected.values()), rtol=1e-9, atol=1e-11
        )
        return {"expected": expected}

    def frame_repeat():
        pd.testing.assert_frame_equal(
            state["frame"], predictive_diagnostics(state["law"], [state["k"]], [state["n"]], seed=SEED)
        )
        return {"deterministic_seed": SEED}

    actions = {
        f"tie:{i}:{operation}": lambda n=n, c=c, operation=operation: tie(n, c, operation)
        for i, (n, c) in enumerate(TIES)
        for operation in ("cdf", "median", "level_one")
    }
    actions.update({f"uniform:{draws}": lambda draws=draws: uniform(draws) for draws in (128, 129)})
    actions.update(
        strict_reference=reference,
        strict_brackets=brackets,
        strict_quantiles=quantiles,
        diagnostic_frame=frame,
        diagnostic_values=frame_values,
        diagnostic_determinism=frame_repeat,
    )
    return execute_subcases(CONTROL_SUBCASES["quantile_diagnostics"], actions, record)


def sampler(backend: str, xp: Any, record=lambda evidence: None) -> dict:
    del xp
    states = {}

    def sample(index):
        p, c = SAMPLERS[index]
        n, size = 64, 20000
        oracle = verified_law(n, p, c, (0, n))
        law = CountPredictive(np.full((size, 1), p), np.full((size, 1), c), cdf_backend=backend)
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            values = law.sample_counts([n], seed=SEED)
        states[index] = (oracle, law, values)
        return {
            "p": p,
            "c": c,
            "n": n,
            "size": size,
            "seed": SEED,
            "sample": values,
            "limitation": "Latent variation below floating resolution cannot distinguish the limit.",
        }

    def check(index, operation):
        oracle, law, values = states[index]
        size, n = 20000, 64
        if operation == "determinism":
            np.testing.assert_array_equal(values, law.sample_counts([n], seed=SEED))
            return {"deterministic_seed": SEED}
        if operation == "shape_range":
            assert values.shape == (size, 1) and np.issubdtype(values.dtype, np.integer)
            assert np.all((values >= 0) & (values <= n))
            return {"shape": values.shape, "dtype": str(values.dtype)}
        variance, fourth = float(oracle.variance), float(oracle.fourth_central)
        mean_se = np.sqrt(variance / size)
        variance_se = np.sqrt((fourth - ((size - 3) / (size - 1)) * variance**2) / size)
        passed = (
            abs(values.mean() - float(oracle.mean)) <= 6 * mean_se
            if operation == "mean"
            else abs(values.var(ddof=1) - variance) <= 6 * variance_se
        )
        return {
            "mean": float(values.mean()),
            "variance": float(values.var(ddof=1)),
            "oracle_mean": str(oracle.mean),
            "oracle_variance": str(oracle.variance),
            "oracle_fourth": str(oracle.fourth_central),
            "mean_se": mean_se,
            "variance_se": variance_se,
            "passed": bool(passed),
        }

    actions = {}
    for index in range(len(SAMPLERS)):
        actions[f"sample:{index}"] = lambda index=index: sample(index)
        for operation in ("determinism", "shape_range", "mean", "variance"):
            actions[f"sample:{index}:{operation}"] = lambda index=index, operation=operation: check(
                index, operation
            )
    return execute_subcases(CONTROL_SUBCASES["sampler_moments"], actions, record)


def domain(backend: str, xp: Any, record=lambda evidence: None) -> dict:
    del xp

    def law(p=0.5, c=1e300):
        return CountPredictive(np.array([[p]]), np.array([[c]]), cdf_backend=backend)

    def refusal(operation):
        try:
            operation()
        except (ValueError, TypeError) as error:
            return {"message": str(error)}
        raise AssertionError("expected domain refusal")

    def seam(c, operation):
        actual = law(c=c).log_prob([0], [1])[0] if operation == "mass" else law(c=c).cdf([0], [1])[0]
        assert np.isfinite(actual) if operation == "mass" else actual == 0.5
        return {"concentration": c, "actual": actual}

    def low_scope(operation):
        low = law(c=20.0)
        if operation == "sample":
            actual = low.sample_counts([2**31 - 1])
            assert actual.shape == (1, 1)
        else:
            actual = low.cdf([-1 if operation == "lower" else 2**31 - 1], [2**31 - 1])
            assert actual[0] == (0 if operation == "lower" else 1)
        return {"actual": actual}

    def degenerate():
        model = CountPredictive(np.array([[0.0, 1.0]]), np.array([[1e301, 1e301]]), cdf_backend=backend)
        actual = model.sample_counts([65537, 65537])
        np.testing.assert_array_equal(actual, [[0, 65537]])
        return {"sample": actual}

    def cpu_import():
        if backend == "scipy":
            assert "cupy" not in sys.modules, "CPU validation imported CUDA"
        return {"applicable": backend == "scipy", "cpu_cuda_import_absent": "cupy" not in sys.modules}

    actions = {
        f"seam:{index}:{operation}": lambda c=c, operation=operation: seam(c, operation)
        for index, c in enumerate(SEAMS)
        for operation in ("mass", "cdf")
    }
    actions.update(
        {
            f"invalid_parameter:{index}": lambda p=p, c=c: refusal(lambda: law(p, c))
            for index, (p, c) in enumerate(INVALID_PARAMETERS)
        }
    )
    actions.update(
        {
            f"invalid_counts:{index}": lambda ac=ac, an=an: refusal(lambda: law().log_prob([ac], [an]))
            for index, (ac, an) in enumerate(INVALID_COUNTS)
        }
    )
    for name, operation in {
        "mass": lambda: law().log_prob([0], [65537]),
        "cdf_lower": lambda: law().cdf([-1], [65537]),
        "cdf_upper": lambda: law().cdf([65537], [65537]),
        "quantile": lambda: law().quantiles([65537], [0, 1]),
        "sample": lambda: law().sample_counts([65537]),
    }.items():
        actions[f"high_count:{name}"] = lambda operation=operation: refusal(operation)
    actions.update(
        {
            f"low_scope:{operation}": lambda operation=operation: low_scope(operation)
            for operation in ("lower", "upper", "sample")
        }
    )
    actions.update(degenerate_scope=degenerate, cpu_import=cpu_import)
    return execute_subcases(CONTROL_SUBCASES["domain_seams"], actions, record)


def unavailable_backend(backend: str, xp: Any, record=lambda evidence: None) -> dict:
    """An isolated import denial proves explicit backend requests cannot fall back."""
    del backend, xp
    code = """
import importlib.abc
import sys
import numpy as np
from genomeos.validation.predictive import CountPredictive
assert "cupy" not in sys.modules
class DenyCuPy(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "cupy" or fullname.startswith("cupy."):
            raise ImportError("explicit unavailable-backend control")
sys.meta_path.insert(0, DenyCuPy())
law = CountPredictive(np.array([[0.5]]), np.array([[1e300]]), cdf_backend="cupy")
try:
    law.cdf([1], [2])
except RuntimeError as error:
    print(type(error).__name__ + ": " + str(error))
else:
    raise AssertionError("CuPy request silently fell back")
"""
    completed = subprocess.run(
        [sys.executable, "-c", code], text=True, capture_output=True, timeout=60, check=False
    )
    record({"stdout": completed.stdout, "stderr": completed.stderr, "returncode": completed.returncode})
    if completed.returncode:
        raise AssertionError(completed.stdout + completed.stderr)
    return {
        "command": [sys.executable, "-c", code],
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "returncode": completed.returncode,
    }


CONTROLS = {
    "mixture_chunk_boundaries": mixture,
    "quantile_diagnostics": quantiles_and_diagnostics,
    "sampler_moments": sampler,
    "domain_seams": domain,
    "explicit_unavailable_backend": unavailable_backend,
}


CONTROL_SUBCASES = {
    "mixture_chunk_boundaries": [
        subcase("setup"),
        subcase("mixture_cdf", "setup"),
        subcase("chunk_default", "setup"),
        subcase("chunk_257", "setup"),
        *[
            subcase(name, "chunk_default", "chunk_257")
            for name in ("chunk_log_mass", "chunk_lower", "chunk_upper")
        ],
        subcase("sample_counts", "setup"),
        subcase("sample_endpoints", "sample_counts"),
        subcase("sample_determinism", "sample_counts"),
        subcase("diagnostics", "setup"),
        subcase("diagnostic_determinism", "diagnostics"),
    ],
    "quantile_diagnostics": [
        *[
            subcase(f"tie:{index}:{operation}")
            for index in range(len(TIES))
            for operation in ("cdf", "median", "level_one")
        ],
        *[subcase(f"uniform:{draws}") for draws in (128, 129)],
        subcase("strict_reference"),
        subcase("strict_brackets", "strict_reference"),
        subcase("strict_quantiles", "strict_brackets"),
        subcase("diagnostic_frame", "strict_reference"),
        subcase("diagnostic_values", "strict_brackets", "diagnostic_frame"),
        subcase("diagnostic_determinism", "diagnostic_frame"),
    ],
    "sampler_moments": [
        item
        for index in range(len(SAMPLERS))
        for item in (
            subcase(f"sample:{index}"),
            subcase(f"sample:{index}:determinism", f"sample:{index}"),
            subcase(f"sample:{index}:shape_range", f"sample:{index}"),
            subcase(f"sample:{index}:mean", f"sample:{index}:shape_range"),
            subcase(f"sample:{index}:variance", f"sample:{index}:shape_range"),
        )
    ],
    "domain_seams": [
        *[
            subcase(f"seam:{index}:{operation}")
            for index in range(len(SEAMS))
            for operation in ("mass", "cdf")
        ],
        *[subcase(f"invalid_parameter:{index}") for index in range(len(INVALID_PARAMETERS))],
        *[subcase(f"invalid_counts:{index}") for index in range(len(INVALID_COUNTS))],
        *[subcase(f"high_count:{name}") for name in ("mass", "cdf_lower", "cdf_upper", "quantile", "sample")],
        *[subcase(f"low_scope:{name}") for name in ("lower", "upper", "sample")],
        subcase("degenerate_scope"),
        subcase("cpu_import"),
    ],
    "explicit_unavailable_backend": [subcase("operation")],
}
