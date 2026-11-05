"""Explicit native implementation adapter for Catalog's legacy `billing` consumer."""

import datetime as dt
from typing import Literal
from zoneinfo import ZoneInfo

from billing_platform.authz import ScopePath
from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.errors import AuthenticationRequiredError, ValidationFailedError
from billing_platform.idempotency import canonical_json
from billing_platform.outbox import audit_payload, emit
from billing_platform.owner_snapshot import (
    SnapshotCredential,
    authenticate_snapshot,
    response_headers,
)
from fastapi import APIRouter, Request, Response
from sqlalchemy import select
from voucher_execution.stock_policy import KEY, PATH, PolicyInspection, PolicyInspectionResult

from accounting.models.fiscal import FinancialSetup
from accounting.models.masters import AccountingSetup
from accounting.tasks.stock_effects import OPERATIONS
from accounting.tasks.stock_reverse_effects import REVERSAL_OPERATION

router = APIRouter()
# Native operation compilation chooses this catalogue, and every branch calls
# stock_effects.permitted against fresh signed Catalog facts under a definition
# lease. The adjustment flag is enforced by compensating reversals; free-form
# adjustment entry is still outside this selected release.
FLAGS = {
    "SALE_ISSUE": "allow_sale_issue",
    "PURCHASE_RECEIPT": "allow_purchase_receipt",
    "TRANSFER_IN": "allow_transfer_in",
    "TRANSFER_OUT": "allow_transfer_out",
    "CUSTOMER_RETURN_RECEIPT": "allow_customer_return_receipt",
    "SUPPLIER_RETURN_ISSUE": "allow_supplier_return_issue",
    "OPENING_STOCK": "allow_opening_stock",
    "ADJUSTMENT": "allow_adjustment",
}
assert set(OPERATIONS.values()) | {REVERSAL_OPERATION} == set(FLAGS)


# Private read-only service inspection: both the separate Catalog key and the
# original current company publisher grant are required. No key grants a tenant.
@router.post(PATH, include_in_schema=False)
async def inspect_policy(request: Request) -> Response:
    settings = request.app.state.settings
    if settings.stock_policy_secret is None:
        raise AuthenticationRequiredError("native stock policy adapter is not configured")
    if request.url.query:
        raise ValidationFailedError("policy inspection does not accept a query")
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 262144:
            raise ValidationFailedError("policy inspection exceeds its native bound")
    credential = SnapshotCredential(
        secret=settings.stock_policy_secret, allow_enrolled_companies=True
    )
    _, framed, key_id = authenticate_snapshot(
        {KEY: credential},
        owner="accounting",
        requester="catalog",
        headers=request.headers,
        method=request.method,
        path=request.url.path,
        query="",
        body=bytes(raw),
    )
    try:
        body = PolicyInspection.model_validate_json(bytes(raw))
    except ValueError as exc:
        raise ValidationFailedError("invalid native policy inspection") from exc
    actor = body.authority.verified_actor(
        settings.actor_signing_secret.get_secret_value().encode(),
        tenant_id=body.tenant_id,
        actor_user_id=body.actor_user_id,
    )
    actor.require_scope("warehouse.manage", target=ScopePath(company_id=body.company_id))
    result: Literal["PENDING", "APPLIED", "REJECTED"] = "PENDING"
    reason: Literal["SOURCE_UNAVAILABLE", "UNSUPPORTED_OPERATION"] | None = "SOURCE_UNAVAILABLE"
    with tenant_scope(body.tenant_id):
        async with request.app.state.session_factory.begin() as db:
            setup = await db.scalar(
                select(AccountingSetup).where(AccountingSetup.company_id == body.company_id)
            )
            finance = await db.scalar(
                select(FinancialSetup).where(FinancialSetup.company_id == body.company_id)
            )
            if (
                setup is not None
                and finance is not None
                and settings.voucher_stock_enabled
                and settings.stock_execution_secret
                and settings.stock_owner_url
                and settings.stock_owner_secret
                and settings.stock_identity_url
                and settings.stock_identity_request_secret
                and settings.stock_identity_response_secret
                and body.effective_date <= utcnow().astimezone(ZoneInfo(finance.timezone)).date()
            ):
                unsupported = any(
                    not row.flags <= set(FLAGS.values()) for row in body.manifest.locations
                )
                result = "REJECTED" if unsupported else "APPLIED"
                reason = "UNSUPPORTED_OPERATION" if unsupported else None
            event = "accounting.stock_policy.inspect"
            emit(
                db,
                tenant_id=body.tenant_id,
                aggregate_type="accounting.stock_policy",
                aggregate_id=body.check_id,
                event_type=event,
                payload=audit_payload(
                    action=event,
                    category="system",
                    entity_type="accounting.stock_policy",
                    entity_id=body.check_id,
                    actor_user_id=actor.user_id,
                    company_id=body.company_id,
                ),
            )
    now = utcnow()
    payload = PolicyInspectionResult.model_validate(
        {
            "check_id": body.check_id,
            "request_hash": body.digest(),
            "issued_at": now,
            "expires_at": now + dt.timedelta(seconds=30),
            "result": result,
            "reason": reason,
        }
    )
    content = canonical_json(payload.model_dump(mode="json"))
    return Response(
        content,
        media_type="application/json",
        headers=response_headers(
            credential,
            owner="accounting",
            requester="catalog",
            key_id=key_id,
            request_bytes=framed,
            body=content,
        ),
    )
