# Real-Time Captions

Windows-first, cross-platform real-time captioning foundation. The repository
contains the deterministic caption core plus working Windows system,
per-process, and microphone capture adapters. Model runtime and GUI/overlay are
the next milestones.

## Implemented

- Bounded PCM window handling and normalization.
- AudioSource, AsrBackend, and TranslationBackend extension protocols.
- Latest-wins ASR scheduling with independent ASR request and source revision
  identities.
- Immediate native provisional text with language confirmation per utterance.
- Unicode-aware word stabilization and append-only committed source.
- Pending committed translation deltas with stable segment identities,
  append-only committed translation, and exact stale-result rejection.
- NumPy message payloads that are copied and exposed read-only.
- Versioned settings at an injected path and portable runtime metrics.
- A deterministic Czech-to-Polish core smoke command.
- Windows WASAPI output, physical loopback, and microphone discovery.
- Selected-process capture with stable executable-path selection across PID
  changes and explicit reconnect without system-audio fallback.
- Bounded callback queues, immutable PCM frames, lifecycle diagnostics, and
  metadata-only JSON discovery/probe commands.

All audio and word timestamps are session-relative seconds. See
[the architecture document](docs/Architecture.md) for the exact clocks,
ownership, finalization, failure, and translation contracts.

## Not implemented yet

Real ASR and translation models are not wired yet. There is no GUI, subtitle
overlay, AI child process, IPC, or release packaging yet.

The approved product uses platformdirs for host-owned per-user paths. This
milestone has no host, so SettingsStore receives an injected path and
platformdirs is intentionally deferred to the host/UI plan.

## Windows quick start

From the repository directory in Windows PowerShell:

~~~powershell
uv sync --group dev --group windows-audio
uv run pytest
uv run real-time-captions core-smoke
uv run real-time-captions audio-list
uv run real-time-captions audio-probe-system --seconds 2
~~~

Windows audio requires Windows 10/11 x64 and CPython 3.12. PyAudioWPatch
installs from a binary wheel. Per-process capture uses the Rust helper source
included in this repository and pinned to flexaudio 0.2.0; build it once:

~~~powershell
cargo build --release --manifest-path native/windows_audio_helper/Cargo.toml
~~~
`audio-list` prints stable source IDs. Use an ID for process or microphone:

~~~powershell
uv run real-time-captions audio-probe-process --source 'process:c:/apps/player.exe' --seconds 2
uv run real-time-captions audio-probe-microphone --source 'wasapi-input:3' --seconds 2
~~~

Probe output contains metrics only and never stores or prints PCM. Protected
or DRM-controlled audio may intentionally produce silence. Process capture
targets the selected audio-owning PID. For a multi-process application, choose
the process that owns its audio session; automatic child-process aggregation is
not part of this milestone.

## Development checks

~~~powershell
uv lock --check
uv sync --group dev --group windows-audio
uv run pytest -m 'not windows_audio' -v --cov=real_time_captions --cov-report=term-missing
uv run pytest tests/test_architecture_boundaries.py -v
uv run real-time-captions core-smoke
git diff --check
~~~

## Roadmap

The portable core and Windows audio capture are complete. Real-model
benchmarks for RTX 3080, GUI/overlay work, and child-process/release integration
follow as separate milestones.

## License

MIT. See [LICENSE](LICENSE).
