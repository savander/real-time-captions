import math

import numpy as np
from scipy.signal import resample_poly

from .frame import AudioFrame


def normalize_frame(frame: AudioFrame, target_rate: int = 16_000) -> np.ndarray:
    rates_and_channels = (frame.sample_rate, frame.channels, target_rate)
    if not all(
        isinstance(value, (int, np.integer))
        and not isinstance(value, bool)
        and value > 0
        for value in rates_and_channels
    ):
        raise ValueError('sample rates and channels must be positive')

    samples = np.asarray(frame.samples)
    if np.issubdtype(samples.dtype, np.integer):
        limit = float(np.iinfo(samples.dtype).max)
        samples = samples.astype(np.float32) / limit
    else:
        samples = samples.astype(np.float32, copy=False)

    samples = samples.reshape(-1, frame.channels).mean(axis=1)
    if frame.sample_rate != target_rate:
        divisor = math.gcd(frame.sample_rate, target_rate)
        samples = resample_poly(
            samples, target_rate // divisor, frame.sample_rate // divisor
        ).astype(np.float32)
    return np.ascontiguousarray(samples)
