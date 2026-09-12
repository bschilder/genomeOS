"""Optional float64 CuPy CDF evaluation for count predictions (design §7, §8; #189).

This module is a numerical backend for ``CountPredictive``. It receives already validated,
host-resident draw and count arrays through a public typed interface; validation policy remains
owned by ``genomeos.validation.predictive``. CuPy is imported only when ``CuPyCDF`` is explicitly
constructed, and a missing library or CUDA device is an error rather than a CPU fallback.

Beta-binomial tails are exact finite sums. Temporary log-mass grids are bounded by
``CDF_ROW_CHUNK_SIZE * CDF_DRAW_CHUNK_SIZE * CDF_SUPPORT_CHUNK_SIZE`` float64 elements and no
array dimension depends on the complete allele-number support.
"""

from __future__ import annotations

from typing import Any

import numpy as np

CDF_ROW_CHUNK_SIZE = 4
CDF_DRAW_CHUNK_SIZE = 128
CDF_SUPPORT_CHUNK_SIZE = 1024
MAX_TEMPORARY_ELEMENTS = (
    CDF_ROW_CHUNK_SIZE * CDF_DRAW_CHUNK_SIZE * CDF_SUPPORT_CHUNK_SIZE
)


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


class CuPyCDF:
    """Reusable device-resident CDF evaluator for validated float64 predictive draws."""

    def __init__(self, mean_draws: np.ndarray, concentration: np.ndarray | None) -> None:
        self._cp, self._special = _load_cupy()
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
        if self._concentration is None:
            result = self._binomial_cdf(ac, an)
        else:
            result = self._beta_binomial_cdf(ac, an)
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

    def _binomial_cdf(self, ac: np.ndarray, an: np.ndarray) -> np.ndarray:
        cp = self._cp
        count, denominator, observation = self._query_arrays(ac, an)
        output = cp.empty(count.shape, dtype=cp.float64)
        for row_start in range(0, count.size, CDF_ROW_CHUNK_SIZE):
            row_stop = min(row_start + CDF_ROW_CHUNK_SIZE, count.size)
            k = count[row_start:row_stop]
            n = denominator[row_start:row_stop]
            obs = observation[row_start:row_stop]
            total = cp.zeros(row_stop - row_start, dtype=cp.float64)
            for draw_start in range(0, self._mean.shape[0], CDF_DRAW_CHUNK_SIZE):
                draw_stop = min(draw_start + CDF_DRAW_CHUNK_SIZE, self._mean.shape[0])
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
    ) -> Any:
        cp = self._cp
        special = self._special
        total = cp.full(mean.shape, -cp.inf, dtype=cp.float64)
        maximum_terms = int(cp.asnumpy(cp.max(stop - start)))
        alpha = mean * concentration
        beta = (1.0 - mean) * concentration
        log_normalizer = special.betaln(alpha, beta)
        for support_start in range(0, maximum_terms, CDF_SUPPORT_CHUNK_SIZE):
            width = min(CDF_SUPPORT_CHUNK_SIZE, maximum_terms - support_start)
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

    def _beta_binomial_cdf(self, ac: np.ndarray, an: np.ndarray) -> np.ndarray:
        cp = self._cp
        count, denominator, observation = self._query_arrays(ac, an)
        output = cp.empty(count.shape, dtype=cp.float64)
        for row_start in range(0, count.size, CDF_ROW_CHUNK_SIZE):
            row_stop = min(row_start + CDF_ROW_CHUNK_SIZE, count.size)
            k = count[row_start:row_stop]
            n = denominator[row_start:row_stop]
            obs = observation[row_start:row_stop]
            total = cp.zeros(row_stop - row_start, dtype=cp.float64)
            for draw_start in range(0, self._mean.shape[0], CDF_DRAW_CHUNK_SIZE):
                draw_stop = min(draw_start + CDF_DRAW_CHUNK_SIZE, self._mean.shape[0])
                mean = self._mean[draw_start:draw_stop, obs].T
                concentration = self._concentration[draw_start:draw_stop, obs].T
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
                )
                short_is_valid = log_short < 0.0
                values = cp.where(
                    lower_is_shorter[:, None],
                    cp.exp(log_short),
                    -cp.expm1(log_short),
                )

                fallback = interior & ~short_is_valid
                if bool(cp.asnumpy(cp.any(fallback))):
                    long_start = cp.where(lower_is_shorter, k + 1, 0)
                    long_stop = cp.where(lower_is_shorter, n + 1, k + 1)
                    log_long = self._tail_logsum(
                        safe_mean,
                        concentration,
                        n,
                        long_start,
                        long_stop,
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
                total += cp.sum(values, axis=1)
            output[row_start:row_stop] = total / self._mean.shape[0]
        return cp.asnumpy(output).reshape(ac.shape)
