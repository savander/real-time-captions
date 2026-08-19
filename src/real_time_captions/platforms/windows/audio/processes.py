from dataclasses import dataclass
from types import ModuleType
from typing import Protocol

from real_time_captions.audio.capture import (
    AmbiguousAudioSource,
    AudioSourceDescriptor,
    AudioSourceKind,
    AudioSourceNotFound,
)
from real_time_captions.platforms.windows.audio.dependencies import load_psutil


@dataclass(frozen=True, slots=True)
class ProcessInfo:
    pid: int
    name: str
    executable_path: str | None


class ProcessDiscoveryApi(Protocol):
    def processes(self) -> tuple[ProcessInfo, ...]: ...


class PsutilProcessApi:
    def __init__(self, module: ModuleType | None = None) -> None:
        self._module = module or load_psutil()

    def processes(self) -> tuple[ProcessInfo, ...]:
        result: list[ProcessInfo] = []
        for process in self._module.process_iter(['pid', 'name', 'exe', 'status']):
            try:
                info = process.info
                if info.get('status') == self._module.STATUS_ZOMBIE:
                    continue
                pid = int(info['pid'])
                name = str(info.get('name') or f'PID {pid}')
                path = info.get('exe')
                result.append(ProcessInfo(pid, name, str(path) if path else None))
            except (
                self._module.NoSuchProcess,
                self._module.AccessDenied,
                self._module.ZombieProcess,
                KeyError,
                TypeError,
                ValueError,
            ):
                continue
        return tuple(result)


def _normalized_path(path: str) -> str:
    return path.replace('\\', '/').casefold()


def process_selection_key(process: ProcessInfo) -> str:
    if process.executable_path:
        return f'process:{_normalized_path(process.executable_path)}'
    return f'process:pid:{process.pid}'


def discover_process_sources(
    api: ProcessDiscoveryApi,
) -> tuple[AudioSourceDescriptor, ...]:
    processes = sorted(
        api.processes(), key=lambda item: (item.name.casefold(), item.pid)
    )
    return tuple(
        AudioSourceDescriptor(
            process_selection_key(process),
            AudioSourceKind.PROCESS,
            f'{process.name} (PID {process.pid})',
            process_id=process.pid,
            executable_path=process.executable_path,
        )
        for process in processes
    )


def resolve_process_selection(
    key: str, api: ProcessDiscoveryApi
) -> ProcessInfo:
    processes = api.processes()
    if key.startswith('process:pid:'):
        try:
            pid = int(key.removeprefix('process:pid:'))
        except ValueError as exc:
            raise AudioSourceNotFound(key) from exc
        matches = [process for process in processes if process.pid == pid]
    elif key.startswith('process:'):
        path = key.removeprefix('process:').casefold()
        matches = [
            process
            for process in processes
            if process.executable_path
            and _normalized_path(process.executable_path) == path
        ]
    else:
        raise AudioSourceNotFound(key)
    if not matches:
        raise AudioSourceNotFound(key)
    if len(matches) > 1:
        raise AmbiguousAudioSource(f'{len(matches)} processes match {key}')
    return matches[0]
