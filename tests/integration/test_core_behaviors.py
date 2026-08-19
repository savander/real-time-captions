from dataclasses import FrozenInstanceError

import numpy as np
import pytest

from real_time_captions.contracts import (
    AsrHypothesis,
    InferenceRequest,
    TargetLanguage,
    Word,
)
from real_time_captions.core import RealtimeCaptionCore
from tests.fakes import FakeAsrBackend, FakeTranslationBackend


def test_core_bypasses_translation_for_native_captions() -> None:
    asr = FakeAsrBackend(
        hypotheses=[('cs', (Word('Ahoj', 0.0, 0.4),))]
    )
    core = RealtimeCaptionCore(
        session_id='native',
        asr=asr,
        translator=FakeTranslationBackend({}),
        target=TargetLanguage.NATIVE,
        sample_rate=16_000,
        context_seconds=5,
    )

    snapshot = core.submit_audio(
        np.ones(1_000, dtype=np.float32), audio_end=0.5
    )

    assert snapshot.source_provisional == 'Ahoj'
    assert snapshot.translation_committed == ''
    assert snapshot.translation_provisional == ''


def test_finalize_commits_the_last_confirmed_provisional_caption() -> None:
    utterance = (
        Word('Dobr\u00fd', 0.0, 0.4),
        Word('den', 0.4, 0.8),
    )
    asr = FakeAsrBackend(hypotheses=[('cs', utterance), ('cs', utterance)])
    core = RealtimeCaptionCore(
        session_id='finalize',
        asr=asr,
        translator=FakeTranslationBackend(
            {'Dobr\u00fd den': 'Dzie\u0144 dobry'}
        ),
        target=TargetLanguage.POLISH,
        sample_rate=16_000,
        context_seconds=5,
    )
    core.submit_audio(np.ones(1_000, dtype=np.float32), audio_end=0.8)
    provisional = core.submit_audio(
        np.ones(1_000, dtype=np.float32), audio_end=0.8
    )

    finalized = core.finalize()

    assert provisional.source_provisional == 'Dobr\u00fd den'
    assert finalized.source_committed == 'Dobr\u00fd den'
    assert finalized.source_provisional == ''
    assert finalized.translation_committed == 'Dzie\u0144 dobry'
    assert finalized.translation_provisional == ''


def test_returned_snapshots_remain_immutable_and_coherent() -> None:
    words = (Word('Ahoj', 0.0, 0.2),)
    core = RealtimeCaptionCore(
        session_id='snapshots',
        asr=FakeAsrBackend(hypotheses=[('cs', words), ('cs', words)]),
        translator=FakeTranslationBackend({'Ahoj': 'Cze\u015b\u0107'}),
        target=TargetLanguage.POLISH,
        sample_rate=10,
        context_seconds=2,
    )

    first = core.submit_audio(np.ones(5, dtype=np.float32), audio_end=0.5)
    second = core.submit_audio(np.ones(5, dtype=np.float32), audio_end=1.5)

    assert first.sequence == 1
    assert first.source_provisional == 'Ahoj'
    assert first.translation_provisional == ''
    assert second.sequence == 2
    assert second.source_committed == 'Ahoj'
    assert second.translation_committed == 'Cze\u015b\u0107'
    assert core.snapshot() == second
    with pytest.raises(FrozenInstanceError):
        first.sequence = 99  # type: ignore[misc]


class FirstResultMismatchedAsrBackend:
    def __init__(self, mismatch: str) -> None:
        self._mismatch = mismatch
        self._calls = 0
        self._words = (Word('Ahoj', 0.0, 0.2),)

    def transcribe(self, request: InferenceRequest) -> AsrHypothesis:
        self._calls += 1
        session_id = request.session_id
        sequence = request.sequence
        if self._calls == 1:
            if self._mismatch == 'session':
                session_id = 'stale-session'
            else:
                sequence += 10
        return AsrHypothesis(
            session_id,
            sequence,
            self._words,
            'cs',
            1.0,
            request.audio_end,
        )


@pytest.mark.parametrize('mismatch', ['session', 'sequence'])
def test_mismatched_asr_result_cannot_mutate_caption_state(
    mismatch: str,
) -> None:
    core = RealtimeCaptionCore(
        session_id='current-session',
        asr=FirstResultMismatchedAsrBackend(mismatch),
        translator=FakeTranslationBackend({}),
        target=TargetLanguage.NATIVE,
        sample_rate=10,
        context_seconds=2,
    )

    rejected = core.submit_audio(
        np.ones(5, dtype=np.float32), audio_end=0.5
    )
    accepted = core.submit_audio(
        np.ones(5, dtype=np.float32), audio_end=1.5
    )

    assert rejected.sequence == -1
    assert rejected.language is None
    assert rejected.source_committed == ''
    assert rejected.source_provisional == ''
    assert accepted.sequence == 1
    assert accepted.source_committed == ''
    assert accepted.source_provisional == 'Ahoj'


def test_asr_receives_only_the_bounded_rolling_audio_context() -> None:
    asr = FakeAsrBackend(hypotheses=[('cs', ()), ('cs', ())])
    core = RealtimeCaptionCore(
        session_id='bounded',
        asr=asr,
        translator=FakeTranslationBackend({}),
        target=TargetLanguage.NATIVE,
        sample_rate=4,
        context_seconds=2,
    )

    core.submit_audio(
        np.array([1, 2, 3, 4, 5, 6], dtype=np.float32),
        audio_end=1.5,
    )
    core.submit_audio(
        np.array([7, 8, 9, 10, 11], dtype=np.float32),
        audio_end=2.75,
    )

    assert len(asr.requests) == 2
    np.testing.assert_array_equal(
        asr.requests[0].samples,
        np.array([1, 2, 3, 4, 5, 6], dtype=np.float32),
    )
    np.testing.assert_array_equal(
        asr.requests[1].samples,
        np.array([4, 5, 6, 7, 8, 9, 10, 11], dtype=np.float32),
    )
