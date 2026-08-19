from real_time_captions.captions.translation import (
    TranslationRequest,
    TranslationResult,
)
from real_time_captions.contracts import CaptionSnapshot, TargetLanguage, Word


def _text(words: tuple[str, ...]) -> str:
    return ' '.join(words).strip()


def _append_text(existing: str, addition: str) -> str:
    return ' '.join(part for part in (existing, addition.strip()) if part)


class CaptionStore:
    def __init__(self, session_id: str, target: TargetLanguage) -> None:
        self.session_id = session_id
        self.target = target
        self.sequence = -1
        self.language: str | None = None
        self.source_committed = ''
        self.source_provisional = ''
        self.translation_committed = ''
        self.translation_provisional = ''
        self._committed_words: tuple[str, ...] = ()
        self._pending_committed_words: tuple[str, ...] = ()
        self._pending_segment_id: int | None = None
        self._pending_source_language: str | None = None
        self._next_segment_id = 1

    def apply_source(
        self,
        sequence: int,
        language: str | None,
        committed: tuple[Word, ...],
        provisional: tuple[Word, ...],
    ) -> bool:
        if sequence <= self.sequence:
            return False

        committed_words = tuple(word.text for word in committed)
        if committed_words[: len(self._committed_words)] != self._committed_words:
            return False

        source_committed = _text(committed_words)
        source_provisional = _text(tuple(word.text for word in provisional))
        if (
            language,
            source_committed,
            source_provisional,
        ) == (
            self.language,
            self.source_committed,
            self.source_provisional,
        ):
            return False

        committed_delta = committed_words[len(self._committed_words) :]
        self.sequence = sequence
        self.language = language
        self._committed_words = committed_words
        self.source_committed = source_committed
        self.source_provisional = source_provisional
        self.translation_provisional = ''

        if committed_delta:
            if self._pending_segment_id is None:
                self._pending_segment_id = self._next_segment_id
                self._next_segment_id += 1
                self._pending_source_language = language
            self._pending_committed_words += committed_delta
        if (
            self._pending_segment_id is not None
            and self._pending_source_language is None
            and language is not None
        ):
            self._pending_source_language = language
        return True

    def translation_request(self) -> TranslationRequest | None:
        if self.target is TargetLanguage.NATIVE:
            return None

        committed = _text(self._pending_committed_words)
        segment_id = self._pending_segment_id
        if committed:
            source_language = self._pending_source_language
            provisional = (
                self.source_provisional
                if self.language == source_language
                else ''
            )
        else:
            source_language = self.language
            provisional = self.source_provisional

        if source_language is None or not (committed or provisional):
            return None
        return TranslationRequest(
            session_id=self.session_id,
            sequence=self.sequence,
            source_language=source_language,
            target=self.target,
            committed=committed,
            provisional=provisional,
            committed_segment_id=segment_id,
        )

    def apply_translation(self, result: TranslationResult) -> bool:
        if self.target is TargetLanguage.NATIVE or self.sequence < 0:
            return False
        if (result.session_id, result.sequence) != (
            self.session_id,
            self.sequence,
        ):
            return False
        if result.committed_segment_id != self._pending_segment_id:
            return False
        if self._pending_segment_id is None and result.committed:
            return False
        if self._pending_segment_id is not None and not result.committed:
            return False
        if not self.source_provisional and result.provisional:
            return False

        if self._pending_segment_id is not None:
            self.translation_committed = _append_text(
                self.translation_committed, result.committed
            )
            self._pending_committed_words = ()
            self._pending_segment_id = None
            self._pending_source_language = None
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
