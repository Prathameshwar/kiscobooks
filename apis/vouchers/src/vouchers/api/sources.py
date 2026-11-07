"""Internal signed owner ingress with explicit tenant/company grants and inbox dedupe."""

import time
from typing import Any

from billing_platform.db import tenant_scope
from billing_platform.errors import (
    AuthenticationRequiredError,
)
from billing_platform.service_auth import ServiceKey, service_request_bytes, verify_service_body
from fastapi import APIRouter, Request
from sqlalchemy import select

from vouchers.api.auth import limit_service_ingress
from vouchers.schemas.sources import SourceBundle

router = APIRouter()
OPERATION = "vouchers.sources.apply"


@router.post("/internal/v1/sources")
async def apply_sources(body: SourceBundle, request: Request) -> dict[str, Any]:
    settings = request.app.state.settings
    key_id = request.headers.get("x-service-key-id", "")
    credential = settings.source_credentials.get(key_id)
    if credential is None:
        raise AuthenticationRequiredError("unknown source credential")
    framed = service_request_bytes(
        method=request.method,
        path=request.url.path,
        query=request.url.query,
        body=await request.body(),
    )
    principal = verify_service_body(
        {
            key_id: ServiceKey(
                credential.issuer,
                "vouchers",
                credential.operations,
                credential.secret.get_secret_value().encode(),
            )
        },
        key_id=key_id,
        issuer=request.headers.get("x-service-issuer", ""),
        audience="vouchers",
        operation=OPERATION,
        timestamp=request.headers.get("x-service-timestamp", ""),
        signature=request.headers.get("x-service-signature", ""),
        body=framed,
        now=int(time.time()),
    )
    allowed = any(
        scope.tenant_id == body.tenant_id and scope.company_id == body.company_id
        for scope in credential.scopes
    )
    if not allowed and credential.allow_enrolled_companies:
        from vouchers.models import core as m

        with tenant_scope(body.tenant_id):
            async with request.app.state.session_factory() as db:
                allowed = (await db.scalar(
                    select(m.VoucherMasterEvidence.id).where(
                        m.VoucherMasterEvidence.company_id == body.company_id,
                        m.VoucherMasterEvidence.owner == "identity",
                        m.VoucherMasterEvidence.entity_type == "company",
                        m.VoucherMasterEvidence.source_id == body.company_id,
                        m.VoucherMasterEvidence.status == "ACTIVE",
                    ).limit(1)
                )) is not None
    if not allowed:
        raise AuthenticationRequiredError("source company scope is not authorized")
    limit_service_ingress(request, key_id, body.tenant_id, body.company_id)
    from vouchers.tasks.sources import apply_bundle

    return await apply_bundle(request.app.state.session_factory, body, principal.issuer)
