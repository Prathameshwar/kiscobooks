import uuid

from billing_platform.db import tenant_scope
from billing_platform.snapshots import SnapshotRecord
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models.warranties import (
    WarrantyPolicy,
    WarrantyPolicyRevision,
)
from catalog.schemas.warranties import WarrantyRevisionInput
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
            "warranty_policy.read",
            "warranty_policy.manage",
            "warranty_policy.publish",
        ],
    )


async def seed_policy(
    factory: async_sessionmaker[AsyncSession], tenant: uuid.UUID, company: uuid.UUID
) -> tuple[uuid.UUID, uuid.UUID]:
    with tenant_scope(tenant):
        async with factory.begin() as db:
            parent = WarrantyPolicy(
                tenant_id=tenant, company_id=company, code="STANDARD", name="Standard warranty"
            )
            db.add(parent)
            await db.flush()
            revision = WarrantyPolicyRevision(
                tenant_id=tenant,
                company_id=company,
                policy_id=parent.id,
                revision=1,
                **WarrantyRevisionInput(duration=12, duration_unit="MONTHS").model_dump(),
            )
            db.add(revision)
            await db.flush()
            return parent.id, revision.id
