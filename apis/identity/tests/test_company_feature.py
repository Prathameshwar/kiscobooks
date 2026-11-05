"""``company_feature`` — isolation, the one-row-per-pair key, and the ratchet's storage.

The transitions themselves are tested with no database at all, in
`test_company_features_domain.py`. What is tested here is the storage the rules
depend on: exactly one row per ``(company, feature)``, ``feature_key`` free of any
foreign key because features are code, and ``locked_at`` surviving a round trip.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from billing_platform.db.tenant_context import TenantContextError, tenant_scope, unfiltered
from billing_platform.features import FEATURES
from billing_platform.ids import uuid7
from billing_platform.testing import table_of
from sqlalchemy import UniqueConstraint, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from identity.models import CompanyFeature, Tenant
from tests.factories import build_company_feature, seed_two_companies

# --- the isolation pattern ----------------------------------------------------


async def test_a_tenant_sees_only_its_own_feature_rows(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    company_a, company_b = await seed_two_companies(session, tenant_a, tenant_b)

    with unfiltered():
        session.add_all(
            [
                build_company_feature(
                    tenant_id=tenant_a, company_id=company_a, feature_key="inventory"
                ),
                build_company_feature(tenant_id=tenant_b, company_id=company_b, feature_key="tds"),
            ]
        )
        await session.commit()

    with tenant_scope(tenant_a):
        rows = (await session.execute(select(CompanyFeature))).scalars().all()

    assert [row.feature_key for row in rows] == ["inventory"]


async def test_the_other_tenants_feature_row_is_not_reachable_by_id(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """Which features a competitor has turned on is commercially interesting on its
    own, before it is a write path."""
    company_a, company_b = await seed_two_companies(session, tenant_a, tenant_b)
    theirs = build_company_feature(tenant_id=tenant_b, company_id=company_b)

    with unfiltered():
        session.add_all([theirs, build_company_feature(tenant_id=tenant_a, company_id=company_a)])
        await session.commit()

    with tenant_scope(tenant_a):
        found = (
            await session.execute(select(CompanyFeature).where(CompanyFeature.id == theirs.id))
        ).scalar_one_or_none()
        counted = (await session.execute(select(func.count(CompanyFeature.id)))).scalar_one()

    assert found is None
    assert counted == 1


async def test_a_feature_query_with_no_tenant_in_context_raises(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    company_a, _ = await seed_two_companies(session, tenant_a, tenant_b)

    with unfiltered():
        session.add(build_company_feature(tenant_id=tenant_a, company_id=company_a))
        await session.commit()

    with pytest.raises(TenantContextError):
        await session.execute(select(CompanyFeature))


async def test_every_feature_row_tenant_id_resolves_to_a_real_tenant(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """The compensating control for ``tenant_id`` carrying no foreign key
    (docs/identity-db-plan.md §1.4), which the plan requires **per tenant-scoped
    table** — only `company` had one."""
    company_a, company_b = await seed_two_companies(session, tenant_a, tenant_b)

    with unfiltered():
        session.add_all(
            [
                build_company_feature(tenant_id=tenant_a, company_id=company_a),
                build_company_feature(tenant_id=tenant_b, company_id=company_b),
            ]
        )
        await session.commit()

        tenants = set((await session.execute(select(Tenant.id))).scalars().all())
        owners = set((await session.execute(select(CompanyFeature.tenant_id))).scalars().all())

    assert owners
    assert owners <= tenants


# --- the table's own keys -----------------------------------------------------


async def test_one_company_cannot_hold_a_feature_twice(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """`uq_company_feature_company_id_feature_key`. Two rows for one pair means the
    answer to "is inventory on?" depends on which row is read first — and one of them
    could be the locked one."""
    company_a, _ = await seed_two_companies(session, tenant_a, tenant_b)

    with unfiltered():
        session.add(build_company_feature(tenant_id=tenant_a, company_id=company_a))
        await session.commit()

        session.add(
            build_company_feature(tenant_id=tenant_a, company_id=company_a, is_enabled=False)
        )
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


async def test_two_companies_may_each_hold_the_same_feature(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    company_a, company_b = await seed_two_companies(session, tenant_a, tenant_b)

    with unfiltered():
        session.add_all(
            [
                build_company_feature(tenant_id=tenant_a, company_id=company_a),
                build_company_feature(tenant_id=tenant_b, company_id=company_b),
            ]
        )
        await session.commit()

        counted = (await session.execute(select(func.count(CompanyFeature.id)))).scalar_one()

    assert counted == 2


def test_the_unique_key_deliberately_omits_tenant_id() -> None:
    """Unlike `uq_company_tenant_id_code`, and for the opposite reason to §1.7's.

    `company_id` already determines the tenant, so prefixing `tenant_id` here would
    *weaken* the constraint: the same ``(company, feature)`` pair could then insert
    twice under a mismatched `tenant_id`. Unique constraints stay minimal; it is
    query indexes that lead with `tenant_id`.
    """
    key = next(
        constraint
        for constraint in table_of(CompanyFeature).constraints
        if isinstance(constraint, UniqueConstraint)
        and constraint.name == "uq_company_feature_company_id_feature_key"
    )

    assert [column.name for column in key.columns] == ["company_id", "feature_key"]


async def test_a_feature_row_must_belong_to_a_real_company(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    await seed_two_companies(session, tenant_a, tenant_b)

    with unfiltered():
        session.add(build_company_feature(tenant_id=tenant_a, company_id=uuid7()))
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


async def test_feature_key_has_no_foreign_key_and_takes_any_catalogue_key(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """Invariant 13's shape applied to features: **features are code, not data**
    (docs/company-features.md §2). A `feature` table would let a tenant invent one
    that no service knows how to honour, so validation is
    ``billing_platform.features``' job and the column carries no FK."""
    company_a, _ = await seed_two_companies(session, tenant_a, tenant_b)

    with unfiltered():
        session.add_all(
            [
                build_company_feature(
                    tenant_id=tenant_a, company_id=company_a, feature_key=key, is_enabled=False
                )
                for key in sorted(FEATURES)
            ]
        )
        await session.commit()

    with tenant_scope(tenant_a):
        rows = (await session.execute(select(CompanyFeature.feature_key))).scalars().all()

    assert set(rows) == set(FEATURES)
    assert table_of(CompanyFeature).c.feature_key.foreign_keys == set()


# --- what the rules read back -------------------------------------------------


async def test_an_absent_row_is_how_disabled_is_stored(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """docs/company-features.md §3. A company gets no rows at creation, so "no row"
    has to mean disabled — never "unknown, so allow"."""
    company_a, _ = await seed_two_companies(session, tenant_a, tenant_b)

    with tenant_scope(tenant_a):
        rows = (
            (
                await session.execute(
                    select(CompanyFeature).where(CompanyFeature.company_id == company_a)
                )
            )
            .scalars()
            .all()
        )

    assert rows == []


async def test_a_locked_feature_keeps_its_timestamp_and_reason(
    session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """``locked_at`` records the *first* dependent write and is never cleared. The
    reason travels with it because it is what the refusal message quotes."""
    company_a, _ = await seed_two_companies(session, tenant_a, tenant_b)

    with unfiltered():
        session.add(
            build_company_feature(
                tenant_id=tenant_a,
                company_id=company_a,
                locked_at=dt.datetime(2026, 5, 2, 6, 15, tzinfo=dt.UTC),
                lock_reason="stock_movement",
            )
        )
        await session.commit()
        session.expunge_all()

    with tenant_scope(tenant_a):
        found = (await session.execute(select(CompanyFeature))).scalar_one()

    assert found.locked_at is not None
    assert found.locked_at.tzinfo is not None
    assert found.lock_reason == "stock_movement"
    assert found.is_enabled is True, "a locked feature is by definition still enabled"


def test_the_table_declares_exactly_one_lifecycle_mechanism() -> None:
    """Rule 4.12. `is_enabled` is the boolean form; the ``enabled_at``/``disabled_at``
    pair records *when the switch moved*, which is not a second lifecycle — and there
    is no `status` and no validity window."""
    columns = set(table_of(CompanyFeature).c.keys())

    assert "is_enabled" in columns
    assert not columns & {"status", "is_active", "valid_from", "valid_to"}
