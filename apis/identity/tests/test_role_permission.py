"""``role_permission`` — the composite foreign key, and the absent one.

Two constraints carry this table. ``permission_key`` has **no** foreign key, because
permissions are code (CLAUDE.md invariant 13), and the compensating control is the boot
check tested here against the shipped catalogue. The composite FK
``(role_id, tenant_id)`` → ``role (id, tenant_id)`` is the one that stops a tenant
attaching a permission row to another tenant's role — the escalation this table would
otherwise permit, since it is the row that decides what a role grants.
"""

from __future__ import annotations

import uuid

import pytest
from billing_platform.constants import SCOPE_ALL
from billing_platform.db.tenant_context import TenantContextError, tenant_scope, unfiltered
from billing_platform.ids import uuid7
from billing_platform.permissions import PERMISSIONS, assert_known_permission
from billing_platform.testing import table_of
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from identity.models import RolePermission, Tenant
from tests.factories import (
    build_role,
    build_role_permission,
    seed_system_role,
    seed_two_tenants,
)


async def _one_role_per_tenant(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> tuple[uuid.UUID, uuid.UUID]:
    role_a, role_b = uuid7(), uuid7()
    await seed_two_tenants(session, tenant_a, tenant_b)
    with unfiltered():
        session.add_all(
            [
                build_role(tenant_id=tenant_a, role_id=role_a, key="alpha_clerk"),
                build_role(tenant_id=tenant_b, role_id=role_b, key="beta_clerk"),
            ]
        )
        await session.commit()
    return role_a, role_b


# --- the isolation pattern, with the sentinel exception ------------------------


async def test_a_tenant_sees_the_system_grants_and_not_another_tenants(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """``__tenant_shared__`` follows ``role``: without it the twelve shipped roles resolve
    to the empty permission set — every route denying every actor, which is safe and
    completely unusable."""
    role_a, role_b = await _one_role_per_tenant(session, tenant_a, tenant_b)
    await seed_system_role(session, key="billing_clerk", permission_key="invoice.post")

    with unfiltered():
        session.add_all(
            [
                build_role_permission(
                    tenant_id=tenant_a, role_id=role_a, permission_key="invoice.create"
                ),
                build_role_permission(
                    tenant_id=tenant_b, role_id=role_b, permission_key="period.close"
                ),
            ]
        )
        await session.commit()

    with tenant_scope(tenant_a):
        keys = sorted(
            (await session.execute(select(RolePermission.permission_key))).scalars().all()
        )

    assert keys == ["invoice.create", "invoice.post"]


async def test_the_other_tenants_grant_is_not_reachable_by_id(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """Reading which permissions another tenant's roles carry is a map of their internal
    controls — who can approve, who can close a period."""
    role_a, role_b = await _one_role_per_tenant(session, tenant_a, tenant_b)
    theirs = build_role_permission(tenant_id=tenant_b, role_id=role_b)

    with unfiltered():
        session.add_all([theirs, build_role_permission(tenant_id=tenant_a, role_id=role_a)])
        await session.commit()

    with tenant_scope(tenant_a):
        found = (
            await session.execute(select(RolePermission).where(RolePermission.id == theirs.id))
        ).scalar_one_or_none()
        counted = (await session.execute(select(func.count(RolePermission.id)))).scalar_one()

    assert found is None
    assert counted == 1


async def test_a_grant_query_with_no_tenant_in_context_raises(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    role_a, _ = await _one_role_per_tenant(session, tenant_a, tenant_b)

    with unfiltered():
        session.add(build_role_permission(tenant_id=tenant_a, role_id=role_a))
        await session.commit()

    with pytest.raises(TenantContextError):
        await session.execute(select(RolePermission))


async def test_every_tenant_grant_resolves_to_a_real_tenant(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """§1.4's compensating control, with the sentinel excluded as on ``role``."""
    role_a, role_b = await _one_role_per_tenant(session, tenant_a, tenant_b)
    await seed_system_role(session)

    with unfiltered():
        session.add_all(
            [
                build_role_permission(tenant_id=tenant_a, role_id=role_a),
                build_role_permission(tenant_id=tenant_b, role_id=role_b),
            ]
        )
        await session.commit()

        tenants = set((await session.execute(select(Tenant.id))).scalars().all())
        owners = set((await session.execute(select(RolePermission.tenant_id))).scalars().all())

    assert SCOPE_ALL in owners
    assert owners - {SCOPE_ALL} <= tenants


# --- the composite foreign key ------------------------------------------------


async def test_a_grant_cannot_be_attached_to_another_tenants_role(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """**The load-bearing test in this file.** The row is well-formed — a real role, a
    real tenant, a real permission — and it is refused because the two disagree. With a
    plain FK to ``role.id`` it would insert, and tenant A would then have written what
    tenant B's role grants."""
    _, role_b = await _one_role_per_tenant(session, tenant_a, tenant_b)

    with unfiltered():
        session.add(build_role_permission(tenant_id=tenant_a, role_id=role_b))
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


async def test_a_tenant_grant_cannot_claim_to_be_a_system_grant(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """The same constraint in the direction that matters most: a row at ``SCOPE_ALL``
    pointing at a tenant's role would be visible to **every** tenant, and would grant
    them whatever it names."""
    role_a, _ = await _one_role_per_tenant(session, tenant_a, tenant_b)

    with unfiltered():
        session.add(build_role_permission(tenant_id=SCOPE_ALL, role_id=role_a))
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


async def test_a_grant_must_belong_to_a_real_role(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    await _one_role_per_tenant(session, tenant_a, tenant_b)

    with unfiltered():
        session.add(build_role_permission(tenant_id=tenant_a, role_id=uuid7()))
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


async def test_one_role_cannot_grant_the_same_permission_twice(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """Two rows for one pair make "does this role grant it" depend on which is read, and
    make revoking it a loop somebody has to remember to finish."""
    role_a, _ = await _one_role_per_tenant(session, tenant_a, tenant_b)

    with unfiltered():
        session.add(
            build_role_permission(
                tenant_id=tenant_a, role_id=role_a, permission_key="invoice.create"
            )
        )
        await session.commit()

        session.add(
            build_role_permission(
                tenant_id=tenant_a, role_id=role_a, permission_key="invoice.create"
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


async def test_two_roles_may_grant_the_same_permission(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """Roles are additive (docs/roles-permissions.md §1.1), so overlap is normal — a
    unique on ``permission_key`` alone would allow exactly one role to grant each key."""
    role_a, role_b = await _one_role_per_tenant(session, tenant_a, tenant_b)

    with unfiltered():
        session.add_all(
            [
                build_role_permission(
                    tenant_id=tenant_a, role_id=role_a, permission_key="invoice.read"
                ),
                build_role_permission(
                    tenant_id=tenant_b, role_id=role_b, permission_key="invoice.read"
                ),
            ]
        )
        await session.commit()

        counted = (await session.execute(select(func.count(RolePermission.id)))).scalar_one()

    assert counted == 2


# --- permissions are code -----------------------------------------------------


def test_permission_key_carries_no_foreign_key() -> None:
    """There is no ``permission`` table (CLAUDE.md invariant 13). A table would make the
    key set user-editable and nothing about it could be checked before a request
    arrives."""
    assert table_of(RolePermission).c.permission_key.foreign_keys == set()


async def test_the_column_holds_every_key_in_the_catalogue(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """``VARCHAR(80)``, checked against the whole shipped catalogue rather than the
    longest key today: MariaDB truncates a too-long value on write rather than erroring,
    and a truncated key matches nothing — a role that silently grants less than it
    says."""
    role_a, _ = await _one_role_per_tenant(session, tenant_a, tenant_b)

    with unfiltered():
        session.add_all(
            [
                build_role_permission(tenant_id=tenant_a, role_id=role_a, permission_key=key)
                for key in sorted(PERMISSIONS)
            ]
        )
        await session.commit()

    with tenant_scope(tenant_a):
        stored = set((await session.execute(select(RolePermission.permission_key))).scalars().all())

    assert stored == set(PERMISSIONS)


async def test_a_stored_key_absent_from_the_catalogue_fails_the_boot_check(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """**The exit criterion** (docs/identity-db-plan.md, Phase 5), and the compensating
    control for the missing foreign key. The database accepts the row — that is the
    trade-off invariant 13 makes — and startup refuses to come up, because a role
    granting a key no code recognizes grants nothing, silently, forever."""
    role_a, _ = await _one_role_per_tenant(session, tenant_a, tenant_b)

    with unfiltered():
        session.add(
            build_role_permission(
                tenant_id=tenant_a, role_id=role_a, permission_key="invoice.publish"
            )
        )
        await session.commit()

    with tenant_scope(tenant_a):
        stored = (await session.execute(select(RolePermission.permission_key))).scalars().all()

    with pytest.raises(ValueError, match="not in the code catalogue"):
        for key in stored:
            assert_known_permission(key, named_by="a stored role_permission row")


def test_the_table_has_no_lifecycle_switch_because_revoking_is_a_delete() -> None:
    """Rule 4.12. Revoking a permission from a role removes the row; a deactivated row
    left behind would still occupy the unique key and silently refuse the re-grant. What
    the change *was* lives in the audit trail, which is where history belongs."""
    columns = set(table_of(RolePermission).c.keys())

    assert not columns & {"status", "is_active", "valid_from", "valid_to"}
