"""``tenant`` — isolation, uniqueness, and its two reference foreign keys.

**This file establishes the two-tenant isolation pattern** every later table in
`identity` reuses: seed two tenants, query as one, assert the other's rows are
absent, and assert that knowing the other's primary key is not enough
(CLAUDE.md §7, §5.2). It is the highest-value shape in the suite, so it is written
once here in full and copied deliberately rather than abstracted into a helper —
an isolation test that reads as a call to something else is one nobody checks.

`tenant` is the hardest case of the pattern, not the easiest: it has no
`tenant_id`, so the assertion is against ``SelfTenantMixin`` filtering on ``id``.
Every later table gets the simpler `tenant_id` form.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from billing_platform.db.tenant_context import TenantContextError, tenant_scope, unfiltered
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from identity.models import TENANT_STATUSES, Tenant
from tests.factories import build_tenant, seed_jurisdiction, seed_two_tenants

# --- the isolation pattern ----------------------------------------------------


async def test_a_tenant_sees_only_its_own_row(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    await seed_two_tenants(session, tenant_a, tenant_b)

    with tenant_scope(tenant_a):
        rows = (await session.execute(select(Tenant))).scalars().all()

    assert [row.slug for row in rows] == ["alpha"]


async def test_the_other_tenants_row_is_absent(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """The canonical assertion: not "the query is scoped" but "the other tenant's
    data is not in the result"."""
    await seed_two_tenants(session, tenant_a, tenant_b)

    with tenant_scope(tenant_a):
        rows = (await session.execute(select(Tenant))).scalars().all()

    assert all(row.id == tenant_a for row in rows)
    assert "beta" not in {row.slug for row in rows}


async def test_knowing_the_other_tenants_id_is_not_enough(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """§5.2, at session level. A tenant id is not a secret — it is in every JWT and
    in a good many URLs — so the filter, not its obscurity, is what protects the row.
    """
    await seed_two_tenants(session, tenant_a, tenant_b)

    with tenant_scope(tenant_a):
        found = (
            await session.execute(select(Tenant).where(Tenant.id == tenant_b))
        ).scalar_one_or_none()
        counted = (await session.execute(select(func.count(Tenant.id)))).scalar_one()

    assert found is None
    assert counted == 1, "an aggregate must see one tenant too, not every tenant"


async def test_a_query_with_no_tenant_in_context_raises(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """Deny by default: an unscoped read raises rather than returning every tenant."""
    await seed_two_tenants(session, tenant_a, tenant_b)

    with pytest.raises(TenantContextError):
        await session.execute(select(Tenant))


async def test_crossing_tenants_requires_unfiltered(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """Provisioning and platform-admin listing are the only callers. Both are audited,
    and both are greppable because they name ``unfiltered()``."""
    await seed_two_tenants(session, tenant_a, tenant_b)

    with unfiltered():
        rows = (await session.execute(select(Tenant))).scalars().all()

    assert {row.slug for row in rows} == {"alpha", "beta"}


# --- the table's own constraints ----------------------------------------------


async def test_two_tenants_cannot_share_a_slug(session: AsyncSession) -> None:
    """`uq_tenant_slug`. The slug is a subdomain, so a duplicate is not a cosmetic
    collision — two tenants would resolve to one host."""
    with unfiltered():
        await seed_jurisdiction(session)
        session.add(build_tenant(slug="acme"))
        await session.commit()

        session.add(build_tenant(slug="acme"))
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


async def test_a_tenant_in_an_unknown_country_is_rejected(session: AsyncSession) -> None:
    """`fk_tenant_default_country_code`, enforced by the database rather than by the
    signup form."""
    with unfiltered():
        await seed_jurisdiction(session)
        session.add(build_tenant(default_country_code="ZZ"))
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


async def test_a_tenant_with_an_unknown_currency_is_rejected(session: AsyncSession) -> None:
    with unfiltered():
        await seed_jurisdiction(session)
        session.add(build_tenant(default_currency_code="ZZZ"))
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


async def test_a_plan_id_needs_no_plan_table(session: AsyncSession) -> None:
    """`plan_id` carries no foreign key while `plan` is deferred (§3.2). Asserted so
    the absence is a recorded decision rather than an oversight someone later
    "fixes" by pointing it at nothing."""
    with unfiltered():
        await seed_jurisdiction(session)
        session.add(build_tenant(plan_id=uuid.uuid4()))
        await session.commit()

    assert Tenant.__table__.c.plan_id.foreign_keys == set()


async def test_a_suspended_tenant_keeps_its_row_and_its_reason(
    session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """Suspension is a `status`, never a delete and never `is_active` (rule 4.12).
    The reason is shown to tenant admins, so it has to survive."""
    with unfiltered():
        await seed_jurisdiction(session)
        session.add(
            build_tenant(
                tenant_id=tenant_a,
                slug="lapsed",
                status="suspended",
                suspended_at=dt.datetime(2026, 9, 1, 12, 0, tzinfo=dt.UTC),
                suspended_reason="Payment failed three times",
            )
        )
        await session.commit()

    with tenant_scope(tenant_a):
        found = (await session.execute(select(Tenant))).scalar_one()

    assert found.status == "suspended"
    assert found.suspended_reason == "Payment failed three times"
    assert found.suspended_at is not None
    assert found.suspended_at.tzinfo is not None, "timestamps come back UTC-aware"


def test_the_table_declares_exactly_one_lifecycle_mechanism() -> None:
    """Rule 4.12. `status` and `is_active` on one table means two sources of truth
    about whether a row is usable, and they diverge."""
    columns = set(Tenant.__table__.c.keys())

    assert "status" in columns
    assert not columns & {"is_active", "deactivated_at", "valid_from", "valid_to"}


def test_the_table_has_no_tenant_id_column() -> None:
    """It *is* the tenant. A `tenant_id` here would be a self-reference that is
    either always equal to `id` or a bug."""
    assert "tenant_id" not in Tenant.__table__.c


def test_the_documented_statuses_are_the_ones_the_code_knows() -> None:
    assert TENANT_STATUSES == {"active", "suspended", "closed"}
