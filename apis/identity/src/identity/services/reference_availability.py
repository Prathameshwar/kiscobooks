"""New selections require active, delivered references; history is untouched."""

from __future__ import annotations

from billing_platform.db.reference_management import ReferenceRevision, ReferenceSyncState
from billing_platform.errors import ConflictError
from sqlalchemy import and_, exists, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute
from sqlalchemy.sql.elements import ColumnElement

from identity.models import PlatformInstallation
from identity.services.reference_management import sync_ready


def selectable(
    kind: str, code: ColumnElement[str] | InstrumentedAttribute[str]
) -> ColumnElement[bool]:
    delivered = and_(
        *(
            exists(
                select(ReferenceSyncState.id).where(
                    ReferenceSyncState.service == service,
                    ReferenceSyncState.cursor >= ReferenceRevision.change_id,
                )
            )
            for service in ("catalog", "accounting")
        )
    )
    pending = exists(
        select(ReferenceRevision.id).where(
            ReferenceRevision.kind == kind,
            ReferenceRevision.code == code,
            ReferenceRevision.is_custom.is_(True),
            ReferenceRevision.change_id.is_not(None),
            ~delivered,
        )
    )
    return ~pending


async def require_delivered(db: AsyncSession, kind: str, code: str) -> None:
    revision = await db.scalar(
        select(ReferenceRevision).where(
            ReferenceRevision.kind == kind, ReferenceRevision.code == code
        )
    )
    if revision is not None and revision.is_custom and not await sync_ready(db, revision):
        raise ConflictError("this reference is still synchronizing; retry shortly")


async def lock_configuration(db: AsyncSession) -> None:
    """Serialize new configuration selections against global reference changes."""
    await db.scalar(
        select(PlatformInstallation.id)
        .where(PlatformInstallation.key == "platform")
        .with_for_update()
    )
