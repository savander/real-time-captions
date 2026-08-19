import pytest

from real_time_captions.captions.store import CaptionStore
from real_time_captions.contracts import TargetLanguage, Word


@pytest.mark.parametrize(
    ("target", "language", "expected_target"),
    [
        (TargetLanguage.ENGLISH, "cs", TargetLanguage.ENGLISH),
        (TargetLanguage.POLISH, "en", TargetLanguage.POLISH),
    ],
)
def test_translation_request_carries_the_exact_source_revision(
    target: TargetLanguage, language: str, expected_target: TargetLanguage
) -> None:
    store = CaptionStore(session_id="session-9", target=target)
    store.apply_source(
        12,
        language,
        (Word("one", 0.0, 0.2), Word("two", 0.2, 0.4)),
        (Word("three", 0.4, 0.6), Word("four", 0.6, 0.8)),
    )

    request = store.translation_request()

    assert request is not None
    assert request.session_id == "session-9"
    assert request.sequence == 12
    assert request.source_language == language
    assert request.target is expected_target
    assert request.committed == "one two"
    assert request.provisional == "three four"


def test_source_text_joins_committed_words_and_replaces_provisional_words() -> None:
    store = CaptionStore(session_id="s1", target=TargetLanguage.ENGLISH)
    store.apply_source(
        1,
        "cs",
        (Word("Dobré", 0.0, 0.3), Word("ráno", 0.3, 0.6)),
        (Word("světe", 0.6, 0.9),),
    )
    store.apply_source(
        2,
        "cs",
        (
            Word("Dobré", 0.0, 0.3),
            Word("ráno", 0.3, 0.6),
            Word("světe", 0.6, 0.9),
        ),
        (Word("dnes", 0.9, 1.2),),
    )

    snapshot = store.snapshot()
    assert snapshot.source_committed == "Dobré ráno světe"
    assert snapshot.source_provisional == "dnes"
