import importlib
from types import ModuleType

from real_time_captions.audio.capture import MissingAudioDependency


def _load(module_name: str) -> ModuleType:
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        raise MissingAudioDependency(
            f'{module_name} is unavailable; run '
            '`uv sync --group windows-audio` on supported Windows x64'
        ) from exc


def load_pyaudio() -> ModuleType:
    return _load('pyaudiowpatch')


def load_proctap() -> ModuleType:
    return _load('proctap')


def load_psutil() -> ModuleType:
    return _load('psutil')
