from collections.abc import Callable

import numpy as np
import pytest

from real_time_captions.audio.capture import (
    AmbiguousAudioSource,
    AudioCaptureConfig,
    AudioReconnectExhausted,
    AudioSourceDescriptor,
    AudioSourceKind,
    AudioSourceNotFound,
    AudioSourceOpenError,
)
from real_time_captions.contracts import SourceState
from real_time_captions.platforms.windows.audio.process_source import (
    ProcessAudioSource,
)
from real_time_captions.platforms.windows.audio.processes import ProcessInfo


PATH = r'C:\Apps\Player.exe'


class Clock:
    value = 4.0

    def __call__(self) -> float:
        return self.value


class FakeTap:
    def __init__(self, callback: Callable[[bytes, int], None], sample_format: str = 'float32') -> None:
        self.callback = callback
        self.sample_format = sample_format
        self.is_running = False
        self.closes = 0
        self.fail_start: Exception | None = None

    def get_format(self) -> dict[str, int | str]:
        return {
            'sample_rate': 48_000,
            'channels': 2,
            'sample_format': self.sample_format,
            'frames_per_chunk': 960,
        }

    def start(self) -> None:
        if self.fail_start:
            raise self.fail_start
        self.is_running = True

    def close(self) -> None:
        self.is_running = False
        self.closes += 1

    def emit(self, payload: bytes, frames: int = -1) -> None:
        self.callback(payload, frames)

    def stop_unexpectedly(self) -> None:
        self.is_running = False


class FakeFactory:
    def __init__(self, formats: tuple[str, ...] = ('float32',)) -> None:
        self.formats = iter(formats)
        self.pids: list[int] = []
        self.taps: list[FakeTap] = []

    def create(self, pid: int, callback: Callable[[bytes, int], None]) -> FakeTap:
        self.pids.append(pid)
        tap = FakeTap(callback, next(self.formats, 'float32'))
        self.taps.append(tap)
        return tap


class ScriptedResolver:
    def __init__(self, results: list[ProcessInfo | Exception]) -> None:
        self.results = iter(results)

    def __call__(self, _key: str) -> ProcessInfo:
        result = next(self.results)
        if isinstance(result, Exception):
            raise result
        return result


def selection() -> AudioSourceDescriptor:
    return AudioSourceDescriptor(
        'process:c:/apps/player.exe',
        AudioSourceKind.PROCESS,
        'Player.exe',
        process_id=42,
        executable_path=PATH,
    )


def make_source(
    resolver: ScriptedResolver,
    factory: FakeFactory,
    clock: Clock,
    *,
    reconnect_attempts: int = 3,
    queue_seconds: float = 2.0,
) -> ProcessAudioSource:
    sessions = iter(('session-1', 'session-2', 'session-3'))
    return ProcessAudioSource(
        selection(),
        AudioCaptureConfig(
            selection().id,
            queue_seconds=queue_seconds,
            reconnect_attempts=reconnect_attempts,
        ),
        resolver,
        factory,
        clock=clock,
        session_id_factory=lambda: next(sessions),
    )


def test_process_callback_emits_float32_for_selected_pid() -> None:
    clock = Clock()
    factory = FakeFactory()
    source = make_source(ScriptedResolver([ProcessInfo(42, 'Player.exe', PATH)]), factory, clock)
    session = source.start()
    samples = np.array([0.1, -0.1], dtype=np.float32)

    clock.value = 4.02
    factory.taps[0].emit(samples.tobytes(), frames=-1)
    frame = source.read(0)

    assert frame is not None
    assert frame.session_id == session
    assert (frame.sample_rate, frame.channels, frame.sequence) == (48_000, 2, 1)
    np.testing.assert_allclose(frame.samples, samples)
    assert factory.pids == [42]


def test_queue_capacity_uses_helper_chunk_duration() -> None:
    clock = Clock()
    factory = FakeFactory()
    source = make_source(
        ScriptedResolver([ProcessInfo(42, 'Player.exe', PATH)]),
        factory,
        clock,
        queue_seconds=0.02,
    )
    source.start()
    payload = np.zeros(1_920, dtype=np.float32).tobytes()

    factory.taps[0].emit(payload, frames=960)
    factory.taps[0].emit(payload, frames=960)

    frame = source.read(0)
    assert frame is not None
    assert frame.sequence == 2
    assert source.diagnostics().dropped_frames == 1


def test_int16_format_is_decoded_without_losing_metadata() -> None:
    clock = Clock()
    factory = FakeFactory(('int16',))
    source = make_source(ScriptedResolver([ProcessInfo(42, 'Player.exe', PATH)]), factory, clock)
    source.start()
    samples = np.array([100, -100], dtype=np.int16)

    factory.taps[0].emit(samples.tobytes())
    frame = source.read(0)

    assert frame is not None
    assert frame.samples.dtype == np.int16
    np.testing.assert_array_equal(frame.samples, samples)


def test_process_restart_reattaches_with_new_session_only() -> None:
    clock = Clock()
    resolver = ScriptedResolver(
        [
            ProcessInfo(42, 'Player.exe', PATH),
            AudioSourceNotFound('gone'),
            ProcessInfo(77, 'Player.exe', PATH),
        ]
    )
    factory = FakeFactory(('float32', 'float32'))
    source = make_source(resolver, factory, clock)
    first_session = source.start()
    first_tap = factory.taps[0]
    first_tap.stop_unexpectedly()

    assert source.read(0) is None
    assert source.diagnostics().state is SourceState.RECONNECTING
    assert source.reconnect_once() is False
    assert source.reconnect_once() is True
    assert source.session_id != first_session
    assert factory.pids == [42, 77]

    first_tap.emit(np.zeros(2, dtype=np.float32).tobytes())
    assert source.read(0) is None


def test_reconnect_exhaustion_is_failed_and_never_falls_back() -> None:
    clock = Clock()
    factory = FakeFactory()
    source = make_source(
        ScriptedResolver(
            [
                ProcessInfo(42, 'Player.exe', PATH),
                AudioSourceNotFound('gone'),
                AmbiguousAudioSource('two'),
            ]
        ),
        factory,
        clock,
        reconnect_attempts=2,
    )
    source.start()
    factory.taps[0].stop_unexpectedly()
    source.read(0)

    assert source.reconnect_once() is False
    with pytest.raises(AudioReconnectExhausted, match='two'):
        source.reconnect_once()
    assert source.diagnostics().state is SourceState.FAILED
    assert factory.pids == [42]


def test_failed_native_start_closes_tap_and_preserves_cause() -> None:
    clock = Clock()
    factory = FakeFactory()
    source = make_source(ScriptedResolver([ProcessInfo(42, 'Player.exe', PATH)]), factory, clock)
    original_create = factory.create

    def failing_create(pid: int, callback: Callable[[bytes, int], None]) -> FakeTap:
        tap = original_create(pid, callback)
        tap.fail_start = OSError('native start failed')
        return tap

    factory.create = failing_create  # type: ignore[method-assign]

    with pytest.raises(AudioSourceOpenError, match='native start failed') as caught:
        source.start()

    assert isinstance(caught.value.__cause__, OSError)
    assert factory.taps[0].closes == 1


def test_invalid_callback_length_marks_stream_failed() -> None:
    clock = Clock()
    factory = FakeFactory()
    source = make_source(ScriptedResolver([ProcessInfo(42, 'Player.exe', PATH)]), factory, clock)
    source.start()

    factory.taps[0].emit(b'bad')

    assert source.diagnostics().state is SourceState.FAILED
    assert source.read(0) is None
