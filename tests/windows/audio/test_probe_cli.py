import json

import numpy as np

from real_time_captions.audio.capture import (
    AudioSourceDescriptor,
    AudioSourceKind,
    CaptureDiagnostics,
)
from real_time_captions.audio.frame import AudioFrame
from real_time_captions.cli import main
from real_time_captions.contracts import SourceState
from real_time_captions.platforms.windows.audio import probe


def descriptor() -> AudioSourceDescriptor:
    return AudioSourceDescriptor(
        'default-output', AudioSourceKind.SYSTEM, 'Default output'
    )


class FakeSource:
    session_id = 'probe-session'

    def __init__(self) -> None:
        self.frames = [
            AudioFrame('probe-session', np.ones(1_600, dtype=np.float32), 16_000, 1, 1, 0.05),
            AudioFrame('probe-session', np.ones(1_600, dtype=np.float32) * 0.5, 16_000, 1, 2, 0.1),
        ]

    def start(self) -> str:
        return self.session_id

    def read(self, timeout: float | None = None) -> AudioFrame | None:
        return self.frames.pop(0) if self.frames else None

    def stop(self) -> None:
        return None

    def diagnostics(self) -> CaptureDiagnostics:
        return CaptureDiagnostics(SourceState.STOPPED, 3, None, None)


def test_audio_list_prints_deterministic_json(monkeypatch, capsys) -> None:
    monkeypatch.setattr(probe, 'discover_all_sources', lambda: (descriptor(),))

    assert main(['audio-list']) == 0

    assert json.loads(capsys.readouterr().out) == [
        {
            'available': True,
            'executable_path': None,
            'id': 'default-output',
            'kind': 'system',
            'name': 'Default output',
            'process_id': None,
        }
    ]


def test_probe_reports_metrics_without_pcm(monkeypatch, capsys) -> None:
    monkeypatch.setattr(probe, 'open_source', lambda descriptor_id: FakeSource())

    assert main(['audio-probe-system', '--seconds', '0.01']) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload['frames'] == 2
    assert payload['samples'] == 3_200
    assert payload['peak'] == 1.0
    assert payload['dropped_frames'] == 3
    assert payload['descriptor_id'] == 'default-output'
    assert 'pcm' not in payload


def test_process_probe_requires_source(capsys) -> None:
    assert main(['audio-probe-process', '--seconds', '0.01']) == 2
    assert 'source' in capsys.readouterr().err


def test_open_source_accepts_explicit_pid_even_when_exe_is_visible(
    monkeypatch,
) -> None:
    sentinel = object()
    monkeypatch.setattr(probe, 'PsutilProcessApi', lambda: object())
    monkeypatch.setattr(
        probe,
        'resolve_process_selection',
        lambda key, api: (_ for _ in ()).throw(
            AssertionError('open_source must resolve only when start is called')
        ),
    )
    monkeypatch.setattr(probe, 'FlexAudioProcessFactory', lambda: object())
    monkeypatch.setattr(
        probe, 'ProcessAudioSource', lambda descriptor, config, resolver, factory: sentinel
    )

    assert probe.open_source('process:pid:42') is sentinel
