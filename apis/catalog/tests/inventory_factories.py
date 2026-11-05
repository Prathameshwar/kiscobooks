import uuid

from billing_platform.db import tenant_scope
from billing_platform.snapshots import SnapshotRecord
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models.inventory_templates import (
    InventoryProfileTemplate,
    InventoryProfileTemplateRevision,
)
from catalog.schemas.inventory_templates import InventoryRevisionInput
from tests.test_api import headers
from tests.test_classification_api import setup_source


async def auth(
    factory: async_sessionmaker[AsyncSession],
    tenant: uuid.UUID,
    company: uuid.UUID,
    user: uuid.UUID,
    *,
    version: int = 2,
    facts: tuple[SnapshotRecord, ...] | None = None,
) -> dict[str, str]:
    await setup_source(factory, tenant, company, user, version=version, facts=facts)
    return headers(
        company,
        tenant=tenant,
        user=user,
        permission=[
            "inventory_profile_template.read",
            "inventory_profile_template.manage",
            "inventory_profile_template.publish",
            "identifier_profile.read",
            "identifier_profile.manage",
        ],
    )


async def seed_template(
    factory: async_sessionmaker[AsyncSession], tenant: uuid.UUID, company: uuid.UUID
) -> tuple[uuid.UUID, uuid.UUID]:
    with tenant_scope(tenant):
        async with factory.begin() as db:
            parent = InventoryProfileTemplate(
                tenant_id=tenant, company_id=company, code="STOCK", name="Stock"
            )
            db.add(parent)
            await db.flush()
            revision = InventoryProfileTemplateRevision(
                tenant_id=tenant,
                company_id=company,
                template_id=parent.id,
                revision=1,
                **InventoryRevisionInput().model_dump(),
            )
            db.add(revision)
            await db.flush()
            return parent.id, revision.id
