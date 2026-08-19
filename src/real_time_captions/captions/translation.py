from dataclasses import dataclass
from typing import Protocol

from real_time_captions.contracts import TargetLanguage


@dataclass(frozen=True, slots=True)
class TranslationRequest:
    session_id: str
    # Monotonic source-state revision, not an ASR request sequence.
    sequence: int
    source_language: str
    target: TargetLanguage
    committed: str
    provisional: str
    committed_segment_id: int | None = None


@dataclass(frozen=True, slots=True)
class TranslationResult:
    session_id: str
    # Exact source-state revision copied from the request.
    sequence: int
    committed: str
    provisional: str
    committed_segment_id: int | None = None


class TranslationBackend(Protocol):
    def translate(self, request: TranslationRequest) -> TranslationResult: ...
