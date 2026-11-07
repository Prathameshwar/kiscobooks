"""Internal company-scoped source API authenticated independently of user grants."""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from billing_platform.actor_authorization import CREATION_REQUEST_OPERATION, REQUEST_OPERATION
from billing_platform.db import tenant_scope
from billing_platform.errors import (
    AuthenticationRequiredError,
    ErrorEnvelope,
    PermissionDeniedError,
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
from billing_platform.snapshots import SnapshotManifest, SnapshotPage
from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from identity.config import Settings
from identity.services.catalog_enrollment import is_enrolled
from identity.tasks.catalog_snapshots import create_snapshot, load_snapshot, read_page

router = APIRouter(
    prefix="/internal/v1/tenants/{tenant_id}/companies/{company_id}/catalog-snapshots",
    responses={code: {"model": ErrorEnvelope} for code in (401, 403, 404, 409, 422)},
)
SOURCE_HEADERS = {
    "parameters": [
        {
            "in": "header",
            "name": name,
            "required": True,
            "schema": {"type": "string"},
            "description": description,
        }
        for name, description in (
            ("x-source-key-id", "Scoped Catalog-to-Identity service key identifier."),
            ("x-source-issued-at", "Unix timestamp covered by the service signature."),
            ("x-source-signature", "HMAC of the method/path/query/body-hash request frame."),
        )
    ]
}
OPERATIONS = frozenset({"catalog.snapshot.create", "catalog.snapshot.read"})


@dataclass(frozen=True)
class VerifiedSourceRequest:
    key_id: str
    request_bytes: bytes


@dataclass(frozen=True)
class VerifiedScope:
    tenant_id: uuid.UUID
    company_id: uuid.UUID
    request_bytes: bytes


class SnapshotCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: uuid.UUID

    @field_validator("request_id")
    @classmethod
    def real_id(cls, value: uuid.UUID) -> uuid.UUID:
        if value.int == 0:
            raise ValueError("real snapshot request identity required")
        return value


async def source_scope(
    tenant_id: uuid.UUID, company_id: uuid.UUID, request: Request
) -> VerifiedScope:
    operation = "catalog.snapshot.create" if request.method == "POST" else "catalog.snapshot.read"
    return await authenticate_source(tenant_id, company_id, request, operation=operation)


async def authenticate_source(
    tenant_id: uuid.UUID, company_id: uuid.UUID, request: Request, *, operation: str
) -> VerifiedScope:
    if tenant_id.int == 0 or company_id.int == 0:
        raise AuthenticationRequiredError("source authentication is unavailable")
    verified = await authenticate_source_request(request, operation=operation)
    settings: Settings = request.app.state.settings
    credential = settings.catalog_source_credentials[verified.key_id]
    allowed = any(
        scope.tenant_id == tenant_id and scope.company_id == company_id
        for scope in credential.scopes
    )
    if not allowed and credential.allow_enrolled_companies:
        with tenant_scope(tenant_id):
            async with request.app.state.session_factory() as db:
                allowed = await is_enrolled(db, company_id)
    if not allowed:
        raise PermissionDeniedError("source principal cannot access this tenant/company")
    return VerifiedScope(tenant_id, company_id, verified.request_bytes)


async def authenticate_source_request(request: Request, *, operation: str) -> VerifiedSourceRequest:
    settings: Settings = request.app.state.settings
    if settings.catalog_source_response_secret is None:
        raise AuthenticationRequiredError("source authentication is unavailable")
    keys = {
        key_id: ServiceKey(
            "catalog",
            "identity",
            OPERATIONS
            | ({REQUEST_OPERATION, CREATION_REQUEST_OPERATION}
               if entry.allow_actor_authorization else set())
            | ({"catalog.enrollment.read"} if entry.allow_enrolled_companies else set()),
            entry.secret.get_secret_value().encode(),
        )
        for key_id, entry in settings.catalog_source_credentials.items()
    }
    key_id = request.headers.get("x-source-key-id", "")
    if key_id not in keys:
        raise AuthenticationRequiredError("source authentication failed")
    pieces: list[bytes] = []
    size = 0
    async for piece in request.stream():
        size += len(piece)
        if size > 4096:
            raise ValidationFailedError("source request exceeds size bound")
        pieces.append(piece)
    body = b"".join(pieces)
    request.state.source_raw_body = body
    if request.query_params or len(body) > 4096 or (request.method == "GET" and body):
        raise ValidationFailedError("unexpected source query or oversized body")
    framed = service_request_bytes(
        method=request.method, path=request.url.path, query="", body=body
    )
    principal = verify_service_body(
        keys,
        key_id=request.headers.get("x-source-key-id", ""),
        issuer="catalog",
        audience="identity",
        operation=operation,
        timestamp=request.headers.get("x-source-issued-at", ""),
        signature=request.headers.get("x-source-signature", ""),
        body=framed,
        now=int(time.time()),
    )
    return VerifiedSourceRequest(principal.key_id, framed)


async def source_session(
    request: Request, scope: VerifiedScope = Depends(source_scope)
) -> AsyncIterator[AsyncSession]:
    with tenant_scope(scope.tenant_id):
        async with request.app.state.session_factory() as db, db.begin():
            yield db


def signed_response(
    request: Request,
    scope: VerifiedScope | VerifiedSourceRequest,
    payload: dict[str, Any],
    *,
    operation: str = "catalog.snapshot.response",
) -> Response:
    settings: Settings = request.app.state.settings
    secret = settings.catalog_source_response_secret
    if secret is None:
        raise AuthenticationRequiredError("source signing is unavailable")
    body = canonical_json(payload)
    stamp = int(time.time())
    key_id = settings.catalog_source_response_key_id
    key = ServiceKey(
        "identity",
        "catalog",
        frozenset({operation}),
        secret.get_secret_value().encode(),
    )
    signature = sign_service_body(
        key,
        key_id=key_id,
        operation=operation,
        timestamp=stamp,
        body=service_response_bytes(request_bytes=scope.request_bytes, response_body=body),
    )
    return Response(
        content=body,
        media_type="application/json",
        headers={
            "x-source-key-id": key_id,
            "x-source-issued-at": str(stamp),
            "x-source-signature": signature,
            "cache-control": "no-store",
        },
    )


@router.post(
    "",
    response_model=SnapshotManifest,
    operation_id="create_catalog_source_snapshot",
    openapi_extra={
        **SOURCE_HEADERS,
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": SnapshotCreate.model_json_schema()}},
        },
    },
)
async def start_snapshot(
    request: Request,
    scope: VerifiedScope = Depends(source_scope),
    db: AsyncSession = Depends(source_session),
) -> Response:
    settings: Settings = request.app.state.settings
    try:
        body = SnapshotCreate.model_validate_json(request.state.source_raw_body)
    except ValidationError as exc:
        raise ValidationFailedError("invalid source snapshot request") from exc
    manifest = await create_snapshot(
        db,
        company_id=scope.company_id,
        request_id=body.request_id,
        ttl_seconds=settings.catalog_source_ttl_seconds,
    )
    return signed_response(request, scope, manifest.model_dump(mode="json"))


@router.get(
    "/{snapshot_id}",
    response_model=SnapshotManifest,
    operation_id="get_catalog_source_snapshot",
    openapi_extra=SOURCE_HEADERS,
)
async def get_snapshot(
    snapshot_id: uuid.UUID,
    request: Request,
    scope: VerifiedScope = Depends(source_scope),
    db: AsyncSession = Depends(source_session),
) -> Response:
    row = await load_snapshot(db, scope.company_id, snapshot_id)
    return signed_response(request, scope, row.manifest)


@router.get(
    "/{snapshot_id}/pages/{page_number}",
    response_model=SnapshotPage,
    operation_id="get_catalog_source_snapshot_page",
    openapi_extra=SOURCE_HEADERS,
)
async def get_page(
    snapshot_id: uuid.UUID,
    page_number: int,
    request: Request,
    scope: VerifiedScope = Depends(source_scope),
    db: AsyncSession = Depends(source_session),
) -> Response:
    if page_number < 0:
        raise ValidationFailedError("source page number must be nonnegative")
    page = await read_page(
        db, company_id=scope.company_id, snapshot_id=snapshot_id, page_number=page_number
    )
    return signed_response(request, scope, page.model_dump(mode="json"))
