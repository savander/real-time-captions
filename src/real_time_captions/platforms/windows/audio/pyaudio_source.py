from collections.abc import Callable
from time import monotonic
from typing import Any

import numpy as np

from real_time_captions.audio.capture import AudioCaptureConfig, AudioSourceDescriptor, AudioSourceKind, AudioSourceNotFound, AudioSourceOpenError
from real_time_captions.contracts import SourceState
from real_time_captions.platforms.windows.audio.pyaudio_api import PyAudioApi, WasapiDevice
from real_time_captions.platforms.windows.audio.source_base import ManagedSourceBase


class WasapiAudioSource(ManagedSourceBase):
    def __init__(self, descriptor: AudioSourceDescriptor, config: AudioCaptureConfig, api: PyAudioApi, *, clock: Callable[[], float] = monotonic, session_id_factory: Callable[[], str] | None = None) -> None:
        kwargs: dict[str, Any] = {'clock': clock}
        if session_id_factory is not None:
            kwargs['session_id_factory'] = session_id_factory
        super().__init__(config.queue_seconds, **kwargs)
        self._descriptor = descriptor
        self._api = api
        self._stream: Any | None = None

    def start(self) -> str:
        device = self._resolve_device()
        frames_per_buffer = max(1, round(device.sample_rate * 0.04))
        session_id, generation = self._begin(device.sample_rate, frames_per_buffer)

        def callback(payload: bytes, frame_count: int, _time_info: object, _status: int) -> tuple[None, int]:
            count = frame_count * device.input_channels
            samples = np.frombuffer(payload, dtype=np.float32, count=count).copy()
            self._publish(generation, samples, device.sample_rate, device.input_channels)
            return None, self._api.continue_token

        try:
            stream = self._api.open_input(device, frames_per_buffer, callback)
            self._stream = stream
            stream.start_stream()
        except Exception as exc:
            self._close_stream()
            error = AudioSourceOpenError(str(exc))
            self._mark_failed(error)
            raise error from exc
        self._mark_running()
        return session_id

    def stop(self) -> None:
        if self._stream is None and self.diagnostics().state is SourceState.STOPPED:
            return
        self._close_stream()
        self._stop_session()

    def close(self) -> None:
        self.stop()
        self._api.close()

    def _close_stream(self) -> None:
        stream = self._stream
        self._stream = None
        if stream is None:
            return
        try:
            if stream.is_active():
                stream.stop_stream()
        finally:
            stream.close()

    def _resolve_device(self) -> WasapiDevice:
        if self._descriptor.kind is AudioSourceKind.PROCESS:
            raise AudioSourceOpenError('process sources require the Rust helper')
        if self._descriptor.id == 'default-output':
            device = self._api.default_loopback()
            if device is None:
                raise AudioSourceNotFound('default WASAPI output is unavailable')
            return device
        prefix = 'wasapi-loopback:' if self._descriptor.kind is AudioSourceKind.SYSTEM else 'wasapi-input:'
        if not self._descriptor.id.startswith(prefix):
            raise AudioSourceNotFound(self._descriptor.id)
        try:
            index = int(self._descriptor.id.removeprefix(prefix))
        except ValueError as exc:
            raise AudioSourceNotFound(self._descriptor.id) from exc
        devices = self._api.loopback_devices() if self._descriptor.kind is AudioSourceKind.SYSTEM else self._api.input_devices()
        try:
            return next(device for device in devices if device.index == index)
        except StopIteration as exc:
            raise AudioSourceNotFound(self._descriptor.id) from exc
