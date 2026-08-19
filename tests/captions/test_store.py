from dataclasses import FrozenInstanceError

import pytest

from real_time_captions.captions.store import CaptionStore
from real_time_captions.captions.translation import TranslationResult
from real_time_captions.contracts import TargetLanguage, Word


def test_newer_source_clears_translation_from_an_older_revision() -> None:
    store = CaptionStore(session_id="s1", target=TargetLanguage.POLISH)
    store.apply_source(1, "cs", (Word("Ahoj", 0.0, 0.4),), ())
    store.apply_translation(TranslationResult("s1", 1, "Cześć", ""))

    store.apply_source(2, "cs", (Word("světe", 0.4, 0.8),), ())

    assert store.snapshot().source_committed == "světe"
    assert store.snapshot().translation_committed == ""
    assert store.snapshot().translation_provisional == ""


def test_same_source_sequence_updates_text_without_clearing_translation() -> None:
    store = CaptionStore(session_id="s1", target=TargetLanguage.ENGLISH)
    store.apply_source(3, "cs", (Word("Ahoj", 0.0, 0.4),), ())
    store.apply_translation(TranslationResult("s1", 3, "Hello", ""))

    store.apply_source(3, "cs", (Word("Ahoj", 0.0, 0.4),), (Word("světe", 0.4, 0.8),))

    snapshot = store.snapshot()
    assert snapshot.source_provisional == "světe"
    assert snapshot.translation_committed == "Hello"


def test_stale_source_cannot_regress_the_latest_revision() -> None:
    store = CaptionStore(session_id="s1", target=TargetLanguage.POLISH)
    store.apply_source(5, "cs", (Word("nové", 0.0, 0.4),), ())

    store.apply_source(4, "cs", (Word("staré", 0.0, 0.4),), ())

    snapshot = store.snapshot()
    assert snapshot.sequence == 5
    assert snapshot.source_committed == "nové"


def test_stale_translation_cannot_replace_newer_revision() -> None:
    store = CaptionStore(session_id="s1", target=TargetLanguage.POLISH)
    store.apply_source(2, "cs", (Word("Ahoj", 0.0, 0.4),), ())

    accepted = store.apply_translation(
        TranslationResult("s1", 1, committed="Cześć", provisional="")
    )

    assert accepted is False
    assert store.snapshot().translation_committed == ""


def test_translation_for_a_different_session_is_rejected() -> None:
    store = CaptionStore(session_id="s1", target=TargetLanguage.POLISH)
    store.apply_source(1, "cs", (), (Word("Ahoj", 0.0, 0.4),))

    accepted = store.apply_translation(TranslationResult("other", 1, "", "Hello"))

    assert accepted is False
    assert store.snapshot().translation_provisional == ""


def test_translation_for_a_different_sequence_is_rejected() -> None:
    store = CaptionStore(session_id="s1", target=TargetLanguage.POLISH)
    store.apply_source(1, "cs", (), (Word("Ahoj", 0.0, 0.4),))

    accepted = store.apply_translation(TranslationResult("s1", 2, "", "Cześć"))

    assert accepted is False
    assert store.snapshot().translation_provisional == ""


def test_translation_before_any_source_is_rejected_without_mutation() -> None:
    store = CaptionStore(session_id="s1", target=TargetLanguage.ENGLISH)

    accepted = store.apply_translation(TranslationResult("s1", -1, "Hello", "there"))

    snapshot = store.snapshot()
    assert accepted is False
    assert snapshot.translation_committed == ""
    assert snapshot.translation_provisional == ""


def test_native_target_never_requests_translation() -> None:
    store = CaptionStore(session_id="s1", target=TargetLanguage.NATIVE)
    store.apply_source(1, "cs", (), (Word("Ahoj", 0.0, 0.4),))

    assert store.translation_request() is None


def test_native_target_rejects_matching_translation_without_mutation() -> None:
    store = CaptionStore(session_id="s1", target=TargetLanguage.NATIVE)
    store.apply_source(1, "cs", (Word("Ahoj", 0.0, 0.4),), ())

    accepted = store.apply_translation(TranslationResult("s1", 1, "Hello", ""))

    snapshot = store.snapshot()
    assert accepted is False
    assert snapshot.translation_committed == ""
    assert snapshot.translation_provisional == ""


def test_snapshot_is_an_immutable_coherent_record_of_one_revision() -> None:
    store = CaptionStore(session_id="s1", target=TargetLanguage.ENGLISH)
    store.apply_source(7, "cs", (Word("Dobré", 0.0, 0.4),), (Word("ráno", 0.4, 0.8),))
    store.apply_translation(TranslationResult("s1", 7, "Good", "morning"))

    snapshot = store.snapshot()
    store.apply_source(8, "cs", (Word("Ahoj", 0.8, 1.2),), ())

    assert snapshot.sequence == 7
    assert snapshot.source_committed == "Dobré"
    assert snapshot.source_provisional == "ráno"
    assert snapshot.translation_committed == "Good"
    assert snapshot.translation_provisional == "morning"
    with pytest.raises(FrozenInstanceError):
        snapshot.sequence = 8  # type: ignore[misc]
