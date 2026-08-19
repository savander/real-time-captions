# Portable Core Architecture

## Milestone boundary

This branch delivers a deterministic, portable Python caption-processing core.
It accepts already-captured PCM sample windows, invokes injected backends, and
publishes coherent caption snapshots. It deliberately contains no Windows
device discovery, loopback or microphone capture, machine-learning runtime,
GUI/overlay, child process, IPC, or release packaging integration.

The portable package depends only on NumPy, SciPy, and platform-neutral Python
standard-library facilities. Platform and model adapters belong behind the
backend protocols, outside the core package boundary.

## Contracts

### Value contracts

- `SourceState` describes a future source lifecycle: `starting`, `running`,
  `reconnecting`, `failed`, and `stopped`.
- `TargetLanguage` selects native captions, English, or Polish. `ViewMode`
  selects target-only or bilingual presentation for a future UI.
- `AudioFrame` carries a source `session_id`, PCM samples, source sample rate,
  channel count, monotonically supplied source sequence, and capture time.
- `Word` is immutable text with start and end timestamps. `InferenceRequest`
  identifies one audio window by session and sequence, carries its samples, and
  records its audio end time. `AsrHypothesis` returns that identity, timestamped
  words, detected language and confidence, and audio end time.
- `StabilizedText` divides words into committed and provisional tuples.
  `CaptionSnapshot` is the immutable externally visible source and translation
  state for one session and sequence.
- `TranslationRequest` names the exact session, source sequence, source
  language, target, committed source text, and provisional source text to
  translate. `TranslationResult` returns the same session and sequence plus
  separate committed and provisional translations.

### Extension contracts

- `AudioSource` emits timestamped PCM frames without exposing platform APIs:
  `read()` returns one `AudioFrame` or `None` when no frame is available.
- `AsrBackend` converts one latest-window `InferenceRequest` into an
  `AsrHypothesis` with word timestamps. An implementation must preserve the
  request's session and sequence identities in its result.
- `TranslationBackend` translates the exact source revision in a
  `TranslationRequest` to English or Polish, returning a `TranslationResult`
  with matching session and sequence identities.

Adapters implement these protocols. The core owns neither capture hardware nor
model loading, so replacing an adapter does not require a core change.

## Core components and state ownership

`RealtimeCaptionCore` is the orchestration owner. It owns the rolling audio
window, monotonically increasing request sequence, `LatestWindowScheduler`,
`LanguageSmoother`, `HypothesisStabilizer`, and `CaptionStore`; adapters own
their own runtime state.

- `AudioRingBuffer` stores only the bounded latest mono sample context. Its
  capacity is `sample_rate * context_seconds`; appends normalize to `float32`
  and overwrites old samples.
- `normalize_frame` validates positive integer rates/channels, converts PCM to
  mono `float32`, and resamples to the requested rate (16 kHz by default).
- `LatestWindowScheduler` permits one active inference request and one pending
  request. While busy, a submission replaces the pending request; replacing an
  existing pending request increments `coalesced_count`.
- `LanguageSmoother` confirms a language only after configured high-confidence
  observations, supports a manual lock, and resets a candidate at an utterance
  boundary.
- `HypothesisStabilizer` commits only agreeing words older than its guard time;
  it filters overlap with already committed words and can finalize a remaining
  tail.
- `CaptionStore` owns source and translation text plus the last accepted
  sequence. It emits snapshots and creates a translation request only when a
  non-native target and a source language exist.
- `RuntimeMetrics` owns bounded latency samples and counters, returning p50/p95
  diagnostics, coalesced-window count, and worker-restart count. It is a
  portable measurement utility; no worker exists in this milestone.
- `AppSettings` and `SettingsStore` own the versioned local settings document.
  Settings save through a same-directory temporary file and replacement.
- `real-time-captions core-smoke` constructs deterministic in-process ASR and
  translation adapters and prints one JSON `CaptionSnapshot`. It is a core
  verification command, not a live application mode.

## Data flow and scheduling

1. A future `AudioSource` supplies an `AudioFrame`; its caller uses
   `normalize_frame` and calls `RealtimeCaptionCore.submit_audio(samples,
   audio_end)`.
2. The core appends samples to its bounded ring buffer, assigns the next
   sequence, and submits the full current rolling window to the scheduler.
3. If inference is idle, the core calls `AsrBackend.transcribe`. If it is busy,
   only the newest pending window survives (latest-wins).
4. A matching ASR hypothesis is smoothed for language, stabilized into
   committed/provisional words, and applied to the caption store.
5. For English or Polish targets, the store creates one exact-revision request
   for `TranslationBackend`; a matching result updates both translation
   channels. The returned `CaptionSnapshot` is immutable.

## Session, sequence, and caption invariants

- A core instance represents one supplied `session_id`; its request sequence
  increases for every submitted audio window.
- At most one inference request is active and one latest request is pending.
  Completing a request promotes only that latest pending request.
- The scheduler rejects completion identities that do not match its active
  session and sequence. An ASR result with a mismatched identity cannot mutate
  caption state. A translation result with a mismatched identity is ignored.
- The caption store ignores source updates older than its accepted sequence.
  A newer source revision clears previous translation text before its new
  translation arrives.
- Provisional text may be replaced by later hypotheses. Committed text is
  append-only within a session: stabilization never re-commits overlapping old
  words, and `finalize()` appends the remaining provisional tail then clears it.
- A native target has no translation request or translation text. Snapshots
  always contain source and translation channels for the same accepted source
  revision.

## Failure semantics

- Invalid ring-buffer capacity, invalid audio-frame rates/channels, and invalid
  metric values raise `ValueError`.
- Scheduler completion for no active request or the wrong identity raises
  `ValueError`.
- If ASR or translation raises during `submit_audio`, the core resets active and
  pending scheduler work, preserves the last successfully stored snapshot, and
  re-raises the original exception. A later submission can proceed.
- `SettingsStore.load()` returns default settings plus warnings for missing,
  unreadable, malformed, unsupported, or invalid settings values. `save()`
  validates the profile and propagates write or replacement errors; temporary
  cleanup errors are also surfaced when there was no earlier save error.

## Roadmap

1. **Current: portable core** — deterministic audio-window processing,
   extension contracts, stabilization, caption state, settings, diagnostics,
   and a core smoke command.
2. **Windows audio plan** — implement device selection and loopback/microphone
   adapters behind `AudioSource`.
3. **Model benchmark plan** — implement and evaluate real ASR and translation
   adapters behind `AsrBackend` and `TranslationBackend`.
4. **GUI and overlay plan** — add display controls and an overlay that consumes
   snapshots without taking ownership of core state.
5. **Child-process and release integration plan** — isolate heavyweight runtime
   work, define IPC/lifecycle behavior, and package the Windows application.

The four follow-up plans are intentionally not implemented by this milestone.
