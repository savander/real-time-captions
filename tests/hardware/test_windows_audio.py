import os
import subprocess
import sys
import time

import pytest

from real_time_captions.platforms.windows.audio.probe import probe_source


pytestmark = pytest.mark.windows_audio


_TONE_PROGRAM = r'''
import sys
import numpy as np
import pyaudiowpatch as pyaudio
amplitude = float(sys.argv[1])
manager = pyaudio.PyAudio()
info = manager.get_default_output_device_info()
rate = int(info['defaultSampleRate'])
channels = min(2, int(info['maxOutputChannels']))
stream = manager.open(format=pyaudio.paFloat32, channels=channels, rate=rate, output=True, frames_per_buffer=960)
for phase in range(0, rate * 4, 960):
    timeline = (np.arange(960, dtype=np.float32) + phase) / rate
    mono = (amplitude * np.sin(2 * np.pi * 440 * timeline)).astype(np.float32)
    stream.write(np.repeat(mono[:, None], channels, axis=1).reshape(-1).tobytes())
stream.stop_stream()
stream.close()
manager.terminate()
'''


def _enabled() -> None:
    if os.getenv('RUN_WINDOWS_AUDIO_TESTS') != '1':
        pytest.skip('set RUN_WINDOWS_AUDIO_TESTS=1 for Windows hardware tests')


def _start_tone(amplitude: float) -> subprocess.Popen[bytes]:
    return subprocess.Popen([sys.executable, '-c', _TONE_PROGRAM, str(amplitude)])


def _stop_tones(*processes: subprocess.Popen[bytes]) -> None:
    for process in processes:
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.terminate()
            process.wait(timeout=2)


def test_system_loopback_emits_frames() -> None:
    _enabled()
    source_id = os.getenv('RTC_SYSTEM_SOURCE_ID', 'default-output')
    tone = _start_tone(0.01)
    try:
        time.sleep(0.5)
        result = probe_source(source_id, 2.0)
    finally:
        _stop_tones(tone)

    assert result['frames'] > 20
    assert result['samples'] > result['sample_rate']
    assert result['sample_rate']


def test_selected_process_emits_frames() -> None:
    _enabled()
    selected = _start_tone(0.005)
    outside = _start_tone(0.05)
    try:
        time.sleep(0.5)
        result = probe_source(f'process:pid:{selected.pid}', 2.0)
    finally:
        _stop_tones(selected, outside)

    assert result['frames'] > 50
    assert result['samples'] > 96_000
    assert 0.002 < result['peak'] < 0.02


def test_microphone_emits_frames() -> None:
    _enabled()
    source_id = os.getenv('RTC_MICROPHONE_SOURCE_ID')
    if not source_id:
        pytest.skip('set RTC_MICROPHONE_SOURCE_ID to a WASAPI input ID')
    result = probe_source(source_id, 2.0)

    assert result['frames'] > 0
    assert result['samples'] > 0
