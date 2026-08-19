import numpy as np

from real_time_captions.audio.ring_buffer import AudioRingBuffer
from real_time_captions.backends.protocols import AsrBackend
from real_time_captions.captions.store import CaptionStore
from real_time_captions.captions.translation import TranslationBackend
from real_time_captions.contracts import (
    CaptionSnapshot,
    InferenceRequest,
    StabilizedText,
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
        self._asr_sequence = 0
        self._source_revision = 0
        self._utterance_id = 1
        self._utterance_active = False
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
        self._asr_sequence += 1
        request = InferenceRequest(
            self._session_id,
            self._asr_sequence,
            self._audio.latest(self._audio.size),
            audio_end,
        )
        active = self._scheduler.submit(request)
        if active is None:
            return self.snapshot()

        try:
            snapshot = self._process(active)
            pending = self._scheduler.complete(
                active.session_id, active.sequence
            )
            while pending is not None:
                snapshot = self._process(pending)
                pending = self._scheduler.complete(
                    pending.session_id, pending.sequence
                )
            return snapshot
        except Exception:
            self._scheduler.reset()
            raise

    def _process(self, request: InferenceRequest) -> CaptionSnapshot:
        hypothesis = self._asr.transcribe(request)
        if (hypothesis.session_id, hypothesis.sequence) != (
            request.session_id,
            request.sequence,
        ):
            return self._store.snapshot()

        self._last_words = hypothesis.words
        self._utterance_active = self._utterance_active or bool(hypothesis.words)
        language = (
            self._language.observe(
                hypothesis.language,
                hypothesis.language_confidence,
                str(self._utterance_id),
            )
            if hypothesis.words
            else None
        )
        stable = self._stabilizer.update(
            hypothesis.words, hypothesis.audio_end
        )
        self._apply_source(language, stable)
        self._translate_current()
        return self._store.snapshot()

    def finalize(self) -> CaptionSnapshot:
        if not self._utterance_active:
            self._translate_current()
            return self._store.snapshot()

        stable = self._stabilizer.finalize(self._last_words)
        self._apply_source(self._store.language, stable)
        self._last_words = ()
        self._utterance_active = False
        self._utterance_id += 1
        self._translate_current()
        return self._store.snapshot()

    def snapshot(self) -> CaptionSnapshot:
        return self._store.snapshot()

    def _apply_source(
        self, language: str | None, stable: StabilizedText
    ) -> None:
        revision = self._source_revision + 1
        if self._store.apply_source(
            revision,
            language,
            stable.committed,
            stable.provisional,
        ):
            self._source_revision = revision

    def _translate_current(self) -> None:
        request = self._store.translation_request()
        if request is not None:
            result = self._translator.translate(request)
            self._store.apply_translation(result)
