import wave

import numpy as np


class AudioFileWriter:
    def __init__(self, filename: str, sample_rate: int):
        self.filename = filename
        self.sample_rate = sample_rate
        self._file = wave.open(filename, "wb")
        self._file.setnchannels(1)
        self._file.setsampwidth(2)
        self._file.setframerate(sample_rate)

    def write_chunk(self, chunk: np.ndarray):
        int16_chunk = (chunk * 32767).astype(np.int16)
        self._file.writeframes(int16_chunk.tobytes())

    def close(self):
        self._file.close()
        print(f"Audio saved to {self.filename}")
