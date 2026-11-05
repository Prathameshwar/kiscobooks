"""Bounded provider JSON transport. Services own origins, credentials and policy."""

from __future__ import annotations

import json
from typing import Any

import httpx


class ProviderHttpError(Exception):
    """An opaque transport failure, safe to translate to a service error."""


async def provider_json(
    http: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    headers: dict[str, str],
    body: dict[str, Any] | None = None,
    max_bytes: int,
    expected_status: int = 200,
) -> dict[str, Any]:
    """Never follow redirects or retain provider values in exceptions."""
    try:
        async with http.stream(
            method, url, headers=headers, json=body, timeout=5, follow_redirects=False
        ) as response:
            if response.status_code != expected_status:
                raise ValueError("unexpected status")
            if expected_status == 204:
                return {}
            content = bytearray()
            async for chunk in response.aiter_bytes():
                if len(content) + len(chunk) > max_bytes:
                    raise ValueError("response too large")
                content.extend(chunk)
        value = json.loads(content)
        if not isinstance(value, dict):
            raise ValueError("unexpected response")
        return value
    except (httpx.HTTPError, ValueError):
        raise ProviderHttpError("Provider request unavailable.") from None
