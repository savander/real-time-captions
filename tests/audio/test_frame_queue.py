from threading import Event, Thread

import numpy as np
import pytest

from real_time_captions.audio.frame import AudioFrame
from real_time_captions.audio.frame_queue import BoundedFrameQueue


def frame(sequence: int) -> AudioFrame:
    return AudioFrame(
        's1',
        np.array([sequence], dtype=np.float32),
        16_000,
        1,
        sequence,
        sequence / 10,
    )


def test_full_queue_drops_oldest_frame() -> None:
    queue = BoundedFrameQueue(max_frames=2)
    queue.put(frame(1))
    queue.put(frame(2))
    queue.put(frame(3))

    assert queue.get(0).sequence == 2  # type: ignore[union-attr]
    assert queue.get(0).sequence == 3  # type: ignore[union-attr]
    assert queue.dropped_frames == 1


def test_get_times_out_without_a_frame() -> None:
    queue = BoundedFrameQueue(max_frames=1)
    assert queue.get(0) is None


def test_close_rejects_late_frames_and_returns_none() -> None:
    queue = BoundedFrameQueue(max_frames=1)
    queue.close()
    queue.put(frame(1))

    assert queue.get(0) is None
    assert queue.size == 0


def test_close_unblocks_waiting_consumer() -> None:
    queue = BoundedFrameQueue(max_frames=1)
    finished = Event()
    results: list[AudioFrame | None] = []

    def consume() -> None:
        results.append(queue.get(None))
        finished.set()

    consumer = Thread(target=consume)
    consumer.start()
    queue.close()
    consumer.join(timeout=1)

    assert finished.is_set()
    assert results == [None]


def test_clear_removes_frames_without_closing_queue() -> None:
    queue = BoundedFrameQueue(max_frames=2)
    queue.put(frame(1))
    queue.clear()
    queue.put(frame(2))

    assert queue.get(0).sequence == 2  # type: ignore[union-attr]


@pytest.mark.parametrize('max_frames', [True, 0, -1])
def test_queue_rejects_invalid_capacity(max_frames: int) -> None:
    with pytest.raises(ValueError, match='max_frames'):
        BoundedFrameQueue(max_frames=max_frames)
