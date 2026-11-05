"""Authenticated global reference change feed; never grants tenant access."""

from __future__ import annotations

import time
import uuid

from billing_platform.db.reference_management import ReferenceSyncState
from billing_platform.errors import AuthenticationRequiredError, ValidationFailedError
from billing_platform.idempotency import canonical_json
from billing_platform.reference.replication import Change, ChangePage
from billing_platform.service_auth import (
    ServiceKey,
    service_request_bytes,
    service_response_bytes,
    sign_service_body,
    verify_service_body,
)
from fastapi import APIRouter, Request, Response
from sqlalchemy import select

from identity.api.route import ERROR_RESPONSES, StrictRoute
from identity.models import ReferenceChange

router = APIRouter(
    prefix="/internal/v1/reference-changes", route_class=StrictRoute, responses=ERROR_RESPONSES
)


async def authenticate(request: Request, service: str) -> tuple[ServiceKey, bytes, str]:
    configuration = request.app.state.settings.reference_sync_credentials
    secret = configuration.get(service)
    if service not in {"catalog", "accounting"} or secret is None:
        raise AuthenticationRequiredError("reference source authentication is unavailable")
    raw = b""
    async for part in request.stream():
        raw += part
        if len(raw) > 4096:
            raise ValidationFailedError("source request exceeds size limit")
    if raw:
        raise ValidationFailedError("unexpected source request body")
    operation = "reference.read" if request.method == "GET" else "reference.ack"
    key = ServiceKey(
        service,
        "identity",
        frozenset({"reference.read", "reference.ack"}),
        secret.get_secret_value().encode(),
    )
    framed = service_request_bytes(
        method=request.method, path=request.url.path, query=request.url.query, body=raw
    )
    verify_service_body(
        {service: key},
        key_id=request.headers.get("x-source-key-id", ""),
        issuer=service,
        audience="identity",
        operation=operation,
        timestamp=request.headers.get("x-source-issued-at", ""),
        signature=request.headers.get("x-source-signature", ""),
        body=framed,
        now=int(time.time()),
    )
    return key, framed, operation


def respond(value: object, key: ServiceKey, framed: bytes, operation: str) -> Response:
    raw = canonical_json(value, maximum_bytes=1_000_000)
    issued = int(time.time())
    signature = sign_service_body(
        key,
        key_id=key.issuer,
        operation=operation,
        timestamp=issued,
        body=service_response_bytes(request_bytes=framed, response_body=raw),
    )
    return Response(
        raw,
        media_type="application/json",
        headers={
            "Cache-Control": "no-store",
            "x-source-issued-at": str(issued),
            "x-source-signature": signature,
        },
    )


@router.get("/{service}")
async def changes(service: str, request: Request, cursor: uuid.UUID | None = None) -> Response:
    key, framed, operation = await authenticate(request, service)
    async with request.app.state.session_factory() as db:
        statement = select(ReferenceChange).order_by(ReferenceChange.id).limit(101)
        if cursor:
            statement = statement.where(ReferenceChange.id > cursor)
        rows = list(await db.scalars(statement))
        page = ChangePage(
            items=[
                Change(id=r.id, kind=r.kind, code=r.code, version=r.version, payload=r.payload)
                for r in rows[:100]
            ],
            has_more=len(rows) > 100,
        )
        return respond(page.model_dump(mode="json"), key, framed, operation)


@router.post("/{service}/ack")
async def acknowledge(service: str, request: Request, cursor: uuid.UUID) -> Response:
    key, framed, operation = await authenticate(request, service)
    async with request.app.state.session_factory() as db, db.begin():
        if await db.get(ReferenceChange, cursor) is None:
            raise ValidationFailedError("unknown reference checkpoint")
        state = await db.scalar(
            select(ReferenceSyncState)
            .where(ReferenceSyncState.service == service)
            .with_for_update()
        )
        if state is None:
            state = ReferenceSyncState(service=service)
            db.add(state)
        if state.cursor is None or cursor > state.cursor:
            state.cursor = cursor
        return respond({"cursor": str(state.cursor)}, key, framed, operation)
