from unittest.mock import AsyncMock, patch


async def test_review_worker_honours_owned_stop_file_before_delivery(tmp_path):
    from identity.tasks.account_review_worker import run

    stop = tmp_path / "review.stop"
    stop.write_text("stop")
    with patch("identity.tasks.account_review_worker.tick", AsyncMock()) as tick:
        await run(None, False, stop)
        tick.assert_not_called()


async def test_review_worker_stops_during_retry_interval(tmp_path):
    from identity.tasks.account_review_worker import run

    stop = tmp_path / "review.stop"

    async def delivered(_settings):
        stop.write_text("stop")

    with patch("identity.tasks.account_review_worker.tick", delivered):
        await run(None, False, stop)
