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
from scripts.count_recurrence_oracle import verified_law

SEED = 42


def mixture(backend: str, xp: Any, record=lambda evidence: None) -> dict:
    means = np.broadcast_to(np.tile([0.05, 0.5, 0.95], 43)[:, None], (129, 5)).copy()
    means[0, 0], means[1, 1] = 0, 1
    concentrations = np.broadcast_to(np.tile([2.0, 1e12, 134217728.0], 43)[:, None], means.shape)
    an = np.array([2, 3, 20, 64, 1025])
    ac = an // 2
    law = CountPredictive(means, concentrations, cdf_backend=backend)
    expected = []
    for j, (n, k) in enumerate(zip(an, ac, strict=True)):
        values = []
        for p, c in zip(means[:, j], concentrations[:, j], strict=True):
            values.append(
                1.0
                if p == 0
                else 0.0
                if p == 1
                else float(verified_law(int(n), float(p), float(c), (int(k),)).lower[0])
            )
        expected.append(np.mean(values))
    actual = law.cdf(ac, an)
    record(
        {
            "stage": "mixture_cdf",
            "cdf": actual,
            "oracle_cdf": expected,
            "mean": means,
            "concentration": concentrations,
            "ac": ac,
            "an": an,
        }
    )
    np.testing.assert_allclose(actual, expected, rtol=1e-9, atol=1e-11)
    interior_means = np.where((means.T > 0) & (means.T < 1), means.T, 0.5)
    arguments = [xp.asarray(item) for item in (interior_means, concentrations.T, an[:, None], ac[:, None])]
    original = recurrence.SUPPORT_CHUNK_SIZE
    try:
        parts = recurrence.beta_binomial_log_partitions(*arguments, array_module=xp, max_count=1025)
        recurrence.SUPPORT_CHUNK_SIZE = 257
        alternate = recurrence.beta_binomial_log_partitions(*arguments, array_module=xp, max_count=1025)
    finally:
        recurrence.SUPPORT_CHUNK_SIZE = original
    pairs = [(parts.log_mass(array_module=xp), alternate.log_mass(array_module=xp))]
    pairs.extend(zip(parts.tails(array_module=xp), alternate.tails(array_module=xp), strict=True))
    for index, (first, second) in enumerate(pairs):
        if backend == "cupy":
            first, second = xp.asnumpy(first), xp.asnumpy(second)
        record({"stage": "chunks", "partition": index, "first": first, "second": second})
        np.testing.assert_allclose(
            first, second, rtol=0 if index == 0 else 1e-9, atol=5e-10 if index == 0 else 1e-11
        )
    samples = law.sample_counts(an, seed=SEED)
    record({"stage": "count_draws", "sample": samples})
    assert samples[0, 0] == 0 and samples[1, 1] == an[1]
    np.testing.assert_array_equal(samples, law.sample_counts(an, seed=SEED))
    frame = predictive_diagnostics(law, ac, an, seed=SEED)
    record({"stage": "diagnostics", "frame": frame.to_dict(orient="list")})
    pd.testing.assert_frame_equal(frame, predictive_diagnostics(law, ac, an, seed=SEED))
    return {
        "cdf": actual.tolist(),
        "oracle_cdf": expected,
        "sample": samples.tolist(),
        "diagnostics": frame.to_dict(orient="list"),
        "chunks": [original, 257],
    }


def quantiles_and_diagnostics(backend: str, xp: Any, record=lambda evidence: None) -> dict:
    del xp
    ties = []
    for n, c in [(1, 1e300), (4097, 1e300), (4097, 2.0)]:
        law = CountPredictive(np.array([[0.5]]), np.array([[c]]), cdf_backend=backend)
        record(
            {
                "stage": "analytical_ties",
                "an": n,
                "concentration": c,
                "cdf": law.cdf([n // 2], [n]),
                "quantiles": law.quantiles([n], [0.5, 1]),
            }
        )
        assert law.cdf([n // 2], [n])[0] == 0.5
        assert law.quantiles([n], [0.5])[0, 0] == n // 2
        assert law.quantiles([n], [1])[0, 0] == n
        ties.append([n, c, n // 2])
    for draws in (128, 129):
        law = CountPredictive(np.full((draws, 1), 0.5), np.full((draws, 1), 2.0), cdf_backend=backend)
        levels = np.array([1, 4, 7, 13, 21]) / 21
        record(
            {
                "stage": "uniform_mixture",
                "draws": draws,
                "levels": levels,
                "quantiles": law.quantiles([20], levels),
            }
        )
        np.testing.assert_array_equal(law.quantiles([20], levels)[:, 0], [0, 3, 6, 12, 20])
    n, p, c, k = 20, 0.05, 134217728.0, 1
    reference = verified_law(n, p, c, tuple(range(n + 1)))
    lower = np.array([float(value) for value in reference.lower])
    levels = np.array([0.025, 0.1, 0.25, 0.5, 0.75, 0.9, 0.975])
    quantiles = np.searchsorted(lower, levels)
    assert np.all(lower[quantiles] > levels)
    assert all(q == 0 or lower[q - 1] < level for q, level in zip(quantiles, levels, strict=True))
    law = CountPredictive(np.array([[p]]), np.array([[c]]), cdf_backend=backend)
    np.testing.assert_array_equal(law.quantiles([n], levels)[:, 0], quantiles)
    frame = predictive_diagnostics(law, [k], [n], seed=SEED)
    record(
        {
            "stage": "strict_brackets",
            "levels": levels,
            "quantiles": quantiles,
            "oracle_lower": lower,
            "frame": frame.to_dict(orient="list"),
        }
    )
    expected = {
        "log_score": float(reference.log_mass[k]),
        "absolute_error": abs(quantiles[3] / n - k / n),
        "squared_error": (p - k / n) ** 2,
    }
    for level, lo, hi in [(50, 2, 4), (80, 1, 5), (95, 0, 6)]:
        expected[f"coverage_{level}"] = bool(quantiles[lo] <= k <= quantiles[hi])
        expected[f"interval_width_{level}"] = (quantiles[hi] - quantiles[lo]) / n
    expected["randomized_pit"] = lower[k - 1] + np.random.default_rng(SEED).uniform() * float(
        reference.log_mass[k].exp()
    )
    assert list(frame) == list(expected)
    np.testing.assert_allclose(
        frame.iloc[0].to_numpy(dtype=float), list(expected.values()), rtol=1e-9, atol=1e-11
    )
    pd.testing.assert_frame_equal(frame, predictive_diagnostics(law, [k], [n], seed=SEED))
    return {
        "ties": ties,
        "quantiles": quantiles.tolist(),
        "levels": levels.tolist(),
        "diagnostics": frame.to_dict(orient="list"),
        "expected": expected,
    }


def sampler(backend: str, xp: Any, record=lambda evidence: None) -> dict:
    del xp
    outcomes = []
    for p, c in [(0.05, 134217728.0), (0.5, 1e300), (0.95, 134217728.0)]:
        n, size = 64, 20000
        reference = verified_law(n, p, c, (0, n))
        law = CountPredictive(np.full((size, 1), p), np.full((size, 1), c), cdf_backend=backend)
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            sample = law.sample_counts([n], seed=SEED)
        record({"stage": "sample", "p": p, "c": c, "n": n, "seed": SEED, "sample": sample})
        np.testing.assert_array_equal(sample, law.sample_counts([n], seed=SEED))
        assert sample.shape == (size, 1) and np.issubdtype(sample.dtype, np.integer)
        assert np.all((sample >= 0) & (sample <= n))
        variance, fourth = float(reference.variance), float(reference.fourth_central)
        mean_se = np.sqrt(variance / size)
        variance_se = np.sqrt((fourth - ((size - 3) / (size - 1)) * variance**2) / size)
        outcomes.append(
            {
                "p": p,
                "c": c,
                "size": size,
                "mean": float(sample.mean()),
                "variance": float(sample.var(ddof=1)),
                "oracle_mean": str(reference.mean),
                "oracle_variance": str(reference.variance),
                "oracle_fourth": str(reference.fourth_central),
                "mean_se": mean_se,
                "variance_se": variance_se,
                "mean_passed": bool(abs(sample.mean() - float(reference.mean)) <= 6 * mean_se),
                "variance_passed": bool(abs(sample.var(ddof=1) - variance) <= 6 * variance_se),
            }
        )
    return {
        "outcomes": outcomes,
        "seed": SEED,
        "passed": all(row["mean_passed"] and row["variance_passed"] for row in outcomes),
        "limitation": "Latent variation below floating resolution cannot distinguish the limit.",
    }


def domain(backend: str, xp: Any, record=lambda evidence: None) -> dict:
    del xp
    refusals = []

    def refuse(name, operation):
        try:
            operation()
        except (ValueError, TypeError) as error:
            refusals.append({"case": name, "message": str(error)})
            record(refusals[-1])
        else:
            raise AssertionError(f"expected refusal: {name}")

    for c in (67108864.0, np.nextafter(67108864.0, np.inf), 1e300):
        law = CountPredictive(np.array([[0.5]]), np.array([[c]]), cdf_backend=backend)
        assert np.isfinite(law.log_prob([0], [1])[0])
        assert law.cdf([0], [1])[0] == 0.5
    for p, c in [
        (0.5, np.nextafter(1e300, np.inf)),
        (-0.1, 2),
        (np.nan, 2),
        (0.5, 0),
        (0.5, np.inf),
        (np.nextafter(0.0, 1.0), 1e-10),
    ]:
        refuse(
            f"parameter:{p}:{c}",
            lambda p=p, c=c: CountPredictive(np.array([[p]]), np.array([[c]]), cdf_backend=backend),
        )
    law = CountPredictive(np.array([[0.5]]), np.array([[1e300]]), cdf_backend=backend)
    for ac, an in [(-1, 20), (21, 20), (0.5, 20), (0, 0), (0, 2**31)]:
        refuse(f"counts:{ac}:{an}", lambda ac=ac, an=an: law.log_prob([ac], [an]))
    for name, call in [
        ("mass", lambda: law.log_prob([0], [65537])),
        ("cdf_lower", lambda: law.cdf([-1], [65537])),
        ("cdf_upper", lambda: law.cdf([65537], [65537])),
        ("quantile", lambda: law.quantiles([65537], [0, 1])),
        ("sample", lambda: law.sample_counts([65537])),
    ]:
        refuse(name, call)
    low = CountPredictive(np.array([[0.5]]), np.array([[20.0]]), cdf_backend=backend)
    assert low.cdf([-1], [2**31 - 1])[0] == 0
    assert low.cdf([2**31 - 1], [2**31 - 1])[0] == 1
    assert low.sample_counts([2**31 - 1]).shape == (1, 1)
    degenerate = CountPredictive(np.array([[0.0, 1.0]]), np.array([[1e301, 1e301]]), cdf_backend=backend)
    np.testing.assert_array_equal(degenerate.sample_counts([65537, 65537]), [[0, 65537]])
    if backend == "scipy":
        assert "cupy" not in sys.modules, "CPU validation imported CUDA"
    return {"refusals": refusals, "cpu_cuda_import_absent": backend == "scipy"}


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
