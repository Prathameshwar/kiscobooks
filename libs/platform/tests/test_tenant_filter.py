"""The highest-value tests in the platform.

One forgotten WHERE is a cross-tenant breach, so the filter is tested for the
positive case, the negative case, the shared-row exception, the no-tenant case,
and — most importantly — statement caching across tenants.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from billing_platform.constants import SCOPE_ALL
from billing_platform.db.tenant_context import (
    TenantContextError,
    UnfilterableStatementError,
    tenant_scope,
    unfiltered,
)
from billing_platform.ids import uuid7
from tests.models import ExemptThing, RootLike, SharedThing, TenantThing


async def _seed(session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID) -> None:
    with unfiltered():
        session.add_all(
            [
                TenantThing(id=uuid7(), tenant_id=tenant_a, name="a-one"),
                TenantThing(id=uuid7(), tenant_id=tenant_a, name="a-two"),
                TenantThing(id=uuid7(), tenant_id=tenant_b, name="b-one"),
            ]
        )
        await session.commit()


async def test_query_returns_only_the_current_tenants_rows(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    await _seed(session, tenant_a, tenant_b)

    with tenant_scope(tenant_a):
        rows = (await session.execute(select(TenantThing))).scalars().all()

    assert {r.name for r in rows} == {"a-one", "a-two"}


async def test_other_tenants_rows_are_absent(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """The canonical two-tenant isolation assertion, reused per table."""
    await _seed(session, tenant_a, tenant_b)

    with tenant_scope(tenant_a):
        rows = (await session.execute(select(TenantThing))).scalars().all()

    assert all(r.tenant_id == tenant_a for r in rows)
    assert "b-one" not in {r.name for r in rows}


async def test_fetching_another_tenants_row_by_primary_key_returns_nothing(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """Knowing the id must not be enough. This is the object-level scope case."""
    with unfiltered():
        target = TenantThing(id=uuid7(), tenant_id=tenant_b, name="b-secret")
        session.add(target)
        await session.commit()
        target_id = target.id

    with tenant_scope(tenant_a):
        found = (
            await session.execute(select(TenantThing).where(TenantThing.id == target_id))
        ).scalar_one_or_none()

    assert found is None


async def test_two_tenants_sequentially_are_not_cached(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """Proves the tenant value is a bound parameter, not baked into a cached plan.

    If the filter closed over the tenant in a way SQLAlchemy compiled once, the
    second tenant would see the first tenant's rows. Running the *same* statement
    under two tenants in sequence is the only thing that catches it.
    """
    async with factory() as session:
        with unfiltered():
            session.add_all(
                [
                    TenantThing(id=uuid7(), tenant_id=tenant_a, name="a-one"),
                    TenantThing(id=uuid7(), tenant_id=tenant_b, name="b-one"),
                ]
            )
            await session.commit()

    stmt = select(TenantThing)

    async with factory() as session:
        with tenant_scope(tenant_a):
            first = {r.name for r in (await session.execute(stmt)).scalars().all()}

    async with factory() as session:
        with tenant_scope(tenant_b):
            second = {r.name for r in (await session.execute(stmt)).scalars().all()}

    assert first == {"a-one"}
    assert second == {"b-one"}


async def test_no_tenant_in_context_raises_rather_than_returning_everything(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """Deny by default. Returning all rows would be a breach; returning none
    would hide the bug until someone reported missing data."""
    await _seed(session, tenant_a, tenant_b)

    with pytest.raises(TenantContextError):
        await session.execute(select(TenantThing))


async def test_unfiltered_is_required_to_cross_tenants(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    await _seed(session, tenant_a, tenant_b)

    with unfiltered():
        rows = (await session.execute(select(TenantThing))).scalars().all()

    assert len(rows) == 3


async def test_shared_rows_are_visible_to_every_tenant(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """The ``role`` case: system rows carry SCOPE_ALL and belong to everyone.

    A filter written as plain equality hides every system role — which is why
    ``__tenant_shared__`` exists and why it has its own test.
    """
    with unfiltered():
        session.add_all(
            [
                SharedThing(id=uuid7(), tenant_id=SCOPE_ALL, key="system_role"),
                SharedThing(id=uuid7(), tenant_id=tenant_a, key="tenant_a_role"),
                SharedThing(id=uuid7(), tenant_id=tenant_b, key="tenant_b_role"),
            ]
        )
        await session.commit()

    with tenant_scope(tenant_a):
        rows = (await session.execute(select(SharedThing))).scalars().all()

    assert {r.key for r in rows} == {"system_role", "tenant_a_role"}


async def test_exempt_table_needs_no_tenant_in_context(session: AsyncSession) -> None:
    """Reference tables are queryable with no tenant, e.g. for a signup dropdown."""
    with unfiltered():
        session.add(ExemptThing(id=uuid7(), code="IN"))
        await session.commit()

    rows = (await session.execute(select(ExemptThing))).scalars().all()
    assert [r.code for r in rows] == ["IN"]


# --- the self-tenant case: `tenant` itself ------------------------------------


async def _seed_roots(session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID) -> None:
    with unfiltered():
        session.add_all([RootLike(id=tenant_a, name="alpha"), RootLike(id=tenant_b, name="beta")])
        await session.commit()


async def test_a_self_tenant_table_returns_only_the_current_tenants_row(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """``tenant`` has no ``tenant_id``, so without ``SelfTenantMixin`` the one table
    that defines the isolation boundary would be the only one outside it."""
    await _seed_roots(session, tenant_a, tenant_b)

    with tenant_scope(tenant_a):
        rows = (await session.execute(select(RootLike))).scalars().all()

    assert [(r.id, r.name) for r in rows] == [(tenant_a, "alpha")]


async def test_fetching_another_tenants_root_row_by_id_returns_nothing(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """The object-level case (CLAUDE.md §5.2): knowing the other tenant's id — which
    appears in URLs and in its own JWT — must not be enough to read its row."""
    await _seed_roots(session, tenant_a, tenant_b)

    with tenant_scope(tenant_a):
        found = (
            await session.execute(select(RootLike).where(RootLike.id == tenant_b))
        ).scalar_one_or_none()

    assert found is None


async def test_a_self_tenant_table_raises_with_no_tenant_in_context(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    await _seed_roots(session, tenant_a, tenant_b)

    with pytest.raises(TenantContextError):
        await session.execute(select(RootLike))


async def test_provisioning_a_tenant_needs_unfiltered(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """The cost of filtering ``tenant``: creating one, and any platform-admin listing,
    is a deliberate cross-tenant operation rather than an ordinary query."""
    await _seed_roots(session, tenant_a, tenant_b)

    with unfiltered():
        rows = (await session.execute(select(RootLike))).scalars().all()

    assert {r.name for r in rows} == {"alpha", "beta"}


async def test_two_tenants_sequentially_see_their_own_root_row(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """The caching case again, for the second mechanism. A criteria compiled once
    with the first tenant's id baked in would show it to the second."""
    async with factory() as session:
        await _seed_roots(session, tenant_a, tenant_b)

    stmt = select(RootLike)

    async with factory() as session:
        with tenant_scope(tenant_a):
            first = {r.name for r in (await session.execute(stmt)).scalars().all()}

    async with factory() as session:
        with tenant_scope(tenant_b):
            second = {r.name for r in (await session.execute(stmt)).scalars().all()}

    assert first == {"alpha"}
    assert second == {"beta"}


# --- the shape the filter cannot reach ----------------------------------------


async def test_a_count_with_no_orm_entity_is_refused(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """``select(func.count()).select_from(Model)`` puts no ORM entity in the columns
    clause, so ``with_loader_criteria`` has nothing to attach to and silently drops
    the filter — the count comes back across every tenant.

    It is refused rather than allowed. This is the one shape where the
    session-level filter is not enough on its own, and it is an easy thing to write
    by accident: a paginated list endpoint needs a total.
    """
    await _seed(session, tenant_a, tenant_b)

    with tenant_scope(tenant_a):
        with pytest.raises(UnfilterableStatementError):
            await session.execute(select(func.count()).select_from(TenantThing))


async def test_naming_the_column_counts_only_the_current_tenants_rows(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """The fix the error message names, asserted so it stays true."""
    await _seed(session, tenant_a, tenant_b)

    with tenant_scope(tenant_a):
        counted = (await session.execute(select(func.count(TenantThing.id)))).scalar_one()

    assert counted == 2


async def test_a_join_is_filtered_on_every_entity_it_touches(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """A joined entity absent from the columns clause *is* reached, so the guard above
    must not be read as "joins are unfiltered". Tenant B's row matches the join
    condition and must not contribute to the result."""
    with unfiltered():
        session.add_all(
            [
                TenantThing(id=uuid7(), tenant_id=tenant_a, name="shared-key"),
                TenantThing(id=uuid7(), tenant_id=tenant_b, name="shared-key"),
                SharedThing(id=uuid7(), tenant_id=tenant_a, key="shared-key"),
            ]
        )
        await session.commit()

    with tenant_scope(tenant_a):
        rows = (
            await session.execute(
                select(SharedThing.key, TenantThing.tenant_id).join(
                    TenantThing, TenantThing.name == SharedThing.key
                )
            )
        ).all()

    assert [row.tenant_id for row in rows] == [tenant_a]


async def test_a_count_with_no_entity_is_allowed_under_unfiltered(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """The guard is part of the filter, so bypassing the filter bypasses it too —
    a platform-admin total across tenants is a real, audited need."""
    await _seed(session, tenant_a, tenant_b)

    with unfiltered():
        counted = (
            await session.execute(select(func.count()).select_from(TenantThing))
        ).scalar_one()

    assert counted == 3


async def test_an_exempt_table_may_still_be_counted_without_an_entity(
    session: AsyncSession,
) -> None:
    """The guard fires only where a tenant table is involved. A reference-table count
    has no tenant dimension and must stay ordinary."""
    with unfiltered():
        session.add(ExemptThing(id=uuid7(), code="IN"))
        await session.commit()

    counted = (await session.execute(select(func.count()).select_from(ExemptThing))).scalar_one()
    assert counted == 1


async def test_a_tenant_table_inside_an_exists_subquery_is_filtered(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """The subquery form the guard must *not* reject. Tenant B's row exists, so an
    unfiltered EXISTS would return the exempt row; filtered, it returns nothing."""
    with unfiltered():
        session.add_all(
            [
                TenantThing(id=uuid7(), tenant_id=tenant_b, name="only-b"),
                ExemptThing(id=uuid7(), code="IN"),
            ]
        )
        await session.commit()

    with tenant_scope(tenant_a):
        rows = (
            (
                await session.execute(
                    select(ExemptThing).where(
                        select(TenantThing.id).where(TenantThing.name == "only-b").exists()
                    )
                )
            )
            .scalars()
            .all()
        )

    assert rows == []


async def test_a_count_over_a_tenant_subquery_is_refused(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """Wrapping the table in a subquery does not restore an entity to the columns
    clause, so this is the same leak wearing a different shape."""
    await _seed(session, tenant_a, tenant_b)

    with tenant_scope(tenant_a):
        with pytest.raises(UnfilterableStatementError):
            await session.execute(select(func.count()).select_from(select(TenantThing).subquery()))
