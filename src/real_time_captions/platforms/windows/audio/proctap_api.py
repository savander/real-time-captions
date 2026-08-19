from collections.abc import Callable
from types import ModuleType
from typing import Protocol

from real_time_captions.platforms.windows.audio.dependencies import load_proctap


class ProcTap(Protocol):
    @property
    def is_running(self) -> bool: ...

    def get_format(self) -> dict[str, int | str]: ...

    def start(self) -> None: ...

    def close(self) -> None: ...


class ProcTapFactory:
    def __init__(self, module: ModuleType | None = None) -> None:
        self._module = module or load_proctap()

    def create(
        self, pid: int, callback: Callable[[bytes, int], None]
    ) -> ProcTap:
        return self._module.ProcessAudioCapture(
            pid=pid,
            on_data=callback,
            resample_quality='fast',
        )
