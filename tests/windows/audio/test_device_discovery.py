from dataclasses import dataclass

import pytest

from real_time_captions.audio.capture import (
    AudioSourceKind,
    AudioSourceOpenError,
)
from real_time_captions.platforms.windows.audio.discovery import (
    discover_wasapi_sources,
)
from real_time_captions.platforms.windows.audio.pyaudio_api import (
    WasapiDevice,
    wasapi_device_from_info,
)


def device(
    index: int,
    name: str,
    input_channels: int,
    output_channels: int,
    sample_rate: int,
    *,
    loopback: bool,
) -> WasapiDevice:
    return WasapiDevice(
        index,
        name,
        sample_rate,
        input_channels,
        output_channels,
        loopback,
    )


@dataclass
class FakePyAudioApi:
    loopbacks: tuple[WasapiDevice, ...]
    inputs: tuple[WasapiDevice, ...]
    default: WasapiDevice | None

    def default_loopback(self) -> WasapiDevice | None:
        return self.default

    def loopback_devices(self) -> tuple[WasapiDevice, ...]:
        return self.loopbacks

    def input_devices(self) -> tuple[WasapiDevice, ...]:
        return self.inputs


def test_discovery_maps_loopbacks_and_microphones_without_duplicates() -> None:
    default = device(8, 'Speakers [Loopback]', 2, 0, 48_000, loopback=True)
    api = FakePyAudioApi(
        loopbacks=(default, default),
        inputs=(device(3, 'USB Microphone', 1, 0, 48_000, loopback=False),),
        default=default,
    )

    descriptors = discover_wasapi_sources(api)

    assert [(item.id, item.kind) for item in descriptors] == [
        ('default-output', AudioSourceKind.SYSTEM),
        ('wasapi-loopback:8', AudioSourceKind.SYSTEM),
        ('wasapi-input:3', AudioSourceKind.MICROPHONE),
    ]


def test_discovery_orders_each_source_kind_by_name_then_index() -> None:
    api = FakePyAudioApi(
        loopbacks=(
            device(9, 'Zulu', 2, 0, 48_000, loopback=True),
            device(4, 'alpha', 2, 0, 48_000, loopback=True),
        ),
        inputs=(
            device(7, 'Mic Z', 1, 0, 48_000, loopback=False),
            device(2, 'mic a', 1, 0, 48_000, loopback=False),
        ),
        default=None,
    )

    assert [item.id for item in discover_wasapi_sources(api)] == [
        'wasapi-loopback:4',
        'wasapi-loopback:9',
        'wasapi-input:2',
        'wasapi-input:7',
    ]


def test_device_mapping_copies_real_pyaudio_fields() -> None:
    mapped = wasapi_device_from_info(
        {
            'index': 21,
            'structVersion': 2,
            'name': 'Headphones [Loopback]',
            'hostApi': 2,
            'maxInputChannels': 2,
            'maxOutputChannels': 0,
            'defaultLowInputLatency': 0.003,
            'defaultLowOutputLatency': 0.0,
            'defaultHighInputLatency': 0.01,
            'defaultHighOutputLatency': 0.0,
            'defaultSampleRate': 96_000.0,
            'isLoopbackDevice': True,
        }
    )

    assert mapped == device(
        21,
        'Headphones [Loopback]',
        2,
        0,
        96_000,
        loopback=True,
    )


def test_device_mapping_rejects_malformed_native_data() -> None:
    with pytest.raises(AudioSourceOpenError, match='device metadata'):
        wasapi_device_from_info({'index': 1, 'name': 'broken'})
