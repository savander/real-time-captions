from real_time_captions.streaming.language import LanguageSmoother


def test_initial_language_requires_configured_confirmations() -> None:
    smoother = LanguageSmoother(confirmations=2, minimum_confidence=0.60)

    assert smoother.observe('cs', 0.91, 'u1') is None
    assert smoother.observe('cs', 0.92, 'u1') == 'cs'
    assert smoother.current == 'cs'


def test_new_utterance_requires_fresh_confirmations_before_publication() -> None:
    smoother = LanguageSmoother(confirmations=2, minimum_confidence=0.60)
    smoother.observe('cs', 0.91, 'u1')
    smoother.observe('cs', 0.92, 'u1')

    assert smoother.observe('pl', 0.95, 'u2') is None
    assert smoother.current == 'cs'
    assert smoother.observe('pl', 0.96, 'u2') == 'pl'


def test_low_confidence_observation_does_not_add_candidate_evidence() -> None:
    smoother = LanguageSmoother(confirmations=2, minimum_confidence=0.60)

    assert smoother.observe('cs', 0.59, 'u1') is None
    assert smoother.observe('cs', 0.91, 'u1') is None
    assert smoother.observe('cs', 0.92, 'u1') == 'cs'


def test_conflicting_observation_restarts_candidate_count() -> None:
    smoother = LanguageSmoother(confirmations=3, minimum_confidence=0.60)

    assert smoother.observe('cs', 0.91, 'u1') is None
    assert smoother.observe('pl', 0.92, 'u1') is None
    assert smoother.observe('cs', 0.93, 'u1') is None
    assert smoother.observe('cs', 0.94, 'u1') is None
    assert smoother.observe('cs', 0.95, 'u1') == 'cs'


def test_confirmed_utterance_retains_language_during_conflicting_fragment() -> None:
    smoother = LanguageSmoother(confirmations=2, minimum_confidence=0.60)
    smoother.observe('cs', 0.91, 'u1')
    smoother.observe('cs', 0.92, 'u1')

    assert smoother.observe('pl', 0.95, 'u1') == 'cs'
    assert smoother.observe('pl', 0.96, 'u1') == 'pl'


def test_manual_lock_ignores_automatic_observations() -> None:
    smoother = LanguageSmoother(confirmations=2, minimum_confidence=0.60)
    smoother.lock('cs')

    assert smoother.observe('en', 1.0, 'u1') == 'cs'
    assert smoother.current == 'cs'


def test_unlock_allows_automatic_observations_again() -> None:
    smoother = LanguageSmoother(confirmations=1, minimum_confidence=0.60)
    smoother.lock('cs')
    smoother.unlock()

    assert smoother.observe('en', 1.0, 'u1') == 'en'


def test_current_is_none_until_a_language_is_confirmed() -> None:
    smoother = LanguageSmoother(confirmations=2, minimum_confidence=0.60)

    assert smoother.current is None
    assert smoother.observe('en', 0.60, 'u1') is None
    assert smoother.current is None
