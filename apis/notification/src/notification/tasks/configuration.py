"""Bounded, idempotent configuration jobs with provider IO outside SQL transactions."""

from __future__ import annotations

import asyncio
import hashlib
import json

import httpx
from billing_platform.db import tenant_scope, unfiltered
from billing_platform.db.types import utcnow
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from notification.config import Settings
from notification.credentials import resolve_credentials, validate_sender
from notification.models import (
    NotificationJob,
    ProviderAccount,
    ProviderEvent,
    ProviderTemplateBinding,
    SenderIdentity,
    TemplateVersion,
)
from notification.ownership import space_scope
from notification.providers.aws import client as aws_client
from notification.providers.inspection import Inspection, inspect_provider
from notification.security import AesGcmCipher


async def run_configuration_jobs(
    factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    *,
    limit: int = 50,
) -> int:
    # Only routing identities leave this deliberate cross-owner scan.
    with unfiltered():
        async with factory() as db:
            candidates = list(
                await db.execute(
                    select(
                        NotificationJob.tenant_id,
                        NotificationJob.space_id,
                        NotificationJob.id,
                    )
                    .where(NotificationJob.status == "pending")
                    .order_by(NotificationJob.created_at)
                    .limit(limit)
                )
            )
    count = 0
    for tenant, space, identity in candidates:
        with tenant_scope(tenant), space_scope(space):
            async with factory() as db:
                job = await db.get(NotificationJob, identity, with_for_update=True)
                if job is None or job.status != "pending":
                    continue
                sender = (
                    await db.get(SenderIdentity, job.target_id)
                    if job.kind.startswith("sender.")
                    else None
                )
                binding = (
                    await db.get(ProviderTemplateBinding, job.target_id)
                    if job.kind == "binding.sync"
                    else None
                )
                event = (
                    await db.get(ProviderEvent, job.target_id)
                    if job.kind == "sns.confirm"
                    else None
                )
                version = (
                    await db.get(TemplateVersion, binding.template_version_id) if binding else None
                )
                provider_id = (
                    sender.provider_account_id
                    if sender
                    else binding.provider_account_id
                    if binding
                    else event.provider_account_id
                    if event
                    else job.target_id
                )
                provider = await db.get(ProviderAccount, provider_id)
                job.status, job.started_at = "running", utcnow()
                await db.commit()
            result = Inspection(False, "configuration_unavailable")
            try:
                if provider is not None:
                    if sender is not None:
                        validate_sender(
                            settings, provider.credential_ref, sender.external_sender_id, tenant
                        )
                    credentials = resolve_credentials(
                        settings, provider.credential_ref, tenant_id=tenant, space_id=space
                    )
                    async with asyncio.timeout(30):
                        if event is not None and event.payload_ciphertext:
                            key = settings.data_encryption_key.get_secret_value().encode()
                            key = key if len(key) == 32 else hashlib.sha256(key).digest()
                            payload = json.loads(
                                AesGcmCipher(key).decrypt(
                                    event.payload_ciphertext, associated_data=provider.id.bytes
                                )
                            )
                            # The signature, topic and confirmation URL were verified before
                            # this immutable inbox row was committed. Use the SDK, no URL fetch.
                            sns = await asyncio.to_thread(
                                aws_client, "sns", provider.region, credentials
                            )
                            await asyncio.to_thread(
                                sns.confirm_subscription,
                                TopicArn=payload["TopicArn"],
                                Token=payload["Token"],
                                AuthenticateOnUnsubscribe="true",
                            )
                            result = Inspection(True, "subscription_confirmed")
                        else:
                            async with httpx.AsyncClient(
                                timeout=15, follow_redirects=False
                            ) as client:
                                result = await inspect_provider(
                                    provider,
                                    credentials,
                                    job.kind,
                                    sender=sender,
                                    binding=binding,
                                    version=version,
                                    client=client,
                                )
            except Exception:
                # Neither provider errors nor exception strings may expose secret/PII data.
                result = Inspection(False, "provider_check_failed")
            async with factory() as db:
                current = await db.get(NotificationJob, identity, with_for_update=True)
                if current is None or current.status != "running":
                    continue
                db.info["notification_actor_id"] = current.actor_user_id
                if provider is not None:
                    fresh_provider = await db.get(
                        ProviderAccount, provider.id, with_for_update=True
                    )
                    if fresh_provider is None or fresh_provider.updated_at != provider.updated_at:
                        result = Inspection(False, "configuration_changed_during_check")
                fresh_sender = (
                    await db.get(SenderIdentity, sender.id, with_for_update=True)
                    if sender
                    else None
                )
                if sender is not None and (
                    fresh_sender is None or fresh_sender.updated_at != sender.updated_at
                ):
                    result = Inspection(False, "configuration_changed_during_check")
                current.status = "completed" if result.success else "failed"
                current.reason_code, current.completed_at = result.reason, utcnow()
                if provider is not None and result.success:
                    if sender is not None and result.verification_status:
                        target = fresh_sender
                        if target is not None:
                            target.verification_status = result.verification_status
                            target.updated_at = utcnow()
                            target.verified_at = (
                                utcnow() if result.verification_status == "verified" else None
                            )
                    elif binding is not None and result.approval_status:
                        target_binding = await db.get(
                            ProviderTemplateBinding, binding.id, with_for_update=True
                        )
                        if target_binding is not None:
                            target_binding.approval_status, target_binding.synced_at = (
                                result.approval_status,
                                utcnow(),
                            )
                    elif current.kind == "provider.validate":
                        account = await db.get(ProviderAccount, provider.id, with_for_update=True)
                        if account is not None and account.status == "pending":
                            account.status = "active"
                    if event is not None:
                        inbox = await db.get(ProviderEvent, event.id)
                        if inbox:
                            inbox.processing_status, inbox.processed_at = "processed", utcnow()
                await db.commit()
            count += 1
    return count
