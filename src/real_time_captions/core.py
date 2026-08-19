import numpy as np

from real_time_captions.audio.ring_buffer import AudioRingBuffer
from real_time_captions.backends.protocols import AsrBackend
from real_time_captions.captions.store import CaptionStore
from real_time_captions.captions.translation import TranslationBackend
from real_time_captions.contracts import (
    CaptionSnapshot,
    InferenceRequest,
    TargetLanguage,
    Word,
)
from real_time_captions.streaming.language import LanguageSmoother
from real_time_captions.streaming.scheduler import LatestWindowScheduler
from real_time_captions.streaming.stabilizer import HypothesisStabilizer


class RealtimeCaptionCore:
    def __init__(
        self,
        session_id: str,
        asr: AsrBackend,
        translator: TranslationBackend,
        target: TargetLanguage,
        sample_rate: int,
        context_seconds: int,
    ) -> None:
        self._session_id = session_id
        self._asr = asr
        self._translator = translator
        self._sequence = 0
        self._last_words: tuple[Word, ...] = ()
        self._audio = AudioRingBuffer(sample_rate * context_seconds)
        self._scheduler = LatestWindowScheduler()
        self._language = LanguageSmoother(2, 0.60)
        self._stabilizer = HypothesisStabilizer(2, 0.8)
        self._store = CaptionStore(session_id, target)

    def submit_audio(
        self, samples: np.ndarray, audio_end: float
    ) -> CaptionSnapshot:
        self._audio.append(samples)
        self._sequence += 1
        request = InferenceRequest(
            self._session_id,
            self._sequence,
            self._audio.latest(self._audio.size),
            audio_end,
        )
        active = self._scheduler.submit(request)
        if active is None:
            return self.snapshot()

        snapshot = self._process(active)
        pending = self._scheduler.complete(active.session_id, active.sequence)
        while pending is not None:
            snapshot = self._process(pending)
            pending = self._scheduler.complete(pending.session_id, pending.sequence)
        return snapshot

    def _process(self, request: InferenceRequest) -> CaptionSnapshot:
        hypothesis = self._asr.transcribe(request)
        if (hypothesis.session_id, hypothesis.sequence) != (
            request.session_id,
            request.sequence,
        ):
            return self._store.snapshot()
        self._last_words = hypothesis.words
        language = (
            self._language.observe(
                hypothesis.language,
                hypothesis.language_confidence,
                'active',
            )
            or hypothesis.language
        )
        stable = self._stabilizer.update(hypothesis.words, hypothesis.audio_end)
        self._store.apply_source(
            hypothesis.sequence,
            language,
            stable.committed,
            stable.provisional,
        )
        translation = self._store.translation_request()
        if translation is not None:
            self._store.apply_translation(self._translator.translate(translation))
        return self._store.snapshot()

    def finalize(self) -> CaptionSnapshot:
        stable = self._stabilizer.finalize(self._last_words)
        language = self._language.current or self._store.language or 'und'
        self._store.apply_source(
            self._sequence,
            language,
            stable.committed,
            stable.provisional,
        )
        translation = self._store.translation_request()
        if translation is not None:
            self._store.apply_translation(self._translator.translate(translation))
        return self._store.snapshot()

    def snapshot(self) -> CaptionSnapshot:
        return self._store.snapshot()
