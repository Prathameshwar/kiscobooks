"""Fresh Identity permission proof acquisition and transaction-local job checks."""

from __future__ import annotations

import asyncio
import datetime as dt
import uuid

import httpx
from billing_platform.actor_authorization import (
    REQUEST_OPERATION,
    RESPONSE_OPERATION,
    ActorAuthorizationProof,
    ActorAuthorizationRequest,
)
from billing_platform.authz import Grant, Scope
from billing_platform.db.tenant_context import require_current_tenant
from billing_platform.db.types import utcnow
from billing_platform.errors import PermissionDeniedError, PlatformError, ValidationFailedError
from billing_platform.gateway import Actor
from billing_platform.idempotency import canonical_json
from billing_platform.ids import uuid7
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.tasks.identity_source import (
    IdentitySourceSettings,
    IdentitySourceUnavailableError,
    _request,
)
from catalog.tasks.projections import require_identity_context


def validate_proof(
    proof: ActorAuthorizationProof,
    *,
    tenant_id: uuid.UUID,
    company_id: uuid.UUID,
    user_id: uuid.UUID,
    permissions: frozenset[str],
) -> None:
    now = utcnow()
    if (
        proof.tenant_id != tenant_id
        or proof.company_id != company_id
        or proof.user_id != user_id
        or not proof.permissions <= permissions
        or proof.expires_at <= now
        or proof.generated_at > now + dt.timedelta(seconds=5)
    ):
        raise IdentitySourceUnavailableError("actor authorization is stale or has an invalid scope")


async def fetch_actor_authorization(
    settings: IdentitySourceSettings,
    *,
    tenant_id: uuid.UUID,
    company_id: uuid.UUID,
    user_id: uuid.UUID,
    permissions: frozenset[str],
) -> ActorAuthorizationProof:
    if any(value.int == 0 for value in (tenant_id, company_id, user_id)):
        raise ValidationFailedError("actor authorization requires real scope identities")
    try:
        request = ActorAuthorizationRequest(
            request_id=uuid7(), user_id=user_id, permissions=permissions
        )
        async with (
            asyncio.timeout(settings.total_timeout_seconds),
            httpx.AsyncClient(
                base_url=settings.base_url, timeout=5, follow_redirects=False, trust_env=False
            ) as client,
        ):
            raw = await _request(
                client,
                settings,
                method="POST",
                path=f"/internal/v1/tenants/{tenant_id}/companies/{company_id}/catalog-authorizations",
                body=canonical_json(request.model_dump(mode="json")),
                request_operation=REQUEST_OPERATION,
                response_operation=RESPONSE_OPERATION,
                max_response_bytes=32768,
            )
            proof = ActorAuthorizationProof.model_validate_json(raw)
        if proof.request_id != request.request_id:
            raise IdentitySourceUnavailableError("actor authorization request binding failed")
        validate_proof(
            proof,
            tenant_id=tenant_id,
            company_id=company_id,
            user_id=user_id,
            permissions=permissions,
        )
        return proof
    except (httpx.HTTPError, TimeoutError, ValueError, PlatformError) as exc:
        raise IdentitySourceUnavailableError(
            "current actor authorization could not be verified"
        ) from exc


async def require_job_actor(
    db: AsyncSession,
    proof: ActorAuthorizationProof,
    *,
    company_id: uuid.UUID,
    user_id: uuid.UUID,
    permissions: frozenset[str],
) -> Actor:
    """Use only proofs returned by fetch_actor_authorization, never persisted job grants.

    Call for every chunk and again before commit. No HTTP runs inside this DB
    transaction. The source lock prevents a local policy transition mid-command;
    exact version agreement makes a detected newer revocation retry, not widen.
    """
    tenant = require_current_tenant()
    validate_proof(
        proof, tenant_id=tenant, company_id=company_id, user_id=user_id, permissions=permissions
    )
    checkpoint = await require_identity_context(db, company_id)
    if checkpoint.source_version != proof.source_version:
        raise IdentitySourceUnavailableError("actor authorization and Identity context must agree")
    if not permissions <= proof.permissions:
        raise PermissionDeniedError(
            "initiating actor no longer holds the required company permissions"
        )
    return Actor(
        tenant_id=tenant,
        user_id=user_id,
        grants=(
            Grant(
                permissions=proof.permissions,
                scope=Scope("company", company_id),
                valid_from=proof.generated_at.date(),
                valid_to=proof.expires_at.date(),
            ),
        ),
    )
