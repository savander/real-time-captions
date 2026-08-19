from typing import Protocol

from real_time_captions.audio.frame import AudioFrame
from real_time_captions.contracts import AsrHypothesis, InferenceRequest


class AudioSource(Protocol):
    def read(self) -> AudioFrame | None: ...


class AsrBackend(Protocol):
    def transcribe(self, request: InferenceRequest) -> AsrHypothesis: ...
