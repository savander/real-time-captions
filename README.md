# Real-Time Captions - Portable Core

This branch is the portable-core milestone for real-time captions. It provides
a deterministic Python pipeline for rolling audio windows, ASR and translation
adapter contracts, append-only caption state, settings, and diagnostics. It is
not yet the finished Windows application.

## Implemented today

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

All audio and word timestamps are session-relative seconds. See
[the architecture document](docs/Architecture.md) for the exact clocks,
ownership, finalization, failure, and translation contracts.

## Not implemented today

Hardware capture is unsupported: there is no Windows loopback, per-process, or
microphone adapter. Real ASR and translation models are unsupported. There is
no GUI, subtitle overlay, AI child process, IPC, or release packaging.

The approved product uses platformdirs for host-owned per-user paths. This
milestone has no host, so SettingsStore receives an injected path and
platformdirs is intentionally deferred to the host/UI plan.

## Windows quick start

From the repository directory in Windows PowerShell:

~~~powershell
uv sync --group dev
uv run pytest
uv run real-time-captions core-smoke
~~~

The smoke command exits with code 0 and prints deterministic JSON for one
Czech-to-Polish CaptionSnapshot. It does not capture audio or load a model.

## Development checks

~~~powershell
uv lock --check
uv sync --group dev
uv run pytest -v --cov=real_time_captions --cov-report=term-missing
uv run pytest tests/test_architecture_boundaries.py -v
uv run real-time-captions core-smoke
git diff --check
~~~

## Roadmap

The portable core is followed by Windows audio capture, real-model benchmarks,
GUI/overlay work, and child-process/release integration. Those are separate
plans rather than capabilities of this branch.

## License

MIT. See [LICENSE](LICENSE).
