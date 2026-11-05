import datetime as dt
import uuid

import pytest
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models import (
    CatalogPolicyState,
    CategoryScheme,
    ItemCategory,
    ItemGroup,
    ItemGroupParent,
)


async def seed_classification(
    factory: async_sessionmaker[AsyncSession], tenant: uuid.UUID, company: uuid.UUID
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    with tenant_scope(tenant):
        async with factory.begin() as db:
            group = ItemGroup(
                tenant_id=tenant,
                company_id=company,
                code="GENERAL",
                name="General",
                allowed_kind="BOTH",
            )
            scheme = CategoryScheme(
                tenant_id=tenant,
                company_id=company,
                code="DEPARTMENT",
                name="Department",
                membership_mode="MULTIPLE",
            )
            db.add_all([group, scheme, CatalogPolicyState(tenant_id=tenant, company_id=company)])
            await db.flush()
            category = ItemCategory(
                tenant_id=tenant,
                company_id=company,
                scheme_id=scheme.id,
                code="FIRST",
                name="First",
            )
            db.add_all(
                [
                    category,
                    ItemGroupParent(
                        tenant_id=tenant,
                        company_id=company,
                        group_id=group.id,
                        valid_from=dt.date(2025, 1, 1),
                    ),
                ]
            )
            await db.flush()
            return group.id, scheme.id, category.id


async def test_every_classification_table_is_tenant_isolated(
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
) -> None:
    first, second = uuid7(), uuid7()
    await seed_classification(factory, tenant_a, first)
    await seed_classification(factory, tenant_b, second)
    for tenant, company in [(tenant_a, first), (tenant_b, second)]:
        with tenant_scope(tenant):
            async with factory() as db:
                for model in (
                    CatalogPolicyState,
                    ItemGroup,
                    ItemGroupParent,
                    CategoryScheme,
                    ItemCategory,
                ):
                    rows = list(await db.scalars(select(model)))
                    assert len(rows) == 1
                    row = rows[0]
                    assert isinstance(
                        row,
                        CatalogPolicyState
                        | ItemGroup
                        | ItemGroupParent
                        | CategoryScheme
                        | ItemCategory,
                    )
                    assert row.tenant_id == tenant and row.company_id == company


async def test_database_rejects_cross_company_and_cross_scheme_hierarchy_refs(
    factory: async_sessionmaker[AsyncSession],
    tenant_a: uuid.UUID,
) -> None:
    company, other = uuid7(), uuid7()
    group, scheme, category = await seed_classification(factory, tenant_a, company)
    other_group, other_scheme, other_category = await seed_classification(factory, tenant_a, other)
    with tenant_scope(tenant_a):
        alternate_scheme = uuid7()
        async with factory.begin() as db:
            db.add(
                CategoryScheme(
                    id=alternate_scheme,
                    tenant_id=tenant_a,
                    company_id=company,
                    code="ALTERNATE",
                    name="Alternate",
                    membership_mode="SINGLE",
                )
            )
        for invalid in (
            ItemCategory(
                tenant_id=tenant_a,
                company_id=company,
                code="OTHER-SCHEME",
                name="Other",
                scheme_id=alternate_scheme,
                parent_id=category,
            ),
            ItemGroupParent(
                tenant_id=tenant_a,
                company_id=company,
                group_id=group,
                parent_group_id=other_group,
                valid_from=dt.date(2026, 1, 1),
            ),
            ItemCategory(
                tenant_id=tenant_a,
                company_id=company,
                code="FOREIGN",
                name="Foreign",
                scheme_id=other_scheme,
            ),
            ItemCategory(
                tenant_id=tenant_a,
                company_id=company,
                code="FOREIGN",
                name="Foreign",
                scheme_id=scheme,
                parent_id=other_category,
            ),
            ItemCategory(
                tenant_id=tenant_a,
                company_id=company,
                code="SELF",
                name="Self",
                scheme_id=scheme,
                parent_id=category,
                id=category,
            ),
            ItemGroupParent(
                tenant_id=tenant_a,
                company_id=company,
                group_id=group,
                parent_group_id=group,
                valid_from=dt.date(2026, 1, 1),
            ),
        ):
            with pytest.raises(IntegrityError):
                async with factory.begin() as db:
                    db.add(invalid)
                    await db.flush()
