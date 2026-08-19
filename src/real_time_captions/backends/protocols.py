from typing import Protocol

from real_time_captions.audio.capture import CaptureDiagnostics
from real_time_captions.audio.frame import AudioFrame
from real_time_captions.contracts import AsrHypothesis, InferenceRequest


class AudioSource(Protocol):
    @property
    def session_id(self) -> str | None: ...

    def start(self) -> str: ...

    def read(self, timeout: float | None = None) -> AudioFrame | None: ...

    def stop(self) -> None: ...

    def diagnostics(self) -> CaptureDiagnostics: ...


class AsrBackend(Protocol):
    def transcribe(self, request: InferenceRequest) -> AsrHypothesis: ...
