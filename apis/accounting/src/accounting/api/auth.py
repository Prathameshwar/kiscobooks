"""Verify gateway-issued actor and company context before any database access."""

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

from billing_platform.audit_context import audit_actor, audit_request
from billing_platform.company_context import CompanyContext, verify_company_context
from billing_platform.errors import AuthenticationRequiredError, PermissionDeniedError
from billing_platform.gateway import Actor, decode_actor_context
from fastapi import Header, Request
from voucher_execution.contracts import DelegatedAuthority


@dataclass(frozen=True)
class Access:
    actor: Actor
    context: CompanyContext


def delegated_access(
    authority: DelegatedAuthority,
    secret: bytes,
    *,
    tenant_id: uuid.UUID,
    company_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> Access:
    actor = decode_actor_context(authority.actor_context, authority.actor_signature, secret)
    context = verify_company_context(authority.company_context, authority.company_signature, secret)
    context.assert_current(actor, company_id)
    if (actor.tenant_id, actor.user_id) != (tenant_id, actor_user_id):
        raise AuthenticationRequiredError("delegated actor differs from gateway authority")
    if not {"accounting", "vouchers"} <= context.policy_namespaces:
        raise AuthenticationRequiredError("complete owner and voucher field policies are required")
    return Access(actor, context)


async def access(
    company_id: uuid.UUID,
    request: Request,
    x_actor_context: str | None = Header(default=None),
    x_actor_signature: str | None = Header(default=None),
    x_company_context: str | None = Header(default=None),
    x_company_signature: str | None = Header(default=None),
) -> AsyncIterator[Access]:
    if not all((x_actor_context, x_actor_signature, x_company_context, x_company_signature)):
        raise AuthenticationRequiredError("verified actor and company context are required")
    secret = request.app.state.settings.actor_signing_secret.get_secret_value().encode()
    current = decode_actor_context(x_actor_context or "", x_actor_signature or "", secret)
    context = verify_company_context(x_company_context or "", x_company_signature or "", secret)
    context.assert_current(current, company_id)
    if current.impersonation_id and request.method not in {"GET", "HEAD"}:
        raise PermissionDeniedError("support sessions are read only")
    with (
        audit_actor(current.real_user_id, current.user_id),
        audit_request(request.headers.get("x-trace-id"), request.headers.get("x-request-id")),
    ):
        yield Access(current, context)
