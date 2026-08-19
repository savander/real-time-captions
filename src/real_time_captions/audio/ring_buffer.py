import numpy as np


class AudioRingBuffer:
    def __init__(self, capacity_samples: int) -> None:
        if capacity_samples <= 0:
            raise ValueError('capacity_samples must be positive')
        self._data = np.zeros(capacity_samples, dtype=np.float32)
        self._write = 0
        self._size = 0

    @property
    def size(self) -> int:
        return self._size

    def append(self, samples: np.ndarray) -> None:
        values = np.asarray(samples, dtype=np.float32).reshape(-1)
        if len(values) >= len(self._data):
            values = values[-len(self._data) :]
        first = min(len(values), len(self._data) - self._write)
        self._data[self._write : self._write + first] = values[:first]
        rest = len(values) - first
        self._data[:rest] = values[first:]
        self._write = (self._write + len(values)) % len(self._data)
        self._size = min(len(self._data), self._size + len(values))

    def latest(self, count: int) -> np.ndarray:
        count = min(max(count, 0), self._size)
        start = (self._write - count) % len(self._data)
        if start + count <= len(self._data):
            return self._data[start : start + count].copy()
        split = len(self._data) - start
        return np.concatenate((self._data[start:], self._data[: count - split]))
