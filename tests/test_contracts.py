from dataclasses import FrozenInstanceError

import pytest

from real_time_captions.contracts import AsrHypothesis, Word


def test_asr_hypothesis_is_immutable_and_keeps_sequence_identity() -> None:
    word = Word(text="Ahoj", start=0.0, end=0.4)
    hypothesis = AsrHypothesis(
        session_id="session-1",
        sequence=7,
        words=(word,),
        language="cs",
        language_confidence=0.92,
        audio_end=0.5,
    )

    assert hypothesis.words == (word,)
    with pytest.raises(FrozenInstanceError):
        hypothesis.sequence = 8  # type: ignore[misc]
