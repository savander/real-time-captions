from real_time_captions.captions.store import CaptionStore
from real_time_captions.captions.translation import (
    TranslationRequest,
    TranslationResult,
)
from real_time_captions.contracts import TargetLanguage, Word


def words(*texts: str) -> tuple[Word, ...]:
    return tuple(
        Word(text, index * 0.25, (index + 1) * 0.25)
        for index, text in enumerate(texts)
    )


def result_for(
    request: TranslationRequest,
    *,
    committed: str = '',
    provisional: str = '',
    committed_segment_id: int | None = None,
) -> TranslationResult:
    return TranslationResult(
        session_id=request.session_id,
        sequence=request.sequence,
        committed=committed,
        provisional=provisional,
        committed_segment_id=(
            request.committed_segment_id
            if committed_segment_id is None
            else committed_segment_id
        ),
    )


def test_source_updates_require_a_new_revision_and_preserve_committed_prefix() -> None:
    store = CaptionStore('s1', TargetLanguage.POLISH)

    assert store.apply_source(1, 'cs', words('Ahoj'), words('sv\u011bte')) is True
    assert store.apply_source(1, 'cs', words('Ahoj', 'sv\u011bte'), ()) is False
    assert store.apply_source(2, 'cs', words('Nazdar'), ()) is False
    assert store.apply_source(2, 'cs', (), ()) is False

    snapshot = store.snapshot()
    assert snapshot.sequence == 1
    assert snapshot.source_committed == 'Ahoj'
    assert snapshot.source_provisional == 'sv\u011bte'


def test_unchanged_source_does_not_consume_a_new_revision() -> None:
    store = CaptionStore('s1', TargetLanguage.POLISH)
    committed = words('Ahoj')

    assert store.apply_source(1, 'cs', committed, ()) is True
    assert store.apply_source(2, 'cs', committed, ()) is False

    assert store.snapshot().sequence == 1


def test_pending_committed_delta_keeps_one_segment_id_until_exact_success() -> None:
    store = CaptionStore('s1', TargetLanguage.POLISH)
    assert store.apply_source(1, 'cs', words('Dobr\u00fd'), ()) is True
    first = store.translation_request()
    assert first is not None
    assert first.committed == 'Dobr\u00fd'
    assert first.committed_segment_id is not None

    assert store.apply_source(2, 'cs', words('Dobr\u00fd', 'den'), ()) is True
    joined = store.translation_request()
    assert joined is not None
    assert joined.sequence == 2
    assert joined.committed == 'Dobr\u00fd den'
    assert joined.committed_segment_id == first.committed_segment_id

    assert store.apply_translation(
        result_for(first, committed='Dzie\u0144')
    ) is False
    assert store.apply_translation(
        result_for(joined, committed='Dzie\u0144 dobry')
    ) is True
    assert store.snapshot().translation_committed == 'Dzie\u0144 dobry'

    assert store.apply_source(
        3, 'cs', words('Dobr\u00fd', 'den', 'sv\u011bte'), ()
    ) is True
    next_segment = store.translation_request()
    assert next_segment is not None
    assert next_segment.committed == 'sv\u011bte'
    assert next_segment.committed_segment_id != first.committed_segment_id

    assert store.apply_translation(
        result_for(next_segment, committed='\u015bwiecie')
    ) is True
    assert store.snapshot().translation_committed == 'Dzie\u0144 dobry \u015bwiecie'


def test_segment_identity_is_required_even_at_the_current_source_revision() -> None:
    store = CaptionStore('s1', TargetLanguage.POLISH)
    assert store.apply_source(1, 'cs', words('Ahoj'), ()) is True
    request = store.translation_request()
    assert request is not None and request.committed_segment_id is not None

    accepted = store.apply_translation(
        result_for(
            request,
            committed='Cze\u015b\u0107',
            committed_segment_id=request.committed_segment_id + 1,
        )
    )

    assert accepted is False
    assert store.snapshot().translation_committed == ''


def test_new_source_preserves_committed_translation_and_clears_provisional() -> None:
    store = CaptionStore('s1', TargetLanguage.POLISH)
    assert store.apply_source(1, 'cs', words('Dobr\u00fd'), words('den')) is True
    first = store.translation_request()
    assert first is not None
    assert store.apply_translation(
        result_for(first, committed='Dobry', provisional='dzie\u0144')
    ) is True

    assert store.apply_source(2, 'cs', words('Dobr\u00fd', 'den'), ()) is True

    snapshot = store.snapshot()
    assert snapshot.translation_committed == 'Dobry'
    assert snapshot.translation_provisional == ''
    pending = store.translation_request()
    assert pending is not None
    assert pending.committed == 'den'


def test_unconfirmed_source_language_never_creates_a_translation_request() -> None:
    store = CaptionStore('s1', TargetLanguage.POLISH)

    assert store.apply_source(1, None, (), words('Ahoj')) is True

    assert store.snapshot().language is None
    assert store.translation_request() is None
