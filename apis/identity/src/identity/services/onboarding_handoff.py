"""Password-free onboarding delivery and persistent manual handoff details."""

from __future__ import annotations

import datetime as dt
import uuid
from urllib.parse import urlencode, urlsplit

from billing_platform.db import unfiltered
from billing_platform.db.types import utcnow
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.config import Settings
from identity.models import Outbox, User, UserInvitation
from identity.services.platform_notifications import stage


def sign_in_url(settings: Settings) -> str | None:
    base = urlsplit(settings.public_auth_url or "")
    if (
        not base.hostname
        or base.username
        or base.password
        or base.query
        or base.fragment
        or (
            base.scheme != "https"
            and not (base.scheme == "http" and base.hostname in {"localhost", "127.0.0.1", "::1"})
        )
    ):
        return None
    return (settings.public_auth_url or "").rstrip("/") + "/login"


async def notification_queued(db: AsyncSession, settings: Settings, reference: uuid.UUID) -> bool:
    if settings.notification_platform_tenant_id is None:
        return False
    with unfiltered():
        return (
            await db.scalar(
                select(Outbox.id)
                .where(
                    Outbox.tenant_id == settings.notification_platform_tenant_id,
                    Outbox.aggregate_id == reference,
                    Outbox.event_type == "identity.platform_notification.requested",
                )
                .limit(1)
            )
            is not None
        )


async def queue_ready(
    db: AsyncSession,
    settings: Settings,
    *,
    reference: uuid.UUID,
    target_tenant_id: uuid.UUID | None,
    email: str,
    username: str,
    locale: str = "en",
    access_url: str | None = None,
) -> bool:
    if await notification_queued(db, settings, reference):
        return True
    owner, space, key = (
        settings.notification_platform_tenant_id,
        settings.notification_platform_space_id,
        settings.notification_platform_encryption_key,
    )
    if not owner or not space or not key or not owner.int or not space.int or owner == space:
        return False
    link = access_url or sign_in_url(settings)
    if link is None:
        return False
    queued = stage(
        db,
        settings,
        use_case="tenant.administrator.ready",
        trigger="identity.tenant_administrator.ready",
        recipient_ref=reference,
        target_tenant_id=target_tenant_id,
        destinations={"email": email},
        variables={"sign_in_url": link, "username": username},
        locale=locale,
        expires_at=utcnow() + dt.timedelta(days=3),
    )
    if queued:
        await db.flush()
    return queued


async def invitation_link(db: AsyncSession, settings: Settings, email: str) -> str | None:
    if sign_in_url(settings) is None:
        return None
    with unfiltered():
        rows = list(
            await db.execute(
                select(UserInvitation.tenant_id, UserInvitation.id)
                .join(
                    User,
                    (User.tenant_id == UserInvitation.tenant_id)
                    & (User.id == UserInvitation.user_id),
                )
                .where(
                    User.email == email,
                    User.status == "invited",
                    UserInvitation.status == "pending",
                    UserInvitation.expires_at > utcnow(),
                )
                .limit(2)
            )
        )
    if len(rows) != 1:
        return None
    tenant, invitation = rows[0]
    return (
        (settings.public_auth_url or "").rstrip("/")
        + "/accept?"
        + urlencode(
            {
                "tenant": str(tenant),
                "invitation": str(invitation),
            }
        )
    )
