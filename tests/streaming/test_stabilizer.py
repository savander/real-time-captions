from real_time_captions.contracts import Word
from real_time_captions.streaming.stabilizer import HypothesisStabilizer


def words(*values: tuple[str, float, float]) -> tuple[Word, ...]:
    return tuple(Word(text, start, end) for text, start, end in values)


def test_repeated_old_prefix_commits_and_tail_stays_provisional() -> None:
    stabilizer = HypothesisStabilizer(required_agreements=2, guard_seconds=0.8)
    first = words(("Dobrý", 0.0, 0.4), ("den", 0.4, 0.8), ("dnes", 0.9, 1.2))
    second = words(("Dobrý", 0.0, 0.4), ("den", 0.4, 0.8), ("dneska", 0.9, 1.3))

    assert stabilizer.update(first, audio_end=1.5).committed == ()
    result = stabilizer.update(second, audio_end=1.7)

    assert [word.text for word in result.committed] == ["Dobrý", "den"]
    assert [word.text for word in result.provisional] == ["dneska"]


def test_punctuation_and_case_agreement_preserve_current_display_text() -> None:
    stabilizer = HypothesisStabilizer(required_agreements=2, guard_seconds=0.0)

    stabilizer.update(words(("Dobrý,", 0.0, 0.5)), audio_end=1.0)
    result = stabilizer.update(words(("dobrý", 0.0, 0.5)), audio_end=1.0)

    assert [word.text for word in result.committed] == ["dobrý"]


def test_repeated_words_are_committed_in_their_original_order() -> None:
    stabilizer = HypothesisStabilizer(required_agreements=2, guard_seconds=0.0)
    repeated = words(("ano", 0.0, 0.2), ("ano", 0.2, 0.4), ("ne", 0.4, 0.6))

    stabilizer.update(repeated, audio_end=1.0)
    result = stabilizer.update(repeated, audio_end=1.0)

    assert [word.text for word in result.committed] == ["ano", "ano", "ne"]


def test_adjacent_repeated_tail_survives_update_and_finalization() -> None:
    stabilizer = HypothesisStabilizer(required_agreements=2, guard_seconds=0.1)
    hypothesis = words(('ano', 0.0, 0.2), ('ano', 0.2, 0.4))

    stabilizer.update(hypothesis, audio_end=0.31)
    partial = stabilizer.update(hypothesis, audio_end=0.31)
    retained = stabilizer.update(hypothesis, audio_end=0.31)
    final = stabilizer.finalize(hypothesis)

    assert [word.text for word in partial.committed] == ['ano']
    assert [word.text for word in partial.provisional] == ['ano']
    assert [word.text for word in retained.committed] == ['ano']
    assert [word.text for word in retained.provisional] == ['ano']
    assert [word.text for word in final.committed] == ['ano', 'ano']
    assert final.provisional == ()


def test_repeated_tail_finalize_is_idempotent_after_partial_commit() -> None:
    stabilizer = HypothesisStabilizer(required_agreements=2, guard_seconds=0.1)
    hypothesis = words(('ano', 0.0, 0.2), ('ano', 0.2, 0.4))

    stabilizer.update(hypothesis, audio_end=0.31)
    partial = stabilizer.update(hypothesis, audio_end=0.31)
    first_final = stabilizer.finalize(hypothesis)
    second_final = stabilizer.finalize(hypothesis)

    assert first_final.committed[: len(partial.committed)] == partial.committed
    assert [word.text for word in first_final.committed] == ['ano', 'ano']
    assert second_final.committed == first_final.committed
    assert second_final.provisional == ()


def test_overlapping_timestamp_drift_counts_as_agreement() -> None:
    stabilizer = HypothesisStabilizer(required_agreements=2, guard_seconds=0.0)

    stabilizer.update(words(("světe", 1.0, 1.4)), audio_end=2.0)
    result = stabilizer.update(words(("SVĚTE", 1.05, 1.45)), audio_end=2.0)

    assert [word.text for word in result.committed] == ["SVĚTE"]


def test_guard_time_defers_an_agreed_word_until_audio_has_advanced() -> None:
    stabilizer = HypothesisStabilizer(required_agreements=2, guard_seconds=0.4)
    hypothesis = words(("počkej", 0.2, 0.8))

    stabilizer.update(hypothesis, audio_end=1.0)
    delayed = stabilizer.update(hypothesis, audio_end=1.0)
    committed = stabilizer.update(hypothesis, audio_end=1.3)

    assert delayed.committed == ()
    assert [word.text for word in delayed.provisional] == ["počkej"]
    assert [word.text for word in committed.committed] == ["počkej"]


def test_required_agreement_count_must_be_reached_before_commit() -> None:
    stabilizer = HypothesisStabilizer(required_agreements=3, guard_seconds=0.0)
    hypothesis = words(("potvrdit", 0.0, 0.5))

    assert stabilizer.update(hypothesis, audio_end=1.0).committed == ()
    assert stabilizer.update(hypothesis, audio_end=1.0).committed == ()
    result = stabilizer.update(hypothesis, audio_end=1.0)

    assert [word.text for word in result.committed] == ["potvrdit"]


def test_guard_time_includes_a_word_exactly_at_the_cutoff() -> None:
    stabilizer = HypothesisStabilizer(required_agreements=2, guard_seconds=0.4)
    hypothesis = words(('hranice', 0.2, 0.8))

    stabilizer.update(hypothesis, audio_end=1.2)
    result = stabilizer.update(hypothesis, audio_end=1.2)

    assert [word.text for word in result.committed] == ['hranice']
    assert result.provisional == ()


def test_unicode_curly_quotes_and_ellipsis_are_trimmed_for_agreement() -> None:
    stabilizer = HypothesisStabilizer(required_agreements=2, guard_seconds=0.0)

    stabilizer.update(
        words(
            ('\u201eP\u0159\u00edli\u0161\u2026\u201c', 0.0, 0.5),
            ('\u201e\u017c\u00f3\u0142\u0107\u2026\u201d', 0.5, 1.0),
        ),
        audio_end=2.0,
    )
    result = stabilizer.update(
        words(
            ('p\u0159\u00edli\u0161', 0.0, 0.5),
            ('\u017b\u00d3\u0141\u0106', 0.5, 1.0),
        ),
        audio_end=2.0,
    )

    assert [word.text for word in result.committed] == [
        'p\u0159\u00edli\u0161',
        '\u017b\u00d3\u0141\u0106',
    ]


def test_committed_word_with_tolerable_drift_is_not_recommitted() -> None:
    stabilizer = HypothesisStabilizer(required_agreements=2, guard_seconds=0.0)
    first = words(("už", 0.0, 0.4), ("teď", 0.5, 0.8))

    stabilizer.update(first, audio_end=1.0)
    committed = stabilizer.update(first, audio_end=1.0)
    repeated = stabilizer.update(
        words(("už", 0.0, 0.42), ("teď", 0.5, 0.82), ("pokračuj", 0.9, 1.2)),
        audio_end=1.5,
    )

    assert [word.text for word in committed.committed] == ["už", "teď"]
    assert [word.text for word in repeated.committed] == ["už", "teď"]
    assert [word.text for word in repeated.provisional] == ["pokračuj"]


def test_shortened_hypothesis_does_not_recommit_later_committed_word() -> None:
    stabilizer = HypothesisStabilizer(required_agreements=2, guard_seconds=0.0)
    complete = words(('a', 0.0, 0.2), ('b', 0.3, 0.5))
    shortened = words(('b', 0.3, 0.55))

    stabilizer.update(complete, audio_end=1.0)
    stabilizer.update(complete, audio_end=1.0)
    stabilizer.update(shortened, audio_end=1.0)
    result = stabilizer.update(shortened, audio_end=1.0)

    assert [word.text for word in result.committed] == ['a', 'b']
    assert result.provisional == ()


def test_finalize_appends_remaining_tail_without_recommitting_drifted_words() -> None:
    stabilizer = HypothesisStabilizer(required_agreements=2, guard_seconds=0.0)
    first = words(("hotovo", 0.0, 0.4))

    stabilizer.update(first, audio_end=1.0)
    stabilizer.update(first, audio_end=1.0)
    result = stabilizer.finalize(words(("hotovo", 0.0, 0.42), ("teď", 0.5, 0.8)))

    assert [word.text for word in result.committed] == ["hotovo", "teď"]
    assert result.provisional == ()


def test_reset_discards_committed_and_provisional_state() -> None:
    stabilizer = HypothesisStabilizer(required_agreements=2, guard_seconds=0.0)
    hypothesis = words(("znovu", 0.0, 0.5))

    stabilizer.update(hypothesis, audio_end=1.0)
    stabilizer.update(hypothesis, audio_end=1.0)
    stabilizer.reset()
    result = stabilizer.update(hypothesis, audio_end=1.0)

    assert result.committed == ()
    assert [word.text for word in result.provisional] == ["znovu"]


def test_committed_output_is_append_only_across_updates() -> None:
    stabilizer = HypothesisStabilizer(required_agreements=2, guard_seconds=0.0)
    updates = (
        (words(("a", 0.0, 0.2), ("b", 0.3, 0.5)), 1.0),
        (words(("a", 0.0, 0.2), ("bé", 0.3, 0.5)), 1.0),
        (words(("a", 0.0, 0.2), ("bé", 0.3, 0.5), ("c", 0.6, 0.8)), 1.0),
        (words(("a", 0.0, 0.2), ("bé", 0.3, 0.5), ("c", 0.6, 0.8)), 1.0),
    )
    previous: tuple[Word, ...] = ()

    for hypothesis, audio_end in updates:
        result = stabilizer.update(hypothesis, audio_end)

        assert result.committed[: len(previous)] == previous
        previous = result.committed

    assert [word.text for word in previous] == ["a", "bé", "c"]
