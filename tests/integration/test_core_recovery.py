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
from tests.fakes import FakeAsrBackend, FakeTranslationBackend


class ReentrantFailingAsrBackend:
    def __init__(self) -> None:
        self.core: RealtimeCaptionCore | None = None
        self.sequences: list[int] = []

    def transcribe(self, request: InferenceRequest) -> AsrHypothesis:
        self.sequences.append(request.sequence)
        if len(self.sequences) == 1:
            assert self.core is not None
            self.core.submit_audio(
                np.ones(2, dtype=np.float32), audio_end=1.0
            )
            raise RuntimeError('asr failed')
        return AsrHypothesis(
            request.session_id,
            request.sequence,
            (Word('Ahoj', 0.0, 0.2),),
            'cs',
            1.0,
            request.audio_end,
        )


class ReentrantFailingTranslationBackend:
    def __init__(self) -> None:
        self.core: RealtimeCaptionCore | None = None
        self.calls = 0

    def translate(self, request: TranslationRequest) -> TranslationResult:
        self.calls += 1
        if self.calls == 1:
            assert self.core is not None
            self.core.submit_audio(
                np.ones(2, dtype=np.float32), audio_end=2.5
            )
            raise RuntimeError('translation failed')
        return TranslationResult(
            request.session_id,
            request.sequence,
            committed='Cze\u015b\u0107' if request.committed else '',
            provisional='Cze\u015b\u0107' if request.provisional else '',
            committed_segment_id=request.committed_segment_id,
        )


def test_asr_error_discards_pending_work_and_later_submission_runs() -> None:
    asr = ReentrantFailingAsrBackend()
    core = RealtimeCaptionCore(
        session_id='asr-recovery',
        asr=asr,
        translator=FakeTranslationBackend({}),
        target=TargetLanguage.NATIVE,
        sample_rate=10,
        context_seconds=2,
    )
    asr.core = core

    with pytest.raises(RuntimeError, match='asr failed'):
        core.submit_audio(np.ones(2, dtype=np.float32), audio_end=0.5)

    recovered = core.submit_audio(
        np.ones(2, dtype=np.float32), audio_end=2.0
    )

    assert asr.sequences == [1, 3]
    assert recovered.sequence == 1
    assert recovered.source_committed == ''
    assert recovered.source_provisional == 'Ahoj'


def test_translation_error_preserves_pending_commit_for_later_processing() -> None:
    words = (Word('Ahoj', 0.0, 0.2),)
    asr = FakeAsrBackend(
        hypotheses=[('cs', words), ('cs', words), ('cs', words)]
    )
    translator = ReentrantFailingTranslationBackend()
    core = RealtimeCaptionCore(
        session_id='translation-recovery',
        asr=asr,
        translator=translator,
        target=TargetLanguage.POLISH,
        sample_rate=10,
        context_seconds=2,
    )
    translator.core = core

    first = core.submit_audio(
        np.ones(2, dtype=np.float32), audio_end=0.5
    )
    with pytest.raises(RuntimeError, match='translation failed'):
        core.submit_audio(np.ones(2, dtype=np.float32), audio_end=2.0)

    after_error = core.snapshot()
    recovered = core.submit_audio(
        np.ones(2, dtype=np.float32), audio_end=3.0
    )

    assert first.sequence == 1
    assert first.source_provisional == 'Ahoj'
    assert after_error.sequence == 2
    assert after_error.source_committed == 'Ahoj'
    assert after_error.translation_provisional == ''
    assert [request.sequence for request in asr.requests] == [1, 2, 4]
    assert recovered.sequence == 2
    assert recovered.source_committed == 'Ahoj'
    assert recovered.translation_committed == 'Cze\u015b\u0107'
