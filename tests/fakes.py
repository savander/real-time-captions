from dataclasses import dataclass, field

from real_time_captions.captions.translation import (
    TranslationRequest,
    TranslationResult,
)
from real_time_captions.contracts import AsrHypothesis, InferenceRequest, Word


@dataclass
class FakeAsrBackend:
    hypotheses: list[tuple[str, tuple[Word, ...]]]
    requests: list[InferenceRequest] = field(default_factory=list, init=False)

    def transcribe(self, request: InferenceRequest) -> AsrHypothesis:
        self.requests.append(request)
        language, words = self.hypotheses.pop(0)
        return AsrHypothesis(
            request.session_id,
            request.sequence,
            words,
            language,
            1.0,
            request.audio_end,
        )


@dataclass
class FakeTranslationBackend:
    translations: dict[str, str]

    def translate(self, request: TranslationRequest) -> TranslationResult:
        source = ' '.join(
            part for part in (request.committed, request.provisional) if part
        )
        translated = self.translations[source]
        return TranslationResult(
            request.session_id,
            request.sequence,
            committed=translated if request.committed else '',
            provisional=translated if not request.committed else '',
        )
