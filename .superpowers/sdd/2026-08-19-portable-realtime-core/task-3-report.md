# Task 3 Report: Coalesce inference requests with latest-wins backpressure

## Scope

Implemented `LatestWindowScheduler` in `src/real_time_captions/streaming/scheduler.py` and exported it from the new `streaming` package. The scheduler maintains one active request and one latest pending request, dispatches immediately while idle, coalesces replacements while busy, promotes pending work on a matching completion, rejects stale or idle completions, and clears active/pending work on `reset()`.

`coalesced_count` is cumulative for the scheduler lifetime and is preserved by `reset()`, matching the Task 3 brief.

## TDD evidence

### RED

Command:

```text
uv run pytest tests/streaming/test_scheduler.py -v
```

Result before production modules existed:

```text
collected 0 items / 1 error
ModuleNotFoundError: No module named 'real_time_captions.streaming'
```

### GREEN

Command:

```text
uv run pytest tests/streaming/test_scheduler.py -v
```

Result:

```text
collected 6 items
6 passed in 0.13s
```

Covered behaviors:

- immediate dispatch while idle and `in_flight` state
- one active request with latest-wins pending replacement
- cumulative `coalesced_count`
- matching completion and pending promotion
- completion with no pending request returning idle
- mismatched and idle completion errors
- `reset()` clearing active/pending work while preserving the counter

## Full-suite evidence

Command:

```text
uv run pytest -v
```

Result:

```text
collected 27 items
27 passed in 1.10s
```

## Files changed

- `src/real_time_captions/streaming/__init__.py`
- `src/real_time_captions/streaming/scheduler.py`
- `tests/streaming/test_scheduler.py`
