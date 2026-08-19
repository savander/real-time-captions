import numpy as np
import pytest

from real_time_captions.audio.ring_buffer import AudioRingBuffer


def test_ring_buffer_discards_oldest_samples_at_capacity() -> None:
    buffer = AudioRingBuffer(capacity_samples=5)
    buffer.append(np.array([1, 2, 3], dtype=np.float32))
    buffer.append(np.array([4, 5, 6, 7], dtype=np.float32))

    np.testing.assert_array_equal(
        buffer.latest(5), np.array([3, 4, 5, 6, 7], dtype=np.float32)
    )
    assert buffer.size == 5


def test_ring_buffer_returns_empty_array_when_no_samples_are_available() -> None:
    buffer = AudioRingBuffer(capacity_samples=3)

    result = buffer.latest(2)

    np.testing.assert_array_equal(result, np.array([], dtype=np.float32))
    assert result.dtype == np.float32


def test_ring_buffer_keeps_only_tail_when_single_append_exceeds_capacity() -> None:
    buffer = AudioRingBuffer(capacity_samples=3)

    buffer.append(np.array([1, 2, 3, 4, 5], dtype=np.float32))

    np.testing.assert_array_equal(buffer.latest(3), np.array([3, 4, 5], dtype=np.float32))
    assert buffer.size == 3


def test_ring_buffer_reads_across_wrapped_storage() -> None:
    buffer = AudioRingBuffer(capacity_samples=5)
    buffer.append(np.array([1, 2, 3, 4], dtype=np.float32))
    buffer.append(np.array([5, 6, 7], dtype=np.float32))

    np.testing.assert_array_equal(buffer.latest(4), np.array([4, 5, 6, 7], dtype=np.float32))


def test_ring_buffer_latest_returns_a_copy() -> None:
    buffer = AudioRingBuffer(capacity_samples=3)
    buffer.append(np.array([1, 2, 3], dtype=np.float32))

    result = buffer.latest(2)
    result[0] = 99

    np.testing.assert_array_equal(buffer.latest(2), np.array([2, 3], dtype=np.float32))


def test_ring_buffer_clamps_requested_count_to_available_samples() -> None:
    buffer = AudioRingBuffer(capacity_samples=3)
    buffer.append(np.array([1, 2], dtype=np.float32))

    np.testing.assert_array_equal(buffer.latest(-1), np.array([], dtype=np.float32))
    np.testing.assert_array_equal(buffer.latest(10), np.array([1, 2], dtype=np.float32))


@pytest.mark.parametrize("capacity_samples", [0, -1])
def test_ring_buffer_rejects_non_positive_capacity(capacity_samples: int) -> None:
    with pytest.raises(ValueError, match="capacity_samples must be positive"):
        AudioRingBuffer(capacity_samples=capacity_samples)
