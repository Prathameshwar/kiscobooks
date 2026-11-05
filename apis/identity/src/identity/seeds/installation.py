"""Create the locked installation control row during deployment, never on HTTP startup."""

from billing_platform.ids import uuid7
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.domain.branding import PRODUCT_NAME
from identity.models.platform_installation import PlatformInstallation
from identity.models.reference_cache import ReferenceCacheGeneration
from identity.seeds.branding import seed_branding


async def seed_installation(db: AsyncSession) -> None:
    if (
        await db.scalar(
            select(ReferenceCacheGeneration.id).where(ReferenceCacheGeneration.key == "global")
        )
        is None
    ):
        db.add(ReferenceCacheGeneration(key="global", token=uuid7()))
        await db.flush()
    if (
        await db.scalar(
            select(PlatformInstallation.id).where(PlatformInstallation.key == "platform")
        )
        is None
    ):
        db.add(PlatformInstallation(id=uuid7(), key="platform", name=PRODUCT_NAME))
        await db.flush()
    await seed_branding(db)
