from dataclasses import dataclass
from enum import StrEnum


class SourceState(StrEnum):
    STARTING = 'starting'
    RUNNING = 'running'
    RECONNECTING = 'reconnecting'
    FAILED = 'failed'
    STOPPED = 'stopped'


class TargetLanguage(StrEnum):
    NATIVE = 'native'
    ENGLISH = 'en'
    POLISH = 'pl'


class ViewMode(StrEnum):
    TARGET_ONLY = 'target_only'
    BILINGUAL = 'bilingual'


@dataclass(frozen=True, slots=True)
class Word:
    text: str
    start: float
    end: float


@dataclass(frozen=True, slots=True)
class InferenceRequest:
    session_id: str
    sequence: int
    samples: object
    audio_end: float


@dataclass(frozen=True, slots=True)
class AsrHypothesis:
    session_id: str
    sequence: int
    words: tuple[Word, ...]
    language: str
    language_confidence: float
    audio_end: float


@dataclass(frozen=True, slots=True)
class StabilizedText:
    committed: tuple[Word, ...]
    provisional: tuple[Word, ...]


@dataclass(frozen=True, slots=True)
class CaptionSnapshot:
    session_id: str
    sequence: int
    language: str | None
    source_committed: str
    source_provisional: str
    translation_committed: str
    translation_provisional: str
