"""Private effect-owner transport: service signature AND exact delegated actor."""

import time
import uuid
from collections.abc import Mapping

from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.errors import (
    AuthenticationRequiredError,
    ConflictError,
    PlatformError,
    ValidationFailedError,
)
from billing_platform.idempotency import canonical_json
from billing_platform.service_auth import (
    ServiceKey,
    service_request_bytes,
    service_response_bytes,
    sign_service_body,
    verify_service_body,
)
from fastapi import APIRouter, Request, Response
from pydantic import ValidationError
from sqlalchemy import select
from voucher_execution.contracts import Contract
from voucher_execution.stock_facts import StockFenceRequest

from catalog.models.stock_source import StockSourceFence
from catalog.tasks.policy_state import company_policy_state
from catalog.tasks.stock_sources import acquire, fence_audit, verified_actor

router = APIRouter()


class Release(Contract):
    tenant_id: uuid.UUID
    company_id: uuid.UUID
    execution_id: uuid.UUID
    fence_id: uuid.UUID


async def authenticate(request: Request, operation: str) -> tuple[bytes, bytes, bytes]:
    secret = request.app.state.settings.stock_owner_secret
    if secret is None:
        raise AuthenticationRequiredError("stock owner transport is not configured")
    if request.url.query:
        raise ValidationFailedError("stock owner transport does not accept a query")
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 262144:
            raise ValidationFailedError("stock source request exceeds its native bound")
    body = bytes(raw)
    framed = service_request_bytes(
        method=request.method, path=request.url.path, query="", body=body
    )
    key = ServiceKey(
        "accounting", "catalog", frozenset({operation}), secret.get_secret_value().encode()
    )
    verify_service_body(
        {"current": key},
        key_id=request.headers.get("x-source-key-id", ""),
        issuer="accounting",
        audience="catalog",
        operation=operation,
        timestamp=request.headers.get("x-source-issued-at", ""),
        signature=request.headers.get("x-source-signature", ""),
        body=framed,
        now=int(time.time()),
        maximum_age=30,
    )
    return body, framed, key.secret


def signed_response(
    secret: bytes,
    framed: bytes,
    body: Mapping[str, object],
    operation: str,
    *,
    status_code: int = 200,
) -> Response:
    raw = canonical_json(body)
    stamp = int(time.time())
    key = ServiceKey("catalog", "accounting", frozenset({operation}), secret)
    return Response(
        raw,
        status_code=status_code,
        media_type="application/json",
        headers={
            "Cache-Control": "no-store",
            "X-Source-Key-Id": "current",
            "X-Source-Issued-At": str(stamp),
            "X-Source-Signature": sign_service_body(
                key,
                key_id="current",
                operation=operation,
                timestamp=stamp,
                body=service_response_bytes(request_bytes=framed, response_body=raw),
            ),
        },
    )


# Fixed Accounting service purpose plus gateway-signed real actor/company grants;
# no caller can acquire a tenant/company merely by naming its UUID.
@router.post("/internal/v1/stock-source-fences", include_in_schema=False)
async def stock_fence(request: Request) -> Response:
    raw, framed, secret = await authenticate(request, "accounting.stock.fence.acquire")
    try:
        body = StockFenceRequest.model_validate_json(raw)
    except ValidationError as exc:
        raise ValidationFailedError("invalid stock source request") from exc
    try:
        actor = verified_actor(
            body, request.app.state.settings.actor_signing_secret.get_secret_value().encode()
        )
        with tenant_scope(body.tenant_id):
            async with request.app.state.session_factory.begin() as db:
                facts = await acquire(db, body, actor)
    except PlatformError as exc:
        return signed_response(
            secret,
            framed,
            exc.envelope().model_dump(mode="json"),
            "accounting.stock.fence.response",
            status_code=exc.status_code,
        )
    return signed_response(
        secret, framed, facts.model_dump(mode="json"), "accounting.stock.fence.response"
    )


# Only the authenticated effect owner closes its exact retained execution lease.
# Closing cannot post stock; the immutable source evidence is retained.
@router.post("/internal/v1/stock-source-fences/release", include_in_schema=False)
async def release_fence(request: Request) -> Response:
    raw, framed, secret = await authenticate(request, "accounting.stock.fence.release")
    try:
        body = Release.model_validate_json(raw)
    except ValidationError as exc:
        raise ValidationFailedError("invalid stock source release") from exc
    with tenant_scope(body.tenant_id):
        async with request.app.state.session_factory.begin() as db:
            await company_policy_state(db, body.tenant_id, body.company_id, lock=True)
            row = await db.scalar(
                select(StockSourceFence)
                .where(
                    StockSourceFence.company_id == body.company_id,
                    StockSourceFence.id == body.fence_id,
                    StockSourceFence.execution_id == body.execution_id,
                )
                .with_for_update()
            )
            if row is None:
                raise ConflictError("stock source release does not match a retained execution")
            if row.closed_at is None:
                row.closed_at = utcnow()
                fence_audit(db, row, "release")
    return signed_response(
        secret, framed, {"released": True}, "accounting.stock.fence.release.response"
    )
