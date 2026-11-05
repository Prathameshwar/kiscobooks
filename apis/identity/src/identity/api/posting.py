"""Authenticated financial-service-to-Identity reservation contract, independently idempotent."""

from __future__ import annotations

import datetime as dt
import time
import uuid
from typing import Any, Literal

from billing_platform.db import tenant_scope
from billing_platform.errors import (
    AuthenticationRequiredError,
    NotFoundError,
    PermissionDeniedError,
    ValidationFailedError,
)
from billing_platform.idempotency import canonical_json
from billing_platform.schema import resolved_schema
from billing_platform.service_auth import (
    ServiceKey,
    service_request_bytes,
    service_response_bytes,
    sign_service_body,
    verify_service_body,
)
from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field, ValidationError, field_validator
from sqlalchemy import select

from identity.api.route import ERROR_RESPONSES
from identity.api.security import lock_tenant
from identity.events.catalog_source import CAPTURE_KEY
from identity.models import Company, PostingReservation
from identity.schemas.base import StrictModel
from identity.services import posting

OPERATIONS = frozenset(
    {
        "billing.posting.configuration",
        "billing.posting.reserve",
        "billing.posting.confirmed",
        "billing.posting.aborted",
    }
)
router = APIRouter(
    prefix="/internal/v1/tenants/{tenant_id}/companies/{company_id}/posting",
    responses=ERROR_RESPONSES,
)


class ReserveRequest(StrictModel):
    operation_id: uuid.UUID
    actor_user_id: uuid.UUID
    configuration_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    features: list[str] = Field(default_factory=list, max_length=32)

    @field_validator("operation_id", "actor_user_id")
    @classmethod
    def non_nil(cls, value: uuid.UUID) -> uuid.UUID:
        if value.int == 0:
            raise ValueError("non-nil identifier required")
        return value


class TerminalRequest(StrictModel):
    terminal_reference: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9_.:/-]+$")
    posted_at: dt.datetime | None = None
    intent: ReserveRequest | None = None


class PostingReceipt(StrictModel):
    operation_id: uuid.UUID
    reservation_id: uuid.UUID
    status: Literal["pending", "confirmed", "aborted"]
    configuration_hash: str
    features: list[str]
    confirmed_at: dt.datetime | None


class PostingConfiguration(StrictModel):
    company_id: uuid.UUID
    configuration_hash: str
    settings: dict[str, Any]
    enabled_features: list[str]


def contract_headers(body: type[BaseModel] | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "parameters": [
            {"in": "header", "name": name, "required": True, "schema": {"type": "string"}}
            for name in ("x-source-key-id", "x-source-issued-at", "x-source-signature")
        ]
    }
    if body is not None:
        result["requestBody"] = {
            "required": True,
            "content": {"application/json": {"schema": resolved_schema(body)}},
        }
    return result


async def verified(
    request: Request, tenant_id: uuid.UUID, company_id: uuid.UUID, operation: str
) -> bytes:
    settings = request.app.state.settings
    issuer = request.headers.get("x-source-issuer", "billing")
    if issuer not in {"billing", "accounting"}:
        raise AuthenticationRequiredError("posting service authentication is unavailable")
    credentials = (
        settings.billing_reservation_credentials
        if issuer == "billing"
        else settings.accounting_reservation_credentials
    )
    response_secret = (
        settings.billing_reservation_response_secret
        if issuer == "billing"
        else settings.accounting_reservation_response_secret
    )
    operation = issuer + operation.removeprefix("billing")
    operations = frozenset(issuer + item.removeprefix("billing") for item in OPERATIONS)
    if tenant_id.int == 0 or company_id.int == 0 or response_secret is None:
        raise AuthenticationRequiredError("posting service authentication is unavailable")
    keys = {
        key: ServiceKey(issuer, "identity", operations, value.secret.get_secret_value().encode())
        for key, value in credentials.items()
    }
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > 4096:
            raise ValidationFailedError("posting command exceeds request bounds")
        chunks.append(chunk)
    raw = b"".join(chunks)
    if (request.method == "GET" and raw) or request.query_params:
        raise ValidationFailedError("posting command exceeds request bounds")
    framed = service_request_bytes(method=request.method, path=request.url.path, query="", body=raw)
    principal = verify_service_body(
        keys,
        key_id=request.headers.get("x-source-key-id", ""),
        issuer=issuer,
        audience="identity",
        operation=operation,
        timestamp=request.headers.get("x-source-issued-at", ""),
        signature=request.headers.get("x-source-signature", ""),
        body=framed,
        now=int(time.time()),
    )
    scopes = credentials[principal.key_id].scopes
    if not any(scope.tenant_id == tenant_id and scope.company_id == company_id for scope in scopes):
        raise PermissionDeniedError("posting principal does not hold this company")
    request.state.posting_issuer = issuer
    request.state.posting_response_secret = response_secret
    request.state.posting_frame = framed
    return raw


def response(request: Request, value: dict[str, Any]) -> Response:
    body = canonical_json(value)
    key = ServiceKey(
        "identity",
        request.state.posting_issuer,
        frozenset({"identity.posting.response"}),
        request.state.posting_response_secret.get_secret_value().encode(),
    )
    stamp = int(time.time())
    signature = sign_service_body(
        key,
        key_id="current",
        operation="identity.posting.response",
        timestamp=stamp,
        body=service_response_bytes(request_bytes=request.state.posting_frame, response_body=body),
    )
    return Response(
        content=body,
        media_type="application/json",
        headers={
            "x-source-key-id": "current",
            "x-source-issued-at": str(stamp),
            "x-source-signature": signature,
            "cache-control": "no-store",
        },
    )


def receipt(row: PostingReservation) -> dict[str, Any]:
    return {
        "operation_id": str(row.operation_id),
        "reservation_id": str(row.id),
        "status": row.status,
        "configuration_hash": row.configuration_hash,
        "features": row.features,
        "confirmed_at": row.confirmed_at.isoformat() if row.confirmed_at else None,
    }


@router.get("/configuration", response_model=PostingConfiguration, openapi_extra=contract_headers())
async def configuration(tenant_id: uuid.UUID, company_id: uuid.UUID, request: Request) -> Response:
    await verified(request, tenant_id, company_id, "billing.posting.configuration")
    with tenant_scope(tenant_id):
        async with request.app.state.session_factory() as db, db.begin():
            await lock_tenant(db, tenant_id)
            company = await db.get(Company, company_id)
            if company is None:
                raise NotFoundError("company not found")
            state = await posting.configuration(db, company)
            return response(
                request,
                {
                    "company_id": str(company_id),
                    "configuration_hash": posting.digest(state),
                    **state,
                },
            )


@router.post(
    "/reservations", response_model=PostingReceipt, openapi_extra=contract_headers(ReserveRequest)
)
async def reserve(tenant_id: uuid.UUID, company_id: uuid.UUID, request: Request) -> Response:
    raw = await verified(request, tenant_id, company_id, "billing.posting.reserve")
    try:
        body = ReserveRequest.model_validate_json(raw)
    except ValidationError as exc:
        raise ValidationFailedError("invalid posting reservation") from exc
    with tenant_scope(tenant_id):
        async with request.app.state.session_factory() as db, db.begin():
            await lock_tenant(db, tenant_id)
            company = await db.scalar(
                select(Company).where(Company.id == company_id).with_for_update()
            )
            if company is None:
                raise NotFoundError("company not found")
            row = await posting.reserve(
                db,
                company,
                operation_id=body.operation_id,
                actor_user_id=body.actor_user_id,
                expected_hash=body.configuration_hash,
                features=body.features,
                owner_service=request.state.posting_issuer,
            )
            return response(request, receipt(row))


@router.post(
    "/reservations/{operation_id}/{outcome}",
    response_model=PostingReceipt,
    openapi_extra=contract_headers(TerminalRequest),
)
async def terminal(
    tenant_id: uuid.UUID,
    company_id: uuid.UUID,
    operation_id: uuid.UUID,
    outcome: Literal["confirmed", "aborted"],
    request: Request,
) -> Response:
    raw = await verified(request, tenant_id, company_id, "billing.posting." + outcome)
    try:
        body = TerminalRequest.model_validate_json(raw)
    except ValidationError as exc:
        raise ValidationFailedError("invalid posting outcome") from exc
    if body.intent is not None and (
        outcome != "aborted" or body.intent.operation_id != operation_id
    ):
        raise ValidationFailedError("cancellation intent must match the aborted operation")
    if outcome == "aborted" and body.posted_at is not None:
        raise ValidationFailedError("an aborted operation cannot have a posting timestamp")
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
                    PostingReservation.owner_service == request.state.posting_issuer,
                )
            )
            if company is None:
                raise NotFoundError("posting reservation not found")
            if body.intent is not None:
                row = await posting.retain_abort(
                    db,
                    company,
                    operation_id=operation_id,
                    actor_user_id=body.intent.actor_user_id,
                    expected_hash=body.intent.configuration_hash,
                    features=body.intent.features,
                    owner_service=request.state.posting_issuer,
                )
            if row is None:
                raise NotFoundError("posting reservation not found")
            if row.authority_kind != "GENERAL":
                raise PermissionDeniedError(
                    "stock reservations require their delegated stock channel"
                )
            await posting.terminate(
                db,
                company,
                row,
                outcome=outcome,
                reference=body.terminal_reference,
                posted_at=body.posted_at,
            )
            return response(request, receipt(row))
