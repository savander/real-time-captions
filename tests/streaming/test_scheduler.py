import numpy as np
import pytest

from real_time_captions.contracts import InferenceRequest
from real_time_captions.streaming.scheduler import LatestWindowScheduler


def request(sequence: int, session_id: str = "s1") -> InferenceRequest:
    return InferenceRequest(session_id, sequence, np.array([sequence]), float(sequence))


def test_submit_dispatches_immediately_when_idle() -> None:
    scheduler = LatestWindowScheduler()

    dispatched = scheduler.submit(request(1))

    assert dispatched is not None and dispatched.sequence == 1
    assert scheduler.in_flight is True
    assert scheduler.coalesced_count == 0


def test_scheduler_keeps_only_latest_request_while_busy() -> None:
    scheduler = LatestWindowScheduler()

    first = scheduler.submit(request(1))
    assert first is not None and first.sequence == 1
    assert scheduler.submit(request(2)) is None
    assert scheduler.submit(request(3)) is None

    promoted = scheduler.complete("s1", 1)

    assert promoted is not None and promoted.sequence == 3
    assert scheduler.coalesced_count == 1
    assert scheduler.in_flight is True


def test_complete_without_pending_request_becomes_idle() -> None:
    scheduler = LatestWindowScheduler()
    scheduler.submit(request(1))

    promoted = scheduler.complete("s1", 1)

    assert promoted is None
    assert scheduler.in_flight is False


def test_complete_rejects_mismatched_active_identity() -> None:
    scheduler = LatestWindowScheduler()
    scheduler.submit(request(1))

    with pytest.raises(ValueError, match="completion does not match active request"):
        scheduler.complete("s1", 2)

    assert scheduler.in_flight is True


def test_complete_rejects_when_idle() -> None:
    scheduler = LatestWindowScheduler()

    with pytest.raises(ValueError, match="completion does not match active request"):
        scheduler.complete("s1", 1)


def test_reset_clears_active_and_pending_work_without_changing_count() -> None:
    scheduler = LatestWindowScheduler()
    scheduler.submit(request(1))
    scheduler.submit(request(2))
    scheduler.submit(request(3))

    scheduler.reset()

    assert scheduler.in_flight is False
    assert scheduler.coalesced_count == 1
    assert scheduler.submit(request(4)) is not None


def test_pending_request_from_before_reset_cannot_be_promoted_later() -> None:
    scheduler = LatestWindowScheduler()
    scheduler.submit(request(1))
    scheduler.submit(request(2))

    scheduler.reset()
    post_reset = scheduler.submit(request(3))

    assert post_reset is not None and post_reset.sequence == 3
    assert scheduler.complete('s1', 3) is None
    assert scheduler.in_flight is False
