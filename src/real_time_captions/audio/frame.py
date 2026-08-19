from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class AudioFrame:
    session_id: str
    samples: np.ndarray
    sample_rate: int
    channels: int
    sequence: int
    # Session-relative seconds from the start of the current capture session.
    captured_at: float

    def __post_init__(self) -> None:
        owned = np.array(self.samples, copy=True)
        owned.setflags(write=False)
        object.__setattr__(self, 'samples', owned)
