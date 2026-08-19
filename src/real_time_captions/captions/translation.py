from dataclasses import dataclass
from typing import Protocol

from real_time_captions.contracts import TargetLanguage


@dataclass(frozen=True, slots=True)
class TranslationRequest:
    session_id: str
    sequence: int
    source_language: str
    target: TargetLanguage
    committed: str
    provisional: str


@dataclass(frozen=True, slots=True)
class TranslationResult:
    session_id: str
    sequence: int
    committed: str
    provisional: str


class TranslationBackend(Protocol):
    def translate(self, request: TranslationRequest) -> TranslationResult: ...
