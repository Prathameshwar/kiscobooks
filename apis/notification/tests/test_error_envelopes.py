from __future__ import annotations

import uuid
from typing import Any

import httpx

from notification.api.dependencies import session
from tests.test_control import headers


async def test_unexpected_failures_never_expose_internal_payloads(
    app: Any, tenant_a: uuid.UUID
) -> None:
    async def unavailable():
        raise RuntimeError("private provider credentials and SQL parameters")

    app.dependency_overrides[session] = unavailable
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as client:
            response = await client.get("/v1/channels", headers=headers(tenant_a))
        assert response.status_code == 500
        assert response.json()["error"]["code"] == "internal_error"
        assert "private" not in response.text and "SQL" not in response.text
    finally:
        app.dependency_overrides.clear()
