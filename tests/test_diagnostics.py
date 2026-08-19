from dataclasses import FrozenInstanceError

import pytest

from real_time_captions.diagnostics import RuntimeMetrics


def test_runtime_metrics_report_none_for_empty_latency_samples() -> None:
    snapshot = RuntimeMetrics(max_samples=2).snapshot()

    assert snapshot.first_caption_p50 is None
    assert snapshot.first_caption_p95 is None
    assert snapshot.commit_p50 is None
    assert snapshot.commit_p95 is None


def test_runtime_metrics_report_single_latency_for_each_percentile() -> None:
    metrics = RuntimeMetrics(max_samples=2)
    metrics.record_first_caption_latency(0.25)
    metrics.record_commit_latency(0.75)

    snapshot = metrics.snapshot()

    assert (snapshot.first_caption_p50, snapshot.first_caption_p95) == (0.25, 0.25)
    assert (snapshot.commit_p50, snapshot.commit_p95) == (0.75, 0.75)


def test_runtime_metrics_report_nearest_rank_percentiles() -> None:
    metrics = RuntimeMetrics(max_samples=100)
    for value in (0.1, 0.2, 0.3, 1.0):
        metrics.record_first_caption_latency(value)

    snapshot = metrics.snapshot()

    assert snapshot.first_caption_p50 == 0.2
    assert snapshot.first_caption_p95 == 1.0


def test_latency_samples_are_bounded_to_the_most_recent_capacity() -> None:
    metrics = RuntimeMetrics(max_samples=3)
    for value in (1.0, 2.0, 3.0, 4.0):
        metrics.record_commit_latency(value)

    snapshot = metrics.snapshot()

    assert snapshot.commit_p50 == 3.0
    assert snapshot.commit_p95 == 4.0


def test_first_and_commit_latency_samples_are_independent() -> None:
    metrics = RuntimeMetrics(max_samples=3)
    metrics.record_first_caption_latency(1.0)
    metrics.record_commit_latency(9.0)
    metrics.record_commit_latency(10.0)

    snapshot = metrics.snapshot()

    assert (snapshot.first_caption_p50, snapshot.first_caption_p95) == (1.0, 1.0)
    assert (snapshot.commit_p50, snapshot.commit_p95) == (9.0, 10.0)


def test_snapshot_includes_recorded_runtime_counters() -> None:
    metrics = RuntimeMetrics(max_samples=1)
    metrics.record_coalesced_window()
    metrics.record_coalesced_window()
    metrics.record_worker_restart()

    snapshot = metrics.snapshot()

    assert snapshot.coalesced_windows == 2
    assert snapshot.worker_restarts == 1


def test_snapshot_is_immutable() -> None:
    snapshot = RuntimeMetrics(max_samples=1).snapshot()

    with pytest.raises(FrozenInstanceError):
        snapshot.coalesced_windows = 1


@pytest.mark.parametrize('capacity', (0, -1))
def test_runtime_metrics_rejects_non_positive_sample_capacity(capacity: int) -> None:
    with pytest.raises(ValueError, match='max_samples'):
        RuntimeMetrics(max_samples=capacity)


@pytest.mark.parametrize('latency', (-0.01, float('inf'), float('nan')))
def test_runtime_metrics_rejects_invalid_latency_values(latency: float) -> None:
    metrics = RuntimeMetrics(max_samples=1)

    with pytest.raises(ValueError, match='latency'):
        metrics.record_first_caption_latency(latency)
