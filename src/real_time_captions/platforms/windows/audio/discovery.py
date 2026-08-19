from typing import Protocol

from real_time_captions.audio.capture import (
    AudioSourceDescriptor,
    AudioSourceKind,
)
from real_time_captions.platforms.windows.audio.pyaudio_api import WasapiDevice


class DeviceDiscoveryApi(Protocol):
    def default_loopback(self) -> WasapiDevice | None: ...

    def loopback_devices(self) -> tuple[WasapiDevice, ...]: ...

    def input_devices(self) -> tuple[WasapiDevice, ...]: ...


def _ordered_unique(
    devices: tuple[WasapiDevice, ...],
) -> tuple[WasapiDevice, ...]:
    unique = {device.index: device for device in devices}
    return tuple(
        sorted(unique.values(), key=lambda item: (item.name.casefold(), item.index))
    )


def discover_wasapi_sources(
    api: DeviceDiscoveryApi,
) -> tuple[AudioSourceDescriptor, ...]:
    descriptors: list[AudioSourceDescriptor] = []
    default = api.default_loopback()
    if default is not None:
        descriptors.append(
            AudioSourceDescriptor(
                'default-output',
                AudioSourceKind.SYSTEM,
                f'Default output — {default.name}',
            )
        )
    descriptors.extend(
        AudioSourceDescriptor(
            f'wasapi-loopback:{device.index}',
            AudioSourceKind.SYSTEM,
            device.name,
        )
        for device in _ordered_unique(api.loopback_devices())
    )
    descriptors.extend(
        AudioSourceDescriptor(
            f'wasapi-input:{device.index}',
            AudioSourceKind.MICROPHONE,
            device.name,
        )
        for device in _ordered_unique(api.input_devices())
    )
    return tuple(descriptors)
