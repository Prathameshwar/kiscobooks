"""Transactional invitation creation; only verified provider ownership can accept it."""

from __future__ import annotations

import datetime as dt
from urllib.parse import urlencode, urlsplit

from billing_platform.constants import SCOPE_ALL
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError
from billing_platform.ids import uuid7
from billing_platform.oidc import IdentityProviderUnavailableError
from billing_platform.outbox import emit
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.api.audit import audit_payload
from identity.api.auth import Actor
from identity.config import Settings
from identity.models import User, UserInvitation
from identity.services.audit import record


async def issue_invitation(
    db: AsyncSession, current: Actor, user: User, settings: Settings
) -> UserInvitation:
    if user.status != "invited":
        raise ConflictError("only an invited user can receive an invitation")
    url = urlsplit(settings.public_auth_url or "")
    if (
        (
            url.scheme != "https"
            and not (url.scheme == "http" and url.hostname in {"localhost", "127.0.0.1", "::1"})
        )
        or not url.hostname
        or url.username
        or url.password
        or url.query
        or url.fragment
    ):
        raise IdentityProviderUnavailableError("invitation delivery is not configured")
    now = utcnow()
    pending = await db.scalar(
        select(UserInvitation).where(
            UserInvitation.user_id == user.id,
            UserInvitation.status == "pending",
        )
    )
    if pending is not None:
        pending.status, pending.cancelled_at, pending.updated_by = "cancelled", now, current.user_id
        record(
            db,
            current,
            action="user.invitation_cancelled",
            entity="user_invitation",
            entity_id=pending.id,
            reason="superseded by a new invitation",
        )
        await db.flush()
    invitation = UserInvitation(
        id=uuid7(),
        tenant_id=current.tenant_id,
        user_id=user.id,
        status="pending",
        expires_at=now + dt.timedelta(days=3),
        created_by=current.user_id,
        updated_by=current.user_id,
    )
    db.add(invitation)
    await db.flush()
    # This URL is a public workflow reference, not a bearer secret. Acceptance also
    # requires a valid provider token with the invited email verified by the provider.
    invitation_url = (
        (settings.public_auth_url or "").rstrip("/")
        + "/accept?"
        + urlencode(
            {
                "tenant": str(current.tenant_id),
                "invitation": str(invitation.id),
            }
        )
    )
    from identity.services.platform_notifications import stage

    platform_staged = stage(
        db,
        settings,
        use_case="user.invited",
        trigger="identity.invitation.requested",
        recipient_ref=invitation.id,
        target_tenant_id=current.tenant_id,
        destinations={"email": user.email},
        variables={"invitation_url": invitation_url},
        locale=user.locale or "en",
        expires_at=invitation.expires_at,
    )
    if not platform_staged:
        emit(
            db,
            tenant_id=current.tenant_id,
            aggregate_type="user_invitation",
            aggregate_id=invitation.id,
            event_type="identity.invitation.requested",
            payload={
                "invitation_id": str(invitation.id),
                "user_id": str(user.id),
                "company_id": str(user.default_company_id or SCOPE_ALL),
                "email": user.email,
                "locale": user.locale or "en",
                "invitation_url": invitation_url,
                "expires_at": invitation.expires_at.isoformat(),
            },
        )
    emit(
        db,
        tenant_id=current.tenant_id,
        aggregate_type="user_invitation",
        aggregate_id=invitation.id,
        event_type="user.invitation_issued",
        payload=audit_payload(
            action="user.invitation_issued",
            category="security",
            entity_type="user_invitation",
            entity_id=invitation.id,
            actor_user_id=current.user_id,
        ),
    )
    return invitation
