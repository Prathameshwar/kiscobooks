import asyncio
import logging
import uuid

import httpx
import pytest
from fastapi import FastAPI

from billing_platform.audit_context import correlation


@pytest.mark.asyncio
async def test_request_correlation_survives_response_and_is_isolated():
    from billing_platform.request_logging import RequestCorrelation

    app = FastAPI()
    app.add_middleware(RequestCorrelation)

    @app.get("/events")
    async def events():
        await asyncio.sleep(0)
        return {"trace": correlation()[0], "request": correlation()[1]}

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        supplied = {"X-Trace-Id": "a" * 32, "X-Request-Id": str(uuid.uuid4())}
        first, second = await asyncio.gather(c.get("/events", headers=supplied), c.get("/events"))
        assert first.json() == {
            "trace": supplied["X-Trace-Id"],
            "request": supplied["X-Request-Id"],
        }
        assert second.json()["trace"] != first.json()["trace"]
        for response in (first, second):
            assert response.headers["x-trace-id"] == response.json()["trace"]
            assert response.headers["x-request-id"] == response.json()["request"]
        invalid = await c.get(
            "/events", headers={"X-Trace-Id": "private", "X-Request-Id": "private"}
        )
        assert len(invalid.json()["trace"]) == 32
        uuid.UUID(invalid.json()["request"])
    assert correlation() == (None, None)


def test_access_log_does_not_keep_sensitive_query_or_referrer():
    from billing_platform.request_logging import SafeAccessLogFilter

    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        "",
        1,
        "%s - %s %s %s %d",
        (
            "127.0.0.1",
            "GET",
            "/v1/companies/id/tax-registrations?q=PRIVATE_TAX_ID",
            "1.1",
            200,
        ),
        None,
    )
    assert SafeAccessLogFilter().filter(record)
    assert "PRIVATE_TAX_ID" not in record.getMessage()
    assert "?" not in record.getMessage()
