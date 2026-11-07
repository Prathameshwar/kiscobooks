"""Thin adapter for the platform's existing signed gateway context."""

from collections.abc import AsyncIterator

from billing_platform.audit_context import audit_actor, audit_request
from billing_platform.company_context import verify_company_context
from billing_platform.errors import AuthenticationRequiredError, PermissionDeniedError
from billing_platform.gateway import Actor, decode_actor_context
from fastapi import Header, Request
from voucher_execution.retirement_transport import RetirementClient
from voucher_execution.stock_policy_transport import PolicyClient
from voucher_execution.stock_retirement import ActorProof

from catalog.tasks.stock_policy_delivery import request_scope as policy_scope
from catalog.tasks.stock_retirement import request_scope
from catalog.tasks.warehouse_tax import request_context as tax_context


async def actor(
    request: Request,
    x_actor_context: str | None = Header(default=None),
    x_actor_signature: str | None = Header(default=None),
    x_company_context: str | None = Header(default=None),
    x_company_signature: str | None = Header(default=None),
) -> AsyncIterator[Actor]:
    if x_actor_context is None or x_actor_signature is None:
        raise AuthenticationRequiredError("actor context is required")
    secret: bytes = request.app.state.settings.actor_signing_secret.get_secret_value().encode()
    current = decode_actor_context(x_actor_context, x_actor_signature, secret)
    company = None
    if x_company_context is not None or x_company_signature is not None:
        if x_company_context is None or x_company_signature is None:
            raise AuthenticationRequiredError("signed company context is required")
        company = verify_company_context(x_company_context, x_company_signature, secret)
    if current.impersonation_id and request.method not in {"GET", "HEAD"}:
        raise PermissionDeniedError("support sessions allow read requests only")
    settings = request.app.state.settings
    async with request_scope(
        current,
        ActorProof(context=x_actor_context, signature=x_actor_signature),
        RetirementClient("accounting", settings.stock_retirement_accounting)
        if settings.stock_retirement_accounting
        else None,
        RetirementClient("vouchers", settings.stock_retirement_vouchers)
        if settings.stock_retirement_vouchers
        else None,
    ):
        with (
            policy_scope(
                ActorProof(context=x_actor_context, signature=x_actor_signature),
                PolicyClient(settings.stock_policy_accounting)
                if settings.stock_policy_accounting
                else None,
            ),
            audit_actor(current.real_user_id, current.user_id),
            tax_context(company),
            audit_request(request.headers.get("x-trace-id"), request.headers.get("x-request-id")),
        ):
            yield current
