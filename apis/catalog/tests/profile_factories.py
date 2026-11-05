import uuid

from billing_platform.db import tenant_scope
from billing_platform.snapshots import SnapshotRecord
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.models.profiles import IdentifierProfile, IdentifierProfileRequirement
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
        permission=["identifier_profile.read", "identifier_profile.manage"],
    )


async def seed_identifier_profile(
    factory: async_sessionmaker[AsyncSession], tenant: uuid.UUID, company: uuid.UUID
) -> uuid.UUID:
    with tenant_scope(tenant):
        async with factory.begin() as db:
            profile = IdentifierProfile(
                tenant_id=tenant,
                company_id=company,
                code="PHONE",
                name="Phone",
                normalization_version=1,
            )
            db.add(profile)
            await db.flush()
            db.add(
                IdentifierProfileRequirement(
                    tenant_id=tenant,
                    company_id=company,
                    profile_id=profile.id,
                    identifier_type="IMEI",
                    namespace_rule="COMPANY",
                    min_count=2,
                    max_count=2,
                    requires_slot=True,
                )
            )
            await db.flush()
            return profile.id
