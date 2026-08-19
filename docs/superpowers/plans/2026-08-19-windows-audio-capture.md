# Windows Audio Capture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add wheel-only Windows system, process-tree, and microphone capture adapters that feed immutable bounded PCM frames into the portable captions core.

**Architecture:** Portable capture contracts and buffering remain under `real_time_captions.audio`; all PyAudioWPatch, ProcTap, psutil, and Windows behavior remains under `real_time_captions.platforms.windows.audio`. Adapter callbacks copy native PCM into a bounded oldest-drop queue, while lifecycle and reconnect logic stay independent from models and GUI code.

**Tech Stack:** Python 3.12, uv, NumPy, PyAudioWPatch 0.2.12.8, ProcTap 1.0.3, psutil 7.x, pytest, pytest-cov

**Spec:** `docs/superpowers/specs/2026-08-19-windows-audio-capture-design.md`

## Global Constraints

- The base dependency set remains platform-neutral; Windows dependencies live only in the `windows-audio` dependency group.
- CPython 3.12 Windows x64 installation must use wheels and must not invoke Visual Studio, CMake, or a local compiler.
- `real_time_captions.audio`, core, contracts, settings, and caption modules must not import PyAudioWPatch, ProcTap, psutil, ctypes, or Windows APIs.
- Hardware callbacks copy and enqueue PCM only; they never normalize, call ASR, translate, mutate captions, or invoke Qt.
- Each started source owns one session ID, a monotonic frame sequence, and a session-relative monotonic clock.
- Queues are bounded to approximately two seconds and drop the oldest frame before admitting a new frame.
- Per-process capture never silently falls back to full-system capture.
- Ordinary tests require no physical audio device; hardware tests use explicit `windows_audio` markers.
- No test persists captured user audio.

---

### Task 1: Define portable managed-capture contracts

**Files:**
- Create: `src/real_time_captions/audio/capture.py`
- Modify: `src/real_time_captions/backends/protocols.py`
- Test: `tests/audio/test_capture_contracts.py`

**Interfaces:**
- Consumes: existing `AudioFrame` and `SourceState`.
- Produces: `AudioSourceKind`, `AudioSourceDescriptor`, `AudioCaptureConfig`, `CaptureDiagnostics`, typed capture exceptions, and the expanded `AudioSource` protocol.

- [ ] **Step 1: Write failing contract tests**

```python
from dataclasses import FrozenInstanceError

import pytest

from real_time_captions.audio.capture import (
    AudioCaptureConfig,
    AudioSourceDescriptor,
    AudioSourceKind,
    CaptureDiagnostics,
)
from real_time_captions.contracts import SourceState


def test_descriptor_is_immutable_and_keeps_process_identity() -> None:
    descriptor = AudioSourceDescriptor(
        id='process:c:/apps/player.exe',
        kind=AudioSourceKind.PROCESS,
        name='Player',
        available=True,
        process_id=42,
        executable_path='C:/Apps/Player.exe',
    )

    assert descriptor.process_id == 42
    with pytest.raises(FrozenInstanceError):
        descriptor.name = 'changed'  # type: ignore[misc]


def test_capture_config_rejects_non_positive_queue_duration() -> None:
    with pytest.raises(ValueError, match='queue_seconds'):
        AudioCaptureConfig('default-output', queue_seconds=0.0)


def test_diagnostics_exposes_lifecycle_and_drop_count() -> None:
    diagnostics = CaptureDiagnostics(SourceState.RUNNING, 3, 1.25, None)
    assert diagnostics.dropped_frames == 3
    assert diagnostics.silent_seconds == 1.25
```

- [ ] **Step 2: Run tests and verify RED**

Run: `uv run pytest tests/audio/test_capture_contracts.py -v`

Expected: collection fails because `real_time_captions.audio.capture` does not exist.

- [ ] **Step 3: Implement the minimal portable contracts**

```python
# src/real_time_captions/audio/capture.py
from dataclasses import dataclass
from enum import StrEnum

from real_time_captions.contracts import SourceState


class AudioSourceKind(StrEnum):
    SYSTEM = 'system'
    PROCESS = 'process'
    MICROPHONE = 'microphone'


@dataclass(frozen=True, slots=True)
class AudioSourceDescriptor:
    id: str
    kind: AudioSourceKind
    name: str
    available: bool = True
    process_id: int | None = None
    executable_path: str | None = None


@dataclass(frozen=True, slots=True)
class AudioCaptureConfig:
    descriptor_id: str
    queue_seconds: float = 2.0

    def __post_init__(self) -> None:
        if self.queue_seconds <= 0:
            raise ValueError('queue_seconds must be positive')


@dataclass(frozen=True, slots=True)
class CaptureDiagnostics:
    state: SourceState
    dropped_frames: int
    silent_seconds: float | None
    last_error: str | None


class AudioCaptureError(RuntimeError): ...
class UnsupportedAudioCapture(AudioCaptureError): ...
class MissingAudioDependency(AudioCaptureError): ...
class AudioSourceNotFound(AudioCaptureError): ...
class AmbiguousAudioSource(AudioCaptureError): ...
class AudioSourceOpenError(AudioCaptureError): ...
class AudioStreamInterrupted(AudioCaptureError): ...
class InvalidAudioLifecycle(AudioCaptureError): ...
class AudioReconnectExhausted(AudioCaptureError): ...
```

Update `AudioSource` in `backends/protocols.py` to declare:

```python
class AudioSource(Protocol):
    @property
    def session_id(self) -> str | None: ...
    def start(self) -> str: ...
    def read(self, timeout: float | None = None) -> AudioFrame | None: ...
    def stop(self) -> None: ...
    def diagnostics(self) -> CaptureDiagnostics: ...
```

- [ ] **Step 4: Run focused and boundary tests**

Run: `uv run pytest tests/audio/test_capture_contracts.py tests/test_architecture_boundaries.py -v`

Expected: all tests pass; no Windows dependency is imported.

- [ ] **Step 5: Commit**

```powershell
git add src/real_time_captions/audio/capture.py src/real_time_captions/backends/protocols.py tests/audio/test_capture_contracts.py
git commit -m "feat(audio): define managed capture contracts"
```

---

### Task 2: Add the bounded frame handoff queue

**Files:**
- Create: `src/real_time_captions/audio/frame_queue.py`
- Test: `tests/audio/test_frame_queue.py`

**Interfaces:**
- Consumes: immutable `AudioFrame`.
- Produces: `BoundedFrameQueue(max_frames: int)` with `put`, `get`, `close`, `clear`, and `dropped_frames`.

- [ ] **Step 1: Write failing queue tests**

```python
import numpy as np

from real_time_captions.audio.frame import AudioFrame
from real_time_captions.audio.frame_queue import BoundedFrameQueue


def frame(sequence: int) -> AudioFrame:
    return AudioFrame('s1', np.array([sequence], dtype=np.float32), 16_000, 1, sequence, sequence / 10)


def test_full_queue_drops_oldest_frame() -> None:
    queue = BoundedFrameQueue(max_frames=2)
    queue.put(frame(1))
    queue.put(frame(2))
    queue.put(frame(3))

    assert queue.get(0).sequence == 2
    assert queue.get(0).sequence == 3
    assert queue.dropped_frames == 1


def test_close_unblocks_and_rejects_late_frames() -> None:
    queue = BoundedFrameQueue(max_frames=1)
    queue.close()
    queue.put(frame(1))

    assert queue.get(0) is None
    assert queue.size == 0
```

- [ ] **Step 2: Run tests and verify RED**

Run: `uv run pytest tests/audio/test_frame_queue.py -v`

Expected: import failure for `frame_queue`.

- [ ] **Step 3: Implement a condition-protected deque**

```python
class BoundedFrameQueue:
    def __init__(self, max_frames: int) -> None:
        if isinstance(max_frames, bool) or max_frames <= 0:
            raise ValueError('max_frames must be a positive integer')
        self._frames: deque[AudioFrame] = deque()
        self._condition = Condition()
        self._max_frames = max_frames
        self._closed = False
        self._dropped_frames = 0

    def put(self, frame: AudioFrame) -> None:
        with self._condition:
            if self._closed:
                return
            if len(self._frames) == self._max_frames:
                self._frames.popleft()
                self._dropped_frames += 1
            self._frames.append(frame)
            self._condition.notify()
```

`get(timeout)` uses `Condition.wait_for`, returns `None` on timeout or closed-empty state, and never returns a frame after `clear()` removed it. Properties read state under the same condition.

- [ ] **Step 4: Run queue tests and audio suite**

Run: `uv run pytest tests/audio -v`

Expected: all audio tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src/real_time_captions/audio/frame_queue.py tests/audio/test_frame_queue.py
git commit -m "feat(audio): bound capture frame handoff"
```

---

### Task 3: Add wheel-only Windows dependencies and import boundaries

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Create: `src/real_time_captions/platforms/__init__.py`
- Create: `src/real_time_captions/platforms/windows/__init__.py`
- Create: `src/real_time_captions/platforms/windows/audio/__init__.py`
- Create: `src/real_time_captions/platforms/windows/audio/dependencies.py`
- Modify: `tests/test_architecture_boundaries.py`
- Test: `tests/windows/audio/test_dependencies.py`

**Interfaces:**
- Consumes: portable capture exceptions.
- Produces: lazy `load_pyaudio()`, `load_proctap()`, and `load_psutil()` functions.

- [ ] **Step 1: Write failing dependency-boundary tests**

```python
def test_portable_files_exclude_windows_adapter_tree() -> None:
    files = portable_package_files()
    assert all('platforms/windows' not in path.as_posix() for path in files)


def test_missing_optional_module_has_typed_error(monkeypatch) -> None:
    monkeypatch.setattr(importlib, 'import_module', lambda name: (_ for _ in ()).throw(ModuleNotFoundError(name)))
    with pytest.raises(MissingAudioDependency, match='windows-audio'):
        load_pyaudio()
```

Also assert the manifest group contains exact Windows markers and pinned minimum-compatible versions.

- [ ] **Step 2: Run tests and verify RED**

Run: `uv run pytest tests/windows/audio/test_dependencies.py tests/test_architecture_boundaries.py -v`

Expected: missing loader/package paths and old all-package boundary behavior fail.

- [ ] **Step 3: Add the optional dependency group and lazy loaders**

```toml
[dependency-groups]
dev = [
    'pytest>=8.3',
    'pytest-cov>=6.0',
]
windows-audio = [
    'PyAudioWPatch==0.2.12.8; sys_platform == "win32"',
    'proc-tap==1.0.3; sys_platform == "win32" and platform_machine == "AMD64"',
    'psutil>=7.0,<8; sys_platform == "win32"',
]
```

`dependencies.py` imports through `importlib.import_module` only when a concrete adapter is constructed and wraps `ModuleNotFoundError` as `MissingAudioDependency` with the install command `uv sync --group windows-audio`.

Change the architecture scanner to scan `portable_package_files()` for forbidden modules and separately assert that files outside `platforms/windows/audio` never import `pyaudiowpatch`, `proctap`, or `psutil`. Keep the dynamic-import scanner active.

- [ ] **Step 4: Resolve and verify wheel-only installation**

Run:

```powershell
uv lock
uv sync --group dev --group windows-audio --locked
uv run python -c "import pyaudiowpatch, proctap, psutil; print('windows-audio wheels ok')"
uv run pytest tests/windows/audio/test_dependencies.py tests/test_architecture_boundaries.py -v
```

Expected: installation and imports succeed without invoking a compiler; tests pass.

- [ ] **Step 5: Commit**

```powershell
git add pyproject.toml uv.lock src/real_time_captions/platforms tests/test_architecture_boundaries.py tests/windows/audio/test_dependencies.py
git commit -m "build(audio): add Windows capture wheels"
```

---

### Task 4: Discover WASAPI output and microphone devices

**Files:**
- Create: `src/real_time_captions/platforms/windows/audio/pyaudio_api.py`
- Create: `src/real_time_captions/platforms/windows/audio/discovery.py`
- Test: `tests/windows/audio/test_device_discovery.py`

**Interfaces:**
- Consumes: `AudioSourceDescriptor`, `AudioSourceKind`, lazy PyAudioWPatch loader.
- Produces: `WasapiDevice`, `PyAudioApi`, and `discover_wasapi_sources(api) -> tuple[AudioSourceDescriptor, ...]`.

- [ ] **Step 1: Write failing discovery tests with complete fake device dictionaries**

```python
def test_discovery_maps_loopbacks_and_microphones_without_duplicates() -> None:
    api = FakePyAudioApi(
        loopbacks=[device(8, 'Speakers [Loopback]', 2, 0, 48_000)],
        inputs=[device(3, 'USB Microphone', 0, 1, 48_000)],
        default_loopback=device(8, 'Speakers [Loopback]', 2, 0, 48_000),
    )

    descriptors = discover_wasapi_sources(api)

    assert [(item.id, item.kind) for item in descriptors] == [
        ('default-output', AudioSourceKind.SYSTEM),
        ('wasapi-loopback:8', AudioSourceKind.SYSTEM),
        ('wasapi-input:3', AudioSourceKind.MICROPHONE),
    ]
```

Add tests for missing default output, duplicate loopback indexes, malformed native device data, and deterministic ordering.

- [ ] **Step 2: Run tests and verify RED**

Run: `uv run pytest tests/windows/audio/test_device_discovery.py -v`

Expected: missing discovery module.

- [ ] **Step 3: Implement the facade and pure descriptor mapping**

`PyAudioApi` owns the PyAudio context and exposes copied `WasapiDevice` values instead of raw dictionaries. `discover_wasapi_sources` prepends `default-output` only when a default loopback resolves, sorts physical loopbacks and microphones by casefolded name then index, and never exposes PortAudio's transient dictionaries.

```python
@dataclass(frozen=True, slots=True)
class WasapiDevice:
    index: int
    name: str
    sample_rate: int
    input_channels: int
    output_channels: int
    loopback: bool
```

- [ ] **Step 4: Run discovery and architecture tests**

Run: `uv run pytest tests/windows/audio/test_device_discovery.py tests/test_architecture_boundaries.py -v`

Expected: all pass.

- [ ] **Step 5: Commit**

```powershell
git add src/real_time_captions/platforms/windows/audio/pyaudio_api.py src/real_time_captions/platforms/windows/audio/discovery.py tests/windows/audio/test_device_discovery.py
git commit -m "feat(audio): discover WASAPI sources"
```

---

### Task 5: Capture system loopback and microphone frames

**Files:**
- Create: `src/real_time_captions/platforms/windows/audio/source_base.py`
- Create: `src/real_time_captions/platforms/windows/audio/pyaudio_source.py`
- Test: `tests/windows/audio/test_pyaudio_source.py`

**Interfaces:**
- Consumes: `AudioCaptureConfig`, `BoundedFrameQueue`, `PyAudioApi`, and a selected `WasapiDevice`.
- Produces: `WasapiAudioSource` implementing `AudioSource` for system and microphone descriptors.

- [ ] **Step 1: Write failing lifecycle and callback tests**

```python
def test_callback_publishes_owned_native_format_frame() -> None:
    clock = FakeClock([10.0, 10.04])
    stream = FakeStream()
    source = WasapiAudioSource(device(), config(), FakeApi(stream), clock=clock)
    session_id = source.start()

    stream.emit(np.array([0.25, -0.25], dtype=np.float32).tobytes(), frames=1)
    frame = source.read(0)

    assert frame is not None
    assert frame.session_id == session_id
    assert frame.sequence == 1
    assert frame.sample_rate == 48_000
    assert frame.channels == 2
    assert frame.captured_at == pytest.approx(0.04)
    assert frame.samples.flags.writeable is False
```

Add tests for idempotent stop, late callback rejection, queue overflow diagnostics, invalid descriptor kind, native open failure, and `default-output` resolution at each start.

- [ ] **Step 2: Run tests and verify RED**

Run: `uv run pytest tests/windows/audio/test_pyaudio_source.py -v`

Expected: missing source classes.

- [ ] **Step 3: Implement shared lifecycle and PyAudio callback conversion**

`ManagedSourceBase` creates `uuid4().hex`, records `monotonic()` as session zero, increments sequence under a lock, builds `AudioFrame`, and publishes it to `BoundedFrameQueue`. Queue capacity is `max(1, ceil(queue_seconds * sample_rate / frames_per_buffer))`.

`WasapiAudioSource` opens PyAudio with `input=True`, selected `input_device_index`, native channel count/rate, float32 format, and a callback. The callback converts exactly `frames * channels` samples from the supplied bytes and returns the facade's continue token.

- [ ] **Step 4: Run focused and complete portable suites**

Run:

```powershell
uv run pytest tests/windows/audio/test_pyaudio_source.py tests/audio -v
uv run pytest -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src/real_time_captions/platforms/windows/audio/source_base.py src/real_time_captions/platforms/windows/audio/pyaudio_source.py tests/windows/audio/test_pyaudio_source.py
git commit -m "feat(audio): capture WASAPI PCM frames"
```

---

### Task 6: Discover and resolve process selections

**Files:**
- Create: `src/real_time_captions/platforms/windows/audio/processes.py`
- Modify: `src/real_time_captions/platforms/windows/audio/discovery.py`
- Test: `tests/windows/audio/test_process_discovery.py`

**Interfaces:**
- Consumes: lazy psutil loader and process descriptor fields.
- Produces: `ProcessInfo`, `process_selection_key(path, pid)`, `discover_process_sources(api)`, and `resolve_process_selection(key, api)`.

- [ ] **Step 1: Write failing process identity tests**

```python
def test_path_based_selection_survives_pid_change() -> None:
    original = ProcessInfo(10, 'Player.exe', r'C:\Apps\Player.exe')
    restarted = ProcessInfo(99, 'Player.exe', r'c:\apps\PLAYER.exe')
    key = process_selection_key(original)

    assert key == 'process:c:/apps/player.exe'
    assert resolve_process_selection(key, FakeProcessApi([restarted])) == restarted


def test_multiple_matching_processes_are_ambiguous() -> None:
    api = FakeProcessApi([
        ProcessInfo(10, 'Player.exe', r'C:\Apps\Player.exe'),
        ProcessInfo(11, 'Player.exe', r'C:\Apps\Player.exe'),
    ])
    with pytest.raises(AmbiguousAudioSource):
        resolve_process_selection('process:c:/apps/player.exe', api)
```

Add tests for inaccessible executable paths, PID-only keys, vanished processes, ignored zombie entries, and deterministic descriptor ordering.

- [ ] **Step 2: Run tests and verify RED**

Run: `uv run pytest tests/windows/audio/test_process_discovery.py -v`

Expected: missing process module.

- [ ] **Step 3: Implement the psutil facade and pure resolution rules**

Normalize executable paths with `Path.resolve(strict=False)`, forward slashes, and `casefold()`. A path-based key may reattach only when exactly one live process matches. A PID-only key never reattaches to a different PID. Access-denied processes remain discoverable by name/PID but have no executable path.

- [ ] **Step 4: Run process and architecture tests**

Run: `uv run pytest tests/windows/audio/test_process_discovery.py tests/test_architecture_boundaries.py -v`

Expected: all pass.

- [ ] **Step 5: Commit**

```powershell
git add src/real_time_captions/platforms/windows/audio/processes.py src/real_time_captions/platforms/windows/audio/discovery.py tests/windows/audio/test_process_discovery.py
git commit -m "feat(audio): resolve process capture targets"
```

---

### Task 7: Capture and reconnect selected process audio

**Files:**
- Create: `src/real_time_captions/platforms/windows/audio/proctap_api.py`
- Create: `src/real_time_captions/platforms/windows/audio/process_source.py`
- Test: `tests/windows/audio/test_process_source.py`

**Interfaces:**
- Consumes: `ManagedSourceBase`, process resolver, ProcTap 1.0.3 callback API, and `AudioCaptureConfig`.
- Produces: `ProcessAudioSource` implementing `AudioSource` without system fallback.

- [ ] **Step 1: Write failing process capture and reconnect tests**

```python
def test_process_callback_emits_float32_frames_for_selected_pid() -> None:
    tap = FakeProcTap(format_info={'sample_rate': 48_000, 'channels': 2, 'format': 'float32'})
    source = ProcessAudioSource(selection(), config(), FakeResolver(pid=42), FakeProcTapFactory(tap), clock=clock())
    session = source.start()

    tap.emit(np.array([0.1, -0.1], dtype=np.float32).tobytes(), frames=1)
    frame = source.read(0)

    assert frame is not None
    assert frame.session_id == session
    assert frame.channels == 2
    assert frame.sample_rate == 48_000


def test_process_restart_reattaches_with_new_session_and_no_system_fallback() -> None:
    resolver = ScriptedResolver([ProcessInfo(42, 'Player.exe', PATH), AudioSourceNotFound(), ProcessInfo(77, 'Player.exe', PATH)])
    factory = RecordingProcTapFactory()
    source = ProcessAudioSource(selection(), config(), resolver, factory, clock=clock())
    first_session = source.start()
    factory.latest.stop_unexpectedly()

    assert source.reconnect_once() is False
    assert source.diagnostics().state is SourceState.RECONNECTING
    assert source.reconnect_once() is True
    assert source.session_id != first_session
    assert factory.pids == [42, 77]
    assert factory.system_loopback_calls == 0
```

Add tests for int16 fallback conversion metadata, close on failed start, ambiguous restart, reconnect exhaustion, stale callback rejection, prolonged silence diagnostics, and exact exception chaining.

- [ ] **Step 2: Run tests and verify RED**

Run: `uv run pytest tests/windows/audio/test_process_source.py -v`

Expected: missing ProcTap facade and process source.

- [ ] **Step 3: Implement ProcTap facade and explicit reconnect**

Construct ProcTap as:

```python
tap = proctap.ProcTap(
    pid=pid,
    config=proctap.StreamConfig(sample_rate=48_000, channels=2),
    on_data=callback,
)
tap.start()
format_info = tap.get_format()
```

`ProcessAudioSource` maps `float32` to `np.float32` and `int16` to `np.int16`, validates callback byte length, and delegates immutable frame publication to `ManagedSourceBase`. Unexpected native stop enters `RECONNECTING`; `reconnect_once()` closes the old tap, resolves the stable key, and opens only a matching process. Exhaustion changes state to `FAILED` and raises `AudioReconnectExhausted`.

- [ ] **Step 4: Run process, Windows adapter, and full suites**

Run:

```powershell
uv run pytest tests/windows/audio/test_process_source.py tests/windows/audio -v
uv run pytest -q
```

Expected: all pass.

- [ ] **Step 5: Commit**

```powershell
git add src/real_time_captions/platforms/windows/audio/proctap_api.py src/real_time_captions/platforms/windows/audio/process_source.py tests/windows/audio/test_process_source.py
git commit -m "feat(audio): capture selected process tree"
```

---

### Task 8: Add Windows hardware probes and milestone documentation

**Files:**
- Modify: `src/real_time_captions/cli.py`
- Create: `src/real_time_captions/platforms/windows/audio/probe.py`
- Create: `tests/windows/audio/test_probe_cli.py`
- Create: `tests/hardware/test_windows_audio.py`
- Modify: `pyproject.toml`
- Modify: `README.md`
- Modify: `docs/Architecture.md`

**Interfaces:**
- Consumes: discovery, all three source kinds, normalizer, diagnostics.
- Produces: `audio-list`, `audio-probe-system`, `audio-probe-process`, and `audio-probe-microphone` CLI commands plus explicitly marked hardware evidence.

- [ ] **Step 1: Write failing CLI tests**

```python
def test_audio_list_prints_deterministic_json(monkeypatch, capsys) -> None:
    monkeypatch.setattr(probe, 'discover_all_sources', lambda: (descriptor(),))
    assert main(['audio-list']) == 0
    assert json.loads(capsys.readouterr().out) == [{
        'available': True,
        'id': 'default-output',
        'kind': 'system',
        'name': 'Default output',
        'process_id': None,
    }]


def test_probe_reports_frame_and_drop_metrics_without_pcm(monkeypatch, capsys) -> None:
    monkeypatch.setattr(probe, 'open_source', lambda descriptor_id: FakeSource())
    assert main(['audio-probe-system', '--seconds', '0.1']) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload['frames'] == 2
    assert payload['samples'] == 3200
    assert 'pcm' not in payload
```

- [ ] **Step 2: Run tests and verify RED**

Run: `uv run pytest tests/windows/audio/test_probe_cli.py -v`

Expected: commands are unknown.

- [ ] **Step 3: Implement probe commands and hardware markers**

Commands print JSON only. Probes report descriptor, session ID, frame/sample counts, source format, peak absolute amplitude, duration, dropped frames, and final lifecycle state. They never print or write PCM.

Register markers:

```toml
[tool.pytest.ini_options]
markers = [
    'windows_audio: requires Windows audio hardware and optional dependencies',
]
```

Hardware tests skip unless `RUN_WINDOWS_AUDIO_TESTS=1`. System and microphone tests accept descriptor IDs from environment variables. Process isolation accepts a PID and verifies a non-empty selected stream while a separately generated tone is outside the selected process tree. Each capture is at most five seconds and stays in memory.

- [ ] **Step 4: Document support and run all non-hardware gates**

Update README quick start with:

```powershell
uv sync --group dev --group windows-audio
uv run real-time-captions audio-list
uv run real-time-captions audio-probe-system --seconds 2
```

Document source lifecycle, explicit no-fallback behavior, Windows 10/11 x64 and CPython 3.12 wheel requirements, protected-content silence, and privacy in `docs/Architecture.md`.

Run:

```powershell
uv lock --check
uv sync --group dev --group windows-audio --locked
uv run pytest -m "not windows_audio" -v --cov=real_time_captions --cov-report=term-missing
uv run pytest tests/test_architecture_boundaries.py -v
uv run real-time-captions audio-list
uv run real-time-captions core-smoke
uv build
git diff --check
```

Expected: all commands exit 0, coverage remains at least 90%, audio-list returns valid JSON, and both source and wheel builds succeed.

- [ ] **Step 5: Run available Windows hardware smoke**

Run after selecting a live output descriptor:

```powershell
$env:RUN_WINDOWS_AUDIO_TESTS = '1'
$env:RTC_SYSTEM_SOURCE_ID = 'default-output'
uv run pytest tests/hardware/test_windows_audio.py -m windows_audio -v
```

Expected: system loopback emits non-empty immutable frames. Process and microphone cases skip only when their explicit PID/device variables are absent and print the missing variable in the skip reason.

- [ ] **Step 6: Commit**

```powershell
git add src/real_time_captions/cli.py src/real_time_captions/platforms/windows/audio/probe.py tests/windows/audio/test_probe_cli.py tests/hardware/test_windows_audio.py pyproject.toml README.md docs/Architecture.md
git commit -m "feat(audio): verify Windows capture milestone"
```

---

## Final milestone gate

- [ ] Install into a fresh uv environment with both `dev` and `windows-audio` groups and confirm no compiler process starts.
- [ ] Run the complete non-hardware suite with at least 90% coverage.
- [ ] Run architecture boundary tests with optional Windows modules installed and with them unavailable.
- [ ] Run `audio-list`, system loopback probe, and any available process/microphone probes.
- [ ] Confirm all probe output is metadata-only JSON and no captured PCM file exists.
- [ ] Review `git diff --check`, dependency lock changes, licenses, and the full branch diff.
- [ ] Push only after the final review has no open Critical or Important finding.
