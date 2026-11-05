"""Unexpected HTTP errors must not escape with private driver/request details."""

from __future__ import annotations

import json
import traceback
from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI
from starlette.responses import StreamingResponse
from starlette.types import Message, Receive, Scope, Send

from catalog.main import _FailureBoundary


@pytest.mark.parametrize("trace", ["a" * 32, "private-query-value"])
async def test_unexpected_failure_is_handled_and_logged_without_private_context(
    app: FastAPI, caplog: pytest.LogCaptureFixture, trace: str
) -> None:
    @app.get("/__failure", include_in_schema=False)
    async def failure() -> None:
        raise RuntimeError("private SQL parameters and password")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=True),
        base_url="http://catalog.test",
    ) as client:
        response = await client.get("/__failure?private=secret", headers={"x-trace-id": trace})
    assert response.status_code == 500
    records = [record for record in caplog.records if record.name == "catalog.http"]
    assert len(records) == 1
    log = records[0]
    payload = json.loads(log.getMessage())
    assert payload["error_type"] == "RuntimeError"
    assert payload["trace_id"] == response.headers["x-trace-id"]
    assert len(payload["trace_id"]) == 32
    if trace == "a" * 32:
        assert payload["trace_id"] == trace
    assert log.exc_info is None and "private" not in log.getMessage()
    assert "private" not in response.text


async def test_failed_stream_aborts_with_only_sanitized_server_error(
    app: FastAPI, caplog: pytest.LogCaptureFixture
) -> None:
    @app.get("/__stream_failure", include_in_schema=False)
    async def failure() -> StreamingResponse:
        async def chunks() -> AsyncIterator[bytes]:
            yield b"started"
            raise RuntimeError("private streaming token")

        return StreamingResponse(chunks())

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=True),
        base_url="http://catalog.test",
    ) as client:
        with pytest.raises(RuntimeError, match="response stream failed") as caught:
            await client.get("/__stream_failure")
    rendered = "".join(traceback.format_exception(caught.value))
    assert "private streaming token" not in rendered
    assert "private streaming token" not in caplog.text


async def test_failure_boundary_preserves_non_http_lifecycle() -> None:
    events: list[Message] = []

    async def lifecycle(scope: Scope, receive: Receive, send: Send) -> None:
        assert scope["type"] == "lifespan"
        assert (await receive())["type"] == "lifespan.startup"
        await send({"type": "lifespan.startup.complete"})

    async def receive() -> Message:
        return {"type": "lifespan.startup"}

    async def send(message: Message) -> None:
        events.append(message)

    await _FailureBoundary(lifecycle)({"type": "lifespan"}, receive, send)
    assert events == [{"type": "lifespan.startup.complete"}]
