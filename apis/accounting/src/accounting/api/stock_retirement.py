"""Current Accounting NoStock proof, restricted to the Catalog retirement adapter."""

import datetime as dt

from billing_platform.authz import ScopePath
from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.errors import (
    AuthenticationRequiredError,
    PlatformError,
    ValidationFailedError,
)
from billing_platform.outbox import audit_payload, emit
from billing_platform.service_auth import service_request_bytes
from fastapi import APIRouter, Request, Response
from voucher_execution.retirement_transport import bounded_body, response_body, verified
from voucher_execution.stock_retirement import RetirementEvidence, RetirementRequest

from accounting.tasks.stock_retirement import no_stock

router = APIRouter()


# The Catalog transport key authenticates its owner, not an arbitrary company.
# The original current gateway subject must separately hold lifecycle authority.
@router.post("/internal/v1/stock-retirement", include_in_schema=False)
async def check_retirement(request: Request) -> Response:
    configured = request.app.state.settings.stock_retirement_secret
    if configured is None:
        raise AuthenticationRequiredError("retirement owner transport is not configured")
    if request.url.query:
        raise ValidationFailedError("retirement transport does not accept a query")
    raw = await bounded_body(request.stream())
    framed = service_request_bytes(method=request.method, path=request.url.path, query="", body=raw)
    secret = configured.get_secret_value().encode()
    verified(secret, "accounting", "inspect", framed, request.headers)
    status = 200
    try:
        try:
            body = RetirementRequest.model_validate_json(raw)
        except ValueError as exc:
            raise ValidationFailedError("invalid retirement check") from exc
        actor = body.verified_actor(
            request.app.state.settings.actor_signing_secret.get_secret_value().encode()
        )
        actor.require_scope(
            "warehouse_bin.manage" if body.bin_id else "warehouse.deactivate",
            target=ScopePath(company_id=body.company_id),
        )
        with tenant_scope(body.tenant_id):
            async with request.app.state.session_factory.begin() as db:
                reason = await no_stock(db, body.company_id, body.warehouse_id, bin_id=body.bin_id)
                event = "accounting.stock_retirement.check"
                emit(
                    db,
                    tenant_id=body.tenant_id,
                    aggregate_type="accounting.stock_retirement",
                    aggregate_id=body.check_id,
                    event_type=event,
                    payload=audit_payload(
                        action=event,
                        category="system",
                        entity_type="accounting.stock_retirement",
                        entity_id=body.check_id,
                        actor_user_id=actor.user_id,
                        company_id=body.company_id,
                    ),
                )
        now = utcnow()
        payload = RetirementEvidence(
            owner="accounting",
            check_id=body.check_id,
            request_hash=body.digest(),
            issued_at=now,
            expires_at=now + dt.timedelta(seconds=30),
            result="CLEARED" if reason is None else "BLOCKED",
            reason=reason,
        ).model_dump(mode="json")
    except PlatformError as exc:
        status, payload = exc.status_code, exc.envelope().model_dump(mode="json")
    content, headers = response_body(secret, "accounting", "inspect", framed, payload)
    return Response(content, status_code=status, media_type="application/json", headers=headers)
