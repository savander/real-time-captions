from collections.abc import Callable
from pathlib import Path
import subprocess
from threading import Event, Thread
from typing import Any, Protocol


SAMPLE_RATE = 48_000
CHANNELS = 2
FRAMES_PER_CHUNK = 960
BYTES_PER_CHUNK = FRAMES_PER_CHUNK * CHANNELS * 4


class ProcessTap(Protocol):
    @property
    def is_running(self) -> bool: ...

    def get_format(self) -> dict[str, int | str]: ...

    def start(self) -> None: ...

    def close(self) -> None: ...


def default_helper_path() -> Path:
    packaged = Path(__file__).with_name('bin') / 'rtc-audio-helper.exe'
    if packaged.exists():
        return packaged
    return (
        Path(__file__).parents[5]
        / 'native'
        / 'windows_audio_helper'
        / 'target'
        / 'release'
        / 'rtc-audio-helper.exe'
    )


class FlexAudioProcess:
    def __init__(
        self,
        helper: Path,
        pid: int,
        callback: Callable[[bytes, int], None],
        *,
        popen: Callable[..., Any] = subprocess.Popen,
        pid_alive: Callable[[int], bool],
    ) -> None:
        self._helper = helper
        self._pid = pid
        self._callback = callback
        self._popen = popen
        self._pid_alive = pid_alive
        self._process: Any | None = None
        self._reader: Thread | None = None
        self._closing = Event()

    @property
    def is_running(self) -> bool:
        return (
            self._process is not None
            and self._process.poll() is None
            and self._pid_alive(self._pid)
        )

    def get_format(self) -> dict[str, int | str]:
        return {
            'sample_rate': SAMPLE_RATE,
            'channels': CHANNELS,
            'sample_format': 'float32',
            'frames_per_chunk': FRAMES_PER_CHUNK,
        }

    def start(self) -> None:
        if not self._helper.is_file():
            raise FileNotFoundError(
                f'rtc-audio-helper is missing at {self._helper}; '
                'build native/windows_audio_helper first'
            )
        self._closing.clear()
        self._process = self._popen(
            [str(self._helper), str(self._pid)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
        self._reader = Thread(target=self._read_stdout, daemon=True)
        self._reader.start()

    def _read_stdout(self) -> None:
        process = self._process
        if process is None or process.stdout is None:
            return
        pending = bytearray()
        while not self._closing.is_set():
            chunk = process.stdout.read(BYTES_PER_CHUNK - len(pending))
            if not chunk:
                break
            pending.extend(chunk)
            if len(pending) == BYTES_PER_CHUNK:
                self._callback(bytes(pending), FRAMES_PER_CHUNK)
                pending.clear()

    def close(self) -> None:
        self._closing.set()
        process = self._process
        self._process = None
        if process is not None:
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=2)
        reader = self._reader
        self._reader = None
        if reader is not None:
            reader.join(timeout=2)


class FlexAudioProcessFactory:
    def __init__(
        self,
        helper: Path | None = None,
        *,
        popen: Callable[..., Any] = subprocess.Popen,
        pid_alive: Callable[[int], bool] | None = None,
    ) -> None:
        if pid_alive is None:
            from real_time_captions.platforms.windows.audio.dependencies import (
                load_psutil,
            )

            pid_alive = load_psutil().pid_exists
        self._helper = helper or default_helper_path()
        self._popen = popen
        self._pid_alive = pid_alive

    def create(
        self, pid: int, callback: Callable[[bytes, int], None]
    ) -> ProcessTap:
        return FlexAudioProcess(
            self._helper,
            pid,
            callback,
            popen=self._popen,
            pid_alive=self._pid_alive,
        )
