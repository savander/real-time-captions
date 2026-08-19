from io import BytesIO
from pathlib import Path
from threading import Event

import numpy as np

from real_time_captions.platforms.windows.audio.flexaudio_api import (
    FlexAudioProcessFactory,
)


class FakeProcess:
    def __init__(self, payload: bytes) -> None:
        self.stdout = BytesIO(payload)
        self.terminated = False

    def poll(self) -> int | None:
        return 0 if self.terminated else None

    def terminate(self) -> None:
        self.terminated = True

    def wait(self, timeout: float | None = None) -> int:
        return 0


def test_helper_stream_delivers_fixed_float32_chunks(tmp_path: Path) -> None:
    helper = tmp_path / 'rtc-audio-helper.exe'
    helper.touch()
    samples = np.arange(1_920, dtype=np.float32)
    process = FakeProcess(samples.tobytes())
    calls: list[tuple[bytes, int]] = []
    received = Event()
    commands: list[list[str]] = []

    def popen(command: list[str], **kwargs) -> FakeProcess:
        commands.append(command)
        return process

    tap = FlexAudioProcessFactory(helper, popen=popen).create(
        42, lambda payload, frames: (calls.append((payload, frames)), received.set())
    )
    tap.start()
    assert received.wait(1)
    tap.close()

    assert commands == [[str(helper), '42']]
    assert len(calls) == 1
    assert calls[0][1] == 960
    np.testing.assert_array_equal(
        np.frombuffer(calls[0][0], dtype=np.float32), samples
    )
    assert process.terminated


def test_helper_reports_standard_format_and_target_liveness(tmp_path: Path) -> None:
    helper = tmp_path / 'rtc-audio-helper.exe'
    helper.touch()
    process = FakeProcess(b'')
    alive = True
    tap = FlexAudioProcessFactory(
        helper,
        popen=lambda command, **kwargs: process,
        pid_alive=lambda pid: alive,
    ).create(42, lambda payload, frames: None)

    assert tap.get_format() == {
        'sample_rate': 48_000,
        'channels': 2,
        'sample_format': 'float32',
        'frames_per_chunk': 960,
    }
    tap.start()
    assert tap.is_running
    alive = False
    assert not tap.is_running
    tap.close()


def test_missing_helper_fails_before_spawning(tmp_path: Path) -> None:
    spawned = False

    def popen(command: list[str], **kwargs) -> FakeProcess:
        nonlocal spawned
        spawned = True
        return FakeProcess(b'')

    tap = FlexAudioProcessFactory(
        tmp_path / 'missing.exe', popen=popen
    ).create(42, lambda payload, frames: None)

    try:
        tap.start()
    except FileNotFoundError as exc:
        assert 'rtc-audio-helper' in str(exc)
    else:
        raise AssertionError('missing helper must fail')
    assert not spawned
