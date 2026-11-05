from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
from fastapi import FastAPI


async def test_auth_limit_fails_closed_before_authentication(
    app: FastAPI, client: httpx.AsyncClient
):
    app.state.auth_limiter.capacity = 0
    response = await client.get("/v1/session")
    assert response.status_code == 429
    assert response.headers["retry-after"] == "60"
    assert (await client.get("/health/live")).status_code == 200


async def test_lifespan_closes_optional_external_clients(app: FastAPI):
    # One Redis client is shared by the proof store and the permission cache, so the
    # lifespan closes that client once rather than each wrapper (which would double-close
    # the same connection). The document store and OIDC HTTP client are still closed.
    redis, document = SimpleNamespace(aclose=AsyncMock()), SimpleNamespace(close=AsyncMock())
    app.state.redis, app.state.document_store = redis, document
    async with app.router.lifespan_context(app):
        pass
    redis.aclose.assert_awaited_once()
    document.close.assert_awaited_once()
    assert app.state.oidc_http.is_closed
