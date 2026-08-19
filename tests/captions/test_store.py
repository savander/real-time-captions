from dataclasses import FrozenInstanceError

import pytest

from real_time_captions.captions.store import CaptionStore
from real_time_captions.captions.translation import TranslationResult
from real_time_captions.contracts import TargetLanguage, Word


def test_newer_source_preserves_committed_translation_and_clears_provisional() -> None:
    store = CaptionStore('s1', TargetLanguage.POLISH)
    store.apply_source(
        1,
        'cs',
        (Word('Ahoj', 0.0, 0.4),),
        (Word('sv\u011bte', 0.4, 0.8),),
    )
    request = store.translation_request()
    assert request is not None
    assert store.apply_translation(
        TranslationResult(
            's1',
            1,
            'Cze\u015b\u0107',
            'czy \u015bwiecie',
            request.committed_segment_id,
        )
    )

    store.apply_source(
        2,
        'cs',
        (Word('Ahoj', 0.0, 0.4), Word('sv\u011bte', 0.4, 0.8)),
        (),
    )

    snapshot = store.snapshot()
    assert snapshot.source_committed == 'Ahoj sv\u011bte'
    assert snapshot.translation_committed == 'Cze\u015b\u0107'
    assert snapshot.translation_provisional == ''


def test_same_source_revision_cannot_update_text() -> None:
    store = CaptionStore('s1', TargetLanguage.ENGLISH)
    store.apply_source(3, 'cs', (Word('Ahoj', 0.0, 0.4),), ())

    accepted = store.apply_source(
        3,
        'cs',
        (Word('Ahoj', 0.0, 0.4),),
        (Word('sv\u011bte', 0.4, 0.8),),
    )

    assert accepted is False
    assert store.snapshot().source_provisional == ''


def test_stale_source_cannot_regress_the_latest_revision() -> None:
    store = CaptionStore('s1', TargetLanguage.POLISH)
    store.apply_source(5, 'cs', (Word('nov\u00e9', 0.0, 0.4),), ())

    accepted = store.apply_source(
        4, 'cs', (Word('star\u00e9', 0.0, 0.4),), ()
    )

    snapshot = store.snapshot()
    assert accepted is False
    assert snapshot.sequence == 5
    assert snapshot.source_committed == 'nov\u00e9'


def test_stale_translation_cannot_replace_newer_revision() -> None:
    store = CaptionStore('s1', TargetLanguage.POLISH)
    store.apply_source(2, 'cs', (Word('Ahoj', 0.0, 0.4),), ())
    request = store.translation_request()
    assert request is not None

    accepted = store.apply_translation(
        TranslationResult(
            's1',
            1,
            'Cze\u015b\u0107',
            '',
            request.committed_segment_id,
        )
    )

    assert accepted is False
    assert store.snapshot().translation_committed == ''


def test_translation_for_a_different_session_is_rejected() -> None:
    store = CaptionStore('s1', TargetLanguage.POLISH)
    store.apply_source(1, 'cs', (), (Word('Ahoj', 0.0, 0.4),))

    accepted = store.apply_translation(
        TranslationResult('other', 1, '', 'Cze\u015b\u0107', None)
    )

    assert accepted is False
    assert store.snapshot().translation_provisional == ''


def test_translation_for_a_different_sequence_is_rejected() -> None:
    store = CaptionStore('s1', TargetLanguage.POLISH)
    store.apply_source(1, 'cs', (), (Word('Ahoj', 0.0, 0.4),))

    accepted = store.apply_translation(
        TranslationResult('s1', 2, '', 'Cze\u015b\u0107', None)
    )

    assert accepted is False
    assert store.snapshot().translation_provisional == ''


def test_translation_before_any_source_is_rejected_without_mutation() -> None:
    store = CaptionStore('s1', TargetLanguage.ENGLISH)

    accepted = store.apply_translation(
        TranslationResult('s1', -1, 'Hello', 'there', None)
    )

    snapshot = store.snapshot()
    assert accepted is False
    assert snapshot.translation_committed == ''
    assert snapshot.translation_provisional == ''


def test_native_target_never_requests_or_accepts_translation() -> None:
    store = CaptionStore('s1', TargetLanguage.NATIVE)
    store.apply_source(1, 'cs', (Word('Ahoj', 0.0, 0.4),), ())

    assert store.translation_request() is None
    assert store.apply_translation(
        TranslationResult('s1', 1, 'Hello', '', 1)
    ) is False
    assert store.snapshot().translation_committed == ''


def test_snapshot_is_an_immutable_coherent_record_of_one_revision() -> None:
    store = CaptionStore('s1', TargetLanguage.ENGLISH)
    committed = (Word('Dobr\u00e9', 0.0, 0.4),)
    store.apply_source(7, 'cs', committed, (Word('r\u00e1no', 0.4, 0.8),))
    request = store.translation_request()
    assert request is not None
    store.apply_translation(
        TranslationResult('s1', 7, 'Good', 'morning', request.committed_segment_id)
    )

    snapshot = store.snapshot()
    store.apply_source(
        8,
        'cs',
        committed + (Word('r\u00e1no', 0.4, 0.8),),
        (Word('Ahoj', 0.8, 1.2),),
    )

    assert snapshot.sequence == 7
    assert snapshot.source_committed == 'Dobr\u00e9'
    assert snapshot.source_provisional == 'r\u00e1no'
    assert snapshot.translation_committed == 'Good'
    assert snapshot.translation_provisional == 'morning'
    with pytest.raises(FrozenInstanceError):
        snapshot.sequence = 8  # type: ignore[misc]
