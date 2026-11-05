"""Dispatch transaction boundaries: prepare, call provider, then finalize."""

from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import json
import uuid
from dataclasses import replace

import httpx
from billing_platform.db import tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, NotFoundError
from billing_platform.ids import uuid7
from billing_platform.outbox import emit
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from notification.domain import planning
from notification.domain.retry import backoff_seconds
from notification.domain.state import should_advance
from notification.models import (
    ChannelSetting,
    DeliveryAttempt,
    DeliveryEvent,
    NotificationContent,
    NotificationDelivery,
    NotificationRequest,
    NotificationSpace,
    NotificationTemplate,
    ProviderAccount,
    ProviderTemplateBinding,
    RecipientEndpoint,
    RoutingRule,
    SenderIdentity,
    TemplateVariant,
    TemplateVersion,
)
from notification.ownership import current_space
from notification.providers import ProviderAdapter, SendCommand, SendResult
from notification.security import AesGcmCipher
from notification.tasks.consume import endpoint_policy


async def fail_preflight(
    db: AsyncSession, delivery: NotificationDelivery, reason: str
) -> SendResult:
    now = utcnow()
    delivery.status, delivery.status_reason = "failed", reason
    delivery.failed_at = delivery.completed_at = delivery.updated_at = now
    delivery.next_attempt_at = None
    await db.commit()  # the audit hook supplies exactly one transition event/outbox row
    return SendResult("permanent_failure", None, error_code=reason)


class Dispatcher:
    def __init__(
        self,
        factory: async_sessionmaker[AsyncSession],
        adapters: dict[uuid.UUID, ProviderAdapter],
        *,
        per_provider_minute: int = 120,
        per_space_channel_minute: int = 300,
        provider_revisions: dict[uuid.UUID, dt.datetime] | None = None,
    ) -> None:
        self.factory, self.adapters = factory, adapters
        self.per_provider_minute = per_provider_minute
        self.per_space_channel_minute = per_space_channel_minute
        self.provider_revisions = provider_revisions or {}

    async def dispatch_stored(
        self,
        tenant_id: uuid.UUID,
        delivery_id: uuid.UUID,
        *,
        cipher: AesGcmCipher,
        key_ref: str,
    ) -> SendResult:
        """Assemble the frozen rendered message without exposing plaintext in API responses."""
        with tenant_scope(tenant_id):
            async with self.factory() as db:
                delivery = await db.get(NotificationDelivery, delivery_id, with_for_update=True)
                if delivery is None:
                    raise NotFoundError("delivery not found")
                if delivery.status not in {"pending", "scheduled", "retry_wait"}:
                    raise ConflictError("delivery is not dispatchable")
                content = await db.get(NotificationContent, delivery_id)
                request = await db.get(NotificationRequest, delivery.request_id)
                endpoint = await db.get(RecipientEndpoint, delivery.recipient_endpoint_id)
                sender = await db.get(SenderIdentity, delivery.sender_identity_id)
                provider = await db.get(ProviderAccount, delivery.provider_account_id)
                now = utcnow()

                req_expired = (
                    request is not None
                    and request.expires_at is not None
                    and request.expires_at <= now
                )
                content_expired = content is not None and content.expires_at <= now
                if req_expired or content_expired:
                    prior = delivery.status
                    delivery.status = "expired"
                    delivery.status_reason = "content_or_request_expired"
                    delivery.completed_at = now
                    delivery.updated_at = now
                    db.add(
                        DeliveryEvent(
                            id=uuid7(),
                            tenant_id=tenant_id,
                            delivery_id=delivery.id,
                            source="dispatcher",
                            source_event_key=f"{delivery.id}:expired",
                            from_status=prior,
                            to_status="expired",
                            reason_code="content_or_request_expired",
                            provider_occurred_at=None,
                            observed_at=now,
                            metadata_json=None,
                        )
                    )
                    await db.commit()
                    return SendResult(
                        "permanent_failure", None, error_code="content_or_request_expired"
                    )

                if (
                    (endpoint is not None and not endpoint.is_active)
                    or (sender is not None and not sender.is_active)
                    or (provider is not None and provider.status != "active")
                ):
                    prior = delivery.status
                    delivery.status = "failed"
                    delivery.status_reason = "route_or_endpoint_unavailable"
                    delivery.failed_at = now
                    delivery.completed_at = now
                    delivery.updated_at = now
                    db.add(
                        DeliveryEvent(
                            id=uuid7(),
                            tenant_id=tenant_id,
                            delivery_id=delivery.id,
                            source="dispatcher",
                            source_event_key=f"{delivery.id}:failed",
                            from_status=prior,
                            to_status="failed",
                            reason_code="route_or_endpoint_unavailable",
                            provider_occurred_at=None,
                            observed_at=now,
                            metadata_json=None,
                        )
                    )
                    await db.commit()
                    return SendResult(
                        "permanent_failure", None, error_code="route_or_endpoint_unavailable"
                    )

                if content is None or endpoint is None or sender is None or provider is None:
                    prior = delivery.status
                    delivery.status = "failed"
                    delivery.status_reason = "missing_content_or_endpoint"
                    delivery.failed_at = now
                    delivery.completed_at = now
                    delivery.updated_at = now
                    db.add(
                        DeliveryEvent(
                            id=uuid7(),
                            tenant_id=tenant_id,
                            delivery_id=delivery.id,
                            source="dispatcher",
                            source_event_key=f"{delivery.id}:failed",
                            from_status=prior,
                            to_status="failed",
                            reason_code="missing_content_or_endpoint",
                            provider_occurred_at=None,
                            observed_at=now,
                            metadata_json=None,
                        )
                    )
                    await db.commit()
                    return SendResult(
                        "permanent_failure", None, error_code="missing_content_or_endpoint"
                    )

                if (
                    content is None
                    or content.encryption_key_ref != key_ref
                    or request is None
                    or endpoint is None
                    or not endpoint.destination_ciphertext
                    or endpoint.destination_hmac != delivery.destination_hmac
                    or sender is None
                    or sender.verification_status != "verified"
                    or provider is None
                    or not content.body_text_ciphertext
                ):
                    previous = delivery.status
                    delivery.status = "failed"
                    delivery.status_reason = "invalid_preflight_evidence"
                    delivery.failed_at = delivery.completed_at = delivery.updated_at = now
                    db.add(
                        DeliveryEvent(
                            id=uuid7(),
                            tenant_id=tenant_id,
                            delivery_id=delivery.id,
                            source="dispatcher",
                            source_event_key=f"{delivery.id}:preflight:{uuid7()}",
                            from_status=previous,
                            to_status="failed",
                            reason_code=delivery.status_reason,
                            observed_at=now,
                        )
                    )
                    emit(
                        db,
                        aggregate_type="notification_delivery",
                        aggregate_id=delivery.id,
                        event_type="notification.delivery.status_changed",
                        tenant_id=tenant_id,
                        payload={
                            "delivery_id": str(delivery.id),
                            "request_id": str(delivery.request_id),
                            "from_status": previous,
                            "to_status": "failed",
                            "reason_code": delivery.status_reason,
                        },
                    )
                    await db.commit()
                    return SendResult(
                        "permanent_failure", None, error_code="invalid_preflight_evidence"
                    )
                if (request.scheduled_at is not None and request.scheduled_at > now) or (
                    delivery.next_attempt_at is not None and delivery.next_attempt_at > now
                ):
                    raise ConflictError("delivery is not due")

                provider_template_name = None
                template_language = None
                template_parameters: tuple[str, ...] = ()
                template_components = ()
                if content.payload_ciphertext:
                    frozen_payload = json.loads(
                        cipher.decrypt(
                            content.payload_ciphertext, associated_data=delivery_id.bytes
                        )
                    )
                    template_components = tuple(frozen_payload.get("components", []))

                if delivery.provider_template_binding_id is not None:
                    binding = await db.get(
                        ProviderTemplateBinding, delivery.provider_template_binding_id
                    )
                    if binding is None or binding.approval_status != "approved":
                        return await fail_preflight(
                            db, delivery, "provider_template_approval_unavailable"
                        )
                    if binding is not None:
                        provider_template_name = binding.external_name
                        template_language = binding.external_language
                        version = await db.get(TemplateVersion, delivery.template_version_id)
                        if (
                            not content.payload_ciphertext
                            and version is not None
                            and version.channel_payload
                        ):
                            param_names = version.channel_payload.get("template_parameters")
                            if param_names and not request.context_ciphertext:
                                return await fail_preflight(
                                    db, delivery, "provider_parameters_purged"
                                )
                            if param_names and request.context_ciphertext:
                                variables = json.loads(
                                    cipher.decrypt(
                                        request.context_ciphertext,
                                        associated_data=request.id.bytes,
                                    ).decode()
                                )
                                if any(name not in variables for name in param_names):
                                    return await fail_preflight(
                                        db, delivery, "provider_parameters_missing"
                                    )
                                template_parameters = tuple(
                                    str(variables[name]) for name in param_names
                                )

                body_html = (
                    cipher.decrypt(
                        content.body_html_ciphertext, associated_data=delivery_id.bytes
                    ).decode()
                    if content.body_html_ciphertext
                    else None
                )
                command = SendCommand(
                    destination=cipher.decrypt(
                        endpoint.destination_ciphertext, associated_data=endpoint.id.bytes
                    ).decode(),
                    sender=sender.external_sender_id,
                    body=cipher.decrypt(
                        content.body_text_ciphertext, associated_data=delivery_id.bytes
                    ).decode(),
                    subject=cipher.decrypt(
                        content.subject_ciphertext, associated_data=delivery_id.bytes
                    ).decode()
                    if content.subject_ciphertext
                    else None,
                    attempt_key=f"{delivery_id}:{delivery.attempt_count + 1}",
                    body_html=body_html,
                    provider_template_name=provider_template_name,
                    template_language=template_language,
                    template_parameters=template_parameters,
                    template_components=template_components,
                )
        return await self.dispatch(tenant_id, delivery_id, command)

    async def dispatch(
        self, tenant_id: uuid.UUID, delivery_id: uuid.UUID, command: SendCommand
    ) -> SendResult:
        with tenant_scope(tenant_id):
            async with self.factory() as db:
                # Serialize each space's admission before any consistent read. Network IO
                # starts only after this short transaction releases the lock.
                await db.scalar(
                    select(NotificationSpace)
                    .where(NotificationSpace.id == current_space())
                    .with_for_update()
                )
                delivery = await db.get(NotificationDelivery, delivery_id, with_for_update=True)
                if delivery is None:
                    raise NotFoundError("delivery not found")
                if delivery.status not in {"pending", "retry_wait", "scheduled"}:
                    raise ConflictError("delivery is not dispatchable")
                started = utcnow()  # Admission may have waited for another transaction's lock.
                request = await db.get(NotificationRequest, delivery.request_id)
                content = await db.get(NotificationContent, delivery_id)
                if request is None or content is None or content.purged_at is not None:
                    return await fail_preflight(db, delivery, "missing_content_or_request")
                if (request.expires_at is not None and request.expires_at <= started) or (
                    content.expires_at <= started
                ):
                    delivery.status, delivery.status_reason = (
                        "expired",
                        "content_or_request_expired",
                    )
                    delivery.completed_at = delivery.updated_at = started
                    delivery.next_attempt_at = None
                    await db.commit()
                    return SendResult(
                        "permanent_failure", None, error_code="content_or_request_expired"
                    )
                if (request.scheduled_at is not None and request.scheduled_at > started) or (
                    delivery.next_attempt_at is not None and delivery.next_attempt_at > started
                ):
                    raise ConflictError("delivery is not due")
                endpoint = await db.get(
                    RecipientEndpoint, delivery.recipient_endpoint_id, with_for_update=True
                )
                if endpoint is None:
                    raise ConflictError("delivery policy evidence is unavailable")
                if endpoint.destination_hmac != delivery.destination_hmac:
                    return await fail_preflight(db, delivery, "destination_changed")
                setting = await db.scalar(
                    select(ChannelSetting).where(ChannelSetting.channel == delivery.channel)
                )
                decision = await endpoint_policy(
                    db,
                    endpoint=endpoint,
                    source_service=request.source_service,
                    event_key=request.event_key,
                    category=request.category,
                    now=started,
                )
                if (setting is not None and not setting.is_enabled) or (
                    setting is None and current_space() != tenant_id
                ):
                    decision = planning.ChannelDecision(planning.SUPPRESSED, "channel_disabled")
                if decision.decision != planning.SEND:
                    previous = delivery.status
                    delivery.status = "suppressed"
                    delivery.status_reason = decision.reason
                    delivery.completed_at = delivery.updated_at = started
                    db.add(
                        DeliveryEvent(
                            id=uuid7(),
                            tenant_id=tenant_id,
                            delivery_id=delivery.id,
                            source="dispatcher",
                            source_event_key=f"{delivery.id}:policy:{uuid7()}",
                            from_status=previous,
                            to_status="suppressed",
                            reason_code=decision.reason,
                            observed_at=started,
                        )
                    )
                    emit(
                        db,
                        aggregate_type="notification_delivery",
                        aggregate_id=delivery.id,
                        event_type="notification.delivery.status_changed",
                        tenant_id=tenant_id,
                        payload={
                            "delivery_id": str(delivery.id),
                            "request_id": str(delivery.request_id),
                            "from_status": previous,
                            "to_status": "suppressed",
                            "reason_code": decision.reason,
                        },
                    )
                    await db.commit()
                    return SendResult("permanent_failure", None, error_code=decision.reason)
                provider = await db.get(
                    ProviderAccount, delivery.provider_account_id, with_for_update=True
                )
                expected_revision = self.provider_revisions.get(delivery.provider_account_id)
                if provider is not None and (
                    expected_revision is not None and provider.updated_at != expected_revision
                ):
                    raise ConflictError("provider changed; rebuild the dispatch transport")
                sender = await db.get(
                    SenderIdentity, delivery.sender_identity_id, with_for_update=True
                )
                route = await db.get(RoutingRule, delivery.routing_rule_id, with_for_update=True)
                version = await db.get(TemplateVersion, delivery.template_version_id)
                variant = (
                    await db.get(TemplateVariant, version.template_variant_id) if version else None
                )
                template = (
                    await db.get(NotificationTemplate, variant.template_id) if variant else None
                )
                if (
                    provider is None
                    or provider.status != "active"
                    or sender is None
                    or not sender.is_active
                    or sender.verification_status != "verified"
                    or route is None
                    or not route.is_active
                    or variant is None
                    or not variant.is_active
                    or template is None
                    or not template.is_active
                ):
                    return await fail_preflight(db, delivery, "configuration_revoked")
                if delivery.provider_template_binding_id:
                    binding = await db.get(
                        ProviderTemplateBinding,
                        delivery.provider_template_binding_id,
                        with_for_update=True,
                    )
                    if binding is None or binding.approval_status != "approved":
                        return await fail_preflight(
                            db, delivery, "provider_template_approval_unavailable"
                        )
                cutoff = started - dt.timedelta(minutes=1)
                account_used = (
                    await db.scalar(
                        select(func.count(DeliveryAttempt.id))
                        .select_from(DeliveryAttempt)
                        .where(
                            DeliveryAttempt.provider_account_id == delivery.provider_account_id,
                            DeliveryAttempt.started_at > cutoff,
                        )
                    )
                    or 0
                )
                channel_used = (
                    await db.scalar(
                        select(func.count(DeliveryAttempt.id))
                        .select_from(DeliveryAttempt)
                        .join(
                            NotificationDelivery,
                            NotificationDelivery.id == DeliveryAttempt.delivery_id,
                        )
                        .where(
                            NotificationDelivery.channel == delivery.channel,
                            DeliveryAttempt.started_at > cutoff,
                        )
                    )
                    or 0
                )
                if (
                    account_used >= self.per_provider_minute
                    or channel_used >= self.per_space_channel_minute
                ):
                    delivery.next_attempt_at = started + dt.timedelta(seconds=60)
                    delivery.status_reason = "local_capacity_limit"
                    await db.commit()
                    return SendResult(
                        "retryable_failure",
                        None,
                        error_code="local_capacity_limit",
                        retry_after_seconds=60,
                    )
                attempt_number = delivery.attempt_count + 1
                # Allocate the native correlation reference under the same claim lock.
                command = replace(command, attempt_key=f"{delivery_id}:{attempt_number}")
                timeout_seconds = route.timeout_seconds if route is not None else 20
                db.add(
                    DeliveryAttempt(
                        id=uuid7(),
                        tenant_id=tenant_id,
                        delivery_id=delivery.id,
                        attempt_number=attempt_number,
                        provider_account_id=delivery.provider_account_id,
                        sender_identity_id=delivery.sender_identity_id,
                        attempt_key=command.attempt_key,
                        provider_message_id=None,
                        started_at=started,
                        completed_at=None,
                        latency_ms=None,
                        outcome="in_progress",
                        http_status=None,
                        provider_error_code=None,
                        error_class=None,
                        retry_after_at=None,
                        request_sha256=hashlib.sha256(repr(command).encode()).digest(),
                        response_sha256=None,
                        metadata_json=None,
                    )
                )
                delivery.status = "sending"
                delivery.attempt_count = attempt_number
                delivery.updated_at = started
                await db.commit()

        # Deliberately outside every database transaction.
        adapter = self.adapters.get(delivery.provider_account_id)
        if adapter is None:
            result = SendResult("permanent_failure", None, error_code="adapter_not_configured")
        else:
            try:
                async with asyncio.timeout(timeout_seconds):
                    result = await adapter.send(command)
            except (TimeoutError, httpx.TransportError):
                result = SendResult("unknown", None, error_code="ambiguous_transport")

        await self._finalize(tenant_id, delivery_id, attempt_number, started, result)
        return result

    async def _finalize(
        self,
        tenant_id: uuid.UUID,
        delivery_id: uuid.UUID,
        attempt_number: int,
        started: dt.datetime,
        result: SendResult,
    ) -> None:
        completed = utcnow()
        with tenant_scope(tenant_id):
            async with self.factory() as db:
                delivery = await db.get(NotificationDelivery, delivery_id, with_for_update=True)
                if delivery is None:
                    raise NotFoundError("delivery not found")
                attempt = await db.scalar(
                    select(DeliveryAttempt)
                    .where(
                        DeliveryAttempt.delivery_id == delivery_id,
                        DeliveryAttempt.attempt_number == attempt_number,
                    )
                    .with_for_update()
                )
                if attempt is None or attempt.outcome != "in_progress":
                    raise ConflictError("attempt has already been finalized")
                if attempt.provider_message_id is not None and (
                    result.provider_message_id not in {None, attempt.provider_message_id}
                    or result.outcome in {"retryable_failure", "permanent_failure"}
                ):
                    # Signed receipt evidence arrived while provider IO was in flight.
                    # Contradictory HTTP results cannot replace its identity or enable retry.
                    result = replace(
                        result,
                        outcome="unknown",
                        provider_message_id=attempt.provider_message_id,
                        error_code="provider_result_conflicts_with_receipt",
                    )
                attempt.outcome = result.outcome
                attempt.provider_message_id = (
                    result.provider_message_id or attempt.provider_message_id
                )
                attempt.completed_at = completed
                attempt.latency_ms = int((completed - started).total_seconds() * 1000)
                attempt.http_status = result.http_status
                attempt.provider_error_code = result.error_code
                attempt.response_sha256 = (
                    hashlib.sha256(result.response_body).digest() if result.response_body else None
                )
                rule = await db.get(RoutingRule, delivery.routing_rule_id)
                max_attempts = rule.max_attempts if rule is not None else 3
                initial_backoff = rule.initial_backoff_seconds if rule is not None else 5
                max_backoff = rule.max_backoff_seconds if rule is not None else 300
                last_retry = await db.scalar(
                    select(DeliveryEvent)
                    .where(
                        DeliveryEvent.delivery_id == delivery_id,
                        DeliveryEvent.source == "manual_retry",
                    )
                    .order_by(DeliveryEvent.observed_at.desc(), DeliveryEvent.id.desc())
                    .limit(1)
                )
                retry_start = (
                    int(last_retry.metadata_json.get("attempt_count", 0))
                    if last_retry is not None and last_retry.metadata_json
                    else 0
                )
                if delivery.attempt_count != attempt_number or retry_start >= attempt_number:
                    # A receipt may fail this attempt and permit a manual retry while
                    # its HTTP response is still in flight. Keep historical transport
                    # evidence, but never project it into the newer dispatch cycle.
                    await db.commit()
                    return
                cycle_attempt = attempt_number - retry_start

                target = {
                    "accepted": "accepted",
                    "retryable_failure": "retry_wait",
                    "permanent_failure": "failed",
                    # Ambiguous results remain in the reconciliation lane. Marking
                    # them failed would make a blind retry look safe and duplicate a send.
                    "unknown": "sending",
                }[result.outcome]
                previous = delivery.status
                if result.outcome == "retryable_failure" and previous == "sending":
                    if cycle_attempt >= max_attempts:
                        delivery.status = "failed"
                        delivery.status_reason = "max_attempts_exceeded"
                        delivery.failed_at = completed
                        delivery.completed_at = completed
                    else:
                        delivery.status = "retry_wait"
                        if result.retry_after_seconds:
                            wait_seconds = result.retry_after_seconds
                        else:
                            wait_seconds = backoff_seconds(
                                cycle_attempt,
                                initial=initial_backoff,
                                maximum=max_backoff,
                                stable_key=delivery.id,
                            )
                        delivery.next_attempt_at = completed + dt.timedelta(seconds=wait_seconds)
                        delivery.status_reason = result.error_code or "provider_retryable_failure"
                elif should_advance(previous, target):
                    delivery.status = target
                    if target == "accepted":
                        delivery.accepted_at = completed
                    elif target == "failed":
                        delivery.failed_at = completed
                        delivery.completed_at = completed
                delivery.provider_message_id = (
                    result.provider_message_id or delivery.provider_message_id
                )
                if result.outcome == "unknown" and delivery.status == "sending":
                    delivery.status_reason = result.error_code or "ambiguous_provider_result"
                delivery.updated_at = completed
                db.add(
                    DeliveryEvent(
                        id=uuid7(),
                        tenant_id=tenant_id,
                        delivery_id=delivery.id,
                        source="dispatcher",
                        source_event_key=f"{delivery.id}:{attempt_number}",
                        from_status=previous,
                        to_status=delivery.status,
                        reason_code=result.error_code,
                        provider_occurred_at=None,
                        observed_at=completed,
                        metadata_json=None,
                    )
                )
                if delivery.status != previous:
                    emit(
                        db,
                        aggregate_type="notification_delivery",
                        aggregate_id=delivery.id,
                        event_type="notification.delivery.status_changed",
                        tenant_id=tenant_id,
                        payload={
                            "delivery_id": str(delivery.id),
                            "request_id": str(delivery.request_id),
                            "from_status": previous,
                            "to_status": delivery.status,
                            "reason_code": delivery.status_reason or result.error_code,
                        },
                    )
                await db.commit()
