"""Run a service-local reference sync worker: python -m billing_platform.reference.worker.

Fixed Identity endpoint and scoped HMAC key configured by deployment. Checkpoint
commits with local materializations; only then acknowledge the owner. A crash
between commit and acknowledgement retries the ack on the next cycle.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from billing_platform.db import create_engine, create_session_factory
from billing_platform.db.reference_management import ReferenceSyncState
from billing_platform.reference import register_language
from billing_platform.reference.replication import ChangePage, apply
from billing_platform.service_auth import (
    ServiceKey,
    service_request_bytes,
    service_response_bytes,
    sign_service_body,
    verify_service_body,
)

logger = logging.getLogger(__name__)


async def request(
    client: httpx.AsyncClient,
    key: ServiceKey,
    base: str,
    path: str,
    *,
    method: str = "GET",
    query: str = "",
) -> bytes:
    frame = service_request_bytes(method=method, path=path, query=query, body=b"")
    stamp = int(time.time())
    operation = "reference.read" if method == "GET" else "reference.ack"
    signature = sign_service_body(
        key, key_id=key.issuer, operation=operation, timestamp=stamp, body=frame
    )
    async with client.stream(
        method,
        base + path + ("?" + query if query else ""),
        headers={
            "x-source-key-id": key.issuer,
            "x-source-issued-at": str(stamp),
            "x-source-signature": signature,
        },
    ) as response:
        response.raise_for_status()
        body = bytearray()
        async for chunk in response.aiter_bytes():
            body.extend(chunk)
            if len(body) > 1_000_000:
                raise ValueError("reference response exceeds size bound")
    verify_service_body(
        {key.issuer: key},
        key_id=key.issuer,
        issuer=key.issuer,
        audience="identity",
        operation=operation,
        timestamp=response.headers.get("x-source-issued-at", ""),
        signature=response.headers.get("x-source-signature", ""),
        body=service_response_bytes(request_bytes=frame, response_body=bytes(body)),
        now=int(time.time()),
    )
    return bytes(body)


async def cycle(
    factory: async_sessionmaker[AsyncSession], client: httpx.AsyncClient, key: ServiceKey, base: str
) -> bool:
    async with factory() as db:
        state = await db.scalar(
            select(ReferenceSyncState).where(ReferenceSyncState.service == key.issuer)
        )
        cursor = state.cursor if state else None
    path = "/internal/v1/reference-changes/" + key.issuer
    if cursor:
        await request(
            client, key, base, path + "/ack", method="POST", query="cursor=" + str(cursor)
        )
    page = ChangePage.model_validate_json(
        await request(client, key, base, path, query="cursor=" + str(cursor) if cursor else "")
    )
    if page.items:
        async with factory() as db, db.begin():
            cursor = await apply(db, page.items, service=key.issuer)
        await request(
            client, key, base, path + "/ack", method="POST", query="cursor=" + str(cursor)
        )
    return page.has_more


async def run() -> None:
    service = os.environ["REFERENCE_SYNC_SERVICE"]
    if service not in {"catalog", "accounting"}:
        raise ValueError("unsupported reference consumer")
    __import__(service + ".models")
    register_language()
    base = os.environ["REFERENCE_SYNC_IDENTITY_URL"].rstrip("/")
    url = urlsplit(base)
    if (
        url.username
        or url.password
        or url.path
        or url.query
        or url.fragment
        or not (
            url.scheme == "https"
            or (url.scheme == "http" and url.hostname in {"localhost", "127.0.0.1"})
        )
    ):
        raise ValueError("trusted HTTPS or loopback Identity URL required")
    key = ServiceKey(
        service,
        "identity",
        frozenset({"reference.read", "reference.ack"}),
        os.environ["REFERENCE_SYNC_SECRET"].encode(),
    )
    engine = create_engine(
        os.environ.get("REFERENCE_SYNC_DATABASE_URL")
        or os.environ[service.upper() + "_DATABASE_URL"]
    )
    factory = create_session_factory(engine)
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
            stop_file = os.environ.get("REFERENCE_SYNC_STOP_FILE")
            while not (stop_file and Path(stop_file).exists()):
                try:
                    more = await cycle(factory, client, key, base)
                except Exception as exc:
                    logger.warning("Reference synchronization failed: %s", type(exc).__name__)
                    more = False
                await asyncio.sleep(0.1 if more else 3)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
