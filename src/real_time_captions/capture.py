import logging
from typing import cast

import numpy as np
import soundcard as sc

logger = logging.getLogger(__name__)


class AudioStreamer:
    def __init__(self, sample_rate: int = 16000, use_microphone: bool = False) -> None:
        self.sample_rate = sample_rate
        self.use_microphone = use_microphone

    def _get_audio_input_device(self):
        if self.use_microphone:
            device = sc.default_microphone()
            logger.info("Using microphone for audio capture.")
        else:
            # Use default speaker's loopback for system audio capture
            device = sc.get_microphone(
                id=sc.default_speaker().name, include_loopback=True
            )
            logger.info("Using loopback device for audio capture.")

        return device

    def stream_audio(self, block_size: int = 4000):
        try:
            device = self._get_audio_input_device()
        except Exception as e:
            logger.error(f"Error finding audio device: {e}")
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
