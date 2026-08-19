import json
from pathlib import Path

import pytest

import real_time_captions.settings as settings_module
from real_time_captions.settings import AppSettings, SettingsStore


@pytest.mark.parametrize('version', (True, 1.0))
def test_non_integer_schema_version_falls_back_to_defaults_with_warning(
    tmp_path, version: bool | float
) -> None:
    path = tmp_path / 'settings.json'
    path.write_text(json.dumps({'schema_version': version}), encoding='utf-8')
    store = SettingsStore(path)

    assert store.load() == AppSettings()
    assert store.warnings == ('unsupported settings schema',)


def test_save_rejects_invalid_profile_without_touching_destination(tmp_path) -> None:
    path = tmp_path / 'settings.json'
    path.write_text('unchanged', encoding='utf-8')
    store = SettingsStore(path)

    with pytest.raises(ValueError, match='profile'):
        store.save(AppSettings(profile='low_latency'))

    assert path.read_text(encoding='utf-8') == 'unchanged'
    assert list(tmp_path.glob('*.tmp')) == []


def test_save_uses_a_unique_sibling_temporary_file(tmp_path, monkeypatch) -> None:
    path = tmp_path / 'settings.json'
    store = SettingsStore(path)
    replacements: list[tuple[Path, Path]] = []
    original_replace = Path.replace

    def record_replace(source: Path, target: Path) -> Path:
        replacements.append((source, target))
        return original_replace(source, target)

    monkeypatch.setattr(Path, 'replace', record_replace)

    store.save(AppSettings())

    temporary, destination = replacements[0]
    assert destination == path
    assert temporary.parent == path.parent
    assert temporary != path.with_suffix(path.suffix + '.tmp')
    assert temporary.name.startswith('.settings.json.')
    assert temporary.name.endswith('.tmp')


def test_save_cleans_up_temporary_file_after_a_write_failure(tmp_path, monkeypatch) -> None:
    path = tmp_path / 'settings.json'
    path.write_text('unchanged', encoding='utf-8')
    store = SettingsStore(path)

    def fail_dump(*args: object, **kwargs: object) -> None:
        raise OSError('write failed')

    monkeypatch.setattr(settings_module.json, 'dump', fail_dump)

    with pytest.raises(OSError, match='write failed'):
        store.save(AppSettings())

    assert path.read_text(encoding='utf-8') == 'unchanged'
    assert list(tmp_path.glob('*.tmp')) == []


def test_save_cleans_up_temporary_file_after_a_replace_failure(tmp_path, monkeypatch) -> None:
    path = tmp_path / 'settings.json'
    path.write_text('unchanged', encoding='utf-8')
    store = SettingsStore(path)

    def fail_replace(source: Path, target: Path) -> Path:
        raise OSError('replace failed')

    monkeypatch.setattr(Path, 'replace', fail_replace)

    with pytest.raises(OSError, match='replace failed'):
        store.save(AppSettings())

    assert path.read_text(encoding='utf-8') == 'unchanged'
    assert list(tmp_path.glob('*.tmp')) == []
