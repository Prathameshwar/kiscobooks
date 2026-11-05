"""The provider-event normalizer (docs/notification.md §2.2).

The callback route captures a verified provider event into the durable ``provider_event``
inbox and returns fast. This asynchronous pass drains pending events, maps each to a
delivery status, and advances ``notification_delivery`` **without regression**
(``domain/state.should_advance``), writing an immutable ``delivery_event`` and a domain
outbox row. It is the second transaction of the split callback path, so slow
normalization never amplifies provider retries.

Runs as a background job across tenants: the pending scan is a single audited
``unfiltered()`` query, and each event is then processed inside its own tenant scope.
Idempotent — a re-run skips already-processed events, and out-of-order events that would
regress the state are recorded as processed without changing it.
"""

from __future__ import annotations

from dataclasses import replace

from billing_platform.db.tenant_context import tenant_scope, unfiltered
from billing_platform.db.types import utcnow
from billing_platform.ids import uuid7
from billing_platform.outbox import emit
from cryptography.exceptions import InvalidTag
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from notification.domain.state import TERMINAL, should_advance
from notification.models import (
    DeliveryAttempt,
    DeliveryEvent,
    NotificationDelivery,
    ProviderAccount,
    ProviderEvent,
    RecipientEndpoint,
    Suppression,
)
from notification.ownership import space_scope
from notification.providers.normalize import CallbackFact, extract_callback_facts, normalized_status
from notification.security import AesGcmCipher

_STATUS_TIMESTAMP = {
    "accepted": "accepted_at",
    "delivered": "delivered_at",
    "read": "read_at",
    "failed": "failed_at",
}


async def normalize_pending(
    db: AsyncSession, *, cipher: AesGcmCipher | None = None, limit: int = 100
) -> int:
    """Process up to ``limit`` pending provider events. Returns the number handled.

    The caller owns the transaction. A delivery that cannot be matched by
    ``(provider_account_id, provider_message_id)`` is left ``unmatched`` for the
    reconciliation job rather than dropped.
    """
    with unfiltered():
        pending = list(
            (
                await db.scalars(
                    select(ProviderEvent)
                    .where(
                        ProviderEvent.processing_status == "pending",
                        ProviderEvent.event_type.not_like("sns.%"),
                    )
                    .order_by(ProviderEvent.received_at)
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                    .execution_options(populate_existing=True)
                )
            ).all()
        )

    handled = 0
    for event in pending:
        with tenant_scope(event.tenant_id), space_scope(event.space_id):
            try:
                async with db.begin_nested():
                    await _normalize_one(db, event, cipher=cipher)
                    await db.flush()
            except (InvalidTag, ValueError, UnicodeDecodeError, RecursionError, TypeError):
                # Quarantine malformed payloads without losing the rest of the inbox.
                event.processing_status = "error"
                event.processing_error = "invalid_provider_payload"
                event.processed_at = utcnow()
        handled += 1
    with unfiltered():  # flush quarantined rows from the bounded audited inbox scan
        await db.flush()
    return handled


async def _normalize_one(
    db: AsyncSession, event: ProviderEvent, cipher: AesGcmCipher | None = None
) -> None:
    now = utcnow()
    if not event.signature_verified:
        event.processing_status, event.processing_error, event.processed_at = (
            "error",
            "unverified_provider_receipt",
            now,
        )
        return
    account = await db.get(ProviderAccount, event.provider_account_id)
    if account is None:
        return
    if account.channel == "whatsapp" and event.payload_ciphertext is None:
        event.processing_status, event.processing_error, event.processed_at = (
            "error",
            "provider_payload_unavailable",
            now,
        )
        return  # A batch cannot be reconstructed from a first-message projection.
    facts = [
        CallbackFact(
            event.provider_message_id,
            event.event_type,
            event.external_event_key,
            event.provider_occurred_at,
            event.attempt_key,
        )
    ]
    if event.payload_ciphertext:
        # An encrypted batch must never be consumed through its first-message projection.
        if cipher is None:
            return
        raw_body = cipher.decrypt(event.payload_ciphertext, associated_data=account.id.bytes)
        facts = extract_callback_facts(account.channel, raw_body)
        if account.channel == "sms" and event.attempt_key:
            facts = [replace(fact, attempt_key=event.attempt_key) for fact in facts]
    if not facts:
        event.processing_status, event.processed_at = "processed", now
        return  # Verified inbound/non-delivery notifications need no delivery match.
    matched = True
    for fact in sorted(facts, key=lambda item: item.message_id or ""):
        matched = await _apply_fact(db, event, fact) and matched
    event.processing_status = "processed" if matched else "unmatched"
    event.processed_at = now


async def _apply_fact(db: AsyncSession, event: ProviderEvent, fact: CallbackFact) -> bool:
    now = utcnow()
    affects_current = True
    if not fact.message_id:
        return False
    delivery: NotificationDelivery | None = await db.scalar(
        select(NotificationDelivery)
        .where(
            NotificationDelivery.provider_account_id == event.provider_account_id,
            NotificationDelivery.provider_message_id == fact.message_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if delivery is None:
        lookup = await db.scalar(
            select(DeliveryAttempt).where(
                DeliveryAttempt.provider_account_id == event.provider_account_id,
                DeliveryAttempt.attempt_key == fact.attempt_key
                if fact.attempt_key
                else DeliveryAttempt.provider_message_id == fact.message_id,
            )
        )
        # Match finalization's delivery -> attempt lock order.
        candidate = (
            await db.get(NotificationDelivery, lookup.delivery_id, with_for_update=True)
            if lookup
            else None
        )
        attempt = await db.get(DeliveryAttempt, lookup.id, with_for_update=True) if lookup else None
        if attempt is not None and attempt.provider_message_id in {None, fact.message_id}:
            if candidate is not None:
                affects_current = (
                    candidate.attempt_count == attempt.attempt_number
                    and candidate.status in {"sending", "accepted"}
                )
                if affects_current and candidate.provider_message_id not in {None, fact.message_id}:
                    return False
                attempt.provider_message_id = fact.message_id
                event.delivery_id = candidate.id
                if affects_current and candidate.provider_message_id in {None, fact.message_id}:
                    candidate.provider_message_id = fact.message_id
                delivery = candidate
    if delivery is None:
        # Reconciliation waits for this missing message, rather than spinning on an
        # already matched first constituent. The encrypted original remains immutable.
        event.provider_message_id = fact.message_id
        return False

    event.delivery_id = delivery.id
    mapping = normalized_status(delivery.channel, fact.event_type)
    # A complaint/hard bounce remains authoritative after read/cancel/failure.
    # Delivery state monotonicity must never discard a future suppression gate.
    if mapping is not None and mapping[1] in {"hard_bounce", "complaint"}:
        key = f"{event.provider_account_id}:{fact.event_key}"
        prior = await db.scalar(
            select(Suppression.id).where(
                Suppression.source == "provider", Suppression.source_event_key == key
            )
        )
        if prior is None:
            endpoint = await db.get(
                RecipientEndpoint, delivery.recipient_endpoint_id, with_for_update=True
            )
            if endpoint is not None:
                endpoint.last_failure_at, endpoint.health_status = now, "degraded"
                db.add(
                    Suppression(
                        tenant_id=event.tenant_id,
                        channel=delivery.channel,
                        recipient_endpoint_id=endpoint.id,
                        destination_hmac=endpoint.destination_hmac,
                        scope_type="global",
                        scope_key="",
                        reason=mapping[1],
                        source="provider",
                        source_event_key=key,
                        valid_from=now,
                    )
                )
    if affects_current and mapping is not None and should_advance(delivery.status, mapping[0]):
        to_status, reason = mapping
        from_status = delivery.status
        delivery.status = to_status
        delivery.status_reason = reason
        setattr(delivery, _STATUS_TIMESTAMP[to_status], fact.occurred_at or now)
        if to_status in TERMINAL or to_status == "delivered":
            delivery.completed_at = now
        delivery.updated_at = now
        endpoint = await db.get(
            RecipientEndpoint, delivery.recipient_endpoint_id, with_for_update=True
        )
        if endpoint is not None:
            if to_status in {"delivered", "read"}:
                endpoint.last_success_at, endpoint.failure_count, endpoint.health_status = (
                    now,
                    0,
                    "healthy",
                )
            elif to_status == "failed":
                endpoint.last_failure_at = now
                endpoint.failure_count += 1
                endpoint.health_status = "degraded"
        db.add(
            DeliveryEvent(
                id=uuid7(),
                tenant_id=event.tenant_id,
                delivery_id=delivery.id,
                source=delivery.channel,
                source_event_key=f"{event.provider_account_id}:{fact.event_key}",
                from_status=from_status,
                to_status=to_status,
                reason_code=reason,
                provider_occurred_at=fact.occurred_at,
                observed_at=now,
            )
        )
        emit(
            db,
            aggregate_type="notification_delivery",
            aggregate_id=delivery.id,
            event_type="notification.delivery.status_changed",
            tenant_id=event.tenant_id,
            payload={
                "delivery_id": str(delivery.id),
                "from_status": from_status,
                "to_status": to_status,
                "reason_code": reason,
            },
        )

    return True
