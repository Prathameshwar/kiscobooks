"""Fresh Identity-issued contexts for durable product continuation.

No user credential, gateway context or permission grant is retained in a job.
"""

import json
import uuid

import httpx
from billing_platform.actor_authorization import (
    CREATION_REQUEST_OPERATION,
    CREATION_RESPONSE_OPERATION,
    ActorAuthorizationRequest,
)
from billing_platform.authz import ScopePath
from billing_platform.company_context import CompanyContext, verify_company_context
from billing_platform.gateway import Actor, decode_actor_context
from billing_platform.idempotency import canonical_json
from billing_platform.ids import uuid7
from pydantic import BaseModel, ConfigDict, Field

from catalog.tasks.identity_source import IdentitySourceSettings, _request


class ContinuationContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actor_context: str = Field(min_length=1, max_length=32768)
    actor_signature: str = Field(pattern=r"^[0-9a-f]{64}$")
    company_context: str = Field(min_length=1, max_length=32768)
    company_signature: str = Field(pattern=r"^[0-9a-f]{64}$")
    expires_at: str


async def fetch_context(
    settings: IdentitySourceSettings,
    secret: bytes,
    tenant_id: uuid.UUID,
    company_id: uuid.UUID,
    user_id: uuid.UUID,
    permissions: frozenset[str],
) -> tuple[Actor, CompanyContext, dict[str, str]]:
    request = ActorAuthorizationRequest(
        request_id=uuid7(), user_id=user_id, permissions=permissions
    )
    path = (
        f"/internal/v1/tenants/{tenant_id}/companies/{company_id}"
        "/catalog-authorizations/creation-context"
    )
    async with httpx.AsyncClient(
        base_url=settings.base_url, timeout=5, follow_redirects=False, trust_env=False
    ) as client:
        raw = await _request(
            client, settings, method="POST", path=path,
            body=canonical_json(request.model_dump(mode="json")),
            request_operation=CREATION_REQUEST_OPERATION,
            response_operation=CREATION_RESPONSE_OPERATION,
            max_response_bytes=65536,
        )
    value = ContinuationContext.model_validate(json.loads(raw))
    actor = decode_actor_context(value.actor_context, value.actor_signature, secret)
    context = verify_company_context(value.company_context, value.company_signature, secret)
    context.assert_current(actor, company_id)
    if actor.tenant_id != tenant_id or actor.user_id != user_id:
        raise ValueError("creation actor scope changed")
    for permission in permissions:
        actor.require_scope(permission, target=ScopePath(company_id=company_id))
    headers: dict[str, str] = {
        "x-actor-context": value.actor_context,
        "x-actor-signature": value.actor_signature,
        "x-company-context": value.company_context,
        "x-company-signature": value.company_signature,
    }
    return actor, context, headers
