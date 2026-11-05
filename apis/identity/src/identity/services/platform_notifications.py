"""Encrypted platform delivery commands staged with the owning Identity transaction."""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import json
import secrets
import uuid

from billing_platform.crypto import AesGcmCipher
from billing_platform.errors import ValidationFailedError
from billing_platform.outbox import emit
from sqlalchemy.ext.asyncio import AsyncSession

from identity.config import Settings


def stage(
    db: AsyncSession,
    settings: Settings,
    *,
    use_case: str,
    trigger: str,
    recipient_ref: uuid.UUID,
    target_tenant_id: uuid.UUID | None,
    destinations: dict[str, str],
    variables: dict[str, str],
    locale: str,
    expires_at: dt.datetime,
) -> bool:
    owner, space, secret = (
        settings.notification_platform_tenant_id,
        settings.notification_platform_space_id,
        settings.notification_platform_encryption_key,
    )
    if owner is None and space is None and secret is None:
        return False  # explicit legacy-compatibility mode until platform provisioning
    if (
        owner is None
        or space is None
        or secret is None
        or not owner.int
        or not space.int
        or owner == space
    ):
        raise ValidationFailedError("platform notification ownership is incomplete")
    row = emit(
        db,
        tenant_id=owner,
        aggregate_type="platform_notification",
        aggregate_id=recipient_ref,
        event_type="identity.platform_notification.requested",
        payload={},
    )
    aad = row.message_id.bytes + space.bytes + use_case.encode()
    payload = json.dumps({"destinations": destinations, "variables": variables}).encode()
    cipher = AesGcmCipher(hashlib.sha256(secret.get_secret_value().encode()).digest())
    row.payload = {
        "space_id": str(space),
        "use_case": use_case,
        "trigger_key": trigger,
        "recipient_ref": str(recipient_ref),
        "target_tenant_id": str(target_tenant_id) if target_tenant_id else None,
        "channels": sorted(destinations),
        "locale": locale,
        "expires_at": expires_at.isoformat(),
        "key_id": settings.notification_platform_key_id,
        "encrypted_payload": base64.b64encode(
            cipher.encrypt(payload, nonce=secrets.token_bytes(12), associated_data=aad)
        ).decode(),
    }
    return True
