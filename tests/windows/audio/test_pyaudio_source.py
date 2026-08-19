from collections.abc import Callable

import numpy as np
import pytest

from real_time_captions.audio.capture import (
    AudioCaptureConfig,
    AudioSourceDescriptor,
    AudioSourceKind,
    AudioSourceOpenError,
)
from real_time_captions.contracts import SourceState
from real_time_captions.platforms.windows.audio.pyaudio_api import WasapiDevice
from real_time_captions.platforms.windows.audio.pyaudio_source import (
    WasapiAudioSource,
)


class Clock:
    value = 10.0

    def __call__(self) -> float:
        return self.value


class FakeStream:
    def __init__(self, callback: Callable[..., tuple[None, int]]) -> None:
        self.callback = callback
        self.starts = 0
        self.stops = 0
        self.closes = 0

    def start_stream(self) -> None:
        self.starts += 1

    def stop_stream(self) -> None:
        self.stops += 1

    def is_active(self) -> bool:
        return self.starts > self.stops

    def close(self) -> None:
        self.closes += 1

    def emit(self, payload: bytes | bytearray, frames: int) -> None:
        self.callback(payload, frames, {}, 0)


class FakeApi:
    continue_token = 0

    def __init__(self, device: WasapiDevice) -> None:
        self.default = device
        self.streams: list[FakeStream] = []
        self.opened: list[tuple[WasapiDevice, int]] = []
        self.failure: Exception | None = None

    def default_loopback(self) -> WasapiDevice | None:
        return self.default

    def loopback_devices(self) -> tuple[WasapiDevice, ...]:
        return (self.default,)

    def input_devices(self) -> tuple[WasapiDevice, ...]:
        return (self.default,)

    def open_input(
        self,
        device: WasapiDevice,
        frames_per_buffer: int,
        callback: Callable[..., tuple[None, int]],
    ) -> FakeStream:
        if self.failure:
            raise self.failure
        self.opened.append((device, frames_per_buffer))
        stream = FakeStream(callback)
        self.streams.append(stream)
        return stream


def device(index: int = 21, channels: int = 2) -> WasapiDevice:
    return WasapiDevice(
        index,
        'Headphones [Loopback]',
        48_000,
        channels,
        0,
        True,
    )


def source(
    api: FakeApi,
    clock: Clock,
    *,
    descriptor_id: str = 'default-output',
    kind: AudioSourceKind = AudioSourceKind.SYSTEM,
    queue_seconds: float = 2.0,
) -> WasapiAudioSource:
    return WasapiAudioSource(
        AudioSourceDescriptor(descriptor_id, kind, 'Test source'),
        AudioCaptureConfig(descriptor_id, queue_seconds),
        api,
        clock=clock,
        session_id_factory=lambda: 'session-1',
    )


def test_callback_publishes_owned_native_format_frame() -> None:
    clock = Clock()
    api = FakeApi(device())
    capture = source(api, clock)
    session_id = capture.start()
    samples = np.array([0.1, -0.2, 0.3, -0.4], dtype=np.float32)
    payload = bytearray(samples.tobytes())

    clock.value = 10.04
    api.streams[0].emit(payload, frames=2)
    payload[:] = bytes(len(payload))

    frame = capture.read(0)
    assert frame is not None
    assert session_id == frame.session_id == 'session-1'
    assert (frame.sequence, frame.sample_rate, frame.channels) == (1, 48_000, 2)
    assert frame.captured_at == pytest.approx(0.04)
    np.testing.assert_allclose(frame.samples, samples)
    assert not frame.samples.flags.writeable


def test_queue_overflow_drops_oldest_callback_frame() -> None:
    clock = Clock()
    api = FakeApi(device(channels=1))
    capture = source(api, clock, queue_seconds=0.04)
    capture.start()

    api.streams[0].emit(np.zeros(1_920, dtype=np.float32).tobytes(), 1_920)
    api.streams[0].emit(np.ones(1_920, dtype=np.float32).tobytes(), 1_920)

    assert capture.read(0).sequence == 2  # type: ignore[union-attr]
    assert capture.diagnostics().dropped_frames == 1


def test_stop_is_idempotent_and_rejects_late_callbacks() -> None:
    clock = Clock()
    api = FakeApi(device())
    capture = source(api, clock)
    capture.start()
    stream = api.streams[0]

    capture.stop()
    capture.stop()
    stream.emit(np.zeros(4, dtype=np.float32).tobytes(), 2)

    assert (stream.stops, stream.closes) == (1, 1)
    assert capture.read(0) is None
    assert capture.diagnostics().state is SourceState.STOPPED


def test_default_output_is_resolved_again_for_each_session() -> None:
    clock = Clock()
    first = device(21)
    api = FakeApi(first)
    capture = source(api, clock)
    capture.start()
    capture.stop()
    second = device(22)
    api.default = second

    capture.start()

    assert [opened[0].index for opened in api.opened] == [21, 22]


def test_native_open_failure_is_typed_and_marks_source_failed() -> None:
    clock = Clock()
    api = FakeApi(device())
    api.failure = OSError('device busy')
    capture = source(api, clock)

    with pytest.raises(AudioSourceOpenError, match='device busy'):
        capture.start()

    assert capture.diagnostics().state is SourceState.FAILED


def test_wasapi_source_rejects_process_descriptor() -> None:
    capture = source(
        FakeApi(device()),
        Clock(),
        descriptor_id='process:42',
        kind=AudioSourceKind.PROCESS,
    )

    with pytest.raises(AudioSourceOpenError, match='process'):
        capture.start()
