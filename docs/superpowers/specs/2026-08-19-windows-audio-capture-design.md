# Windows Audio Capture Design

**Date:** 2026-08-19
**Status:** Approved
**Milestone:** 2 of 5
**Reference platform:** Windows 10/11 x64 with CPython 3.12

> **Implementation amendment (2026-08-19):** hardware validation rejected
> ProcTap 1.0.3. Its native source contains a silent system-wide fallback and
> it failed to attach to an already-playing process on the reference machine.
> The shipped process adapter instead uses the pinned Rust `flexaudio 0.2.0`
> helper, which captured an already-playing target with no system fallback.
> PyAudioWPatch remains the system/microphone adapter. Release packaging must
> bundle the prebuilt helper; source builds require Rust plus MSVC Build Tools.
> Hardware validation covers the exact audio-owning PID. Automatic aggregation
> of separate child-process audio sessions is deferred.
> ProcTap-specific text below is retained only as the original approved design
> record and is superseded by this amendment.

## Summary

Add replaceable Windows audio adapters to the portable real-time captions core.
The application will capture either an entire output endpoint, one selected
process tree, or an optional microphone. Full-system loopback uses
PyAudioWPatch; per-process capture uses ProcTap's native WASAPI process
loopback wheel. End users must not need Visual Studio, a Windows SDK, or a
local compiler.

This milestone stops at reliable PCM delivery and hardware evidence. Model,
GUI, child-process, and release-host integration remain separate milestones.

## Goals

- Enumerate Windows output endpoints, input endpoints, and capturable
  processes without importing Windows libraries from the portable core.
- Capture full-system output through WASAPI loopback without rerouting normal
  playback.
- Capture a selected process and its child process tree without mixing other
  applications.
- Offer microphone capture through the same source contract.
- Emit immutable `AudioFrame` values with session identity, monotonic sequence,
  native format metadata, and session-relative timestamps.
- Keep callbacks bounded and independent from normalization, ASR, translation,
  and GUI work.
- Reconnect explicitly after device or process restarts without silently
  changing the selected source kind.
- Install from Windows wheels on CPython 3.12 x64 without compiling native
  code.

## Non-goals

- Linux PipeWire/PulseAudio and macOS CoreAudio adapters.
- ASR or translation model selection and benchmarking.
- PyQt controls, overlay rendering, or notification-area integration.
- AI child-process IPC and application packaging.
- Capturing DRM-protected or otherwise protected audio.
- Automatic fallback from per-process capture to full-system capture.

## Technology decision

The selected implementation uses two small, replaceable adapters:

- PyAudioWPatch 0.2.12.8 for output endpoint enumeration, WASAPI loopback, and
  microphone input. PyPI publishes CPython 3.12 Windows x64 wheels.
- ProcTap 1.0.3 for `AUDIOCLIENT_ACTIVATION_TYPE_PROCESS_LOOPBACK`. PyPI
  publishes a CPython 3.12 Windows x64 wheel and the implementation includes
  the selected process and its child process tree.

Both projects declare MIT licensing. Their imports remain in the Windows
adapter package. A future adapter may replace either dependency without
changing core contracts.

Rejected alternatives:

- A custom C++ helper based on Microsoft's ApplicationLoopback sample offers
  more control but adds a native build and maintenance surface before hardware
  evidence shows it is necessary.
- GStreamer `wasapi2src` supports endpoint and process loopback but adds a much
  larger runtime and packaging burden than this application needs.

## Package boundaries

Portable declarations live under `real_time_captions.audio`. Concrete Windows
code lives under `real_time_captions.platforms.windows.audio`.

The portable layer defines:

- `AudioSourceKind`: `SYSTEM`, `PROCESS`, or `MICROPHONE`;
- `AudioSourceDescriptor`: stable ID, kind, display name, availability, and
  optional process metadata;
- `AudioCaptureConfig`: selected descriptor ID and bounded queue duration;
- typed capture failures and a small lifecycle contract; and
- source diagnostics independent from backend-specific exception types.

The Windows layer owns:

- PyAudioWPatch and ProcTap facades;
- device and process discovery;
- full-system, process-tree, and microphone source implementations;
- conversion of backend callbacks into `AudioFrame`; and
- capability probes and Windows-only smoke tests.

Portable modules must remain importable when Windows extras are absent.

## Source lifecycle

An audio source exposes `start()`, bounded `read(timeout)`, `stop()`, and a
diagnostic snapshot. Lifecycle states reuse `SourceState`: `STARTING`,
`RUNNING`, `RECONNECTING`, `FAILED`, and `STOPPED`.

Rules:

1. `start()` begins a new capture session and resets frame sequence and the
   session-relative clock.
2. Exactly one producer callback writes into a bounded queue. Consumers call
   `read()` outside the callback thread.
3. `stop()` is idempotent, closes native handles, unblocks waiting reads, and
   prevents later callbacks from publishing frames.
4. Restarting the same source creates a new session identity. Frames from the
   ended session cannot enter the new session.
5. Backend callbacks never normalize audio, invoke models, update captions, or
   call Qt.

## Buffering and frame semantics

Adapters request native shared-mode PCM and preserve the backend sample rate,
channel count, and dtype in each frame. The existing portable normalizer owns
downmixing, scaling, and resampling to mono 16 kHz.

Capture callbacks produce 20-100 ms chunks when supported. The handoff queue
holds approximately two seconds of audio. When full, the oldest queued frame
is discarded before the newest frame is accepted. Each discard increments a
diagnostic counter; capture threads never block on a slow consumer.

`AudioFrame.sequence` increases monotonically within one capture session.
`captured_at` is the session-relative end time of that frame, derived from a
monotonic clock. The adapter copies backend memory before publishing; the
existing `AudioFrame` constructor then provides a read-only owned array.

## Discovery and selection

Discovery is separate from streaming and returns immutable descriptors.

- Output descriptors use the WASAPI endpoint identity and human-readable
  device name. A synthetic `default-output` descriptor follows the current
  default endpoint.
- Microphone descriptors use stable WASAPI input identities.
- Process descriptors contain PID, executable name, executable path when
  available, and a stable selection key derived from the normalized executable
  path. Processes without accessible paths retain PID-scoped descriptors.
- Discovery failures return typed diagnostics rather than partially valid
  descriptors.

The host stores a selection key, not only a transient PID or device index.

## Full-system and microphone capture

PyAudioWPatch enumerates WASAPI devices and maps an output endpoint to its
loopback analogue. The adapter opens shared-mode input using the device's
native format. Selecting `default-output` resolves the current default at
start and reconnects when the default endpoint changes.

Microphone capture uses an ordinary WASAPI input stream through the same queue
and lifecycle. It remains optional in product UI but is fully testable as an
adapter.

An endpoint removal or format change transitions the source to
`RECONNECTING`. The source retries with bounded backoff while the same stable
selection can be resolved. It never switches to an unrelated device.

## Per-process capture

ProcTap opens process loopback for the selected PID and includes its child
processes. The adapter records the executable selection key when available.

If the process exits, the source enters `RECONNECTING`, closes the old native
stream, and searches for a matching executable. A single match may be opened
as the next instance. Multiple matches remain ambiguous and require a new host
selection; the adapter does not guess. Reconnection keeps the logical capture
selection but starts a new session identity.

Per-process failure never falls back to system loopback. Unsupported Windows
builds, missing wheels, access denial, and native initialization failure are
reported distinctly. Protected-content silence is treated as an external
limitation, not an application crash.

## Silence and health

No PCM can mean that a valid source is currently silent. Silence alone does
not trigger fallback or failure. Diagnostics distinguish:

- stream open and receiving frames;
- stream open but silent;
- source unavailable and reconnecting;
- queue overflow; and
- terminal adapter failure.

A configurable health interval records prolonged silence and exposes it to the
future host, which may offer an explicit source change. This milestone does
not change the selection automatically.

## Error model

Portable typed exceptions cover:

- unsupported platform or missing optional dependency;
- source not found or ambiguous selection;
- source open/format failure;
- interrupted stream;
- invalid lifecycle operation; and
- terminal reconnect exhaustion.

Windows exception details are chained as causes and summarized in diagnostics,
but backend-specific exception classes do not cross the adapter boundary.

## Dependencies

The base project remains portable. A `windows-audio` dependency group contains
pinned compatible ranges for PyAudioWPatch and ProcTap. Lock resolution must
select CPython 3.12 Windows x64 wheels. CI and source-import tests must not
require installing this group on non-Windows platforms.

No optional high-quality ProcTap resampler is installed because normalization
already belongs to the portable SciPy pipeline.

## Testing strategy

Ordinary automated tests inject small backend facades and do not access real
hardware. They cover:

- descriptor mapping and stable selection keys;
- start/stop idempotence and stale-callback rejection;
- frame format, copying, timestamp, and sequence behavior;
- bounded oldest-drop queue behavior and counters;
- device and process reconnect state transitions;
- ambiguity, unsupported platform, missing dependency, and native failures;
- absence of silent per-process-to-system fallback; and
- import boundaries with Windows extras absent.

Windows hardware tests use explicit markers and are excluded from the default
suite. They cover:

- full-system capture of a known generated tone;
- microphone enumeration and an opt-in read smoke test;
- process isolation using two simultaneous tone-producing processes;
- selected-process restart and reattachment;
- default endpoint change where the test environment supports it; and
- wheel-only installation on CPython 3.12 x64.

Hardware tests record only short in-memory PCM fixtures and do not persist user
audio.

## Acceptance criteria

- The portable suite remains green without Windows audio dependencies.
- `uv sync --group windows-audio` installs on CPython 3.12 Windows x64 without
  invoking a compiler.
- Full-system capture yields non-empty immutable frames while normal playback
  remains audible.
- Per-process capture hears the selected process tree and excludes a controlled
  second process.
- Microphone enumeration works and optional capture yields valid frames.
- Restart and endpoint-change paths expose deterministic lifecycle states and
  do not leak native handles or old-session frames.
- A slow consumer causes bounded, counted oldest-frame drops rather than
  unbounded memory growth or callback blocking.
- Per-process errors never silently change the source to full-system capture.
- Windows imports remain outside the portable core boundary.
- Documentation states supported Windows versions, wheel requirements,
  protected-content limitations, and privacy behavior.

## References

- Microsoft Application Loopback sample:
  <https://github.com/microsoft/Windows-classic-samples/tree/main/Samples/ApplicationLoopback>
- Microsoft `AUDIOCLIENT_ACTIVATION_TYPE` documentation:
  <https://learn.microsoft.com/windows/win32/api/audioclientactivationparams/ne-audioclientactivationparams-audioclient_activation_type>
- PyAudioWPatch:
  <https://pypi.org/project/PyAudioWPatch/>
- ProcTap:
  <https://pypi.org/project/proc-tap/>
- GStreamer WASAPI2 source:
  <https://gstreamer.freedesktop.org/documentation/wasapi2/wasapi2src.html>
