"""Owner-scoped configuration and operational evidence APIs."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import uuid
from typing import Any

from billing_platform.constants import SCOPE_ALL
from billing_platform.db.tenant_context import get_current_tenant
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, NotFoundError, ValidationFailedError
from billing_platform.ids import uuid7
from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy import and_, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from notification.api.auth import Actor, actor
from notification.api.control_schemas import (
    AssignmentCreate,
    AssignmentItem,
    AttemptItem,
    CallbackConfiguration,
    Channel,
    ChannelPolicy,
    ChannelReadiness,
    DeliveryDetail,
    EffectivePolicy,
    EffectiveResult,
    EndWindow,
    EventItem,
    JobItem,
    Page,
    PlanningItem,
    PreviewRequest,
    PreviewResponse,
    ProviderReceiptItem,
    ReceiptReconciliation,
    RequestDetail,
    RouteDetail,
    RouteUpdate,
    SenderUpdate,
    TemplateDetail,
    TemplateUpdate,
    UseCaseItem,
    VariantUpdate,
    VersionDetail,
)
from notification.api.dependencies import session
from notification.api.listing import page_of
from notification.api.route import ERROR_RESPONSES, StrictRoute
from notification.api.schemas import DeliveryItem, StrictModel
from notification.api.schemas_mgmt import (
    ActivationCreate,
    ActivationItem,
    BindingItem,
    SenderIdentityItem,
    VariantItem,
    VersionItem,
)
from notification.domain.catalogue import PROVIDERS, USE_CASES, definition, validate_variables
from notification.domain.template import render, render_html
from notification.models import (
    ChannelSetting,
    DeliveryAttempt,
    DeliveryEvent,
    NotificationDelivery,
    NotificationJob,
    NotificationRequest,
    NotificationSpace,
    NotificationTemplate,
    PlanningOutcome,
    ProviderAccount,
    ProviderEvent,
    ProviderTemplateBinding,
    RoutingRule,
    SenderIdentity,
    TemplateActivation,
    TemplateVariant,
    TemplateVersion,
    UseCaseBinding,
)
from notification.ownership import current_space

router = APIRouter(route_class=StrictRoute, responses=ERROR_RESPONSES)


@router.get("/provider-events", response_model=Page[ProviderReceiptItem])
async def provider_receipts(
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = None,
    provider_account_id: uuid.UUID | None = None,
    processing_status: str | None = Query(None, alias="status"),
) -> Any:
    current.require("notification.delivery.read")
    if processing_status is not None and processing_status not in {
        "pending",
        "processed",
        "unmatched",
        "error",
    }:
        raise ValidationFailedError("unsupported receipt processing status")
    return await page_of(
        db,
        request,
        ProviderEvent,
        ProviderReceiptItem,
        limit=limit,
        cursor=cursor,
        sort="-received_at",
        where=and_(
            (
                ProviderEvent.provider_account_id == provider_account_id
                if provider_account_id
                else true()
            ),
            ProviderEvent.processing_status == processing_status if processing_status else true(),
        ),
    )


@router.get("/provider-events/{event_id}", response_model=ProviderReceiptItem)
async def provider_receipt_detail(
    event_id: uuid.UUID, current: Actor = Depends(actor), db: AsyncSession = Depends(session)
) -> ProviderEvent:
    current.require("notification.delivery.read")
    return await get_row(db, ProviderEvent, event_id)


async def get_row[T](
    db: AsyncSession, model: type[T], identity: uuid.UUID, *, lock: bool = False
) -> T:
    row = await db.get(model, identity, with_for_update=lock)
    if row is None:
        raise NotFoundError("notification resource not found")
    return row


def company_access(current: Actor, permission: str, company_id: uuid.UUID) -> None:
    if company_id == SCOPE_ALL:
        current.require(permission)
    else:
        current.require_company(permission, company_id)


def checked_changes(row: Any, body: StrictModel) -> dict[str, Any]:
    changes = body.model_dump(exclude_unset=True)
    expected = changes.pop("expected_updated_at", None)
    if expected is not None and expected != row.updated_at:
        raise ConflictError("configuration changed; refresh before saving")
    return changes


async def readiness(db: AsyncSession, channel: str) -> ChannelReadiness:
    policy = await db.scalar(select(ChannelSetting).where(ChannelSetting.channel == channel))
    enabled = (
        policy.is_enabled if policy is not None else current_space() == get_current_tenant()
    )  # compatibility for existing installs
    provider = await db.scalar(
        select(ProviderAccount.id).where(
            ProviderAccount.channel == channel, ProviderAccount.status == "active"
        )
    )
    sender = await db.scalar(
        select(SenderIdentity.id)
        .join(ProviderAccount, ProviderAccount.id == SenderIdentity.provider_account_id)
        .where(
            ProviderAccount.channel == channel,
            ProviderAccount.status == "active",
            SenderIdentity.is_active.is_(True),
            SenderIdentity.verification_status == "verified",
        )
    )
    reasons = []
    if not enabled:
        reasons.append("channel_disabled")
    if provider is None:
        reasons.append("no_active_provider")
    if sender is None:
        reasons.append("no_verified_sender")
    return ChannelReadiness.model_validate(
        {"channel": channel, "is_enabled": enabled, "ready": not reasons, "reasons": reasons}
    )


@router.get("/channels", response_model=list[ChannelReadiness])
async def channels(current: Actor = Depends(actor), db: AsyncSession = Depends(session)) -> Any:
    current.require("notification.provider.read")
    return [await readiness(db, ch) for ch in sorted(set(PROVIDERS.values()))]


@router.get("/provider-types", response_model=dict[str, str])
async def provider_types(current: Actor = Depends(actor)) -> dict[str, str]:
    current.require("notification.provider.read")
    return PROVIDERS


@router.get("/credential-bindings", response_model=list[str])
async def credential_bindings(request: Request, current: Actor = Depends(actor)) -> list[str]:
    current.require("notification.provider.manage")
    # This catalogue has no database-session dependency to establish space_scope.
    # Select the realm from verified authority instead of an absent ContextVar.
    settings = request.app.state.settings
    space = settings.platform_space_id if current.platform else current.tenant_id
    return sorted(
        reference
        for reference, binding in settings.credential_bindings.items()
        if binding.tenant_id == current.tenant_id and binding.space_id == space
    )


@router.get("/use-cases", response_model=list[UseCaseItem])
async def use_cases(current: Actor = Depends(actor)) -> Any:
    current.require("notification.template.read")
    from dataclasses import asdict

    return [
        asdict(c) for c in USE_CASES if c.owner == ("platform" if current.platform else "tenant")
    ]


@router.put("/channel-settings/{channel}", response_model=ChannelReadiness)
async def set_channel(
    channel: Channel,
    body: ChannelPolicy,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Any:
    current.require("notification.provider.manage")
    # Serialize first-write races through the owner-space row.
    space = await db.get(NotificationSpace, current_space(), with_for_update=True)
    if space is None:
        space = NotificationSpace(
            id=current_space(),
            tenant_id=current.tenant_id,
            kind="platform" if current.platform else "tenant",
        )
        db.add(space)
        await db.flush()
    check = await readiness(db, channel)
    if body.is_enabled and any(r != "channel_disabled" for r in check.reasons):
        raise ConflictError("provider and verified sender must be ready before enabling")
    row = await db.scalar(
        select(ChannelSetting).where(ChannelSetting.channel == channel).with_for_update()
    )
    if row is None:
        row = ChannelSetting(
            tenant_id=current.tenant_id,
            channel=channel,
            is_enabled=body.is_enabled,
            created_by=current.user_id,
        )
        db.add(row)
    row.is_enabled, row.updated_by, row.updated_at = body.is_enabled, current.user_id, utcnow()
    await db.flush()
    return await readiness(db, channel)


@router.get("/sender-identities/{sender_id}", response_model=SenderIdentityItem)
async def sender_detail(
    sender_id: uuid.UUID, current: Actor = Depends(actor), db: AsyncSession = Depends(session)
) -> Any:
    current.require("notification.provider.read")
    return await get_row(db, SenderIdentity, sender_id)


@router.patch("/sender-identities/{sender_id}", response_model=SenderIdentityItem)
async def sender_update(
    sender_id: uuid.UUID,
    body: SenderUpdate,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Any:
    current.require("notification.provider.manage")
    row = await get_row(db, SenderIdentity, sender_id, lock=True)
    for key, value in checked_changes(row, body).items():
        if value is None:
            raise ValidationFailedError("sender fields cannot be null")
        if key == "is_active" and value is True and not row.is_active:
            row.verification_status, row.verified_at = "unverified", None
        setattr(row, key, value)
    row.updated_at, row.updated_by = utcnow(), current.user_id
    return row


async def queue_job(
    db: AsyncSession,
    current: Actor,
    kind: str,
    target: uuid.UUID,
    key: str,
    parameters: dict[str, Any] | None = None,
) -> NotificationJob:
    digest = hashlib.sha256(f"{current.user_id}:{key}".encode()).digest()
    request_hash = hashlib.sha256(json.dumps(parameters or {}, sort_keys=True).encode()).digest()
    row = await db.scalar(
        select(NotificationJob).where(NotificationJob.request_key == digest).with_for_update()
    )
    if row is not None:
        if (
            row.kind != kind
            or row.target_id != target
            or (row.request_hash is not None and row.request_hash != request_hash)
        ):
            raise ConflictError("idempotency key belongs to another command")
        return row
    row = NotificationJob(
        id=uuid7(),
        tenant_id=current.tenant_id,
        kind=kind,
        target_id=target,
        actor_user_id=current.user_id,
        request_key=digest,
        request_hash=request_hash,
    )
    db.add(row)
    await db.flush()
    return row


@router.post("/sender-identities/{sender_id}/sync", response_model=JobItem, status_code=202)
async def sender_sync(
    sender_id: uuid.UUID,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
    idempotency_key: str = Header(min_length=1, max_length=200),
) -> Any:
    current.require("notification.provider.manage")
    await get_row(db, SenderIdentity, sender_id)
    return await queue_job(db, current, "sender.sync", sender_id, idempotency_key)


@router.post("/provider-accounts/{provider_id}/validate", response_model=JobItem, status_code=202)
async def provider_validate(
    provider_id: uuid.UUID,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
    idempotency_key: str = Header(min_length=1, max_length=200),
) -> Any:
    current.require("notification.provider.manage")
    await get_row(db, ProviderAccount, provider_id)
    return await queue_job(db, current, "provider.validate", provider_id, idempotency_key)


@router.post("/bindings/{binding_id}/sync", response_model=JobItem, status_code=202)
async def binding_sync(
    binding_id: uuid.UUID,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
    idempotency_key: str = Header(min_length=1, max_length=200),
) -> Any:
    current.require("notification.template.manage")
    await get_row(db, ProviderTemplateBinding, binding_id)
    return await queue_job(db, current, "binding.sync", binding_id, idempotency_key)


@router.get("/jobs/{job_id}", response_model=JobItem)
async def job_detail(
    job_id: uuid.UUID, current: Actor = Depends(actor), db: AsyncSession = Depends(session)
) -> NotificationJob:
    row = await get_row(db, NotificationJob, job_id)
    permission = (
        "notification.template.read"
        if row.kind in {"binding.sync", "template.activate"}
        else "notification.delivery.read"
        if row.kind.startswith("delivery.")
        else "notification.consent.manage"
        if row.kind.startswith("consent.")
        else "notification.suppression.manage"
        if row.kind.startswith("suppression.")
        else "notification.route.read"
        if row.kind.startswith("route.")
        else "notification.provider.read"
    )
    current.require(permission)
    return row


@router.get("/templates/{template_id}", response_model=TemplateDetail)
async def template_detail(
    template_id: uuid.UUID, current: Actor = Depends(actor), db: AsyncSession = Depends(session)
) -> Any:
    current.require_endpoint("notification.template.read")
    row = await get_row(db, NotificationTemplate, template_id)
    company_access(current, "notification.template.read", row.company_id)
    return row


@router.patch("/templates/{template_id}", response_model=TemplateDetail)
async def template_update(
    template_id: uuid.UUID,
    body: TemplateUpdate,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Any:
    current.require_endpoint("notification.template.manage")
    row = await get_row(db, NotificationTemplate, template_id, lock=True)
    company_access(current, "notification.template.manage", row.company_id)
    if "is_active" in body.model_fields_set and body.is_active is None:
        raise ValidationFailedError("is_active cannot be null")
    for key, value in checked_changes(row, body).items():
        setattr(row, key, value)
    row.updated_at, row.updated_by = utcnow(), current.user_id
    return row


@router.get("/templates/{template_id}/variants", response_model=Page[VariantItem])
async def variants(
    template_id: uuid.UUID,
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = None,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Any:
    await template_detail(template_id, current, db)
    return await page_of(
        db,
        request,
        TemplateVariant,
        VariantItem,
        limit=limit,
        cursor=cursor,
        where=TemplateVariant.template_id == template_id,
    )


@router.get("/variants/{variant_id}/versions", response_model=Page[VersionItem])
async def versions(
    variant_id: uuid.UUID,
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = None,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Any:
    current.require("notification.template.read")
    await get_row(db, TemplateVariant, variant_id)
    return await page_of(
        db,
        request,
        TemplateVersion,
        VersionItem,
        limit=limit,
        cursor=cursor,
        where=TemplateVersion.template_variant_id == variant_id,
    )


@router.get("/template-versions/{version_id}", response_model=VersionDetail)
async def version_detail(
    version_id: uuid.UUID, current: Actor = Depends(actor), db: AsyncSession = Depends(session)
) -> Any:
    current.require("notification.template.read")
    return await get_row(db, TemplateVersion, version_id)


@router.post("/template-versions/{version_id}/preview", response_model=PreviewResponse)
async def preview(
    version_id: uuid.UUID,
    body: PreviewRequest,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Any:
    current.require("notification.template.read")
    row = await get_row(db, TemplateVersion, version_id)
    variant = await get_row(db, TemplateVariant, row.template_variant_id)
    template = await get_row(db, NotificationTemplate, variant.template_id)
    validate_variables(template.variable_schema, body.variables)
    return PreviewResponse(
        subject=render(row.subject_text, body.variables) if row.subject_text else None,
        body=render(row.body_text, body.variables),
        body_html=render_html(row.body_html, body.variables) if row.body_html else None,
    )


@router.get("/variants/{variant_id}/activations", response_model=Page[ActivationItem])
async def activations(
    variant_id: uuid.UUID,
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = None,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Any:
    current.require("notification.template.read")
    await get_row(db, TemplateVariant, variant_id)
    return await page_of(
        db,
        request,
        TemplateActivation,
        ActivationItem,
        limit=limit,
        cursor=cursor,
        where=TemplateActivation.template_variant_id == variant_id,
    )


@router.post("/activations/{activation_id}/end", response_model=ActivationItem)
async def end_activation(
    activation_id: uuid.UUID,
    body: EndWindow,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Any:
    current.require("notification.template.manage")
    row = await get_row(db, TemplateActivation, activation_id, lock=True)
    if row.valid_to is not None or body.valid_to <= row.valid_from or body.valid_to < utcnow():
        raise ConflictError("only an open activation can be ended prospectively")
    row.valid_to = body.valid_to
    return row


@router.get("/template-versions/{version_id}/bindings", response_model=Page[BindingItem])
async def bindings(
    version_id: uuid.UUID,
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = None,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Any:
    current.require("notification.template.read")
    await get_row(db, TemplateVersion, version_id)
    return await page_of(
        db,
        request,
        ProviderTemplateBinding,
        BindingItem,
        limit=limit,
        cursor=cursor,
        where=ProviderTemplateBinding.template_version_id == version_id,
    )


@router.post("/use-case-bindings", response_model=AssignmentItem, status_code=201)
async def assign(
    body: AssignmentCreate, current: Actor = Depends(actor), db: AsyncSession = Depends(session)
) -> Any:
    company_access(current, "notification.template.manage", body.company_id)
    use_case = definition(body.event_key, owner="platform" if current.platform else "tenant")
    if body.trigger_key not in use_case.triggers or body.channel not in use_case.channels:
        raise ValidationFailedError("trigger/channel does not belong to this use case")
    template = await get_row(db, NotificationTemplate, body.template_id, lock=True)
    company_access(current, "notification.template.manage", template.company_id)
    if (
        template.event_key != body.event_key
        or template.category != use_case.category
        or template.company_id not in {SCOPE_ALL, body.company_id}
    ):
        raise ValidationFailedError("template does not match the use case and company")
    # Space row serializes competing assignments even when they choose different templates.
    owner = await db.get(NotificationSpace, current_space(), with_for_update=True)
    if owner is None:
        db.add(
            NotificationSpace(
                id=current_space(),
                tenant_id=current.tenant_id,
                kind="platform" if current.platform else "tenant",
            )
        )
        await db.flush()
    rows = await db.scalars(
        select(UseCaseBinding)
        .where(
            UseCaseBinding.company_id == body.company_id,
            UseCaseBinding.event_key == body.event_key,
            UseCaseBinding.trigger_key == body.trigger_key,
            UseCaseBinding.channel == body.channel,
        )
        .with_for_update()
    )
    if any(
        (r.valid_to is None or body.valid_from < r.valid_to)
        and (body.valid_to is None or r.valid_from < body.valid_to)
        for r in rows
    ):
        raise ConflictError("an assignment already covers this validity window")
    row = UseCaseBinding(
        tenant_id=current.tenant_id, created_by=current.user_id, **body.model_dump()
    )
    db.add(row)
    await db.flush()
    return row


@router.get("/use-case-bindings", response_model=Page[AssignmentItem])
async def assignments(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = None,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Any:
    current.require("notification.template.read")
    return await page_of(db, request, UseCaseBinding, AssignmentItem, limit=limit, cursor=cursor)


@router.post("/use-case-bindings/{binding_id}/end", response_model=AssignmentItem)
async def end_assignment(
    binding_id: uuid.UUID,
    body: EndWindow,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Any:
    current.require_endpoint("notification.template.manage")
    row = await get_row(db, UseCaseBinding, binding_id, lock=True)
    company_access(current, "notification.template.manage", row.company_id)
    if row.valid_to is not None or body.valid_to <= row.valid_from or body.valid_to < utcnow():
        raise ConflictError("assignment must be ended prospectively")
    row.valid_to = body.valid_to
    return row


@router.patch("/routing-rules/{route_id}", response_model=RouteDetail)
async def route_update(
    route_id: uuid.UUID,
    body: RouteUpdate,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Any:
    current.require_endpoint("notification.route.manage")
    row = await get_row(db, RoutingRule, route_id, lock=True)
    company_access(current, "notification.route.manage", row.company_id)
    for key, value in checked_changes(row, body).items():
        if value is None:
            raise ValidationFailedError("route fields cannot be null")
        setattr(row, key, value)
    if row.max_backoff_seconds < row.initial_backoff_seconds:
        raise ValidationFailedError("maximum backoff must not precede initial backoff")
    row.updated_at, row.updated_by = utcnow(), current.user_id
    return row


@router.post("/effective-policy", response_model=EffectiveResult)
async def effective(
    body: EffectivePolicy, current: Actor = Depends(actor), db: AsyncSession = Depends(session)
) -> EffectiveResult:
    company_access(current, "notification.route.read", body.company_id)
    current.require("notification.template.read")
    from notification.tasks.consume import _resolve_route, _resolve_template_version

    use_case = definition(body.event_key, owner="platform" if current.platform else "tenant")
    state = await readiness(db, body.channel)
    version = await _resolve_template_version(
        db,
        company_id=body.company_id,
        event_key=body.event_key,
        trigger_key=body.trigger_key,
        channel=body.channel,
        locale=body.locale,
        now=utcnow(),
    )
    route = await _resolve_route(
        db,
        company_id=body.company_id,
        event_key=body.event_key,
        category=use_case.category,
        channel=body.channel,
        stable_key=body.company_id,
    )
    reasons = list(state.reasons)
    if version is None:
        reasons.append("no_active_template_assignment")
    if route is None:
        reasons.append("no_eligible_route")
    return EffectiveResult(
        ready=not reasons,
        reasons=reasons,
        template_version_id=version.id if version else None,
        route_id=route.id if route else None,
    )


async def request_authority(
    db: AsyncSession, current: Actor, request_id: uuid.UUID
) -> NotificationRequest:
    current.require_endpoint("notification.request.read")
    row = await get_row(db, NotificationRequest, request_id)
    company_access(current, "notification.request.read", row.company_id)
    return row


async def delivery_authority(
    db: AsyncSession, current: Actor, delivery_id: uuid.UUID
) -> NotificationDelivery:
    current.require_endpoint("notification.delivery.read")
    row = await get_row(db, NotificationDelivery, delivery_id)
    req = await get_row(db, NotificationRequest, row.request_id)
    company_access(current, "notification.delivery.read", req.company_id)
    return row


@router.get("/requests/{request_id}", response_model=RequestDetail)
async def request_detail(
    request_id: uuid.UUID, current: Actor = Depends(actor), db: AsyncSession = Depends(session)
) -> Any:
    return await request_authority(db, current, request_id)


@router.get("/requests/{request_id}/outcomes", response_model=Page[PlanningItem])
async def outcomes(
    request_id: uuid.UUID,
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = None,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Any:
    await request_authority(db, current, request_id)
    return await page_of(
        db,
        request,
        PlanningOutcome,
        PlanningItem,
        limit=limit,
        cursor=cursor,
        where=PlanningOutcome.request_id == request_id,
    )


@router.get("/deliveries/{delivery_id}", response_model=DeliveryDetail)
async def delivery_detail(
    delivery_id: uuid.UUID, current: Actor = Depends(actor), db: AsyncSession = Depends(session)
) -> Any:
    return await delivery_authority(db, current, delivery_id)


@router.get("/deliveries/{delivery_id}/attempts", response_model=Page[AttemptItem])
async def attempts(
    delivery_id: uuid.UUID,
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = None,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Any:
    await delivery_authority(db, current, delivery_id)
    return await page_of(
        db,
        request,
        DeliveryAttempt,
        AttemptItem,
        limit=limit,
        cursor=cursor,
        where=DeliveryAttempt.delivery_id == delivery_id,
    )


@router.get("/deliveries/{delivery_id}/events", response_model=Page[EventItem])
async def events(
    delivery_id: uuid.UUID,
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = None,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Any:
    await delivery_authority(db, current, delivery_id)
    return await page_of(
        db,
        request,
        DeliveryEvent,
        EventItem,
        limit=limit,
        cursor=cursor,
        where=DeliveryEvent.delivery_id == delivery_id,
    )


@router.post("/sender-identities/{sender_id}/verify", response_model=JobItem, status_code=202)
async def sender_verify(
    sender_id: uuid.UUID,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
    idempotency_key: str = Header(min_length=1, max_length=200),
) -> Any:
    current.require("notification.provider.manage")
    await get_row(db, SenderIdentity, sender_id)
    return await queue_job(db, current, "sender.verify", sender_id, idempotency_key)


@router.get("/reconciliation-cases", response_model=Page[DeliveryItem])
async def reconciliation_cases(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = None,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Any:
    current.require("notification.delivery.read")
    return await page_of(
        db,
        request,
        NotificationDelivery,
        DeliveryItem,
        limit=limit,
        cursor=cursor,
        where=NotificationDelivery.status == "sending",
    )


@router.post("/deliveries/{delivery_id}/reconciliation", response_model=DeliveryItem)
async def reconcile_receipt(
    delivery_id: uuid.UUID,
    body: ReceiptReconciliation,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
    idempotency_key: str = Header(min_length=1, max_length=200),
) -> Any:
    current.require_endpoint("notification.delivery.retry")
    event = await get_row(db, ProviderEvent, body.provider_event_id, lock=True)
    row = await get_row(db, NotificationDelivery, delivery_id, lock=True)
    source = await get_row(db, NotificationRequest, row.request_id)
    company_access(current, "notification.delivery.retry", source.company_id)
    receipt = await queue_job(
        db,
        current,
        "delivery.reconcile",
        row.id,
        idempotency_key,
        {"provider_event_id": str(body.provider_event_id)},
    )
    if receipt.status == "completed":
        return row
    if (
        not event.signature_verified
        or event.provider_account_id != row.provider_account_id
        or not event.provider_message_id
        or event.delivery_id not in {None, row.id}
        or row.provider_message_id not in {None, event.provider_message_id}
    ):
        raise ValidationFailedError("receipt does not match the delivery provider evidence")
    if row.provider_message_id is None:
        proven = await db.scalar(
            select(DeliveryAttempt.id).where(
                DeliveryAttempt.delivery_id == row.id,
                DeliveryAttempt.provider_account_id == row.provider_account_id,
                DeliveryAttempt.provider_message_id == event.provider_message_id,
            )
        )
        if proven is None:
            raise ValidationFailedError(
                "receipt lacks a message identity proven by this delivery attempt"
            )
    if row.status not in {"sending", "accepted"}:
        raise ConflictError("only an unresolved or accepted delivery can be reconciled")
    row.provider_message_id = event.provider_message_id
    event.delivery_id = row.id
    event.processing_status, event.processed_at = "pending", None
    receipt.status, receipt.completed_at = "completed", utcnow()
    # The normalizer applies signed provider facts; an operator cannot assert
    # delivery success or release an ambiguous send by submitting a free-text reason.
    return row


@router.get(
    "/provider-accounts/{provider_id}/callback-configuration", response_model=CallbackConfiguration
)
async def callback_configuration(
    provider_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> CallbackConfiguration:
    current.require("notification.provider.read")
    row = await get_row(db, ProviderAccount, provider_id)
    origin = request.app.state.settings.callback_public_origin
    url = origin.rstrip("/") + f"/v1/callbacks/{row.channel}/{row.callback_key}" if origin else None
    scheme = {
        "email": "SNS RSA",
        "sms": "X-Twilio-Signature",
        "whatsapp": "X-Hub-Signature-256",
    }.get(row.channel, "provider-native")
    return CallbackConfiguration(url=url, signature_scheme=scheme, ready=url is not None)


@router.get("/variants/{variant_id}", response_model=VariantItem)
async def variant_detail(
    variant_id: uuid.UUID, current: Actor = Depends(actor), db: AsyncSession = Depends(session)
) -> TemplateVariant:
    current.require_endpoint("notification.template.read")
    row = await get_row(db, TemplateVariant, variant_id)
    await template_detail(row.template_id, current, db)
    return row


@router.patch("/variants/{variant_id}", response_model=VariantItem)
async def variant_update(
    variant_id: uuid.UUID,
    body: VariantUpdate,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> TemplateVariant:
    current.require_endpoint("notification.template.manage")
    row = await get_row(db, TemplateVariant, variant_id, lock=True)
    template = await get_row(db, NotificationTemplate, row.template_id)
    company_access(current, "notification.template.manage", template.company_id)
    row.is_active = body.is_active
    return row


@router.get("/routing-rules/{route_id}", response_model=RouteDetail)
async def route_detail(
    route_id: uuid.UUID, current: Actor = Depends(actor), db: AsyncSession = Depends(session)
) -> RoutingRule:
    current.require_endpoint("notification.route.read")
    row = await get_row(db, RoutingRule, route_id)
    company_access(current, "notification.route.read", row.company_id)
    return row


@router.get("/use-case-bindings/{binding_id}", response_model=AssignmentItem)
async def assignment_detail(
    binding_id: uuid.UUID, current: Actor = Depends(actor), db: AsyncSession = Depends(session)
) -> UseCaseBinding:
    current.require_endpoint("notification.template.read")
    row = await get_row(db, UseCaseBinding, binding_id)
    company_access(current, "notification.template.read", row.company_id)
    return row


@router.post("/variants/{variant_id}/activate", response_model=ActivationItem, status_code=201)
async def replace_activation(
    variant_id: uuid.UUID,
    body: ActivationCreate,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
    idempotency_key: str = Header(min_length=1, max_length=200),
) -> TemplateActivation:
    current.require_endpoint("notification.template.manage")
    variant = await get_row(db, TemplateVariant, variant_id, lock=True)
    template = await get_row(db, NotificationTemplate, variant.template_id)
    company_access(current, "notification.template.manage", template.company_id)
    receipt = await queue_job(
        db, current, "template.activate", variant_id, idempotency_key, body.model_dump(mode="json")
    )
    if receipt.status == "completed" and receipt.result_id:
        return await get_row(db, TemplateActivation, receipt.result_id)
    version = await get_row(db, TemplateVersion, body.template_version_id)
    if version.template_variant_id != variant_id or (
        body.valid_to and body.valid_to <= body.valid_from
    ):
        raise ValidationFailedError("activation version/window does not match the variant")
    if body.valid_from < utcnow() - dt.timedelta(seconds=30):
        raise ValidationFailedError("replacement activation must not rewrite history")
    existing = list(
        await db.scalars(
            select(TemplateActivation)
            .where(TemplateActivation.template_variant_id == variant_id)
            .with_for_update()
        )
    )
    for prior in existing:
        if prior.valid_to is not None and prior.valid_to <= body.valid_from:
            continue
        if prior.valid_from >= body.valid_from:
            raise ConflictError("a scheduled activation conflicts with this replacement")
        prior.valid_to = body.valid_from
    row = TemplateActivation(
        id=uuid7(),
        tenant_id=current.tenant_id,
        template_variant_id=variant_id,
        template_version_id=version.id,
        valid_from=body.valid_from,
        valid_to=body.valid_to,
        activated_by=current.user_id,
        activation_reason=body.activation_reason,
    )
    db.add(row)
    receipt.status, receipt.completed_at, receipt.result_id = "completed", utcnow(), row.id
    await db.flush()
    return row
