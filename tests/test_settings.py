import json

import pytest

from real_time_captions.contracts import TargetLanguage, ViewMode
from real_time_captions.settings import AppSettings, SettingsStore


def test_missing_settings_loads_defaults_without_warnings(tmp_path) -> None:
    store = SettingsStore(tmp_path / 'settings.json')

    assert store.load() == AppSettings()
    assert store.warnings == ()


def test_settings_round_trip_uses_schema_version_and_preserves_non_ascii_lock(
    tmp_path,
) -> None:
    path = tmp_path / 'settings.json'
    store = SettingsStore(path)
    expected = AppSettings(
        target=TargetLanguage.POLISH,
        view_mode=ViewMode.BILINGUAL,
        profile='quality',
        locked_language='польский-Łódź',
    )

    store.save(expected)

    assert store.load() == expected
    assert json.loads(path.read_text(encoding='utf-8')) == {
        'schema_version': 1,
        'target': 'pl',
        'view_mode': 'bilingual',
        'profile': 'quality',
        'locked_language': 'польский-Łódź',
    }


def test_truncated_settings_file_falls_back_to_defaults_with_warning(tmp_path) -> None:
    path = tmp_path / 'settings.json'
    path.write_text('{"schema_version": 1, "target": ', encoding='utf-8')
    store = SettingsStore(path)

    assert store.load() == AppSettings()
    assert store.warnings


def test_wrong_schema_falls_back_to_defaults_with_warning(tmp_path) -> None:
    path = tmp_path / 'settings.json'
    path.write_text('{"schema_version": 2}', encoding='utf-8')
    store = SettingsStore(path)

    assert store.load() == AppSettings()
    assert store.warnings == ('unsupported settings schema',)


@pytest.mark.parametrize(
    ('field', 'invalid_value', 'expected'),
    [
        ('target', 'fr', AppSettings(target=TargetLanguage.NATIVE)),
        ('view_mode', 'side_by_side', AppSettings(view_mode=ViewMode.TARGET_ONLY)),
        ('profile', 'low_latency', AppSettings(profile='balanced')),
        ('locked_language', 42, AppSettings(locked_language=None)),
    ],
)
def test_invalid_setting_field_uses_its_default_without_discarding_valid_fields(
    tmp_path, field: str, invalid_value: object, expected: AppSettings
) -> None:
    path = tmp_path / 'settings.json'
    payload = {
        'schema_version': 1,
        'target': 'pl',
        'view_mode': 'bilingual',
        'profile': 'fast',
        'locked_language': 'English',
    }
    payload[field] = invalid_value
    path.write_text(json.dumps(payload), encoding='utf-8')
    store = SettingsStore(path)

    loaded = store.load()

    assert loaded == AppSettings(
        target=expected.target if field == 'target' else TargetLanguage.POLISH,
        view_mode=expected.view_mode if field == 'view_mode' else ViewMode.BILINGUAL,
        profile=expected.profile if field == 'profile' else 'fast',
        locked_language=expected.locked_language if field == 'locked_language' else 'English',
    )
    assert store.warnings == (f'invalid {field}',)


def test_load_resets_warnings_after_a_successful_recovery(tmp_path) -> None:
    path = tmp_path / 'settings.json'
    store = SettingsStore(path)
    path.write_text('{', encoding='utf-8')
    store.load()

    store.save(AppSettings(profile='custom'))

    assert store.load() == AppSettings(profile='custom')
    assert store.warnings == ()


def test_save_replaces_existing_file_without_leaving_a_sibling_temp_file(tmp_path) -> None:
    path = tmp_path / 'settings.json'
    path.write_text('obsolete', encoding='utf-8')
    store = SettingsStore(path)

    store.save(AppSettings(profile='fast'))

    assert json.loads(path.read_text(encoding='utf-8'))['profile'] == 'fast'
    assert list(tmp_path.glob('settings.json.tmp')) == []
