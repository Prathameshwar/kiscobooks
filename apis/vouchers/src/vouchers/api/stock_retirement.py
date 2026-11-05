"""Catalog-only retirement transport plus fresh delegated administrator authority."""

from billing_platform.db import tenant_scope
from billing_platform.errors import (
    AuthenticationRequiredError,
    PlatformError,
    ValidationFailedError,
)
from billing_platform.service_auth import service_request_bytes
from fastapi import APIRouter, Request, Response
from voucher_execution.retirement_transport import Action, bounded_body, response_body, verified
from voucher_execution.stock_retirement import RetirementRelease, RetirementRequest

from vouchers.tasks.stock_retirement import acquire, release

router = APIRouter()


async def handle(request: Request, *, closing: bool) -> Response:
    configured = request.app.state.settings.stock_retirement_secret
    if configured is None:
        raise AuthenticationRequiredError("retirement owner transport is not configured")
    if request.url.query:
        raise ValidationFailedError("retirement transport does not accept a query")
    raw = await bounded_body(request.stream())
    framed = service_request_bytes(method=request.method, path=request.url.path, query="", body=raw)
    secret = configured.get_secret_value().encode()
    action: Action = "release" if closing else "acquire"
    verified(secret, "vouchers", action, framed, request.headers)
    status = 200
    try:
        if closing:
            try:
                close = RetirementRelease.model_validate_json(raw)
            except ValueError as exc:
                raise ValidationFailedError("invalid retirement release") from exc
            with tenant_scope(close.tenant_id):
                async with request.app.state.session_factory.begin() as db:
                    await release(db, close)
            payload = {"released": True}
        else:
            try:
                body = RetirementRequest.model_validate_json(raw)
            except ValueError as exc:
                raise ValidationFailedError("invalid retirement check") from exc
            actor = body.verified_actor(
                request.app.state.settings.actor_signing_secret.get_secret_value().encode()
            )
            with tenant_scope(body.tenant_id):
                async with request.app.state.session_factory.begin() as db:
                    payload = (await acquire(db, body, actor)).model_dump(mode="json")
    except PlatformError as exc:
        status, payload = exc.status_code, exc.envelope().model_dump(mode="json")
    content, headers = response_body(secret, "vouchers", action, framed, payload)
    return Response(content, status_code=status, media_type="application/json", headers=headers)


# A service key alone cannot obtain a lease: acquire additionally verifies a
# fresh gateway actor, exact company permission and the native company guard.
@router.post("/internal/v1/stock-retirement", include_in_schema=False)
async def check_retirement(request: Request) -> Response:
    return await handle(request, closing=False)


# An exact retained lease can only be closed, never used to grant new authority.
@router.post("/internal/v1/stock-retirement/release", include_in_schema=False)
async def release_retirement(request: Request) -> Response:
    return await handle(request, closing=True)
