"""Optional GPU count-predictive parity tests (design §7, §8; #189)."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from genomeos.validation.predictive import MAX_COUNT, CountPredictive, predictive_diagnostics
from genomeos.validation.predictive_cupy import CuPyCDF

ROOT = Path(__file__).resolve().parents[1]
PROFILER = ROOT / "scripts" / "profile_count_scoring.py"
PROFILE_SPEC = importlib.util.spec_from_file_location("profile_count_scoring", PROFILER)
assert PROFILE_SPEC is not None and PROFILE_SPEC.loader is not None
PROFILE_MODULE = importlib.util.module_from_spec(PROFILE_SPEC)
PROFILE_SPEC.loader.exec_module(PROFILE_MODULE)


def _cupy_device_available() -> bool:
    if importlib.util.find_spec("cupy") is None:
        return False
    import cupy as cp

    try:
        return cp.cuda.runtime.getDeviceCount() > 0
    except cp.cuda.runtime.CUDARuntimeError:
        return False


GPU_AVAILABLE = _cupy_device_available()
requires_gpu = pytest.mark.skipif(not GPU_AVAILABLE, reason="requires a working CUDA device")


def _profile_command(out: Path) -> list[str]:
    return [
        sys.executable,
        str(PROFILER),
        "--draws",
        "8",
        "--observations",
        "2",
        "--an",
        "10",
        "--concentration",
        "3",
        "--repeats",
        "1",
        "--seed",
        "42",
        "--source-revision",
        "0123456789abcdef0123456789abcdef01234567",
        "--out",
        str(out),
    ]


def test_profiler_rejects_nonpositive_workload_before_cuda_access(tmp_path):
    """A zero-sized synthetic comparison is not valid performance evidence."""
    command = _profile_command(tmp_path / "run")
    command[command.index("--draws") + 1] = "0"

    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)

    assert completed.returncode == 2
    assert "positive integer" in completed.stderr


def test_profiler_refuses_an_existing_output_directory_before_cuda_access(tmp_path):
    """A profiler rerun must not overwrite or mingle immutable measurement evidence."""
    output = tmp_path / "run"
    output.mkdir()

    completed = subprocess.run(
        _profile_command(output), cwd=ROOT, capture_output=True, text=True, check=False
    )

    assert completed.returncode == 2
    assert "output directory already exists" in completed.stderr


def test_profiler_refuses_malformed_supplied_revision_before_cuda_access(tmp_path):
    """Source-only snapshots need a full explicit commit instead of invented provenance."""
    command = _profile_command(tmp_path / "run")
    command[command.index("--source-revision") + 1] = "not-a-commit"

    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)

    assert completed.returncode == 2
    assert "40-character hexadecimal commit" in completed.stderr


def test_profiler_missing_cuda_is_an_actionable_nonzero_failure(tmp_path):
    """Explicit GPU measurement cannot turn unavailable CUDA into an empty success report."""
    environment = os.environ.copy()
    environment["CUDA_VISIBLE_DEVICES"] = ""
    environment["PYTHONPATH"] = str(ROOT)

    completed = subprocess.run(
        _profile_command(tmp_path / "run"),
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 2
    assert "CUDA" in completed.stderr
    assert not (tmp_path / "run").exists()


def test_profiler_parity_fails_for_shifted_count_quantiles_with_equal_diagnostics():
    """Equal widths and observed coverage cannot conceal shifted integer endpoints."""
    frame = pd.DataFrame(
        {
            "log_score": [-1.0],
            "absolute_error": [0.1],
            "squared_error": [0.01],
            "coverage_50": [True],
            "interval_width_50": [0.2],
            "coverage_80": [True],
            "interval_width_80": [0.4],
            "coverage_95": [True],
            "interval_width_95": [0.6],
            "randomized_pit": [0.5],
        }
    )

    result = PROFILE_MODULE._parity(
        frame,
        frame.copy(),
        np.array([[1]]),
        np.array([[1]]),
        cpu_quantiles=np.array([[1], [3]]),
        gpu_quantiles=np.array([[2], [4]]),
    )

    assert result["count_quantiles_equal"] is False
    assert result["maximum_absolute_count_quantile_discrepancy"] == 1
    assert result["passed"] is False


def test_explicit_cupy_backend_does_not_silently_fall_back_when_cupy_is_missing(monkeypatch):
    """Removing CuPy must make an explicit GPU request fail rather than return a CPU result."""
    monkeypatch.setitem(sys.modules, "cupy", None)
    monkeypatch.setitem(sys.modules, "cupyx", None)
    predictive = CountPredictive(np.array([[0.2]]), cdf_backend="cupy")

    with pytest.raises(RuntimeError, match="CuPy.*required"):
        predictive.cdf(np.array([0]), np.array([2]))


def test_cpu_only_import_and_cdf_do_not_import_cupy():
    """Keeping the default backend must not import CuPy or initialize its CUDA runtime."""
    code = """
import sys
import numpy as np
from genomeos.validation.predictive import CountPredictive
assert "cupy" not in sys.modules
CountPredictive(np.array([[0.2]])).cdf([0], [2])
assert "cupy" not in sys.modules
"""

    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr


@pytest.mark.skipif(importlib.util.find_spec("cupy") is None, reason="requires CuPy package")
def test_explicit_cupy_backend_refuses_a_hidden_cuda_device():
    """A present CuPy wheel without a visible device is not permission to use SciPy instead."""
    environment = os.environ.copy()
    environment["CUDA_VISIBLE_DEVICES"] = ""
    environment["PYTHONPATH"] = str(ROOT)
    code = """
import numpy as np
from genomeos.validation.predictive import CountPredictive
try:
    CountPredictive(np.array([[0.2]]), cdf_backend="cupy").cdf([0], [2])
except RuntimeError as error:
    assert "CUDA device" in str(error), str(error)
else:
    raise AssertionError("hidden CUDA device did not fail")
"""

    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr


@pytest.mark.parametrize(
    ("mean_draws", "concentration", "message"),
    [
        (np.array([0.2, 0.3]), None, "two-dimensional"),
        (np.empty((0, 1)), None, "at least one"),
        (np.array([[0.2, np.nan]]), None, "finite"),
        (np.array([["0.2"]]), None, "numeric"),
        (np.array([[-0.1, 0.2]]), None, "between 0 and 1"),
        (np.array([[0.2, 1.1]]), None, "between 0 and 1"),
        (np.array([[0.2, 0.3]]), np.array([[2.0]]), "same shape"),
        (np.array([[0.2]]), np.array([[0.0]]), "positive"),
        (np.array([[0.2]]), np.array([[np.nan]]), "finite"),
        (np.array([[np.nextafter(0.0, 1.0)]]), np.array([[0.1]]), "beta-binomial shape"),
        (
            np.array([[np.nextafter(1.0, 0.0)]]),
            np.array([[np.nextafter(0.0, 1.0)]]),
            "beta-binomial shape",
        ),
        (np.array([[0.5]]), np.array([[np.finfo(float).max]]), "beta-binomial shape"),
    ],
)
def test_cupy_selection_preserves_all_predictive_parameter_refusals(
    mean_draws, concentration, message
):
    """Selecting the GPU CDF must not bypass the single CPU-side validation policy."""
    with pytest.raises(ValueError, match=message):
        CountPredictive(mean_draws, concentration=concentration, cdf_backend="cupy")


@pytest.mark.parametrize(
    ("method", "ac", "an", "message"),
    [
        ("log_prob", np.array([0.5]), np.array([2]), "integer"),
        ("log_prob", np.array([-1]), np.array([2]), "between 0 and AN"),
        ("log_prob", np.array([3]), np.array([2]), "between 0 and AN"),
        ("log_prob", np.array([np.nan]), np.array([2]), "finite"),
        ("log_prob", np.array(["0"]), np.array([2]), "numeric"),
        ("log_prob", np.array([0]), np.array([0]), "positive"),
        ("log_prob", np.array([0, 1]), np.array([2, 2]), "shape"),
        ("cdf", np.array([-2]), np.array([2]), "between -1 and AN"),
        ("cdf", np.array([3]), np.array([2]), "between -1 and AN"),
    ],
)
def test_cupy_selection_preserves_all_count_refusals(method, ac, an, message):
    """Invalid counts fail before optional-library or device access."""
    predictive = CountPredictive(np.array([[0.3]]), cdf_backend="cupy")

    with pytest.raises(ValueError, match=message):
        getattr(predictive, method)(ac=ac, an=an)


def test_cupy_selection_preserves_sampling_and_diagnostic_count_refusals():
    """CPU-resident helpers retain the same strict count contract under GPU CDF selection."""
    predictive = CountPredictive(np.array([[0.3]]), cdf_backend="cupy")

    with pytest.raises(ValueError, match="integer"):
        predictive.sample_counts(np.array([2.5]))
    with pytest.raises(ValueError, match="positive"):
        predictive.sample_counts(np.array([0]))
    with pytest.raises(ValueError, match="between 0 and AN"):
        predictive_diagnostics(predictive, ac=np.array([-1]), an=np.array([2]))


@requires_gpu
@pytest.mark.parametrize("concentration", [None, 20.0])
def test_gpu_complete_diagnostics_match_cpu_across_row_and_draw_chunks(concentration):
    """Wrong row/draw chunk accumulation changes complete interval and PIT outputs."""
    rng = np.random.default_rng(42)
    means = rng.uniform(0.01, 0.99, size=(257, 17))
    means[:, 0] = 0.0
    means[:, 1] = 1.0
    shape = None if concentration is None else np.full_like(means, concentration)
    an = np.array([1, 1, 2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47])
    ac = np.array([0, 1, 0, 3, 2, 1, 11, 5, 8, 19, 3, 14, 1, 30, 20, 0, 46])
    cpu = CountPredictive(means, concentration=shape, cdf_backend="scipy")
    gpu = CountPredictive(means, concentration=shape, cdf_backend="cupy")

    cpu_frame = predictive_diagnostics(cpu, ac, an, seed=123)
    gpu_frame = predictive_diagnostics(gpu, ac, an, seed=123)
    levels = np.array([0.025, 0.1, 0.25, 0.5, 0.75, 0.9, 0.975])

    np.testing.assert_array_equal(cpu.quantiles(an, levels), gpu.quantiles(an, levels))
    for column in ("coverage_50", "coverage_80", "coverage_95"):
        np.testing.assert_array_equal(cpu_frame[column], gpu_frame[column])
    for column in (
        "absolute_error",
        "squared_error",
        "interval_width_50",
        "interval_width_80",
        "interval_width_95",
    ):
        np.testing.assert_array_equal(cpu_frame[column], gpu_frame[column])
    pd.testing.assert_frame_equal(cpu_frame, gpu_frame, rtol=1e-9, atol=1e-11)
    np.testing.assert_array_equal(cpu.sample_counts(an, seed=456), gpu.sample_counts(an, seed=456))


@requires_gpu
@pytest.mark.parametrize("concentration", [None, 3.0])
def test_gpu_cdf_matches_cpu_at_count_boundaries_and_heterogeneous_denominators(concentration):
    """Boundary shortcuts and heterogeneous AN must stay aligned with the CPU oracle."""
    means = np.array(
        [
            [0.0, 1.0, 0.25, 0.75, 0.5, 0.1],
            [0.0, 1.0, 0.75, 0.25, 0.5, 0.9],
        ]
    )
    shape = None if concentration is None else np.full_like(means, concentration)
    ac = np.array([-1, 4, 0, 7, 10, 0])
    an = np.array([5, 5, 2, 7, 10, MAX_COUNT])
    cpu = CountPredictive(means, concentration=shape)
    gpu = CountPredictive(means, concentration=shape, cdf_backend="cupy")

    np.testing.assert_allclose(gpu.cdf(ac, an), cpu.cdf(ac, an), rtol=1e-9, atol=1e-11)


@requires_gpu
def test_gpu_beta_binomial_cdf_crosses_the_support_chunk_boundary():
    """Dropping or double-counting one support chunk changes this exact uniform CDF."""
    an = 8193
    predictive = CountPredictive(
        np.array([[0.5], [0.5]]),
        concentration=np.array([[2.0], [2.0]]),
        cdf_backend="cupy",
    )

    result = predictive.cdf(np.array([4096]), np.array([an]))

    assert result == pytest.approx(np.array([4097 / (an + 1)]), rel=1e-9, abs=1e-11)


@requires_gpu
def test_gpu_beta_binomial_cdf_preserves_the_analytic_tiny_lower_tail():
    """Cancellation must not erase the same nonzero tail protected by the CPU regression."""
    predictive = CountPredictive(
        np.array([[np.nextafter(1.0, 0.0)]]),
        concentration=np.array([[1.0 / np.sqrt(np.finfo(float).eps)]]),
        cdf_backend="cupy",
    )

    result = predictive.cdf(np.array([1]), np.array([2]))

    assert result == pytest.approx(
        np.array([2.220446032706701e-16]), rel=1e-9, abs=0.0
    )


@requires_gpu
@pytest.mark.parametrize(
    ("mean", "concentration", "count", "an"),
    [(1e-11, 5000.0, 0, 2), (1e-11, 8000.0, 1, 352), (0.0014, 6400.0, 6, 52)],
)
def test_gpu_near_one_short_lower_tail_matches_repaired_cpu_cdf(
    mean, concentration, count, an
):
    """The GPU must pivot to the small-probability complement before near-one cancellation."""
    means = np.array([[mean]])
    concentrations = np.array([[concentration]])
    cpu = CountPredictive(means, concentrations)
    gpu = CountPredictive(means, concentrations, cdf_backend="cupy")

    np.testing.assert_allclose(gpu.cdf([count], [an]), cpu.cdf([count], [an]), rtol=2e-14, atol=0.0)


@requires_gpu
def test_gpu_refuses_invalid_fallback_component_before_cancellation(monkeypatch):
    """A negative draw CDF can cancel in the mixture and evade aggregate validation."""
    evaluator = CuPyCDF(np.array([[0.2], [0.3]]), np.ones((2, 1)))
    cp = evaluator._cp
    calls = 0

    def injected_tail(*args):
        nonlocal calls
        calls += 1
        if calls == 1:
            return cp.asarray([[np.log(0.25), np.log(1.5)]])
        return cp.asarray([[np.log(0.25), np.log1p(0.25)]])

    monkeypatch.setattr(evaluator, "_tail_logsum", injected_tail)

    with pytest.raises(FloatingPointError, match="component"):
        evaluator(np.array([[0]]), np.array([2]))


@requires_gpu
def test_gpu_refuses_nan_cdf_component_before_accumulation(monkeypatch):
    """A non-finite draw must be refused at its source rather than only after averaging."""
    evaluator = CuPyCDF(np.array([[0.2], [0.3]]), np.ones((2, 1)))
    cp = evaluator._cp
    monkeypatch.setattr(
        evaluator,
        "_tail_logsum",
        lambda *args: cp.asarray([[np.log(0.25), cp.nan]]),
    )

    with pytest.raises(FloatingPointError, match="component"):
        evaluator(np.array([[0]]), np.array([2]))


@requires_gpu
def test_gpu_exact_boundaries_override_irrelevant_invalid_tail_components(monkeypatch):
    """Exact probability and count boundaries must be assigned before component validation."""
    evaluator = CuPyCDF(np.array([[0.0], [1.0]]), np.ones((2, 1)))
    cp = evaluator._cp
    monkeypatch.setattr(
        evaluator,
        "_tail_logsum",
        lambda *args: cp.full((1, 2), cp.nan, dtype=cp.float64),
    )

    np.testing.assert_array_equal(
        evaluator(np.array([[-1], [2]]), np.array([2])),
        np.array([[0.0], [1.0]]),
    )


@requires_gpu
def test_gpu_quantile_tie_is_reported_without_relaxing_exact_endpoint_parity():
    """The exact half-mass tie must retain the left-continuous endpoint on both backends."""
    means = np.array([[0.0], [1.0]])
    cpu = CountPredictive(means)
    gpu = CountPredictive(means, cdf_backend="cupy")

    cpu_frame = predictive_diagnostics(cpu, np.array([0]), np.array([1]), seed=42)
    gpu_frame = predictive_diagnostics(gpu, np.array([0]), np.array([1]), seed=42)
    levels = np.array([0.25, 0.5, 0.75])

    np.testing.assert_array_equal(cpu.quantiles([1], levels), np.array([[0], [0], [1]]))
    np.testing.assert_array_equal(cpu.quantiles([1], levels), gpu.quantiles([1], levels))
    np.testing.assert_array_equal(
        cpu_frame[["coverage_50", "interval_width_50"]],
        gpu_frame[["coverage_50", "interval_width_50"]],
    )
    assert cpu.cdf([0], [1])[0] == gpu.cdf([0], [1])[0] == 0.5


@requires_gpu
@pytest.mark.parametrize("concentration", [None, 20.0])
def test_gpu_one_hundred_percent_quantiles_use_exact_mixed_support(concentration):
    """Both backends must use actual support despite CDF rounding at the 100% level."""
    means = np.array([[0.0, 1.0, 0.1, 0.0], [0.0, 1.0, 0.5, 0.1]])
    shape = None if concentration is None else np.full_like(means, concentration)
    an = [100, 100, 1000, 100]
    for backend in ["scipy", "cupy"]:
        predictive = CountPredictive(means, shape, cdf_backend=backend)
        np.testing.assert_array_equal(predictive.quantiles(an, [1.0]), [[0, 100, 1000, 100]])


@requires_gpu
def test_gpu_diagnostics_preserve_stable_near_degenerate_log_score():
    """GPU CDF selection must compose with the analytically correct CPU scoring path."""
    means, concentration = np.full((3, 1), 1e-16), np.full((3, 1), 1e6)
    cpu = predictive_diagnostics(CountPredictive(means, concentration), [0], [1])
    gpu = predictive_diagnostics(
        CountPredictive(means, concentration, cdf_backend="cupy"), [0], [1]
    )
    np.testing.assert_allclose(gpu["log_score"], [np.log1p(-1e-16)], rtol=2e-14, atol=0.0)
    pd.testing.assert_frame_equal(cpu, gpu, rtol=1e-9, atol=1e-11)
