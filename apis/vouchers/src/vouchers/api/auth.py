"""Fresh signed gateway context, followed by action and object authorization."""

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

from billing_platform.audit_context import audit_actor, audit_request
from billing_platform.company_context import CompanyContext, verify_company_context
from billing_platform.errors import AuthenticationRequiredError, PermissionDeniedError
from billing_platform.gateway import Actor, decode_actor_context
from fastapi import Header, HTTPException, Request
from voucher_execution.contracts import DelegatedAuthority


@dataclass(frozen=True)
class Access:
    actor: Actor
    context: CompanyContext
    authority: DelegatedAuthority | None = None


def limit_service_ingress(
    request: Request, key_id: str, tenant_id: uuid.UUID, company_id: uuid.UUID
) -> None:
    if not request.app.state.write_limiter.allow(
        f"service:{key_id}:{tenant_id}:{company_id}", limit=1200
    ):
        raise HTTPException(status_code=429, detail="service ingress rate limit exceeded")


async def access(
    company_id: uuid.UUID,
    request: Request,
    x_actor_context: str | None = Header(default=None),
    x_actor_signature: str | None = Header(default=None),
    x_company_context: str | None = Header(default=None),
    x_company_signature: str | None = Header(default=None),
) -> AsyncIterator[Access]:
    if not all((x_actor_context, x_actor_signature, x_company_context, x_company_signature)):
        raise AuthenticationRequiredError("verified actor and company context required")
    secret = request.app.state.settings.actor_signing_secret.get_secret_value().encode()
    actor = decode_actor_context(x_actor_context or "", x_actor_signature or "", secret)
    context = verify_company_context(x_company_context or "", x_company_signature or "", secret)
    context.assert_current(actor, company_id)
    if not {"accounting", "vouchers"} <= context.policy_namespaces:
        raise AuthenticationRequiredError("complete accounting and voucher field policies required")
    if request.method not in {"GET", "HEAD"} and not request.app.state.write_limiter.allow(
        f"{actor.tenant_id}:{company_id}:{actor.user_id}", limit=240
    ):
        raise HTTPException(status_code=429)
    if actor.impersonation_id and request.method not in {"GET", "HEAD"}:
        raise PermissionDeniedError("support sessions are read only")
    with (
        audit_actor(actor.real_user_id, actor.user_id),
        audit_request(request.headers.get("x-trace-id"), request.headers.get("x-request-id")),
    ):
        yield Access(
            actor,
            context,
            DelegatedAuthority(
                actor_context=x_actor_context or "",
                actor_signature=x_actor_signature or "",
                company_context=x_company_context or "",
                company_signature=x_company_signature or "",
            ),
        )
