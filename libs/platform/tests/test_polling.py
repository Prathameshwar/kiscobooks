import asyncio

import pytest

from billing_platform.polling import repeat


async def test_polling_recovers_dependency_errors_and_honors_shutdown(caplog):
    calls = 0

    async def operation():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("private connection details must not enter logs")
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await repeat(operation, interval=0.001)
    assert calls == 2
    assert "OSError" in caplog.text
    assert "private connection" not in caplog.text


async def test_company_polling_keeps_progress_and_bounds_parallel_work():
    from billing_platform.polling import repeat_independently

    started, progress = asyncio.Event(), asyncio.Event()
    active, peak, completed = 0, 0, 0

    async def slow():
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            active -= 1

    async def fast():
        nonlocal active, peak, completed
        active += 1
        peak = max(peak, active)
        try:
            await started.wait()
            await asyncio.sleep(0)
            completed += 1
            if completed >= 4:
                progress.set()
        finally:
            active -= 1

    worker = asyncio.create_task(
        repeat_independently((slow, fast, fast), parallelism=2, interval=0.001)
    )
    try:
        await asyncio.wait_for(progress.wait(), 5)
        assert completed >= 4 and peak == 2
    finally:
        worker.cancel()
        with pytest.raises(asyncio.CancelledError):
            await worker
    assert active == 0


@pytest.mark.parametrize("parallelism,interval,empty", [(0, 1, False), (1, 0, False), (1, 1, True)])
async def test_independent_polling_rejects_unbounded_or_empty_configuration(
    parallelism, interval, empty
):
    from billing_platform.polling import repeat_independently

    async def work():
        raise AssertionError("invalid configuration cannot run work")

    with pytest.raises(ValueError):
        await repeat_independently(
            () if empty else (work,), parallelism=parallelism, interval=interval
        )
