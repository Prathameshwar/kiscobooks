"""Gateway authority for platform history, without tenant business audit grants."""

from billing_platform.authz import ScopePath
from billing_platform.errors import PermissionDeniedError
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from identity.api.auth import Actor, refresh_current
from identity.api.platform import platform_actor
from identity.services.login import live_grants


async def gateway_context(db: AsyncSession, request: Request, current: Actor) -> dict[str, object]:
    await platform_actor(request, current)
    await refresh_current(db, request, current)
    current.grants, current.group_ids = await live_grants(db, current.user_id)
    if not any(
        current_allows(current, key)
        for key in (
            "platform.tenant.read",
            "platform.account.read",
            "platform.config.manage",
            "platform.notification_provider.read",
            "platform.notification_template.read",
            "platform.notification_route.read",
            "platform.notification_recipient.read",
            "platform.notification_request.read",
            "platform.notification_delivery.read",
            "platform.notification_consent.manage",
            "platform.notification_suppression.manage",
        )
    ):
        raise PermissionDeniedError("platform history permission is required")
    # Existing signed user_type is a purpose-bound marker minted only for this
    # gateway path. Audit still checks current grants and each event family.
    return {"user_type": "platform_operator", "audit_scope": {"company_id": None}}


def current_allows(current: Actor, permission: str) -> bool:
    try:
        current.require_scope(permission, target=ScopePath())
    except PermissionDeniedError:
        return False
    return True
