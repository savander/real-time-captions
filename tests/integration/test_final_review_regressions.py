from dataclasses import dataclass, field

import numpy as np
import pytest

from real_time_captions.captions.translation import (
    TranslationRequest,
    TranslationResult,
)
from real_time_captions.contracts import (
    AsrHypothesis,
    InferenceRequest,
    TargetLanguage,
    Word,
)
from real_time_captions.core import RealtimeCaptionCore


@dataclass(frozen=True)
class HypothesisSpec:
    language: str
    confidence: float
    words: tuple[Word, ...]
    mismatched_session: bool = False


@dataclass
class ScriptedAsrBackend:
    hypotheses: list[HypothesisSpec]
    requests: list[InferenceRequest] = field(default_factory=list, init=False)

    def transcribe(self, request: InferenceRequest) -> AsrHypothesis:
        self.requests.append(request)
        spec = self.hypotheses.pop(0)
        return AsrHypothesis(
            'stale-session' if spec.mismatched_session else request.session_id,
            request.sequence,
            spec.words,
            spec.language,
            spec.confidence,
            request.audio_end,
        )


@dataclass
class RecordingTranslationBackend:
    translations: dict[str, str]
    fail_committed_attempts: int = 0
    requests: list[TranslationRequest] = field(default_factory=list, init=False)

    def translate(self, request: TranslationRequest) -> TranslationResult:
        self.requests.append(request)
        if request.committed and self.fail_committed_attempts:
            self.fail_committed_attempts -= 1
            raise RuntimeError('final translation failed')
        return TranslationResult(
            session_id=request.session_id,
            sequence=request.sequence,
            committed=(
                self.translations[request.committed] if request.committed else ''
            ),
            provisional=(
                self.translations[request.provisional] if request.provisional else ''
            ),
            committed_segment_id=request.committed_segment_id,
        )


def make_core(
    hypotheses: list[HypothesisSpec], translator: RecordingTranslationBackend
) -> RealtimeCaptionCore:
    return RealtimeCaptionCore(
        session_id='session',
        asr=ScriptedAsrBackend(hypotheses),
        translator=translator,
        target=TargetLanguage.POLISH,
        sample_rate=10,
        context_seconds=2,
    )


def test_native_provisional_is_immediate_but_translation_waits_for_confirmation() -> None:
    utterance = (Word('Ahoj', 0.0, 0.2),)
    translator = RecordingTranslationBackend({'Ahoj': 'Cze\u015b\u0107'})
    core = make_core(
        [
            HypothesisSpec('cs', 0.95, utterance),
            HypothesisSpec('cs', 0.96, utterance),
        ],
        translator,
    )

    first = core.submit_audio(np.ones(2, dtype=np.float32), audio_end=0.5)
    second = core.submit_audio(np.ones(2, dtype=np.float32), audio_end=0.5)

    assert first.source_provisional == 'Ahoj'
    assert first.language is None
    assert first.translation_provisional == ''
    assert second.language == 'cs'
    assert second.translation_provisional == 'Cze\u015b\u0107'
    assert [request.source_language for request in translator.requests] == ['cs']


def test_low_confidence_language_does_not_enable_translation() -> None:
    utterance = (Word('Ahoj', 0.0, 0.2),)
    translator = RecordingTranslationBackend({'Ahoj': 'Cze\u015b\u0107'})
    core = make_core(
        [HypothesisSpec('cs', 0.20, utterance)],
        translator,
    )

    snapshot = core.submit_audio(
        np.ones(2, dtype=np.float32), audio_end=0.5
    )

    assert snapshot.source_provisional == 'Ahoj'
    assert snapshot.language is None
    assert translator.requests == []


def test_finalize_advances_utterance_and_new_language_requires_fresh_confirmation() -> None:
    czech = (Word('Ahoj', 0.0, 0.2),)
    polish = (Word('Cze\u015b\u0107', 1.0, 1.2),)
    translator = RecordingTranslationBackend(
        {'Ahoj': 'Cze\u015b\u0107', 'Cze\u015b\u0107': 'Ahoj'}
    )
    core = make_core(
        [
            HypothesisSpec('cs', 0.95, czech),
            HypothesisSpec('cs', 0.96, czech),
            HypothesisSpec('pl', 0.95, polish),
            HypothesisSpec('pl', 0.96, polish),
        ],
        translator,
    )
    core.submit_audio(np.ones(2, dtype=np.float32), audio_end=0.5)
    core.submit_audio(np.ones(2, dtype=np.float32), audio_end=0.5)
    core.finalize()
    calls_after_finalize = len(translator.requests)

    first_polish = core.submit_audio(
        np.ones(2, dtype=np.float32), audio_end=1.3
    )

    assert first_polish.source_provisional == 'Cze\u015b\u0107'
    assert first_polish.language is None
    assert len(translator.requests) == calls_after_finalize

    second_polish = core.submit_audio(
        np.ones(2, dtype=np.float32), audio_end=1.3
    )

    assert second_polish.language == 'pl'
    assert len(translator.requests) == calls_after_finalize + 1
    assert translator.requests[-1].source_language == 'pl'


def test_unconfirmed_finalized_segment_cannot_inherit_next_utterance_language() -> None:
    czech = (Word('Ahoj', 0.0, 0.2),)
    polish = (Word('Cześć', 1.0, 1.2),)
    translator = RecordingTranslationBackend(
        {'Ahoj': 'Cześć', 'Cześć': 'Hello'}
    )
    core = make_core(
        [
            HypothesisSpec('cs', 0.95, czech),
            HypothesisSpec('pl', 0.95, polish),
            HypothesisSpec('pl', 0.96, polish),
        ],
        translator,
    )

    core.submit_audio(np.ones(2, dtype=np.float32), audio_end=0.5)
    finalized = core.finalize()
    core.submit_audio(np.ones(2, dtype=np.float32), audio_end=1.3)
    confirmed_polish = core.submit_audio(
        np.ones(2, dtype=np.float32), audio_end=1.3
    )

    assert finalized.source_committed == 'Ahoj'
    assert finalized.language is None
    assert confirmed_polish.source_committed == 'Ahoj'
    assert len(translator.requests) == 1
    assert translator.requests[0].source_language == 'pl'
    assert translator.requests[0].committed == ''
    assert translator.requests[0].provisional == 'Cześć'


def test_finalize_of_already_committed_source_advances_without_a_revision() -> None:
    first_words = (Word('Ahoj', 0.0, 0.2),)
    next_words = (Word('nov\u00e9', 1.0, 1.2),)
    translator = RecordingTranslationBackend(
        {'Ahoj': 'Cze\u015b\u0107', 'nov\u00e9': 'nowe'}
    )
    core = make_core(
        [
            HypothesisSpec('cs', 0.95, first_words),
            HypothesisSpec('cs', 0.96, first_words),
            HypothesisSpec('cs', 0.97, next_words),
        ],
        translator,
    )
    core.submit_audio(np.ones(2, dtype=np.float32), audio_end=1.1)
    committed = core.submit_audio(
        np.ones(2, dtype=np.float32), audio_end=1.1
    )

    finalized = core.finalize()
    next_utterance = core.submit_audio(
        np.ones(2, dtype=np.float32), audio_end=1.3
    )

    assert committed.source_committed == 'Ahoj'
    assert finalized.sequence == committed.sequence
    assert next_utterance.language is None
    assert next_utterance.source_provisional == 'nov\u00e9'


def test_pristine_and_repeated_successful_finalize_are_no_ops() -> None:
    translator = RecordingTranslationBackend({'Ahoj': 'Cze\u015b\u0107'})
    utterance = (Word('Ahoj', 0.0, 0.2),)
    core = make_core(
        [
            HypothesisSpec('cs', 0.95, utterance),
            HypothesisSpec('cs', 0.96, utterance),
        ],
        translator,
    )

    pristine = core.finalize()
    core.submit_audio(np.ones(2, dtype=np.float32), audio_end=0.5)
    provisional = core.submit_audio(np.ones(2, dtype=np.float32), audio_end=0.5)
    first = core.finalize()
    calls_after_first = len(translator.requests)
    second = core.finalize()

    assert pristine.sequence == -1
    assert pristine.language is None
    assert provisional.source_provisional == 'Ahoj'
    assert first.sequence == provisional.sequence + 1
    assert second == first
    assert len(translator.requests) == calls_after_first


def test_failed_final_translation_clears_old_provisional_and_retries_exact_segment() -> None:
    utterance = (Word('Ahoj', 0.0, 0.2),)
    translator = RecordingTranslationBackend(
        {'Ahoj': 'Cze\u015b\u0107'}, fail_committed_attempts=1
    )
    core = make_core(
        [
            HypothesisSpec('cs', 0.95, utterance),
            HypothesisSpec('cs', 0.96, utterance),
        ],
        translator,
    )
    core.submit_audio(np.ones(2, dtype=np.float32), audio_end=0.5)
    provisional = core.submit_audio(np.ones(2, dtype=np.float32), audio_end=0.5)
    assert provisional.translation_provisional == 'Cze\u015b\u0107'

    with pytest.raises(RuntimeError, match='final translation failed'):
        core.finalize()

    failed = core.snapshot()
    failed_request = translator.requests[-1]
    recovered = core.finalize()
    retry_request = translator.requests[-1]
    calls_after_retry = len(translator.requests)
    repeated = core.finalize()

    assert failed.source_committed == 'Ahoj'
    assert failed.source_provisional == ''
    assert failed.translation_provisional == ''
    assert failed_request.sequence == retry_request.sequence == failed.sequence
    assert failed_request.committed_segment_id == retry_request.committed_segment_id
    assert recovered.translation_committed == 'Cze\u015b\u0107'
    assert repeated == recovered
    assert len(translator.requests) == calls_after_retry


def test_mismatched_asr_cannot_influence_language_words_or_translation() -> None:
    stale = (Word('B\u0142\u0105d', 0.0, 0.2),)
    accepted = (Word('Ahoj', 0.0, 0.2),)
    translator = RecordingTranslationBackend({'Ahoj': 'Cze\u015b\u0107'})
    core = make_core(
        [
            HypothesisSpec('pl', 1.0, stale, mismatched_session=True),
            HypothesisSpec('cs', 0.95, accepted),
            HypothesisSpec('cs', 0.96, accepted),
        ],
        translator,
    )

    rejected = core.submit_audio(np.ones(2, dtype=np.float32), audio_end=0.5)
    first_valid = core.submit_audio(np.ones(2, dtype=np.float32), audio_end=0.5)
    confirmed = core.submit_audio(np.ones(2, dtype=np.float32), audio_end=1.1)

    assert rejected.sequence == -1
    assert first_valid.sequence == 1
    assert first_valid.language is None
    assert confirmed.sequence == 2
    assert confirmed.source_committed == 'Ahoj'
    assert confirmed.language == 'cs'
    assert len(translator.requests) == 1
    assert translator.requests[0].committed == 'Ahoj'
    assert 'B\u0142\u0105d' not in translator.requests[0].committed
