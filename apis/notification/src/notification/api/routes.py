from __future__ import annotations

import datetime as dt
import uuid

from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, NotFoundError, ValidationFailedError
from billing_platform.ids import uuid7
from billing_platform.outbox import emit
from billing_platform.pagination import CursorCodec, PageRequest, validate_sort
from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only

from notification.api.auth import Actor, actor
from notification.api.dependencies import session
from notification.api.route import ERROR_RESPONSES, StrictRoute
from notification.api.schemas import (
    DeliveryItem,
    DeliveryPage,
    PageMeta,
    ProviderCreate,
    ProviderDetail,
    ProviderItem,
    ProviderPage,
    ProviderUpdate,
    RequestItem,
    RequestPage,
)
from notification.credentials import validate_reference
from notification.domain.catalogue import PROVIDERS
from notification.domain.constants import CHANNELS
from notification.models import (
    DeliveryEvent,
    NotificationContent,
    NotificationDelivery,
    NotificationRequest,
    ProviderAccount,
    SenderIdentity,
)

router = APIRouter(route_class=StrictRoute, responses=ERROR_RESPONSES)


def _codec(request: Request, context: str) -> CursorCodec:
    from notification.api.listing import cursor_codec

    return cursor_codec(request, context)


@router.post(
    "/provider-accounts", response_model=ProviderDetail, status_code=status.HTTP_201_CREATED
)
async def create_provider(
    body: ProviderCreate,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> ProviderAccount:
    current.require("notification.provider.manage")
    if body.channel not in CHANNELS:
        raise ValidationFailedError(
            "unsupported channel", fields={"channel": "email, sms, whatsapp, or push"}
        )
    if body.callback_secret_ref is None and body.provider_key not in {"ses", "fcm"}:
        raise ValidationFailedError("callback verifier configuration is required")
    if PROVIDERS.get(body.provider_key) != body.channel:
        raise ValidationFailedError("unsupported provider/channel combination")
    validate_reference(request.app.state.settings, body.credential_ref, current.tenant_id)
    validate_reference(request.app.state.settings, body.callback_secret_ref, current.tenant_id)
    if body.capabilities is not None:
        validate_reference(
            request.app.state.settings, body.capabilities.verification_token_ref, current.tenant_id
        )
    now = utcnow()
    row = ProviderAccount(
        id=uuid7(),
        tenant_id=current.tenant_id,
        status="pending",
        created_at=now,
        created_by=current.user_id,
        updated_at=now,
        updated_by=current.user_id,
        **body.model_dump(),
    )
    db.add(row)
    await db.flush()
    return row


@router.get("/provider-accounts/{provider_id}", response_model=ProviderDetail)
async def get_provider(
    provider_id: uuid.UUID, current: Actor = Depends(actor), db: AsyncSession = Depends(session)
) -> ProviderAccount:
    current.require("notification.provider.read")
    row = await db.get(ProviderAccount, provider_id)
    if row is None:
        raise NotFoundError("provider account not found")
    return row


@router.patch("/provider-accounts/{provider_id}", response_model=ProviderDetail)
async def update_provider(
    provider_id: uuid.UUID,
    body: ProviderUpdate,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> ProviderAccount:
    current.require("notification.provider.manage")
    row = await db.get(ProviderAccount, provider_id, with_for_update=True)
    if row is None:
        raise NotFoundError("provider account not found")
    from notification.api.control import checked_changes

    changes = checked_changes(row, body)
    if changes.get("status") == "active" and row.status != "active":
        raise ValidationFailedError("use the provider validation job before activation")
    verifier_ref = changes.get("callback_secret_ref", row.callback_secret_ref)
    if verifier_ref is None and row.provider_key not in {"ses", "fcm"}:
        raise ValidationFailedError("callback verifier configuration is required")
    for reference in (changes.get("credential_ref"), changes.get("callback_secret_ref")):
        validate_reference(request.app.state.settings, reference, current.tenant_id)
    capabilities = changes.get("capabilities")
    if capabilities:
        validate_reference(
            request.app.state.settings,
            capabilities.get("verification_token_ref"),
            current.tenant_id,
        )
    if any(
        name in changes and changes[name] != getattr(row, name)
        for name in ("credential_ref", "region")
    ):
        senders = list(
            await db.scalars(
                select(SenderIdentity)
                .where(
                    SenderIdentity.provider_account_id == row.id,
                    SenderIdentity.verification_status != "unverified",
                )
                .limit(201)
            )
        )
        if len(senders) > 200:
            raise ConflictError(
                "reset verification before rotating an account with over 200 verified senders"
            )
        for sender in senders:
            sender.verification_status, sender.verified_at = "unverified", None
            sender.updated_at, sender.updated_by = utcnow(), current.user_id
        changes["status"] = "pending"
    for name, value in changes.items():
        setattr(row, name, value)
    row.updated_at = utcnow()
    row.updated_by = current.user_id
    await db.flush()
    return row


@router.delete("/provider-accounts/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
async def disable_provider(
    provider_id: uuid.UUID, current: Actor = Depends(actor), db: AsyncSession = Depends(session)
) -> Response:
    current.require("notification.provider.manage")
    row = await db.get(ProviderAccount, provider_id)
    if row is None:
        raise NotFoundError("provider account not found")
    row.status = "disabled"
    row.updated_at = utcnow()
    row.updated_by = current.user_id
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/provider-accounts", response_model=ProviderPage)
async def list_providers(
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = None,
    channel: str | None = None,
    provider_status: str | None = Query(None, alias="status"),
    q: str | None = Query(None, min_length=2, max_length=100),
    sort: str = "-updated_at",
) -> ProviderPage:
    current.require("notification.provider.read")
    page = PageRequest(limit, cursor)
    field, descending = validate_sort(
        sort, allowed=frozenset({"updated_at", "display_name"}), default="-updated_at"
    )
    sort_column = getattr(ProviderAccount, field)
    statement = select(ProviderAccount).options(
        load_only(*(getattr(ProviderAccount, name) for name in ProviderItem.model_fields))
    )
    if channel:
        statement = statement.where(ProviderAccount.channel == channel)
    if provider_status:
        statement = statement.where(ProviderAccount.status == provider_status)
    if q:
        escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        statement = statement.where(
            or_(
                ProviderAccount.key.like(f"{escaped}%", escape="\\"),
                ProviderAccount.display_name.like(f"{escaped}%", escape="\\"),
            )
        )
    codec = _codec(request, "provider-accounts")
    if page.cursor:
        values = codec.decode(page.cursor)
        pivot, pivot_id = values[field], uuid.UUID(values["id"])
        if field == "updated_at":
            pivot = dt.datetime.fromisoformat(pivot)
        comparison = sort_column < pivot if descending else sort_column > pivot
        statement = statement.where(
            or_(comparison, and_(sort_column == pivot, ProviderAccount.id > pivot_id))
        )
    order = sort_column.desc() if descending else sort_column.asc()
    rows = list(
        (
            await db.scalars(
                statement.order_by(order, ProviderAccount.id.asc()).limit(page.limit + 1)
            )
        ).all()
    )
    has_more = len(rows) > page.limit
    rows = rows[: page.limit]
    next_cursor = None
    if has_more:
        last = rows[-1]
        value = getattr(last, field)
        next_cursor = codec.encode(
            {
                field: value.isoformat() if isinstance(value, dt.datetime) else value,
                "id": str(last.id),
            }
        )
    return ProviderPage(
        items=[ProviderItem.model_validate(row) for row in rows],
        page=PageMeta(next_cursor=next_cursor, has_more=has_more),
    )


@router.get("/requests", response_model=RequestPage)
async def list_requests(
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = None,
    request_status: str | None = Query(None, alias="status"),
    event_key: str | None = None,
) -> RequestPage:
    current.require("notification.request.read")
    statement = select(NotificationRequest).options(
        load_only(*(getattr(NotificationRequest, name) for name in RequestItem.model_fields))
    )
    if request_status:
        statement = statement.where(NotificationRequest.status == request_status)
    if event_key:
        statement = statement.where(NotificationRequest.event_key == event_key)
    codec = _codec(request, "requests")
    if cursor:
        values = codec.decode(cursor)
        pivot = dt.datetime.fromisoformat(values["received_at"])
        pivot_id = uuid.UUID(values["id"])
        statement = statement.where(
            or_(
                NotificationRequest.received_at < pivot,
                and_(NotificationRequest.received_at == pivot, NotificationRequest.id > pivot_id),
            )
        )
    rows = list(
        (
            await db.scalars(
                statement.order_by(
                    NotificationRequest.received_at.desc(), NotificationRequest.id.asc()
                ).limit(limit + 1)
            )
        ).all()
    )
    has_more = len(rows) > limit
    rows = rows[:limit]
    token = (
        codec.encode({"received_at": rows[-1].received_at.isoformat(), "id": str(rows[-1].id)})
        if has_more
        else None
    )
    return RequestPage(
        items=[RequestItem.model_validate(row) for row in rows],
        page=PageMeta(next_cursor=token, has_more=has_more),
    )


@router.get("/deliveries", response_model=DeliveryPage)
async def list_deliveries(
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = None,
    delivery_status: str | None = Query(None, alias="status"),
    channel: str | None = None,
    request_id: uuid.UUID | None = None,
) -> DeliveryPage:
    current.require("notification.delivery.read")
    statement = select(NotificationDelivery).options(
        load_only(*(getattr(NotificationDelivery, name) for name in DeliveryItem.model_fields))
    )
    if delivery_status:
        statement = statement.where(NotificationDelivery.status == delivery_status)
    if channel:
        statement = statement.where(NotificationDelivery.channel == channel)
    if request_id:
        statement = statement.where(NotificationDelivery.request_id == request_id)
    codec = _codec(request, "deliveries")
    if cursor:
        values = codec.decode(cursor)
        pivot = dt.datetime.fromisoformat(values["created_at"])
        pivot_id = uuid.UUID(values["id"])
        statement = statement.where(
            or_(
                NotificationDelivery.created_at < pivot,
                and_(NotificationDelivery.created_at == pivot, NotificationDelivery.id > pivot_id),
            )
        )
    rows = list(
        (
            await db.scalars(
                statement.order_by(
                    NotificationDelivery.created_at.desc(), NotificationDelivery.id.asc()
                ).limit(limit + 1)
            )
        ).all()
    )
    has_more = len(rows) > limit
    rows = rows[:limit]
    token = (
        codec.encode({"created_at": rows[-1].created_at.isoformat(), "id": str(rows[-1].id)})
        if has_more
        else None
    )
    return DeliveryPage(
        items=[DeliveryItem.model_validate(row) for row in rows],
        page=PageMeta(next_cursor=token, has_more=has_more),
    )


@router.post("/deliveries/{delivery_id}/retry", response_model=DeliveryItem)
async def retry_delivery(
    delivery_id: uuid.UUID,
    idempotency_key: str = Header(min_length=1, max_length=200),
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> NotificationDelivery:
    current.require("notification.delivery.retry")
    delivery = await db.get(NotificationDelivery, delivery_id, with_for_update=True)
    if delivery is None:
        raise NotFoundError("delivery not found")
    from notification.api.control import queue_job

    receipt = await queue_job(db, current, "delivery.retry", delivery.id, idempotency_key)
    if receipt.status == "completed":
        return delivery
    request_row = await db.get(NotificationRequest, delivery.request_id)
    content = await db.get(NotificationContent, delivery.id)
    now = utcnow()
    if (
        request_row is None
        or (request_row.expires_at and request_row.expires_at <= now)
        or content is None
        or content.purged_at is not None
        or content.expires_at <= now
    ):
        raise ConflictError("expired or purged delivery content cannot be retried")
    if delivery.status not in {"failed", "expired"}:
        raise ConflictError(
            f"only failed or expired deliveries can be retried (current status: {delivery.status})"
        )
    previous = delivery.status
    now = utcnow()
    delivery.status = "pending"
    receipt.status, receipt.completed_at = "completed", now
    delivery.status_reason = "manual_retry"
    # Previous attempt identities remain on immutable attempt rows. A delayed old
    # failure receipt must not terminate the new send cycle.
    delivery.provider_message_id = None
    delivery.next_attempt_at = now
    delivery.failed_at = None
    delivery.completed_at = None
    delivery.updated_at = now
    db.add(
        DeliveryEvent(
            id=uuid7(),
            tenant_id=current.tenant_id,
            delivery_id=delivery.id,
            source="manual_retry",
            source_event_key=f"{delivery.id}:retry:{uuid7()}",
            from_status=previous,
            to_status="pending",
            reason_code="manual_retry",
            provider_occurred_at=None,
            observed_at=now,
            metadata_json={"attempt_count": delivery.attempt_count},
        )
    )
    emit(
        db,
        aggregate_type="notification_delivery",
        aggregate_id=delivery.id,
        event_type="notification.delivery.status_changed",
        tenant_id=current.tenant_id,
        payload={
            "delivery_id": str(delivery.id),
            "request_id": str(delivery.request_id),
            "from_status": previous,
            "to_status": "pending",
            "reason_code": "manual_retry",
        },
    )
    await db.flush()
    return delivery


@router.get(
    "/companies/{company_id}/vouchers/{voucher_id}/requests",
    response_model=RequestPage,
)
async def voucher_requests(
    company_id: uuid.UUID,
    voucher_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = None,
) -> RequestPage:
    current.require_company("notification.request.read", company_id)
    statement = (
        select(NotificationRequest)
        .options(
            load_only(*(getattr(NotificationRequest, name) for name in RequestItem.model_fields))
        )
        .where(
            NotificationRequest.company_id == company_id,
            NotificationRequest.aggregate_type == "voucher",
            NotificationRequest.aggregate_id == voucher_id,
            NotificationRequest.source_service == "vouchers",
        )
    )
    codec = _codec(request, f"voucher-requests:{company_id}:{voucher_id}")
    if cursor:
        values = codec.decode(cursor)
        pivot = dt.datetime.fromisoformat(values["received_at"])
        pivot_id = uuid.UUID(values["id"])
        statement = statement.where(
            or_(
                NotificationRequest.received_at < pivot,
                and_(NotificationRequest.received_at == pivot, NotificationRequest.id > pivot_id),
            )
        )
    rows = list(
        (
            await db.scalars(
                statement.order_by(
                    NotificationRequest.received_at.desc(),
                    NotificationRequest.id.asc(),
                ).limit(limit + 1)
            )
        ).all()
    )
    has_more = len(rows) > limit
    rows = rows[:limit]
    token = (
        codec.encode(
            {
                "received_at": rows[-1].received_at.isoformat(),
                "id": str(rows[-1].id),
            }
        )
        if has_more
        else None
    )
    return RequestPage(
        items=[RequestItem.model_validate(row) for row in rows],
        page=PageMeta(next_cursor=token, has_more=has_more),
    )


@router.get(
    "/companies/{company_id}/vouchers/{voucher_id}/deliveries",
    response_model=DeliveryPage,
)
async def voucher_deliveries(
    company_id: uuid.UUID,
    voucher_id: uuid.UUID,
    request: Request,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = None,
) -> DeliveryPage:
    current.require_company("notification.delivery.read", company_id)
    statement = (
        select(NotificationDelivery)
        .options(
            load_only(*(getattr(NotificationDelivery, name) for name in DeliveryItem.model_fields))
        )
        .join(
            NotificationRequest,
            NotificationRequest.id == NotificationDelivery.request_id,
        )
        .where(
            NotificationRequest.company_id == company_id,
            NotificationRequest.aggregate_type == "voucher",
            NotificationRequest.aggregate_id == voucher_id,
            NotificationRequest.source_service == "vouchers",
        )
    )
    codec = _codec(request, f"voucher-deliveries:{company_id}:{voucher_id}")
    if cursor:
        values = codec.decode(cursor)
        pivot = dt.datetime.fromisoformat(values["created_at"])
        pivot_id = uuid.UUID(values["id"])
        statement = statement.where(
            or_(
                NotificationDelivery.created_at < pivot,
                and_(NotificationDelivery.created_at == pivot, NotificationDelivery.id > pivot_id),
            )
        )
    rows = list(
        (
            await db.scalars(
                statement.order_by(
                    NotificationDelivery.created_at.desc(),
                    NotificationDelivery.id.asc(),
                ).limit(limit + 1)
            )
        ).all()
    )
    has_more = len(rows) > limit
    rows = rows[:limit]
    token = (
        codec.encode(
            {
                "created_at": rows[-1].created_at.isoformat(),
                "id": str(rows[-1].id),
            }
        )
        if has_more
        else None
    )
    return DeliveryPage(
        items=[DeliveryItem.model_validate(row) for row in rows],
        page=PageMeta(next_cursor=token, has_more=has_more),
    )
