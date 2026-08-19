import math
from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DiagnosticsSnapshot:
    first_caption_p50: float | None
    first_caption_p95: float | None
    commit_p50: float | None
    commit_p95: float | None
    coalesced_windows: int
    worker_restarts: int


class RuntimeMetrics:
    def __init__(self, max_samples: int) -> None:
        if isinstance(max_samples, bool) or not isinstance(max_samples, int) or max_samples <= 0:
            raise ValueError('max_samples must be a positive integer')
        self._first_caption_latencies: deque[float] = deque(maxlen=max_samples)
        self._commit_latencies: deque[float] = deque(maxlen=max_samples)
        self._coalesced_windows = 0
        self._worker_restarts = 0

    def record_first_caption_latency(self, seconds: float) -> None:
        self._first_caption_latencies.append(self._validated_latency(seconds))

    def record_commit_latency(self, seconds: float) -> None:
        self._commit_latencies.append(self._validated_latency(seconds))

    def record_coalesced_window(self) -> None:
        self._coalesced_windows += 1

    def record_worker_restart(self) -> None:
        self._worker_restarts += 1

    def snapshot(self) -> DiagnosticsSnapshot:
        return DiagnosticsSnapshot(
            first_caption_p50=_nearest_rank(self._first_caption_latencies, 0.50),
            first_caption_p95=_nearest_rank(self._first_caption_latencies, 0.95),
            commit_p50=_nearest_rank(self._commit_latencies, 0.50),
            commit_p95=_nearest_rank(self._commit_latencies, 0.95),
            coalesced_windows=self._coalesced_windows,
            worker_restarts=self._worker_restarts,
        )

    @staticmethod
    def _validated_latency(seconds: float) -> float:
        if isinstance(seconds, bool) or not isinstance(seconds, (int, float)):
            raise ValueError('latency must be a finite, non-negative number')
        latency = float(seconds)
        if not math.isfinite(latency) or latency < 0:
            raise ValueError('latency must be a finite, non-negative number')
        return latency


def _nearest_rank(values: deque[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[math.ceil(quantile * len(ordered)) - 1]
