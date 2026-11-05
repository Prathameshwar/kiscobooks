"""Benchmark pacing must respect the real 120 financial-write requests/minute guard."""

from itertools import pairwise

import pytest

from tools.reporting_snapshot_benchmark import PostingPacer


async def test_posting_samples_are_paced_outside_measured_operations(monkeypatch):
    from tools import reporting_snapshot_benchmark as benchmark

    elapsed = 0.0
    waits = []

    async def sleep(seconds):
        nonlocal elapsed
        waits.append(seconds)
        elapsed += seconds

    monkeypatch.setattr(benchmark.time, "monotonic", lambda: elapsed)
    monkeypatch.setattr(benchmark.asyncio, "sleep", sleep)
    pacer = PostingPacer()
    starts = []
    for _ in range(201):
        await pacer.wait()
        starts.append(elapsed)
        elapsed += 0.2  # Two guarded create/post requests complete inside the sample.
    assert all(b - a == pytest.approx(1.1) for a, b in pairwise(starts))
    assert max(sum(start <= point < start + 60 for point in starts) * 2 for start in starts) < 120
    assert sum(waits) == pytest.approx(180)
    elapsed += 10
    before = len(waits)
    await pacer.wait()
    assert len(waits) == before
