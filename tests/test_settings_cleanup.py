from pathlib import Path

import pytest

import real_time_captions.settings as settings_module
from real_time_captions.settings import AppSettings, SettingsStore


def test_save_preserves_write_failure_when_temporary_cleanup_also_fails(
    tmp_path, monkeypatch
) -> None:
    store = SettingsStore(tmp_path / 'settings.json')

    def fail_dump(*args: object, **kwargs: object) -> None:
        raise OSError('write failed')

    def fail_unlink(path: Path, missing_ok: bool = False) -> None:
        raise OSError('cleanup failed')

    monkeypatch.setattr(settings_module.json, 'dump', fail_dump)
    monkeypatch.setattr(Path, 'unlink', fail_unlink)

    with pytest.raises(OSError, match='^write failed$') as error:
        store.save(AppSettings())

    assert type(error.value) is OSError


def test_save_surfaces_cleanup_failure_when_no_primary_error_exists(tmp_path, monkeypatch) -> None:
    store = SettingsStore(tmp_path / 'settings.json')

    def fail_unlink(path: Path, missing_ok: bool = False) -> None:
        raise OSError('cleanup failed')

    monkeypatch.setattr(Path, 'unlink', fail_unlink)

    with pytest.raises(OSError, match='^cleanup failed$'):
        store.save(AppSettings())
