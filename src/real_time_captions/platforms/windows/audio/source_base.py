from collections.abc import Callable
from math import ceil
from time import monotonic
from uuid import uuid4

import numpy as np

from real_time_captions.audio.capture import CaptureDiagnostics
from real_time_captions.audio.frame import AudioFrame
from real_time_captions.audio.frame_queue import BoundedFrameQueue
from real_time_captions.contracts import SourceState


class ManagedSourceBase:
    def __init__(self, queue_seconds: float, *, clock: Callable[[], float] = monotonic, session_id_factory: Callable[[], str] = lambda: uuid4().hex) -> None:
        self._queue_seconds = queue_seconds
        self._clock = clock
        self._session_id_factory = session_id_factory
        self._state = SourceState.STOPPED
        self._session_id: str | None = None
        self._session_zero = 0.0
        self._sequence = 0
        self._generation = 0
        self._queue: BoundedFrameQueue | None = None
        self._last_frame_at: float | None = None
        self._last_error: str | None = None

    @property
    def session_id(self) -> str | None:
        return self._session_id

    def _begin(self, sample_rate: int, frames_per_buffer: int) -> tuple[str, int]:
        self._generation += 1
        self._state = SourceState.STARTING
        self._session_id = self._session_id_factory()
        self._session_zero = self._clock()
        self._sequence = 0
        self._last_frame_at = None
        self._last_error = None
        capacity = max(1, ceil(self._queue_seconds * sample_rate / frames_per_buffer))
        self._queue = BoundedFrameQueue(capacity)
        return self._session_id, self._generation

    def _mark_running(self) -> None:
        self._state = SourceState.RUNNING

    def _mark_reconnecting(self, error: Exception | None = None) -> None:
        self._state = SourceState.RECONNECTING
        if error is not None:
            self._last_error = str(error)

    def _mark_failed(self, error: Exception) -> None:
        self._state = SourceState.FAILED
        self._last_error = str(error)
        if self._queue is not None:
            self._queue.close()

    def _publish(self, generation: int, samples: np.ndarray, sample_rate: int, channels: int) -> None:
        if generation != self._generation or self._state is not SourceState.RUNNING:
            return
        queue = self._queue
        session_id = self._session_id
        if queue is None or session_id is None:
            return
        now = self._clock()
        self._sequence += 1
        self._last_frame_at = now
        queue.put(AudioFrame(session_id, samples, sample_rate, channels, self._sequence, max(0.0, now - self._session_zero)))

    def read(self, timeout: float | None = None) -> AudioFrame | None:
        queue = self._queue
        return None if queue is None else queue.get(timeout)

    def _stop_session(self) -> None:
        if self._state is SourceState.STOPPED:
            return
        self._generation += 1
        if self._queue is not None:
            self._queue.close()
        self._state = SourceState.STOPPED

    def diagnostics(self) -> CaptureDiagnostics:
        silent_seconds = None
        if self._state is SourceState.RUNNING:
            since = self._last_frame_at or self._session_zero
            silent_seconds = max(0.0, self._clock() - since)
        return CaptureDiagnostics(self._state, self._queue.dropped_frames if self._queue else 0, silent_seconds, self._last_error)
