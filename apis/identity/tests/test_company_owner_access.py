"""Company creation grants only its creator the fixed roles at the new company's scope."""

from __future__ import annotations

import uuid

import httpx
import pytest
from billing_platform.authz import Grant, Scope, ScopePath, has_permission
from billing_platform.constants import SCOPE_ALL
from billing_platform.db import tenant_scope, unfiltered
from billing_platform.db.platform_models import Outbox
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, PermissionDeniedError
from billing_platform.ids import uuid7
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.api.auth import Actor
from identity.models import CatalogSourceEnrollment, Company, Role, RoleAssignment, RolePermission
from identity.seeds.roles import seed_system_roles
from identity.services.company_owner import grant_company_creator
from identity.services.login import live_grants
from tests.api_support import actor_headers, grant
from tests.factories import (
    build_company,
    build_role,
    build_role_permission,
    build_user,
    seed_two_tenants,
)
from tests.test_api_companies import _valid_company_body

pytestmark = pytest.mark.asyncio


async def test_create_grants_only_the_new_company_and_audits_it(
    client: httpx.AsyncClient, session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    await seed_two_tenants(session, tenant_a, tenant_b)
    await seed_system_roles(session)
    user_id = uuid7()
    with tenant_scope(tenant_a):
        session.add(build_user(tenant_id=tenant_a, user_id=user_id))
        await session.commit()
    headers = actor_headers(
        tenant_id=tenant_a, user_id=user_id, grants=[grant(["company.create", "company.read"])]
    )
    response = await client.post("/v1/companies", json=_valid_company_body(), headers=headers)
    assert response.status_code == 201, response.text
    company_id = uuid.UUID(response.json()["id"])
    with tenant_scope(tenant_a):
        assignments = list(await session.scalars(select(RoleAssignment)))
        assert len(assignments) == 2
        by_key = {(await session.get(Role, row.role_id)).key: row for row in assignments}
        assert set(by_key) == {"company_admin", "stock_operator"}
        assignment = by_key["company_admin"]
        assert assignment is not None
        role = await session.get(Role, assignment.role_id)
        assert role is not None and role.is_system and role.key == "company_admin"
        assert assignment.subject_id == user_id and assignment.subject_type == "user"
        assert assignment.scope_type == "company" and assignment.scope_id == company_id
        assert assignment.is_active and assignment.granted_by == user_id
        assert all(
            row.subject_id == user_id and row.scope_type == "company" and row.scope_id == company_id
            for row in assignments
        )
        evidence = await session.scalar(
            select(Outbox).where(Outbox.event_type == "role_assignment.granted")
        )
        assert evidence is not None
        assert evidence.payload["category"] == "security"
        assert evidence.payload["company_id"] == str(company_id)
        grants, _ = await live_grants(session, user_id)
        assert has_permission(
            grants, "item.read", target=ScopePath(company_id=company_id), on_date=utcnow().date()
        )
        assert has_permission(
            grants, "report.read", target=ScopePath(company_id=company_id), on_date=utcnow().date()
        )
        for permission in ("vouchers.create", "vouchers.post", "accounting.stock.post"):
            assert has_permission(
                grants, permission, target=ScopePath(company_id=company_id), on_date=utcnow().date()
            )
            assert not has_permission(
                grants, permission, target=ScopePath(company_id=uuid7()), on_date=utcnow().date()
            )
        assert not has_permission(
            grants,
            "vouchers.approve",
            target=ScopePath(company_id=company_id),
            on_date=utcnow().date(),
        )
        assert not has_permission(
            grants, "item.read", target=ScopePath(company_id=uuid7()), on_date=utcnow().date()
        )
    with tenant_scope(tenant_b):
        assert await session.scalar(select(func.count(RoleAssignment.id))) == 0


@pytest.mark.parametrize(
    "role_state",
    [
        "missing",
        "inactive",
        "tenant_copy",
        "incomplete",
        "unexpected",
        "stock_inactive",
        "stock_incomplete",
    ],
)
async def test_unavailable_system_role_rolls_back_company_and_audits(
    client: httpx.AsyncClient,
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
    role_state: str,
) -> None:
    await seed_two_tenants(session, tenant_a, tenant_b)
    if role_state != "missing":
        await seed_system_roles(session)
        with unfiltered():
            role = await session.scalar(
                select(Role).where(
                    Role.key
                    == ("stock_operator" if role_state.startswith("stock_") else "company_admin")
                )
            )
            assert role is not None
            if role_state in {"inactive", "tenant_copy", "stock_inactive"}:
                role.is_active = False
            if role_state in {"incomplete", "stock_incomplete"}:
                permission = await session.scalar(
                    select(RolePermission).where(
                        RolePermission.role_id == role.id,
                        RolePermission.permission_key == "item.read",
                    )
                )
                assert permission is not None
                await session.delete(permission)
            elif role_state == "unexpected":
                session.add(
                    build_role_permission(
                        tenant_id=SCOPE_ALL, role_id=role.id, permission_key="ledger.post_journal"
                    )
                )
            elif role_state == "tenant_copy":
                session.add(build_role(tenant_id=tenant_a, key="company_admin"))
            await session.commit()
    headers = actor_headers(
        tenant_id=tenant_a, user_id=uuid7(), grants=[grant(["company.create", "company.read"])]
    )
    response = await client.post("/v1/companies", json=_valid_company_body(), headers=headers)
    assert response.status_code == 409, response.text
    with tenant_scope(tenant_a):
        assert await session.scalar(select(func.count(CatalogSourceEnrollment.id))) == 0
        assert await session.scalar(select(func.count(Company.id))) == 0
        assert await session.scalar(select(func.count(RoleAssignment.id))) == 0
        assert await session.scalar(select(func.count(Outbox.id))) == 0


@pytest.mark.parametrize("revoked_role", ["company_admin", "stock_operator"])
async def test_legacy_repair_is_idempotent_and_never_restores_a_revoked_assignment(
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
    revoked_role: str,
) -> None:
    await seed_two_tenants(session, tenant_a, tenant_b)
    await seed_system_roles(session)
    creator = uuid7()
    current = Actor(
        tenant_a,
        creator,
        (
            Grant(
                frozenset({"company.create"}),
                Scope("tenant", SCOPE_ALL),
                utcnow().date(),
                None,
                True,
            ),
        ),
    )
    with tenant_scope(tenant_a):
        company = build_company(tenant_id=tenant_a, created_by=creator)
        session.add(company)
        await session.commit()
        assignment = await grant_company_creator(session, current, company.id)
        assert (await grant_company_creator(session, current, company.id)).id == assignment.id
        assert await session.scalar(select(func.count(RoleAssignment.id))) == 2
        assert await session.scalar(select(func.count(Outbox.id))) == 2
        revoked = await session.scalar(
            select(RoleAssignment)
            .join(Role, Role.id == RoleAssignment.role_id)
            .where(Role.key == revoked_role)
        )
        revoked.is_active = False
        await session.flush()
        with pytest.raises(ConflictError):
            await grant_company_creator(session, current, company.id)
        assert await session.scalar(select(func.count(Outbox.id))) == 2


@pytest.mark.parametrize("reason", ["other_creator", "other_tenant", "inactive", "scoped_create"])
async def test_owner_bootstrap_cannot_be_used_for_another_company_or_tenant(
    session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
    reason: str,
) -> None:
    await seed_two_tenants(session, tenant_a, tenant_b)
    await seed_system_roles(session)
    creator = uuid7()
    with unfiltered():
        company = build_company(
            tenant_id=tenant_b if reason == "other_tenant" else tenant_a,
            created_by=uuid7() if reason == "other_creator" else creator,
            status="closed" if reason == "inactive" else "active",
        )
        session.add(company)
        await session.commit()
    current = Actor(
        tenant_a,
        creator,
        (
            Grant(
                frozenset({"company.create"}),
                Scope("company", company.id)
                if reason == "scoped_create"
                else Scope("tenant", SCOPE_ALL),
                utcnow().date(),
                None,
                True,
            ),
        ),
    )
    with tenant_scope(tenant_a):
        with pytest.raises(PermissionDeniedError):
            await grant_company_creator(session, current, company.id)
    with unfiltered():
        assert await session.scalar(select(func.count(RoleAssignment.id))) == 0
        assert await session.scalar(select(func.count(Outbox.id))) == 0
