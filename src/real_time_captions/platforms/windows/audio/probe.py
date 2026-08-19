from dataclasses import asdict
from sys import platform
from time import monotonic
from typing import Any

import numpy as np

from real_time_captions.audio.capture import (
    AudioCaptureConfig,
    AudioSourceDescriptor,
    AudioSourceKind,
    AudioSourceNotFound,
    UnsupportedAudioCapture,
)
from real_time_captions.backends.protocols import AudioSource
from real_time_captions.platforms.windows.audio.discovery import (
    discover_wasapi_sources,
)
from real_time_captions.platforms.windows.audio.process_source import (
    ProcessAudioSource,
)
from real_time_captions.platforms.windows.audio.processes import (
    PsutilProcessApi,
    discover_process_sources,
    resolve_process_selection,
)
from real_time_captions.platforms.windows.audio.flexaudio_api import (
    FlexAudioProcessFactory,
)
from real_time_captions.platforms.windows.audio.pyaudio_api import PyAudioApi
from real_time_captions.platforms.windows.audio.pyaudio_source import (
    WasapiAudioSource,
)


def _require_windows() -> None:
    if platform != 'win32':
        raise UnsupportedAudioCapture('Windows audio capture requires Windows')


def discover_all_sources() -> tuple[AudioSourceDescriptor, ...]:
    _require_windows()
    audio_api = PyAudioApi()
    try:
        devices = discover_wasapi_sources(audio_api)
    finally:
        audio_api.close()
    processes = discover_process_sources(PsutilProcessApi())
    return devices + processes


def open_source(descriptor_id: str) -> AudioSource:
    _require_windows()
    if descriptor_id.startswith('process:'):
        process_api = PsutilProcessApi()
        descriptor = AudioSourceDescriptor(
            descriptor_id,
            AudioSourceKind.PROCESS,
            descriptor_id,
        )
        resolver = lambda key: resolve_process_selection(key, process_api)
        return ProcessAudioSource(
            descriptor,
            AudioCaptureConfig(descriptor_id),
            resolver,
            FlexAudioProcessFactory(),
        )

    audio_api = PyAudioApi()
    descriptors = discover_wasapi_sources(audio_api)
    try:
        descriptor = next(item for item in descriptors if item.id == descriptor_id)
    except StopIteration as exc:
        audio_api.close()
        raise AudioSourceNotFound(descriptor_id) from exc
    return WasapiAudioSource(
        descriptor, AudioCaptureConfig(descriptor_id), audio_api
    )


def descriptor_payload(descriptor: AudioSourceDescriptor) -> dict[str, Any]:
    payload = asdict(descriptor)
    payload['kind'] = descriptor.kind.value
    return payload


def probe_source(descriptor_id: str, seconds: float) -> dict[str, Any]:
    if seconds <= 0 or seconds > 5:
        raise ValueError('seconds must be in the range (0, 5]')
    source = open_source(descriptor_id)
    opening_at = monotonic()
    frames = 0
    samples = 0
    peak = 0.0
    sample_rate: int | None = None
    channels: int | None = None
    session_id: str | None = None
    try:
        session_id = source.start()
        started_at = monotonic()
        deadline = started_at + seconds
        while (remaining := deadline - monotonic()) > 0:
            frame = source.read(min(0.1, remaining))
            if frame is None:
                continue
            frames += 1
            samples += int(frame.samples.size)
            sample_rate = frame.sample_rate
            channels = frame.channels
            if frame.samples.size:
                peak = max(peak, float(np.max(np.abs(frame.samples))))
    finally:
        source.stop()
        close = getattr(source, 'close', None)
        if callable(close):
            close()
    diagnostics = source.diagnostics()
    return {
        'descriptor_id': descriptor_id,
        'session_id': session_id,
        'frames': frames,
        'samples': samples,
        'sample_rate': sample_rate,
        'channels': channels,
        'peak': peak,
        'startup_seconds': started_at - opening_at,
        'duration_seconds': monotonic() - started_at,
        'dropped_frames': diagnostics.dropped_frames,
        'state': diagnostics.state.value,
        'last_error': diagnostics.last_error,
    }
