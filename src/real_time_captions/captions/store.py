from real_time_captions.captions.translation import TranslationRequest, TranslationResult
from real_time_captions.contracts import CaptionSnapshot, TargetLanguage, Word


def _text(words: tuple[Word, ...]) -> str:
    return " ".join(word.text for word in words).strip()


class CaptionStore:
    def __init__(self, session_id: str, target: TargetLanguage) -> None:
        self.session_id = session_id
        self.target = target
        self.sequence = -1
        self.language: str | None = None
        self.source_committed = ""
        self.source_provisional = ""
        self.translation_committed = ""
        self.translation_provisional = ""

    def apply_source(
        self,
        sequence: int,
        language: str,
        committed: tuple[Word, ...],
        provisional: tuple[Word, ...],
    ) -> None:
        if sequence < self.sequence:
            return
        if sequence != self.sequence:
            self.translation_committed = ""
            self.translation_provisional = ""
        self.sequence = sequence
        self.language = language
        self.source_committed = _text(committed)
        self.source_provisional = _text(provisional)

    def translation_request(self) -> TranslationRequest | None:
        if self.target is TargetLanguage.NATIVE or self.language is None:
            return None
        return TranslationRequest(
            self.session_id,
            self.sequence,
            self.language,
            self.target,
            self.source_committed,
            self.source_provisional,
        )

    def apply_translation(self, result: TranslationResult) -> bool:
        if self.language is None or self.target is TargetLanguage.NATIVE:
            return False
        if (result.session_id, result.sequence) != (self.session_id, self.sequence):
            return False
        self.translation_committed = result.committed
        self.translation_provisional = result.provisional
        return True

    def snapshot(self) -> CaptionSnapshot:
        return CaptionSnapshot(
            self.session_id,
            self.sequence,
            self.language,
            self.source_committed,
            self.source_provisional,
            self.translation_committed,
            self.translation_provisional,
        )
