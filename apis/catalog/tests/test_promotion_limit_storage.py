"""Limit tables enforce tenant scope, cap shape and immutable publications."""

import pytest
from billing_platform.db import tenant_scope
from billing_platform.errors import ConflictError
from billing_platform.db.types import utcnow
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from catalog.models.promotion_limits import PromotionLimitDefinition, PromotionLimitRevision
from tests.product_definition_factories import seed_definitions


async def test_limit_caps_and_publication_lineage_cannot_be_null(factory, tenant_a):
    company, _ = await seed_definitions(factory, tenant_a)
    with tenant_scope(tenant_a):
        async with factory.begin() as db:
            parent = PromotionLimitDefinition(
                tenant_id=tenant_a,
                company_id=company,
                code="COUNT",
                name="Usage cap",
                scope_kind="PROGRAM",
                metric="TOTAL_USES",
                period_basis="LIFETIME",
                timezone="UTC",
            )
            db.add(parent)
            await db.flush()
            for extra in ({}, {"maximum_count": 1, "published_at": utcnow()}):
                with pytest.raises(IntegrityError):
                    async with db.begin_nested():
                        db.add(
                            PromotionLimitRevision(
                                tenant_id=tenant_a,
                                company_id=company,
                                definition_id=parent.id,
                                revision=1,
                                change_reason="Invalid incomplete cap",
                                **extra,
                            )
                        )
                        await db.flush()


async def test_limit_tables_are_scoped_and_publication_is_immutable(factory, tenant_a, tenant_b):
    ids = {}
    for tenant in (tenant_a, tenant_b):
        company, _ = await seed_definitions(factory, tenant)
        with tenant_scope(tenant):
            async with factory.begin() as db:
                parent = PromotionLimitDefinition(
                    tenant_id=tenant,
                    company_id=company,
                    code="COUNT",
                    name="Usage cap",
                    scope_kind="PROGRAM",
                    metric="TOTAL_USES",
                    period_basis="LIFETIME",
                    timezone="UTC",
                )
                db.add(parent)
                await db.flush()
                revision = PromotionLimitRevision(
                    tenant_id=tenant,
                    company_id=company,
                    definition_id=parent.id,
                    revision=1,
                    change_reason="Initial cap",
                    maximum_count=2**63 - 1,
                    published_at=utcnow(),
                    publication_generation=1,
                    published_source_version=1,
                )
                db.add(revision)
                await db.flush()
                ids[tenant] = (company, parent.id, revision.id)
    with tenant_scope(tenant_a):
        async with factory() as db:
            assert [row.id for row in await db.scalars(select(PromotionLimitDefinition))] == [
                ids[tenant_a][1]
            ]
            assert [row.id for row in await db.scalars(select(PromotionLimitRevision))] == [
                ids[tenant_a][2]
            ]
            revision = await db.get(PromotionLimitRevision, ids[tenant_a][2])
            revision.maximum_count = 1
            with pytest.raises(ConflictError):
                await db.flush()
            await db.rollback()
