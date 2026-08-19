# Portable Realtime Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the legacy implementation with a tested, platform-neutral realtime caption core that runs end-to-end with deterministic fake audio, ASR, and translation adapters.

**Architecture:** Immutable domain messages cross module and future process boundaries. Audio is normalized into a bounded ring buffer, a latest-wins scheduler prevents backlog, and language/stability/translation components publish coherent caption snapshots. Hardware audio, real models, and PyQt views remain outside this first plan and consume the interfaces produced here.

**Tech Stack:** Python 3.12, NumPy, SciPy, dataclasses, typing protocols, platformdirs, pytest, pytest-cov, uv

**Spec:** `docs/superpowers/specs/2026-08-19-realtime-captions-rewrite-design.md`

## Global Constraints

- Windows is the reference platform, but no module created by this plan may import a Windows API.
- Run without WSL, Docker, cloud APIs, or network access.
- Keep the package name `real_time_captions` and command `uv run real-time-captions`.
- Use native ASR text as the source for optional English or Polish translation.
- Provisional text may change; committed text is append-only.
- Keep audio memory bounded and allow at most one inference request in flight.
- Every asynchronous-domain message carries `session_id` and `sequence`.
- Python remains `>=3.12,<3.13`.
- Use `uv` for dependency management and command execution.
- Write every behavior test first and observe the expected failure before production code.
- Do not retain a parallel legacy runtime or compatibility shim.

## Follow-up Plans

1. Windows WASAPI and per-process audio adapters.
2. ASR/translation adapters and RTX 3080 benchmark harness.
3. PyQt6 control center, tray, and overlay.
4. AI child process, Windows integration, soak tests, and release documentation.

---

### Task 1: Reset the package and define immutable contracts

**Files:**
- Delete: `src/real_time_captions/args.py`
- Delete: `src/real_time_captions/bootstrap.py`
- Delete: `src/real_time_captions/capture.py`
- Delete: `src/real_time_captions/hardware_utils.py`
- Delete: `src/real_time_captions/logging_config.py`
- Delete: `src/real_time_captions/transcriber.py`
- Delete: `src/real_time_captions/worker.py`
- Delete: `src/real_time_captions/writer.py`
- Delete: `src/real_time_captions/gui/`
- Modify: `src/real_time_captions/__init__.py`
- Modify: `src/real_time_captions/__main__.py`
- Create: `src/real_time_captions/contracts.py`
- Create: `src/real_time_captions/cli.py`
- Modify: `pyproject.toml`
- Modify: `.gitignore`
- Create: `tests/test_contracts.py`
- Create: `tests/test_cli.py`

**Interfaces:**
- Consumes: no new interfaces.
- Produces: `Word`, `AsrHypothesis`, `InferenceRequest`, `StabilizedText`, `CaptionSnapshot`, `SourceState`, `TargetLanguage`, `ViewMode`, and `main(argv: Sequence[str] | None = None) -> int`.

- [ ] **Step 1: Write failing contract and entrypoint tests**

```python
# tests/test_contracts.py
from dataclasses import FrozenInstanceError

import pytest

from real_time_captions.contracts import AsrHypothesis, Word


def test_asr_hypothesis_is_immutable_and_keeps_sequence_identity() -> None:
    word = Word(text="Ahoj", start=0.0, end=0.4)
    hypothesis = AsrHypothesis(
        session_id="session-1",
        sequence=7,
        words=(word,),
        language="cs",
        language_confidence=0.92,
        audio_end=0.5,
    )

    assert hypothesis.words == (word,)
    with pytest.raises(FrozenInstanceError):
        hypothesis.sequence = 8  # type: ignore[misc]
```

```python
# tests/test_cli.py
from real_time_captions.cli import main


def test_main_returns_success_for_core_smoke_command(capsys) -> None:
    assert main(["core-smoke"]) == 0
    assert capsys.readouterr().out.strip() == "portable core ready"
```

- [ ] **Step 2: Run the new tests and verify the new contracts are missing**

Run: `uv run pytest tests/test_contracts.py tests/test_cli.py -v`

Expected: collection fails because `real_time_captions.contracts` and the new `cli.main` do not exist.

- [ ] **Step 3: Add the minimal immutable contracts and CLI**

```python
# src/real_time_captions/contracts.py
from dataclasses import dataclass
from enum import StrEnum


class SourceState(StrEnum):
    STARTING = "starting"
    RUNNING = "running"
    RECONNECTING = "reconnecting"
    FAILED = "failed"
    STOPPED = "stopped"


class TargetLanguage(StrEnum):
    NATIVE = "native"
    ENGLISH = "en"
    POLISH = "pl"


class ViewMode(StrEnum):
    TARGET_ONLY = "target_only"
    BILINGUAL = "bilingual"


@dataclass(frozen=True, slots=True)
class Word:
    text: str
    start: float
    end: float


@dataclass(frozen=True, slots=True)
class InferenceRequest:
    session_id: str
    sequence: int
    samples: object
    audio_end: float


@dataclass(frozen=True, slots=True)
class AsrHypothesis:
    session_id: str
    sequence: int
    words: tuple[Word, ...]
    language: str
    language_confidence: float
    audio_end: float


@dataclass(frozen=True, slots=True)
class StabilizedText:
    committed: tuple[Word, ...]
    provisional: tuple[Word, ...]


@dataclass(frozen=True, slots=True)
class CaptionSnapshot:
    session_id: str
    sequence: int
    language: str | None
    source_committed: str
    source_provisional: str
    translation_committed: str
    translation_provisional: str
```

```python
# src/real_time_captions/cli.py
import sys
from collections.abc import Sequence


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args == ["core-smoke"]:
        print("portable core ready")
        return 0
    return 0
```

Export `main` from `__init__.py`; make `__main__.py` call it. Add `pytest>=8.3` and `pytest-cov>=6.0` to a `dev` dependency group. Add `.superpowers/` to `.gitignore`. Remove the listed legacy modules only after the new imports succeed.

- [ ] **Step 4: Run the focused and package smoke tests**

Run: `uv run pytest tests/test_contracts.py tests/test_cli.py -v`

Expected: both tests pass.

Run: `uv run real-time-captions core-smoke`

Expected: exit code 0 and `portable core ready`.

- [ ] **Step 5: Commit the clean package boundary**

```bash
git add .gitignore pyproject.toml uv.lock src/real_time_captions tests/test_contracts.py tests/test_cli.py
git commit -m "refactor: reset caption package core"
```

---

### Task 2: Normalize PCM and store it in a bounded ring buffer

**Files:**
- Create: `src/real_time_captions/audio/__init__.py`
- Create: `src/real_time_captions/audio/frame.py`
- Create: `src/real_time_captions/audio/normalize.py`
- Create: `src/real_time_captions/audio/ring_buffer.py`
- Create: `tests/audio/test_normalize.py`
- Create: `tests/audio/test_ring_buffer.py`

**Interfaces:**
- Consumes: immutable sequence identity from `contracts.py`.
- Produces: `AudioFrame`, `normalize_frame(frame, target_rate=16000) -> np.ndarray`, and `AudioRingBuffer.append/latest/size`.

- [ ] **Step 1: Write failing normalization and capacity tests**

```python
# tests/audio/test_normalize.py
import numpy as np

from real_time_captions.audio.frame import AudioFrame
from real_time_captions.audio.normalize import normalize_frame


def test_normalize_frame_downmixes_stereo_float32() -> None:
    frame = AudioFrame(
        samples=np.array([[1.0, -1.0], [0.5, 0.5]], dtype=np.float32),
        sample_rate=16_000,
        channels=2,
        sequence=1,
        captured_at=1.0,
    )

    result = normalize_frame(frame)

    np.testing.assert_allclose(result, np.array([0.0, 0.5], dtype=np.float32))
    assert result.flags.c_contiguous
```

```python
# tests/audio/test_ring_buffer.py
import numpy as np

from real_time_captions.audio.ring_buffer import AudioRingBuffer


def test_ring_buffer_discards_oldest_samples_at_capacity() -> None:
    buffer = AudioRingBuffer(capacity_samples=5)
    buffer.append(np.array([1, 2, 3], dtype=np.float32))
    buffer.append(np.array([4, 5, 6, 7], dtype=np.float32))

    np.testing.assert_array_equal(
        buffer.latest(5), np.array([3, 4, 5, 6, 7], dtype=np.float32)
    )
    assert buffer.size == 5
```

- [ ] **Step 2: Verify both modules are absent**

Run: `uv run pytest tests/audio/test_normalize.py tests/audio/test_ring_buffer.py -v`

Expected: collection fails for missing audio modules.

- [ ] **Step 3: Implement the frame, normalizer, and preallocated ring buffer**

```python
# src/real_time_captions/audio/frame.py
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class AudioFrame:
    samples: np.ndarray
    sample_rate: int
    channels: int
    sequence: int
    captured_at: float
```

Add `scipy>=1.14` to the runtime dependencies. `normalize_frame` validates finite positive rates/channels, converts integer PCM to normalized float32, reshapes interleaved samples, averages channels, and uses `scipy.signal.resample_poly` only when the source rate differs. `AudioRingBuffer` preallocates one float32 array, writes with wraparound, and returns copies from `latest(count)` so callers cannot mutate internal state.

```python
# src/real_time_captions/audio/normalize.py
import math
import numpy as np
from scipy.signal import resample_poly

from .frame import AudioFrame


def normalize_frame(frame: AudioFrame, target_rate: int = 16_000) -> np.ndarray:
    if frame.sample_rate <= 0 or frame.channels <= 0 or target_rate <= 0:
        raise ValueError('sample rates and channels must be positive')
    samples = np.asarray(frame.samples)
    if np.issubdtype(samples.dtype, np.integer):
        limit = float(np.iinfo(samples.dtype).max)
        samples = samples.astype(np.float32) / limit
    else:
        samples = samples.astype(np.float32, copy=False)
    samples = samples.reshape(-1, frame.channels).mean(axis=1)
    if frame.sample_rate != target_rate:
        divisor = math.gcd(frame.sample_rate, target_rate)
        samples = resample_poly(
            samples, target_rate // divisor, frame.sample_rate // divisor
        ).astype(np.float32)
    return np.ascontiguousarray(samples)
```

```python
# src/real_time_captions/audio/ring_buffer.py
import numpy as np


class AudioRingBuffer:
    def __init__(self, capacity_samples: int) -> None:
        if capacity_samples <= 0:
            raise ValueError('capacity_samples must be positive')
        self._data = np.zeros(capacity_samples, dtype=np.float32)
        self._write = 0
        self._size = 0

    @property
    def size(self) -> int:
        return self._size

    def append(self, samples: np.ndarray) -> None:
        values = np.asarray(samples, dtype=np.float32).reshape(-1)
        if len(values) >= len(self._data):
            values = values[-len(self._data):]
        first = min(len(values), len(self._data) - self._write)
        self._data[self._write:self._write + first] = values[:first]
        rest = len(values) - first
        self._data[:rest] = values[first:]
        self._write = (self._write + len(values)) % len(self._data)
        self._size = min(len(self._data), self._size + len(values))

    def latest(self, count: int) -> np.ndarray:
        count = min(max(count, 0), self._size)
        start = (self._write - count) % len(self._data)
        if start + count <= len(self._data):
            return self._data[start:start + count].copy()
        split = len(self._data) - start
        return np.concatenate((self._data[start:], self._data[:count - split]))
```

- [ ] **Step 4: Run focused tests plus coverage for audio code**

Run: `uv run pytest tests/audio -v --cov=real_time_captions.audio --cov-report=term-missing`

Expected: all audio tests pass; add focused tests for invalid rates, int16 scaling, resampling length, empty reads, oversize appends, and wraparound until branch coverage is at least 90%.

- [ ] **Step 5: Commit bounded audio primitives**

```bash
git add src/real_time_captions/audio tests/audio pyproject.toml uv.lock
git commit -m "feat(audio): add bounded PCM pipeline"
```

---

### Task 3: Coalesce inference requests with latest-wins backpressure

**Files:**
- Create: `src/real_time_captions/streaming/__init__.py`
- Create: `src/real_time_captions/streaming/scheduler.py`
- Create: `tests/streaming/test_scheduler.py`

**Interfaces:**
- Consumes: `InferenceRequest`.
- Produces: `LatestWindowScheduler.submit(request) -> InferenceRequest | None`, `complete(session_id, sequence) -> InferenceRequest | None`, `in_flight`, and `coalesced_count`.

- [ ] **Step 1: Write the failing one-in-flight/latest-pending test**

```python
import numpy as np

from real_time_captions.contracts import InferenceRequest
from real_time_captions.streaming.scheduler import LatestWindowScheduler


def request(sequence: int) -> InferenceRequest:
    return InferenceRequest("s1", sequence, np.array([sequence]), float(sequence))


def test_scheduler_keeps_only_latest_request_while_busy() -> None:
    scheduler = LatestWindowScheduler()

    first = scheduler.submit(request(1))
    assert first is not None and first.sequence == 1
    assert scheduler.submit(request(2)) is None
    assert scheduler.submit(request(3)) is None

    promoted = scheduler.complete("s1", 1)
    assert promoted is not None and promoted.sequence == 3
    assert scheduler.coalesced_count == 1
```

- [ ] **Step 2: Verify scheduler import fails**

Run: `uv run pytest tests/streaming/test_scheduler.py -v`

Expected: collection fails because `LatestWindowScheduler` is missing.

- [ ] **Step 3: Implement the minimal state machine**

Store one active `(session_id, sequence)` and one pending request. Replacing an existing pending request increments `coalesced_count`. `complete` rejects mismatched active identity with `ValueError`; a valid completion promotes and returns the latest pending request.

```python
from real_time_captions.contracts import InferenceRequest


class LatestWindowScheduler:
    def __init__(self) -> None:
        self._active: InferenceRequest | None = None
        self._pending: InferenceRequest | None = None
        self.coalesced_count = 0

    @property
    def in_flight(self) -> bool:
        return self._active is not None

    def submit(self, request: InferenceRequest) -> InferenceRequest | None:
        if self._active is None:
            self._active = request
            return request
        if self._pending is not None:
            self.coalesced_count += 1
        self._pending = request
        return None

    def complete(self, session_id: str, sequence: int) -> InferenceRequest | None:
        if self._active is None or (
            self._active.session_id, self._active.sequence
        ) != (session_id, sequence):
            raise ValueError('completion does not match active request')
        promoted = self._pending
        self._active = promoted
        self._pending = None
        return promoted

    def reset(self) -> None:
        self._active = None
        self._pending = None
```

- [ ] **Step 4: Exercise completion, stale identity, and session reset**

Run: `uv run pytest tests/streaming/test_scheduler.py -v`

Expected: tests pass for immediate dispatch, latest replacement, mismatched completion, and `reset()` clearing pending work.

- [ ] **Step 5: Commit the scheduler**

```bash
git add src/real_time_captions/streaming tests/streaming/test_scheduler.py
git commit -m "feat(streaming): coalesce inference windows"
```

---

### Task 4: Smooth language changes per utterance

**Files:**
- Create: `src/real_time_captions/streaming/language.py`
- Create: `tests/streaming/test_language.py`

**Interfaces:**
- Consumes: ASR language code/confidence and utterance identifiers.
- Produces: `LanguageSmoother.observe(language, confidence, utterance_id) -> str | None`, `lock(language)`, `unlock()`, and `current`.

- [ ] **Step 1: Write failing hysteresis and lock tests**

```python
from real_time_captions.streaming.language import LanguageSmoother


def test_language_switch_requires_two_confident_observations() -> None:
    smoother = LanguageSmoother(confirmations=2, minimum_confidence=0.60)

    assert smoother.observe("cs", 0.91, "u1") is None
    assert smoother.observe("cs", 0.92, "u1") == "cs"
    assert smoother.observe("pl", 0.95, "u2") == "cs"
    assert smoother.observe("pl", 0.96, "u2") == "pl"


def test_manual_lock_ignores_automatic_observations() -> None:
    smoother = LanguageSmoother(confirmations=2, minimum_confidence=0.60)
    smoother.lock("cs")

    assert smoother.observe("en", 1.0, "u1") == "cs"
```

- [ ] **Step 2: Verify the language smoother is missing**

Run: `uv run pytest tests/streaming/test_language.py -v`

Expected: collection fails for missing `LanguageSmoother`.

- [ ] **Step 3: Implement confidence filtering and candidate counts**

Track `current`, candidate language, candidate count, utterance identifier, and optional lock. Ignore observations below `minimum_confidence`. A new utterance clears candidate evidence but retains `current` as a prior. Two qualifying observations select or change the language.

```python
class LanguageSmoother:
    def __init__(self, confirmations: int, minimum_confidence: float) -> None:
        self.confirmations = confirmations
        self.minimum_confidence = minimum_confidence
        self.current: str | None = None
        self._candidate: str | None = None
        self._count = 0
        self._utterance: str | None = None
        self._locked: str | None = None

    def observe(self, language: str, confidence: float, utterance_id: str) -> str | None:
        if self._locked is not None:
            return self._locked
        if utterance_id != self._utterance:
            self._utterance = utterance_id
            self._candidate = None
            self._count = 0
        if confidence < self.minimum_confidence:
            return self.current
        if language != self._candidate:
            self._candidate, self._count = language, 1
        else:
            self._count += 1
        if self._count >= self.confirmations:
            self.current = language
        return self.current

    def lock(self, language: str) -> None:
        self._locked = language
        self.current = language

    def unlock(self) -> None:
        self._locked = None
```

- [ ] **Step 4: Run all language transition cases**

Run: `uv run pytest tests/streaming/test_language.py -v`

Expected: tests pass for initial selection, mid-session switch, low confidence, short conflicting evidence, new utterance, lock, and unlock.

- [ ] **Step 5: Commit language smoothing**

```bash
git add src/real_time_captions/streaming/language.py tests/streaming/test_language.py
git commit -m "feat(streaming): smooth language switches"
```

---

### Task 5: Stabilize provisional words into append-only captions

**Files:**
- Create: `src/real_time_captions/streaming/stabilizer.py`
- Create: `tests/streaming/test_stabilizer.py`

**Interfaces:**
- Consumes: `tuple[Word, ...]` plus `audio_end`.
- Produces: `HypothesisStabilizer.update(words, audio_end) -> StabilizedText`, `finalize(words) -> StabilizedText`, and `reset()`.

- [ ] **Step 1: Write failing provisional/commit tests**

```python
from real_time_captions.contracts import Word
from real_time_captions.streaming.stabilizer import HypothesisStabilizer


def words(*values: tuple[str, float, float]) -> tuple[Word, ...]:
    return tuple(Word(text, start, end) for text, start, end in values)


def test_repeated_old_prefix_commits_and_tail_stays_provisional() -> None:
    stabilizer = HypothesisStabilizer(required_agreements=2, guard_seconds=0.8)
    first = words(("Dobrý", 0.0, 0.4), ("den", 0.4, 0.8), ("dnes", 0.9, 1.2))
    second = words(("Dobrý", 0.0, 0.4), ("den", 0.4, 0.8), ("dneska", 0.9, 1.3))

    assert stabilizer.update(first, audio_end=1.5).committed == ()
    result = stabilizer.update(second, audio_end=1.7)

    assert [word.text for word in result.committed] == ["Dobrý", "den"]
    assert [word.text for word in result.provisional] == ["dneska"]
```

- [ ] **Step 2: Verify the stabilizer is absent**

Run: `uv run pytest tests/streaming/test_stabilizer.py -v`

Expected: collection fails for missing `HypothesisStabilizer`.

- [ ] **Step 3: Implement timestamp-aware LocalAgreement behavior**

Normalize words with Unicode casefold and surrounding punctuation trimming for comparison while preserving original display text. Align the uncommitted previous/current hypotheses by timestamp overlap and normalized text. Commit only the common prefix whose words end before `audio_end - guard_seconds`; keep the current remainder provisional. Never modify `_committed`.

```python
import unicodedata

from real_time_captions.contracts import StabilizedText, Word


def _key(word: Word) -> str:
    return unicodedata.normalize('NFKC', word.text).casefold().strip('.,!?;:')


class HypothesisStabilizer:
    def __init__(self, required_agreements: int, guard_seconds: float) -> None:
        self.required_agreements = required_agreements
        self.guard_seconds = guard_seconds
        self._committed: tuple[Word, ...] = ()
        self._previous: tuple[Word, ...] = ()
        self._counts: tuple[int, ...] = ()
        self._last_committed_end = -1.0

    def update(self, words: tuple[Word, ...], audio_end: float) -> StabilizedText:
        current = tuple(w for w in words if w.end > self._last_committed_end)
        common = 0
        for previous, candidate in zip(self._previous, current, strict=False):
            overlaps = min(previous.end, candidate.end) >= max(previous.start, candidate.start)
            if not overlaps or _key(previous) != _key(candidate):
                break
            common += 1
        counts = tuple(
            self._counts[index] + 1 if index < common else 1
            for index in range(len(current))
        )
        commit_count = 0
        cutoff = audio_end - self.guard_seconds
        for word, count in zip(current, counts, strict=False):
            if count < self.required_agreements or word.end > cutoff:
                break
            commit_count += 1
        self._committed += current[:commit_count]
        if commit_count:
            self._last_committed_end = self._committed[-1].end
        self._previous = current[commit_count:]
        self._counts = counts[commit_count:]
        return StabilizedText(self._committed, self._previous)

    def finalize(self, words: tuple[Word, ...]) -> StabilizedText:
        tail = tuple(w for w in words if w.end > self._last_committed_end)
        self._committed += tail
        self._previous = ()
        self._counts = ()
        return StabilizedText(self._committed, ())

    def reset(self) -> None:
        self.__init__(self.required_agreements, self.guard_seconds)
```

- [ ] **Step 4: Prove corrections and finalization do not retract text**

Run: `uv run pytest tests/streaming/test_stabilizer.py -v`

Expected: tests pass for changing tails, punctuation, repeated words, timestamp drift, guard time, explicit finalization, reset, and the invariant that each committed output starts with the previous committed output.

- [ ] **Step 5: Commit the stability engine**

```bash
git add src/real_time_captions/streaming/stabilizer.py tests/streaming/test_stabilizer.py
git commit -m "feat(streaming): stabilize caption hypotheses"
```

---

### Task 6: Coordinate caption state and revision-safe translation

**Files:**
- Create: `src/real_time_captions/captions/__init__.py`
- Create: `src/real_time_captions/captions/store.py`
- Create: `src/real_time_captions/captions/translation.py`
- Create: `tests/captions/test_store.py`
- Create: `tests/captions/test_translation.py`

**Interfaces:**
- Consumes: `StabilizedText`, `TargetLanguage`, session/sequence identity.
- Produces: `TranslationBackend` protocol, `TranslationRequest`, `TranslationResult`, and `CaptionStore.apply_source/apply_translation/snapshot/translation_request`.

- [ ] **Step 1: Write failing stale-translation and native-bypass tests**

```python
from real_time_captions.captions.store import CaptionStore
from real_time_captions.captions.translation import TranslationResult
from real_time_captions.contracts import TargetLanguage, Word


def test_stale_translation_cannot_replace_newer_revision() -> None:
    store = CaptionStore(session_id="s1", target=TargetLanguage.POLISH)
    store.apply_source(2, "cs", (Word("Ahoj", 0.0, 0.4),), ())

    accepted = store.apply_translation(
        TranslationResult("s1", 1, committed="Cześć", provisional="")
    )

    assert accepted is False
    assert store.snapshot().translation_committed == ""


def test_native_target_never_requests_translation() -> None:
    store = CaptionStore(session_id="s1", target=TargetLanguage.NATIVE)
    store.apply_source(1, "cs", (), (Word("Ahoj", 0.0, 0.4),))

    assert store.translation_request() is None
```

- [ ] **Step 2: Verify caption modules are absent**

Run: `uv run pytest tests/captions -v`

Expected: collection fails because caption store and translation contracts do not exist.

- [ ] **Step 3: Implement a single-owner caption store**

`CaptionStore` owns the latest source sequence, language, committed/provisional words, and matching translation. Applying newer source clears only translation fields derived from an older sequence. `translation_request()` returns native text, language, target, session, and sequence. Translation results are accepted only on exact session/sequence identity.

```python
# src/real_time_captions/captions/translation.py
from dataclasses import dataclass
from typing import Protocol

from real_time_captions.contracts import TargetLanguage


@dataclass(frozen=True, slots=True)
class TranslationRequest:
    session_id: str
    sequence: int
    source_language: str
    target: TargetLanguage
    committed: str
    provisional: str


@dataclass(frozen=True, slots=True)
class TranslationResult:
    session_id: str
    sequence: int
    committed: str
    provisional: str


class TranslationBackend(Protocol):
    def translate(self, request: TranslationRequest) -> TranslationResult: ...
```

```python
# src/real_time_captions/captions/store.py
from real_time_captions.captions.translation import TranslationRequest, TranslationResult
from real_time_captions.contracts import CaptionSnapshot, TargetLanguage, Word


def _text(words: tuple[Word, ...]) -> str:
    return ' '.join(word.text for word in words).strip()


class CaptionStore:
    def __init__(self, session_id: str, target: TargetLanguage) -> None:
        self.session_id = session_id
        self.target = target
        self.sequence = -1
        self.language: str | None = None
        self.source_committed = ''
        self.source_provisional = ''
        self.translation_committed = ''
        self.translation_provisional = ''

    def apply_source(
        self,
        sequence: int,
        language: str,
        committed: tuple[Word, ...],
        provisional: tuple[Word, ...],
    ) -> None:
        if sequence < self.sequence:
            return
        if sequence != self.sequence:
            self.translation_committed = ''
            self.translation_provisional = ''
        self.sequence = sequence
        self.language = language
        self.source_committed = _text(committed)
        self.source_provisional = _text(provisional)

    def translation_request(self) -> TranslationRequest | None:
        if self.target is TargetLanguage.NATIVE or self.language is None:
            return None
        return TranslationRequest(
            self.session_id,
            self.sequence,
            self.language,
            self.target,
            self.source_committed,
            self.source_provisional,
        )

    def apply_translation(self, result: TranslationResult) -> bool:
        if (result.session_id, result.sequence) != (self.session_id, self.sequence):
            return False
        self.translation_committed = result.committed
        self.translation_provisional = result.provisional
        return True

    def snapshot(self) -> CaptionSnapshot:
        return CaptionSnapshot(
            self.session_id,
            self.sequence,
            self.language,
            self.source_committed,
            self.source_provisional,
            self.translation_committed,
            self.translation_provisional,
        )
```

- [ ] **Step 4: Test bilingual snapshots and latest-wins revisions**

Run: `uv run pytest tests/captions -v`

Expected: tests pass for provisional replacement, committed accumulation, native bypass, English/Polish requests, stale rejection, unsupported-result errors, and coherent immutable snapshots.

- [ ] **Step 5: Commit caption and translation state**

```bash
git add src/real_time_captions/captions tests/captions
git commit -m "feat(captions): coordinate revision-safe text"
```

---

### Task 7: Run the portable core end-to-end with fake adapters

**Files:**
- Create: `src/real_time_captions/backends/__init__.py`
- Create: `src/real_time_captions/backends/protocols.py`
- Create: `src/real_time_captions/core.py`
- Create: `tests/fakes.py`
- Create: `tests/integration/test_core_pipeline.py`
- Modify: `src/real_time_captions/cli.py`

**Interfaces:**
- Consumes: all prior contracts and components.
- Produces: `AsrBackend.transcribe(request) -> AsrHypothesis`, `TranslationBackend.translate(request) -> TranslationResult`, and `RealtimeCaptionCore.submit_audio/finalize/snapshot`.

- [ ] **Step 1: Write a failing Czech-to-Polish pipeline test**

```python
import numpy as np

from real_time_captions.contracts import TargetLanguage, Word
from real_time_captions.core import RealtimeCaptionCore
from tests.fakes import FakeAsrBackend, FakeTranslationBackend


def test_core_emits_provisional_then_committed_bilingual_caption() -> None:
    asr = FakeAsrBackend(
        hypotheses=[
            ("cs", (Word("Dobrý", 0.0, 0.4), Word("den", 0.4, 0.8))),
            ("cs", (Word("Dobrý", 0.0, 0.4), Word("den", 0.4, 0.8))),
        ]
    )
    translator = FakeTranslationBackend({"Dobrý den": "Dzień dobry"})
    core = RealtimeCaptionCore(
        session_id="s1",
        asr=asr,
        translator=translator,
        target=TargetLanguage.POLISH,
        sample_rate=16_000,
        context_seconds=5,
    )

    first = core.submit_audio(np.ones(16_000, dtype=np.float32), audio_end=1.0)
    second = core.submit_audio(np.ones(16_000, dtype=np.float32), audio_end=2.0)

    assert first.source_provisional == "Dobrý den"
    assert second.source_committed == "Dobrý den"
    assert second.translation_committed == "Dzień dobry"
```

- [ ] **Step 2: Verify the core and fake adapters are missing**

Run: `uv run pytest tests/integration/test_core_pipeline.py -v`

Expected: collection fails for missing `RealtimeCaptionCore` and fakes.

- [ ] **Step 3: Implement protocols, deterministic fakes, and synchronous core orchestration**

The core appends samples, creates an `InferenceRequest`, invokes the supplied ASR backend, smooths language, stabilizes words, updates `CaptionStore`, invokes translation only when required, and returns one immutable `CaptionSnapshot`. It uses `LatestWindowScheduler` even in synchronous tests so the same state transitions can serve the later child-process implementation.

```python
# src/real_time_captions/backends/protocols.py
from typing import Protocol

from real_time_captions.audio.frame import AudioFrame
from real_time_captions.contracts import AsrHypothesis, InferenceRequest


class AudioSource(Protocol):
    def read(self) -> AudioFrame | None: ...


class AsrBackend(Protocol):
    def transcribe(self, request: InferenceRequest) -> AsrHypothesis: ...
```

```python
# tests/fakes.py
from dataclasses import dataclass

from real_time_captions.captions.translation import (
    TranslationRequest,
    TranslationResult,
)
from real_time_captions.contracts import AsrHypothesis, InferenceRequest, Word


@dataclass
class FakeAsrBackend:
    hypotheses: list[tuple[str, tuple[Word, ...]]]

    def transcribe(self, request: InferenceRequest) -> AsrHypothesis:
        language, words = self.hypotheses.pop(0)
        return AsrHypothesis(
            request.session_id,
            request.sequence,
            words,
            language,
            1.0,
            request.audio_end,
        )


@dataclass
class FakeTranslationBackend:
    translations: dict[str, str]

    def translate(self, request: TranslationRequest) -> TranslationResult:
        source = ' '.join(
            part for part in (request.committed, request.provisional) if part
        )
        translated = self.translations[source]
        return TranslationResult(
            request.session_id,
            request.sequence,
            committed=translated if request.committed else '',
            provisional=translated if not request.committed else '',
        )
```

```python
# src/real_time_captions/core.py
import numpy as np

from real_time_captions.audio.ring_buffer import AudioRingBuffer
from real_time_captions.backends.protocols import AsrBackend
from real_time_captions.captions.store import CaptionStore
from real_time_captions.captions.translation import TranslationBackend
from real_time_captions.contracts import (
    CaptionSnapshot,
    InferenceRequest,
    TargetLanguage,
    Word,
)
from real_time_captions.streaming.language import LanguageSmoother
from real_time_captions.streaming.scheduler import LatestWindowScheduler
from real_time_captions.streaming.stabilizer import HypothesisStabilizer


class RealtimeCaptionCore:
    def __init__(
        self,
        session_id: str,
        asr: AsrBackend,
        translator: TranslationBackend,
        target: TargetLanguage,
        sample_rate: int,
        context_seconds: int,
    ) -> None:
        self._session_id = session_id
        self._asr = asr
        self._translator = translator
        self._sample_rate = sample_rate
        self._sequence = 0
        self._last_words: tuple[Word, ...] = ()
        self._audio = AudioRingBuffer(sample_rate * context_seconds)
        self._scheduler = LatestWindowScheduler()
        self._language = LanguageSmoother(2, 0.60)
        self._stabilizer = HypothesisStabilizer(2, 0.8)
        self._store = CaptionStore(session_id, target)

    def submit_audio(
        self, samples: np.ndarray, audio_end: float
    ) -> CaptionSnapshot:
        self._audio.append(samples)
        self._sequence += 1
        request = InferenceRequest(
            self._session_id,
            self._sequence,
            self._audio.latest(self._audio.size),
            audio_end,
        )
        active = self._scheduler.submit(request)
        if active is None:
            return self.snapshot()
        snapshot = self._process(active)
        pending = self._scheduler.complete(active.session_id, active.sequence)
        while pending is not None:
            snapshot = self._process(pending)
            pending = self._scheduler.complete(pending.session_id, pending.sequence)
        return snapshot

    def _process(self, request: InferenceRequest) -> CaptionSnapshot:
        hypothesis = self._asr.transcribe(request)
        self._last_words = hypothesis.words
        language = (
            self._language.observe(
                hypothesis.language,
                hypothesis.language_confidence,
                'active',
            )
            or hypothesis.language
        )
        stable = self._stabilizer.update(
            hypothesis.words, hypothesis.audio_end
        )
        self._store.apply_source(
            hypothesis.sequence,
            language,
            stable.committed,
            stable.provisional,
        )
        translation = self._store.translation_request()
        if translation is not None:
            self._store.apply_translation(self._translator.translate(translation))
        return self._store.snapshot()

    def finalize(self) -> CaptionSnapshot:
        stable = self._stabilizer.finalize(self._last_words)
        language = self._language.current or self._store.language or 'und'
        self._store.apply_source(
            self._sequence, language, stable.committed, stable.provisional
        )
        translation = self._store.translation_request()
        if translation is not None:
            self._store.apply_translation(self._translator.translate(translation))
        return self._store.snapshot()

    def snapshot(self) -> CaptionSnapshot:
        return self._store.snapshot()
```

Extend `core-smoke` to construct deterministic fakes and print a JSON `CaptionSnapshot` without importing PyQt or model libraries.

- [ ] **Step 4: Run integration, full suite, and import-boundary checks**

Run: `uv run pytest -v`

Expected: all tests pass.

Run: `uv run real-time-captions core-smoke`

Expected: JSON contains `source_committed`, `source_provisional`, `translation_committed`, and `translation_provisional`.

Run: `uv run python -c "import sys, real_time_captions.core; assert 'torch' not in sys.modules; assert 'PyQt6' not in sys.modules"`

Expected: exit code 0.

- [ ] **Step 5: Commit the portable end-to-end core**

```bash
git add src/real_time_captions tests
git commit -m "feat(core): run deterministic caption pipeline"
```

---

### Task 8: Add schema-versioned settings and runtime diagnostics

**Files:**
- Create: `src/real_time_captions/settings.py`
- Create: `src/real_time_captions/diagnostics.py`
- Create: `tests/test_settings.py`
- Create: `tests/test_diagnostics.py`

**Interfaces:**
- Consumes: profile, target, and view enums.
- Produces: `AppSettings`, `SettingsStore.load/save`, `RuntimeMetrics.record_first_caption_latency/record_commit_latency/snapshot`, and `DiagnosticsSnapshot`.

- [ ] **Step 1: Write failing atomic-settings and percentile tests**

```python
from real_time_captions.contracts import TargetLanguage, ViewMode
from real_time_captions.settings import AppSettings, SettingsStore


def test_settings_round_trip_uses_schema_version(tmp_path) -> None:
    store = SettingsStore(tmp_path / "settings.json")
    expected = AppSettings(
        target=TargetLanguage.POLISH,
        view_mode=ViewMode.BILINGUAL,
        profile="balanced",
        locked_language=None,
    )

    store.save(expected)

    assert store.load() == expected
    assert '"schema_version": 1' in (tmp_path / "settings.json").read_text()
```

```python
from real_time_captions.diagnostics import RuntimeMetrics


def test_runtime_metrics_report_nearest_rank_percentiles() -> None:
    metrics = RuntimeMetrics(max_samples=100)
    for value in (0.1, 0.2, 0.3, 1.0):
        metrics.record_first_caption_latency(value)

    snapshot = metrics.snapshot()
    assert snapshot.first_caption_p50 == 0.2
    assert snapshot.first_caption_p95 == 1.0
```

- [ ] **Step 2: Verify settings and diagnostics modules are missing**

Run: `uv run pytest tests/test_settings.py tests/test_diagnostics.py -v`

Expected: collection fails for missing modules.

- [ ] **Step 3: Implement atomic JSON and bounded diagnostic samples**

`SettingsStore.save` writes UTF-8 JSON to a sibling temporary file, flushes it, then uses `Path.replace`. `load` validates individual fields and returns defaults plus warning strings for invalid values. `RuntimeMetrics` keeps bounded deques for first-caption and commit latencies, counters for coalesced windows/restarts, and returns immutable snapshots.

```python
# src/real_time_captions/settings.py
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

from real_time_captions.contracts import TargetLanguage, ViewMode


@dataclass(frozen=True, slots=True)
class AppSettings:
    target: TargetLanguage = TargetLanguage.NATIVE
    view_mode: ViewMode = ViewMode.TARGET_ONLY
    profile: str = 'balanced'
    locked_language: str | None = None


class SettingsStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.warnings: tuple[str, ...] = ()

    def load(self) -> AppSettings:
        try:
            raw = json.loads(self.path.read_text(encoding='utf-8'))
            if raw.get('schema_version') != 1:
                raise ValueError('unsupported settings schema')
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
            self.warnings = (str(error),)
            return AppSettings()

        defaults = AppSettings()
        warnings: list[str] = []

        try:
            target = TargetLanguage(raw.get('target', defaults.target))
        except (ValueError, TypeError):
            warnings.append('invalid target')
            target = defaults.target
        try:
            view_mode = ViewMode(raw.get('view_mode', defaults.view_mode))
        except (ValueError, TypeError):
            warnings.append('invalid view_mode')
            view_mode = defaults.view_mode
        profile = raw.get('profile', defaults.profile)
        if profile not in {'low_latency', 'balanced', 'accuracy'}:
            warnings.append('invalid profile')
            profile = defaults.profile
        locked = raw.get('locked_language')
        if locked is not None and not isinstance(locked, str):
            warnings.append('invalid locked_language')
            locked = None
        self.warnings = tuple(warnings)
        return AppSettings(
            target=target,
            view_mode=view_mode,
            profile=profile,
            locked_language=locked,
        )

    def save(self, settings: AppSettings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + '.tmp')
        payload = {'schema_version': 1, **asdict(settings)}
        with temporary.open('w', encoding='utf-8') as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(self.path)
```

```python
# src/real_time_captions/diagnostics.py
import math
from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DiagnosticsSnapshot:
    first_caption_p50: float | None
    first_caption_p95: float | None
    commit_p50: float | None
    commit_p95: float | None
    coalesced_windows: int
    worker_restarts: int


def _percentile(values: deque[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[math.ceil(quantile * len(ordered)) - 1]


class RuntimeMetrics:
    def __init__(self, max_samples: int) -> None:
        self._first = deque[float](maxlen=max_samples)
        self._commit = deque[float](maxlen=max_samples)
        self.coalesced_windows = 0
        self.worker_restarts = 0

    def record_first_caption_latency(self, seconds: float) -> None:
        self._first.append(seconds)

    def record_commit_latency(self, seconds: float) -> None:
        self._commit.append(seconds)

    def snapshot(self) -> DiagnosticsSnapshot:
        return DiagnosticsSnapshot(
            _percentile(self._first, 0.50),
            _percentile(self._first, 0.95),
            _percentile(self._commit, 0.50),
            _percentile(self._commit, 0.95),
            self.coalesced_windows,
            self.worker_restarts,
        )
```

- [ ] **Step 4: Run settings recovery and diagnostics edge cases**

Run: `uv run pytest tests/test_settings.py tests/test_diagnostics.py -v`

Expected: tests pass for defaults, round trip, truncated JSON recovery, invalid individual fields, atomic replacement, bounded sample count, empty percentiles, and counters.

- [ ] **Step 5: Commit settings and diagnostics**

```bash
git add src/real_time_captions/settings.py src/real_time_captions/diagnostics.py tests/test_settings.py tests/test_diagnostics.py
git commit -m "feat(core): persist settings and metrics"
```

---

### Task 9: Verify the portable-core milestone and document its boundary

**Files:**
- Create: `docs/Architecture.md`
- Modify: `README.md`
- Create: `tests/test_architecture_boundaries.py`

**Interfaces:**
- Consumes: public modules produced by Tasks 1–8.
- Produces: documented extension contracts and a stable portable-core verification command.

- [ ] **Step 1: Write a failing architecture-boundary test**

```python
import ast
from pathlib import Path


def test_portable_core_does_not_import_platform_or_heavy_runtime_modules() -> None:
    forbidden = {"PyQt6", "torch", "transformers", "faster_whisper", "pyaudiowpatch"}
    core_files = [
        path
        for path in Path("src/real_time_captions").rglob("*.py")
        if "backends" not in path.parts
    ]

    imported: set[str] = set()
    for path in core_files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])

    assert imported.isdisjoint(forbidden)
    architecture = Path("docs/Architecture.md")
    assert architecture.exists()
    documentation = architecture.read_text(encoding="utf-8")
    assert all(
        contract in documentation
        for contract in ("AudioSource", "AsrBackend", "TranslationBackend")
    )
```

- [ ] **Step 2: Run the boundary test and confirm it exposes any accidental imports or missing documentation marker**

Run: `uv run pytest tests/test_architecture_boundaries.py -v`

Expected: fail until the package boundary matches the allowed structure and `docs/Architecture.md` lists `AudioSource`, `AsrBackend`, and `TranslationBackend`.

- [ ] **Step 3: Document the current milestone without claiming hardware support**

`docs/Architecture.md` describes each public contract, state ownership, latest-wins scheduling, provisional/committed invariants, and the five-plan roadmap. Rewrite the README to label this branch as a portable-core milestone, show `uv sync --group dev`, `uv run pytest`, and `uv run real-time-captions core-smoke`, and explicitly state that hardware capture, real models, and GUI arrive in later plans.

```markdown
# Portable Core Architecture

## Contracts

- `AudioSource` emits timestamped PCM frames without exposing platform APIs.
- `AsrBackend` converts one latest-window request into a word-timestamped hypothesis.
- `TranslationBackend` translates an exact source revision to English or Polish.

## State ownership

The core exclusively owns the audio window, scheduler, language smoother,
stabilizer, and caption store.

## Invariants

- At most one inference request is active and one latest request is pending.
- Provisional text may be replaced.
- Committed text is append-only within a session.
- Results with stale session or sequence identities are ignored.

## Roadmap

Portable core is followed by Windows audio, model benchmarks, GUI/overlay,
and child-process/release integration plans.
```

- [ ] **Step 4: Run all milestone gates**

Run: `uv sync --group dev`

Expected: dependencies resolve from a clean lockfile.

Run: `uv run pytest -v --cov=real_time_captions --cov-report=term-missing`

Expected: all tests pass and portable-core line coverage is at least 90%.

Run: `uv run real-time-captions core-smoke`

Expected: deterministic JSON caption output and exit code 0.

Run: `git diff --check`

Expected: no output.

- [ ] **Step 5: Commit and push the portable-core milestone**

```bash
git add README.md docs/Architecture.md tests/test_architecture_boundaries.py
git commit -m "docs: define portable core boundary"
git push -u origin feature/rewrite-portable-core
```
