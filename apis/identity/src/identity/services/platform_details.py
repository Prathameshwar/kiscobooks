"""Installation metadata updates preserve every bootstrap and operator field."""

from billing_platform.errors import NotFoundError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.api.auth import Actor
from identity.models import PlatformInstallation
from identity.schemas.platform import PlatformDetails
from identity.services.audit import record


async def installation(db: AsyncSession, *, lock: bool = False) -> PlatformInstallation:
    statement = select(PlatformInstallation).where(
        PlatformInstallation.key == "platform", PlatformInstallation.completed_at.is_not(None)
    )
    row = await db.scalar(statement.with_for_update() if lock else statement)
    if row is None:
        raise NotFoundError("platform setup has not been completed")
    return row


def details(row: PlatformInstallation) -> PlatformDetails:
    return PlatformDetails(name=row.name or "", public_url=row.public_url or "")


async def update(db: AsyncSession, current: Actor, body: PlatformDetails) -> PlatformDetails:
    row = await installation(db, lock=True)
    changed = [
        field for field in ("name", "public_url") if getattr(row, field) != getattr(body, field)
    ]
    for field in changed:
        setattr(row, field, getattr(body, field))
    if changed:
        record(
            db,
            current,
            action="platform.details_updated",
            entity="platform_installation",
            entity_id=row.id,
            changes={field: {"changed": True} for field in changed},
        )
    await db.flush()
    return details(row)
