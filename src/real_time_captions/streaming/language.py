class LanguageSmoother:
    def __init__(self, confirmations: int, minimum_confidence: float) -> None:
        self.confirmations = confirmations
        self.minimum_confidence = minimum_confidence
        self.current: str | None = None
        self._candidate: str | None = None
        self._count = 0
        self._utterance: str | None = None
        self._locked: str | None = None

    def observe(self, language: str, confidence: float, utterance_id: str) -> str | None:
        if self._locked is not None:
            return self._locked
        if utterance_id != self._utterance:
            self._utterance = utterance_id
            self._candidate = None
            self._count = 0
        if confidence < self.minimum_confidence:
            return self.current
        if language != self._candidate:
            self._candidate, self._count = language, 1
        else:
            self._count += 1
        if self._count >= self.confirmations:
            self.current = language
        return self.current

    def lock(self, language: str) -> None:
        self._locked = language
        self.current = language

    def unlock(self) -> None:
        self._locked = None
