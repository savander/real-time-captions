import unicodedata

from real_time_captions.contracts import StabilizedText, Word


def _key(word: Word) -> str:
    return unicodedata.normalize("NFKC", word.text).casefold().strip(".,!?;:")


def _matches(left: Word, right: Word) -> bool:
    overlaps = min(left.end, right.end) >= max(left.start, right.start)
    return overlaps and _key(left) == _key(right)


def _is_committed_duplicate(left: Word, right: Word) -> bool:
    overlaps = min(left.end, right.end) > max(left.start, right.start)
    return overlaps and _key(left) == _key(right)


class HypothesisStabilizer:
    def __init__(self, required_agreements: int, guard_seconds: float) -> None:
        self.required_agreements = required_agreements
        self.guard_seconds = guard_seconds
        self._committed: tuple[Word, ...] = ()
        self._previous: tuple[Word, ...] = ()
        self._counts: tuple[int, ...] = ()
        self._last_committed_end = -1.0

    def update(self, words: tuple[Word, ...], audio_end: float) -> StabilizedText:
        current = self._uncommitted(words)
        common = 0
        for previous, candidate in zip(self._previous, current, strict=False):
            if not _matches(previous, candidate):
                break
            common += 1

        counts = tuple(
            self._counts[index] + 1 if index < common else 1
            for index in range(len(current))
        )
        cutoff = audio_end - self.guard_seconds
        commit_count = 0
        for word, count in zip(current, counts, strict=False):
            if count < self.required_agreements or word.end > cutoff:
                break
            commit_count += 1

        self._append(current[:commit_count])
        self._previous = current[commit_count:]
        self._counts = counts[commit_count:]
        return StabilizedText(self._committed, self._previous)

    def finalize(self, words: tuple[Word, ...]) -> StabilizedText:
        self._append(self._uncommitted(words))
        self._previous = ()
        self._counts = ()
        return StabilizedText(self._committed, ())

    def reset(self) -> None:
        self._committed = ()
        self._previous = ()
        self._counts = ()
        self._last_committed_end = -1.0

    def _append(self, words: tuple[Word, ...]) -> None:
        if words:
            self._committed += words
            self._last_committed_end = self._committed[-1].end

    def _uncommitted(self, words: tuple[Word, ...]) -> tuple[Word, ...]:
        committed_prefix = 0
        for start in range(len(self._committed)):
            length = 0
            for committed, candidate in zip(self._committed[start:], words, strict=False):
                if not _is_committed_duplicate(committed, candidate):
                    break
                length += 1
            committed_prefix = max(committed_prefix, length)
        return tuple(
            word
            for word in words[committed_prefix:]
            if word.end > self._last_committed_end
        )
