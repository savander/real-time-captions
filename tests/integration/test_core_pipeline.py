import numpy as np

from real_time_captions.contracts import TargetLanguage, Word
from real_time_captions.core import RealtimeCaptionCore
from tests.fakes import FakeAsrBackend, FakeTranslationBackend


def test_core_emits_provisional_then_committed_bilingual_caption() -> None:
    asr = FakeAsrBackend(
        hypotheses=[
            ("cs", (Word("Dobrý", 0.0, 0.4), Word("den", 0.4, 0.8))),
            ("cs", (Word("Dobrý", 0.0, 0.4), Word("den", 0.4, 0.8))),
        ]
    )
    translator = FakeTranslationBackend({"Dobrý den": "Dzień dobry"})
    core = RealtimeCaptionCore(
        session_id="s1",
        asr=asr,
        translator=translator,
        target=TargetLanguage.POLISH,
        sample_rate=16_000,
        context_seconds=5,
    )

    first = core.submit_audio(
        np.ones(16_000, dtype=np.float32), audio_end=1.0
    )
    second = core.submit_audio(
        np.ones(16_000, dtype=np.float32), audio_end=2.0
    )

    assert first.source_provisional == "Dobrý den"
    assert second.source_committed == "Dobrý den"
    assert second.translation_committed == "Dzień dobry"
