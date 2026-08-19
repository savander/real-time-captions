import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from real_time_captions.contracts import TargetLanguage, ViewMode


_SCHEMA_VERSION = 1
_PROFILES = frozenset({'fast', 'balanced', 'quality', 'custom'})


@dataclass(frozen=True, slots=True)
class AppSettings:
    target: TargetLanguage = TargetLanguage.NATIVE
    view_mode: ViewMode = ViewMode.TARGET_ONLY
    profile: str = 'balanced'
    locked_language: str | None = None


class SettingsStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.warnings: tuple[str, ...] = ()

    def load(self) -> AppSettings:
        try:
            raw = json.loads(self.path.read_text(encoding='utf-8'))
        except FileNotFoundError:
            self.warnings = ()
            return AppSettings()
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
            self.warnings = (str(error),)
            return AppSettings()

        if not isinstance(raw, dict):
            self.warnings = ('invalid settings document',)
            return AppSettings()
        version = raw.get('schema_version')
        if type(version) is not int or version != _SCHEMA_VERSION:
            self.warnings = ('unsupported settings schema',)
            return AppSettings()

        defaults = AppSettings()
        warnings: list[str] = []

        target = self._read_target(raw, defaults, warnings)
        view_mode = self._read_view_mode(raw, defaults, warnings)
        profile = self._read_profile(raw, defaults, warnings)
        locked_language = self._read_locked_language(raw, warnings)

        self.warnings = tuple(warnings)
        return AppSettings(target, view_mode, profile, locked_language)

    def save(self, settings: AppSettings) -> None:
        if not isinstance(settings.profile, str) or settings.profile not in _PROFILES:
            raise ValueError('profile must be an approved product profile')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {'schema_version': _SCHEMA_VERSION, **asdict(settings)}
        temporary: Path | None = None
        primary_error = False

        try:
            with tempfile.NamedTemporaryFile(
                mode='w',
                encoding='utf-8',
                dir=self.path.parent,
                prefix=f'.{self.path.name}.',
                suffix='.tmp',
                delete=False,
            ) as stream:
                temporary = Path(stream.name)
                json.dump(payload, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(self.path)
        except BaseException:
            primary_error = True
            raise
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    if not primary_error:
                        raise

    @staticmethod
    def _read_target(
        raw: dict[str, object], defaults: AppSettings, warnings: list[str]
    ) -> TargetLanguage:
        try:
            return TargetLanguage(raw.get('target', defaults.target))
        except (TypeError, ValueError):
            warnings.append('invalid target')
            return defaults.target

    @staticmethod
    def _read_view_mode(
        raw: dict[str, object], defaults: AppSettings, warnings: list[str]
    ) -> ViewMode:
        try:
            return ViewMode(raw.get('view_mode', defaults.view_mode))
        except (TypeError, ValueError):
            warnings.append('invalid view_mode')
            return defaults.view_mode

    @staticmethod
    def _read_profile(
        raw: dict[str, object], defaults: AppSettings, warnings: list[str]
    ) -> str:
        profile = raw.get('profile', defaults.profile)
        if not isinstance(profile, str) or profile not in _PROFILES:
            warnings.append('invalid profile')
            return defaults.profile
        return profile

    @staticmethod
    def _read_locked_language(raw: dict[str, object], warnings: list[str]) -> str | None:
        locked_language = raw.get('locked_language')
        if locked_language is not None and not isinstance(locked_language, str):
            warnings.append('invalid locked_language')
            return None
        return locked_language
