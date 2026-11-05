import uuid

from billing_platform.db import tenant_scope
from billing_platform.snapshots import SnapshotRecord
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models.returns import (
    ReturnPolicy,
    ReturnPolicyCondition,
    ReturnPolicyRevision,
)
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
            "return_policy.read",
            "return_policy.manage",
            "return_policy.publish",
        ],
    )


async def seed_policy(
    factory: async_sessionmaker[AsyncSession], tenant: uuid.UUID, company: uuid.UUID
) -> tuple[uuid.UUID, uuid.UUID]:
    with tenant_scope(tenant):
        async with factory.begin() as db:
            parent = ReturnPolicy(
                tenant_id=tenant,
                company_id=company,
                code="STANDARD",
                name="Standard returns",
            )
            db.add(parent)
            await db.flush()
            revision = ReturnPolicyRevision(
                tenant_id=tenant,
                company_id=company,
                policy_id=parent.id,
                revision=1,
                returns_allowed=True,
                window_days=30,
                condition_count=2,
            )
            db.add(revision)
            await db.flush()
            for code in ("UNUSED", "UNDAMAGED"):
                db.add(
                    ReturnPolicyCondition(
                        tenant_id=tenant,
                        company_id=company,
                        revision_id=revision.id,
                        condition_code=code,
                    )
                )
            await db.flush()
            return parent.id, revision.id
