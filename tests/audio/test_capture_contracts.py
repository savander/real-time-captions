from dataclasses import FrozenInstanceError

import pytest

from real_time_captions.audio.capture import (
    AudioCaptureConfig,
    AudioSourceDescriptor,
    AudioSourceKind,
    CaptureDiagnostics,
)
from real_time_captions.contracts import SourceState


def test_descriptor_is_immutable_and_keeps_process_identity() -> None:
    descriptor = AudioSourceDescriptor(
        id='process:c:/apps/player.exe',
        kind=AudioSourceKind.PROCESS,
        name='Player',
        available=True,
        process_id=42,
        executable_path='C:/Apps/Player.exe',
    )

    assert descriptor.process_id == 42
    with pytest.raises(FrozenInstanceError):
        descriptor.name = 'changed'  # type: ignore[misc]


@pytest.mark.parametrize('queue_seconds', [0.0, -1.0])
def test_capture_config_rejects_non_positive_queue_duration(
    queue_seconds: float,
) -> None:
    with pytest.raises(ValueError, match='queue_seconds'):
        AudioCaptureConfig('default-output', queue_seconds=queue_seconds)


def test_capture_config_rejects_empty_descriptor_id() -> None:
    with pytest.raises(ValueError, match='descriptor_id'):
        AudioCaptureConfig('')


def test_diagnostics_exposes_lifecycle_and_drop_count() -> None:
    diagnostics = CaptureDiagnostics(SourceState.RUNNING, 3, 1.25, None)

    assert diagnostics.dropped_frames == 3
    assert diagnostics.silent_seconds == 1.25
