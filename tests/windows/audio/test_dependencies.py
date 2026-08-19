import importlib
import tomllib
from pathlib import Path
from types import ModuleType

import pytest

from real_time_captions.audio.capture import MissingAudioDependency
from real_time_captions.platforms.windows.audio.dependencies import (
    load_psutil,
    load_pyaudio,
)


def test_manifest_declares_wheel_only_windows_audio_group() -> None:
    manifest = tomllib.loads(Path('pyproject.toml').read_text(encoding='utf-8'))
    dependencies = manifest['dependency-groups']['windows-audio']

    assert dependencies == [
        "PyAudioWPatch==0.2.12.8; sys_platform == 'win32'",
        "psutil>=7.0,<8; sys_platform == 'win32'",
    ]


@pytest.mark.parametrize(
    ('loader', 'module_name'),
    [
        (load_pyaudio, 'pyaudiowpatch'),
        (load_psutil, 'psutil'),
    ],
)
def test_missing_optional_module_has_typed_install_error(
    monkeypatch: pytest.MonkeyPatch, loader: object, module_name: str
) -> None:
    def missing(name: str) -> ModuleType:
        raise ModuleNotFoundError(name=name)

    monkeypatch.setattr(importlib, 'import_module', missing)

    with pytest.raises(
        MissingAudioDependency,
        match='uv sync --group windows-audio',
    ):
        loader()  # type: ignore[operator]


def test_loader_returns_imported_module(monkeypatch: pytest.MonkeyPatch) -> None:
    expected = ModuleType('pyaudiowpatch')
    monkeypatch.setattr(importlib, 'import_module', lambda name: expected)

    assert load_pyaudio() is expected
