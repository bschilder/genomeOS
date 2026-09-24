"""Optional float64 CuPy CDF evaluation for count predictions (design §7, §8; #189).

This module is a numerical backend for ``CountPredictive`` and ``ActivityCountPredictive``. It
receives already validated, host-resident draw and count arrays through public typed interfaces;
validation policy remains owned by their predictive modules. CuPy is imported only when a GPU
evaluator is explicitly constructed, and a missing library or CUDA device is an error rather than
a CPU fallback.

High-concentration beta-binomial queries through ``AN=65_536`` use the shared complete-support
scaled-probability core. Lower-concentration draws and larger denominators retain exact finite tail
sums, pivoting at probability one half so subtraction uses the directly summed smaller tail.
Query, draw, and support batches are chosen from current free device memory using a conservative
peak-byte model and fixed caps. No array dimension depends on the complete allele-number support.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from genomeos.validation.count_probability_adapter import (
    beta_binomial_probability_queries,
    probability_float64,
)

CDF_ROW_CHUNK_CAP = 8
CDF_DRAW_CHUNK_CAP = 256
CDF_SUPPORT_CHUNK_CAP = 2048
CDF_TEMPORARY_BYTES_PER_ELEMENT = 96
CDF_MEMORY_CAP_BYTES = 512 * 1024**2
CDF_MIN_MEMORY_BUDGET_BYTES = 64 * 1024**2
# Profiler compatibility: these are the maximum plan, while each call may choose less.
CDF_ROW_CHUNK_SIZE = CDF_ROW_CHUNK_CAP
CDF_DRAW_CHUNK_SIZE = CDF_DRAW_CHUNK_CAP
CDF_SUPPORT_CHUNK_SIZE = CDF_SUPPORT_CHUNK_CAP
MAX_TEMPORARY_ELEMENTS = (
    CDF_ROW_CHUNK_CAP * CDF_DRAW_CHUNK_CAP * CDF_SUPPORT_CHUNK_CAP
)
LOG_HALF = float(np.log(0.5))
_DIRECT_CONCENTRATION = 67_108_864.0
_DIRECT_MAX_COUNT = 65_536


def _cdf_chunk_plan(
    *, rows: int, draws: int, free_device_bytes: int
) -> tuple[int, int, int]:
    """Choose bounded row, draw, and support batches from available device memory.

    The peak model reserves 96 bytes for each row×draw×support element, covering twelve
    simultaneous float64-sized arrays. Only one eighth of currently free memory is eligible and
    the budget is capped at 512 MiB, leaving space for JAX, CuPy pools, and non-grid temporaries.
    """
    if any(type(value) is not int or value <= 0 for value in (rows, draws, free_device_bytes)):
        raise ValueError("chunk-plan inputs must be positive integers")
    memory_budget = min(free_device_bytes // 8, CDF_MEMORY_CAP_BYTES)
    if memory_budget < CDF_MIN_MEMORY_BUDGET_BYTES:
        raise RuntimeError(
            "CuPy CDF requires at least 512 MiB free device memory for bounded exact tails"
        )
    row_chunk = min(rows, CDF_ROW_CHUNK_CAP)
    draw_chunk = min(draws, CDF_DRAW_CHUNK_CAP)
    maximum_elements = memory_budget // CDF_TEMPORARY_BYTES_PER_ELEMENT
    support_chunk = min(
        CDF_SUPPORT_CHUNK_CAP,
        maximum_elements // (row_chunk * draw_chunk),
    )
    if support_chunk < 1:
        raise RuntimeError("CuPy CDF cannot construct a bounded exact-tail chunk plan")
    return row_chunk, draw_chunk, support_chunk


def _load_cupy() -> tuple[Any, Any]:
    try:
        import cupy as cp
        from cupyx.scipy import special
    except (ImportError, ModuleNotFoundError) as error:
        raise RuntimeError(
            "CuPy is required for cdf_backend='cupy'; install a CUDA-compatible CuPy wheel"
        ) from error

    try:
        device_count = int(cp.cuda.runtime.getDeviceCount())
    except cp.cuda.runtime.CUDARuntimeError as error:
        raise RuntimeError(
            "cdf_backend='cupy' requires an available CUDA device; CuPy could not access one"
        ) from error
    if device_count < 1:
        raise RuntimeError("cdf_backend='cupy' requires an available CUDA device")
    return cp, special


def require_cupy_cdf() -> None:
    """Require one accessible CUDA device and successful float64 CuPy arithmetic."""
    cp, _ = _load_cupy()
    try:
        probe = cp.asarray([0.25], dtype=cp.float64)
        observed = cp.asnumpy(probe + probe)
        cp.cuda.Stream.null.synchronize()
    except cp.cuda.runtime.CUDARuntimeError as error:
        raise RuntimeError("cdf_backend='cupy' float64 device preflight failed") from error
    if not np.array_equal(observed, np.asarray([0.5])):
        raise RuntimeError("cdf_backend='cupy' float64 device preflight produced a wrong result")


class CuPyCDF:
    """Reusable device-resident CDF evaluator for validated float64 predictive draws."""

    def __init__(self, mean_draws: np.ndarray, concentration: np.ndarray | None) -> None:
        self._cp, self._special = _load_cupy()
        self._high_concentration = (
            np.zeros(mean_draws.shape, dtype=bool)
            if concentration is None
            else (
                (mean_draws > 0.0)
                & (mean_draws < 1.0)
                & (concentration > _DIRECT_CONCENTRATION)
            )
        )
        self._direct_observations = np.any(self._high_concentration, axis=0)
        self._mean = self._cp.asarray(mean_draws, dtype=self._cp.float64)
        self._concentration = (
            None
            if concentration is None
            else self._cp.asarray(concentration, dtype=self._cp.float64)
        )

    def __call__(self, ac: np.ndarray, an: np.ndarray) -> np.ndarray:
        """Return mixture CDFs for a ``(queries, observations)`` threshold matrix."""
        if ac.ndim != 2 or an.ndim != 1 or ac.shape[1] != an.shape[0]:
            raise ValueError("validated CDF arrays have incompatible shapes")
        free_device_bytes, _ = self._cp.cuda.runtime.memGetInfo()
        chunk_plan = _cdf_chunk_plan(
            rows=ac.size,
            draws=self._mean.shape[0],
            free_device_bytes=int(free_device_bytes),
        )
        if self._concentration is None:
            result = self._binomial_cdf(ac, an, chunk_plan[:2])
        else:
            result = self._beta_binomial_cdf(ac, an, chunk_plan)
        if not np.all(np.isfinite(result)) or np.any((result < 0.0) | (result > 1.0)):
            raise FloatingPointError("CuPy CDF produced a non-finite or out-of-range probability")
        return result

    def _query_arrays(self, ac: np.ndarray, an: np.ndarray) -> tuple[Any, Any, Any]:
        queries = ac.shape[0]
        observations = ac.shape[1]
        count = self._cp.asarray(ac.reshape(-1), dtype=self._cp.int64)
        denominator = self._cp.asarray(
            np.broadcast_to(an, (queries, observations)).reshape(-1),
            dtype=self._cp.int64,
        )
        observation = self._cp.asarray(
            np.tile(np.arange(observations, dtype=np.int64), queries)
        )
        return count, denominator, observation

    def _binomial_cdf(
        self, ac: np.ndarray, an: np.ndarray, chunk_plan: tuple[int, int]
    ) -> np.ndarray:
        cp = self._cp
        row_chunk_size, draw_chunk_size = chunk_plan
        count, denominator, observation = self._query_arrays(ac, an)
        output = cp.empty(count.shape, dtype=cp.float64)
        for row_start in range(0, count.size, row_chunk_size):
            row_stop = min(row_start + row_chunk_size, count.size)
            k = count[row_start:row_stop]
            n = denominator[row_start:row_stop]
            obs = observation[row_start:row_stop]
            total = cp.zeros(row_stop - row_start, dtype=cp.float64)
            for draw_start in range(0, self._mean.shape[0], draw_chunk_size):
                draw_stop = min(draw_start + draw_chunk_size, self._mean.shape[0])
                means = self._mean[draw_start:draw_stop, obs].T
                values = self._special.bdtr(k[:, None], n[:, None], means)
                values = cp.where(k[:, None] < 0, 0.0, values)
                values = cp.where(k[:, None] >= n[:, None], 1.0, values)
                total += cp.sum(values, axis=1)
            output[row_start:row_stop] = total / self._mean.shape[0]
        return cp.asnumpy(output).reshape(ac.shape)

    def _tail_logsum(
        self,
        mean: Any,
        concentration: Any,
        denominator: Any,
        start: Any,
        stop: Any,
        support_chunk_size: int,
    ) -> Any:
        cp = self._cp
        special = self._special
        total = cp.full(mean.shape, -cp.inf, dtype=cp.float64)
        maximum_terms = int(cp.asnumpy(cp.max(stop - start)))
        alpha = mean * concentration
        beta = (1.0 - mean) * concentration
        log_normalizer = special.betaln(alpha, beta)
        for support_start in range(0, maximum_terms, support_chunk_size):
            width = min(support_chunk_size, maximum_terms - support_start)
            offset = cp.arange(support_start, support_start + width, dtype=cp.int64)
            support = start[:, None] + offset[None, :]
            valid = support < stop[:, None]
            k = support[:, None, :]
            n = denominator[:, None, None]
            log_mass = (
                special.gammaln(n + 1)
                - special.gammaln(k + 1)
                - special.gammaln(n - k + 1)
                + special.betaln(k + alpha[:, :, None], n - k + beta[:, :, None])
                - log_normalizer[:, :, None]
            )
            log_mass = cp.where(valid[:, None, :], log_mass, -cp.inf)
            total = cp.logaddexp(total, special.logsumexp(log_mass, axis=2))
        return total

    def _beta_binomial_cdf(
        self,
        ac: np.ndarray,
        an: np.ndarray,
        chunk_plan: tuple[int, int, int] | None = None,
    ) -> np.ndarray:
        if chunk_plan is None:
            chunk_plan = (
                CDF_ROW_CHUNK_CAP,
                CDF_DRAW_CHUNK_CAP,
                CDF_SUPPORT_CHUNK_CAP,
            )
        direct = (an <= _DIRECT_MAX_COUNT) & self._direct_observations
        result = np.empty(ac.shape)
        if np.any(direct):
            direct_columns = np.flatnonzero(direct).astype(np.int64, copy=False)
            routing_masks, routing_groups = np.unique(
                self._high_concentration[:, direct_columns].T,
                axis=0,
                return_inverse=True,
            )
            for group_id, high in enumerate(routing_masks):
                columns = direct_columns[routing_groups == group_id]
                high_indices = np.flatnonzero(high).astype(np.int64, copy=False)
                legacy_indices = np.flatnonzero(~high).astype(np.int64, copy=False)
                count = self._cp.asarray(ac[:, columns], dtype=self._cp.int64)
                denominator = self._cp.asarray(an[columns], dtype=self._cp.int64)
                probabilities = beta_binomial_probability_queries(
                    self._mean[high_indices][:, columns],
                    self._concentration[high_indices][:, columns],
                    denominator,
                    count,
                    array_module=self._cp,
                    max_count=int(np.max(an[columns])),
                )
                high_result = self._cp.asnumpy(
                    probability_float64(probabilities.lower, array_module=self._cp)
                )
                if legacy_indices.size == 0:
                    result[:, columns] = high_result
                    continue
                legacy_result = self._legacy_beta_binomial_cdf_arrays(
                    ac[:, columns],
                    an[columns],
                    self._mean[legacy_indices][:, columns],
                    self._concentration[legacy_indices][:, columns],
                    chunk_plan,
                )
                result[:, columns] = (
                    high_indices.size * high_result
                    + legacy_indices.size * legacy_result
                ) / self._mean.shape[0]
        if np.any(~direct):
            columns = np.flatnonzero(~direct).astype(np.int64, copy=False)
            result[:, columns] = self._legacy_beta_binomial_cdf_arrays(
                ac[:, columns],
                an[columns],
                self._mean[:, columns],
                self._concentration[:, columns],
                chunk_plan,
            )
        return result

    def _legacy_beta_binomial_cdf_arrays(
        self,
        ac: np.ndarray,
        an: np.ndarray,
        mean_draws: Any,
        concentration_draws: Any,
        chunk_plan: tuple[int, int, int],
        *,
        draw_weights: Any | None = None,
        normalization_draws: int | None = None,
    ) -> np.ndarray:
        cp = self._cp
        row_chunk_size, draw_chunk_size, support_chunk_size = chunk_plan
        if draw_weights is not None and draw_weights.shape != mean_draws.shape:
            raise ValueError("draw_weights must match the selected predictive draw shape")
        divisor = mean_draws.shape[0] if normalization_draws is None else normalization_draws
        if type(divisor) is not int or divisor <= 0:
            raise ValueError("normalization_draws must be a positive integer")
        count, denominator, observation = self._query_arrays(ac, an)
        output = cp.empty(count.shape, dtype=cp.float64)
        for row_start in range(0, count.size, row_chunk_size):
            row_stop = min(row_start + row_chunk_size, count.size)
            k = count[row_start:row_stop]
            n = denominator[row_start:row_stop]
            obs = observation[row_start:row_stop]
            total = cp.zeros(row_stop - row_start, dtype=cp.float64)
            for draw_start in range(0, mean_draws.shape[0], draw_chunk_size):
                draw_stop = min(draw_start + draw_chunk_size, mean_draws.shape[0])
                mean = mean_draws[draw_start:draw_stop, obs].T
                concentration = concentration_draws[draw_start:draw_stop, obs].T
                boundary_zero = mean == 0.0
                boundary_one = mean == 1.0
                interior = ~(boundary_zero | boundary_one)
                safe_mean = cp.where(interior, mean, 0.5)
                lower_is_shorter = (k + 1) <= (n - k)
                short_start = cp.where(lower_is_shorter, 0, k + 1)
                short_stop = cp.where(lower_is_shorter, k + 1, n + 1)
                log_short = self._tail_logsum(
                    safe_mean,
                    concentration,
                    n,
                    short_start,
                    short_stop,
                    support_chunk_size,
                )
                values = cp.where(
                    lower_is_shorter[:, None],
                    cp.exp(log_short),
                    -cp.expm1(log_short),
                )

                fallback = interior & (log_short > LOG_HALF)
                if bool(cp.asnumpy(cp.any(fallback))):
                    long_start = cp.where(lower_is_shorter, k + 1, 0)
                    long_stop = cp.where(lower_is_shorter, n + 1, k + 1)
                    fallback_rows = cp.any(fallback, axis=1)
                    long_start = cp.where(fallback_rows, long_start, 0)
                    long_stop = cp.where(fallback_rows, long_stop, 0)
                    log_long = self._tail_logsum(
                        safe_mean,
                        concentration,
                        n,
                        long_start,
                        long_stop,
                        support_chunk_size,
                    )
                    fallback_values = cp.where(
                        lower_is_shorter[:, None],
                        -cp.expm1(log_long),
                        cp.exp(log_long),
                    )
                    values = cp.where(fallback, fallback_values, values)

                values = cp.where(boundary_zero, 1.0, values)
                values = cp.where(boundary_one, 0.0, values)
                values = cp.where(k[:, None] < 0, 0.0, values)
                values = cp.where(k[:, None] >= n[:, None], 1.0, values)
                invalid = ~cp.isfinite(values) | (values < 0.0) | (values > 1.0)
                if bool(cp.asnumpy(cp.any(invalid))):
                    raise FloatingPointError(
                        "CuPy CDF produced a non-finite or out-of-range component probability"
                    )
                if draw_weights is not None:
                    weights = draw_weights[draw_start:draw_stop, obs].T
                    values = values * weights
                total += cp.sum(values, axis=1)
            output[row_start:row_stop] = total / divisor
        return cp.asnumpy(output).reshape(ac.shape)


class ActivityCuPyCDF(CuPyCDF):
    """Exact device CDF for an inactive-zero plus beta-binomial draw mixture."""

    def __init__(
        self,
        mean_draws: np.ndarray,
        concentration: np.ndarray,
        activity_probability: np.ndarray,
    ) -> None:
        if activity_probability.shape != mean_draws.shape:
            raise ValueError("activity_probability must match the predictive draw shape")
        if not np.all(np.isfinite(activity_probability)) or np.any(
            (activity_probability < 0.0) | (activity_probability > 1.0)
        ):
            raise ValueError("activity_probability must be finite and between zero and one")
        super().__init__(mean_draws, concentration)
        self._activity_host = np.asarray(activity_probability, dtype=np.float64)
        self._activity = self._cp.asarray(activity_probability, dtype=self._cp.float64)

    def __call__(self, ac: np.ndarray, an: np.ndarray) -> np.ndarray:
        """Return activity-mixture CDFs for a query-by-observation threshold matrix."""
        if ac.ndim != 2 or an.ndim != 1 or ac.shape[1] != an.shape[0]:
            raise ValueError("validated CDF arrays have incompatible shapes")
        free_device_bytes, _ = self._cp.cuda.runtime.memGetInfo()
        chunk_plan = _cdf_chunk_plan(
            rows=ac.size,
            draws=self._mean.shape[0],
            free_device_bytes=int(free_device_bytes),
        )
        result = self._activity_beta_binomial_cdf(ac, an, chunk_plan)
        if not np.all(np.isfinite(result)) or np.any((result < 0.0) | (result > 1.0)):
            raise FloatingPointError(
                "activity CuPy CDF produced a non-finite or out-of-range probability"
            )
        return result

    def _activity_beta_binomial_cdf(
        self,
        ac: np.ndarray,
        an: np.ndarray,
        chunk_plan: tuple[int, int, int],
    ) -> np.ndarray:
        draws = self._mean.shape[0]
        inactive = np.mean(1.0 - self._activity_host, axis=0)
        result = np.where(ac < 0, 0.0, inactive[np.newaxis, :])
        direct = (an <= _DIRECT_MAX_COUNT) & self._direct_observations
        if np.any(direct):
            direct_columns = np.flatnonzero(direct).astype(np.int64, copy=False)
            routing_masks, routing_groups = np.unique(
                self._high_concentration[:, direct_columns].T,
                axis=0,
                return_inverse=True,
            )
            for group_id, high in enumerate(routing_masks):
                columns = direct_columns[routing_groups == group_id]
                high_indices = np.flatnonzero(high).astype(np.int64, copy=False)
                legacy_indices = np.flatnonzero(~high).astype(np.int64, copy=False)
                if legacy_indices.size:
                    result[:, columns] += self._legacy_beta_binomial_cdf_arrays(
                        ac[:, columns],
                        an[columns],
                        self._mean[legacy_indices][:, columns],
                        self._concentration[legacy_indices][:, columns],
                        chunk_plan,
                        draw_weights=self._activity[legacy_indices][:, columns],
                        normalization_draws=draws,
                    )
                count = self._cp.asarray(ac[:, columns], dtype=self._cp.int64)
                denominator = self._cp.asarray(an[columns], dtype=self._cp.int64)
                for draw_index in high_indices:
                    probabilities = beta_binomial_probability_queries(
                        self._mean[draw_index : draw_index + 1, columns],
                        self._concentration[draw_index : draw_index + 1, columns],
                        denominator,
                        count,
                        array_module=self._cp,
                        max_count=int(np.max(an[columns])),
                    )
                    component = self._cp.asnumpy(
                        probability_float64(probabilities.lower, array_module=self._cp)
                    )
                    weights = self._activity_host[draw_index, columns]
                    result[:, columns] += component * weights[np.newaxis, :] / draws
        if np.any(~direct):
            columns = np.flatnonzero(~direct).astype(np.int64, copy=False)
            result[:, columns] += self._legacy_beta_binomial_cdf_arrays(
                ac[:, columns],
                an[columns],
                self._mean[:, columns],
                self._concentration[:, columns],
                chunk_plan,
                draw_weights=self._activity[:, columns],
                normalization_draws=draws,
            )
        result = np.where(ac < 0, 0.0, result)
        return np.where(ac >= an[np.newaxis, :], 1.0, result)
