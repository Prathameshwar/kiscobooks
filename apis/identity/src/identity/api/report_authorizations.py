"""Service-authenticated report authority, bound to fresh native grants and field denies."""

import uuid

from billing_platform.actor_authorization import ActorAuthorizationRequest
from billing_platform.authz import ScopePath
from billing_platform.db import tenant_scope
from billing_platform.errors import ErrorEnvelope, PermissionDeniedError, ValidationFailedError
from billing_platform.idempotency import canonical_json
from billing_platform.owner_snapshot import (
    authenticate_snapshot,
    require_snapshot_scope,
    response_headers,
)
from fastapi import APIRouter, Request
from fastapi.responses import Response
from pydantic import ValidationError
from reporting_contract.authority import REPORT_PERMISSIONS, ReportAuthority

from identity.api.auth import Actor
from identity.models import Tenant
from identity.services.accounting_context import accounting_policies
from identity.tasks.catalog_authorizations import authorize_actor

router = APIRouter(
    prefix="/internal/v1/report-authority/{tenant_id}/{company_id}",
    responses={code: {"model": ErrorEnvelope} for code in (401, 403, 422, 503)},
)


@router.post(
    "",
    response_model=ReportAuthority,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {"schema": ActorAuthorizationRequest.model_json_schema()}
            },
        }
    },
)
async def report_authority(
    tenant_id: uuid.UUID, company_id: uuid.UUID, request: Request
) -> Response:
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 4096:
            raise ValidationFailedError("authority request exceeds its bound")
    if request.query_params:
        raise ValidationFailedError("authority request does not accept query parameters")
    credential, framed, key_id = authenticate_snapshot(
        request.app.state.settings.report_authority_credentials,
        owner="identity",
        requester="reports",
        headers=request.headers,
        method="POST",
        path=request.url.path,
        query="",
        body=bytes(raw),
    )
    try:
        body = ActorAuthorizationRequest.model_validate_json(raw)
    except ValidationError as exc:
        raise ValidationFailedError("invalid report authority request") from exc
    with tenant_scope(tenant_id):
        async with request.app.state.session_factory() as db, db.begin():
            from identity.services.report_enrollment import is_enrolled

            require_snapshot_scope(
                credential,
                tenant_id=tenant_id,
                company_id=company_id,
                enrolled=await is_enrolled(db, company_id, retained=True),
            )
            # The resolver holds the source-generation shared lock before native grants reads.
            proof = await authorize_actor(
                db,
                company_id=company_id,
                request=body,
                requestable_permissions=REPORT_PERMISSIONS,
                retained_reports=True,
            )
            tenant = await db.get(Tenant, tenant_id)
            if tenant is None or tenant.status != "active":
                raise PermissionDeniedError("report tenant is unavailable")
            current = Actor(tenant_id, body.user_id)
            policies = []
            namespaces = ("accounting.", "reports.")
            if {"item.read", "warehouse.read"} & set(body.permissions):
                namespaces += ("catalog.",)
            for namespace in namespaces:
                policies.extend(
                    await accounting_policies(
                        db, current, ScopePath(company_id=company_id), entity_prefix=namespace
                    )
                )
            allowed = not any(row.access == "read" and row.effect == "deny" for row in policies)
            result = ReportAuthority(**proof.model_dump(), read_allowed=allowed)
    encoded = canonical_json(result.model_dump(mode="json"))
    return Response(
        content=encoded,
        media_type="application/json",
        headers=response_headers(
            credential,
            owner="identity",
            requester="reports",
            key_id=key_id,
            request_bytes=framed,
            body=encoded,
        ),
    )
