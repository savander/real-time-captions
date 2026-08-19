from collections import deque
from threading import Condition

from real_time_captions.audio.frame import AudioFrame


class BoundedFrameQueue:
    def __init__(self, max_frames: int) -> None:
        if isinstance(max_frames, bool) or max_frames <= 0:
            raise ValueError('max_frames must be a positive integer')
        self._max_frames = max_frames
        self._frames: deque[AudioFrame] = deque()
        self._condition = Condition()
        self._closed = False
        self._dropped_frames = 0

    @property
    def size(self) -> int:
        with self._condition:
            return len(self._frames)

    @property
    def dropped_frames(self) -> int:
        with self._condition:
            return self._dropped_frames

    def put(self, frame: AudioFrame) -> None:
        with self._condition:
            if self._closed:
                return
            if len(self._frames) == self._max_frames:
                self._frames.popleft()
                self._dropped_frames += 1
            self._frames.append(frame)
            self._condition.notify()

    def get(self, timeout: float | None = None) -> AudioFrame | None:
        with self._condition:
            if not self._frames and not self._closed:
                self._condition.wait_for(
                    lambda: bool(self._frames) or self._closed,
                    timeout=timeout,
                )
            return self._frames.popleft() if self._frames else None

    def clear(self) -> None:
        with self._condition:
            self._frames.clear()

    def close(self) -> None:
        with self._condition:
            self._closed = True
            self._frames.clear()
            self._condition.notify_all()
