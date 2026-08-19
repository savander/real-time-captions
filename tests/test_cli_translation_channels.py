from real_time_captions.captions.translation import TranslationRequest
from real_time_captions.cli import _SmokeTranslationBackend
from real_time_captions.contracts import TargetLanguage


def test_smoke_translator_keeps_committed_and_provisional_channels_separate() -> None:
    result = _SmokeTranslationBackend().translate(
        TranslationRequest(
            session_id='smoke',
            sequence=4,
            source_language='cs',
            target=TargetLanguage.POLISH,
            committed='Dobr\u00fd den',
            provisional='sv\u011bte',
        )
    )

    assert result.committed == 'Dzie\u0144 dobry'
    assert result.provisional == '\u015bwiecie'
