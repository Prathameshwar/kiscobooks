"""Two-tenant isolation for every Phase 6 table (CLAUDE.md §7, the highest-value test).

Seed a row for each of two tenants, query scoped to one, and assert the other's row is
absent — the session-level filter is what guarantees it, and a forgotten WHERE is a
cross-tenant breach.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from billing_platform.db.tenant_context import tenant_scope, unfiltered
from billing_platform.ids import uuid7
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.models import Department, Membership, UserGroup, UserGroupMember
from tests.factories import (
    build_department,
    build_membership,
    build_user,
    build_user_group,
    build_user_group_member,
    seed_two_companies,
)

pytestmark = pytest.mark.asyncio


async def _count(session: AsyncSession, model: Any, tenant_id: uuid.UUID) -> int:
    with tenant_scope(tenant_id):
        return int(await session.scalar(select(func.count(model.id))) or 0)


async def test_department_isolation(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    company_a, company_b = await seed_two_companies(session, tenant_a, tenant_b)
    with unfiltered():
        session.add(build_department(tenant_id=tenant_a, company_id=company_a, code="A"))
        session.add(build_department(tenant_id=tenant_b, company_id=company_b, code="B"))
        await session.commit()
    assert await _count(session, Department, tenant_a) == 1
    assert await _count(session, Department, tenant_b) == 1
    with tenant_scope(tenant_a):
        rows = (await session.scalars(select(Department))).all()
    assert {r.tenant_id for r in rows} == {tenant_a}


async def test_user_group_isolation(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    await seed_two_companies(session, tenant_a, tenant_b)
    with unfiltered():
        session.add(build_user_group(tenant_id=tenant_a, code="finance"))
        session.add(build_user_group(tenant_id=tenant_b, code="finance"))
        await session.commit()
    assert await _count(session, UserGroup, tenant_a) == 1
    assert await _count(session, UserGroup, tenant_b) == 1


async def test_user_group_member_isolation(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    await seed_two_companies(session, tenant_a, tenant_b)
    ua, ga = uuid7(), uuid7()
    ub, gb = uuid7(), uuid7()
    with unfiltered():
        session.add(build_user(tenant_id=tenant_a, user_id=ua, email="a@alpha.example"))
        session.add(build_user(tenant_id=tenant_b, user_id=ub, email="b@beta.example"))
        session.add(build_user_group(tenant_id=tenant_a, group_id=ga))
        session.add(build_user_group(tenant_id=tenant_b, group_id=gb))
        await session.flush()
        session.add(build_user_group_member(tenant_id=tenant_a, user_group_id=ga, user_id=ua))
        session.add(build_user_group_member(tenant_id=tenant_b, user_group_id=gb, user_id=ub))
        await session.commit()
    assert await _count(session, UserGroupMember, tenant_a) == 1
    assert await _count(session, UserGroupMember, tenant_b) == 1


async def test_membership_isolation(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    company_a, company_b = await seed_two_companies(session, tenant_a, tenant_b)
    ua, ub = uuid7(), uuid7()
    with unfiltered():
        session.add(build_user(tenant_id=tenant_a, user_id=ua, email="a@alpha.example"))
        session.add(build_user(tenant_id=tenant_b, user_id=ub, email="b@beta.example"))
        await session.flush()
        session.add(build_membership(tenant_id=tenant_a, user_id=ua, company_id=company_a))
        session.add(build_membership(tenant_id=tenant_b, user_id=ub, company_id=company_b))
        await session.commit()
    assert await _count(session, Membership, tenant_a) == 1
    assert await _count(session, Membership, tenant_b) == 1
