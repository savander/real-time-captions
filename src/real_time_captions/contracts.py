from dataclasses import dataclass
from enum import StrEnum

import numpy as np


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
    # Session-relative seconds from the start of the current capture session.
    start: float
    end: float


@dataclass(frozen=True, slots=True)
class InferenceRequest:
    session_id: str
    sequence: int
    samples: np.ndarray
    # Session-relative end of the represented audio window, in seconds.
    audio_end: float

    def __post_init__(self) -> None:
        owned = np.array(self.samples, copy=True)
        owned.setflags(write=False)
        object.__setattr__(self, 'samples', owned)


@dataclass(frozen=True, slots=True)
class AsrHypothesis:
    session_id: str
    sequence: int
    words: tuple[Word, ...]
    language: str
    language_confidence: float
    # Same session-relative clock as every contained Word.
    audio_end: float


@dataclass(frozen=True, slots=True)
class StabilizedText:
    committed: tuple[Word, ...]
    provisional: tuple[Word, ...]


@dataclass(frozen=True, slots=True)
class CaptionSnapshot:
    session_id: str
    # Monotonic source-state revision, independent of ASR request sequence.
    sequence: int
    language: str | None
    source_committed: str
    source_provisional: str
    translation_committed: str
    translation_provisional: str
