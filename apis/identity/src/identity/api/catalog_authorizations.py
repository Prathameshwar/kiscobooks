"""Internal permission proofs: independent service authentication, explicit opt-in."""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
import uuid
from collections.abc import AsyncIterator

from billing_platform.actor_authorization import (
    CREATION_PERMISSIONS,
    CREATION_REQUEST_OPERATION,
    CREATION_RESPONSE_OPERATION,
    REQUEST_OPERATION,
    RESPONSE_OPERATION,
    ActorAuthorizationProof,
    ActorAuthorizationRequest,
)
from billing_platform.authz import Grant, Scope, ScopePath, grant_to_wire, resolve_permissions
from billing_platform.company_context import sign_company_context
from billing_platform.db import tenant_scope
from billing_platform.errors import ErrorEnvelope, PermissionDeniedError, ValidationFailedError
from billing_platform.idempotency import canonical_json
from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from identity.api.auth import Actor
from identity.api.catalog_sources import (
    SOURCE_HEADERS,
    VerifiedScope,
    authenticate_source,
    signed_response,
)
from identity.services.accounting_context import company_context
from identity.services.login import live_grants
from identity.tasks.catalog_authorizations import authorize_actor

router = APIRouter(
    prefix="/internal/v1/tenants/{tenant_id}/companies/{company_id}/catalog-authorizations",
    responses={code: {"model": ErrorEnvelope} for code in (401, 403, 422, 503)},
)


async def actor_scope(
    tenant_id: uuid.UUID, company_id: uuid.UUID, request: Request
) -> VerifiedScope:
    return await authenticate_source(tenant_id, company_id, request, operation=REQUEST_OPERATION)


async def actor_session(
    request: Request, scope: VerifiedScope = Depends(actor_scope)
) -> AsyncIterator[AsyncSession]:
    with tenant_scope(scope.tenant_id):
        async with request.app.state.session_factory() as db, db.begin():
            yield db


@router.post(
    "",
    response_model=ActorAuthorizationProof,
    operation_id="authorize_catalog_job_actor",
    openapi_extra={
        **SOURCE_HEADERS,
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {"schema": ActorAuthorizationRequest.model_json_schema()}
            },
        },
    },
)
async def authorize(
    request: Request,
    scope: VerifiedScope = Depends(actor_scope),
    db: AsyncSession = Depends(actor_session),
) -> Response:
    try:
        body = ActorAuthorizationRequest.model_validate_json(request.state.source_raw_body)
    except ValidationError as exc:
        raise ValidationFailedError("invalid actor authorization request") from exc
    proof = await authorize_actor(db, company_id=scope.company_id, request=body)
    return signed_response(
        request, scope, proof.model_dump(mode="json"), operation=RESPONSE_OPERATION
    )


@router.post("/creation-context", include_in_schema=False)
async def creation_context(
    tenant_id: uuid.UUID, company_id: uuid.UUID, request: Request,
) -> Response:
    """Issue one short-lived, company-scoped continuation context for an accepted job."""
    scope = await authenticate_source(
        tenant_id, company_id, request, operation=CREATION_REQUEST_OPERATION
    )
    try:
        body = ActorAuthorizationRequest.model_validate_json(request.state.source_raw_body)
    except ValidationError as exc:
        raise ValidationFailedError("invalid creation authority request") from exc
    with tenant_scope(scope.tenant_id):
        async with request.app.state.session_factory() as db, db.begin():
            proof = await authorize_actor(
                db, company_id=scope.company_id, request=body,
                requestable_permissions=CREATION_PERMISSIONS,
            )
            if proof.permissions != body.permissions:
                raise PermissionDeniedError("product creator no longer has required permissions")
            grants, groups = await live_grants(db, body.user_id)
            full_actor = Actor(scope.tenant_id, body.user_id, grants, group_ids=groups)
            facts = await company_context(
                db, full_actor, scope.company_id, entity_prefix="vouchers."
            )
    secret = request.app.state.settings.actor_signing_secret.get_secret_value().encode()
    company_token, company_signature = sign_company_context(facts, secret)
    narrowed = Grant(
        permissions=resolve_permissions(
            grants, target=ScopePath(company_id=scope.company_id),
            on_date=proof.generated_at.date(),
        ),
        scope=Scope("company", scope.company_id),
        valid_from=proof.generated_at.date(),
        valid_to=proof.expires_at.date(),
    )
    raw = canonical_json({
        "issued_at": int(time.time()),
        "tenant_id": str(scope.tenant_id),
        "user_id": str(body.user_id),
        "group_ids": sorted(str(group) for group in groups),
        "grants": [grant_to_wire(narrowed)],
    }, maximum_bytes=24_000)
    return signed_response(
        request, scope,
        {
            "actor_context": base64.urlsafe_b64encode(raw).rstrip(b"=").decode(),
            "actor_signature": hmac.new(secret, raw, hashlib.sha256).hexdigest(),
            "company_context": company_token,
            "company_signature": company_signature,
            "expires_at": proof.expires_at.isoformat(),
        },
        operation=CREATION_RESPONSE_OPERATION,
    )
