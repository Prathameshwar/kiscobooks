"""``role`` — the tenant filter's one exception, and the two departures from §5.1.

The exit criterion for this phase names the test in the middle of this file:
``test_a_tenant_sees_the_system_roles_and_not_another_tenants``. The session filter is
``tenant_id = :current OR tenant_id = SCOPE_ALL`` for this table, and both halves have to
be proved — a naive filter hides all twelve shipped roles, and a filter that trusted
``__tenant_shared__`` to mean "shared" would show every tenant every other tenant's.

The two departures from docs/identity-schema.md §5.1, both asserted here: ``tenant_id`` is
NOT NULL with ``SCOPE_ALL`` standing in for the doc's NULL, and there is no ``is_system``
column — it is derived, so it cannot disagree with ``tenant_id``.
"""

from __future__ import annotations

import uuid

import pytest
from billing_platform.constants import SCOPE_ALL
from billing_platform.db.tenant_context import TenantContextError, tenant_scope, unfiltered
from billing_platform.ids import uuid7
from billing_platform.testing import table_of
from sqlalchemy import UniqueConstraint, func, select
from sqlalchemy.dialects import mysql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.schema import CreateTable

from identity.models import SCOPE_HINTS, Role, Tenant
from tests.factories import build_role, seed_system_role, seed_two_tenants

# --- the isolation pattern, with the sentinel exception ------------------------


async def test_a_tenant_sees_the_system_roles_and_not_another_tenants(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """**The exit criterion** (docs/identity-db-plan.md, Phase 5). Three rows exist: a
    shipped role at ``SCOPE_ALL``, tenant A's clone of it, and tenant B's own. Scoped to
    A, exactly the first two are visible."""
    await seed_two_tenants(session, tenant_a, tenant_b)
    await seed_system_role(session, key="billing_clerk")

    with unfiltered():
        session.add_all(
            [
                build_role(tenant_id=tenant_a, key="alpha_clerk"),
                build_role(tenant_id=tenant_b, key="beta_clerk"),
            ]
        )
        await session.commit()

    with tenant_scope(tenant_a):
        keys = sorted((await session.execute(select(Role.key))).scalars().all())

    assert keys == ["alpha_clerk", "billing_clerk"]


async def test_the_other_tenants_role_is_not_reachable_by_id(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """The shared-row exception widens the filter, and this is the test that it was
    widened only as far as the sentinel."""
    await seed_two_tenants(session, tenant_a, tenant_b)
    theirs = build_role(tenant_id=tenant_b, key="beta_clerk")

    with unfiltered():
        session.add_all([theirs, build_role(tenant_id=tenant_a, key="alpha_clerk")])
        await session.commit()

    with tenant_scope(tenant_a):
        found = (
            await session.execute(select(Role).where(Role.id == theirs.id))
        ).scalar_one_or_none()
        counted = (await session.execute(select(func.count(Role.id)))).scalar_one()

    assert found is None
    assert counted == 1


async def test_a_role_query_with_no_tenant_in_context_raises(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """The exception widens the filter; it does not make the table exempt from needing a
    tenant in context (docs/identity-schema.md §0.3)."""
    await seed_two_tenants(session, tenant_a, tenant_b)
    await seed_system_role(session)

    with pytest.raises(TenantContextError):
        await session.execute(select(Role))


async def test_every_tenant_role_resolves_to_a_real_tenant(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """§1.4's compensating control, with the sentinel excluded: ``SCOPE_ALL`` is the one
    ``tenant_id`` in this schema that deliberately has no ``tenant`` row, and a check
    that did not exclude it would fail on every shipped role."""
    await seed_two_tenants(session, tenant_a, tenant_b)
    await seed_system_role(session)

    with unfiltered():
        session.add(build_role(tenant_id=tenant_a, key="alpha_clerk"))
        await session.commit()

        tenants = set((await session.execute(select(Tenant.id))).scalars().all())
        owners = set((await session.execute(select(Role.tenant_id))).scalars().all())

    assert SCOPE_ALL in owners
    assert owners - {SCOPE_ALL}
    assert owners - {SCOPE_ALL} <= tenants


# --- the unique key and the sentinel ------------------------------------------


async def test_one_tenant_cannot_hold_the_same_role_key_twice(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    await seed_two_tenants(session, tenant_a, tenant_b)

    with unfiltered():
        session.add(build_role(tenant_id=tenant_a, key="alpha_clerk"))
        await session.commit()

        session.add(build_role(tenant_id=tenant_a, key="alpha_clerk", name="Another"))
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


async def test_a_system_role_key_cannot_be_shipped_twice(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """**The reason ``tenant_id`` is NOT NULL** (docs/identity-db-plan.md §2). With the
    doc's nullable column, MariaDB would treat the two NULLs as distinct and
    ``billing_clerk`` could be shipped any number of times — each copy a different
    permission set, resolved by whichever the seed read last."""
    await seed_two_tenants(session, tenant_a, tenant_b)
    await seed_system_role(session, key="billing_clerk")

    with unfiltered():
        session.add(build_role(tenant_id=SCOPE_ALL, key="billing_clerk"))
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


async def test_a_tenant_may_reuse_a_system_role_key_for_its_own_clone(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """The key is unique per owner, so a tenant editing a copy of ``billing_clerk`` keeps
    the name it recognizes rather than being pushed into ``billing_clerk_2``."""
    await seed_two_tenants(session, tenant_a, tenant_b)
    system_role_id = await seed_system_role(session, key="billing_clerk")

    with unfiltered():
        session.add(
            build_role(tenant_id=tenant_a, key="billing_clerk", cloned_from_role_id=system_role_id)
        )
        await session.commit()

    with tenant_scope(tenant_a):
        rows = (await session.execute(select(Role).where(Role.key == "billing_clerk"))).scalars()
        owners = sorted(str(row.tenant_id) for row in rows)

    assert owners == sorted([str(SCOPE_ALL), str(tenant_a)])


async def test_a_clone_must_point_at_a_real_role(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    await seed_two_tenants(session, tenant_a, tenant_b)

    with unfiltered():
        session.add(build_role(tenant_id=tenant_a, cloned_from_role_id=uuid7()))
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


# --- is_system is derived -----------------------------------------------------


def test_there_is_no_is_system_column() -> None:
    """docs/identity-schema.md §5.1 lists one, and it is dropped deliberately. A stored
    flag can disagree with ``tenant_id``, and the disagreement is an escalation:
    ``is_system = false`` on a row with ``tenant_id = SCOPE_ALL`` is a platform-wide role
    a tenant may edit. Deriving it makes that state unrepresentable."""
    assert "is_system" not in table_of(Role).c.keys()


def test_is_system_is_true_exactly_when_the_owner_is_the_sentinel() -> None:
    assert build_role(tenant_id=SCOPE_ALL).is_system
    assert not build_role(tenant_id=uuid7()).is_system


async def test_a_role_read_back_still_reports_its_own_kind(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """Derived from a persisted column, so it has to survive the round trip — a property
    reading an attribute the loader did not populate would report every role as a tenant
    role."""
    await seed_two_tenants(session, tenant_a, tenant_b)
    await seed_system_role(session, key="billing_clerk")

    with unfiltered():
        session.add(build_role(tenant_id=tenant_a, key="alpha_clerk"))
        await session.commit()
        session.expunge_all()

    with tenant_scope(tenant_a):
        rows = (await session.execute(select(Role).order_by(Role.key))).scalars().all()

    assert [(row.key, row.is_system) for row in rows] == [
        ("alpha_clerk", False),
        ("billing_clerk", True),
    ]


# --- the reserved words -------------------------------------------------------


def test_the_table_and_column_names_are_quoted_for_mariadb() -> None:
    """``role`` and ``key`` are both MariaDB reserved words. SQLAlchemy quotes them in
    generated SQL; the raw DDL in ``dbs/identity/versions/0016`` does not get that for
    free, so this compiles the model under the mysql dialect and asserts the spelling the
    migration has to match. Unquoted, revision 0016 is a syntax error at migrate time."""
    ddl = str(CreateTable(table_of(Role)).compile(dialect=mysql.dialect()))

    assert "CREATE TABLE `role`" in ddl
    assert "`key` VARCHAR(60) NOT NULL" in ddl
    assert "UNIQUE (tenant_id, `key`)" in ddl


def test_the_composite_unique_exists_to_parent_the_permission_foreign_key() -> None:
    """``role_permission``'s composite FK references ``(id, tenant_id)``, and InnoDB
    requires the referenced columns to lead an index on the parent. Declared UNIQUE
    rather than as a plain index because ``id`` is the primary key, so the pair is
    trivially unique and saying so is more honest than relying on InnoDB's laxer rule."""
    key = next(
        constraint
        for constraint in table_of(Role).constraints
        if isinstance(constraint, UniqueConstraint) and constraint.name == "uq_role_id_tenant_id"
    )

    assert [column.name for column in key.columns] == ["id", "tenant_id"]


def test_the_documented_scope_hints_are_the_ones_the_code_knows() -> None:
    """UI guidance only. What a grant reaches is ``role_assignment``'s own scope — reading
    this as the check would put authorization in a hint column."""
    assert SCOPE_HINTS == {"platform", "tenant", "company", "department"}


def test_the_table_declares_exactly_one_lifecycle_mechanism() -> None:
    """Rule 4.12. ``is_active`` false means not assignable to anyone new; it never
    invalidates the assignments already made, which is ``role_assignment``'s own
    ``is_active``."""
    columns = set(table_of(Role).c.keys())

    assert "is_active" in columns
    assert not columns & {"status", "valid_from", "valid_to"}
