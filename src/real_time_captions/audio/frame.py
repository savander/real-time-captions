from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class AudioFrame:
    session_id: str
    samples: np.ndarray
    sample_rate: int
    channels: int
    sequence: int
    captured_at: float
