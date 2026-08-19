from collections.abc import Callable
from time import monotonic

import numpy as np

from real_time_captions.audio.capture import (
    AudioCaptureConfig,
    AudioReconnectExhausted,
    AudioSourceDescriptor,
    AudioSourceOpenError,
    AudioStreamInterrupted,
)
from real_time_captions.contracts import SourceState
from real_time_captions.platforms.windows.audio.processes import ProcessInfo
from real_time_captions.platforms.windows.audio.flexaudio_api import (
    FlexAudioProcessFactory,
    ProcessTap,
)
from real_time_captions.platforms.windows.audio.source_base import (
    ManagedSourceBase,
)


class ProcessAudioSource(ManagedSourceBase):
    def __init__(
        self,
        descriptor: AudioSourceDescriptor,
        config: AudioCaptureConfig,
        resolver: Callable[[str], ProcessInfo],
        factory: FlexAudioProcessFactory,
        *,
        clock: Callable[[], float] = monotonic,
        session_id_factory: Callable[[], str] | None = None,
    ) -> None:
        kwargs: dict[str, object] = {'clock': clock}
        if session_id_factory is not None:
            kwargs['session_id_factory'] = session_id_factory
        super().__init__(config.queue_seconds, **kwargs)  # type: ignore[arg-type]
        self._descriptor = descriptor
        self._resolver = resolver
        self._factory = factory
        self._reconnect_limit = config.reconnect_attempts
        self._reconnect_attempts = 0
        self._tap: ProcessTap | None = None

    def start(self) -> str:
        try:
            process = self._resolver(self._descriptor.id)
        except Exception as exc:
            self._mark_failed(exc)
            raise
        self._reconnect_attempts = 0
        return self._open(process)

    def _open(self, process: ProcessInfo) -> str:
        context: dict[str, object] = {}

        def callback(payload: bytes, reported_frames: int) -> None:
            try:
                dtype = context['dtype']
                channels = int(context['channels'])
                sample_rate = int(context['sample_rate'])
                generation = int(context['generation'])
                item_size = np.dtype(dtype).itemsize
                frame_bytes = item_size * channels
                if len(payload) % frame_bytes:
                    raise AudioStreamInterrupted('invalid helper PCM byte length')
                frame_count = len(payload) // frame_bytes
                if reported_frames >= 0 and reported_frames != frame_count:
                    raise AudioStreamInterrupted('helper frame count mismatch')
                samples = np.frombuffer(payload, dtype=dtype).copy()
                self._publish(generation, samples, sample_rate, channels)
            except Exception as exc:
                self._mark_failed(exc)

        tap: ProcessTap | None = None
        try:
            tap = self._factory.create(process.pid, callback)
            self._tap = tap
            format_info = tap.get_format()
            sample_rate = int(format_info['sample_rate'])
            channels = int(format_info['channels'])
            sample_format = str(format_info['sample_format']).casefold()
            dtype = {'float32': np.float32, 'int16': np.int16}[sample_format]
            frames_per_buffer = int(
                format_info.get(
                    'frames_per_chunk', max(1, round(sample_rate * 0.01))
                )
            )
            session_id, generation = self._begin(
                sample_rate, frames_per_buffer
            )
            context.update(
                dtype=dtype,
                channels=channels,
                sample_rate=sample_rate,
                generation=generation,
            )
            tap.start()
        except Exception as exc:
            if tap is not None:
                tap.close()
            self._tap = None
            error = AudioSourceOpenError(str(exc))
            self._mark_failed(error)
            raise error from exc
        self._mark_running()
        return session_id

    def read(self, timeout: float | None = None):
        frame = super().read(timeout)
        tap = self._tap
        if (
            frame is None
            and tap is not None
            and not tap.is_running
            and self.diagnostics().state is SourceState.RUNNING
        ):
            self._mark_reconnecting(
                AudioStreamInterrupted('selected process capture stopped')
            )
        return frame

    def reconnect_once(self) -> bool:
        self._close_tap()
        self._reconnect_attempts += 1
        try:
            process = self._resolver(self._descriptor.id)
        except Exception as exc:
            self._mark_reconnecting(exc)
            if self._reconnect_attempts >= self._reconnect_limit:
                error = AudioReconnectExhausted(str(exc))
                self._mark_failed(error)
                raise error from exc
            return False
        self._open(process)
        self._reconnect_attempts = 0
        return True

    def stop(self) -> None:
        if self._tap is None and self.diagnostics().state is SourceState.STOPPED:
            return
        self._close_tap()
        self._stop_session()

    def close(self) -> None:
        self.stop()

    def _close_tap(self) -> None:
        tap = self._tap
        self._tap = None
        if tap is not None:
            tap.close()
