# Real-Time Captions Architecture

## Milestone boundary

The platform-neutral core accepts captured PCM sample windows, invokes injected
backends, and publishes immutable caption snapshots. Windows capture lives in
an adapter tree; machine-learning runtime, GUI, child process, IPC, and release
integration remain outside this milestone.

The portable package depends only on NumPy, SciPy, and platform-neutral Python
standard-library facilities. Platform and model adapters belong behind
protocols and outside the core package boundary.

## Clocks and value contracts

Every timestamp uses one clock: session-relative seconds measured from the
start of the current capture session.

- AudioFrame.captured_at locates a captured frame on that clock.
- InferenceRequest.audio_end, AsrHypothesis.audio_end, and every Word.start
  and Word.end use the same coordinate system. A backend whose model returns
  window-relative timestamps must convert them at its adapter boundary.
- AudioFrame and InferenceRequest copy NumPy payloads at construction and
  expose read-only arrays. Producers therefore cannot mutate an already
  identified asynchronous message through a retained source array.
- StabilizedText contains immutable committed and provisional word tuples.
  CaptionSnapshot is one immutable externally visible source revision.

There are two distinct monotonic identities:

| Identity | Owner | Advances when |
| --- | --- | --- |
| ASR request sequence | RealtimeCaptionCore | an audio window is submitted |
| source revision sequence | core and CaptionStore | accepted visible source state changes |

An ignored or mismatched ASR result does not consume a source revision.
Finalization consumes a source revision only if it changes source state.

TranslationRequest.sequence is the source revision, never the ASR request
sequence. TranslationRequest.committed is only the still-untranslated
committed source delta, while provisional is the replaceable current suffix.
committed_segment_id is optional for provisional-only work and stable for a
pending committed unit. TranslationResult must echo the exact session, source
revision, and committed segment identity.

## Extension contracts

- AudioSource.read() returns one AudioFrame or None without exposing a
  platform API.
- AsrBackend.transcribe() converts a latest-window InferenceRequest into an
  AsrHypothesis. It must echo the request session and ASR sequence and return
  session-relative timestamps.
- TranslationBackend.translate() translates an exact source revision to
  English or Polish and echoes its committed segment identity.

Adapters own capture or model runtime state. The core owns no hardware,
download, model-loading, or process lifecycle.

## Windows audio adapters

Windows 10/11 x64 on CPython 3.12 supports three source kinds behind the same
AudioSource contract: system output and microphones through
PyAudioWPatch/WASAPI, and a specific audio-owning process through the
repository's Rust flexaudio/Windows Process Loopback helper. The default-output
alias is resolved again for every session.

Native callbacks copy PCM into a bounded oldest-drop queue and return
immediately. AudioFrame owns a read-only NumPy copy, sequence numbers restart
per session, and captured_at uses the session-relative monotonic clock. Source
lifecycle is STARTING, RUNNING, optionally RECONNECTING, FAILED, then STOPPED.

Process selections prefer a normalized executable path, so they survive PID
changes. PID-only selection is used when Windows denies executable-path access.
An ambiguous restarted executable is reported instead of guessed. A selected
process that disappears enters explicit reconnect and never falls back to
system loopback.

PyAudioWPatch and psutil are optional Windows dependencies loaded lazily. The
process helper is a separately built executable with a raw float32 stdout
boundary. Importing the portable core does not load platform code. Capture
probes run for at most five seconds and emit metadata only; they never persist
or print PCM. Protected content can be silent by design. Microphone probing is
opt-in. Hardware validation guarantees isolation of the selected PID, not
automatic aggregation of audio sessions owned by its child processes.

## State ownership

RealtimeCaptionCore owns:

- the bounded AudioRingBuffer;
- independent ASR request and source revision counters;
- LatestWindowScheduler;
- the current utterance identity and activity flag;
- LanguageSmoother;
- HypothesisStabilizer; and
- CaptionStore.

The scheduler permits one active ASR request and one latest pending request.
Replacing a pending request increments coalesced_count. Reset removes both
active and pending work; no pre-reset request can later be promoted.

The language smoother retains the last confirmed language only as a weak
prior. Each utterance must satisfy the configured confirmations before the
core publishes a language or asks for translation. Native provisional source
text remains immediate while confirmation is pending.

The stabilizer compares normalized text and overlapping session timestamps.
It trims leading and trailing Unicode punctuation for comparison, commits
agreements at or before the inclusive guard cutoff, and never edits already
committed words.

## Caption and translation state

CaptionStore is the single owner of visible caption text.

- apply_source accepts only a strictly newer source revision that changes
  visible source state.
- A candidate committed word sequence must start with the complete accepted
  committed prefix. Retraction or rewording is rejected.
- Accepted committed source and committed translation are append-only.
- A newer source revision preserves accepted committed translation and clears
  provisional translation derived from the older revision.
- Newly committed source is accumulated as one pending translation unit.
  Additional commits may join it, but its segment ID remains stable until an
  exact translation succeeds.
- After success, only the returned committed delta is appended to committed
  translation. The next committed unit receives a new segment ID.
- Translation results are accepted only for the exact session, current source
  revision, and current optional segment identity.

These rules prevent a newly committed source prefix from appearing beside an
old provisional translation and prevent stale work from replacing accepted
state.

## Realtime flow

1. The host supplies normalized samples plus a session-relative audio_end.
2. The core appends them to its bounded ring buffer and assigns an ASR request
   sequence.
3. A matching hypothesis updates the current utterance, language evidence, and
   stabilizer. A mismatched session or ASR sequence is ignored before any of
   those states mutate.
4. The core proposes the next source revision. The store accepts it only when
   visible source state changed and the committed prefix is valid.
5. Native source is returned immediately. Translation is requested only after
   the current utterance language is confirmed.
6. A matching translation updates the replaceable provisional channel and/or
   appends the exact committed delta.

## Finalization and failure semantics

Pristine finalization is a no-op. Finalizing an active utterance commits its
remaining stabilizer tail, creates a source revision only for a real source
change, and advances the utterance identity even when all words had already
committed. Repeating a successful finalization performs no duplicate backend
work.

Translation failure occurs after source state has been applied. The new native
source remains visible, stale provisional translation is already cleared, and
the pending committed segment remains retryable with its original ID. A later
processing step or repeated finalize after that failure retries the exact
pending unit. Once it succeeds, further finalize calls are no-ops.

An ASR failure happens before source mutation. ASR or translation exceptions
reset scheduler work, preserve the last accepted caption state, and are
re-raised. Stale session, ASR sequence, source revision, or segment results
cannot mutate state.

## Settings, diagnostics, and host paths

RuntimeMetrics owns bounded first-caption and commit latency samples plus
coalesced-window and worker-restart counters. DiagnosticsSnapshot exposes
first_caption_p50, first_caption_p95, commit_p50, commit_p95,
coalesced_windows, and worker_restarts.

AppSettings contains target, view_mode, profile, and locked_language.
SettingsStore accepts an injected path and persists schema-versioned JSON
through same-directory temporary replacement. A
missing settings file returns defaults without warnings; invalid values recover
individually with warnings.

The approved product design assigns per-user path discovery to the future
host/UI through platformdirs. This portable milestone has no host and
therefore injects a path and intentionally does not depend on platformdirs.
The host/UI plan must add that dependency and resolve the per-user settings
path before constructing SettingsStore.

## Roadmap

1. **Complete: portable core** - deterministic state, protocols, settings,
   diagnostics, and core smoke command.
2. **Complete: Windows audio** - device, loopback, process, and microphone
   adapters.
3. **Next: model benchmarks** - real ASR and translation adapters and RTX 3080
   profile evidence.
4. **GUI and overlay** - host-owned paths, controls, tray, and caption view.
5. **Child-process and release integration** - IPC, lifecycle, soak tests, and
   packaging.
