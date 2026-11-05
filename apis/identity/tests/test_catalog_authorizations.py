from __future__ import annotations

import datetime as dt
import time
import uuid

import httpx
import pytest
from billing_platform.actor_authorization import (
    REQUEST_OPERATION,
    RESPONSE_OPERATION,
    ActorAuthorizationProof,
    ActorAuthorizationRequest,
)
from billing_platform.constants import SCOPE_ALL
from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.errors import PermissionDeniedError
from billing_platform.idempotency import canonical_json
from billing_platform.ids import uuid7
from billing_platform.service_auth import (
    ServiceKey,
    service_request_bytes,
    service_response_bytes,
    sign_service_body,
    verify_service_body,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.models import Company, User
from identity.models.catalog_source import CatalogSourceGeneration
from identity.tasks import catalog_authorizations as owner
from tests.factories import (
    build_role,
    build_role_assignment,
    build_role_permission,
    build_user,
    build_user_group,
    build_user_group_member,
    seed_two_companies,
)
from tests.test_catalog_sources import REQUEST_SECRET, RESPONSE_SECRET, configure


def route(tenant: uuid.UUID, company: uuid.UUID) -> str:
    return f"/internal/v1/tenants/{tenant}/companies/{company}/catalog-authorizations"


def headers(path: str, body: bytes, operation: str = REQUEST_OPERATION) -> dict[str, str]:
    key = ServiceKey("catalog", "identity", frozenset({operation}), REQUEST_SECRET)
    stamp = int(time.time())
    return {
        "content-type": "application/json",
        "x-source-key-id": "current",
        "x-source-issued-at": str(stamp),
        "x-source-signature": sign_service_body(
            key,
            key_id="current",
            operation=operation,
            timestamp=stamp,
            body=service_request_bytes(method="POST", path=path, query="", body=body),
        ),
    }


async def seed(
    session: AsyncSession, tenant: uuid.UUID, other: uuid.UUID
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    company, foreign = await seed_two_companies(session, tenant, other)
    with tenant_scope(tenant):
        user = build_user(tenant_id=tenant, user_type="tenant_admin")
        session.add_all([user, CatalogSourceGeneration(tenant_id=tenant, version=7)])
        await session.commit()
    return company, foreign, user.id


async def test_service_opt_in_scope_signatures_and_bounded_response(
    app: object,
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    company, foreign, user = await seed(session, tenant_a, tenant_b)
    application = configure(app, [(tenant_a, company)])
    path = route(tenant_a, company)
    body = canonical_json(
        {"request_id": str(uuid7()), "user_id": str(user), "permissions": ["unit.manage"]}
    )
    assert (await client.post(path, content=body)).status_code == 401
    # Existing snapshot keys are not automatically permission introspection keys.
    assert (await client.post(path, content=body, headers=headers(path, body))).status_code == 401
    credential = application.state.settings.catalog_source_credentials["current"]
    application.state.settings.catalog_source_credentials["current"] = credential.model_copy(
        update={"allow_actor_authorization": True}
    )
    response = await client.post(path, content=body, headers=headers(path, body))
    assert response.status_code == 200, response.text
    proof = ActorAuthorizationProof.model_validate(response.json())
    assert not proof.permissions  # user_type and role names never grant rights.
    assert proof.source_version == 7 and proof.user_id == user
    assert response.headers["cache-control"] == "no-store"
    verify_service_body(
        {
            "current": ServiceKey(
                "identity", "catalog", frozenset({RESPONSE_OPERATION}), RESPONSE_SECRET
            )
        },
        key_id=response.headers["x-source-key-id"],
        issuer="identity",
        audience="catalog",
        operation=RESPONSE_OPERATION,
        timestamp=response.headers["x-source-issued-at"],
        signature=response.headers["x-source-signature"],
        now=int(time.time()),
        body=service_response_bytes(
            request_bytes=service_request_bytes(method="POST", path=path, query="", body=body),
            response_body=response.content,
        ),
    )
    assert (
        await client.post(
            path, content=body, headers=headers(path, body, "catalog.snapshot.create")
        )
    ).status_code == 401
    other_path = route(tenant_b, foreign)
    assert (
        await client.post(other_path, content=body, headers=headers(other_path, body))
    ).status_code == 403
    for payload in (
        {},
        {"request_id": str(uuid7()), "user_id": str(user), "permissions": ["invoice.post"]},
    ):
        raw = canonical_json(payload)
        assert (await client.post(path, content=raw, headers=headers(path, raw))).status_code == 422
    with tenant_scope(tenant_a):
        assert await session.scalar(select(CatalogSourceGeneration.version)) == 7


async def test_native_grants_membership_revocation_scope_and_dates(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    company, _, user = await seed(session, tenant_a, tenant_b)
    today = utcnow().date()
    with tenant_scope(tenant_a):
        role = build_role(tenant_id=tenant_a)
        group = build_user_group(tenant_id=tenant_a)
        session.add_all([role, group])
        await session.flush()
        membership = build_user_group_member(
            tenant_id=tenant_a, user_group_id=group.id, user_id=user
        )
        permission = build_role_permission(
            tenant_id=tenant_a, role_id=role.id, permission_key="unit.manage"
        )
        assignment = build_role_assignment(
            tenant_id=tenant_a,
            role_id=role.id,
            subject_type="user_group",
            subject_id=group.id,
            scope_type="company",
            scope_id=company,
            valid_from=today,
        )
        session.add_all([membership, permission, assignment])
        await session.commit()
        request = ActorAuthorizationRequest(
            request_id=uuid7(), user_id=user, permissions=frozenset({"unit.manage", "unit.read"})
        )

        async def allowed() -> frozenset[str]:
            return (
                await owner.authorize_actor(session, company_id=company, request=request)
            ).permissions

        assert await allowed() == {"unit.manage"}
        for obj, field, value in [
            (group, "is_active", False),
            (role, "is_active", False),
            (assignment, "is_active", False),
            (assignment, "valid_from", today + dt.timedelta(days=1)),
            (assignment, "valid_to", today - dt.timedelta(days=1)),
            (assignment, "scope_id", uuid7()),
        ]:
            original = getattr(obj, field)
            setattr(obj, field, value)
            await session.flush()
            assert not await allowed()
            setattr(obj, field, original)
            await session.flush()
        await session.delete(membership)
        await session.flush()
        assert not await allowed()
        assignment.subject_type, assignment.subject_id = "user", user
        assignment.scope_type, assignment.scope_id = "department", company
        await session.flush()
        assert not await allowed()
        assignment.scope_type, assignment.scope_id = "tenant", SCOPE_ALL
        await session.flush()
        assert await allowed() == {"unit.manage"}
        await session.delete(permission)
        await session.flush()
        assert not await allowed()
        actor = await session.get(User, user)
        assert actor is not None
        actor.status = "suspended"
        await session.flush()
        with pytest.raises(PermissionDeniedError):
            await allowed()
        actor.status = "active"
        company_row = await session.get(Company, company)
        assert company_row is not None
        company_row.status = "suspended"
        await session.flush()
        with pytest.raises(PermissionDeniedError):
            await allowed()
        company_row.status = "active"
        with pytest.raises(PermissionDeniedError):
            await owner.authorize_actor(
                session, company_id=company, request=request.model_copy(update={"user_id": uuid7()})
            )


async def test_bounds_bootstrap_and_midnight(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    company, _, user = await seed(session, tenant_a, tenant_b)
    with tenant_scope(tenant_a):
        request = ActorAuthorizationRequest(
            request_id=uuid7(), user_id=user, permissions=frozenset({"unit.read"})
        )
        generation = await session.scalar(select(CatalogSourceGeneration))
        assert generation is not None
        await session.delete(generation)
        await session.flush()
        with pytest.raises(owner.AuthorizationUnavailableError):
            await owner.authorize_actor(session, company_id=company, request=request)
        session.add(CatalogSourceGeneration(tenant_id=tenant_a, version=8))
        await session.flush()
        now = utcnow().replace(hour=23, minute=59, second=59, microsecond=0)
        monkeypatch.setattr(owner, "utcnow", lambda: now)
        result = await owner.authorize_actor(session, company_id=company, request=request)
        assert result.expires_at - result.generated_at == dt.timedelta(seconds=1)
        group = build_user_group(tenant_id=tenant_a)
        role = build_role(tenant_id=tenant_a)
        session.add_all([group, role])
        await session.flush()
        session.add(
            build_user_group_member(tenant_id=tenant_a, user_group_id=group.id, user_id=user)
        )
        session.add(build_role_assignment(tenant_id=tenant_a, role_id=role.id, subject_id=user))
        await session.flush()
        monkeypatch.setattr(owner, "MAX_SUBJECTS", 0)
        with pytest.raises(owner.AuthorizationUnavailableError, match="membership"):
            await owner.authorize_actor(session, company_id=company, request=request)
        monkeypatch.setattr(owner, "MAX_SUBJECTS", 1000)
        monkeypatch.setattr(owner, "MAX_ASSIGNMENTS", 0)
        with pytest.raises(owner.AuthorizationUnavailableError, match="assignments"):
            await owner.authorize_actor(session, company_id=company, request=request)


async def test_permission_mutation_advances_source_barrier(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    from billing_platform.db.platform_models import Outbox

    from identity.events.catalog_source import CAPTURE_KEY

    await seed(session, tenant_a, tenant_b)
    with tenant_scope(tenant_a):
        role = build_role(tenant_id=tenant_a)
        session.add(role)
        await session.commit()
        session.info[CAPTURE_KEY] = True
        session.add(
            build_role_permission(tenant_id=tenant_a, role_id=role.id, permission_key="unit.manage")
        )
        await session.commit()
        assert await session.scalar(select(CatalogSourceGeneration.version)) == 8
        event = await session.scalar(
            select(Outbox).where(Outbox.event_type == "identity.catalog_context.changed")
        )
        assert event is not None and event.payload["records"] == []
