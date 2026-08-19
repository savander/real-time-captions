# Real-Time Captions Rewrite Design

**Date:** 2026-08-19  
**Status:** Approved in design discussion; awaiting written-spec review  
**Target release:** Windows-first local desktop application  

## Summary

Rewrite Real-Time Captions from scratch as a local, Windows-first desktop application with a portable core. It captures all system audio or one selected process, produces immediate provisional captions, commits stable captions after repeated agreement, and optionally translates native text into English or Polish. A normal Windows control panel configures an independent always-on-top overlay.

The old implementation is not retained at runtime and no compatibility layer is required. Git history is the recovery mechanism. The package name and command `uv run real-time-captions` remain stable.

## Goals

- Run natively on Windows without WSL, Docker, cloud APIs, or a Linux service.
- Be optimized and benchmarked on an NVIDIA RTX 3080 with 10 GB VRAM.
- Prioritize European languages, with Czech and Polish as mandatory quality gates.
- Detect language changes between utterances during a running session.
- Show provisional text immediately in a distinct color.
- Turn stable text into append-only committed captions that are never retracted.
- Support native-only, translated-only, and native-plus-translation overlay modes.
- Translate at least into English and Polish.
- Capture a complete Windows output device, one selected application/process tree, or an optional microphone.
- Keep capture, streaming policy, ASR, translation, state, and GUI independently replaceable and testable.
- Prevent unbounded queues and latency growth.
- Keep the shared core free of Windows API imports for future Linux and macOS adapters.
- Install and run through `uv`.

## Non-goals for the Windows-first release

- Full behavioral parity and end-to-end testing on Linux or macOS.
- An installer, portable executable, or Microsoft Store package.
- Cloud transcription or translation.
- Speech synthesis, translated audio output, or speaker diarization.
- Silent capture of DRM-protected content.
- Commercial redistribution of non-commercial model weights. The selected NLLB checkpoint is suitable for this personal project but must be replaced or relicensed before commercial use.

## Product behavior

### Control center

The PyQt6 control center owns application configuration and provides:

- Start and Stop controls and an explicit session status.
- Audio source type: full system output, selected application, or microphone.
- Output-device or process selection.
- Source-language mode: automatic or manually locked.
- Target mode: native, English, or Polish.
- Overlay layout: target only or native plus translation.
- Performance profile: Fast, Balanced, Quality, or Custom.
- Overlay visibility, edit mode, and click-through mode.
- Live diagnostics and access to logs.

Closing the control center minimizes it to the notification area and does not stop captions. The tray menu provides Start/Stop, show/hide overlay, edit/click-through, open control center, and Exit.

### Overlay

The overlay is a frameless, transparent, always-on-top PyQt6 window that can be placed over any ordinary desktop application. It supports:

- Target-only and native-plus-translation modes.
- Separate configurable colors for committed source, committed translation, and provisional text.
- Provisional suffixes that can be replaced and committed prefixes that never change.
- Configurable font, alignment, line count, background opacity, position, and size.
- Edit mode and click-through mode.
- Automatic persistence of visual settings and geometry.

Status and errors are shown in the control center, not injected as subtitle text.

## Architecture

```text
Platform Audio Adapter
        |
        v
Normalizer / Resampler -> Bounded Ring Buffer -> Realtime Scheduler
                                                    |
                                                    v
                                          Separate AI Process
                                   ASR -> Language Smoother -> Stabilizer
                                                    |
                                                    v
                                              Translator
                                                    |
                                                    v
                                             Caption State
                                                    |
                                                    v
                                      Control Center + Overlay
```

### Process boundaries

The GUI and orchestration run in the main process. Audio callbacks run on dedicated capture threads and never call model code or Qt widgets. ASR and translation run in one dedicated AI child process so CUDA initialization, model failure, and GPU memory are isolated from the GUI.

The processes exchange typed, versioned messages. Every request and result contains a session identifier and monotonically increasing sequence number. Results from an ended session, superseded source, or old configuration are discarded. The GUI remains usable while models load, download, restart, or fail.

### Core module boundaries

- `AudioSource`: enumerates or captures PCM frames from a platform source.
- `AudioNormalizer`: converts frames to mono, 16 kHz, contiguous `float32` samples.
- `AudioRingBuffer`: stores a bounded rolling window without repeated full-array copies.
- `RealtimeScheduler`: coalesces work and guarantees at most one ASR request in flight.
- `AsrBackend`: returns native words, timestamps, language candidates, and confidence.
- `LanguageSmoother`: selects a stable language per utterance and applies manual locks.
- `HypothesisStabilizer`: separates provisional words from append-only committed words.
- `TranslationBackend`: translates native source text into the selected target language.
- `CaptionStore`: owns committed and provisional source/translation state.
- `SessionController`: coordinates lifecycle, settings changes, recovery, and diagnostics.
- `ControlCenter` and `CaptionOverlay`: render state but do not own recognition logic.

All platform imports remain under adapter packages. All large model imports remain inside backend packages and the AI child process.

## Audio capture

### Windows full-system capture

Use WASAPI loopback through PyAudioWPatch or an equivalent adapter with Windows wheels. The adapter enumerates output endpoints, emits native device-format frames, and reports endpoint removal or format changes.

### Windows per-process capture

Use Windows Process Loopback (`AUDIOCLIENT_ACTIVATION_TYPE_PROCESS_LOOPBACK`) through a replaceable adapter. ProcTap is the initial integration candidate because it yields PCM chunks to Python, but core code depends only on `AudioSource`.

Requirements:

- Windows 10 version 2004 or newer, or Windows 11.
- Capture the selected process and its child process tree.
- Reconnect when an application restarts and a matching executable becomes available.
- Never silently fall back to full-system capture.
- If capture is unsupported or persistently silent, offer an explicit source switch.
- Treat protected-content silence as an external limitation, not an application crash.

### Microphone and future platforms

Microphone capture uses the same frame contract and remains optional. Future Linux adapters may use PipeWire or PulseAudio; macOS adapters may use CoreAudio or ScreenCaptureKit; Apple Silicon may use an MLX ASR backend. These are outside the first release gate and must not change core interfaces.

## Realtime data flow

1. Capture produces 20–100 ms PCM frames.
2. Frames are normalized and appended to a bounded 5–10 second ring buffer.
3. The scheduler requests a hypothesis every 350–1000 ms, according to profile.
4. If inference is busy, intermediate requests are coalesced into the newest complete window.
5. ASR always produces native text, supporting bilingual display without a second ASR pass.
6. Language smoothing chooses one language for the current utterance.
7. The stabilizer compares consecutive timestamped hypotheses and emits committed and provisional regions.
8. Provisional source appears immediately and may be replaced.
9. Provisional translation is debounced and uses latest-wins semantics.
10. When source words commit, the translator produces final target text for that segment.
11. The caption store publishes one coherent snapshot to the GUI.

The rolling context improves accuracy but does not impose a 5–10 second display delay.

## Language detection and stability

Manual language selection overrides automatic detection. In automatic mode:

- Language is evaluated per utterance rather than once per application run.
- A switch requires two consecutive hypotheses supporting the new language.
- A low-confidence short fragment cannot switch language solely due to a name or foreign phrase.
- VAD boundaries reset switch evidence while retaining the last language as a weak prior.
- The UI reports detected language and confidence.

The initial stabilizer follows LocalAgreement-style behavior:

- Align words by timestamp and normalized text across consecutive hypotheses.
- Keep the unstable suffix provisional.
- Commit the common prefix after repeated agreement and a configurable time guard.
- At a VAD endpoint, run one final pass and commit the remaining stable segment.
- Never edit or remove a committed word.

Thresholds belong to profile configuration, not UI constants.

## Translation

Translation is downstream of native ASR so native and translated text can be shown simultaneously. The initial candidate is NLLW backed by `nllb-200-distilled-600M`, using CTranslate2 INT8 or FP16 as determined by benchmark.

Rules:

- Native target bypasses translation.
- English and Polish use the same translation interface.
- Provisional translations may change and inherit provisional styling.
- A committed source segment receives a final translation with the same segment identifier.
- A stale translation cannot overwrite a newer source revision.
- Unsupported pairs show native text and a warning instead of hiding captions.
- Translator licensing is displayed in model metadata and documentation.

## ASR candidates and profiles

The architecture does not declare a winner before local benchmarking.

Candidates:

- NVIDIA Parakeet-TDT-0.6B-v3: European-language efficiency candidate.
- Qwen3-ASR-0.6B: streaming/offline candidate.
- Faster-Whisper large-v3-turbo: established Windows latency baseline.
- Faster-Whisper large-v3: quality and broad-language fallback.

| Profile | Update interval | Context | Intended behavior |
| --- | ---: | ---: | --- |
| Fast | 350–500 ms | 5–6 s | Lowest sustainable latency, quantized smaller backend |
| Balanced | about 500 ms | about 8 s | Default RTX 3080 quality/latency tradeoff |
| Quality | 750–1000 ms | about 10 s | Large model and conservative committing |
| Custom | user-controlled | user-controlled | Explicit backend and streaming parameters |

Hardware selection maps detected hardware to a tested profile and never invents unbenchmarked combinations.

## Benchmark design

Benchmark candidates on the target RTX 3080 using identical audio, scheduler policy, and translation inputs. The corpus includes Czech, Polish, English, German, French, Spanish, Slovak, Ukrainian, and Russian, with clean speech, music, noise, silence, long-form speech, and language changes.

Metrics:

- Native WER and CER.
- Translation COMET and chrF or BLEU where references exist.
- First provisional-caption latency p50 and p95.
- Commit latency p50 and p95.
- Provisional edit rate and committed-text retraction count.
- Real-time factor, peak VRAM/RAM, and coalesced-window count.
- One-hour memory, queue-depth, and latency trend.

Balanced-profile gates:

- First provisional caption p95 below 1.5 seconds.
- Commit latency p95 below 5 seconds.
- Zero committed-caption retractions.
- No CUDA OOM in a one-hour soak test.
- No sustained queue-depth or latency increase.
- Czech and Polish pass explicit quality review; easier languages cannot mask regression.

The Windows default is the Pareto-optimal candidate passing every gate with the best quality inside latency and VRAM limits. Other working backends remain optional.

## Backpressure and consistency

- Audio uses a fixed-capacity ring buffer.
- At most one ASR request is in flight.
- Pending ASR work is one latest snapshot, not a FIFO queue.
- Provisional translation is latest-wins per segment.
- UI updates are immutable snapshots or typed events applied on the Qt thread.
- Every message carries session, source, configuration revision, and sequence identifiers.
- Restarting capture or changing models invalidates old results.

## Failure handling

Sources expose `starting`, `running`, `reconnecting`, `failed`, and `stopped`.

- A closed target process waits for a matching process while reconnecting.
- A removed device yields an actionable error or follows an explicit default-device policy.
- No source switch occurs silently.
- The AI process receives one automatic restart after an unexpected crash.
- On CUDA OOM, Auto or Balanced may retry once with a benchmark-approved safer configuration.
- Repeated model failure stops the session and reports recovery choices.
- AI restart clears provisional work and does not replay stale audio as new captions.
- Configuration writes are atomic and schema-versioned.

## Diagnostics, logs, privacy, and configuration

Diagnostics expose source state; backend, model and compute type; GPU and VRAM; language and confidence; latency p50/p95; real-time factor; coalesced windows; and recovery history.

Logs are structured, size-limited, and rotated. They do not contain raw audio. Audio recording is disabled by default and any future debug recording requires explicit opt-in and a user-selected path.

Use `platformdirs` for per-user paths. Store schema-versioned JSON through atomic replace. Keep recognition settings separate from overlay geometry so corrupt visual preferences cannot prevent model startup. Invalid values fall back individually with a diagnostic warning.

## Dependency and packaging strategy

- Python remains 3.12 unless a selected backend requires a different supported range.
- `uv` is the only documented environment and launch workflow.
- GUI/core dependencies are separate from heavyweight backend groups.
- The default set contains only the selected production backend and translator.
- Benchmark candidates use explicit `uv` groups to avoid unnecessary runtime conflicts.
- Models download from official hubs on first use and use standard cache directories.
- GUI modules never import Torch, Transformers, CTranslate2, or CUDA libraries.

## Testing strategy

### Unit tests

- Ring-buffer boundaries and fixed capacity.
- Resampling and channel normalization contracts.
- Scheduler coalescing and one-in-flight invariant.
- Language-switch hysteresis and manual lock.
- Hypothesis alignment, provisional replacement, and append-only commits.
- Translation revision ordering and session invalidation.
- Configuration validation and atomic recovery.

### Contract and integration tests

Every `AudioSource`, `AsrBackend`, and `TranslationBackend` passes a shared contract with deterministic fixtures. Fakes let core tests run without hardware, network, or GPU.

Integration coverage includes recorded Czech, Polish, and mixed-language audio; AI startup/crash/stale-result rejection; WASAPI system and process capture; process and device restarts; translation transitions; and PyQt6 behavior with `pytest-qt`.

### Performance tests

- Explicit GPU benchmark separate from ordinary tests.
- One-hour soak test for RAM, VRAM, queue, and latency growth.
- Machine-readable profile reports.

Ordinary CI does not download multi-gigabyte models. GPU and hardware tests are explicit markers.

## Rewrite strategy

Implementation occurs on a dedicated Git branch or worktree. The old `src/real_time_captions` implementation is removed, not preserved beside the new system. The rewrite keeps the package name and command but does not promise compatibility with old internal modules, worker protocols, configuration, or CLI flags.

The first implementation task establishes tests and a minimal new entrypoint, then removes the old implementation in the feature branch. Later tasks use test-first development and end in a testable state. Git history preserves the old application for reference or recovery.

README, dependencies, lockfile, and launch helper are rewritten to describe only behavior that exists.

## Acceptance criteria

- `uv sync` and `uv run real-time-captions` launch the control center on supported Windows.
- Full-system and selected-process capture work without rerouting normal audio.
- Czech and Polish pass the benchmark quality gate.
- Automatic language detection changes between utterances.
- Provisional captions use a distinct style and committed captions never retract.
- Native-only, translated-only, and bilingual modes work for English and Polish targets.
- The overlay is movable, resizable, persistent, always-on-top, and click-through.
- Balanced meets RTX 3080 latency, stability, and memory gates.
- Closing the panel leaves the tray session running; Exit shuts down cleanly.
- Unit, contract, integration, GUI, and selected Windows hardware tests pass.
- Documentation states support, licenses, privacy behavior, and capture limitations.

## References

- Microsoft Application Loopback: <https://github.com/microsoft/Windows-classic-samples/tree/main/Samples/ApplicationLoopback>
- WASAPI loopback: <https://learn.microsoft.com/windows/win32/coreaudio/loopback-recording>
- ProcTap: <https://github.com/m96-chan/ProcTap>
- PyAudioWPatch: <https://github.com/s0d3s/PyAudioWPatch>
- WhisperLiveKit: <https://github.com/QuentinFuxa/WhisperLiveKit>
- Faster-Whisper: <https://github.com/SYSTRAN/faster-whisper>
- Parakeet-TDT-0.6B-v3: <https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3>
- Qwen3-ASR: <https://github.com/QwenLM/Qwen3-ASR>
- NLLB-200 distilled 600M: <https://huggingface.co/facebook/nllb-200-distilled-600M>
