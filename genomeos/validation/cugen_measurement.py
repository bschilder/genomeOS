"""External synchronized CuGen pilot measurements (CuGen pilot design §8).

Measurements remain outside immutable scientific artifacts. Pool observations are explicitly
stage-boundary snapshots; process RSS is an operating-system high-water observation.
"""

from __future__ import annotations

import resource
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar

from genomeos.validation.cugen_pilot import PilotStageObserver

_STAGES = (
    "input_validation",
    "source_snapshot",
    "cugen_import",
    "subset",
    "training_validation",
    "reference",
    "cpu_ld",
    "cpu_reconciliation",
    "gpu_ld",
    "gpu_reconciliation",
    "artifact_write",
    "artifact_verification",
)
_DEVICE_STAGES = frozenset({"subset", "gpu_ld"})
T = TypeVar("T")


@dataclass(frozen=True)
class StageMeasurement:
    """One complete observed stage interval and its boundary-only memory readings."""

    stage: str
    seconds: float
    rss_high_water_start_bytes: int
    rss_high_water_end_bytes: int
    pool_start: tuple[tuple[str, int], ...]
    pool_end: tuple[tuple[str, int], ...]
    memory_semantics: str = "stage_boundary_snapshots_not_peaks"


def process_rss_high_water_bytes() -> int:
    """Return the process maximum-resident-set observation in bytes."""
    observed = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(observed if sys.platform == "darwin" else observed * 1024)


class PilotMeasurementObserver:
    """Measure the fixed observer contract with synchronization at device stages."""

    def __init__(
        self,
        *,
        synchronize: Callable[[], None],
        clock: Callable[[], float] = time.perf_counter,
        rss_high_water: Callable[[], int] = process_rss_high_water_bytes,
        pool_snapshot: Callable[[], dict[str, int]],
    ) -> None:
        self._synchronize = synchronize
        self._clock = clock
        self._rss_high_water = rss_high_water
        self._pool_snapshot = pool_snapshot
        self._active: tuple[str, float, int, tuple[tuple[str, int], ...]] | None = None
        self._records: list[StageMeasurement] = []

    @property
    def records(self) -> tuple[StageMeasurement, ...]:
        return tuple(self._records)

    def __call__(self, stage: str, event: str) -> None:
        if stage not in _STAGES or event not in ("start", "end"):
            raise ValueError("observer received an unknown stage or event")
        if stage in _DEVICE_STAGES:
            self._synchronize()
        observed_at = self._clock()
        rss = self._rss_high_water()
        pool = tuple(sorted(self._pool_snapshot().items()))
        if event == "start":
            if self._active is not None:
                raise ValueError("observer stages must not overlap")
            self._active = stage, observed_at, rss, pool
            return
        if self._active is None or self._active[0] != stage:
            raise ValueError("observer end event does not match the active stage")
        active_stage, started_at, rss_start, pool_start = self._active
        self._records.append(
            StageMeasurement(
                stage=active_stage,
                seconds=observed_at - started_at,
                rss_high_water_start_bytes=rss_start,
                rss_high_water_end_bytes=rss,
                pool_start=pool_start,
                pool_end=pool,
            )
        )
        self._active = None


def measure_full_workflow(
    run: Callable[[PilotStageObserver], T],
    *,
    observer: PilotStageObserver,
    clock: Callable[[], float] = time.perf_counter,
) -> tuple[T, float]:
    """Measure from immediately before the adapter call through its verified return."""
    started = clock()
    result = run(observer)
    return result, clock() - started


def cupy_pool_snapshot(cupy: Any) -> dict[str, int]:
    """Return labeled current/retained pool observations, never claimed as peaks."""
    device_pool = cupy.get_default_memory_pool()
    pinned_pool = cupy.get_default_pinned_memory_pool()
    return {
        "device_used_bytes": int(device_pool.used_bytes()),
        "device_retained_bytes": int(device_pool.total_bytes()),
        "pinned_free_blocks": int(pinned_pool.n_free_blocks()),
    }
