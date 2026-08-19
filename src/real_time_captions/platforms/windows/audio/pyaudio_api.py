from dataclasses import dataclass
from types import ModuleType
from collections.abc import Callable
from typing import Mapping

from real_time_captions.audio.capture import AudioSourceOpenError
from real_time_captions.platforms.windows.audio.dependencies import load_pyaudio


@dataclass(frozen=True, slots=True)
class WasapiDevice:
    index: int
    name: str
    sample_rate: int
    input_channels: int
    output_channels: int
    loopback: bool


def wasapi_device_from_info(info: Mapping[str, object]) -> WasapiDevice:
    try:
        device = WasapiDevice(
            index=int(info['index']),
            name=str(info['name']),
            sample_rate=int(float(info['defaultSampleRate'])),
            input_channels=int(info['maxInputChannels']),
            output_channels=int(info['maxOutputChannels']),
            loopback=bool(info.get('isLoopbackDevice', False)),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise AudioSourceOpenError('invalid WASAPI device metadata') from exc
    if device.sample_rate <= 0 or min(
        device.input_channels, device.output_channels
    ) < 0:
        raise AudioSourceOpenError('invalid WASAPI device metadata')
    return device


class PyAudioApi:
    def __init__(self, module: ModuleType | None = None) -> None:
        self.module = module or load_pyaudio()
        self.manager = self.module.PyAudio()

    def close(self) -> None:
        self.manager.terminate()

    @property
    def continue_token(self) -> int:
        return int(self.module.paContinue)

    def open_input(self, device: WasapiDevice, frames_per_buffer: int, callback: Callable[..., tuple[None, int]]) -> object:
        return self.manager.open(
            format=self.module.paFloat32,
            channels=device.input_channels,
            rate=device.sample_rate,
            input=True,
            input_device_index=device.index,
            frames_per_buffer=frames_per_buffer,
            stream_callback=callback,
            start=False,
        )

    def default_loopback(self) -> WasapiDevice | None:
        try:
            return wasapi_device_from_info(
                self.manager.get_default_wasapi_loopback()
            )
        except OSError:
            return None

    def loopback_devices(self) -> tuple[WasapiDevice, ...]:
        return tuple(
            wasapi_device_from_info(info)
            for info in self.manager.get_loopback_device_info_generator()
        )

    def input_devices(self) -> tuple[WasapiDevice, ...]:
        devices = (
            wasapi_device_from_info(info)
            for info in self.manager.get_device_info_generator_by_host_api(
                host_api_type=self.module.paWASAPI
            )
        )
        return tuple(
            device
            for device in devices
            if device.input_channels > 0 and not device.loopback
        )
