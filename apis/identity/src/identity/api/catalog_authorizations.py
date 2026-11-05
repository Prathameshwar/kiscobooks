"""Internal permission proofs: independent service authentication, explicit opt-in."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

from billing_platform.actor_authorization import (
    REQUEST_OPERATION,
    RESPONSE_OPERATION,
    ActorAuthorizationProof,
    ActorAuthorizationRequest,
)
from billing_platform.db import tenant_scope
from billing_platform.errors import ErrorEnvelope, ValidationFailedError
from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from identity.api.catalog_sources import (
    SOURCE_HEADERS,
    VerifiedScope,
    authenticate_source,
    signed_response,
)
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
