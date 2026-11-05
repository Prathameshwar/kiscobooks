"""Company contacts and user notification choices, with explicit object authority."""

from __future__ import annotations

import uuid

from billing_platform.authz import ScopePath
from billing_platform.db.types import utcnow
from billing_platform.errors import ConflictError, NotFoundError, ValidationFailedError
from billing_platform.ids import uuid7
from billing_platform.outbox import emit
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.api.auth import Actor, actor
from identity.api.common import load_company
from identity.api.dependencies import session
from identity.api.lifecycle import ToggleRequest
from identity.api.listing import paged
from identity.api.route import ERROR_RESPONSES, StrictRoute
from identity.models import CompanyContact, User, UserNotificationPreference
from identity.models.user_notification_preference import NOTIFICATION_CHANNELS
from identity.schemas.base import Page
from identity.schemas.children import (
    ContactCreate,
    ContactItem,
    ContactUpdate,
    PreferenceItem,
    PreferenceWrite,
)
from identity.services.audit import record

router = APIRouter(prefix="/v1", route_class=StrictRoute, responses=ERROR_RESPONSES)
# Fixed producer vocabulary. Preferences never override Notification consent or suppression.
PREFERENCE_EVENTS = frozenset(
    {"invoice.posted", "invoice.overdue", "payment.received", "company.document.expiring"}
)


async def contact_company(
    db: AsyncSession, current: Actor, company_id: uuid.UUID, write: bool
) -> None:
    current.require_scope(
        "company.update" if write else "company.read", target=ScopePath(company_id=company_id)
    )
    company = await load_company(db, company_id)
    if write and company.status != "active":
        raise ConflictError("company is inactive")


async def contact_row(
    db: AsyncSession, company_id: uuid.UUID, contact_id: uuid.UUID
) -> CompanyContact:
    row = await db.get(CompanyContact, contact_id)
    if row is None or row.company_id != company_id:
        raise NotFoundError("contact not found")
    return row


async def primary_contact(db: AsyncSession, row: CompanyContact, current: Actor) -> None:
    if not row.is_primary or not row.is_active:
        return
    previous = await db.scalars(
        select(CompanyContact).where(
            CompanyContact.company_id == row.company_id,
            CompanyContact.type == row.type,
            CompanyContact.is_active.is_(True),
            CompanyContact.is_primary.is_(True),
            CompanyContact.id != row.id,
        )
    )
    for old in previous:
        old.is_primary, old.updated_by = False, current.user_id
        record(
            db,
            current,
            action="company.contact_updated",
            entity="company_contact",
            entity_id=old.id,
            company_id=row.company_id,
            changes={"is_primary": {"to": False}},
        )


@router.post("/companies/{company_id}/contacts", response_model=ContactItem, status_code=201)
async def create_contact(
    company_id: uuid.UUID,
    body: ContactCreate,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> CompanyContact:
    await contact_company(db, current, company_id, True)
    row = CompanyContact(
        id=uuid7(),
        tenant_id=current.tenant_id,
        company_id=company_id,
        **body.model_dump(),
        is_active=True,
        created_by=current.user_id,
        updated_by=current.user_id,
    )
    await primary_contact(db, row, current)
    db.add(row)
    record(
        db,
        current,
        action="company.contact_created",
        entity="company_contact",
        entity_id=row.id,
        company_id=company_id,
    )
    await db.flush()
    return row


@router.get("/companies/{company_id}/contacts", response_model=Page[ContactItem])
async def contacts(
    company_id: uuid.UUID,
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = None,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[ContactItem]:
    await contact_company(db, current, company_id, False)
    return await paged(
        db,
        request,
        select(CompanyContact).where(CompanyContact.company_id == company_id),
        model=CompanyContact,
        schema=ContactItem,
        limit=limit,
        cursor=cursor,
    )


@router.get("/companies/{company_id}/contacts/{contact_id}", response_model=ContactItem)
async def get_contact(
    company_id: uuid.UUID,
    contact_id: uuid.UUID,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> CompanyContact:
    await contact_company(db, current, company_id, False)
    return await contact_row(db, company_id, contact_id)


@router.put("/companies/{company_id}/contacts/{contact_id}", response_model=ContactItem)
async def update_contact(
    company_id: uuid.UUID,
    contact_id: uuid.UUID,
    body: ContactUpdate,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> CompanyContact:
    await contact_company(db, current, company_id, True)
    row = await contact_row(db, company_id, contact_id)
    if not row.is_active:
        raise ConflictError("contact is inactive")
    changes = {
        k: {"from": getattr(row, k), "to": v}
        for k, v in body.model_dump().items()
        if getattr(row, k) != v
    }
    for key, value in body.model_dump().items():
        setattr(row, key, value)
    await primary_contact(db, row, current)
    if changes:
        row.updated_by = current.user_id
        record(
            db,
            current,
            action="company.contact_updated",
            entity="company_contact",
            entity_id=row.id,
            company_id=company_id,
            changes=changes,
        )
    await db.flush()
    return row


@router.post("/companies/{company_id}/contacts/{contact_id}/lifecycle", response_model=ContactItem)
async def contact_lifecycle(
    company_id: uuid.UUID,
    contact_id: uuid.UUID,
    body: ToggleRequest,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> CompanyContact:
    await contact_company(db, current, company_id, True)
    row = await contact_row(db, company_id, contact_id)
    if row.is_active != body.is_active:
        row.is_active = body.is_active
        row.deactivated_at = None if body.is_active else utcnow()
        row.deactivated_by = None if body.is_active else current.user_id
        row.updated_by = current.user_id
        if not body.is_active:
            row.is_primary = False
        record(
            db,
            current,
            action="company.contact_lifecycle_changed",
            entity="company_contact",
            entity_id=row.id,
            company_id=company_id,
            reason=body.reason,
            changes={"is_active": {"to": body.is_active}},
        )
    await db.flush()
    return row


async def preference_user(
    db: AsyncSession, current: Actor, user_id: uuid.UUID, write: bool
) -> None:
    # Authenticated self-service; editing somebody else requires tenant administration.
    if current.user_id != user_id:
        current.require_scope("user.update" if write else "user.read", target=ScopePath())
    user = await db.get(User, user_id)
    if user is None:
        raise NotFoundError("user not found")
    if write and user.status != "active":
        raise ConflictError("user is inactive")


@router.get("/users/{user_id}/notification-preferences", response_model=Page[PreferenceItem])
async def preferences(
    user_id: uuid.UUID,
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = None,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> Page[PreferenceItem]:
    await preference_user(db, current, user_id, False)
    return await paged(
        db,
        request,
        select(UserNotificationPreference).where(UserNotificationPreference.user_id == user_id),
        model=UserNotificationPreference,
        schema=PreferenceItem,
        limit=limit,
        cursor=cursor,
    )


@router.put(
    "/users/{user_id}/notification-preferences/{event_key}/{channel}", response_model=PreferenceItem
)
async def set_preference(
    user_id: uuid.UUID,
    event_key: str,
    channel: str,
    body: PreferenceWrite,
    current: Actor = Depends(actor),
    db: AsyncSession = Depends(session),
) -> UserNotificationPreference:
    await preference_user(db, current, user_id, True)
    if channel not in NOTIFICATION_CHANNELS or event_key not in PREFERENCE_EVENTS:
        raise ValidationFailedError("unsupported notification event or channel")
    row = await db.scalar(
        select(UserNotificationPreference).where(
            UserNotificationPreference.user_id == user_id,
            UserNotificationPreference.channel == channel,
            UserNotificationPreference.event_key == event_key,
        )
    )
    if row is not None and row.is_enabled == body.is_enabled:
        return row
    if row is None:
        row = UserNotificationPreference(
            id=uuid7(),
            tenant_id=current.tenant_id,
            user_id=user_id,
            channel=channel,
            event_key=event_key,
            is_enabled=body.is_enabled,
            source_version=1,
        )
        db.add(row)
    else:
        row.is_enabled = body.is_enabled
        row.source_version += 1
    emit(
        db,
        tenant_id=current.tenant_id,
        aggregate_type="user_notification_preference",
        aggregate_id=row.id,
        event_type="user_notification_preference.changed",
        payload={
            "subject_type": "user",
            "subject_id": str(user_id),
            "event_key": event_key,
            "channel": channel,
            "is_enabled": row.is_enabled,
            "source_version": row.source_version,
            "source_updated_at": utcnow().isoformat(),
        },
    )
    record(
        db,
        current,
        action="user.notification_preference_updated",
        entity="user_notification_preference",
        entity_id=row.id,
    )
    await db.flush()
    return row
