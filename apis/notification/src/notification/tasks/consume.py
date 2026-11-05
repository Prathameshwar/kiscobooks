"""The send-command consumer — the planning transaction (docs/notification.md §5).

A business service writes a send command to its outbox; RabbitMQ delivers it here as a
``MessageEnvelope``. :func:`handle_send_command` runs the ten gates in order and, for each
channel that passes, writes a ``notification_delivery`` + encrypted ``notification_content``
snapshot — all in one transaction with a domain event on the local outbox. It is
idempotent on the source ``message_id`` (``notification_request.source_message_id`` is
unique), so a broker redelivery produces one effect.

The handler is pure DB logic and is tested against SQLite. :func:`run_consumer` is the
thin aio-pika entrypoint that binds it to a live broker (prod/CI only).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import uuid
from dataclasses import dataclass, field
from typing import Any

from billing_platform.constants import SCOPE_ALL
from billing_platform.db.tenant_context import get_current_tenant, tenant_scope
from billing_platform.db.types import utcnow
from billing_platform.errors import NotFoundError, ValidationFailedError
from billing_platform.ids import uuid7
from billing_platform.messages import MessageEnvelope
from billing_platform.outbox import emit
from sqlalchemy import or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from notification.domain import planning
from notification.domain.catalogue import render_payload, validate_variables
from notification.domain.routing import RouteCandidate, select_route
from notification.domain.template import render, render_html
from notification.events import SendCommand
from notification.models import (
    ChannelSetting,
    ConsentState,
    NotificationContent,
    NotificationDelivery,
    NotificationPreference,
    NotificationRequest,
    NotificationTemplate,
    PlanningOutcome,
    ProviderAccount,
    ProviderTemplateBinding,
    RecipientEndpoint,
    RoutingRule,
    SenderIdentity,
    Suppression,
    TemplateActivation,
    TemplateVariant,
    TemplateVersion,
    UseCaseBinding,
)
from notification.ownership import current_space
from notification.security import AesGcmCipher


@dataclass(slots=True)
class ConsumeResult:
    request_id: uuid.UUID
    deduplicated: bool = False
    deliveries_created: int = 0
    outcomes: dict[str, str] = field(default_factory=dict)


async def _active_endpoint(
    db: AsyncSession,
    *,
    subject_type: str,
    subject_id: uuid.UUID,
    channel: str,
    company_id: uuid.UUID = SCOPE_ALL,
) -> RecipientEndpoint | None:
    rows = await db.scalars(
        select(RecipientEndpoint).where(
            RecipientEndpoint.subject_type == subject_type,
            RecipientEndpoint.subject_id == subject_id,
            RecipientEndpoint.channel == channel,
            RecipientEndpoint.company_id == company_id,
            RecipientEndpoint.is_active.is_(True),
        )
    )
    # Prefer a verified, healthy endpoint; otherwise the first active one.
    candidates = list(rows.all())
    for endpoint in candidates:
        if endpoint.verification_status == "verified" and endpoint.health_status == "healthy":
            return endpoint
    return candidates[0] if candidates else None


async def _preference_enabled(
    db: AsyncSession, *, subject_type: str, subject_id: uuid.UUID, event_key: str, channel: str
) -> bool | None:
    enabled: bool | None = await db.scalar(
        select(NotificationPreference.is_enabled).where(
            NotificationPreference.subject_type == subject_type,
            NotificationPreference.subject_id == subject_id,
            NotificationPreference.event_key == event_key,
            NotificationPreference.channel == channel,
        )
    )
    return enabled


async def _consent_granted(
    db: AsyncSession, *, endpoint_id: uuid.UUID, category: str, now: dt.datetime
) -> bool:
    row = await db.scalar(
        select(ConsentState).where(
            ConsentState.recipient_endpoint_id == endpoint_id, ConsentState.purpose == category
        )
    )
    if row is None:
        return False
    return planning.consent_is_granted(row.state, row.expires_at, now=now)


async def _suppression_reason(
    db: AsyncSession,
    *,
    channel: str,
    destination_hmac: bytes,
    event_key: str,
    category: str,
    now: dt.datetime,
) -> str | None:
    rows = await db.scalars(
        select(Suppression).where(
            Suppression.channel == channel, Suppression.destination_hmac == destination_hmac
        )
    )
    rules = [
        planning.SuppressionRule(r.reason, r.scope_type, r.scope_key, r.valid_from, r.valid_to)
        for r in rows.all()
    ]
    return planning.active_suppression_reason(
        rules, now=now, event_key=event_key, category=category
    )


async def endpoint_policy(
    db: AsyncSession,
    *,
    endpoint: RecipientEndpoint,
    source_service: str,
    event_key: str,
    category: str,
    now: dt.datetime,
) -> planning.ChannelDecision:
    """Shared planning and final dispatch policy, evaluated from current replica facts."""
    preference = None
    if source_service != "vouchers":
        preference = await _preference_enabled(
            db,
            subject_type=endpoint.subject_type,
            subject_id=endpoint.subject_id,
            event_key=event_key,
            channel=endpoint.channel,
        )
    consent = await _consent_granted(db, endpoint_id=endpoint.id, category=category, now=now)
    suppression = await _suppression_reason(
        db,
        channel=endpoint.channel,
        destination_hmac=endpoint.destination_hmac,
        event_key=event_key,
        category=category,
        now=now,
    )
    return planning.decide(
        category=category,
        has_endpoint=endpoint.is_active,
        preference_enabled=preference,
        consent_granted=consent,
        suppression_reason=suppression,
    )


async def _resolve_template_version(
    db: AsyncSession,
    *,
    company_id: uuid.UUID,
    event_key: str,
    channel: str,
    locale: str | None,
    now: dt.datetime,
    trigger_key: str | None = None,
) -> TemplateVersion | None:
    templates = list(
        (
            await db.scalars(
                select(NotificationTemplate).where(
                    NotificationTemplate.event_key == event_key,
                    NotificationTemplate.company_id.in_([company_id, SCOPE_ALL]),
                    NotificationTemplate.is_active.is_(True),
                )
            )
        ).all()
    )
    assignments = list(
        await db.scalars(
            select(UseCaseBinding).where(
                UseCaseBinding.event_key == event_key,
                UseCaseBinding.channel == channel,
                UseCaseBinding.company_id.in_([company_id, SCOPE_ALL]),
                UseCaseBinding.trigger_key == trigger_key if trigger_key else true(),
            )
        )
    )
    configured = bool(assignments)
    assignments = [
        a for a in assignments if a.valid_from <= now and (a.valid_to is None or a.valid_to > now)
    ]
    if not assignments and (configured or current_space() != get_current_tenant()):
        return None
    if assignments:
        best = min(a.company_id != company_id for a in assignments)
        eligible = [a for a in assignments if (a.company_id != company_id) == best]
        if len(eligible) != 1:
            return None
        templates = [t for t in templates if t.id == eligible[0].template_id]
    if not templates:
        return None
    # Legacy data may have no assignments yet. Only an unambiguous candidate at
    # the most specific scope is executable during the compatibility period.
    best = min(t.company_id != company_id for t in templates)
    templates = [t for t in templates if (t.company_id != company_id) == best]
    if len(templates) != 1:
        return None
    template = templates[0]

    wanted_locales = [loc for loc in (locale, template.default_locale) if loc]
    for loc in wanted_locales:
        variant = await db.scalar(
            select(TemplateVariant).where(
                TemplateVariant.template_id == template.id,
                TemplateVariant.channel == channel,
                TemplateVariant.locale == loc,
                TemplateVariant.is_active.is_(True),
            )
        )
        if variant is None:
            continue
        activations = list(
            await db.scalars(
                select(TemplateActivation).where(
                    TemplateActivation.template_variant_id == variant.id,
                    TemplateActivation.valid_from <= now,
                    or_(TemplateActivation.valid_to.is_(None), TemplateActivation.valid_to > now),
                )
            )
        )
        if len(activations) > 1:
            return None  # Corrupt/overlapping historical data must never choose arbitrarily.
        if activations:
            return await db.get(TemplateVersion, activations[0].template_version_id)
    return None


async def _resolve_route(
    db: AsyncSession,
    *,
    company_id: uuid.UUID,
    event_key: str,
    category: str,
    channel: str,
    stable_key: uuid.UUID,
) -> RoutingRule | None:
    rules = list(
        (
            await db.scalars(
                select(RoutingRule)
                .join(ProviderAccount, ProviderAccount.id == RoutingRule.provider_account_id)
                .join(SenderIdentity, SenderIdentity.id == RoutingRule.sender_identity_id)
                .where(
                    ProviderAccount.status == "active",
                    SenderIdentity.is_active.is_(True),
                    SenderIdentity.verification_status == "verified",
                    RoutingRule.channel == channel,
                    RoutingRule.company_id.in_([company_id, SCOPE_ALL]),
                    RoutingRule.is_active.is_(True),
                )
            )
        ).all()
    )
    candidates = [
        RouteCandidate(
            id=r.id,
            company_id=r.company_id,
            event_key=r.event_key,
            category=r.category,
            priority=r.priority,
            weight=r.weight,
            is_active=r.is_active,
            conditions=r.conditions,
        )
        for r in rules
    ]
    try:
        chosen = select_route(
            candidates,
            company_id=company_id,
            event_key=event_key,
            category=category,
            stable_key=stable_key,
        )
    except NotFoundError:
        return None
    return next((r for r in rules if r.id == chosen.id), None)


async def handle_send_command(
    db: AsyncSession,
    envelope: MessageEnvelope,
    *,
    cipher: AesGcmCipher,
    key_ref: str,
    endpoint_id: uuid.UUID | None = None,
    content_retention_days: int = 90,
) -> ConsumeResult:
    """Plan a send command into deliveries. Idempotent on ``envelope.message_id``.

    The caller owns the transaction (commit/rollback); this stages rows and one outbox
    event. Runs inside the command's tenant scope so every query is tenant-filtered.
    """
    command = SendCommand.model_validate(envelope.payload)
    command.validate_vocabulary()
    now = utcnow()

    with tenant_scope(envelope.tenant_id):
        existing = await db.scalar(
            select(NotificationRequest.id).where(
                NotificationRequest.source_message_id == envelope.message_id
            )
        )
        if existing is not None:
            return ConsumeResult(request_id=existing, deduplicated=True)

        request_id = uuid7()
        context_plain = json.dumps(command.variables, sort_keys=True, default=str).encode()
        request = NotificationRequest(
            id=request_id,
            tenant_id=envelope.tenant_id,
            status="processing",
            company_id=command.company_id,
            source_service=command.source_service,
            source_message_id=envelope.message_id,
            source_event_key=command.source_event_key,
            event_key=command.event_key,
            category=command.category,
            aggregate_type=command.aggregate_type,
            aggregate_id=command.aggregate_id,
            correlation_id=command.correlation_id,
            causation_id=command.causation_id,
            trace_id=envelope.trace_id,
            priority=command.priority,
            scheduled_at=command.scheduled_at,
            expires_at=command.expires_at,
            context_ciphertext=cipher.encrypt(
                context_plain, nonce=os.urandom(12), associated_data=request_id.bytes
            ),
            context_sha256=hashlib.sha256(context_plain).digest(),
            encryption_key_ref=key_ref,
            received_at=now,
        )
        db.add(request)
        await db.flush()

        result = ConsumeResult(request_id=request_id)
        for channel in command.channels:
            outcome = await _plan_channel(
                db,
                command=command,
                channel=channel,
                request_id=request_id,
                tenant_id=envelope.tenant_id,
                cipher=cipher,
                key_ref=key_ref,
                now=now,
                endpoint_id=endpoint_id,
                content_retention_days=content_retention_days,
            )
            reason = (
                outcome.split(":", 1)[1]
                if ":" in outcome
                else ("planned" if outcome == planning.SEND else outcome)
            )
            outcome = outcome.split(":", 1)[0]
            result.outcomes[channel] = outcome
            db.add(
                PlanningOutcome(
                    tenant_id=envelope.tenant_id,
                    request_id=request_id,
                    channel=channel,
                    decision=outcome,
                    reason_code=reason,
                )
            )
            if outcome == planning.SEND:
                result.deliveries_created += 1

        request.status = "completed"
        request.completed_at = now
        emit(
            db,
            aggregate_type="notification_request",
            aggregate_id=request_id,
            event_type="notification.request.planned",
            tenant_id=envelope.tenant_id,
            trace_id=envelope.trace_id,
            payload={
                "request_id": str(request_id),
                "event_key": command.event_key,
                "category": command.category,
                "outcomes": result.outcomes,
            },
        )
        await db.flush()
        return result


async def _plan_channel(
    db: AsyncSession,
    *,
    command: SendCommand,
    channel: str,
    request_id: uuid.UUID,
    tenant_id: uuid.UUID,
    cipher: AesGcmCipher,
    key_ref: str,
    now: dt.datetime,
    endpoint_id: uuid.UUID | None = None,
    content_retention_days: int = 90,
) -> str:
    if command.expires_at is not None and command.expires_at <= now:
        return "expired:request_expired"
    setting = await db.scalar(select(ChannelSetting).where(ChannelSetting.channel == channel))
    if (setting is not None and not setting.is_enabled) or (
        setting is None and current_space() != get_current_tenant()
    ):
        return "skipped:channel_disabled"
    endpoint = await _active_endpoint(
        db,
        subject_type=command.subject_type,
        subject_id=command.subject_id,
        channel=channel,
        company_id=command.company_id if command.source_service == "vouchers" else SCOPE_ALL,
    )
    if endpoint_id is not None:
        endpoint = await db.get(RecipientEndpoint, endpoint_id)
        if endpoint is not None and (
            endpoint.subject_id != command.subject_id
            or endpoint.subject_type != command.subject_type
            or endpoint.channel != channel
            or (command.source_service == "vouchers" and endpoint.company_id != command.company_id)
            or not endpoint.is_active
        ):
            endpoint = None
    preference = None
    consent = False
    suppression = None
    if endpoint is not None:
        if command.source_service != "vouchers":
            # Generic preference keys have no company dimension; party endpoint
            # consent and suppression remain the voucher-specific delivery gates.
            preference = await _preference_enabled(
                db,
                subject_type=command.subject_type,
                subject_id=command.subject_id,
                event_key=command.event_key,
                channel=channel,
            )
        consent = await _consent_granted(
            db, endpoint_id=endpoint.id, category=command.category, now=now
        )
        suppression = await _suppression_reason(
            db,
            channel=channel,
            destination_hmac=endpoint.destination_hmac,
            event_key=command.event_key,
            category=command.category,
            now=now,
        )

    decision = planning.decide(
        category=command.category,
        has_endpoint=endpoint is not None,
        preference_enabled=preference,
        consent_granted=consent,
        suppression_reason=suppression,
    )
    if decision.decision != planning.SEND or endpoint is None:
        return f"{decision.decision}:{decision.reason or 'no_active_endpoint'}"

    version = await _resolve_template_version(
        db,
        company_id=command.company_id,
        event_key=command.event_key,
        channel=channel,
        locale=command.locale,
        now=now,
        trigger_key=command.source_event_key,
    )
    if version is None:
        return "skipped:no_active_template_assignment"
    route = await _resolve_route(
        db,
        company_id=command.company_id,
        event_key=command.event_key,
        category=command.category,
        channel=channel,
        stable_key=command.aggregate_id,
    )
    if route is None:
        return "skipped:no_eligible_route"

    binding_id = None
    if channel == "whatsapp":
        binding = await db.scalar(
            select(ProviderTemplateBinding).where(
                ProviderTemplateBinding.template_version_id == version.id,
                ProviderTemplateBinding.provider_account_id == route.provider_account_id,
                ProviderTemplateBinding.approval_status == "approved",
            )
        )
        if binding is None:
            return "skipped:no_approved_provider_template"
        binding_id = binding.id

    variant = await db.get(TemplateVariant, version.template_variant_id)
    template = await db.get(NotificationTemplate, variant.template_id) if variant else None
    if template is None or template.category != command.category:
        return "skipped:template_purpose_mismatch"
    try:
        validate_variables(template.variable_schema, command.variables)
        subject = render(version.subject_text, command.variables) if version.subject_text else None
        body = render(
            version.body_text,
            command.variables,
            max_bytes={"sms": 1600, "whatsapp": 4096}.get(channel, 1_000_000),
        )
        body_html = render_html(version.body_html, command.variables) if version.body_html else None
        payload = render_payload(version.channel_payload, command.variables)
    except (ValidationFailedError, KeyError):
        return "skipped:template_variables_or_rendering_invalid"
    delivery_id = uuid7()
    assignments = list(
        await db.scalars(
            select(UseCaseBinding).where(
                UseCaseBinding.template_id == template.id,
                UseCaseBinding.event_key == command.event_key,
                UseCaseBinding.trigger_key == command.source_event_key,
                UseCaseBinding.channel == channel,
                UseCaseBinding.company_id.in_([command.company_id, SCOPE_ALL]),
                UseCaseBinding.valid_from <= now,
                or_(UseCaseBinding.valid_to.is_(None), UseCaseBinding.valid_to > now),
            )
        )
    )
    assignment = (
        min(assignments, key=lambda row: row.company_id != command.company_id)
        if assignments
        else None
    )

    is_scheduled = command.scheduled_at is not None and command.scheduled_at > now
    db.add(
        NotificationDelivery(
            id=delivery_id,
            tenant_id=tenant_id,
            status="scheduled" if is_scheduled else "pending",
            request_id=request_id,
            recipient_endpoint_id=endpoint.id,
            channel=channel,
            destination_hmac=endpoint.destination_hmac,
            destination_masked=endpoint.destination_masked,
            template_version_id=version.id,
            provider_template_binding_id=binding_id,
            use_case_binding_id=assignment.id if assignment else None,
            provider_account_id=route.provider_account_id,
            sender_identity_id=route.sender_identity_id,
            routing_rule_id=route.id,
            attempt_count=0,
            next_attempt_at=command.scheduled_at if is_scheduled else now,
            created_at=now,
            updated_at=now,
        )
    )
    # Flush the delivery before its content row: no ORM relationship links them, so the
    # unit of work would otherwise order the content insert first and break the FK.
    await db.flush()
    # The rendered snapshot is encrypted at rest, bound to the delivery id, and expires
    # before the delivery evidence (retention §6). Content hash is over the plaintext.
    content_plain = json.dumps(
        {"subject": subject, "body": body, "body_html": body_html, "payload": payload},
        sort_keys=True,
    ).encode()

    def _enc(value: str | None) -> bytes | None:
        if value is None:
            return None
        return cipher.encrypt(
            value.encode(), nonce=os.urandom(12), associated_data=delivery_id.bytes
        )

    db.add(
        NotificationContent(
            delivery_id=delivery_id,
            tenant_id=tenant_id,
            subject_ciphertext=_enc(subject),
            body_text_ciphertext=_enc(body),
            body_html_ciphertext=_enc(body_html),
            payload_ciphertext=_enc(json.dumps(payload, sort_keys=True)),
            content_sha256=hashlib.sha256(content_plain).digest(),
            encryption_key_ref=key_ref,
            created_at=now,
            expires_at=now + dt.timedelta(days=max(90, content_retention_days)),
        )
    )
    return planning.SEND


async def run_consumer(  # pragma: no cover - live-broker transport, exercised in CI
    settings: Any, session_factory: Any
) -> None:
    """Legacy entrypoint is intentionally disabled: it did not authenticate broker sources."""
    raise RuntimeError("use the authenticated, source-scoped notification.tasks.vouchers consumer")
