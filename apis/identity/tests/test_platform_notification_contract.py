from __future__ import annotations

import base64
import datetime as dt
import hashlib
import json

from billing_platform.crypto import AesGcmCipher
from billing_platform.db import tenant_scope
from billing_platform.ids import uuid7
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.config import Settings
from identity.models import Outbox
from identity.services.platform_notifications import stage


async def test_platform_notification_outbox_contains_only_encrypted_recipient_data(
    session: AsyncSession,
) -> None:
    owner, space, recipient = uuid7(), uuid7(), uuid7()
    secret = "test-only-platform-key-00000000000000"
    settings = Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        actor_signing_secret=SecretStr("a" * 32),
        cursor_signing_secret=SecretStr("c" * 32),
        notification_platform_tenant_id=owner,
        notification_platform_space_id=space,
        notification_platform_encryption_key=SecretStr(secret),
    )
    with tenant_scope(owner):
        assert stage(
            session,
            settings,
            use_case="user.invited",
            trigger="identity.invitation.requested",
            recipient_ref=recipient,
            target_tenant_id=None,
            destinations={"email": "new@example.invalid"},
            variables={"invitation_url": "https://auth.invalid/accept"},
            locale="en",
            expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(hours=1),
        )
        await session.commit()
        row = await session.scalar(
            select(Outbox).where(Outbox.event_type == "identity.platform_notification.requested")
        )
        assert row is not None and "new@example.invalid" not in json.dumps(row.payload)
        decoded = AesGcmCipher(hashlib.sha256(secret.encode()).digest()).decrypt(
            base64.b64decode(row.payload["encrypted_payload"]),
            associated_data=row.message_id.bytes + space.bytes + b"user.invited",
        )
        assert json.loads(decoded)["destinations"]["email"] == "new@example.invalid"
