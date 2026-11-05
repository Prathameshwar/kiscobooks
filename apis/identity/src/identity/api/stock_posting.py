"""Delegated stock first use on the common durable reservation lifecycle."""

import time
import uuid
from typing import Literal

from billing_platform.authz import ScopePath
from billing_platform.company_context import verify_company_context
from billing_platform.db import tenant_scope
from billing_platform.errors import (
    AuthenticationRequiredError,
    ConflictError,
    ErrorEnvelope,
    NotFoundError,
    PermissionDeniedError,
    PlatformError,
    ValidationFailedError,
)
from billing_platform.gateway import decode_actor_context, verify_retained_actor_subject
from billing_platform.idempotency import canonical_json
from billing_platform.service_auth import (
    ServiceKey,
    service_request_bytes,
    service_response_bytes,
    sign_service_body,
    verify_service_body,
)
from fastapi import APIRouter, Request, Response
from identity_posting.stock import KEY_ID, OPERATIONS, StockReservationIntent, StockTerminalRequest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.api.posting import PostingReceipt, contract_headers, receipt
from identity.api.security import lock_tenant
from identity.events.catalog_source import CAPTURE_KEY
from identity.models import Company, PostingReservation
from identity.services import posting
from identity.services.catalog_enrollment import is_enrolled

router = APIRouter(
    prefix="/internal/v1/tenants/{tenant_id}/companies/{company_id}/stock-posting/reservations",
    responses={status: {"model": ErrorEnvelope} for status in (401, 403, 404, 409, 422)},
)


async def authenticate(request: Request, operation: str) -> tuple[bytes, bytes, bytes]:
    settings = request.app.state.settings
    if (
        settings.stock_reservation_request_secret is None
        or settings.stock_reservation_response_secret is None
    ):
        raise AuthenticationRequiredError("stock first-use transport is not configured")
    if request.query_params:
        raise ValidationFailedError("stock first-use transport does not accept query parameters")
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 131072:
            raise ValidationFailedError("stock first-use request exceeds its bound")
    framed = service_request_bytes(
        method=request.method, path=request.url.path, query="", body=bytes(raw)
    )
    key = ServiceKey(
        "accounting-stock",
        "identity",
        OPERATIONS,
        settings.stock_reservation_request_secret.get_secret_value().encode(),
    )
    verify_service_body(
        {KEY_ID: key},
        key_id=request.headers.get("x-source-key-id", ""),
        issuer="accounting-stock",
        audience="identity",
        operation="accounting-stock." + operation,
        timestamp=request.headers.get("x-source-issued-at", ""),
        signature=request.headers.get("x-source-signature", ""),
        body=framed,
        now=int(time.time()),
        maximum_age=30,
    )
    return (
        bytes(raw),
        framed,
        settings.stock_reservation_response_secret.get_secret_value().encode(),
    )


def signed(secret: bytes, framed: bytes, value: dict[str, object], status: int = 200) -> Response:
    raw, stamp = canonical_json(value), int(time.time())
    key = ServiceKey(
        "identity", "accounting-stock", frozenset({"identity.stock-posting.response"}), secret
    )
    return Response(
        raw,
        status_code=status,
        media_type="application/json",
        headers={
            "Cache-Control": "no-store",
            "X-Source-Key-Id": KEY_ID,
            "X-Source-Issued-At": str(stamp),
            "X-Source-Signature": sign_service_body(
                key,
                key_id=KEY_ID,
                operation="identity.stock-posting.response",
                timestamp=stamp,
                body=service_response_bytes(request_bytes=framed, response_body=raw),
            ),
        },
    )


def proof(
    request: Request,
    tenant: uuid.UUID,
    company: uuid.UUID,
    body: StockReservationIntent,
    *,
    cancellation: bool = False,
) -> None:
    secret = request.app.state.settings.actor_signing_secret.get_secret_value().encode()
    authority = body.authority
    context = verify_company_context(authority.company_context, authority.company_signature, secret)
    if cancellation:
        subject = verify_retained_actor_subject(
            authority.actor_context, authority.actor_signature, secret
        )
        if (
            subject.tenant_id,
            subject.user_id,
            context.tenant_id,
            context.user_id,
            context.company_id,
        ) != (tenant, body.actor_user_id, tenant, body.actor_user_id, company) or abs(
            context.issued_at - subject.issued_at
        ) > 60:
            raise AuthenticationRequiredError("retained stock cancellation subject differs")
        return  # Historical identity only: never used by the reserve endpoint.
    actor = decode_actor_context(authority.actor_context, authority.actor_signature, secret)
    context.assert_current(actor, company)
    if (actor.tenant_id, actor.user_id) != (tenant, body.actor_user_id) or actor.impersonation_id:
        raise PermissionDeniedError("stock first use requires its original company actor")
    if (
        context.finance is None
        or context.finance.configuration_hash != body.configuration_hash
        or not set(body.features) <= context.features
        or not {"accounting", "vouchers"} <= context.policy_namespaces
    ):
        raise AuthenticationRequiredError("current full financial company authority is required")
    target = ScopePath(company_id=company)
    reverse = body.source.action == "REVERSE"
    for permission in (
        "ledger.post_journal",
        "accounting.stock.reverse" if reverse else "accounting.stock.post",
        "vouchers.reverse" if reverse else "vouchers.post",
    ):
        actor.require_scope(permission, target=target)


async def unique_source(db: AsyncSession, company: uuid.UUID, body: StockReservationIntent) -> None:
    existing = await db.scalar(
        select(PostingReservation).where(
            PostingReservation.company_id == company,
            PostingReservation.source_execution_id == body.source.execution_id,
        )
    )
    if existing is not None and existing.operation_id != body.operation_id:
        raise ConflictError("stock execution already has a different reservation")


# Private service authentication plus fresh delegated actor/company authority.
@router.post(
    "", response_model=PostingReceipt, openapi_extra=contract_headers(StockReservationIntent)
)
async def reserve(tenant_id: uuid.UUID, company_id: uuid.UUID, request: Request) -> Response:
    raw, framed, response_secret = await authenticate(request, "reserve")
    try:
        body = StockReservationIntent.model_validate_json(raw)
        proof(request, tenant_id, company_id, body)
        with tenant_scope(tenant_id):
            async with request.app.state.session_factory() as db, db.begin():
                await lock_tenant(db, tenant_id)
                if not await is_enrolled(db, company_id):
                    raise PermissionDeniedError("company is not enrolled for stock first use")
                company = await db.scalar(
                    select(Company).where(Company.id == company_id).with_for_update()
                )
                if company is None:
                    raise NotFoundError("stock company is unavailable")
                await unique_source(db, company_id, body)
                row = await posting.reserve(
                    db,
                    company,
                    operation_id=body.operation_id,
                    actor_user_id=body.actor_user_id,
                    expected_hash=body.configuration_hash,
                    features=list(body.features),
                    owner_service="accounting",
                    stock_source=body.source,
                )
                value = receipt(row)
    except ValidationError:
        error = ValidationFailedError("invalid stock first-use intent")
        return signed(
            response_secret, framed, error.envelope().model_dump(mode="json"), error.status_code
        )
    except PlatformError as error:
        return signed(
            response_secret, framed, error.envelope().model_dump(mode="json"), error.status_code
        )
    return signed(response_secret, framed, value)


# Terminal authority is restricted to the retained STOCK discriminator and scope.
@router.post(
    "/{operation_id}/{outcome}",
    response_model=PostingReceipt,
    openapi_extra=contract_headers(StockTerminalRequest),
)
async def terminal(
    tenant_id: uuid.UUID,
    company_id: uuid.UUID,
    operation_id: uuid.UUID,
    outcome: Literal["confirmed", "aborted"],
    request: Request,
) -> Response:
    raw, framed, response_secret = await authenticate(request, outcome)
    try:
        body = StockTerminalRequest.model_validate_json(raw)
        if (
            body.terminal_reference
            not in {
                "accounting-stock:" + str(operation_id),
                "accounting-journal:" + str(operation_id),
            }
            or (outcome == "confirmed" and (body.posted_at is None or body.intent is not None))
            or (outcome == "aborted" and body.posted_at is not None)
        ):
            raise ValidationFailedError("stock terminal evidence differs from its outcome")
        if body.intent is not None:
            if outcome != "aborted" or body.intent.operation_id != operation_id:
                raise ValidationFailedError(
                    "stock cancellation must identify its retained operation"
                )
        with tenant_scope(tenant_id):
            async with request.app.state.session_factory() as db, db.begin():
                await lock_tenant(db, tenant_id)
                db.sync_session.info[CAPTURE_KEY] = True
                company = await db.scalar(
                    select(Company).where(Company.id == company_id).with_for_update()
                )
                row = await db.scalar(
                    select(PostingReservation).where(
                        PostingReservation.company_id == company_id,
                        PostingReservation.operation_id == operation_id,
                    )
                )
                if company is None:
                    raise NotFoundError("stock reservation is unavailable")
                if row is not None and (
                    row.owner_service != "accounting" or row.authority_kind != "STOCK"
                ):
                    raise PermissionDeniedError(
                        "stock credential cannot terminate an ordinary reservation"
                    )
                if body.intent is not None:
                    if row is None:
                        proof(request, tenant_id, company_id, body.intent, cancellation=True)
                    await unique_source(db, company_id, body.intent)
                    row = await posting.retain_abort(
                        db,
                        company,
                        operation_id=operation_id,
                        actor_user_id=body.intent.actor_user_id,
                        expected_hash=body.intent.configuration_hash,
                        features=list(body.intent.features),
                        owner_service="accounting",
                        stock_source=body.intent.source,
                    )
                if row is None:
                    raise NotFoundError("stock reservation is unavailable")
                await posting.terminate(
                    db,
                    company,
                    row,
                    outcome=outcome,
                    reference=body.terminal_reference,
                    posted_at=body.posted_at,
                )
                value = receipt(row)
    except ValidationError:
        error = ValidationFailedError("invalid stock terminal evidence")
        return signed(
            response_secret, framed, error.envelope().model_dump(mode="json"), error.status_code
        )
    except PlatformError as error:
        return signed(
            response_secret, framed, error.envelope().model_dump(mode="json"), error.status_code
        )
    return signed(response_secret, framed, value)
