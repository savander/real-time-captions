import numpy as np
import pytest

from real_time_captions.audio.frame import AudioFrame
from real_time_captions.audio.normalize import normalize_frame


def make_frame(
    samples: np.ndarray,
    *,
    sample_rate: int = 16_000,
    channels: int = 1,
) -> AudioFrame:
    return AudioFrame(
        session_id="session-1",
        samples=samples,
        sample_rate=sample_rate,
        channels=channels,
        sequence=1,
        captured_at=1.0,
    )


def test_normalize_frame_downmixes_stereo_float32() -> None:
    frame = make_frame(
        np.array([[1.0, -1.0], [0.5, 0.5]], dtype=np.float32), channels=2
    )

    result = normalize_frame(frame)

    np.testing.assert_allclose(result, np.array([0.0, 0.5], dtype=np.float32))
    assert result.flags.c_contiguous


def test_normalize_frame_scales_int16_to_float32() -> None:
    frame = make_frame(np.array([-32768, 0, 32767], dtype=np.int16))

    result = normalize_frame(frame)

    np.testing.assert_allclose(
        result, np.array([-1.0, 0.0, 32767 / 32768], dtype=np.float32)
    )
    assert result.dtype == np.float32


def test_normalize_frame_centers_and_scales_uint8_pcm() -> None:
    frame = make_frame(np.array([0, 128, 255], dtype=np.uint8))

    result = normalize_frame(frame)

    np.testing.assert_allclose(
        result, np.array([-1.0, 0.0, 127 / 128], dtype=np.float32)
    )


def test_normalize_frame_resamples_to_requested_rate() -> None:
    frame = make_frame(np.ones(8_000, dtype=np.float32), sample_rate=8_000)

    result = normalize_frame(frame)

    assert len(result) == 16_000
    assert result.dtype == np.float32


@pytest.mark.parametrize(
    ("sample_rate", "channels", "target_rate"),
    [
        (0, 1, 16_000),
        (-1, 1, 16_000),
        (16_000, 0, 16_000),
        (16_000, -1, 16_000),
        (16_000, 1, 0),
        (16_000, 1, -1),
    ],
)
def test_normalize_frame_rejects_non_positive_rates_and_channels(
    sample_rate: int, channels: int, target_rate: int
) -> None:
    frame = make_frame(np.array([0.0], dtype=np.float32), sample_rate=sample_rate, channels=channels)

    with pytest.raises(ValueError, match="sample rates and channels must be positive"):
        normalize_frame(frame, target_rate=target_rate)


def test_normalize_frame_rejects_samples_that_do_not_fit_channel_count() -> None:
    frame = make_frame(np.array([0.0, 0.5, 1.0], dtype=np.float32), channels=2)

    with pytest.raises(ValueError):
        normalize_frame(frame)


def test_audio_frame_owns_a_read_only_sample_snapshot() -> None:
    source = np.array([0.25, 0.5], dtype=np.float32)

    frame = make_frame(source)
    source[0] = 9.0

    np.testing.assert_array_equal(
        frame.samples, np.array([0.25, 0.5], dtype=np.float32)
    )
    with pytest.raises(ValueError, match='read-only'):
        frame.samples[0] = 1.0
