# Real-Time Captions — Portable Core

This branch is a portable-core milestone for real-time captions. It provides a
deterministic Python pipeline for rolling audio windows, ASR and translation
adapter contracts, caption stabilization, state snapshots, settings, and
diagnostics. It is not yet the finished Windows application.

## Implemented today

- Bounded PCM window handling and normalization utilities.
- `AudioSource`, `AsrBackend`, and `TranslationBackend` extension contracts.
- Latest-wins inference scheduling, language smoothing, word stabilization,
  committed/provisional caption state, and exact-revision translation channels.
- Versioned local settings and portable runtime metrics.
- A deterministic end-to-end core smoke command using in-process test adapters.

Read [the architecture document](docs/Architecture.md) for ownership,
invariants, failure behavior, extension boundaries, and the follow-up roadmap.

## Not implemented today

Hardware capture is unsupported: there is no Windows loopback or microphone
capture adapter, device picker, or live audio command. Real ASR and translation
models are unsupported: this milestone does not install or run model runtimes.
There is no GUI, subtitle overlay, AI child process, IPC, release packaging, or
integrated desktop application.

## Windows quick start

In Windows PowerShell, from the repository directory:

```powershell
uv sync --group dev
uv run pytest
uv run real-time-captions core-smoke
```

The smoke command exits with code 0 and prints deterministic JSON for one
caption snapshot. It is the stable verification command for this milestone;
it does not capture audio or load a model.

## Development checks

```powershell
uv run pytest -v --cov=real_time_captions --cov-report=term-missing
uv run pytest tests/test_architecture_boundaries.py -v
git diff --check
```

## Roadmap

The portable core is followed by Windows audio capture, real-model benchmarks,
GUI/overlay work, and child-process/release integration. Those are separate
follow-up plans, not capabilities of this branch.

## License

MIT. See [LICENSE](LICENSE).
