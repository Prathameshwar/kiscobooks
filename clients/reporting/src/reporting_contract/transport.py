"""Scoped signed export requests; no redirects or implicit cross-company authority."""

from typing import Any, Literal

import httpx
from billing_platform.owner_snapshot import (
    SnapshotCredential,
    request_headers,
    verify_response,
)
from billing_platform.service_auth import (
    service_request_bytes,
)
from pydantic import Field, field_validator


class Owner(SnapshotCredential):
    owner: Literal["accounting"] = "accounting"
    origin: str
    key_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,119}$")

    @field_validator("origin")
    @classmethod
    def safe_origin(cls, value: str) -> str:
        url = httpx.URL(value)
        if (
            (
                url.scheme != "https"
                and not (url.scheme == "http" and url.host in {"127.0.0.1", "::1"})
            )
            or not url.host
            or url.path not in {"", "/"}
            or url.userinfo
            or url.query
            or url.fragment
        ):
            raise ValueError("HTTPS origin or literal loopback is required")
        return value.rstrip("/")


async def request(
    client: httpx.AsyncClient,
    owner: Owner,
    method: str,
    path: str,
    params: dict[str, str] | None = None,
) -> dict[str, Any]:
    url = httpx.URL(owner.origin + path, params=params)
    framed = service_request_bytes(method=method, path=url.path, query=url.query.decode(), body=b"")
    headers = request_headers(
        requester="reports",
        owner=owner.owner,
        key_id=owner.key_id,
        secret=owner.secret.get_secret_value().encode(),
        framed=framed,
    )
    async with client.stream(method, url, follow_redirects=False, headers=headers) as response:
        response.raise_for_status()
        raw = bytearray()
        async for chunk in response.aiter_bytes():
            raw.extend(chunk)
            if len(raw) > 1048576:
                raise ValueError("financial export page exceeds its byte bound")
        body = bytes(raw)
        verify_response(
            requester="reports",
            owner=owner.owner,
            key_id=owner.key_id,
            secret=owner.secret.get_secret_value().encode(),
            framed=framed,
            body=body,
            headers=response.headers,
        )
    import json

    value = json.loads(body)
    if not isinstance(value, dict):
        raise ValueError("financial export response must be an object")
    return value
