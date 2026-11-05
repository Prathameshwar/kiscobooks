from __future__ import annotations

import datetime as dt
import json
import uuid
from typing import Any

import httpx
import pytest
from billing_platform.actor_authorization import ActorAuthorizationProof
from billing_platform.authz import ScopePath
from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.errors import PermissionDeniedError, ValidationFailedError
from billing_platform.ids import uuid7
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.tasks import actor_authorization as consumer
from catalog.tasks.identity_source import IdentitySourceUnavailableError
from catalog.tasks.projections import activate_snapshot
from tests.source_factories import snapshot
from tests.test_identity_source_client import settings


def proof(
    tenant: uuid.UUID, company: uuid.UUID, user: uuid.UUID, **changes: Any
) -> ActorAuthorizationProof:
    now = utcnow()
    return ActorAuthorizationProof.model_validate(
        {
            "request_id": uuid7(),
            "tenant_id": tenant,
            "company_id": company,
            "user_id": user,
            "source_version": 1,
            "generated_at": now,
            "expires_at": min(
                now + dt.timedelta(seconds=30),
                dt.datetime.combine(now.date() + dt.timedelta(days=1), dt.time(), dt.UTC),
            ),
            "permissions": ["unit.manage"],
            **changes,
        }
    )


async def test_job_actor_is_company_scoped_and_rechecks_current_checkpoint(
    session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    company, user = uuid7(), uuid7()
    verified = proof(tenant_a, company, user)
    with tenant_scope(tenant_a):
        await session.begin()
        source = snapshot(tenant_a, company)
        checkpoint = await activate_snapshot(session, source)
        verified = verified.model_copy(update={"source_version": checkpoint.source_version})
        actor = await consumer.require_job_actor(
            session,
            verified,
            company_id=company,
            user_id=user,
            permissions=frozenset({"unit.manage"}),
        )
        assert actor.user_id == user and actor.allows_scope(
            "unit.manage", target=ScopePath(company_id=company)
        )
        assert not actor.allows_scope("unit.manage", target=ScopePath(company_id=uuid7()))
        with pytest.raises(PermissionDeniedError):
            await consumer.require_job_actor(
                session,
                verified.model_copy(update={"permissions": frozenset()}),
                company_id=company,
                user_id=user,
                permissions=frozenset({"unit.manage"}),
            )
        checkpoint.source_version += 1
        await session.flush()
        with pytest.raises(IdentitySourceUnavailableError, match="agree"):
            await consumer.require_job_actor(
                session,
                verified,
                company_id=company,
                user_id=user,
                permissions=frozenset({"unit.manage"}),
            )
    for changes in (
        {"tenant_id": uuid7()},
        {"company_id": uuid7()},
        {"user_id": uuid7()},
        {"permissions": frozenset({"unit.read"})},
        {"expires_at": utcnow() - dt.timedelta(seconds=1)},
        {"generated_at": utcnow() + dt.timedelta(seconds=6)},
    ):
        with pytest.raises(IdentitySourceUnavailableError):
            consumer.validate_proof(
                verified.model_copy(update=changes),
                tenant_id=tenant_a,
                company_id=company,
                user_id=user,
                permissions=frozenset({"unit.manage"}),
            )


async def test_client_validates_request_binding_and_returns_known_empty_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant, company, user = uuid7(), uuid7(), uuid7()
    mode = "valid"

    async def response(*args: Any, **kwargs: Any) -> bytes:
        assert kwargs["max_response_bytes"] == 32768
        body = json.loads(kwargs["body"])
        result = proof(tenant, company, user, request_id=body["request_id"], permissions=[])
        if mode == "other_request":
            result = result.model_copy(update={"request_id": uuid7()})
        elif mode == "overscoped":
            result = result.model_copy(update={"permissions": frozenset({"unit.read"})})
        elif mode == "timeout":
            raise TimeoutError
        elif mode == "http":
            raise httpx.ConnectError("offline")
        elif mode == "malformed":
            return b"{}"
        return result.model_dump_json().encode()

    monkeypatch.setattr(consumer, "_request", response)

    async def fetch() -> ActorAuthorizationProof:
        return await consumer.fetch_actor_authorization(
            settings(),
            tenant_id=tenant,
            company_id=company,
            user_id=user,
            permissions=frozenset({"unit.manage"}),
        )

    assert not (await fetch()).permissions
    for failure_mode in ("other_request", "overscoped", "timeout", "http", "malformed"):
        mode = failure_mode
        with pytest.raises(IdentitySourceUnavailableError):
            await fetch()
    with pytest.raises(ValidationFailedError):
        await consumer.fetch_actor_authorization(
            settings(),
            tenant_id=uuid.UUID(int=0),
            company_id=company,
            user_id=user,
            permissions=frozenset({"unit.manage"}),
        )
