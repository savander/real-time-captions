from dataclasses import dataclass
from enum import StrEnum

from real_time_captions.contracts import SourceState


class AudioSourceKind(StrEnum):
    SYSTEM = 'system'
    PROCESS = 'process'
    MICROPHONE = 'microphone'


@dataclass(frozen=True, slots=True)
class AudioSourceDescriptor:
    id: str
    kind: AudioSourceKind
    name: str
    available: bool = True
    process_id: int | None = None
    executable_path: str | None = None


@dataclass(frozen=True, slots=True)
class AudioCaptureConfig:
    descriptor_id: str
    queue_seconds: float = 2.0
    reconnect_attempts: int = 3

    def __post_init__(self) -> None:
        if not self.descriptor_id:
            raise ValueError('descriptor_id must not be empty')
        if self.queue_seconds <= 0:
            raise ValueError('queue_seconds must be positive')
        if isinstance(self.reconnect_attempts, bool) or self.reconnect_attempts <= 0:
            raise ValueError('reconnect_attempts must be a positive integer')


@dataclass(frozen=True, slots=True)
class CaptureDiagnostics:
    state: SourceState
    dropped_frames: int
    silent_seconds: float | None
    last_error: str | None


class AudioCaptureError(RuntimeError):
    pass


class UnsupportedAudioCapture(AudioCaptureError):
    pass


class MissingAudioDependency(AudioCaptureError):
    pass


class AudioSourceNotFound(AudioCaptureError):
    pass


class AmbiguousAudioSource(AudioCaptureError):
    pass


class AudioSourceOpenError(AudioCaptureError):
    pass


class AudioStreamInterrupted(AudioCaptureError):
    pass


class InvalidAudioLifecycle(AudioCaptureError):
    pass


class AudioReconnectExhausted(AudioCaptureError):
    pass
