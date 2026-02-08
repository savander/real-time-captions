import logging
from typing import cast

import numpy as np
import soundcard as sc

logger = logging.getLogger(__name__)


class AudioStreamer:
    def __init__(self, sample_rate: int = 16000) -> None:
        self.sample_rate = sample_rate

    def _get_loopback_device(self):
        return sc.get_microphone(id=sc.default_speaker().name, include_loopback=True)

    def stream_audio(self, block_size: int = 4000):
        try:
            device = self._get_loopback_device()
        except Exception as e:
            logger.error(f"Error finding loopback device: {e}")
            return

        logger.info("Capturing audio from device: %s", device.name)

        try:
            with device.recorder(samplerate=self.sample_rate) as recorder:
                while True:
                    raw_data = recorder.record(numframes=block_size)
                    data = cast(np.ndarray, raw_data)

                    if data.ndim > 1:
                        data = np.mean(data, axis=1)

                    yield data.astype(np.float32)
        except Exception as e:
            logger.error(f"Error capturing audio: {e}")
        finally:
            logger.info("Audio stream stopped.")
