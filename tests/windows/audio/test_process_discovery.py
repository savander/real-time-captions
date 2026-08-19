from dataclasses import dataclass

import pytest

from real_time_captions.audio.capture import (
    AmbiguousAudioSource,
    AudioSourceKind,
    AudioSourceNotFound,
)
from real_time_captions.platforms.windows.audio.processes import (
    ProcessInfo,
    discover_process_sources,
    process_selection_key,
    resolve_process_selection,
)


@dataclass
class FakeProcessApi:
    entries: tuple[ProcessInfo, ...]

    def processes(self) -> tuple[ProcessInfo, ...]:
        return self.entries


def test_path_based_selection_survives_pid_change() -> None:
    original = ProcessInfo(10, 'Player.exe', r'C:\Apps\Player.exe')
    restarted = ProcessInfo(99, 'Player.exe', r'c:\apps\PLAYER.exe')
    key = process_selection_key(original)

    assert key == 'process:c:/apps/player.exe'
    assert resolve_process_selection(key, FakeProcessApi((restarted,))) == restarted


def test_multiple_matching_paths_are_ambiguous() -> None:
    api = FakeProcessApi(
        (
            ProcessInfo(10, 'Player.exe', r'C:\Apps\Player.exe'),
            ProcessInfo(11, 'Player.exe', r'C:\Apps\Player.exe'),
        )
    )

    with pytest.raises(AmbiguousAudioSource, match='2 processes'):
        resolve_process_selection('process:c:/apps/player.exe', api)


def test_inaccessible_path_uses_pid_only_key() -> None:
    process = ProcessInfo(42, 'Protected.exe', None)

    assert process_selection_key(process) == 'process:pid:42'
    assert resolve_process_selection('process:pid:42', FakeProcessApi((process,))) == process


def test_pid_resolution_uses_direct_lookup_when_available() -> None:
    process = ProcessInfo(42, 'Player.exe', r'C:\Apps\Player.exe')

    class DirectApi:
        def process(self, pid: int) -> ProcessInfo:
            assert pid == 42
            return process

        def processes(self) -> tuple[ProcessInfo, ...]:
            raise AssertionError('PID lookup must not enumerate every process')

    assert resolve_process_selection('process:pid:42', DirectApi()) == process


def test_vanished_process_is_typed() -> None:
    with pytest.raises(AudioSourceNotFound, match='process:pid:42'):
        resolve_process_selection('process:pid:42', FakeProcessApi(()))


def test_discovery_is_deterministic_and_keeps_duplicate_executables() -> None:
    api = FakeProcessApi(
        (
            ProcessInfo(8, 'Zulu.exe', r'C:\Z\Zulu.exe'),
            ProcessInfo(3, 'alpha.exe', r'C:\A\alpha.exe'),
            ProcessInfo(2, 'Alpha.exe', r'C:\A\alpha.exe'),
        )
    )

    sources = discover_process_sources(api)

    assert [(item.process_id, item.kind) for item in sources] == [
        (2, AudioSourceKind.PROCESS),
        (3, AudioSourceKind.PROCESS),
        (8, AudioSourceKind.PROCESS),
    ]
    assert sources[0].id == sources[1].id == 'process:c:/a/alpha.exe'
    assert sources[0].executable_path == r'C:\A\alpha.exe'


def test_invalid_pid_key_is_not_found() -> None:
    with pytest.raises(AudioSourceNotFound):
        resolve_process_selection('process:pid:nope', FakeProcessApi(()))
