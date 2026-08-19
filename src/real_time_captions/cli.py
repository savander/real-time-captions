import json
import sys
from collections.abc import Sequence
from dataclasses import asdict

import numpy as np

from real_time_captions.captions.translation import (
    TranslationRequest,
    TranslationResult,
)
from real_time_captions.contracts import (
    AsrHypothesis,
    InferenceRequest,
    TargetLanguage,
    Word,
)
from real_time_captions.core import RealtimeCaptionCore


class _SmokeAsrBackend:
    def transcribe(self, request: InferenceRequest) -> AsrHypothesis:
        return AsrHypothesis(
            request.session_id,
            request.sequence,
            (Word('Dobr\u00fd', 0.0, 0.4), Word('den', 0.4, 0.8)),
            'cs',
            1.0,
            request.audio_end,
        )


class _SmokeTranslationBackend:
    _translations = {
        'Dobr\u00fd den': 'Dzie\u0144 dobry',
        'sv\u011bte': '\u015bwiecie',
    }

    def translate(self, request: TranslationRequest) -> TranslationResult:
        return TranslationResult(
            request.session_id,
            request.sequence,
            committed=(
                self._translations[request.committed]
                if request.committed
                else ''
            ),
            provisional=(
                self._translations[request.provisional]
                if request.provisional
                else ''
            ),
        )


def _core_smoke() -> None:
    core = RealtimeCaptionCore(
        session_id='core-smoke',
        asr=_SmokeAsrBackend(),
        translator=_SmokeTranslationBackend(),
        target=TargetLanguage.POLISH,
        sample_rate=16_000,
        context_seconds=5,
    )
    samples = np.ones(16_000, dtype=np.float32)
    core.submit_audio(samples, audio_end=1.0)
    snapshot = core.submit_audio(samples, audio_end=2.0)
    print(json.dumps(asdict(snapshot), sort_keys=True))


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args == ['core-smoke']:
        _core_smoke()
    return 0
