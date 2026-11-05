"""Dispatch due deliveries using credential references and tenant-fenced sessions."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import os
from typing import Any

import httpx
from billing_platform.db import create_engine, tenant_scope, unfiltered
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, ValidationFailedError
from cryptography.exceptions import InvalidTag
from sqlalchemy import select

from notification.config import Settings
from notification.credentials import resolve_credentials, validate_sender
from notification.models import NotificationDelivery, ProviderAccount, SenderIdentity
from notification.ownership import session_factory as notification_session_factory
from notification.ownership import space_scope
from notification.providers import (
    FcmAdapter,
    MetaWhatsAppAdapter,
    SesAdapter,
    TwilioSmsAdapter,
)
from notification.providers.aws import client as aws_client
from notification.security import AesGcmCipher
from notification.tasks.dispatch import Dispatcher

logger = logging.getLogger(__name__)


class _SesClient:
    def __init__(self, region: str, credentials: dict[str, Any]) -> None:
        self.region, self.credentials = region, credentials
        self.client: Any = None

    async def send_email(self, **kwargs: Any) -> dict[str, Any]:
        if self.client is None:
            self.client = await asyncio.to_thread(
                aws_client, "sesv2", self.region, self.credentials
            )
        return await asyncio.to_thread(self.client.send_email, **kwargs)


def adapter_for(
    provider: ProviderAccount, client: httpx.AsyncClient, settings: Settings | None = None
) -> Any:
    """Resolve secrets only from environment; never persist or log their values."""
    ref = provider.credential_ref
    if settings is not None:
        values = resolve_credentials(
            settings, ref, tenant_id=provider.tenant_id, space_id=provider.space_id
        )
    else:
        # Compatibility for direct adapter unit tests. Runtime always supplies settings.
        if not ref.startswith("env:"):
            raise ValueError("provider credential must be an environment reference")
        raw = os.environ.get(ref[4:])
        if raw is None:
            raise ValueError("provider credential is unavailable")
        values = json.loads(raw)
    if not isinstance(values, dict):
        raise ValueError("provider credential must be a JSON object")
    if provider.provider_key == "twilio" and provider.channel == "sms":
        return TwilioSmsAdapter(
            client,
            account_sid=values["account_sid"],
            auth_token=values["auth_token"],
            callback_url=(
                settings.callback_public_origin.rstrip("/")
                + "/v1/callbacks/sms/"
                + provider.callback_key
            )
            if settings and settings.callback_public_origin
            else None,
        )
    if provider.provider_key == "meta" and provider.channel == "whatsapp":
        return MetaWhatsAppAdapter(
            client,
            access_token=values["access_token"],
            api_version=values.get("api_version", "v23.0"),
        )
    if provider.provider_key == "fcm" and provider.channel == "push":
        return FcmAdapter(
            client, project_id=values["project_id"], access_token=values["access_token"]
        )
    if provider.provider_key == "ses" and provider.channel == "email":
        if not provider.region:
            raise ValueError("SES provider region is required")
        return SesAdapter(_SesClient(provider.region, values))
    raise ValueError("unsupported provider/channel combination")


async def dispatch_due(settings: Settings, *, limit: int = 100) -> int:
    raw_key = settings.data_encryption_key.get_secret_value().encode()
    data_key = raw_key if len(raw_key) == 32 else hashlib.sha256(raw_key).digest()
    engine = create_engine(settings.database_url)
    factory = notification_session_factory(engine)
    attempted = 0
    try:
        with unfiltered():
            async with factory() as db:
                rows = list(
                    (
                        await db.execute(
                            select(
                                NotificationDelivery.tenant_id,
                                NotificationDelivery.id,
                                ProviderAccount,
                                SenderIdentity.external_sender_id,
                            )
                            .join(
                                ProviderAccount,
                                ProviderAccount.id == NotificationDelivery.provider_account_id,
                            )
                            .join(
                                SenderIdentity,
                                SenderIdentity.id == NotificationDelivery.sender_identity_id,
                            )
                            .where(
                                NotificationDelivery.status.in_(
                                    ("pending", "scheduled", "retry_wait")
                                ),
                                NotificationDelivery.next_attempt_at <= utcnow(),
                            )
                            .order_by(NotificationDelivery.next_attempt_at, NotificationDelivery.id)
                            .limit(limit)
                        )
                    ).all()
                )
        async with httpx.AsyncClient(timeout=20) as client:
            for tenant_id, delivery_id, provider, sender_id in rows:
                try:
                    with tenant_scope(tenant_id), space_scope(provider.space_id):
                        validate_sender(settings, provider.credential_ref, sender_id, tenant_id)
                        adapter = adapter_for(provider, client, settings)
                except (
                    ValueError,
                    KeyError,
                    TypeError,
                    json.JSONDecodeError,
                    ValidationFailedError,
                ):
                    logger.error("Notification provider configuration unavailable: %s", provider.id)
                    with tenant_scope(tenant_id), space_scope(provider.space_id):
                        async with factory() as db:
                            row = await db.get(
                                NotificationDelivery, delivery_id, with_for_update=True
                            )
                            fresh_provider = await db.get(
                                ProviderAccount, provider.id, with_for_update=True
                            )
                            if (
                                fresh_provider is None
                                or fresh_provider.updated_at != provider.updated_at
                            ):
                                continue  # Rebuild configuration from the next bounded scan.
                            if row is not None and row.status in {
                                "pending",
                                "scheduled",
                                "retry_wait",
                            }:
                                row.status = "failed"
                                row.next_attempt_at = None
                                row.failed_at = row.completed_at = utcnow()
                                row.status_reason = "provider_configuration_unavailable"
                                await db.commit()
                    continue
                dispatcher = Dispatcher(
                    factory,
                    {provider.id: adapter},
                    per_provider_minute=settings.dispatch_per_provider_minute,
                    per_space_channel_minute=settings.dispatch_per_space_channel_minute,
                    provider_revisions={provider.id: provider.updated_at},
                )
                try:
                    with space_scope(provider.space_id):
                        await dispatcher.dispatch_stored(
                            tenant_id,
                            delivery_id,
                            cipher=AesGcmCipher(data_key),
                            key_ref=settings.data_encryption_key_ref,
                        )
                    attempted += 1
                except ConflictError:
                    # A concurrent dispatcher, cancellation or expired content won the race.
                    continue
                except (InvalidTag, UnicodeDecodeError, ValueError, KeyError, TypeError):
                    with tenant_scope(tenant_id), space_scope(provider.space_id):
                        async with factory() as db:
                            row = await db.get(
                                NotificationDelivery, delivery_id, with_for_update=True
                            )
                            if row is not None and row.status in {
                                "pending",
                                "scheduled",
                                "retry_wait",
                            }:
                                row.status, row.status_reason = "failed", "invalid_retained_payload"
                                row.next_attempt_at = None
                                row.failed_at = row.completed_at = utcnow()
                                await db.commit()
                except Exception as exc:
                    logger.error(
                        "Notification dispatch failed for delivery %s: %s",
                        delivery_id,
                        type(exc).__name__,
                    )
    finally:
        await engine.dispose()
    return attempted


async def run(settings: Settings) -> None:
    if not settings.dispatch_enabled:
        raise ValueError("notification dispatch is disabled")
    while True:
        try:
            await dispatch_due(settings)
        except Exception as exc:
            logger.error("Notification dispatch scan failed: %s", type(exc).__name__)
        await asyncio.sleep(2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file")
    args = parser.parse_args()
    asyncio.run(run(Settings(_env_file=args.env_file)))  # type: ignore[call-arg]
