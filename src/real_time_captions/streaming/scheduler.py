from real_time_captions.contracts import InferenceRequest


class LatestWindowScheduler:
    def __init__(self) -> None:
        self._active: InferenceRequest | None = None
        self._pending: InferenceRequest | None = None
        self.coalesced_count = 0

    @property
    def in_flight(self) -> bool:
        return self._active is not None

    def submit(self, request: InferenceRequest) -> InferenceRequest | None:
        if self._active is None:
            self._active = request
            return request
        if self._pending is not None:
            self.coalesced_count += 1
        self._pending = request
        return None

    def complete(self, session_id: str, sequence: int) -> InferenceRequest | None:
        if self._active is None or (
            self._active.session_id,
            self._active.sequence,
        ) != (session_id, sequence):
            raise ValueError("completion does not match active request")

        promoted = self._pending
        self._active = promoted
        self._pending = None
        return promoted

    def reset(self) -> None:
        self._active = None
        self._pending = None
