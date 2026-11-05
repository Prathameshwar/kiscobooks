"""Management CRUD/list for notification configuration and evidence (Phases 4-6).

Mirrors the provider-account pattern: every handler declares its permission
(``current.require``), runs under the tenant-scoped session, and returns the lean item
schema. Immutable evidence (template versions, consent events) is created, never mutated;
a template activation whose window overlaps an existing one is a 409; a suppression stores
only the keyed HMAC of the destination, never the raw value.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import uuid
from typing import Any, cast

from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, NotFoundError, ValidationFailedError
from billing_platform.ids import uuid7
from billing_platform.pagination import PageRequest
from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only

from notification.api.auth import Actor, actor
from notification.api.control_schemas import Page
from notification.api.dependencies import session
from notification.api.listing import cursor_codec, keyset_page, page_of
from notification.api.route import ERROR_RESPONSES, StrictRoute
from notification.api.schemas import PageMeta
from notification.api.schemas_mgmt import (
    ActivationCreate,
    ActivationItem,
    AttachmentCreate,
    AttachmentItem,
    BindingApproval,
    BindingCreate,
    BindingItem,
    ConsentRecord,
    ConsentStateItem,
    DeliveryAttachmentCreate,
    DeliveryAttachmentItem,
    RecipientEndpointItem,
    RoutingRuleCreate,
    RoutingRuleItem,
    RoutingRulePage,
    ScanStatusUpdate,
    SenderIdentityCreate,
    SenderIdentityItem,
    SuppressionCreate,
    SuppressionItem,
    SuppressionPage,
    TemplateCreate,
    TemplateItem,
    TemplatePage,
    VariantCreate,
    VariantItem,
    VersionCreate,
    VersionItem,
)
from notification.credentials import validate_sender
from notification.domain.attachments import assert_scan_status
from notification.domain.catalogue import validate_content, validate_schema
from notification.domain.constants import CATEGORIES, CHANNELS
from notification.models import (
    Attachment,
    ConsentEvent,
    ConsentState,
    DeliveryAttachment,
    NotificationTemplate,
    ProviderAccount,
    ProviderTemplateBinding,
    RecipientEndpoint,
    RoutingRule,
    SenderIdentity,
    Suppression,
    TemplateActivation,
    TemplateVariant,
    TemplateVersion,
)
from notification.security import AesGcmCipher, keyed_destination_hash

_ATTACHMENT_TTL = dt.timedelta(days=90)

router = APIRouter(route_class=StrictRoute, responses=ERROR_RESPONSES)


async def _require_exists(
    db: AsyncSession, model: type[Any], obj_id: uuid.UUID, label: str
) -> object:
    row = await db.get(model, obj_id)
    if row is None:
        raise ValidationFailedError(f"unknown {label}", fields={label: "not found"})
    return row


# --- sender identity ----------------------------------------------------------


@router.post("/sender-identities", response_model=SenderIdentityItem, status_code=201)
async def create_sender_identity(
    body: SenderIdentityCreate,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> SenderIdentity:
    current.require("notification.provider.manage")
    provider = cast(
        ProviderAccount,
        await _require_exists(db, ProviderAccount, body.provider_account_id, "provider_account_id"),
    )
    if body.sender_type != provider.channel:
        raise ValidationFailedError("sender type must match its provider channel")
    validate_sender(
        request.app.state.settings,
        provider.credential_ref,
        body.external_sender_id,
        current.tenant_id,
    )
    now = utcnow()
    row = SenderIdentity(
        id=uuid7(),
        tenant_id=current.tenant_id,
        provider_account_id=body.provider_account_id,
        key=body.key,
        sender_type=body.sender_type,
        external_sender_id=body.external_sender_id,
        display_name=body.display_name,
        reply_to_ciphertext=None,
        verification_status="unverified",
        capabilities=body.capabilities,
        verified_at=None,
        is_active=True,
        created_at=now,
        created_by=current.user_id,
        updated_at=now,
        updated_by=current.user_id,
    )
    db.add(row)
    await db.flush()
    return row


@router.get("/sender-identities", response_model=Page[SenderIdentityItem])
async def list_sender_identities(
    provider_account_id: uuid.UUID,
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = None,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[SenderIdentityItem]:
    current.require("notification.provider.read")
    return await page_of(
        db,
        request,
        SenderIdentity,
        SenderIdentityItem,
        limit=limit,
        cursor=cursor,
        where=SenderIdentity.provider_account_id == provider_account_id,
    )


# --- routing rule -------------------------------------------------------------


@router.post("/routing-rules", response_model=RoutingRuleItem, status_code=201)
async def create_routing_rule(
    body: RoutingRuleCreate,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
    idempotency_key: str | None = Header(default=None, min_length=1, max_length=200),
) -> RoutingRule:
    current.require("notification.route.manage")
    from notification.api.control import get_row, queue_job

    receipt = None
    if idempotency_key:
        receipt = await queue_job(
            db,
            current,
            "route.create",
            current.tenant_id,
            idempotency_key,
            body.model_dump(mode="json"),
        )
        if receipt.status == "completed" and receipt.result_id:
            return await get_row(db, RoutingRule, receipt.result_id)
    if body.conditions:
        raise ValidationFailedError(
            "routing conditions are not supported; use typed event/company scope"
        )
    if body.channel not in CHANNELS:
        raise ValidationFailedError("unsupported channel", fields={"channel": "unknown"})
    if body.category != "*" and body.category not in CATEGORIES:
        raise ValidationFailedError("unsupported category", fields={"category": "unknown"})
    provider = cast(
        ProviderAccount,
        await _require_exists(db, ProviderAccount, body.provider_account_id, "provider_account_id"),
    )
    sender = cast(
        SenderIdentity,
        await _require_exists(db, SenderIdentity, body.sender_identity_id, "sender_identity_id"),
    )
    if provider.channel != body.channel:
        raise ValidationFailedError(
            "provider channel does not match rule channel",
            fields={"provider_account_id": "channel mismatch"},
        )
    if sender.provider_account_id != provider.id:
        raise ValidationFailedError(
            "sender identity does not belong to provider account",
            fields={"sender_identity_id": "account mismatch"},
        )
    now = utcnow()
    row = RoutingRule(
        id=uuid7(),
        tenant_id=current.tenant_id,
        company_id=body.company_id,
        event_key=body.event_key,
        category=body.category,
        channel=body.channel,
        provider_account_id=body.provider_account_id,
        sender_identity_id=body.sender_identity_id,
        priority=body.priority,
        weight=body.weight,
        max_attempts=body.max_attempts,
        timeout_seconds=body.timeout_seconds,
        initial_backoff_seconds=body.initial_backoff_seconds,
        max_backoff_seconds=body.max_backoff_seconds,
        conditions=body.conditions,
        is_active=True,
        created_at=now,
        created_by=current.user_id,
        updated_at=now,
        updated_by=current.user_id,
    )
    db.add(row)
    await db.flush()
    if receipt:
        receipt.status, receipt.completed_at, receipt.result_id = "completed", now, row.id
    return row


@router.get("/routing-rules", response_model=RoutingRulePage)
async def list_routing_rules(
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = None,
    channel: str | None = None,
    event_key: str | None = None,
    sort: str = "-created_at",
) -> RoutingRulePage:
    current.require("notification.route.read")
    stmt = select(RoutingRule).options(
        load_only(*(getattr(RoutingRule, name) for name in RoutingRuleItem.model_fields))
    )
    if channel:
        stmt = stmt.where(RoutingRule.channel == channel)
    if event_key:
        stmt = stmt.where(RoutingRule.event_key == event_key)
    rows, nxt, more = await keyset_page(
        db,
        stmt,
        model=RoutingRule,
        page=PageRequest(limit, cursor),
        sort=sort,
        allowed=frozenset({"created_at", "priority"}),
        default="-created_at",
        codec=cursor_codec(request, "routing-rules"),
    )
    return RoutingRulePage(
        items=[RoutingRuleItem.model_validate(r) for r in rows],
        page=PageMeta(next_cursor=nxt, has_more=more),
    )


# --- suppression --------------------------------------------------------------


@router.post("/suppressions", response_model=SuppressionItem, status_code=201)
async def create_suppression(
    body: SuppressionCreate,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
    idempotency_key: str | None = Header(default=None, min_length=1, max_length=200),
) -> Suppression:
    current.require("notification.suppression.manage")
    from notification.api.control import get_row, queue_job

    receipt = None
    if idempotency_key:
        receipt = await queue_job(
            db,
            current,
            "suppression.create",
            current.tenant_id,
            idempotency_key,
            body.model_dump(mode="json"),
        )
        if receipt.status == "completed" and receipt.result_id:
            return await get_row(db, Suppression, receipt.result_id)
    if body.channel not in CHANNELS:
        raise ValidationFailedError("unsupported channel", fields={"channel": "unknown"})
    if body.scope_type not in {"global", "event", "category"}:
        raise ValidationFailedError("bad scope", fields={"scope_type": "global|event|category"})
    # Store only the keyed HMAC of the destination, never the raw value (§3).
    destination = body.destination.strip()
    if body.channel == "email":
        destination = destination.casefold()
    destination_hmac = keyed_destination_hash(destination, request.app.state.data_key)
    now = utcnow()
    if body.valid_to is not None and body.valid_to <= (body.valid_from or now):
        raise ValidationFailedError("suppression end must follow its start")
    if body.scope_type == "category" and body.scope_key not in CATEGORIES:
        raise ValidationFailedError("unknown suppression category")
    row = Suppression(
        id=uuid7(),
        tenant_id=current.tenant_id,
        recipient_endpoint_id=None,
        channel=body.channel,
        destination_hmac=destination_hmac,
        scope_type=body.scope_type,
        scope_key=body.scope_key,
        reason=body.reason,
        source="manual",
        source_event_key=uuid7().hex,
        valid_from=body.valid_from or now,
        valid_to=body.valid_to,
        created_at=now,
        created_by=current.user_id,
    )
    db.add(row)
    await db.flush()
    if receipt:
        receipt.status, receipt.completed_at, receipt.result_id = "completed", now, row.id
    return row


@router.get("/suppressions", response_model=SuppressionPage)
async def list_suppressions(
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = None,
    channel: str | None = None,
    sort: str = "-created_at",
) -> SuppressionPage:
    current.require("notification.suppression.manage")
    stmt = select(Suppression).options(
        load_only(*(getattr(Suppression, name) for name in SuppressionItem.model_fields))
    )
    if channel:
        stmt = stmt.where(Suppression.channel == channel)
    rows, nxt, more = await keyset_page(
        db,
        stmt,
        model=Suppression,
        page=PageRequest(limit, cursor),
        sort=sort,
        allowed=frozenset({"created_at"}),
        default="-created_at",
        codec=cursor_codec(request, "suppressions"),
    )
    return SuppressionPage(
        items=[SuppressionItem.model_validate(r) for r in rows],
        page=PageMeta(next_cursor=nxt, has_more=more),
    )


@router.post("/suppressions/{suppression_id}/expire", response_model=SuppressionItem)
async def expire_suppression(
    suppression_id: uuid.UUID, current: Actor = Depends(actor), db: AsyncSession = Depends(session)
) -> Suppression:
    current.require("notification.suppression.manage")
    row = await db.get(Suppression, suppression_id)
    if row is None:
        raise NotFoundError("suppression not found")
    now = utcnow()
    if row.valid_to is None or row.valid_to > now:
        row.valid_to = now
    await db.flush()
    return row


# --- consent ------------------------------------------------------------------


@router.post("/consent-events", response_model=ConsentStateItem, status_code=201)
async def record_consent(
    body: ConsentRecord,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
    idempotency_key: str | None = Header(default=None, min_length=1, max_length=200),
) -> ConsentState:
    current.require("notification.consent.manage")
    await _require_exists(
        db, RecipientEndpoint, body.recipient_endpoint_id, "recipient_endpoint_id"
    )
    from notification.api.control import get_row, queue_job

    receipt = None
    if idempotency_key:
        receipt = await queue_job(
            db,
            current,
            "consent.record",
            body.recipient_endpoint_id,
            idempotency_key,
            body.model_dump(mode="json"),
        )
        if receipt.status == "completed" and receipt.result_id:
            return await get_row(db, ConsentState, receipt.result_id)
    now = utcnow()
    if body.occurred_at > now + dt.timedelta(seconds=30):
        raise ValidationFailedError("consent evidence cannot occur in the future")
    event = ConsentEvent(
        id=uuid7(),
        tenant_id=current.tenant_id,
        recipient_endpoint_id=body.recipient_endpoint_id,
        purpose=body.purpose,
        state=body.state,
        source=body.source,
        source_event_key=body.source_event_key,
        actor_user_id=current.user_id,
        evidence_ref=body.evidence_ref,
        occurred_at=body.occurred_at,
        recorded_at=now,
    )
    db.add(event)
    await db.flush()

    state = await db.scalar(
        select(ConsentState).where(
            ConsentState.recipient_endpoint_id == body.recipient_endpoint_id,
            ConsentState.purpose == body.purpose,
        )
    )
    if state is None:
        state = ConsentState(
            id=uuid7(),
            tenant_id=current.tenant_id,
            recipient_endpoint_id=body.recipient_endpoint_id,
            purpose=body.purpose,
            state=body.state,
            lawful_basis=body.lawful_basis,
            evidence_ref=body.evidence_ref,
            effective_at=body.occurred_at,
            expires_at=body.expires_at,
            last_event_id=event.id,
            updated_at=now,
        )
        db.add(state)
    elif body.occurred_at >= state.effective_at:
        # A later event supersedes; an out-of-order older event is kept only as evidence.
        state.state = body.state
        state.lawful_basis = body.lawful_basis
        state.evidence_ref = body.evidence_ref
        state.effective_at = body.occurred_at
        state.expires_at = body.expires_at
        state.last_event_id = event.id
        state.updated_at = now
    await db.flush()
    if receipt:
        receipt.status, receipt.completed_at, receipt.result_id = "completed", now, state.id
    return state


@router.get("/consent-states", response_model=Page[ConsentStateItem])
async def list_consent_states(
    recipient_endpoint_id: uuid.UUID,
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = None,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[ConsentStateItem]:
    current.require("notification.consent.manage")
    return await page_of(
        db,
        request,
        ConsentState,
        ConsentStateItem,
        limit=limit,
        cursor=cursor,
        where=ConsentState.recipient_endpoint_id == recipient_endpoint_id,
    )


# --- templates ----------------------------------------------------------------


@router.post("/templates", response_model=TemplateItem, status_code=201)
async def create_template(
    body: TemplateCreate, current: Actor = Depends(actor), db: AsyncSession = Depends(session)
) -> NotificationTemplate:
    current.require("notification.template.manage")
    validate_schema(body.variable_schema)
    if body.category not in CATEGORIES:
        raise ValidationFailedError("unsupported notification category")
    now = utcnow()
    row = NotificationTemplate(
        id=uuid7(),
        tenant_id=current.tenant_id,
        company_id=body.company_id,
        key=body.key,
        event_key=body.event_key,
        category=body.category,
        description=body.description,
        default_locale=body.default_locale,
        variable_schema=body.variable_schema,
        is_active=True,
        created_at=now,
        created_by=current.user_id,
        updated_at=now,
        updated_by=current.user_id,
    )
    db.add(row)
    await db.flush()
    return row


@router.get("/templates", response_model=TemplatePage)
async def list_templates(
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = None,
    event_key: str | None = None,
    sort: str = "-created_at",
) -> TemplatePage:
    current.require("notification.template.read")
    stmt = select(NotificationTemplate).options(
        load_only(*(getattr(NotificationTemplate, name) for name in TemplateItem.model_fields))
    )
    if event_key:
        stmt = stmt.where(NotificationTemplate.event_key == event_key)
    rows, nxt, more = await keyset_page(
        db,
        stmt,
        model=NotificationTemplate,
        page=PageRequest(limit, cursor),
        sort=sort,
        allowed=frozenset({"created_at", "key"}),
        default="-created_at",
        codec=cursor_codec(request, "templates"),
    )
    return TemplatePage(
        items=[TemplateItem.model_validate(r) for r in rows],
        page=PageMeta(next_cursor=nxt, has_more=more),
    )


@router.post("/templates/{template_id}/variants", response_model=VariantItem, status_code=201)
async def create_variant(
    template_id: uuid.UUID,
    body: VariantCreate,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> TemplateVariant:
    current.require("notification.template.manage")
    if body.channel not in CHANNELS:
        raise ValidationFailedError("unsupported channel", fields={"channel": "unknown"})
    if await db.get(NotificationTemplate, template_id) is None:
        raise NotFoundError("template not found")
    row = TemplateVariant(
        id=uuid7(),
        tenant_id=current.tenant_id,
        template_id=template_id,
        channel=body.channel,
        locale=body.locale,
        is_active=True,
        created_at=utcnow(),
        created_by=current.user_id,
    )
    db.add(row)
    await db.flush()
    return row


@router.post("/variants/{variant_id}/versions", response_model=VersionItem, status_code=201)
async def create_version(
    variant_id: uuid.UUID,
    body: VersionCreate,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> TemplateVersion:
    current.require("notification.template.manage")
    variant = await db.get(TemplateVariant, variant_id, with_for_update=True)
    if variant is None:
        raise NotFoundError("variant not found")
    template = await db.get(NotificationTemplate, variant.template_id)
    if template is None:
        raise NotFoundError("template not found")
    validate_content(
        template.variable_schema,
        [body.subject_text, body.body_text, body.body_html],
        body.channel_payload,
    )
    limit = {"sms": 1600, "whatsapp": 4096}.get(variant.channel, 1000000)
    if len(body.body_text.encode()) > limit:
        raise ValidationFailedError("template exceeds its channel limit")
    canonical = json.dumps(body.model_dump(), sort_keys=True, separators=(",", ":")).encode()
    content_sha = hashlib.sha256(canonical).digest()
    highest = await db.scalar(
        select(func.max(TemplateVersion.version)).where(
            TemplateVersion.template_variant_id == variant_id
        )
    )
    row = TemplateVersion(
        id=uuid7(),
        tenant_id=current.tenant_id,
        template_variant_id=variant_id,
        version=(highest or 0) + 1,
        subject_text=body.subject_text,
        body_text=body.body_text,
        body_html=body.body_html,
        channel_payload=body.channel_payload,
        content_sha256=content_sha,
        created_at=utcnow(),
        created_by=current.user_id,
    )
    db.add(row)
    await db.flush()  # unique (variant, content_sha256) rejects an identical re-upload → 409
    return row


@router.post("/variants/{variant_id}/activations", response_model=ActivationItem, status_code=201)
async def create_activation(
    variant_id: uuid.UUID,
    body: ActivationCreate,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> TemplateActivation:
    current.require("notification.template.manage")
    if await db.get(TemplateVariant, variant_id, with_for_update=True) is None:
        raise NotFoundError("variant not found")
    version = await db.get(TemplateVersion, body.template_version_id)
    if version is None or version.template_variant_id != variant_id:
        raise ValidationFailedError(
            "template version does not belong to this variant",
            fields={"template_version_id": "unknown version or variant mismatch"},
        )
    if body.valid_to is not None and body.valid_to <= body.valid_from:
        raise ValidationFailedError("valid_to must be after valid_from")
    # Overlap lock: no two activations for a variant may cover the same instant.
    existing = (
        await db.scalars(
            select(TemplateActivation)
            .where(TemplateActivation.template_variant_id == variant_id)
            .with_for_update()
        )
    ).all()
    for other in existing:
        starts_before_other_ends = other.valid_to is None or body.valid_from < other.valid_to
        other_starts_before_this_ends = body.valid_to is None or other.valid_from < body.valid_to
        if starts_before_other_ends and other_starts_before_this_ends:
            raise ConflictError("an activation window already overlaps this one")
    row = TemplateActivation(
        id=uuid7(),
        tenant_id=current.tenant_id,
        template_variant_id=variant_id,
        template_version_id=body.template_version_id,
        valid_from=body.valid_from,
        valid_to=body.valid_to,
        activated_by=current.user_id,
        activation_reason=body.activation_reason,
        created_at=utcnow(),
    )
    db.add(row)
    await db.flush()
    return row


@router.post(
    "/template-versions/{version_id}/bindings", response_model=BindingItem, status_code=201
)
async def create_binding(
    version_id: uuid.UUID,
    body: BindingCreate,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> ProviderTemplateBinding:
    current.require("notification.template.manage")
    if body.template_version_id != version_id:
        raise ValidationFailedError("binding version must match its path")
    version = cast(
        TemplateVersion,
        await _require_exists(db, TemplateVersion, version_id, "template_version_id"),
    )
    variant = await db.get(TemplateVariant, version.template_variant_id)
    provider = cast(
        ProviderAccount,
        await _require_exists(db, ProviderAccount, body.provider_account_id, "provider_account_id"),
    )
    if (
        variant is None
        or variant.channel != "whatsapp"
        or provider.channel != "whatsapp"
        or provider.provider_key != "meta"
    ):
        raise ValidationFailedError(
            "approved template bindings require a WhatsApp variant and Meta account"
        )
    row = ProviderTemplateBinding(
        id=uuid7(),
        tenant_id=current.tenant_id,
        template_version_id=version_id,
        provider_account_id=body.provider_account_id,
        external_template_id=body.external_template_id,
        external_name=body.external_name,
        external_language=body.external_language,
        external_category=body.external_category,
        approval_status="pending",
        synced_at=utcnow(),
    )
    db.add(row)
    await db.flush()
    return row


@router.patch("/bindings/{binding_id}", response_model=BindingItem)
async def update_binding_approval(
    binding_id: uuid.UUID,
    body: BindingApproval,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> ProviderTemplateBinding:
    current.require("notification.template.manage")
    row = await db.get(ProviderTemplateBinding, binding_id)
    if row is None:
        raise NotFoundError("binding not found")
    if body.approval_status not in {"pending", "approved", "rejected"}:
        raise ValidationFailedError("bad approval_status")
    raise ValidationFailedError("approval is provider-authoritative; request a binding sync job")


# --- attachments --------------------------------------------------------------


@router.post("/attachments", response_model=AttachmentItem, status_code=201)
async def register_attachment(
    body: AttachmentCreate,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Attachment:
    current.require("notification.template.manage")
    now = utcnow()
    attachment_id = uuid7()
    filename_ciphertext = AesGcmCipher(request.app.state.data_key).encrypt(
        body.filename.encode(), nonce=os.urandom(12), associated_data=attachment_id.bytes
    )
    row = Attachment(
        id=attachment_id,
        tenant_id=current.tenant_id,
        storage_key=body.storage_key,
        filename_ciphertext=filename_ciphertext,
        media_type=body.media_type,
        byte_size=body.byte_size,
        sha256=bytes.fromhex(body.sha256_hex),
        scan_status="pending",
        created_at=now,
        expires_at=now + _ATTACHMENT_TTL,
    )
    db.add(row)
    await db.flush()
    return row


@router.patch("/attachments/{attachment_id}/scan", response_model=AttachmentItem)
async def update_scan_status(
    attachment_id: uuid.UUID,
    body: ScanStatusUpdate,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Attachment:
    current.require("notification.attachment.scan")
    assert_scan_status(body.scan_status)
    row = await db.get(Attachment, attachment_id)
    if row is None:
        raise NotFoundError("attachment not found")
    row.scan_status = body.scan_status
    await db.flush()
    return row


@router.post(
    "/deliveries/{delivery_id}/attachments", response_model=DeliveryAttachmentItem, status_code=201
)
async def attach_to_delivery(
    delivery_id: uuid.UUID,
    body: DeliveryAttachmentCreate,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> DeliveryAttachment:
    current.require("notification.template.manage")
    raise ConflictError(
        "external attachments are unavailable until private artifact handoff is configured"
    )


# --- recipient endpoints (read only) ------------------------------------------


@router.get("/recipient-endpoints", response_model=Page[RecipientEndpointItem])
async def list_recipient_endpoints(
    subject_id: uuid.UUID,
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = None,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[RecipientEndpointItem]:
    current.require("notification.recipient.read")
    return await page_of(
        db,
        request,
        RecipientEndpoint,
        RecipientEndpointItem,
        limit=limit,
        cursor=cursor,
        where=RecipientEndpoint.subject_id == subject_id,
    )


@router.get("/recipient-endpoints/{endpoint_id}", response_model=RecipientEndpointItem)
async def recipient_endpoint_detail(
    endpoint_id: uuid.UUID, current: Actor = Depends(actor), db: AsyncSession = Depends(session)
) -> RecipientEndpoint:
    current.require("notification.recipient.read")
    row = await db.get(RecipientEndpoint, endpoint_id)
    if row is None:
        raise NotFoundError("recipient endpoint not found")
    return row
