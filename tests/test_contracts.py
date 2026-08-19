from dataclasses import FrozenInstanceError

import numpy as np
import pytest

from real_time_captions.contracts import AsrHypothesis, InferenceRequest, Word


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


def test_inference_request_owns_a_read_only_sample_snapshot() -> None:
    source = np.array([0.25, 0.5], dtype=np.float32)

    request = InferenceRequest('session-1', 3, source, 1.5)
    source[0] = 9.0

    np.testing.assert_array_equal(
        request.samples, np.array([0.25, 0.5], dtype=np.float32)
    )
    with pytest.raises(ValueError, match='read-only'):
        request.samples[0] = 1.0
