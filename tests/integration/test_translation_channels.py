import numpy as np

from real_time_captions.contracts import TargetLanguage, Word
from real_time_captions.core import RealtimeCaptionCore
from tests.fakes import FakeAsrBackend, FakeTranslationBackend


def test_mixed_revision_translates_committed_and_provisional_channels() -> None:
    words = (
        Word('Dobr\u00fd', 0.0, 0.4),
        Word('den', 0.4, 0.8),
        Word('sv\u011bte', 0.8, 1.6),
    )
    core = RealtimeCaptionCore(
        session_id='mixed-translation',
        asr=FakeAsrBackend(hypotheses=[('cs', words), ('cs', words)]),
        translator=FakeTranslationBackend(
            {
                'Dobr\u00fd den sv\u011bte': 'Dzie\u0144 dobry \u015bwiecie',
                'Dobr\u00fd den': 'Dzie\u0144 dobry',
                'sv\u011bte': '\u015bwiecie',
            }
        ),
        target=TargetLanguage.POLISH,
        sample_rate=10,
        context_seconds=2,
    )

    core.submit_audio(np.ones(5, dtype=np.float32), audio_end=1.0)
    mixed = core.submit_audio(np.ones(5, dtype=np.float32), audio_end=2.0)

    assert mixed.source_committed == 'Dobr\u00fd den'
    assert mixed.source_provisional == 'sv\u011bte'
    assert mixed.translation_committed == 'Dzie\u0144 dobry'
    assert mixed.translation_provisional == '\u015bwiecie'
