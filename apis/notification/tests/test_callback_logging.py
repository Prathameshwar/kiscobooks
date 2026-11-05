from unittest.mock import AsyncMock

import pytest

from notification.callback_logging import CallbackQueryRedaction


@pytest.mark.parametrize("failed", [False, True])
async def test_callback_verification_sees_query_but_access_logging_does_not(failed):
    scope = {
        "type": "http",
        "path": "/v1/callbacks/whatsapp/key",
        "query_string": b"hub.verify_token=private",
    }
    logged = []

    async def send(message):
        logged.append(scope["query_string"])

    async def handler(scope, receive, send):
        assert scope["query_string"] == b"hub.verify_token=private"
        if failed:
            raise RuntimeError("failed verification")
        await send({"type": "http.response.start", "status": 200, "headers": []})

    middleware = CallbackQueryRedaction(handler)
    if failed:
        with pytest.raises(RuntimeError):
            await middleware(scope, AsyncMock(), send)
    else:
        await middleware(scope, AsyncMock(), send)
        assert logged == [b""]
    assert scope["query_string"] == b""


async def test_ordinary_query_logging_is_preserved():
    app = AsyncMock()
    scope = {"type": "http", "path": "/v1/templates", "query_string": b"limit=50"}
    await CallbackQueryRedaction(app)(scope, AsyncMock(), AsyncMock())
    assert scope["query_string"] == b"limit=50"
