import uuid

import pytest
from billing_platform.db import tenant_scope
from billing_platform.gateway import Actor
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models.bulk import BULK_MODELS, BulkJobRecord
from catalog.tasks.bulk_jobs import new
from tests.bulk_factories import seed_storage


async def test_all_six_bulk_tables_are_tenant_isolated(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    _, first = await seed_storage(factory, tenant_a)
    _, second = await seed_storage(factory, tenant_b)
    for tenant, own, foreign in ((tenant_a, first, second), (tenant_b, second, first)):
        with tenant_scope(tenant):
            async with factory() as db:
                for model in BULK_MODELS:
                    ids = set(await db.scalars(select(model.id)))
                    assert own[model.__tablename__] in ids
                    assert foreign[model.__tablename__] not in ids


async def test_record_change_set_cannot_cross_company_or_job(
    factory: async_sessionmaker[AsyncSession], tenant_a: uuid.UUID
) -> None:
    company, first = await seed_storage(factory, tenant_a)
    _, other_job = await seed_storage(factory, tenant_a, company=company)
    _, other_company = await seed_storage(factory, tenant_a)
    for other in (other_job, other_company):
        with tenant_scope(tenant_a):
            async with factory.begin() as db:
                db.add(
                    new(
                        BulkJobRecord,
                        Actor(tenant_id=tenant_a, user_id=uuid.uuid4()),
                        company,
                        job_id=first["bulk_job"],
                        change_set_id=other["bulk_change_set"],
                        logical_key="foreign",
                        ordinal=3,
                        resource="unit_of_measure",
                        action="CREATE",
                        source_sheet="JSON",
                        source_row=3,
                        state="STAGED",
                        normalized_input={},
                    )
                )
                with pytest.raises(IntegrityError):
                    await db.flush()
                await db.rollback()
